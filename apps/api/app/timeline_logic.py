from __future__ import annotations

import copy
import uuid
from collections.abc import Iterable
from typing import Any

from .auto_edit_models import AutoEditAnalysisRead
from .media_intelligence_models import MediaPlanRead
from .platform_models import AssetRead
from .timeline_models import (
    TimelineClip,
    TimelineOperation,
    TimelineSnapshot,
    TimelineTrack,
)


class TimelineEditError(ValueError):
    pass


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def build_initial_timeline(
    *,
    analysis: AutoEditAnalysisRead,
    source_asset: AssetRead,
    media_plan: MediaPlanRead | None,
    media_assets: dict[str, AssetRead],
) -> TimelineSnapshot:
    if analysis.status != "succeeded":
        raise TimelineEditError("Auto Edit analysis must be succeeded before building a timeline")
    if analysis.source_media.duration_seconds is None or analysis.source_media.duration_seconds <= 0:
        raise TimelineEditError("source media must have a positive duration before building a timeline")
    source_duration = float(analysis.source_media.duration_seconds)
    cuts = sorted(
        (
            max(0.0, item.start_seconds - item.padding_before_seconds),
            min(source_duration, item.end_seconds + item.padding_after_seconds),
        )
        for item in analysis.silence_decisions
        if item.enabled and not item.conflicts_with_speech
    )
    source_windows: list[tuple[float, float, dict[str, Any]]] = []
    for scene in analysis.scenes:
        for start, end in _subtract_intervals(scene.start_seconds, scene.end_seconds, cuts):
            if end - start < 0.05:
                continue
            source_windows.append(
                (
                    start,
                    end,
                    {
                        "scene_id": scene.scene_id,
                        "scene_ordinal": scene.ordinal,
                        "semantic_label": scene.semantic_label,
                        "quality_score": scene.quality_score,
                    },
                )
            )
    if not source_windows:
        source_windows = [(0.0, source_duration, {"fallback": "full-source"})]

    source_clips: list[TimelineClip] = []
    audio_clips: list[TimelineClip] = []
    cursor = 0.0
    for ordinal, (start, end, evidence) in enumerate(source_windows):
        duration = round(end - start, 6)
        metadata = {
            **evidence,
            "source_checksum_sha256": source_asset.checksum_sha256,
            "content_type": source_asset.content_type,
            "object_key": source_asset.object_key,
            "original_evidence": True,
        }
        source_clips.append(
            TimelineClip(
                clip_id=_new_id("clip"),
                kind="source",
                label=f"Cảnh {ordinal + 1}",
                asset_id=source_asset.asset_id,
                source_start=round(start, 6),
                source_end=round(end, 6),
                timeline_start=round(cursor, 6),
                duration=duration,
                metadata=metadata,
            )
        )
        audio_clips.append(
            TimelineClip(
                clip_id=_new_id("clip"),
                kind="original_audio",
                label=f"Âm thanh gốc {ordinal + 1}",
                asset_id=source_asset.asset_id,
                source_start=round(start, 6),
                source_end=round(end, 6),
                timeline_start=round(cursor, 6),
                duration=duration,
                metadata=metadata,
            )
        )
        cursor += duration
    main_duration = max(0.1, round(cursor, 6))

    subtitle_clips: list[TimelineClip] = []
    if analysis.transcript:
        for segment in analysis.transcript.segments:
            for source_clip in source_clips:
                overlap_start = max(segment.start_seconds, source_clip.source_start)
                overlap_end = min(segment.end_seconds, source_clip.source_end)
                if overlap_end - overlap_start < 0.05:
                    continue
                mapped_start = source_clip.timeline_start + (overlap_start - source_clip.source_start)
                duration = overlap_end - overlap_start
                subtitle_clips.append(
                    TimelineClip(
                        clip_id=_new_id("clip"),
                        kind="subtitle",
                        label=segment.text[:120],
                        asset_id=None,
                        source_start=round(overlap_start, 6),
                        source_end=round(overlap_end, 6),
                        timeline_start=round(mapped_start, 6),
                        duration=round(duration, 6),
                        metadata={
                            "transcript_id": analysis.transcript.transcript_id,
                            "segment_id": segment.segment_id,
                            "language": analysis.transcript.language,
                            "confidence": segment.confidence,
                            "editable_in": "V2-08",
                        },
                    )
                )

    broll_clips: list[TimelineClip] = []
    if media_plan:
        provenance_by_media_id = {item.media_asset_id: item for item in media_plan.media_assets}
        for item in media_plan.items:
            if not item.selected_media_asset_id:
                continue
            media_evidence = provenance_by_media_id.get(item.selected_media_asset_id)
            if media_evidence is None:
                continue
            asset = media_assets.get(media_evidence.asset_id)
            if asset is None:
                continue
            start = _map_source_time(item.broll.placement_start_seconds, source_clips)
            end = _map_source_time(item.broll.placement_end_seconds, source_clips)
            if end <= start:
                end = min(main_duration, start + max(0.5, item.broll.placement_end_seconds - item.broll.placement_start_seconds))
            remaining = main_duration - start
            if remaining < 0.05:
                continue
            duration = max(0.05, min(remaining, end - start))
            source_end = min(float(media_evidence.duration_seconds or duration), duration)
            if source_end <= 0:
                source_end = duration
            broll_clips.append(
                TimelineClip(
                    clip_id=_new_id("clip"),
                    kind=("generated" if media_evidence.source_type.startswith("ai_") else "broll"),
                    label=item.broll.search_query[:120],
                    asset_id=asset.asset_id,
                    source_start=0,
                    source_end=round(source_end, 6),
                    timeline_start=round(start, 6),
                    duration=round(source_end, 6),
                    metadata={
                        "media_plan_id": media_plan.media_plan_id,
                        "media_plan_item_id": item.media_plan_item_id,
                        "media_asset_id": media_evidence.media_asset_id,
                        "rights_status": media_evidence.rights_status,
                        "license": media_evidence.license,
                        "production_eligible": media_evidence.production_eligible,
                        "publishing_allowed": False,
                        "content_type": asset.content_type,
                        "object_key": asset.object_key,
                    },
                )
            )

    tracks = [
        TimelineTrack(
            track_id=_new_id("trk"),
            type="video",
            kind="source",
            label="Video gốc",
            order=0,
            clips=source_clips,
        ),
        TimelineTrack(
            track_id=_new_id("trk"),
            type="video",
            kind="broll",
            label="B-roll",
            order=1,
            clips=broll_clips,
        ),
        TimelineTrack(
            track_id=_new_id("trk"),
            type="text",
            kind="subtitles",
            label="Bản chép lời",
            order=2,
            clips=subtitle_clips,
        ),
        TimelineTrack(
            track_id=_new_id("trk"),
            type="audio",
            kind="original_audio",
            label="Âm thanh gốc",
            order=3,
            clips=audio_clips,
        ),
        TimelineTrack(
            track_id=_new_id("trk"),
            type="metadata",
            kind="metadata",
            label="Dấu mốc AI",
            order=4,
            locked=True,
            clips=[],
        ),
    ]
    return TimelineSnapshot(
        duration_seconds=main_duration,
        tracks=tracks,
        metadata={
            "source_analysis_id": analysis.analysis_id,
            "source_media_plan_id": media_plan.media_plan_id if media_plan else None,
            "source_asset_id": source_asset.asset_id,
            "source_duration_seconds": source_duration,
            "silence_decisions_applied": sum(
                item.enabled and not item.conflicts_with_speech for item in analysis.silence_decisions
            ),
            "highlight_ids": [item.highlight_id for item in analysis.highlights],
            "preview_profile": "proxy-540x960-no-audio-v1",
            "approval_invalidates_on_change": True,
        },
    )


