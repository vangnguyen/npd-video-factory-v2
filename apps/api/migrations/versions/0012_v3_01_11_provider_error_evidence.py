"""add secret-free provider error evidence to durable attempts

Revision ID: 0012_v3_01_11
Revises: 0011_v3_01_03
Create Date: 2026-08-28
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0012_v3_01_11"
down_revision: Union[str, None] = "0011_v3_01_03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "provider_safety_attempts",
        sa.Column("error_evidence", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("provider_safety_attempts", "error_evidence")
