"""Add immutable channel recommendation snapshots; retain analytics history."""
from alembic import op
import sqlalchemy as sa

revision = '0024_ns_channel_learning'
down_revision = '0023_ns_analytics_refresh'
branch_labels = depends_on = None


def upgrade():
    op.create_table('channel_learning_snapshots',
        sa.Column('learning_snapshot_id', sa.String(64), primary_key=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publications.publication_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('anchor_snapshot_id', sa.String(64), sa.ForeignKey('analytics_metric_snapshots.snapshot_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('idempotency_key_hash', sa.String(64), nullable=False),
        sa.Column('request_fingerprint', sa.String(64), nullable=False),
        sa.Column('content_sha256', sa.String(64), nullable=False),
        sa.Column('snapshot_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(160), nullable=False),
        sa.UniqueConstraint('project_id', 'idempotency_key_hash', name='uq_learning_project_key'))
    op.create_index('ix_learning_workspace_created', 'channel_learning_snapshots', ['workspace_id', 'created_at'])


def downgrade():
    raise RuntimeError('Learning snapshots require export and explicit Owner approval before destructive downgrade')
