"""Scheduling revocation, bounded due claims and backoff; no external transport."""
import asyncio
from datetime import datetime, timedelta, timezone
from dataclasses import replace

import httpx
import pytest
from sqlalchemy import select

from app.analytics_db import AnalyticsSyncORM
from app.analytics_models import AnalyticsSyncRequest
from app.analytics_official import AnalyticsHTTPClient
from app.analytics_providers import AnalyticsRateLimited
from app.analytics_repository import AnalyticsRepository, _utc_input
from app.analytics_service import AnalyticsBoundaryError
from app.db import utc_now
from test_analytics_runtime import runtime_stack


@pytest.mark.asyncio
@pytest.mark.parametrize('trigger', ['initial', 'manual_refresh', 'scheduled_refresh'])
async def test_explicit_schedule_cannot_bypass_gate_and_revocation_stops_queued_job(runtime_stack, trigger):
    stack, _, _, calls, _, _ = runtime_stack
    payload = AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='fixture',
        trigger=trigger, fixture_profile='normal', scheduled_for=utc_now() - timedelta(seconds=1))
    with pytest.raises(AnalyticsBoundaryError, match='Scheduled analytics refresh is disabled'):
        await stack.service.create_sync(project_id=stack.publication.project_id, payload=payload,
            idempotency_key='schedule-gate-disabled-' + trigger)
    assert await stack.repository.list_syncs(stack.publication.project_id) == []
    stack.settings.analytics_scheduled_refresh_enabled = True
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id, payload=payload,
        idempotency_key='schedule-gate-enabled-' + trigger)
    stack.settings.analytics_scheduled_refresh_enabled = False
    result = await stack.processor.process(sync.sync_id)
    assert result.status == 'not_configured' and result.failure_code == 'ANALYTICS_SCHEDULED_REFRESH_DISABLED'
    assert calls == [] and await stack.repository.list_snapshots(sync.project_id) == []


@pytest.mark.asyncio
async def test_schedule_switch_is_rechecked_between_official_reads(runtime_stack):
    stack, runtime, current, _, _, _ = runtime_stack
    stack.settings.analytics_scheduled_refresh_enabled = True
    calls = []
    def receive(request):
        calls.append(request.url.path); stack.settings.analytics_scheduled_refresh_enabled = False
        return httpx.Response(200, json={'items': [{'id': current[0].target_account_id}]})
    runtime.clients['youtube'] = AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))
    payload = AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='official',
        trigger='scheduled_refresh', scheduled_for=utc_now() - timedelta(seconds=1),
        query={'start_date': '2026-10-01', 'end_date': '2026-10-06'})
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id, payload=payload,
        idempotency_key='official-read-schedule-revocation-fixture')
    result = await stack.processor.process(sync.sync_id)
    assert result.status == 'not_configured' and result.failure_code == 'ANALYTICS_SCHEDULED_REFRESH_DISABLED'
    assert len(calls) == 1 and calls[0].endswith('/channels')
    assert result.mock is True and result.external_call is False
    assert await stack.repository.list_snapshots(sync.project_id) == []


@pytest.mark.asyncio
async def test_provider_retry_after_is_not_shortened_to_local_backoff_cap(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    async def limited(_context): raise AnalyticsRateLimited(3600)
    stack.providers.fixture.collect = limited
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='retry-after-hour-explicit-fixture')
    before = utc_now(); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'retry_scheduled'
    assert result.next_retry_at >= before + timedelta(seconds=3600)
    assert result.next_retry_at > before + timedelta(seconds=stack.settings.analytics_retry_max_seconds)
    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_due_ticks_are_bounded_and_claim_each_job_once(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    stack.settings.analytics_scheduled_refresh_enabled = True
    due = utc_now() + timedelta(minutes=1)
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='fixture',
            trigger='scheduled_refresh', fixture_profile='normal', scheduled_for=due),
        idempotency_key='due-claim-seed-explicit-fixture')
    async with stack.repository.session_factory() as session:
        row = await session.get(AnalyticsSyncORM, sync.sync_id)
        values = {column.name: getattr(row, column.name) for column in row.__table__.columns}
        for index in range(119):
            session.add(AnalyticsSyncORM(**{**values, 'sync_id': f'ans_due_explicit_fixture_{index}',
                'idempotency_key_hash': f'{index:064x}'}))
        await session.commit()
    assert await stack.repository.activate_due_sync_ids() == []
    batches = await asyncio.gather(stack.repository.activate_due_sync_ids(at=due + timedelta(seconds=1)),
        stack.repository.activate_due_sync_ids(at=due + timedelta(seconds=1)))
    assert all(len(batch) <= 100 for batch in batches)
    claimed = [item for batch in batches for item in batch]
    assert len(claimed) == len(set(claimed)) and 100 <= len(claimed) <= 120
    # Concurrent SQLite readers may choose the same first page. A loser does
    # not claim it again; the next scheduler tick picks the remaining page.
    remaining = await stack.repository.activate_due_sync_ids(at=due + timedelta(seconds=1))
    assert len(remaining) <= 100 and not set(remaining) & set(claimed)
    assert len(claimed) + len(remaining) == 120
    assert await stack.repository.activate_due_sync_ids(at=due + timedelta(seconds=1)) == []
    assert len(await stack.repository.list_events(sync.project_id)) == 121  # Original reservation plus one event per due claim.
    assert len(await stack.repository.queued_sync_ids()) == 100
    assert calls == []


