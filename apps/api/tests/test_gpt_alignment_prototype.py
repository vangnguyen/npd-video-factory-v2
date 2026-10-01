from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from app.auto_edit_providers import (
    MediaSignals,
    PositiveDurationTranscript,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)
from app.auto_edit_logic import build_scenes
from app.config import Settings
from app.gpt_alignment_prototype import (
    ALIGNER_ENGINE_STATUS,
    GPT_ALIGNMENT_LIVE_EXECUTION,
    VIETNAMESE_PROVIDER_CONTRACT,
    AlignmentCandidate,
    AlignmentEngineBinding,
    DeterministicFixtureAligner,
    FlowACompatibilityAssessment,
    GptTranscribeRequestProfile,
    PronunciationLexicon,
    PronunciationLexiconEntry,
    ProviderTextProvenance,
    ProviderTextResult,
    ProviderTextUsage,
    PrototypeCostContract,
    PrototypeEvidenceManifest,
    PrototypeTimeoutContract,
    build_alignment_input,
    build_request_manifest,
    canonical_sha256,
    compose_quality_gates,
    evaluate_alignment,
    evaluate_text_quality,
    lexicon_sha256,
    project_validated_derived_alignment,
    request_profile_sha256,
    require_request_profile,
    timing_source_of,
    utf8_sha256,
)


FIXTURE_PATH = (
    Path(__file__).parent
    / "fixtures"
    / "gpt_alignment"
    / "synthetic-offline-fixture.json"
)


def fixture_payload() -> dict[str, object]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def profile() -> GptTranscribeRequestProfile:
    raw = fixture_payload()["request_profile"]
    assert isinstance(raw, dict)
    return GptTranscribeRequestProfile(**raw)


def provider_result(
    *, transcript: str | None = None, profile_value: GptTranscribeRequestProfile | None = None
) -> ProviderTextResult:
    fixture = fixture_payload()
    raw = fixture["provider_text_result"]
    assert isinstance(raw, dict)
    selected_profile = profile_value or profile()
    manifest = build_request_manifest(
        asset_sha256=str(fixture["asset_sha256"]), profile=selected_profile
    )
    text = transcript or str(raw["transcript_utf8"])
    return ProviderTextResult(
        request_id=str(raw["request_id"]),
        request_sha256=str(raw["request_sha256"]),
        raw_response_sha256=str(raw["raw_response_sha256"]),
        transcript_utf8=text,
        transcript_sha256=utf8_sha256(text),
        detected_languages=tuple(raw["detected_languages"]),
        usage=ProviderTextUsage(duration_seconds=Decimal(str(raw["duration_seconds"]))),
        provider_latency_ms=Decimal(str(raw["provider_latency_ms"])),
        provider_cost_vnd=Decimal(str(raw["provider_cost_vnd"])),
        provenance=ProviderTextProvenance(
            fixture_classification="SYNTHETIC_OFFLINE_FIXTURE",
            request_profile_sha256=request_profile_sha256(selected_profile),
            request_manifest_sha256=canonical_sha256(manifest),
        ),
    )


def lexicon() -> PronunciationLexicon:
    return PronunciationLexicon(
        lexicon_id="vi-real-estate-alignment-v1",
        version=1,
        entries=tuple(
            sorted(
                (
                    PronunciationLexiconEntry(
                        term="Ngọc Phương Đông", pronunciation="ngọc phương đông"
                    ),
                    PronunciationLexiconEntry(
                        term="Vinhomes Green Paradise",
                        pronunciation="vin-hôm grin pa-ra-đai",
                    ),
                    PronunciationLexiconEntry(
                        term="Cần Giờ", pronunciation="cần giờ"
                    ),
                    PronunciationLexiconEntry(
                        term="chính sách bán hàng", pronunciation="chính sách bán hàng"
                    ),
                ),
                key=lambda item: item.term.casefold(),
            )
        ),
    )


def engine() -> AlignmentEngineBinding:
    return AlignmentEngineBinding(
        status="DETERMINISTIC_TEST_FIXTURE",
        implementation_id="deterministic-fixture-aligner-v1",
        implementation_version_sha256="d" * 64,
        model_identity="synthetic-fixture-no-model",
        model_sha256=None,
        configuration_sha256="e" * 64,
        software_license_status="IN_REPO_TEST_FIXTURE",
        model_license_status="NO_EXTERNAL_MODEL",
        commercial_use_status="NOT_APPLICABLE_TEST_FIXTURE",
        redistribution_status="NOT_APPLICABLE_TEST_FIXTURE",
    )


