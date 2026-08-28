from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .auto_edit_models import MediaMetadata
from .models import StrictModel


AspectRatio = Literal["9:16", "16:9", "1:1", "4:5"]
VisionStatus = Literal["pending", "analyzing", "succeeded", "failed"]


class NormalizedBox(StrictModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    width: float = Field(gt=0, le=1)
    height: float = Field(gt=0, le=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> "NormalizedBox":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("normalized box must remain inside the frame")
        return self


class ObjectDetectionRead(StrictModel):
    label: str = Field(min_length=1, max_length=160)
    category: Literal["person", "face", "product", "object", "building", "logo", "text"]
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalizedBox
    track_hint: str | None = Field(default=None, max_length=120)


class OCRDetectionRead(StrictModel):
    text: str = Field(min_length=1, max_length=500)
    language: str = Field(default="und", min_length=2, max_length=16)
    confidence: float = Field(ge=0, le=1)
    bounding_box: NormalizedBox


class FrameCompositionRead(StrictModel):
    primary_subject_box: NormalizedBox | None
    subject_position: Literal[
        "left", "center", "right", "upper_left", "upper_center", "upper_right", "unknown"
    ]
    saliency_box: NormalizedBox | None
    headroom_ratio: float = Field(ge=0, le=1)
    visual_balance_score: float = Field(ge=0, le=1)
    safe_crop: bool


class FrameQualityRead(StrictModel):
    quality_score: float = Field(ge=0, le=1)
    black_frame: bool
    blur_score: float = Field(ge=0, le=1)
    overexposed: bool
    underexposed: bool
    low_resolution: bool
    watermark_or_logo_detected: bool
    frozen_or_duplicate: bool
    issues: list[str]


class VisionFrameRead(StrictModel):
    frame_id: str
    timestamp_seconds: float = Field(ge=0)
    evidence_frame_reference: str = Field(min_length=1, max_length=768)
    caption: str = Field(min_length=1, max_length=1000)
    scene_description: str = Field(min_length=1, max_length=2000)
    semantic_label: str = Field(min_length=1, max_length=240)
    environment: str = Field(min_length=1, max_length=240)
    action: str = Field(min_length=1, max_length=240)
    objects: list[ObjectDetectionRead]
    ocr: list[OCRDetectionRead]
    composition: FrameCompositionRead
    quality: FrameQualityRead
    confidence: float = Field(ge=0, le=1)
    provider_key: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=160)


class VisionSceneRead(StrictModel):
    vision_scene_id: str
    scene_id: str | None
    ordinal: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    semantic_label: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    subjects: list[str]
    quality_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence_frame_ids: list[str]


class SubjectObservationRead(StrictModel):
    timestamp_seconds: float = Field(ge=0)
    bounding_box: NormalizedBox
    confidence: float = Field(ge=0, le=1)


class SubjectTrackRead(StrictModel):
    track_id: str
    label: str = Field(min_length=1, max_length=160)
    category: Literal["person", "face", "product", "object", "building", "logo", "text"]
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(ge=0)
    confidence: float = Field(ge=0, le=1)
    continuity_score: float = Field(ge=0, le=1)
    observations: list[SubjectObservationRead]


class ReframeKeyframeRead(StrictModel):
    time: float = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    scale: float = Field(ge=1, le=20)


class ManualCropOverride(StrictModel):
    aspect_ratio: AspectRatio
    time: float = Field(ge=0)
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    scale: float = Field(ge=1, le=20)


class ReframePlanRead(StrictModel):
    reframe_id: str
    aspect_ratio: AspectRatio
    strategy: Literal["subject_track", "center_crop", "manual_override"]
    subject_track_id: str | None
    keyframes: list[ReframeKeyframeRead]
    smoothing: Literal["bounded_ema", "none"]
    maximum_jump: float = Field(ge=0, le=1)
    subtitle_safe_area_bottom: float = Field(ge=0, le=0.45)
    confidence: float = Field(ge=0, le=1)
    fallback: Literal["none", "center_crop"]
    needs_attention: bool
    manual_override_allowed: Literal[True] = True
    manual_override_applied: bool
    source_media_mutated: Literal[False] = False


class VisionAnalysisRequest(StrictModel):
    acceptance_operation_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/-]{2,199}$",
    )
    aspect_ratios: list[AspectRatio] = Field(
        default_factory=lambda: ["9:16", "16:9", "1:1", "4:5"],
        min_length=1,
        max_length=4,
    )
    sample_interval_seconds: float = Field(default=4.0, ge=0.5, le=30)
    minimum_tracking_confidence: float = Field(default=0.6, ge=0, le=1)
    subtitle_safe_area_bottom: float = Field(default=0.18, ge=0, le=0.45)
    maximum_crop_jump: float = Field(default=0.08, ge=0.01, le=0.3)
    manual_overrides: list[ManualCropOverride] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def validate_configuration(self) -> "VisionAnalysisRequest":
        if len(set(self.aspect_ratios)) != len(self.aspect_ratios):
            raise ValueError("aspect ratios must be unique")
        requested = set(self.aspect_ratios)
        seen: set[tuple[str, float]] = set()
        for override in self.manual_overrides:
            if override.aspect_ratio not in requested:
                raise ValueError("manual override aspect ratio must be requested")
            key = (override.aspect_ratio, override.time)
            if key in seen:
                raise ValueError("manual override timestamps must be unique per aspect ratio")
            seen.add(key)
        return self


class VisionAnalysisRead(StrictModel):
    vision_analysis_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    analysis_id: str
    asset_id: str
    status: VisionStatus
    fingerprint: str
    configuration: VisionAnalysisRequest
    source_media: MediaMetadata
    provider_key: str
    model: str
    frames: list[VisionFrameRead]
    scenes: list[VisionSceneRead]
    subject_tracks: list[SubjectTrackRead]
    reframe_plans: list[ReframePlanRead]
    best_frame_ids: list[str]
    thumbnail_candidate_ids: list[str]
    ocr_detection_count: int = Field(ge=0)
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False
    paid_external_call: Literal[False] = False
    error_code: str | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
