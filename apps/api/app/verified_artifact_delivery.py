"""Recorded output-byte delivery; no source trust, approval or provider dispatch."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
import stat
import tempfile
from datetime import date, datetime
from decimal import Decimal

import anyio
from starlette.datastructures import MutableHeaders
from starlette.responses import FileResponse
from secrets import token_hex
from sqlalchemy import select

from .bounded_storage_download import StorageDownloadError
from .frozen_storage_read import completed_read, asset_custody
from .object_storage import filesystem_path, validate_object_key, download_cancellation_is_drained
from .db import AssetORM, VideoProjectORM, JobORM


class ArtifactDeliveryRejected(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def scalar_record(row):
    """Private value snapshot, never an ORM reference or public response body."""
    def value(item):
        if isinstance(item,(date,datetime)):return item.isoformat()
        if isinstance(item,Decimal):return str(item)
        if isinstance(item,dict):return {key:value(v) for key,v in item.items()}
        if isinstance(item,list):return [value(v) for v in item]
        return item
    return {column.key:value(getattr(row,column.key)) for column in row.__table__.columns}


def asset_output_identity(asset):
    return {**asset_custody(asset), 'filename':asset.filename}


async def output_sql_snapshot(session_factory, model, identity_column, identity, *, project_id, workspace_id):
    """Owner/output/asset/project are one SQL statement's coherent snapshot."""
    async with session_factory() as session:
        result = (await session.execute(select(model,AssetORM,VideoProjectORM.workspace_id)
            .join(AssetORM,model.output_asset_id==AssetORM.asset_id)
            .join(VideoProjectORM,model.project_id==VideoProjectORM.project_id)
            .where(identity_column==identity,model.project_id==project_id,model.workspace_id==workspace_id,
                AssetORM.project_id==project_id,AssetORM.workspace_id==workspace_id,
                VideoProjectORM.workspace_id==workspace_id))).one_or_none()
        if result is None:return None
        parent,asset,_ = result
        return {'parent':scalar_record(parent),'asset':asset_output_identity(asset)}


async def legacy_sql_snapshot(session_factory, job_id):
    async with session_factory() as session:
        result = (await session.execute(select(JobORM,VideoProjectORM.workspace_id)
            .join(VideoProjectORM,JobORM.project_id==VideoProjectORM.project_id)
            .where(JobORM.job_id==job_id,JobORM.workspace_id==VideoProjectORM.workspace_id))).one_or_none()
        return scalar_record(result[0]) if result is not None else None


@dataclass(frozen=True)
class RecordedArtifactRead:
    """Nonnegative server output proof; an empty artifact is explicit, not a source."""
    object_key: str
    workspace_id: str
    project_id: str
    size_bytes: int
    checksum_sha256: str
    storage_provider: str
    allow_empty: bool = False

    def __post_init__(self):
        if (type(self.size_bytes) is not int or self.size_bytes < 0 or type(self.allow_empty) is not bool
                or self.size_bytes == 0 and not self.allow_empty
                or not isinstance(self.checksum_sha256, str)
                or re.fullmatch('[a-f0-9]{64}', self.checksum_sha256) is None
                or self.size_bytes == 0 and self.checksum_sha256 != hashlib.sha256(b'').hexdigest()
                or any(not isinstance(value, str) or not value for value in (
                    self.object_key, self.workspace_id, self.project_id, self.storage_provider))
                or any('/' in value or '\\' in value for value in (self.workspace_id, self.project_id))):
            raise ArtifactDeliveryRejected('ARTIFACT_READ_PROOF_INVALID')
        try:
            key = validate_object_key(self.object_key)
        except (TypeError, ValueError):
            raise ArtifactDeliveryRejected('ARTIFACT_READ_PROOF_INVALID') from None
        if key != self.object_key or not key.startswith(self.prefix):
            raise ArtifactDeliveryRejected('ARTIFACT_READ_SCOPE_CHANGED')

    @property
    def prefix(self):
        return f'workspaces/{self.workspace_id}/projects/{self.project_id}/'

    @property
    def maximum(self):
        # Preserve all registered output sizes. Empty artifacts still have a
        # positive transfer ceiling and an exact zero-size/empty-SHA proof.
        return max(1, self.size_bytes)

    async def download(self, storage, destination):
        if storage.name != self.storage_provider:
            raise ArtifactDeliveryRejected('ARTIFACT_READ_PROVIDER_CHANGED')
        await completed_read(storage.download_file(object_key=self.object_key, destination=destination,
            max_bytes=self.maximum, expected_size_bytes=self.size_bytes,
            expected_sha256=self.checksum_sha256, expected_prefix=self.prefix),
            cancel_operation=download_cancellation_is_drained(storage))


