from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from pydantic import ValidationError
from sqlalchemy import text

from app.auto_edit_models import (
    AutoEditAnalysisRequest,
    MediaMetadata,
    UploadCompleteRequest,
    UploadInitRequest,
)
from app.auto_edit_providers import DeterministicMediaSignalProvider, DeterministicTranscriptionProvider
from app.auto_edit_repository import AutoEditRepository
from app.auto_edit_service import AutoEditAnalysisService, UploadService
from app.db import Base, create_engine, create_session_factory
from app.main import app
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository
from app.vision_logic import build_reframe_plans
from app.vision_models import ManualCropOverride, VisionAnalysisRequest
from app.vision_providers import (
    ContractOnlyVisionProvider,
    DeterministicVisionProvider,
    ProviderVisionResult,
    VisionProviderNotConfigured,
)
from app.vision_repository import VisionRepository
from app.vision_service import VisionAnalysisService


class FakeMediaProbe:
    async def probe(self, path: Path, *, detected_content_type: str, media_kind: str) -> MediaMetadata:
        assert path.is_file()
        return MediaMetadata(
            media_kind=media_kind,
            detected_content_type=detected_content_type,
            format_name="mov,mp4,m4a,3gp,3g2,mj2",
            duration_seconds=16.0,
            width=1080,
            height=1920,
            fps=30,
            video_codec="h264",
            audio_codec="aac",
            audio_channels=2,
            audio_sample_rate=48000,
        )


class UnsafeExternalVisionProvider(DeterministicVisionProvider):
    key = "external-vision-test"
    model = "external-test-model"

    async def analyze(self, *args, **kwargs) -> ProviderVisionResult:
        result = await super().analyze(*args, **kwargs)
        return ProviderVisionResult(
            frames=result.frames,
            provenance={
                **result.provenance,
                "fixture": False,
                "external_call": True,
                "paid": True,
            },
        )


async def bytes_stream(payload: bytes) -> AsyncIterator[bytes]:
    midpoint = max(1, len(payload) // 2)
    yield payload[:midpoint]
    yield payload[midpoint:]


def synthetic_mp4(size: int = 100_000) -> bytes:
    header = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    return header + b"V" * (size - len(header))


async def setup_services(tmp_path: Path):
    database = tmp_path / "vision.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="vision-test", name="Vision Test", owner_ref="test-owner")
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="smart-reframe", name="Smart Reframe", niche="real_estate"),
    )
    version = await platform.ensure_initial_version(project.project_id, snapshot={"mode": "vision"})
    await platform.seed_providers(
        [
            {
                "provider_key": "fixture-transcription",
                "display_name": "Fixture Transcript",
                "capability": "transcription",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
            },
            {
                "provider_key": "fixture-media-signals",
                "display_name": "Fixture Signals",
                "capability": "media_analysis",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
            },
            {
                "provider_key": "fixture-vision",
                "display_name": "Fixture Vision",
                "capability": "vision",
                "adapter": "fixture",
                "routing_mode": "primary",
                "status": "healthy",
                "enabled": True,
                "supports_dry_run": True,
            },
        ]
    )
    storage = LocalObjectStorageProvider(tmp_path / "objects")
    await storage.ensure_ready()
    auto_repository = AutoEditRepository(session_factory)
    upload_service = UploadService(
        repository=auto_repository,
        platform=platform,
        object_storage=storage,
        media_probe=FakeMediaProbe(),
        staging_root=tmp_path / "uploads",
        default_part_size_bytes=64 * 1024,
        max_part_size_bytes=128 * 1024,
        max_upload_size_bytes=1024 * 1024,
    )
    auto_service = AutoEditAnalysisService(
        repository=auto_repository,
        platform=platform,
        object_storage=storage,
        transcription_provider=DeterministicTranscriptionProvider(),
        signal_provider=DeterministicMediaSignalProvider(),
        staging_root=tmp_path / "auto-analysis",
    )
    vision_repository = VisionRepository(session_factory)
    vision_service = VisionAnalysisService(
        repository=vision_repository,
        auto_edit_repository=auto_repository,
        platform=platform,
        object_storage=storage,
        provider=DeterministicVisionProvider(),
        staging_root=tmp_path / "vision-analysis",
    )
    return (
        engine,
        session_factory,
        platform,
        storage,
        auto_repository,
        upload_service,
        auto_service,
        vision_repository,
        vision_service,
        project,
        version,
    )


async def create_auto_edit(upload_service, auto_service, project, version):
    payload = synthetic_mp4()
    checksum = hashlib.sha256(payload).hexdigest()
    upload = await upload_service.initialize(
        UploadInitRequest(
            project_id=project.project_id,
            project_version_id=version.project_version_id,
            filename="vision-source.mp4",
            media_kind="video",
            content_type="video/mp4",
            size_bytes=len(payload),
            checksum_sha256=checksum,
            part_size_bytes=64 * 1024,
        )
    )
    for part_number in range(1, upload.total_parts + 1):
        start = (part_number - 1) * upload.part_size_bytes
        part = payload[start : start + upload.part_size_bytes]
        await upload_service.store_part(
            upload.upload_id,
            part_number,
            bytes_stream(part),
            expected_part_sha256=hashlib.sha256(part).hexdigest(),
        )
    completed = await upload_service.complete(
        upload.upload_id,
        UploadCompleteRequest(checksum_sha256=checksum),
    )
    auto_edit = await auto_service.analyze(
        project.project_id,
        AutoEditAnalysisRequest(asset_id=completed.asset_id, top_highlights=3),
    )
    return completed, auto_edit