def aligned_package(*, confidence: Decimal = Decimal("0.95")):
    fixture = fixture_payload()
    result = provider_result()
    selected_engine = engine()
    selected_lexicon = lexicon()
    alignment_input = build_alignment_input(
        audio_asset_sha256=str(fixture["asset_sha256"]),
        audio_duration_seconds=Decimal(str(fixture["audio_duration_seconds"])),
        provider_result=result,
        engine=selected_engine,
        lexicon=selected_lexicon,
    )
    starts_and_ends = tuple(
        (Decimal(index) / 2, Decimal(index) / 2 + Decimal("0.4"))
        for index in range(len(alignment_input.tokens))
    )
    adapter = DeterministicFixtureAligner(
        binding=selected_engine,
        starts_and_ends=starts_and_ends,
        confidences=(confidence,) * len(alignment_input.tokens),
    )
    candidate = adapter.align(alignment_input)
    critical_terms = tuple(fixture["critical_terms"])
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=candidate,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
        critical_terms=critical_terms,
    )
    return result, selected_engine, selected_lexicon, alignment_input, candidate, evaluation


def test_a_exact_gpt_transcribe_request_profile() -> None:
    selected = profile()
    assert selected.provider == "openai-transcription"
    assert selected.model == "gpt-transcribe"
    assert selected.capability == "asr_text"
    assert selected.languages == ("vi",)
    assert selected.provider_fields() == {
        "model": "gpt-transcribe",
        "languages": ["vi"],
        "prompt": selected.context_prompt,
        "response_format": "json",
        "keywords": list(selected.keyword_hints),
    }
    assert VIETNAMESE_PROVIDER_CONTRACT == "NOT_LIVE_VALIDATED"


def test_b_modified_request_profile_and_hidden_keyword_rejected() -> None:
    selected = profile()
    expected = request_profile_sha256(selected)
    modified = selected.model_copy(
        update={
            "context_prompt": selected.context_prompt + " hidden",
            "keyword_hints": selected.keyword_hints + ("hidden answer",),
        }
    )
    with pytest.raises(ValueError, match="GPT_TRANSCRIBE_REQUEST_PROFILE_MISMATCH"):
        require_request_profile(modified, expected_sha256=expected)
    with pytest.raises(ValidationError, match="reference_transcript"):
        GptTranscribeRequestProfile(
            **selected.model_dump(mode="json"),
            reference_transcript="hidden answer key",
        )


def test_c_timestamp_fields_forbidden_for_text_stage() -> None:
    with pytest.raises(ValidationError, match="timestamp_granularities"):
        GptTranscribeRequestProfile(
            **profile().model_dump(mode="json"),
            timestamp_granularities=["word"],
        )
    assert not {
        "timestamp_granularities",
        "timestamp_granularities[]",
    }.intersection(profile().provider_fields())


def test_d_provider_text_is_immutable_through_alignment_projection() -> None:
    result, _, _, alignment_input, candidate, evaluation = aligned_package()
    projection = project_validated_derived_alignment(
        provider_result=result,
        alignment_input=alignment_input,
        candidate=candidate,
        evaluation=evaluation,
    )
    assert projection.value.segments[0].text == result.transcript_utf8
    assert " ".join(word.text for word in projection.value.segments[0].words) == " ".join(
        token.text for token in alignment_input.tokens
    )
    assert projection.provider_transcript_sha256 == result.transcript_sha256
    assert timing_source_of(projection) == "derived_local_alignment"
    scenes = build_scenes(
        duration=30.0,
        signals=MediaSignals(
            shot_boundaries=((15.0, 0.9),),
            silence_intervals=(),
            provenance={"fixture": True},
        ),
        transcript=projection,
    )
    assert scenes
    assert "Ngọc Phương Đông" in scenes[0]["description"]


@pytest.mark.parametrize("mutation", ["insert", "delete", "substitute"])
def test_e_aligner_cannot_insert_delete_or_substitute_tokens(mutation: str) -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    tokens = list(candidate.aligned_tokens)
    if mutation == "insert":
        tokens.append(tokens[-1].model_copy(update={"index": len(tokens)}))
    elif mutation == "delete":
        tokens.pop()
    else:
        tokens[0] = tokens[0].model_copy(update={"text": "rewritten"})
    rejected = candidate.model_copy(update={"aligned_tokens": tuple(tokens)})
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert evaluation.status == "FAIL"
    assert "ALIGNMENT_TOKEN_COVERAGE_FAILED" in evaluation.failure_codes


