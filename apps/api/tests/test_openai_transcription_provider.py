from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.auto_edit_models import AutoEditAnalysisRequest, MediaMetadata
from app.openai_transcription_provider import (
    OpenAITranscriptionProvider,
    OpenAITranscriptionResponseError,
    compatible_openai_asr_models,
    openai_asr_compatibility_matrix,
)
from app.provider_safety import (
    ProviderCallContext,
    ProviderExecutionTrace,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    ProviderTimeoutError,
)


class SecretResolver:
    def __init__(self, value: str = "synthetic-contract-key") -> None:
        self.value = value
        self.calls = 0

    def __call__(self, alias: str) -> str:
        assert alias == "secret://openai/asr-contract-test"
        self.calls += 1
        return self.value


def media_metadata(*, duration: float = 6.0) -> MediaMetadata:
    return MediaMetadata(
        media_kind="audio",
        detected_content_type="audio/mpeg",
        format_name="mp3",
        duration_seconds=duration,
        audio_codec="mp3",
        audio_channels=1,
        audio_sample_rate=44_100,
    )


def response_payload() -> dict[str, object]:
    return {
        "task": "transcribe",
        "language": "vietnamese",
        "duration": 4.0,
        "text": "Ngọc Phương Đông. Vị trí rất đẹp.",
        "segments": [
            {"id": 0, "start": 0.0, "end": 1.8, "text": "Ngọc Phương Đông."},
            {"id": 1, "start": 2.0, "end": 4.0, "text": "Vị trí rất đẹp."},
        ],
        "words": [
            {"word": "Ngọc", "start": 0.0, "end": 0.4},
            {"word": "Phương", "start": 0.4, "end": 0.9},
            {"word": "Đông.", "start": 0.9, "end": 1.4},
            {"word": "Vị", "start": 2.0, "end": 2.3},
            {"word": "trí", "start": 2.3, "end": 2.7},
            {"word": "rất", "start": 2.7, "end": 3.1},
            {"word": "đẹp.", "start": 3.1, "end": 3.7},
        ],
    }


def mock_transport(
    payload: object | bytes,
    *,
    status_code: int = 200,
    request_id: str | None = "req_asr_contract_001",
    calls: list[httpx.Request] | None = None,
) -> httpx.MockTransport:
    async def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        headers = {"x-request-id": request_id} if request_id is not None else {}
        if isinstance(payload, bytes):
            return httpx.Response(status_code, content=payload, headers=headers)
        return httpx.Response(status_code, json=payload, headers=headers)

    return httpx.MockTransport(handler)


def provider(
    *,
    transport: httpx.AsyncBaseTransport,
    resolver: SecretResolver | None = None,
    estimated_cost_vnd: Decimal = Decimal("10"),
    vnd_per_minute: Decimal = Decimal("60"),
    allow_zero_cost_contract_test: bool = True,
) -> tuple[OpenAITranscriptionProvider, SecretResolver]:
    secret = resolver or SecretResolver()
    return (
        OpenAITranscriptionProvider(
            model="whisper-1",
            credential_alias="secret://openai/asr-contract-test",
            credential_resolver=secret,
            transport=transport,
            max_duration_seconds=10,
            estimated_cost_vnd=estimated_cost_vnd,
            vnd_per_minute=vnd_per_minute,
            allow_zero_cost_contract_test=allow_zero_cost_contract_test,
        ),
        secret,
    )


async def transcribe(
    adapter: OpenAITranscriptionProvider,
    path: Path,
    *,
    metadata: MediaMetadata | None = None,
):
    return await adapter.transcribe(
        path,
        metadata=metadata or media_metadata(),
        checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )


