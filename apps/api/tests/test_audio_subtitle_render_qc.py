from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.auto_edit_repository import AutoEditRepository
from app.db import Base, create_engine, create_session_factory
from app.main import app
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import AssetRegister, ProjectCreate, WorkspaceCreate
from app.production_audio import UnconfiguredVietnameseTTSProvider, audio_provider_status
from app.production_logic import (
    ProductionContractError,
    TimelineRenderContractValidator,
    validate_production_visual_asset,
)
from app.production_models import (
    ApprovalDecisionRequest,
    ApprovalRequest,
    FinalRenderCreateRequest,
    ProductionPackageCreateRequest,
    RenderCreateRequest,
    SubtitleReplaceRequest,
)
from app.production_qc import DeterministicProductionQC
from app.production_repository import ApprovalBoundaryError, ProductionRepository
from app.production_service import (
    PRODUCTION_RENDER_QUEUE_KEY,
    DeterministicTimelineRenderEngine,
    ProductionPackageService,
    ProductionRenderProcessor,
)
from app.repositories import PlatformRepository
from app.timeline_models import TimelineClip, TimelineSnapshot, TimelineTrack
from app.timeline_repository import TimelineRepository


CONTRACT = Path(__file__).resolve().parents[3] / "packages" / "contracts" / "timeline-render.schema.json"


def test_production_visual_assets_reject_planning_fixtures() -> None:
    source = SimpleNamespace(
        asset_id="ast_source_fixture",
        content_type="video/mp4",
        provenance={"source": "owner-upload"},
    )
    fixture = SimpleNamespace(
        asset_id="ast_planning_fixture",
        content_type="image/svg+xml",
        provenance={"production_eligible": False},
    )
    assert validate_production_visual_asset(source) == "video"
    with pytest.raises(ProductionContractError, match="not production eligible"):
        validate_production_visual_asset(fixture)


class FakeQueue:
    def __init__(self) -> None:
        self.items: list[tuple[str, str]] = []

    async def rpush(self, key: str, value: str) -> int:
        self.items.append((key, value))
        return len(self.items)


class DeterministicAudioEngine:
    async def synthesize_narration(
        self,
        _provider,
        *,
        cues,
        config,
        duration_seconds,
        output_path,
        workdir,
    ):
        del config, workdir
        output_path.write_bytes(b"deterministic-narration")
        return {
            "provider": "fixture-vi",
            "voice": "fixture-vi",
            "cue_count": len(cues),
            "duration_seconds": duration_seconds,
            "timing": [
                {
                    "cue_id": cue.cue_id,
                    "start_seconds": cue.start_seconds,
                    "end_seconds": cue.end_seconds,
                    "slot_end_seconds": cue.end_seconds,
                    "audible": True,
                }
                for cue in cues
            ],
        }

    async def mix(
        self,
        *,
        narration_path,
        music_path,
        cues,
        config,
        duration_seconds,
        output_path,
    ):
        del narration_path, music_path, cues
        output_path.write_bytes(b"deterministic-48khz-stereo-audio")
        return {
            "engine": "deterministic-audio-mix-v2-08",
            "sample_rate": config.sample_rate,
            "duration_seconds": duration_seconds,
            "peak_dbfs": -1,
            "limiter_peak_db": config.limiter_peak_db,
            "configured": False,
            "ducking_applied": False,
        }


def production_snapshot(asset_id: str) -> TimelineSnapshot:
    return TimelineSnapshot(
        duration_seconds=3,
        tracks=[
            TimelineTrack(
                track_id="trk_video_main",
                type="video",
                kind="source",
                label="Video chính",
                order=0,
                clips=[
                    TimelineClip(
                        clip_id="clip_video_main",
                        kind="source",
                        label="Cảnh Vịnh Tiên",
                        asset_id=asset_id,
                        source_start=0,
                        source_end=3,
                        timeline_start=0,
                        duration=3,
                    )
                ],
            ),
            TimelineTrack(
                track_id="trk_subtitles",
                type="text",
                kind="subtitles",
                label="Phụ đề",
                order=1,
                clips=[
                    TimelineClip(
                        clip_id="clip_subtitle_main",
                        kind="subtitle",
                        label="Vịnh Tiên - hành trình sống ven biển",
                        source_start=0,
                        source_end=3,
                        timeline_start=0,
                        duration=3,
                    )
                ],
            ),
        ],
    )


