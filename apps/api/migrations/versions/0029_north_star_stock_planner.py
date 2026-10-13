"""Append-only planner scheduling evidence; preserve all existing plan versions."""
from alembic import op
import sqlalchemy as sa
revision = '0029_ns_stock_planner'
down_revision = '0028_ns_stock_wire_quota'
branch_labels = depends_on = None


def upgrade():
    op.create_table('media_plan_stock_events',
        sa.Column('event_id', sa.String(40), primary_key=True),
        sa.Column('media_plan_id', sa.String(64), sa.ForeignKey('media_plans.media_plan_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('action', sa.String(80), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('media_plan_id', 'version', name='uq_media_plan_stock_event_version'))


def downgrade():
    raise RuntimeError('Removing planner history requires export and explicit Owner approval')
