"""Owned SQLite, official read requests through MockTransport; no provider acceptance."""
import asyncio
from datetime import timedelta
from decimal import Decimal
import json

import httpx
import pytest
from sqlalchemy import select, update

from app.analytics_models import AnalyticsSyncRequest, VideoFeatureMetadata, NormalizedMetrics
from app.analytics_providers import AnalyticsCollectionContext, AnalyticsCollection
from app.analytics_logic import assess_winner
from app.analytics_repository import AnalyticsRepository
from app.analytics_runtime import OfficialAnalyticsRuntime
from app.analytics_official import AnalyticsHTTPClient, AnalyticsOAuthCredential, YT_READ, YT_ANALYTICS
from app.db import ProviderRegistryORM, ProviderUsageORM, CostRecordORM, utc_now
from app.analytics_db import AnalyticsSyncORM
from app.timeline_db import TimelineORM, TimelineVersionORM
from app.publishing_db import PublicationORM
from app.publishing_models import PublicationReceipt, PublishingTargetBinding
from app.publishing_profiles import PROVIDER_KEYS
from test_analytics_learning import analytics_stack
from test_analytics_official import yt_table


@pytest.fixture
async def runtime_stack(tmp_path):
    stack = await analytics_stack(tmp_path)
    platform = 'youtube'; parent = stack.publication
    target = PublishingTargetBinding(workspace_id=parent.workspace_id, profile_id='ppf_analytics_fixture', profile_version=1,
        platform=platform, provider_key=PROVIDER_KEYS[platform], target_account_id='UC_analytics_fixture', credential_binding_sha256='a' * 64)
    current = [target]; calls = []; reply = [yt_table()]; intercept = [None]
    async with stack.production.repository.session_factory() as session:
        async with session.begin():
            row = await session.get(PublicationORM, parent.publication_id)
            row.provider_key = target.provider_key; row.mode = 'live'; row.dry_run = False; row.status = 'published'; row.mock = True; row.external_action = False
            row.provider_validation_json = {**row.provider_validation_json, 'provider_key': target.provider_key,
                'target_binding': target.model_dump(mode='json')}
            row.receipt_json = PublicationReceipt(receipt_id='receipt_EXPLICIT_ANALYTICS_FIXTURE', provider_key=target.provider_key,
                platform=platform, mode='live', request_fingerprint=parent.request_fingerprint, remote_post_id='abcDEfgHI_1',
                remote_url=None, mock=True, external_action=False, created_at=utc_now()).model_dump(mode='json')
            session.add(ProviderRegistryORM(provider_id='pvd_analytics_fixture', workspace_id=parent.workspace_id,
                provider_key='youtube-analytics-api', display_name='EXPLICIT ANALYTICS FIXTURE', capability='analytics',
                adapter='explicit.fixture', routing_mode='disabled', status='fixture', enabled=False, supports_dry_run=True,
                config_ref=None, metadata_json={'fixture_only': True}))
    def receive(request):
        calls.append({'method': request.method, 'host': request.url.host, 'path': request.url.path})
        if request.url.path.endswith('/channels'): value = {'items': [{'id': target.target_account_id}]}
        elif request.url.path.endswith('/videos'): value = {'items': [{'id': 'abcDEfgHI_1', 'snippet': {'channelId': target.target_account_id}}]}
        else:
            if intercept[0]: intercept[0]()
            if isinstance(reply[0], int): return httpx.Response(reply[0], headers={'Retry-After': '40'}, json={'private-error': 'PRIVATE TOKEN'})
            value = reply[0]
        return httpx.Response(200, json=value)
    settings = stack.settings
    settings.analytics_external_execution_enabled = True; settings.provider_external_execution_enabled = True
    runtime = OfficialAnalyticsRuntime(repository=stack.repository, publishing_repository=stack.service.publishing_repository,
        settings=settings, target_provider=lambda *_: current[0],
        credential_resolver=lambda selected: AnalyticsOAuthCredential(selected, utc_now() + timedelta(hours=1),
            frozenset({YT_READ, YT_ANALYTICS}), 'EXPLICIT-ANALYTICS-FIXTURE-TOKEN'),
        clients={'youtube': AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))})
    runtime.install(stack.providers)
    try: yield stack, runtime, current, calls, reply, intercept
    finally: await stack.production.engine.dispose()


async def reserve(stack, suffix='initial'):
    return (await stack.service.create_sync(project_id=stack.production.project.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='official',
            query={'start_date': '2026-10-01', 'end_date': '2026-10-06'}), idempotency_key='analytics-runtime-fixture-' + suffix))[0]