def test_vision_request_rejects_ambiguous_overrides() -> None:
    with pytest.raises(ValidationError, match="aspect ratios must be unique"):
        VisionAnalysisRequest(aspect_ratios=["9:16", "9:16"])
    with pytest.raises(ValidationError, match="must be requested"):
        VisionAnalysisRequest(
            aspect_ratios=["9:16"],
            manual_overrides=[
                ManualCropOverride(aspect_ratio="1:1", time=1, x=0.5, y=0.5, scale=1.5)
            ],
        )


@pytest.mark.asyncio
async def test_structured_vision_ocr_tracking_reframe_persistence_and_replay(tmp_path: Path) -> None:
    (
        engine,
        session_factory,
        platform,
        storage,
        auto_repository,
        upload_service,
        auto_service,
        _,
        vision_service,
        project,
        version,
    ) = await setup_services(tmp_path)
    completed, auto_edit = await create_auto_edit(upload_service, auto_service, project, version)
    source_asset = await auto_repository.get_asset(completed.asset_id)
    assert source_asset is not None
    before_path = tmp_path / "source-before-vision.mp4"
    await storage.download_file(object_key=source_asset.object_key, destination=before_path)
    before_checksum = hashlib.sha256(before_path.read_bytes()).hexdigest()
    request = VisionAnalysisRequest()
    result = await vision_service.analyze(
        project_id=project.project_id,
        analysis_id=auto_edit.analysis_id,
        payload=request,
    )
    assert result.status == "succeeded"
    assert result.provider_key == "fixture-vision"
    assert result.model == "deterministic-vision-v2-05"
    assert result.frames and result.scenes and result.subject_tracks
    assert result.ocr_detection_count == len(result.frames)
    assert all(frame.evidence_frame_reference.startswith("asset://") for frame in result.frames)
    assert all(frame.quality.black_frame is False for frame in result.frames)
    assert all(frame.objects and frame.ocr for frame in result.frames)
    assert {plan.aspect_ratio for plan in result.reframe_plans} == {"9:16", "16:9", "1:1", "4:5"}
    assert all(plan.strategy == "subject_track" for plan in result.reframe_plans)
    for plan in result.reframe_plans:
        for before, after in zip(plan.keyframes, plan.keyframes[1:]):
            assert abs(after.x - before.x) <= request.maximum_crop_jump + 1e-9
            assert abs(after.y - before.y) <= request.maximum_crop_jump + 1e-9
    assert result.best_frame_ids
    assert result.thumbnail_candidate_ids
    assert result.source_media_mutated is False
    assert result.publish_requested is False
    assert result.paid_external_call is False
    assert result.provenance["provider_evidence"]["fixture"] is True
    assert result.provenance["provider_evidence"]["real_provider_tested"] is False
    after_path = tmp_path / "source-after-vision.mp4"
    await storage.download_file(object_key=source_asset.object_key, destination=after_path)
    assert hashlib.sha256(after_path.read_bytes()).hexdigest() == before_checksum
    assert before_checksum == source_asset.checksum_sha256
    assert not any((tmp_path / "vision-analysis").iterdir())

    replay = await vision_service.analyze(
        project_id=project.project_id,
        analysis_id=auto_edit.analysis_id,
        payload=request,
    )
    assert replay.vision_analysis_id == result.vision_analysis_id
    assert len(await vision_service.list(project.project_id)) == 1
    summary = await platform.project_cost_summary(project.project_id)
    assert summary.currency == "VND"
    assert summary.actual_cost == 0
    assert summary.records == 3

    restarted = VisionRepository(session_factory)
    assert await restarted.get_analysis(result.vision_analysis_id) == result
    await engine.dispose()


@pytest.mark.asyncio
async def test_manual_override_is_versioned_by_fingerprint_and_applied(tmp_path: Path) -> None:
    (
        engine,
        _,
        _,
        _,
        _,
        upload_service,
        auto_service,
        _,
        vision_service,
        project,
        version,
    ) = await setup_services(tmp_path)
    _, auto_edit = await create_auto_edit(upload_service, auto_service, project, version)
    request = VisionAnalysisRequest(
        aspect_ratios=["9:16"],
        manual_overrides=[
            ManualCropOverride(aspect_ratio="9:16", time=1.0, x=0.4, y=0.42, scale=1.2),
            ManualCropOverride(aspect_ratio="9:16", time=8.0, x=0.6, y=0.4, scale=1.25),
        ],
    )
    result = await vision_service.analyze(
        project_id=project.project_id,
        analysis_id=auto_edit.analysis_id,
        payload=request,
    )
    plan = result.reframe_plans[0]
    assert plan.strategy == "manual_override"
    assert plan.manual_override_applied is True
    assert [item.model_dump() for item in plan.keyframes] == [
        {"time": 1.0, "x": 0.4, "y": 0.42, "scale": 1.2},
        {"time": 8.0, "x": 0.6, "y": 0.4, "scale": 1.25},
    ]
    await engine.dispose()