def apply_operations(
    snapshot: TimelineSnapshot,
    operations: Iterable[TimelineOperation],
) -> TimelineSnapshot:
    payload = copy.deepcopy(snapshot.model_dump(mode="json"))
    tracks: list[dict[str, Any]] = payload["tracks"]
    for operation in operations:
        if operation.type == "set_track_state":
            track = _find_track(tracks, operation.track_id or "")
            if operation.locked is not None:
                track["locked"] = operation.locked
            if operation.muted is not None:
                track["muted"] = operation.muted
            if operation.disabled is not None:
                track["disabled"] = operation.disabled
            continue

        track, clip, clip_index = _find_clip(tracks, operation.clip_id or "")
        if track["locked"]:
            raise TimelineEditError(f"track {track['track_id']} is locked")

        if operation.type == "move":
            if operation.timeline_start is not None:
                clip["timeline_start"] = operation.timeline_start
            if operation.target_track_id and operation.target_track_id != track["track_id"]:
                target = _find_track(tracks, operation.target_track_id)
                if target["locked"]:
                    raise TimelineEditError(f"track {target['track_id']} is locked")
                if target["type"] != track["type"]:
                    raise TimelineEditError("clips can only move between tracks of the same type")
                track["clips"].pop(clip_index)
                target["clips"].append(clip)
        elif operation.type == "trim":
            source_start = operation.source_start if operation.source_start is not None else clip["source_start"]
            source_end = operation.source_end if operation.source_end is not None else clip["source_end"]
            if source_end <= source_start:
                raise TimelineEditError("trim must preserve a positive source window")
            clip["source_start"] = source_start
            clip["source_end"] = source_end
            clip["duration"] = round((source_end - source_start) / clip["speed"], 6)
            if operation.timeline_start is not None:
                clip["timeline_start"] = operation.timeline_start
        elif operation.type == "split":
            split_at = float(operation.at_seconds or 0)
            start = float(clip["timeline_start"])
            end = start + float(clip["duration"])
            if split_at <= start + 0.02 or split_at >= end - 0.02:
                raise TimelineEditError("split point must be inside the clip")
            left_duration = split_at - start
            source_split = float(clip["source_start"]) + left_duration * float(clip["speed"])
            right = copy.deepcopy(clip)
            right["clip_id"] = _new_id("clip")
            right["label"] = f"{clip['label']} · phần 2"
            right["source_start"] = round(source_split, 6)
            right["timeline_start"] = round(split_at, 6)
            right["duration"] = round(end - split_at, 6)
            clip["source_end"] = round(source_split, 6)
            clip["duration"] = round(left_duration, 6)
            track["clips"].insert(clip_index + 1, right)
        elif operation.type == "delete":
            track["clips"].pop(clip_index)
        elif operation.type == "reorder":
            track["clips"].pop(clip_index)
            target_index = min(int(operation.target_index or 0), len(track["clips"]))
            track["clips"].insert(target_index, clip)
        elif operation.type == "disable":
            clip["disabled"] = bool(operation.disabled)
        elif operation.type == "duplicate":
            duplicate = copy.deepcopy(clip)
            duplicate["clip_id"] = _new_id("clip")
            duplicate["label"] = f"{clip['label']} · bản sao"
            duplicate["timeline_start"] = (
                operation.timeline_start
                if operation.timeline_start is not None
                else round(float(clip["timeline_start"]) + float(clip["duration"]), 6)
            )
            target = track
            if operation.target_track_id and operation.target_track_id != track["track_id"]:
                target = _find_track(tracks, operation.target_track_id)
                if target["locked"] or target["type"] != track["type"]:
                    raise TimelineEditError("duplicate target track is not editable or compatible")
            target["clips"].append(duplicate)
        elif operation.type == "set_clip_properties":
            if operation.opacity is not None:
                clip["opacity"] = operation.opacity
            if operation.volume is not None:
                clip["volume"] = operation.volume
            if operation.crop is not None:
                clip["crop"] = operation.crop.model_dump(mode="json")
            if operation.transform is not None:
                clip["transform"] = operation.transform.model_dump(mode="json")
            if operation.speed is not None:
                clip["speed"] = operation.speed
                clip["duration"] = round(
                    (float(clip["source_end"]) - float(clip["source_start"])) / operation.speed,
                    6,
                )
        else:  # pragma: no cover - Pydantic constrains the operation type.
            raise TimelineEditError(f"unsupported timeline operation: {operation.type}")

    payload["duration_seconds"] = max(
        0.1,
        round(
            max(
                (
                    float(clip["timeline_start"]) + float(clip["duration"])
                    for track in tracks
                    for clip in track["clips"]
                    if not clip["disabled"] and not track["disabled"]
                ),
                default=0.1,
            ),
            6,
        ),
    )
    payload["source_media_mutated"] = False
    payload["publish_requested"] = False
    return TimelineSnapshot.model_validate(payload)


