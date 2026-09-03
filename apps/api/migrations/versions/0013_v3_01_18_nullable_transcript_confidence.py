"""allow provider-native null transcript confidence

Revision ID: 0013_v3_01_18
Revises: 0012_v3_01_11
Create Date: 2026-09-03
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0013_v3_01_18"
down_revision: Union[str, None] = "0012_v3_01_11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transcripts") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=True)
    with op.batch_alter_table("transcript_segments") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=True)
    with op.batch_alter_table("transcript_words") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=True)


def downgrade() -> None:
    # The legacy schema cannot represent provider-native unknown confidence.
    # A downgrade explicitly marks those legacy-only rows with 0.0 rather than
    # pretending this is real provider evidence; V3 provenance remains intact.
    op.execute(sa.text("UPDATE transcripts SET confidence = 0.0 WHERE confidence IS NULL"))
    op.execute(
        sa.text(
            "UPDATE transcript_segments SET confidence = 0.0 WHERE confidence IS NULL"
        )
    )
    op.execute(
        sa.text("UPDATE transcript_words SET confidence = 0.0 WHERE confidence IS NULL")
    )
    with op.batch_alter_table("transcript_words") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=False)
    with op.batch_alter_table("transcript_segments") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=False)
    with op.batch_alter_table("transcripts") as batch:
        batch.alter_column("confidence", existing_type=sa.Float(), nullable=False)
