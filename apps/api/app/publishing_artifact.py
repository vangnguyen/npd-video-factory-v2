"""Private approved-artifact admission; bounded storage, real QC, verified ranges."""
from contextlib import asynccontextmanager, suppress
import asyncio
import hashlib
import logging
import os
from pathlib import Path, PurePosixPath
import stat
import tempfile
import threading
import time

from botocore.config import Config

from .db import AssetORM
from .object_storage import LocalObjectStorageProvider, S3ObjectStorageProvider, validate_object_key
from .production_db import ProductionRenderJobORM
from .production_logic import PROFILE_DIMENSIONS
from .production_qc import FullProductionQC, ProductionQCError
from .publishing_db import PublicationDispatchORM
from .publishing_dispatch import PublishingDispatchJournal
from .publishing_wire import _PrivacyFilter, _sensitive
from .timeline_db import TimelineVersionORM
from .timeline_models import TimelineSnapshot


BLOCK = 256 * 1024
MAX_BYTES = 512 * 1024 * 1024


class ArtifactAdmissionError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def publishing_storage_config():
    """Opt-in SDK profile for this reader; existing storage defaults stay intact."""
    return Config(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': 1})


def guarded_path(value, *, directory=False):
    path = Path(value).absolute()
    if '..' in path.parts: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_PATH_INVALID')
    try:
        for part in (*reversed(path.parents), path):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 1024:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_LINK_REJECTED')
        info = path.lstat()
        if (directory and not stat.S_ISDIR(info.st_mode)) or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1)):
            raise ArtifactAdmissionError('PUBLISH_ARTIFACT_PATH_INVALID')
        return path
    except OSError: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_PATH_UNAVAILABLE') from None


def bounded_copy(storage, object_key, destination, expected_size, cancellation=None):
    """Only already configured local/S3 objects; no bucket creation or URL fallback."""
    stream = None; privacy = None; deadline = time.monotonic() + 120
    try:
        if type(expected_size) is not int or not 1 <= expected_size <= MAX_BYTES:
            raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
        object_key = validate_object_key(object_key)
        if isinstance(storage, LocalObjectStorageProvider):
            source = guarded_path(storage.root / Path(*PurePosixPath(object_key).parts))
            stream = source.open('rb')
            if os.fstat(stream.fileno()).st_size != expected_size:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
        elif isinstance(storage, S3ObjectStorageProvider):
            config = storage.client.meta.config
            retries = config.retries or {}
            if (not 0 < config.connect_timeout <= 5 or not 0 < config.read_timeout <= 30
                or not (retries.get('total_max_attempts') == 1 or ('total_max_attempts' not in retries and retries.get('max_attempts') == 0))):
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_S3_BOUNDED_CLIENT_REQUIRED')
            # The SDK can log signed headers/URLs at DEBUG. Suppress only this
            # thread's private storage operation, leaving unrelated logs intact.
            names = {'botocore', 'boto3', 's3transfer', 'urllib3', 'urllib3.connectionpool'}
            names.update(name for name in logging.Logger.manager.loggerDict if name.startswith(('botocore.', 'boto3.', 's3transfer.', 'urllib3.')))
            for name in names:
                logger = logging.getLogger(name)
                if not any(isinstance(value, _PrivacyFilter) for value in logger.filters): logger.addFilter(_PrivacyFilter())
            privacy = _sensitive.set(True)
            response = storage.client.get_object(Bucket=storage.bucket, Key=object_key)
            stream = response.get('Body')
            if stream is None or type(response.get('ContentLength')) is not int or response['ContentLength'] != expected_size:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
        else: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_STORAGE_NOT_CONFIGURED')
        count = 0
        with destination.open('xb') as output:
            while True:
                if cancellation is not None and cancellation.is_set(): raise ArtifactAdmissionError('PUBLISH_ARTIFACT_READ_CANCELLED')
                if time.monotonic() >= deadline: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_READ_TIMEOUT')
                content = stream.read(min(BLOCK, expected_size - count + 1))
                if not isinstance(content, bytes): raise ArtifactAdmissionError('PUBLISH_ARTIFACT_STREAM_INVALID')
                if not content: break
                count += len(content)
                if count > expected_size: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
                output.write(content)
            if count != expected_size: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
            output.flush(); os.fsync(output.fileno())
    except ArtifactAdmissionError: raise
    except Exception: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_STORAGE_READ_FAILED') from None
    finally:
        if stream is not None:
            with suppress(Exception): stream.close()
        if privacy is not None: _sensitive.reset(privacy)


