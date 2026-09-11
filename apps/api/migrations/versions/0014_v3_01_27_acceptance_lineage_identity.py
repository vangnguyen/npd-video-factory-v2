"""bind provider safety ledger rows to an acceptance lineage

Revision ID: 0014_v3_01_27
Revises: 0013_v3_01_18
Create Date: 2026-09-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0014_v3_01_27"
down_revision: Union[str, None] = "0013_v3_01_18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("provider_safety_operations") as batch:
        batch.add_column(sa.Column("acceptance_lineage_id", sa.String(80), nullable=True))
        batch.create_index(
            "ix_provider_safety_operation_lineage",
            ["acceptance_lineage_id"],
            unique=False,
        )
    with op.batch_alter_table("provider_safety_attempts") as batch:
        batch.add_column(sa.Column("acceptance_lineage_id", sa.String(80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("provider_safety_attempts") as batch:
        batch.drop_column("acceptance_lineage_id")
    with op.batch_alter_table("provider_safety_operations") as batch:
        batch.drop_index("ix_provider_safety_operation_lineage")
        batch.drop_column("acceptance_lineage_id")