def _find_track(tracks: list[dict[str, Any]], track_id: str) -> dict[str, Any]:
    for track in tracks:
        if track["track_id"] == track_id:
            return track
    raise TimelineEditError(f"track not found: {track_id}")


def _find_clip(
    tracks: list[dict[str, Any]], clip_id: str
) -> tuple[dict[str, Any], dict[str, Any], int]:
    for track in tracks:
        for index, clip in enumerate(track["clips"]):
            if clip["clip_id"] == clip_id:
                return track, clip, index
    raise TimelineEditError(f"clip not found: {clip_id}")


def _subtract_intervals(
    start: float,
    end: float,
    cuts: Iterable[tuple[float, float]],
) -> list[tuple[float, float]]:
    windows = [(float(start), float(end))]
    for cut_start, cut_end in cuts:
        next_windows: list[tuple[float, float]] = []
        for window_start, window_end in windows:
            if cut_end <= window_start or cut_start >= window_end:
                next_windows.append((window_start, window_end))
                continue
            if cut_start > window_start:
                next_windows.append((window_start, min(window_end, cut_start)))
            if cut_end < window_end:
                next_windows.append((max(window_start, cut_end), window_end))
        windows = next_windows
    return windows


def _map_source_time(source_time: float, source_clips: list[TimelineClip]) -> float:
    for clip in source_clips:
        if clip.source_start <= source_time <= clip.source_end:
            return clip.timeline_start + (source_time - clip.source_start) / clip.speed
    earlier = [clip for clip in source_clips if clip.source_end < source_time]
    if earlier:
        last = earlier[-1]
        return last.timeline_start + last.duration
    return 0.0
