"""Owner carry-forward provenance; no historical provider rows are reconstructed."""
from alembic import op
import sqlalchemy as sa

revision = "0017_content_budget_epoch"
down_revision = "0016_mvp1_multi_input"
branch_labels = depends_on = None


def upgrade():
    op.create_table(
        "provider_safety_accounting_epochs",
        sa.Column("epoch_id", sa.String(120), primary_key=True),
        sa.Column("budget_day", sa.Date(), nullable=False, unique=True),
        sa.Column("classification", sa.String(80), nullable=False),
        sa.Column("owner_decision_id", sa.String(120), nullable=False),
        sa.Column("opening_committed_vnd", sa.Numeric(20, 4), nullable=False),
        sa.Column("opening_reserved_vnd", sa.Numeric(20, 4), nullable=False),
        sa.Column("artifact_sha256", sa.String(64), nullable=False),
        sa.Column("artifact_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["budget_day"], ["provider_safety_budget_days.budget_day"], ondelete="RESTRICT"),
        sa.CheckConstraint("classification = 'OWNER_CARRY_FORWARD_CONSERVATIVE_CHARGE'",
                           name="ck_provider_safety_epoch_classification"),
        sa.CheckConstraint("opening_committed_vnd >= 0 AND opening_reserved_vnd = 0",
                           name="ck_provider_safety_epoch_opening"),
    )


def downgrade():
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM provider_safety_accounting_epochs")).scalar():
        raise RuntimeError("cannot downgrade while Owner accounting epoch provenance exists")
    op.drop_table("provider_safety_accounting_epochs")
