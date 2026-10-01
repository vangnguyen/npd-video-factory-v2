from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Protocol

from pydantic import ConfigDict, Field, model_validator

from .auto_edit_providers import (
    DerivedLocalAlignmentPositiveDurationTranscript,
    PositiveDurationTranscript,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)
from .models import StrictModel


SHA256_PATTERN = r"^[a-f0-9]{64}$"
GPT_ALIGNMENT_LIVE_EXECUTION = False
VIETNAMESE_PROVIDER_CONTRACT = "NOT_LIVE_VALIDATED"
ALIGNER_ENGINE_STATUS = "ALIGNER_ENGINE_NOT_SELECTED"
SYNTHETIC_FIXTURE_CLASSIFICATION = "SYNTHETIC_OFFLINE_FIXTURE"

AlignmentFailureCode = Literal[
    "ALIGNMENT_FAILED_NO_TIMED_TRANSCRIPT",
    "ALIGNMENT_TOKEN_COVERAGE_FAILED",
    "ALIGNMENT_NON_MONOTONIC",
    "ALIGNMENT_ZERO_DURATION",
    "ALIGNMENT_AUDIO_BOUNDS_FAILED",
    "ALIGNMENT_LOW_CONFIDENCE_REVIEW_REQUIRED",
    "ALIGNMENT_PROVENANCE_INVALID",
]


