"""Reviewable supporting-media evidence and canonical timeline placement.

Ranking uses saved, attributed metadata only. It neither calls providers nor
promotes filenames/tags into semantic Vision evidence.
"""
from __future__ import annotations

import math
import re
import uuid
from typing import Any

from pydantic import Field, model_validator

from .models import StrictModel
from .timeline_logic import TimelineEditError
from .timeline_models import TimelineClip, TimelineSnapshot, TimelineTrack
from .media_frame_facts import PixelAssetSummary


class BrollApplyRequest(StrictModel):
    expected_version: int = Field(ge=1)
    item_ids: list[str] = Field(min_length=1, max_length=200)
    replace_plan_clips: bool = False

    @model_validator(mode="after")
    def unique_items(self):
        if len(set(self.item_ids)) != len(self.item_ids):
            raise ValueError("B-roll selections must be unique")
        return self


def tokens(value: str) -> set[str]:
    return {word.casefold() for word in re.findall(r"[^\W_]+", value) if len(word) >= 3}


def supporting_candidates(assets, analysis, query: str) -> list[dict[str, Any]]:
    wanted = tokens(query)
    result = []
    for asset in assets:
        if asset.project_id != analysis.project_id or asset.workspace_id != analysis.workspace_id:
            continue
        if asset.asset_id == analysis.asset_id or asset.asset_class in {"render", "metadata"}:
            continue
        if asset.kind in {"logo", "thumbnail", "subtitle"}:
            continue
        if asset.content_type not in {"image/png", "image/jpeg", "image/webp"} and not asset.content_type.startswith("video/"):
            continue
        rights = asset.provenance.get("rights_status", "unknown")
        if rights == "restricted":
            continue
        metadata = asset.provenance.get("media_metadata") or {}
        duration = metadata.get("duration_seconds")
        if asset.content_type.startswith("video/") and (not isinstance(duration, (float, int)) or not math.isfinite(duration) or duration <= 0):
            continue
        tier = "internal_library" if asset.provenance.get("source_type") == "internal_library" else "user_asset"
        if tier == "internal_library" and rights not in {"owned", "licensed", "verified"}:
            continue
        tags = asset.provenance.get("tags") or []
        if not isinstance(tags, list):
            tags = []
        description = str(asset.provenance.get("description") or "")
        available = tokens(" ".join([asset.filename, description, *[str(tag) for tag in tags]]))
        overlap = sorted(wanted & available)
        score = len(overlap) / max(1, len(wanted))
        measured=None
        if asset.provenance.get('pixel_quality_summary'):
            measured=PixelAssetSummary.model_validate(asset.provenance['pixel_quality_summary'])
            if measured.source_sha256!=asset.checksum_sha256 or any(frame.source_sha256!=asset.checksum_sha256 for frame in measured.frames):
                raise ValueError('supporting pixel observations source checksum mismatch')
        result.append({"asset_id": asset.asset_id, "filename": asset.filename,
            "checksum_sha256": asset.checksum_sha256, "source_type": tier,
            "rights_status": rights, "license": asset.provenance.get("license", "unknown"),
            "content_type": asset.content_type, "duration_seconds": duration,
            "width": metadata.get("width"), "height": metadata.get("height"),
            "relevance_score": round(score, 6), "confidence": None,
            "score_basis": "lexical overlap in saved filename, description and tags; not semantic Vision",
            "matched_tokens": overlap, "needs_attention": not overlap or rights == "unknown",
            "provider": asset.provenance.get("provider", "user-upload"),
            "source_reference": asset.provenance.get("source_reference", f"asset://{asset.asset_id}"),
            "generation_provenance": asset.provenance.get("generation_provenance", {}),
            "pixel_quality_summary":measured.model_dump(mode='json') if measured else None,
            "quality_score":measured.heuristic_quality_score if measured else None,
            "quality_basis":"uncalibrated sampled pixel sharpness/brightness heuristic" if measured else None,
            "fixture": bool(asset.provenance.get("fixture")), "provider_dispatches": 0})
    return sorted(result, key=lambda item: (-item["relevance_score"],-item['quality_score'] if item['quality_score'] is not None else 0,item["asset_id"]))


