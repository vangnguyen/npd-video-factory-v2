from __future__ import annotations

from datetime import timedelta
from typing import Protocol

from .analytics_logic import (
    analytics_request_fingerprint,
    assess_winner,
    hash_idempotency_key,
    learning_insights,
)
from .analytics_models import (
    AnalyticsEventRead,
    AnalyticsMetricSnapshotRead,
    AnalyticsProviderStateRead,
    AnalyticsReportRead,
    AnalyticsSyncRead,
    AnalyticsSyncRequest,
    LearningInsightRead,
    VideoFeatureMetadata,
    WinnerAssessmentRead,
)
from .analytics_providers import (
    AnalyticsCollectionContext,
    AnalyticsProviderNotConfigured,
    AnalyticsProviderRegistry,
    AnalyticsRateLimited,
)
from .analytics_repository import AnalyticsRepository, AnalyticsRefreshPlanDisabled
from .db import utc_now
from .timeline_models import TimelineSnapshot


ANALYTICS_SYNC_QUEUE_KEY = "npd:video-factory:v2:analytics:queued"
ANALYTICS_SYNC_PROCESSING_KEY = "npd:video-factory:v2:analytics:processing"

# Atomic list admission on the repository's Redis 7 profile. The stable sync ID
# plus the database attempt fence prevent replaying a collection after completion.
ANALYTICS_QUEUE_ADMISSION = """
if redis.call('LPOS', KEYS[1], ARGV[1]) or redis.call('LPOS', KEYS[2], ARGV[1]) then
  return 0
end
redis.call('RPUSH', KEYS[1], ARGV[1])
return 1
"""


async def enqueue_analytics_sync(redis, sync_id):
    import re
    if not isinstance(sync_id, str) or not re.fullmatch(r'ans_[A-Za-z0-9_-]{4,60}', sync_id):
        raise ValueError('ANALYTICS_QUEUE_IDENTIFIER_INVALID')
    return bool(await redis.eval(ANALYTICS_QUEUE_ADMISSION, 2,
        ANALYTICS_SYNC_QUEUE_KEY, ANALYTICS_SYNC_PROCESSING_KEY, sync_id))


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


class AnalyticsBoundaryError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


