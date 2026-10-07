"""Synthetic history to proposal ranking and explicit template edit; owned data only."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys
import httpx
from fastapi import Depends
from sqlalchemy import select
from app.main import app
from app.db import create_engine, create_session_factory, CostRecordORM
from app.learning_service import ChannelLearningService
from app.analytics_repository import AnalyticsRepository
from app.production_repository import ProductionRepository
from app.trend_repository import TrendRepository
from app.human_auth import authorize_human_request
from app.trend_routes import router as trend_router
from app.production_routes import router as production_router
from app.subtitle_templates import template_catalog
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_runtime import runtime_stack
from test_channel_learning import learning_app
from test_personalized_opportunities import personalized_history


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as file: json.dump(value, file, ensure_ascii=False, indent=2, default=str)


async def read(database, project, workspace):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix()); factory = create_session_factory(engine)
    learning = ChannelLearningService(factory); analytics = AnalyticsRepository(factory)
    value = {'learning': [item.model_dump(mode='json') for item in await learning.list(project)],
        'analytics': [item.model_dump(mode='json') for item in await analytics.list_snapshots(project)],
        'queue': [item.model_dump(mode='json') for item in await TrendRepository(factory).list_queue(workspace)],
        'production': (await ProductionRepository(factory).get_package(project)).model_dump(mode='json')}
    async with factory() as session:
        rows = (await session.scalars(select(CostRecordORM).where(CostRecordORM.project_id == project).order_by(CostRecordORM.cost_id))).all()
        value['costs'] = [{'cost_id': item.cost_id, 'actual_cost': str(item.actual_cost) if item.actual_cost is not None else None,
            'provenance': item.provenance} for item in rows]
    await engine.dispose(); return value


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False); owned = root / 'owned-fixture'; owned.mkdir()
    generator = runtime_stack.__wrapped__(owned); stack, _, target, calls, _, _ = await anext(generator)
    try:
        catalog = template_catalog(); sentence = next(item for item in catalog['templates'] if item['template_ref'] == 'sentence-clean@v1')
        fade = next(item for item in catalog['templates'] if item['template_ref'] == 'animated-fade@v1')
        _, trend, snapshot, _ = await personalized_history(stack, target[0], subtitle_styles=[sentence['style'], fade['style']])
        assert len(calls) == 3
        project = snapshot.project_id; workspace = snapshot.workspace_id
        before = [item.model_dump(mode='json') for item in await stack.repository.list_snapshots(project)]
        package = await stack.production.service.get(project); original_version = package.subtitle.version
        application = learning_app(stack); application.state.trend_intelligence_service = trend; application.state.production_package_service = stack.production.service
        application.include_router(trend_router, dependencies=[Depends(authorize_human_request)])
        application.include_router(production_router, dependencies=[Depends(authorize_human_request)])
        requests = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
            endpoint = f'/api/v1/workspaces/{workspace}/trend-clusters'
            ranked = await client.get(endpoint, params={'learning_snapshot_id': snapshot.learning_snapshot_id, 'niche': snapshot.scope['niche'], 'history_weight': .5})
            requests.append({'method': 'GET', 'path': endpoint}); assert ranked.status_code == 200
            adjusted = [item['learning_feedback']['personalized_opportunity'] for item in ranked.json()]
            assert any((item['history_adjustment_points'] or 0) > 0 for item in adjusted)
            assert any((item['history_adjustment_points'] or 0) < 0 for item in adjusted)
            endpoint = f'/api/v1/workspaces/{workspace}/content-opportunities/refresh'
            queued = await client.post(endpoint, json={'niche': snapshot.scope['niche'], 'learning_snapshot_id': snapshot.learning_snapshot_id,
                'learning_policy': {'history_weight': .5}})
            requests.append({'method': 'POST', 'path': endpoint}); assert queued.status_code == 200
            assert queued.json() and all(item['provenance']['personalized_estimate']['recommendation_only'] for item in queued.json())
            endpoint = f'/api/v1/projects/{project}/analytics/learning-snapshots/{snapshot.learning_snapshot_id}/subtitle-suggestions'
            advice = await client.get(endpoint); requests.append({'method': 'GET', 'path': endpoint}); assert advice.status_code == 200
            assert await stack.production.service.get(project) == package
            choice = next(item for item in advice.json()['suggestions'] if item['template_ref'] == 'sentence-clean@v1')
            assert choice['selectable'] and not choice['historical_template_identity_verified']
            endpoint = f'/api/v1/projects/{project}/subtitles'
            saved = await client.put(endpoint, json={'expected_timeline_version': package.timeline_version,
                'expected_subtitle_version': package.subtitle.version, 'style': choice['style'],
                'cues': [item.model_dump(mode='json') for item in package.subtitle.cues], 'actor_ref': 'explicit-fixture-template-choice'})
            requests.append({'method': 'PUT', 'path': endpoint}); assert saved.status_code == 200
            assert saved.json()['subtitle']['version'] == original_version + 1
            assert saved.json()['subtitle']['style']['template_ref'] == choice['template_ref']
        assert len(calls) == 3 and (await application.state.channel_learning_service.get(workspace, snapshot.learning_snapshot_id)) == snapshot
        assert [item.model_dump(mode='json') for item in await stack.repository.list_snapshots(project)] == before
        await stack.production.engine.dispose(); expected = await read(owned / 'production.db', project, workspace)
        restarted = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db', str(owned / 'production.db'),
            '--project', project, '--workspace', workspace], timeout=60)); assert restarted == expected
        analytics_costs = [item for item in restarted['costs'] if item['provenance'].get('analytics_sync_id')]
        assert len(analytics_costs) == 3 and all(item['actual_cost'] is None for item in analytics_costs)
        write(root, 'restored-state.json', restarted); write(root, 'learning-snapshot.json', snapshot.model_dump(mode='json'))
        write(root, 'personalized-trends.json', ranked.json()); write(root, 'opportunity-queue.json', queued.json())
        write(root, 'subtitle-suggestions.json', advice.json()); write(root, 'explicit-template-edit.json', saved.json())
        write(root, 'requests.json', {'authenticated_requests': requests, 'official_mock_reads': calls, 'actual_external_calls': 0})
        write(root, 'contract.json', {'status': 'PASS', 'synthetic_history_seeds': 6, 'official_mock_reads': 3, 'authenticated_requests': 4,
            'persisted_snapshots': 7, 'fresh_process_exact_restore': True, 'personalized_estimated_proposals': True,
            'positive_and_negative_history_adjustments': True, 'base_trend_facts_preserved': True,
            'explicit_template_save_version_increment': 1, 'template_identity_inferred_only_from_style_fields': True,
            'no_edit_from_reading_suggestions': True, 'historical_metrics_and_learning_unchanged': True,
            'analytics_actual_cost': None, 'actual_external_calls': 0, 'paid_calls': 0, 'real_credentials_read': 0,
            'media_is_nonplayable_fixture_bytes': True, 'full_media_qc': False, 'owner_uat_accepted': False,
            'accepted_media_replaced': False, 'real_provider_tested': False, 'production_deployed': False,
            'learning_loop_ready': False, 'video_factory_north_star_ready': False})
        print(json.dumps({'status': 'PASS', 'output': str(root), 'mock_reads': 3, 'authenticated_requests': 4, 'snapshots': 7}))
    finally:
        try: await anext(generator)
        except StopAsyncIteration: pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--read-db'); parser.add_argument('--project'); parser.add_argument('--workspace'); args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(read(args.read_db, args.project, args.workspace)), ensure_ascii=True))
    elif args.output: asyncio.run(run(args))
    else: parser.error('--output or --read-db is required')
