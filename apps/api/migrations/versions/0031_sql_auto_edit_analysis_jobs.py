"""Add durable video-analysis job custody; existing transcript FKs are unchanged."""
from alembic import op
import sqlalchemy as sa
revision = '0031_ns_video_jobs'
down_revision = '0030_sql_tts_reuse'
branch_labels = depends_on = None


def upgrade():
    op.create_table('auto_edit_analysis_jobs',
        sa.Column('relation_id', sa.String(64), primary_key=True),
        sa.Column('analysis_id', sa.String(64), sa.ForeignKey('auto_edit_analyses.analysis_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('job_id', sa.String(80), sa.ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('source_json', sa.JSON(), nullable=False),
        sa.Column('configuration_json', sa.JSON(), nullable=False),
        sa.Column('provider_json', sa.JSON(), nullable=False),
        sa.Column('actor_ref', sa.String(160), nullable=False),
        sa.Column('request_json', sa.JSON(), nullable=False),
        sa.Column('custody_sha256', sa.String(64), nullable=False),
        sa.Column('claim_id', sa.String(64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False))
    op.create_table('auto_edit_analysis_job_requests',
        sa.Column('receipt_id', sa.String(64), primary_key=True),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('job_id', sa.String(80), sa.ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('request_key_sha256', sa.String(64), nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('actor_ref', sa.String(160), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id','request_key_sha256',name='uq_auto_edit_job_request'))


def downgrade():
    raise RuntimeError('Video job evidence deletion requires export and explicit Owner approval')
