from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.auto_edit_models import MediaMetadata
from app.openai_vision_provider import (
    ExtractedVisionFrame,
    FFmpegVisionFrameExtractor,
    OpenAIVisionProvider,
    OpenAIVisionResponseError,
    VisionFrameExtractionError,
)
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderCallContext,
    ProviderCircuitPolicy,
    ProviderRetryPolicy,
    ProviderRightsEvidence,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    ProviderSafetyPolicy,
    ProviderTimeoutError,
)
from app.vision_providers import VisionProviderNotConfigured


class StaticFrameExtractor:
    def __init__(self, count: int = 2) -> None:
        self.calls = 0
        self.max_frames = count
        self.frames = tuple(
            ExtractedVisionFrame(
                timestamp_seconds=float(index),
                evidence_frame_reference=f"asset://ast_test#frame={index}",
                content_type="image/jpeg",
                payload=b"\xff\xd8\xff" + bytes([index]) + b"contract-frame",
                sha256=__import__("hashlib").sha256(
                    b"\xff\xd8\xff" + bytes([index]) + b"contract-frame"
                ).hexdigest(),
            )
            for index in range(count)
        )

    async def extract(self, *_args, **_kwargs) -> tuple[ExtractedVisionFrame, ...]:
        self.calls += 1
        return self.frames


class SecretResolver:
    def __init__(self, value: str = "contract-test-credential") -> None:
        self.value = value
        self.calls = 0

    def __call__(self, _alias: str) -> str:
        self.calls += 1
        return self.value


def output_frame(index: int) -> dict[str, object]:
    return {
        "frame_index": index,
        "caption": f"Khung hình {index} có tòa nhà và tiêu đề tiếng Việt.",
        "scene_description": "Phối cảnh dự án bất động sản nhìn từ bên ngoài.",
        "semantic_label": "project_overview",
        "environment": "outdoor_property",
        "action": "showing_property",
        "objects": [
            {
                "label": "tòa nhà",
                "category": "building",
                "confidence": 0.94,
                "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.6, "height": 0.6},
                "track_hint": "primary-building",
            }
        ],
        "ocr": [
            {
                "text": "NGỌC PHƯƠNG ĐÔNG",
                "language": "vi",
                "confidence": 0.91,
                "bounding_box": {"x": 0.2, "y": 0.05, "width": 0.5, "height": 0.1},
            }
        ],
        "primary_subject_box": {"x": 0.1, "y": 0.2, "width": 0.6, "height": 0.6},
        "saliency_box": {"x": 0.1, "y": 0.2, "width": 0.6, "height": 0.6},
        "headroom_ratio": 0.2,
        "visual_balance_score": 0.87,
        "safe_crop": True,
        "quality_score": 0.9,
        "black_frame": False,
        "blur_score": 0.08,
        "overexposed": False,
        "underexposed": False,
        "low_resolution": False,
        "watermark_or_logo_detected": True,
        "frozen_or_duplicate": False,
        "quality_issues": [],
        "confidence": 0.92,
    }


def response_payload(count: int = 2) -> dict[str, object]:
    structured = json.dumps(
        {"frames": [output_frame(index) for index in range(count)]},
        ensure_ascii=False,
    )
    return {
        "id": "resp_contract_test",
        "status": "completed",
        "model": "gpt-5-mini",
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": structured}],
            }
        ],
        "usage": {
            "input_tokens": 120,
            "input_tokens_details": {"cached_tokens": 20},
            "output_tokens": 80,
        },
    }


def metadata() -> MediaMetadata:
    return MediaMetadata(
        media_kind="image",
        detected_content_type="image/jpeg",
        format_name="jpeg",
        width=1200,
        height=800,
    )


def provider(
    handler,
    *,
    resolver: SecretResolver | None = None,
    extractor: StaticFrameExtractor | None = None,
    estimate: Decimal = Decimal("0"),
) -> tuple[OpenAIVisionProvider, SecretResolver, StaticFrameExtractor]:
    secret_resolver = resolver or SecretResolver()
    frame_extractor = extractor or StaticFrameExtractor()
    adapter = OpenAIVisionProvider(
        credential_alias="secret://openai/codex-video",
        credential_resolver=secret_resolver,
        frame_extractor=frame_extractor,
        estimated_cost_vnd=estimate,
        transport=httpx.MockTransport(handler),
        allow_zero_cost_contract_test=True,
    )
    return adapter, secret_resolver, frame_extractor


async def analyze(adapter: OpenAIVisionProvider, path: Path):
    return await adapter.analyze(
        path,
        metadata=metadata(),
        scenes=[],
        asset_id="ast_test",
        checksum_sha256="a" * 64,
        sample_interval_seconds=4,
    )


