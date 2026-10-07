"""Clone retained mock publication evidence, collect through official read contracts, export history."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
from types import SimpleNamespace

from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi import Depends, FastAPI
import httpx
from sqlalchemy import select

from app.main import app
from app.db import CostRecordORM, ProviderUsageORM, create_engine, create_session_factory, utc_now
from app.analytics_official import AnalyticsHTTPClient, AnalyticsOAuthCredential, YT_READ, YT_ANALYTICS
from app.analytics_providers import AnalyticsProviderRegistry
from app.analytics_repository import AnalyticsRepository
from app.analytics_runtime import OfficialAnalyticsRuntime
from app.analytics_service import AnalyticsService, AnalyticsSyncProcessor
from app.analytics_routes import router
from app.human_auth import authorize_human_request, HumanRateLimiter
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from app.publishing_repository import PublishingRepository
from app.publishing_models import PublicationRead
from app.publishing_profiles import PublishingProfileRegistry
from app.repositories import PlatformRepository
from app.production_repository import ProductionRepository
from app.timeline_repository import TimelineRepository
from app.trend_repository import TrendRepository
from app.db import ProviderRegistryORM
from auth_test_support import MemoryRateStore
from test_analytics_learning import analytics_settings, FakeQueue
from test_analytics_official import yt_table


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as handle: json.dump(value, handle, ensure_ascii=False, indent=2, default=str)


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False)
    source = Path(args.source_db).resolve(); before = sha(source); profiles_path = Path(args.profiles).resolve()
    database = root / 'analytics-owned-clone.db'
    original = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True); clone = sqlite3.connect(database)
    try:
        original.backup(clone)
        fk_before = clone.execute('PRAGMA foreign_key_check').fetchall()
        from sqlalchemy import create_engine as sync_engine
        engine = sync_engine('sqlite:///' + database.as_posix())
        with engine.begin() as connection:
            connection.exec_driver_sql('PRAGMA foreign_keys=OFF')
            for name in ('0022_north_star_analytics_reads.py', '0023_north_star_analytics_refresh.py'):
                file = Path(__file__).parents[1] / 'apps/api/migrations/versions' / name
                spec = importlib.util.spec_from_file_location('owned_analytics_migration_' + name[:4], file)
                migration = importlib.util.module_from_spec(spec); spec.loader.exec_module(migration)
                with Operations.context(MigrationContext.configure(connection)): migration.upgrade()
        engine.dispose()
        assert clone.execute('PRAGMA foreign_key_check').fetchall() == fk_before
        publications = clone.execute("SELECT receipt_json FROM publications WHERE status='published' AND mode='live' AND mock=1").fetchall()
        assert len(publications) == 1, 'One explicitly mock published receipt required'
    finally: clone.close(); original.close()
    engine = create_engine('sqlite+aiosqlite:///' + database.as_posix()); factory = create_session_factory(engine)
    publishing = PublishingRepository(factory); repository = AnalyticsRepository(factory); platform = PlatformRepository(factory)
    profiles = PublishingProfileRegistry.from_json(profiles_path.read_bytes())
    async with factory() as session:
        from app.publishing_db import PublicationORM
        row = await session.scalar(select(PublicationORM).where(PublicationORM.status == 'published', PublicationORM.mock.is_(True)))
        workspace, project, publication = row.workspace_id, row.project_id, row.publication_id
        parent = await publishing.get(project, publication)
        assert parent.receipt.mock and not parent.receipt.external_action
        session.add(ProviderRegistryORM(provider_id='pvd_explicit_analytics_read_contract', workspace_id=workspace,
            provider_key='youtube-analytics-api', display_name='EXPLICIT MOCK ANALYTICS CONTRACT', capability='analytics',
            adapter='explicit.fixture', routing_mode='disabled', status='fixture', enabled=False, supports_dry_run=True,
            config_ref=None, metadata_json={'fixture_only': True})); await session.commit()
    target = profiles.select(workspace, 'youtube').target; remote_id = parent.receipt.remote_post_id
    request_audit = []; table = [yt_table()]
    def receive(request):
        request_audit.append({'method': request.method, 'origin': request.url.host, 'path': request.url.path, 'mock': True, 'external_call': False})
        if request.url.path.endswith('/channels'): payload = {'items': [{'id': target.target_account_id}]}
        elif request.url.path.endswith('/videos'): payload = {'items': [{'id': remote_id, 'snippet': {'channelId': target.target_account_id}}]}
        else: payload = table[0]
        return httpx.Response(200, json=payload)
    settings = analytics_settings(analytics_external_execution_enabled=True, provider_external_execution_enabled=True)
    providers = AnalyticsProviderRegistry(settings); queue = FakeQueue()
    runtime = OfficialAnalyticsRuntime(repository=repository, publishing_repository=publishing, settings=settings,
        target_provider=lambda selected_workspace, selected_platform, profile_id: profiles.select(selected_workspace, selected_platform, profile_id).target,
        credential_resolver=lambda selected: AnalyticsOAuthCredential(selected, utc_now() + timedelta(hours=1),
            frozenset({YT_READ, YT_ANALYTICS}), 'EXPLICIT-MOCK-ANALYTICS-CONTRACT-TOKEN'),
        clients={'youtube': AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))})
    runtime.install(providers)
    service = AnalyticsService(repository=repository, publishing_repository=publishing, platform_repository=platform,
        providers=providers, queue=queue, settings=settings)
    processor = AnalyticsSyncProcessor(repository=repository, publishing_repository=publishing, platform_repository=platform,
        trend_repository=TrendRepository(factory), timeline_repository=TimelineRepository(factory),
        production_repository=ProductionRepository(factory), providers=providers, settings=settings)
    now = utc_now(); token = 'vf1.analytics-contract.' + 'x' * 48
    registry = HumanAuthRegistry.model_validate({'version': 1, 'tokens': {'analytics-contract': {
        'token_id': 'analytics-contract', 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'subject': 'usr:EXPLICIT_ANALYTICS_CONTRACT', 'display_name': 'EXPLICIT FIXTURE; NOT OWNER UAT',
        'platform_role': None, 'workspace_roles': {workspace: 'editor'}, 'issued_at': (now - timedelta(seconds=60)).isoformat(),
        'expires_at': (now + timedelta(hours=1)).isoformat(), 'enabled': True}}})
    application = FastAPI(); application.include_router(router, dependencies=[Depends(authorize_human_request)])
    application.state.analytics_service = service; application.state.platform_repository = platform
    application.state.human_api_enabled = True; application.state.human_write_enabled = True
    application.state.human_auth_verifier = HumanAuthVerifier(registry, max_token_ttl_seconds=86400)
    application.state.human_rate_limiter = HumanRateLimiter(MemoryRateStore(), requests_per_minute=1000)
    api = []; syncs = []; observation_views = {}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://fixture', headers={'Authorization': 'Bearer ' + token}) as client:
        for index in range(2):
            payload = {'publication_id': publication, 'provider_mode': 'official', 'trigger': 'initial' if index == 0 else 'manual_refresh',
                'query': {'start_date': '2026-10-01', 'end_date': '2026-10-06'}}
            response = await client.post(f'/api/v1/projects/{project}/analytics/syncs', json=payload,
                headers={'Idempotency-Key': 'explicit-analytics-read-contract-' + str(index)})
            assert response.status_code == 202; api.append({'method': 'POST', 'status': 202, 'no_store': response.headers.get('cache-control') == 'no-store'})
            result = await processor.process(response.json()['sync_id']); assert result.status == 'succeeded' and result.mock and not result.external_call
            syncs.append(result.model_dump(mode='json'))
            table[0] = yt_table([2000, 220, 6.6, 60, 3, 11, 8])
        for suffix in ('', '/snapshots', '/history'):
            response = await client.get(f'/api/v1/projects/{project}/analytics' + suffix)
            assert response.status_code == 200 and response.headers.get('cache-control') == 'no-store', (suffix, response.status_code, response.headers.get('cache-control'))
            api.append({'method': 'GET', 'status': 200, 'no_store': True})
        for mode in ('official', 'fixture'):
            for suffix in ('', '/snapshots'):
                response = await client.get(f'/api/v1/projects/{project}/publications/{publication}/analytics' + suffix,
                    params={'provider_mode': mode})
                assert response.status_code == 200 and response.headers.get('cache-control') == 'no-store'
                body = response.json()
                if suffix: assert len(body) == (2 if mode == 'official' else 0)
                else: assert body['publication_id'] == publication and body['history_count'] == (2 if mode == 'official' else 0)
                api.append({'method': 'GET', 'status': 200, 'no_store': True, 'publication_scoped': True, 'provider_mode': mode})
        base = f'/api/v1/projects/{project}/publications/{publication}/analytics/observations'
        first = await client.get(base, params={'provider_mode': 'official', 'limit': 1})
        assert first.status_code == 200 and first.json()['total_count'] == 2 and first.json()['next_cursor']
        second = await client.get(base, params={'provider_mode': 'official', 'limit': 1, 'cursor': first.json()['next_cursor']})
        assert second.status_code == 200 and second.json()['next_cursor'] is None
        assert first.json()['items'][0]['snapshot_id'] != second.json()['items'][0]['snapshot_id']
        empty = await client.get(base, params={'provider_mode': 'fixture', 'limit': 1})
        assert empty.status_code == 200 and empty.json()['items'] == [] and empty.json()['total_count'] == 0
        observation_views['history_pages'] = [first.json(), second.json(), empty.json()]
        for response in (first, second, empty):
            assert response.headers.get('cache-control') == 'no-store'
            api.append({'method': 'GET', 'status': 200, 'no_store': True, 'bounded_observations': True})
        for mode in ('official', 'fixture'):
            response = await client.get(f'/api/v1/workspaces/{workspace}/analytics/channels', params={'provider_mode': mode, 'limit': 50})
            assert response.status_code == 200 and response.headers.get('cache-control') == 'no-store'
            body = response.json(); assert body['account_totals'] is None
            if mode == 'official':
                videos = [video for channel in body['channels'] for video in channel['videos'] if video['publication_id'] == publication]
                assert len(videos) == 1 and videos[0]['binding_state'] == 'matched' and videos[0]['latest_snapshot']['mock'] is True
            observation_views['channels_' + mode] = body
            api.append({'method': 'GET', 'status': 200, 'no_store': True, 'workspace_channels': True, 'provider_mode': mode})
    snapshots = await repository.list_snapshots(project); assert len(snapshots) == 2 and snapshots[1].metrics.views == 1000
    report = await repository.report(project)
    async with factory() as session:
        usages = (await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.capability == 'analytics'))).all()
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provider_usage_id.in_([usage.usage_id for usage in usages])))).all()
    assert len(costs) == 6 and all(cost.actual_cost is None for cost in costs)
    await engine.dispose()
    restart_code = """import asyncio,json,sys
