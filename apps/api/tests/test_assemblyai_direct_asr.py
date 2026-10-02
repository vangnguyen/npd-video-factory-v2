from __future__ import annotations

import json
import copy
import hashlib
from decimal import Decimal
from pathlib import Path

import pytest

from app.assemblyai_asr_profile import (
    ASSEMBLYAI_CONTEXT_PROMPT,
    ASSEMBLYAI_CONTEXT_PROMPT_SHA256,
    ASSEMBLYAI_KEYTERMS,
    ASSEMBLYAI_KEYTERMS_SHA256,
    ASSEMBLYAI_PROFILE_ID,
    assemblyai_asr_profile,
    assemblyai_profile_sha256,
    validate_assemblyai_profile,
)
from app.assemblyai_transcription_provider import AssemblyAITranscriptionProvider
from app.asr_quality_guards import evaluate_direct_asr_quality, evaluate_prompt_insertion_guard
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import require_positive_duration_transcript
from app.config import Settings
from app.main import _provider_definitions
from app.provider_gate_loader import AssemblyAIAsrGateBundle, canonical_sha256, execution_scope_sha256
from app.provider_credentials import verify_provider_credential_binding
from app.transcription_provider_factory import create_verified_transcription_provider
from app.provider_runtime_bootstrap import OperationBinding
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key
from app.provider_secret_resolver import ResolverRequest
from test_openai_asr_gate_loader import _bundle


ASSET01_TERMS = (
    "Ngọc Phương Đông", "Vinhomes Green Paradise", "Cần Giờ", "đăng ký tư vấn",
    "tham quan sa bàn", "ngân sách dự kiến", "chính sách bán hàng", "đồng Việt Nam",
)
ASSET02_TERMS = (
    "mã chiến dịch", "nguồn liên hệ", "cơ hội bán hàng", "phạm vi được cấp quyền",
    "nhận dạng giọng nói", "không tự động gửi tin nhắn", "không tự xuất bản",
    "không thay đổi giá bán",
)


FIXTURES = Path(__file__).parent / "fixtures" / "assemblyai"


class FakeTransport:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result
        self.uploads = 0
        self.jobs = 0
        self.poll_ids: list[str] = []

    async def upload(self, audio: bytes, credential: str, timeout: float) -> str:
        self.uploads += 1
        assert credential == "test-secret" and audio == b"synthetic-wave"
        return "https://upload.invalid/opaque-token"

    async def create_transcript(self, request, credential: str, timeout: float):
        self.jobs += 1
        assert request["speech_models"] == ["universal-3-5-pro"]
        assert request["language_code"] == "vi"
        assert request["keyterms_prompt"] == list(ASSEMBLYAI_KEYTERMS)
        assert request["prompt"] == ASSEMBLYAI_CONTEXT_PROMPT
        return {"id": self.result["id"], "status": "queued"}

    async def get_transcript(self, transcript_id: str, credential: str, timeout: float):
        self.poll_ids.append(transcript_id)
        return self.result


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _provider(transport: FakeTransport) -> AssemblyAITranscriptionProvider:
    return AssemblyAITranscriptionProvider(
        model="universal-3-5-pro",
        credential_alias="secret://assemblyai/stt-video-factory-benchmark",
        credential_resolver=lambda _alias: "test-secret",
        profile=assemblyai_asr_profile(),
        transport=transport,
        poll_interval_seconds=0,
        estimated_cost_vnd=Decimal("300"),
    )


def test_assemblyai_registry_definition_remains_public_schema_compatible() -> None:
    definition = next(
        item
        for item in _provider_definitions()
        if item["provider_key"] == "assemblyai-transcription"
    )

    assert definition["status"] == "not_configured"
    assert definition["routing_mode"] == "disabled"
    assert definition["enabled"] is False
    assert definition["metadata"] == {
        "adapter_implemented": True,
        "provider_selection_benchmark": "PASS_TWO_ASSETS",
        "production_accepted": False,
        "paid": True,
        "external_execution_enabled": False,
    }


