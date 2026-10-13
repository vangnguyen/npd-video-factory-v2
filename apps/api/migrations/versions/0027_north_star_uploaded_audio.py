"""Independent uploaded audio evidence; no changes to existing video records."""
from alembic import op
import sqlalchemy as sa
revision = '0027_ns_uploaded_audio'
down_revision = '0026_ns_service_outcomes'
branch_labels = depends_on = None


def upgrade():
    op.create_table('uploaded_audio_transcriptions',
        sa.Column('audio_id', sa.String(64), primary_key=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='CASCADE'), nullable=False),
        sa.Column('asset_id', sa.String(64), sa.ForeignKey('assets.asset_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('job_id', sa.String(80), sa.ForeignKey('jobs.job_id', ondelete='RESTRICT'), nullable=False, unique=True),
        sa.Column('source_sha256', sa.String(64), nullable=False),
        sa.Column('source_size_bytes', sa.Integer(), nullable=False),
        sa.Column('request_key_sha256', sa.String(64), nullable=False),
        sa.Column('request_sha256', sa.String(64), nullable=False),
        sa.Column('configuration_json', sa.JSON(), nullable=False),
        sa.Column('media_metadata_json', sa.JSON(), nullable=False),
        sa.Column('original_evidence_json', sa.JSON(), nullable=True),
        sa.Column('original_evidence_sha256', sa.String(64), nullable=True),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('claim_id', sa.String(64), nullable=True),
        sa.Column('lease_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('project_id', 'request_key_sha256', name='uq_uploaded_audio_request'))
    op.create_table('uploaded_audio_transcript_versions',
        sa.Column('transcript_id', sa.String(64), primary_key=True),
        sa.Column('audio_id', sa.String(64), sa.ForeignKey('uploaded_audio_transcriptions.audio_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('transcript_json', sa.JSON(), nullable=False),
        sa.Column('transcript_sha256', sa.String(64), nullable=False),
        sa.Column('actor_ref', sa.String(160), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('audio_id', 'version', name='uq_uploaded_audio_version'))


def downgrade():
    raise RuntimeError('Audio evidence deletion requires export and explicit Owner approval')
