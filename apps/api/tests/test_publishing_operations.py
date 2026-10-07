"""Real existing-table transactions; project/identity/media/provider inputs are fixtures."""
import asyncio
from dataclasses import replace
from decimal import Decimal
import json

import pytest
from sqlalchemy import select

from app.db import CostRecordORM, ProviderRegistryORM, ProviderUsageORM
from app.publishing_operations import PublishingOperationError, PublishingOperationMeter, amount
from app.publishing_db import PublicationORM
from test_publishing_dispatch import fixture_stack


async def meter_for(fixture):
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            session.add(ProviderRegistryORM(provider_id='pvd_explicit_meter_fixture', workspace_id=fixture['workspace'],
                provider_key=fixture['publication'].provider_key, display_name='EXPLICIT FIXTURE; NOT LIVE PROVIDER',
                capability='publishing', adapter='explicit.fixture', routing_mode='disabled', status='fixture',
                enabled=False, supports_dry_run=True, config_ref=None, metadata_json={'fixture_only': True}))
    return PublishingOperationMeter(fixture['stack'].repository.session_factory, clock=lambda: fixture['clock'][0])


@pytest.mark.parametrize('value', [True, 1, 1.2, '1', Decimal('-1'), Decimal('NaN'), Decimal('Infinity'), Decimal('1.00001'), Decimal('1e30')])
def test_money_is_exact_finite_nonnegative_vnd_precision(value):
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_AMOUNT_INVALID'):
        amount(value)


@pytest.mark.asyncio
async def test_request_and_unknown_cost_are_committed_before_admission_and_replay_cannot_send_again(fixture_stack):
    fixture = fixture_stack; meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    value = await meter.admit(fixture['workspace'], pub, 'account_lookup', request_identity='a' * 32, mock=True)
    assert value.allowed and value.mock
    async with fixture['stack'].repository.session_factory() as session:
        usage = await session.get(ProviderUsageORM, value.usage_id); cost = await session.get(CostRecordORM, value.cost_id)
        assert usage.status == 'dispatch_intent' and usage.completed_at is None and usage.unit_name == 'request_intent'
        assert usage.metadata_json['provider_quota_units'] is None
        assert usage.workspace_id == fixture['workspace'] and usage.project_id == fixture['publication'].project_id
        assert usage.job_id is None and cost.job_id is None and cost.actual_cost is None and cost.estimated_cost is None
        assert cost.provenance['estimate_source'] == 'unknown' and not cost.approved
        assert 'a' * 32 not in json.dumps(usage.metadata_json)
    with pytest.raises(PublishingOperationError, match='PUBLISH_OPERATION_ALREADY_RESERVED'):
        await meter.admit(fixture['workspace'], pub, 'account_lookup', request_identity='a' * 32, mock=True)
    completed = await meter.finish(fixture['workspace'], pub, value, outcome='confirmed')
    assert completed['actual_cost'] is None and completed['status'] == 'confirmed'
    assert await meter.finish(fixture['workspace'], pub, value, outcome='confirmed') == completed


@pytest.mark.asyncio
async def test_unknown_cost_under_cap_records_approval_need_without_admitting_wire(fixture_stack):
    fixture = fixture_stack; meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    value = await meter.admit(fixture['workspace'], pub, 'initialize', request_identity='b' * 32, max_ai_cost=Decimal('100'), mock=True)
    assert not value.allowed
    async with fixture['stack'].repository.session_factory() as session:
        cost = await session.get(CostRecordORM, value.cost_id); usage = await session.get(ProviderUsageORM, value.usage_id)
        assert cost.needs_approval and cost.actual_cost is None and cost.estimated_cost is None
        assert usage.status == 'needs_approval' and usage.completed_at is None
    with pytest.raises(PublishingOperationError, match='PUBLISH_OPERATION_OUTCOME_CONFLICT'):
        await meter.finish(fixture['workspace'], pub, value, outcome='confirmed')


