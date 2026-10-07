"""Owned SQLite/ASGI projection tests, with explicitly simulated transport flags."""
from types import SimpleNamespace
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, update

from app.analytics_db import AnalyticsMetricSnapshotORM, AnalyticsMetricPointORM
from app.analytics_models import AnalyticsSyncRequest
from app.analytics_repository import AnalyticsRepository
from app.analytics_views import _target
from app.publishing_db import PublicationORM
from app.publishing_credentials import target_digest
from app.publishing_models import PublishingTargetBinding
from test_analytics_publication_api import application
from test_analytics_runtime import runtime_stack, reserve
from auth_test_support import TEST_HUMAN_HEADERS


async def seed_observations(stack, count=7):
    sync = await reserve(stack); await stack.processor.process(sync.sync_id)
    async with stack.repository.session_factory() as session:
        original = await session.scalar(select(AnalyticsMetricSnapshotORM))
        values = {column.name: getattr(original, column.name) for column in original.__table__.columns}
        # New sync IDs are real fixture jobs; no provider call is made for these copied observations.
    for index in range(count - 1):
        queued = await reserve(stack, f'copied-page-{index}')
        async with stack.repository.session_factory() as session:
            data = {**values, 'snapshot_id': f'ams_explicit_copied_page_{index:04d}', 'sync_id': queued.sync_id}
            session.add(AnalyticsMetricSnapshotORM(**data)); await session.flush()
            session.add(AnalyticsMetricPointORM(point_id=f'amp_explicit_page_{index}', snapshot_id=data['snapshot_id'],
                metric_name='views', value=0 if index == 0 else None, unit='count', supported=index == 0))
            await session.commit()
    return sync