def canonical_json_bytes(value: object) -> bytes:
    if isinstance(value, StrictModel):
        value = value.model_dump(mode="json")
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def utf8_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class FrozenStrictModel(StrictModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GptTranscribeRequestProfile(FrozenStrictModel):
    """Immutable text-only request profile for the source prototype.

    `languages` is the current gpt-transcribe API field. The profile deliberately
    has no timestamp-granularity field and cannot select another model.
    """

    contract: Literal["gpt-transcribe-text-request-v1"] = (
        "gpt-transcribe-text-request-v1"
    )
    request_profile_id: str = Field(pattern=r"^asr-gpt-transcribe-[a-z0-9-]{1,80}$")
    provider: Literal["openai-transcription"] = "openai-transcription"
    model: Literal["gpt-transcribe"] = "gpt-transcribe"
    capability: Literal["asr_text"] = "asr_text"
    languages: tuple[Literal["vi"], ...] = ("vi",)
    language_contract_status: Literal["NOT_LIVE_VALIDATED"] = "NOT_LIVE_VALIDATED"
    context_prompt: str = Field(min_length=1, max_length=2048)
    keyword_hints: tuple[str, ...] = Field(default=(), max_length=32)
    context_source: Literal["OWNER_REVIEWED_DOMAIN_CONTEXT_NOT_REFERENCE_ANSWER_KEY"] = (
        "OWNER_REVIEWED_DOMAIN_CONTEXT_NOT_REFERENCE_ANSWER_KEY"
    )
    response_format: Literal["json"] = "json"
    automatic_retry: Literal[False] = False
    model_fallback: Literal[False] = False
    live_execution_enabled: Literal[False] = False

    @model_validator(mode="after")
    def validate_bounded_context(self) -> "GptTranscribeRequestProfile":
        if len(self.context_prompt.encode("utf-8")) > 2048:
            raise ValueError("gpt-transcribe context prompt exceeds 2048 UTF-8 bytes")
        if not self.languages:
            raise ValueError("gpt-transcribe language hints must be explicit")
        if len(set(self.keyword_hints)) != len(self.keyword_hints):
            raise ValueError("gpt-transcribe keyword hints must be unique")
        for keyword in self.keyword_hints:
            if not keyword.strip() or keyword != keyword.strip():
                raise ValueError("gpt-transcribe keyword hints must be canonical strings")
            if len(keyword.encode("utf-8")) > 160:
                raise ValueError("gpt-transcribe keyword hint exceeds 160 UTF-8 bytes")
        return self

    def provider_fields(self) -> dict[str, object]:
        fields: dict[str, object] = {
            "model": self.model,
            "languages": list(self.languages),
            "prompt": self.context_prompt,
            "response_format": self.response_format,
        }
        if self.keyword_hints:
            fields["keywords"] = list(self.keyword_hints)
        return fields


def request_profile_sha256(profile: GptTranscribeRequestProfile) -> str:
    return canonical_sha256(profile)


def require_request_profile(
    profile: GptTranscribeRequestProfile, *, expected_sha256: str
) -> GptTranscribeRequestProfile:
    if request_profile_sha256(profile) != expected_sha256:
        raise ValueError("GPT_TRANSCRIBE_REQUEST_PROFILE_MISMATCH")
    fields = profile.provider_fields()
    if "timestamp_granularities" in fields or "timestamp_granularities[]" in fields:
        raise ValueError("GPT_TRANSCRIBE_TIMESTAMP_FIELDS_FORBIDDEN")
    if profile.model != "gpt-transcribe" or profile.model_fallback:
        raise ValueError("GPT_TRANSCRIBE_MODEL_SUBSTITUTION_FORBIDDEN")
    return profile


class GptTranscribeRequestManifest(FrozenStrictModel):
    contract: Literal["gpt-transcribe-request-manifest-v1"] = (
        "gpt-transcribe-request-manifest-v1"
    )
    fixture_classification: Literal["SYNTHETIC_OFFLINE_FIXTURE"]
    asset_sha256: str = Field(pattern=SHA256_PATTERN)
    request_profile_id: str
    request_profile_sha256: str = Field(pattern=SHA256_PATTERN)
    provider_fields_sha256: str = Field(pattern=SHA256_PATTERN)
    response_format: Literal["json"] = "json"
    timestamp_fields_present: Literal[False] = False
    credential_read_performed: Literal[False] = False
    provider_call_performed: Literal[False] = False


def build_request_manifest(
    *, asset_sha256: str, profile: GptTranscribeRequestProfile
) -> GptTranscribeRequestManifest:
    profile_sha = request_profile_sha256(profile)
    require_request_profile(profile, expected_sha256=profile_sha)
    return GptTranscribeRequestManifest(
        fixture_classification=SYNTHETIC_FIXTURE_CLASSIFICATION,
        asset_sha256=asset_sha256,
        request_profile_id=profile.request_profile_id,
        request_profile_sha256=profile_sha,
        provider_fields_sha256=canonical_sha256(profile.provider_fields()),
    )


class ProviderTextUsage(FrozenStrictModel):
    duration_seconds: Decimal | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class ProviderTextProvenance(FrozenStrictModel):
    contract: Literal["gpt-transcribe-text-result-v1"] = "gpt-transcribe-text-result-v1"
    fixture_classification: Literal["SYNTHETIC_OFFLINE_FIXTURE"]
    request_profile_sha256: str = Field(pattern=SHA256_PATTERN)
    request_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    timestamp_source: Literal["none_text_only"] = "none_text_only"
    provider_native_timestamps_present: Literal[False] = False
    live_quality_evidence: Literal[False] = False


class ProviderTextResult(FrozenStrictModel):
    provider: Literal["openai-transcription"] = "openai-transcription"
    model: Literal["gpt-transcribe"] = "gpt-transcribe"
    request_id: str = Field(min_length=1, max_length=200)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    raw_response_sha256: str = Field(pattern=SHA256_PATTERN)
    transcript_utf8: str = Field(min_length=1)
    transcript_sha256: str = Field(pattern=SHA256_PATTERN)
    detected_languages: tuple[str, ...] = ()
    usage: ProviderTextUsage
    provider_latency_ms: Decimal = Field(ge=0)
    provider_cost_vnd: Decimal = Field(ge=0)
    provenance: ProviderTextProvenance

    @model_validator(mode="after")
    def validate_immutable_text(self) -> "ProviderTextResult":
        if self.transcript_sha256 != utf8_sha256(self.transcript_utf8):
            raise ValueError("PROVIDER_TRANSCRIPT_SHA256_MISMATCH")
        return self


class TranscriptToken(FrozenStrictModel):
    index: int = Field(ge=0)
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)
    text: str = Field(min_length=1)
    token_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_token(self) -> "TranscriptToken":
        if self.char_end <= self.char_start:
            raise ValueError("transcript token span must be positive")
        if self.token_sha256 != canonical_sha256(
            {"index": self.index, "text": self.text}
        ):
            raise ValueError("TRANSCRIPT_TOKEN_IDENTITY_MISMATCH")
        return self