def choose_supporting_strategy(payload, candidates, *, stock, image, video, preferred_type):
    """An irrelevant uploaded file stays selectable but does not win automatically."""
    for tier in payload.resolver_priority:
        if tier in {"user_asset", "internal_library"}:
            candidate = next((item for item in candidates if item["source_type"] == tier and item["relevance_score"] > 0), None)
            if candidate:
                return "user_asset", candidate
        elif tier == "licensed_stock" and payload.allow_stock and stock:
            return "stock_video" if preferred_type == "video" else "stock_image", None
        elif tier == "ai_image" and payload.allow_ai_image and image:
            return "ai_image", None
        elif tier == "ai_video" and payload.allow_ai_video and video:
            return "ai_video", None
        elif tier == "motion_graphic" and payload.allow_ai_image and image:
            return "motion_graphic", None
    # Keep the original footage visible until an editor selects supporting media.
    return "user_asset", None


def place_broll(snapshot: TimelineSnapshot, plan, selections, assets, *, replace_plan_clips=False):
    """Map source placements through the existing trim/cut/reorder/speed decisions."""
    output = snapshot.model_copy(deep=True)
    target = next((track for track in output.tracks if track.type == "video" and track.kind == "broll"), None)
    if target is not None and target.locked:
        raise TimelineEditError("unlock the B-roll track before applying selections")
    if target is None:
        if len(output.tracks) >= 32:
            raise TimelineEditError("timeline track limit reached")
        # Video compositing follows track order. Place above source, below text.
        insert = next((index for index, track in enumerate(output.tracks) if track.type != "video"), len(output.tracks))
        target = TimelineTrack(track_id="trk_" + uuid.uuid4().hex[:20], type="video", kind="broll", label="B-roll", order=insert)
        output.tracks.insert(insert, target)
        for index, track in enumerate(output.tracks):
            track.order = index
    if target.disabled:
        raise TimelineEditError("enable the B-roll track before applying selections")
    selected_ids = {item.media_plan_item_id for item, _ in selections}
    old = [clip for clip in target.clips if clip.metadata.get("media_plan_id") == plan.media_plan_id and clip.metadata.get("media_plan_item_id") in selected_ids]
    if old and not replace_plan_clips:
        raise TimelineEditError("selected B-roll already exists; explicitly replace its plan clips")
    if replace_plan_clips:
        target.clips = [clip for clip in target.clips if clip not in old]
    primary = [clip for track in output.tracks if track.type == "video" and track.kind == "source" and not track.disabled
        for clip in track.clips if not clip.disabled and clip.asset_id == snapshot.metadata.get("source_asset_id")]
    additions = []
    for item, evidence in selections:
        asset = assets[evidence.asset_id]
        is_image = asset.content_type.startswith("image/")
        metadata = asset.provenance.get("media_metadata") or {}
        measured_duration = metadata.get("duration_seconds")
        if not is_image and (not isinstance(measured_duration, (float, int)) or not math.isfinite(measured_duration) or measured_duration <= 0):
            raise TimelineEditError("B-roll video needs measured source duration")
        mapped = 0
        for source in primary:
            start = max(source.source_start, item.broll.placement_start_seconds)
            end = min(source.source_end, item.broll.placement_end_seconds)
            if end - start < .05:
                continue
            mapped += 1
            duration = (end - start) / source.speed
            if not is_image:
                duration = min(duration, measured_duration)
            position = source.timeline_start + (start - source.source_start) / source.speed
            additions.append(TimelineClip(clip_id="clip_" + uuid.uuid4().hex[:20], kind="image" if is_image else "broll",
                label=item.broll.search_query[:120], asset_id=asset.asset_id,
                source_start=0, source_end=None if is_image else duration,
                timeline_start=round(position, 6), duration=round(duration, 6), volume=0,
                metadata={"media_plan_id": plan.media_plan_id, "media_plan_fingerprint": plan.fingerprint,
                    "media_plan_item_id": item.media_plan_item_id, "media_asset_id": evidence.media_asset_id,
                    "source_asset_sha256": asset.checksum_sha256, "content_type": asset.content_type,
                    "object_key": asset.object_key, "rights_status": evidence.rights_status, "license": evidence.license,
                    "generation_provenance": evidence.generation_provenance, "source_reference": evidence.source_reference,
                    "publishing_allowed": evidence.publishing_allowed, "production_eligible": evidence.production_eligible,
                    "broll_intent": item.broll.broll_intent, "placement_source_window": [start, end],
                    "original_audio_preserved": True, "provider_dispatches": 0}))
        if not mapped:
            raise TimelineEditError("selected B-roll placement no longer overlaps the retained footage")
    for index, clip in enumerate(additions):
        for existing in [*target.clips, *additions[:index]]:
            if not existing.disabled and min(clip.timeline_start + clip.duration, existing.timeline_start + existing.duration) - max(clip.timeline_start, existing.timeline_start) > .000001:
                raise TimelineEditError("B-roll placement overlaps another clip; review or trim the existing clip")
    target.clips.extend(additions)
    target.clips.sort(key=lambda clip: (clip.timeline_start, clip.clip_id))
    if any(clip.kind == "image" for clip in additions):
        output.schema_version = "1.1"
    output.metadata["broll_review"] = {"media_plan_id": plan.media_plan_id, "item_ids": sorted(selected_ids),
        "human_approval_required": True, "source_media_mutated": False}
    return TimelineSnapshot.model_validate(output.model_dump(mode="json"))


