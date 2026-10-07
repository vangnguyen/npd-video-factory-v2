"""Owned SQLite plan persistence; no scheduler or provider invocation."""
import asyncio
from datetime import timedelta

import pytest
import httpx
from sqlalchemy import select

from app.analytics_refresh_models import AnalyticsRefreshCreate
from app.analytics_refresh_repository import AnalyticsRefreshRepository, AnalyticsRefreshError
from app.db import utc_now
from app.analytics_refresh_db import AnalyticsRefreshOccurrenceORM
from app.analytics_official import AnalyticsHTTPClient
from app.publishing_credentials import target_digest
from test_analytics_runtime import runtime_stack


async def create_plan(stack, *, key='refresh-owned-sqlite-fixture', config=None):
    repo = AnalyticsRefreshRepository(stack.repository.session_factory)
    config = config or AnalyticsRefreshCreate(publication_id=stack.publication.publication_id, first_run_at=utc_now() + timedelta(hours=1))
    result = await repo.create(workspace=stack.publication.workspace_id, project=stack.publication.project_id,
        config=config, provider_key=stack.providers.fixture.provider_key, target_sha256=None,
        publication_fingerprint=stack.publication.request_fingerprint, actor='usr:EXPLICIT_PLAN_OWNER_FIXTURE', key=key)
    return repo, result, config


@pytest.mark.asyncio
async def test_plan_identity_config_audit_and_idempotency_survive_repository_restart(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    repo, (plan, replay), config = await create_plan(stack)
    assert replay is False and not plan.enabled and plan.run_count == 0 and plan.revision == 1
    restarted = AnalyticsRefreshRepository(stack.repository.session_factory)
    assert (await restarted.get(plan.project_id, plan.plan_id)).model_dump(mode='json') == plan.model_dump(mode='json')
    _, (same, replay), _ = await create_plan(stack, config=config)
    assert replay and same.plan_id == plan.plan_id
    assert await repo.get('prj_foreign', plan.plan_id) is None
    assert await repo.list('prj_foreign') == []
    assert len(await repo.history(plan.project_id, plan.plan_id)) == 1
    with pytest.raises(AnalyticsRefreshError, match='IDEMPOTENCY_CONFLICT'):
        await create_plan(stack, config=config.model_copy(update={'interval_hours': 2}))
    assert calls == []


@pytest.mark.asyncio
async def test_concurrent_revision_change_has_one_winner_without_replacing_config(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    repo, (plan, _), _ = await create_plan(stack)
    outcomes = await asyncio.gather(repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=True, actor='usr:fixture-owner-a'),
        repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=False, actor='usr:fixture-owner-b'), return_exceptions=True)
    assert sum(isinstance(result, AnalyticsRefreshError) for result in outcomes) == 1
    saved = await repo.get(plan.project_id, plan.plan_id)
    assert saved.revision == 2 and saved.config == plan.config and saved.next_due_at == plan.next_due_at
    assert len(await repo.history(plan.project_id, plan.plan_id)) == 2
    disabled = await repo.change_state(plan.project_id, plan.plan_id, revision=2, enabled=False, actor='usr:fixture-owner-final')
    assert disabled.revision == 3 and not disabled.enabled
    assert len(await repo.history(plan.project_id, plan.plan_id)) == 3 and calls == []


@pytest.mark.asyncio
async def test_concurrent_same_key_creates_one_plan_and_one_audit(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    config = AnalyticsRefreshCreate(publication_id=stack.publication.publication_id,
        first_run_at=utc_now() + timedelta(hours=1))
    results = await asyncio.gather(create_plan(stack, config=config), create_plan(stack, config=config))
    assert {result[1][0].plan_id for result in results} == {results[0][1][0].plan_id}
    assert sorted(result[1][1] for result in results) == [False, True]
    repo, (plan, _), _ = results[0]
    assert len(await repo.list(plan.project_id)) == len(await repo.history(plan.project_id, plan.plan_id)) == 1
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('rate_limited', [False, True])
async def test_revocation_during_provider_error_terminates_without_retry(runtime_stack, rate_limited):
    stack, _, _, calls, _, _ = runtime_stack
    from app.analytics_providers import AnalyticsRateLimited
    now = utc_now(); stack.settings.analytics_scheduled_refresh_enabled = True
    config = AnalyticsRefreshCreate(publication_id=stack.publication.publication_id, first_run_at=now,
        enabled=True, acknowledged_read_only=True)
    repo, (plan, _), _ = await create_plan(stack, config=config)
    ids = await repo.create_due(settings=stack.settings, provider_ready=lambda *_: True, at=now)
    async def collect(context):
        await repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=False, actor='usr:fixture-owner')
        if rate_limited: raise AnalyticsRateLimited(60, 'fixture rate limit')
        raise RuntimeError('fixture provider error')
    stack.providers.fixture.collect = collect
    result = await stack.processor.process(ids[0])
    assert result.status == 'not_configured' and result.failure_code == 'ANALYTICS_REFRESH_PLAN_DISABLED'
    assert result.next_retry_at is None and calls == []
    assert await stack.repository.list_snapshots(plan.project_id) == []


