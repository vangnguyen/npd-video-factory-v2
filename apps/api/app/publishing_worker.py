"""One fenced YouTube upload step. Inert unless explicitly injected; no factory wiring."""
import asyncio
from contextlib import suppress
from decimal import Decimal
import uuid

from .publishing_artifact import PublishingArtifactGuard
from .publishing_credentials import (confirm_youtube_account, resolve_youtube_credential, youtube_account_request)
from .publishing_db import PublicationDispatchORM, PublishApprovalORM
from .publishing_dispatch import PublishingDispatchJournal
from .publishing_models import PublicationMetadata, PublishingTargetBinding
from .publishing_operations import PublishingOperationMeter
from .publishing_session_vault import PublishingSessionVault
from .publishing_wire import OfficialHTTPClient
from .youtube_upload import (UNIT, chunk_request, start_request, started_session, status_request, upload_progress)


class PublishingWorkerError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class YouTubePublishingWorker:
    def __init__(self, *, journal, vault, artifact_guard, meter, client, credential_resolver=None, policy_provider=None,
                 category_id=None, made_for_kids=None, contains_synthetic_media=None, chunk_size=8 * 1024 * 1024):
        if (type(journal) is not PublishingDispatchJournal or journal.require_target_binding is not True
            or type(vault) is not PublishingSessionVault or vault.session_factory is not journal.session_factory
            or type(artifact_guard) is not PublishingArtifactGuard
            or artifact_guard.journal is not journal or type(meter) is not PublishingOperationMeter
            or meter.session_factory is not journal.session_factory
            or type(client) is not OfficialHTTPClient or client.platform != 'youtube'
            or type(chunk_size) is not int or not UNIT <= chunk_size <= 16 * 1024 * 1024 or chunk_size % UNIT):
            raise PublishingWorkerError('PUBLISH_WORKER_CONFIGURATION_INVALID')
        self.journal, self.vault, self.guard, self.meter, self.client = journal, vault, artifact_guard, meter, client
        self.credential_resolver, self.policy_provider = credential_resolver, policy_provider
        self.category_id, self.made_for_kids, self.synthetic = category_id, made_for_kids, contains_synthetic_media
        self.chunk_size = chunk_size
        self.mock = client.transport is not None

    def policy(self):
        try:
            value = self.policy_provider() if callable(self.policy_provider) else None
            if not isinstance(value, dict) or any(value.get(key) is not True for key in (
                'publish_enabled', 'publish_external_execution_enabled', 'publish_owner_gate_enabled')):
                raise ValueError()
            cap = value.get('max_ai_cost'); estimates = value.get('estimated_costs', {})
            if cap is not None and (type(cap) is not Decimal or not cap.is_finite() or cap < 0):
                raise ValueError()
            if not isinstance(estimates, dict):
                raise ValueError()
        except Exception:
            raise PublishingWorkerError('PUBLISH_WORKER_OWNER_GATES_REQUIRED') from None
        return cap, dict(estimates)

    async def context(self, workspace, publication_id, *, reconcile=False):
        async with self.journal.session_factory() as session:
            parent = await self.journal.parent(session, workspace, publication_id)
            dispatch = await session.get(PublicationDispatchORM, publication_id)
            if dispatch is None or dispatch.workspace_id != workspace:
                raise PublishingWorkerError('PUBLISH_WORKER_DISPATCH_REQUIRED')
            grant = await session.get(PublishApprovalORM, dispatch.publish_approval_id)
            if (grant is None or grant.workspace_id != workspace or grant.publication_id != publication_id
                or grant.binding_sha256 != dispatch.binding_sha256 or parent.platform != 'youtube'):
                raise PublishingWorkerError('PUBLISH_WORKER_BINDING_REQUIRED')
            if not reconcile:
                await self.journal.valid_grant(session, parent, grant.publish_approval_id)
            target = self.journal.target_binding(parent)
            if target is None or grant.binding_json.get('target_binding') != target:
                raise PublishingWorkerError('PUBLISH_WORKER_TARGET_CHANGED')
            if self.mock and not parent.mock:
                parent.mock = True
                await session.commit()
            elif not self.mock and parent.mock:
                raise PublishingWorkerError('PUBLISH_WORKER_MOCK_CANNOT_GO_LIVE')
            return {'phase': dispatch.phase, 'version': dispatch.version, 'size': dispatch.total_bytes,
                'offset': dispatch.acknowledged_bytes, 'ref': dispatch.private_session_ref,
                'binding_sha256': dispatch.binding_sha256, 'target': PublishingTargetBinding.model_validate(target),
                'metadata': PublicationMetadata.model_validate(parent.metadata_json)}

    async def send(self, workspace, publication_id, request, operation, *, credential, ticket=None):
        resolve_youtube_credential(lambda _: credential, credential.target, now=self.journal.clock())
        policy = self.policy(); cap, estimates = policy
        mock = self.client.transport is not None
        if mock != self.mock:
            raise PublishingWorkerError('PUBLISH_WORKER_TRANSPORT_MODE_CHANGED')
        reservation = await self.meter.admit(workspace, publication_id, operation,
            request_identity=uuid.uuid4().hex, estimated_cost=estimates.get(operation), max_ai_cost=cap, mock=mock)
        if not reservation.allowed:
            raise PublishingWorkerError('PUBLISH_COST_APPROVAL_REQUIRED')
        if ticket is not None:
            # Claim happens only after cost admission. A failed claim proves this
            # particular reservation was unsent and releases its budget estimate.
            try:
                ticket = await self.journal.intent(workspace, publication_id, ticket['version'], ticket['kind'],
                    **ticket.get('range', {}))
            except BaseException:
                await self.meter.finish(workspace, publication_id, reservation, outcome='not_sent')
                raise
        sent = False
        try:
            if self.policy() != policy:
                raise PublishingWorkerError('PUBLISH_WORKER_POLICY_CHANGED_RELOAD')
            async with asyncio.timeout(60):
                sent = True
                response = await self.client.request(request)
        except BaseException:
            with suppress(Exception):
                await self.meter.finish(workspace, publication_id, reservation, outcome='outcome_unknown' if sent else 'not_sent')
            if ticket is not None:
                with suppress(Exception): await self.journal.finish(ticket, uncertain=True)
            raise
        await self.meter.finish(workspace, publication_id, reservation, outcome='confirmed')
        return response, ticket

    async def step(self, workspace, publication_id):
        self.policy()
        public = await self.journal.get(workspace, publication_id)
        phase = public['phase']
        if phase in ('init_intent', 'init_uncertain'):
            raise PublishingWorkerError('PUBLISH_INITIALIZATION_REVIEW_REQUIRED')
        if phase == 'uploaded':
            return {**public, 'processing_acceptance': 'NOT_CHECKED', 'published': False, 'mock': self.mock}
        reconcile = phase in ('chunk_intent', 'chunk_uncertain', 'reconcile_intent')
        context = await self.context(workspace, publication_id, reconcile=reconcile)
        upload = None
        if phase == 'init_ready':
            self.vault.cipher()  # unavailable key/crypto refuses before account/init wire calls
        else:
            upload = await self.vault.load(workspace, publication_id, context['ref'], expected_binding_sha256=context['binding_sha256'])
        credential = resolve_youtube_credential(self.credential_resolver, context['target'], now=self.journal.clock())
        response, _ = await self.send(workspace, publication_id, youtube_account_request(credential), 'account_lookup', credential=credential)
        confirm_youtube_account(response, context['target'])
        ticket = None
        try:
            if reconcile:
                request = status_request(upload, credential.token)
                response, ticket = await self.send(workspace, publication_id, request, 'reconcile', credential=credential,
                    ticket={'version': context['version'], 'kind': 'reconcile'})
                progress = upload_progress(response, upload)
                if progress.acknowledged_bytes is None:
                    raise PublishingWorkerError('PUBLISH_SESSION_REVIEW_REQUIRED')
                return await self.journal.finish(ticket, acknowledged_bytes=progress.acknowledged_bytes, remote_post_id=progress.remote_video_id)
            async with self.guard.open(workspace, publication_id) as artifact:
                if artifact.binding_sha256 != context['binding_sha256']:
                    raise PublishingWorkerError('PUBLISH_WORKER_ARTIFACT_CHANGED')
                # Refresh/exact target/scopes/expiry again after media QC.
                fresh_credential = resolve_youtube_credential(self.credential_resolver, context['target'], now=self.journal.clock())
                if fresh_credential.token != credential.token:
                    response, _ = await self.send(workspace, publication_id, youtube_account_request(fresh_credential), 'account_lookup', credential=fresh_credential)
                    confirm_youtube_account(response, context['target'])
                credential = fresh_credential
                if phase == 'init_ready':
                    request = start_request(context['metadata'], artifact.size_bytes, credential.token, category_id=self.category_id,
                        made_for_kids=self.made_for_kids, contains_synthetic_media=self.synthetic, now=self.journal.clock())
                    response, ticket = await self.send(workspace, publication_id, request, 'initialize', credential=credential,
                        ticket={'version': context['version'], 'kind': 'init'})
                    upload = started_session(response, artifact.size_bytes)
                    reference = await self.vault.save(ticket, upload)
                    return await self.journal.finish(ticket, session_ref=reference)
                if phase != 'upload_ready':
                    raise PublishingWorkerError('PUBLISH_WORKER_PHASE_INVALID')
                length = min(self.chunk_size, context['size'] - context['offset'])
                content = artifact.read(context['offset'], length)
                request = chunk_request(upload, context['offset'], content, credential.token, chunk_size=self.chunk_size)
                response, ticket = await self.send(workspace, publication_id, request, 'chunk', credential=credential, ticket={'version': context['version'], 'kind': 'chunk',
                    'range': {'offset': context['offset'], 'length': length}})
                progress = upload_progress(response, upload)
                if progress.acknowledged_bytes is None:
                    raise PublishingWorkerError('PUBLISH_SESSION_REVIEW_REQUIRED')
                return await self.journal.finish(ticket, acknowledged_bytes=progress.acknowledged_bytes, remote_post_id=progress.remote_video_id)
        except BaseException:
            if ticket is not None:
                with suppress(Exception): await self.journal.finish(ticket, uncertain=True)
            raise