@pytest.mark.asyncio
async def test_keyset_pages_keep_ties_null_zero_and_scope_without_provider_calls(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    sync = await seed_observations(stack)
    before = len(calls)
    app = application(stack, role='viewer')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        base = f'/api/v1/projects/{sync.project_id}/publications/{sync.publication_id}/analytics'
        seen = []; cursor = None
        for _ in range(3):
            params = {'provider_mode': 'official', 'limit': 3}
            if cursor: params['cursor'] = cursor
            result = await client.get(base + '/observations', params=params)
            assert result.status_code == 200 and result.headers['Cache-Control'] == 'no-store'
            page = result.json(); assert page['total_count'] == 7 and len(page['items']) <= 3
            seen.extend(page['items']); cursor = page['next_cursor']
        assert cursor is None and len({row['snapshot_id'] for row in seen}) == len(seen) == 7
        assert any(row['metrics']['views'] == 0 for row in seen)
        assert any(row['metrics']['views'] is None for row in seen)
        assert (await client.get(base, params={'provider_mode': 'official'})).json()['history_count'] == 7
        for params, expected in [({'limit': 101}, 422), ({'limit': 0}, 422), ({'provider_mode': 'unknown'}, 422),
            ({'provider_mode': 'fixture', 'cursor': seen[0]['snapshot_id']}, 400), ({'cursor': 'ams_missing_cursor'}, 400)]:
            assert (await client.get(base + '/observations', params=params)).status_code == expected
        assert (await client.get(base + '/observations', params={'provider_mode': 'fixture'})).json()['items'] == []
        restarted = AnalyticsRepository(stack.repository.session_factory)
        old = await restarted.list_snapshots(sync.project_id, provider_mode='official')
        assert {value.snapshot_id for value in old} == {row['snapshot_id'] for row in seen}
    assert len(calls) == before == 3


@pytest.mark.asyncio
async def test_channel_projection_separates_targets_transport_and_unverified_fixture(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    sync = await reserve(stack); await stack.processor.process(sync.sync_id)
    fixture, _ = await stack.service.create_sync(project_id=sync.project_id,
        payload=AnalyticsSyncRequest(publication_id=sync.publication_id, provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='channel-views-explicit-fixture')
    await stack.processor.process(fixture.sync_id)
    async with stack.repository.session_factory() as session:
        parent = await session.get(PublicationORM, sync.publication_id)
        values = {column.name: getattr(parent, column.name) for column in parent.__table__.columns}
        for index in range(3):
            other = {**values, 'publication_id': f'pub_channel_explicit_fixture_{index}', 'idempotency_key_hash': str(index) * 64}
            if index == 2:
                target = current[0].model_copy(update={'target_account_id': 'UC_second_fixture'})
                other['provider_validation_json'] = {**values['provider_validation_json'], 'target_binding': target.model_dump(mode='json')}
            session.add(PublicationORM(**other))
        await session.commit()
        snapshot = await session.scalar(select(AnalyticsMetricSnapshotORM).where(AnalyticsMetricSnapshotORM.source_kind == 'official_api'))
        copied = {column.name: getattr(snapshot, column.name) for column in snapshot.__table__.columns}
    for index in range(3):
        queued, _ = await stack.service.create_sync(project_id=sync.project_id,
            payload=AnalyticsSyncRequest(publication_id=f'pub_channel_explicit_fixture_{index}', provider_mode='official', query=sync.query),
            idempotency_key=f'channel-copy-explicit-fixture-{index}')
        async with stack.repository.session_factory() as session:
            # Deliberate metadata simulation only; never real-provider acceptance.
            session.add(AnalyticsMetricSnapshotORM(**{**copied, 'snapshot_id': f'ams_explicit_channel_copy_{index}',
                'sync_id': queued.sync_id, 'publication_id': queued.publication_id, 'mock': index != 0,
                'external_call': False, 'evidence_json': {**copied['evidence_json'], 'transport_flag_simulation': True}}))
            await session.commit()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(stack, role='viewer')), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        base = f'/api/v1/workspaces/{sync.workspace_id}/analytics/channels'
        response = await client.get(base, params={'provider_mode': 'official'})
        assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
        result = response.json(); assert result['account_totals'] is None and result['publications_in_page'] == 4
        matched = [channel for channel in result['channels'] if any(video['binding_state'] == 'matched' for video in channel['videos'])]
        assert sorted(channel['mock'] for channel in matched) == [False, True]
        assert all(channel['target_binding_sha256'] == target_digest(current[0]) for channel in matched)
        assert all(channel['target_account_id'] == current[0].target_account_id for channel in matched)
        mismatch = [video for channel in result['channels'] for video in channel['videos'] if video['binding_state'] == 'mismatch']
        assert len(mismatch) == 1 and mismatch[0]['publication_id'].endswith('_2')
        fixture_result = (await client.get(base)).json()
        observed = [video for channel in fixture_result['channels'] for video in channel['videos'] if video['latest_snapshot']]
        assert len(observed) == 1 and observed[0]['binding_state'] == 'fixture_unverified'
        assert observed[0]['latest_snapshot']['metrics']['views'] == 18000
        first = (await client.get(base, params={'limit': 2})).json()
        assert first['publications_in_page'] == 2 and first['next_cursor']
        second = (await client.get(base, params={'limit': 2, 'cursor': first['next_cursor']})).json()
        assert second['publications_in_page'] == 2 and second['next_cursor'] is None
        first_ids = {video['publication_id'] for channel in first['channels'] for video in channel['videos']}
        second_ids = {video['publication_id'] for channel in second['channels'] for video in channel['videos']}
        assert not first_ids & second_ids
        assert (await client.get(base, params={'cursor': 'pub_missing_cursor'})).status_code == 400
    assert len(calls) == 3  # Every view is a database read.


@pytest.mark.asyncio
async def test_channel_read_requires_exact_workspace_and_human_identity(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    base = f'/api/v1/workspaces/{stack.publication.workspace_id}/analytics/channels'
    app = application(stack)
    from auth_test_support import install_test_human_auth
    install_test_human_auth(app, platform_repository=stack.production.platform, platform_role=None,
        workspace_roles={'wsp_foreign_only': 'owner'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture') as client:
        assert (await client.get(base)).status_code == 401
        assert (await client.get(base, headers=TEST_HUMAN_HEADERS)).status_code == 404
    assert calls == []


@pytest.mark.asyncio
async def test_summary_keeps_assessment_and_learning_bound_to_latest_observation(runtime_stack):
    stack, _, _, _, _, _ = runtime_stack
    official = await reserve(stack); await stack.processor.process(official.sync_id)
    first = (await stack.repository.list_snapshots(official.project_id))[0]
    fixture, _ = await stack.service.create_sync(project_id=official.project_id,
        payload=AnalyticsSyncRequest(publication_id=official.publication_id, provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='summary-later-created-fixture-observation')
    await stack.processor.process(fixture.sync_id)
    async with stack.repository.session_factory() as session:
        await session.execute(update(AnalyticsMetricSnapshotORM).where(AnalyticsMetricSnapshotORM.snapshot_id == first.snapshot_id)
            .values(collected_at=first.collected_at + timedelta(days=1)))
        await session.commit()
    report = await stack.repository.report(official.project_id)
    assert report.history_count == 2 and report.latest_snapshot.snapshot_id == first.snapshot_id
    assert report.latest_assessment.snapshot_id == first.snapshot_id
    assert report.learning_insights and all(insight.snapshot_id == first.snapshot_id for insight in report.learning_insights)
    assert report.learning_insights_truncated is False


@pytest.mark.parametrize('change', [{'workspace_id': 'foreign'}, {'platform': 'tiktok'}, {'provider_key': 'other'}])
def test_wrong_workspace_or_platform_binding_is_unbound(change):
    target = PublishingTargetBinding(workspace_id='wsp_fixture', platform='youtube', provider_key='youtube-provider',
        profile_id='ppf_fixture', profile_version=1, target_account_id='UC_fixture', credential_binding_sha256='a' * 64)
    parent = SimpleNamespace(workspace_id='wsp_fixture', platform='youtube', provider_key='youtube-provider',
        provider_validation_json={'target_binding': target.model_copy(update=change).model_dump(mode='json')})
    assert _target(parent) is None