def test_profile_is_exact_and_immutable() -> None:
    profile = assemblyai_asr_profile()
    assert profile.profile_id == ASSEMBLYAI_PROFILE_ID
    assert profile.keyterms_sha256 == ASSEMBLYAI_KEYTERMS_SHA256
    assert profile.context_prompt_sha256 == ASSEMBLYAI_CONTEXT_PROMPT_SHA256
    assert profile.prompt_sha256 == ASSEMBLYAI_CONTEXT_PROMPT_SHA256
    assert len(assemblyai_profile_sha256(profile)) == 64
    changed = profile.model_dump(mode="python")
    changed["keyterms"] = (*profile.keyterms, "hidden answer")
    with pytest.raises(ValueError, match="ASSEMBLYAI_PROFILE_NOT_ALLOWLISTED"):
        validate_assemblyai_profile(changed)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("context_prompt", "modified prompt"),
        ("automatic_retry", True),
        ("model_fallback", True),
    ],
)
def test_profile_mutation_retry_and_fallback_are_rejected(field: str, value: object) -> None:
    changed = assemblyai_asr_profile().model_dump(mode="python")
    changed[field] = value
    with pytest.raises(ValueError, match="ASSEMBLYAI_PROFILE_NOT_ALLOWLISTED"):
        validate_assemblyai_profile(changed)


def test_provider_credential_mapping_rejects_cross_provider_alias() -> None:
    verify_provider_credential_binding(
        provider_key="assemblyai-transcription",
        credential_alias="secret://assemblyai/stt-video-factory-benchmark",
        systemd_credential_id="assemblyai-stt-video-factory-benchmark",
    )
    with pytest.raises(ValueError, match="PROVIDER_CREDENTIAL_ALIAS_MISMATCH"):
        verify_provider_credential_binding(
            provider_key="assemblyai-transcription",
            credential_alias="secret://openai/codex-video",
        )
    with pytest.raises(ValueError, match="PROVIDER_SYSTEMD_CREDENTIAL_ID_MISMATCH"):
        verify_provider_credential_binding(
            provider_key="assemblyai-transcription",
            credential_alias="secret://assemblyai/stt-video-factory-benchmark",
            systemd_credential_id="openai-codex-video",
        )
    with pytest.raises(ValueError):
        ResolverRequest(
            version=2,
            provider_key="assemblyai-transcription",
            credential_alias="secret://openai/codex-video",
            operation_id="operation-1",
            authority_receipt_sha256="a" * 64,
            final_bundle_sha256="b" * 64,
            execution_scope_sha256="c" * 64,
            execution_plane_promotion_sha256="d" * 64,
            o2_activation_receipt_sha256="e" * 64,
        )


@pytest.mark.asyncio
async def test_direct_adapter_preserves_positive_native_word_intervals(tmp_path: Path) -> None:
    result = _fixture("asset01.synthetic.json")
    transport = FakeTransport(result)
    provider = _provider(transport)
    audio = tmp_path / "asset.wav"
    audio.write_bytes(b"synthetic-wave")
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    callbacks: list[tuple[str, str]] = []

    async def before_send(request_sha: str, client_id: str) -> None:
        callbacks.append((request_sha, client_id))

    transcript = await provider.transcribe(
        audio,
        metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0),
        checksum_sha256=digest,
        expected_asr_prompt_profile=assemblyai_asr_profile(),
        on_http_dispatch=before_send,
    )
    assert transport.uploads == transport.jobs == 1
    assert transport.poll_ids == ["synthetic-asset01"]
    assert len(callbacks) == 1
    assert transcript.provenance["word_timing_source"] == "provider_native_word_timestamps"
    assert transcript.provenance["segment_timing_source"] == "segment_envelope_derived_from_provider_word_bounds"
    assert transcript.provenance["provider_request_id"] == "synthetic-asset01"
    assert transcript.provenance["secret_recorded"] is False
    assert len(transcript.segments[0].words) == len(result["words"])
    assert require_positive_duration_transcript(transcript).transformation_applied is False
    with pytest.raises(ValueError, match="ASSEMBLYAI_OPERATION_ALREADY_DISPATCHED"):
        await provider.transcribe(
            audio,
            metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0),
            checksum_sha256=digest,
        )


