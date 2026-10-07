"""Application admission for Owner intent; never resolves tokens or contacts platforms."""
from .analytics_refresh_repository import AnalyticsRefreshRepository, AnalyticsRefreshError
from .analytics_refresh_models import AnalyticsRefreshCreate
from .publishing_credentials import target_digest


class AnalyticsRefreshService:
    def __init__(self, analytics_service):
        self.analytics = analytics_service
        self.repository = AnalyticsRefreshRepository(analytics_service.repository.session_factory)

    async def validate(self, project, config, *, enabled):
        parent = await self.analytics.publishing_repository.get(project, config.publication_id)
        if parent is None: raise AnalyticsRefreshError('ANALYTICS_REFRESH_PUBLICATION_NOT_FOUND')
        if parent.status not in ('published', 'dry_run_succeeded'):
            raise AnalyticsRefreshError('ANALYTICS_REFRESH_PUBLICATION_NOT_READY')
        target = parent.provider_validation.target_binding if parent.provider_validation else None
        if config.provider_mode == 'official':
            if parent.status != 'published' or parent.mode != 'live' or parent.dry_run or not target:
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_BOUND_PUBLICATION_REQUIRED')
            if target.workspace_id != parent.workspace_id or target.platform != parent.platform or target.provider_key != parent.provider_key:
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_BOUND_PUBLICATION_REQUIRED')
            if parent.platform == 'youtube' and config.query_policy not in ('fixed_dates', 'rolling_complete_days'):
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_QUERY_REQUIRED')
            if parent.platform == 'tiktok' and config.query_policy != 'cumulative':
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_QUERY_UNSUPPORTED')
        provider = self.analytics.providers.get(platform=parent.platform, mode=config.provider_mode, workspace=parent.workspace_id)
        if enabled:
            if not self.analytics.settings.analytics_scheduled_refresh_enabled:
                raise AnalyticsRefreshError('ANALYTICS_SCHEDULED_REFRESH_DISABLED')
            if config.provider_mode == 'fixture' and not self.analytics.settings.analytics_fixture_enabled:
                raise AnalyticsRefreshError('ANALYTICS_FIXTURE_DISABLED')
            if not provider.state(parent.platform).supports_sync:
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_PROVIDER_NOT_CONFIGURED')
        return parent, provider, target

    async def create(self, project, config, *, actor, key):
        parent, provider, target = await self.validate(project, config, enabled=config.enabled)
        return await self.repository.create(workspace=parent.workspace_id, project=project, config=config,
            provider_key=provider.provider_key, target_sha256=target_digest(target) if target else None,
            publication_fingerprint=parent.request_fingerprint, actor=actor, key=key)

    async def change_state(self, project, plan_id, payload, *, actor):
        plan = await self.repository.get(project, plan_id)
        if plan is None: raise AnalyticsRefreshError('ANALYTICS_REFRESH_NOT_FOUND')
        if payload.enabled:
            parent, provider, target = await self.validate(project, plan.config, enabled=True)
            if (provider.provider_key != plan.provider_key or parent.request_fingerprint != (await self._fingerprint(plan_id))
                or (target_digest(target) if target else None) != plan.target_binding_sha256):
                raise AnalyticsRefreshError('ANALYTICS_REFRESH_BINDING_CHANGED')
        return await self.repository.change_state(project, plan_id, revision=payload.expected_revision, enabled=payload.enabled, actor=actor)

    async def _fingerprint(self, plan_id):
        from .analytics_refresh_db import AnalyticsRefreshPlanORM
        async with self.repository.factory() as session:
            row = await session.get(AnalyticsRefreshPlanORM, plan_id)
            return row.publication_fingerprint if row else None
