"""Add durable publication scheduling without rewriting existing rows."""
from alembic import op
import sqlalchemy as sa

revision = '0021_ns_publish_work'
down_revision = '0020_ns_private_publish_session'
branch_labels = depends_on = None


def upgrade():
    op.create_table('publication_work',
        sa.Column('work_id', sa.String(64), primary_key=True),
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publication_dispatches.publication_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('binding_sha256', sa.String(64), nullable=False), sa.Column('status', sa.String(32), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('failures', sa.Integer(), nullable=False),
        sa.Column('run_count', sa.Integer(), nullable=False), sa.Column('next_run_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('lease_owner', sa.String(32), nullable=True), sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('failure_code', sa.String(100), nullable=True), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('publication_id', name='uq_publication_work'),
        sa.CheckConstraint('version >= 1 AND failures >= 0 AND run_count >= 0', name='ck_publication_work_counts'))
    op.create_index('ix_publication_work_due', 'publication_work', ['workspace_id', 'status', 'next_run_at'])


def downgrade():
    raise RuntimeError('Publication work requires export and explicit Owner approval before destructive downgrade')
