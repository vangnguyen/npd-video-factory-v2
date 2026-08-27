from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel


ApprovalStatus = Literal["draft", "awaiting_review", "changes_requested", "approved", "rejected"]
RenderKind = Literal["review", "final"]
RenderStatus = Literal[
    "queued",
    "running",
    "awaiting_review",
    "ready",
    "stale",
    "cancelled",
    "failed",
    "failed_qc",
]
RenderProfile = Literal["review-540x960", "vertical-1080x1920", "landscape-1920x1080", "square-1080x1080"]


class SubtitleWord(StrictModel):
    text: str = Field(min_length=1, max_length=60)
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_window(self) -> "SubtitleWord":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("subtitle word end must be after start")
        return self


class SubtitleCue(StrictModel):
    cue_id: str = Field(pattern=r"^sub_[A-Za-z0-9_-]{4,60}$")
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    text: str = Field(min_length=1, max_length=180)
    words: list[SubtitleWord] = Field(default_factory=list, max_length=40)

    @model_validator(mode="after")
    def validate_window_and_words(self) -> "SubtitleCue":
        if self.end_seconds <= self.start_seconds:
            raise ValueError("subtitle cue end must be after start")
        previous_end = self.start_seconds
        for word in self.words:
            if word.start_seconds < previous_end - 0.001:
                raise ValueError("subtitle words must be monotonic and non-overlapping")
            if word.start_seconds < self.start_seconds - 0.001 or word.end_seconds > self.end_seconds + 0.001:
                raise ValueError("subtitle words must remain inside their cue")
            previous_end = word.end_seconds
        return self


class SubtitleStyle(StrictModel):
    font_family: Literal["Noto Sans", "Noto Sans Display"] = "Noto Sans"
    font_size: int = Field(default=48, ge=28, le=84)
    font_weight: int = Field(default=800, ge=400, le=900)
    text_color: str = Field(default="#FFFFFF", pattern=r"^#[0-9A-Fa-f]{6}$")
    highlight_color: str = Field(default="#F5C451", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_color: str = Field(default="#000000", pattern=r"^#[0-9A-Fa-f]{6}$")
    background_opacity: float = Field(default=0.58, ge=0, le=1)
    position: Literal["top", "center", "bottom"] = "bottom"
    animation: Literal["none", "fade", "pop", "word_highlight"] = "word_highlight"
    max_lines: int = Field(default=3, ge=1, le=3)
    safe_margin_percent: float = Field(default=7, ge=3, le=15)


class SubtitleReplaceRequest(StrictModel):
    expected_timeline_version: int = Field(ge=1)
    expected_subtitle_version: int = Field(ge=1)
    cues: list[SubtitleCue] = Field(min_length=1, max_length=300)
    style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)
    reason: str = Field(default="subtitle-edit", min_length=1, max_length=240)


class SubtitleVersionRead(StrictModel):
    subtitle_version_id: str
    package_id: str
    project_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    version: int = Field(ge=1)
    cues: list[SubtitleCue]
    style: SubtitleStyle
    actor_ref: str
    created_at: datetime


class VoiceConfig(StrictModel):
    enabled: bool = True
    language: Literal["vi"] = "vi"
    voice: str = Field(default="vi", min_length=1, max_length=80)
    speed: float = Field(default=1, ge=0.75, le=1.35)
    instructions: str = Field(default="", max_length=500)
    gain_db: float = Field(default=0, ge=-18, le=9)
    max_timing_adjustment: float = Field(default=1.35, ge=1, le=1.5)


class MusicConfig(StrictModel):
    asset_id: str | None = Field(default=None, pattern=r"^ast_[A-Za-z0-9_-]{4,60}$")
    gain_db: float = Field(default=-22, ge=-40, le=-3)
    ducking_db: float = Field(default=-12, ge=-30, le=-3)
    fade_in_seconds: float = Field(default=0.8, ge=0, le=5)
    fade_out_seconds: float = Field(default=1.2, ge=0, le=5)
    loop: bool = True