@pytest.mark.asyncio
async def test_zero_duration_and_transcript_id_substitution_fail_closed(tmp_path: Path) -> None:
    audio = tmp_path / "asset.wav"
    audio.write_bytes(b"synthetic-wave")
    digest = hashlib.sha256(audio.read_bytes()).hexdigest()
    result = _fixture("asset01.synthetic.json")
    result["words"][0]["end"] = result["words"][0]["start"]
    with pytest.raises(ValueError, match="ASSEMBLYAI_WORD_INTERVAL_INVALID"):
        await _provider(FakeTransport(result)).transcribe(
            audio, metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0), checksum_sha256=digest,
        )
    result = _fixture("asset01.synthetic.json")
    transport = FakeTransport(result)
    result["id"] = "substituted-after-ack"
    # Override acknowledgement to establish a different authorized ID.
    async def create(*_args, **_kwargs):
        return {"id": "authorized-id", "status": "queued"}
    transport.create_transcript = create
    with pytest.raises(ValueError, match="ASSEMBLYAI_TRANSCRIPT_ID_SUBSTITUTION"):
        await _provider(transport).transcribe(
            audio, metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0), checksum_sha256=digest,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("mutation", "code"),
    [
        ("negative", "ASSEMBLYAI_WORD_INTERVAL_INVALID"),
        ("non_monotonic", "ASSEMBLYAI_WORD_TIMING_NON_MONOTONIC"),
        ("out_of_audio", "ASSEMBLYAI_WORD_TIMING_OUT_OF_AUDIO"),
        ("missing_words", "ASSEMBLYAI_COMPLETE_RESULT_INCOMPLETE"),
        ("coverage", "ASSEMBLYAI_TRANSCRIPT_WORD_COVERAGE_INVALID"),
    ],
)
async def test_hostile_timing_and_incomplete_results_fail_closed(
    tmp_path: Path, mutation: str, code: str,
) -> None:
    audio = tmp_path / "asset.wav"
    audio.write_bytes(b"synthetic-wave")
    result = _fixture("asset01.synthetic.json")
    if mutation == "negative":
        result["words"][0]["start"] = -1
    elif mutation == "non_monotonic":
        result["words"][1]["start"] = result["words"][0]["end"] - 1
    elif mutation == "out_of_audio":
        result["words"][-1]["end"] = 2002
    elif mutation == "missing_words":
        result["words"] = []
    else:
        result["words"].pop()
    with pytest.raises(ValueError, match=code):
        await _provider(FakeTransport(result)).transcribe(
            audio,
            metadata=MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0),
            checksum_sha256=hashlib.sha256(audio.read_bytes()).hexdigest(),
        )


