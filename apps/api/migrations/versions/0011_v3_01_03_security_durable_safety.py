"""add media quarantine evidence and durable provider safety state

Revision ID: 0011_v3_01_03
Revises: 0010_v2_11
Create Date: 2026-08-27
"""

from datetime import datetime, timezone
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0011_v3_01_03"
down_revision: Union[str, None] = "0010_v2_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "upload_sessions",
        sa.Column(
            "quarantine_state",
            sa.String(length=32),
            nullable=False,
            server_default="not_scanned",
        ),
    )
    op.add_column("upload_sessions", sa.Column("scan_verdict", sa.String(length=20), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_provider", sa.String(length=80), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_signature_version", sa.String(length=120), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_result_code", sa.String(length=120), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_checksum_sha256", sa.String(length=64), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("upload_sessions", sa.Column("scan_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("upload_sessions", sa.Column("trusted_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "provider_safety_control",
        sa.Column("control_key", sa.String(length=32), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("control_key"),
    )
    op.bulk_insert(
        sa.table(
            "provider_safety_control",
            sa.column("control_key", sa.String()),
            sa.column("revision", sa.Integer()),
            sa.column("updated_at", sa.DateTime(timezone=True)),
        ),
        [{"control_key": "global", "revision": 0, "updated_at": datetime.now(timezone.utc)}],
    )
    op.create_table(
        "provider_safety_budget_days",
        sa.Column("budget_day", sa.Date(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("daily_limit_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("committed_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("reserved_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("currency = 'VND'", name="ck_provider_safety_budget_vnd_only"),
        sa.CheckConstraint("daily_limit_vnd >= 0", name="ck_provider_safety_daily_limit_nonnegative"),
        sa.CheckConstraint("committed_vnd >= 0", name="ck_provider_safety_committed_nonnegative"),
        sa.CheckConstraint("reserved_vnd >= 0", name="ck_provider_safety_reserved_nonnegative"),
        sa.PrimaryKeyConstraint("budget_day"),
    )
    op.create_table(
        "provider_safety_circuits",
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("half_open_operation_key", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('closed', 'open', 'half_open')",
            name="ck_provider_safety_circuit_state",
        ),
        sa.CheckConstraint(
            "consecutive_failures >= 0",
            name="ck_provider_safety_circuit_failures_nonnegative",
        ),
        sa.PrimaryKeyConstraint("provider_key", "capability"),
    )
    op.create_table(
        "provider_safety_operations",
        sa.Column("operation_key", sa.String(length=200), nullable=False),
        sa.Column("provider_key", sa.String(length=120), nullable=False),
        sa.Column("capability", sa.String(length=120), nullable=False),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("project_id", sa.String(length=64), nullable=True),
        sa.Column("job_id", sa.String(length=80), nullable=True),
        sa.Column("operation", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("external_call", sa.Boolean(), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("estimated_cost_vnd", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("reserved_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("charged_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("budget_day", sa.Date(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("failure_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retention_until", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('reserved', 'succeeded', 'failed', 'recovered')",
            name="ck_provider_safety_operation_status",
        ),
        sa.CheckConstraint("external_call = true", name="ck_provider_safety_operation_external"),
        sa.CheckConstraint("currency = 'VND'", name="ck_provider_safety_operation_vnd_only"),
        sa.CheckConstraint("reserved_vnd >= 0", name="ck_provider_safety_reserved_cost_nonnegative"),
        sa.CheckConstraint("charged_vnd >= 0", name="ck_provider_safety_charged_nonnegative"),
        sa.PrimaryKeyConstraint("operation_key"),
    )
    op.create_index(
        "ix_provider_safety_operation_status_updated",
        "provider_safety_operations",
        ["status", "updated_at"],
    )
    op.create_index(
        "ix_provider_safety_operation_provider_created",
        "provider_safety_operations",
        ["provider_key", "capability", "created_at"],
    )
    op.create_table(
        "provider_safety_attempts",
        sa.Column("usage_id", sa.String(length=64), nullable=False),
        sa.Column("operation_key", sa.String(length=200), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("estimated_cost_vnd", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("actual_cost_vnd", sa.Numeric(precision=20, scale=4), nullable=True),
        sa.Column("charged_cost_vnd", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("cost_status", sa.String(length=20), nullable=False),
        sa.Column("retryable", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('succeeded', 'failed', 'rate_limited', 'timed_out')",
            name="ck_provider_safety_attempt_status",
        ),
        sa.CheckConstraint("currency = 'VND'", name="ck_provider_safety_attempt_vnd_only"),
        sa.CheckConstraint("charged_cost_vnd >= 0", name="ck_provider_safety_attempt_charge_nonnegative"),
        sa.ForeignKeyConstraint(
            ["operation_key"],
            ["provider_safety_operations.operation_key"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("usage_id"),
        sa.UniqueConstraint("operation_key", "attempt", name="uq_provider_safety_operation_attempt"),
    )
    op.create_index(
        "ix_provider_safety_attempt_operation_created",
        "provider_safety_attempts",
        ["operation_key", "created_at"],
    )
    op.create_table(
        "provider_safety_budget_alerts",
        sa.Column("budget_day", sa.Date(), nullable=False),
        sa.Column("threshold_percent", sa.Integer(), nullable=False),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "threshold_percent IN (50, 80, 100)",
            name="ck_provider_safety_alert_threshold",
        ),
        sa.PrimaryKeyConstraint("budget_day", "threshold_percent"),
    )


def downgrade() -> None:
    op.drop_table("provider_safety_budget_alerts")
    op.drop_index(
        "ix_provider_safety_attempt_operation_created",
        table_name="provider_safety_attempts",
    )
    op.drop_table("provider_safety_attempts")
    op.drop_index(
        "ix_provider_safety_operation_provider_created",
        table_name="provider_safety_operations",
    )
    op.drop_index(
        "ix_provider_safety_operation_status_updated",
        table_name="provider_safety_operations",
    )
    op.drop_table("provider_safety_operations")
    op.drop_table("provider_safety_circuits")
    op.drop_table("provider_safety_budget_days")
    op.drop_table("provider_safety_control")

    op.drop_column("upload_sessions", "trusted_at")
    op.drop_column("upload_sessions", "scan_completed_at")
    op.drop_column("upload_sessions", "scan_started_at")
    op.drop_column("upload_sessions", "scan_checksum_sha256")
    op.drop_column("upload_sessions", "scan_result_code")
    op.drop_column("upload_sessions", "scan_signature_version")
    op.drop_column("upload_sessions", "scan_provider")
    op.drop_column("upload_sessions", "scan_verdict")
    op.drop_column("upload_sessions", "quarantine_state")