def test_offline_compatibility_matrix_has_three_unapproved_candidates() -> None:
    matrix = openai_asr_compatibility_matrix()

    assert [row.model for row in matrix] == [
        "whisper-1",
        "gpt-transcribe",
        "gpt-4o-transcribe",
    ]
    assert all(row.selection_status == "PROPOSED_NOT_APPROVED" for row in matrix)
    assert all(row.live_api_calls == 0 for row in matrix)
    assert all(row.credential_reads == 0 for row in matrix)
    assert all(row.spend_vnd == 0 for row in matrix)
    assert compatible_openai_asr_models() == frozenset({"whisper-1"})
    assert matrix[0].word_timestamps == "SUPPORTED"
    assert matrix[0].strict_flow_a_compatible is True
    assert matrix[1].word_timestamps == "UNSUPPORTED"
    assert matrix[1].language == "UNRESOLVED"
    assert matrix[1].strict_flow_a_compatible is False
    assert matrix[2].word_timestamps == "UNSUPPORTED"
    assert matrix[2].strict_flow_a_compatible is False


@pytest.mark.parametrize("model", ["gpt-transcribe", "gpt-4o-transcribe"])
def test_incompatible_candidate_is_rejected_before_secret_or_transport(model: str) -> None:
    resolver = SecretResolver()
    with pytest.raises(ValueError, match="strict native timestamp contract"):
        OpenAITranscriptionProvider(
            model=model,
            credential_alias="secret://openai/asr-contract-test",
            credential_resolver=resolver,
        )
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_mock_success_maps_unicode_native_timestamps_and_cost_without_network(
    tmp_path: Path,
) -> None:
    calls: list[httpx.Request] = []
    adapter, resolver = provider(
        transport=mock_transport(response_payload(), calls=calls),
    )
    source = tmp_path / "owned-audio.mp3"
    source.write_bytes(b"offline-owned-audio-fixture")

    result = await transcribe(adapter, source)

    assert len(calls) == 1
    assert calls[0].url == "https://api.openai.com/v1/audio/transcriptions"
    assert calls[0].method == "POST"
    assert calls[0].headers["authorization"] == "Bearer synthetic-contract-key"
    assert b'filename="acceptance-input.mp3"' in calls[0].content
    assert resolver.calls == 1
    assert result.language == "vi"
    assert result.confidence is None
    assert [segment.text for segment in result.segments] == [
        "Ngọc Phương Đông.",
        "Vị trí rất đẹp.",
    ]
    assert all(segment.speaker is None for segment in result.segments)
    assert all(segment.confidence is None for segment in result.segments)
    assert all(word.confidence is None for segment in result.segments for word in segment.words)
    assert result.actual_cost_vnd == Decimal("4.000000")
    assert result.provenance["provider_request_id"] == "req_asr_contract_001"
    assert result.provenance["cost_receipt"] == {
        "currency": "VND",
        "basis": "provider_native_duration",
        "duration_seconds": "4.0",
        "vnd_per_minute": "60",
        "actual_cost_vnd": "4.000000",
        "estimated_cost_vnd": "10",
    }
    assert len(str(result.provenance["request_sha256"])) == 64
    assert len(str(result.provenance["response_sha256"])) == 64
    assert result.provenance["secret_recorded"] is False
    assert "synthetic-contract-key" not in json.dumps(result.provenance)


@pytest.mark.asyncio
async def test_canonical_request_and_response_hashes_are_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "same.mp3"
    source.write_bytes(b"same-offline-input")
    first, _ = provider(transport=mock_transport(response_payload()))
    second, _ = provider(transport=mock_transport(response_payload()))

    left = await transcribe(first, source)
    right = await transcribe(second, source)

    assert left.provenance["request_sha256"] == right.provenance["request_sha256"]
    assert left.provenance["response_sha256"] == right.provenance["response_sha256"]
    assert left.provenance["client_request_id"] != right.provenance["client_request_id"]


