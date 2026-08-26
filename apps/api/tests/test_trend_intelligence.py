from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.db import Base, create_engine, create_session_factory
from app.platform_models import WorkspaceCreate
from app.repositories import PlatformRepository
from app.trend_models import (
    ContentQueueRefreshRequest,
    IdeaGenerateRequest,
    TrendClusterRefreshRequest,
    TrendCollectionRequest,
)
from app.trend_providers import TrendProviderNotConfigured, create_trend_provider_registry
from app.trend_repository import TrendRepository
from app.trend_routes import router as trend_router
from app.trend_service import TrendIntelligenceService


FIXTURE_PATH = Path(__file__).resolve().parents[1] / "app" / "fixtures" / "trend-signals.json"
FIXTURE_AS_OF = datetime(2026, 8, 26, 8, 0, tzinfo=timezone.utc)


async def stack(tmp_path: Path):
    database_path = tmp_path / "trend.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="trend-test", name="Trend Test", owner_ref="test-owner")
    )
    providers = create_trend_provider_registry(FIXTURE_PATH)
    repository = TrendRepository(session_factory)
    await repository.seed_sources(providers.definitions())
    service = TrendIntelligenceService(repository, providers, platform)
    return engine, session_factory, workspace, providers, repository, service


async def collect_and_cluster(service: TrendIntelligenceService, workspace_id: str):
    collection = await service.collect(workspace_id, TrendCollectionRequest())
    clusters = await service.refresh_clusters(
        workspace_id,
        TrendClusterRefreshRequest(
            as_of=FIXTURE_AS_OF,
            channel="short-video",
            niche="real_estate",
            business_objective="lead_generation",
        ),
    )
    return collection, clusters


@pytest.mark.asyncio
async def test_fixture_collection_is_idempotent_and_preserves_missing_metrics(tmp_path: Path) -> None:
    engine, _, workspace, providers, _, service = await stack(tmp_path)
    first = await service.collect(workspace.workspace_id, TrendCollectionRequest())
    replay = await service.collect(workspace.workspace_id, TrendCollectionRequest())

    assert first.snapshot.signal_count == 8
    assert first.snapshot.new_signal_count == 8
    assert replay.snapshot.signal_count == 8
    assert replay.snapshot.new_signal_count == 0
    assert {item.signal_id for item in replay.signals} == {item.signal_id for item in first.signals}
    search_signal = next(item for item in first.signals if item.source_reference.endswith("ai-video-real-estate-03"))
    assert search_signal.views is None
    assert search_signal.likes is None
    assert search_signal.engagement is None
    assert all(item.source_reference.startswith("https://fixtures.local/") for item in first.signals)
    assert all(item.provenance["creator_media_downloaded"] is False for item in first.signals)
    reference = await providers.get("fixture-trends").get_content_reference(search_signal.source_reference)
    assert reference["reference_only"] is True
    assert reference["download_allowed"] is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_clusters_lifecycle_and_opportunity_scores_are_explainable(tmp_path: Path) -> None:
    engine, _, workspace, _, _, service = await stack(tmp_path)
    _, clusters = await collect_and_cluster(service, workspace.workspace_id)
    replay = await service.refresh_clusters(
        workspace.workspace_id,
        TrendClusterRefreshRequest(
            as_of=FIXTURE_AS_OF,
            channel="short-video",
            niche="real_estate",
            business_objective="lead_generation",
        ),
    )

    assert len(clusters) == 4
    assert [
        (item.cluster_id, item.version, item.score.trend_score_id, item.score.version)
        for item in replay
        if item.score
    ] == [
        (item.cluster_id, item.version, item.score.trend_score_id, item.score.version)
        for item in clusters
        if item.score
    ]
    ai_cluster = next(item for item in clusters if item.topic == "AI video cho bất động sản")
    assert ai_cluster.lifecycle == "breakout"
    assert ai_cluster.platforms == ["google_trends", "tiktok", "youtube"]
    assert ai_cluster.score is not None
    assert ai_cluster.score.estimated is True
    assert 0 <= ai_cluster.score.total_score <= 100
    assert {
        "velocity",
        "acceleration",
        "cross_platform_spread",
        "engagement_quality",
        "saturation",
        "competition",
        "rights_risk",
        "policy_risk",
    }.issubset(ai_cluster.score.components)
    assert ai_cluster.source_references
    await engine.dispose()


