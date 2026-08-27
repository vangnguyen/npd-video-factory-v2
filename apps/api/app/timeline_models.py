from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel


TrackType = Literal["video", "text", "audio", "metadata"]
TrackKind = Literal[
    "source",
    "broll",
    "overlay",
    "generated",
    "subtitles",
    "original_audio",
    "voice",
    "music",
    "sfx",
    "metadata",
]
ClipKind = Literal[
    "source",
    "broll",
    "overlay",
    "generated",
    "subtitle",
    "original_audio",
    "voice",
    "music",
    "sfx",
    "metadata",
]
TimelineOperationType = Literal[
    "move",
    "trim",
    "split",
    "delete",
    "reorder",
    "disable",
    "duplicate",
    "set_clip_properties",
    "set_track_state",
]
PreviewStatus = Literal["queued", "running", "ready", "stale", "cancelled", "failed"]


class CropSpec(StrictModel):
    x: float = Field(default=0, ge=0, le=1)
    y: float = Field(default=0, ge=0, le=1)
    width: float = Field(default=1, gt=0, le=1)
    height: float = Field(default=1, gt=0, le=1)

    @model_validator(mode="after")
    def stay_inside_source(self) -> "CropSpec":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("crop rectangle must remain inside the source frame")
        return self


class TransformSpec(StrictModel):
    x: float = Field(default=0, ge=-2, le=2)
    y: float = Field(default=0, ge=-2, le=2)
    scale: float = Field(default=1, gt=0, le=8)
    rotation_degrees: float = Field(default=0, ge=-360, le=360)


class TransitionSpec(StrictModel):
    kind: Literal["none", "cut", "fade", "crossfade", "slide"] = "cut"
    duration_seconds: float = Field(default=0, ge=0, le=5)


class TimelineClip(StrictModel):
    clip_id: str = Field(pattern=r"^clip_[A-Za-z0-9_-]{4,60}$")
    kind: ClipKind
    label: str = Field(min_length=1, max_length=240)
    asset_id: str | None = Field(default=None, pattern=r"^ast_[A-Za-z0-9_-]{4,60}$")
    source_start: float = Field(default=0, ge=0)
    source_end: float = Field(gt=0)
    timeline_start: float = Field(ge=0)
    duration: float = Field(gt=0)
    speed: float = Field(default=1, gt=0, le=8)
    crop: CropSpec = Field(default_factory=CropSpec)
    transform: TransformSpec = Field(default_factory=TransformSpec)
    opacity: float = Field(default=1, ge=0, le=1)
    volume: float = Field(default=1, ge=0, le=2)
    transition_in: TransitionSpec = Field(default_factory=TransitionSpec)
    transition_out: TransitionSpec = Field(default_factory=TransitionSpec)
    effects: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    disabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_source_window(self) -> "TimelineClip":
        if self.source_end <= self.source_start:
            raise ValueError("clip source_end must be after source_start")
        source_duration = (self.source_end - self.source_start) / self.speed
        if self.kind not in {"overlay", "subtitle", "metadata"} and abs(source_duration - self.duration) > 0.05:
            raise ValueError("clip duration must match its source window and speed")
        return self


class TimelineTrack(StrictModel):
    track_id: str = Field(pattern=r"^trk_[A-Za-z0-9_-]{4,60}$")
    type: TrackType
    kind: TrackKind
    label: str = Field(min_length=1, max_length=160)
    order: int = Field(ge=0)
    locked: bool = False
    muted: bool = False
    disabled: bool = False
    clips: list[TimelineClip] = Field(default_factory=list)