@pytest.mark.asyncio
async def test_zero_cost_runtime_fails_before_credential_or_transport(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    resolver = SecretResolver()
    adapter, _ = provider(
        transport=mock_transport(response_payload(), calls=calls),
        resolver=resolver,
        estimated_cost_vnd=Decimal("0"),
        vnd_per_minute=Decimal("0"),
        allow_zero_cost_contract_test=False,
    )
    source = tmp_path / "zero.mp3"
    source.write_bytes(b"offline")

    with pytest.raises(RuntimeError, match="G-02"):
        await transcribe(adapter, source)
    assert resolver.calls == 0
    assert calls == []


@pytest.mark.asyncio
async def test_default_safety_controller_blocks_before_credential_and_transport(
    tmp_path: Path,
) -> None:
    calls: list[httpx.Request] = []
    resolver = SecretResolver()
    adapter, _ = provider(
        transport=mock_transport(response_payload(), calls=calls),
        resolver=resolver,
    )
    source = tmp_path / "blocked.mp3"
    source.write_bytes(b"offline")
    checksum = hashlib.sha256(source.read_bytes()).hexdigest()
    context = ProviderCallContext(
        operation_key="v3-01-rc11-openai-transcription-asr-call-01",
        workspace_id="wsp_contract",
        project_id="prj_contract",
        provider_key=adapter.key,
        model=adapter.model,
        capability="asr",
        operation="flow_a_asr",
        external_call=True,
        paid=True,
        estimated_cost_vnd=adapter.estimated_cost_vnd,
        credential_alias=adapter.credential_alias,
        asset_id="ast_contract",
        asset_hash=checksum,
        input_media_kind="audio",
        rights_required=True,
        rights=[],
    )

    with pytest.raises(ProviderSafetyBlocked):
        await ProviderSafetyController.fail_closed().execute(
            context,
            lambda: adapter.transcribe(
                source,
                metadata=media_metadata(),
                checksum_sha256=checksum,
            ),
            actual_cost=lambda result: result.actual_cost_vnd,
        )
    assert resolver.calls == 0
    assert calls == []


@pytest.mark.asyncio
async def test_missing_alias_and_checksum_drift_fail_before_secret(tmp_path: Path) -> None:
    resolver = SecretResolver()
    adapter = OpenAITranscriptionProvider(
        model="whisper-1",
        credential_alias=None,
        credential_resolver=resolver,
        transport=mock_transport(response_payload()),
        max_duration_seconds=10,
        allow_zero_cost_contract_test=True,
    )
    source = tmp_path / "missing.mp3"
    source.write_bytes(b"offline")

    with pytest.raises(RuntimeError, match="alias"):
        await transcribe(adapter, source)
    with pytest.raises(ValueError, match="checksum mismatch"):
        await adapter.transcribe(
            source,
            metadata=media_metadata(),
            checksum_sha256="0" * 64,
        )
    assert resolver.calls == 0


@pytest.mark.asyncio
async def test_unsupported_file_extension_fails_before_secret(tmp_path: Path) -> None:
    resolver = SecretResolver()
    adapter, _ = provider(
        transport=mock_transport(response_payload()),
        resolver=resolver,
    )
    source = tmp_path / "unsupported.bin"
    source.write_bytes(b"offline")

    with pytest.raises(ValueError, match="unsupported file extension"):
        await transcribe(adapter, source)
    assert resolver.calls == 0


@pytest.mark.parametrize(
    ("mutator", "expected"),
    [
        (lambda payload: payload.pop("words"), "RESPONSE_INVALID"),
        (lambda payload: payload.update(text=""), "RESPONSE_INVALID"),
        (lambda payload: payload.update(language="english"), "RESPONSE_INVALID"),
        (
            lambda payload: payload["words"][1].update(start=0.2),
            "RESPONSE_INVALID",
        ),
        (
            lambda payload: payload["words"][-1].update(end=8.0),
            "RESPONSE_INVALID",
        ),
        (
            lambda payload: payload["segments"][1].update(start=1.0),
            "RESPONSE_INVALID",
        ),
    ],
)
@pytest.mark.asyncio
async def test_malformed_transcript_contract_is_fail_closed(
    tmp_path: Path,
    mutator,
    expected: str,
) -> None:
    payload = response_payload()
    mutator(payload)
    adapter, _ = provider(transport=mock_transport(payload))
    source = tmp_path / "invalid.mp3"
    source.write_bytes(b"offline")

    with pytest.raises(OpenAITranscriptionResponseError) as captured:
        await transcribe(adapter, source)
    assert expected in captured.value.code
    assert captured.value.error_evidence.secret_recorded is False


@pytest.mark.asyncio
async def test_invalid_json_and_missing_request_id_are_distinct(tmp_path: Path) -> None:
    source = tmp_path / "bad-json.mp3"
    source.write_bytes(b"offline")
    invalid_json, _ = provider(transport=mock_transport(b"not-json"))
    missing_id, _ = provider(
        transport=mock_transport(response_payload(), request_id=None)
    )

    with pytest.raises(OpenAITranscriptionResponseError) as invalid:
        await transcribe(invalid_json, source)
    assert invalid.value.code == "OPENAI_TRANSCRIPTION_RESPONSE_JSON_INVALID"
    with pytest.raises(OpenAITranscriptionResponseError) as missing:
        await transcribe(missing_id, source)
    assert missing.value.code == "OPENAI_TRANSCRIPTION_REQUEST_ID_MISSING"


@pytest.mark.asyncio
async def test_provider_http_error_is_redacted_and_never_retried(tmp_path: Path) -> None:
    calls: list[httpx.Request] = []
    adapter, resolver = provider(
        transport=mock_transport(
            {
                "error": {
                    "type": "invalid_request_error",
                    "code": "bad_audio",
                    "param": "file",
                    "message": "api_key=sk-never-record-this invalid audio",
                }
            },
            status_code=400,
            request_id="req_bad_audio",
            calls=calls,
        )
    )
    source = tmp_path / "bad.mp3"
    source.write_bytes(b"offline")

    with pytest.raises(OpenAITranscriptionResponseError) as captured:
        await transcribe(adapter, source)
    evidence = captured.value.error_evidence
    assert len(calls) == 1
    assert resolver.calls == 1
    assert evidence.http_status == 400
    assert evidence.provider_request_id == "req_bad_audio"
    assert "sk-never-record-this" not in json.dumps(evidence.model_dump(mode="json"))
    assert "<redacted>" in str(evidence.provider_error_message)
    assert evidence.retryable is False


@pytest.mark.asyncio
async def test_read_timeout_keeps_phase_evidence_and_has_no_adapter_retry(
    tmp_path: Path,
) -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("synthetic", request=request)

    adapter, _ = provider(transport=httpx.MockTransport(handler))
    source = tmp_path / "timeout.mp3"
    source.write_bytes(b"offline")
    trace = ProviderExecutionTrace()

    with pytest.raises(ProviderTimeoutError) as captured:
        await adapter.transcribe(
            source,
            metadata=media_metadata(),
            checksum_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
            execution_trace=trace,
        )
    evidence = captured.value.error_evidence
    assert calls == 1
    assert evidence is not None
    assert evidence.code == "PROVIDER_TIMEOUT"
    assert evidence.timeout_kind == "read"
    assert evidence.request_dispatch_state == "possibly_sent"
    assert evidence.provider_http_timeout_seconds == 90
    assert evidence.controller_hard_timeout_seconds == 120
    assert evidence.secret_recorded is False


def test_acceptance_operation_id_is_strict_and_optional() -> None:
    payload = AutoEditAnalysisRequest(asset_id="ast_contract")
    assert payload.acceptance_operation_id is None
    accepted = AutoEditAnalysisRequest(
        asset_id="ast_contract",
        acceptance_operation_id="v3-01-rc11-openai-transcription-asr-call-01",
    )
    assert accepted.acceptance_operation_id.endswith("call-01")
    with pytest.raises(ValueError):
        AutoEditAnalysisRequest(
            asset_id="ast_contract",
            acceptance_operation_id="reusable-operation",
        )
