from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel


MediaSourceType = Literal["user_upload", "stock", "ai_generated", "internal_library"]
MediaRightsStatus = Literal["owned", "licensed", "verified", "unknown", "restricted"]
MediaStrategy = Literal[
    "user_asset",
    "stock_video",
    "stock_image",
    "ai_image",
    "ai_video",
    "motion_graphic",
]
MediaType = Literal["image", "video"]
PlatformTarget = Literal[
    "youtube",
    "youtube_shorts",
    "tiktok",
    "facebook_reels",
    "instagram_reels",
    "social_feed",
]
ResolutionStatus = Literal["queued", "running", "needs_approval", "succeeded", "failed", "cancelled"]


class BrollDecisionRead(StrictModel):
    broll_intent: str = Field(min_length=1, max_length=500)
    search_query: str = Field(min_length=1, max_length=500)
    duration_seconds: float = Field(gt=0, le=600)
    preferred_media_type: MediaType
    generation_prompt: str = Field(min_length=1, max_length=2000)
    placement_start_seconds: float = Field(ge=0)
    placement_end_seconds: float = Field(gt=0)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_window(self) -> "BrollDecisionRead":
        if self.placement_end_seconds <= self.placement_start_seconds:
            raise ValueError("B-roll placement end must be after start")
        return self


class StockMediaCandidateRead(StrictModel):
    candidate_id: str
    provider: str = Field(min_length=1, max_length=120)
    provider_asset_id: str = Field(min_length=1, max_length=200)
    creator: str = Field(min_length=1, max_length=240)
    source_reference: str = Field(min_length=1, max_length=1000)
    license: str = Field(min_length=1, max_length=240)
    license_url: str | None = Field(default=None, max_length=1000)
    attribution_requirement: str | None = Field(default=None, max_length=1000)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    duration_seconds: float | None = Field(default=None, gt=0)
    orientation: Literal["portrait", "landscape", "square", "unknown"]
    media_type: MediaType
    semantic_score: float = Field(ge=0, le=1)
    vision_rerank_score: float | None = Field(default=None, ge=0, le=1)
    rights_status: MediaRightsStatus
    production_eligible: bool
    estimated_cost_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ImageGenerationInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=2000)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    reference_images: list[str] = Field(default_factory=list, max_length=10)
    style: str = Field(default="cinematic", min_length=1, max_length=160)
    seed: int = Field(default=1, ge=0, le=2_147_483_647)
    quality: Literal["draft", "standard", "high"] = "draft"
    operation: Literal["generate", "variation", "upscale", "inpaint"] = "generate"


class VideoGenerationInput(StrictModel):
    prompt: str = Field(min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=2000)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    reference_images: list[str] = Field(default_factory=list, max_length=10)
    duration_seconds: float = Field(default=5, gt=0, le=30)
    seed: int = Field(default=1, ge=0, le=2_147_483_647)
    mode: Literal["text_to_video", "image_to_video", "reference_assisted"] = "text_to_video"


class MediaPlanRequest(StrictModel):
    analysis_id: str = Field(pattern=r"^ana_[A-Za-z0-9_-]{4,60}$")
    vision_analysis_id: str | None = Field(default=None, pattern=r"^vis_[A-Za-z0-9_-]{4,60}$")
    platform: PlatformTarget = "facebook_reels"
    brand_context: str = Field(default="NPD Video Factory", min_length=1, max_length=500)
    max_ai_cost_vnd: Decimal = Field(default=Decimal("0"), ge=0, le=Decimal("1000000000"))
    allow_stock: bool = True
    allow_ai_image: bool = True
    allow_ai_video: bool = True
    resolver_priority: list[Literal[
        "user_asset",
        "licensed_stock",
        "internal_library",
        "ai_image",
        "ai_video",
        "motion_graphic",
    ]] = Field(
        default_factory=lambda: [
            "user_asset",
            "licensed_stock",
            "internal_library",
            "ai_image",
            "ai_video",
            "motion_graphic",
        ],
        min_length=1,
        max_length=6,
    )

    @model_validator(mode="after")
    def validate_priority(self) -> "MediaPlanRequest":
        if len(set(self.resolver_priority)) != len(self.resolver_priority):
            raise ValueError("resolver priority entries must be unique")
        return self


class MediaAssetProvenanceRead(StrictModel):
    media_asset_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    media_plan_id: str
    media_plan_item_id: str
    asset_id: str
    source_type: MediaSourceType
    rights_status: MediaRightsStatus
    license: str
    license_url: str | None
    provider: str
    provider_asset_id: str | None
    creator: str | None
    source_reference: str
    attribution_requirement: str | None
    generation_provenance: dict[str, Any]
    width: int | None
    height: int | None
    duration_seconds: float | None
    orientation: str
    production_eligible: bool
    publishing_allowed: bool
    owner_override_recorded: Literal[False] = False
    downloaded_at: datetime | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MediaPlanItemRead(StrictModel):
    media_plan_item_id: str
    media_plan_id: str
    scene_id: str
    ordinal: int = Field(ge=0)
    strategy: MediaStrategy
    fallback: list[MediaStrategy]
    broll: BrollDecisionRead
    candidates: list[StockMediaCandidateRead]
    source_asset_id: str | None
    selected_media_asset_id: str | None
    estimated_cost_vnd: Decimal = Field(ge=0)
    needs_approval: bool
    needs_attention: bool
    status: Literal["planned", "resolving", "resolved", "needs_approval", "failed"]
    provenance: dict[str, Any]


class MediaResolutionRequest(StrictModel):
    candidate_id: str | None = Field(default=None, max_length=120)


class MediaResolutionJobRead(StrictModel):
    resolution_job_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    media_plan_id: str
    media_plan_item_id: str
    status: ResolutionStatus
    progress: int = Field(ge=0, le=100)
    provider_key: str
    capability: Literal["stock_media", "image_generation", "video_generation", "internal_media"]
    operation: str
    provider_job_id: str | None
    selected_candidate_id: str | None
    estimated_cost_vnd: Decimal | None = Field(default=None, ge=0)
    actual_cost_vnd: Decimal | None = Field(default=None, ge=0)
    output_media_asset_id: str | None
    error_code: str | None
    failure_reason: str | None
    external_call: bool
    paid: bool
    real_provider_tested: bool
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MediaPlanRead(StrictModel):
    media_plan_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    analysis_id: str
    vision_analysis_id: str | None
    status: Literal["draft", "failed"]
    fingerprint: str
    version: int = Field(ge=1)
    configuration: MediaPlanRequest
    provider_status: dict[str, Any]
    items: list[MediaPlanItemRead]
    media_assets: list[MediaAssetProvenanceRead]
    resolution_jobs: list[MediaResolutionJobRead]
    projected_ai_cost_vnd: Decimal = Field(ge=0)
    max_ai_cost_vnd: Decimal = Field(ge=0)
    needs_approval: bool
    publishing_blocked: bool
    unresolved_items: int = Field(ge=0)
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False
    paid_external_call: Literal[False] = False
    error_code: str | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