class AnalyticsService:
    def __init__(
        self,
        *,
        repository: AnalyticsRepository,
        publishing_repository,
        platform_repository,
        providers: AnalyticsProviderRegistry,
        queue: QueueClient,
        settings,
    ):
        self.repository = repository
        self.publishing_repository = publishing_repository
        self.platform_repository = platform_repository
        self.providers = providers
        self.queue = queue
        self.settings = settings

    async def create_sync(
        self,
        *,
        project_id: str,
        payload: AnalyticsSyncRequest,
        idempotency_key: str,
    ) -> tuple[AnalyticsSyncRead, bool]:
        project = await self.platform_repository.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        publication = await self.publishing_repository.get(project_id, payload.publication_id)
        if publication is None:
            raise KeyError(payload.publication_id)
        if publication.status not in {"dry_run_succeeded", "published"}:
            raise AnalyticsBoundaryError(
                "ANALYTICS_PUBLICATION_NOT_READY",
                "Analytics requires a successful publication receipt or a clearly labelled mock receipt.",
            )
        if payload.provider_mode == "fixture" and not self.settings.analytics_fixture_enabled:
            raise AnalyticsBoundaryError(
                "ANALYTICS_FIXTURE_DISABLED",
                "Deterministic analytics fixtures are disabled in this environment.",
            )
        if (payload.trigger == "scheduled_refresh" or payload.scheduled_for is not None) and not self.settings.analytics_scheduled_refresh_enabled:
            raise AnalyticsBoundaryError(
                "ANALYTICS_SCHEDULED_REFRESH_DISABLED",
                "Scheduled analytics refresh is disabled until an owner enables the read-only scheduler gate.",
            )
        provider = self.providers.get(platform=publication.platform, mode=payload.provider_mode, workspace=publication.workspace_id)
        if payload.provider_mode == 'official' and provider.state(publication.platform).supports_sync:
            if publication.status != 'published' or publication.dry_run or publication.mode != 'live':
                raise AnalyticsBoundaryError('ANALYTICS_REAL_PUBLICATION_REQUIRED', 'Configured official analytics requires a bound publication receipt.')
            if publication.platform == 'youtube' and payload.query is None:
                raise AnalyticsBoundaryError('ANALYTICS_QUERY_REQUIRED', 'YouTube analytics requires an explicit date interval.')
            if publication.platform == 'tiktok' and payload.query is not None:
                raise AnalyticsBoundaryError('ANALYTICS_QUERY_UNSUPPORTED', 'TikTok video counters are cumulative, not a date-range report.')
        sync, replay = await self.repository.reserve_sync(
            workspace_id=publication.workspace_id,
            project_id=project_id,
            publication_id=publication.publication_id,
            platform=publication.platform,
            provider_key=provider.provider_key,
            provider_mode=payload.provider_mode,
            trigger=payload.trigger,
            fixture_profile=payload.fixture_profile,
            scheduled_for=payload.scheduled_for,
            idempotency_key_hash=hash_idempotency_key(idempotency_key),
            request_fingerprint=analytics_request_fingerprint(payload),
            max_attempts=self.settings.analytics_max_attempts,
            actor_ref=payload.actor_ref,
            query=payload.query,
        )
        if sync.status == "queued":
            await self.queue.rpush(ANALYTICS_SYNC_QUEUE_KEY, sync.sync_id)
        return sync, replay

    async def get_sync(self, project_id: str, sync_id: str) -> AnalyticsSyncRead | None:
        return await self.repository.get_sync(project_id, sync_id)

    async def list_syncs(self, project_id: str) -> list[AnalyticsSyncRead]:
        return await self.repository.list_syncs(project_id)

    async def report(self, project_id: str) -> AnalyticsReportRead:
        if await self.platform_repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.report(project_id)

    async def publication_report(self, project_id, publication_id, *, provider_mode=None):
        if await self.publishing_repository.get(project_id, publication_id) is None: raise KeyError(publication_id)
        return await self.repository.report(project_id, publication_id=publication_id, provider_mode=provider_mode)

    async def publication_snapshots(self, project_id, publication_id, *, provider_mode=None):
        if await self.publishing_repository.get(project_id, publication_id) is None: raise KeyError(publication_id)
        return await self.repository.list_snapshots(project_id, publication_id=publication_id, provider_mode=provider_mode)

    async def observations(self, project_id, publication_id, *, provider_mode, limit, cursor=None):
        publication = await self.publishing_repository.get(project_id, publication_id)
        if publication is None: raise KeyError(publication_id)
        from .analytics_views import observation_page
        return await observation_page(self.repository.session_factory, workspace=publication.workspace_id,
            project=project_id, publication=publication_id, mode=provider_mode, limit=limit, cursor=cursor)

    async def channel_observations(self, workspace_id, *, provider_mode, limit, cursor=None):
        if await self.platform_repository.get_workspace(workspace_id) is None: raise KeyError(workspace_id)
        from .analytics_views import channel_page
        return await channel_page(self.repository.session_factory, workspace=workspace_id,
            mode=provider_mode, limit=limit, cursor=cursor)

    async def snapshots(self, project_id: str) -> list[AnalyticsMetricSnapshotRead]:
        if await self.platform_repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_snapshots(project_id)

    async def assessments(self, project_id: str) -> list[WinnerAssessmentRead]:
        if await self.platform_repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_assessments(project_id)

    async def insights(self, project_id: str) -> list[LearningInsightRead]:
        if await self.platform_repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_insights(project_id)

    async def events(self, project_id: str) -> list[AnalyticsEventRead]:
        if await self.platform_repository.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_events(project_id)

    def provider_states(self) -> list[AnalyticsProviderStateRead]:
        return self.providers.states()

    async def enqueue_due(self) -> list[str]:
        identifiers = await self.repository.activate_due_sync_ids()
        for sync_id in identifiers:
            await self.queue.rpush(ANALYTICS_SYNC_QUEUE_KEY, sync_id)
        return identifiers


