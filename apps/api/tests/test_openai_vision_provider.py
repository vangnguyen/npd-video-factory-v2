from __future__ import annotations

import asyncio
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
    _VisionOutput,
    validate_strict_structured_output_schema,
)
from app.provider_safety import (
    ProviderBudgetPolicy,
    ProviderCallContext,
    ProviderCircuitPolicy,
    ProviderExecutionTrace,
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


class VirtualMonotonic:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value

    def advance_to(self, seconds: float) -> None:
        self.value = seconds


class VirtualDelayStream(httpx.AsyncByteStream):
    def __init__(
        self,
        *,
        payload: bytes,
        request: httpx.Request,
        clock: VirtualMonotonic,
        delay_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self.payload = payload
        self.request = request
        self.clock = clock
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds

    async def __aiter__(self):
        self.clock.advance_to(self.delay_seconds)
        if self.delay_seconds >= self.timeout_seconds:
            raise httpx.ReadTimeout("virtual response timeout", request=self.request)
        yield self.payload


class VirtualDelayTransport(httpx.AsyncBaseTransport):
    def __init__(
        self,
        *,
        clock: VirtualMonotonic,
        delay_seconds: float,
        timeout_seconds: float,
    ) -> None:
        self.clock = clock
        self.delay_seconds = delay_seconds
        self.timeout_seconds = timeout_seconds
        self.calls = 0

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        payload = json.dumps(response_payload(), ensure_ascii=False).encode("utf-8")
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "x-request-id": "req_virtual_delay"},
            stream=VirtualDelayStream(
                payload=payload,
                request=request,
                clock=self.clock,
                delay_seconds=self.delay_seconds,
                timeout_seconds=self.timeout_seconds,
            ),
            request=request,
        )


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
    handler=None,
    *,
    resolver: SecretResolver | None = None,
    extractor: StaticFrameExtractor | None = None,
    estimate: Decimal = Decimal("0"),
    transport: httpx.AsyncBaseTransport | None = None,
    timeout_seconds: float = 60.0,
    monotonic_clock=None,
) -> tuple[OpenAIVisionProvider, SecretResolver, StaticFrameExtractor]:
    secret_resolver = resolver or SecretResolver()
    frame_extractor = extractor or StaticFrameExtractor()
    selected_transport = transport
    if selected_transport is None:
        if handler is None:
            raise ValueError("a mock handler or transport is required")
        selected_transport = httpx.MockTransport(handler)
    kwargs = {}
    if monotonic_clock is not None:
        kwargs["monotonic_clock"] = monotonic_clock
    adapter = OpenAIVisionProvider(
        credential_alias="secret://openai/codex-video",
        credential_resolver=secret_resolver,
        frame_extractor=frame_extractor,
        estimated_cost_vnd=estimate,
        transport=selected_transport,
        timeout_seconds=timeout_seconds,
        allow_zero_cost_contract_test=True,
        **kwargs,
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
    per_request_timeout: float = 1,
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
            per_request_timeout_seconds=per_request_timeout,
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


def test_openai_structured_output_schema_is_recursively_strict_and_nullable_required() -> None:
    schema = _VisionOutput.model_json_schema()

    validate_strict_structured_output_schema(schema)

    objects: list[dict[str, object]] = []

    def walk(node: object) -> None:
        if isinstance(node, dict):
            if isinstance(node.get("properties"), dict):
                objects.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    assert objects
    assert all(set(item["properties"]) == set(item["required"]) for item in objects)
    assert all(item.get("additionalProperties") is False for item in objects)
    object_schema = schema["$defs"]["_ObjectOutput"]
    assert "track_hint" in object_schema["required"]
    assert {item["type"] for item in object_schema["properties"]["track_hint"]["anyOf"]} == {
        "null",
        "string",
    }

    malformed = json.loads(json.dumps(schema))
    malformed["$defs"]["_ObjectOutput"]["required"].remove("track_hint")
    malformed["$defs"]["_OCROutput"]["additionalProperties"] = True
    malformed["$defs"]["_FrameOutput"]["required"].append("unknown_field")
    with pytest.raises(ValueError) as failed:
        validate_strict_structured_output_schema(malformed)
    assert "track_hint" in str(failed.value)
    assert "additionalProperties" in str(failed.value)
    assert "unknown_field" in str(failed.value)


@pytest.mark.asyncio
async def test_openai_vision_contract_uses_responses_structured_output_without_network(
    tmp_path: Path,
) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["authorization"] = request.headers.get("Authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            headers={"x-request-id": "req_contract_success"},
            json=response_payload(),
        )

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
    assert request_payload["text"]["format"]["schema"]["$defs"]["_ObjectOutput"][
        "required"
    ] == ["label", "category", "confidence", "bounding_box", "track_hint"]
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
    assert result.provenance["provider_request_id"] == "req_contract_success"
    assert str(result.provenance["client_request_id"]).startswith("vf-")
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

    with pytest.raises(OpenAIVisionResponseError, match="structured-output") as failed:
        await analyze(adapter, source)
    assert failed.value.error_evidence.category == "structured_output_validation"
    assert failed.value.error_evidence.code == "OPENAI_VISION_STRUCTURED_OUTPUT_INVALID"


@pytest.mark.asyncio
async def test_openai_vision_accepts_required_nullable_track_hint(tmp_path: Path) -> None:
    payload = response_payload()
    payload["output"][0]["content"][0]["text"] = json.dumps(
        {
            "frames": [
                {
                    **output_frame(index),
                    "objects": [
                        {
                            **output_frame(index)["objects"][0],
                            "track_hint": None,
                        }
                    ],
                }
                for index in range(2)
            ]
        },
        ensure_ascii=False,
    )
    adapter, _, _ = provider(lambda _request: httpx.Response(200, json=payload))
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    result = await analyze(adapter, source)

    assert result.frames[0].objects[0].track_hint is None


@pytest.mark.asyncio
async def test_openai_400_error_is_redacted_classified_and_recorded_once(tmp_path: Path) -> None:
    calls = 0
    secret_fragment = "sk-" + ("x" * 24)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            400,
            headers={"x-request-id": "req_schema_contract_400"},
            json={
                "error": {
                    "type": "invalid_request_error",
                    "code": "invalid_json_schema",
                    "param": "text.format.schema",
                    "message": (
                        "Invalid schema: track_hint must be required; "
                        f"Bearer {secret_fragment}; token={secret_fragment}"
                    ),
                }
            },
        )

    adapter, _, _ = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")
    controller = ProviderSafetyController(approved_policy(max_attempts=1))

    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(
            context("openai-vision-schema-400", adapter),
            lambda: analyze(adapter, source),
        )

    evidence = blocked.value.error_evidence
    assert calls == 1
    assert blocked.value.code == "OPENAI_VISION_HTTP_ERROR"
    assert evidence is not None
    assert evidence.category == "http_provider_error"
    assert evidence.http_status == 400
    assert evidence.provider_error_type == "invalid_request_error"
    assert evidence.provider_error_code == "invalid_json_schema"
    assert evidence.provider_error_parameter == "text.format.schema"
    assert evidence.provider_request_id == "req_schema_contract_400"
    assert evidence.response_sha256 is not None
    assert evidence.retryable is False
    assert controller.attempts[0].error_evidence == evidence
    serialized = json.dumps(evidence.model_dump(mode="json"))
    assert secret_fragment not in serialized
    assert "<redacted>" in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("response_factory", "category", "code"),
    [
        (
            lambda: httpx.Response(200, content=b"{not-json"),
            "response_parse_failure",
            "OPENAI_VISION_RESPONSE_PARSE_FAILED",
        ),
        (
            lambda: httpx.Response(
                200,
                json={
                    "status": "incomplete",
                    "incomplete_details": {"reason": "max_output_tokens"},
                },
            ),
            "structured_output_incomplete",
            "OPENAI_VISION_RESPONSE_INCOMPLETE",
        ),
        (
            lambda: httpx.Response(
                200,
                json={
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "refusal", "refusal": "Cannot analyze image"}],
                        }
                    ],
                },
            ),
            "structured_output_refusal",
            "OPENAI_VISION_STRUCTURED_OUTPUT_REFUSAL",
        ),
        (
            lambda: httpx.Response(
                200,
                json={key: value for key, value in response_payload().items() if key != "usage"},
            ),
            "usage_receipt_missing",
            "OPENAI_VISION_USAGE_RECEIPT_MISSING",
        ),
    ],
)
async def test_openai_failure_categories_are_distinct_and_secret_safe(
    tmp_path: Path,
    response_factory,
    category: str,
    code: str,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        response = response_factory()
        response.headers["x-request-id"] = "req_failure_contract"
        return response

    adapter, _, _ = provider(handler)
    source = tmp_path / f"{category}.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(OpenAIVisionResponseError) as failed:
        await analyze(adapter, source)

    evidence = failed.value.error_evidence
    assert evidence.category == category
    assert evidence.code == code
    assert evidence.provider_request_id == "req_failure_contract"
    assert evidence.secret_recorded is False
    assert "contract-test-credential" not in json.dumps(evidence.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_openai_vision_maps_transport_timeout_for_central_retry(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("contract timeout", request=request)

    adapter, _, _ = provider(handler)
    source = tmp_path / "owned.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    with pytest.raises(ProviderTimeoutError) as timed_out:
        await analyze(adapter, source)
    assert timed_out.value.error_evidence is not None
    assert timed_out.value.error_evidence.category == "transport_timeout"
    assert timed_out.value.error_evidence.code == "OPENAI_VISION_TIMEOUT"
    assert str(timed_out.value.error_evidence.client_request_id).startswith("vf-")
    assert timed_out.value.error_evidence.timeout_phase == "http_response_wait"
    assert timed_out.value.error_evidence.timeout_kind == "read"
    assert timed_out.value.error_evidence.request_dispatch_state == "possibly_sent"
    assert timed_out.value.error_evidence.exception_chain == ("ReadTimeout",)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("virtual_delay_seconds", "expect_timeout"),
    [(59.0, False), (60.0, True), (61.0, True)],
)
async def test_openai_vision_virtual_59_60_61_second_boundary_without_wall_clock_wait(
    tmp_path: Path,
    virtual_delay_seconds: float,
    expect_timeout: bool,
) -> None:
    clock = VirtualMonotonic()
    transport = VirtualDelayTransport(
        clock=clock,
        delay_seconds=virtual_delay_seconds,
        timeout_seconds=60.0,
    )
    adapter, resolver, _ = provider(
        transport=transport,
        timeout_seconds=60.0,
        monotonic_clock=clock,
    )
    source = tmp_path / f"virtual-{int(virtual_delay_seconds)}.jpg"
    source.write_bytes(b"trusted-input-placeholder")

    if not expect_timeout:
        result = await analyze(adapter, source)
        assert result.provenance["latency_ms"] == 59_000.0
        assert result.provenance["provider_request_id"] == "req_virtual_delay"
    else:
        with pytest.raises(ProviderTimeoutError) as timed_out:
            await analyze(adapter, source)
        evidence = timed_out.value.error_evidence
        assert evidence is not None
        assert evidence.timeout_phase == "http_response_read"
        assert evidence.timeout_kind == "read"
        assert evidence.configured_timeout_seconds == 60.0
        assert evidence.elapsed_ms == virtual_delay_seconds * 1000
        assert evidence.request_dispatch_state == "response_headers_received"
        assert evidence.provider_request_id == "req_virtual_delay"
        assert evidence.exception_chain == ("ReadTimeout",)

    assert transport.calls == 1
    assert resolver.calls == 1


@pytest.mark.asyncio
async def test_controller_envelope_timeout_keeps_phase_evidence_and_never_retries() -> None:
    controller = ProviderSafetyController(
        approved_policy(max_attempts=1, per_request_timeout=0.01)
    )
    trace = ProviderExecutionTrace()
    calls = 0

    async def waits_after_dispatch() -> str:
        nonlocal calls
        calls += 1
        trace.begin()
        trace.mark(
            "http_response_wait",
            dispatch_state="possibly_sent",
            client_request_id="vf-controller-timeout",
        )
        await asyncio.Event().wait()
        return "unreachable"

    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await controller.execute(
            context("controller-envelope-timeout", provider(lambda _request: None)[0]),
            waits_after_dispatch,
            timeout_evidence_factory=lambda timeout_seconds, error: trace.timeout_evidence(
                code="PROVIDER_TIMEOUT",
                timeout_kind="controller_envelope",
                configured_timeout_seconds=timeout_seconds,
                error=error,
                retryable=True,
                provider_error_message="Vision provider operation exceeded controller deadline",
            ),
        )

    evidence = blocked.value.error_evidence
    assert blocked.value.code == "PROVIDER_TIMEOUT"
    assert evidence is not None
    assert evidence.timeout_phase == "http_response_wait"
    assert evidence.timeout_kind == "controller_envelope"
    assert evidence.request_dispatch_state == "possibly_sent"
    assert evidence.client_request_id == "vf-controller-timeout"
    assert evidence.provider_request_id is None
    assert evidence.retryable is False
    assert calls == 1
    assert len(controller.attempts) == 1
    assert controller.attempts[0].retryable is False
    assert controller.attempts[0].error_evidence == evidence


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