def immutable_transcript_tokens(text: str) -> tuple[TranscriptToken, ...]:
    tokens: list[TranscriptToken] = []
    for index, match in enumerate(re.finditer(r"\S+", text, flags=re.UNICODE)):
        token_text = match.group(0)
        tokens.append(
            TranscriptToken(
                index=index,
                char_start=match.start(),
                char_end=match.end(),
                text=token_text,
                token_sha256=canonical_sha256({"index": index, "text": token_text}),
            )
        )
    if not tokens:
        raise ValueError("provider transcript has no alignable token")
    return tuple(tokens)


class PronunciationLexiconEntry(FrozenStrictModel):
    term: str = Field(min_length=1, max_length=160)
    pronunciation: str = Field(min_length=1, max_length=240)
    language: Literal["vi"] = "vi"
    purpose: Literal["ALIGNMENT_ONLY_NEVER_TEXT_REWRITE"] = (
        "ALIGNMENT_ONLY_NEVER_TEXT_REWRITE"
    )


class PronunciationLexicon(FrozenStrictModel):
    contract: Literal["governed-pronunciation-lexicon-v1"] = (
        "governed-pronunciation-lexicon-v1"
    )
    lexicon_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    version: int = Field(ge=1)
    entries: tuple[PronunciationLexiconEntry, ...] = ()
    review_status: Literal["SOURCE_PROTOTYPE_ONLY"] = "SOURCE_PROTOTYPE_ONLY"

    @model_validator(mode="after")
    def validate_entries(self) -> "PronunciationLexicon":
        terms = [entry.term for entry in self.entries]
        if terms != sorted(terms, key=str.casefold) or len(terms) != len(set(terms)):
            raise ValueError("pronunciation lexicon terms must be unique and sorted")
        return self


def lexicon_sha256(lexicon: PronunciationLexicon) -> str:
    return canonical_sha256(lexicon)


class AlignmentEngineBinding(FrozenStrictModel):
    status: Literal["ALIGNER_ENGINE_NOT_SELECTED", "DETERMINISTIC_TEST_FIXTURE"]
    implementation_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,119}$")
    implementation_version_sha256: str = Field(pattern=SHA256_PATTERN)
    model_identity: str = Field(min_length=1, max_length=200)
    model_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    configuration_sha256: str = Field(pattern=SHA256_PATTERN)
    software_license_status: Literal["NOT_SELECTED", "IN_REPO_TEST_FIXTURE"]
    model_license_status: Literal["NOT_SELECTED", "NO_EXTERNAL_MODEL"]
    commercial_use_status: Literal["NOT_REVIEWED", "NOT_APPLICABLE_TEST_FIXTURE"]
    redistribution_status: Literal["NOT_REVIEWED", "NOT_APPLICABLE_TEST_FIXTURE"]
    live_eligible: Literal[False] = False


class AlignmentInput(FrozenStrictModel):
    contract: Literal["local-alignment-input-v1"] = "local-alignment-input-v1"
    fixture_classification: Literal["SYNTHETIC_OFFLINE_FIXTURE"]
    audio_asset_sha256: str = Field(pattern=SHA256_PATTERN)
    audio_duration_seconds: Decimal = Field(gt=0)
    provider_text_result_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_transcript_sha256: str = Field(pattern=SHA256_PATTERN)
    token_sequence_sha256: str = Field(pattern=SHA256_PATTERN)
    tokens: tuple[TranscriptToken, ...] = Field(min_length=1)
    aligner_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_configuration_sha256: str = Field(pattern=SHA256_PATTERN)
    pronunciation_lexicon_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_token_sequence(self) -> "AlignmentInput":
        if [token.index for token in self.tokens] != list(range(len(self.tokens))):
            raise ValueError("alignment input token indexes must be contiguous")
        if self.token_sequence_sha256 != canonical_sha256(
            [token.model_dump(mode="json") for token in self.tokens]
        ):
            raise ValueError("ALIGNMENT_INPUT_TOKEN_SEQUENCE_MISMATCH")
        return self


