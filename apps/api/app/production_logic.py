from __future__ import annotations

import json
import math
import uuid
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from .production_models import MixConfig, SubtitleCue, SubtitleStyle, SubtitleVersionRead
from .timeline_models import TimelineSnapshot


class ProductionContractError(ValueError):
    pass


PROFILE_DIMENSIONS: dict[str, tuple[int, int]] = {
    "review-540x960": (540, 960),
    "vertical-1080x1920": (1080, 1920),
    "landscape-1920x1080": (1920, 1080),
    "square-1080x1080": (1080, 1080),
}

PRODUCTION_VISUAL_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "video/mp4",
    "video/webm",
    "video/quicktime",
}


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:20]}"


def derive_subtitle_cues(snapshot: TimelineSnapshot) -> list[SubtitleCue]:
    clips = sorted(
        (
            clip
            for track in snapshot.tracks
            if track.kind == "subtitles" and not track.disabled
            for clip in track.clips
            if not clip.disabled and clip.label.strip()
        ),
        key=lambda item: (item.timeline_start, item.clip_id),
    )
    cues: list[SubtitleCue] = []
    for clip in clips:
        start = round(clip.timeline_start, 3)
        end = round(min(snapshot.duration_seconds, clip.timeline_start + clip.duration), 3)
        if end - start < 0.05:
            continue
        words = clip.label.split()
        slot = (end - start) / max(1, len(words))
        word_items = [
            {
                "text": word,
                "start_seconds": round(start + index * slot, 3),
                "end_seconds": round(start + (index + 1) * slot, 3),
            }
            for index, word in enumerate(words)
        ]
        cues.append(
            SubtitleCue(
                cue_id=_new_id("sub"),
                start_seconds=start,
                end_seconds=end,
                text=clip.label[:180],
                words=word_items,
            )
        )
    if not cues:
        raise ProductionContractError("timeline has no enabled subtitle cues")
    validate_subtitles(cues, SubtitleStyle(), snapshot.duration_seconds)
    return cues


def validate_subtitles(
    cues: list[SubtitleCue], style: SubtitleStyle, duration_seconds: float
) -> dict[str, Any]:
    previous_end = 0.0
    identifiers: set[str] = set()
    estimated_line_limit = max(12, int((100 - 2 * style.safe_margin_percent) * 10.8 / (style.font_size * 0.56)))
    maximum_characters = estimated_line_limit * style.max_lines
    for cue in cues:
        if cue.cue_id in identifiers:
            raise ProductionContractError("subtitle cue ids must be unique")
        identifiers.add(cue.cue_id)
        if cue.start_seconds < previous_end - 0.034:
            raise ProductionContractError("subtitle cues must be monotonic and non-overlapping")
        if cue.end_seconds > duration_seconds + 0.034:
            raise ProductionContractError("subtitle cue exceeds timeline duration")
        if len(cue.text) > maximum_characters:
            raise ProductionContractError(
                f"subtitle cue {cue.cue_id} exceeds the estimated {style.max_lines}-line safe area"
            )
        previous_end = cue.end_seconds
    return {
        "status": "passed",
        "cue_count": len(cues),
        "estimated_characters_per_line": estimated_line_limit,
        "max_lines": style.max_lines,
        "safe_margin_percent": style.safe_margin_percent,
        "font_family": style.font_family,
        "vietnamese_font_supported": style.font_family.startswith("Noto Sans"),
    }


def validate_music_rights(asset: Any) -> None:
    if asset is None:
        raise ProductionContractError("configured music asset was not found")
    if not str(asset.content_type).startswith("audio/"):
        raise ProductionContractError("music asset must be an audio asset")
    provenance = dict(asset.provenance or {})
    rights_status = str(provenance.get("rights_status", "")).lower()
    if rights_status not in {"owned", "licensed", "public_domain", "royalty_free"}:
        raise ProductionContractError("music asset requires explicit owned or licensed rights metadata")
    if rights_status == "licensed" and not provenance.get("license"):
        raise ProductionContractError("licensed music requires license metadata")


def validate_production_visual_asset(asset: Any) -> str:
    content_type = str(asset.content_type).lower().split(";", 1)[0].strip()
    provenance = dict(getattr(asset, "provenance", {}) or {})
    if provenance.get("production_eligible") is False:
        raise ProductionContractError(
            f"visual asset {asset.asset_id} is a planning fixture and is not production eligible"
        )
    if content_type not in PRODUCTION_VISUAL_CONTENT_TYPES:
        raise ProductionContractError(
            f"visual asset {asset.asset_id} has unsupported production content type: {content_type}"
        )
    return "image" if content_type.startswith("image/") else "video"


