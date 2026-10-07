"""Owned additive private-session migration rehearsal; no deployed schema change."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select

from app.main import app
from app.db import Base, WorkspaceORM


def rehearse(path):
    engine = create_engine('sqlite:///' + str(path)); name = 'publication_private_sessions'
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            Base.metadata.create_all(connection, tables=[table for table in Base.metadata.sorted_tables if table.name != name])
            connection.execute(WorkspaceORM.__table__.insert().values(workspace_id='wsp_vault_migration_fixture',
                slug='vault-migration-fixture', name='Existing fixture workspace', owner_ref='fixture-only'))
            inspector = inspect(connection); old_names = set(inspector.get_table_names())
            schema = {old: connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (old,)).scalar_one() for old in old_names}
            rows = {old: connection.execute(select(Base.metadata.tables[old])).all() for old in old_names}
            file = Path(__file__).parents[1] / 'migrations/versions/0020_north_star_private_publish_session.py'
            spec = importlib.util.spec_from_file_location('owned_private_session_migration', file)
            migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
            assert migration.down_revision == '0019_ns_publish_dispatch'
            with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
            inspector = inspect(connection); assert set(inspector.get_table_names()) == old_names | {name}
            for old in old_names:
                assert connection.exec_driver_sql('SELECT sql FROM sqlite_master WHERE name=?', (old,)).scalar_one() == schema[old]
                assert connection.execute(select(Base.metadata.tables[old])).all() == rows[old]
            actual = {column['name']: column for column in inspector.get_columns(name)}; table = Base.metadata.tables[name]
            assert set(actual) == set(table.columns.keys())
            for column in table.columns:
                assert actual[column.name]['nullable'] == column.nullable and str(actual[column.name]['type']) == str(column.type)
            expected_fks = {(fk.parent.name, fk.column.table.name, fk.column.name, fk.ondelete) for fk in table.foreign_keys}
            actual_fks = {(fk['constrained_columns'][0], fk['referred_table'], fk['referred_columns'][0], fk['options'].get('ondelete')) for fk in inspector.get_foreign_keys(name)}
            assert expected_fks == actual_fks
            unique = {constraint['name']: constraint['column_names'] for constraint in inspector.get_unique_constraints(name)}
            assert unique == {'uq_publication_private_session': ['publication_id'], 'uq_private_session_key_nonce': ['key_id', 'nonce']}
            assert inspector.get_check_constraints(name)[0]['sqltext'] == 'total_bytes > 0'
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
            with pytest.raises(RuntimeError, match='explicit Owner approval'): migration.downgrade()
            return {'status': 'PASS', 'old_tables': len(old_names), 'added_tables': [name],
                'all_existing_rows_and_table_sql_unchanged': True, 'orm_columns_fk_unique_parity': True,
                'foreign_key_check': 'passed', 'destructive_downgrade_refused': True,
                'production_migration_executed': False, 'database_kind': 'owned SQLite fixture'}
    finally: engine.dispose()


def test_additive_private_session_migration_preserves_existing_schema_and_rows(tmp_path):
    assert rehearse(tmp_path / 'pre-vault.db')['status'] == 'PASS'
