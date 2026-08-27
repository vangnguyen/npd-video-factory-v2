"""add analytics snapshots winner assessments and learning feedback

Revision ID: 0009_v2_10
Revises: 0008_v2_09
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009_v2_10"
down_revision: Union[str, None] = "0008_v2_09"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "analytics_sync_jobs",
        sa.Column("sync_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("provider_mode", sa.String(length=20), nullable=False),
        sa.Column("trigger", sa.String(length=40), nullable=False),
        sa.Column("fixture_profile", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("snapshot_id", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.Column("external_call", sa.Boolean(), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("external_call = false", name="ck_analytics_sync_no_external_call_v2_10"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("sync_id"),
        sa.UniqueConstraint("project_id", "idempotency_key_hash", name="uq_analytics_sync_project_idempotency"),
    )
    op.create_index(
        "ix_analytics_sync_status_schedule",
        "analytics_sync_jobs",
        ["status", "scheduled_for", "next_retry_at"],
    )
    op.create_index(
        "ix_analytics_sync_project_created",
        "analytics_sync_jobs",
        ["project_id", "created_at"],
    )
    op.create_table(
        "analytics_metric_snapshots",
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("sync_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("source", sa.String(length=240), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.Column("external_call", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("external_call = false", name="ck_analytics_snapshot_no_external_call_v2_10"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_id"], ["analytics_sync_jobs.sync_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint("sync_id", name="uq_analytics_snapshot_sync"),
    )
    op.create_index(
        "ix_analytics_snapshot_project_collected",
        "analytics_metric_snapshots",
        ["project_id", "collected_at"],
    )
    op.create_table(
        "analytics_metric_points",
        sa.Column("point_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Numeric(precision=30, scale=8), nullable=True),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("supported", sa.Boolean(), nullable=False),
        sa.CheckConstraint("value IS NULL OR value >= 0", name="ck_analytics_metric_nonnegative"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["analytics_metric_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("point_id"),
        sa.UniqueConstraint("snapshot_id", "metric_name", name="uq_analytics_point_snapshot_metric"),
    )
    op.create_table(
        "analytics_feature_snapshots",
        sa.Column("feature_snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("trend_cluster_id", sa.String(length=64), nullable=True),
        sa.Column("idea_id", sa.String(length=64), nullable=True),
        sa.Column("hook_type", sa.String(length=160), nullable=True),
        sa.Column("duration_seconds", sa.Numeric(precision=12, scale=3), nullable=True),
        sa.Column("scene_count", sa.Integer(), nullable=True),
        sa.Column("subtitle_template", sa.String(length=160), nullable=True),
        sa.Column("voice_profile", sa.String(length=160), nullable=True),
        sa.Column("music_profile", sa.String(length=160), nullable=True),
        sa.Column("visual_strategy", sa.String(length=240), nullable=True),
        sa.Column("niche", sa.String(length=80), nullable=True),
        sa.Column("topic", sa.Text(), nullable=True),
        sa.Column("cta", sa.Text(), nullable=True),
        sa.Column("publishing_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["analytics_metric_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("feature_snapshot_id"),
        sa.UniqueConstraint("snapshot_id", name="uq_analytics_feature_snapshot"),
    )
    op.create_table(
        "analytics_winner_assessments",
        sa.Column("assessment_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("score", sa.Numeric(precision=8, scale=3), nullable=True),
        sa.Column("data_coverage", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("factors_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("recommendations_json", sa.JSON(), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("automatic_action", sa.Boolean(), nullable=False),
        sa.Column("paid_media_mutation", sa.Boolean(), nullable=False),
        sa.Column("content_deletion", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("automatic_action = false", name="ck_analytics_assessment_no_auto_action"),
        sa.CheckConstraint("paid_media_mutation = false", name="ck_analytics_assessment_no_budget_mutation"),
        sa.CheckConstraint("content_deletion = false", name="ck_analytics_assessment_no_delete"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["analytics_metric_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("assessment_id"),
        sa.UniqueConstraint("snapshot_id", name="uq_analytics_assessment_snapshot"),
    )
    op.create_index(
        "ix_analytics_assessment_project_created",
        "analytics_winner_assessments",
        ["project_id", "created_at"],
    )
    op.create_table(
        "analytics_learning_insights",
        sa.Column("insight_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("snapshot_id", sa.String(length=64), nullable=False),
        sa.Column("assessment_id", sa.String(length=64), nullable=False),
        sa.Column("trend_cluster_id", sa.String(length=64), nullable=True),
        sa.Column("idea_id", sa.String(length=64), nullable=True),
        sa.Column("insight_type", sa.String(length=60), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=8, scale=6), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("autonomous_execution", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("applied = false", name="ck_analytics_insight_not_auto_applied"),
        sa.CheckConstraint("autonomous_execution = false", name="ck_analytics_insight_no_execution"),
        sa.ForeignKeyConstraint(["assessment_id"], ["analytics_winner_assessments.assessment_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["analytics_metric_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("insight_id"),
    )
    op.create_index(
        "ix_analytics_insight_project_created",
        "analytics_learning_insights",
        ["project_id", "created_at"],
    )
    op.create_table(
        "analytics_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("sync_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sync_id"], ["analytics_sync_jobs.sync_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_analytics_event_project_created",
        "analytics_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_analytics_event_project_created", table_name="analytics_events")
    op.drop_table("analytics_events")
    op.drop_index("ix_analytics_insight_project_created", table_name="analytics_learning_insights")
    op.drop_table("analytics_learning_insights")
    op.drop_index("ix_analytics_assessment_project_created", table_name="analytics_winner_assessments")
    op.drop_table("analytics_winner_assessments")
    op.drop_table("analytics_feature_snapshots")
    op.drop_table("analytics_metric_points")
    op.drop_index("ix_analytics_snapshot_project_collected", table_name="analytics_metric_snapshots")
    op.drop_table("analytics_metric_snapshots")
    op.drop_index("ix_analytics_sync_project_created", table_name="analytics_sync_jobs")
    op.drop_index("ix_analytics_sync_status_schedule", table_name="analytics_sync_jobs")
    op.drop_table("analytics_sync_jobs")