def build_alignment_input(
    *,
    audio_asset_sha256: str,
    audio_duration_seconds: Decimal,
    provider_result: ProviderTextResult,
    engine: AlignmentEngineBinding,
    lexicon: PronunciationLexicon | None,
) -> AlignmentInput:
    tokens = immutable_transcript_tokens(provider_result.transcript_utf8)
    return AlignmentInput(
        fixture_classification=SYNTHETIC_FIXTURE_CLASSIFICATION,
        audio_asset_sha256=audio_asset_sha256,
        audio_duration_seconds=audio_duration_seconds,
        provider_text_result_sha256=canonical_sha256(provider_result),
        canonical_transcript_sha256=provider_result.transcript_sha256,
        token_sequence_sha256=canonical_sha256(
            [token.model_dump(mode="json") for token in tokens]
        ),
        tokens=tokens,
        aligner_binding_sha256=canonical_sha256(engine),
        alignment_configuration_sha256=engine.configuration_sha256,
        pronunciation_lexicon_sha256=(
            lexicon_sha256(lexicon) if lexicon is not None else None
        ),
    )


class AlignedToken(FrozenStrictModel):
    index: int = Field(ge=0)
    token_sha256: str = Field(pattern=SHA256_PATTERN)
    text: str = Field(min_length=1)
    start_seconds: Decimal
    end_seconds: Decimal
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


class AlignedSegment(FrozenStrictModel):
    token_start_index: int = Field(ge=0)
    token_end_index_exclusive: int = Field(gt=0)
    start_seconds: Decimal
    end_seconds: Decimal


class AlignmentProvenance(FrozenStrictModel):
    source_classification: Literal["derived_local_alignment"] = (
        "derived_local_alignment"
    )
    provider_native_timestamps: Literal[False] = False
    fixture_classification: Literal["SYNTHETIC_OFFLINE_FIXTURE"]
    alignment_input_sha256: str = Field(pattern=SHA256_PATTERN)
    audio_asset_sha256: str = Field(pattern=SHA256_PATTERN)
    canonical_transcript_sha256: str = Field(pattern=SHA256_PATTERN)
    aligner_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    aligner_implementation_id: str
    aligner_implementation_version_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_model_identity: str
    alignment_model_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    alignment_configuration_sha256: str = Field(pattern=SHA256_PATTERN)
    pronunciation_lexicon_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class AlignmentCandidate(FrozenStrictModel):
    contract: Literal["local-alignment-result-v1"] = "local-alignment-result-v1"
    canonical_transcript_sha256: str = Field(pattern=SHA256_PATTERN)
    aligned_tokens: tuple[AlignedToken, ...]
    segments: tuple[AlignedSegment, ...] = ()
    unresolved_oov_token_indexes: tuple[int, ...] = ()
    provenance: AlignmentProvenance


class AlignmentAdapter(Protocol):
    binding: AlignmentEngineBinding

    def align(self, alignment_input: AlignmentInput) -> AlignmentCandidate: ...


@dataclass(frozen=True)
class DeterministicFixtureAligner:
    """A no-model, no-network fixture aligner used only by offline tests."""

    binding: AlignmentEngineBinding
    starts_and_ends: tuple[tuple[Decimal, Decimal], ...]
    confidences: tuple[Decimal | None, ...]

    def align(self, alignment_input: AlignmentInput) -> AlignmentCandidate:
        if self.binding.status != "DETERMINISTIC_TEST_FIXTURE":
            raise ValueError("ALIGNER_ENGINE_NOT_SELECTED")
        if canonical_sha256(self.binding) != alignment_input.aligner_binding_sha256:
            raise ValueError("ALIGNMENT_PROVENANCE_INVALID")
        if len(self.starts_and_ends) != len(alignment_input.tokens):
            return AlignmentCandidate(
                canonical_transcript_sha256=alignment_input.canonical_transcript_sha256,
                aligned_tokens=(),
                provenance=_alignment_provenance(alignment_input, self.binding),
            )
        confidence_values = self.confidences or (None,) * len(alignment_input.tokens)
        if len(confidence_values) != len(alignment_input.tokens):
            raise ValueError("fixture confidence count does not match token count")
        aligned = tuple(
            AlignedToken(
                index=token.index,
                token_sha256=token.token_sha256,
                text=token.text,
                start_seconds=self.starts_and_ends[token.index][0],
                end_seconds=self.starts_and_ends[token.index][1],
                confidence=confidence_values[token.index],
            )
            for token in alignment_input.tokens
        )
        return AlignmentCandidate(
            canonical_transcript_sha256=alignment_input.canonical_transcript_sha256,
            aligned_tokens=aligned,
            provenance=_alignment_provenance(alignment_input, self.binding),
        )


