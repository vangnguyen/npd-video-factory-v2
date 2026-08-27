from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class ProductionPackageORM(Base):
    __tablename__ = "production_packages"
    __table_args__ = (
        UniqueConstraint("project_id", name="uq_production_package_project"),
        CheckConstraint("timeline_version >= 1", name="ck_production_package_timeline_version"),
        Index("ix_production_package_workspace_updated", "workspace_id", "updated_at"),
    )

    package_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
        String(64), ForeignKey("timeline_versions.timeline_version_id", ondelete="RESTRICT"), nullable=False
    )
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_subtitle_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_subtitle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_audio_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    current_audio_version: Mapped[int] = mapped_column(Integer, nullable=False)
    current_approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_review_render_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latest_final_render_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class SubtitleVersionORM(Base):
    __tablename__ = "subtitle_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_subtitle_package_version"),
        CheckConstraint("version >= 1", name="ck_subtitle_version"),
        Index("ix_subtitle_project_created", "project_id", "created_at"),
    )

    subtitle_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    timeline_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timeline_versions.timeline_version_id", ondelete="RESTRICT"), nullable=False
    )
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    cues_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    style_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AudioMixVersionORM(Base):
    __tablename__ = "audio_mix_versions"
    __table_args__ = (
        UniqueConstraint("package_id", "version", name="uq_audio_mix_package_version"),
        CheckConstraint("version >= 1", name="ck_audio_mix_version"),
        Index("ix_audio_mix_project_created", "project_id", "created_at"),
    )

    audio_version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    timeline_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timeline_versions.timeline_version_id", ondelete="RESTRICT"), nullable=False
    )
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ProductionApprovalORM(Base):
    __tablename__ = "production_approvals"
    __table_args__ = (
        Index("ix_production_approval_project_updated", "project_id", "updated_at"),
        Index("ix_production_approval_status", "status"),
    )

    approval_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    timeline_version_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("timeline_versions.timeline_version_id", ondelete="RESTRICT"), nullable=False
    )
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    preview_render_id: Mapped[str] = mapped_column(String(64), nullable=False)
    preview_version: Mapped[int] = mapped_column(Integer, nullable=False)
    subtitle_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subtitle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audio_version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requester_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    reviewer_ref: Mapped[str | None] = mapped_column(String(160), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    decision_comment: Mapped[str] = mapped_column(Text, nullable=False, default="")
    invalidated_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProductionRenderJobORM(Base):
    __tablename__ = "production_render_jobs"
    __table_args__ = (
        UniqueConstraint("package_id", "render_kind", "version", name="uq_production_render_kind_version"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_production_render_progress"),
        Index("ix_production_render_status_created", "status", "created_at"),
        Index("ix_production_render_project_created", "project_id", "created_at"),
    )

    render_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    timeline_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timeline_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    timeline_version: Mapped[int] = mapped_column(Integer, nullable=False)
    subtitle_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    subtitle_version: Mapped[int] = mapped_column(Integer, nullable=False)
    audio_version_id: Mapped[str] = mapped_column(String(64), nullable=False)
    audio_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    render_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    profile: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True
    )
    qc_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    qc_report_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    manifest_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    cancellation_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class ProductionEventORM(Base):
    __tablename__ = "production_events"
    __table_args__ = (Index("ix_production_event_project_created", "project_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
