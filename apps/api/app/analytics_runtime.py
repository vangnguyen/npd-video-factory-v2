"""Explicit, scoped analytics runtime. Reads never authorize publishing or media changes."""
import asyncio

from .analytics_models import AnalyticsProviderStateRead
from .analytics_providers import AnalyticsCollection, AnalyticsProviderNotConfigured, AnalyticsProviderRegistry
from .analytics_official import (AnalyticsHTTPClient, AnalyticsQuery, AnalyticsOfficialError, account_request,
    confirm_account, confirm_youtube_video, youtube_video_request, youtube_report_request, youtube_metrics,
    tiktok_video_request, tiktok_metrics, resolve_credential, response_digest, video_id)
from .publishing_credentials import target_digest
from .publishing_models import PublishingTargetBinding
from .publishing_profiles import PROVIDER_KEYS
from .db import utc_now


class ScopedOfficialAnalyticsProvider:
    def __init__(self, runtime, platform, workspace):
        self.runtime, self.platform, self.workspace = runtime, platform, workspace
        self.provider_key = AnalyticsProviderRegistry.OFFICIAL_KEYS[platform]

    def state(self, platform):
        if platform != self.platform: raise ValueError('ANALYTICS_PLATFORM_MISMATCH')
        runtime = self.runtime; client = runtime.clients[self.platform]
        configured = (callable(runtime.credential_resolver) and callable(runtime.target_provider)
            and (client.mock or runtime.explicit_cost_policy))
        enabled = configured and client.enabled and runtime.enabled()
        return AnalyticsProviderStateRead(platform=platform, provider_key=self.provider_key, mode='official',
            adapter_state='ready' if enabled else 'not_configured', credential_status='configured' if configured else 'not_configured',
            supports_sync=enabled, external_calls_enabled=enabled and not client.mock,
            real_provider_tested=False, production_deployed=False)

    async def collect(self, context):
        runtime = self.runtime
        if not self.state(context.platform).supports_sync:
            raise AnalyticsProviderNotConfigured('ANALYTICS_SCOPED_RUNTIME_NOT_CONFIGURED')
        if (not self.workspace or context.workspace_id != self.workspace or not context.sync_id
            or type(context.attempt_count) is not int or context.attempt_count < 1):
            raise AnalyticsOfficialError('ANALYTICS_SCOPE_REQUIRED')
        client = runtime.clients[self.platform]
        query = AnalyticsQuery.model_validate(context.query) if context.query is not None else None
        if self.platform == 'youtube' and query is None: raise AnalyticsOfficialError('ANALYTICS_QUERY_REQUIRED')
        if self.platform == 'tiktok' and query is not None: raise AnalyticsOfficialError('ANALYTICS_QUERY_UNSUPPORTED')
        parent, target = await runtime.binding(context, client)
        remote_id = video_id(self.platform, context.remote_post_id)
        observations = []; sequence = 0

        async def send(operation, build):
            nonlocal sequence
            # Gates, lease, receipt and account configuration are checked again for every read.
            await runtime.binding(context, client, expected_target=target)
            await runtime.repository.assert_attempt(context.sync_id, context.attempt_count)
            credential = resolve_credential(runtime.credential_resolver, target, query, now=runtime.clock())
            request = build(credential)
            sequence += 1
            reservation = await runtime.repository.reserve_operation(context, operation, sequence,
                mock=client.mock, target_sha256=target_digest(target), **runtime.cost_policy(parent))
            if not reservation['allowed']: raise AnalyticsOfficialError('ANALYTICS_COST_APPROVAL_REQUIRED')
            try:
                await runtime.binding(context, client, expected_target=target)
                await runtime.repository.assert_attempt(context.sync_id, context.attempt_count)
            except BaseException:
                await runtime.repository.finish_operation(context, reservation, outcome='not_sent')
                raise
            try:
                response = await client.request(request)
            except BaseException:
                await runtime.repository.finish_operation(context, reservation, outcome='outcome_unknown')
                raise
            await runtime.repository.finish_operation(context, reservation, outcome='confirmed')
            observations.append({'operation': operation, 'status': response.status,
                'response_sha256': response_digest(response), 'usage_id': reservation['usage_id'],
                'cost_id': reservation['cost_id'], 'mock': client.mock, 'external_call': not client.mock})
            return response

        async with asyncio.timeout(120):
            account = confirm_account(await send('account_lookup', account_request), target)
            if self.platform == 'youtube':
                confirm_youtube_video(await send('video_ownership', lambda credential: youtube_video_request(credential, remote_id)), target, remote_id)
                metrics, evidence = youtube_metrics(await send('metrics', lambda credential: youtube_report_request(credential, remote_id, query)), query)
            else:
                metrics, evidence = tiktok_metrics(await send('metrics', lambda credential: tiktok_video_request(credential, remote_id)), remote_id)
            await runtime.binding(context, client, expected_target=target)
        return AnalyticsCollection(provider_key=self.provider_key, source='official-api://' + self.platform + '/' + remote_id,
            source_kind='official_api', collected_at=runtime.clock(), metrics=metrics, mock=client.mock, external_call=not client.mock,
            evidence={**evidence, **account, 'publication_receipt_id': parent.receipt.receipt_id,
                'publication_id': context.publication_id, 'request_observations': observations,
                'read_only': True, 'real_provider_tested': False})