async def apply_broll(service, project_id, media_plan_id, payload, actor_ref):
    timeline = await service.repository.get_timeline(project_id)
    plan = await service.media_repository.get_plan(media_plan_id)
    if timeline is None or plan is None or plan.project_id != project_id:
        raise KeyError(media_plan_id)
    if plan.configuration.purpose != "supporting_broll" or plan.status != "draft":
        raise TimelineEditError("select a ready supporting B-roll plan")
    if timeline.source_analysis_id != plan.analysis_id:
        raise TimelineEditError("B-roll plan uses another source analysis")
    revision = timeline.snapshot.metadata.get("transcript_revision") or {}
    if plan.provenance.get("transcript_id") != revision.get("transcript_id"):
        raise TimelineEditError("B-roll plan uses another transcript version")
    analysis = await service.auto_edit_repository.get_analysis(plan.analysis_id, transcript_id=revision.get("transcript_id"))
    source = await service.auto_edit_repository.get_asset(analysis.asset_id) if analysis else None
    if source is None or source.project_id != project_id or source.checksum_sha256 != plan.provenance.get("source_asset_sha256"):
        raise TimelineEditError("B-roll plan source checksum is stale")
    by_id = {item.media_plan_item_id: item for item in plan.items}
    evidence_by_id = {item.media_asset_id: item for item in plan.media_assets}
    assets = {}
    selections = []
    for item_id in payload.item_ids:
        item = by_id.get(item_id)
        evidence = evidence_by_id.get(item.selected_media_asset_id) if item else None
        if item is None or evidence is None or item.status != "resolved":
            raise TimelineEditError("all selected B-roll items must be resolved")
        asset = await service.auto_edit_repository.get_asset(evidence.asset_id)
        if asset is None or asset.project_id != project_id or asset.workspace_id != plan.workspace_id:
            raise KeyError(evidence.asset_id)
        if evidence.provenance.get("asset_checksum_sha256") != asset.checksum_sha256:
            raise TimelineEditError("selected B-roll checksum differs from resolved evidence")
        if evidence.rights_status == "restricted" or asset.provenance.get("rights_status") == "restricted":
            raise TimelineEditError("restricted B-roll cannot be applied")
        assets[asset.asset_id] = asset
        selections.append((item, evidence))
    snapshot = place_broll(timeline.snapshot, plan, selections, assets, replace_plan_clips=payload.replace_plan_clips)
    service.validator.validate(snapshot)
    return await service.repository.commit_mutation(project_id=project_id, expected_version=payload.expected_version,
        snapshot=snapshot, mutation={"type": "broll-selection", "media_plan_id": media_plan_id,
            "item_ids": payload.item_ids, "replace_plan_clips": payload.replace_plan_clips,
            "source_media_mutated": False, "publish_requested": False}, actor_ref=actor_ref)
