from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.asr_derived_timing import (
    ADJACENT_SUCCESSOR_PARTITION_V1,
    DerivedTimingRequired,
    derive_positive_duration_transcript,
    transcript_sha256,
)
from app.auto_edit_logic import build_highlights, build_scenes, build_silence_decisions
from app.auto_edit_models import AutoEditAnalysisRequest, TranscriptWordRead
from app.auto_edit_providers import (
    MediaSignals,
    ProviderSegment,
    ProviderTranscript,
    ProviderWord,
)
from app.production_models import SubtitleCue, SubtitleWord
from app.timeline_models import TimelineClip, TimelineSnapshot, TimelineTrack
from app.vision_models import ReframeKeyframeRead


FIXTURE = Path(__file__).parent / "fixtures" / "v3_01_rc21_zero_duration_runs.json"


def _fixture() -> dict[str, object]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _actual_boundary_run_transcript() -> ProviderTranscript:
    payload = _fixture()
    grouped: dict[int, dict[str, object]] = {}
    for run in payload["runs"]:
        segment_index = int(run["s"])
        group = grouped.setdefault(
            segment_index,
            {"bounds": run["b"], "words": {}},
        )
        words = group["words"]
        for global_index, _, text, point in run["z"]:
            words[int(global_index)] = ProviderWord(
                start_seconds=float(point),
                end_seconds=float(point),
                text=str(text),
                confidence=None,
                timing_semantics="provider_boundary_point",
            )
        global_index, _, text, start, end = run["n"]
        words[int(global_index)] = ProviderWord(
            start_seconds=float(start),
            end_seconds=float(end),
            text=str(text),
            confidence=None,
        )

    segments: list[ProviderSegment] = []
    for segment_index, group in sorted(grouped.items()):
        bounds = group["bounds"]
        words_by_index = group["words"]
        words = tuple(words_by_index[index] for index in sorted(words_by_index))
        segments.append(
            ProviderSegment(
                start_seconds=float(bounds[0]),
                end_seconds=float(bounds[1]),
                text=" ".join(word.text for word in words),
                speaker=None,
                confidence=None,
                words=words,
            )
        )
    return ProviderTranscript(
        language="vi",
        confidence=None,
        segments=tuple(segments),
        provenance={
            "fixture_source_operation": payload["source_operation"],
            "fixture_source_terminal_sha256": payload["source_terminal_sha256"],
            "original_evidence": True,
        },
    )


def test_actual_rc21_fixture_covers_all_27_boundary_points() -> None:
    payload = _fixture()
    global_indexes = [
        int(word[0]) for run in payload["runs"] for word in run["z"]
    ]
    assert payload["raw_zero_duration_word_count"] == 27
    assert payload["boundary_run_count"] == 25
    assert len(global_indexes) == len(set(global_indexes)) == 27
    assert global_indexes == [
        5,
        7,
        10,
        17,
        25,
        38,
        59,
        64,
        86,
        87,
        114,
        135,
        139,
        140,
        146,
        169,
        185,
        194,
        197,
        226,
        230,
        265,
        271,
        294,
        303,
        344,
        372,
    ]


def test_adjacent_successor_partition_is_deterministic_and_preserves_raw() -> None:
    raw = _actual_boundary_run_transcript()
    raw_hash_before = transcript_sha256(raw)

    first = derive_positive_duration_transcript(raw)
    second = derive_positive_duration_transcript(raw)

    assert first.algorithm == ADJACENT_SUCCESSOR_PARTITION_V1
    assert transcript_sha256(raw) == raw_hash_before == first.raw_transcript_sha256
    assert first.raw_value is raw
    assert first.derived_transcript_sha256 == second.derived_transcript_sha256
    assert first.word_timing_manifest_sha256 == second.word_timing_manifest_sha256
    assert first.word_timings == second.word_timings
    assert sum(
        item.action == "partitioned_boundary_point" for item in first.word_timings
    ) == 27
    assert sum(
        item.action == "repartitioned_successor_interval"
        for item in first.word_timings
    ) == 25
    assert all(
        word.start_seconds == word.end_seconds
        for segment in raw.segments
        for word in segment.words
        if word.timing_semantics == "provider_boundary_point"
    )

    for segment in first.value.segments:
        previous_end = segment.start_seconds
        for word in segment.words:
            assert word.end_seconds > word.start_seconds
            assert word.start_seconds >= previous_end
            assert segment.start_seconds <= word.start_seconds < word.end_seconds
            assert word.end_seconds <= segment.end_seconds
            previous_end = word.end_seconds

    raw_text = [word.text for segment in raw.segments for word in segment.words]
    derived_text = [
        word.text for segment in first.value.segments for word in segment.words
    ]
    assert derived_text == raw_text
    metadata = first.value.provenance["timing_derivation"]
    assert metadata["raw_provider_evidence_mutated"] is False
    assert metadata["acoustic_alignment_claimed"] is False
    assert metadata["provider_timing_claimed"] is False


