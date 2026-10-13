"""Add atomic canonical service outcome events; retain prior receipts/data."""
from alembic import op
import sqlalchemy as sa
revision='0026_ns_service_outcomes'
down_revision='0025_ns_service_api'
branch_labels=depends_on=None
def upgrade():
    op.create_table('service_outcome_events',
        sa.Column('sequence',sa.Integer(),primary_key=True,autoincrement=True),
        sa.Column('event_id',sa.String(64),unique=True,nullable=False),
        sa.Column('operation_id',sa.String(64),sa.ForeignKey('service_api_operations.operation_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('workspace_id',sa.String(64),sa.ForeignKey('workspaces.workspace_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('service_id',sa.String(160),nullable=False),sa.Column('envelope_json',sa.JSON(),nullable=False),
        sa.Column('envelope_sha256',sa.String(64),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('operation_id',name='uq_service_outcome_operation'))
def downgrade():
    raise RuntimeError('Outcome event deletion requires export and explicit Owner approval')