@pytest.mark.asyncio
async def test_two_concurrent_publication_reservations_cannot_overspend_configured_cap(fixture_stack):
    fixture = fixture_stack; meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    values = await asyncio.gather(*(meter.admit(fixture['workspace'], pub, 'chunk', request_identity=letter * 32,
        estimated_cost=Decimal('4'), max_ai_cost=Decimal('5'), mock=True) for letter in ('c', 'd')))
    assert sum(value.allowed for value in values) == 1
    winner = next(value for value in values if value.allowed)
    await meter.finish(fixture['workspace'], pub, winner, outcome='not_sent')
    # Proven unsent requests release this meter's reservation; their estimates
    # remain in history rather than being converted into fabricated actual zero.
    replacement = await meter.admit(fixture['workspace'], pub, 'chunk', request_identity='e' * 32,
        estimated_cost=Decimal('4'), max_ai_cost=Decimal('5'), mock=True)
    assert replacement.allowed
    async with fixture['stack'].repository.session_factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.cost_id.in_(
            [value.cost_id for value in values] + [replacement.cost_id])))).all()
        assert all(cost.actual_cost is None for cost in costs) and len(costs) == 3


@pytest.mark.asyncio
async def test_ambiguous_prior_cost_blocks_budget_and_outcome_history_is_not_overwritten(fixture_stack):
    fixture = fixture_stack; meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    first = await meter.admit(fixture['workspace'], pub, 'initialize', request_identity='f' * 32, mock=True)
    await meter.finish(fixture['workspace'], pub, first, outcome='outcome_unknown')
    next_request = await meter.admit(fixture['workspace'], pub, 'reconcile', request_identity='0' * 32,
        estimated_cost=Decimal('1'), max_ai_cost=Decimal('100'), mock=True)
    assert not next_request.allowed
    with pytest.raises(PublishingOperationError, match='PUBLISH_OPERATION_OUTCOME_CONFLICT'):
        await meter.finish(fixture['workspace'], pub, first, outcome='confirmed')


@pytest.mark.asyncio
async def test_foreign_scope_unregistered_provider_and_forged_outcome_are_refused(fixture_stack):
    fixture = fixture_stack; factory = fixture['stack'].repository.session_factory
    bare = PublishingOperationMeter(factory)
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_SCOPE_NOT_FOUND'):
        await bare.admit('wsp_foreign', fixture['publication'].publication_id, 'initialize', request_identity='a' * 32)
    # The fixture stack has only a scoped explicit provider after meter_for().
    meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_JOB_SCOPE_INVALID'):
        await meter.admit(fixture['workspace'], pub, 'initialize', request_identity='b' * 32, job_id='job_foreign_fixture')
    value = await meter.admit(fixture['workspace'], pub, 'initialize', request_identity='c' * 32, mock=True)
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_SCOPE_NOT_FOUND'):
        await meter.finish(fixture['workspace'], pub, replace(value, mock=False), outcome='confirmed')
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_SCOPE_NOT_FOUND'):
        await meter.finish('wsp_foreign', pub, value, outcome='confirmed')
    async with factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, pub)
            parent.provider_key = 'explicit-unregistered-provider'
    with pytest.raises(PublishingOperationError, match='PUBLISH_COST_PROVIDER_NOT_REGISTERED'):
        await meter.admit(fixture['workspace'], pub, 'initialize', request_identity='d' * 32)


@pytest.mark.asyncio
async def test_concurrent_same_request_key_retains_exactly_one_cost_intent(fixture_stack):
    fixture = fixture_stack; meter = await meter_for(fixture); pub = fixture['publication'].publication_id
    values = await asyncio.gather(*(meter.admit(fixture['workspace'], pub, 'initialize', request_identity='a' * 32, mock=True)
        for _ in range(2)), return_exceptions=True)
    assert len([value for value in values if not isinstance(value, Exception)]) == 1
    refused = [value for value in values if isinstance(value, Exception)]
    assert len(refused) == 1 and isinstance(refused[0], PublishingOperationError)
    assert refused[0].code == 'PUBLISH_OPERATION_ALREADY_RESERVED'