class MixConfig(StrictModel):
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    music: MusicConfig = Field(default_factory=MusicConfig)
    sample_rate: Literal[48000] = 48000
    limiter_peak_db: float = Field(default=-1, ge=-3, le=-0.1)
    target_lufs: float = Field(default=-16, ge=-24, le=-12)
    original_audio_gain_db: float | None = Field(default=None, ge=-60, le=0)


class AudioMixReplaceRequest(StrictModel):
    expected_timeline_version: int = Field(ge=1)
    expected_audio_version: int = Field(ge=1)
    config: MixConfig
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)
    reason: str = Field(default="audio-mix-edit", min_length=1, max_length=240)


class AudioMixVersionRead(StrictModel):
    audio_version_id: str
    package_id: str
    project_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    version: int = Field(ge=1)
    config: MixConfig
    provider_status: Literal["configured", "not_configured", "disabled"]
    actor_ref: str
    created_at: datetime


class ProductionPackageCreateRequest(StrictModel):
    expected_timeline_version: int | None = Field(default=None, ge=1)
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class RenderCreateRequest(StrictModel):
    expected_timeline_version: int = Field(ge=1)
    expected_subtitle_version: int = Field(ge=1)
    expected_audio_version: int = Field(ge=1)
    profile: RenderProfile = "review-540x960"
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class FinalRenderCreateRequest(RenderCreateRequest):
    profile: Literal["vertical-1080x1920", "landscape-1920x1080", "square-1080x1080"] = (
        "vertical-1080x1920"
    )
    approval_id: str = Field(pattern=r"^apr_[A-Za-z0-9_-]{4,60}$")


class RenderJobRead(StrictModel):
    render_id: str
    version: int = Field(ge=1)
    package_id: str
    workspace_id: str
    project_id: str
    timeline_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    subtitle_version_id: str
    subtitle_version: int = Field(ge=1)
    audio_version_id: str
    audio_version: int = Field(ge=1)
    approval_id: str | None
    render_kind: RenderKind
    profile: RenderProfile
    status: RenderStatus
    progress: int = Field(ge=0, le=100)
    output_asset_id: str | None
    playback_url: str | None
    qc_status: Literal["pending", "passed", "failed"]
    qc_report: dict[str, Any]
    manifest: dict[str, Any]
    cancellation_requested: bool
    error_code: str | None
    failure_reason: str | None
    publishing_allowed: Literal[False] = False
    external_publish_requested: Literal[False] = False
    created_at: datetime
    updated_at: datetime


class ApprovalRequest(StrictModel):
    review_render_id: str = Field(pattern=r"^rnd_[A-Za-z0-9_-]{4,60}$")
    requester_ref: str = Field(default="studio-user", min_length=1, max_length=160)
    note: str = Field(default="", max_length=1000)


class ApprovalDecisionRequest(StrictModel):
    decision: Literal["approved", "changes_requested", "rejected"]
    reviewer_ref: str = Field(min_length=1, max_length=160)
    comment: str = Field(default="", max_length=2000)


class ApprovalRead(StrictModel):
    approval_id: str
    package_id: str
    project_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    preview_render_id: str
    preview_version: int = Field(ge=1)
    subtitle_version_id: str
    subtitle_version: int = Field(ge=1)
    audio_version_id: str
    audio_version: int = Field(ge=1)
    status: ApprovalStatus
    requester_ref: str
    reviewer_ref: str | None
    note: str
    decision_comment: str
    invalidated_reason: str | None
    requested_at: datetime
    decided_at: datetime | None
    updated_at: datetime


class ProductionPackageRead(StrictModel):
    package_id: str
    workspace_id: str
    project_id: str
    timeline_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    subtitle: SubtitleVersionRead
    audio_mix: AudioMixVersionRead
    approval: ApprovalRead | None
    latest_review_render: RenderJobRead | None
    latest_final_render: RenderJobRead | None
    current_for_timeline: bool
    publishing_allowed: Literal[False] = False
    created_at: datetime
    updated_at: datetime


class ProductionEventRead(StrictModel):
    event_id: str
    package_id: str
    project_id: str
    event_type: str
    entity_type: str
    entity_id: str
    actor_ref: str
    payload: dict[str, Any]
    created_at: datetime