class AnalyticsSyncProcessor:
    def __init__(
        self,
        *,
        repository: AnalyticsRepository,
        publishing_repository,
        platform_repository,
        trend_repository,
        timeline_repository,
        production_repository,
        providers: AnalyticsProviderRegistry,
        settings,
    ):
        self.repository = repository
        self.publishing_repository = publishing_repository
        self.platform_repository = platform_repository
        self.trend_repository = trend_repository
        self.timeline_repository = timeline_repository
        self.production_repository = production_repository
        self.providers = providers
        self.settings = settings

    async def process(self, sync_id: str) -> AnalyticsSyncRead:
        sync = await self.repository.claim(sync_id)
        if sync is None:
            busy = await self.repository.get_sync_by_id(sync_id)
            if busy is None: raise KeyError(sync_id)
            return busy
        if sync.status != "running":
            return sync
        if (sync.trigger == 'scheduled_refresh' or sync.scheduled_for is not None) and not self.settings.analytics_scheduled_refresh_enabled:
            return await self.repository.terminal_failure(sync_id, status='not_configured',
                code='ANALYTICS_SCHEDULED_REFRESH_DISABLED', reason='Scheduled analytics refresh is disabled.',
                expected_attempt=sync.attempt_count)
        publication = await self.publishing_repository.get(sync.project_id, sync.publication_id)
        if publication is None:
            return await self.repository.terminal_failure(
                sync_id,
                status="failed",
                code="ANALYTICS_PUBLICATION_MISSING",
                reason="The source publication no longer exists.",
                expected_attempt=sync.attempt_count,
            )
        provider = self.providers.get(platform=sync.platform, mode=sync.provider_mode, workspace=sync.workspace_id)
        provider_state = provider.state(sync.platform)
        if not provider_state.supports_sync:
            return await self.repository.terminal_failure(
                sync_id,
                status="not_configured",
                code="ANALYTICS_PROVIDER_NOT_CONFIGURED",
                reason=(
                    f"{provider.provider_key} is {provider_state.adapter_state}; "
                    "V2-10 does not activate official analytics API calls."
                ),
                expected_attempt=sync.attempt_count,
            )
        if sync.provider_mode == "fixture" and not self.settings.analytics_fixture_enabled:
            return await self.repository.terminal_failure(
                sync_id,
                status="not_configured",
                code="ANALYTICS_FIXTURE_DISABLED",
                reason="Deterministic analytics fixtures are disabled in this environment.",
                expected_attempt=sync.attempt_count,
            )
        try:
            await self.repository.assert_attempt(sync.sync_id, sync.attempt_count)
            collection = await provider.collect(
                AnalyticsCollectionContext(
                    platform=sync.platform,
                    project_id=sync.project_id,
                    publication_id=sync.publication_id,
                    remote_post_id=publication.receipt.remote_post_id if publication.receipt else None,
                    fixture_profile=sync.fixture_profile,
                    workspace_id=sync.workspace_id,
                    sync_id=sync.sync_id,
                    attempt_count=sync.attempt_count,
                    query=sync.query,
                )
            )
            features = await self._capture_features(sync, publication)
            cost = await self.platform_repository.project_cost_summary(sync.project_id)
            assessment = assess_winner(
                collection.metrics,
                video_duration_seconds=features.duration_seconds,
                production_cost_vnd=(
                    float(cost.actual_cost_total)
                    if cost.actual_cost_complete and cost.actual_cost_total is not None
                    else None
                ),
            )
            assessment.evidence.append(
                "Production-cost input covers recorded operations only: "
                f"records={cost.records}; unknown_actual_cost_operations="
                f"{cost.unknown_actual_cost_operations}; actual_cost_complete="
                f"{cost.actual_cost_complete}; estimated spend and budget reservations "
                "are excluded. This does not certify full project billing coverage."
            )
            insights = learning_insights(
                assessment=assessment,
                features=features,
                snapshot_ref=f"analytics-sync:{sync.sync_id}",
            )
            return await self.repository.complete(
                sync.sync_id,
                collection=collection,
                features=features,
                assessment=assessment,
                insights=insights,
                expected_attempt=sync.attempt_count,
            )
        except AnalyticsRefreshPlanDisabled as exc:
            return await self.repository.terminal_failure(sync.sync_id, status='not_configured', code=exc.code,
                reason=exc.code, expected_attempt=sync.attempt_count)
        except AnalyticsProviderNotConfigured as exc:
            return await self.repository.terminal_failure(
                sync.sync_id,
                status="not_configured",
                code="ANALYTICS_PROVIDER_NOT_CONFIGURED",
                reason=str(exc),
                expected_attempt=sync.attempt_count,
            )
        except AnalyticsRateLimited as exc:
            delay = max(exc.retry_after_seconds, min(self.settings.analytics_retry_max_seconds,
                self.settings.analytics_retry_base_seconds * (2 ** max(0, sync.attempt_count - 1))))
            return await self.repository.schedule_retry(
                sync.sync_id,
                next_retry_at=utc_now() + timedelta(seconds=delay),
                code="ANALYTICS_RATE_LIMITED",
                reason=str(exc),
                expected_attempt=sync.attempt_count,
            )
        except Exception as exc:
            from .analytics_official import AnalyticsOfficialError
            if isinstance(exc, AnalyticsOfficialError):
                return await self.repository.terminal_failure(sync.sync_id,
                    status='not_configured' if exc.code in ('ANALYTICS_OAUTH_NOT_CONFIGURED', 'ANALYTICS_OAUTH_REFRESH_REQUIRED', 'ANALYTICS_SCHEDULED_REFRESH_DISABLED') else 'failed',
                    code=exc.code, reason=exc.code, expected_attempt=sync.attempt_count)
            delay = min(
                self.settings.analytics_retry_max_seconds,
                self.settings.analytics_retry_base_seconds * (2 ** max(0, sync.attempt_count - 1)),
            )
            return await self.repository.schedule_retry(
                sync.sync_id,
                next_retry_at=utc_now() + timedelta(seconds=delay),
                code="ANALYTICS_PROVIDER_ERROR",
                reason=getattr(exc, 'code', 'ANALYTICS_COLLECTION_FAILED'),
                expected_attempt=sync.attempt_count,
            )

    async def _capture_features(self, sync: AnalyticsSyncRead, publication) -> VideoFeatureMetadata:
        project = await self.platform_repository.get_project(sync.project_id)
        if project is None:
            raise KeyError(sync.project_id)
        version = (
            await self.platform_repository.get_version(project.current_version_id)
            if project.current_version_id
            else None
        )
        snapshot = dict(version.snapshot) if version else {}
        source_idea = dict(snapshot.get("source_idea") or {})
        linked_idea = await self.trend_repository.get_idea_for_project(sync.project_id)
        frozen = await self.production_repository.get_render_context(publication.final_render_id)
        frozen_render = frozen[0] if frozen else None
        if frozen_render and (frozen_render.project_id != sync.project_id or frozen_render.workspace_id != sync.workspace_id
            or frozen_render.output_asset_id != publication.output_asset_id):
            raise ValueError('ANALYTICS_RENDER_FEATURE_SCOPE_MISMATCH')
        timeline = TimelineSnapshot.model_validate(frozen[3]) if frozen else None
        topic = source_idea.get("title") or snapshot.get("topic")
        content = dict(snapshot.get("content") or {})
        cta = (linked_idea.cta_concept if linked_idea else None) or source_idea.get("cta_concept") or content.get("cta")
        scene_ids = {
            clip.metadata.get("scene_id")
            for track in (timeline.tracks if timeline else [])
            for clip in track.clips
            if clip.metadata.get("scene_id") and not clip.disabled
        }
        visual_kinds = sorted(
            {
                clip.kind
                for track in (timeline.tracks if timeline else [])
                for clip in track.clips
                if not clip.disabled and clip.kind in {"source", "broll", "overlay", "generated"}
            }
        )
        subtitle_template = None
        voice_profile = None
        music_profile = None
        if frozen is not None:
            style = frozen[1].style
            subtitle_template = f"{style.position}:{style.animation}:{style.font_family}:{style.font_weight}"
            voice_profile = frozen[2].config.voice.voice if frozen[2].config.voice.enabled else "disabled"
            music_profile = frozen[2].config.music.asset_id or "none"
        return VideoFeatureMetadata(
            project_id=sync.project_id,
            publication_id=sync.publication_id,
            trend_cluster_id=(linked_idea.cluster_id if linked_idea else source_idea.get("cluster_id")),
            idea_id=(linked_idea.idea_id if linked_idea else source_idea.get("idea_id")),
            hook_type=(linked_idea.hook_concept if linked_idea else source_idea.get("hook_concept")),
            duration_seconds=timeline.duration_seconds if timeline else None,
            scene_count=len(scene_ids) if scene_ids else None,
            subtitle_template=subtitle_template,
            voice_profile=voice_profile,
            music_profile=music_profile,
            visual_strategy=(
                linked_idea.visual_concept
                if linked_idea
                else "+".join(visual_kinds)
                if visual_kinds
                else None
            ),
            niche=project.niche,
            topic=topic,
            cta=cta,
            publishing_time=(publication.receipt.created_at if publication.receipt else publication.created_at) if sync.provider_mode == 'fixture' else None,
            evidence={
                "project_version_id": project.current_version_id,
                "timeline_version_id": frozen_render.timeline_version_id if frozen_render else None,
                'subtitle_version_id': frozen_render.subtitle_version_id if frozen_render else None,
                'audio_version_id': frozen_render.audio_version_id if frozen_render else None,
                'feature_edit_source': 'published_render_context' if frozen else None,
                'project_metadata_source': 'current_project_at_collection',
                "publication_receipt_id": publication.receipt.receipt_id if publication.receipt else None,
                "publication_mock": publication.mock,
                "publishing_time_source": 'mock_receipt' if sync.provider_mode == 'fixture' else None,
                'local_receipt_confirmation_time': publication.receipt.created_at.isoformat() if publication.receipt else None,
                'exact_publishing_time_available': False,
                "trend_rank_mutated": False,
                "idea_rank_mutated": False,
                "automatic_action": False,
            },
        )