def _alignment_provenance(
    alignment_input: AlignmentInput, engine: AlignmentEngineBinding
) -> AlignmentProvenance:
    return AlignmentProvenance(
        fixture_classification=SYNTHETIC_FIXTURE_CLASSIFICATION,
        alignment_input_sha256=canonical_sha256(alignment_input),
        audio_asset_sha256=alignment_input.audio_asset_sha256,
        canonical_transcript_sha256=alignment_input.canonical_transcript_sha256,
        aligner_binding_sha256=canonical_sha256(engine),
        aligner_implementation_id=engine.implementation_id,
        aligner_implementation_version_sha256=engine.implementation_version_sha256,
        alignment_model_identity=engine.model_identity,
        alignment_model_sha256=engine.model_sha256,
        alignment_configuration_sha256=engine.configuration_sha256,
        pronunciation_lexicon_sha256=alignment_input.pronunciation_lexicon_sha256,
    )


class AlignmentQualityEvaluation(FrozenStrictModel):
    status: Literal["PASS", "FAIL", "REVIEW_REQUIRED"]
    failure_codes: tuple[AlignmentFailureCode, ...] = ()
    token_count: int = Field(ge=0)
    complete_token_coverage: bool
    positive_duration: bool
    monotonic: bool
    audio_bounded: bool
    provenance_valid: bool


