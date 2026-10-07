"""Add read-only refresh plans, occurrences and audit; retain existing tables."""
from alembic import op
import sqlalchemy as sa

revision = '0023_ns_analytics_refresh'
down_revision = '0022_ns_analytics_reads'
branch_labels = depends_on = None


def upgrade():
    op.create_table('analytics_refresh_plans',
        sa.Column('plan_id', sa.String(64), primary_key=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('publication_id', sa.String(64), sa.ForeignKey('publications.publication_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('platform', sa.String(40), nullable=False),
        sa.Column('provider_mode', sa.String(20), nullable=False),
        sa.Column('provider_key', sa.String(120), nullable=False),
        sa.Column('target_binding_sha256', sa.String(64), nullable=True),
        sa.Column('publication_fingerprint', sa.String(64), nullable=False),
        sa.Column('config_json', sa.JSON(), nullable=False),
        sa.Column('request_fingerprint', sa.String(64), nullable=False),
        sa.Column('idempotency_key_hash', sa.String(64), nullable=False),
        sa.Column('interval_hours', sa.Integer(), nullable=False),
        sa.Column('max_runs', sa.Integer(), nullable=False),
        sa.Column('run_count', sa.Integer(), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False),
        sa.Column('next_due_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_by', sa.String(160), nullable=False),
        sa.Column('updated_by', sa.String(160), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'idempotency_key_hash', name='uq_analytics_refresh_project_key'),
        sa.CheckConstraint('interval_hours >= 1 AND interval_hours <= 168', name='ck_analytics_refresh_interval'),
        sa.CheckConstraint('max_runs >= 1 AND max_runs <= 365', name='ck_analytics_refresh_runs'),
        sa.CheckConstraint('run_count >= 0 AND run_count <= max_runs', name='ck_analytics_refresh_run_count'),
        sa.CheckConstraint('revision >= 1', name='ck_analytics_refresh_revision'))
    op.create_index('ix_analytics_refresh_due', 'analytics_refresh_plans', ['enabled', 'next_due_at'])
    op.create_table('analytics_refresh_occurrences',
        sa.Column('occurrence_id', sa.String(64), primary_key=True),
        sa.Column('plan_id', sa.String(64), sa.ForeignKey('analytics_refresh_plans.plan_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('sync_id', sa.String(64), sa.ForeignKey('analytics_sync_jobs.sync_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('plan_revision', sa.Integer(), nullable=False),
        sa.Column('ordinal', sa.Integer(), nullable=False),
        sa.Column('planned_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('scheduled_for', sa.DateTime(timezone=True), nullable=False),
        sa.Column('skipped_slots', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('plan_id', 'ordinal', name='uq_analytics_refresh_occurrence'),
        sa.UniqueConstraint('sync_id', name='uq_analytics_refresh_occurrence_sync'),
        sa.CheckConstraint('ordinal >= 1', name='ck_analytics_refresh_ordinal'),
        sa.CheckConstraint('skipped_slots >= 0', name='ck_analytics_refresh_skipped_slots'))
    op.create_table('analytics_refresh_events',
        sa.Column('event_id', sa.String(64), primary_key=True),
        sa.Column('plan_id', sa.String(64), sa.ForeignKey('analytics_refresh_plans.plan_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('revision', sa.Integer(), nullable=False),
        sa.Column('actor_ref', sa.String(160), nullable=False),
        sa.Column('event_type', sa.String(80), nullable=False),
        sa.Column('payload_json', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_analytics_refresh_events_plan_id', 'analytics_refresh_events', ['plan_id'])


def downgrade():
    raise RuntimeError('Refresh plans and occurrence/audit history require export and explicit Owner approval before destructive downgrade')