def approved_policy(
    *,
    max_attempts: int = 2,
    failure_threshold: int = 2,
    per_operation_limit: Decimal = Decimal("10"),
    daily_limit: Decimal = Decimal("20"),
) -> ProviderSafetyPolicy:
    return ProviderSafetyPolicy(
        external_execution_enabled=True,
        paid_execution_enabled=True,
        global_kill_switch_engaged=False,
        credential_gate_approved=True,
        rights_gate_approved=True,
        budget=ProviderBudgetPolicy(
            approved=True,
            owner_approval_id="V3-01-APP-999",
            per_operation_limit_vnd=per_operation_limit,
            daily_limit_vnd=daily_limit,
        ),
        retry=ProviderRetryPolicy(
            max_attempts=max_attempts,
            per_request_timeout_seconds=1,
            base_delay_seconds=0,
            max_delay_seconds=0,
            max_elapsed_seconds=5,
            max_concurrent_calls=2,
        ),
        circuit=ProviderCircuitPolicy(
            failure_threshold=failure_threshold,
            cooldown_seconds=60,
        ),
    )


def rights(*, approved: bool = True) -> ProviderRightsEvidence:
    return ProviderRightsEvidence(
        rights_record_id="RIGHTS-CONTRACT-001",
        asset_id="ast_test",
        asset_hash="a" * 64,
        source_type="user_owned",
        provider="owner-upload",
        provider_asset_or_job_id="ast_test",
        source_url_or_reference="asset://ast_test",
        acquired_at_utc=datetime(2026, 8, 28, tzinfo=timezone.utc),
        license_name="owner-provided",
        license_version_or_terms_date="2026-08-28",
        commercial_use=True,
        derivative_use=True,
        social_platform_use=[],
        territory=["VN"],
        attribution_required=False,
        attribution_text="",
        model_or_voice_rights="not-applicable",
        person_likeness_consent="not-applicable",
        trademark_review="reviewed",
        evidence_reference="evidence://rights/contract-test",
        reviewer="contract-test",
        decision="APPROVED" if approved else "REJECTED",
    )


def context(
    operation_key: str,
    adapter: OpenAIVisionProvider,
    *,
    estimate: Decimal | None = Decimal("0"),
    rights_records: list[ProviderRightsEvidence] | None = None,
) -> ProviderCallContext:
    return ProviderCallContext(
        operation_key=operation_key,
        workspace_id="wsp_test",
        project_id="prj_test",
        provider_key=adapter.key,
        capability="vision",
        operation="vision_analysis",
        external_call=adapter.external_call,
        paid=adapter.paid,
        estimated_cost_vnd=estimate,
        credential_alias=adapter.credential_alias,
        rights_required=True,
        rights=rights_records if rights_records is not None else [rights()],
    )


@pytest.mark.asyncio
async def test_openai_vision_contract_uses_responses_structured_output_without_network(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(200, json=response_payload())

    adapter, resolver, extractor = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    result = await analyze(adapter, source)

    assert captured["path"] == "/v1/responses"
    assert captured["authorization"] == "Bearer contract-test-credential"
    request_payload = captured["payload"]
    assert isinstance(request_payload, dict)
    assert request_payload["model"] == "gpt-5-mini"
    assert request_payload["store"] is False
    assert request_payload["text"]["format"]["type"] == "json_schema"
    assert request_payload["text"]["format"]["strict"] is True
    image_parts = [
        item
        for item in request_payload["input"][0]["content"]
        if item["type"] == "input_image"
    ]
    assert len(image_parts) == 2
    assert resolver.calls == 1 and extractor.calls == 1
    assert len(result.frames) == 2
    assert result.frames[0].ocr[0].text == "NGỌC PHƯƠNG ĐÔNG"
    assert result.frames[0].safe_crop is True
    assert result.actual_cost_vnd == Decimal("0.000000")
    assert result.provenance["model_requested"] == "gpt-5-mini"
    assert result.provenance["real_provider_tested"] is False
    assert result.provenance["mock_tested"] is True
    assert result.provenance["cost_receipt"]["currency"] == "VND"
    assert result.provenance["cost_receipt"]["status"] == "contract_test_zero"
    serialized = json.dumps(result.provenance, ensure_ascii=False)
    assert "contract-test-credential" not in serialized
    assert "secret://openai/codex-video" not in serialized
    assert "OPENAI_API_KEY" not in serialized
    assert "contract-test-credential" not in repr(adapter)


@pytest.mark.asyncio
async def test_image_input_is_bounded_and_keeps_hash_provenance(tmp_path: Path) -> None:
    payload = b"\xff\xd8\xff" + b"owned-image"
    source = tmp_path / "owned.jpg"
    source.write_bytes(payload)
    extractor = FFmpegVisionFrameExtractor(max_frames=1, max_image_bytes=64 * 1024)

    frames = await extractor.extract(
        source,
        metadata=metadata(),
        scenes=[],
        asset_id="ast_test",
        sample_interval_seconds=4,
    )

    assert len(frames) == 1
    assert frames[0].evidence_frame_reference == "asset://ast_test#frame=0"
    assert frames[0].sha256 == __import__("hashlib").sha256(payload).hexdigest()
    source.write_bytes(b"not-an-image")
    with pytest.raises(VisionFrameExtractionError, match="signature"):
        await extractor.extract(
            source,
            metadata=metadata(),
            scenes=[],
            asset_id="ast_test",
            sample_interval_seconds=4,
        )


@pytest.mark.asyncio
async def test_mock_usage_calculates_vnd_receipt_without_real_spend(tmp_path: Path) -> None:
    adapter = OpenAIVisionProvider(
        credential_alias="secret://openai/codex-video",
        credential_resolver=SecretResolver(),
        frame_extractor=StaticFrameExtractor(),
        estimated_cost_vnd=Decimal("300"),
        input_vnd_per_million_tokens=Decimal("1000000"),
        cached_input_vnd_per_million_tokens=Decimal("500000"),
        output_vnd_per_million_tokens=Decimal("2000000"),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=response_payload())
        ),
        allow_zero_cost_contract_test=True,
    )
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    result = await analyze(adapter, source)

    assert result.actual_cost_vnd == Decimal("270.000000")
    receipt = result.provenance["cost_receipt"]
    assert receipt["currency"] == "VND"
    assert receipt["status"] == "contract_test_calculated"
    assert receipt["actual_cost_vnd"] == "270.000000"


