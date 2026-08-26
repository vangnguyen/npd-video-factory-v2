"""add trend radar and idea intelligence

Revision ID: 0002_v2_03
Revises: 0001_v2_02
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0002_v2_03"
down_revision: Union[str, None] = "0001_v2_02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def versioned_columns() -> list[sa.Column]:
    return [
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "trend_sources",
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("authorized_access", sa.Boolean(), nullable=False),
        sa.Column("config_ref", sa.String(length=240), nullable=True),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("source_id"),
        sa.UniqueConstraint("workspace_id", "provider_key", name="uq_trend_source_scope_provider"),
    )
    op.create_index(op.f("ix_trend_sources_workspace_id"), "trend_sources", ["workspace_id"], unique=False)

    op.create_table(
        "trend_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("query_json", sa.JSON(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("new_signal_count", sa.Integer(), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["source_id"], ["trend_sources.source_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_trend_snapshots_workspace_collected",
        "trend_snapshots",
        ["workspace_id", "collected_at"],
        unique=False,
    )

    op.create_table(
        "trend_signals",
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=80), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("country", sa.String(length=2), nullable=True),
        sa.Column("locale", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=12), nullable=True),
        sa.Column("keyword", sa.String(length=240), nullable=True),
        sa.Column("topic", sa.String(length=300), nullable=True),
        sa.Column("hashtags_json", sa.JSON(), nullable=False),
        sa.Column("media_type", sa.String(length=80), nullable=True),
        sa.Column("format", sa.String(length=80), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("views", sa.Integer(), nullable=True),
        sa.Column("likes", sa.Integer(), nullable=True),
        sa.Column("comments", sa.Integer(), nullable=True),
        sa.Column("shares", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("engagement", sa.Numeric(precision=20, scale=6), nullable=True),
        sa.Column("creator_count", sa.Integer(), nullable=True),
        sa.Column("content_count", sa.Integer(), nullable=True),
        sa.Column("velocity", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("acceleration", sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column("raw_signal_hash", sa.String(length=64), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["snapshot_id"], ["trend_snapshots.snapshot_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_id"], ["trend_sources.source_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("signal_id"),
        sa.UniqueConstraint("workspace_id", "source", "raw_signal_hash", name="uq_trend_signal_source_hash"),
    )
    op.create_index("ix_trend_signals_topic", "trend_signals", ["workspace_id", "topic"], unique=False)
    op.create_index(
        "ix_trend_signals_workspace_observed",
        "trend_signals",
        ["workspace_id", "observed_at"],
        unique=False,
    )

    op.create_table(
        "trend_evidence",
        sa.Column("evidence_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("claim", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=1200), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("freshness", sa.String(length=40), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["signal_id"], ["trend_signals.signal_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index("ix_trend_evidence_signal", "trend_evidence", ["signal_id", "retrieved_at"], unique=False)

    op.create_table(
        "trend_clusters",
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("canonical_key", sa.String(length=200), nullable=False),
        sa.Column("topic", sa.String(length=300), nullable=False),
        sa.Column("summary", sa.String(length=1200), nullable=False),
        sa.Column("lifecycle", sa.String(length=30), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("platforms_json", sa.JSON(), nullable=False),
        sa.Column("keywords_json", sa.JSON(), nullable=False),
        sa.Column("hashtags_json", sa.JSON(), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cluster_id"),
        sa.UniqueConstraint("workspace_id", "canonical_key", name="uq_trend_cluster_canonical_key"),
    )
    op.create_index(
        "ix_trend_clusters_workspace_lifecycle",
        "trend_clusters",
        ["workspace_id", "lifecycle"],
        unique=False,
    )

    op.create_table(
        "trend_cluster_signals",
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("signal_id", sa.String(length=64), nullable=False),
        sa.Column("similarity", sa.Numeric(precision=6, scale=5), nullable=False),
        sa.ForeignKeyConstraint(["cluster_id"], ["trend_clusters.cluster_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["signal_id"], ["trend_signals.signal_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cluster_id", "signal_id"),
    )

    op.create_table(
        "trend_scores",
        sa.Column("trend_score_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("niche", sa.String(length=80), nullable=False),
        sa.Column("business_objective", sa.String(length=80), nullable=False),
        sa.Column("profile_hash", sa.String(length=64), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("components_json", sa.JSON(), nullable=False),
        sa.Column("weights_json", sa.JSON(), nullable=False),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        *versioned_columns(),
        sa.CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_trend_score_range"),
        sa.ForeignKeyConstraint(["cluster_id"], ["trend_clusters.cluster_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("trend_score_id"),
        sa.UniqueConstraint("cluster_id", "profile_hash", name="uq_trend_score_cluster_profile"),
    )
    op.create_index(
        "ix_trend_scores_workspace_total",
        "trend_scores",
        ["workspace_id", "total_score"],
        unique=False,
    )

    op.create_table(
        "idea_candidates",
        sa.Column("idea_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("generation_key", sa.String(length=64), nullable=False),
        sa.Column("variant_key", sa.String(length=80), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("niche", sa.String(length=80), nullable=False),
        sa.Column("business_objective", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("angle", sa.String(length=600), nullable=False),
        sa.Column("hook_concept", sa.String(length=600), nullable=False),
        sa.Column("format", sa.String(length=80), nullable=False),
        sa.Column("recommended_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("visual_concept", sa.String(length=1000), nullable=False),
        sa.Column("audience", sa.String(length=500), nullable=False),
        sa.Column("cta_concept", sa.String(length=500), nullable=False),
        sa.Column("trend_references_json", sa.JSON(), nullable=False),
        sa.Column("originality_notes", sa.String(length=1200), nullable=False),
        sa.Column("brief_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["cluster_id"], ["trend_clusters.cluster_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("idea_id"),
        sa.UniqueConstraint("cluster_id", "generation_key", "variant_key", name="uq_idea_generation_variant"),
    )
    op.create_index(
        "ix_idea_candidates_workspace_status",
        "idea_candidates",
        ["workspace_id", "status"],
        unique=False,
    )

    op.create_table(
        "idea_scores",
        sa.Column("idea_score_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("idea_id", sa.String(length=64), nullable=False),
        sa.Column("total_score", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("components_json", sa.JSON(), nullable=False),
        sa.Column("estimated", sa.Boolean(), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        *versioned_columns(),
        sa.CheckConstraint("total_score >= 0 AND total_score <= 100", name="ck_idea_score_range"),
        sa.ForeignKeyConstraint(["idea_id"], ["idea_candidates.idea_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("idea_score_id"),
        sa.UniqueConstraint("idea_id", name="uq_idea_score_idea"),
    )

    op.create_table(
        "channel_opportunities",
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("idea_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("rank_score", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("rationale_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["cluster_id"], ["trend_clusters.cluster_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["idea_candidates.idea_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("opportunity_id"),
        sa.UniqueConstraint("workspace_id", "idea_id", "channel", name="uq_channel_opportunity_idea"),
    )
    op.create_index(
        "ix_channel_opportunities_workspace_score",
        "channel_opportunities",
        ["workspace_id", "rank_score"],
        unique=False,
    )

    op.create_table(
        "content_queue_items",
        sa.Column("queue_item_id", sa.String(length=64), nullable=False),
        sa.Column("queue_run_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("opportunity_id", sa.String(length=64), nullable=False),
        sa.Column("cluster_id", sa.String(length=64), nullable=False),
        sa.Column("idea_id", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=80), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Numeric(precision=7, scale=3), nullable=False),
        sa.Column("state", sa.String(length=30), nullable=False),
        sa.Column("evidence_summary_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["cluster_id"], ["trend_clusters.cluster_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["idea_id"], ["idea_candidates.idea_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["opportunity_id"], ["channel_opportunities.opportunity_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("queue_item_id"),
        sa.UniqueConstraint("queue_run_id", "rank", name="uq_content_queue_run_rank"),
    )
    op.create_index(
        "ix_content_queue_workspace_rank",
        "content_queue_items",
        ["workspace_id", "rank"],
        unique=False,
    )

    op.create_table(
        "research_evidence",
        sa.Column("research_evidence_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("idea_id", sa.String(length=64), nullable=True),
        sa.Column("claim", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.String(length=1200), nullable=False),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("freshness", sa.String(length=40), nullable=False),
        sa.Column("fact_class", sa.String(length=40), nullable=False),
        *versioned_columns(),
        sa.ForeignKeyConstraint(["idea_id"], ["idea_candidates.idea_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("research_evidence_id"),
    )
    op.create_index(
        "ix_research_evidence_idea",
        "research_evidence",
        ["idea_id", "retrieved_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_research_evidence_idea", table_name="research_evidence")
    op.drop_table("research_evidence")
    op.drop_index("ix_content_queue_workspace_rank", table_name="content_queue_items")
    op.drop_table("content_queue_items")
    op.drop_index("ix_channel_opportunities_workspace_score", table_name="channel_opportunities")
    op.drop_table("channel_opportunities")
    op.drop_table("idea_scores")
    op.drop_index("ix_idea_candidates_workspace_status", table_name="idea_candidates")
    op.drop_table("idea_candidates")
    op.drop_index("ix_trend_scores_workspace_total", table_name="trend_scores")
    op.drop_table("trend_scores")
    op.drop_table("trend_cluster_signals")
    op.drop_index("ix_trend_clusters_workspace_lifecycle", table_name="trend_clusters")
    op.drop_table("trend_clusters")
    op.drop_index("ix_trend_evidence_signal", table_name="trend_evidence")
    op.drop_table("trend_evidence")
    op.drop_index("ix_trend_signals_workspace_observed", table_name="trend_signals")
    op.drop_index("ix_trend_signals_topic", table_name="trend_signals")
    op.drop_table("trend_signals")
    op.drop_index("ix_trend_snapshots_workspace_collected", table_name="trend_snapshots")
    op.drop_table("trend_snapshots")
    op.drop_index(op.f("ix_trend_sources_workspace_id"), table_name="trend_sources")
    op.drop_table("trend_sources")
