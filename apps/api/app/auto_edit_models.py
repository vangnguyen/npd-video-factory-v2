from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel


UploadStatus = Literal["initialized", "uploading", "completed", "completed_duplicate", "failed"]
AnalysisStatus = Literal["pending", "analyzing", "succeeded", "failed"]
MediaKind = Literal["video", "audio", "image", "logo", "music", "subtitle"]


class UploadInitRequest(StrictModel):
    project_id: str = Field(pattern=r"^prj_[A-Za-z0-9_-]{4,60}$")
    project_version_id: str | None = Field(
        default=None, pattern=r"^pver_[A-Za-z0-9_-]{4,60}$"
    )
    filename: str = Field(min_length=1, max_length=255)
    media_kind: MediaKind
    content_type: str = Field(min_length=1, max_length=160)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    part_size_bytes: int | None = Field(default=None, ge=64 * 1024, le=32 * 1024 * 1024)
    rights_status: Literal["owned", "licensed", "unknown"] = "owned"
    license: str = Field(default="user-provided", min_length=1, max_length=160)


class UploadPartRead(StrictModel):
    part_number: int = Field(ge=1)
    size_bytes: int = Field(gt=0)
    checksum_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class MediaMetadata(StrictModel):
    media_kind: MediaKind
    detected_content_type: str
    format_name: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, ge=0)
    video_codec: str | None = None
    audio_codec: str | None = None
    audio_channels: int | None = Field(default=None, ge=1)
    audio_sample_rate: int | None = Field(default=None, ge=1)


class UploadRead(StrictModel):
    upload_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    original_filename: str
    safe_filename: str
    media_kind: MediaKind
    declared_content_type: str
    size_bytes: int
    expected_checksum_sha256: str | None
    part_size_bytes: int
    total_parts: int
    rights_status: Literal["owned", "licensed", "unknown"]
    license: str
    received_parts: list[UploadPartRead]
    received_bytes: int
    status: UploadStatus
    asset_id: str | None
    duplicate_of_asset_id: str | None
    media_metadata: MediaMetadata | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime


class UploadCompleteRequest(StrictModel):
    checksum_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class UploadCompleteRead(StrictModel):
    upload: UploadRead
    asset_id: str
    duplicate: bool
    checksum_sha256: str
    media_metadata: MediaMetadata


class TranscriptWordRead(StrictModel):
    word_id: str
    ordinal: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=240)
    confidence: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def validate_window(self) -> "TranscriptWordRead":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("word end must be after start")
        return self


class TranscriptSegmentRead(StrictModel):
    segment_id: str
    ordinal: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1)
    speaker: str | None = Field(default=None, max_length=120)
    confidence: float = Field(ge=0, le=1)
    words: list[TranscriptWordRead]

    @model_validator(mode="after")
    def validate_window(self) -> "TranscriptSegmentRead":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("segment end must be after start")
        return self


class TranscriptRead(StrictModel):
    transcript_id: str
    analysis_id: str
    asset_id: str
    version: int = Field(ge=1)
    is_original_evidence: bool
    provider_key: str
    language: str
    confidence: float = Field(ge=0, le=1)
    segments: list[TranscriptSegmentRead]
    provenance: dict[str, Any]
    created_at: datetime


class SceneRead(StrictModel):
    scene_id: str
    ordinal: int = Field(ge=0)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    semantic_label: str
    description: str
    subjects: list[str]
    quality_score: float = Field(ge=0, le=1)
    motion_score: float = Field(ge=0, le=1)
    speech_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    evidence: dict[str, Any]


class SilenceDecisionRead(StrictModel):
    decision_id: str
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    padding_before_seconds: float = Field(ge=0)
    padding_after_seconds: float = Field(ge=0)
    enabled: bool
    reason: str
    conflicts_with_speech: bool
    evidence: dict[str, Any]


class HighlightRead(StrictModel):
    highlight_id: str
    rank: int = Field(ge=1)
    highlight_score: float = Field(ge=0, le=1)
    reason: str
    recommended_start: float = Field(ge=0)
    recommended_end: float = Field(gt=0)
    recommended_platform: Literal["facebook_reels", "tiktok", "youtube_shorts", "youtube"]
    scene_id: str | None
    evidence: dict[str, Any]


class AutoEditAnalysisRequest(StrictModel):
    asset_id: str = Field(pattern=r"^ast_[A-Za-z0-9_-]{4,60}$")
    top_highlights: Literal[3, 5] = 3
    silence_threshold_db: float = Field(default=-35.0, ge=-80, le=-5)
    minimum_silence_duration: float = Field(default=0.5, ge=0.1, le=10)
    padding_before: float = Field(default=0.08, ge=0, le=2)
    padding_after: float = Field(default=0.08, ge=0, le=2)


class AutoEditAnalysisRead(StrictModel):
    analysis_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    asset_id: str
    status: AnalysisStatus
    fingerprint: str
    configuration: AutoEditAnalysisRequest
    source_media: MediaMetadata
    transcript: TranscriptRead | None
    scenes: list[SceneRead]
    silence_decisions: list[SilenceDecisionRead]
    highlights: list[HighlightRead]
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False
    error_code: str | None
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime
