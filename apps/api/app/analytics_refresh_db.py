"""Durable refresh plans and immutable occurrence-to-sync bindings.

Separate occurrence rows retain the existing analytics job schema. Plans have
immutable collection configuration; enable/disable revisions fence old jobs.
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class AnalyticsRefreshPlanORM(Base):
    __tablename__ = 'analytics_refresh_plans'
    __table_args__ = (
        UniqueConstraint('project_id', 'idempotency_key_hash', name='uq_analytics_refresh_project_key'),
        CheckConstraint('interval_hours >= 1 AND interval_hours <= 168', name='ck_analytics_refresh_interval'),
        CheckConstraint('max_runs >= 1 AND max_runs <= 365', name='ck_analytics_refresh_runs'),
        CheckConstraint('run_count >= 0 AND run_count <= max_runs', name='ck_analytics_refresh_run_count'),
        CheckConstraint('revision >= 1', name='ck_analytics_refresh_revision'),
        Index('ix_analytics_refresh_due', 'enabled', 'next_due_at'),
    )
    plan_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(String(64), ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False)
    project_id: Mapped[str] = mapped_column(String(64), ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False)
    publication_id: Mapped[str] = mapped_column(String(64), ForeignKey('publications.publication_id', ondelete='RESTRICT'), nullable=False)
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    target_binding_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    publication_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    config_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    interval_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    max_runs: Mapped[int] = mapped_column(Integer, nullable=False)
    run_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    next_due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    updated_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AnalyticsRefreshOccurrenceORM(Base):
    __tablename__ = 'analytics_refresh_occurrences'
    __table_args__ = (
        UniqueConstraint('plan_id', 'ordinal', name='uq_analytics_refresh_occurrence'),
        UniqueConstraint('sync_id', name='uq_analytics_refresh_occurrence_sync'),
        CheckConstraint('ordinal >= 1', name='ck_analytics_refresh_ordinal'),
        CheckConstraint('skipped_slots >= 0', name='ck_analytics_refresh_skipped_slots'),
    )
    occurrence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey('analytics_refresh_plans.plan_id', ondelete='RESTRICT'), nullable=False)
    sync_id: Mapped[str] = mapped_column(String(64), ForeignKey('analytics_sync_jobs.sync_id', ondelete='RESTRICT'), nullable=False)
    plan_revision: Mapped[int] = mapped_column(Integer, nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    planned_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    skipped_slots: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AnalyticsRefreshEventORM(Base):
    __tablename__ = 'analytics_refresh_events'
    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(64), ForeignKey('analytics_refresh_plans.plan_id', ondelete='RESTRICT'), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
