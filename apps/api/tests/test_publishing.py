from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import AssetORM
from app.main import app
from app.production_models import (
    ApprovalDecisionRequest,
    ApprovalRequest,
    FinalRenderCreateRequest,
    ProductionPackageCreateRequest,
    RenderCreateRequest,
)
from app.publishing_logic import PublishingCapabilityRegistry
from app.publishing_models import PublicationCreateRequest, PublicationMetadata
from app.publishing_providers import PublishingProviderRegistry
from app.publishing_repository import PublicationIdempotencyConflict, PublishingRepository
from app.publishing_service import PublishingBoundaryError, PublishingService
from test_audio_subtitle_render_qc import setup_stack


CAPABILITIES = (
    Path(__file__).resolve().parents[3] / "packages" / "contracts" / "publishing-capabilities.json"
)


def publishing_settings(**overrides):
    values = {
        "publish_enabled": False,
        "publish_external_execution_enabled": False,
        "publish_owner_gate_enabled": False,
        "youtube_publishing_credential_ref": "",
        "tiktok_publishing_credential_ref": "",
        "instagram_publishing_credential_ref": "",
        "facebook_publishing_credential_ref": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


async def approved_stack(tmp_path: Path, *, rights_status: str = "owned"):
    tmp_path.mkdir(parents=True, exist_ok=True)
    stack = await setup_stack(tmp_path)
    async with stack.repository.session_factory() as session:
        asset = await session.get(AssetORM, stack.asset.asset_id)
        assert asset is not None
        asset.provenance = {
            "source_type": "user_upload",
            "rights_status": rights_status,
            "license": "owner-provided" if rights_status != "unknown" else "",
            "production_eligible": True,
        }
        await session.commit()
    package = await stack.service.create_or_refresh(
        stack.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=1, actor_ref="owner-fixture"),
    )
    review = await stack.service.enqueue_review(
        stack.project.project_id,
        RenderCreateRequest(
            expected_timeline_version=1,
            expected_subtitle_version=package.subtitle.version,
            expected_audio_version=package.audio_mix.version,
            actor_ref="editor-fixture",
        ),
    )
    review = await stack.processor.process(review.render_id)
    approval = await stack.service.request_approval(
        stack.project.project_id,
        ApprovalRequest(review_render_id=review.render_id, requester_ref="editor-fixture"),
    )
    await stack.service.decide_approval(
        stack.project.project_id,
        approval.approval_id,
        ApprovalDecisionRequest(
            decision="approved",
            reviewer_ref="owner-fixture",
            comment="Human review fixture accepted.",
        ),
    )
    final = await stack.service.enqueue_final(
        stack.project.project_id,
        FinalRenderCreateRequest(
            expected_timeline_version=1,
            expected_subtitle_version=package.subtitle.version,
            expected_audio_version=package.audio_mix.version,
            approval_id=approval.approval_id,
            profile="vertical-1080x1920",
            actor_ref="owner-fixture",
        ),
    )
    final = await stack.processor.process(final.render_id)
    settings = publishing_settings()
    publishing = PublishingService(
        repository=PublishingRepository(stack.repository.session_factory),
        production_repository=stack.repository,
        asset_repository=stack.asset_repository,
        capabilities=PublishingCapabilityRegistry(CAPABILITIES),
        providers=PublishingProviderRegistry(settings),
        settings=settings,
    )
    return stack, final, publishing


def request_for(render_id: str, **overrides) -> PublicationCreateRequest:
    values = {
        "platform": "youtube",
        "final_render_id": render_id,
        "mode": "dry_run",
        "metadata": PublicationMetadata(
            title="Vịnh Tiên - hành trình sống ven biển",
            description="Bản mô tả kiểm thử quyền và nền tảng.",
            caption="Khám phá không gian sống Vịnh Tiên.",
            hashtags=["VinhTien", "NgocPhuongDong"],
            privacy="private",
        ),
        "actor_ref": "owner-fixture",
    }
    values.update(overrides)
    return PublicationCreateRequest(**values)


@pytest.mark.asyncio
async def test_approved_rights_checked_dry_run_is_idempotent_and_recovers(tmp_path: Path) -> None:
    stack, final, publishing = await approved_stack(tmp_path)
    payload = request_for(final.render_id)
    created, replay = await publishing.create(
        project_id=stack.project.project_id,
        payload=payload,
        idempotency_key="v2-09-youtube-dry-run-0001",
    )
    assert replay is False
    assert created.status == "dry_run_succeeded"
    assert created.rights_validation and created.rights_validation.status == "passed"
    assert created.platform_validation and created.platform_validation.status == "passed"
    assert created.provider_validation and created.provider_validation.adapter_state == "mock"
    assert created.receipt and created.receipt.mock is True
    assert created.external_action is False and created.receipt.remote_post_id is None

    recovered_service = PublishingService(
        repository=PublishingRepository(stack.repository.session_factory),
        production_repository=stack.repository,
        asset_repository=stack.asset_repository,
        capabilities=PublishingCapabilityRegistry(CAPABILITIES),
        providers=PublishingProviderRegistry(publishing_settings()),
        settings=publishing_settings(),
    )
    recovered, replay = await recovered_service.create(
        project_id=stack.project.project_id,
        payload=payload,
        idempotency_key="v2-09-youtube-dry-run-0001",
    )
    assert replay is True and recovered.publication_id == created.publication_id
    assert len(await recovered_service.list(stack.project.project_id)) == 1
    assert {item.event_type for item in await recovered_service.history(stack.project.project_id)} == {
        "publication.validation_reserved",
        "publication.dry_run_succeeded",
    }

    conflicting = request_for(
        final.render_id,
        metadata=payload.metadata.model_copy(update={"caption": "A different request"}),
    )
    with pytest.raises(PublicationIdempotencyConflict):
        await recovered_service.create(
            project_id=stack.project.project_id,
            payload=conflicting,
            idempotency_key="v2-09-youtube-dry-run-0001",
        )
    await stack.engine.dispose()


