#!/usr/bin/env python3
"""Read-only RC-15 critical-term forensics, never an acceptance override.

The classification compares recorded provider text with an exact pre-call,
owner-confirmed reference. It does not claim a new acoustic listening review.
Only JSON is emitted to stdout. No provider, credential, ledger or write API exists.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import unicodedata
from pathlib import Path
from typing import Any


SOURCE_SHA256 = {
    "operation-1-result.json": "ef06ffc48495e207ae7e827207ff67ee7b345b3323c702c1852b39a27a2d5099",
    "operation-1-evaluator-input.json": "80dfdbe7b8afe38eda7086d452e393d8893fdcca2c562174c055abe91a889474",
    "operation-1-post-run-evaluation.json": "08d71d294dc602e219d09d824c9d66e834a6c713f36f4a94368f5034598ffda9",
}
ASSET_SHA256 = "fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef"
REFERENCE_SHA256 = "585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e"
MANIFEST_SHA256 = "0d7aef962dcb5e34ed5786fadd2e9cfd156cbfb8784d498092262d33b76de7c0"
OBSERVED_VARIANTS = {
    "Vinhomes Green Paradise": ("Vinhome Bring Paradise", "ping home ring paradise"),
    "tham quan sa bàn": ("thăm quan xa bàn",),
    "chính sách bán hàng": ("chính xác bán hàng",),
}


class ForensicBindingError(ValueError):
    """Only a fixed public error code is reported; never an input value."""


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def normalized_tokens(value: str) -> list[str]:
    """Same strict policy as the evaluator; Vietnamese diacritics are retained."""
    if not isinstance(value, str):
        raise ForensicBindingError("FORENSIC_TEXT_TYPE_INVALID")
    normalized = unicodedata.normalize("NFKC", value)
    return "".join(" " if unicodedata.category(c).startswith(("P", "S")) else c for c in normalized).casefold().split()


def phrase_starts(tokens: list[str], phrase: list[str]) -> list[int]:
    if not phrase:
        return []
    return [index for index in range(len(tokens) - len(phrase) + 1) if tokens[index:index + len(phrase)] == phrase]


def diagnostic_edit_distance(expected: list[str], observed: list[str]) -> int:
    """Diagnostic only: this distance must never decide or relax acceptance."""
    row = list(range(len(observed) + 1))
    for i, token in enumerate(expected, 1):
        next_row = [i]
        for j, actual in enumerate(observed, 1):
            next_row.append(min(next_row[-1] + 1, row[j] + 1, row[j - 1] + (token != actual)))
        row = next_row
    return row[-1]


def classify(expected: str, observed: str, reference: str, *, owner_reference_verified: bool) -> str:
    """An evidence-relative diagnosis, not proof of the acoustic ground truth."""
    if not owner_reference_verified or not normalized_tokens(expected) or not normalized_tokens(observed) or not normalized_tokens(reference):
        return "UNKNOWN"
    if not phrase_starts(normalized_tokens(reference), normalized_tokens(expected)):
        return "REFERENCE_MISMATCH"
    if normalized_tokens(expected) == normalized_tokens(observed):
        return "NORMALIZATION_ONLY"
    return "PROVIDER_MISRECOGNITION"


def _load_exact(path: Path, expected: str) -> dict[str, Any]:
    raw = path.read_bytes()
    if sha256_bytes(raw) != expected:
        raise ForensicBindingError("FORENSIC_SOURCE_HASH_MISMATCH")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ForensicBindingError("FORENSIC_SOURCE_SHAPE_INVALID")
    return value


def _require(condition: bool, code: str) -> None:
    if not condition:
        raise ForensicBindingError(code)


def _flatten_words(transcript: dict[str, Any]) -> list[dict[str, Any]]:
    flattened = []
    for segment_index, segment in enumerate(transcript["segments"]):
        for word_index, word in enumerate(segment["words"]):
            flattened.append({
                "global_word_index": len(flattened),
                "segment_index": segment_index,
                "segment_word_index": word_index,
                "text": word["text"],
                "normalized_tokens": normalized_tokens(word["text"]),
                "start_seconds": word["start_seconds"],
                "end_seconds": word["end_seconds"],
                "confidence": word.get("confidence"),
            })
    return flattened


def locate_observed_phrase(transcript: dict[str, Any], phrase: str) -> list[dict[str, Any]]:
    """Locate only exact normalized occurrences; never find a fuzzy substitute."""
    words = _flatten_words(transcript)
    tokens, owners = [], []
    for index, word in enumerate(words):
        tokens.extend(word["normalized_tokens"])
        owners.extend([index] * len(word["normalized_tokens"]))
    phrase_tokens = normalized_tokens(phrase)
    matches = []
    for start in phrase_starts(tokens, phrase_tokens):
        first, last = owners[start], owners[start + len(phrase_tokens) - 1]
        selected = words[first:last + 1]
        segment_indexes = sorted({word["segment_index"] for word in selected})
        matches.append({
            "observed_phrase": " ".join(word["text"] for word in selected),
            "normalized_tokens": tokens[start:start + len(phrase_tokens)],
            "global_word_indexes": list(range(first, last + 1)),
            "segment_indexes": segment_indexes,
            "segments": [
                {"segment_index": index, "text": transcript["segments"][index]["text"],
                 "start_seconds": transcript["segments"][index]["start_seconds"],
                 "end_seconds": transcript["segments"][index]["end_seconds"],
                 "confidence": transcript["segments"][index].get("confidence")}
                for index in segment_indexes
            ],
            "words": selected,
            "start_seconds": selected[0]["start_seconds"],
            "end_seconds": selected[-1]["end_seconds"],
            "previous_word": words[first - 1] if first else None,
            "next_word": words[last + 1] if last + 1 < len(words) else None,
            "timestamp_provenance": "verbatim recorded ProviderTranscript values; raw response evidence is not rewritten",
        })
    return matches


def build_report(repo: Path) -> dict[str, Any]:
    root = repo / "docs" / "acceptance" / "v3-01"
    evidence = root / "evidence" / "rc15-asr-operation-1"
    source = {name: _load_exact(evidence / name, checksum) for name, checksum in SOURCE_SHA256.items()}
    receipt = source["operation-1-result.json"]
    evaluator_input = source["operation-1-evaluator-input.json"]
    evaluation = source["operation-1-post-run-evaluation.json"]
    manifest = _load_exact(root / "assets" / "V3-01-RC11-ASR-ASSET-MANIFEST.json", MANIFEST_SHA256)
    asset = next(item for item in manifest["assets"] if item["slot"] == 1)
    reference_raw = (repo / asset["reference_transcript_path"]).read_bytes()
    _require(sha256_bytes(reference_raw) == REFERENCE_SHA256 == asset["reference_transcript_sha256"], "FORENSIC_REFERENCE_HASH_MISMATCH")
    _require(sha256_bytes((repo / asset["path"]).read_bytes()) == ASSET_SHA256 == asset["sha256"], "FORENSIC_ASSET_HASH_MISMATCH")
    reference = reference_raw.decode("utf-8")
    confirmation = manifest["owner_confirmation"]
    _require(confirmation["decision"] == "APPROVED" and confirmation["content_matches_reference_transcript"] is True and confirmation["voice_processing_consent"] is True, "FORENSIC_OWNER_REFERENCE_UNVERIFIED")
    _require(confirmation["recorded_at_utc"] < receipt["started_at_utc"], "FORENSIC_REFERENCE_NOT_PRECALL")
    # The recorded evaluator input omits the source file's final LF only.
    # Verify that exact representation difference without changing any word.
    _require(evaluator_input["reference"]["transcript"] == reference.removesuffix("\n") and evaluator_input["reference"]["transcript_sha256"] == REFERENCE_SHA256, "FORENSIC_REFERENCE_MISMATCH")
    _require(receipt["binding"]["asset_sha256"] == ASSET_SHA256 and receipt["binding"]["reference_transcript_sha256"] == REFERENCE_SHA256, "FORENSIC_RECEIPT_BINDING_MISMATCH")
    _require(receipt["evaluation_input"]["file_sha256"] == SOURCE_SHA256["operation-1-evaluator-input.json"] and receipt["post_run_evaluation"]["file_sha256"] == SOURCE_SHA256["operation-1-post-run-evaluation.json"], "FORENSIC_DERIVED_RECEIPT_MISMATCH")
    transcript = evaluator_input["provider_transcript"]
    original_transcript = receipt["execution"]["provider_transcript"]
    for key in ("text", "segments", "language", "confidence", "actual_cost_vnd", "provider_duration_seconds"):
        _require(transcript[key] == original_transcript[key], "FORENSIC_PROVIDER_TRANSCRIPT_MISMATCH")
    words = _flatten_words(transcript)
    reference_tokens = normalized_tokens(reference)
    provider_tokens = normalized_tokens(transcript["text"])
    word_tokens = [token for word in words for token in word["normalized_tokens"]]
    _require(word_tokens == provider_tokens, "FORENSIC_TRANSCRIPT_WORD_COVERAGE_MISMATCH")
    _require(evaluator_input["reference"]["critical_terms"] == asset["critical_terms"], "FORENSIC_CRITICAL_SET_MISMATCH")
    failed_terms = [term for term in evaluation["critical_terms"]["terms"] if term["passed"] is False]
    _require({term["term"] for term in failed_terms} == set(OBSERVED_VARIANTS), "FORENSIC_UNEXPECTED_FAILED_TERM_SET")
    findings = []
    for term in failed_terms:
        expected = term["term"]
        expected_tokens = normalized_tokens(expected)
        observed_occurrences = []
        for variant in OBSERVED_VARIANTS[expected]:
            matches = locate_observed_phrase(transcript, variant)
            _require(bool(matches), "FORENSIC_OBSERVED_VARIANT_NOT_FOUND")
            for match in matches:
                match["diagnostic_token_edit_distance"] = diagnostic_edit_distance(expected_tokens, match["normalized_tokens"])
                match["diagnostic_edit_distance_used_for_acceptance"] = False
                observed_occurrences.append(match)
        observed_occurrences.sort(key=lambda item: item["global_word_indexes"][0])
        reference_starts = phrase_starts(reference_tokens, expected_tokens)
        _require(len(observed_occurrences) == len(reference_starts), "FORENSIC_OCCURRENCE_COVERAGE_MISMATCH")
        findings.append({
            "expected_phrase": expected,
            "expected_normalized_tokens": expected_tokens,
            "reference_token_start_indexes": reference_starts,
            "reference_occurrence_count": len(reference_starts),
            "provider_exact_normalized_occurrence_count": len(phrase_starts(provider_tokens, expected_tokens)),
            "observed_occurrences": observed_occurrences,
            "classification": classify(expected, observed_occurrences[0]["observed_phrase"], reference, owner_reference_verified=True),
            "classification_basis": "recorded provider text differs from exact pre-call owner-confirmed reference; not a new acoustic finding",
            "not_normalization_only": True,
            "normalization_policy_unchanged": True,
            "critical_term_accepted": False,
            "severity": "HIGH",
        })
    payload = {
        "schema_version": 1,
        "record_kind": "asr_critical_term_forensic",
        "checkpoint": "V3-01-23",
        "operation_id": receipt["operation_key"],
        "index_base": 0,
        "scope": "offline diagnosis only; never fuzzy acceptance or transcript correction",
        "source_sha256": SOURCE_SHA256,
        "asset_sha256": ASSET_SHA256,
        "reference_transcript_sha256": REFERENCE_SHA256,
        "owner_manifest_sha256": MANIFEST_SHA256,
        "reference_basis": {"owner_confirmation": confirmation, "new_acoustic_listening_performed": False,
                            "recorded_input_representation": "source final LF omitted; all other characters identical",
                            "independent_acoustic_ground_truth": "NOT_REVERIFIED",
                            "caveat": "PROVIDER_MISRECOGNITION is relative to the exact owner-confirmed reference. The assistant did not newly listen to the WAV; this does not independently prove what was pronounced."},
        "normalization": evaluation["normalization"],
        "grain": {"segments": len(transcript["segments"]), "provider_word_objects": len(words),
                  "provider_normalized_tokens": len(provider_tokens), "reference_normalized_tokens": len(reference_tokens),
                  "critical_terms": len(asset["critical_terms"]), "failed_critical_terms": len(findings)},
        "strict_evaluator_snapshot": {"critical_terms": evaluation["critical_terms"], "wer": evaluation["wer"], "verdict": evaluation["verdict"]},
        "provider_provenance": {key: transcript["provenance"][key] for key in ("provider_request_id", "request_sha256", "response_sha256")},
        "findings": findings,
        "invariants": {"provider_transcript_preserved": True, "reference_preserved": True, "timestamps_preserved": True,
                       "nullable_confidence_preserved": True, "all_failed_term_occurrences_accounted_for": True,
                       "fuzzy_acceptance": False, "critical_term_threshold_changed": False, "historical_verdict_changed": False},
        "safety": {"provider_calls": 0, "credential_reads": 0, "reservation_vnd": "0", "spend_vnd": "0",
                   "runtime_authority": False, "operation_2": "NOT_APPROVED_LOCKED", "production_verdict": "NO-GO"},
    }
    payload["report_sha256"] = sha256_bytes(canonical_bytes(payload))
    return payload


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[4])
    args = parser.parse_args()
    try:
        report = build_report(args.repo.resolve())
    except (ForensicBindingError, KeyError, StopIteration, TypeError, ValueError, OSError):
        print(json.dumps({"verdict": "BLOCKED_FORENSIC", "provider_calls": 0, "credential_reads": 0}))
        return 2
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
