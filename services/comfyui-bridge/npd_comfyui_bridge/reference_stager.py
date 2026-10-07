"""Exact scoped image staging; lost upload replies never authorize another POST."""
from datetime import datetime, timezone
import hashlib
from .binary_artifacts import digest
from .execution_models import VerifiedReferenceToken
from .http_transport import ComfyTransportError
from .reference_models import ReferenceUpload
from .reference_store import ReferenceError


class ScopedReferenceStager:
    def __init__(self, *, references, transport, job_store):
        self.references, self.transport, self.job_store = references, transport, job_store

    async def __call__(self, *, workspace_id, project_id, source_reference):
        document, path = self.references.read(workspace_id=workspace_id, project_id=project_id, source_reference=source_reference)
        admission = document['admission']
        if admission['fixture'] and not self.transport.fixture:
            raise ReferenceError('REFERENCE_FIXTURE_LIVE_FORBIDDEN')
        identity = document['reference_id']
        target = digest({'origin': self.transport.origin, 'server_source_sha256': self.transport.server_source_sha256,
            'fixture': self.transport.fixture})
        suffix = 'png' if admission['mime_type'] == 'image/png' else 'jpg'
        filename = 'vfref_' + digest([workspace_id, project_id, identity, target]) + '.' + suffix
        record = self.job_store.reference_upload(workspace_id=workspace_id, project_id=project_id, reference_id=identity, target_sha256=target)
        if record and (record.filename != filename or record.content_sha256 != admission['content_sha256'] or record.fixture != self.transport.fixture):
            raise ReferenceError('REFERENCE_UPLOAD_BINDING_INVALID')
        try:
            existing = await self.transport.read_input_image(filename=filename, expected_sha256=admission['content_sha256'], mime_type=admission['mime_type'])
            if existing is None:
                if record:
                    raise ReferenceError('REFERENCE_UPLOAD_RECOVERY_REQUIRED')
                current = datetime.now(timezone.utc)
                record = ReferenceUpload(workspace_id=workspace_id, project_id=project_id, reference_id=identity,
                    target_sha256=target, filename=filename, content_sha256=admission['content_sha256'],
                    state='intent', fixture=self.transport.fixture, created_at=current, updated_at=current)
                record = self.job_store.save_reference_upload(record)
                # Recheck receipt/scope/bytes immediately before the write.
                document, path = self.references.read(workspace_id=workspace_id, project_id=project_id, source_reference=source_reference)
                content = path.read_bytes()
                if hashlib.sha256(content).hexdigest() != admission['content_sha256']:
                    raise ReferenceError('REFERENCE_CONTENT_CHANGED')
                await self.transport.upload_image(filename=filename, content=content,
                    expected_sha256=admission['content_sha256'], mime_type=admission['mime_type'])
            self.references.read(workspace_id=workspace_id, project_id=project_id, source_reference=source_reference)
            if record is None:
                current = datetime.now(timezone.utc)
                record = ReferenceUpload(workspace_id=workspace_id, project_id=project_id, reference_id=identity,
                    target_sha256=target, filename=filename, content_sha256=admission['content_sha256'],
                    state='confirmed', fixture=self.transport.fixture, created_at=current, updated_at=current)
                self.job_store.save_reference_upload(record)
            elif record.state != 'confirmed':
                self.job_store.save_reference_upload(record.model_copy(update={'state': 'confirmed', 'updated_at': datetime.now(timezone.utc)}), previous=record)
        except ComfyTransportError:
            raise ReferenceError('REFERENCE_UPLOAD_RECOVERY_REQUIRED') from None
        return VerifiedReferenceToken(workspace_id=workspace_id, project_id=project_id, source_reference=source_reference,
            source_sha256=admission['content_sha256'], uploaded_filename=filename,
            upload_sha256=admission['content_sha256'], fixture=self.transport.fixture or admission['fixture'])