@pytest.mark.asyncio
async def test_rights_platform_and_live_boundaries_fail_closed(tmp_path: Path) -> None:
    unknown_stack, unknown_final, unknown_publishing = await approved_stack(
        tmp_path / "unknown", rights_status="unknown"
    )
    with pytest.raises(PublishingBoundaryError) as rights_error:
        await unknown_publishing.create(
            project_id=unknown_stack.project.project_id,
            payload=request_for(unknown_final.render_id),
            idempotency_key="v2-09-rights-blocked-0001",
        )
    assert rights_error.value.publication.failure_code == "RIGHTS_NOT_VERIFIED"
    assert rights_error.value.publication.external_action is False
    await unknown_stack.engine.dispose()

    stack, final, publishing = await approved_stack(tmp_path / "platform")
    too_long = request_for(
        final.render_id,
        platform="tiktok",
        metadata=PublicationMetadata(
            title="Vịnh Tiên",
            caption="x" * 2201,
            hashtags=["VinhTien"],
        ),
    )
    with pytest.raises(PublishingBoundaryError) as platform_error:
        await publishing.create(
            project_id=stack.project.project_id,
            payload=too_long,
            idempotency_key="v2-09-platform-blocked-0001",
        )
    assert platform_error.value.publication.failure_code == "CAPTION_TOO_LONG"

    live = request_for(final.render_id, mode="live")
    with pytest.raises(PublishingBoundaryError) as live_error:
        await publishing.create(
            project_id=stack.project.project_id,
            payload=live,
            idempotency_key="v2-09-live-blocked-0000001",
        )
    assert live_error.value.publication.status == "blocked"
    assert live_error.value.publication.external_action is False
    serialized = json.dumps(live_error.value.publication.model_dump(mode="json"))
    assert "token" not in serialized.lower() and "secret://" not in serialized.lower()
    await stack.engine.dispose()


@pytest.mark.asyncio
async def test_publishing_api_returns_receipt_history_and_block_evidence(tmp_path: Path) -> None:
    stack, final, publishing = await approved_stack(tmp_path)
    app.state.publishing_service = publishing
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            f"/api/v1/projects/{stack.project.project_id}/publish",
            headers={"Idempotency-Key": "v2-09-api-dry-run-0000001"},
            json=request_for(final.render_id).model_dump(mode="json"),
        )
        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "dry_run_succeeded"
        assert body["external_action"] is False and body["receipt"]["remote_post_id"] is None
        assert response.headers["X-Idempotent-Replay"] == "false"

        replay = await client.post(
            f"/api/v1/projects/{stack.project.project_id}/publish",
            headers={"Idempotency-Key": "v2-09-api-dry-run-0000001"},
            json=request_for(final.render_id).model_dump(mode="json"),
        )
        assert replay.status_code == 201
        assert replay.headers["X-Idempotent-Replay"] == "true"
        assert replay.json()["publication_id"] == body["publication_id"]

        publications = await client.get(
            f"/api/v1/projects/{stack.project.project_id}/publications"
        )
        history = await client.get(
            f"/api/v1/projects/{stack.project.project_id}/publication-history"
        )
        platforms = await client.get("/api/v1/publishing-platforms")
        assert publications.status_code == history.status_code == platforms.status_code == 200
        assert len(publications.json()) == 1 and len(history.json()) == 2
        assert len(platforms.json()) == 4
        assert all(item["live_execution_enabled"] is False for item in platforms.json())
        assert all(item["official_provider"]["supports_live_publish"] is False for item in platforms.json())

    gated_settings = publishing_settings(
        publish_enabled=True,
        publish_external_execution_enabled=True,
        publish_owner_gate_enabled=True,
        youtube_publishing_credential_ref="secret://publishing/youtube",
    )
    contract_only = PublishingService(
        repository=PublishingRepository(stack.repository.session_factory),
        production_repository=stack.repository,
        asset_repository=stack.asset_repository,
        capabilities=PublishingCapabilityRegistry(CAPABILITIES),
        providers=PublishingProviderRegistry(gated_settings),
        settings=gated_settings,
    )
    assert all(item.live_execution_enabled is False for item in contract_only.platform_states())
    await stack.engine.dispose()
