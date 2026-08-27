from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class PublicationORM(Base):
    __tablename__ = "publications"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key_hash", name="uq_publication_project_idempotency"),
        Index("ix_publication_project_created", "project_id", "created_at"),
        Index("ix_publication_status_updated", "status", "updated_at"),
    )

    publication_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_packages.package_id", ondelete="RESTRICT"), nullable=False
    )
    approval_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_approvals.approval_id", ondelete="RESTRICT"), nullable=False
    )
    final_render_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("production_render_jobs.render_id", ondelete="RESTRICT"), nullable=False
    )
    output_asset_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("assets.asset_id", ondelete="RESTRICT"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    capability_version: Mapped[str] = mapped_column(String(80), nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    rights_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    platform_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    provider_validation_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    receipt_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class PublicationEventORM(Base):
    __tablename__ = "publication_events"
    __table_args__ = (Index("ix_publication_event_project_created", "project_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
