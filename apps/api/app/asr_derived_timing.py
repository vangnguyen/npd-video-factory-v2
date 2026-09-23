from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, TypeAlias

from .auto_edit_providers import (
    PositiveDurationTranscript,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)


ADJACENT_SUCCESSOR_PARTITION_V1 = "adjacent_successor_partition_v1"
MICROSECONDS_PER_SECOND = Decimal("1000000")


class DerivedTimingRequired(ValueError):
    """The raw timing evidence cannot be safely projected into intervals."""

    code = "DERIVED_POSITIVE_DURATION_TRANSCRIPT_REQUIRED"

    def __init__(
        self,
        *,
        blocked_word_paths: tuple[str, ...],
        reasons: tuple[str, ...],
    ) -> None:
        super().__init__(self.code)
        self.blocked_word_paths = blocked_word_paths
        self.reasons = reasons


@dataclass(frozen=True)
class DerivedWordTiming:
    global_word_index: int
    segment_index: int
    word_index: int
    text: str
    raw_start_seconds: float
    raw_end_seconds: float
    derived_start_seconds: float
    derived_end_seconds: float
    action: Literal[
        "preserved_provider_interval",
        "partitioned_boundary_point",
        "repartitioned_successor_interval",
    ]
    source_timing_semantics: Literal[
        "positive_interval",
        "provider_boundary_point",
        "derived_positive_interval",
    ]


@dataclass(frozen=True)
class DerivedPositiveDurationTranscript:
    """Separate downstream projection whose raw provider value stays immutable.

    ``value`` is safe for interval-only consumers. It is not provider evidence:
    every changed word is marked ``derived_positive_interval`` and every mapping
    back to ``raw_value`` is hash-bound in ``word_timings``.
    """

    raw_value: ProviderTranscript
    value: ProviderTranscript
    algorithm: Literal["adjacent_successor_partition_v1"]
    raw_transcript_sha256: str
    derived_transcript_sha256: str
    word_timing_manifest_sha256: str
    word_timings: tuple[DerivedWordTiming, ...]
    transformation_applied: Literal[True] = True
    provenance: Literal["raw_provider_evidence_preserved_separate"] = (
        "raw_provider_evidence_preserved_separate"
    )


DownstreamTranscript: TypeAlias = (
    PositiveDurationTranscript | DerivedPositiveDurationTranscript
)