def test_f_exact_transcript_sha_mismatch_rejected() -> None:
    raw = provider_result().model_dump(mode="json")
    raw["transcript_sha256"] = "0" * 64
    with pytest.raises(ValidationError, match="PROVIDER_TRANSCRIPT_SHA256_MISMATCH"):
        ProviderTextResult.model_validate(raw)


def test_g_exact_asset_sha_mismatch_rejected() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    tampered = alignment_input.model_copy(update={"audio_asset_sha256": "0" * 64})
    evaluation = evaluate_alignment(
        alignment_input=tampered,
        candidate=candidate,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert evaluation.status == "FAIL"
    assert "ALIGNMENT_PROVENANCE_INVALID" in evaluation.failure_codes


def test_h_zero_duration_alignment_rejected() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    first = candidate.aligned_tokens[0]
    rejected = candidate.model_copy(
        update={
            "aligned_tokens": (
                first.model_copy(update={"end_seconds": first.start_seconds}),
                *candidate.aligned_tokens[1:],
            )
        }
    )
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert "ALIGNMENT_ZERO_DURATION" in evaluation.failure_codes


def test_i_out_of_audio_timing_rejected() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    last = candidate.aligned_tokens[-1]
    rejected = candidate.model_copy(
        update={
            "aligned_tokens": (
                *candidate.aligned_tokens[:-1],
                last.model_copy(update={"end_seconds": Decimal("31")}),
            )
        }
    )
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert "ALIGNMENT_AUDIO_BOUNDS_FAILED" in evaluation.failure_codes


def test_j_non_monotonic_timing_rejected() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    second = candidate.aligned_tokens[1]
    rejected = candidate.model_copy(
        update={
            "aligned_tokens": (
                candidate.aligned_tokens[0],
                second.model_copy(update={"start_seconds": Decimal("0.1")}),
                *candidate.aligned_tokens[2:],
            )
        }
    )
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert "ALIGNMENT_NON_MONOTONIC" in evaluation.failure_codes


def test_k_incomplete_token_coverage_rejected() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    rejected = candidate.model_copy(update={"aligned_tokens": candidate.aligned_tokens[:-1]})
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert "ALIGNMENT_TOKEN_COVERAGE_FAILED" in evaluation.failure_codes


def test_l_unknown_aligner_or_model_identity_rejected() -> None:
    _, _, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    unknown = engine().model_copy(update={"model_identity": "unreviewed-production-model"})
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=candidate,
        engine=unknown,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert "ALIGNMENT_PROVENANCE_INVALID" in evaluation.failure_codes


def test_m_lexicon_mutation_rejected() -> None:
    _, selected_engine, _, alignment_input, candidate, _ = aligned_package()
    mutated = lexicon().model_copy(update={"version": 2})
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=candidate,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(mutated),
    )
    assert "ALIGNMENT_PROVENANCE_INVALID" in evaluation.failure_codes


def test_unresolved_oov_term_fails_closed() -> None:
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    rejected = candidate.model_copy(update={"unresolved_oov_token_indexes": (0,)})
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=rejected,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    assert evaluation.status == "FAIL"
    assert "ALIGNMENT_TOKEN_COVERAGE_FAILED" in evaluation.failure_codes


def test_n_low_confidence_critical_term_requires_review() -> None:
    fixture = fixture_payload()
    _, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package(
        confidence=Decimal("0.1")
    )
    evaluation = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=candidate,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
        critical_terms=tuple(fixture["critical_terms"]),
    )
    assert evaluation.status == "REVIEW_REQUIRED"
    assert "ALIGNMENT_LOW_CONFIDENCE_REVIEW_REQUIRED" in evaluation.failure_codes


def test_o_text_fail_alignment_pass_is_overall_fail() -> None:
    fixture = fixture_payload()
    _, _, _, _, _, alignment = aligned_package()
    failed_result = provider_result(
        transcript="Tư vấn bất động sản nhưng nhận dạng sai toàn bộ tên riêng."
    )
    text = evaluate_text_quality(
        result=failed_result,
        reference_transcript=str(
            fixture["provider_text_result"]["transcript_utf8"]  # type: ignore[index]
        ),
        critical_terms=tuple(fixture["critical_terms"]),
    )
    overall = compose_quality_gates(text, alignment)
    assert overall.status == "TEXT_QUALITY_FAIL"


