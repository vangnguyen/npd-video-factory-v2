#!/usr/bin/env python3
"""Offline, secret-safe evaluator for one ASR acceptance operation.

The tool consumes an already-redacted evidence record. It cannot resolve a
credential, reserve budget, mount a gate, call a provider, deploy, publish, or
write production state. By default it writes only its JSON result to stdout.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from jsonschema import Draft202012Validator


Verdict = Literal["PASS", "REVIEW_REQUIRED", "FAIL"]
SHA256 = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class AsrEvaluationPolicy:
    maximum_wer: float = 0.15
    minimum_critical_term_recall: float = 1.0
    minimum_timestamp_token_coverage: float = 0.98
    maximum_abnormal_overlap_seconds: float = 0.05
    timestamp_duration_tolerance_seconds: float = 0.05
    maximum_duration_delta_seconds: float = 0.50
    maximum_duration_delta_percent: float = 0.50
    expected_language: str = "vi"


@dataclass(frozen=True)
class WordErrorRateResult:
    reference_words: int
    hypothesis_words: int
    edit_errors: int
    wer: float
    threshold: float
    passed: bool


@dataclass(frozen=True)
class CriticalTermResult:
    term: str
    present_in_reference: bool
    exact_match: bool
    normalized_match: bool
    passed: bool


@dataclass(frozen=True)
class TimestampResult:
    segment_count: int
    word_count: int
    invalid_windows: int
    non_monotonic_windows: int
    abnormal_overlaps: int
    maximum_overlap_seconds: float
    words_outside_segment: int
    timestamps_outside_source: int
    timestamp_token_coverage: float
    passed: bool


@dataclass(frozen=True)
class DurationParityResult:
    source_duration_seconds: float
    provider_duration_seconds: float | None
    absolute_delta_seconds: float | None
    delta_percent: float | None
    passed: bool


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _strip_punctuation(value: str) -> str:
    return "".join(
        " " if unicodedata.category(character).startswith(("P", "S")) else character
        for character in unicodedata.normalize("NFKC", value)
    )


def exact_tokens(value: str) -> list[str]:
    """Tokenize after NFKC and punctuation removal, preserving case and accents."""

    return _strip_punctuation(value).split()


def normalized_tokens(value: str) -> list[str]:
    """Tokenize after NFKC, punctuation removal, whitespace collapse, and casefold.

    Vietnamese diacritics are deliberately retained. Critical terms use the same
    tokens and are never removed from the WER input.
    """

    return _strip_punctuation(value).casefold().split()


def _contains_phrase(tokens: list[str], phrase: list[str]) -> bool:
    if not phrase or len(phrase) > len(tokens):
        return False
    return any(tokens[index : index + len(phrase)] == phrase for index in range(len(tokens) - len(phrase) + 1))


def _edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for row, expected in enumerate(reference, start=1):
        current = [row]
        for column, actual in enumerate(hypothesis, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected != actual),
                )
            )
        previous = current
    return previous[-1]


def _sequence_coverage(reference: list[str], timed_words: list[str]) -> float:
    if not reference:
        return 1.0 if not timed_words else 0.0
    previous = [0] * (len(timed_words) + 1)
    for left in reference:
        current = [0]
        for index, right in enumerate(timed_words, start=1):
            if left == right:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1] / len(reference)


def _as_float(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("numeric evidence must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("numeric evidence must be finite")
    return number


def _evaluate_timestamps(
    transcript: dict[str, Any],
    *,
    source_duration: float,
    policy: AsrEvaluationPolicy,
) -> TimestampResult:
    invalid = 0
    non_monotonic = 0
    abnormal_overlaps = 0
    max_overlap = 0.0
    outside_source = 0
    words_outside_segment = 0
    timed_tokens: list[str] = []
    all_word_count = 0
    previous_segment_end = -1.0
    previous_word_end = -1.0

    segments = transcript.get("segments") or []
    for segment in segments:
        start = _as_float(segment["start_seconds"])
        end = _as_float(segment["end_seconds"])
        if start < 0 or end <= start:
            invalid += 1
        if start < previous_segment_end:
            overlap = previous_segment_end - start
            max_overlap = max(max_overlap, overlap)
            if overlap > policy.maximum_abnormal_overlap_seconds:
                abnormal_overlaps += 1
            else:
                non_monotonic += 1
        if end > source_duration + policy.timestamp_duration_tolerance_seconds:
            outside_source += 1
        previous_segment_end = max(previous_segment_end, end)

        for word in segment.get("words") or []:
            all_word_count += 1
            word_start = _as_float(word["start_seconds"])
            word_end = _as_float(word["end_seconds"])
            if word_start < 0 or word_end <= word_start:
                invalid += 1
            if word_start < previous_word_end:
                overlap = previous_word_end - word_start
                max_overlap = max(max_overlap, overlap)
                if overlap > policy.maximum_abnormal_overlap_seconds:
                    abnormal_overlaps += 1
                else:
                    non_monotonic += 1
            if word_end > source_duration + policy.timestamp_duration_tolerance_seconds:
                outside_source += 1
            if (
                word_start < start - policy.timestamp_duration_tolerance_seconds
                or word_end > end + policy.timestamp_duration_tolerance_seconds
            ):
                words_outside_segment += 1
            previous_word_end = max(previous_word_end, word_end)
            timed_tokens.extend(normalized_tokens(str(word["text"])))

    transcript_tokens = normalized_tokens(str(transcript.get("text") or ""))
    coverage = _sequence_coverage(transcript_tokens, timed_tokens)
    passed = all(
        (
            bool(segments),
            all_word_count > 0,
            invalid == 0,
            non_monotonic == 0,
            abnormal_overlaps == 0,
            words_outside_segment == 0,
            outside_source == 0,
            coverage >= policy.minimum_timestamp_token_coverage,
        )
    )
    return TimestampResult(
        segment_count=len(segments),
        word_count=all_word_count,
        invalid_windows=invalid,
        non_monotonic_windows=non_monotonic,
        abnormal_overlaps=abnormal_overlaps,
        maximum_overlap_seconds=round(max_overlap, 6),
        words_outside_segment=words_outside_segment,
        timestamps_outside_source=outside_source,
        timestamp_token_coverage=round(coverage, 6),
        passed=passed,
    )


def _evidence_completeness(payload: dict[str, Any]) -> tuple[dict[str, bool], list[str], list[str]]:
    operation = payload["operation"]
    transcript = payload.get("provider_transcript") or {}
    provenance = transcript.get("provenance") or {}
    receipts = payload["receipts"]
    ledger = receipts["ledger"]
    circuit = receipts["circuit"]
    secret_scan = receipts["secret_scan"]

    checks = {
        "provider_request_id": bool(provenance.get("provider_request_id")),
        "request_sha256": bool(SHA256.fullmatch(str(provenance.get("request_sha256") or ""))),
        "response_sha256": bool(SHA256.fullmatch(str(provenance.get("response_sha256") or ""))),
        "usage_or_duration_receipt": receipts["usage_or_duration_receipt_present"] is True,
        "cost_receipt": receipts["cost_receipt_present"] is True and transcript.get("actual_cost_vnd") is not None,
        "latency": isinstance(provenance.get("latency_ms"), (int, float)) and not isinstance(provenance.get("latency_ms"), bool),
        "circuit": circuit["state"] == "closed" and circuit["consecutive_failures"] == 0,
        "ledger": (
            ledger["operations"] == 1
            and ledger["attempts"] == 1
            and ledger["budget_days"] == 1
            and ledger["circuits"] == 1
            and operation["consumed"] is True
            and operation["status"] == "SUCCEEDED"
        ),
        "duplicate_protection": receipts["duplicate_protection"] == "DUPLICATE_OPERATION_BLOCKED",
        "secret_scan": secret_scan["status"] == "PASS" and secret_scan["finding_count"] == 0,
        "evidence_sha256": bool(SHA256.fullmatch(str(receipts.get("evidence_sha256") or ""))),
        "original_provenance": provenance.get("original_evidence") is True and provenance.get("secret_recorded") is False,
        "single_attempt": operation["attempts"] == 1 and operation["retry_count"] == 0 and operation["fallback_count"] == 0,
        "reservation_reconciled": receipts["post_reconciliation_reserved_vnd"] == "0",
    }
    review_reasons = [f"EVIDENCE_MISSING_OR_INVALID:{name.upper()}" for name, passed in checks.items() if not passed]
    fail_reasons: list[str] = []
    if not checks["secret_scan"] or provenance.get("secret_recorded") is True:
        fail_reasons.append("SECRET_CONTAINMENT_FAILED")
    if operation["attempts"] > 1 or operation["retry_count"] or operation["fallback_count"]:
        fail_reasons.append("SINGLE_ATTEMPT_CONTRACT_VIOLATED")
    if (
        operation["provider_execution"] == "SUCCESS"
        and operation["status"] != "SUCCEEDED"
    ) or (
        operation["provider_execution"] != "SUCCESS"
        and operation["status"] == "SUCCEEDED"
    ) or (
        operation["consumed"] is False
        and (ledger["operations"] or ledger["attempts"])
    ):
        fail_reasons.append("OPERATION_LEDGER_STATE_CONTRADICTORY")
    return checks, review_reasons, fail_reasons


def evaluate(payload: dict[str, Any], policy: AsrEvaluationPolicy | None = None) -> dict[str, Any]:
    policy = policy or AsrEvaluationPolicy()
    fail_reasons: list[str] = []
    review_reasons: list[str] = []

    operation = payload["operation"]
    binding = payload["binding"]
    reference = payload["reference"]
    transcript = payload.get("provider_transcript")
    evidence_checks, evidence_review, evidence_fail = _evidence_completeness(payload)
    review_reasons.extend(evidence_review)
    fail_reasons.extend(evidence_fail)

    if operation["provider_execution"] != "SUCCESS":
        review_reasons.append("PROVIDER_EXECUTION_NOT_SUCCESS")
    if transcript is None:
        review_reasons.append("PROVIDER_TRANSCRIPT_UNAVAILABLE")
        wer_result = None
        term_results: list[CriticalTermResult] = []
        timestamp_result = None
        duration_result = DurationParityResult(
            source_duration_seconds=float(binding["asset_duration_seconds"]),
            provider_duration_seconds=None,
            absolute_delta_seconds=None,
            delta_percent=None,
            passed=False,
        )
        language_result = {"expected": policy.expected_language, "actual": None, "passed": False}
        mapping_checks = {"complete": False, "nullable_confidence_preserved": False}
    else:
        reference_words = normalized_tokens(reference["transcript"])
        hypothesis_words = normalized_tokens(transcript["text"])
        errors = _edit_distance(reference_words, hypothesis_words)
        wer = 0.0 if not reference_words and not hypothesis_words else (
            1.0 if not reference_words else errors / len(reference_words)
        )
        wer_result = WordErrorRateResult(
            reference_words=len(reference_words),
            hypothesis_words=len(hypothesis_words),
            edit_errors=errors,
            wer=round(wer, 6),
            threshold=policy.maximum_wer,
            passed=wer <= policy.maximum_wer,
        )
        if not wer_result.passed:
            fail_reasons.append("WER_EXCEEDS_0_15")

        hypothesis_exact = exact_tokens(transcript["text"])
        hypothesis_normalized = normalized_tokens(transcript["text"])
        reference_normalized = normalized_tokens(reference["transcript"])
        term_results = []
        seen_terms: set[tuple[str, ...]] = set()
        for term in reference["critical_terms"]:
            normalized_term = normalized_tokens(term)
            term_key = tuple(normalized_term)
            present_in_reference = _contains_phrase(reference_normalized, normalized_term)
            exact_match = _contains_phrase(hypothesis_exact, exact_tokens(term))
            normalized_match = _contains_phrase(hypothesis_normalized, normalized_term)
            passed = present_in_reference and normalized_match and term_key not in seen_terms
            term_results.append(
                CriticalTermResult(
                    term=term,
                    present_in_reference=present_in_reference,
                    exact_match=exact_match,
                    normalized_match=normalized_match,
                    passed=passed,
                )
            )
            seen_terms.add(term_key)
        critical_recall = sum(item.passed for item in term_results) / len(term_results)
        if critical_recall < policy.minimum_critical_term_recall:
            fail_reasons.append("CRITICAL_TERM_RECALL_BELOW_1_0")
        if any(not item.present_in_reference for item in term_results):
            fail_reasons.append("CRITICAL_TERM_NOT_PRESENT_IN_REFERENCE")

        source_duration = float(binding["asset_duration_seconds"])
        provider_duration = _as_float(transcript["provider_duration_seconds"])
        duration_delta = abs(source_duration - provider_duration)
        duration_percent = duration_delta / source_duration * 100
        duration_result = DurationParityResult(
            source_duration_seconds=source_duration,
            provider_duration_seconds=provider_duration,
            absolute_delta_seconds=round(duration_delta, 6),
            delta_percent=round(duration_percent, 6),
            passed=(
                duration_delta <= policy.maximum_duration_delta_seconds
                and duration_percent <= policy.maximum_duration_delta_percent
            ),
        )
        if not duration_result.passed:
            fail_reasons.append("PROVIDER_SOURCE_DURATION_PARITY_FAILED")

        language_actual = str(transcript["language"]).strip().lower().replace("_", "-")
        language_passed = language_actual in {"vi", "vi-vn", "vietnamese", "tiếng việt"}
        language_result = {
            "expected": policy.expected_language,
            "actual": language_actual,
            "passed": language_passed,
        }
        if not language_passed:
            fail_reasons.append("LANGUAGE_MISMATCH")

        timestamp_result = _evaluate_timestamps(
            transcript,
            source_duration=source_duration,
            policy=policy,
        )
        if not timestamp_result.passed:
            fail_reasons.append("TIMESTAMP_CONTRACT_FAILED")

        nullable_confidence = transcript.get("confidence") is None and all(
            segment.get("confidence") is None
            and all(word.get("confidence") is None for word in segment.get("words") or [])
            for segment in transcript.get("segments") or []
        )
        mapping_checks = {
            "text": bool(str(transcript.get("text") or "").strip()),
            "segments": bool(transcript.get("segments")),
            "words": bool(timestamp_result.word_count),
            "language": bool(transcript.get("language")),
            "nullable_confidence_preserved": nullable_confidence,
            "provenance": bool(transcript.get("provenance")),
            "actual_cost": transcript.get("actual_cost_vnd") is not None,
            "request_id": bool((transcript.get("provenance") or {}).get("provider_request_id")),
        }
        mapping_checks["complete"] = all(mapping_checks.values())
        if not mapping_checks["complete"]:
            review_reasons.append("PROVIDER_TRANSCRIPT_MAPPING_INCOMPLETE")

    fail_reasons = sorted(set(fail_reasons))
    review_reasons = sorted(set(review_reasons) - set(fail_reasons))
    verdict: Verdict
    if fail_reasons:
        verdict = "FAIL"
    elif review_reasons:
        verdict = "REVIEW_REQUIRED"
    else:
        verdict = "PASS"

    critical_payload = {
        "terms": [asdict(item) for item in term_results],
        "exact_recall": round(
            sum(item.exact_match and item.present_in_reference for item in term_results)
            / len(term_results),
            6,
        ) if term_results else None,
        "normalized_recall": round(
            sum(item.passed for item in term_results) / len(term_results), 6
        ) if term_results else None,
        "precision": None,
        "precision_note": "not_applicable_for_closed_expected_term_set",
        "critical_terms_included_in_wer": True,
    }
    result: dict[str, Any] = {
        "schema_version": 1,
        "record_kind": "asr_post_run_evaluation",
        "operation_id": operation["operation_id"],
        "verdict": verdict,
        "reasons": {"fail": fail_reasons, "review_required": review_reasons},
        "normalization": {
            "unicode": "NFKC",
            "case": "casefold",
            "punctuation_and_symbols": "replace_with_space",
            "whitespace": "collapse_by_tokenization",
            "vietnamese_diacritics": "preserved",
        },
        "wer": asdict(wer_result) if wer_result else None,
        "critical_terms": critical_payload,
        "timestamps": asdict(timestamp_result) if timestamp_result else None,
        "language": language_result,
        "duration_parity": asdict(duration_result),
        "provider_transcript_mapping": mapping_checks,
        "evidence_completeness": {
            "checks": evidence_checks,
            "passed": all(evidence_checks.values()),
        },
        "safety": {
            "provider_calls_performed_by_evaluator": 0,
            "credential_reads_performed_by_evaluator": 0,
            "budget_reserved_vnd_by_evaluator": "0",
            "spend_vnd_by_evaluator": "0",
            "runtime_authority_granted": False,
            "production_verdict": "NO-GO",
        },
    }
    result["evaluation_sha256"] = hashlib.sha256(canonical_json_bytes(result)).hexdigest()
    return result


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("ASR evidence input must be a JSON object")
    return value


def _validate_input(payload: dict[str, Any], schema_path: Path) -> None:
    schema = _load_json(schema_path)
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        location = "/".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"input schema validation failed at {location}: {first.message}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="redacted ASR operation evidence JSON")
    parser.add_argument("--output", type=Path, help="optional evaluation JSON path")
    parser.add_argument("--expect-verdict", choices=("PASS", "REVIEW_REQUIRED", "FAIL"))
    parser.add_argument(
        "--schema",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "schemas" / "asr-post-run-input.schema.json",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        payload = _load_json(args.input)
        _validate_input(payload, args.schema)
        result = evaluate(payload)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(json.dumps({"verdict": "FAIL", "error": type(exc).__name__}, sort_keys=True), file=sys.stderr)
        return 2
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    if args.expect_verdict and result["verdict"] != args.expect_verdict:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