def test_low_confidence_tracking_falls_back_to_center_crop() -> None:
    metadata = MediaMetadata(
        media_kind="video",
        detected_content_type="video/mp4",
        duration_seconds=10,
        width=1920,
        height=1080,
    )
    plans = build_reframe_plans(
        frames=[],
        tracks=[],
        metadata=metadata,
        aspect_ratios=["9:16"],
        manual_overrides=[],
        minimum_tracking_confidence=0.8,
        subtitle_safe_area_bottom=0.18,
        maximum_jump=0.08,
        fingerprint="f" * 64,
    )
    assert plans[0].strategy == "center_crop"
    assert plans[0].fallback == "center_crop"
    assert plans[0].needs_attention is True
    assert plans[0].subject_track_id is None


@pytest.mark.asyncio
async def test_unconfigured_live_provider_fails_closed(tmp_path: Path) -> None:
    (
        engine,
        _,
        platform,
        storage,
        auto_repository,
        upload_service,
        auto_service,
        vision_repository,
        _,
        project,
        version,
    ) = await setup_services(tmp_path)
    _, auto_edit = await create_auto_edit(upload_service, auto_service, project, version)
    service = VisionAnalysisService(
        repository=vision_repository,
        auto_edit_repository=auto_repository,
        platform=platform,
        object_storage=storage,
        provider=ContractOnlyVisionProvider(),
        staging_root=tmp_path / "vision-contract",
    )
    with pytest.raises(VisionProviderNotConfigured):
        await service.analyze(
            project_id=project.project_id,
            analysis_id=auto_edit.analysis_id,
            payload=VisionAnalysisRequest(),
        )
    failed = (await service.list(project.project_id))[0]
    assert failed.status == "failed"
    assert failed.error_code == "PROVIDER_NOT_CONFIGURED"
    assert failed.frames == []
    assert failed.publish_requested is False
    await engine.dispose()


@pytest.mark.asyncio
async def test_external_or_paid_vision_provider_is_rejected_before_cost_record(tmp_path: Path) -> None:
    (
        engine,
        _,
        platform,
        storage,
        auto_repository,
        upload_service,
        auto_service,
        vision_repository,
        _,
        project,
        version,
    ) = await setup_services(tmp_path)
    _, auto_edit = await create_auto_edit(upload_service, auto_service, project, version)
    service = VisionAnalysisService(
        repository=vision_repository,
        auto_edit_repository=auto_repository,
        platform=platform,
        object_storage=storage,
        provider=UnsafeExternalVisionProvider(),
        staging_root=tmp_path / "vision-external-rejected",
    )
    with pytest.raises(RuntimeError, match="external or paid Vision execution is disabled"):
        await service.analyze(
            project_id=project.project_id,
            analysis_id=auto_edit.analysis_id,
            payload=VisionAnalysisRequest(),
        )
    failed = (await service.list(project.project_id))[0]
    assert failed.status == "failed"
    assert failed.error_code == "VISION_ANALYSIS_FAILED"
    summary = await platform.project_cost_summary(project.project_id)
    assert summary.records == 2
    assert summary.actual_cost == 0
    assert not any((tmp_path / "vision-external-rejected").iterdir())
    await engine.dispose()


@pytest.mark.asyncio
async def test_vision_api_contract_and_restart_read(tmp_path: Path) -> None:
    (
        engine,
        _,
        platform,
        _,
        _,
        upload_service,
        auto_service,
        _,
        vision_service,
        project,
        version,
    ) = await setup_services(tmp_path)
    _, auto_edit = await create_auto_edit(upload_service, auto_service, project, version)
    app.state.vision_analysis_service = vision_service
    install_test_human_auth(app, platform_repository=platform)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=TEST_HUMAN_HEADERS
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{project.project_id}/analyses/{auto_edit.analysis_id}/vision",
            json={"aspect_ratios": ["9:16", "1:1"], "sample_interval_seconds": 4},
        )
        assert response.status_code == 201, response.text
        result = response.json()
        assert result["status"] == "succeeded"
        assert [item["aspect_ratio"] for item in result["reframe_plans"]] == ["9:16", "1:1"]
        recovered = await client.get(
            f"/api/v1/projects/{project.project_id}/vision-analyses/{result['vision_analysis_id']}"
        )
        assert recovered.status_code == 200
        assert recovered.json() == result
        listed = await client.get(f"/api/v1/projects/{project.project_id}/vision-analyses")
        assert listed.status_code == 200
        assert len(listed.json()) == 1
    await engine.dispose()
