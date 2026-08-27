from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class TimelineORM(Base):
    __tablename__ = "timelines"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_timeline_project"),
        CheckConstraint("current_version >= 1", name="ck_timeline_current_version"),
        Index("ix_timeline_workspace_updated", "workspace_id", "updated_at"),
    )

    timeline_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    source_analysis_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("auto_edit_analyses.analysis_id", ondelete="RESTRICT"), nullable=False
    )
    source_media_plan_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("media_plans.media_plan_id", ondelete="SET NULL"), nullable=True
    )
    current_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approval_status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    approved_timeline_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latest_preview_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class TimelineVersionORM(Base):
    __tablename__ = "timeline_versions"
    __table_args__ = (
        UniqueConstraint("timeline_id", "version", name="uq_timeline_version"),
        CheckConstraint("version >= 1", name="ck_timeline_version"),
        Index("ix_timeline_version_project_created", "project_id", "created_at"),
    )

    timeline_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    timeline_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timelines.timeline_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    mutation_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PreviewJobORM(Base):
    __tablename__ = "preview_jobs"
    __table_args__ = (
        UniqueConstraint("timeline_version_id", "width", "height", name="uq_preview_version_dimensions"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_preview_progress"),
        Index("ix_preview_status_created", "status", "created_at"),
        Index("ix_preview_project_created", "project_id", "created_at"),
    )

    preview_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timelines.timeline_id", ondelete="CASCADE"), nullable=False
    )
    timeline_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timeline_versions.timeline_version_id", ondelete="CASCADE"), nullable=False
    )
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    width: Mapped[int] = mapped_column(Integer, nullable=False, default=540)
    height: Mapped[int] = mapped_column(Integer, nullable=False, default=960)
    output_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True
    )
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
