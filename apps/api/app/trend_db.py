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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, VersionedMixin, utc_now


class TrendSourceORM(VersionedMixin, Base):
    __tablename__ = "trend_sources"
    __table_args__ = (
        UniqueConstraint("workspace_id", "provider_key", name="uq_trend_source_scope_provider"),
    )

    source_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="not_configured")
    authorized_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_ref: Mapped[str | None] = mapped_column(String(240), nullable=True)
    capabilities_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class TrendSnapshotORM(VersionedMixin, Base):
    __tablename__ = "trend_snapshots"
    __table_args__ = (Index("ix_trend_snapshots_workspace_collected", "workspace_id", "collected_at"),)

    snapshot_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_sources.source_id", ondelete="RESTRICT"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(120), nullable=False)
    query_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    new_signal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TrendSignalORM(VersionedMixin, Base):
    __tablename__ = "trend_signals"
    __table_args__ = (
        UniqueConstraint("workspace_id", "source", "raw_signal_hash", name="uq_trend_signal_source_hash"),
        Index("ix_trend_signals_workspace_observed", "workspace_id", "observed_at"),
        Index("ix_trend_signals_topic", "workspace_id", "topic"),
    )

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    snapshot_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_snapshots.snapshot_id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_sources.source_id", ondelete="RESTRICT"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    locale: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    keyword: Mapped[str | None] = mapped_column(String(240), nullable=True)
    topic: Mapped[str | None] = mapped_column(String(300), nullable=True)
    hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    media_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    format: Mapped[str | None] = mapped_column(String(80), nullable=True)
    duration_seconds: Mapped[Decimal | None] = mapped_column(Numeric(12, 3), nullable=True)
    views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    likes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shares: Mapped[int | None] = mapped_column(Integer, nullable=True)
    saves: Mapped[int | None] = mapped_column(Integer, nullable=True)
    engagement: Mapped[Decimal | None] = mapped_column(Numeric(20, 6), nullable=True)
    creator_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    velocity: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    acceleration: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    raw_signal_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class TrendEvidenceORM(VersionedMixin, Base):
    __tablename__ = "trend_evidence"
    __table_args__ = (Index("ix_trend_evidence_signal", "signal_id", "retrieved_at"),)

    evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    signal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_signals.signal_id", ondelete="CASCADE"), nullable=False
    )
    claim: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(1200), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False)


class TrendClusterORM(VersionedMixin, Base):
    __tablename__ = "trend_clusters"
    __table_args__ = (
        UniqueConstraint("workspace_id", "canonical_key", name="uq_trend_cluster_canonical_key"),
        Index("ix_trend_clusters_workspace_lifecycle", "workspace_id", "lifecycle"),
    )

    cluster_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    canonical_key: Mapped[str] = mapped_column(String(200), nullable=False)
    topic: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(String(1200), nullable=False)
    lifecycle: Mapped[str] = mapped_column(String(30), nullable=False)
    first_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, nullable=False)
    platforms_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    hashtags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class TrendClusterSignalORM(Base):
    __tablename__ = "trend_cluster_signals"

    cluster_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_clusters.cluster_id", ondelete="CASCADE"), primary_key=True
    )
    signal_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_signals.signal_id", ondelete="CASCADE"), primary_key=True
    )
    similarity: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False)


class TrendScoreORM(VersionedMixin, Base):
    __tablename__ = "trend_scores"
    __table_args__ = (
        UniqueConstraint("cluster_id", "profile_hash", name="uq_trend_score_cluster_profile"),
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_trend_score_range"),
        Index("ix_trend_scores_workspace_total", "workspace_id", "total_score"),
    )

    trend_score_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_clusters.cluster_id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    niche: Mapped[str] = mapped_column(String(80), nullable=False)
    business_objective: Mapped[str] = mapped_column(String(80), nullable=False)
    profile_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    total_score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    components_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    weights_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class IdeaCandidateORM(VersionedMixin, Base):
    __tablename__ = "idea_candidates"
    __table_args__ = (
        UniqueConstraint("cluster_id", "generation_key", "variant_key", name="uq_idea_generation_variant"),
        Index("ix_idea_candidates_workspace_status", "workspace_id", "status"),
    )

    idea_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_clusters.cluster_id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("video_projects.project_id", ondelete="SET NULL"), nullable=True
    )
    generation_key: Mapped[str] = mapped_column(String(64), nullable=False)
    variant_key: Mapped[str] = mapped_column(String(80), nullable=False)
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    niche: Mapped[str] = mapped_column(String(80), nullable=False)
    business_objective: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    angle: Mapped[str] = mapped_column(String(600), nullable=False)
    hook_concept: Mapped[str] = mapped_column(String(600), nullable=False)
    format: Mapped[str] = mapped_column(String(80), nullable=False)
    recommended_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    visual_concept: Mapped[str] = mapped_column(String(1000), nullable=False)
    audience: Mapped[str] = mapped_column(String(500), nullable=False)
    cta_concept: Mapped[str] = mapped_column(String(500), nullable=False)
    trend_references_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    originality_notes: Mapped[str] = mapped_column(String(1200), nullable=False)
    brief_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")


class IdeaScoreORM(VersionedMixin, Base):
    __tablename__ = "idea_scores"
    __table_args__ = (
        UniqueConstraint("idea_id", name="uq_idea_score_idea"),
        CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_idea_score_range"),
    )

    idea_score_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    idea_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("idea_candidates.idea_id", ondelete="CASCADE"), nullable=False
    )
    total_score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    components_json: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    estimated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    rationale_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)


class ChannelOpportunityORM(VersionedMixin, Base):
    __tablename__ = "channel_opportunities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "idea_id", "channel", name="uq_channel_opportunity_idea"),
        Index("ix_channel_opportunities_workspace_score", "workspace_id", "rank_score"),
    )

    opportunity_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_clusters.cluster_id", ondelete="CASCADE"), nullable=False
    )
    idea_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("idea_candidates.idea_id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    rank_score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    rationale_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")


class ContentQueueItemORM(VersionedMixin, Base):
    __tablename__ = "content_queue_items"
    __table_args__ = (
        UniqueConstraint("queue_run_id", "rank", name="uq_content_queue_run_rank"),
        Index("ix_content_queue_workspace_rank", "workspace_id", "rank"),
    )

    queue_item_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    queue_run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("channel_opportunities.opportunity_id", ondelete="CASCADE"), nullable=False
    )
    cluster_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("trend_clusters.cluster_id", ondelete="CASCADE"), nullable=False
    )
    idea_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("idea_candidates.idea_id", ondelete="CASCADE"), nullable=False
    )
    channel: Mapped[str] = mapped_column(String(80), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(7, 3), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="proposed")
    evidence_summary_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ResearchEvidenceORM(VersionedMixin, Base):
    __tablename__ = "research_evidence"
    __table_args__ = (Index("ix_research_evidence_idea", "idea_id", "retrieved_at"),)

    research_evidence_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("workspaces.workspace_id", ondelete="CASCADE"), nullable=False
    )
    idea_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("idea_candidates.idea_id", ondelete="CASCADE"), nullable=True
    )
    claim: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(String(1200), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(1000), nullable=False)
    retrieved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False)
    fact_class: Mapped[str] = mapped_column(String(40), nullable=False, default="verified_fact")
