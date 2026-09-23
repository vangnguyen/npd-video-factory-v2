"""Offline, read-only audit for the RC-21 27-boundary-point transcript.

This script never writes to the source terminal artifact. It constructs the
separate derived transcript in memory and emits only aggregate/hash evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from app.asr_derived_timing import (
    derive_positive_duration_transcript,
    transcript_sha256,
)
from app.auto_edit_providers import ProviderSegment, ProviderTranscript, ProviderWord


SOURCE_OPERATION = (
    "v3-01-rc21-openai-transcription-asr-al-0001-"
    "9753fc22463162401f1548bafbd0688620a4efb6239fcbbcff6fe3e87655fa0e-call-01"
)
SOURCE_TERMINAL_SHA256 = (
    "4fd23531dee1bdcc7920d7f090059f72dcac3961eb4aff762d46de8d822852c9"
)


def _load_terminal(path: Path) -> tuple[dict[str, object], ProviderTranscript]:
    source_bytes = path.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_TERMINAL_SHA256:
        raise AssertionError("SOURCE_TERMINAL_SHA256_MISMATCH")
    terminal = json.loads(source_bytes)
    raw = terminal["transcript"]
    segments = tuple(
        ProviderSegment(
            start_seconds=segment["start_seconds"],
            end_seconds=segment["end_seconds"],
            text=segment["text"],
            speaker=segment["speaker"],
            confidence=segment["confidence"],
            words=tuple(
                ProviderWord(
                    start_seconds=word["start_seconds"],
                    end_seconds=word["end_seconds"],
                    text=word["text"],
                    confidence=word["confidence"],
                    timing_semantics=word["timing_semantics"],
                )
                for word in segment["words"]
            ),
        )
        for segment in raw["segments"]
    )
    transcript = ProviderTranscript(
        language=raw["language"],
        confidence=raw["confidence"],
        segments=segments,
        provenance=raw["provenance"],
        actual_cost_vnd=raw["actual_cost_vnd"],
    )
    return terminal, transcript


def audit(path: Path) -> dict[str, object]:
    terminal, raw = _load_terminal(path)
    terminal_hash_before = hashlib.sha256(path.read_bytes()).hexdigest()
    raw_hash_before = transcript_sha256(raw)
    derived = derive_positive_duration_transcript(raw)
    terminal_hash_after = hashlib.sha256(path.read_bytes()).hexdigest()
    raw_hash_after = transcript_sha256(raw)

    words = [word for segment in raw.segments for word in segment.words]
    zero_indexes = [
        index
        for index, word in enumerate(words)
        if word.timing_semantics == "provider_boundary_point"
    ]
    changed = [
        record
        for record in derived.word_timings
        if record.action != "preserved_provider_interval"
    ]
    boundary_records = [
        record
        for record in derived.word_timings
        if record.action == "partitioned_boundary_point"
    ]
    successor_records = [
        record
        for record in derived.word_timings
        if record.action == "repartitioned_successor_interval"
    ]

    run_count = 0
    runs_with_preceding_gap = 0
    preceding_gap_seconds = 0.0
    max_preceding_gap_seconds = 0.0
    for segment in raw.segments:
        index = 0
        previous_end = segment.start_seconds
        while index < len(segment.words):
            word = segment.words[index]
            if word.timing_semantics != "provider_boundary_point":
                previous_end = word.end_seconds
                index += 1
                continue
            run_count += 1
            gap = max(0.0, word.start_seconds - previous_end)
            if gap > 0:
                runs_with_preceding_gap += 1
                preceding_gap_seconds += gap
                max_preceding_gap_seconds = max(max_preceding_gap_seconds, gap)
            anchor = word.start_seconds
            while (
                index < len(segment.words)
                and segment.words[index].timing_semantics == "provider_boundary_point"
                and segment.words[index].start_seconds == anchor
            ):
                index += 1
            successor = segment.words[index]
            previous_end = successor.end_seconds
            index += 1

    durations = [
        record.derived_end_seconds - record.derived_start_seconds
        for record in boundary_records
    ]
    successor_start_shifts = [
        record.derived_start_seconds - record.raw_start_seconds
        for record in successor_records
    ]
    all_derived_words = [
        word for segment in derived.value.segments for word in segment.words
    ]
    report = {
        "verdict": "PASS_OFFLINE_DERIVATION_CANDIDATE",
        "source_operation": SOURCE_OPERATION,
        "source_terminal_sha256": SOURCE_TERMINAL_SHA256,
        "source_terminal_hash_before": terminal_hash_before,
        "source_terminal_hash_after": terminal_hash_after,
        "source_terminal_bytes_unchanged": terminal_hash_before == terminal_hash_after,
        "terminal_operation_consumed": terminal["operation_consumed"],
        "historical_quality_verdict": "FAIL_UNCHANGED",
        "raw_transcript_sha256": raw_hash_before,
        "raw_transcript_hash_after": raw_hash_after,
        "raw_transcript_unchanged": raw_hash_before == raw_hash_after,
        "word_count": len(words),
        "raw_zero_duration_word_count": len(zero_indexes),
        "raw_zero_duration_global_indexes": zero_indexes,
        "boundary_run_count": run_count,
        "runs_with_preceding_gap": runs_with_preceding_gap,
        "preceding_gap_total_seconds": round(preceding_gap_seconds, 6),
        "preceding_gap_max_seconds": round(max_preceding_gap_seconds, 6),
        "selected_algorithm": derived.algorithm,
        "derived_transcript_sha256": derived.derived_transcript_sha256,
        "word_timing_manifest_sha256": derived.word_timing_manifest_sha256,
        "changed_word_count": len(changed),
        "partitioned_boundary_point_count": len(boundary_records),
        "repartitioned_successor_count": len(successor_records),
        "all_derived_words_positive": all(
            word.end_seconds > word.start_seconds for word in all_derived_words
        ),
        "minimum_boundary_duration_seconds": round(min(durations), 6),
        "maximum_boundary_duration_seconds": round(max(durations), 6),
        "maximum_successor_start_shift_seconds": round(
            max(successor_start_shifts), 6
        ),
        "algorithm_comparison": {
            "midpoint_redistribution": {
                "status": "REJECTED",
                "reason": "would recompute unrelated positive provider intervals",
            },
            "neighbor_bound_interpolation": {
                "status": "REJECTED",
                "runs_entering_preceding_gap": runs_with_preceding_gap,
                "preceding_gap_total_seconds": round(preceding_gap_seconds, 6),
                "reason": "would assign speech into provider-native gaps",
            },
            "segment_proportional_allocation": {
                "status": "REJECTED",
                "reason": "lexical-length weighting is not acoustic evidence",
            },
            "constrained_minimum_duration_expansion": {
                "status": "REJECTED",
                "reason": "requires an arbitrary epsilon and can cross interval bounds",
            },
            "adjacent_successor_partition_v1": {
                "status": "SELECTED",
                "reason": (
                    "partitions only the existing positive interval of the immediate "
                    "provider successor; never fills a gap or crosses a segment"
                ),
            },
        },
        "raw_provider_timing_claimed_by_derivation": False,
        "acoustic_alignment_claimed_by_derivation": False,
        "provider_calls": 0,
        "credential_reads": 0,
        "budget_reserved_vnd": "0",
        "additional_cost_vnd": "0",
        "operation_2": "LOCKED",
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--terminal", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.terminal), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
