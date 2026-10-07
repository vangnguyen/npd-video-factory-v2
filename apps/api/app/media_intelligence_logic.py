from __future__ import annotations

import hashlib
import re
from decimal import Decimal

from .auto_edit_models import AutoEditAnalysisRead, SceneRead
from .media_intelligence_models import (
    BrollDecisionRead,
    MediaPlanItemRead,
    MediaPlanRequest,
    MediaStrategy,
    StockMediaCandidateRead,
)
from .platform_models import AssetRead
from .vision_models import VisionAnalysisRead


def stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha256(payload).hexdigest()[:24]}"


def plan_storyboard_media(content: dict) -> list[dict]:
    """Separate storyboard source: no fake video analysis and no provider side effects."""
    from .content_models import ContentDocument
    document = ContentDocument.model_validate(content)
    return [{"scene_id": scene.scene_id, "strategy": scene.media_strategy,
             "asset_id": scene.asset_id, "visual_brief": scene.visual_brief,
             "display_duration_seconds": scene.duration_seconds, "fit": scene.fit,
             "architectural_render": scene.architectural_render,
             "capability": "image_to_video" if scene.media_strategy == "ai_video" else "montage",
             "status": "provider_not_configured" if scene.media_strategy in {"ai_image", "ai_video"} else "locally_plannable"}
            for scene in document.scenes]


def platform_orientation(platform: str) -> str:
    if platform in {"youtube_shorts", "tiktok", "facebook_reels", "instagram_reels"}:
        return "portrait"
    if platform == "social_feed":
        return "square"
    return "landscape"


def platform_aspect_ratio(platform: str) -> str:
    if platform in {"youtube_shorts", "tiktok", "facebook_reels", "instagram_reels"}:
        return "9:16"
    if platform == "social_feed":
        return "1:1"
    return "16:9"


def build_broll_decision(
    *,
    analysis: AutoEditAnalysisRead,
    scene: SceneRead,
    vision: VisionAnalysisRead | None,
    brand_context: str,
) -> BrollDecisionRead:
    transcript_text = " ".join(
        segment.text
        for segment in (analysis.transcript.segments if analysis.transcript else [])
        if segment.end_seconds > scene.start_seconds and segment.start_seconds < scene.end_seconds
    )
    vision_scene = next(
        (item for item in (vision.scenes if vision else []) if item.scene_id == scene.scene_id),
        None,
    )
    subjects = list(dict.fromkeys([*scene.subjects, *(vision_scene.subjects if vision_scene else [])]))
    intent_parts = [scene.semantic_label, *subjects[:3]]
    intent = " / ".join(part for part in intent_parts if part) or "supporting visual"
    evidence = vision_scene.description if vision_scene else transcript_text or scene.description
    query = _compact_query(" ".join([scene.semantic_label, *subjects, evidence]))
    prompt = " ".join(
        part
        for part in [
            brand_context,
            scene.description,
            transcript_text,
            "original supporting visual, no logos, no copied creator treatment",
        ]
        if part
    )
    duration = round(scene.end_seconds - scene.start_seconds, 3)
    confidence = round(min(scene.confidence, vision_scene.confidence if vision_scene else 0.65), 4)
    return BrollDecisionRead(
        broll_intent=intent[:500],
        search_query=query[:500],
        duration_seconds=duration,
        preferred_media_type="video" if scene.motion_score >= 0.45 else "image",
        generation_prompt=prompt[:2000],
        placement_start_seconds=scene.start_seconds,
        placement_end_seconds=scene.end_seconds,
        confidence=confidence,
        provenance={"source_type":"planning_evidence", "source_analysis_id":analysis.analysis_id,
            "source_asset_id":analysis.asset_id,"source_asset_sha256":analysis.provenance.get('source_asset_checksum'),
            "transcript_id":analysis.transcript.transcript_id if analysis.transcript else None,
            "transcript_version":analysis.transcript.version if analysis.transcript else None,
            "fixture_asr":bool(analysis.transcript and analysis.transcript.provenance.get('fixture')),
            "vision_analysis_id":vision.vision_analysis_id if vision else None,
            "confidence_basis":"minimum saved scene/vision confidence" if vision_scene else "scene heuristic capped at 0.65; no Vision evidence",
            "semantic_refresh_required":bool(analysis.provenance.get('semantic_analysis_refresh_required')),
            "frame_evidence":[{"frame_id":frame.frame_id,"timestamp_seconds":frame.timestamp_seconds,
                "provider":frame.provider_key,"model":frame.model,"confidence":frame.confidence,
                "evidence_frame_reference":frame.evidence_frame_reference}
                for frame in (vision.frames if vision else [])
                if vision_scene and frame.frame_id in vision_scene.evidence_frame_ids],
            "provider_dispatches":0,"source_media_mutated":False,"recommendation_only":True},
    )


