"""Private, bounded diagnostics for rejected renders; never production assets.

Quota is reserved by the SQL repository before any object write. A sealed open
temporary descriptor, rather than a renderer path reopened after an await, owns
every uploaded byte. Partial/cancelled attempts keep their quota charge.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .bounded_storage_download import (drained_download, guarded_source, guarded_destination, _plain_parts,
    private_sdk_download)
from .frozen_storage_read import completed_read
from .object_storage import (LocalObjectStorageProvider, S3ObjectStorageProvider,
    filesystem_path, validate_object_key, _require_bounded_download_client)
from .verified_artifact_delivery import ArtifactDeliveryRejected, RecordedArtifactRead

MIB = 1024 * 1024
RESERVATION_EVENT = 'render.failed_qc_evidence_reserved'
SCHEMA = 'failed-qc-evidence.v1'
ARTIFACTS = {'qc': ('qc.json', 'application/json'),
    'manifest': ('manifest.json', 'application/json'), 'evidence': ('evidence.json', 'application/json'),
    'video': ('failed-output.bin', 'application/octet-stream'),
    'audio': ('audio-mix.bin', 'application/octet-stream'), 'subtitles': ('subtitles.txt', 'text/plain')}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def context(render):
    return {key: getattr(render, key) for key in ('render_id', 'version', 'workspace_id', 'project_id',
        'package_id', 'timeline_id', 'timeline_version_id', 'timeline_version',
        'subtitle_version_id', 'audio_version_id', 'render_kind', 'profile')}


def reservation_id(render_id):
    return 'pev_fqe_' + hashlib.sha256(render_id.encode()).hexdigest()[:32]


@dataclass(frozen=True)
class FailureEvidencePolicy:
    per_render_bytes: int = 32 * MIB
    per_project_bytes: int = 128 * MIB
    video_bytes: int = 20 * MIB
    audio_bytes: int = 8 * MIB
    metadata_bytes: int = MIB // 2
    retention_days: int = 7

    def __post_init__(self):
        for name, maximum in (('per_render_bytes', 32*MIB), ('per_project_bytes', 128*MIB),
                ('video_bytes', 20*MIB), ('audio_bytes', 8*MIB), ('metadata_bytes', MIB//2), ('retention_days', 30)):
            value = getattr(self, name)
            if type(value) is not int or not 0 < value <= maximum:
                raise ValueError('FAILED_EVIDENCE_POLICY_INVALID')
        if self.per_render_bytes > self.per_project_bytes:
            raise ValueError('FAILED_EVIDENCE_POLICY_INVALID')


@dataclass
class SealedArtifact:
    name: str
    handle: object
    size_bytes: int
    checksum_sha256: str

    def proof(self):
        return {'name': self.name, 'size_bytes': self.size_bytes, 'checksum_sha256': self.checksum_sha256}


@dataclass
class PreparedEvidence:
    artifacts: list[SealedArtifact] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total(self):
        return sum(item.size_bytes for item in self.artifacts)

    def close(self):
        for item in self.artifacts:
            item.handle.close()


def _seal(path, *, name, maximum, temporary_root):
    source = guarded_source(path, filesystem_path)
    temporary = tempfile.TemporaryFile(mode='w+b', dir=filesystem_path(temporary_root))
    try:
        with source.open('rb') as handle:
            before = os.fstat(handle.fileno())
            observed = source.lstat()
            if (not stat.S_ISREG(before.st_mode) or before.st_nlink != 1
                    or (before.st_dev, before.st_ino) != (observed.st_dev, observed.st_ino)
                    or not 0 < before.st_size <= maximum):
                raise ValueError('FAILED_EVIDENCE_SOURCE_INVALID')
            count = 0; checksum = hashlib.sha256()
            for chunk in iter(lambda: handle.read(128*1024), b''):
                count += len(chunk)
                if count > maximum:
                    raise ValueError('FAILED_EVIDENCE_SIZE_LIMIT')
                temporary.write(chunk); checksum.update(chunk)
            after = os.fstat(handle.fileno())
            latest = guarded_source(path, filesystem_path).lstat()
            identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if count != before.st_size or identity(before) != identity(after) or identity(before) != identity(latest):
                raise ValueError('FAILED_EVIDENCE_SOURCE_CHANGED')
        temporary.flush(); temporary.seek(0)
        return SealedArtifact(name, temporary, count, checksum.hexdigest())
    except BaseException:
        temporary.close(); raise


def prepare(*, workdir, render_kind, qc_report, manifest, evidence, policy):
    _plain_parts(workdir/'unused-evidence-marker', filesystem_path)
    result = PreparedEvidence()
    def add(artifact):
        if result.total + artifact.size_bytes > policy.per_render_bytes:
            artifact.handle.close(); result.errors.append('FAILED_EVIDENCE_RENDER_LIMIT'); return
        result.artifacts.append(artifact)
    try:
        for name, value in (('qc', qc_report), ('manifest', manifest), ('evidence', evidence)):
            payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
            if not 0 < len(payload) <= policy.metadata_bytes:
                result.errors.append('FAILED_EVIDENCE_METADATA_LIMIT'); continue
            handle = tempfile.TemporaryFile(mode='w+b', dir=filesystem_path(workdir))
            handle.write(payload); handle.flush(); handle.seek(0)
            add(SealedArtifact(name, handle, len(payload), hashlib.sha256(payload).hexdigest()))
        for name, filename, maximum in (('video', 'review.mp4' if render_kind=='review' else 'final.mp4', policy.video_bytes),
                ('audio', 'audio-mix.wav', policy.audio_bytes), ('subtitles', 'subtitles.srt', policy.metadata_bytes)):
            path = workdir/filename
            if not path.exists():
                result.errors.append('FAILED_EVIDENCE_FILE_UNAVAILABLE'); continue
            try:
                item = _seal(path, name=name, maximum=maximum, temporary_root=workdir)
                if name == 'video' and qc_report.get('checksum_sha256') is not None:
                    if item.checksum_sha256 != qc_report['checksum_sha256']:
                        item.handle.close(); raise ValueError('FAILED_EVIDENCE_QC_BYTES_CHANGED')
                add(item)
            except (OSError, ValueError):
                result.errors.append('FAILED_EVIDENCE_FILE_REJECTED')
        return result
    except BaseException:
        result.close(); raise


class _ControlledBody:
    def __init__(self, artifact, control, deadline):
        self.artifact, self.control, self.deadline = artifact, control, deadline
    def check(self):
        self.control.check()
        if time.monotonic() > self.deadline:
            raise TimeoutError('FAILED_EVIDENCE_UPLOAD_DEADLINE')
    def read(self, size=-1):
        self.check()
        remaining = self.artifact.size_bytes - self.tell()
        size = min(128*1024, remaining) if size < 0 else min(size, remaining)
        return self.artifact.handle.read(size)
    def seek(self, offset, whence=0):
        self.check()
        position = self.artifact.handle.seek(offset, whence)
        if not 0 <= position <= self.artifact.size_bytes:
            raise ValueError('FAILED_EVIDENCE_BODY_RANGE')
        return position
    def tell(self):
        return self.artifact.handle.tell()
    def readable(self): return True
    def seekable(self): return True
    def close(self): pass  # caller owns the sealed descriptor through drain


def _local_upload(storage, key, artifact, control, deadline):
    # Do not resolve away a junction/symlink before checking its original
    # components, including an in-root redirect into another workspace.
    literal = storage._download_root / Path(*PurePosixPath(validate_object_key(key)).parts)
    destination = guarded_destination(literal, filesystem_path)
    if destination.exists():
        raise ValueError('FAILED_EVIDENCE_OBJECT_EXISTS')
    temporary = destination.parent/('.fqe-'+os.urandom(16).hex()+'.part')
    identity = None
    try:
        with temporary.open('xb') as target:
            identity = os.fstat(target.fileno())
            body = _ControlledBody(artifact, control, deadline); body.seek(0)
            checksum = hashlib.sha256(); count = 0
            for chunk in iter(lambda: body.read(128*1024), b''):
                target.write(chunk); checksum.update(chunk); count += len(chunk)
            target.flush()
        if count != artifact.size_bytes or checksum.hexdigest() != artifact.checksum_sha256:
            raise ValueError('FAILED_EVIDENCE_BODY_CHANGED')
        body.check()
        control.replace(temporary, destination, identity=(identity.st_dev, identity.st_ino),
            parent_identity=(destination.parent.stat().st_dev, destination.parent.stat().st_ino),
            expected_size=count, io_path=filesystem_path)
    finally:
        if identity is not None:
            try:
                observed = temporary.lstat()
                if (observed.st_dev, observed.st_ino) == (identity.st_dev, identity.st_ino):
                    temporary.unlink()
            except FileNotFoundError:
                pass


async def upload(*, storage, prepared, render, attempt_id, policy):
    prefix = validate_object_key(f'workspaces/{render.workspace_id}/projects/{render.project_id}/failed-render-evidence/{render.render_id}/{attempt_id}')
    descriptors = []; errors = list(prepared.errors)
    if type(storage) not in {LocalObjectStorageProvider, S3ObjectStorageProvider}:
        return [], errors+['FAILED_EVIDENCE_STORAGE_NOT_CONFIGURED']
    if type(storage) is S3ObjectStorageProvider:
        try: _require_bounded_download_client(storage.client)
        except Exception: return [], errors+['FAILED_EVIDENCE_SDK_PROFILE_REQUIRED']
    deadline = time.monotonic()+120
    for artifact in prepared.artifacts:
        filename, content_type = ARTIFACTS[artifact.name]
        key = validate_object_key(prefix+'/'+filename)
        def transfer(control):
            if type(storage) is LocalObjectStorageProvider:
                _local_upload(storage, key, artifact, control, deadline)
            else:
                body = _ControlledBody(artifact, control, deadline); body.seek(0)
                with private_sdk_download():  # same process-local SDK privacy boundary for this write
                    storage.client.put_object(Bucket=storage.bucket, Key=key, Body=body,
                        ContentLength=artifact.size_bytes, ContentType=content_type, ACL='private',
                        ChecksumSHA256=base64.b64encode(bytes.fromhex(artifact.checksum_sha256)).decode(),
                        Metadata={'sha256': artifact.checksum_sha256})
                body.check()
        try:
            await drained_download(transfer)
            descriptors.append({**artifact.proof(), 'object_key': key,
                'storage_provider': storage.name, 'content_type': content_type})
        except Exception:
            errors.append('FAILED_EVIDENCE_UPLOAD_FAILED')
            break  # one bounded attempt; no storage/provider retry loop
    return descriptors, sorted(set(errors))


def bundle(render, *, qc_report, attempt_id, reserved_bytes, artifacts, errors, status, policy):
    now = datetime.now(timezone.utc)
    return {'schema_version': SCHEMA, 'context': context(render), 'qc_report_sha256': digest(qc_report),
        'attempt_id': attempt_id, 'reserved_bytes': reserved_bytes, 'status': status,
        'artifacts': artifacts, 'errors': sorted(set(errors)), 'retained_at': now.isoformat(),
        'expires_at': (now+timedelta(days=policy.retention_days)).isoformat(),
        'publishing_allowed': False, 'approved': False}


def artifact_read(render, ledger, name):
    """Strict server-owned diagnostic proof, separate from the output asset path."""
    try:
        value = render.manifest.get('failed_qc_evidence')
        if (render.status != 'failed_qc' or render.qc_status != 'failed' or render.error_code != 'QC_FAILED'
                or render.output_asset_id is not None or not isinstance(value, dict)
                or set(value) != {'schema_version','context','qc_report_sha256','attempt_id','reserved_bytes',
                    'status','artifacts','errors','retained_at','expires_at','publishing_allowed','approved'}
                or value['schema_version'] != SCHEMA or value['context'] != context(render)
                or value['qc_report_sha256'] != digest(render.qc_report)
                or value['publishing_allowed'] is not False or value['approved'] is not False
                or value['status'] not in {'retained','partial'}
                or type(value['reserved_bytes']) is not int or not 0 <= value['reserved_bytes'] <= 32*MIB
                or not re.fullmatch('[a-f0-9]{32}', value['attempt_id'])
                or not isinstance(ledger, dict) or ledger.get('attempt_id') != value['attempt_id']
                or ledger.get('schema_version') != SCHEMA or ledger.get('context') != context(render)
                or ledger.get('claim_status') != 'reserved'
                or ledger.get('context_sha256') != digest(context(render))
                or type(ledger.get('reserved_bytes')) is not int
                or ledger['reserved_bytes'] != value['reserved_bytes']):
            raise ValueError()
        expiry = datetime.fromisoformat(value['expires_at'])
        retained = datetime.fromisoformat(value['retained_at'])
        if retained.tzinfo is None or expiry.tzinfo is None or not 0 < (expiry-retained).total_seconds() <= 30*86400:
            raise ValueError()
        if expiry <= datetime.now(timezone.utc):
            raise ArtifactDeliveryRejected('FAILED_EVIDENCE_EXPIRED', 410)
        items = value['artifacts']
        if not isinstance(items, list) or len(items)>6 or len({item['name'] for item in items}) != len(items):
            raise ValueError()
        plan = ledger['planned_artifacts']
        if (not isinstance(plan,list) or len(plan)>6 or ledger.get('plan_sha256') != digest(plan)
                or any(set(item) != {'name','size_bytes','checksum_sha256'}
                    or item['name'] not in ARTIFACTS or type(item['size_bytes']) is not int
                    or item['size_bytes'] <= 0 for item in plan)
                or len({item['name'] for item in plan}) != len(plan)
                or sum(item['size_bytes'] for item in plan) != value['reserved_bytes']):
            raise ValueError()
        planned = {item['name']:item for item in plan}
        prefix = f'workspaces/{render.workspace_id}/projects/{render.project_id}/failed-render-evidence/{render.render_id}/{value["attempt_id"]}/'
        if ledger.get('prefix') != prefix:
            raise ValueError()
        total=0; selected=None
        for item in items:
            if set(item) != {'name','size_bytes','checksum_sha256','object_key','storage_provider','content_type'}:
                raise ValueError()
            filename, media_type = ARTIFACTS[item['name']]
            if (type(item['size_bytes']) is not int or item['size_bytes'] <= 0
                    or item['object_key'] != prefix+filename or item['content_type'] != media_type
                    or {key:item[key] for key in ('name','size_bytes','checksum_sha256')} != planned[item['name']]):
                raise ValueError()
            total += item['size_bytes']
            proof=RecordedArtifactRead(item['object_key'],render.workspace_id,render.project_id,
                item['size_bytes'],item['checksum_sha256'],item['storage_provider'])
            if item['name']=='video' and render.qc_report.get('checksum_sha256') is not None:
                if proof.checksum_sha256 != render.qc_report['checksum_sha256']:
                    raise ValueError()
            if item['name']==name:selected=(proof,filename,media_type)
        if total > value['reserved_bytes'] or selected is None:
            raise ValueError()
        return selected
    except ArtifactDeliveryRejected:
        raise
    except (KeyError, TypeError, ValueError, OverflowError):
        raise ArtifactDeliveryRejected('FAILED_EVIDENCE_PROOF_INVALID') from None