@pytest.mark.asyncio
async def test_input_dimensions_frames_and_usage_ceilings_are_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    oversized, _, oversized_extractor = provider(
        lambda _request: httpx.Response(200, json=response_payload())
    )
    with pytest.raises(VisionFrameExtractionError, match="dimension"):
        await oversized.analyze(
            source,
            metadata=metadata().model_copy(update={"width": 2049}),
            scenes=[],
            asset_id="ast_test",
            checksum_sha256="a" * 64,
            sample_interval_seconds=4,
        )
    assert oversized_extractor.calls == 0

    one_frame = StaticFrameExtractor(count=1)
    usage_payload = response_payload(count=1)
    usage_payload["usage"]["input_tokens"] = 16_385
    adapter = OpenAIVisionProvider(
        credential_alias="secret://openai/codex-video",
        credential_resolver=SecretResolver(),
        frame_extractor=one_frame,
        max_dimension_pixels=2048,
        input_token_ceiling=16_384,
        max_output_tokens=4_096,
        estimated_cost_vnd=Decimal("500"),
        input_vnd_per_million_tokens=Decimal("6565"),
        cached_input_vnd_per_million_tokens=Decimal("656.5"),
        output_vnd_per_million_tokens=Decimal("52520"),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(200, json=usage_payload)
        ),
    )
    with pytest.raises(OpenAIVisionResponseError, match="input usage"):
        await analyze(adapter, source)


@pytest.mark.asyncio
async def test_zero_vnd_envelope_blocks_live_mode_before_frame_or_transport(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_payload())

    resolver = SecretResolver()
    extractor = StaticFrameExtractor()
    adapter = OpenAIVisionProvider(
        credential_alias="secret://openai/codex-video",
        credential_resolver=resolver,
        frame_extractor=extractor,
        transport=httpx.MockTransport(handler),
    )
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(VisionProviderNotConfigured, match="G-02"):
        await analyze(adapter, source)
    assert resolver.calls == 1
    assert extractor.calls == 0
    assert calls == 0


@pytest.mark.asyncio
async def test_default_safety_blocks_before_secret_resolution_or_transport(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_payload())

    adapter, resolver, extractor = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")
    controller = ProviderSafetyController.fail_closed()

    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(
            context("openai-vision-default-block", adapter),
            lambda: analyze(adapter, source),
            actual_cost=lambda result: result.actual_cost_vnd,
        )

    assert blocked.value.code == "GLOBAL_KILL_SWITCH_ENGAGED"
    assert resolver.calls == 0
    assert extractor.calls == 0
    assert calls == 0
    snapshot = await controller.snapshot()
    assert snapshot.external_calls_recorded == 0
    assert snapshot.paid_calls_recorded == 0
    assert snapshot.committed_today_vnd == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_alias", [True, False])
