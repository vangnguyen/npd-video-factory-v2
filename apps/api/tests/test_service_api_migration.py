"""Additive service receipts in a new owned SQLite DB; production untouched."""
import importlib.util
from pathlib import Path
import pytest,sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.main import app
from app.db import Base

def test_receipt_migration_preserves_existing_rows_and_blocks_destructive_downgrade(tmp_path):
    engine=sa.create_engine('sqlite:///'+(tmp_path/'owned-service-migration.db').as_posix())
    old=[t for t in Base.metadata.sorted_tables if t.name!='service_api_operations'];Base.metadata.create_all(engine,tables=old)
    spec=importlib.util.spec_from_file_location('owned_service_0025',Path(__file__).parents[1]/'migrations/versions/0025_north_star_service_api.py')
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as con:
        con.exec_driver_sql('PRAGMA foreign_keys=ON')
        con.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_service_migration_fixture',slug='service-migration',
            name='EXPLICIT OWNED FIXTURE',owner_ref='fixture'))
        rows={t.name:con.exec_driver_sql('SELECT * FROM "'+t.name+'"').fetchall() for t in old}
        schema={t.name:con.exec_driver_sql('PRAGMA table_info("'+t.name+'")').fetchall() for t in old}
        with Operations.context(MigrationContext.configure(con)):migration.upgrade()
        assert all(con.exec_driver_sql('SELECT * FROM "'+n+'"').fetchall()==v for n,v in rows.items())
        assert all(con.exec_driver_sql('PRAGMA table_info("'+n+'")').fetchall()==v for n,v in schema.items())
        assert not con.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        assert {c['name'] for c in sa.inspect(con).get_columns('service_api_operations')}==set(Base.metadata.tables['service_api_operations'].columns.keys())
        with Operations.context(MigrationContext.configure(con)):
            with pytest.raises(RuntimeError,match='explicit Owner approval'):migration.downgrade()
    engine.dispose()
