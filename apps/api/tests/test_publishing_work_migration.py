"""Additive owned SQLite rehearsal; no production database migration."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select

from app.main import app
from app.db import Base, WorkspaceORM


def test_additive_work_migration_preserves_old_rows_sql_and_matches_model(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'before-work.db')); name = 'publication_work'
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            Base.metadata.create_all(connection, tables=[table for table in Base.metadata.sorted_tables if table.name != name])
            connection.execute(WorkspaceORM.__table__.insert().values(workspace_id='wsp_work_migration_fixture',
                slug='work-migration-fixture', name='Preserved existing fixture', owner_ref='fixture-only'))
            names = set(inspect(connection).get_table_names())
            sql = {old: connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (old,)).scalar_one() for old in names}
            rows = {old: connection.execute(select(Base.metadata.tables[old])).all() for old in names}
            file = Path(__file__).parents[1] / 'migrations/versions/0021_north_star_publish_work.py'
            spec = importlib.util.spec_from_file_location('owned_work_migration', file)
            migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
            assert migration.down_revision == '0020_ns_private_publish_session'
            with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
            inspector = inspect(connection); assert set(inspector.get_table_names()) == names | {name}
            for old in names:
                assert connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (old,)).scalar_one() == sql[old]
                assert connection.execute(select(Base.metadata.tables[old])).all() == rows[old]
            actual = {column['name']: column for column in inspector.get_columns(name)}; table = Base.metadata.tables[name]
            assert set(actual) == set(table.columns.keys())
            for column in table.columns:
                assert actual[column.name]['nullable'] == column.nullable and str(actual[column.name]['type']) == str(column.type)
            expected = {(fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete) for fk in table.foreign_keys}
            assert expected == {(fk['constrained_columns'][0], fk['referred_table'], fk['referred_columns'][0], fk['options']['ondelete']) for fk in inspector.get_foreign_keys(name)}
            assert inspector.get_unique_constraints(name)[0]['column_names'] == ['publication_id']
            assert inspector.get_check_constraints(name)[0]['sqltext'] == 'version >= 1 AND failures >= 0 AND run_count >= 0'
            assert inspector.get_indexes(name)[0]['column_names'] == ['workspace_id', 'status', 'next_run_at']
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            with pytest.raises(RuntimeError, match='explicit Owner approval'): migration.downgrade()
    finally: engine.dispose()