class OfficialAnalyticsRuntime:
    def __init__(self, *, repository, publishing_repository, settings, target_provider=None,
                 credential_resolver=None, clients=None, cost_policy=None, clock=utc_now):
        self.repository, self.publishing_repository, self.settings = repository, publishing_repository, settings
        self.target_provider, self.credential_resolver, self.clock = target_provider, credential_resolver, clock
        self.clients = dict(clients or {})
        if any(type(client) is not AnalyticsHTTPClient or platform != client.platform for platform, client in self.clients.items()):
            raise AnalyticsOfficialError('ANALYTICS_RUNTIME_CONFIGURATION_INVALID')
        if cost_policy is not None and not callable(cost_policy): raise AnalyticsOfficialError('ANALYTICS_RUNTIME_CONFIGURATION_INVALID')
        self.explicit_cost_policy = callable(cost_policy)
        self.cost_policy = cost_policy or (lambda _parent: {'estimated_cost': None, 'max_ai_cost': None})

    def enabled(self):
        return all(getattr(self.settings, key, False) is True for key in
            ('analytics_external_execution_enabled', 'provider_external_execution_enabled'))

    def provider(self, platform, workspace):
        return ScopedOfficialAnalyticsProvider(self, platform, workspace) if platform in self.clients else None

    def install(self, registry):
        if type(registry) is not AnalyticsProviderRegistry: raise AnalyticsOfficialError('ANALYTICS_RUNTIME_CONFIGURATION_INVALID')
        registry.scoped_factory = self.provider

    async def binding(self, context, client, expected_target=None):
        if not self.enabled() or not client.enabled: raise AnalyticsOfficialError('ANALYTICS_EXECUTION_DISABLED')
        sync = await self.repository.get_sync_by_id(context.sync_id)
        if (sync is None or sync.project_id != context.project_id or sync.workspace_id != context.workspace_id
            or sync.publication_id != context.publication_id or sync.platform != context.platform):
            raise AnalyticsOfficialError('ANALYTICS_SCOPE_REQUIRED')
        if (sync.trigger == 'scheduled_refresh' or sync.scheduled_for is not None) and not getattr(self.settings, 'analytics_scheduled_refresh_enabled', False):
            raise AnalyticsOfficialError('ANALYTICS_SCHEDULED_REFRESH_DISABLED')
        if not client.mock and not self.explicit_cost_policy: raise AnalyticsOfficialError('ANALYTICS_COST_POLICY_REQUIRED')
        parent = await self.publishing_repository.get(context.project_id, context.publication_id)
        if (parent is None or parent.workspace_id != context.workspace_id or parent.platform != context.platform
            or parent.status != 'published' or parent.receipt is None or parent.receipt.remote_post_id != context.remote_post_id
            or parent.receipt.request_fingerprint != parent.request_fingerprint
            or parent.receipt.platform != parent.platform or parent.receipt.provider_key != parent.provider_key
            or parent.dry_run or parent.mode != 'live'
            or parent.provider_key != PROVIDER_KEYS.get(parent.platform)
            or parent.mock != parent.receipt.mock or parent.external_action != parent.receipt.external_action
            or (not client.mock and (parent.mock or not parent.receipt.external_action))
            or parent.provider_validation is None or parent.provider_validation.target_binding is None):
            raise AnalyticsOfficialError('ANALYTICS_REAL_PUBLICATION_REQUIRED')
        target = parent.provider_validation.target_binding
        try:
            target = PublishingTargetBinding.model_validate(target.model_dump())
            current = self.target_provider(context.workspace_id, context.platform, target.profile_id)
        except Exception: raise AnalyticsOfficialError('ANALYTICS_ACCOUNT_BINDING_REQUIRED') from None
        if (target.workspace_id != context.workspace_id or target.platform != context.platform or target.provider_key != parent.provider_key
            or current != target or expected_target is not None and expected_target != target):
            raise AnalyticsOfficialError('ANALYTICS_ACCOUNT_BINDING_CHANGED')
        return parent, target