def test_p_text_pass_alignment_fail_is_overall_fail() -> None:
    fixture = fixture_payload()
    result, selected_engine, selected_lexicon, alignment_input, candidate, _ = aligned_package()
    failed_candidate = candidate.model_copy(update={"aligned_tokens": ()})
    alignment = evaluate_alignment(
        alignment_input=alignment_input,
        candidate=failed_candidate,
        engine=selected_engine,
        expected_lexicon_sha256=lexicon_sha256(selected_lexicon),
    )
    text = evaluate_text_quality(
        result=result,
        reference_transcript=result.transcript_utf8,
        critical_terms=tuple(fixture["critical_terms"]),
    )
    assert compose_quality_gates(text, alignment).status == "ALIGNMENT_QUALITY_FAIL"


def test_q_both_pass_is_offline_candidate_only() -> None:
    fixture = fixture_payload()
    result, _, _, _, _, alignment = aligned_package()
    text = evaluate_text_quality(
        result=result,
        reference_transcript=result.transcript_utf8,
        critical_terms=tuple(fixture["critical_terms"]),
    )
    overall = compose_quality_gates(text, alignment)
    assert overall.status == "OFFLINE_COMPATIBILITY_CANDIDATE"
    assert overall.live_execution_enabled is False
    assert overall.provider_calls == overall.credential_reads == 0
    compatibility = FlowACompatibilityAssessment()
    assert compatibility.native_word_timestamps == "NO"
    assert compatibility.requires_local_alignment == "YES"
    assert compatibility.live_execution == "DISABLED"


def test_r_no_automatic_whisper_fallback_or_model_substitution() -> None:
    raw = profile().model_dump(mode="json")
    raw["model"] = "whisper-1"
    with pytest.raises(ValidationError):
        GptTranscribeRequestProfile.model_validate(raw)
    raw = profile().model_dump(mode="json")
    raw["model_fallback"] = True
    with pytest.raises(ValidationError):
        GptTranscribeRequestProfile.model_validate(raw)


def test_s_historical_provider_native_timing_classification_is_preserved() -> None:
    provider_native = PositiveDurationTranscript(
        value=ProviderTranscript(
            language="vi",
            confidence=None,
            segments=(
                ProviderSegment(
                    start_seconds=0,
                    end_seconds=1,
                    text="xin chào",
                    speaker=None,
                    confidence=None,
                    words=(
                        ProviderWord(0, 0.4, "xin", None),
                        ProviderWord(0.4, 1, "chào", None),
                    ),
                ),
            ),
            provenance={"historical_whisper": True},
        )
    )
    assert timing_source_of(provider_native) == "provider_native_word_and_segment"


def test_evidence_cost_timeout_and_live_disable_contracts() -> None:
    result, selected_engine, _, alignment_input, candidate, alignment = aligned_package()
    fixture = fixture_payload()
    text = evaluate_text_quality(
        result=result,
        reference_transcript=result.transcript_utf8,
        critical_terms=tuple(fixture["critical_terms"]),
    )
    projection = compose_quality_gates(text, alignment)
    manifest = PrototypeEvidenceManifest(
        fixture_classification="SYNTHETIC_OFFLINE_FIXTURE",
        provider_request_response_text_sha256=canonical_sha256(result),
        alignment_input_sha256=canonical_sha256(alignment_input),
        alignment_implementation_model_config_sha256=canonical_sha256(selected_engine),
        alignment_result_sha256=canonical_sha256(candidate),
        text_quality_evaluation_sha256=canonical_sha256(text),
        alignment_quality_evaluation_sha256=canonical_sha256(alignment),
        flow_a_compatibility_projection_sha256=canonical_sha256(projection),
    )
    schema_path = (
        Path(__file__).parents[3]
        / "packages"
        / "contracts"
        / "gpt-alignment-evidence.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema).validate(manifest.model_dump(mode="json"))
    assert manifest.provider_calls == manifest.credential_reads == 0
    cost = PrototypeCostContract(
        provider_cost_vnd=Decimal("244.725300"),
        local_alignment_compute_cost_vnd=None,
        total_pipeline_cost_vnd=None,
    )
    assert cost.g02_authority is False
    timeout = PrototypeTimeoutContract(
        provider_transcription_timeout_seconds=120,
        local_alignment_timeout_seconds=300,
        pipeline_hard_timeout_seconds=450,
    )
    assert timeout.provider_transcription_timeout_seconds != 90
    assert ALIGNER_ENGINE_STATUS == "ALIGNER_ENGINE_NOT_SELECTED"
    assert GPT_ALIGNMENT_LIVE_EXECUTION is False
    assert Settings(_env_file=None).gpt_alignment_live_execution_enabled is False
    with pytest.raises(ValidationError, match="GPT_ALIGNMENT_LIVE_EXECUTION_DISABLED"):
        Settings(_env_file=None, gpt_alignment_live_execution_enabled=True)
