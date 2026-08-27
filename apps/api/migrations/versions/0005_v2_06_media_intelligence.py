"""add media intelligence, rights provenance and asynchronous resolution

Revision ID: 0005_v2_06
Revises: 0004_v2_05
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_v2_06"
down_revision: Union[str, None] = "0004_v2_05"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "media_plans",
        sa.Column("media_plan_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("provider_status_json", sa.JSON(), nullable=False),
        sa.Column("projected_ai_cost_vnd", sa.Numeric(20, 4), nullable=False),
        sa.Column("max_ai_cost_vnd", sa.Numeric(20, 4), nullable=False),
        sa.Column("needs_approval", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("max_ai_cost_vnd >= 0", name="ck_media_plan_max_cost"),
        sa.CheckConstraint("projected_ai_cost_vnd >= 0", name="ck_media_plan_projected_cost"),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vision_analysis_id"], ["vision_analyses.vision_analysis_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("media_plan_id"),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_media_plan_project_fingerprint"),
    )
    op.create_index("ix_media_plan_project_created", "media_plans", ["project_id", "created_at"])
    op.create_table(
        "media_plan_items",
        sa.Column("media_plan_item_id", sa.String(length=64), nullable=False),
        sa.Column("media_plan_id", sa.String(length=64), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("fallback_json", sa.JSON(), nullable=False),
        sa.Column("broll_json", sa.JSON(), nullable=False),
        sa.Column("candidates_json", sa.JSON(), nullable=False),
        sa.Column("source_asset_id", sa.String(length=64), nullable=True),
        sa.Column("selected_media_asset_id", sa.String(length=64), nullable=True),
        sa.Column("estimated_cost_vnd", sa.Numeric(20, 4), nullable=False),
        sa.Column("needs_approval", sa.Boolean(), nullable=False),
        sa.Column("needs_attention", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("estimated_cost_vnd >= 0", name="ck_media_plan_item_cost"),
        sa.ForeignKeyConstraint(["media_plan_id"], ["media_plans.media_plan_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_asset_id"], ["assets.asset_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("media_plan_item_id"),
        sa.UniqueConstraint("media_plan_id", "ordinal", name="uq_media_plan_item_ordinal"),
    )
    op.create_table(
        "media_asset_provenance",
        sa.Column("media_asset_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("media_plan_id", sa.String(length=64), nullable=False),
        sa.Column("media_plan_item_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("rights_status", sa.String(length=40), nullable=False),
        sa.Column("license", sa.String(length=240), nullable=False),
        sa.Column("license_url", sa.String(length=1000), nullable=True),
        sa.Column("provider", sa.String(length=120), nullable=False),
        sa.Column("provider_asset_id", sa.String(length=240), nullable=True),
        sa.Column("creator", sa.String(length=240), nullable=True),
        sa.Column("source_reference", sa.String(length=1000), nullable=False),
        sa.Column("attribution_requirement", sa.String(length=1000), nullable=True),
        sa.Column("generation_provenance_json", sa.JSON(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("orientation", sa.String(length=32), nullable=False),
        sa.Column("production_eligible", sa.Boolean(), nullable=False),
        sa.Column("publishing_allowed", sa.Boolean(), nullable=False),
        sa.Column("owner_override_recorded", sa.Boolean(), nullable=False),
        sa.Column("downloaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["media_plan_id"], ["media_plans.media_plan_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_plan_item_id"], ["media_plan_items.media_plan_item_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("media_asset_id"),
        sa.UniqueConstraint("asset_id", name="uq_media_asset_provenance_asset"),
    )
    op.create_index(
        "ix_media_asset_project_created",
        "media_asset_provenance",
        ["project_id", "created_at"],
    )
    op.create_table(
        "media_resolution_jobs",
        sa.Column("resolution_job_id", sa.String(length=64), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("media_plan_id", sa.String(length=64), nullable=False),
        sa.Column("media_plan_item_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("capability", sa.String(length=80), nullable=False),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("provider_job_id", sa.String(length=240), nullable=True),
        sa.Column("selected_candidate_id", sa.String(length=120), nullable=True),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("estimated_cost_vnd", sa.Numeric(20, 4), nullable=True),
        sa.Column("actual_cost_vnd", sa.Numeric(20, 4), nullable=True),
        sa.Column("output_media_asset_id", sa.String(length=64), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("failure_reason", sa.String(length=1000), nullable=True),
        sa.Column("external_call", sa.Boolean(), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("real_provider_tested", sa.Boolean(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("actual_cost_vnd IS NULL OR actual_cost_vnd >= 0", name="ck_media_resolution_actual_cost"),
        sa.CheckConstraint("estimated_cost_vnd IS NULL OR estimated_cost_vnd >= 0", name="ck_media_resolution_estimated_cost"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="ck_media_resolution_progress"),
        sa.ForeignKeyConstraint(["media_plan_id"], ["media_plans.media_plan_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_plan_item_id"], ["media_plan_items.media_plan_item_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("resolution_job_id"),
        sa.UniqueConstraint("fingerprint", name="uq_media_resolution_job_fingerprint"),
    )
    op.create_index(
        "ix_media_resolution_status_created",
        "media_resolution_jobs",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_media_resolution_status_created", table_name="media_resolution_jobs")
    op.drop_table("media_resolution_jobs")
    op.drop_index("ix_media_asset_project_created", table_name="media_asset_provenance")
    op.drop_table("media_asset_provenance")
    op.drop_table("media_plan_items")
    op.drop_index("ix_media_plan_project_created", table_name="media_plans")
    op.drop_table("media_plans")