@pytest.mark.asyncio
async def test_idea_engine_generates_distinct_drafts_and_ranked_queue_survives_restart(tmp_path: Path) -> None:
    engine, session_factory, workspace, providers, repository, service = await stack(tmp_path)
    _, clusters = await collect_and_cluster(service, workspace.workspace_id)
    ai_cluster = next(item for item in clusters if item.topic == "AI video cho bất động sản")
    ideas = await service.generate_ideas(
        ai_cluster.cluster_id,
        IdeaGenerateRequest(
            channel="short-video",
            niche="real_estate",
            business_objective="lead_generation",
            audience="Người đang tìm hiểu bất động sản",
            cta="Đăng ký nhận tư vấn",
            count=6,
        ),
    )
    replay = await service.generate_ideas(
        ai_cluster.cluster_id,
        IdeaGenerateRequest(
            channel="short-video",
            niche="real_estate",
            business_objective="lead_generation",
            audience="Người đang tìm hiểu bất động sản",
            cta="Đăng ký nhận tư vấn",
            count=6,
        ),
    )

    assert len(ideas) == 6
    assert len({item.variant_key for item in ideas}) == 6
    assert len({item.angle for item in ideas}) == 6
    assert len({item.hook_concept for item in ideas}) == 6
    assert {item.idea_id for item in replay} == {item.idea_id for item in ideas}
    assert all(item.status == "draft" and item.project_id is None for item in ideas)
    assert all(item.score.estimated for item in ideas)
    assert all(item.brief["production_mode"] == "draft_only" for item in ideas)
    assert all(item.provenance["copied_creator_media"] is False for item in ideas)

    queue_request = ContentQueueRefreshRequest(
        channel="short-video",
        niche="real_estate",
        business_objective="lead_generation",
        audience="Người đang tìm hiểu bất động sản",
        cta="Đăng ký nhận tư vấn",
        top_n=5,
        ideas_per_cluster=3,
    )
    queue = await service.refresh_queue(workspace.workspace_id, queue_request)
    queue_replay = await service.refresh_queue(workspace.workspace_id, queue_request)
    assert len(queue) == 5
    assert [item.rank for item in queue] == [1, 2, 3, 4, 5]
    assert [item.score for item in queue] == sorted((item.score for item in queue), reverse=True)
    assert [item.queue_item_id for item in queue_replay] == [item.queue_item_id for item in queue]
    assert all(item.state == "proposed" for item in queue)
    assert all(item.provenance["execution"] is False for item in queue)

    database_path = tmp_path / "trend.db"
    await engine.dispose()
    restarted_engine = create_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    restarted_repository = TrendRepository(create_session_factory(restarted_engine))
    recovered = await restarted_repository.list_queue(workspace.workspace_id)
    assert [item.model_dump(mode="json") for item in recovered] == [
        item.model_dump(mode="json") for item in queue
    ]
    await restarted_engine.dispose()


@pytest.mark.asyncio
async def test_selecting_an_idea_creates_only_a_draft_project(tmp_path: Path) -> None:
    engine, _, workspace, _, _, service = await stack(tmp_path)
    _, clusters = await collect_and_cluster(service, workspace.workspace_id)
    ideas = await service.generate_ideas(
        clusters[0].cluster_id,
        IdeaGenerateRequest(niche="real_estate", business_objective="lead_generation", count=1),
    )
    first = await service.create_draft_project(ideas[0].idea_id)
    replay = await service.create_draft_project(ideas[0].idea_id)
    project = await service.platform.get_project(first.project_id)

    assert replay == first
    assert project is not None
    assert project.status == "draft"
    assert project.provenance["execution"] is False
    versions = await service.platform.list_versions(first.project_id)
    assert len(versions) == 1
    assert versions[0].snapshot["approval"] == {
        "human_required": True,
        "approved": False,
        "publish_enabled": False,
    }
    await engine.dispose()


@pytest.mark.asyncio
async def test_live_provider_contracts_fail_closed_when_not_configured(tmp_path: Path) -> None:
    engine, _, workspace, providers, _, service = await stack(tmp_path)
    source_map = {item.provider_key: item for item in await service.list_sources()}
    assert source_map["youtube-data-api"].status == "not_configured"
    assert source_map["youtube-data-api"].authorized_access is False
    with pytest.raises(TrendProviderNotConfigured):
        providers.get("youtube-data-api")
    with pytest.raises(KeyError):
        providers.get("unknown-provider")
    with pytest.raises(TrendProviderNotConfigured):
        await service.collect(
            workspace.workspace_id,
            TrendCollectionRequest(provider_key="youtube-data-api"),
        )
    await engine.dispose()


@pytest.mark.asyncio
async def test_trend_api_acceptance_flow_and_error_contract(tmp_path: Path) -> None:
    engine, _, workspace, _, _, service = await stack(tmp_path)
    app = FastAPI()
    app.include_router(trend_router)
    app.state.trend_intelligence_service = service
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        collection_response = await client.post(
            f"/api/v1/workspaces/{workspace.workspace_id}/trend-signals/collect",
            json={"provider_key": "fixture-trends", "country": "VN", "language": "vi"},
        )
        assert collection_response.status_code == 201
        assert collection_response.json()["snapshot"]["signal_count"] == 8

        clusters_response = await client.post(
            f"/api/v1/workspaces/{workspace.workspace_id}/trend-clusters/refresh",
            json={
                "as_of": FIXTURE_AS_OF.isoformat(),
                "channel": "short-video",
                "niche": "real_estate",
                "business_objective": "lead_generation",
            },
        )
        assert clusters_response.status_code == 200
        clusters = clusters_response.json()
        assert len(clusters) == 4

        ideas_response = await client.post(
            f"/api/v1/trend-clusters/{clusters[0]['cluster_id']}/ideas/generate",
            json={
                "channel": "short-video",
                "niche": "real_estate",
                "business_objective": "lead_generation",
                "audience": "Khách mua nhà",
                "cta": "Nhận tư vấn",
                "count": 3,
            },
        )
        assert ideas_response.status_code == 200
        assert len(ideas_response.json()) == 3

        unavailable = await client.post(
            f"/api/v1/workspaces/{workspace.workspace_id}/trend-signals/collect",
            json={"provider_key": "youtube-data-api"},
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["detail"]["error"]["code"] == "PROVIDER_NOT_CONFIGURED"
    await engine.dispose()
