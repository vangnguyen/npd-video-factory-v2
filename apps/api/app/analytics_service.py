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
from .analytics_repository import AnalyticsRepository
from .db import utc_now


ANALYTICS_SYNC_QUEUE_KEY = "npd:video-factory:v2:analytics:queued"
ANALYTICS_SYNC_PROCESSING_KEY = "npd:video-factory:v2:analytics:processing"


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
        if payload.trigger == "scheduled_refresh" and not self.settings.analytics_scheduled_refresh_enabled:
            raise AnalyticsBoundaryError(
                "ANALYTICS_SCHEDULED_REFRESH_DISABLED",
                "Scheduled analytics refresh is disabled until an owner enables the read-only scheduler gate.",
            )
        provider = self.providers.get(platform=publication.platform, mode=payload.provider_mode)
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
        )
        if not replay and sync.status == "queued":
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
            raise KeyError(sync_id)
        if sync.status != "running":
            return sync
        publication = await self.publishing_repository.get(sync.project_id, sync.publication_id)
        if publication is None:
            return await self.repository.terminal_failure(
                sync_id,
                status="failed",
                code="ANALYTICS_PUBLICATION_MISSING",
                reason="The source publication no longer exists.",
            )
        provider = self.providers.get(platform=sync.platform, mode=sync.provider_mode)
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
            )
        if sync.provider_mode == "fixture" and not self.settings.analytics_fixture_enabled:
            return await self.repository.terminal_failure(
                sync_id,
                status="not_configured",
                code="ANALYTICS_FIXTURE_DISABLED",
                reason="Deterministic analytics fixtures are disabled in this environment.",
            )
        try:
            collection = await provider.collect(
                AnalyticsCollectionContext(
                    platform=sync.platform,
                    project_id=sync.project_id,
                    publication_id=sync.publication_id,
                    remote_post_id=publication.receipt.remote_post_id if publication.receipt else None,
                    fixture_profile=sync.fixture_profile,
                )
            )
            features = await self._capture_features(sync, publication)
            cost = await self.platform_repository.project_cost_summary(sync.project_id)
            assessment = assess_winner(
                collection.metrics,
                video_duration_seconds=features.duration_seconds,
                production_cost_vnd=(
                    float(cost.actual_cost)
                    if cost.actual_cost and cost.actual_cost > 0
                    else float(cost.estimated_cost)
                    if cost.estimated_cost and cost.estimated_cost > 0
                    else None
                ),
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
            )
        except AnalyticsProviderNotConfigured as exc:
            return await self.repository.terminal_failure(
                sync.sync_id,
                status="not_configured",
                code="ANALYTICS_PROVIDER_NOT_CONFIGURED",
                reason=str(exc),
            )
        except AnalyticsRateLimited as exc:
            delay = min(
                self.settings.analytics_retry_max_seconds,
                max(
                    exc.retry_after_seconds,
                    self.settings.analytics_retry_base_seconds * (2 ** max(0, sync.attempt_count - 1)),
                ),
            )
            return await self.repository.schedule_retry(
                sync.sync_id,
                next_retry_at=utc_now() + timedelta(seconds=delay),
                code="ANALYTICS_RATE_LIMITED",
                reason=str(exc),
            )
        except Exception as exc:
            delay = min(
                self.settings.analytics_retry_max_seconds,
                self.settings.analytics_retry_base_seconds * (2 ** max(0, sync.attempt_count - 1)),
            )
            return await self.repository.schedule_retry(
                sync.sync_id,
                next_retry_at=utc_now() + timedelta(seconds=delay),
                code="ANALYTICS_PROVIDER_ERROR",
                reason=f"{type(exc).__name__}: {exc}",
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
        timeline = await self.timeline_repository.get_timeline(sync.project_id)
        package = await self.production_repository.get_package(sync.project_id)
        topic = source_idea.get("title") or snapshot.get("topic")
        content = dict(snapshot.get("content") or {})
        cta = (linked_idea.cta_concept if linked_idea else None) or source_idea.get("cta_concept") or content.get("cta")
        scene_ids = {
            clip.metadata.get("scene_id")
            for track in (timeline.snapshot.tracks if timeline else [])
            for clip in track.clips
            if clip.metadata.get("scene_id") and not clip.disabled
        }
        visual_kinds = sorted(
            {
                clip.kind
                for track in (timeline.snapshot.tracks if timeline else [])
                for clip in track.clips
                if not clip.disabled and clip.kind in {"source", "broll", "overlay", "generated"}
            }
        )
        subtitle_template = None
        voice_profile = None
        music_profile = None
        if package is not None:
            style = package.subtitle.style
            subtitle_template = f"{style.position}:{style.animation}:{style.font_family}:{style.font_weight}"
            voice_profile = package.audio_mix.config.voice.voice if package.audio_mix.config.voice.enabled else "disabled"
            music_profile = package.audio_mix.config.music.asset_id or "none"
        return VideoFeatureMetadata(
            project_id=sync.project_id,
            publication_id=sync.publication_id,
            trend_cluster_id=(linked_idea.cluster_id if linked_idea else source_idea.get("cluster_id")),
            idea_id=(linked_idea.idea_id if linked_idea else source_idea.get("idea_id")),
            hook_type=(linked_idea.hook_concept if linked_idea else source_idea.get("hook_concept")),
            duration_seconds=timeline.snapshot.duration_seconds if timeline else None,
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
            publishing_time=(publication.receipt.created_at if publication.receipt else publication.created_at),
            evidence={
                "project_version_id": project.current_version_id,
                "timeline_version_id": timeline.current_version_id if timeline else None,
                "publication_receipt_id": publication.receipt.receipt_id if publication.receipt else None,
                "publication_mock": publication.mock,
                "publishing_time_source": "mock_receipt" if publication.mock else "official_receipt",
                "trend_rank_mutated": False,
                "idea_rank_mutated": False,
                "automatic_action": False,
            },
        )
