from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from .auto_edit_models import MediaMetadata, SceneRead
from .vision_models import (
    AspectRatio,
    FrameCompositionRead,
    FrameQualityRead,
    ManualCropOverride,
    NormalizedBox,
    ObjectDetectionRead,
    OCRDetectionRead,
    ReframeKeyframeRead,
    ReframePlanRead,
    SubjectObservationRead,
    SubjectTrackRead,
    VisionFrameRead,
    VisionSceneRead,
)
from .vision_providers import ProviderVisionFrame


_ASPECT_VALUES: dict[AspectRatio, float] = {
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "1:1": 1.0,
    "4:5": 4 / 5,
}


def _stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:24]}"


def _subject_position(box: NormalizedBox | None) -> str:
    if box is None:
        return "unknown"
    center_x = box.x + box.width / 2
    center_y = box.y + box.height / 2
    horizontal = "left" if center_x < 0.4 else "right" if center_x > 0.6 else "center"
    if center_y < 0.38:
        return f"upper_{horizontal}"
    return horizontal


def normalize_frames(
    frames: tuple[ProviderVisionFrame, ...], *, provider_key: str, model: str, fingerprint: str
) -> list[VisionFrameRead]:
    normalized: list[VisionFrameRead] = []
    previous_time = -1.0
    for provider_frame in sorted(frames, key=lambda item: item.timestamp_seconds):
        if provider_frame.timestamp_seconds <= previous_time:
            raise ValueError("vision provider frame timestamps must be strictly increasing")
        previous_time = provider_frame.timestamp_seconds
        frame_id = _stable_id("vfr", fingerprint, f"{provider_frame.timestamp_seconds:.6f}")
        normalized.append(
            VisionFrameRead(
                frame_id=frame_id,
                timestamp_seconds=provider_frame.timestamp_seconds,
                evidence_frame_reference=provider_frame.evidence_frame_reference,
                caption=provider_frame.caption,
                scene_description=provider_frame.scene_description,
                semantic_label=provider_frame.semantic_label,
                environment=provider_frame.environment,
                action=provider_frame.action,
                objects=[
                    ObjectDetectionRead(
                        label=item.label,
                        category=item.category,
                        confidence=item.confidence,
                        bounding_box=item.bounding_box,
                        track_hint=item.track_hint,
                    )
                    for item in provider_frame.objects
                ],
                ocr=[
                    OCRDetectionRead(
                        text=item.text,
                        language=item.language,
                        confidence=item.confidence,
                        bounding_box=item.bounding_box,
                    )
                    for item in provider_frame.ocr
                ],
                composition=FrameCompositionRead(
                    primary_subject_box=provider_frame.primary_subject_box,
                    subject_position=_subject_position(provider_frame.primary_subject_box),
                    saliency_box=provider_frame.saliency_box,
                    headroom_ratio=provider_frame.headroom_ratio,
                    visual_balance_score=provider_frame.visual_balance_score,
                    safe_crop=provider_frame.safe_crop,
                ),
                quality=FrameQualityRead(
                    quality_score=provider_frame.quality_score,
                    black_frame=provider_frame.black_frame,
                    blur_score=provider_frame.blur_score,
                    overexposed=provider_frame.overexposed,
                    underexposed=provider_frame.underexposed,
                    low_resolution=provider_frame.low_resolution,
                    watermark_or_logo_detected=provider_frame.watermark_or_logo_detected,
                    frozen_or_duplicate=provider_frame.frozen_or_duplicate,
                    issues=list(provider_frame.quality_issues),
                ),
                confidence=provider_frame.confidence,
                provider_key=provider_key,
                model=model,
            )
        )
    if not normalized:
        raise ValueError("vision provider returned no structured frame evidence")
    return normalized


