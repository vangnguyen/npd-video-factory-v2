"""Add owned stock wire cooldown/lease evidence; never delete old histories."""
from alembic import op
import sqlalchemy as sa

revision = '0028_ns_stock_wire_quota'
down_revision = '0027_ns_uploaded_audio'
branch_labels = depends_on = None


def upgrade():
    op.create_table('stock_wire_control',
        sa.Column('control_key', sa.String(32), primary_key=True),
        sa.Column('revision', sa.Integer(), nullable=False))
    op.create_table('stock_wire_scopes',
        sa.Column('scope_sha256', sa.String(64), primary_key=True),
        sa.Column('scope_json', sa.JSON(), nullable=False),
        sa.Column('cooldown_until', sa.Float(), nullable=False),
        sa.Column('lease_id', sa.String(32), nullable=True),
        sa.Column('lease_until', sa.Float(), nullable=True),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('cooldown_until >= 0', name='ck_stock_wire_cooldown_nonnegative'),
        sa.CheckConstraint('(lease_id IS NULL AND lease_until IS NULL) OR '
            '(lease_id IS NOT NULL AND lease_until IS NOT NULL)', name='ck_stock_wire_lease_pair'))
    op.create_table('stock_wire_events',
        sa.Column('event_id', sa.String(40), primary_key=True),
        sa.Column('scope_sha256', sa.String(64), sa.ForeignKey('stock_wire_scopes.scope_sha256', ondelete='RESTRICT'), nullable=False),
        sa.Column('action', sa.String(40), nullable=False),
        sa.Column('evidence_json', sa.JSON(), nullable=False),
        sa.Column('evidence_sha256', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))


def downgrade():
    raise RuntimeError('Deleting quota and wire evidence requires export and explicit Owner approval')
