"""Owned SQLite additive history migration; no production migration."""
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations
import pytest
import sqlalchemy as sa
from app.main import app
from app.db import Base


def test_planner_history_migration_preserves_existing_schema_rows_and_restricts_deletion(tmp_path):
    engine=sa.create_engine('sqlite:///'+(tmp_path/'owned-planner-migration.db').as_posix())
    old=[table for table in Base.metadata.sorted_tables if table.name!='media_plan_stock_events']
    Base.metadata.create_all(engine,tables=old)
    file=Path(__file__).parents[1]/'migrations/versions/0029_north_star_stock_planner.py'
    spec=importlib.util.spec_from_file_location('owned_stock_planner_0029',file)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    assert migration.down_revision=='0028_ns_stock_wire_quota'
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            connection.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_planner_migration_fixture',
                slug='planner-migration',name='EXPLICIT OWNED MIGRATION FIXTURE',owner_ref='fixture'))
            before_rows={table.name:connection.exec_driver_sql('SELECT * FROM "'+table.name+'"').fetchall() for table in old}
            before_schema={table.name:connection.exec_driver_sql('PRAGMA table_info("'+table.name+'")').fetchall() for table in old}
            with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
            assert all(connection.exec_driver_sql('SELECT * FROM "'+name+'"').fetchall()==rows for name,rows in before_rows.items())
            assert all(connection.exec_driver_sql('PRAGMA table_info("'+name+'")').fetchall()==rows for name,rows in before_schema.items())
            assert not connection.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
            inspector=sa.inspect(connection)
            assert {column['name'] for column in inspector.get_columns('media_plan_stock_events')}==set(Base.metadata.tables['media_plan_stock_events'].columns.keys())
            assert all(foreign['options']['ondelete']=='RESTRICT' for foreign in inspector.get_foreign_keys('media_plan_stock_events'))
            with Operations.context(MigrationContext.configure(connection)):
                with pytest.raises(RuntimeError,match='explicit Owner approval'):migration.downgrade()
    finally:engine.dispose()