@pytest.mark.asyncio
async def test_wrong_asset_and_ambiguous_upload_or_job_never_replay(tmp_path: Path) -> None:
    audio = tmp_path / "asset.wav"
    audio.write_bytes(b"synthetic-wave")
    metadata = MediaMetadata(media_kind="audio", detected_content_type="audio/wav", duration_seconds=2.0)
    with pytest.raises(ValueError, match="ASSEMBLYAI_ASSET_HASH_MISMATCH"):
        await _provider(FakeTransport(_fixture("asset01.synthetic.json"))).transcribe(
            audio, metadata=metadata, checksum_sha256="0" * 64,
        )

    upload = FakeTransport(_fixture("asset01.synthetic.json"))
    async def ambiguous_upload(*_args, **_kwargs):
        upload.uploads += 1
        raise RuntimeError("sensitive transport detail")
    upload.upload = ambiguous_upload
    provider = _provider(upload)
    with pytest.raises(ValueError, match="ASSEMBLYAI_UPLOAD_STATE_UNCERTAIN"):
        await provider.transcribe(audio, metadata=metadata, checksum_sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
    assert upload.uploads == 1 and upload.jobs == 0
    with pytest.raises(ValueError, match="ASSEMBLYAI_OPERATION_ALREADY_DISPATCHED"):
        await provider.transcribe(audio, metadata=metadata, checksum_sha256=hashlib.sha256(audio.read_bytes()).hexdigest())

    job = FakeTransport(_fixture("asset01.synthetic.json"))
    async def ambiguous_job(*_args, **_kwargs):
        job.jobs += 1
        raise RuntimeError("sensitive transport detail")
    job.create_transcript = ambiguous_job
    provider = _provider(job)
    with pytest.raises(ValueError, match="PROVIDER_JOB_ID_UNCERTAIN"):
        await provider.transcribe(audio, metadata=metadata, checksum_sha256=hashlib.sha256(audio.read_bytes()).hexdigest())
    assert job.uploads == 1 and job.jobs == 1
    with pytest.raises(ValueError, match="ASSEMBLYAI_OPERATION_ALREADY_DISPATCHED"):
        await provider.transcribe(audio, metadata=metadata, checksum_sha256=hashlib.sha256(audio.read_bytes()).hexdigest())


def test_asset02_negative_control_is_independent_from_presence_terms() -> None:
    fixture = _fixture("asset02.synthetic.json")
    result = evaluate_prompt_insertion_guard(
        reference=fixture["text"],
        provider_transcript=fixture["text"],
        prompted_terms=ASSEMBLYAI_KEYTERMS,
    )
    assert result.passed and set(result.provider_counts.values()) == {0}
    inserted = evaluate_prompt_insertion_guard(
        reference=fixture["text"],
        provider_transcript=fixture["text"] + " Ngọc Phương Đông",
        prompted_terms=ASSEMBLYAI_KEYTERMS,
    )
    assert not inserted.passed and inserted.excess_counts["Ngọc Phương Đông"] == 1


@pytest.mark.parametrize(
    ("fixture_name", "terms", "expected_blocking_occurrences"),
    [
        ("asset01.synthetic.json", ASSET01_TERMS, 2),
        ("asset02.synthetic.json", ASSET02_TERMS, 0),
    ],
)
def test_synthetic_selection_fixtures_prove_quality_and_negative_control_shape(
    fixture_name: str, terms: tuple[str, ...], expected_blocking_occurrences: int,
) -> None:
    fixture = _fixture(fixture_name)
    text = fixture["text"]
    assert fixture["fixture_classification"] == "SYNTHETIC_OFFLINE_FIXTURE"
    assert all(term.casefold() in text.casefold() for term in terms)
    assert text.casefold().count("chính sách bán hàng") == expected_blocking_occurrences
    assert all(word["end"] > word["start"] >= 0 for word in fixture["words"])
    joined = " ".join(word["text"] for word in fixture["words"])
    from app.asr_quality_guards import _normalized_tokens
    assert _normalized_tokens(joined) == _normalized_tokens(text)


@pytest.mark.parametrize(
    ("fixture_name", "terms"),
    [("asset01.synthetic.json", ASSET01_TERMS), ("asset02.synthetic.json", ASSET02_TERMS)],
)
def test_canonical_direct_evaluator_keeps_exact_thresholds_and_negative_control(
    fixture_name: str, terms: tuple[str, ...],
) -> None:
    fixture = _fixture(fixture_name)
    result = evaluate_direct_asr_quality(
        reference=fixture["text"],
        provider_transcript=fixture["text"],
        critical_terms=terms,
        prompted_terms=ASSEMBLYAI_KEYTERMS,
    )
    assert result.passed and result.wer == 0
    assert result.critical_term_recall == 1.0
    assert result.critical_terms_passed == result.critical_terms_required == 8
    assert result.insertion_guard.passed


def test_live_assemblyai_is_disabled_by_default() -> None:
    defaults = Settings(_env_file=None)
    assert defaults.transcription_provider == "fixture"
    assert defaults.assemblyai_asr_live_execution_enabled is False
    with pytest.raises(ValueError, match="ASSEMBLYAI_ASR_LIVE_EXECUTION_ENABLED"):
        Settings(_env_file=None, transcription_provider="assemblyai")


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("model", "universal-2", "ASSEMBLYAI_MODEL_NOT_ALLOWLISTED"),
        ("language", "en", "ASSEMBLYAI_LANGUAGE_NOT_ALLOWLISTED"),
        ("credential_alias", "secret://openai/codex-video", "ASSEMBLYAI_CREDENTIAL_ALIAS_NOT_ALLOWLISTED"),
    ],
)
def test_adapter_identity_is_fail_closed(field: str, value: str, code: str) -> None:
    values = {
        "model": "universal-3-5-pro",
        "credential_alias": "secret://assemblyai/stt-video-factory-benchmark",
        "credential_resolver": lambda _alias: "test-secret",
        "profile": assemblyai_asr_profile(),
        "language": "vi",
    }
    values[field] = value
    with pytest.raises(ValueError, match=code):
        AssemblyAITranscriptionProvider(**values)


