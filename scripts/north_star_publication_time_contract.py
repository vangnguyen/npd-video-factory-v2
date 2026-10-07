"""Two timestamp read snapshots, authenticated review and exact separate-process restore."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import httpx
from sqlalchemy import select

from app.analytics_repository import AnalyticsRepository
from app.db import CostRecordORM, create_engine, create_session_factory
from app.learning_service import ChannelLearningService
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_runtime import runtime_stack
from test_analytics_publication_time import posted_runtime, collect_posted, POSTED
from test_channel_learning import learning_app


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as file: json.dump(value, file, ensure_ascii=False, indent=2, default=str)


async def read(database, project, publication):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix()); factory = create_session_factory(engine)
    analytics = AnalyticsRepository(factory)
    value = {'report': (await analytics.report(project, publication_id=publication, provider_mode='official')).model_dump(mode='json'),
        'snapshots': [item.model_dump(mode='json') for item in await analytics.list_snapshots(project)],
        'assessments': [item.model_dump(mode='json') for item in await analytics.list_assessments(project)],
        'learning': [item.model_dump(mode='json') for item in await ChannelLearningService(factory).list(project)]}
    async with factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.project_id == project).order_by(CostRecordORM.cost_id))).all()
        value['costs'] = [{'cost_id': item.cost_id, 'actual_cost': str(item.actual_cost) if item.actual_cost is not None else None,
            'estimated_cost': str(item.estimated_cost) if item.estimated_cost is not None else None, 'provenance': item.provenance} for item in costs]
    await engine.dispose(); return value


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False); owned = root / 'owned-fixture'; owned.mkdir()
    generator = runtime_stack.__wrapped__(owned); stack, runtime, _, _, _, _ = await anext(generator)
    try:
        calls, timestamp, _ = await posted_runtime(stack, runtime)
        first = await collect_posted(stack, 'contract-first'); assert first.video_features.publishing_time == POSTED
        old = first.latest_snapshot.model_dump(mode='json')
        project, publication = stack.publication.project_id, stack.publication.publication_id
        app = learning_app(stack); requests = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
            path = f'/api/v1/projects/{project}/publications/{publication}/analytics'
            response = await client.get(path, params={'provider_mode': 'official'}); requests.append({'method': 'GET', 'path': path})
            assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
            first_review = response.json(); assert first_review['video_features']['evidence']['exact_publishing_time_available']
            assert first_review['latest_assessment']['state'] == 'insufficient_data'
            timestamp[0] = None; later = await collect_posted(stack, 'contract-missing'); assert later.video_features.publishing_time is None
            path = f'/api/v1/projects/{project}/analytics/learning-snapshots'
            reply = await client.post(path, json={'publication_id': publication}, headers={'Idempotency-Key': 'posted-contract-fixture-learning'}); requests.append({'method': 'POST', 'path': path})
            assert reply.status_code == 201; learning = reply.json()
            assert not learning['observations'] and all(item['state'] == 'insufficient_data' for item in learning['dimensions'])
        before = await read(owned / 'production.db', project, publication)
        assert any(item == old for item in before['snapshots']) and len(calls) == 4
        await stack.production.engine.dispose()
        restored = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db', str(owned / 'production.db'),
            '--project', project, '--publication', publication], timeout=60)); assert restored == before
        costs = [item for item in restored['costs'] if item['provenance'].get('analytics_sync_id')]
        assert len(costs) == 4 and all(item['actual_cost'] is None for item in costs)
        write(root, 'first-provider-review.json', first_review); write(root, 'missing-refresh-review.json', later.model_dump(mode='json'))
        write(root, 'learning-snapshot.json', learning); write(root, 'restored-state.json', restored)
        write(root, 'requests.json', {'authenticated_requests': requests, 'official_mock_reads': calls, 'actual_external_calls': 0})
        write(root, 'contract.json', {'status': 'PASS', 'official_mock_reads': 4, 'authenticated_requests': 2,
            'snapshots': 2, 'utc_provider_posted_time_bound_to_response': True, 'first_public_exposure_verified': False,
            'missing_refresh_stays_null': True, 'insufficient_retention_prevents_winner_or_learning_claim': True,
            'historical_metrics_unchanged': True, 'fresh_process_exact_restore': True, 'actual_cost': None,
            'media_is_nonplayable_fixture_bytes': True, 'full_media_qc': False, 'owner_uat_accepted': False,
            'accepted_media_replaced': False, 'actual_external_calls': 0, 'paid_calls': 0, 'real_credentials_read': 0,
            'real_provider_tested': False, 'production_deployed': False, 'learning_loop_ready': False,
            'video_factory_north_star_ready': False})
        print(json.dumps({'status': 'PASS', 'output': str(root), 'mock_reads': 4, 'snapshots': 2, 'fresh_process_restore': True}))
    finally:
        try: await anext(generator)
        except StopAsyncIteration: pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--read-db'); parser.add_argument('--project'); parser.add_argument('--publication'); args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(read(args.read_db, args.project, args.publication)), ensure_ascii=True))
    elif args.output: asyncio.run(run(args))
    else: parser.error('--output or --read-db is required')