from app.main import app
from app.db import create_engine,create_session_factory
from app.analytics_repository import AnalyticsRepository
async def run():
 engine=create_engine(sys.argv[1]); repo=AnalyticsRepository(create_session_factory(engine))
 value=await repo.list_snapshots(sys.argv[2]); print(json.dumps([s.model_dump(mode='json') for s in value])); await engine.dispose()
asyncio.run(run())"""
    restarted = json.loads(subprocess.check_output([sys.executable, '-c', restart_code, 'sqlite+aiosqlite:///' + database.as_posix(), project], timeout=30))
    assert restarted == [snapshot.model_dump(mode='json') for snapshot in snapshots]
    assert sha(source) == before
    write(root, 'source.json', {'database': str(source), 'source_before_sha256': before, 'source_after_sha256': sha(source),
        'unchanged': True, 'profiles_sha256': sha(profiles_path), 'source_receipt': parent.receipt.model_dump(mode='json'),
        'foreign_key_baseline': fk_before, 'foreign_key_baseline_unchanged': True})
    write(root, 'syncs.json', syncs); write(root, 'snapshots.json', restarted)
    write(root, 'features-and-recommendations.json', report.model_dump(mode='json'))
    write(root, 'events.json', [event.model_dump(mode='json') for event in await repository.list_events(project)])
    write(root, 'cost.json', [{'cost_id': cost.cost_id, 'estimated_cost': cost.estimated_cost, 'actual_cost': cost.actual_cost,
        'provider_usage_id': cost.provider_usage_id, 'job_id': cost.job_id, 'provenance': cost.provenance} for cost in costs])
    write(root, 'requests.json', {'official_mock_requests': request_audit, 'authenticated_api_requests': api})
    write(root, 'observation-views.json', observation_views)
    write(root, 'contract.json', {'status': 'PASS', 'official_mock_requests': len(request_audit), 'authenticated_api_requests': len(api),
        'immutable_snapshots': 2, 'fresh_process_restore': True, 'external_provider_calls': 0, 'paid_calls': 0,
        'actual_cost': None, 'cost_records': 6, 'source_publication_mock': True, 'real_credentials_read': 0,
        'real_provider_tested': False, 'owner_uat_accepted': False, 'production_deployed': False, 'analytics_ready': False,
        'media_replaced': False, 'requested_dates_are_complete_coverage': False})
    await engine.dispose()
    print(json.dumps({'status': 'PASS', 'output': str(root), 'official_mock_requests': 6, 'authenticated_api_requests': len(api), 'exports': 9}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--source-db', required=True); parser.add_argument('--profiles', required=True)
    parser.add_argument('--output', required=True); asyncio.run(run(parser.parse_args()))
