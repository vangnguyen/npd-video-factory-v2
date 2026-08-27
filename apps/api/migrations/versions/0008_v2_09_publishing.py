"""add fail-closed idempotent publishing dry-run records

Revision ID: 0008_v2_09
Revises: 0007_v2_08
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0008_v2_09"
down_revision: Union[str, None] = "0007_v2_08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "publications",
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("approval_id", sa.String(length=64), nullable=False),
        sa.Column("final_render_id", sa.String(length=64), nullable=False),
        sa.Column("output_asset_id", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=40), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("capability_version", sa.String(length=80), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("rights_validation_json", sa.JSON(), nullable=True),
        sa.Column("platform_validation_json", sa.JSON(), nullable=True),
        sa.Column("provider_validation_json", sa.JSON(), nullable=True),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("mock", sa.Boolean(), nullable=False),
        sa.Column("external_action", sa.Boolean(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["approval_id"], ["production_approvals.approval_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["final_render_id"], ["production_render_jobs.render_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["output_asset_id"], ["assets.asset_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["package_id"], ["production_packages.package_id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("publication_id"),
        sa.UniqueConstraint("project_id", "idempotency_key_hash", name="uq_publication_project_idempotency"),
    )
    op.create_index("ix_publication_project_created", "publications", ["project_id", "created_at"])
    op.create_index("ix_publication_status_updated", "publications", ["status", "updated_at"])
    op.create_table(
        "publication_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("publication_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("actor_ref", sa.String(length=160), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["publication_id"], ["publications.publication_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_publication_event_project_created",
        "publication_events",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_publication_event_project_created", table_name="publication_events")
    op.drop_table("publication_events")
    op.drop_index("ix_publication_status_updated", table_name="publications")
    op.drop_index("ix_publication_project_created", table_name="publications")
    op.drop_table("publications")