def _normalized_tokens(value: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return tuple(re.findall(r"\w+", normalized, flags=re.UNICODE))


def _critical_term_token_indexes(
    tokens: tuple[TranscriptToken, ...], critical_terms: tuple[str, ...]
) -> set[int]:
    normalized = [_normalized_tokens(token.text) for token in tokens]
    flattened = [parts[0] if len(parts) == 1 else " ".join(parts) for parts in normalized]
    indexes: set[int] = set()
    for term in critical_terms:
        expected = _normalized_tokens(term)
        if not expected:
            continue
        for start in range(0, len(flattened) - len(expected) + 1):
            if tuple(flattened[start : start + len(expected)]) == expected:
                indexes.update(range(start, start + len(expected)))
    return indexes


def evaluate_alignment(
    *,
    alignment_input: AlignmentInput,
    candidate: AlignmentCandidate,
    engine: AlignmentEngineBinding,
    expected_lexicon_sha256: str | None,
    critical_terms: tuple[str, ...] = (),
    minimum_critical_term_confidence: Decimal = Decimal("0.50"),
) -> AlignmentQualityEvaluation:
    failures: list[AlignmentFailureCode] = []
    provenance = candidate.provenance
    provenance_valid = all(
        (
            candidate.canonical_transcript_sha256
            == alignment_input.canonical_transcript_sha256,
            provenance.alignment_input_sha256 == canonical_sha256(alignment_input),
            provenance.audio_asset_sha256 == alignment_input.audio_asset_sha256,
            provenance.canonical_transcript_sha256
            == alignment_input.canonical_transcript_sha256,
            provenance.aligner_binding_sha256 == canonical_sha256(engine),
            provenance.aligner_implementation_id == engine.implementation_id,
            provenance.aligner_implementation_version_sha256
            == engine.implementation_version_sha256,
            provenance.alignment_model_identity == engine.model_identity,
            provenance.alignment_model_sha256 == engine.model_sha256,
            provenance.alignment_configuration_sha256
            == engine.configuration_sha256,
            provenance.pronunciation_lexicon_sha256 == expected_lexicon_sha256,
            engine.status == "DETERMINISTIC_TEST_FIXTURE",
            not engine.live_eligible,
        )
    )
    if not provenance_valid:
        failures.append("ALIGNMENT_PROVENANCE_INVALID")

    if not candidate.aligned_tokens:
        failures.append("ALIGNMENT_FAILED_NO_TIMED_TRANSCRIPT")

    complete = len(candidate.aligned_tokens) == len(alignment_input.tokens)
    if complete:
        for expected, actual in zip(
            alignment_input.tokens, candidate.aligned_tokens, strict=True
        ):
            if (
                actual.index != expected.index
                or actual.token_sha256 != expected.token_sha256
                or actual.text != expected.text
            ):
                complete = False
                break
    if not complete:
        failures.append("ALIGNMENT_TOKEN_COVERAGE_FAILED")
    if candidate.unresolved_oov_token_indexes:
        complete = False
        failures.append("ALIGNMENT_TOKEN_COVERAGE_FAILED")
        if any(
            index < 0 or index >= len(alignment_input.tokens)
            for index in candidate.unresolved_oov_token_indexes
        ):
            provenance_valid = False
            failures.append("ALIGNMENT_PROVENANCE_INVALID")

    positive = True
    monotonic = True
    audio_bounded = True
    previous_end = Decimal("0")
    for token in candidate.aligned_tokens:
        if token.end_seconds <= token.start_seconds:
            positive = False
        if token.start_seconds < previous_end:
            monotonic = False
        if (
            token.start_seconds < 0
            or token.end_seconds > alignment_input.audio_duration_seconds
        ):
            audio_bounded = False
        previous_end = max(previous_end, token.end_seconds)
    previous_segment_end = Decimal("0")
    for segment in candidate.segments:
        if segment.end_seconds <= segment.start_seconds:
            positive = False
        if segment.start_seconds < previous_segment_end:
            monotonic = False
        if (
            segment.start_seconds < 0
            or segment.end_seconds > alignment_input.audio_duration_seconds
        ):
            audio_bounded = False
        if (
            segment.token_start_index >= segment.token_end_index_exclusive
            or segment.token_end_index_exclusive > len(alignment_input.tokens)
        ):
            complete = False
            failures.append("ALIGNMENT_TOKEN_COVERAGE_FAILED")
        previous_segment_end = max(previous_segment_end, segment.end_seconds)
    if not positive:
        failures.append("ALIGNMENT_ZERO_DURATION")
    if not monotonic:
        failures.append("ALIGNMENT_NON_MONOTONIC")
    if not audio_bounded:
        failures.append("ALIGNMENT_AUDIO_BOUNDS_FAILED")

    critical_indexes = _critical_term_token_indexes(alignment_input.tokens, critical_terms)
    low_confidence = any(
        token.index in critical_indexes
        and (token.confidence is None or token.confidence < minimum_critical_term_confidence)
        for token in candidate.aligned_tokens
    )
    if low_confidence:
        failures.append("ALIGNMENT_LOW_CONFIDENCE_REVIEW_REQUIRED")

    ordered_failures = tuple(dict.fromkeys(failures))
    hard_failures = tuple(
        failure
        for failure in ordered_failures
        if failure != "ALIGNMENT_LOW_CONFIDENCE_REVIEW_REQUIRED"
    )
    if hard_failures:
        status: Literal["PASS", "FAIL", "REVIEW_REQUIRED"] = "FAIL"
    elif low_confidence:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"
    return AlignmentQualityEvaluation(
        status=status,
        failure_codes=ordered_failures,
        token_count=len(candidate.aligned_tokens),
        complete_token_coverage=complete,
        positive_duration=positive,
        monotonic=monotonic,
        audio_bounded=audio_bounded,
        provenance_valid=provenance_valid,
    )


class TextQualityEvaluation(FrozenStrictModel):
    status: Literal["PASS", "TEXT_QUALITY_FAIL"]
    word_error_rate: Decimal = Field(ge=0)
    critical_term_recall: Decimal = Field(ge=0, le=1)
    critical_terms_matched: int = Field(ge=0)
    critical_terms_total: int = Field(ge=1)
    vietnamese_diacritics_preserved: bool
    matching_policy: Literal["EXACT_CONTIGUOUS_NO_FUZZY_NO_SYNONYM_NO_ACCENT_STRIP"] = (
        "EXACT_CONTIGUOUS_NO_FUZZY_NO_SYNONYM_NO_ACCENT_STRIP"
    )


def _word_error_rate(reference: str, hypothesis: str) -> Decimal:
    expected = list(_normalized_tokens(reference))
    actual = list(_normalized_tokens(hypothesis))
    if not expected:
        return Decimal("0") if not actual else Decimal("1")
    previous = list(range(len(actual) + 1))
    for row, expected_token in enumerate(expected, start=1):
        current = [row]
        for column, actual_token in enumerate(actual, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected_token != actual_token),
                )
            )
        previous = current
    return Decimal(previous[-1]) / Decimal(len(expected))


