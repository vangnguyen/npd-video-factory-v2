"""add Agent Hub bridge requests events and webhook deliveries

Revision ID: 0010_v2_11
Revises: 0009_v2_10
Create Date: 2026-08-27
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0010_v2_11"
down_revision: Union[str, None] = "0009_v2_10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_hub_bridge_requests",
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("service_id", sa.String(length=160), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("project_version_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key_hash", sa.String(length=64), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("request_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("execution_started", sa.Boolean(), nullable=False),
        sa.Column("external_action", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("execution_started = false", name="ck_bridge_request_no_execution"),
        sa.CheckConstraint("external_action = false", name="ck_bridge_request_no_external_action"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_version_id"], ["project_versions.project_version_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.workspace_id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("request_id"),
        sa.UniqueConstraint("service_id", "idempotency_key_hash", name="uq_bridge_request_service_idempotency"),
    )
    op.create_index(
        "ix_bridge_request_project_created",
        "agent_hub_bridge_requests",
        ["project_id", "created_at"],
    )
    op.create_table(
        "agent_hub_bridge_events",
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("contract_version", sa.String(length=80), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("contains_secret", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("contains_secret = false", name="ck_bridge_event_secret_free"),
        sa.ForeignKeyConstraint(["project_id"], ["video_projects.project_id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["request_id"], ["agent_hub_bridge_requests.request_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "ix_bridge_event_project_created",
        "agent_hub_bridge_events",
        ["project_id", "created_at"],
    )
    op.create_table(
        "agent_hub_webhook_deliveries",
        sa.Column("delivery_id", sa.String(length=64), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("destination_ref", sa.String(length=240), nullable=False),
        sa.Column("provider_mode", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("key_id", sa.String(length=80), nullable=True),
        sa.Column("signed_at_unix", sa.Integer(), nullable=True),
        sa.Column("body_sha256", sa.String(length=64), nullable=True),
        sa.Column("signature", sa.String(length=64), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("receipt_json", sa.JSON(), nullable=True),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_call", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["agent_hub_bridge_events.event_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("delivery_id"),
        sa.UniqueConstraint("event_id", "destination_ref", name="uq_bridge_delivery_event_destination"),
    )
    op.create_index(
        "ix_bridge_delivery_status_schedule",
        "agent_hub_webhook_deliveries",
        ["status", "next_retry_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_bridge_delivery_status_schedule", table_name="agent_hub_webhook_deliveries")
    op.drop_table("agent_hub_webhook_deliveries")
    op.drop_index("ix_bridge_event_project_created", table_name="agent_hub_bridge_events")
    op.drop_table("agent_hub_bridge_events")
    op.drop_index("ix_bridge_request_project_created", table_name="agent_hub_bridge_requests")
    op.drop_table("agent_hub_bridge_requests")
