from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
import httpx
from httpx import ASGITransport, AsyncClient
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
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
from app.media_security import DeterministicMediaMalwareScanner
from app.media_intelligence_models import MediaPlanRequest, MediaResolutionRequest
from app.media_intelligence_providers import (
    ComfyUIBridgeGenerationProvider,
    ContractOnlyImageGenerationProvider,
    ContractOnlyStockMediaProvider,
    ContractOnlyVideoGenerationProvider,
    DeterministicImageGenerationProvider,
    DeterministicStockMediaProvider,
    DeterministicVideoGenerationProvider,
)
from app.media_intelligence_models import ImageGenerationInput
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_service import (
    MEDIA_RESOLUTION_QUEUE_KEY,
    MediaPlanningService,
    MediaProviderBundle,
    MediaResolutionService,
)
from app.object_storage import LocalObjectStorageProvider
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository
from app.vision_models import VisionAnalysisRequest
from app.vision_providers import DeterministicVisionProvider
from app.vision_repository import VisionRepository
from app.vision_service import VisionAnalysisService


class FakeRedis:
    def __init__(self) -> None:
        self.values: list[tuple[str, str]] = []

    async def rpush(self, key: str, value: str) -> None:
        self.values.append((key, value))


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


class HighCostImageProvider(DeterministicImageGenerationProvider):
    def __init__(self) -> None:
        self.generate_calls = 0

    async def estimate_cost(self, payload) -> Decimal:
        return Decimal("5000")

    async def generate(self, payload):
        self.generate_calls += 1
        return await super().generate(payload)


class UnknownRightsImageProvider(DeterministicImageGenerationProvider):
    async def generate(self, payload):
        materialized = await super().generate(payload)
        return replace(
            materialized,
            rights_status="unknown",
            production_eligible=True,
            license="unknown",
        )


class UnsafeExternalImageProvider(HighCostImageProvider):
    key = "external-paid-image-test"
    external = True
    paid = True
    real_provider_tested = False

    def __init__(self) -> None:
        super().__init__()
        self.estimate_calls = 0

    async def estimate_cost(self, payload) -> Decimal:
        self.estimate_calls += 1
        return await super().estimate_cost(payload)


