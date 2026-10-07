"""Add publish-only consent and durable dispatch without rewriting publications."""
from alembic import op
import sqlalchemy as sa

revision = '0019_ns_publish_dispatch'
down_revision = '0018_ns_scene_intelligence'
branch_labels = depends_on = None


def upgrade():
    op.create_table('publication_publish_approvals',
        sa.Column('publish_approval_id', sa.String(64), primary_key=True),
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publications.publication_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('idempotency_key_hash', sa.String(64), nullable=False), sa.Column('binding_json', sa.JSON(), nullable=False),
        sa.Column('binding_sha256', sa.String(64), nullable=False), sa.Column('owner_token_id', sa.String(80), nullable=False),
        sa.Column('owner_subject', sa.String(160), nullable=False), sa.Column('owner_identity_revision', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False), sa.Column('revoked_at', sa.DateTime(timezone=True)),
        sa.UniqueConstraint('publication_id', 'idempotency_key_hash', name='uq_publish_approval_request'))
    op.create_table('publication_dispatches',
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publications.publication_id', ondelete='RESTRICT'), primary_key=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('publish_approval_id', sa.String(64), sa.ForeignKey('publication_publish_approvals.publish_approval_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('binding_sha256', sa.String(64), nullable=False), sa.Column('phase', sa.String(40), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('total_bytes', sa.Integer(), nullable=False),
        sa.Column('acknowledged_bytes', sa.Integer(), nullable=False), sa.Column('private_session_ref', sa.String(64)),
        sa.Column('intent_id', sa.String(32)), sa.Column('intent_offset', sa.Integer()), sa.Column('intent_end', sa.Integer()),
        sa.Column('lease_until', sa.DateTime(timezone=True)), sa.Column('remote_post_id', sa.String(128)),
        sa.Column('failure_code', sa.String(100)), sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('version >= 1 AND acknowledged_bytes >= 0', name='ck_publication_dispatch_progress'))
    op.create_index('ix_publication_dispatch_workspace_phase', 'publication_dispatches', ['workspace_id', 'phase'])


def downgrade():
    raise RuntimeError('Publish consent and dispatch evidence require export and explicit Owner approval before destructive downgrade')