def select_strategy(
    *,
    ordinal: int,
    payload: MediaPlanRequest,
    preferred_media_type: str,
    stock_available: bool,
    image_available: bool,
    video_available: bool,
    has_source_asset: bool,
) -> MediaStrategy:
    desired = _strategies_from_priority(
        payload,
        preferred_media_type=preferred_media_type,
    )
    start = ordinal % len(desired) if payload.selection_policy == 'scene_variety' else 0
    candidates = desired[start:] + desired[:start]
    for strategy in candidates:
        if strategy == "user_asset" and has_source_asset:
            return strategy
        if strategy in {"stock_video", "stock_image"} and payload.allow_stock and stock_available:
            return strategy
        if strategy == "ai_image" and payload.allow_ai_image and image_available:
            return strategy
        if strategy == "ai_video" and payload.allow_ai_video and video_available:
            return strategy
        if strategy == "motion_graphic":
            return strategy
    return "motion_graphic"


def rank_stock_candidates(
    candidates: list[StockMediaCandidateRead],
    *,
    query: str,
    vision_description: str,
) -> list[StockMediaCandidateRead]:
    query_tokens = _tokens(f"{query} {vision_description}")
    ranked: list[StockMediaCandidateRead] = []
    for item in candidates:
        source_tokens = _tokens(
            " ".join(
                [
                    str(item.provenance.get("query", "")),
                    item.source_reference,
                    item.provider_asset_id,
                ]
            )
        )
        overlap = len(query_tokens & source_tokens) / max(1, len(query_tokens))
        rerank = round(min(1, item.semantic_score * 0.8 + overlap * 0.2), 4) if item.semantic_score is not None else None
        ranked.append(item.model_copy(update={"vision_rerank_score": rerank}))
    return sorted(
        ranked,
        key=lambda item: (item.vision_rerank_score or 0, item.semantic_score or 0,
            -(item.provenance.get('provider_result_rank') or 0),item.candidate_id),
        reverse=True,
    )