@pytest.mark.asyncio
async def test_scoped_runtime_persists_null_metrics_evidence_costs_and_immutable_history(runtime_stack):
    stack, runtime, current, calls, reply, _ = runtime_stack
    sync = await reserve(stack)
    assert sync.query['start_date'] == '2026-10-01'
    result = await stack.processor.process(sync.sync_id)
    assert result.status == 'succeeded' and result.mock is True and result.external_call is False
    assert len(calls) == 3 and [value['method'] for value in calls] == ['GET'] * 3
    old = (await stack.repository.list_snapshots(sync.project_id))[0]
    assert old.metrics.watch_time == 7230 and old.metrics.revenue is None and old.metrics.completion_rate is None
    assert old.evidence['account_match'] and old.evidence['coverage_end_date'] is None
    assert len(old.evidence['request_observations']) == 3
    old_json = old.model_dump(mode='json')
    reply[0] = yt_table([2000, 220, 6.6, 60, 3, 11, 8])
    refreshed = await reserve(stack, 'refresh')
    await stack.processor.process(refreshed.sync_id)
    restarted = AnalyticsRepository(stack.repository.session_factory)
    snapshots = await restarted.list_snapshots(sync.project_id)
    assert len(snapshots) == 2 and snapshots[1].model_dump(mode='json') == old_json
    async with stack.repository.session_factory() as session:
        usages = (await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.capability == 'analytics'))).all()
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provider_usage_id.in_([usage.usage_id for usage in usages])))).all()
    assert len(usages) == len(costs) == 6 and all(usage.status == 'confirmed' and usage.job_id is None for usage in usages)
    assert all(cost.actual_cost is None and cost.estimated_cost is None for cost in costs)
    assert all('analytics_sync_id' in cost.provenance for cost in costs)
    states = stack.service.provider_states()
    assert all(not state.external_calls_enabled and not state.real_provider_tested for state in states)
    evidence = json.dumps([snapshot.model_dump(mode='json') for snapshot in snapshots])
    assert 'EXPLICIT-ANALYTICS-FIXTURE-TOKEN' not in evidence


