"""Owned additive rehearsal; no live migration or rewrite of prior evidence."""
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from app.main import app
from app.db import Base
from app.stock_wire_quota_db import StockWireControlORM, StockWireScopeORM, StockWireEventORM


def test_additive_stock_wire_migration_preserves_prior_rows_and_model_constraints(tmp_path):
    engine = sa.create_engine('sqlite:///' + (tmp_path / 'owned-stock-migration.db').as_posix())
    new_names = {'stock_wire_control', 'stock_wire_scopes', 'stock_wire_events'}
    old = [table for table in Base.metadata.sorted_tables if table.name not in new_names]
    Base.metadata.create_all(engine, tables=old)
    file = Path(__file__).parents[1] / 'migrations/versions/0028_north_star_stock_wire_quota.py'
    spec = importlib.util.spec_from_file_location('owned_stock_wire_0028', file)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.down_revision == '0027_ns_uploaded_audio'
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.execute(Base.metadata.tables['workspaces'].insert().values(
                workspace_id='wsp_stock_migration_fixture', slug='stock-migration',
                name='EXPLICIT OWNED MIGRATION FIXTURE', owner_ref='fixture'))
            rows = {table.name: connection.exec_driver_sql('SELECT * FROM "'+table.name+'"').fetchall() for table in old}
            schema = {table.name: connection.exec_driver_sql('PRAGMA table_info("'+table.name+'")').fetchall() for table in old}
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
            assert all(connection.exec_driver_sql('SELECT * FROM "'+name+'"').fetchall() == value for name, value in rows.items())
            assert all(connection.exec_driver_sql('PRAGMA table_info("'+name+'")').fetchall() == value for name, value in schema.items())
            inspector = sa.inspect(connection)
            for name in new_names:
                assert {column['name'] for column in inspector.get_columns(name)} == set(Base.metadata.tables[name].columns.keys())
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
            assert inspector.get_foreign_keys('stock_wire_events')[0]['options']['ondelete'] == 'RESTRICT'
            assert {constraint['name'] for constraint in inspector.get_check_constraints('stock_wire_scopes')} == {
                'ck_stock_wire_cooldown_nonnegative', 'ck_stock_wire_lease_pair'}
            with Operations.context(MigrationContext.configure(connection)):
                with pytest.raises(RuntimeError, match='explicit Owner approval'):
                    migration.downgrade()
    finally:
        engine.dispose()