async def test_openai_vision_missing_credential_fails_before_transport(
    tmp_path: Path, missing_alias: bool
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_payload())

    resolver = SecretResolver("" if not missing_alias else "unused")
    adapter = OpenAIVisionProvider(
        credential_alias=None if missing_alias else "secret://openai/codex-video",
        credential_resolver=resolver,
        frame_extractor=StaticFrameExtractor(),
        transport=httpx.MockTransport(handler),
        allow_zero_cost_contract_test=True,
    )
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(VisionProviderNotConfigured):
        await analyze(adapter, source)
    assert calls == 0
    assert resolver.calls == (0 if missing_alias else 1)


@pytest.mark.asyncio
async def test_openai_vision_rejects_malformed_structured_response(tmp_path: Path) -> None:
    adapter, _, _ = provider(
        lambda _request: httpx.Response(
            200,
            json={
                "status": "completed",
                "output_text": '{"frames":[{"frame_index":0,"caption":"missing fields"}]}',
            },
        )
    )
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(OpenAIVisionResponseError, match="structured-output"):
        await analyze(adapter, source)


@pytest.mark.asyncio
async def test_openai_vision_maps_transport_timeout_for_central_retry(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contract timeout", request=request)

    adapter, _, _ = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(ProviderTimeoutError):
        await analyze(adapter, source)


@pytest.mark.asyncio
async def test_provider_safety_retries_rate_limit_then_records_zero_contract_cost(
    tmp_path: Path,
) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429)
        return httpx.Response(200, json=response_payload())

    adapter, _, _ = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")
    controller = ProviderSafetyController(approved_policy(max_attempts=2))

    execution = await controller.execute(
        context("openai-vision-retry", adapter),
        lambda: analyze(adapter, source),
        actual_cost=lambda result: result.actual_cost_vnd,
    )

    assert calls == 2
    assert execution.receipt.attempts == 2
    assert execution.receipt.retries == 1
    assert execution.receipt.charged_cost_vnd == 0
    assert all(attempt.charged_cost_vnd == 0 for attempt in controller.attempts)


@pytest.mark.asyncio
async def test_provider_safety_circuit_and_duplicate_operation_are_fail_closed(
    tmp_path: Path,
) -> None:
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")
    failing_adapter, failing_resolver, _ = provider(
        lambda _request: httpx.Response(503)
    )
    circuit = ProviderSafetyController(
        approved_policy(max_attempts=1, failure_threshold=1)
    )
    with pytest.raises(ProviderSafetyBlocked):
        await circuit.execute(
            context("openai-vision-circuit-failure", failing_adapter),
            lambda: analyze(failing_adapter, source),
        )
    circuit_decision = await circuit.preflight(
        context("openai-vision-circuit-next", failing_adapter)
    )
    assert circuit_decision.code == "CIRCUIT_OPEN"
    assert failing_resolver.calls == 1

    success_calls = 0

    def success_handler(_request: httpx.Request) -> httpx.Response:
        nonlocal success_calls
        success_calls += 1
        return httpx.Response(200, json=response_payload())

    success_adapter, _, _ = provider(success_handler)
    duplicate = ProviderSafetyController(approved_policy(max_attempts=1))
    duplicate_context = context("openai-vision-duplicate", success_adapter)
    await duplicate.execute(
        duplicate_context,
        lambda: analyze(success_adapter, source),
        actual_cost=lambda result: result.actual_cost_vnd,
    )
    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await duplicate.execute(
            duplicate_context,
            lambda: analyze(success_adapter, source),
        )
    assert blocked.value.code == "DUPLICATE_OPERATION_BLOCKED"
    assert success_calls == 1


@pytest.mark.asyncio
async def test_provider_safety_blocks_rights_and_budget_before_adapter(tmp_path: Path) -> None:
    calls = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=response_payload())

    adapter, resolver, extractor = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")
    controller = ProviderSafetyController(
        approved_policy(max_attempts=1, per_operation_limit=Decimal("10"))
    )

    with pytest.raises(ProviderSafetyBlocked) as rights_blocked:
        await controller.execute(
            context(
                "openai-vision-rights-block",
                adapter,
                rights_records=[rights(approved=False)],
            ),
            lambda: analyze(adapter, source),
        )
    assert rights_blocked.value.code == "RIGHTS_BLOCKED"

    with pytest.raises(ProviderSafetyBlocked) as budget_blocked:
        await controller.execute(
            context(
                "openai-vision-budget-block",
                adapter,
                estimate=Decimal("11"),
            ),
            lambda: analyze(adapter, source),
        )
    assert budget_blocked.value.code == "PER_OPERATION_BUDGET_EXCEEDED"
    assert calls == 0
    assert resolver.calls == 0
    assert extractor.calls == 0
