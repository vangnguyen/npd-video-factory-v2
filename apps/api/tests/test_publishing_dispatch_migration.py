"""Additive migration rehearsal against an owned pre-dispatch SQLite schema."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select

from app.main import app  # registers the existing persistence models
from app.db import Base, WorkspaceORM


NEW_TABLES = {'publication_publish_approvals', 'publication_dispatches'}


def rehearse(path):
    engine = create_engine('sqlite:///' + str(path))
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            Base.metadata.create_all(connection, tables=[table for table in Base.metadata.sorted_tables if table.name not in NEW_TABLES])
            connection.execute(WorkspaceORM.__table__.insert().values(workspace_id='wsp_migration_fixture',
                slug='migration-fixture', name='Existing fixture workspace', owner_ref='fixture-only'))
            inspector = inspect(connection); old_names = set(inspector.get_table_names())
            old_schema = {name: connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (name,)).scalar_one() for name in old_names}
            before_rows = {name: connection.execute(select(Base.metadata.tables[name])).all() for name in old_names}
            file = Path(__file__).parents[1] / 'migrations/versions/0019_north_star_publish_dispatch.py'
            spec = importlib.util.spec_from_file_location('owned_publish_dispatch_migration', file)
            migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
            assert migration.down_revision == '0018_ns_scene_intelligence'
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            inspector = inspect(connection)
            assert set(inspector.get_table_names()) == old_names | NEW_TABLES
            for name in old_names:
                assert connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (name,)).scalar_one() == old_schema[name]
                assert connection.execute(select(Base.metadata.tables[name])).all() == before_rows[name]
            for name in NEW_TABLES:
                actual = {column['name']: column for column in inspector.get_columns(name)}
                table = Base.metadata.tables[name]
                assert set(actual) == set(table.columns.keys())
                for column in table.columns:
                    assert actual[column.name]['nullable'] == column.nullable
                    assert str(actual[column.name]['type']) == str(column.type)
                expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete) for fk in table.foreign_keys}
                actual_fks = {(fk['constrained_columns'][0], fk['referred_table'], fk['referred_columns'][0], fk['options'].get('ondelete')) for fk in inspector.get_foreign_keys(name)}
                assert actual_fks == expected_fks
            assert inspector.get_unique_constraints('publication_publish_approvals')[0]['column_names'] == ['publication_id', 'idempotency_key_hash']
            assert inspector.get_check_constraints('publication_dispatches')[0]['sqltext'] == 'version >= 1 AND acknowledged_bytes >= 0'
            assert inspector.get_indexes('publication_dispatches')[0]['column_names'] == ['workspace_id', 'phase']
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            with pytest.raises(RuntimeError, match='explicit Owner approval'):
                migration.downgrade()
            return {'status': 'PASS', 'old_tables': len(old_names), 'added_tables': sorted(NEW_TABLES),
                'all_existing_rows_and_table_sql_unchanged': True, 'orm_column_and_fk_parity': True,
                'foreign_key_check': 'passed', 'destructive_downgrade_refused': True,
                'production_migration_executed': False, 'database_kind': 'owned SQLite fixture'}
    finally:
        engine.dispose()


def test_additive_dispatch_migration_preserves_existing_schema_and_rows(tmp_path):
    assert rehearse(tmp_path / 'pre-dispatch.db')['status'] == 'PASS'