async def setup_stack(tmp_path: Path):
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'production.db'}")
    session_factory = create_session_factory(engine)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(
            slug="v2-08-tests",
            name="V2-08 tests",
            owner_ref="owner-fixture",
            provenance={"fixture": True},
        )
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(
            slug="vinh-tien-v2-08",
            name="Vịnh Tiên V2-08",
            niche="real_estate",
            provenance={"fixture": True},
        ),
    )
    storage = LocalObjectStorageProvider(tmp_path / "objects")
    await storage.ensure_ready()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"deterministic-source")
    stored = await storage.put_file(
        object_key=f"workspaces/{workspace.workspace_id}/projects/{project.project_id}/source/source.mp4",
        path=source,
        content_type="video/mp4",
    )
    asset = await platform.register_asset(
        project.project_id,
        AssetRegister(
            asset_class="source",
            kind="video",
            filename="source.mp4",
            object_key=stored.object_key,
            content_type="video/mp4",
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            storage_provider=stored.storage_provider,
            provenance={"fixture": True},
        ),
    )
    await platform.seed_providers(
        [
            {
                "provider_key": "espeak",
                "display_name": "eSpeak fixture",
                "capability": "tts",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
                "metadata": {"paid": False},
            },
            {
                "provider_key": "remotion",
                "display_name": "Remotion fixture",
                "capability": "rendering",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
                "metadata": {"paid": False},
            },
        ]
    )
    timeline_repository = TimelineRepository(session_factory)
    timeline, _ = await timeline_repository.create_timeline(
        project_id=project.project_id,
        source_analysis_id="ana_v208_fixture",
        source_media_plan_id=None,
        snapshot=production_snapshot(asset.asset_id),
        actor_ref="owner-fixture",
    )
    # The legacy timeline fixture predates SQLite FK enforcement. Reconnect with
    # constraints enabled before exercising the new V2-08 persistence boundary,
    # which mirrors PostgreSQL behavior without widening this PR into V2-07.
    await engine.dispose()

    @event.listens_for(engine.sync_engine, "connect")
    def enforce_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    production_repository = ProductionRepository(session_factory)
    asset_repository = AutoEditRepository(session_factory)
    queue = FakeQueue()
    settings = SimpleNamespace(audio_tts_provider="espeak")
    service = ProductionPackageService(
        repository=production_repository,
        timeline_repository=timeline_repository,
        asset_repository=asset_repository,
        queue=queue,
        settings=settings,
    )
    processor = ProductionRenderProcessor(
        repository=production_repository,
        platform=platform,
        asset_repository=asset_repository,
        object_storage=storage,
        renderer=DeterministicTimelineRenderEngine(),
        qc=DeterministicProductionQC(),
        tts_provider=object(),
        audio_engine=DeterministicAudioEngine(),  # type: ignore[arg-type]
        manifest_validator=TimelineRenderContractValidator(CONTRACT),
        staging_root=tmp_path / "renders",
        brand_name="NPD Video Factory",
    )
    return SimpleNamespace(
        engine=engine,
        platform=platform,
        storage=storage,
        project=project,
        asset=asset,
        timeline=timeline,
        timeline_repository=timeline_repository,
        repository=production_repository,
        service=service,
        processor=processor,
        queue=queue,
        asset_repository=asset_repository,
    )


