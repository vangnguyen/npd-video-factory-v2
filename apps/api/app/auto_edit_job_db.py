"""Additive custody for jobs that analyze genuine uploaded video analyses."""
from datetime import datetime
from typing import Any
from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base, utc_now


class AutoEditJobORM(Base):
    __tablename__ = 'auto_edit_analysis_jobs'
    relation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    analysis_id: Mapped[str] = mapped_column(String(64), ForeignKey('auto_edit_analyses.analysis_id', ondelete='RESTRICT'), nullable=False, unique=True)
    job_id: Mapped[str] = mapped_column(String(80), ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False, unique=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    source_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    configuration_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    provider_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    custody_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    claim_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AutoEditJobRequestORM(Base):
    __tablename__ = 'auto_edit_analysis_job_requests'
    __table_args__ = (UniqueConstraint('project_id', 'request_key_sha256', name='uq_auto_edit_job_request'),)
    receipt_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    job_id: Mapped[str] = mapped_column(String(80), ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False)
    request_key_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
