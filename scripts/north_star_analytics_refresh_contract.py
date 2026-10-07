"""Fresh-process recurring read contract on a copy of explicit mock evidence.

Never changes the retained source DB or contacts an external provider. The
earlier scheduler instant is an explicit clock fixture, not provider coverage.
"""
import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from north_star_analytics_read_contract import (
    AnalyticsHTTPClient, AnalyticsOAuthCredential, AnalyticsProviderRegistry, AnalyticsRepository,
    AnalyticsService, AnalyticsSyncProcessor, CostRecordORM, Depends, FastAPI, FakeQueue,
    OfficialAnalyticsRuntime, PlatformRepository, ProductionRepository, PublishingProfileRegistry,
    PublishingRepository, TimelineRepository, TrendRepository, YT_READ, YT_ANALYTICS,
    analytics_settings, authorize_human_request, httpx, select, sha, utc_now, write, yt_table,
    create_engine, create_session_factory,
)
from app.analytics_refresh_repository import AnalyticsRefreshRepository
from app.analytics_refresh_db import AnalyticsRefreshOccurrenceORM
from app.analytics_db import AnalyticsMetricSnapshotORM
from app.analytics_refresh_routes import router
from app.publishing_db import PublicationORM
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth


async def persisted(database, project, plan_id):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix())
    factory = create_session_factory(engine)
    repository = AnalyticsRepository(factory); refresh = AnalyticsRefreshRepository(factory)
    async with factory() as session:
        occurrences = (await session.scalars(select(AnalyticsRefreshOccurrenceORM)
            .where(AnalyticsRefreshOccurrenceORM.plan_id == plan_id)
            .order_by(AnalyticsRefreshOccurrenceORM.ordinal))).all()
        costs = (await session.scalars(select(CostRecordORM)
            .where(CostRecordORM.project_id == project).order_by(CostRecordORM.cost_id))).all()
    result = {
        'plan': (await refresh.get(project, plan_id)).model_dump(mode='json'),
        'occurrences': [{'sync_id': row.sync_id, 'ordinal': row.ordinal, 'revision': row.plan_revision,
            'skipped_slots': row.skipped_slots} for row in occurrences],
        'plan_audit': json.loads(json.dumps(await refresh.history(project, plan_id), default=str)),
        'snapshots': [row.model_dump(mode='json') for row in await repository.list_snapshots(project)],
        'syncs': [row.model_dump(mode='json') for row in await repository.list_syncs(project)],
        'costs': [{'cost_id': row.cost_id, 'actual_cost': str(row.actual_cost) if row.actual_cost is not None else None,
            'estimated_cost': str(row.estimated_cost) if row.estimated_cost is not None else None,
            'provenance': row.provenance} for row in costs],
    }
    await engine.dispose()
    return result


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False)
    source = Path(args.source_db).resolve(); before = sha(source)
    profiles_file = Path(args.profiles).resolve()
    database = root / 'refresh-owned-clone.db'
    original = sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)
    clone = sqlite3.connect(database)
    try:
        original.backup(clone)
        fk_before = clone.execute('PRAGMA foreign_key_check').fetchall()
        assert clone.execute('SELECT COUNT(*) FROM analytics_refresh_plans').fetchone()[0] == 0
        assert clone.execute('SELECT COUNT(*) FROM ' + AnalyticsMetricSnapshotORM.__tablename__).fetchone()[0] == 2
    finally:
        clone.close(); original.close()
    engine = create_engine('sqlite+aiosqlite:///' + database.as_posix()); factory = create_session_factory(engine)
    repository = AnalyticsRepository(factory); publishing = PublishingRepository(factory)
    refresh = AnalyticsRefreshRepository(factory); platform = PlatformRepository(factory)
    profiles = PublishingProfileRegistry.from_json(profiles_file.read_bytes())
    async with factory() as session:
        row = await session.scalar(select(PublicationORM).where(PublicationORM.status == 'published', PublicationORM.mock.is_(True)))
        workspace, project, publication = row.workspace_id, row.project_id, row.publication_id
    parent = await publishing.get(project, publication)
    assert parent.mode == 'live' and parent.receipt.mock and not parent.receipt.external_action
    old = [row.model_dump(mode='json') for row in await repository.list_snapshots(project)]
    assert len(old) == 2
    target = profiles.select(workspace, 'youtube').target
    requests = []
    def receive(request):
        requests.append({'method': request.method, 'host': request.url.host, 'path': request.url.path,
            'mock': True, 'external_call': False})
        if request.url.path.endswith('/channels'): value = {'items': [{'id': target.target_account_id}]}
        elif request.url.path.endswith('/videos'):
            value = {'items': [{'id': parent.receipt.remote_post_id, 'snippet': {'channelId': target.target_account_id}}]}
        else: value = yt_table([3000, 330, 6.6, 90, 5, 16, 12])
        return httpx.Response(200, json=value)
    settings = analytics_settings(analytics_external_execution_enabled=True, provider_external_execution_enabled=True)
    providers = AnalyticsProviderRegistry(settings)
    runtime = OfficialAnalyticsRuntime(repository=repository, publishing_repository=publishing, settings=settings,
        target_provider=lambda w, p, profile_id: profiles.select(w, p, profile_id).target,
        credential_resolver=lambda selected: AnalyticsOAuthCredential(selected, utc_now() + timedelta(hours=1),
            frozenset({YT_READ, YT_ANALYTICS}), 'EXPLICIT-REFRESH-MOCK-CONTRACT-TOKEN'),
        clients={'youtube': AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))})
    runtime.install(providers)
    service = AnalyticsService(repository=repository, publishing_repository=publishing, platform_repository=platform,
        providers=providers, queue=FakeQueue(), settings=settings)
    processor = AnalyticsSyncProcessor(repository=repository, publishing_repository=publishing, platform_repository=platform,
        trend_repository=TrendRepository(factory), timeline_repository=TimelineRepository(factory),
        production_repository=ProductionRepository(factory), providers=providers, settings=settings)
    application = FastAPI(); application.include_router(router, dependencies=[Depends(authorize_human_request)])
    application.state.analytics_service = service
    install_test_human_auth(application, platform_repository=platform, platform_role=None, workspace_roles={workspace: 'owner'})
    first_clock = utc_now() - timedelta(hours=2)
    body = {'publication_id': publication, 'provider_mode': 'official', 'first_run_at': first_clock.isoformat(),
        'interval_hours': 1, 'max_runs': 2, 'query_policy': 'rolling_complete_days', 'lookback_days': 7}
    api = []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        base = f'/api/v1/projects/{project}/analytics/refresh-plans'
        async def check(method, path, status, **kwargs):
            response = await client.request(method, path, **kwargs)
            assert response.status_code == status, (path, response.status_code, response.text)
            assert response.headers.get('cache-control') == 'no-store'
            api.append({'method': method, 'status': status, 'no_store': True})
            return response
        headers = {'Idempotency-Key': 'explicit-refresh-plan-fresh-process-contract'}
        created = await check('POST', base, 201, json=body, headers=headers)
        plan = created.json(); assert not plan['enabled'] and plan['created_by'] == 'usr:test-owner'
        replay = await check('POST', base, 201, json=body, headers=headers)
        assert replay.headers['x-idempotent-replay'] == 'true' and replay.json()['plan_id'] == plan['plan_id']
        endpoint = base + '/' + plan['plan_id']
        enable = {'expected_revision': 1, 'enabled': True, 'acknowledged_read_only': True}
        await check('POST', endpoint + '/state', 409, json=enable)
        ready = lambda p, mode, w, key: providers.get(platform=p, mode=mode, workspace=w).provider_key == key
        assert await refresh.create_due(settings=settings, provider_ready=ready, at=first_clock) == []
        settings.analytics_scheduled_refresh_enabled = True
        enabled = await check('POST', endpoint + '/state', 200, json=enable)
        assert enabled.json()['revision'] == 2
        ids = await refresh.create_due(settings=settings, provider_ready=ready, at=first_clock)
        assert len(ids) == 1
        assert await refresh.create_due(settings=settings, provider_ready=ready, at=first_clock) == []
        result = await processor.process(ids[0]); assert result.status == 'succeeded' and result.mock and not result.external_call
        assert len(requests) == 3
        second_clock = utc_now()
        second = await refresh.create_due(settings=settings, provider_ready=ready, at=second_clock)
        assert len(second) == 1
        await check('POST', endpoint + '/state', 200, json={'expected_revision': 2, 'enabled': False})
        denied = await processor.process(second[0])
        assert denied.status == 'not_configured' and denied.failure_code == 'ANALYTICS_REFRESH_PLAN_DISABLED'
        assert len(requests) == 3
        assert await refresh.create_due(settings=settings, provider_ready=ready, at=second_clock + timedelta(hours=3)) == []
        await check('POST', endpoint + '/state', 409, json=enable)
        for path in (base, endpoint, endpoint + '/history'): await check('GET', path, 200)
    await engine.dispose()
    expected = await persisted(database, project, plan['plan_id'])
    restarted = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()),
        '--read-db', str(database), '--project', project, '--plan', plan['plan_id']], timeout=45))
    assert restarted == expected and restarted['plan']['run_count'] == 2 and restarted['plan']['revision'] == 3
    by_id = {row['snapshot_id']: row for row in restarted['snapshots']}
    assert len(by_id) == 3 and all(by_id[row['snapshot_id']] == row for row in old)
    assert len(restarted['occurrences']) == 2 and len(restarted['plan_audit']) == 5
    analytics_costs = [row for row in restarted['costs'] if row['provenance'].get('analytics_sync_id')]
    assert len(analytics_costs) == 9 and all(row['actual_cost'] is None for row in analytics_costs)
    with sqlite3.connect(database) as connection: assert connection.execute('PRAGMA foreign_key_check').fetchall() == fk_before
    assert sha(source) == before
    write(root, 'source.json', {'source_database': str(source), 'source_before_sha256': before, 'source_after_sha256': sha(source),
        'unchanged': True, 'profile_sha256': sha(profiles_file), 'foreign_key_baseline_unchanged': True})
    write(root, 'restored-state.json', restarted)
    write(root, 'requests.json', {'official_mock_requests': requests, 'authenticated_api_requests': api})
    write(root, 'clock-fixture.json', {'first_scheduler_instant': first_clock, 'second_scheduler_instant': second_clock,
        'earlier_instant_is_test_fixture': True, 'requested_dates_certify_complete_coverage': False})
    write(root, 'contract.json', {'status': 'PASS', 'official_mock_requests': 3, 'authenticated_api_requests': len(api),
        'fresh_process_restore': True, 'old_snapshots_unchanged': 2, 'new_snapshots': 1, 'durable_occurrences': 2,
        'revoked_occurrences_not_collected': 1, 'analytics_cost_records': 9, 'actual_cost': None, 'external_provider_calls': 0,
        'real_credentials_read': 0, 'paid_calls': 0, 'real_provider_tested': False, 'owner_uat_accepted': False,
        'production_deployed': False, 'media_replaced': False, 'analytics_ready': False})
    print(json.dumps({'status': 'PASS', 'output': str(root), 'mock_reads': len(requests), 'api_requests': len(api)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source-db'); parser.add_argument('--profiles'); parser.add_argument('--output')
    parser.add_argument('--read-db'); parser.add_argument('--project'); parser.add_argument('--plan')
    args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(persisted(args.read_db, args.project, args.plan))))
    else:
        assert args.source_db and args.profiles and args.output
        asyncio.run(run(args))