def build_vision_scenes(
    *, scenes: list[SceneRead], frames: list[VisionFrameRead], fingerprint: str
) -> list[VisionSceneRead]:
    results: list[VisionSceneRead] = []
    for ordinal, scene in enumerate(scenes):
        evidence = [
            frame for frame in frames if scene.start_seconds <= frame.timestamp_seconds < scene.end_seconds
        ]
        if not evidence:
            continue
        labels: dict[str, int] = defaultdict(int)
        subjects: set[str] = set(scene.subjects)
        for frame in evidence:
            labels[frame.semantic_label] += 1
            subjects.update(item.label for item in frame.objects if item.category != "text")
        semantic_label = max(labels, key=lambda key: (labels[key], key))
        results.append(
            VisionSceneRead(
                vision_scene_id=_stable_id("vsc", fingerprint, scene.scene_id),
                scene_id=scene.scene_id,
                ordinal=ordinal,
                start_seconds=scene.start_seconds,
                end_seconds=scene.end_seconds,
                semantic_label=semantic_label,
                description=evidence[0].scene_description,
                subjects=sorted(subjects),
                quality_score=round(sum(item.quality.quality_score for item in evidence) / len(evidence), 6),
                confidence=round(sum(item.confidence for item in evidence) / len(evidence), 6),
                evidence_frame_ids=[item.frame_id for item in evidence],
            )
        )
    return results


def build_subject_tracks(
    *, frames: list[VisionFrameRead], fingerprint: str, minimum_confidence: float
) -> list[SubjectTrackRead]:
    grouped: dict[tuple[str, str], list[tuple[VisionFrameRead, ObjectDetectionRead]]] = defaultdict(list)
    for frame in frames:
        for item in frame.objects:
            if item.confidence < minimum_confidence or item.category in {"text", "logo"}:
                continue
            identity = item.track_hint or item.label.casefold()
            grouped[(identity, item.category)].append((frame, item))
    tracks: list[SubjectTrackRead] = []
    for (identity, category), observations in sorted(grouped.items()):
        observations.sort(key=lambda pair: pair[0].timestamp_seconds)
        first_item = observations[0][1]
        continuity = min(1.0, len(observations) / max(1, len(frames)))
        tracks.append(
            SubjectTrackRead(
                track_id=_stable_id("trk", fingerprint, identity, category),
                label=first_item.label,
                category=category,
                start_seconds=observations[0][0].timestamp_seconds,
                end_seconds=observations[-1][0].timestamp_seconds,
                confidence=round(sum(item.confidence for _, item in observations) / len(observations), 6),
                continuity_score=round(continuity, 6),
                observations=[
                    SubjectObservationRead(
                        timestamp_seconds=frame.timestamp_seconds,
                        bounding_box=item.bounding_box,
                        confidence=item.confidence,
                    )
                    for frame, item in observations
                ],
            )
        )
    return tracks


def _crop_scale(metadata: MediaMetadata, aspect_ratio: AspectRatio) -> float:
    source_aspect = float(metadata.width or 1) / float(metadata.height or 1)
    target_aspect = _ASPECT_VALUES[aspect_ratio]
    if source_aspect > target_aspect:
        crop_fraction = target_aspect / source_aspect
    else:
        crop_fraction = source_aspect / target_aspect
    return round(max(1.0, 1.0 / max(crop_fraction, 0.05)), 6)


def _bounded_ema(
    observations: list[SubjectObservationRead], *, maximum_jump: float, subtitle_safe_area_bottom: float
) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    previous_x: float | None = None
    previous_y: float | None = None
    for observation in observations:
        target_x = observation.bounding_box.x + observation.bounding_box.width / 2
        target_y = observation.bounding_box.y + observation.bounding_box.height / 2
        target_y = min(target_y, max(0.5, 1 - subtitle_safe_area_bottom - 0.05))
        if previous_x is None or previous_y is None:
            current_x, current_y = target_x, target_y
        else:
            proposed_x = previous_x + 0.45 * (target_x - previous_x)
            proposed_y = previous_y + 0.45 * (target_y - previous_y)
            current_x = previous_x + max(-maximum_jump, min(maximum_jump, proposed_x - previous_x))
            current_y = previous_y + max(-maximum_jump, min(maximum_jump, proposed_y - previous_y))
        current_x = max(0.0, min(1.0, current_x))
        current_y = max(0.0, min(1.0, current_y))
        result.append((observation.timestamp_seconds, current_x, current_y))
        previous_x, previous_y = current_x, current_y
    return result