@pytest.mark.parametrize('value', [0, -1, True, 1.5, float('inf'), '30', 86401])
def test_rate_limit_delay_rejects_invalid_provider_values(value):
    with pytest.raises(ValueError, match='ANALYTICS_RETRY_AFTER_INVALID'): AnalyticsRateLimited(value)


def test_fixture_provider_state_reflects_disabled_runtime_switch():
    from app.analytics_providers import AnalyticsProviderRegistry
    from test_analytics_learning import analytics_settings
    settings = analytics_settings(analytics_fixture_enabled=False)
    registry = AnalyticsProviderRegistry(settings)
    assert all(not state.supports_sync and state.adapter_state == 'not_configured' for state in registry.states() if state.mode == 'fixture')
    settings.analytics_fixture_enabled = True
    assert all(state.supports_sync for state in registry.states() if state.mode == 'fixture')


@pytest.mark.asyncio
async def test_same_key_retry_reenqueues_a_sync_after_queue_admission_failure(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    original = stack.queue.rpush
    async def unavailable(*_args): raise ConnectionError('EXPLICIT QUEUE FAILURE')
    stack.queue.rpush = unavailable
    payload = AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='fixture', fixture_profile='normal')
    with pytest.raises(ConnectionError):
        await stack.service.create_sync(project_id=stack.publication.project_id, payload=payload, idempotency_key='queue-outage-explicit-fixture')
    pending = await stack.repository.queued_sync_ids(); assert len(pending) == 1
    stack.queue.rpush = original
    replay, repeated = await stack.service.create_sync(project_id=stack.publication.project_id, payload=payload, idempotency_key='queue-outage-explicit-fixture')
    assert repeated is True and replay.sync_id == pending[0] and stack.queue.values == pending
    assert len(await stack.repository.list_syncs(replay.project_id)) == 1 and calls == []


@pytest.mark.asyncio
async def test_offset_schedule_retry_and_observation_keep_exact_instant_after_restart(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    stack.settings.analytics_scheduled_refresh_enabled = True
    expected = utc_now() + timedelta(hours=1); local = expected.astimezone(timezone(timedelta(hours=7)))
    scheduled, _ = await stack.service.create_sync(project_id=stack.publication.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='fixture',
            fixture_profile='normal', trigger='scheduled_refresh', scheduled_for=local),
        idempotency_key='offset-schedule-explicit-fixture')
    restarted = AnalyticsRepository(stack.repository.session_factory)
    saved = await restarted.get_sync_by_id(scheduled.sync_id)
    assert saved.scheduled_for == expected and saved.scheduled_for.utcoffset() == timedelta(0)
    assert (await restarted.claim(saved.sync_id)).status == 'scheduled'
    assert await restarted.activate_due_sync_ids() == []
    manual, _ = await stack.service.create_sync(project_id=saved.project_id,
        payload=AnalyticsSyncRequest(publication_id=saved.publication_id, provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='offset-retry-explicit-fixture')
    owned = await restarted.claim(manual.sync_id)
    retry = await restarted.schedule_retry(manual.sync_id, next_retry_at=local, code='FIXTURE', reason='FIXTURE', expected_attempt=owned.attempt_count)
    assert retry.next_retry_at == expected and retry.next_retry_at.utcoffset() == timedelta(0)
    assert await restarted.activate_due_sync_ids() == []
    collected = utc_now(); original = stack.providers.fixture.collect
    async def offset_collection(context):
        return replace(await original(context), collected_at=collected.astimezone(timezone(timedelta(hours=7))))
    stack.providers.fixture.collect = offset_collection
    fresh, _ = await stack.service.create_sync(project_id=saved.project_id,
        payload=AnalyticsSyncRequest(publication_id=saved.publication_id, provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='offset-observation-explicit-fixture')
    await stack.processor.process(fresh.sync_id)
    observation = (await restarted.list_snapshots(saved.project_id))[0]
    assert observation.collected_at == collected and observation.collected_at.utcoffset() == timedelta(0)
    assert observation.model_dump(mode='json')['collected_at'].endswith('Z') and calls == []


def test_naive_collection_timestamp_is_rejected_instead_of_assuming_provider_timezone():
    with pytest.raises(ValueError, match='ANALYTICS_TIMESTAMP_TIMEZONE_REQUIRED'): _utc_input(datetime(2026, 10, 7))