@pytest.mark.asyncio
async def test_concurrent_claim_does_not_collect_twice_and_live_attempt_is_not_recovered(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    sync = await reserve(stack)
    claims = await asyncio.gather(stack.repository.claim(sync.sync_id), stack.repository.claim(sync.sync_id))
    assert sum(claim is not None for claim in claims) == 1
    assert await stack.repository.recover_incomplete_sync_ids() == []
    busy = await stack.processor.process(sync.sync_id)
    assert busy.status == 'running' and calls == []
    async with stack.repository.session_factory() as session:
        await session.execute(update(AnalyticsSyncORM).where(AnalyticsSyncORM.sync_id == sync.sync_id).values(updated_at=utc_now() - timedelta(minutes=6)))
        await session.commit()
    assert await stack.repository.recover_incomplete_sync_ids() == [sync.sync_id]
    fresh = await stack.repository.claim(sync.sync_id)
    assert fresh.attempt_count == 2
    with pytest.raises(RuntimeError, match='OWNERSHIP_LOST'):
        await stack.repository.schedule_retry(sync.sync_id, next_retry_at=utc_now(), code='STALE', reason='STALE', expected_attempt=1)
    assert (await stack.repository.get_sync_by_id(sync.sync_id)).attempt_count == 2


@pytest.mark.asyncio
async def test_account_configuration_change_blocks_before_any_read(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    sync = await reserve(stack)
    current[0] = current[0].model_copy(update={'profile_version': 2})
    failed = await stack.processor.process(sync.sync_id)
    assert failed.status == 'failed' and failed.failure_code == 'ANALYTICS_ACCOUNT_BINDING_CHANGED'
    assert calls == [] and await stack.repository.list_snapshots(sync.project_id) == []


@pytest.mark.asyncio
async def test_binding_change_after_response_prevents_snapshot_or_learning(runtime_stack):
    stack, _, current, calls, _, intercept = runtime_stack
    sync = await reserve(stack)
    intercept[0] = lambda: current.__setitem__(0, current[0].model_copy(update={'profile_version': 2}))
    failed = await stack.processor.process(sync.sync_id)
    assert failed.status == 'failed' and len(calls) == 3
    assert await stack.repository.list_snapshots(sync.project_id) == []
    assert await stack.repository.list_insights(sync.project_id) == []


@pytest.mark.asyncio
async def test_read_backoff_keeps_history_empty_and_records_unknown_actual_cost(runtime_stack):
    stack, _, _, calls, reply, _ = runtime_stack
    reply[0] = 429; sync = await reserve(stack)
    result = await stack.processor.process(sync.sync_id)
    assert result.status == 'retry_scheduled' and result.failure_code == 'ANALYTICS_RATE_LIMITED'
    assert result.next_retry_at is not None and len(calls) == 3
    assert 'PRIVATE TOKEN' not in result.failure_reason and await stack.repository.list_snapshots(sync.project_id) == []


@pytest.mark.asyncio
async def test_unknown_read_price_under_configured_cap_records_approval_without_wire(runtime_stack):
    stack, runtime, _, calls, _, _ = runtime_stack
    runtime.cost_policy = lambda _: {'max_ai_cost': Decimal('100'), 'estimated_cost': None}
    sync = await reserve(stack); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'failed' and result.failure_code == 'ANALYTICS_COST_APPROVAL_REQUIRED' and calls == []
    async with stack.repository.session_factory() as session:
        cost = await session.scalar(select(CostRecordORM).where(CostRecordORM.needs_approval.is_(True)))
    assert cost is not None and cost.actual_cost is None and cost.estimated_cost is None


@pytest.mark.asyncio
async def test_default_no_install_and_mock_publication_cannot_use_network_runtime(runtime_stack):
    stack, runtime, _, calls, _, _ = runtime_stack
    assert not OfficialAnalyticsRuntime(repository=stack.repository, publishing_repository=stack.service.publishing_repository,
        settings=stack.settings).clients
    runtime.clients['youtube'] = AnalyticsHTTPClient('youtube', network_enabled=True)
    runtime.explicit_cost_policy = True
    sync = await reserve(stack); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'failed' and result.failure_code == 'ANALYTICS_REAL_PUBLICATION_REQUIRED'
    assert calls == [] and result.external_call is False


@pytest.mark.asyncio
async def test_simulated_transport_flag_is_persisted_without_silent_false_rewrite(runtime_stack):
    # Unit-level transport truth simulation. This does not make a provider call,
    # assert real acceptance, or populate observed metrics.
    stack, _, _, calls, _, _ = runtime_stack
    sync = await reserve(stack); claimed = await stack.repository.claim(sync.sync_id)
    collection = AnalyticsCollection(provider_key='youtube-analytics-api', source='contract://transport-flag-only',
        source_kind='official_api', collected_at=utc_now(), metrics=NormalizedMetrics(), mock=False, external_call=True,
        evidence={'transport_flag_simulation_only': True, 'actual_provider_calls_in_test': 0})
    result = await stack.repository.complete(sync.sync_id, collection=collection,
        features=VideoFeatureMetadata(project_id=sync.project_id, publication_id=sync.publication_id),
        assessment=assess_winner(collection.metrics, video_duration_seconds=None, production_cost_vnd=None),
        insights=[], expected_attempt=claimed.attempt_count)
    assert result.external_call and not result.mock and calls == []
    snapshot = (await stack.repository.list_snapshots(sync.project_id))[0]
    assert snapshot.external_call and not snapshot.mock and snapshot.evidence['transport_flag_simulation_only']
    event = next(event for event in await stack.repository.list_events(sync.project_id) if event.event_type == 'video.analytics.updated')
    assert event.payload['external_call'] is True


@pytest.mark.asyncio
async def test_feature_capture_uses_published_render_after_later_canonical_edit(runtime_stack):
    stack, _, _, _, _, _ = runtime_stack
    original = await stack.production.repository.get_render_context(stack.publication.final_render_id)
    async with stack.repository.session_factory() as session:
        async with session.begin():
            timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == stack.publication.project_id))
            edited = {**original[3], 'duration_seconds': original[3]['duration_seconds'] + 10}
            session.add(TimelineVersionORM(timeline_version_id='tlv_explicit_later_edit', timeline_id=timeline.timeline_id,
                project_id=timeline.project_id, version=2, snapshot_json=edited, mutation_json={'fixture_only': True}, actor_ref='explicit-fixture'))
            timeline.current_version = 2; timeline.current_version_id = 'tlv_explicit_later_edit'
    sync = await reserve(stack); await stack.processor.process(sync.sync_id)
    report = await stack.repository.report(sync.project_id)
    assert report.video_features.duration_seconds == original[3]['duration_seconds']
    assert report.video_features.evidence['timeline_version_id'] == original[0].timeline_version_id
    assert report.video_features.evidence['feature_edit_source'] == 'published_render_context'
    assert report.video_features.publishing_time is None and not report.video_features.evidence['exact_publishing_time_available']
