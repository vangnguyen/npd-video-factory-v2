"""Add immutable highlight drafts; no existing data/schema is removed."""
from alembic import op
import sqlalchemy as sa
revision='0017_ns_highlight_drafts'
down_revision='0016_mvp1_multi_input'
branch_labels=depends_on=None

def upgrade():
    op.create_table('auto_edit_highlight_drafts',
        sa.Column('draft_id',sa.String(64),primary_key=True),
        sa.Column('project_id',sa.String(64),sa.ForeignKey('video_projects.project_id',ondelete='CASCADE'),nullable=False),
        sa.Column('analysis_id',sa.String(64),sa.ForeignKey('auto_edit_analyses.analysis_id',ondelete='RESTRICT'),nullable=False),
        sa.Column('transcript_id',sa.String(64),sa.ForeignKey('transcripts.transcript_id',ondelete='RESTRICT'),nullable=True),
        sa.Column('fingerprint',sa.String(64),nullable=False),sa.Column('snapshot_json',sa.JSON(),nullable=False),
        sa.Column('evidence_json',sa.JSON(),nullable=False),sa.Column('actor_ref',sa.String(160),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('project_id','fingerprint',name='uq_highlight_draft_fingerprint'))

def downgrade():
    raise RuntimeError('Highlight drafts contain review evidence; export and obtain Owner approval before destructive downgrade')
