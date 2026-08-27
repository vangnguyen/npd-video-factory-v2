from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utc_now


class AnalyticsSyncORM(Base):
    __tablename__ = "analytics_sync_jobs"
    __table_args__ = (
        UniqueConstraint("project_id", "idempotency_key_hash", name="uq_analytics_sync_project_idempotency"),
        CheckConstraint("external_call = false", name="ck_analytics_sync_no_external_call_v2_10"),
        Index("ix_analytics_sync_status_schedule", "status", "scheduled_for", "next_retry_at"),
        Index("ix_analytics_sync_project_created", "project_id", "created_at"),
    )

    sync_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(40), nullable=False)
    fixture_profile: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    idempotency_key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AnalyticsMetricSnapshotORM(Base):
    __tablename__ = "analytics_metric_snapshots"
    __table_args__ = (
        UniqueConstraint("sync_id", name="uq_analytics_snapshot_sync"),
        CheckConstraint("external_call = false", name="ck_analytics_snapshot_no_external_call_v2_10"),
        Index("ix_analytics_snapshot_project_collected", "project_id", "collected_at"),
    )

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sync_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_sync_jobs.sync_id", ondelete="CASCADE"), nullable=False
    )
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="RESTRICT"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    platform: Mapped[str] = mapped_column(String(40), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    source: Mapped[str] = mapped_column(String(240), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(30), nullable=False)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    mock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    external_call: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)

class AnalyticsMetricPointORM(Base):
    __tablename__ = "analytics_metric_points"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "metric_name", name="uq_analytics_point_snapshot_metric"),
        CheckConstraint("value IS NULL OR value >= 0", name="ck_analytics_metric_nonnegative"),
    )

    point_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_metric_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    metric_name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[Decimal | None] = mapped_column(Numeric(30, 8), nullable=True)
    unit: Mapped[str] = mapped_column(String(80), nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, nullable=False)


class AnalyticsFeatureSnapshotORM(Base):
    __tablename__ = "analytics_feature_snapshots"
    __table_args__ = (UniqueConstraint("snapshot_id", name="uq_analytics_feature_snapshot"),)

    feature_snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_metric_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    trend_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idea_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    hook_type: Mapped[str | None] = mapped_column(String(160), nullable=True)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    scene_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtitle_template: Mapped[str | None] = mapped_column(String(160), nullable=True)
    voice_profile: Mapped[str | None] = mapped_column(String(160), nullable=True)
    music_profile: Mapped[str | None] = mapped_column(String(160), nullable=True)
    visual_strategy: Mapped[str | None] = mapped_column(String(240), nullable=True)
    niche: Mapped[str | None] = mapped_column(String(80), nullable=True)
    topic: Mapped[str | None] = mapped_column(Text, nullable=True)
    cta: Mapped[str | None] = mapped_column(Text, nullable=True)
    publishing_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class WinnerAssessmentORM(Base):
    __tablename__ = "analytics_winner_assessments"
    __table_args__ = (
        UniqueConstraint("snapshot_id", name="uq_analytics_assessment_snapshot"),
        CheckConstraint("automatic_action = false", name="ck_analytics_assessment_no_auto_action"),
        CheckConstraint("paid_media_mutation = false", name="ck_analytics_assessment_no_budget_mutation"),
        CheckConstraint("content_deletion = false", name="ck_analytics_assessment_no_delete"),
        Index("ix_analytics_assessment_project_created", "project_id", "created_at"),
    )

    assessment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_metric_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(40), nullable=False)
    score: Mapped[Decimal | None] = mapped_column(Numeric(8, 3), nullable=True)
    data_coverage: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    factors_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    recommendations_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    automatic_action: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    paid_media_mutation: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content_deletion: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AnalyticsLearningInsightORM(Base):
    __tablename__ = "analytics_learning_insights"
    __table_args__ = (
        CheckConstraint("applied = false", name="ck_analytics_insight_not_auto_applied"),
        CheckConstraint("autonomous_execution = false", name="ck_analytics_insight_no_execution"),
        Index("ix_analytics_insight_project_created", "project_id", "created_at"),
    )

    insight_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    publication_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("publications.publication_id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_metric_snapshots.snapshot_id", ondelete="CASCADE"), nullable=False
    )
    assessment_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_winner_assessments.assessment_id", ondelete="CASCADE"), nullable=False
    )
    trend_cluster_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    idea_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    insight_type: Mapped[str] = mapped_column(String(60), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 6), nullable=False)
    evidence_refs_json: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    applied: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    autonomous_execution: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AnalyticsEventORM(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (Index("ix_analytics_event_project_created", "project_id", "created_at"),)

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    sync_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("analytics_sync_jobs.sync_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(120), nullable=False)
    actor_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
