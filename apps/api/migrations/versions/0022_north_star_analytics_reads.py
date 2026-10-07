"""Permit truthful analytics transport records and retain all historical metrics."""
from alembic import op
import sqlalchemy as sa

revision = '0022_ns_analytics_reads'
down_revision = '0021_ns_publish_work'
branch_labels = depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == 'sqlite' and bind.exec_driver_sql('PRAGMA foreign_keys').scalar():
        raise RuntimeError('SQLite analytics migration requires an offline backup/restore rehearsal and foreign_keys=OFF before the transaction')
    # PostgreSQL alters checks/nullable columns in place. SQLite rehearsals use
    # Alembic's row-preserving batch copy; no production migration is executed here.
    for table, prefix, column in (
        ('analytics_sync_jobs', 'sync', 'query_json'),
        ('analytics_metric_snapshots', 'snapshot', 'evidence_json')):
        with op.batch_alter_table(table) as batch:
            batch.drop_constraint(f'ck_analytics_{prefix}_no_external_call_v2_10', type_='check')
            batch.add_column(sa.Column(column, sa.JSON(), nullable=True))
            batch.create_check_constraint(f'ck_analytics_{prefix}_transport_truth', 'NOT (mock = true AND external_call = true)')


def downgrade():
    raise RuntimeError('Historical analytics and transport evidence require export and explicit Owner approval before destructive downgrade')
