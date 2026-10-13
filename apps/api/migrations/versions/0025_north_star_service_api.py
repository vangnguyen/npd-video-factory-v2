"""Add scoped service API operation receipts; no existing state is rewritten."""
from alembic import op
import sqlalchemy as sa
revision='0025_ns_service_api'
down_revision='0024_ns_channel_learning'
branch_labels=depends_on=None
def upgrade():
    op.create_table('service_api_operations',
        sa.Column('operation_id',sa.String(64),primary_key=True),
        sa.Column('workspace_id',sa.String(64),sa.ForeignKey('workspaces.workspace_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('service_id',sa.String(160),nullable=False),sa.Column('action',sa.String(64),nullable=False),
        sa.Column('project_id',sa.String(64),nullable=True),sa.Column('actor_ref',sa.String(160),nullable=False),
        sa.Column('key_sha256',sa.String(64),nullable=False),sa.Column('request_sha256',sa.String(64),nullable=False),
        sa.Column('status',sa.String(32),nullable=False),sa.Column('response_status',sa.Integer(),nullable=True),
        sa.Column('response_json',sa.JSON(),nullable=True),sa.Column('response_sha256',sa.String(64),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('workspace_id','service_id','key_sha256',name='uq_service_api_workspace_key'))
def downgrade():
    raise RuntimeError('Service receipts require export and explicit Owner approval before destructive downgrade')
