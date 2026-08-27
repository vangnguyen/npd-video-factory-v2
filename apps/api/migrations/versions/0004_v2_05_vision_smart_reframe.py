"""add vision analysis and smart reframe

Revision ID: 0004_v2_05
Revises: 0003_v2_04
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0004_v2_05"
down_revision: Union[str, None] = "0003_v2_04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "vision_analyses",
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("source_media_json", sa.JSON(), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.Column("best_frame_ids_json", sa.JSON(), nullable=False),
        sa.Column("thumbnail_candidate_ids_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("vision_analysis_id"),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_vision_project_fingerprint"),
    )
    op.create_index(
        "ix_vision_project_created", "vision_analyses", ["project_id", "created_at"], unique=False
    )
    op.create_table(
        "vision_frames",
        sa.Column("frame_id", sa.String(length=64), nullable=False),
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("timestamp_seconds", sa.Float(), nullable=False),
        sa.Column("evidence_frame_reference", sa.String(length=768), nullable=False),
        sa.Column("caption", sa.String(length=1000), nullable=False),
        sa.Column("scene_description", sa.String(length=2000), nullable=False),
        sa.Column("semantic_label", sa.String(length=240), nullable=False),
        sa.Column("environment", sa.String(length=240), nullable=False),
        sa.Column("action", sa.String(length=240), nullable=False),
        sa.Column("objects_json", sa.JSON(), nullable=False),
        sa.Column("ocr_json", sa.JSON(), nullable=False),
        sa.Column("composition_json", sa.JSON(), nullable=False),
        sa.Column("quality_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("model", sa.String(length=160), nullable=False),
        sa.ForeignKeyConstraint(["vision_analysis_id"], ["vision_analyses.vision_analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("frame_id"),
        sa.UniqueConstraint("vision_analysis_id", "ordinal", name="uq_vision_frame_ordinal"),
    )
    op.create_table(
        "vision_scene_insights",
        sa.Column("vision_scene_id", sa.String(length=64), nullable=False),
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("semantic_label", sa.String(length=240), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("subjects_json", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_frame_ids_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vision_analysis_id"], ["vision_analyses.vision_analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vision_scene_id"),
        sa.UniqueConstraint("vision_analysis_id", "ordinal", name="uq_vision_scene_ordinal"),
    )
    op.create_table(
        "vision_subject_tracks",
        sa.Column("track_id", sa.String(length=64), nullable=False),
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("continuity_score", sa.Float(), nullable=False),
        sa.Column("observations_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["vision_analysis_id"], ["vision_analyses.vision_analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("track_id"),
    )
    op.create_table(
        "vision_reframe_plans",
        sa.Column("reframe_id", sa.String(length=64), nullable=False),
        sa.Column("vision_analysis_id", sa.String(length=64), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=12), nullable=False),
        sa.Column("strategy", sa.String(length=40), nullable=False),
        sa.Column("subject_track_id", sa.String(length=64), nullable=True),
        sa.Column("keyframes_json", sa.JSON(), nullable=False),
        sa.Column("smoothing", sa.String(length=40), nullable=False),
        sa.Column("maximum_jump", sa.Float(), nullable=False),
        sa.Column("subtitle_safe_area_bottom", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("fallback", sa.String(length=40), nullable=False),
        sa.Column("needs_attention", sa.Boolean(), nullable=False),
        sa.Column("manual_override_applied", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["subject_track_id"], ["vision_subject_tracks.track_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vision_analysis_id"], ["vision_analyses.vision_analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("reframe_id"),
        sa.UniqueConstraint("vision_analysis_id", "aspect_ratio", name="uq_vision_reframe_aspect"),
    )


def downgrade() -> None:
    op.drop_table("vision_reframe_plans")
    op.drop_table("vision_subject_tracks")
    op.drop_table("vision_scene_insights")
    op.drop_table("vision_frames")
    op.drop_index("ix_vision_project_created", table_name="vision_analyses")
    op.drop_table("vision_analyses")
