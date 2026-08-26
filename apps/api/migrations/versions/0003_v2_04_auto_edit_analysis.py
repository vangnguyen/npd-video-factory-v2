"""add upload and auto edit analysis

Revision ID: 0003_v2_04
Revises: 0002_v2_03
Create Date: 2026-08-26
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003_v2_04"
down_revision: Union[str, None] = "0002_v2_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "upload_sessions",
        sa.Column("upload_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("safe_filename", sa.String(length=128), nullable=False),
        sa.Column("media_kind", sa.String(length=32), nullable=False),
        sa.Column("declared_content_type", sa.String(length=160), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("expected_checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("part_size_bytes", sa.Integer(), nullable=False),
        sa.Column("total_parts", sa.Integer(), nullable=False),
        sa.Column("received_parts_json", sa.JSON(), nullable=False),
        sa.Column("received_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("rights_status", sa.String(length=32), nullable=False),
        sa.Column("license", sa.String(length=160), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=True),
        sa.Column("duplicate_of_asset_id", sa.String(length=64), nullable=True),
        sa.Column("media_metadata_json", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("upload_id"),
    )
    op.create_index(
        "ix_upload_sessions_project_created",
        "upload_sessions",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "auto_edit_analyses",
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("source_media_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("analysis_id"),
        sa.UniqueConstraint("project_id", "fingerprint", name="uq_auto_edit_project_fingerprint"),
    )
    op.create_index(
        "ix_auto_edit_project_created",
        "auto_edit_analyses",
        ["project_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "transcripts",
        sa.Column("transcript_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("asset_id", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_original_evidence", sa.Boolean(), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.asset_id"]),
        sa.PrimaryKeyConstraint("transcript_id"),
        sa.UniqueConstraint("analysis_id", "version", name="uq_transcript_analysis_version"),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("transcript_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.String(length=4000), nullable=False),
        sa.Column("speaker", sa.String(length=120), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.transcript_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("segment_id"),
        sa.UniqueConstraint("transcript_id", "ordinal", name="uq_transcript_segment_ordinal"),
    )

    op.create_table(
        "transcript_words",
        sa.Column("word_id", sa.String(length=64), nullable=False),
        sa.Column("transcript_id", sa.String(length=64), nullable=False),
        sa.Column("segment_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.String(length=240), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(["segment_id"], ["transcript_segments.segment_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcript_id"], ["transcripts.transcript_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("word_id"),
        sa.UniqueConstraint("transcript_id", "ordinal", name="uq_transcript_word_ordinal"),
    )

    op.create_table(
        "scenes",
        sa.Column("scene_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("semantic_label", sa.String(length=240), nullable=False),
        sa.Column("description", sa.String(length=2000), nullable=False),
        sa.Column("subjects_json", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("motion_score", sa.Float(), nullable=False),
        sa.Column("speech_score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("scene_id"),
        sa.UniqueConstraint("analysis_id", "ordinal", name="uq_scene_analysis_ordinal"),
    )

    op.create_table(
        "silence_decisions",
        sa.Column("decision_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("padding_before_seconds", sa.Float(), nullable=False),
        sa.Column("padding_after_seconds", sa.Float(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("conflicts_with_speech", sa.Boolean(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
    )

    op.create_table(
        "highlights",
        sa.Column("highlight_id", sa.String(length=64), nullable=False),
        sa.Column("analysis_id", sa.String(length=64), nullable=False),
        sa.Column("scene_id", sa.String(length=64), nullable=True),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("highlight_score", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("recommended_start", sa.Float(), nullable=False),
        sa.Column("recommended_end", sa.Float(), nullable=False),
        sa.Column("recommended_platform", sa.String(length=40), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["auto_edit_analyses.analysis_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.scene_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("highlight_id"),
        sa.UniqueConstraint("analysis_id", "rank", name="uq_highlight_analysis_rank"),
    )


def downgrade() -> None:
    op.drop_table("highlights")
    op.drop_table("silence_decisions")
    op.drop_table("scenes")
    op.drop_table("transcript_words")
    op.drop_table("transcript_segments")
    op.drop_table("transcripts")
    op.drop_index("ix_auto_edit_project_created", table_name="auto_edit_analyses")
    op.drop_table("auto_edit_analyses")
    op.drop_index("ix_upload_sessions_project_created", table_name="upload_sessions")
    op.drop_table("upload_sessions")