def test_provider_factory_has_no_dynamic_or_unknown_provider_escape() -> None:
    from types import SimpleNamespace
    unknown = SimpleNamespace(
        provider_key="caller-selected-class", credential_alias="secret://invalid",
        requested_language="vi", provider_http_timeout_seconds=90,
        controller_hard_timeout_seconds=180, max_file_bytes=1,
        max_duration_seconds=1, per_operation_limit_vnd=Decimal("1"),
        vnd_per_minute=Decimal("1"), asr_prompt_profile=None,
    )
    with pytest.raises(ValueError, match="PROVIDER_IMPLEMENTATION_NOT_ALLOWLISTED"):
        create_verified_transcription_provider(unknown, lambda _alias: "secret")


def test_v3_gate_binds_assemblyai_without_relabelling_historical_gate() -> None:
    historical = _bundle()
    payload = copy.deepcopy(historical.model_dump(mode="json"))
    old_scope = execution_scope_sha256(
        rc_tag=historical.rc_tag, rc_commit=historical.rc_commit,
        provider_key=historical.provider_key, model=historical.model,
        capability=historical.capability, credential_alias=historical.credential_alias,
        valid_from_utc=historical.valid_from_utc, expires_at_utc=historical.expires_at_utc,
        budget=historical.budget,
        rights_record_sha256s=tuple(item.record_sha256 for item in historical.rights_records),
        allowed_operations=historical.allowed_operations,
    )
    old_provider = canonical_sha256({
        "provider_key": historical.provider_key, "model": historical.model,
        "capability": historical.capability, "credential_alias": historical.credential_alias,
    })
    old_budget = canonical_sha256(historical.budget)
    payload.update({
        "version": 3,
        "provider_key": "assemblyai-transcription",
        "model": "universal-3-5-pro",
        "credential_alias": "secret://assemblyai/stt-video-factory-benchmark",
        "acceptance_lineage_sequence": 1,
        "asr_prompt_profile": assemblyai_asr_profile().model_dump(mode="json"),
    })
    lineage = derive_acceptance_lineage_id(
        rc_tag=historical.rc_tag, rc_commit=historical.rc_commit,
        provider_key="assemblyai-transcription", model="universal-3-5-pro",
        capability="asr", sequence=1,
    )
    payload["acceptance_lineage_id"] = lineage
    payload["budget"]["response_format"] = "json"
    payload["budget"]["timestamp_granularities"] = ["word"]
    for slot, operation in enumerate(payload["allowed_operations"], 1):
        operation["operation_key"] = derive_rc_bound_operation_key(
            rc_tag=historical.rc_tag, provider_key="assemblyai-transcription",
            capability="asr", slot=slot, acceptance_lineage_id=lineage,
        )
    new_scope = execution_scope_sha256(
        rc_tag=historical.rc_tag, rc_commit=historical.rc_commit,
        provider_key="assemblyai-transcription", model="universal-3-5-pro",
        capability="asr", credential_alias=payload["credential_alias"],
        valid_from_utc=historical.valid_from_utc, expires_at_utc=historical.expires_at_utc,
        budget=type(historical.budget).model_validate(payload["budget"]),
        rights_record_sha256s=tuple(item.record_sha256 for item in historical.rights_records),
        allowed_operations=tuple(type(historical.allowed_operations[0]).model_validate(item) for item in payload["allowed_operations"]),
        asr_prompt_profile=assemblyai_asr_profile(),
        acceptance_lineage_sequence=1, acceptance_lineage_id=lineage,
    )
    new_provider = canonical_sha256({
        "provider_key": "assemblyai-transcription", "model": "universal-3-5-pro",
        "capability": "asr", "credential_alias": payload["credential_alias"],
    })
    new_budget = canonical_sha256(type(historical.budget).model_validate(payload["budget"]))
    for key in ("credential_approval", "budget_approval", "rights_approval"):
        record = payload[key]["record"]
        record["artifact_or_commit_hashes"] = [
            {old_scope: new_scope, old_provider: new_provider, old_budget: new_budget}.get(item, item)
            for item in record["artifact_or_commit_hashes"]
        ]
        payload[key]["record_sha256"] = canonical_sha256(record)
    gate = AssemblyAIAsrGateBundle.model_validate(payload)
    assert gate.version == 3 and gate.provider_key == "assemblyai-transcription"
    assert gate.budget.timestamp_granularities == ("word",)
    historical_payload = historical.model_dump(mode="json")
    assert historical_payload["version"] == 1
    assert historical_payload["provider_key"] == "openai-transcription"


