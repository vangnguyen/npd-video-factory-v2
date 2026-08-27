from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class VisionAnalysisORM(Base):
    __tablename__ = "vision_analyses"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_vision_project_fingerprint"),
        Index("ix_vision_project_created", "project_id", "created_at"),
    )

    vision_analysis_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_media_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)
    best_frame_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    thumbnail_candidate_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class VisionFrameORM(Base):
    __tablename__ = "vision_frames"
    __table_args__ = (
        UniqueConstraint("vision_analysis_id", "ordinal", name="uq_vision_frame_ordinal"),
    )

    frame_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vision_analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vision_analyses.vision_analysis_id", ondelete="CASCADE"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    timestamp_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_frame_reference: Mapped[str] = mapped_column(String(768), nullable=False)
    caption: Mapped[str] = mapped_column(String(1000), nullable=False)
    scene_description: Mapped[str] = mapped_column(String(2000), nullable=False)
    semantic_label: Mapped[str] = mapped_column(String(240), nullable=False)
    environment: Mapped[str] = mapped_column(String(240), nullable=False)
    action: Mapped[str] = mapped_column(String(240), nullable=False)
    objects_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    ocr_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    composition_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    quality_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    model: Mapped[str] = mapped_column(String(160), nullable=False)


class VisionSceneInsightORM(Base):
    __tablename__ = "vision_scene_insights"
    __table_args__ = (
        UniqueConstraint("vision_analysis_id", "ordinal", name="uq_vision_scene_ordinal"),
    )

    vision_scene_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vision_analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vision_analyses.vision_analysis_id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("scenes.scene_id", ondelete="SET NULL"), nullable=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    semantic_label: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(String(2000), nullable=False)
    subjects_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    quality_score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_frame_ids_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class VisionSubjectTrackORM(Base):
    __tablename__ = "vision_subject_tracks"

    track_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vision_analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vision_analyses.vision_analysis_id", ondelete="CASCADE"), nullable=False
    )
    label: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    start_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    end_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    continuity_score: Mapped[float] = mapped_column(Float, nullable=False)
    observations_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)


class VisionReframePlanORM(Base):
    __tablename__ = "vision_reframe_plans"
    __table_args__ = (
        UniqueConstraint("vision_analysis_id", "aspect_ratio", name="uq_vision_reframe_aspect"),
    )

    reframe_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    vision_analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vision_analyses.vision_analysis_id", ondelete="CASCADE"), nullable=False
    )
    aspect_ratio: Mapped[str] = mapped_column(String(12), nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    subject_track_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("vision_subject_tracks.track_id", ondelete="SET NULL"), nullable=True
    )
    keyframes_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    smoothing: Mapped[str] = mapped_column(String(40), nullable=False)
    maximum_jump: Mapped[float] = mapped_column(Float, nullable=False)
    subtitle_safe_area_bottom: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    fallback: Mapped[str] = mapped_column(String(40), nullable=False)
    needs_attention: Mapped[bool] = mapped_column(nullable=False)
    manual_override_applied: Mapped[bool] = mapped_column(nullable=False)
