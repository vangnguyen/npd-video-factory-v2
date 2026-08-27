from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.analytics_logic import assess_winner
from app.analytics_models import AnalyticsSyncRequest, NormalizedMetrics
from app.analytics_providers import AnalyticsProviderRegistry
from app.analytics_repository import AnalyticsIdempotencyConflict, AnalyticsRepository
from app.analytics_service import AnalyticsBoundaryError, AnalyticsService, AnalyticsSyncProcessor
from app.db import utc_now
from app.main import app
from app.publishing_repository import PublishingRepository
from app.trend_repository import TrendRepository
from test_publishing import approved_stack, request_for


class FakeQueue:
    def __init__(self) -> None:
        self.values: list[str] = []

    async def rpush(self, _key: str, value: str) -> int:
        self.values.append(value)
        return len(self.values)


def analytics_settings(**overrides):
    values = {
        "analytics_fixture_enabled": True,
        "analytics_external_execution_enabled": False,
        "analytics_scheduled_refresh_enabled": False,
        "analytics_max_attempts": 3,
        "analytics_retry_base_seconds": 30,
        "analytics_retry_max_seconds": 900,
        "youtube_analytics_credential_ref": "",
        "tiktok_analytics_credential_ref": "",
        "instagram_analytics_credential_ref": "",
        "facebook_analytics_credential_ref": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def analytics_stack(tmp_path):
    production, final, publishing = await approved_stack(tmp_path)
    publication, _ = await publishing.create(
        project_id=production.project.project_id,
        payload=request_for(final.render_id),
        idempotency_key="v2-10-source-publication-0001",
    )
    repository = AnalyticsRepository(production.repository.session_factory)
    queue = FakeQueue()
    settings = analytics_settings()
    providers = AnalyticsProviderRegistry(settings)
    publishing_repository = PublishingRepository(production.repository.session_factory)
    service = AnalyticsService(
        repository=repository,
        publishing_repository=publishing_repository,
        platform_repository=production.platform,
        providers=providers,
        queue=queue,
        settings=settings,
    )
    processor = AnalyticsSyncProcessor(
        repository=repository,
        publishing_repository=publishing_repository,
        platform_repository=production.platform,
        trend_repository=TrendRepository(production.repository.session_factory),
        timeline_repository=production.timeline_repository,
        production_repository=production.repository,
        providers=providers,
        settings=settings,
    )
    return SimpleNamespace(
        production=production,
        publication=publication,
        repository=repository,
        queue=queue,
        settings=settings,
        providers=providers,
        service=service,
        processor=processor,
    )


def request(publication_id: str, *, profile: str = "winner_candidate", mode: str = "fixture"):
    return AnalyticsSyncRequest(
        publication_id=publication_id,
        provider_mode=mode,
        fixture_profile=profile,
        trigger="initial",
        actor_ref="analytics-test",
    )


def test_winner_detection_is_explainable_and_preserves_missing_metrics() -> None:
    winner = assess_winner(
        NormalizedMetrics(
            views=120_000,
            watch_time=4_800_000,
            average_view_duration=40,
            completion_rate=0.82,
            likes=9_500,
            comments=1_200,
            shares=5_100,
            saves=4_300,
            followers_gained=2_100,
            ctr=0.045,
            revenue=12_000_000,
            rpm=100_000,
            observation_window_hours=24,
        ),
        video_duration_seconds=45,
        production_cost_vnd=2_000_000,
    )
    assert winner.state == "winner_candidate"
    assert winner.score is not None and winner.score >= 72
    assert all(item.evidence for item in winner.factors)

    insufficient = assess_winner(
        NormalizedMetrics(views=80, observation_window_hours=1),
        video_duration_seconds=45,
        production_cost_vnd=None,
    )
    assert insufficient.state == "insufficient_data"
    assert insufficient.score is None
    assert next(item for item in insufficient.factors if item.factor == "ctr").score is None


@pytest.mark.asyncio
async def test_fixture_sync_persists_history_winner_and_recommendation_only_learning(tmp_path) -> None:
    stack = await analytics_stack(tmp_path)
    first, replay = await stack.service.create_sync(
        project_id=stack.production.project.project_id,
        payload=request(stack.publication.publication_id),
        idempotency_key="v2-10-analytics-winner-0001",
    )
    assert replay is False and first.status == "queued"
    assert stack.queue.values == [first.sync_id]
    completed = await stack.processor.process(first.sync_id)
    assert completed.status == "succeeded"
    assert completed.external_call is False and completed.mock is True

    report = await stack.repository.report(stack.production.project.project_id)
    assert report.status == "ready"
    assert report.history_count == 1
    assert report.latest_snapshot is not None
    assert len(report.latest_snapshot.points) == 16
    assert report.latest_snapshot.source_kind == "fixture"
    assert report.latest_assessment is not None
    assert report.latest_assessment.state == "winner_candidate"
    assert report.latest_assessment.automatic_action is False
    assert report.latest_assessment.paid_media_mutation is False
    assert report.learning_insights
    assert all(item.applied is False and item.autonomous_execution is False for item in report.learning_insights)
    assert report.video_features is not None
    assert report.video_features.evidence["publication_mock"] is True
    assert report.video_features.evidence["idea_rank_mutated"] is False

    replayed, replay = await stack.service.create_sync(
        project_id=stack.production.project.project_id,
        payload=request(stack.publication.publication_id),
        idempotency_key="v2-10-analytics-winner-0001",
    )
    assert replay is True and replayed.sync_id == first.sync_id
    with pytest.raises(AnalyticsIdempotencyConflict):
        await stack.service.create_sync(
            project_id=stack.production.project.project_id,
            payload=request(stack.publication.publication_id, profile="normal"),
            idempotency_key="v2-10-analytics-winner-0001",
        )

    second, _ = await stack.service.create_sync(
        project_id=stack.production.project.project_id,
        payload=AnalyticsSyncRequest(
            publication_id=stack.publication.publication_id,
            provider_mode="fixture",
            trigger="manual_refresh",
            fixture_profile="normal",
            actor_ref="analytics-test",
        ),
        idempotency_key="v2-10-analytics-normal-0002",
    )
    await stack.processor.process(second.sync_id)
    restarted = AnalyticsRepository(stack.production.repository.session_factory)
    recovered = await restarted.report(stack.production.project.project_id)
    assert recovered.history_count == 2
    snapshots = await restarted.list_snapshots(stack.production.project.project_id)
    assert snapshots[0].snapshot_id != snapshots[1].snapshot_id
    assert snapshots[0].metrics.revenue is None
    assert next(point for point in snapshots[0].points if point.metric == "revenue").supported is False
    events = await restarted.list_events(stack.production.project.project_id)
    assert any(item.event_type == "video.analytics.updated" for item in events)
    assert any(item.event_type == "video.winner.detected" for item in events)
    await stack.production.engine.dispose()

@pytest.mark.asyncio
async def test_official_provider_is_truthfully_not_configured_without_external_call(tmp_path) -> None:
    stack = await analytics_stack(tmp_path)
    sync, _ = await stack.service.create_sync(
        project_id=stack.production.project.project_id,
        payload=request(stack.publication.publication_id, mode="official"),
        idempotency_key="v2-10-official-not-configured-0001",
    )
    result = await stack.processor.process(sync.sync_id)
    assert result.status == "not_configured"
    assert result.failure_code == "ANALYTICS_PROVIDER_NOT_CONFIGURED"
    assert result.external_call is False
    assert (await stack.repository.list_snapshots(stack.production.project.project_id)) == []
    states = stack.service.provider_states()
    assert len(states) == 8
    assert all(item.external_calls_enabled is False for item in states)
    assert all(item.real_provider_tested is False for item in states)
    await stack.production.engine.dispose()


@pytest.mark.asyncio
async def test_rate_limit_backoff_and_restart_recovery_are_durable(tmp_path) -> None:
    stack = await analytics_stack(tmp_path)
    sync, _ = await stack.service.create_sync(
        project_id=stack.production.project.project_id,
        payload=request(stack.publication.publication_id, profile="rate_limited"),
        idempotency_key="v2-10-rate-limit-0001",
    )
    first = await stack.processor.process(sync.sync_id)
    assert first.status == "retry_scheduled"
    assert first.next_retry_at is not None and first.attempt_count == 1
    assert await stack.repository.recover_incomplete_sync_ids() == []
    due = await stack.repository.activate_due_sync_ids(at=utc_now() + timedelta(hours=1))
    assert due == [sync.sync_id]
    recovered = AnalyticsRepository(stack.production.repository.session_factory)
    assert await recovered.recover_incomplete_sync_ids() == [sync.sync_id]
    second = await stack.processor.process(sync.sync_id)
    assert second.status == "retry_scheduled" and second.attempt_count == 2
    await stack.repository.activate_due_sync_ids(at=utc_now() + timedelta(hours=1))
    third = await stack.processor.process(sync.sync_id)
    assert third.status == "failed" and third.attempt_count == 3
    assert third.failure_code == "ANALYTICS_RATE_LIMITED"
    await stack.production.engine.dispose()


@pytest.mark.asyncio
async def test_scheduled_refresh_and_fixture_gates_fail_closed(tmp_path) -> None:
    stack = await analytics_stack(tmp_path)
    scheduled = AnalyticsSyncRequest(
        publication_id=stack.publication.publication_id,
        provider_mode="fixture",
        trigger="scheduled_refresh",
        fixture_profile="normal",
        scheduled_for=utc_now() + timedelta(hours=1),
    )
    with pytest.raises(AnalyticsBoundaryError, match="Scheduled analytics refresh is disabled"):
        await stack.service.create_sync(
            project_id=stack.production.project.project_id,
            payload=scheduled,
            idempotency_key="v2-10-scheduled-disabled-0001",
        )
    disabled_settings = analytics_settings(analytics_fixture_enabled=False)
    disabled = AnalyticsService(
        repository=stack.repository,
        publishing_repository=PublishingRepository(stack.production.repository.session_factory),
        platform_repository=stack.production.platform,
        providers=AnalyticsProviderRegistry(disabled_settings),
        queue=FakeQueue(),
        settings=disabled_settings,
    )
    with pytest.raises(AnalyticsBoundaryError, match="fixtures are disabled"):
        await disabled.create_sync(
            project_id=stack.production.project.project_id,
            payload=request(stack.publication.publication_id),
            idempotency_key="v2-10-fixture-disabled-0001",
        )
    await stack.production.engine.dispose()


@pytest.mark.asyncio
async def test_analytics_api_exposes_report_history_and_provider_truth(tmp_path) -> None:
    stack = await analytics_stack(tmp_path)
    app.state.analytics_service = stack.service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/projects/{stack.production.project.project_id}/analytics/syncs",
            headers={"Idempotency-Key": "v2-10-api-analytics-sync-0001"},
            json=request(stack.publication.publication_id).model_dump(mode="json"),
        )
        assert response.status_code == 202
        assert response.headers["X-Idempotent-Replay"] == "false"
        sync_id = response.json()["sync_id"]
        await stack.processor.process(sync_id)
        report = await client.get(f"/api/v1/projects/{stack.production.project.project_id}/analytics")
        snapshots = await client.get(
            f"/api/v1/projects/{stack.production.project.project_id}/analytics/snapshots"
        )
        assessments = await client.get(
            f"/api/v1/projects/{stack.production.project.project_id}/analytics/assessments"
        )
        insights = await client.get(
            f"/api/v1/projects/{stack.production.project.project_id}/analytics/learning-insights"
        )
        history = await client.get(
            f"/api/v1/projects/{stack.production.project.project_id}/analytics/history"
        )
        providers = await client.get("/api/v1/analytics-providers")
        assert {report.status_code, snapshots.status_code, assessments.status_code, insights.status_code, history.status_code, providers.status_code} == {200}
        assert report.json()["latest_assessment"]["state"] == "winner_candidate"
        assert report.json()["external_execution_enabled"] is False
        assert len(providers.json()) == 8
    await stack.production.engine.dispose()
