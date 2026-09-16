"""add an opt-in durable boundary for single-dispatch operations

Revision ID: 0015_v3_01_dispatch
Revises: 0014_v3_01_27
Create Date: 2026-09-16

Historical rows remain NULL and retain their existing controller semantics.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0015_v3_01_dispatch"
down_revision: Union[str, None] = "0014_v3_01_27"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("provider_safety_operations") as batch:
        batch.add_column(sa.Column("dispatch_protocol_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("dispatch_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("dispatch_request_sha256", sa.String(64), nullable=True))
        batch.add_column(sa.Column("dispatch_client_request_id", sa.String(200), nullable=True))
        batch.create_check_constraint(
            "ck_provider_safety_dispatch_protocol",
            "dispatch_protocol_version IS NULL OR dispatch_protocol_version = 1",
        )
        batch.create_check_constraint(
            "ck_provider_safety_dispatch_marker_complete",
            "(dispatch_started_at IS NULL AND dispatch_request_sha256 IS NULL "
            "AND dispatch_client_request_id IS NULL) OR "
            "(dispatch_protocol_version IS NOT NULL AND dispatch_protocol_version = 1 "
            "AND dispatch_started_at IS NOT NULL "
            "AND dispatch_request_sha256 IS NOT NULL "
            "AND dispatch_client_request_id IS NOT NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("provider_safety_operations") as batch:
        batch.drop_constraint("ck_provider_safety_dispatch_marker_complete", type_="check")
        batch.drop_constraint("ck_provider_safety_dispatch_protocol", type_="check")
        batch.drop_column("dispatch_client_request_id")
        batch.drop_column("dispatch_request_sha256")
        batch.drop_column("dispatch_started_at")
        batch.drop_column("dispatch_protocol_version")
