from __future__ import annotations

import re
from typing import Any

from .auto_edit_models import AutoEditAnalysisRequest
from .auto_edit_providers import MediaSignals, ProviderTranscript


_HOOK_WORDS = {
    "quan trọng",
    "cơ hội",
    "lưu ý",
    "quyết định",
    "bằng chứng",
    "điểm nổi bật",
    "thử nghiệm",
}


def _overlap(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    return max(0.0, min(end_a, end_b) - max(start_a, start_b))


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 6)


def build_scenes(
    *, duration: float, signals: MediaSignals, transcript: ProviderTranscript
) -> list[dict[str, Any]]:
    boundary_values = sorted(
        {round(float(timestamp), 6) for timestamp, _ in signals.shot_boundaries if 0 < timestamp < duration}
    )
    points = [0.0, *boundary_values, duration]
    scenes: list[dict[str, Any]] = []
    for ordinal, (start, end) in enumerate(zip(points, points[1:])):
        if end - start < 0.08:
            continue
        matching = [
            segment
            for segment in transcript.segments
            if _overlap(start, end, segment.start_seconds, segment.end_seconds) > 0
        ]
        text = " ".join(segment.text for segment in matching).strip()
        words = re.findall(r"[\wÀ-ỹ]+", text, flags=re.UNICODE)
        speech_seconds = sum(
            _overlap(start, end, segment.start_seconds, segment.end_seconds) for segment in matching
        )
        speech_score = _clamp(speech_seconds / max(end - start, 0.001))
        boundary_score = next(
            (score for timestamp, score in signals.shot_boundaries if abs(timestamp - start) < 0.001),
            0.55 if ordinal else 0.5,
        )
        label = "Mở đầu" if ordinal == 0 else f"Phân đoạn {ordinal + 1}"
        scenes.append(
            {
                "ordinal": ordinal,
                "start_seconds": round(start, 6),
                "end_seconds": round(end, 6),
                "semantic_label": label,
                "description": text[:500] or "Phân đoạn hình ảnh không có lời thoại nhận diện.",
                "subjects": list(dict.fromkeys(word.casefold() for word in words if len(word) >= 5))[:6],
                "quality_score": _clamp(0.62 + 0.18 * speech_score),
                "motion_score": _clamp(float(boundary_score)),
                "speech_score": speech_score,
                "confidence": _clamp(0.55 + 0.2 * float(boundary_score) + 0.2 * speech_score),
                "evidence": {
                    "shot_boundary": ordinal > 0,
                    "transcript_segment_count": len(matching),
                    "vision_used": False,
                    "vision_deferred_to": "V2-05",
                },
            }
        )
    return scenes


def build_silence_decisions(
    *, signals: MediaSignals, transcript: ProviderTranscript, config: AutoEditAnalysisRequest
) -> list[dict[str, Any]]:
    words = [word for segment in transcript.segments for word in segment.words]
    decisions: list[dict[str, Any]] = []
    for raw_start, raw_end, measured_db in signals.silence_intervals:
        start = round(raw_start + config.padding_before, 6)
        end = round(raw_end - config.padding_after, 6)
        conflicts = any(_overlap(start, end, word.start_seconds, word.end_seconds) > 0 for word in words)
        long_enough = end - start >= config.minimum_silence_duration
        enabled = long_enough and not conflicts
        reason = (
            "Disabled because the proposed cut overlaps a spoken word."
            if conflicts
            else "Non-destructive silence cut proposed from audio energy and transcript gaps."
            if long_enough
            else "Disabled because padding leaves less than the minimum silence duration."
        )
        decisions.append(
            {
                "start_seconds": max(0.0, start),
                "end_seconds": max(max(0.0, start) + 0.000001, end),
                "padding_before_seconds": config.padding_before,
                "padding_after_seconds": config.padding_after,
                "enabled": enabled,
                "reason": reason,
                "conflicts_with_speech": conflicts,
                "evidence": {
                    "raw_start": raw_start,
                    "raw_end": raw_end,
                    "measured_db": measured_db,
                    "threshold_db": config.silence_threshold_db,
                    "minimum_duration": config.minimum_silence_duration,
                    "source_media_mutated": False,
                },
            }
        )
    return decisions


def build_highlights(
    *, scenes: list[dict[str, Any]], top_k: int
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for scene in scenes:
        text = str(scene["description"]).casefold()
        hooks = sorted(word for word in _HOOK_WORDS if word in text)
        word_count = len(text.split())
        information_density = _clamp(word_count / max(12.0, (scene["end_seconds"] - scene["start_seconds"]) * 3.2))
        hook_score = min(1.0, len(hooks) * 0.3)
        score = _clamp(
            0.15
            + 0.28 * float(scene["speech_score"])
            + 0.22 * float(scene["motion_score"])
            + 0.20 * information_density
            + 0.15 * hook_score
        )
        duration = float(scene["end_seconds"] - scene["start_seconds"])
        platform = "youtube" if duration > 60 else "facebook_reels"
        reasons = ["speech semantics", "scene motion", "information density"]
        if hooks:
            reasons.append(f"hook keywords: {', '.join(hooks)}")
        candidates.append(
            {
                "scene_ordinal": scene["ordinal"],
                "highlight_score": score,
                "reason": "; ".join(reasons),
                "recommended_start": scene["start_seconds"],
                "recommended_end": scene["end_seconds"],
                "recommended_platform": platform,
                "evidence": {
                    "speech_semantics": True,
                    "audio_proxy": float(scene["speech_score"]),
                    "motion": float(scene["motion_score"]),
                    "information_density": information_density,
                    "hook_keywords": hooks,
                    "vision_used": False,
                },
            }
        )
    selected = sorted(
        candidates,
        key=lambda item: (-float(item["highlight_score"]), int(item["scene_ordinal"])),
    )[:top_k]
    for rank, item in enumerate(selected, start=1):
        item["rank"] = rank
    return selected
