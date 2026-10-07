"""Persisted relative assessment and restart; every metric/provider input is synthetic."""
import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys

from app.main import app
from app.db import CostRecordORM, create_engine, create_session_factory
from sqlalchemy import select
from app.analytics_repository import AnalyticsRepository
from app.analytics_cohort import VERSION
from test_analytics_runtime import runtime_stack, reserve
from test_analytics_cohort import seed_peer, exercise_counter_history


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as file: json.dump(value, file, ensure_ascii=False, indent=2, default=str)


async def read(database, project):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix())
    repository = AnalyticsRepository(create_session_factory(engine))
    value = {'report': (await repository.report(project)).model_dump(mode='json'),
        'snapshots': [row.model_dump(mode='json') for row in await repository.list_snapshots(project)],
        'assessments': [row.model_dump(mode='json') for row in await repository.list_assessments(project)]}
    async with repository.session_factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.project_id == project).order_by(CostRecordORM.cost_id))).all()
        value['costs'] = [{'cost_id': row.cost_id, 'actual_cost': str(row.actual_cost) if row.actual_cost is not None else None,
            'estimated_cost': str(row.estimated_cost) if row.estimated_cost is not None else None, 'provenance': row.provenance} for row in costs]
    await engine.dispose()
    return value


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False)
    owned = root / 'owned-fixture'; owned.mkdir()
    generator = runtime_stack.__wrapped__(owned)
    stack, runtime, current, requests, _, _ = await anext(generator)
    try:
        if args.counter_history:
            report, calls = await exercise_counter_history(stack, runtime)
            await stack.production.engine.dispose()
            expected = await read(owned / 'production.db', report.project_id)
            restarted = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db',
                str(owned / 'production.db'), '--project', report.project_id], timeout=45))
            assert restarted == expected and len(restarted['snapshots']) == 12
            analytics_costs = [row for row in restarted['costs'] if row['provenance'].get('analytics_sync_id')]
            assert len(analytics_costs) == 24 and all(row['actual_cost'] is None for row in analytics_costs)
            write(root, 'restored-state.json', restarted)
            write(root, 'policy.json', stack.processor.winner_policy.model_dump(mode='json'))
            write(root, 'requests.json', {'official_mock_reads': calls, 'actual_external_calls': 0})
            factor = next(item for item in report.latest_assessment.factors if item.factor == 'view_velocity')
            write(root, 'counter-evidence.json', factor.model_dump(mode='json'))
            write(root, 'contract.json', {'status': 'PASS', 'collections': 12, 'official_mock_reads': 24,
                'persisted_snapshots': 12, 'distinct_peer_posts': 5, 'analytics_cost_records': 24, 'actual_cost': None,
                'fresh_process_restore': True, 'earlier_collection_clock_is_fixture': True,
                'historical_counter_refs_preserved': True, 'views_per_hour_is_reported_counter_growth': True,
                'unsupported_retention_and_completion_null': True, 'publishing_age_null': True,
                'assessment_state': 'insufficient_data', 'algorithm_version': VERSION,
                'media_is_nonplayable_fixture_bytes': True, 'real_provider_tested': False,
                'actual_external_calls': 0, 'paid_calls': 0, 'real_credentials_read': 0,
                'owner_uat_accepted': False, 'accepted_media_replaced': False,
                'production_deployed': False, 'winner_detection_ready': False})
            print(json.dumps({'status': 'PASS', 'output': str(root), 'mock_reads': 24, 'peer_posts': 5, 'snapshots': 12}))
            return
        for index in range(5): await seed_peer(stack, current[0], index)
        await seed_peer(stack, current[0], 5, remote='PeerVid0000')
        await seed_peer(stack, current[0], 6, query={'start_date': '2026-09-01', 'end_date': '2026-09-02'})
        await seed_peer(stack, current[0], 7, target=current[0].model_copy(update={'profile_version': 2}))
        await seed_peer(stack, current[0], 8, mock=False)  # Flag simulation only; zero external calls.
        assert requests == []
        before = [row.model_dump(mode='json') for row in await stack.repository.list_snapshots(stack.publication.project_id)]
        sync = await reserve(stack, 'cohort-fresh-process'); result = await stack.processor.process(sync.sync_id)
        assert result.status == 'succeeded' and result.mock and not result.external_call and len(requests) == 3
        report = await stack.repository.report(sync.project_id)
        assert report.latest_assessment.algorithm_version == VERSION and report.latest_assessment.state == 'winner_candidate'
        retention = next(item for item in report.latest_assessment.factors if item.factor == 'retention')
        assert retention.evidence['peer_count'] == 5
        await stack.production.engine.dispose()
        expected = await read(owned / 'production.db', sync.project_id)
        restarted = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db',
            str(owned / 'production.db'), '--project', sync.project_id], timeout=45))
        assert restarted == expected
        after = {row['snapshot_id']: row for row in restarted['snapshots']}
        assert len(after) == 10 and all(after[row['snapshot_id']] == row for row in before)
        assert report.latest_snapshot.metrics.observation_window_hours is None
        write(root, 'restored-state.json', restarted)
        write(root, 'policy.json', stack.processor.winner_policy.model_dump(mode='json'))
        write(root, 'requests.json', {'official_mock_reads': requests, 'actual_external_calls': 0})
        write(root, 'lineage.json', {'prior_snapshots_unchanged': [row['snapshot_id'] for row in before],
            'current_snapshot_id': report.latest_snapshot.snapshot_id, 'peer_refs': retention.evidence['peer_snapshot_ids'],
            'policy_sha256': stack.processor.winner_policy.digest()})
        write(root, 'contract.json', {'status': 'PASS', 'synthetic_metric_seed_count': 9, 'mock_official_requests': 3,
            'compatible_distinct_peer_posts': 5, 'persisted_snapshots': 10, 'old_snapshots_unchanged': 9,
            'fresh_process_restore': True, 'scope_mismatches_excluded': True, 'remote_post_duplicates_not_counted': True,
            'source_transport_flag_simulation_only': True, 'media_is_nonplayable_fixture_bytes': True,
            'provider_coverage_fabricated': False, 'publishing_age_fabricated': False,
            'algorithm_version': VERSION, 'observed_state_is_mock_only': True, 'real_provider_tested': False,
            'actual_external_calls': 0, 'paid_calls': 0, 'real_credentials_read': 0, 'owner_uat_accepted': False,
            'accepted_media_replaced': False, 'production_deployed': False, 'winner_detection_ready': False})
        print(json.dumps({'status': 'PASS', 'output': str(root), 'mock_reads': 3, 'peer_posts': 5, 'snapshots': 10}))
    finally: await generator.aclose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--read-db'); parser.add_argument('--project')
    parser.add_argument('--counter-history', action='store_true')
    args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(read(args.read_db, args.project))))
    else:
        assert args.output
        asyncio.run(run(args))
