"""Durable publish-only consent and fenced intent; no provider/network activation."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta, timezone
import hashlib
import json
import re
import uuid

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from .db import AssetORM, utc_now
from .human_identity import HumanAuthVerifier, HumanPrincipal
from .production_db import ProductionApprovalORM, ProductionPackageORM, ProductionRenderJobORM
from .publishing_db import PublicationDispatchORM, PublicationEventORM, PublicationORM, PublishApprovalORM
from .publishing_logic import hash_idempotency_key, validate_rights
from .publishing_models import ProviderValidationRead, PublishingTargetBinding
from .timeline_db import TimelineORM


class DispatchError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def checksum(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


@dataclass(frozen=True)
class DispatchTicket:
    workspace_id: str
    publication_id: str
    phase: str
    version: int
    intent_id: str = field(repr=False)

    def __post_init__(self):
        if (self.phase not in ('init_intent', 'chunk_intent', 'reconcile_intent') or type(self.version) is not int or self.version < 2
            or not isinstance(self.intent_id, str) or not re.fullmatch('[a-f0-9]{32}', self.intent_id)):
            raise DispatchError('PUBLISH_DISPATCH_TICKET_INVALID')


def public(row):
    return {key: getattr(row, key) for key in ('publication_id', 'workspace_id', 'project_id', 'publish_approval_id',
        'binding_sha256', 'phase', 'version', 'total_bytes', 'acknowledged_bytes', 'remote_post_id', 'failure_code')}


class PublishingDispatchJournal:
    def __init__(self, session_factory, *, identity_provider=None, target_provider=None,
                 require_target_binding=False, clock=utc_now, lease_seconds=180):
        if type(lease_seconds) is not int or not 90 <= lease_seconds <= 900:
            raise DispatchError('PUBLISH_DISPATCH_LEASE_INVALID')
        self.session_factory, self.clock, self.lease_seconds = session_factory, clock, lease_seconds
        self.identity_provider = identity_provider
        if type(require_target_binding) is not bool:
            raise DispatchError('PUBLISH_TARGET_POLICY_INVALID')
        self.target_provider = target_provider
        self.require_target_binding = require_target_binding

    def target_binding(self, parent):
        """Resolve the current server configuration; a saved snapshot cannot authorize itself."""
        raw = parent.provider_validation_json.get('target_binding')
        if raw is None:
            if self.require_target_binding or parent.status == 'awaiting_publish_approval':
                raise DispatchError('PUBLISH_TARGET_BINDING_REQUIRED')
            return None
        try:
            validation = ProviderValidationRead.model_validate(parent.provider_validation_json)
            target = validation.target_binding
            if (target is None or target.workspace_id != parent.workspace_id or target.platform != parent.platform
                or target.provider_key != parent.provider_key or validation.provider_key != parent.provider_key
                or validation.credential_status != 'configured' or not validation.official_api_only):
                raise ValueError()
        except Exception:
            raise DispatchError('PUBLISH_TARGET_BINDING_INVALID') from None
        try:
            current = self.target_provider(parent.workspace_id, target.profile_id) if callable(self.target_provider) else None
            if not isinstance(current, PublishingTargetBinding):
                raise ValueError()
            current = PublishingTargetBinding.model_validate(current.model_dump())
        except Exception:
            raise DispatchError('PUBLISH_TARGET_REVALIDATION_REQUIRED') from None
        if current != target:
            raise DispatchError('PUBLISH_TARGET_CHANGED_REVALIDATE')
        return target.model_dump(mode='json')

    def identity_revision(self, token_id, workspace, subject=None):
        try:
            verifier = self.identity_provider() if callable(self.identity_provider) else None
        except Exception:
            raise DispatchError('PUBLISH_OWNER_IDENTITY_REVALIDATION_REQUIRED') from None
        if not isinstance(verifier, HumanAuthVerifier):
            raise DispatchError('PUBLISH_OWNER_IDENTITY_REVALIDATION_REQUIRED')
        record = verifier.registry.tokens.get(token_id)
        now = utc(self.clock())
        if record is None or not record.enabled or utc(record.issued_at) > now or utc(record.expires_at) <= now or (subject is not None and subject != record.subject):
            raise DispatchError('HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED')
        principal = HumanPrincipal(token_id=record.token_id, subject=record.subject, display_name=record.display_name,
            platform_role=record.platform_role, workspace_roles=record.workspace_roles, expires_at=record.expires_at)
        if principal.role_for(workspace) != 'owner':
            raise DispatchError('HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED')
        return checksum(record.model_dump(mode='json'))

    async def parent(self, session, workspace, publication_id):
        row = await session.get(PublicationORM, publication_id)
        if row is None or row.workspace_id != workspace:
            raise DispatchError('PUBLISH_SCOPE_NOT_FOUND')
        return row

    async def binding(self, session, parent):
        if parent.mode != 'live' or parent.status not in ('awaiting_publish_approval', 'publishing') or parent.receipt_json is not None:
            raise DispatchError('PUBLISH_LIVE_VALIDATED_PARENT_REQUIRED')
        for name in ('rights_validation_json', 'platform_validation_json'):
            value = getattr(parent, name)
            if (not isinstance(value, dict) or value.get('status') != 'passed' or not isinstance(value.get('checks'), list)
                or not value['checks'] or any(not isinstance(check, dict) or check.get('passed') is not True for check in value['checks'])):
                raise DispatchError('PUBLISH_VALIDATION_REQUIRED')
        provider = parent.provider_validation_json
        if (not isinstance(provider, dict) or provider.get('adapter_state') != 'ready' or provider.get('supports_live_publish') is not True
            or not isinstance(provider.get('checks'), list) or not provider['checks'] or any(not isinstance(c, dict) or c.get('passed') is not True for c in provider['checks'])):
            raise DispatchError('PUBLISH_PROVIDER_NOT_READY')
        package = await session.get(ProductionPackageORM, parent.package_id)
        approval = await session.get(ProductionApprovalORM, parent.approval_id)
        render = await session.get(ProductionRenderJobORM, parent.final_render_id)
        asset = await session.get(AssetORM, parent.output_asset_id)
        if (not all((package, approval, render, asset)) or any(row.workspace_id != parent.workspace_id or row.project_id != parent.project_id for row in (package, render, asset))
            or approval.project_id != parent.project_id or approval.package_id != package.package_id or render.package_id != package.package_id):
            raise DispatchError('PUBLISH_SOURCE_BINDING_INVALID')
        timeline = await session.get(TimelineORM, package.timeline_id)
        if (timeline is None or timeline.workspace_id != parent.workspace_id or timeline.project_id != parent.project_id
            or timeline.current_version_id != package.timeline_version_id or timeline.current_version != package.timeline_version
            or package.current_approval_id != approval.approval_id or approval.status != 'approved'
            or package.latest_final_render_id != render.render_id or render.render_kind != 'final' or render.status != 'ready'
            or render.qc_status != 'passed' or render.invalidated_at is not None or render.cancellation_requested
            or render.approval_id != approval.approval_id or render.output_asset_id != asset.asset_id):
            raise DispatchError('PUBLISH_CURRENT_APPROVAL_QC_REQUIRED')
        if any((getattr(package, 'current_' + stage + '_version_id') != getattr(approval, stage + '_version_id')
                or getattr(render, stage + '_version_id') != getattr(approval, stage + '_version_id')) for stage in ('subtitle', 'audio')) or render.timeline_version_id != approval.timeline_version_id or render.timeline_version_id != package.timeline_version_id:
            raise DispatchError('PUBLISH_CURRENT_APPROVAL_QC_REQUIRED')
        if asset.content_type != 'video/mp4' or not re.fullmatch('[a-f0-9]{64}', asset.checksum_sha256) or not 1 <= asset.size_bytes <= 512 * 1024 * 1024:
            raise DispatchError('PUBLISH_SOURCE_BINDING_INVALID')
        source_ids = parent.rights_validation_json.get('asset_ids')
        if not isinstance(source_ids, list) or not source_ids or len(source_ids) > 1000:
            raise DispatchError('PUBLISH_RIGHTS_REVALIDATION_REQUIRED')
        sources = []
        for identifier in source_ids:
            if not isinstance(identifier, str) or not re.fullmatch('ast_[A-Za-z0-9_-]{4,60}', identifier):
                raise DispatchError('PUBLISH_RIGHTS_REVALIDATION_REQUIRED')
            source = await session.get(AssetORM, identifier)
            if source is None or source.workspace_id != parent.workspace_id or source.project_id != parent.project_id:
                raise DispatchError('PUBLISH_RIGHTS_REVALIDATION_REQUIRED')
            sources.append(source)
        if validate_rights(sources).status != 'passed':
            raise DispatchError('PUBLISH_RIGHTS_REVALIDATION_REQUIRED')
        target = self.target_binding(parent)
        binding = {'workspace_id': parent.workspace_id, 'project_id': parent.project_id, 'publication_id': parent.publication_id,
            'package_id': parent.package_id, 'production_approval_id': parent.approval_id, 'final_render_id': render.render_id,
            'output_asset_id': asset.asset_id, 'artifact_sha256': asset.checksum_sha256, 'total_bytes': asset.size_bytes,
            'request_fingerprint': parent.request_fingerprint, 'metadata_sha256': checksum(parent.metadata_json),
            'platform': parent.platform, 'provider_key': parent.provider_key}
        if target is not None:
            binding.update(target_binding=target, target_binding_sha256=checksum(target),
                provider_validation_sha256=checksum(provider))
        return binding

    async def approve(self, workspace, publication_id, *, principal, expected_fingerprint, expected_artifact_sha256,
                      acknowledged, idempotency_key, ttl_seconds=3600, expected_target_sha256=None):
        options = dict(principal=principal, expected_fingerprint=expected_fingerprint,
            expected_artifact_sha256=expected_artifact_sha256, acknowledged=acknowledged,
            idempotency_key=idempotency_key, ttl_seconds=ttl_seconds, expected_target_sha256=expected_target_sha256)
        try:
            return await self._approve(workspace, publication_id, **options)
        except IntegrityError:
            # A concurrent same-key consent may have committed; re-read once.
            try:
                return await self._approve(workspace, publication_id, **options)
            except IntegrityError:
                raise DispatchError('PUBLISH_APPROVAL_CONCURRENT_RESERVATION_RELOAD') from None

    async def review(self, workspace, publication_id):
        """Fresh public review snapshot; reading it grants no authority or lease."""
        async with self.session_factory() as session:
            parent = await self.parent(session, workspace, publication_id)
            binding = await self.binding(session, parent)
            grants = (await session.scalars(select(PublishApprovalORM).where(
                PublishApprovalORM.workspace_id == workspace, PublishApprovalORM.publication_id == publication_id)
                .order_by(PublishApprovalORM.created_at.desc()).limit(100))).all()
            active = None
            for grant in grants:
                try:
                    await self.valid_grant(session, parent, grant.publish_approval_id)
                except DispatchError:
                    continue
                active = self.grant_public(grant)
                break
            return {**binding, 'binding_sha256': checksum(binding), 'metadata': parent.metadata_json,
                'active_publish_approval': active, 'mock': parent.mock,
                'reviewed_at': utc(self.clock()).isoformat(), 'external_action': False}

    async def _approve(self, workspace, publication_id, *, principal, expected_fingerprint, expected_artifact_sha256,
                       acknowledged, idempotency_key, ttl_seconds, expected_target_sha256):
        now = utc(self.clock())
        if (not isinstance(principal, HumanPrincipal) or principal.role_for(workspace) != 'owner' or utc(principal.expires_at) <= now
            or acknowledged is not True or type(ttl_seconds) is not int or not 60 <= ttl_seconds <= 3600):
            raise DispatchError('HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED')
        key = hash_idempotency_key(idempotency_key)
        authority = self.identity_revision(principal.token_id, workspace, principal.subject)
        async with self.session_factory() as session:
            async with session.begin():
                parent = await self.parent(session, workspace, publication_id); binding = await self.binding(session, parent)
                if binding['request_fingerprint'] != expected_fingerprint or binding['artifact_sha256'] != expected_artifact_sha256:
                    raise DispatchError('PUBLISH_APPROVAL_STALE_RELOAD')
                if binding.get('target_binding_sha256') != expected_target_sha256:
                    raise DispatchError('PUBLISH_APPROVAL_TARGET_STALE_RELOAD')
                digest = checksum(binding)
                prior = await session.scalar(select(PublishApprovalORM).where(PublishApprovalORM.publication_id == publication_id, PublishApprovalORM.idempotency_key_hash == key))
                if prior:
                    if prior.binding_sha256 != digest or prior.owner_token_id != principal.token_id or prior.owner_identity_revision != authority:
                        raise DispatchError('PUBLISH_APPROVAL_IDEMPOTENCY_CONFLICT')
                    return self.grant_public(prior)
                grant = PublishApprovalORM(publish_approval_id='pua_' + uuid.uuid4().hex, publication_id=publication_id,
                    workspace_id=workspace, project_id=parent.project_id, idempotency_key_hash=key, binding_json=binding,
                    binding_sha256=digest, owner_token_id=principal.token_id, owner_subject=principal.subject, owner_identity_revision=authority, created_at=now,
                    expires_at=min(now + timedelta(seconds=ttl_seconds), utc(principal.expires_at)), revoked_at=None)
                session.add(grant); await session.flush()
                self.event(session, parent, 'publication.publish_only_approved', principal.token_id,
                    {'publish_approval_id': grant.publish_approval_id, 'binding_sha256': digest, 'scope': 'PUBLISH_ONLY', 'external_action': False})
            return self.grant_public(grant)

    async def revoke(self, workspace, publish_approval_id, *, principal, publication_id=None):
        if not isinstance(principal, HumanPrincipal) or principal.role_for(workspace) != 'owner' or utc(principal.expires_at) <= utc(self.clock()):
            raise DispatchError('HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED')
        self.identity_revision(principal.token_id, workspace, principal.subject)
        async with self.session_factory() as session:
            async with session.begin():
                grant = await session.get(PublishApprovalORM, publish_approval_id)
                if grant is None or grant.workspace_id != workspace or (publication_id is not None and grant.publication_id != publication_id):
                    raise DispatchError('PUBLISH_SCOPE_NOT_FOUND')
                parent = await self.parent(session, workspace, grant.publication_id)
                changed = await session.execute(update(PublishApprovalORM).where(
                    PublishApprovalORM.publish_approval_id == publish_approval_id, PublishApprovalORM.workspace_id == workspace,
                    PublishApprovalORM.revoked_at.is_(None)).values(revoked_at=utc(self.clock())))
                if changed.rowcount == 1:
                    self.event(session, parent, 'publication.publish_only_approval_revoked', principal.token_id,
                        {'publish_approval_id': publish_approval_id, 'external_action': False})
            return self.grant_public(grant)

    @staticmethod
    def grant_public(grant):
        value = {'publish_approval_id': grant.publish_approval_id, 'publication_id': grant.publication_id,
            'workspace_id': grant.workspace_id, 'binding_sha256': grant.binding_sha256,
            'expires_at': utc(grant.expires_at).isoformat(), 'revoked': grant.revoked_at is not None, 'scope': 'PUBLISH_ONLY'}
        if 'target_binding' in grant.binding_json:
            value['target_binding'] = grant.binding_json['target_binding']
            value['target_binding_sha256'] = grant.binding_json['target_binding_sha256']
        return value

    @staticmethod
    def event(session, parent, action, actor, payload):
        session.add(PublicationEventORM(event_id='pue_' + uuid.uuid4().hex, publication_id=parent.publication_id,
            project_id=parent.project_id, event_type=action, actor_ref=actor, payload_json={**payload, 'secret_free': True}, created_at=utc_now()))

    async def valid_grant(self, session, parent, identifier):
        grant = await session.get(PublishApprovalORM, identifier)
        if (grant is None or grant.workspace_id != parent.workspace_id or grant.publication_id != parent.publication_id
            or grant.revoked_at is not None or utc(grant.expires_at) <= utc(self.clock())):
            raise DispatchError('PUBLISH_APPROVAL_REQUIRED_OR_EXPIRED')
        if self.identity_revision(grant.owner_token_id, parent.workspace_id, grant.owner_subject) != grant.owner_identity_revision:
            raise DispatchError('PUBLISH_OWNER_IDENTITY_CHANGED')
        binding = await self.binding(session, parent)
        if checksum(binding) != grant.binding_sha256 or grant.binding_json != binding:
            raise DispatchError('PUBLISH_APPROVAL_STALE_RELOAD')
        return grant

    async def prepare(self, workspace, publication_id, publish_approval_id):
        async with self.session_factory() as session:
            try:
                async with session.begin():
                    parent = await self.parent(session, workspace, publication_id)
                    grant = await self.valid_grant(session, parent, publish_approval_id)
                    row = await session.get(PublicationDispatchORM, publication_id)
                    if row:
                        if row.binding_sha256 != grant.binding_sha256 or row.publish_approval_id != publish_approval_id:
                            raise DispatchError('PUBLISH_DISPATCH_BINDING_CONFLICT')
                        return public(row)
                    row = PublicationDispatchORM(publication_id=publication_id, workspace_id=workspace, project_id=parent.project_id,
                        publish_approval_id=publish_approval_id, binding_sha256=grant.binding_sha256, phase='init_ready', version=1,
                        total_bytes=grant.binding_json['total_bytes'], acknowledged_bytes=0, created_at=utc(self.clock()), updated_at=utc(self.clock()))
                    session.add(row); await session.flush()
                    if parent.status == 'awaiting_publish_approval':
                        changed = await session.execute(update(PublicationORM).where(
                            PublicationORM.publication_id == publication_id, PublicationORM.workspace_id == workspace,
                            PublicationORM.status == 'awaiting_publish_approval').values(status='publishing', updated_at=utc(self.clock())))
                        if changed.rowcount != 1:
                            raise DispatchError('PUBLISH_QUEUE_STALE_RELOAD')
                        self.event(session, parent, 'publication.publish_consent_admitted', 'publishing-service',
                            {'publish_approval_id': publish_approval_id, 'external_action': False})
                    self.event(session, parent, 'publication.dispatch_prepared', 'publishing-service', {'version': 1, 'phase': 'init_ready'})
                return public(row)
            except IntegrityError:
                raise DispatchError('PUBLISH_DISPATCH_CONCURRENT_RESERVATION_RELOAD') from None

    async def get(self, workspace, publication_id):
        async with self.session_factory() as session:
            await self.parent(session, workspace, publication_id)
            row = await session.get(PublicationDispatchORM, publication_id)
            if row is None: raise DispatchError('PUBLISH_DISPATCH_NOT_FOUND')
            return public(row)

    async def intent(self, workspace, publication_id, expected_version, kind, *, offset=None, length=None):
        if type(expected_version) is not int or kind not in ('init', 'chunk', 'reconcile'):
            raise DispatchError('PUBLISH_DISPATCH_REQUEST_INVALID')
        now, identifier = utc(self.clock()), uuid.uuid4().hex
        async with self.session_factory() as session:
            async with session.begin():
                parent = await self.parent(session, workspace, publication_id)
                row = await session.get(PublicationDispatchORM, publication_id)
                if row is None or row.workspace_id != workspace or row.version != expected_version:
                    raise DispatchError('PUBLISH_DISPATCH_STALE_RELOAD')
                if kind != 'reconcile': await self.valid_grant(session, parent, row.publish_approval_id)
                if kind == 'init' and row.phase != 'init_ready':
                    raise DispatchError('PUBLISH_INITIALIZATION_MUST_NOT_REPEAT')
                if kind == 'chunk' and (row.phase != 'upload_ready' or row.private_session_ref is None or type(offset) is not int
                    or type(length) is not int or offset != row.acknowledged_bytes or not 1 <= length <= 16 * 1024 * 1024 or offset + length > row.total_bytes):
                    raise DispatchError('PUBLISH_CHUNK_RECONCILIATION_REQUIRED')
                if kind == 'reconcile' and (row.private_session_ref is None or row.phase not in ('upload_ready', 'chunk_uncertain', 'chunk_intent', 'reconcile_intent')
                    or (row.phase in ('chunk_intent', 'reconcile_intent') and row.lease_until is not None and utc(row.lease_until) > now)):
                    raise DispatchError('PUBLISH_RECONCILIATION_LEASE_OR_SCOPE_INVALID')
                values = {'phase': kind + '_intent', 'intent_id': identifier, 'version': expected_version + 1,
                    'intent_offset': offset if kind == 'chunk' else None, 'intent_end': offset + length if kind == 'chunk' else None,
                    'lease_until': now + timedelta(seconds=self.lease_seconds), 'updated_at': now, 'failure_code': None}
                changed = await session.execute(update(PublicationDispatchORM).where(PublicationDispatchORM.publication_id == publication_id,
                    PublicationDispatchORM.workspace_id == workspace, PublicationDispatchORM.version == expected_version).values(**values))
                if changed.rowcount != 1: raise DispatchError('PUBLISH_DISPATCH_STALE_RELOAD')
                self.event(session, parent, 'publication.' + kind + '_intent_committed', 'publishing-service',
                    {'phase': values['phase'], 'version': values['version'], 'offset': values['intent_offset'], 'end': values['intent_end'], 'external_action': False})
            # Transaction has committed before the ticket can authorize a wire call.
            return DispatchTicket(workspace, publication_id, kind + '_intent', expected_version + 1, identifier)

    async def finish(self, ticket, *, session_ref=None, acknowledged_bytes=None, remote_post_id=None, uncertain=False):
        if not isinstance(ticket, DispatchTicket) or type(uncertain) is not bool:
            raise DispatchError('PUBLISH_DISPATCH_TICKET_INVALID')
        now = utc(self.clock())
        async with self.session_factory() as session:
            async with session.begin():
                parent = await self.parent(session, ticket.workspace_id, ticket.publication_id)
                row = await session.get(PublicationDispatchORM, ticket.publication_id)
                if row is None or row.version != ticket.version or row.phase != ticket.phase or row.intent_id != ticket.intent_id:
                    raise DispatchError('PUBLISH_DISPATCH_STALE_TICKET')
                values = {'version': row.version + 1, 'updated_at': now, 'lease_until': None, 'failure_code': None}
                if uncertain:
                    if session_ref is not None or acknowledged_bytes is not None or remote_post_id is not None:
                        raise DispatchError('PUBLISH_DISPATCH_COMPLETION_INVALID')
                    values.update(phase='init_uncertain' if ticket.phase == 'init_intent' else 'chunk_uncertain', failure_code='PUBLISH_OUTCOME_UNKNOWN')
                elif ticket.phase == 'init_intent':
                    if not isinstance(session_ref, str) or not re.fullmatch(r'pss_[a-f0-9]{32}', session_ref) or acknowledged_bytes is not None or remote_post_id is not None:
                        raise DispatchError('PUBLISH_PRIVATE_SESSION_REFERENCE_REQUIRED')
                    values.update(phase='upload_ready', private_session_ref=session_ref)
                elif ticket.phase in ('chunk_intent', 'reconcile_intent'):
                    if session_ref is not None or type(acknowledged_bytes) is not int or not row.acknowledged_bytes <= acknowledged_bytes <= row.total_bytes:
                        raise DispatchError('PUBLISH_ACKNOWLEDGED_RANGE_INVALID')
                    if ticket.phase == 'chunk_intent' and acknowledged_bytes > row.intent_end:
                        raise DispatchError('PUBLISH_ACKNOWLEDGED_RANGE_INVALID')
                    if remote_post_id is not None:
                        if not isinstance(remote_post_id, str) or not re.fullmatch(r'[A-Za-z0-9._~-]{1,128}', remote_post_id) or acknowledged_bytes != row.total_bytes:
                            raise DispatchError('PUBLISH_REMOTE_RECEIPT_INVALID')
                    elif acknowledged_bytes == row.total_bytes:
                        raise DispatchError('PUBLISH_REMOTE_RECEIPT_REQUIRED')
                    values.update(phase='uploaded' if remote_post_id is not None else 'upload_ready',
                        acknowledged_bytes=acknowledged_bytes, remote_post_id=remote_post_id)
                else:
                    raise DispatchError('PUBLISH_DISPATCH_TICKET_INVALID')
                changed = await session.execute(update(PublicationDispatchORM).where(PublicationDispatchORM.publication_id == row.publication_id,
                    PublicationDispatchORM.workspace_id == ticket.workspace_id, PublicationDispatchORM.version == ticket.version,
                    PublicationDispatchORM.intent_id == ticket.intent_id, PublicationDispatchORM.phase == ticket.phase).values(**values))
                if changed.rowcount != 1: raise DispatchError('PUBLISH_DISPATCH_STALE_TICKET')
                self.event(session, parent, 'publication.dispatch_' + values['phase'], 'publishing-service',
                    {'phase': values['phase'], 'version': values['version'], 'acknowledged_bytes': values.get('acknowledged_bytes', row.acknowledged_bytes),
                        'remote_post_id': remote_post_id, 'failure_code': values['failure_code'], 'external_action': None,
                        'wire_outcome_recorded': True, 'mock_parent': parent.mock})
            return await self.get(ticket.workspace_id, ticket.publication_id)
