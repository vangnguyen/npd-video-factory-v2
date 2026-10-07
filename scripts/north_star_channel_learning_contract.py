"""Owned synthetic channel history, authenticated feedback and exact process restart."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import httpx
from sqlalchemy import select
from app.main import app
from app.db import create_engine, create_session_factory, CostRecordORM
from app.learning_service import ChannelLearningService
from app.analytics_repository import AnalyticsRepository
from app.trend_repository import TrendRepository
from app.trend_service import TrendIntelligenceService
from app.trend_providers import create_trend_provider_registry
from app.trend_models import TrendCollectionRequest, TrendClusterRefreshRequest, IdeaGenerateRequest
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_runtime import runtime_stack
from test_channel_learning import learning_app, seed_learning_history
from test_trend_intelligence import FIXTURE_PATH, FIXTURE_AS_OF


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as file: json.dump(value, file, ensure_ascii=False, indent=2, default=str)


async def read(database, project):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix()); factory = create_session_factory(engine)
    learning = ChannelLearningService(factory); analytics = AnalyticsRepository(factory)
    value = {'learning': [item.model_dump(mode='json') for item in await learning.list(project)],
        'analytics': [item.model_dump(mode='json') for item in await analytics.list_snapshots(project)],
        'assessments': [item.model_dump(mode='json') for item in await analytics.list_assessments(project)]}
    async with factory() as session:
        rows = (await session.scalars(select(CostRecordORM).where(CostRecordORM.project_id == project).order_by(CostRecordORM.cost_id))).all()
        value['costs'] = [{'cost_id': item.cost_id, 'actual_cost': str(item.actual_cost) if item.actual_cost is not None else None,
            'estimated_cost': str(item.estimated_cost) if item.estimated_cost is not None else None, 'provenance': item.provenance} for item in rows]
    await engine.dispose(); return value


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False); owned = root / 'owned-fixture'; owned.mkdir()
    generator = runtime_stack.__wrapped__(owned); stack, _, current, calls, _, _ = await anext(generator)
    try:
        await seed_learning_history(stack, current[0]); assert len(calls) == 3
        project = stack.publication.project_id; before = [item.model_dump(mode='json') for item in await stack.repository.list_snapshots(project)]
        application = learning_app(stack); learning = application.state.channel_learning_service
        path = f'/api/v1/projects/{project}/analytics/learning-snapshots'; request_count = 0
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
            body = {'publication_id': stack.publication.publication_id}; headers = {'Idempotency-Key': 'channel-learning-contract-fixture-key'}
            reply = await client.post(path, json=body, headers=headers); request_count += 1
            assert reply.status_code == 201 and reply.headers['Cache-Control'] == 'no-store'; saved = reply.json()
            replay = await client.post(path, json=body, headers=headers); request_count += 1
            assert replay.status_code == 201 and replay.headers['X-Idempotent-Replay'] == 'true' and replay.json() == saved
            feedback = await client.get(f'/api/v1/workspaces/{saved["workspace_id"]}/learning-snapshots/{saved["learning_snapshot_id"]}/recommendations'); request_count += 1
            assert feedback.status_code == 200 and feedback.json()['content_sha256'] == saved['content_sha256']
        assert len(saved['observations']) == 7 and saved['scope']['mock'] and not saved['scope']['external_call']
        hook = next(item for item in saved['dimensions'] if item['dimension'] == 'hook')
        assert hook['state'] == 'recommendations_available' and hook['groups'][0]['sample_count'] == 3
        assert next(item for item in saved['dimensions'] if item['dimension'] == 'publishing_window')['state'] == 'insufficient_data'
        providers = create_trend_provider_registry(FIXTURE_PATH); repository = TrendRepository(stack.repository.session_factory)
        await repository.seed_sources(providers.definitions())
        service = TrendIntelligenceService(repository, providers, stack.production.platform, learning=learning)
        collection = await service.collect(saved['workspace_id'], TrendCollectionRequest())
        clusters = await service.refresh_clusters(saved['workspace_id'], TrendClusterRefreshRequest(niche=saved['scope']['niche'], as_of=FIXTURE_AS_OF, learning_snapshot_id=saved['learning_snapshot_id']))
        ideas = await service.generate_ideas(clusters[0].cluster_id, IdeaGenerateRequest(niche=saved['scope']['niche'], learning_snapshot_id=saved['learning_snapshot_id']))
        assert all(item.brief['learning_feedback']['content_sha256'] == saved['content_sha256'] for item in ideas)
        await stack.production.engine.dispose()
        expected = await read(owned / 'production.db', project)
        restarted = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db', str(owned / 'production.db'), '--project', project], timeout=60))
        assert restarted == expected and restarted['learning'] == [saved] and restarted['analytics'] == before
        costs = [item for item in restarted['costs'] if item['provenance'].get('analytics_sync_id')]
        assert len(costs) == 3 and all(item['actual_cost'] is None for item in costs)
        write(root, 'restored-state.json', restarted)
        write(root, 'learning-snapshot.json', saved)
        write(root, 'feedback.json', feedback.json())
        write(root, 'trend-evidence.json', collection.model_dump(mode='json'))
        write(root, 'idea-shortlist.json', [item.model_dump(mode='json') for item in ideas])
        write(root, 'requests.json', {'authenticated_learning_requests': request_count, 'official_mock_reads': calls, 'actual_external_calls': 0})
        write(root, 'contract.json', {'status': 'PASS', 'synthetic_metric_seeds': 6, 'official_mock_reads': 3,
            'persisted_metric_snapshots': 7, 'learning_snapshots': 1, 'authenticated_learning_requests': request_count,
            'fresh_process_exact_restore': True, 'historical_metrics_unchanged': True, 'learning_cost_operations': 0,
            'analytics_cost_records': 3, 'actual_cost': None, 'advisory_trend_idea_lineage_verified': True,
            'publishing_time_unknown': True, 'full_media_qc': False, 'media_is_nonplayable_fixture_bytes': True,
            'real_provider_tested': False, 'paid_calls': 0, 'actual_external_calls': 0, 'real_credentials_read': 0,
            'owner_uat_accepted': False, 'accepted_media_replaced': False, 'production_deployed': False,
            'learning_loop_ready': False, 'video_factory_north_star_ready': False})
        print(json.dumps({'status': 'PASS', 'output': str(root), 'snapshots': 7, 'learning_snapshots': 1, 'mock_reads': 3}))
    finally:
        try: await anext(generator)
        except StopAsyncIteration: pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--read-db'); parser.add_argument('--project'); args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(read(args.read_db, args.project)), ensure_ascii=False))
    elif args.output: asyncio.run(run(args))
    else: parser.error('--output or --read-db is required')