def test_operation_binding_derives_distinct_assemblyai_identity_and_alias() -> None:
    rc_tag, rc_commit = "vf-v3-01-rc27", "a" * 40
    lineage = derive_acceptance_lineage_id(
        rc_tag=rc_tag, rc_commit=rc_commit, provider_key="assemblyai-transcription",
        model="universal-3-5-pro", capability="asr", sequence=1,
    )
    operation = derive_rc_bound_operation_key(
        rc_tag=rc_tag, provider_key="assemblyai-transcription", capability="asr",
        slot=1, acceptance_lineage_id=lineage,
    )
    values = dict(
        version=2, mode="OPERATION_EXECUTION", environment="v3_01_acceptance_runtime",
        rc_tag=rc_tag, rc_commit=rc_commit, governance_main_commit="b" * 40,
        executable_tree_sha256="1" * 64, executor_executable_tree_sha256="2" * 64,
        execution_plane_promotion_sha256="3" * 64, acceptance_lineage_id=lineage,
        sequence=1, provider_key="assemblyai-transcription", model="universal-3-5-pro",
        capability="asr", language="vi",
        credential_alias="secret://assemblyai/stt-video-factory-benchmark", slot=1,
        operation_key=operation, authority_receipt_sha256="4" * 64,
        bundle_sha256="5" * 64, prepared_scope_sha256="6" * 64,
        execution_scope_sha256="7" * 64, loaded_scope_sha256="8" * 64,
        w1_profile_sha256=assemblyai_profile_sha256(),
        prompt_sha256=ASSEMBLYAI_CONTEXT_PROMPT_SHA256, asset_sha256="9" * 64,
        reference_transcript_sha256="a" * 64, rights_record_sha256="b" * 64,
    )
    binding = OperationBinding.model_validate(values)
    assert binding.operation_key != operation.replace("assemblyai", "openai")
    values["credential_alias"] = "secret://openai/codex-video"
    with pytest.raises(ValueError, match="OPERATION_BINDING_CREDENTIAL_MISMATCH"):
        OperationBinding.model_validate(values)
    values["credential_alias"] = "secret://assemblyai/stt-video-factory-benchmark"
    values["model"] = "whisper-1"
    with pytest.raises(ValueError, match="OPERATION_BINDING_PROVIDER_MODEL_MISMATCH"):
        OperationBinding.model_validate(values)
    values["model"] = "universal-3-5-pro"
    values["acceptance_lineage_id"] = "al-0001-" + "f" * 64
    with pytest.raises(ValueError, match="OPERATION_BINDING_IDENTITY_MISMATCH"):
        OperationBinding.model_validate(values)
