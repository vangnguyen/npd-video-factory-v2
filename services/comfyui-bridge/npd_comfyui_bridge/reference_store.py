"""Bridge-owned immutable reference bytes; no URLs or shared database lookup."""
from __future__ import annotations
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import os
import uuid

from .binary_artifacts import FFmpegMediaValidator, checked, digest, native_path
from .http_transport import IMAGE_LIMIT
from .job_store import linked
from .reference_models import ReferenceAdmission


class ReferenceError(RuntimeError): pass


class ReferenceStore:
    def __init__(self, root, *, validator: FFmpegMediaValidator, enabled=False, clock=None):
        if type(enabled) is not bool or not isinstance(validator, FFmpegMediaValidator) or linked(Path(root)):
            raise ReferenceError('REFERENCE_CONFIGURATION_INVALID')
        self.root = native_path(root)
        self.validator, self.enabled = validator, enabled
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = asyncio.Lock()

    def _admit(self, admission):
        if not self.enabled or not self.validator.configured:
            raise ReferenceError('REFERENCE_INTAKE_NOT_CONFIGURED')
        if not isinstance(admission, ReferenceAdmission):
            raise ReferenceError('REFERENCE_ADMISSION_INVALID')
        current = self.clock()
        if admission.issued_at > current + timedelta(seconds=30) or admission.expires_at <= current:
            raise ReferenceError('REFERENCE_ADMISSION_EXPIRED')

    def _directory(self, workspace_id, reference_id):
        if not isinstance(reference_id, str) or not re.fullmatch(r'[a-f0-9]{64}', reference_id):
            raise ReferenceError('REFERENCE_ID_INVALID')
        return checked(self.root / digest(workspace_id) / reference_id, self.root)

    def read(self, *, workspace_id, project_id, source_reference):
        if not isinstance(source_reference, str) or not re.fullmatch(r'vf-reference://[a-f0-9]{64}', source_reference):
            raise ReferenceError('REFERENCE_ID_INVALID')
        identity = source_reference.removeprefix('vf-reference://')
        directory = self._directory(workspace_id, identity)
        metadata = checked(directory / 'reference.json', self.root)
        try:
            if not metadata.is_file() or metadata.stat().st_size > 65536: raise ValueError()
            wrapper = json.loads(metadata.read_bytes()); document = wrapper['document']
            admission = ReferenceAdmission.model_validate(document['admission'])
            if (set(wrapper) != {'schema', 'document', 'sha256'} or wrapper['schema'] != 'vf-reference-store-v1'
                    or digest(document) != wrapper['sha256'] or digest(admission.model_dump(mode='json')) != identity
                    or admission.workspace_id != workspace_id or admission.project_id != project_id
                    or document['source_reference'] != source_reference or document['reference_id'] != identity
                    or document['rights_independently_verified'] is not False or document['publishing_authorized'] is not False
                    or document['media']['full_decode_passed'] is not True): raise ValueError()
            self._admit(admission)
            expected = 'reference.png' if admission.mime_type == 'image/png' else 'reference.jpg'
            if document['filename'] != expected: raise ValueError()
            path = checked(directory / expected, self.root)
            if (not path.is_file() or type(document['size_bytes']) is not int
                    or path.stat().st_size != document['size_bytes'] or not 1 <= path.stat().st_size <= IMAGE_LIMIT
                    or hashlib.sha256(path.read_bytes()).hexdigest() != admission.content_sha256): raise ValueError()
        except (ValueError, KeyError, TypeError):
            raise ReferenceError('REFERENCE_NOT_FOUND_OR_INVALID') from None
        return document, path

    async def register(self, *, admission, content):
        self._admit(admission)
        if (not isinstance(content, bytes) or not 1 <= len(content) <= IMAGE_LIMIT
                or hashlib.sha256(content).hexdigest() != admission.content_sha256
                or not (content.startswith(b'\x89PNG\r\n\x1a\n') if admission.mime_type == 'image/png' else content.startswith(b'\xff\xd8\xff'))):
            raise ReferenceError('REFERENCE_CONTENT_INVALID')
        identity = digest(admission.model_dump(mode='json')); uri = 'vf-reference://' + identity
        directory = self._directory(admission.workspace_id, identity)
        async with self._lock:
            if directory.exists():
                document, path = self.read(workspace_id=admission.workspace_id, project_id=admission.project_id, source_reference=uri)
                return document
            # Bounded isolated storage; retention never deletes caller assets.
            records, total = 0, 0
            if self.root.exists():
                for metadata in self.root.glob('*/*/reference.json'):
                    checked(metadata, self.root); records += 1
                    for media in metadata.parent.glob('reference.*'):
                        checked(media, self.root); total += media.stat().st_size
                    if records >= 512 or total + len(content) > 2 * 1024**3:
                        raise ReferenceError('REFERENCE_STORAGE_LIMIT')
            workspace_root = directory.parent; workspace_root.mkdir(parents=True, exist_ok=True)
            temporary = checked(workspace_root / ('.partial-' + uuid.uuid4().hex), self.root)
            temporary.mkdir(exist_ok=False)
            path = temporary / ('reference.png' if admission.mime_type == 'image/png' else 'reference.jpg')
            metadata = temporary / 'reference.json'
            try:
                with path.open('xb') as handle:
                    handle.write(content); handle.flush(); os.fsync(handle.fileno())
                media = await self.validator.validate(path, admission.mime_type)
                self._admit(admission)
                document = {'reference_id': identity, 'source_reference': uri, 'filename': path.name,
                    'size_bytes': len(content), 'admission': admission.model_dump(mode='json'), 'media': media,
                    'rights_independently_verified': False, 'publishing_authorized': False,
                    'created_at': self.clock().isoformat()}
                with metadata.open('xb') as handle:
                    handle.write(json.dumps({'schema': 'vf-reference-store-v1', 'document': document, 'sha256': digest(document)},
                        allow_nan=False, ensure_ascii=False).encode()); handle.flush(); os.fsync(handle.fileno())
                temporary.rename(directory)
                return self.read(workspace_id=admission.workspace_id, project_id=admission.project_id, source_reference=uri)[0]
            finally:
                if temporary.exists():
                    for owned in (path, metadata):
                        if owned.is_file() and not linked(owned): owned.unlink()
                    temporary.rmdir()
