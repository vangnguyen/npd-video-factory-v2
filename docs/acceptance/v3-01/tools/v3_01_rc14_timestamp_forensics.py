#!/usr/bin/env python3
"""Build a secret-free forensic report from retained RC-14 timestamp diagnostics.

The source receipt intentionally did not retain transcript/word text or the raw
provider response. This tool never invents those fields. It reports them as
unavailable while exhaustively analysing every retained segment and word timing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


EXPECTED_OPERATION = "v3-01-rc14-openai-transcription-asr-call-01"
EXPECTED_REQUEST_ID = "req_0e79520e09d64387b40973352ef9fec6"
EXPECTED_RESPONSE_SHA256 = (
    "1d55f138d8518dfc171fe345be7f7cba948dfa2a3036b9f292ef87230aa22878"
)
TIMING_TOLERANCE = 0.000001


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("RC-14 evidence must be one JSON object")
    return value


def _number(value: object, *, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a JSON number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be finite")
    return number


def _close(left: float, right: float) -> bool:
    return abs(left - right) <= TIMING_TOLERANCE


def _selected_segment(
    *, start: float, end: float, segments: list[dict[str, Any]]
) -> tuple[list[int], int | None]:
    candidates = [
        item["segment_index"]
        for item in segments
        if start >= item["raw_start_seconds"] - TIMING_TOLERANCE
        and end <= item["raw_end_seconds"] + TIMING_TOLERANCE
    ]
    if not candidates:
        return candidates, None
    exact_starts = [
        index
        for index in candidates
        if _close(start, segments[index]["raw_start_seconds"])
    ]
    if len(exact_starts) == 1:
        return candidates, exact_starts[0]
    half_open = [
        index
        for index in candidates
        if segments[index]["raw_start_seconds"] <= start
        and end <= segments[index]["raw_end_seconds"]
        and start < segments[index]["raw_end_seconds"]
    ]
    if len(half_open) == 1:
        return candidates, half_open[0]
    if len(candidates) == 1:
        return candidates, candidates[0]
    if _close(end, segments[-1]["raw_end_seconds"]):
        return candidates, candidates[-1]
    return candidates, None


def build_report(
    source: dict[str, Any], *, source_sha256: str, source_label: str, generated_at_utc: str
) -> dict[str, Any]:
    operation = str(source.get("operation_key") or "")
    attempt = source["ledger"]["attempts"][0]
    error = attempt["error_evidence"]
    request_id = str(error.get("provider_request_id") or "")
    response_sha = str(error.get("response_sha256") or "")
    if operation != EXPECTED_OPERATION:
        raise ValueError("unexpected RC-14 operation ID")
    if request_id != EXPECTED_REQUEST_ID:
        raise ValueError("unexpected RC-14 provider request ID")
    if response_sha != EXPECTED_RESPONSE_SHA256:
        raise ValueError("unexpected RC-14 response SHA-256")

    diagnostics = error["timestamp_diagnostics"]
    segment_rows = sorted(
        (row for row in diagnostics if row["item_kind"] == "segment"),
        key=lambda row: row["index"],
    )
    word_rows = sorted(
        (row for row in diagnostics if row["item_kind"] == "word"),
        key=lambda row: row["index"],
    )
    if [row["index"] for row in segment_rows] != list(range(len(segment_rows))):
        raise ValueError("segment diagnostics are not complete and contiguous")
    if [row["index"] for row in word_rows] != list(range(len(word_rows))):
        raise ValueError("word diagnostics are not complete and contiguous")

    segments: list[dict[str, Any]] = []
    for row in segment_rows:
        start = _number(row["raw_start_seconds"], path=row["path"] + ".start")
        end = _number(row["raw_end_seconds"], path=row["path"] + ".end")
        segments.append(
            {
                "segment_index": row["index"],
                "path": row["path"],
                "raw_start_seconds": start,
                "raw_end_seconds": end,
                "raw_duration_seconds": end - start,
                "canonical_start_seconds": row["canonical_start_seconds"],
                "canonical_end_seconds": row["canonical_end_seconds"],
                "historical_classification": row["classification"],
                "historical_action": row["action"],
                "valid_positive_interval": start >= 0 and end > start,
            }
        )

    source_duration = _number(source["binding"]["wav"]["duration_seconds"], path="$.binding.wav.duration_seconds")
    raw_intervals = [
        (
            _number(row["raw_start_seconds"], path=row["path"] + ".start"),
            _number(row["raw_end_seconds"], path=row["path"] + ".end"),
        )
        for row in word_rows
    ]
    interval_peers: dict[tuple[float, float], list[int]] = defaultdict(list)
    for index, interval in enumerate(raw_intervals):
        interval_peers[interval].append(index)

    selected_segments: list[int | None] = []
    segment_candidates: list[list[int]] = []
    for start, end in raw_intervals:
        candidates, selected = _selected_segment(start=start, end=end, segments=segments)
        segment_candidates.append(candidates)
        selected_segments.append(selected)
    positions: dict[int, dict[int, int]] = defaultdict(dict)
    for word_index, segment_index in enumerate(selected_segments):
        if segment_index is not None:
            positions[segment_index][word_index] = len(positions[segment_index])

    zero_indexes = {
        index for index, (start, end) in enumerate(raw_intervals) if start == end
    }
    words: list[dict[str, Any]] = []
    zero_category_counts: Counter[str] = Counter()
    for index, (row, interval) in enumerate(zip(word_rows, raw_intervals, strict=True)):
        start, end = interval
        previous = raw_intervals[index - 1] if index else None
        following = raw_intervals[index + 1] if index + 1 < len(raw_intervals) else None
        segment_index = selected_segments[index]
        segment = segments[segment_index] if segment_index is not None else None
        peers = [peer for peer in interval_peers[interval] if peer != index]
        duration = end - start
        is_zero = duration == 0
        categories: list[str] = []
        if is_zero:
            categories.append("provider_emitted_exact_boundary_point")
            if segment and _close(start, segment["raw_start_seconds"]):
                categories.append("segment_start_boundary_point")
            elif segment and _close(end, segment["raw_end_seconds"]):
                categories.append("segment_end_boundary_point")
            else:
                categories.append("segment_interior_boundary_point")
            if previous and _close(start, previous[1]):
                categories.append("matches_previous_word_end")
            if following and _close(end, following[0]):
                categories.append("matches_next_word_start")
            if peers:
                categories.append("duplicate_zero_timestamp_group_member")
            if (index - 1 in zero_indexes) or (index + 1 in zero_indexes):
                categories.append("consecutive_zero_duration_word")
            zero_category_counts.update(categories)

        boundary_position = None
        if segment is not None:
            if _close(start, segment["raw_start_seconds"]):
                boundary_position = "segment_start"
            elif _close(end, segment["raw_end_seconds"]):
                boundary_position = "segment_end"
            else:
                boundary_position = "segment_interior"
        words.append(
            {
                "word_index": index,
                "path": row["path"],
                "token_text": None,
                "token_text_availability": "UNKNOWN_NOT_RETAINED",
                "punctuation_characteristics": None,
                "punctuation_availability": "UNKNOWN_NOT_RETAINED",
                "raw_start_seconds": start,
                "raw_end_seconds": end,
                "raw_duration_seconds": duration,
                "canonical_start_seconds_in_historical_receipt": row["canonical_start_seconds"],
                "canonical_end_seconds_in_historical_receipt": row["canonical_end_seconds"],
                "historical_classification": row["classification"],
                "historical_action": row["action"],
                "containing_segment_candidates": segment_candidates[index],
                "selected_segment_index": segment_index,
                "position_in_selected_segment": (
                    positions[segment_index][index] if segment_index is not None else None
                ),
                "selected_segment_boundary_position": boundary_position,
                "previous_word": (
                    None
                    if previous is None
                    else {
                        "word_index": index - 1,
                        "raw_start_seconds": previous[0],
                        "raw_end_seconds": previous[1],
                        "end_matches_current_start": _close(previous[1], start),
                    }
                ),
                "next_word": (
                    None
                    if following is None
                    else {
                        "word_index": index + 1,
                        "raw_start_seconds": following[0],
                        "raw_end_seconds": following[1],
                        "start_matches_current_end": _close(following[0], end),
                    }
                ),
                "duplicate_interval_peer_indexes": peers,
                "monotonic": (
                    previous is None
                    or (start >= previous[0] - TIMING_TOLERANCE and end >= previous[1] - TIMING_TOLERANCE)
                ),
                "overlaps_previous_word": previous is not None and start < previous[1] - TIMING_TOLERANCE,
                "inside_source_duration": start >= 0 and end <= source_duration + TIMING_TOLERANCE,
                "inside_selected_segment": segment_index is not None,
                "zero_duration": is_zero,
                "zero_duration_categories": categories,
                "transcript_coverage_contribution": "UNKNOWN_NOT_RETAINED",
            }
        )

    zero_words = [word for word in words if word["zero_duration"]]
    positive_words = [word for word in words if not word["zero_duration"]]
    duplicate_zero_groups = [
        indexes
        for interval, indexes in sorted(interval_peers.items())
        if interval[0] == interval[1] and len(indexes) > 1
    ]
    all_zero_boundary_safe = all(
        word["inside_source_duration"]
        and word["inside_selected_segment"]
        and word["monotonic"]
        and not word["overlaps_previous_word"]
        and "matches_next_word_start" in word["zero_duration_categories"]
        for word in zero_words
    )
    report: dict[str, Any] = {
        "schema_version": 1,
        "record_kind": "asr_word_timestamp_forensic_report",
        "forensic_id": "V3-01-22-RC14-ASR-OP1-TIMESTAMPS",
        "generated_at_utc": generated_at_utc,
        "source": {
            "label": source_label,
            "sha256": source_sha256,
            "operation_id": operation,
            "provider_request_id": request_id,
            "request_sha256": error["request_sha256"],
            "response_sha256": response_sha,
            "raw_provider_response_retained": False,
            "transcript_text_retained": False,
            "word_text_retained": False,
        },
        "historical_operation": {
            "provider_http_status": error["http_status"],
            "provider_execution": "SUCCESS_AT_HTTP_TRANSPORT_LEVEL",
            "acceptance": source["acceptance_verdict"],
            "operation_consumed": source["operation_1_consumed"],
            "actual_provider_cost_vnd": None,
            "safety_charge_vnd": "500",
            "safety_charge_is_actual_cost": False,
            "operation_2_status": source["operation_2_status"],
            "production_verdict": source["production_verdict"],
        },
        "population": {
            "source_duration_seconds": source_duration,
            "segment_count": len(segments),
            "word_count": len(words),
            "positive_duration_word_count": len(positive_words),
            "zero_duration_word_count": len(zero_words),
            "zero_duration_percent": round(len(zero_words) / len(words) * 100, 6),
            "all_diagnostic_words_accounted_for": len(words) == error["timestamp_summary"]["word_count_received"],
        },
        "aggregate": {
            "zero_duration_indexes": [word["word_index"] for word in zero_words],
            "zero_duration_category_counts": dict(sorted(zero_category_counts.items())),
            "duplicate_zero_timestamp_groups": duplicate_zero_groups,
            "zero_duration_outside_source": sum(not word["inside_source_duration"] for word in zero_words),
            "zero_duration_outside_segment": sum(not word["inside_selected_segment"] for word in zero_words),
            "zero_duration_non_monotonic": sum(not word["monotonic"] for word in zero_words),
            "zero_duration_overlaps_previous": sum(word["overlaps_previous_word"] for word in zero_words),
            "all_zero_duration_points_match_next_word_start": all(
                "matches_next_word_start" in word["zero_duration_categories"]
                for word in zero_words
            ),
            "all_zero_duration_points_are_bounded_monotonic_boundaries": all_zero_boundary_safe,
            "all_word_intervals_inside_source": all(word["inside_source_duration"] for word in words),
            "all_words_map_to_one_selected_segment": all(
                word["selected_segment_index"] is not None for word in words
            ),
            "transcript_coverage": None,
            "transcript_coverage_status": "UNKNOWN_NOT_RETAINED",
        },
        "segments": segments,
        "words": words,
        "conclusions": {
            "observed_shape": "provider_emitted_ordered_zero_duration_word_boundary_points",
            "evidence_supports_provider_boundary_artifact_semantics": all_zero_boundary_safe,
            "provider_documentation_proves_zero_duration_semantics": False,
            "word_or_punctuation_identity_known": False,
            "no_provider_timestamp_was_modified": True,
            "no_word_was_dropped": True,
            "no_duration_was_fabricated": True,
            "historical_rc14_verdict_changed": False,
        },
        "safety": {
            "provider_calls": 0,
            "credential_reads": 0,
            "reservation_vnd": "0",
            "spend_vnd": "0",
            "operation_1_reused": False,
            "operation_2_executed": False,
            "production_verdict": "NO-GO",
        },
    }
    report["report_sha256"] = sha256_bytes(canonical_json_bytes(report))
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-label", required=True)
    parser.add_argument("--generated-at-utc", required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source_bytes = args.source.read_bytes()
    report = build_report(
        json.loads(source_bytes),
        source_sha256=sha256_bytes(source_bytes),
        source_label=args.source_label,
        generated_at_utc=args.generated_at_utc,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
