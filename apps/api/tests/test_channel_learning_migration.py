"""New owned SQLite only; no live migration or schema rewrite."""
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from app.main import app
from app.db import Base


def test_additive_snapshot_migration_preserves_old_rows_schema_and_restricts_deletion(tmp_path):
    engine = sa.create_engine('sqlite:///' + (tmp_path / 'owned-learning-migration.db').as_posix())
    old = [table for table in Base.metadata.sorted_tables if table.name != 'channel_learning_snapshots']
    Base.metadata.create_all(engine, tables=old)
    spec = importlib.util.spec_from_file_location('owned_learning_0024', Path(__file__).parents[1] / 'migrations/versions/0024_north_star_channel_learning.py')
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_learning_migration_fixture', slug='learning-migration', name='EXPLICIT OWNED FIXTURE', owner_ref='fixture'))
        rows = {table.name: connection.exec_driver_sql('SELECT * FROM "' + table.name + '"').fetchall() for table in old}
        schema = {table.name: connection.exec_driver_sql('PRAGMA table_info("' + table.name + '")').fetchall() for table in old}
        with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
        assert all(connection.exec_driver_sql('SELECT * FROM "' + name + '"').fetchall() == values for name, values in rows.items())
        assert all(connection.exec_driver_sql('PRAGMA table_info("' + name + '")').fetchall() == values for name, values in schema.items())
        assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        assert {column['name'] for column in sa.inspect(connection).get_columns('channel_learning_snapshots')} == set(Base.metadata.tables['channel_learning_snapshots'].columns.keys())
        assert all(fk['options']['ondelete'] == 'RESTRICT' for fk in sa.inspect(connection).get_foreign_keys('channel_learning_snapshots'))
        with Operations.context(MigrationContext.configure(connection)):
            with pytest.raises(RuntimeError, match='explicit Owner approval'): migration.downgrade()
    engine.dispose()
