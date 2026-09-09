"""W1 request/provenance tests use synthetic files and mock transport only."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

import app.asr_prompt_profile as profiles
from app.asr_prompt_profile import prompt_profile_sha256, w1_prompt_profile
from app.auto_edit_models import AutoEditAnalysisRequest, MediaMetadata
from app.auto_edit_providers import (
    PositiveDurationTranscriptRequired,
    require_positive_duration_transcript,
)
from app.auto_edit_service import AutoEditAnalysisService
from app.openai_transcription_provider import (
    OpenAITranscriptionProvider,
    OpenAITranscriptionResponseError,
)


class SyntheticResolver:
    def __init__(self) -> None:
        self.calls = 0
        self.on_resolve = lambda: None

    def __call__(self, alias: str) -> str:
        assert alias == "secret://openai/w1-offline-test"
        self.calls += 1
        self.on_resolve()
        return "synthetic-contract-key"


def metadata() -> MediaMetadata:
    return MediaMetadata(
        media_kind="audio", detected_content_type="audio/mpeg", format_name="mp3",
        duration_seconds=6, audio_codec="mp3", audio_channels=1, audio_sample_rate=24000,
    )


def response_payload() -> dict:
    # Deliberately not the W1 prompt: the adapter must not correct provider text.
    return {
        "task": "transcribe", "language": "vietnamese", "duration": 4.0,
        "text": "Câu trả lời thực.",
        "segments": [{"id": 0, "start": 0.0, "end": 4.0, "text": "Câu trả lời thực."}],
        "words": [
            {"word": "Câu", "start": 0.0, "end": 0.5},
            {"word": "trả", "start": 0.5, "end": 1.0},
            {"word": "lời", "start": 1.0, "end": 1.5},
            {"word": "thực.", "start": 1.5, "end": 3.0},
        ],
    }


def make_adapter(*, w1=True, payload=None, status=200):
    requests: list[httpx.Request] = []
    responses: list[httpx.Response] = []
    resolver = SyntheticResolver()

    async def handler(request):
        requests.append(request)
        response = httpx.Response(
            status, json=response_payload() if payload is None else payload,
            headers={"x-request-id": "req_w1_offline_fixture"},
        )
        responses.append(response)
        return response

    adapter = OpenAITranscriptionProvider(
        model="whisper-1", credential_alias="secret://openai/w1-offline-test",
        credential_resolver=resolver, transport=httpx.MockTransport(handler),
        max_duration_seconds=10, estimated_cost_vnd=Decimal("10"),
        vnd_per_minute=Decimal("60"), allow_zero_cost_contract_test=True,
        asr_prompt_profile=w1_prompt_profile() if w1 else None,
    )
    return adapter, resolver, requests, responses


def source_file(tmp_path: Path, name="asset-01.mp3", content=b"synthetic-owned-audio-01"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


async def run(adapter, path, *, expected=None):
    return await adapter.transcribe(
        path, metadata=metadata(), checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        expected_asr_prompt_profile=expected,
    )


def request_hash(path, *, profile=None):
    manifest = {
        "endpoint": "/v1/audio/transcriptions", "model": "whisper-1", "language": "vi",
        "response_format": "verbose_json", "timestamp_granularities": ["segment", "word"],
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "source_bytes": path.stat().st_size, "source_duration_seconds": 6.0,
        "source_file_suffix": ".mp3", "content_type": "audio/mpeg",
    }
    if profile is not None:
        manifest["asr_prompt_profile"] = profile.model_dump(mode="json")
        manifest["asr_prompt_profile_sha256"] = prompt_profile_sha256(profile)
    return hashlib.sha256(json.dumps(
        manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


@pytest.mark.asyncio
async def test_exact_w1_multipart_request_hash_and_result_provenance(tmp_path):
    adapter, resolver, requests, responses = make_adapter()
    profile = w1_prompt_profile()
    path = source_file(tmp_path)
    result = await run(adapter, path, expected=profile)
    body = requests[0].content
    assert len(requests) == resolver.calls == 1
    assert requests[0].url == "https://api.openai.com/v1/audio/transcriptions"
    for name, value in [
        ("model", "whisper-1"), ("language", "vi"), ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "segment"), ("timestamp_granularities[]", "word"),
        ("prompt", profile.prompt),
    ]:
        assert f'name="{name}"\r\n\r\n{value}\r\n'.encode() in body
    assert body.count(b'name="prompt"') == 1
    assert b'name="temperature"' not in body
    assert result.provenance["request_sha256"] == request_hash(path, profile=profile)
    assert result.provenance["response_sha256"] == hashlib.sha256(responses[0].content).hexdigest()
    assert result.provenance["asr_prompt_profile"] == profile.model_dump(mode="json")
    assert result.provenance["asr_prompt_profile_sha256"] == prompt_profile_sha256(profile)
    assert result.provenance["provider_request_id"] == "req_w1_offline_fixture"
    assert result.segments[0].text == response_payload()["text"]
    assert [(w.text, w.start_seconds, w.end_seconds) for w in result.segments[0].words] == [
        (word["word"], word["start"], word["end"]) for word in response_payload()["words"]
    ]
    assert result.actual_cost_vnd == Decimal("4.000000")
    assert "synthetic-contract-key" not in json.dumps(result.provenance)


@pytest.mark.asyncio
async def test_w0_legacy_request_hash_and_omissions_are_unchanged(tmp_path):
    adapter, resolver, requests, _ = make_adapter(w1=False)
    path = source_file(tmp_path)
    # The legacy call signature remains valid with no expected-profile keyword.
    result = await adapter.transcribe(
        path, metadata=metadata(), checksum_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
    )
    assert len(requests) == resolver.calls == 1
    assert b'name="prompt"' not in requests[0].content
    assert b'name="temperature"' not in requests[0].content
    assert result.provenance["request_sha256"] == request_hash(path)
    assert result.provenance["request_sha256"] != request_hash(path, profile=w1_prompt_profile())
    assert "asr_prompt_profile" not in result.provenance
    assert "asr_prompt_profile_sha256" not in result.provenance


@pytest.mark.asyncio
async def test_two_assets_share_exact_w1_not_asset_specific_reference_text(tmp_path):
    adapter, _, requests, _ = make_adapter()
    profile = w1_prompt_profile()
    results = []
    for slot in (1, 2):
        path = source_file(tmp_path, f"asset-{slot}.mp3", f"synthetic-audio-{slot}".encode())
        results.append(await run(adapter, path, expected=profile))
    assert len(requests) == 2  # Two offline mock transports, never real operations.
    assert all(profile.prompt.encode() in request.content for request in requests)
    assert results[0].provenance["asr_prompt_profile"] == results[1].provenance["asr_prompt_profile"]
    assert results[0].provenance["request_sha256"] != results[1].provenance["request_sha256"]


@pytest.mark.asyncio
async def test_w1_does_not_invent_intervals_or_remove_positive_duration_boundary(tmp_path):
    payload = response_payload()
    payload["words"][1]["end"] = payload["words"][1]["start"]
    adapter, _, requests, _ = make_adapter(payload=payload)
    result = await run(adapter, source_file(tmp_path), expected=w1_prompt_profile())
    point = result.segments[0].words[1]
    assert point.start_seconds == point.end_seconds == 0.5
    assert point.text == "trả"
    assert point.timing_semantics == "provider_boundary_point"
    assert len(result.segments[0].words) == 4
    assert result.segments[0].text == payload["text"]
    with pytest.raises(PositiveDurationTranscriptRequired, match="POSITIVE_DURATION_TRANSCRIPT_REQUIRED"):
        require_positive_duration_transcript(result)
    assert len(requests) == 1


@pytest.mark.parametrize("adapter_w1,expected_w1", [(True, False), (False, True)])
@pytest.mark.asyncio
async def test_missing_or_different_profile_binding_denied_before_resolver_transport(
    tmp_path, adapter_w1, expected_w1,
):
    adapter, resolver, requests, _ = make_adapter(w1=adapter_w1)
    with pytest.raises(ValueError, match="ASR_PROMPT_PROFILE_BINDING_MISMATCH"):
        await run(adapter, source_file(tmp_path), expected=w1_prompt_profile() if expected_w1 else None)
    assert resolver.calls == 0
    assert requests == []


@pytest.mark.parametrize("side", ["expected", "adapter"])
@pytest.mark.parametrize("field,value", [
    ("prompt", "tampered public prompt"), ("prompt_sha256", "0" * 64),
    ("tokenizer_context_token_count", 32), ("temperature_policy", "zero"),
])
@pytest.mark.asyncio
async def test_copied_tampered_profile_denied_before_boundary(tmp_path, side, field, value):
    adapter, resolver, requests, _ = make_adapter()
    expected = w1_prompt_profile()
    tampered = expected.model_copy(update={field: value})
    if side == "expected":
        expected = tampered
    else:
        adapter.asr_prompt_profile = tampered
    with pytest.raises(ValueError):
        await run(adapter, source_file(tmp_path), expected=expected)
    assert resolver.calls == 0
    assert requests == []


@pytest.mark.parametrize("field,value", [
    ("model", "gpt-4o-transcribe"), ("language", "en"),
    ("response_format", "json"), ("timestamp_granularities", ("word",)),
])
@pytest.mark.asyncio
async def test_adapter_request_drift_denied_before_boundary(tmp_path, field, value):
    adapter, resolver, requests, _ = make_adapter()
    setattr(adapter, field, value)
    with pytest.raises(ValueError, match="ASR_PROMPT_PROFILE_REQUEST_MISMATCH"):
        await run(adapter, source_file(tmp_path), expected=w1_prompt_profile())
    assert resolver.calls == 0
    assert requests == []


@pytest.mark.asyncio
async def test_dispatch_uses_validated_snapshot_if_adapter_changes_during_resolution(tmp_path):
    adapter, resolver, requests, _ = make_adapter()
    profile = w1_prompt_profile()
    resolver.on_resolve = lambda: setattr(adapter, "asr_prompt_profile", None)
    path = source_file(tmp_path)
    result = await run(adapter, path, expected=profile)
    assert profile.prompt.encode() in requests[0].content
    assert result.provenance["request_sha256"] == request_hash(path, profile=profile)
    assert result.provenance["asr_prompt_profile"] == profile.model_dump(mode="json")
    with pytest.raises(ValueError, match="ASR_PROMPT_PROFILE_BINDING_MISMATCH"):
        await run(adapter, path, expected=profile)
    assert len(requests) == resolver.calls == 1


@pytest.mark.parametrize("status", [200, 400])
@pytest.mark.asyncio
async def test_post_dispatch_artifact_unavailability_cannot_destroy_result_evidence(
    tmp_path, monkeypatch, status,
):
    adapter, resolver, _, _ = make_adapter()
    profile = w1_prompt_profile()
    profile_hash = prompt_profile_sha256(profile)
    path = source_file(tmp_path)
    expected_request_hash = request_hash(path, profile=profile)
    requests = []
    responses = []
    async def handler(request):
        requests.append(request)
        # Simulate packaged-artifact unavailability after dispatch; never modify
        # the real pinned file. The completed call retains its preflight snapshot.
        monkeypatch.setattr(profiles, "_RANKS_PATH", tmp_path / "missing-tokenizer.tiktoken")
        response = httpx.Response(
            status, headers={"x-request-id": "req_w1_snapshot_fixture"},
            json=response_payload() if status == 200 else {
                "error": {"message": "Offline rejection", "type": "invalid_request_error", "code": "invalid_prompt"},
            },
        )
        responses.append(response)
        return response
    adapter._transport = httpx.MockTransport(handler)
    if status == 200:
        result = await run(adapter, path, expected=profile)
        evidence = result.provenance
        assert evidence["asr_prompt_profile_sha256"] == profile_hash
        assert evidence["asr_prompt_profile"] == profile.model_dump(mode="json")
        assert result.actual_cost_vnd == Decimal("4.000000")
    else:
        with pytest.raises(OpenAITranscriptionResponseError) as error:
            await run(adapter, path, expected=profile)
        evidence = error.value.error_evidence.model_dump(mode="json")
    assert evidence["request_sha256"] == expected_request_hash
    assert evidence["response_sha256"] == hashlib.sha256(responses[0].content).hexdigest()
    assert evidence["provider_request_id"] == "req_w1_snapshot_fixture"
    assert len(requests) == resolver.calls == 1
    assert "synthetic-contract-key" not in json.dumps(evidence)
    # Artifact failure is still fail-closed for the next preflight, not ignored.
    with pytest.raises(ValueError, match="ASR_PROMPT_TOKENIZER_ARTIFACT_UNAVAILABLE"):
        profiles.validate_prompt_profile(profile)


@pytest.mark.parametrize("status,payload", [
    (400, {"error": {"message": "Offline malformed request", "type": "invalid_request_error", "code": "invalid_prompt"}}),
    (200, {"language": "vietnamese", "duration": 4.0, "text": "x", "segments": [], "words": []}),
])
@pytest.mark.asyncio
async def test_failure_evidence_keeps_prompt_bound_request_hash_without_secret(tmp_path, status, payload):
    adapter, resolver, requests, responses = make_adapter(status=status, payload=payload)
    path = source_file(tmp_path)
    profile = w1_prompt_profile()
    with pytest.raises(OpenAITranscriptionResponseError) as error:
        await run(adapter, path, expected=profile)
    evidence = error.value.error_evidence.model_dump(mode="json")
    assert evidence["request_sha256"] == request_hash(path, profile=profile)
    assert evidence["response_sha256"] == hashlib.sha256(responses[0].content).hexdigest()
    assert evidence["provider_request_id"] == "req_w1_offline_fixture"
    assert "synthetic-contract-key" not in json.dumps(evidence)
    assert len(requests) == resolver.calls == 1


def service_fixture(tmp_path, adapter, *, cached=False):
    content = b"synthetic-owned-audio-01"
    asset = SimpleNamespace(
        asset_id="ast_owned_test01", project_id="project_offline", workspace_id="workspace_offline",
        asset_class="source", kind="video", filename="owned.mp3", object_key="offline-owned.mp3",
        checksum_sha256=hashlib.sha256(content).hexdigest(),
        provenance={"media_metadata": metadata().model_dump(mode="json")},
    )
    existing = SimpleNamespace(cached=True)
    repository = SimpleNamespace(
        get_asset=AsyncMock(return_value=asset),
        create_analysis=AsyncMock(return_value=("analysis_offline", not cached)),
        get_analysis=AsyncMock(return_value=existing), mark_analysis_running=AsyncMock(),
        mark_analysis_failed=AsyncMock(),
    )
    async def download(*, object_key, destination):
        assert object_key == "offline-owned.mp3"
        destination.write_bytes(content)
    safety = SimpleNamespace(execute=AsyncMock())
    service = AutoEditAnalysisService(
        repository=repository, platform=SimpleNamespace(),
        object_storage=SimpleNamespace(download_file=download),
        transcription_provider=adapter,
        signal_provider=SimpleNamespace(key="offline-signals", analyze=AsyncMock(return_value=None)),
        staging_root=tmp_path / "staging", provider_safety=safety,
    )
    return service, repository, safety, asset


@pytest.mark.asyncio
async def test_w1_cache_fingerprint_is_distinct_while_w0_fingerprint_is_exact_legacy(tmp_path):
    payload = AutoEditAnalysisRequest(asset_id="ast_owned_test01")
    fingerprints = []
    for w1 in (False, True):
        adapter, resolver, requests, _ = make_adapter(w1=w1)
        service, repository, safety, asset = service_fixture(tmp_path, adapter, cached=True)
        assert (await service.analyze(asset.project_id, payload)).cached is True
        kwargs = repository.create_analysis.call_args.kwargs
        fingerprints.append(kwargs["fingerprint"])
        if not w1:
            legacy = {
                "asset_checksum": asset.checksum_sha256, "configuration": payload.model_dump(mode="json"),
                "transcription_provider": adapter.key, "signal_provider": "offline-signals",
                "algorithm_version": service.algorithm_version,
            }
            assert kwargs["fingerprint"] == hashlib.sha256(json.dumps(
                legacy, sort_keys=True, separators=(",", ":"),
            ).encode()).hexdigest()
            assert "asr_prompt_profile_sha256" not in kwargs["provenance"]
        else:
            assert kwargs["provenance"]["asr_prompt_profile_sha256"] == prompt_profile_sha256(w1_prompt_profile())
        assert resolver.calls == 0 and requests == []
        safety.execute.assert_not_called()
    assert fingerprints[0] != fingerprints[1]


@pytest.mark.asyncio
async def test_service_revalidates_profile_before_cache_lookup(tmp_path):
    adapter, resolver, requests, _ = make_adapter()
    service, repository, safety, asset = service_fixture(tmp_path, adapter, cached=True)
    adapter.asr_prompt_profile = adapter.asr_prompt_profile.model_copy(update={"prompt": "tampered"})
    with pytest.raises(ValueError):
        await service.analyze(asset.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id))
    repository.create_analysis.assert_not_called()
    safety.execute.assert_not_called()
    assert resolver.calls == 0 and requests == []


@pytest.mark.asyncio
async def test_service_uses_same_w1_context_and_callback_snapshot(tmp_path):
    class OfflineStopped(RuntimeError):
        pass
    adapter, resolver, requests, _ = make_adapter()
    service, _, safety, asset = service_fixture(tmp_path, adapter)
    replacement = SimpleNamespace(transcribe=AsyncMock())
    captured = []
    async def execute(context, operation, **kwargs):
        service.transcription_provider = replacement
        result = await operation()
        captured.append((context, result))
        raise OfflineStopped("stop after offline provider result, before persistence")
    safety.execute.side_effect = execute
    with pytest.raises(OfflineStopped):
        await service.analyze(asset.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id))
    context, result = captured[0]
    assert context.asr_prompt_profile == w1_prompt_profile()
    assert result.provenance["asr_prompt_profile"] == context.asr_prompt_profile.model_dump(mode="json")
    assert result.provenance["asr_prompt_profile_sha256"] == prompt_profile_sha256(context.asr_prompt_profile)
    assert len(requests) == resolver.calls == 1
    replacement.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_service_profile_snapshot_cannot_drift_before_callback(tmp_path):
    adapter, resolver, requests, _ = make_adapter()
    service, repository, safety, asset = service_fixture(tmp_path, adapter)
    captured = []
    async def execute(context, operation, **kwargs):
        captured.append(context)
        adapter.asr_prompt_profile = None
        return await operation()
    safety.execute.side_effect = execute
    with pytest.raises(ValueError, match="ASR_PROMPT_PROFILE_BINDING_MISMATCH"):
        await service.analyze(asset.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id))
    assert captured[0].asr_prompt_profile == w1_prompt_profile()
    assert resolver.calls == 0 and requests == []
    repository.mark_analysis_failed.assert_awaited_once_with("analysis_offline", "AUTO_EDIT_ANALYSIS_FAILED")


@pytest.mark.asyncio
async def test_service_freezes_provider_instance_and_does_not_add_fixture_kwargs(tmp_path):
    class OfflineStopped(RuntimeError):
        pass
    class LegacyFixture:
        key = "fixture-transcription"
        model = "offline-model"
        external_call = False
        paid = False
        credential_alias = None
        estimated_cost_vnd = Decimal("0")
        calls = 0
        async def transcribe(self, path, *, metadata, checksum_sha256, execution_trace):
            self.calls += 1
            raise OfflineStopped("offline fixture stop")
    fixture = LegacyFixture()
    service, _, safety, asset = service_fixture(tmp_path, fixture)
    replacement = SimpleNamespace(transcribe=AsyncMock())
    async def execute(context, operation, **kwargs):
        assert context.asr_prompt_profile is None
        service.transcription_provider = replacement
        return await operation()
    safety.execute.side_effect = execute
    with pytest.raises(OfflineStopped):
        await service.analyze(asset.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id))
    assert fixture.calls == 1
    replacement.transcribe.assert_not_called()
