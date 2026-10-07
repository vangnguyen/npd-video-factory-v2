"""Owned SQLite scheduling; every account/approval/provider input is a fixture."""
import asyncio
from datetime import timedelta
import json

import httpx
import pytest

from app.publishing_dispatch import DispatchError
from app.publishing_scheduler import PublishingScheduler, PublishingWorkQueue
from app.publishing_worker import YouTubePublishingWorker
from test_publishing_dispatch import fixture_stack
from test_publishing_worker import configured_worker


async def scheduler_for(fixture, tmp_path, **receiver_options):
    worker, options, receiver, grant, work, policy = await configured_worker(fixture, tmp_path, **receiver_options)
    original = receiver.handle
    async def handler(request):
        if request.url.path.endswith('/videos') and request.method == 'GET':
            receiver.requests.append('GET')
            return httpx.Response(200, json={'items': [{'id': 'AbcD_12-345', 'status': {'privacyStatus': 'private'},
                'processingDetails': {'processingStatus': 'succeeded'}}]})
        return await original(request)
    worker.client.transport = httpx.MockTransport(handler)
    queue = PublishingWorkQueue(worker.journal)
    factory = lambda guard: YouTubePublishingWorker(**options, admission_guard=guard)
    return queue, PublishingScheduler(queue, factory), receiver, grant, policy, options