async def bytes_stream(payload: bytes) -> AsyncIterator[bytes]:
    midpoint = max(1, len(payload) // 2)
    yield payload[:midpoint]
    yield payload[midpoint:]


def synthetic_mp4(size: int = 100_000) -> bytes:
    header = b"\x00\x00\x00\x18ftypisom\x00\x00\x02\x00isomiso2"
    return header + b"M" * (size - len(header))


async def setup_media_stack(tmp_path: Path, providers: MediaProviderBundle | None = None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "media-intelligence.db"
    engine = create_engine(f"sqlite+aiosqlite:///{database.as_posix()}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.run_sync(Base.metadata.create_all)
    session_factory = create_session_factory(engine)
    platform = PlatformRepository(session_factory)
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="media-test", name="Media Test", owner_ref="test-owner")
    )
    project = await platform.create_project(
        workspace.workspace_id,
        ProjectCreate(slug="media-intelligence", name="Media Intelligence", niche="real_estate"),
    )
    version = await platform.ensure_initial_version(project.project_id, snapshot={"mode": "v2-06"})
    await platform.seed_providers(
        [
            {"provider_key": key, "display_name": key, "capability": capability,
             "adapter": "fixture", "routing_mode": "primary", "status": "healthy",
             "enabled": True, "supports_dry_run": True}
            for key, capability in [
                ("fixture-transcription", "transcription"),
                ("fixture-media-signals", "media_analysis"),
                ("fixture-vision", "vision"),
                ("internal-media", "internal_media"),
                ("fixture-stock", "stock_media"),
                ("stock-not-configured", "stock_media"),
                ("fixture-image-generation", "image_generation"),
                ("image-generation-not-configured", "image_generation"),
                ("fixture-video-generation", "video_generation"),
                ("video-generation-not-configured", "video_generation"),
                ("external-paid-image-test", "image_generation"),
            ]
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
        malware_scanner=DeterministicMediaMalwareScanner(),
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
    payload = synthetic_mp4()
    checksum = hashlib.sha256(payload).hexdigest()
    upload = await upload_service.initialize(
        UploadInitRequest(
            project_id=project.project_id,
            project_version_id=version.project_version_id,
            filename="media-source.mp4",
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
    source_asset = await upload_service.complete(
        upload.upload_id, UploadCompleteRequest(checksum_sha256=checksum)
    )
    auto_edit = await auto_service.analyze(
        project.project_id,
        AutoEditAnalysisRequest(asset_id=source_asset.asset_id, top_highlights=3),
    )
    vision = await vision_service.analyze(
        project_id=project.project_id,
        analysis_id=auto_edit.analysis_id,
        payload=VisionAnalysisRequest(aspect_ratios=["9:16", "16:9", "1:1", "4:5"]),
    )
    media_repository = MediaIntelligenceRepository(session_factory)
    provider_bundle = providers or MediaProviderBundle(
        stock=DeterministicStockMediaProvider(),
        image=DeterministicImageGenerationProvider(),
        video=DeterministicVideoGenerationProvider(),
    )
    queue = FakeRedis()
    planner = MediaPlanningService(
        repository=media_repository,
        auto_edit_repository=auto_repository,
        vision_repository=vision_repository,
        platform=platform,
        providers=provider_bundle,
        allow_external_execution=False,
        allow_paid_execution=False,
    )
    resolver = MediaResolutionService(
        repository=media_repository,
        platform=platform,
        auto_edit_repository=auto_repository,
        object_storage=storage,
        providers=provider_bundle,
        queue=queue,
        staging_root=tmp_path / "media-resolution",
        allow_external_execution=False,
        allow_paid_execution=False,
    )
    return {
        "engine": engine,
        "session_factory": session_factory,
        "platform": platform,
        "storage": storage,
        "auto_repository": auto_repository,
        "media_repository": media_repository,
        "planner": planner,
        "resolver": resolver,
        "queue": queue,
        "project": project,
        "version": version,
        "source_asset": source_asset,
        "auto_edit": auto_edit,
        "vision": vision,
    }


def plan_request(stack, *, max_ai_cost_vnd: Decimal = Decimal("0")) -> MediaPlanRequest:
    return MediaPlanRequest(
        analysis_id=stack["auto_edit"].analysis_id,
        vision_analysis_id=stack["vision"].vision_analysis_id,
        platform="facebook_reels",
        brand_context="Ngoc Phuong Dong original real-estate media",
        max_ai_cost_vnd=max_ai_cost_vnd,
    )


@pytest.mark.asyncio
async def test_media_plan_broll_resolution_rights_cost_and_restart(tmp_path: Path) -> None:
    stack = await setup_media_stack(tmp_path)
    plan = await stack["planner"].create(
        project_id=stack["project"].project_id,
        payload=plan_request(stack),
    )
    replay = await stack["planner"].create(
        project_id=stack["project"].project_id,
        payload=plan_request(stack),
    )
    assert replay.media_plan_id == plan.media_plan_id
    assert [item.strategy for item in plan.items] == [
        "user_asset", "stock_video", "ai_image", "ai_video"
    ]
    assert all(item.broll.search_query and item.broll.generation_prompt for item in plan.items)
    assert all(item.broll.placement_end_seconds > item.broll.placement_start_seconds for item in plan.items)
    assert plan.projected_ai_cost_vnd == 0
    assert plan.needs_approval is False
    assert plan.paid_external_call is False
    assert plan.source_media_mutated is False and plan.publish_requested is False
    assert plan.items[1].candidates
    assert all(candidate.license and candidate.creator and candidate.source_reference for candidate in plan.items[1].candidates)
    assert all(candidate.provenance["social_media_downloaded"] is False for candidate in plan.items[1].candidates)

    jobs = []
    for item in plan.items:
        job = await stack["resolver"].enqueue(
            project_id=plan.project_id,
            media_plan_id=plan.media_plan_id,
            media_plan_item_id=item.media_plan_item_id,
            payload=MediaResolutionRequest(),
        )
        assert job.status == "queued"
        assert job.external_call is False and job.paid is False and job.real_provider_tested is False
        jobs.append(job)
    assert stack["queue"].values == [
        (MEDIA_RESOLUTION_QUEUE_KEY, job.resolution_job_id) for job in jobs
    ]
    # Resolution normally happens in another worker process.  Recreate every
    # deterministic provider to prove persisted plan candidates, rather than an
    # API-process memory cache, are sufficient after a restart.
    resolver_after_restart = MediaResolutionService(
        repository=stack["media_repository"],
        platform=stack["platform"],
        auto_edit_repository=stack["auto_repository"],
        object_storage=stack["storage"],
        providers=MediaProviderBundle(
            stock=DeterministicStockMediaProvider(),
            image=DeterministicImageGenerationProvider(),
            video=DeterministicVideoGenerationProvider(),
        ),
        queue=stack["queue"],
        staging_root=tmp_path / "media-resolution",
        allow_external_execution=False,
        allow_paid_execution=False,
    )
    results = [await resolver_after_restart.process(job.resolution_job_id) for job in jobs]
    assert all(result.status == "succeeded" for result in results)
    materialized_results = [
        result for result in results if result.capability != "internal_media"
    ]
    assert materialized_results
    assert all(
        result.provenance["provider_artifact_storage_verified"] is True
        and result.provenance["provider_artifact_evidence_id"].startswith("pae_")
        and result.provenance["provider_safety_receipt"]["external_call"] is False
        for result in materialized_results
    )
    completed = await stack["media_repository"].get_plan(plan.media_plan_id)
    assert completed is not None
    assert completed.unresolved_items == 0
    assert len(completed.media_assets) == 4
    assert completed.publishing_blocked is True
    user_media = next(item for item in completed.media_assets if item.source_type == "user_upload")
    assert user_media.rights_status == "owned" and user_media.publishing_allowed is True
    fixture_media = [item for item in completed.media_assets if item.source_type != "user_upload"]
    assert fixture_media and all(not item.production_eligible for item in fixture_media)
    assert all(not item.publishing_allowed and not item.owner_override_recorded for item in fixture_media)
    assert all(item.generation_provenance.get("real_provider_tested") is False for item in fixture_media)
    source_after = await stack["auto_repository"].get_asset(stack["source_asset"].asset_id)
    assert source_after is not None
    assert source_after.checksum_sha256 == stack["source_asset"].checksum_sha256
    staging = tmp_path / "media-resolution"
    assert staging.is_dir() and not list(staging.iterdir())
    costs = await stack["platform"].list_cost_records(plan.project_id)
    assert len(costs) >= 7
    assert all(item.currency == "VND" and item.actual_cost == 0 for item in costs)
    restarted = MediaIntelligenceRepository(stack["session_factory"])
    assert (await restarted.get_plan(plan.media_plan_id)) == completed
    await stack["engine"].dispose()


@pytest.mark.asyncio
async def test_unknown_rights_fail_closed_and_no_owner_override(tmp_path: Path) -> None:
    providers = MediaProviderBundle(
        stock=DeterministicStockMediaProvider(),
        image=UnknownRightsImageProvider(),
        video=DeterministicVideoGenerationProvider(),
    )
    stack = await setup_media_stack(tmp_path, providers)
    plan = await stack["planner"].create(project_id=stack["project"].project_id, payload=plan_request(stack))
    item = next(value for value in plan.items if value.strategy == "ai_image")
    job = await stack["resolver"].enqueue(
        project_id=plan.project_id,
        media_plan_id=plan.media_plan_id,
        media_plan_item_id=item.media_plan_item_id,
        payload=MediaResolutionRequest(),
    )
    assert (await stack["resolver"].process(job.resolution_job_id)).status == "succeeded"
    recovered = await stack["media_repository"].get_plan(plan.media_plan_id)
    assert recovered is not None
    media = next(value for value in recovered.media_assets if value.media_plan_item_id == item.media_plan_item_id)
    assert media.rights_status == "unknown"
    assert media.production_eligible is True
    assert media.publishing_allowed is False
    assert media.owner_override_recorded is False
    await stack["engine"].dispose()


@pytest.mark.asyncio
async def test_configured_resolver_priority_changes_strategy_and_fallback_order(
    tmp_path: Path,
) -> None:
    stack = await setup_media_stack(tmp_path)
    request = plan_request(stack).model_copy(
        update={
            "resolver_priority": [
                "ai_video",
                "licensed_stock",
                "user_asset",
                "ai_image",
                "motion_graphic",
            ]
        }
    )
    plan = await stack["planner"].create(
        project_id=stack["project"].project_id,
        payload=request,
    )
    assert plan.items[0].strategy == "ai_video"
    assert plan.items[0].fallback[0] in {"stock_video", "stock_image"}
    assert plan.configuration.resolver_priority == request.resolver_priority
    await stack["engine"].dispose()


@pytest.mark.asyncio
async def test_cost_gate_not_configured_and_external_providers_fail_closed(tmp_path: Path) -> None:
    costly = HighCostImageProvider()
    stack = await setup_media_stack(
        tmp_path / "cost",
        MediaProviderBundle(
            stock=DeterministicStockMediaProvider(),
            image=costly,
            video=DeterministicVideoGenerationProvider(),
        ),
    )
    plan = await stack["planner"].create(project_id=stack["project"].project_id, payload=plan_request(stack))
    ai_item = next(value for value in plan.items if value.strategy == "ai_image")
    assert ai_item.needs_approval is True and plan.needs_approval is True
    job = await stack["resolver"].enqueue(
        project_id=plan.project_id,
        media_plan_id=plan.media_plan_id,
        media_plan_item_id=ai_item.media_plan_item_id,
        payload=MediaResolutionRequest(),
    )
    assert job.status == "needs_approval"
    assert costly.generate_calls == 0
    await stack["engine"].dispose()

    external = UnsafeExternalImageProvider()
    external_stack = await setup_media_stack(
        tmp_path / "external",
        MediaProviderBundle(
            stock=DeterministicStockMediaProvider(),
            image=external,
            video=ContractOnlyVideoGenerationProvider(),
        ),
    )
    external_plan = await external_stack["planner"].create(
        project_id=external_stack["project"].project_id,
        payload=plan_request(external_stack),
    )
    assert external.estimate_calls == 0 and external.generate_calls == 0
    assert external_plan.provider_status["image_generation"]["status"] == "disabled"
    assert external_plan.provider_status["external_execution_enabled"] is False
    assert external_plan.provider_status["paid_execution_enabled"] is False
    await external_stack["engine"].dispose()

    contract_stack = await setup_media_stack(
        tmp_path / "contract",
        MediaProviderBundle(
            stock=ContractOnlyStockMediaProvider(),
            image=ContractOnlyImageGenerationProvider(),
            video=ContractOnlyVideoGenerationProvider(),
        ),
    )
    contract_plan = await contract_stack["planner"].create(
        project_id=contract_stack["project"].project_id,
        payload=plan_request(contract_stack),
    )
    assert all(value["status"] == "not_configured" for key, value in contract_plan.provider_status.items() if key in {"stock", "image_generation", "video_generation"})
    assert contract_plan.items[0].strategy == "user_asset"
    unavailable = next(item for item in contract_plan.items[1:] if item.strategy == "motion_graphic")
    assert unavailable.needs_attention is True
    unavailable_job = await contract_stack["resolver"].enqueue(
        project_id=contract_plan.project_id,
        media_plan_id=contract_plan.media_plan_id,
        media_plan_item_id=unavailable.media_plan_item_id,
        payload=MediaResolutionRequest(),
    )
    unavailable_result = await contract_stack["resolver"].process(unavailable_job.resolution_job_id)
    assert unavailable_result.status == "failed"
    assert unavailable_result.error_code == "PROVIDER_NOT_CONFIGURED", unavailable_result.failure_reason
    await contract_stack["engine"].dispose()


@pytest.mark.asyncio
async def test_media_intelligence_api_contract(tmp_path: Path) -> None:
    stack = await setup_media_stack(tmp_path)
    app.state.media_planning_service = stack["planner"]
    app.state.media_resolution_service = stack["resolver"]
    install_test_human_auth(app, platform_repository=stack["platform"])
    payload = plan_request(stack).model_dump(mode="json")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test", headers=TEST_HUMAN_HEADERS
    ) as client:
        response = await client.post(
            f"/api/v1/projects/{stack['project'].project_id}/media-plans", json=payload
        )
        assert response.status_code == 201, response.text
        plan = response.json()
        assert len(plan["items"]) == 4
        listed = await client.get(f"/api/v1/projects/{stack['project'].project_id}/media-plans")
        assert listed.status_code == 200 and len(listed.json()) == 1
        recovered = await client.get(
            f"/api/v1/projects/{stack['project'].project_id}/media-plans/{plan['media_plan_id']}"
        )
        assert recovered.status_code == 200 and recovered.json() == plan
        item = plan["items"][0]
        queued = await client.post(
            f"/api/v1/projects/{stack['project'].project_id}/media-plans/{plan['media_plan_id']}/items/{item['media_plan_item_id']}/resolve",
            json={},
        )
        assert queued.status_code == 202, queued.text
        job = queued.json()
        status_response = await client.get(
            f"/api/v1/projects/{stack['project'].project_id}/media-resolution-jobs/{job['resolution_job_id']}"
        )
        assert status_response.status_code == 200 and status_response.json() == job
        assets = await client.get(f"/api/v1/projects/{stack['project'].project_id}/media-assets")
        assert assets.status_code == 200 and assets.json() == []
    await stack["engine"].dispose()


@pytest.mark.asyncio
async def test_comfyui_provider_sends_only_allowlisted_contract_fields() -> None:
    submitted: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal submitted
        if request.method == "POST":
            submitted = __import__("json").loads(request.content)
            return httpx.Response(
                202,
                json={
                    "job_id": "cui_fixture_http",
                    "status": "queued",
                    "workflow_id": "npd-text-to-image-v1",
                },
            )
        return httpx.Response(
            200,
            json={
                "job_id": "cui_fixture_http",
                "status": "succeeded",
                "result": {
                    "artifact_reference": "fixture://comfyui/result",
                    "checksum_sha256": "a" * 64,
                },
            },
        )

    provider = ComfyUIBridgeGenerationProvider(
        bridge_url="http://bridge.test",
        modality="image",
        workflow_id="npd-text-to-image-v1",
        enabled=True,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )
    result = await provider.generate(
        ImageGenerationInput(prompt="original fixture", aspect_ratio="9:16", seed=9)
    )
    assert set(submitted) == {"workflow_id", "inputs", "client_request_id"}
    assert "graph" not in submitted and "model_weights" not in submitted
    assert submitted["workflow_id"] == "npd-text-to-image-v1"
    assert result.external_call is True and result.paid is False
    assert result.rights_status == "unknown" and result.production_eligible is False
    assert result.real_provider_tested is False
