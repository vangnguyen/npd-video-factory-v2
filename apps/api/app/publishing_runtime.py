"""Explicit server-owned YouTube registration; construction performs no wire calls."""
from sqlalchemy import select

from .db import utc_now
from .publishing_artifact import PublishingArtifactGuard
from .publishing_db import PublicationORM
from .publishing_dispatch import PublishingDispatchJournal, DispatchError
from .publishing_logic import validation_check
from .publishing_models import ProviderValidationRead, PublicationReceipt, PublicationSubmission
from .publishing_operations import PublishingOperationMeter
from .publishing_profiles import PublishingProfileRegistry, PublishingProfileError, PROVIDER_KEYS
from .publishing_providers import ExternalPublishingNotActivated
from .publishing_scheduler import PublishingScheduler, PublishingWorkQueue
from .publishing_session_vault import PublishingSessionVault
from .publishing_wire import OfficialHTTPClient
from .publishing_worker import YouTubePublishingWorker


class ScopedYouTubePublishingProvider:
    platform = 'youtube'
    provider_key = PROVIDER_KEYS['youtube']

    def __init__(self, runtime, workspace=None, profile_id=None):
        self.runtime, self.workspace, self.profile_id = runtime, workspace, profile_id

    def validate(self):
        runtime = self.runtime; profile = None
        if self.workspace is not None:
            try: profile = runtime.profiles.select(self.workspace, 'youtube', self.profile_id)
            except PublishingProfileError: pass
        configured = profile.youtube_ready() if profile else self.workspace is None and runtime.profiles.has_platform('youtube', require_youtube_ready=True)
        gates = all(getattr(runtime.service.settings, key, False) is True for key in (
            'publish_enabled', 'publish_external_execution_enabled', 'publish_owner_gate_enabled'))
        resolvers = callable(runtime.credential_resolver) and callable(runtime.key_provider)
        transport = runtime.client.transport is not None or runtime.client.network_enabled is True
        ready = bool(configured and gates and resolvers and transport)
        checks = [validation_check(name, bool(passed), code, message, **evidence) for name, passed, code, message, evidence in (
            ('profile', configured, 'PUBLISH_PROFILE_CONFIGURED' if configured else 'PUBLISH_PROFILE_REQUIRED',
                'Scoped profile configuration; not official account verification.', {}),
            ('owner-gates', gates, 'PUBLISH_OWNER_GATES_CONFIGURED' if gates else 'PUBLISH_OWNER_GATES_REQUIRED', 'Current publishing enablement flags.', {}),
            ('resolvers', resolvers, 'PUBLISH_RESOLVERS_CONFIGURED' if resolvers else 'PUBLISH_RESOLVERS_REQUIRED',
                'Resolver callbacks configured; actual keys/OAuth are checked before wire.', {}),
            ('transport', transport, 'PUBLISH_TRANSPORT_CONFIGURED' if transport else 'PUBLISH_TRANSPORT_DISABLED',
                'Official bounded transport configuration.', {'mock_transport': runtime.client.transport is not None}),
        )]
        if profile:
            checks.append(validation_check('profile-revision', True, 'PUBLISH_PROFILE_REVISION_BOUND',
                'The complete public profile revision is bound.', profile_sha256=profile.fingerprint()))
        return ProviderValidationRead(provider_key=self.provider_key, adapter_state='ready' if ready else 'not_configured',
            credential_status='configured' if resolvers else 'not_configured', supports_dry_run=False,
            supports_live_publish=ready, checks=checks, target_binding=profile.target if profile else None,
            mock_execution=runtime.client.transport is not None)

    async def publish(self, context):
        """Submit already approved work, rather than manufacture a terminal receipt."""
        validation = self.validate()
        if self.workspace is None or not validation.supports_live_publish or context.publication_id is None or context.publish_approval_id is None:
            raise ExternalPublishingNotActivated('PUBLISH_SCOPED_CONSENT_REQUIRED')
        parent = await self.runtime.service.get(context.project_id, context.publication_id)
        if (parent is None or parent.workspace_id != self.workspace or parent.platform != 'youtube' or context.platform != 'youtube'
            or parent.provider_validation is None or parent.provider_validation.target_binding != validation.target_binding
            or parent.request_fingerprint != context.request_fingerprint or parent.final_render_id != context.final_render_id
            or parent.output_asset_id != context.output_asset_id or parent.metadata != context.metadata):
            raise ExternalPublishingNotActivated('PUBLISH_EXECUTION_CONTEXT_MISMATCH')
        await self.runtime.journal.prepare(self.workspace, parent.publication_id, context.publish_approval_id)
        work = await self.runtime.queue.enqueue(self.workspace, parent.publication_id)
        return PublicationSubmission(work_id=work['work_id'], publication_id=parent.publication_id,
            status=work['status'], mock=self.runtime.client.transport is not None)

    async def get_status(self, receipt):
        if self.workspace is not None and type(receipt) is PublicationSubmission:
            work = await self.runtime.queue.get(self.workspace, receipt.work_id)
            if work['publication_id'] != receipt.publication_id:
                raise ExternalPublishingNotActivated('PUBLISH_RECEIPT_SCOPE_REQUIRED')
            return work['status']
        if self.workspace is None or not isinstance(receipt, PublicationReceipt):
            raise ExternalPublishingNotActivated('PUBLISH_RECEIPT_SCOPE_REQUIRED')
        async with self.runtime.session_factory() as session:
            parent = await session.scalar(select(PublicationORM).where(PublicationORM.workspace_id == self.workspace,
                PublicationORM.platform == 'youtube', PublicationORM.provider_key == self.provider_key,
                PublicationORM.receipt_json['receipt_id'].as_string() == receipt.receipt_id))
            if parent is None or parent.receipt_json != receipt.model_dump(mode='json'):
                raise ExternalPublishingNotActivated('PUBLISH_RECEIPT_SCOPE_REQUIRED')
            selected = self.runtime.profiles.select(self.workspace, 'youtube', self.profile_id)
            if (parent.provider_validation_json or {}).get('target_binding') != selected.target.model_dump(mode='json'):
                raise ExternalPublishingNotActivated('PUBLISH_RECEIPT_SCOPE_REQUIRED')
            publication_id = parent.publication_id
        worker = await self.runtime.worker_for(self.workspace, publication_id)
        return (await worker.poll_processing(self.workspace, publication_id))['status']

    async def delete_or_cancel_if_supported(self, receipt):
        # A receipt is not separate Owner authorization for irreversible deletion.
        return False