class TimelineSnapshot(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    width: int = Field(default=1080, ge=16, le=7680)
    height: int = Field(default=1920, ge=16, le=7680)
    fps: float = Field(default=30, gt=0, le=120)
    aspect_ratio: Literal["9:16", "16:9", "1:1", "4:5"] = "9:16"
    duration_seconds: float = Field(gt=0)
    tracks: list[TimelineTrack] = Field(min_length=1, max_length=32)
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False

    @model_validator(mode="after")
    def validate_identity_and_bounds(self) -> "TimelineSnapshot":
        track_ids = [track.track_id for track in self.tracks]
        if len(track_ids) != len(set(track_ids)):
            raise ValueError("timeline track ids must be unique")
        clip_ids = [clip.clip_id for track in self.tracks for clip in track.clips]
        if len(clip_ids) != len(set(clip_ids)):
            raise ValueError("timeline clip ids must be unique")
        if any(track.order != index for index, track in enumerate(sorted(self.tracks, key=lambda item: item.order))):
            raise ValueError("track order must be contiguous from zero")
        furthest_end = max(
            (
                clip.timeline_start + clip.duration
                for track in self.tracks
                for clip in track.clips
                if not clip.disabled and not track.disabled
            ),
            default=0,
        )
        if furthest_end > self.duration_seconds + 0.05:
            raise ValueError("timeline duration must cover every enabled clip")
        return self


class TimelineCreateRequest(StrictModel):
    analysis_id: str = Field(pattern=r"^ana_[A-Za-z0-9_-]{4,60}$")
    media_plan_id: str | None = Field(default=None, pattern=r"^mpl_[A-Za-z0-9_-]{4,60}$")
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class TimelineOperation(StrictModel):
    type: TimelineOperationType
    clip_id: str | None = Field(default=None, pattern=r"^clip_[A-Za-z0-9_-]{4,60}$")
    track_id: str | None = Field(default=None, pattern=r"^trk_[A-Za-z0-9_-]{4,60}$")
    target_track_id: str | None = Field(default=None, pattern=r"^trk_[A-Za-z0-9_-]{4,60}$")
    target_index: int | None = Field(default=None, ge=0)
    timeline_start: float | None = Field(default=None, ge=0)
    source_start: float | None = Field(default=None, ge=0)
    source_end: float | None = Field(default=None, gt=0)
    at_seconds: float | None = Field(default=None, ge=0)
    disabled: bool | None = None
    locked: bool | None = None
    muted: bool | None = None
    opacity: float | None = Field(default=None, ge=0, le=1)
    volume: float | None = Field(default=None, ge=0, le=2)
    speed: float | None = Field(default=None, gt=0, le=8)
    crop: CropSpec | None = None
    transform: TransformSpec | None = None

    @model_validator(mode="after")
    def require_operation_arguments(self) -> "TimelineOperation":
        clip_operations = {
            "move", "trim", "split", "delete", "reorder", "disable", "duplicate", "set_clip_properties"
        }
        if self.type in clip_operations and not self.clip_id:
            raise ValueError(f"{self.type} requires clip_id")
        if self.type == "move" and self.timeline_start is None and self.target_track_id is None:
            raise ValueError("move requires timeline_start or target_track_id")
        if self.type == "trim" and self.source_start is None and self.source_end is None:
            raise ValueError("trim requires source_start or source_end")
        if self.type == "split" and self.at_seconds is None:
            raise ValueError("split requires at_seconds")
        if self.type == "reorder" and self.target_index is None:
            raise ValueError("reorder requires target_index")
        if self.type == "disable" and self.disabled is None:
            raise ValueError("disable requires disabled")
        if self.type == "set_track_state":
            if not self.track_id:
                raise ValueError("set_track_state requires track_id")
            if self.locked is None and self.muted is None and self.disabled is None:
                raise ValueError("set_track_state requires locked, muted or disabled")
        if self.type == "set_clip_properties" and all(
            value is None
            for value in (self.opacity, self.volume, self.speed, self.crop, self.transform)
        ):
            raise ValueError("set_clip_properties requires at least one property")
        return self


class TimelineMutationRequest(StrictModel):
    expected_version: int = Field(ge=1)
    operations: list[TimelineOperation] = Field(min_length=1, max_length=100)
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)
    reason: str = Field(default="manual-edit", min_length=1, max_length=240)


class TimelineRestoreRequest(StrictModel):
    expected_version: int = Field(ge=1)
    restore_version: int = Field(ge=1)
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class TimelineVersionRead(StrictModel):
    timeline_version_id: str
    timeline_id: str
    project_id: str
    version: int = Field(ge=1)
    snapshot: TimelineSnapshot
    mutation: dict[str, Any]
    actor_ref: str
    created_at: datetime


class TimelineRead(StrictModel):
    timeline_id: str
    workspace_id: str
    project_id: str
    project_version_id: str | None
    source_analysis_id: str
    source_media_plan_id: str | None
    current_version_id: str
    current_version: int = Field(ge=1)
    approval_status: Literal["draft", "awaiting_review", "changes_requested", "approved"]
    approved_timeline_version: int | None
    snapshot: TimelineSnapshot
    latest_preview_id: str | None
    latest_preview_valid: bool
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False
    created_at: datetime
    updated_at: datetime


class PreviewCreateRequest(StrictModel):
    timeline_version: int | None = Field(default=None, ge=1)
    width: Literal[540] = 540
    height: Literal[960] = 960
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)


class PreviewRead(StrictModel):
    preview_id: str
    workspace_id: str
    project_id: str
    timeline_id: str
    timeline_version_id: str
    timeline_version: int = Field(ge=1)
    status: PreviewStatus
    progress: int = Field(ge=0, le=100)
    width: int = Field(ge=16)
    height: int = Field(ge=16)
    output_asset_id: str | None
    playback_url: str | None
    valid_for_current_timeline: bool
    cancellation_requested: bool
    error_code: str | None
    failure_reason: str | None
    manifest: dict[str, Any]
    source_media_mutated: Literal[False] = False
    publish_requested: Literal[False] = False
    external_call: Literal[False] = False
    created_at: datetime
    updated_at: datetime
