"""Offline owned database rehearsal; retained rows and FK edges must survive."""
import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import CheckConstraint, MetaData, create_engine, inspect, select

from app.main import app
from app.db import Base
from app.auto_edit_db import AutoEditAnalysisORM
from test_analytics_learning import analytics_stack, request


@pytest.mark.asyncio
async def test_offline_analytics_migration_preserves_all_old_rows_and_rejects_unsafe_online_sqlite(tmp_path):
    stack = await analytics_stack(tmp_path / 'source')
    engine = create_engine('sqlite:///' + str(tmp_path / 'offline-restored.db'))
    try:
        sync, _ = await stack.service.create_sync(project_id=stack.production.project.project_id,
            payload=request(stack.publication.publication_id), idempotency_key='analytics-migration-historical-fixture')
        await stack.processor.process(sync.sync_id)
        # The legacy production test fixture references a synthetic analysis ID
        # without seeding it. Register that explicit fixture before FK rehearsal.
        async with stack.production.repository.session_factory() as session:
            session.add(AutoEditAnalysisORM(analysis_id='ana_v208_fixture', workspace_id=stack.production.project.workspace_id,
                project_id=stack.production.project.project_id, project_version_id=None, asset_id=stack.production.asset.asset_id,
                status='fixture', fingerprint='a' * 64, configuration_json={'fixture_only': True}, source_media_json={'fixture_only': True}))
            await session.commit()
        async with stack.production.engine.connect() as connection:
            data = await connection.run_sync(lambda conn: {table.name: [dict(row._mapping) for row in conn.execute(select(table))]
                for table in Base.metadata.sorted_tables})
        old = MetaData()
        for table in Base.metadata.sorted_tables: table.to_metadata(old)
        for name, prefix, column in [('analytics_sync_jobs', 'sync', 'query_json'), ('analytics_metric_snapshots', 'snapshot', 'evidence_json')]:
            table = old.tables[name]; table._columns.remove(table.c[column])
            constraint = next(item for item in table.constraints if isinstance(item, CheckConstraint) and item.name == f'ck_analytics_{prefix}_transport_truth')
            table.constraints.remove(constraint)
            table.append_constraint(CheckConstraint('external_call = false', name=f'ck_analytics_{prefix}_no_external_call_v2_10'))
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON'); old.create_all(connection)
            for table in old.sorted_tables:
                rows = [{key: value for key, value in row.items() if key in table.c} for row in data[table.name]]
                if rows: connection.execute(table.insert(), rows)
        file = Path(__file__).parents[1] / 'migrations/versions/0022_north_star_analytics_reads.py'
        spec = importlib.util.spec_from_file_location('offline_analytics_migration', file)
        migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
        assert migration.down_revision == '0021_ns_publish_work'
        with engine.connect() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            before = {table.name: connection.execute(select(table)).all() for table in old.sorted_tables}
            with Operations.context(MigrationContext.configure(connection)):
                with pytest.raises(RuntimeError, match='offline backup'): migration.upgrade()
            assert {table.name: connection.execute(select(table)).all() for table in old.sorted_tables} == before
            connection.commit()
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF'); connection.commit()
            with connection.begin():
                with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
                for table in old.sorted_tables:
                    assert connection.execute(select(table)).all() == before[table.name]
                assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
                for name in ('analytics_sync_jobs', 'analytics_metric_snapshots'):
                    assert {column['name'] for column in inspect(connection).get_columns(name)} == set(Base.metadata.tables[name].columns.keys())
                with pytest.raises(RuntimeError, match='explicit Owner approval'): migration.downgrade()
            connection.exec_driver_sql('PRAGMA foreign_keys=ON')
            assert connection.exec_driver_sql('PRAGMA foreign_key_check').all() == []
    finally:
        engine.dispose()
        await stack.production.engine.dispose()