def build_reframe_plans(
    *,
    frames: list[VisionFrameRead],
    tracks: list[SubjectTrackRead],
    metadata: MediaMetadata,
    aspect_ratios: list[AspectRatio],
    manual_overrides: list[ManualCropOverride],
    minimum_tracking_confidence: float,
    subtitle_safe_area_bottom: float,
    maximum_jump: float,
    fingerprint: str,
) -> list[ReframePlanRead]:
    del frames
    overrides_by_aspect: dict[str, list[ManualCropOverride]] = defaultdict(list)
    for item in manual_overrides:
        overrides_by_aspect[item.aspect_ratio].append(item)
    viable = [
        track
        for track in tracks
        if track.confidence >= minimum_tracking_confidence and track.observations
    ]
    viable.sort(key=lambda item: (item.confidence * item.continuity_score, item.confidence), reverse=True)
    primary = viable[0] if viable else None
    plans: list[ReframePlanRead] = []
    for aspect_ratio in aspect_ratios:
        scale = _crop_scale(metadata, aspect_ratio)
        overrides = sorted(overrides_by_aspect.get(aspect_ratio, []), key=lambda item: item.time)
        if overrides:
            keyframes = [
                ReframeKeyframeRead(time=item.time, x=item.x, y=item.y, scale=item.scale)
                for item in overrides
            ]
            strategy = "manual_override"
            confidence = 1.0
            fallback = "none"
            needs_attention = False
            smoothing = "none"
            subject_track_id = primary.track_id if primary else None
        elif primary:
            keyframes = [
                ReframeKeyframeRead(time=time, x=round(x, 6), y=round(y, 6), scale=scale)
                for time, x, y in _bounded_ema(
                    primary.observations,
                    maximum_jump=maximum_jump,
                    subtitle_safe_area_bottom=subtitle_safe_area_bottom,
                )
            ]
            strategy = "subject_track"
            confidence = round(primary.confidence * primary.continuity_score, 6)
            fallback = "none"
            needs_attention = confidence < 0.7
            smoothing = "bounded_ema"
            subject_track_id = primary.track_id
        else:
            duration = float(metadata.duration_seconds or 0)
            times = [0.0] if duration <= 0 else [0.0, round(max(0.0, duration - 0.001), 3)]
            keyframes = [ReframeKeyframeRead(time=time, x=0.5, y=0.5, scale=scale) for time in times]
            strategy = "center_crop"
            confidence = 0.0
            fallback = "center_crop"
            needs_attention = True
            smoothing = "none"
            subject_track_id = None
        plans.append(
            ReframePlanRead(
                reframe_id=_stable_id("rfr", fingerprint, aspect_ratio),
                aspect_ratio=aspect_ratio,
                strategy=strategy,
                subject_track_id=subject_track_id,
                keyframes=keyframes,
                smoothing=smoothing,
                maximum_jump=maximum_jump,
                subtitle_safe_area_bottom=subtitle_safe_area_bottom,
                confidence=confidence,
                fallback=fallback,
                needs_attention=needs_attention,
                manual_override_applied=bool(overrides),
            )
        )
    return plans


def rank_best_frames(frames: list[VisionFrameRead]) -> tuple[list[str], list[str]]:
    ranked = sorted(
        frames,
        key=lambda item: (
            item.quality.quality_score * 0.55
            + item.composition.visual_balance_score * 0.25
            + item.confidence * 0.2,
            -item.timestamp_seconds,
        ),
        reverse=True,
    )
    best = [item.frame_id for item in ranked[: min(5, len(ranked))]]
    thumbnails = [
        item.frame_id
        for item in ranked
        if not item.quality.black_frame and not item.quality.frozen_or_duplicate
    ][: min(3, len(ranked))]
    return best, thumbnails
