"""Editorial segment scheduling. No word alignment, speech repair or authority."""
from __future__ import annotations
import copy
import hashlib
import math
from .content_service import canonical_bytes
from .production_logic import ProductionContractError
from .timeline_models import TimelineSnapshot


def narration_plan(document):
    """TTS sentence units may cross visual/caption boundaries (max 2000 chars)."""
    units, group = [], []
    for index, scene in enumerate(document.scenes):
        if not scene.narration.strip():
            continue
        group.append(index)
        joined = " ".join(document.scenes[i].narration for i in group)
        if joined.rstrip().endswith((".", "!", "?", "…")) or index == len(document.scenes)-1 or len(joined) >= 1000:
            first, last = document.scenes[group[0]], document.scenes[group[-1]]
            text = document.script[first.script_start:last.script_end] if all(
                document.scenes[i].script_start is not None for i in group) else joined
            if " ".join(text.split()) != " ".join(joined.split()):
                text = joined  # manually reordered/edited scenes; never stale source slice
            if len(text) > 2000:
                raise ProductionContractError("NARRATION_UNIT_ADJUSTMENT_REQUIRED")
            units.append({"unit_id": f"narration_{len(units):04d}", "text": text,
                "text_sha256": hashlib.sha256(text.encode()).hexdigest(), "scene_indices": group,
                "script_start": first.script_start, "script_end": last.script_end})
            group = []
    if group:
        raise ProductionContractError("NARRATION_PLAN_INCOMPLETE")
    return {"version": 1, "units": units, "scenes": [{"scene_id": s.scene_id,
        "duration_mode": s.duration_mode, "pause_after_seconds": s.pause_after_seconds} for s in document.scenes],
        "cue_timing_source": "estimated_editorial_segment_schedule_NOT_word_alignment"}


def reflow_snapshot(snapshot: TimelineSnapshot, narration: dict) -> TimelineSnapshot:
    """Create a new draft from decoded PCM durations; never mutate approved bytes."""
    value = copy.deepcopy(snapshot.model_dump(mode="json"))
    plan = value["metadata"].get("narration_plan")
    if not plan or narration.get("plan_sha256") != hashlib.sha256(canonical_bytes(plan)).hexdigest():
        raise ProductionContractError("NARRATION_PLAN_CHANGED")
    timing = narration.get("timing", [])
    if len(timing) != len(plan["units"]):
        raise ProductionContractError("MEASURED_NARRATION_INCOMPLETE")
    visuals = next(t["clips"] for t in value["tracks"] if t["track_id"] == "trk_storyboard")
    captions = next(t["clips"] for t in value["tracks"] if t["kind"] == "subtitles")
    caption_map = {c["metadata"]["scene_index"]: c for c in captions}
    measured = {}
    for unit, observation in zip(plan["units"], timing, strict=True):
        duration = observation.get("rendered_audio_duration_seconds")
        if (observation.get("text_sha256") != unit["text_sha256"] or
            observation.get("audio_duration_source") != "decoded_pcm_sample_count" or
            observation.get("applied_timing_speedup") != 1 or not isinstance(duration,(int,float)) or
            not math.isfinite(duration) or duration <= 0):
            raise ProductionContractError("MEASURED_NARRATION_INVALID")
        indices = unit["scene_indices"]
        total = sum(len(caption_map[i]["label"].split()) for i in indices)
        for i in indices:
            # Editorial allocation within a measured sentence, explicitly NOT
            # measured word/cue alignment. The complete TTS sentence stays intact.
            measured[i] = duration * len(caption_map[i]["label"].split()) / total
    cursor = 0.0
    for i, (clip, policy) in enumerate(zip(visuals, plan["scenes"], strict=True)):
        speech = measured.get(i, 0)
        pause = policy["pause_after_seconds"]
        proposed = max(0.5, speech+pause)
        duration = clip["duration"] if policy["duration_mode"] == "locked" else proposed
        if speech+pause > duration+0.001 or duration > 30:
            raise ProductionContractError("NARRATION_DURATION_ADJUSTMENT_REQUIRED: locked scene/audio exceeds bounds; no automatic speedup")
        if clip["kind"] == "source":
            # Never extend beyond the already validated video source window.
            if duration > clip["duration"]+0.001:
                raise ProductionContractError("VIDEO_REFLOW_SOURCE_BOUNDS_REVIEW_REQUIRED")
            clip["source_end"] = clip["source_start"]+duration*clip["speed"]
        clip["timeline_start"], clip["duration"] = round(cursor,6), round(duration,6)
        if i in caption_map:
            cue = caption_map[i]
            cue.update(timeline_start=round(cursor,6), duration=round(speech,6), source_end=round(speech,6))
            cue["metadata"]["timing_source"] = plan["cue_timing_source"]
        cursor += duration
    if cursor > 180:
        raise ProductionContractError("REFLOW_DURATION_LIMIT")
    for track in value["tracks"]:
        if track["kind"] == "original_audio":
            for clip in track["clips"]:
                visual = next(c for c in visuals if c["metadata"]["scene_id"] == clip["metadata"]["scene_id"])
                for key in ("timeline_start","duration","source_end"):
                    clip[key] = visual[key]
    value["duration_seconds"] = round(cursor,6)
    value["metadata"]["narration_reflow"] = {"source": "decoded_pcm_sample_count",
        "observation_sha256": hashlib.sha256(canonical_bytes(narration)).hexdigest(),
        "word_alignment": "NOT_AVAILABLE", "policy": "preserve_locked_durations_explicit_pauses",
        "measured_unit_durations": [t["rendered_audio_duration_seconds"] for t in timing]}
    return TimelineSnapshot.model_validate(value)
