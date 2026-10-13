"""Add master variant reservations. No existing timeline/package/cache rewrite."""
from alembic import op
import sqlalchemy as sa

revision = '0032_ns_sql_variants'
down_revision = '0031_ns_video_jobs'
branch_labels = depends_on = None


def fk(name, target, nullable=False):
    return sa.Column(name, sa.String(64), sa.ForeignKey(target, ondelete='RESTRICT'), nullable=nullable)


def string(name, length=64, nullable=False):
    return sa.Column(name, sa.String(length), nullable=nullable)


def dates():
    return [sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
            sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False)]


def upgrade():
    op.create_table('sql_variant_families',
        sa.Column('family_id', sa.String(64), primary_key=True),
        fk('workspace_id', 'workspaces.workspace_id'), fk('master_project_id', 'video_projects.project_id'),
        fk('master_timeline_version_id', 'timeline_versions.timeline_version_id'),
        sa.Column('version', sa.Integer(), nullable=False), string('state', 32),
        string('request_key_sha256'), string('request_sha256'),
        sa.Column('snapshot_json', sa.JSON(), nullable=False), string('snapshot_sha256'),
        sa.Column('result_json', sa.JSON(), nullable=False), string('result_sha256'), string('actor_ref', 160),
        *dates(),
        sa.UniqueConstraint('workspace_id', 'master_project_id', 'request_key_sha256', name='uq_sql_variant_family_request'),
        sa.CheckConstraint('version >= 1', name='ck_sql_variant_family_version'),
        sa.CheckConstraint("state IN ('reserved','deriving','review_required','needs_attention','recovery_required','cancelled','failed')", name='ck_sql_variant_family_state'))
    op.create_index('ix_sql_variant_family_history', 'sql_variant_families',
        ['workspace_id', 'master_project_id', 'created_at', 'family_id'])
    op.create_table('sql_variant_members',
        sa.Column('member_id', sa.String(64), primary_key=True),
        fk('family_id', 'sql_variant_families.family_id'), fk('workspace_id', 'workspaces.workspace_id'),
        string('profile_ref', 80), sa.Column('profile_json', sa.JSON(), nullable=False), string('profile_sha256'),
        string('planned_project_id'), fk('child_project_id', 'video_projects.project_id', True),
        fk('initial_timeline_version_id', 'timeline_versions.timeline_version_id', True), string('state', 32), *dates(),
        sa.UniqueConstraint('family_id', 'profile_ref', name='uq_sql_variant_member_profile'),
        sa.UniqueConstraint('planned_project_id', name='uq_sql_variant_planned_project'),
        sa.UniqueConstraint('child_project_id', name='uq_sql_variant_child_project'),
        sa.CheckConstraint("state IN ('reserved','deriving','review_required','needs_attention','cancelled','failed')", name='ck_sql_variant_member_state'))
    op.create_table('sql_variant_artifact_receipts',
        sa.Column('receipt_id', sa.String(64), primary_key=True),
        fk('family_id', 'sql_variant_families.family_id'), fk('member_id', 'sql_variant_members.member_id'),
        fk('workspace_id', 'workspaces.workspace_id'), string('kind'), string('state', 16),
        string('request_key_sha256'), string('request_sha256'),
        sa.Column('input_json', sa.JSON(), nullable=False), string('input_sha256'),
        sa.Column('result_json', sa.JSON(), nullable=True), string('result_sha256', nullable=True),
        string('claim_id', nullable=True), sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        fk('target_asset_id', 'assets.asset_id', True), string('error_code', 80, True), string('actor_ref', 160), *dates(),
        sa.UniqueConstraint('family_id', 'request_key_sha256', name='uq_sql_variant_receipt_request'),
        sa.UniqueConstraint('member_id', 'kind', 'input_sha256', name='uq_sql_variant_receipt_input'),
        sa.CheckConstraint("state IN ('reserved','pending','ready','unknown','cancelled')", name='ck_sql_variant_receipt_state'))
    op.create_index('ix_sql_variant_receipt_member', 'sql_variant_artifact_receipts', ['family_id','member_id','receipt_id'])
    op.create_table('sql_variant_events',
        sa.Column('event_id', sa.String(64), primary_key=True),
        fk('family_id', 'sql_variant_families.family_id'), fk('workspace_id', 'workspaces.workspace_id'),
        sa.Column('version', sa.Integer(), nullable=False), string('event_type', 80),
        string('request_key_sha256'), string('request_sha256'), string('actor_ref', 160),
        sa.Column('payload_json', sa.JSON(), nullable=False), string('payload_sha256'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('family_id', 'request_key_sha256', name='uq_sql_variant_event_request'),
        sa.UniqueConstraint('family_id', 'version', name='uq_sql_variant_event_version'))


def downgrade():
    raise RuntimeError('Removing variant family source/receipt history requires export and explicit Owner approval')
