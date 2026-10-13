"""Add scoped immutable TTS-unit reuse; preserve all accepted render evidence."""
from alembic import op
import sqlalchemy as sa
revision = '0030_sql_tts_reuse'
down_revision = '0029_ns_stock_planner'
branch_labels = depends_on = None


def upgrade():
    op.create_table('sql_tts_artifact_reuse',
        sa.Column('reuse_id', sa.String(80), primary_key=True),
        sa.Column('workspace_id', sa.String(64), sa.ForeignKey('workspaces.workspace_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('project_id', sa.String(64), sa.ForeignKey('video_projects.project_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('content_version_id', sa.String(64), sa.ForeignKey('project_versions.project_version_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('binding_json', sa.JSON(), nullable=False),
        sa.Column('state', sa.String(16), nullable=False),
        sa.Column('claim_id', sa.String(32), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('source_render_id', sa.String(64), sa.ForeignKey('production_render_jobs.render_id', ondelete='RESTRICT'), nullable=False),
        sa.Column('result_json', sa.JSON(), nullable=True),
        sa.Column('result_sha256', sa.String(64), nullable=True),
        sa.Column('error_code', sa.String(80), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('workspace_id','project_id','content_version_id','fingerprint',name='uq_sql_tts_reuse_scope'),
        sa.CheckConstraint("state IN ('pending','ready','unknown')",name='ck_sql_tts_reuse_state'))


def downgrade():
    raise RuntimeError('Removing raw TTS custody requires export and explicit Owner approval')
