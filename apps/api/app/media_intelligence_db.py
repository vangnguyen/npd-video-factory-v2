from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class MediaPlanORM(Base):
    __tablename__ = "media_plans"
    __table_args__ = (
        UniqueConstraint("project_id", "fingerprint", name="uq_media_plan_project_fingerprint"),
        CheckConstraint("projected_ai_cost_vnd >= 0", name="ck_media_plan_projected_cost"),
        CheckConstraint("max_ai_cost_vnd >= 0", name="ck_media_plan_max_cost"),
        Index("ix_media_plan_project_created", "project_id", "created_at"),
    )

    media_plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
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
    vision_analysis_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("vision_analyses.vision_analysis_id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_status_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    projected_ai_cost_vnd: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0")
    )
    max_ai_cost_vnd: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0")
    )
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MediaPlanItemORM(Base):
    __tablename__ = "media_plan_items"
    __table_args__ = (
        UniqueConstraint("media_plan_id", "ordinal", name="uq_media_plan_item_ordinal"),
        CheckConstraint("estimated_cost_vnd >= 0", name="ck_media_plan_item_cost"),
    )

    media_plan_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    media_plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("media_plans.media_plan_id", ondelete="CASCADE"), nullable=False
    )
    scene_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("scenes.scene_id", ondelete="RESTRICT"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy: Mapped[str] = mapped_column(String(40), nullable=False)
    fallback_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    broll_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    candidates_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False, default=list)
    source_asset_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="SET NULL"), nullable=True
    )
    selected_media_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_cost_vnd: Mapped[Decimal] = mapped_column(
        Numeric(20, 4), nullable=False, default=Decimal("0")
    )
    needs_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    needs_attention: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="planned")
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MediaAssetProvenanceORM(Base):
    __tablename__ = "media_asset_provenance"
    __table_args__ = (
        UniqueConstraint("asset_id", name="uq_media_asset_provenance_asset"),
        Index("ix_media_asset_project_created", "project_id", "created_at"),
    )

    media_asset_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    media_plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("media_plans.media_plan_id", ondelete="CASCADE"), nullable=False
    )
    media_plan_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("media_plan_items.media_plan_item_id", ondelete="CASCADE"), nullable=False
    )
    asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    rights_status: Mapped[str] = mapped_column(String(40), nullable=False)
    license: Mapped[str] = mapped_column(String(240), nullable=False)
    license_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    provider: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_asset_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    creator: Mapped[str | None] = mapped_column(String(240), nullable=True)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    attribution_requirement: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    generation_provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    orientation: Mapped[str] = mapped_column(String(32), nullable=False, default="unknown")
    production_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publishing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    owner_override_recorded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class MediaResolutionJobORM(Base):
    __tablename__ = "media_resolution_jobs"
    __table_args__ = (
        UniqueConstraint("fingerprint", name="uq_media_resolution_job_fingerprint"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="ck_media_resolution_progress"),
        CheckConstraint(
            "estimated_cost_vnd IS NULL OR estimated_cost_vnd >= 0",
            name="ck_media_resolution_estimated_cost",
        ),
        CheckConstraint(
            "actual_cost_vnd IS NULL OR actual_cost_vnd >= 0",
            name="ck_media_resolution_actual_cost",
        ),
        Index("ix_media_resolution_status_created", "status", "created_at"),
    )

    resolution_job_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    project_version_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("project_versions.project_version_id", ondelete="SET NULL"), nullable=True
    )
    media_plan_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("media_plans.media_plan_id", ondelete="CASCADE"), nullable=False
    )
    media_plan_item_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("media_plan_items.media_plan_item_id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability: Mapped[str] = mapped_column(String(80), nullable=False)
    operation: Mapped[str] = mapped_column(String(160), nullable=False)
    provider_job_id: Mapped[str | None] = mapped_column(String(240), nullable=True)
    selected_candidate_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    estimated_cost_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    actual_cost_vnd: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    output_media_asset_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    external_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    real_provider_tested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    provenance_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )
