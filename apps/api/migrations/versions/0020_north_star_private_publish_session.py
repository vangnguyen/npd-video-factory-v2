"""Add immutable encrypted session receipts without changing existing rows."""
from alembic import op
import sqlalchemy as sa

revision = '0020_ns_private_publish_session'
down_revision = '0019_ns_publish_dispatch'
branch_labels = depends_on = None


def upgrade():
    op.create_table('publication_private_sessions',
        sa.Column('session_ref', sa.String(64), primary_key=True),
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publication_dispatches.publication_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('binding_sha256', sa.String(64), nullable=False), sa.Column('platform', sa.String(40), nullable=False),
        sa.Column('total_bytes', sa.Integer(), nullable=False), sa.Column('key_id', sa.String(64), nullable=False),
        sa.Column('nonce', sa.LargeBinary(12), nullable=False), sa.Column('ciphertext', sa.LargeBinary(8192), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False), sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('publication_id', name='uq_publication_private_session'),
        sa.UniqueConstraint('key_id', 'nonce', name='uq_private_session_key_nonce'),
        sa.CheckConstraint('total_bytes > 0', name='ck_private_session_size'))


def downgrade():
    raise RuntimeError('Private publish receipts require export and explicit Owner approval before destructive downgrade')