def evaluate_text_quality(
    *,
    result: ProviderTextResult,
    reference_transcript: str,
    critical_terms: tuple[str, ...],
) -> TextQualityEvaluation:
    if not critical_terms:
        raise ValueError("text quality requires at least one critical term")
    reference = " ".join(_normalized_tokens(reference_transcript))
    hypothesis = " ".join(_normalized_tokens(result.transcript_utf8))
    matched = 0
    for term in critical_terms:
        expected_term = " ".join(_normalized_tokens(term))
        if not expected_term or expected_term not in reference:
            raise ValueError("critical term absent from exact reference transcript")
        matched += int(expected_term in hypothesis)
    recall = Decimal(matched) / Decimal(len(critical_terms))
    wer = _word_error_rate(reference_transcript, result.transcript_utf8)
    diacritics_preserved = all(
        " ".join(_normalized_tokens(term)) in hypothesis for term in critical_terms
    )
    passed = wer <= Decimal("0.15") and recall == Decimal("1") and diacritics_preserved
    return TextQualityEvaluation(
        status="PASS" if passed else "TEXT_QUALITY_FAIL",
        word_error_rate=wer.quantize(Decimal("0.000001")),
        critical_term_recall=recall,
        critical_terms_matched=matched,
        critical_terms_total=len(critical_terms),
        vietnamese_diacritics_preserved=diacritics_preserved,
    )


class PipelineQualityEvaluation(FrozenStrictModel):
    route: Literal["TEXT_PROVIDER + ALIGNMENT_PIPELINE"] = (
        "TEXT_PROVIDER + ALIGNMENT_PIPELINE"
    )
    status: Literal[
        "OFFLINE_COMPATIBILITY_CANDIDATE",
        "TEXT_QUALITY_FAIL",
        "ALIGNMENT_QUALITY_FAIL",
        "ALIGNMENT_REVIEW_REQUIRED",
    ]
    text_quality: Literal["PASS", "FAIL"]
    alignment_quality: Literal["PASS", "FAIL", "REVIEW_REQUIRED"]
    live_execution_enabled: Literal[False] = False
    provider_calls: Literal[0] = 0
    credential_reads: Literal[0] = 0


class FlowACompatibilityAssessment(FrozenStrictModel):
    route: Literal["TEXT_PROVIDER + ALIGNMENT_PIPELINE"] = (
        "TEXT_PROVIDER + ALIGNMENT_PIPELINE"
    )
    text_quality: Literal["UNKNOWN"] = "UNKNOWN"
    native_word_timestamps: Literal["NO"] = "NO"
    native_segment_timestamps: Literal["NO"] = "NO"
    requires_local_alignment: Literal["YES"] = "YES"
    positive_duration_transcript: Literal["NOT_YET_PROVEN"] = "NOT_YET_PROVEN"
    live_execution: Literal["DISABLED"] = "DISABLED"
    required_gates: tuple[
        Literal["TEXT_QUALITY_PASS"], Literal["ALIGNMENT_QUALITY_PASS"]
    ] = ("TEXT_QUALITY_PASS", "ALIGNMENT_QUALITY_PASS")


def compose_quality_gates(
    text: TextQualityEvaluation,
    alignment: AlignmentQualityEvaluation,
) -> PipelineQualityEvaluation:
    if text.status != "PASS":
        status = "TEXT_QUALITY_FAIL"
    elif alignment.status == "FAIL":
        status = "ALIGNMENT_QUALITY_FAIL"
    elif alignment.status == "REVIEW_REQUIRED":
        status = "ALIGNMENT_REVIEW_REQUIRED"
    else:
        status = "OFFLINE_COMPATIBILITY_CANDIDATE"
    return PipelineQualityEvaluation(
        status=status,
        text_quality="PASS" if text.status == "PASS" else "FAIL",
        alignment_quality=alignment.status,
    )