def validate_timeline_renderability(
    snapshot: TimelineSnapshot,
    *,
    available_asset_ids: set[str],
) -> dict[str, Any]:
    visual_clips = sorted(
        (
            clip
            for track in snapshot.tracks
            if track.type == "video" and not track.disabled
            for clip in track.clips
            if not clip.disabled and clip.opacity > 0
        ),
        key=lambda item: (item.timeline_start, item.clip_id),
    )
    if not visual_clips:
        raise ProductionContractError("timeline has no enabled visual clips")
    missing = sorted(
        {
            str(clip.asset_id or "<missing>")
            for clip in visual_clips
            if not clip.asset_id or clip.asset_id not in available_asset_ids
        }
    )
    if missing:
        raise ProductionContractError(f"timeline has missing visual assets: {', '.join(str(item) for item in missing)}")

    intervals = sorted((clip.timeline_start, clip.timeline_start + clip.duration) for clip in visual_clips)
    covered_until = 0.0
    gaps: list[dict[str, float]] = []
    for start, end in intervals:
        if start > covered_until + 0.05:
            gaps.append({"start_seconds": round(covered_until, 3), "end_seconds": round(start, 3)})
        covered_until = max(covered_until, end)
    if covered_until < snapshot.duration_seconds - 0.05:
        gaps.append({"start_seconds": round(covered_until, 3), "end_seconds": round(snapshot.duration_seconds, 3)})
    if gaps:
        raise ProductionContractError(f"timeline contains uncovered visual gaps: {gaps}")
    return {
        "status": "passed",
        "visual_clip_count": len(visual_clips),
        "timeline_duration_seconds": snapshot.duration_seconds,
        "missing_assets": [],
        "scene_gaps": [],
    }


def build_timeline_render_manifest(
    *,
    snapshot: TimelineSnapshot,
    subtitles: SubtitleVersionRead,
    mix_config: MixConfig,
    mixed_audio_path: Path,
    asset_paths: dict[str, tuple[Any, Path]],
    profile: str,
    project_name: str,
    project_slug: str,
    niche: str,
    brand_name: str,
) -> dict[str, Any]:
    width, height = PROFILE_DIMENSIONS[profile]
    validate_subtitles(subtitles.cues, subtitles.style, snapshot.duration_seconds)
    validate_timeline_renderability(snapshot, available_asset_ids=set(asset_paths))
    visual_clips: list[dict[str, Any]] = []
    for track in sorted(snapshot.tracks, key=lambda item: item.order):
        if track.type != "video" or track.disabled:
            continue
        for clip in sorted(track.clips, key=lambda item: (item.timeline_start, item.clip_id)):
            if clip.disabled or clip.opacity <= 0 or not clip.asset_id:
                continue
            asset, path = asset_paths[clip.asset_id]
            media_type = validate_production_visual_asset(asset)
            visual_clips.append(
                {
                    "clip_id": clip.clip_id,
                    "track_order": track.order,
                    "type": media_type,
                    "uri": str(path),
                    "timeline_start": clip.timeline_start,
                    "duration": clip.duration,
                    "source_start": clip.source_start,
                    "source_end": clip.source_end,
                    "fit": "cover",
                    "crop": clip.crop.model_dump(mode="json"),
                    "transform": clip.transform.model_dump(mode="json"),
                    "opacity": clip.opacity,
                }
            )
    return {
        "version": "2.0",
        "metadata": {
            "title": f"{project_name} final edit",
            "project": project_slug,
            "niche": niche if niche else "custom",
            "template": "timeline-render-v1",
            "duration_seconds": snapshot.duration_seconds,
            "fps": int(round(snapshot.fps)),
            "width": width,
            "height": height,
            "language": "vi",
        },
        "brand": {
            "name": brand_name,
            "primary_color": "#F5C451",
            "accent_color": "#17B9A6",
        },
        "audio": {
            "mix_uri": str(mixed_audio_path),
            "gain_db": 0,
            "sample_rate": mix_config.sample_rate,
            "ducking_applied": bool(mix_config.music.asset_id),
        },
        "visual_clips": visual_clips,
        "subtitles": [item.model_dump(mode="json") for item in subtitles.cues],
        "subtitle_style": subtitles.style.model_dump(mode="json"),
        "safety": {
            "human_approval_required": True,
            "publishing_allowed": False,
            "external_publish_requested": False,
            "source_media_mutated": False,
        },
    }


class TimelineRenderContractValidator:
    def __init__(self, schema_path: Path):
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        self.validator = Draft202012Validator(schema)

    def validate(self, manifest: dict[str, Any]) -> None:
        errors = sorted(self.validator.iter_errors(manifest), key=lambda item: list(item.path))
        if errors:
            first = errors[0]
            location = ".".join(str(item) for item in first.path) or "$"
            raise ProductionContractError(f"timeline render manifest invalid at {location}: {first.message}")


def amplitude_from_db(db: float) -> float:
    return math.pow(10, db / 20)