@pytest.mark.asyncio
async def test_queue_is_exact_idempotent_scoped_and_does_not_expose_lease(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, _runner, receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    workspace, pub = fixture['workspace'], fixture['publication'].publication_id
    first = await queue.enqueue(workspace, pub); assert await queue.enqueue(workspace, pub) == first
    assert (await queue.due(workspace)) == [first] and await queue.due('foreign') == []
    for call in (queue.enqueue('foreign', pub), queue.get('foreign', first['work_id'])):
        with pytest.raises(DispatchError): await call
    assert not receiver.requests and 'lease' not in json.dumps(first)


@pytest.mark.asyncio
async def test_competing_claims_have_one_owner_and_no_duplicate_worker_admission(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, _runner, _receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    values = await asyncio.gather(*[queue.claim(fixture['workspace'], state['work_id'], state['version']) for _ in range(2)], return_exceptions=True)
    assert sum(isinstance(value, DispatchError) for value in values) == 1
    winner = next(value for value in values if not isinstance(value, Exception))
    assert await queue.owned(winner) == 0 and winner.owner not in repr(winner)
    assert await queue.due(fixture['workspace']) == []


@pytest.mark.asyncio
async def test_expired_lease_reclaims_and_fences_old_guard_and_finish(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, _runner, _receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    old = await queue.claim(fixture['workspace'], state['work_id'], state['version'])
    fixture['clock'][0] += timedelta(seconds=601)
    due = (await queue.due(fixture['workspace']))[0]
    await fixture['stack'].engine.dispose()
    fresh = await queue.claim(fixture['workspace'], due['work_id'], due['version'])
    assert await queue.owned(fresh) == 0
    for call in (queue.owned(old), queue.finish(old, status='completed')):
        with pytest.raises(DispatchError, match='OWNERSHIP_LOST'): await call


@pytest.mark.asyncio
async def test_scheduler_runs_one_init_chunks_and_mock_processing_across_restart(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    for _ in range(5):
        await fixture['stack'].engine.dispose()
        state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
        fixture['clock'][0] += timedelta(seconds=2)
    assert state['status'] == 'completed' and state['run_count'] == 5 and state['failures'] == 0
    assert receiver.initializations == 1 and bytes(receiver.received) == receiver.raw
    assert await queue.due(fixture['workspace']) == []


@pytest.mark.asyncio
async def test_uncertain_init_never_requeues_post_even_after_restart(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path, lose_init=True)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'review_required' and receiver.initializations == 1
    await fixture['stack'].engine.dispose(); fixture['clock'][0] += timedelta(hours=1)
    assert await queue.due(fixture['workspace']) == []
    with pytest.raises(DispatchError, match='NOT_DUE_OR_STALE'):
        await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert receiver.initializations == 1


@pytest.mark.asyncio
async def test_rate_limit_respects_bounded_retry_after_then_failure_cap(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, options = await scheduler_for(fixture, tmp_path)
    attempts = []
    def limited(request):
        assert request.method == 'GET'; attempts.append(True)
        return httpx.Response(429, headers={'retry-after': '120'})
    options['client'].transport = httpx.MockTransport(limited); runner.max_failures = 2
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    first = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert first['status'] == 'waiting' and first['failures'] == 1
    assert first['next_run_at'] == (fixture['clock'][0] + timedelta(seconds=120)).isoformat()
    assert await queue.due(fixture['workspace']) == []
    fixture['clock'][0] += timedelta(seconds=120)
    state = await runner.run_one(fixture['workspace'], first['work_id'], first['version'])
    assert state['status'] == 'review_required' and state['failures'] == 2 and len(attempts) == 2
    assert receiver.initializations == 0


@pytest.mark.asyncio
async def test_lost_known_final_waits_then_queries_without_another_initialization(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path, lose_final=True)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    for _ in range(4):
        state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
        fixture['clock'][0] += timedelta(seconds=2)
    assert state['status'] == 'waiting' and state['failures'] == 1 and receiver.initializations == 1
    fixture['clock'][0] += timedelta(seconds=30)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'waiting' and state['failures'] == 0
    assert (await queue.journal.get(fixture['workspace'], fixture['publication'].publication_id))['phase'] == 'uploaded'
    assert receiver.initializations == 1


@pytest.mark.asyncio
async def test_missing_policy_and_revoked_consent_stay_review_without_requests(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    await queue.journal.revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'review_required' and not receiver.requests


def test_queue_configuration_and_public_limits_are_strict():
    for value in (True, 0, 180, 901):
        with pytest.raises(DispatchError, match='LEASE_INVALID'): PublishingWorkQueue(None, lease_seconds=value)
    with pytest.raises(DispatchError, match='CONFIGURATION_INVALID'): PublishingWorkQueue(None)


@pytest.mark.asyncio
async def test_old_worker_losing_ownership_during_qc_cannot_initialize(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, _runner, receiver, _grant, _policy, options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    old = await queue.claim(fixture['workspace'], state['work_id'], state['version'])
    async def guard(): await queue.owned(old)
    worker = YouTubePublishingWorker(**options, admission_guard=guard)
    qc = worker.guard.qc.inspect
    async def expire_and_reclaim(*args, **kwargs):
        report = await qc(*args, **kwargs)
        fixture['clock'][0] += timedelta(seconds=601)
        due = (await queue.due(fixture['workspace']))[0]
        await queue.claim(fixture['workspace'], due['work_id'], due['version'])
        return report
    worker.guard.qc.inspect = expire_and_reclaim
    with pytest.raises(DispatchError, match='OWNERSHIP_LOST'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    assert receiver.requests == ['GET'] and receiver.initializations == 0
    assert (await queue.journal.get(fixture['workspace'], fixture['publication'].publication_id))['phase'] == 'init_ready'


@pytest.mark.asyncio
async def test_guard_failure_after_cost_reservation_is_proven_unsent(fixture_stack, tmp_path):
    from sqlalchemy import select
    from app.db import ProviderUsageORM
    fixture = fixture_stack; _queue, _runner, receiver, _grant, _policy, options = await scheduler_for(fixture, tmp_path)
    calls = []
    async def guard():
        calls.append(True)
        if len(calls) == 2: raise DispatchError('PUBLISH_WORK_OWNERSHIP_LOST')
    worker = YouTubePublishingWorker(**options, admission_guard=guard)
    with pytest.raises(DispatchError, match='OWNERSHIP_LOST'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    async with worker.journal.session_factory() as session:
        usages = (await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.capability == 'publishing'))).all()
    assert len(usages) == 1 and usages[0].status == 'not_sent' and not receiver.requests


@pytest.mark.asyncio
async def test_partial_chunk_ack_honors_provider_delay_before_next_range(fixture_stack, tmp_path):
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, options = await scheduler_for(fixture, tmp_path)
    initial_handler = options['client'].transport.handler
    async def delayed(request):
        value = await initial_handler(request)
        if value.status_code == 308: value.headers['retry-after'] = '10'
        return value
    options['client'].transport = httpx.MockTransport(delayed)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    fixture['clock'][0] += timedelta(seconds=2)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'waiting' and state['next_run_at'] == (fixture['clock'][0] + timedelta(seconds=10)).isoformat()
    assert receiver.initializations == 1


@pytest.mark.asyncio
async def test_known_inflight_chunk_waits_for_dispatch_lease_before_status_query(fixture_stack, tmp_path):
    from app.youtube_upload import UNIT
    fixture = fixture_stack; queue, runner, receiver, _grant, _policy, _options = await scheduler_for(fixture, tmp_path)
    state = await queue.enqueue(fixture['workspace'], fixture['publication'].publication_id)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    dispatch = await queue.journal.get(fixture['workspace'], fixture['publication'].publication_id)
    await queue.journal.intent(fixture['workspace'], dispatch['publication_id'], dispatch['version'], 'chunk', offset=0, length=UNIT)
    fixture['clock'][0] += timedelta(seconds=2)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'waiting' and state['failure_code'] == 'PUBLISHING_RECONCILIATION_LEASE_ACTIVE'
    assert state['next_run_at'] == (fixture['clock'][0] + timedelta(seconds=178)).isoformat()
    assert receiver.requests == ['GET', 'POST']
    fixture['clock'][0] += timedelta(seconds=178)
    state = await runner.run_one(fixture['workspace'], state['work_id'], state['version'])
    assert state['status'] == 'waiting' and state['failures'] == 0
    assert receiver.requests == ['GET', 'POST', 'GET', 'PUT'] and receiver.initializations == 1