@pytest.mark.asyncio
async def test_version_bound_review_approval_final_render_and_invalidation(tmp_path: Path) -> None:
    stack = await setup_stack(tmp_path)
    package = await stack.service.create_or_refresh(
        stack.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=1, actor_ref="owner-fixture"),
    )
    assert package.subtitle.version == 1
    assert package.audio_mix.provider_status == "configured"
    assert package.publishing_allowed is False

    with pytest.raises(ApprovalBoundaryError, match="approved review"):
        await stack.service.enqueue_final(
            stack.project.project_id,
            FinalRenderCreateRequest(
                expected_timeline_version=1,
                expected_subtitle_version=1,
                expected_audio_version=1,
                approval_id="apr_missing_fixture",
            ),
        )

    review = await stack.service.enqueue_review(
        stack.project.project_id,
        RenderCreateRequest(
            expected_timeline_version=1,
            expected_subtitle_version=1,
            expected_audio_version=1,
        ),
    )
    assert stack.queue.items == [(PRODUCTION_RENDER_QUEUE_KEY, review.render_id)]
    completed_review = await stack.processor.process(review.render_id)
    assert completed_review.status == "awaiting_review"
    assert completed_review.qc_status == "passed"
    assert completed_review.manifest["safety"]["publishing_allowed"] is False
    assert completed_review.manifest["qc_status"] == "passed"

    approval = await stack.service.request_approval(
        stack.project.project_id,
        ApprovalRequest(review_render_id=review.render_id, requester_ref="operator-fixture"),
    )
    approved = await stack.service.decide_approval(
        stack.project.project_id,
        approval.approval_id,
        ApprovalDecisionRequest(
            decision="approved",
            reviewer_ref="owner-fixture",
            comment="Đã nghe giọng, đọc phụ đề và xem preview.",
        ),
    )
    assert approved.status == "approved"
    assert approved.timeline_version == 1 and approved.preview_version == 1

    final = await stack.service.enqueue_final(
        stack.project.project_id,
        FinalRenderCreateRequest(
            expected_timeline_version=1,
            expected_subtitle_version=1,
            expected_audio_version=1,
            approval_id=approval.approval_id,
            profile="vertical-1080x1920",
        ),
    )
    completed_final = await stack.processor.process(final.render_id)
    assert completed_final.status == "ready" and completed_final.qc_status == "passed"
    assert completed_final.profile == "vertical-1080x1920"
    assert completed_final.publishing_allowed is False

    cues = [item.model_copy(deep=True) for item in package.subtitle.cues]
    cues[0].text = "Vịnh Tiên - bản phụ đề đã chỉnh sửa"
    changed = await stack.service.replace_subtitles(
        stack.project.project_id,
        SubtitleReplaceRequest(
            expected_timeline_version=1,
            expected_subtitle_version=1,
            cues=cues,
            style=package.subtitle.style,
            actor_ref="operator-fixture",
            reason="subtitle-copy-change",
        ),
    )
    assert changed.subtitle.version == 2
    assert changed.approval is None
    assert (await stack.repository.get_render(final.render_id)).status == "stale"
    with pytest.raises(ApprovalBoundaryError):
        await stack.service.enqueue_final(
            stack.project.project_id,
            FinalRenderCreateRequest(
                expected_timeline_version=1,
                expected_subtitle_version=2,
                expected_audio_version=1,
                approval_id=approval.approval_id,
            ),
        )

    recovered = await ProductionRepository(stack.repository.session_factory).get_package(
        stack.project.project_id
    )
    assert recovered and recovered.subtitle.version == 2
    history = await stack.service.history(stack.project.project_id)
    assert {item.event_type for item in history} >= {
        "production_package.created",
        "render.review_completed",
        "approval.approved",
        "render.final_completed",
        "subtitles.version_created",
    }
    assert '"publishing_allowed": true' not in json.dumps(
        [item.model_dump(mode="json") for item in history]
    ).lower()
    costs = await stack.platform.project_cost_summary(stack.project.project_id)
    assert costs.currency == "VND" and costs.records == 4
    await stack.engine.dispose()


@pytest.mark.asyncio
async def test_api_contract_and_not_configured_provider_state(tmp_path: Path) -> None:
    stack = await setup_stack(tmp_path)
    contract_settings = SimpleNamespace(audio_tts_provider="contract")
    assert audio_provider_status(contract_settings) == "not_configured"
    with pytest.raises(Exception, match="not configured"):
        await UnconfiguredVietnameseTTSProvider().synthesize(
            text="Xin chào", language="vi", output_path=tmp_path / "voice.wav"
        )

    app.state.production_package_service = stack.service
    app.state.auto_edit_repository = stack.asset_repository
    app.state.object_storage = stack.storage
    app.state.production_render_download_root = tmp_path / "downloads"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        created = await client.post(
            f"/api/v1/projects/{stack.project.project_id}/production-package",
            json={"expected_timeline_version": 1, "actor_ref": "owner-fixture"},
        )
        assert created.status_code == 201
        body = created.json()
        assert body["publishing_allowed"] is False
        queued = await client.post(
            f"/api/v1/projects/{stack.project.project_id}/review-render",
            json={
                "expected_timeline_version": 1,
                "expected_subtitle_version": 1,
                "expected_audio_version": 1,
                "profile": "review-540x960",
            },
        )
        assert queued.status_code == 202
        assert queued.json()["external_publish_requested"] is False
        history = await client.get(
            f"/api/v1/projects/{stack.project.project_id}/production-history"
        )
        assert history.status_code == 200
    await stack.engine.dispose()
