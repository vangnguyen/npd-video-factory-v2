"""MVP1 storyboard sources; historical video timelines keep analysis bindings."""
from alembic import op
import sqlalchemy as sa

revision = "0016_mvp1_multi_input"
down_revision = "0015_v3_01_dispatch"
branch_labels = depends_on = None

def upgrade():
    with op.batch_alter_table("timelines") as batch:
        batch.alter_column("source_analysis_id", existing_type=sa.String(64), nullable=True)
        batch.add_column(sa.Column("source_content_version_id", sa.String(64), nullable=True))
        batch.create_foreign_key("fk_timeline_content_version", "project_versions",
                                 ["source_content_version_id"], ["project_version_id"], ondelete="RESTRICT")
        batch.create_check_constraint("ck_timeline_source_identity",
            "(source_analysis_id IS NOT NULL AND source_content_version_id IS NULL) OR "
            "(source_analysis_id IS NULL AND source_content_version_id IS NOT NULL)")

def downgrade():
    # Fail closed when storyboard data exists: do not discard source identity.
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT COUNT(*) FROM timelines WHERE source_content_version_id IS NOT NULL")).scalar():
        raise RuntimeError("cannot downgrade while storyboard timelines exist")
    with op.batch_alter_table("timelines") as batch:
        batch.drop_constraint("ck_timeline_source_identity", type_="check")
        batch.drop_constraint("fk_timeline_content_version", type_="foreignkey")
        batch.drop_column("source_content_version_id")
        batch.alter_column("source_analysis_id", existing_type=sa.String(64), nullable=False)
