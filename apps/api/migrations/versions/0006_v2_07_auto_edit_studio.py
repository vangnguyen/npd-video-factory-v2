"""add versioned timelines and proxy previews

Revision ID: 0006_v2_07
Revises: 0005_v2_06
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_v2_07"
down_revision: Union[str, None] = "0005_v2_06"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "timelines",
        sa.Column("timeline_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("source_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("source_media_plan_id", sa.String(length=64), nullable=True),
        sa.Column("current_version_id", sa.String(length=64), nullable=False),
        sa.Column("current_version", sa.Integer(), nullable=False),
        sa.Column("approval_status", sa.String(length=32), nullable=False),
        sa.Column("approved_timeline_version", sa.Integer(), nullable=True),
        sa.Column("latest_preview_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("current_version >= 1", name="ck_timeline_current_version"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_media_plan_id"], ["media_plans.media_plan_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("timeline_id"),
        sa.UniqueConstraint("project_id", name="uq_timeline_project"),
    )
    op.create_index("ix_timeline_workspace_updated", "timelines", ["workspace_id", "updated_at"])
    op.create_table(
        "timeline_versions",
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("mutation_json", sa.JSON(), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_timeline_version"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.timeline_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("timeline_version_id"),
        sa.UniqueConstraint("timeline_id", "version", name="uq_timeline_version"),
    )
    op.create_index(
        "ix_timeline_version_project_created",
        "timeline_versions",
        ["project_id", "created_at"],
    )
    op.create_table(
        "preview_jobs",
        sa.Column("preview_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("output_asset_id", sa.String(length=64), nullable=True),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.String(length=1000), nullable=True),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_preview_progress"),
        sa.ForeignKeyConstraint(["output_asset_id"], ["assets.asset_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.timeline_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_version_id"], ["timeline_versions.timeline_version_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("preview_id"),
        sa.UniqueConstraint("timeline_version_id", "width", "height", name="uq_preview_version_dimensions"),
    )
    op.create_index("ix_preview_status_created", "preview_jobs", ["status", "created_at"])
    op.create_index("ix_preview_project_created", "preview_jobs", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_preview_project_created", table_name="preview_jobs")
    op.drop_index("ix_preview_status_created", table_name="preview_jobs")
    op.drop_table("preview_jobs")
    op.drop_index("ix_timeline_version_project_created", table_name="timeline_versions")
    op.drop_table("timeline_versions")
    op.drop_index("ix_timeline_workspace_updated", table_name="timelines")
    op.drop_table("timelines")