def _seconds_to_microseconds(value: float) -> int:
    return int(
        (Decimal(str(value)) * MICROSECONDS_PER_SECOND).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _microseconds_to_seconds(value: int) -> float:
    return float(Decimal(value) / MICROSECONDS_PER_SECOND)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _canonical_sha256(payload: object) -> str:
    encoded = json.dumps(
        _json_safe(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _transcript_payload(transcript: ProviderTranscript) -> dict[str, object]:
    return {
        "language": transcript.language,
        "confidence": transcript.confidence,
        "segments": [
            {
                "start_seconds": segment.start_seconds,
                "end_seconds": segment.end_seconds,
                "text": segment.text,
                "speaker": segment.speaker,
                "confidence": segment.confidence,
                "words": [
                    {
                        "start_seconds": word.start_seconds,
                        "end_seconds": word.end_seconds,
                        "text": word.text,
                        "confidence": word.confidence,
                        "timing_semantics": word.timing_semantics,
                    }
                    for word in segment.words
                ],
            }
            for segment in transcript.segments
        ],
        "provenance": transcript.provenance,
        "actual_cost_vnd": transcript.actual_cost_vnd,
    }


def transcript_sha256(transcript: ProviderTranscript) -> str:
    return _canonical_sha256(_transcript_payload(transcript))


def _validate_positive_projection(segments: tuple[ProviderSegment, ...]) -> None:
    blocked: list[str] = []
    reasons: list[str] = []
    for segment_index, segment in enumerate(segments):
        previous_end_us = _seconds_to_microseconds(segment.start_seconds)
        segment_start_us = previous_end_us
        segment_end_us = _seconds_to_microseconds(segment.end_seconds)
        if segment_end_us <= segment_start_us:
            blocked.append(f"$.segments[{segment_index}]")
            reasons.append("segment_not_positive")
            continue
        for word_index, word in enumerate(segment.words):
            path = f"$.segments[{segment_index}].words[{word_index}]"
            start_us = _seconds_to_microseconds(word.start_seconds)
            end_us = _seconds_to_microseconds(word.end_seconds)
            if end_us <= start_us:
                blocked.append(path)
                reasons.append("word_not_positive")
            elif start_us < segment_start_us or end_us > segment_end_us:
                blocked.append(path)
                reasons.append("word_outside_segment")
            elif start_us < previous_end_us:
                blocked.append(path)
                reasons.append("word_overlap")
            previous_end_us = max(previous_end_us, end_us)
    if blocked:
        raise DerivedTimingRequired(
            blocked_word_paths=tuple(blocked), reasons=tuple(reasons)
        )


def derive_positive_duration_transcript(
    transcript: ProviderTranscript,
    *,
    algorithm: Literal["adjacent_successor_partition_v1"] = (
        ADJACENT_SUCCESSOR_PARTITION_V1
    ),
) -> DerivedPositiveDurationTranscript:
    """Create a separate positive-duration projection without changing raw evidence.

    For each run of boundary-point words, V1 partitions only the already-positive
    interval of the immediately following provider word. It never fills a silence
    gap, crosses a segment boundary, or moves another provider interval. A run at
    segment end, a non-adjacent successor, or insufficient microsecond resolution
    fails closed.
    """

    if algorithm != ADJACENT_SUCCESSOR_PARTITION_V1:
        raise ValueError("unsupported derived timing algorithm")

    raw_sha256 = transcript_sha256(transcript)
    derived_segments: list[ProviderSegment] = []
    timing_records: list[DerivedWordTiming] = []
    global_word_index = 0

    for segment_index, segment in enumerate(transcript.segments):
        words = segment.words
        derived_words: list[ProviderWord] = []
        word_index = 0
        previous_derived_end_us = _seconds_to_microseconds(segment.start_seconds)

        while word_index < len(words):
            word = words[word_index]
            path = f"$.segments[{segment_index}].words[{word_index}]"
            start_us = _seconds_to_microseconds(word.start_seconds)
            end_us = _seconds_to_microseconds(word.end_seconds)

            if end_us > start_us:
                if start_us < previous_derived_end_us:
                    raise DerivedTimingRequired(
                        blocked_word_paths=(path,), reasons=("raw_word_overlap",)
                    )
                derived_words.append(word)
                timing_records.append(
                    DerivedWordTiming(
                        global_word_index=global_word_index,
                        segment_index=segment_index,
                        word_index=word_index,
                        text=word.text,
                        raw_start_seconds=word.start_seconds,
                        raw_end_seconds=word.end_seconds,
                        derived_start_seconds=word.start_seconds,
                        derived_end_seconds=word.end_seconds,
                        action="preserved_provider_interval",
                        source_timing_semantics=word.timing_semantics,
                    )
                )
                previous_derived_end_us = end_us
                global_word_index += 1
                word_index += 1
                continue

            if word.timing_semantics != "provider_boundary_point":
                raise DerivedTimingRequired(
                    blocked_word_paths=(path,),
                    reasons=("zero_duration_word_without_boundary_semantics",),
                )

            anchor_us = start_us
            run_end = word_index
            while run_end < len(words):
                candidate = words[run_end]
                candidate_start_us = _seconds_to_microseconds(
                    candidate.start_seconds
                )
                candidate_end_us = _seconds_to_microseconds(candidate.end_seconds)
                if (
                    candidate_start_us != anchor_us
                    or candidate_end_us != anchor_us
                    or candidate.timing_semantics != "provider_boundary_point"
                ):
                    break
                run_end += 1

            if run_end >= len(words):
                blocked = tuple(
                    f"$.segments[{segment_index}].words[{index}]"
                    for index in range(word_index, run_end)
                )
                raise DerivedTimingRequired(
                    blocked_word_paths=blocked,
                    reasons=("boundary_run_has_no_successor_interval",) * len(blocked),
                )

            successor = words[run_end]
            successor_start_us = _seconds_to_microseconds(successor.start_seconds)
            successor_end_us = _seconds_to_microseconds(successor.end_seconds)
            if (
                successor_start_us != anchor_us
                or successor_end_us <= successor_start_us
                or successor.timing_semantics != "positive_interval"
            ):
                blocked = tuple(
                    f"$.segments[{segment_index}].words[{index}]"
                    for index in range(word_index, run_end)
                )
                raise DerivedTimingRequired(
                    blocked_word_paths=blocked,
                    reasons=("boundary_run_not_anchored_to_positive_successor",)
                    * len(blocked),
                )
            if anchor_us < previous_derived_end_us:
                raise DerivedTimingRequired(
                    blocked_word_paths=(path,),
                    reasons=("boundary_run_overlaps_previous_interval",),
                )

            run_count = run_end - word_index
            part_count = run_count + 1
            span_us = successor_end_us - anchor_us
            boundaries = [
                anchor_us + (span_us * part_index) // part_count
                for part_index in range(part_count + 1)
            ]
            if any(right <= left for left, right in zip(boundaries, boundaries[1:])):
                blocked = tuple(
                    f"$.segments[{segment_index}].words[{index}]"
                    for index in range(word_index, run_end + 1)
                )
                raise DerivedTimingRequired(
                    blocked_word_paths=blocked,
                    reasons=("successor_interval_has_insufficient_resolution",)
                    * len(blocked),
                )

            for offset, source_index in enumerate(range(word_index, run_end)):
                source_word = words[source_index]
                derived_start = _microseconds_to_seconds(boundaries[offset])
                derived_end = _microseconds_to_seconds(boundaries[offset + 1])
                derived_words.append(
                    ProviderWord(
                        start_seconds=derived_start,
                        end_seconds=derived_end,
                        text=source_word.text,
                        confidence=source_word.confidence,
                        timing_semantics="derived_positive_interval",
                    )
                )
                timing_records.append(
                    DerivedWordTiming(
                        global_word_index=global_word_index,
                        segment_index=segment_index,
                        word_index=source_index,
                        text=source_word.text,
                        raw_start_seconds=source_word.start_seconds,
                        raw_end_seconds=source_word.end_seconds,
                        derived_start_seconds=derived_start,
                        derived_end_seconds=derived_end,
                        action="partitioned_boundary_point",
                        source_timing_semantics=source_word.timing_semantics,
                    )
                )
                global_word_index += 1

            successor_derived_start = _microseconds_to_seconds(boundaries[-2])
            successor_derived_end = _microseconds_to_seconds(boundaries[-1])
            derived_words.append(
                ProviderWord(
                    start_seconds=successor_derived_start,
                    end_seconds=successor_derived_end,
                    text=successor.text,
                    confidence=successor.confidence,
                    timing_semantics="derived_positive_interval",
                )
            )
            timing_records.append(
                DerivedWordTiming(
                    global_word_index=global_word_index,
                    segment_index=segment_index,
                    word_index=run_end,
                    text=successor.text,
                    raw_start_seconds=successor.start_seconds,
                    raw_end_seconds=successor.end_seconds,
                    derived_start_seconds=successor_derived_start,
                    derived_end_seconds=successor_derived_end,
                    action="repartitioned_successor_interval",
                    source_timing_semantics=successor.timing_semantics,
                )
            )
            previous_derived_end_us = boundaries[-1]
            global_word_index += 1
            word_index = run_end + 1

        derived_segments.append(
            ProviderSegment(
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                speaker=segment.speaker,
                confidence=segment.confidence,
                words=tuple(derived_words),
            )
        )

    derived_segments_tuple = tuple(derived_segments)
    _validate_positive_projection(derived_segments_tuple)
    manifest_payload = [asdict(item) for item in timing_records]
    manifest_sha256 = _canonical_sha256(manifest_payload)
    derived_content_sha256 = _canonical_sha256(
        {
            "algorithm": algorithm,
            "raw_transcript_sha256": raw_sha256,
            "word_timing_manifest_sha256": manifest_sha256,
            "segments": _transcript_payload(
                ProviderTranscript(
                    language=transcript.language,
                    confidence=transcript.confidence,
                    segments=derived_segments_tuple,
                    provenance={},
                    actual_cost_vnd=transcript.actual_cost_vnd,
                )
            )["segments"],
        }
    )
    derived_provenance = {
        **transcript.provenance,
        "original_evidence": False,
        "timestamp_source": "derived_from_provider_native_word_boundaries",
        "timing_derivation": {
            "algorithm": algorithm,
            "algorithm_version": "1",
            "raw_provider_evidence_mutated": False,
            "raw_transcript_sha256": raw_sha256,
            "derived_transcript_sha256": derived_content_sha256,
            "word_timing_manifest_sha256": manifest_sha256,
            "word_count": len(timing_records),
            "partitioned_boundary_point_count": sum(
                item.action == "partitioned_boundary_point"
                for item in timing_records
            ),
            "repartitioned_successor_count": sum(
                item.action == "repartitioned_successor_interval"
                for item in timing_records
            ),
            "acoustic_alignment_claimed": False,
            "provider_timing_claimed": False,
        },
    }
    derived_value = ProviderTranscript(
        language=transcript.language,
        confidence=transcript.confidence,
        segments=derived_segments_tuple,
        provenance=derived_provenance,
        actual_cost_vnd=transcript.actual_cost_vnd,
    )
    return DerivedPositiveDurationTranscript(
        raw_value=transcript,
        value=derived_value,
        algorithm=algorithm,
        raw_transcript_sha256=raw_sha256,
        derived_transcript_sha256=derived_content_sha256,
        word_timing_manifest_sha256=manifest_sha256,
        word_timings=tuple(timing_records),
    )