def output_asset_read(asset, *, workspace_id, project_id, storage, kind):
    if (asset.workspace_id != workspace_id or asset.project_id != project_id
            or asset.asset_class != 'render' or asset.kind != kind or asset.content_type != 'video/mp4'):
        raise ArtifactDeliveryRejected('ARTIFACT_OUTPUT_ASSET_CHANGED')
    proof = RecordedArtifactRead(asset.object_key, workspace_id, project_id,
        asset.size_bytes, asset.checksum_sha256, asset.storage_provider)
    if storage.name != proof.storage_provider:
        raise ArtifactDeliveryRejected('ARTIFACT_READ_PROVIDER_CHANGED')
    return proof


def verified_output_handle(path, proof):
    handle = None
    try:
        if path.is_symlink():
            raise ArtifactDeliveryRejected('ARTIFACT_STAGED_FILE_CHANGED')
        handle = filesystem_path(path).open('rb')
        before = os.fstat(handle.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size != proof.size_bytes:
            raise ArtifactDeliveryRejected('ARTIFACT_BYTES_CHANGED')
        checksum = hashlib.sha256()
        for chunk in iter(lambda:handle.read(128*1024), b''):
            checksum.update(chunk)
        after = os.fstat(handle.fileno())
        if checksum.hexdigest() != proof.checksum_sha256 or (
                before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ArtifactDeliveryRejected('ARTIFACT_BYTES_CHANGED')
        handle.seek(0)
        return handle, after
    except BaseException:
        if handle is not None:
            handle.close()
        raise


def unchanged_descriptor(handle, verified_stat):
    """Final non-awaiting fence after the SQL check, before headers/ownership handoff."""
    try:
        current = os.fstat(handle.fileno())
    except (OSError, ValueError):
        raise ArtifactDeliveryRejected('ARTIFACT_BYTES_CHANGED') from None
    def identity(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
    if (not stat.S_ISREG(current.st_mode) or current.st_nlink != 1
            or identity(current) != identity(verified_stat)):
        raise ArtifactDeliveryRejected('ARTIFACT_BYTES_CHANGED')
    return current


class OwnedArtifactResponse(FileResponse):
    """FileResponse range/HEAD protocol with a verified private descriptor and drain."""
    def __init__(self, path, handle, temporary, **kwargs):
        self._handle, self._temporary, self._closed = handle, temporary, False
        super().__init__(path, **kwargs)

    async def _io(self, operation, *args):
        # AnyIO disconnect cancellation and direct repeated asyncio cancellation
        # cannot abandon a thread which still owns this descriptor.
        with anyio.CancelScope(shield=True):
            return await completed_read(asyncio.to_thread(operation, *args))

    async def _send_bytes(self, send, start, end):
        await self._io(self._handle.seek, start)
        while start < end:
            chunk = await self._io(self._handle.read, min(self.chunk_size, end-start))
            if not chunk:
                raise ArtifactDeliveryRejected('ARTIFACT_DELIVERY_SHORT_READ')
            start += len(chunk)
            await send({'type':'http.response.body', 'body':chunk, 'more_body':start < end})
        if start == end and end == 0:
            await send({'type':'http.response.body', 'body':b'', 'more_body':False})

    async def _handle_simple(self, send, send_header_only, send_pathsend):
        await send({'type':'http.response.start', 'status':self.status_code, 'headers':self.raw_headers})
        if send_header_only:
            await send({'type':'http.response.body', 'body':b'', 'more_body':False})
        else:
            await self._send_bytes(send, 0, self.stat_result.st_size)

    async def _handle_single_range(self, send, start, end, file_size, send_header_only):
        headers = MutableHeaders(raw=list(self.raw_headers))
        headers['content-range'] = f'bytes {start}-{end-1}/{file_size}'
        headers['content-length'] = str(end-start)
        await send({'type':'http.response.start', 'status':206, 'headers':headers.raw})
        if send_header_only:
            await send({'type':'http.response.body', 'body':b'', 'more_body':False})
        else:
            await self._send_bytes(send, start, end)

    async def _handle_multiple_ranges(self, send, ranges, file_size, send_header_only):
        boundary = token_hex(13)
        length, header = self.generate_multipart(ranges, boundary, file_size, self.headers['content-type'])
        headers = MutableHeaders(raw=list(self.raw_headers))
        headers['content-type'] = f'multipart/byteranges; boundary={boundary}'
        headers['content-length'] = str(length)
        await send({'type':'http.response.start', 'status':206, 'headers':headers.raw})
        if send_header_only:
            await send({'type':'http.response.body', 'body':b'', 'more_body':False})
            return
        for start, end in ranges:
            await send({'type':'http.response.body', 'body':header(start,end), 'more_body':True})
            await self._io(self._handle.seek, start)
            while start < end:
                chunk = await self._io(self._handle.read, min(self.chunk_size, end-start))
                if not chunk:
                    raise ArtifactDeliveryRejected('ARTIFACT_DELIVERY_SHORT_READ')
                start += len(chunk)
                await send({'type':'http.response.body', 'body':chunk, 'more_body':True})
            await send({'type':'http.response.body', 'body':b'\r\n', 'more_body':True})
        await send({'type':'http.response.body', 'body':f'--{boundary}--'.encode(), 'more_body':False})

    def _close(self):
        if not self._closed:
            self._closed = True
            try:
                self._handle.close()
            finally:
                self._temporary.cleanup()

    async def __call__(self, scope, receive, send):
        # Never hand a private path to a deferred sendfile extension: the owned
        # descriptor must finish before its directory can be removed.
        scope = {**scope, 'extensions':{k:v for k,v in scope.get('extensions',{}).items()
            if k != 'http.response.pathsend'}}
        async def private_headers(message):
            if message['type']=='http.response.start':
                message={**message,'headers':list(message['headers'])}
                headers=MutableHeaders(raw=message['headers'])
                headers['cache-control']='no-store';headers['x-content-type-options']='nosniff'
            await send(message)
        try:
            await super().__call__(scope, receive, private_headers)
        finally:
            await self._io(self._close)


async def deliver_verified_artifact(*, proof, storage, staging_root, basename,
        filename, media_type, current):
    if basename not in {'render.mp4','preview.mp4','artifact.bin'}:
        raise ArtifactDeliveryRejected('ARTIFACT_STAGING_NAME_INVALID')
    if media_type is not None and (not isinstance(media_type,str) or not media_type.isascii()
            or any(ord(c)<32 or ord(c)==127 for c in media_type)
            or re.fullmatch(r'[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+',media_type.split(';',1)[0].strip()) is None):
        raise ArtifactDeliveryRejected('ARTIFACT_CONTENT_TYPE_INVALID')
    root = Path(staging_root);root.mkdir(parents=True, exist_ok=True)
    temporary = tempfile.TemporaryDirectory(prefix='verified-artifact-', dir=root)
    path = Path(temporary.name)/basename
    handle = None;handed_off = False
    try:
        try:
            await proof.download(storage, path)
            handle, actual_stat = await completed_read(asyncio.to_thread(verified_output_handle,path,proof),
                dispose_cancelled_result=lambda result:result[0].close())
        except FileNotFoundError:
            raise
        except ArtifactDeliveryRejected:
            raise
        except StorageDownloadError as error:
            if error.code in {'STORAGE_DOWNLOAD_SIZE_MISMATCH','STORAGE_DOWNLOAD_SIZE_LIMIT',
                    'STORAGE_DOWNLOAD_HASH_MISMATCH','STORAGE_DOWNLOAD_STAGE_HASH_MISMATCH'}:
                raise ArtifactDeliveryRejected('ARTIFACT_BYTES_CHANGED') from None
            raise ArtifactDeliveryRejected('ARTIFACT_STORAGE_UNAVAILABLE',503) from None
        except Exception:
            raise ArtifactDeliveryRejected('ARTIFACT_STORAGE_UNAVAILABLE',503) from None
        # This is the final awaited metadata/owner/currentness fence before
        # constructing a response. No storage read or provider replay follows.
        await current()
        # The SQL await cannot leave a gap in the already verified descriptor:
        # reject changed bytes/identity before a SHA ETag or body can be sent.
        # No await follows this local fstat fence before response construction.
        actual_stat = unchanged_descriptor(handle, actual_stat)
        response = OwnedArtifactResponse(path, handle, temporary, filename=filename, media_type=media_type,
            stat_result=actual_stat, headers={'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
                'ETag':'"'+proof.checksum_sha256+'"'})
        handed_off = True
        return response
    finally:
        if not handed_off:
            def close():
                try:
                    if handle is not None:handle.close()
                finally:temporary.cleanup()
            with anyio.CancelScope(shield=True):
                await completed_read(asyncio.to_thread(close))
