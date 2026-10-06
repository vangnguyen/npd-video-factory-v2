"""Add immutable combined-scene evidence without modifying source analyses."""
from alembic import op
import sqlalchemy as sa
revision='0018_ns_scene_intelligence'
down_revision='0017_ns_highlight_drafts'
branch_labels=depends_on=None


def upgrade():
    op.create_table('auto_edit_scene_intelligence',
        sa.Column('assessment_id',sa.String(64),primary_key=True),
        sa.Column('project_id',sa.String(64),sa.ForeignKey('video_projects.project_id',ondelete='CASCADE'),nullable=False),
        sa.Column('analysis_id',sa.String(64),sa.ForeignKey('auto_edit_analyses.analysis_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('transcript_id',sa.String(64),sa.ForeignKey('transcripts.transcript_id',ondelete='RESTRICT'),nullable=True),
        sa.Column('vision_analysis_id',sa.String(64),sa.ForeignKey('vision_analyses.vision_analysis_id',ondelete='RESTRICT'),nullable=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('snapshot_json',sa.JSON(),nullable=False),
        sa.Column('actor_ref',sa.String(160),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('project_id','fingerprint',name='uq_scene_intelligence_fingerprint'))


def downgrade():
    raise RuntimeError('Scene assessments contain review evidence; export and obtain Owner approval before destructive downgrade')
