"""Additive migration rehearsal on a new owned database only."""
import importlib.util
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa

from app.main import app  # Register the existing complete metadata graph.
from app.db import Base


def test_additive_refresh_migration_keeps_old_schema_rows_and_foreign_keys(tmp_path):
    new_tables = {'analytics_refresh_plans', 'analytics_refresh_occurrences', 'analytics_refresh_events'}
    target = tmp_path / 'owned-additive-refresh.db'
    engine = sa.create_engine('sqlite:///' + target.as_posix())
    old_tables = [table for table in Base.metadata.sorted_tables if table.name not in new_tables]
    Base.metadata.create_all(engine, tables=old_tables)
    file = Path(__file__).parents[1] / 'migrations/versions/0023_north_star_analytics_refresh.py'
    spec = importlib.util.spec_from_file_location('owned_refresh_0023', file)
    migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.exec_driver_sql('PRAGMA foreign_keys=ON')
        connection.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_migration_fixture',
            slug='refresh-migration', name='EXPLICIT MIGRATION FIXTURE', owner_ref='usr:fixture'))
        before = {table.name: connection.exec_driver_sql('SELECT * FROM "' + table.name + '"').fetchall() for table in old_tables}
        context = MigrationContext.configure(connection)
        with Operations.context(context): migration.upgrade()
        for table in old_tables:
            assert connection.exec_driver_sql('SELECT * FROM "' + table.name + '"').fetchall() == before[table.name]
        assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        assert set(sa.inspect(connection).get_table_names()) == {table.name for table in old_tables} | new_tables
        for name in new_tables:
            assert {column['name'] for column in sa.inspect(connection).get_columns(name)} == set(Base.metadata.tables[name].columns.keys())
        with Operations.context(context):
            with pytest.raises(RuntimeError, match='explicit Owner approval'): migration.downgrade()
    engine.dispose()