class YouTubePublishingRuntime:
    def __init__(self, *, service, profiles, storage, private_root, identity_provider=None,
                 credential_resolver=None, key_provider=None, client=None, clock=utc_now,
                 ffmpeg='ffmpeg', ffprobe='ffprobe'):
        if type(profiles) is not PublishingProfileRegistry:
            raise PublishingProfileError('PUBLISH_RUNTIME_CONFIGURATION_INVALID')
        client = client or OfficialHTTPClient('youtube')
        if type(client) is not OfficialHTTPClient or client.platform != 'youtube':
            raise PublishingProfileError('PUBLISH_RUNTIME_CONFIGURATION_INVALID')
        self.service, self.profiles, self.client = service, profiles, client
        self.credential_resolver, self.key_provider = credential_resolver, key_provider
        self.session_factory, self.clock = service.repository.session_factory, clock
        self.journal = PublishingDispatchJournal(self.session_factory, identity_provider=identity_provider,
            target_provider=profiles.target, require_target_binding=True, clock=clock)
        self.queue = PublishingWorkQueue(self.journal)
        self.vault = PublishingSessionVault(self.session_factory, key_provider=key_provider, clock=clock)
        self.guard = PublishingArtifactGuard(self.journal, storage, private_root, ffmpeg_path=str(ffmpeg), ffprobe_path=str(ffprobe))
        self.meter = PublishingOperationMeter(self.session_factory, clock=clock)

    def install(self):
        """Explicit installation only; no task, request, secret read or auto-enablement."""
        service = self.service
        previous = service.providers.scoped_factory
        other = {key: value for key, value in service.providers.official.items() if key != 'youtube'}
        def select_provider(platform, workspace, profile_id):
            if platform == 'youtube': return ScopedYouTubePublishingProvider(self, workspace, profile_id)
            return previous(platform, workspace, profile_id) if callable(previous) else other[platform]
        service.providers.scoped_factory = select_provider
        service.providers.official['youtube'] = ScopedYouTubePublishingProvider(self)
        service.dispatch_journal, service.work_queue, service.dispatch_worker = self.journal, self.queue, self
        return self

    async def worker_for(self, workspace, publication_id, admission_guard=None):
        async with self.session_factory() as session:
            parent = await self.journal.parent(session, workspace, publication_id)
            binding = (parent.provider_validation_json or {}).get('target_binding')
            if not isinstance(binding, dict) or parent.platform != 'youtube':
                raise PublishingProfileError('PUBLISH_RUNTIME_TARGET_REQUIRED')
            profile = self.profiles.resolve(workspace, binding.get('profile_id'))
            provider_key = parent.provider_key
        if profile.target.model_dump(mode='json') != binding or provider_key != profile.target.provider_key:
            raise PublishingProfileError('PUBLISH_RUNTIME_TARGET_CHANGED')
        def policy():
            current = self.profiles.resolve(workspace, profile.target.profile_id)
            if current != profile: raise PublishingProfileError('PUBLISH_RUNTIME_PROFILE_CHANGED')
            return {**{key: getattr(self.service.settings, key, False) for key in (
                'publish_enabled', 'publish_external_execution_enabled', 'publish_owner_gate_enabled')},
                'max_ai_cost': current.max_ai_cost, 'estimated_costs': dict(current.estimated_costs)}
        return YouTubePublishingWorker(journal=self.journal, vault=self.vault, artifact_guard=self.guard,
            meter=self.meter, client=self.client, credential_resolver=self.credential_resolver, policy_provider=policy,
            category_id=profile.category_id, made_for_kids=profile.made_for_kids,
            contains_synthetic_media=profile.contains_synthetic_media, admission_guard=admission_guard)

    async def run_one(self, workspace, work_id, expected_version):
        work = await self.queue.get(workspace, work_id)
        async def factory(guard):
            # Resolution is inside the owned bounded step so configuration failures
            # persist review state rather than repeatedly breaking a due scan.
            return await self.worker_for(workspace, work['publication_id'], guard)
        return await PublishingScheduler(self.queue, factory).run_one(workspace, work_id, expected_version)

    async def run_due(self, workspace, *, limit=8):
        results = []
        for work in await self.queue.due(workspace, limit=limit):
            try:
                results.append(await self.run_one(workspace, work['work_id'], work['version']))
            except DispatchError as error:
                if error.code not in ('PUBLISH_WORK_NOT_DUE_OR_STALE', 'PUBLISH_WORK_OWNERSHIP_LOST', 'PUBLISH_WORK_SCOPE_NOT_FOUND'):
                    raise
                # Another worker owns or completed this item; keep processing the
                # batch without claiming a persisted state change for the loser.
                results.append({**work, 'execution_status': 'not_claimed', 'execution_code': error.code})
        return results