def project_validated_derived_alignment(
    *,
    provider_result: ProviderTextResult,
    alignment_input: AlignmentInput,
    candidate: AlignmentCandidate,
    evaluation: AlignmentQualityEvaluation,
) -> DerivedLocalAlignmentPositiveDurationTranscript:
    if evaluation.status != "PASS":
        raise ValueError("ALIGNMENT_FAILED_NO_TIMED_TRANSCRIPT")
    if provider_result.transcript_sha256 != alignment_input.canonical_transcript_sha256:
        raise ValueError("ALIGNMENT_PROVENANCE_INVALID")
    words = tuple(
        ProviderWord(
            start_seconds=float(item.start_seconds),
            end_seconds=float(item.end_seconds),
            text=item.text,
            confidence=float(item.confidence) if item.confidence is not None else None,
            timing_semantics="derived_positive_interval",
        )
        for item in candidate.aligned_tokens
    )
    segment = ProviderSegment(
        start_seconds=words[0].start_seconds,
        end_seconds=words[-1].end_seconds,
        text=provider_result.transcript_utf8,
        speaker=None,
        confidence=None,
        words=words,
    )
    transcript = ProviderTranscript(
        language=(provider_result.detected_languages[0] if provider_result.detected_languages else ""),
        confidence=None,
        segments=(segment,),
        provenance={
            "provider_transcript_text_sha256": provider_result.transcript_sha256,
            "derived_alignment_timestamps_sha256": canonical_sha256(candidate),
            "timing_source": "derived_local_alignment",
            "provider_native_timestamps": False,
        },
        actual_cost_vnd=provider_result.provider_cost_vnd,
    )
    return DerivedLocalAlignmentPositiveDurationTranscript(
        value=transcript,
        provider_transcript_sha256=provider_result.transcript_sha256,
        alignment_result_sha256=canonical_sha256(candidate),
    )


TimingSource = Literal[
    "provider_native_word_and_segment",
    "derived_from_provider_native_word_boundaries",
    "derived_local_alignment",
]


def timing_source_of(value: object) -> TimingSource:
    if isinstance(value, DerivedLocalAlignmentPositiveDurationTranscript):
        return "derived_local_alignment"
    if isinstance(value, PositiveDurationTranscript):
        return "provider_native_word_and_segment"
    if getattr(value, "timestamp_source", None) == "derived_from_provider_native_word_boundaries":
        return "derived_from_provider_native_word_boundaries"
    raise ValueError("TIMING_SOURCE_UNCLASSIFIED")


class PrototypeEvidenceManifest(FrozenStrictModel):
    contract: Literal["gpt-alignment-evidence-separation-v1"] = (
        "gpt-alignment-evidence-separation-v1"
    )
    provider_request_response_text_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_input_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_implementation_model_config_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_result_sha256: str = Field(pattern=SHA256_PATTERN)
    text_quality_evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    alignment_quality_evaluation_sha256: str = Field(pattern=SHA256_PATTERN)
    flow_a_compatibility_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    fixture_classification: Literal["SYNTHETIC_OFFLINE_FIXTURE"]
    provider_calls: Literal[0] = 0
    credential_reads: Literal[0] = 0


class PrototypeCostContract(FrozenStrictModel):
    contract: Literal["gpt-alignment-cost-v1"] = "gpt-alignment-cost-v1"
    provider_cost_vnd: Decimal = Field(ge=0)
    local_alignment_compute_cost_vnd: Decimal | None = Field(default=None, ge=0)
    total_pipeline_cost_vnd: Decimal | None = Field(default=None, ge=0)
    planning_only: Literal[True] = True
    g02_authority: Literal[False] = False

    @model_validator(mode="after")
    def validate_total(self) -> "PrototypeCostContract":
        if self.local_alignment_compute_cost_vnd is None:
            if self.total_pipeline_cost_vnd is not None:
                raise ValueError("total pipeline cost is unknown until local compute is modeled")
        elif self.total_pipeline_cost_vnd != (
            self.provider_cost_vnd + self.local_alignment_compute_cost_vnd
        ):
            raise ValueError("total pipeline cost must equal provider plus alignment compute")
        return self


class PrototypeTimeoutContract(FrozenStrictModel):
    contract: Literal["gpt-alignment-timeout-v1"] = "gpt-alignment-timeout-v1"
    provider_transcription_timeout_seconds: int = Field(gt=0)
    local_alignment_timeout_seconds: int = Field(gt=0)
    pipeline_hard_timeout_seconds: int = Field(gt=0)
    planning_only: Literal[True] = True

    @model_validator(mode="after")
    def validate_time_budget(self) -> "PrototypeTimeoutContract":
        if self.pipeline_hard_timeout_seconds <= (
            self.provider_transcription_timeout_seconds
            + self.local_alignment_timeout_seconds
        ):
            raise ValueError("pipeline timeout must include explicit orchestration headroom")
        return self