def build_plan_items(
    *,
    media_plan_id: str,
    fingerprint: str,
    analysis: AutoEditAnalysisRead,
    vision: VisionAnalysisRead | None,
    payload: MediaPlanRequest,
    source_asset: AssetRead | None,
    stock_candidates: dict[str, list[StockMediaCandidateRead]],
    stock_available: bool,
    image_available: bool,
    video_available: bool,
    image_cost_vnd: Decimal | None,
    video_cost_vnd: Decimal | None,
    supporting_assets: list[AssetRead] | None = None,
) -> list[MediaPlanItemRead]:
    items: list[MediaPlanItemRead] = []
    for scene in analysis.scenes:
        broll = build_broll_decision(
            analysis=analysis,
            scene=scene,
            vision=vision,
            brand_context=payload.brand_context,
        )
        raw_candidates = stock_candidates.get(scene.scene_id, [])
        stock_searched = scene.scene_id in stock_candidates
        eligible_candidates = [candidate for candidate in raw_candidates if candidate.rights_status in {'licensed','owned','verified'}]
        effective_stock = stock_available and (bool(eligible_candidates) if payload.selection_policy == 'priority' and stock_searched else True)
        supporting = []
        selected_support = None
        if payload.purpose == 'supporting_broll':
            from .broll_planner import supporting_candidates, choose_supporting_strategy
            supporting = supporting_candidates(supporting_assets or [], analysis, broll.search_query)
            strategy, selected_support = choose_supporting_strategy(payload, supporting,
                stock=effective_stock, image=image_available, video=video_available,
                preferred_type=broll.preferred_media_type)
        else:
            strategy = select_strategy(
                ordinal=scene.ordinal, payload=payload, preferred_media_type=broll.preferred_media_type,
                stock_available=effective_stock, image_available=image_available, video_available=video_available,
                has_source_asset=source_asset is not None)
        vision_scene = next(
            (item for item in (vision.scenes if vision else []) if item.scene_id == scene.scene_id),
            None,
        )
        ranked = rank_stock_candidates(
            eligible_candidates if payload.selection_policy == 'priority' else raw_candidates,
            query=broll.search_query,
            vision_description=vision_scene.description if vision_scene else scene.description,
        )
        if strategy == "ai_image":
            estimated = image_cost_vnd
        elif strategy == "ai_video":
            estimated = video_cost_vnd
        else:
            estimated = Decimal("0")
        needs_approval = estimated is None or estimated > payload.max_ai_cost_vnd
        estimated_value = estimated or Decimal("0")
        fallbacks = _fallbacks(
            strategy,
            payload=payload,
            preferred_media_type=broll.preferred_media_type,
            has_source_asset=source_asset is not None,
            stock_available=effective_stock and payload.allow_stock,
            image_available=image_available and payload.allow_ai_image,
            video_available=video_available and payload.allow_ai_video,
        )
        items.append(
            MediaPlanItemRead(
                media_plan_item_id=stable_id("mpi", fingerprint, scene.scene_id),
                media_plan_id=media_plan_id,
                scene_id=scene.scene_id,
                ordinal=scene.ordinal,
                strategy=strategy,
                fallback=fallbacks,
                broll=broll,
                candidates=ranked if strategy in {"stock_video", "stock_image"} else [],
                source_asset_id=(selected_support['asset_id'] if selected_support else None) if payload.purpose == 'supporting_broll' else (source_asset.asset_id if strategy == "user_asset" and source_asset else None),
                selected_media_asset_id=None,
                estimated_cost_vnd=estimated_value,
                needs_approval=needs_approval,
                needs_attention=needs_approval or strategy == "motion_graphic" or bool(broll.provenance['semantic_refresh_required']) or (payload.purpose == 'supporting_broll' and (not selected_support or selected_support['needs_attention'])),
                status="needs_approval" if needs_approval else "planned",
                provenance={
                    "algorithm": "priority-media-planner-v1",
                    "selection_policy":payload.selection_policy,
                    "resolver_priority":payload.resolver_priority,
                    "stock_search_state":'results' if eligible_candidates else ('empty_or_rights_rejected' if stock_searched else 'not_searched'),
                    "stock_result_count":len(raw_candidates) if stock_searched else None,
                    "stock_rejected_rights_count":len(raw_candidates)-len(eligible_candidates) if stock_searched else None,
                    "stock_tier_available":effective_stock,
                    "source_scene_id": scene.scene_id,
                    "source_analysis_id": analysis.analysis_id,
                    "vision_analysis_id": vision.vision_analysis_id if vision else None,
                    "originality_guardrail": True,
                    "social_media_downloaded": False,
                    "strategy_estimated": True,
                    "estimated_cost_unknown": estimated is None,
                    "estimated_cost_lower_bound_only": estimated is None,
                    **({'supporting_candidates':supporting,'purpose':'supporting_broll',
                        'fallback_keeps_original_footage':selected_support is None and strategy=='user_asset'} if payload.purpose=='supporting_broll' else {}),
                },
            )
        )
    return items


def _fallbacks(
    strategy: MediaStrategy,
    *,
    payload: MediaPlanRequest,
    preferred_media_type: str,
    has_source_asset: bool,
    stock_available: bool,
    image_available: bool,
    video_available: bool,
) -> list[MediaStrategy]:
    ordered: list[MediaStrategy] = []
    for candidate in _strategies_from_priority(
        payload,
        preferred_media_type=preferred_media_type,
    ):
        if candidate == "user_asset" and has_source_asset:
            ordered.append(candidate)
        elif candidate in {"stock_video", "stock_image"} and stock_available:
            ordered.append(candidate)
        elif candidate == "ai_image" and image_available:
            ordered.append(candidate)
        elif candidate == "ai_video" and video_available:
            ordered.append(candidate)
        elif candidate == "motion_graphic":
            ordered.append(candidate)
    return [item for item in dict.fromkeys(ordered) if item != strategy][:4]


def _strategies_from_priority(
    payload: MediaPlanRequest,
    *,
    preferred_media_type: str,
) -> list[MediaStrategy]:
    stock_strategy: MediaStrategy = (
        "stock_video" if preferred_media_type == "video" else "stock_image"
    )
    mapping: dict[str, MediaStrategy | None] = {
        "user_asset": "user_asset",
        "licensed_stock": stock_strategy,
        # A distinct internal-library provider is intentionally not configured
        # in V2-06. User-upload reuse remains available through user_asset.
        "internal_library": None,
        "ai_image": "ai_image",
        "ai_video": "ai_video",
        "motion_graphic": "motion_graphic",
    }
    ordered = [mapping[item] for item in payload.resolver_priority if mapping[item] is not None]
    return list(dict.fromkeys(ordered)) or ["motion_graphic"]


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\wÀ-ỹ]+", value.casefold()) if len(token) > 2}


def _compact_query(value: str) -> str:
    tokens = list(dict.fromkeys(re.findall(r"[\wÀ-ỹ-]+", value, flags=re.UNICODE)))
    return " ".join(tokens[:28]) or "original supporting visual"