class VerifiedPublishingArtifact:
    """Internal worker object; no file path, content or manifest in repr/public API."""
    def __init__(self, path, *, expected_sha256, expected_size, binding_sha256):
        self._path = guarded_path(path); self._lock = threading.RLock(); self._file = self._path.open('rb')
        self.sha256, self.size_bytes, self.binding_sha256 = expected_sha256, expected_size, binding_sha256
        digest = hashlib.sha256(); hashes = []; count = 0
        try:
            if type(expected_size) is not int or not 1 <= expected_size <= MAX_BYTES:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
            if self._file.read(12)[4:8] != b'ftyp': raise ArtifactAdmissionError('PUBLISH_ARTIFACT_MP4_REQUIRED')
            self._file.seek(0)
            while chunk := self._file.read(BLOCK):
                count += len(chunk)
                if count > expected_size: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SIZE_MISMATCH')
                digest.update(chunk); hashes.append(hashlib.sha256(chunk).digest())
            if count != expected_size or digest.hexdigest() != expected_sha256:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_CHECKSUM_MISMATCH')
            self._hashes = tuple(hashes)
        except BaseException:
            self._file.close(); raise

    def read(self, offset, length):
        if type(offset) is not int or type(length) is not int or offset < 0 or not 1 <= length <= 16 * 1024 * 1024 or offset + length > self.size_bytes:
            raise ArtifactAdmissionError('PUBLISH_ARTIFACT_RANGE_INVALID')
        with self._lock:
            if self._file.closed: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_CLOSED')
            if os.fstat(self._file.fileno()).st_size != self.size_bytes:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_CHANGED')
            first, last = offset // BLOCK, (offset + length - 1) // BLOCK
            verified = bytearray()
            for index in range(first, last + 1):
                self._file.seek(index * BLOCK); chunk = self._file.read(min(BLOCK, self.size_bytes - index * BLOCK))
                if hashlib.sha256(chunk).digest() != self._hashes[index]:
                    raise ArtifactAdmissionError('PUBLISH_ARTIFACT_CHANGED')
                verified.extend(chunk)
            start = offset - first * BLOCK
            return bytes(verified[start:start + length])

    def close(self):
        with self._lock: self._file.close()


class PublishingArtifactGuard:
    def __init__(self, journal: PublishingDispatchJournal, storage, work_root, *, ffprobe_path='ffprobe', ffmpeg_path='ffmpeg'):
        self.journal, self.storage, self.work_root = journal, storage, Path(work_root)
        self.qc = FullProductionQC(ffprobe_path=ffprobe_path, ffmpeg_path=ffmpeg_path)

    async def context(self, workspace, publication_id):
        async with self.journal.session_factory() as session:
            parent = await self.journal.parent(session, workspace, publication_id)
            dispatch = await session.get(PublicationDispatchORM, publication_id)
            if dispatch is None or dispatch.workspace_id != workspace:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_DISPATCH_REQUIRED')
            grant = await self.journal.valid_grant(session, parent, dispatch.publish_approval_id)
            asset = await session.get(AssetORM, parent.output_asset_id)
            render = await session.get(ProductionRenderJobORM, parent.final_render_id)
            timeline = await session.get(TimelineVersionORM, render.timeline_version_id)
            if timeline is None or timeline.project_id != parent.project_id or render.profile.startswith('review-') or render.profile not in PROFILE_DIMENSIONS:
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_FINAL_PROFILE_REQUIRED')
            try:
                key = validate_object_key(asset.object_key)
                snapshot = TimelineSnapshot.model_validate(timeline.snapshot_json)
            except Exception: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_SOURCE_INVALID') from None
            prefix = f'workspaces/{workspace}/projects/{parent.project_id}/'
            if not key.startswith(prefix) or asset.storage_provider != getattr(self.storage, 'name', None):
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_STORAGE_SCOPE_INVALID')
            return {'binding': dict(grant.binding_json), 'binding_sha256': grant.binding_sha256, 'object_key': key,
                'duration': snapshot.duration_seconds, 'fps': snapshot.fps, 'dimensions': PROFILE_DIMENSIONS[render.profile],
                'subtitle_qc': render.qc_report_json.get('subtitle_bounds') or {}, 'timeline_qc': render.qc_report_json.get('timeline') or {}}

    @asynccontextmanager
    async def open(self, workspace, publication_id):
        context = await self.context(workspace, publication_id)
        work_root = guarded_path(self.work_root, directory=True)
        with tempfile.TemporaryDirectory(prefix='vf-publish-', dir=work_root) as owned:
            owned_path = guarded_path(owned, directory=True)
            if owned_path.parent != work_root or owned_path.resolve().parent != work_root.resolve():
                raise ArtifactAdmissionError('PUBLISH_ARTIFACT_PRIVATE_ROOT_INVALID')
            path = owned_path / 'artifact.mp4'; size = context['binding']['total_bytes']; snapshot = None
            cancellation = threading.Event()
            task = asyncio.create_task(asyncio.to_thread(bounded_copy, self.storage, context['object_key'], path, size, cancellation))
            try:
                await asyncio.shield(task)
            except BaseException:
                # A cancelled caller cannot leave a thread writing after private cleanup.
                cancellation.set()
                while not task.done():
                    try: await asyncio.shield(task)
                    except asyncio.CancelledError: continue
                    except Exception: break
                with suppress(Exception, asyncio.CancelledError): await task
                raise
            try:
                snapshot = VerifiedPublishingArtifact(path, expected_sha256=context['binding']['artifact_sha256'],
                    expected_size=size, binding_sha256=context['binding_sha256'])
                width, height = context['dimensions']
                try:
                    qc = await self.qc.inspect(path, expected_duration=context['duration'], expected_width=width,
                        expected_height=height, expected_fps=context['fps'], subtitle_qc=context['subtitle_qc'], timeline_qc=context['timeline_qc'])
                except ProductionQCError: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_QC_FAILED') from None
                except OSError: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_QC_TOOLS_NOT_CONFIGURED') from None
                if qc.get('status') != 'passed' or qc.get('checksum_sha256') != snapshot.sha256:
                    raise ArtifactAdmissionError('PUBLISH_ARTIFACT_QC_FAILED')
                fresh = await self.context(workspace, publication_id)
                if fresh != context: raise ArtifactAdmissionError('PUBLISH_ARTIFACT_BINDING_CHANGED')
                snapshot.qc_report = qc  # Actual quality facts; the report grants no publish authority.
                yield snapshot
            finally:
                if snapshot is not None: snapshot.close()