@pytest.mark.asyncio
async def test_due_occurrence_and_sync_are_atomic_bounded_and_do_not_catch_up_in_a_burst(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    now = utc_now()
    config = AnalyticsRefreshCreate(publication_id=stack.publication.publication_id, first_run_at=now - timedelta(hours=10),
        interval_hours=1, max_runs=2, enabled=True, acknowledged_read_only=True)
    repo, (plan, _), _ = await create_plan(stack, config=config)
    ready = lambda *_: True  # Fixture configuration only; no provider call.
    assert await repo.create_due(settings=stack.settings, provider_ready=ready, at=now) == []
    stack.settings.analytics_scheduled_refresh_enabled = True
    batches = await asyncio.gather(repo.create_due(settings=stack.settings, provider_ready=ready, at=now),
        repo.create_due(settings=stack.settings, provider_ready=ready, at=now))
    identifiers = [identifier for batch in batches for identifier in batch]
    assert len(identifiers) == 1
    saved = await repo.get(plan.project_id, plan.plan_id)
    assert saved.run_count == 1 and saved.next_due_at == now + timedelta(hours=1)
    async with stack.repository.session_factory() as session:
        occurrence = await session.scalar(select(AnalyticsRefreshOccurrenceORM))
        assert occurrence.sync_id == identifiers[0] and occurrence.ordinal == 1 and occurrence.skipped_slots == 10
    assert (await stack.repository.get_sync_by_id(identifiers[0])).trigger == 'scheduled_refresh'
    assert await repo.create_due(settings=stack.settings, provider_ready=ready, at=now) == []
    later = await repo.create_due(settings=stack.settings, provider_ready=ready, at=now + timedelta(hours=2))
    assert len(later) == 1 and (await repo.get(plan.project_id, plan.plan_id)).run_count == 2
    assert await repo.create_due(settings=stack.settings, provider_ready=ready, at=now + timedelta(hours=10)) == []
    assert calls == [] and len(await stack.repository.list_syncs(plan.project_id)) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize('during_collection', [False, True])
async def test_revoked_plan_stops_fixture_collection_or_discards_result_without_revival(runtime_stack, during_collection):
    stack, _, _, calls, _, _ = runtime_stack
    now = utc_now(); stack.settings.analytics_scheduled_refresh_enabled = True
    config = AnalyticsRefreshCreate(publication_id=stack.publication.publication_id, first_run_at=now,
        interval_hours=1, max_runs=2, enabled=True, acknowledged_read_only=True)
    repo, (plan, _), _ = await create_plan(stack, config=config)
    identifiers = await repo.create_due(settings=stack.settings, provider_ready=lambda *_: True, at=now)
    invoked = []; original = stack.providers.fixture.collect
    async def collect(context):
        invoked.append(context.sync_id)
        if during_collection: await repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=False, actor='usr:fixture-owner')
        return await original(context)
    stack.providers.fixture.collect = collect
    if not during_collection:
        await repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=False, actor='usr:fixture-owner')
    result = await stack.processor.process(identifiers[0])
    assert result.status == 'not_configured' and result.failure_code == 'ANALYTICS_REFRESH_PLAN_DISABLED'
    assert invoked == (identifiers if during_collection else [])
    assert await stack.repository.list_snapshots(plan.project_id) == []
    assert await stack.repository.list_insights(plan.project_id) == []
    await repo.change_state(plan.project_id, plan.plan_id, revision=2, enabled=True, actor='usr:fixture-owner')
    same = await stack.processor.process(identifiers[0]); assert same.status == 'not_configured'
    assert (await repo.get(plan.project_id, plan.plan_id)).revision == 3 and calls == []


@pytest.mark.asyncio
async def test_official_plan_rechecks_revocation_between_wire_reads_and_keeps_cost_intent(runtime_stack):
    stack, runtime, current, _, _, _ = runtime_stack
    now = utc_now(); stack.settings.analytics_scheduled_refresh_enabled = True
    config = AnalyticsRefreshCreate(publication_id=stack.publication.publication_id, first_run_at=now,
        provider_mode='official', query_policy='rolling_complete_days', lookback_days=7, enabled=True, acknowledged_read_only=True)
    repo = AnalyticsRefreshRepository(stack.repository.session_factory)
    plan, _ = await repo.create(workspace=stack.publication.workspace_id, project=stack.publication.project_id, config=config,
        provider_key='youtube-analytics-api', target_sha256=target_digest(current[0]),
        publication_fingerprint=stack.publication.request_fingerprint, actor='usr:EXPLICIT_PLAN_OWNER_FIXTURE', key='official-plan-read-revocation-fixture')
    calls = []
    async def receive(request):
        calls.append(request.url.path)
        await repo.change_state(plan.project_id, plan.plan_id, revision=1, enabled=False, actor='usr:EXPLICIT_PLAN_OWNER_FIXTURE')
        return httpx.Response(200, json={'items': [{'id': current[0].target_account_id}]})
    runtime.clients['youtube'] = AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))
    ids = await repo.create_due(settings=stack.settings, provider_ready=lambda *_: True, at=now)
    result = await stack.processor.process(ids[0])
    assert result.status == 'not_configured' and result.failure_code == 'ANALYTICS_REFRESH_PLAN_DISABLED'
    assert result.mock is True and result.external_call is False and len(calls) == 1
    assert await stack.repository.list_snapshots(plan.project_id) == []
    from app.db import ProviderUsageORM, CostRecordORM
    async with stack.repository.session_factory() as session:
        usage = await session.scalar(select(ProviderUsageORM).where(ProviderUsageORM.capability == 'analytics'))
        cost = await session.scalar(select(CostRecordORM).where(CostRecordORM.provider_usage_id == usage.usage_id))
        assert usage.status == 'confirmed' and cost.actual_cost is None
