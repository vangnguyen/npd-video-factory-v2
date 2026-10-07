"""AES-256-GCM encrypted upload receipts. No key bootstrap or provider activation."""
from dataclasses import dataclass, field
from datetime import timedelta
import hmac
import json
import os
import re
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .db import utc_now
from .publishing_db import PublicationDispatchORM, PublicationEventORM, PublicationORM, PublicationPrivateSessionORM
from .publishing_dispatch import DispatchTicket, public, utc
from .youtube_upload import UploadSession


class SessionVaultError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class SessionEncryptionKey:
    key_id: str
    key: bytes = field(repr=False)

    def __post_init__(self):
        if not isinstance(self.key_id, str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', self.key_id) or not isinstance(self.key, bytes) or len(self.key) != 32:
            raise SessionVaultError('PUBLISH_SESSION_KEY_INVALID')


def aad(row):
    return json.dumps({'schema': 'vf-publish-session-aes256gcm-v1',
        **{name: getattr(row, name) for name in ('session_ref', 'publication_id', 'workspace_id', 'project_id',
            'binding_sha256', 'platform', 'total_bytes', 'key_id')},
        'created_at': utc(row.created_at).isoformat(), 'expires_at': utc(row.expires_at).isoformat()},
        sort_keys=True, separators=(',', ':')).encode('utf-8')


class PublishingSessionVault:
    def __init__(self, session_factory, *, key_provider=None, clock=utc_now):
        self.session_factory, self.key_provider, self.clock = session_factory, key_provider, clock

    def cipher(self, identifier=None):
        if identifier is not None and (not isinstance(identifier, str) or not re.fullmatch('[A-Za-z0-9_-]{1,64}', identifier)):
            raise SessionVaultError('PUBLISH_SESSION_KEY_UNAVAILABLE')
        if not callable(self.key_provider):
            raise SessionVaultError('PUBLISH_SESSION_KEY_NOT_CONFIGURED')
        try:
            key = self.key_provider(identifier)
        except Exception:
            raise SessionVaultError('PUBLISH_SESSION_KEY_UNAVAILABLE') from None
        if not isinstance(key, SessionEncryptionKey) or (identifier is not None and key.key_id != identifier):
            raise SessionVaultError('PUBLISH_SESSION_KEY_UNAVAILABLE')
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            return key.key_id, AESGCM(key.key)
        except Exception:
            raise SessionVaultError('PUBLISH_SESSION_CRYPTO_NOT_CONFIGURED') from None

    def decrypt(self, row):
        if utc(row.expires_at) <= utc(self.clock()):
            raise SessionVaultError('PUBLISH_SESSION_EXPIRED_REVIEW_REQUIRED')
        if (row.platform != 'youtube' or not isinstance(row.nonce, bytes) or len(row.nonce) != 12
            or not isinstance(row.ciphertext, bytes) or not 17 <= len(row.ciphertext) <= 8192):
            raise SessionVaultError('PUBLISH_SESSION_RECORD_INVALID')
        _key_id, cipher = self.cipher(row.key_id)
        try:
            uri = cipher.decrypt(row.nonce, row.ciphertext, aad(row)).decode('ascii')
            return UploadSession(uri, row.total_bytes)
        except Exception:
            raise SessionVaultError('PUBLISH_SESSION_AUTHENTICATION_FAILED') from None

    async def save(self, ticket, upload_session, *, ttl_seconds=3600):
        if (not isinstance(ticket, DispatchTicket) or ticket.phase != 'init_intent' or not isinstance(upload_session, UploadSession)
            or type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 86400):
            raise SessionVaultError('PUBLISH_SESSION_REQUEST_INVALID')
        # Revalidate even if a caller constructed/mutated an object outside its normal constructor.
        try: value = UploadSession(upload_session.uri, upload_session.total_bytes)
        except Exception: raise SessionVaultError('PUBLISH_SESSION_REQUEST_INVALID') from None
        try:
            return await self._save(ticket, value, ttl_seconds)
        except IntegrityError:
            # Concurrent same-publication saves can re-read the immutable receipt once.
            try: return await self._save(ticket, value, ttl_seconds)
            except IntegrityError: raise SessionVaultError('PUBLISH_SESSION_CONCURRENT_RECEIPT_RELOAD') from None

    async def _save(self, ticket, value, ttl_seconds):
        now = utc(self.clock())
        async with self.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, ticket.publication_id)
                dispatch = await session.get(PublicationDispatchORM, ticket.publication_id)
                if (parent is None or dispatch is None or parent.workspace_id != ticket.workspace_id or dispatch.workspace_id != ticket.workspace_id
                    or parent.platform != 'youtube' or dispatch.phase != ticket.phase or dispatch.version != ticket.version
                    or dispatch.intent_id != ticket.intent_id or dispatch.total_bytes != value.total_bytes):
                    raise SessionVaultError('PUBLISH_SESSION_STALE_OR_FOREIGN_TICKET')
                prior = await session.scalar(select(PublicationPrivateSessionORM).where(PublicationPrivateSessionORM.publication_id == ticket.publication_id))
                if prior is not None:
                    # No overwrite, key rotation or deadline extension on replay.
                    if prior.workspace_id != ticket.workspace_id or prior.binding_sha256 != dispatch.binding_sha256:
                        raise SessionVaultError('PUBLISH_SESSION_RECEIPT_CONFLICT')
                    old = self.decrypt(prior)
                    if old.total_bytes != value.total_bytes or not hmac.compare_digest(old.uri, value.uri):
                        raise SessionVaultError('PUBLISH_SESSION_RECEIPT_CONFLICT')
                    return prior.session_ref
                key_id, cipher = self.cipher()
                row = PublicationPrivateSessionORM(session_ref='pss_' + uuid.uuid4().hex, publication_id=ticket.publication_id,
                    workspace_id=ticket.workspace_id, project_id=dispatch.project_id, binding_sha256=dispatch.binding_sha256,
                    platform='youtube', total_bytes=value.total_bytes, key_id=key_id, nonce=os.urandom(12),
                    created_at=now, expires_at=now + timedelta(seconds=ttl_seconds))
                row.ciphertext = cipher.encrypt(row.nonce, value.uri.encode('ascii'), aad(row))
                session.add(row); await session.flush()
                session.add(PublicationEventORM(event_id='pue_' + uuid.uuid4().hex, publication_id=parent.publication_id,
                    project_id=parent.project_id, event_type='publication.private_session_sealed', actor_ref='publishing-service',
                    payload_json={'secret_free': True, 'binding_sha256': dispatch.binding_sha256, 'encryption': 'AES-256-GCM',
                        'expiry_source': 'internal_policy', 'external_action': False}, created_at=now))
            return row.session_ref

    async def load(self, workspace, publication_id, reference, *, expected_binding_sha256):
        if not isinstance(reference, str) or not re.fullmatch('pss_[a-f0-9]{32}', reference):
            raise SessionVaultError('PUBLISH_SESSION_SCOPE_NOT_FOUND')
        async with self.session_factory() as session:
            row = await session.get(PublicationPrivateSessionORM, reference)
            dispatch = await session.get(PublicationDispatchORM, publication_id)
            if (row is None or dispatch is None or row.workspace_id != workspace or dispatch.workspace_id != workspace
                or row.publication_id != publication_id or row.project_id != dispatch.project_id
                or row.binding_sha256 != expected_binding_sha256 or row.binding_sha256 != dispatch.binding_sha256
                or row.total_bytes != dispatch.total_bytes):
                raise SessionVaultError('PUBLISH_SESSION_SCOPE_NOT_FOUND')
            # Internal worker only. A valid session is not authority to publish another chunk.
            return self.decrypt(row)

    async def recover_initialization(self, workspace, publication_id, *, expected_version):
        """Attach a sealed past response, never authorize/repeat a provider request.

        A revoked/expired approval does not erase an already received session.
        Every subsequent chunk still needs the journal's fresh grant admission.
        """
        if type(expected_version) is not int or expected_version < 2:
            raise SessionVaultError('PUBLISH_SESSION_RECOVERY_VERSION_INVALID')
        now = utc(self.clock())
        async with self.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, publication_id)
                dispatch = await session.get(PublicationDispatchORM, publication_id)
                if (parent is None or dispatch is None or parent.workspace_id != workspace
                    or dispatch.workspace_id != workspace or parent.project_id != dispatch.project_id
                    or parent.platform != 'youtube'):
                    raise SessionVaultError('PUBLISH_SESSION_SCOPE_NOT_FOUND')
                if (dispatch.version != expected_version or dispatch.phase not in ('init_intent', 'init_uncertain')
                    or dispatch.private_session_ref is not None or dispatch.acknowledged_bytes != 0
                    or dispatch.remote_post_id is not None):
                    raise SessionVaultError('PUBLISH_SESSION_RECOVERY_STALE_RELOAD')
                sealed = await session.scalar(select(PublicationPrivateSessionORM).where(
                    PublicationPrivateSessionORM.publication_id == publication_id))
                if sealed is None:
                    return None  # an ambiguous POST without a receipt remains Owner review
                if (sealed.workspace_id != workspace or sealed.project_id != dispatch.project_id
                    or sealed.binding_sha256 != dispatch.binding_sha256 or sealed.total_bytes != dispatch.total_bytes):
                    raise SessionVaultError('PUBLISH_SESSION_SCOPE_NOT_FOUND')
                self.decrypt(sealed)  # authenticated AAD, original key, URI and deadline
                result = await session.execute(update(PublicationDispatchORM).where(
                    PublicationDispatchORM.publication_id == publication_id,
                    PublicationDispatchORM.workspace_id == workspace,
                    PublicationDispatchORM.version == expected_version,
                    PublicationDispatchORM.phase == dispatch.phase,
                    PublicationDispatchORM.binding_sha256 == sealed.binding_sha256,
                    PublicationDispatchORM.private_session_ref.is_(None)).values(
                        phase='upload_ready', version=expected_version + 1,
                        private_session_ref=sealed.session_ref, intent_id=None,
                        intent_offset=None, intent_end=None, lease_until=None,
                        failure_code=None, updated_at=now))
                if result.rowcount != 1:
                    raise SessionVaultError('PUBLISH_SESSION_RECOVERY_STALE_RELOAD')
                session.add(PublicationEventORM(event_id='pue_' + uuid.uuid4().hex,
                    publication_id=publication_id, project_id=parent.project_id,
                    event_type='publication.initialization_receipt_recovered', actor_ref='publishing-service',
                    payload_json={'secret_free': True, 'phase': 'upload_ready', 'version': expected_version + 1,
                        'external_action': False, 'mock_parent': parent.mock}, created_at=now))
            await session.refresh(dispatch)
            return public(dispatch)