@pytest.mark.parametrize(
    ("words", "reason"),
    [
        (
            (
                ProviderWord(
                    start_seconds=1,
                    end_seconds=1,
                    text="cuối",
                    confidence=None,
                    timing_semantics="provider_boundary_point",
                ),
            ),
            "boundary_run_has_no_successor_interval",
        ),
        (
            (
                ProviderWord(
                    start_seconds=1,
                    end_seconds=1,
                    text="điểm",
                    confidence=None,
                    timing_semantics="provider_boundary_point",
                ),
                ProviderWord(
                    start_seconds=1.1,
                    end_seconds=1.2,
                    text="rời",
                    confidence=None,
                ),
            ),
            "boundary_run_not_anchored_to_positive_successor",
        ),
    ],
)
def test_derivation_fails_closed_when_boundary_support_is_missing(
    words: tuple[ProviderWord, ...], reason: str
) -> None:
    transcript = ProviderTranscript(
        language="vi",
        confidence=None,
        segments=(
            ProviderSegment(
                start_seconds=0,
                end_seconds=2,
                text="kiểm thử",
                speaker=None,
                confidence=None,
                words=words,
            ),
        ),
        provenance={"original_evidence": True},
    )
    with pytest.raises(DerivedTimingRequired) as captured:
        derive_positive_duration_transcript(transcript)
    assert reason in captured.value.reasons


def test_actual_27_case_projection_satisfies_downstream_interval_contracts() -> None:
    derived = derive_positive_duration_transcript(
        _actual_boundary_run_transcript()
    )
    duration = max(segment.end_seconds for segment in derived.value.segments)
    signals = MediaSignals(
        shot_boundaries=((31.6, 0.9), (63.459999, 0.8), (87.480003, 0.7)),
        silence_intervals=((23.45, 23.77, -50.0), (69.8, 70.8, -50.0)),
        provenance={"fixture": True},
    )
    request = AutoEditAnalysisRequest(
        asset_id="ast_rc21timing",
        word_timing_policy="adjacent_successor_partition_v1",
        padding_before=0,
        padding_after=0,
    )
    scenes = build_scenes(duration=duration, signals=signals, transcript=derived)
    silence = build_silence_decisions(
        signals=signals,
        transcript=derived,
        config=request,
    )
    highlights = build_highlights(scenes=scenes, top_k=3)

    assert scenes
    assert len(highlights) == 3
    assert silence[0]["conflicts_with_speech"] is True
    assert silence[0]["enabled"] is False
    assert silence[1]["conflicts_with_speech"] is False
    assert silence[1]["enabled"] is True

    cues: list[SubtitleCue] = []
    for segment_index, segment in enumerate(derived.value.segments):
        persisted_words = [
            TranscriptWordRead(
                word_id=f"wrd_{segment_index:02d}{word_index:02d}",
                ordinal=word_index,
                start_seconds=word.start_seconds,
                end_seconds=word.end_seconds,
                text=word.text,
                confidence=word.confidence,
            )
            for word_index, word in enumerate(segment.words)
        ]
        cues.append(
            SubtitleCue(
                cue_id=f"sub_{segment_index:04d}",
                start_seconds=segment.start_seconds,
                end_seconds=segment.end_seconds,
                text=segment.text,
                words=[
                    SubtitleWord(
                        text=word.text,
                        start_seconds=word.start_seconds,
                        end_seconds=word.end_seconds,
                    )
                    for word in persisted_words
                ],
            )
        )

    subtitle_clips = [
        TimelineClip(
            clip_id=f"clip_{index:04d}",
            kind="subtitle",
            label=cue.text,
            source_start=cue.start_seconds,
            source_end=cue.end_seconds,
            timeline_start=cue.start_seconds,
            duration=cue.end_seconds - cue.start_seconds,
        )
        for index, cue in enumerate(cues)
    ]
    timeline = TimelineSnapshot(
        duration_seconds=duration,
        tracks=[
            TimelineTrack(
                track_id="trk_subtitles",
                type="text",
                kind="subtitles",
                label="Derived timing fixture",
                order=0,
                clips=subtitle_clips,
            )
        ],
        metadata={
            "derived_transcript_sha256": derived.derived_transcript_sha256,
            "raw_transcript_sha256": derived.raw_transcript_sha256,
        },
    )
    assert timeline.duration_seconds == duration
    assert len(timeline.tracks[0].clips) == len(cues)

    reframe_keyframes = [
        ReframeKeyframeRead(
            time=scene["start_seconds"], x=0.5, y=0.4, scale=1.0
        )
        for scene in scenes
    ]
    assert all(
        current.time <= following.time
        for current, following in zip(reframe_keyframes, reframe_keyframes[1:])
    )
