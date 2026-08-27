"""add version-bound audio subtitle render approval and QC records

Revision ID: 0007_v2_08
Revises: 0006_v2_07
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_v2_08"
down_revision: Union[str, None] = "0006_v2_07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "production_packages",
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("current_subtitle_version_id", sa.String(length=64), nullable=False),
        sa.Column("current_subtitle_version", sa.Integer(), nullable=False),
        sa.Column("current_audio_version_id", sa.String(length=64), nullable=False),
        sa.Column("current_audio_version", sa.Integer(), nullable=False),
        sa.Column("current_approval_id", sa.String(length=64), nullable=True),
        sa.Column("latest_review_render_id", sa.String(length=64), nullable=True),
        sa.Column("latest_final_render_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("timeline_version >= 1", name="ck_production_package_timeline_version"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_id"], ["timelines.timeline_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_version_id"], ["timeline_versions.timeline_version_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("package_id"),
        sa.UniqueConstraint("project_id", name="uq_production_package_project"),
    )
    op.create_index(
        "ix_production_package_workspace_updated",
        "production_packages",
        ["workspace_id", "updated_at"],
    )
    op.create_table(
        "subtitle_versions",
        sa.Column("subtitle_version_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("cues_json", sa.JSON(), nullable=False),
        sa.Column("style_json", sa.JSON(), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_subtitle_version"),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_version_id"], ["timeline_versions.timeline_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("subtitle_version_id"),
        sa.UniqueConstraint("package_id", "version", name="uq_subtitle_package_version"),
    )
    op.create_index("ix_subtitle_project_created", "subtitle_versions", ["project_id", "created_at"])
    op.create_table(
        "audio_mix_versions",
        sa.Column("audio_version_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("provider_status", sa.String(length=32), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_audio_mix_version"),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_version_id"], ["timeline_versions.timeline_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("audio_version_id"),
        sa.UniqueConstraint("package_id", "version", name="uq_audio_mix_package_version"),
    )
    op.create_index("ix_audio_mix_project_created", "audio_mix_versions", ["project_id", "created_at"])
    op.create_table(
        "production_approvals",
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("preview_render_id", sa.String(length=64), nullable=False),
        sa.Column("preview_version", sa.Integer(), nullable=False),
        sa.Column("subtitle_version_id", sa.String(length=64), nullable=False),
        sa.Column("subtitle_version", sa.Integer(), nullable=False),
        sa.Column("audio_version_id", sa.String(length=64), nullable=False),
        sa.Column("audio_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requester_ref", sa.String(length=160), nullable=False),
        sa.Column("reviewer_ref", sa.String(length=160), nullable=True),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("decision_comment", sa.Text(), nullable=False),
        sa.Column("invalidated_reason", sa.String(length=500), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["timeline_version_id"], ["timeline_versions.timeline_version_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("approval_id"),
    )
    op.create_index("ix_production_approval_project_updated", "production_approvals", ["project_id", "updated_at"])
    op.create_index("ix_production_approval_status", "production_approvals", ["status"])
    op.create_table(
        "production_render_jobs",
        sa.Column("render_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version_id", sa.String(length=64), nullable=False),
        sa.Column("timeline_version", sa.Integer(), nullable=False),
        sa.Column("subtitle_version_id", sa.String(length=64), nullable=False),
        sa.Column("subtitle_version", sa.Integer(), nullable=False),
        sa.Column("audio_version_id", sa.String(length=64), nullable=False),
        sa.Column("audio_version", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.String(length=64), nullable=True),
        sa.Column("render_kind", sa.String(length=16), nullable=False),
        sa.Column("profile", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("output_asset_id", sa.String(length=64), nullable=True),
        sa.Column("qc_status", sa.String(length=16), nullable=False),
        sa.Column("qc_report_json", sa.JSON(), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("cancellation_requested", sa.Boolean(), nullable=False),
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_production_render_progress"),
        sa.ForeignKeyConstraint(["output_asset_id"], ["assets.asset_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("render_id"),
        sa.UniqueConstraint("package_id", "render_kind", "version", name="uq_production_render_kind_version"),
    )
    op.create_index("ix_production_render_status_created", "production_render_jobs", ["status", "created_at"])
    op.create_index("ix_production_render_project_created", "production_render_jobs", ["project_id", "created_at"])
    op.create_table(
        "production_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("ix_production_event_project_created", "production_events", ["project_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_production_event_project_created", table_name="production_events")
    op.drop_table("production_events")
    op.drop_index("ix_production_render_project_created", table_name="production_render_jobs")
    op.drop_index("ix_production_render_status_created", table_name="production_render_jobs")
    op.drop_table("production_render_jobs")
    op.drop_index("ix_production_approval_status", table_name="production_approvals")
    op.drop_index("ix_production_approval_project_updated", table_name="production_approvals")
    op.drop_table("production_approvals")
    op.drop_index("ix_audio_mix_project_created", table_name="audio_mix_versions")
    op.drop_table("audio_mix_versions")
    op.drop_index("ix_subtitle_project_created", table_name="subtitle_versions")
    op.drop_table("subtitle_versions")
    op.drop_index("ix_production_package_workspace_updated", table_name="production_packages")
    op.drop_table("production_packages")
