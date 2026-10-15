"""Owned SQL/ASGI terminal release; synthetic fixtures, no external execution."""
import asyncio
import copy
from dataclasses import asdict
from decimal import Decimal
import hashlib
import json

import pytest
from sqlalchemy import select, event

from app.db import Base, AssetORM, VideoProjectORM
from app.media_intelligence_db import MediaResolutionJobORM
from app.service_api_repository import ServiceOperationORM, digest
from app.broll_internal_settlement_command import NAMESPACE
from auth_test_support import TEST_HUMAN_TOKEN, TEST_HUMAN_HEADERS
from test_broll_internal_resolution import setup, client_for, url, request
from test_broll_request_recovery import renew
from test_sql_broll_review_main import deny_wire


def settlement_url(env):
    return url(env).replace('internal-resolution-review', 'internal-resolution-settlement')


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def inspected_body(intent):
    raw = encoded(intent)
    return {'intent_json': raw, 'intent_sha256': hashlib.sha256(raw.encode()).hexdigest()}


async def admitted(client, env):
    context = (await client.get(url(env))).json()
    principal = (await client.get('/api/v1/auth/session')).json()
    body = request(env, context)
    response = await client.post(url(env), json=body)
    assert response.status_code == 202, response.text
    result = response.json()
    intent = {'schema_version': 'sql-broll-internal-pending.v1', 'body': body, 'context': context,
        'core_sha256': hashlib.sha256(b'owned local UI binding, not authorization').hexdigest(),
        'principal_sha256': digest(principal), 'credential_sha256': hashlib.sha256(TEST_HUMAN_TOKEN.encode()).hexdigest(),
        'receipt': result['receipt']}
    return intent, result


async def terminal(env, result, status):
    identifier = result['job']['resolution_job_id']
    if status == 'cancelled':
        # A persisted terminal-cancellation fixture; this does not claim a new
        # cancel route or force cancellation in the settlement command.
        async with env['session_factory']() as session:
            job = await session.get(MediaResolutionJobORM, identifier)
            job.status = 'cancelled'
            await session.commit()
    else:
        if status == 'failed':
            env['storage']._path(env['review_asset'].object_key).write_bytes(b'owned corrupted fixture bytes')
        assert (await env['resolver'].process(identifier)).status == status


async def original_rows(env):
    """Every owned SQL table/row except the new append-only namespace."""
    result = {}
    async with env['session_factory']() as session:
        for name, table in Base.metadata.tables.items():
            query = select(table)
            if name == ServiceOperationORM.__tablename__:
                query = query.where(ServiceOperationORM.service_id != NAMESPACE)
            query = query.order_by(*table.primary_key.columns)
            result[name] = [dict(r) for r in (await session.execute(query)).mappings()]
    return copy.deepcopy(result)


async def settlements(env):
    async with env['session_factory']() as session:
        return (await session.scalars(select(ServiceOperationORM).where(ServiceOperationORM.service_id == NAMESPACE))).all()


async def observe(client, env, intent):
    response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
    assert response.status_code == 200, response.text
    assert response.headers['cache-control'] == 'no-store'
    return response.json()


async def release(client, env, intent, observation):
    response = await client.post(settlement_url(env) + '/settle', json={**inspected_body(intent),
        'observation_sha256': observation['observation_sha256'], 'acknowledged': True})
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['failed', 'cancelled', 'succeeded'])
async def test_actual_main_terminal_inspect_zero_writes_settle_one_append_originals_preserved(tmp_path, deny_wire, status):
    env = await setup(tmp_path)
    writes = []
    def mutations(_connection, _cursor, sql, _params, _ctx, _many):
        if sql.lstrip().split(None, 1)[0].upper() in {'INSERT', 'UPDATE', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'}:
            writes.append(sql)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, status)
            before, queue_calls = await original_rows(env), env['resolver'].queue.calls
            event.listen(env['engine'].sync_engine, 'before_cursor_execute', mutations)
            observed = await observe(client, env, intent)
            assert writes == [] and observed['job']['status'] == status and observed['can_adopt'] is False and observed['output'] is None
            saved = await release(client, env, intent, observed)
            assert len(writes) == 1 and writes[0].lstrip().upper().startswith('INSERT INTO SERVICE_API_OPERATIONS')
            assert saved['settlement']['terminal_status'] == status and saved['settlement']['current_output_adopted'] is False
            assert saved['admission_receipt'] == result['receipt'] and saved['original_job_preserved'] is True
            assert await original_rows(env) == before
            replay = await release(client, env, intent, observed)
            assert replay == saved
            audit = await client.get(settlement_url(env) + '/settlements/' + saved['settlement']['settlement_id'])
            assert audit.status_code == 200 and audit.json() == saved and len(writes) == 1
            assert (await observe(client, env, intent)) == saved and len(writes) == 1
            late = await client.post(url(env), json=intent['body'])
            assert late.status_code == 409 and late.json()['detail']['error']['code'] == 'BROLL_INTERNAL_REQUEST_SETTLED'
            identifier = result['job']['resolution_job_id']
            assert (await env['resolver'].process(identifier)).status == status
            exact = await client.get(url(env) + f"/requests/{intent['body']['request_key']}/jobs/{identifier}")
            value = exact.json()
            assert value['state'] == (status if status in {'failed', 'cancelled'} else 'unknown')
            assert value['error_code'] == 'BROLL_INTERNAL_REQUEST_SETTLED' and value['needs_attention'] is True
            assert not value['can_adopt'] and value['output'] is None and value['receipt'] == result['receipt']
            assert await original_rows(env) == before and len(await settlements(env)) == 1
            assert env['resolver'].queue.calls == queue_calls and deny_wire == []
            assert 'materialization_started' not in audit.text and 'byte_proof' not in audit.text and TEST_HUMAN_TOKEN not in audit.text
    finally:
        event.remove(env['engine'].sync_engine, 'before_cursor_execute', mutations)
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_old_source_asset_rights_provider_project_and_timeline_can_change_without_blocking_terminal_release(tmp_path, deny_wire):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'succeeded')
            async with env['session_factory']() as session:
                for identifier in (env['source_asset'].asset_id, env['review_asset'].asset_id):
                    asset = await session.get(AssetORM, identifier)
                    asset.storage_provider = 's3'
                    asset.version += 1
                    asset.provenance = {**asset.provenance, 'rights_status': 'restricted', 'changed_after_job': True}
                project = await session.get(VideoProjectORM, env['project'].project_id)
                project.name = 'Current changed project; no new source approval'
                project.provenance = {**project.provenance, 'changed_after_original': True}
                await session.commit()
            before = await original_rows(env)
            observed = await observe(client, env, intent)
            saved = await release(client, env, intent, observed)
            assert saved['job']['status'] == 'succeeded' and not saved['can_adopt'] and saved['output'] is None
            assert await original_rows(env) == before and len(await settlements(env)) == 1 and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['queued', 'running'])
async def test_active_jobs_cannot_be_settled_or_resumed_by_inspection(tmp_path, deny_wire, status):
    from app.broll_internal_resolution_worker import claim
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            if status == 'running':
                assert await claim(env['resolver'], result['job']['resolution_job_id']) is not None
            before, calls = await original_rows(env), env['resolver'].queue.calls
            for suffix, extra in [('/inspect', {}), ('/settle', {'observation_sha256': 'a' * 64, 'acknowledged': True})]:
                response = await client.post(settlement_url(env) + suffix, json={**inspected_body(intent), **extra})
                assert response.status_code == 409 and response.json()['detail']['error']['code'] == 'BROLL_INTERNAL_TERMINAL_JOB_REQUIRED'
            assert await original_rows(env) == before and await settlements(env) == []
            assert env['resolver'].queue.calls == calls and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['receipt-null', 'absent', 'body-key', 'job', 'context', 'principal', 'provider-graph'])
async def test_unverifiable_or_changed_original_intent_cannot_be_settled(tmp_path, deny_wire, change):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            if change == 'receipt-null': intent['receipt'] = None
            elif change == 'absent': intent['receipt']['operation_id'] = 'sop_' + 'f' * 32
            elif change == 'body-key': intent['body']['request_key'] = 'foreign-request-key-0001'
            elif change == 'job': intent['receipt']['resolution_job_id'] = 'mrj_foreign_fixture_job'
            elif change == 'context': intent['context']['candidates'][0]['asset_custody']['version'] += 1
            elif change == 'principal': intent['principal_sha256'] = 'f' * 64
            else: intent['body']['provider_graph'] = {'unapproved': True}
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code in {404, 409}, response.text
            response = await client.post(settlement_url(env) + '/settle', json={**inspected_body(intent),
                'observation_sha256': 'a' * 64, 'acknowledged': True})
            assert response.status_code in {404, 409} and await settlements(env) == []
            assert await original_rows(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_known_admission_survives_same_actor_renewal_and_old_registry_pruning_without_authenticating_old_token(tmp_path, deny_wire):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (app, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            before = await original_rows(env)
            client.headers.update(renew(app, remove_old=True))
            old = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent), headers=TEST_HUMAN_HEADERS)
            assert old.status_code == 401
            observed = await observe(client, env, intent)
            saved = await release(client, env, intent, observed)
            history = await client.get(settlement_url(env) + '/settlements/' + saved['settlement']['settlement_id'])
            assert history.status_code == 200 and history.json() == saved
            assert await original_rows(env) == before and len(await settlements(env)) == 1 and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('role,actor', [('editor', None), (None, 'usr:foreign-fixture')])
async def test_changed_current_roles_or_actor_cannot_borrow_original_private_proof(tmp_path, deny_wire, role, actor):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (app, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            client.headers.update(renew(app, role=role, actor=actor, remove_old=True))
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code == 403, response.text
            assert await original_rows(env) == before and await settlements(env) == [] and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['write-disabled', 'credential-revoked'])
async def test_late_current_authority_change_after_sql_rolls_back_without_settlement(tmp_path, deny_wire, monkeypatch, change):
    from app import broll_internal_settlement_command as command
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (app, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            observed = await observe(client, env, intent)
            before = await original_rows(env)
            actual = command.settlement_for
            checks = []
            async def changed(*args, **kwargs):
                value = await actual(*args, **kwargs)
                checks.append(True)
                if change == 'write-disabled': app.state.human_write_enabled = False
                else:
                    registry = app.state.human_auth_verifier.registry
                    registry.tokens['test-owner'] = registry.tokens['test-owner'].model_copy(update={'enabled': False})
                return value
            monkeypatch.setattr(command, 'settlement_for', changed)
            response = await client.post(settlement_url(env) + '/settle', json={**inspected_body(intent),
                'observation_sha256': observed['observation_sha256'], 'acknowledged': True})
            assert response.status_code == 403, response.text
            assert checks and await settlements(env) == [] and await original_rows(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_terminal_cost_change_invalidates_CAS_and_concurrent_current_replays_append_once(tmp_path, deny_wire):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            old = await observe(client, env, intent)
            async with env['session_factory']() as session:
                job = await session.get(MediaResolutionJobORM, result['job']['resolution_job_id'])
                job.actual_cost_vnd = Decimal('0.0100')  # explicit owned metadata race fixture
                await session.commit()
            before = await original_rows(env)
            stale = await client.post(settlement_url(env) + '/settle', json={**inspected_body(intent),
                'observation_sha256': old['observation_sha256'], 'acknowledged': True})
            assert stale.status_code == 409 and await settlements(env) == []
            fresh = await observe(client, env, intent)
            a, b = await asyncio.gather(release(client, env, intent, fresh), release(client, env, intent, fresh))
            assert a == b and len(await settlements(env)) == 1 and await original_rows(env) == before
            altered = inspected_body(intent)
            altered['intent_json'] += ' '
            altered['intent_sha256'] = hashlib.sha256(altered['intent_json'].encode()).hexdigest()
            changed = await client.post(settlement_url(env) + '/settle', json={**altered,
                'observation_sha256': fresh['observation_sha256'], 'acknowledged': True})
            assert changed.status_code == 409 and len(await settlements(env)) == 1 and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('revived', ['queued', 'running'])
async def test_seal_fences_late_delivery_start_completion_and_failure_without_resurrecting_job(tmp_path, deny_wire, revived):
    from app.broll_internal_resolution_worker import handoff, guard_completion
    from app.broll_internal_resolution_core import InternalResolutionConflict
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            await release(client, env, intent, await observe(client, env, intent))
            identifier = result['job']['resolution_job_id']
            # Simulate a stale external writer/delivery. The settlement never
            # performs this transition and must not repair or execute it.
            async with env['session_factory']() as session:
                job = await session.get(MediaResolutionJobORM, identifier)
                job.status = revived
                await session.commit()
            before, calls = await original_rows(env), env['resolver'].queue.calls
            assert (await env['resolver'].process(identifier)).status == revived
            assert await handoff(env['resolver'], result['receipt']['operation_id']) == 'not_queued'
            assert await env['media_repository'].mark_resolution_running(identifier,
                expected_reviewed_internal_claim_id='f' * 32) is False
            await env['media_repository'].mark_resolution_failed(identifier, error_code='late-test', reason='late-test',
                expected_reviewed_internal_claim_id='f' * 32)
            async with env['session_factory']() as session:
                async with session.begin():
                    with pytest.raises(InternalResolutionConflict, match='BROLL_INTERNAL_REQUEST_SETTLED'):
                        await guard_completion(session, identifier, 'f' * 32, env['review_asset'])
            assert await original_rows(env) == before and env['resolver'].queue.calls == calls and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_public_audit_cost_tamper_cannot_relabel_the_CAS_chain_even_with_rehashed_response(tmp_path, deny_wire):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            saved = await release(client, env, intent, await observe(client, env, intent))
            identifier = saved['settlement']['settlement_id']
            async with env['session_factory']() as session:
                row = await session.get(ServiceOperationORM, identifier)
                value = copy.deepcopy(row.response_json)
                value['public']['job']['actual_cost_vnd'] = '9999'
                row.response_json, row.response_sha256 = value, digest(value)
                await session.commit()
            before = await original_rows(env)
            response = await client.get(settlement_url(env) + '/settlements/' + identifier)
            assert response.status_code == 409, response.text
            assert await original_rows(env) == before and env['resolver'].queue.calls == 1 and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_succeeded_without_private_completion_proof_is_not_a_known_terminal_success(tmp_path, deny_wire):
    from app.broll_internal_resolution_worker import claim_id
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'succeeded')
            async with env['session_factory']() as session:
                claim = await session.get(ServiceOperationORM, claim_id(result['job']['resolution_job_id']))
                await session.delete(claim)
                await session.commit()
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code == 409 and await settlements(env) == [] and await original_rows(env) == before
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['routing-key', 'response-status', 'receipt-provider', 'receipt-owner'])
async def test_original_admission_routing_key_status_and_safety_flags_are_part_of_server_proof(tmp_path, deny_wire, change):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            async with env['session_factory']() as session:
                op = await session.get(ServiceOperationORM, result['receipt']['operation_id'])
                if change == 'routing-key': op.key_sha256 = 'f' * 64
                elif change == 'response-status': op.response_status = 200
                else:
                    value = copy.deepcopy(op.response_json)
                    value['receipt']['provider_calls' if change == 'receipt-provider' else 'owner_approval_inferred'] = 1 if change == 'receipt-provider' else True
                    op.response_json, op.response_sha256 = value, digest(value)
                    intent['receipt'] = copy.deepcopy(value['receipt'])
                await session.commit()
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code == 409, response.text
            assert await original_rows(env) == before and await settlements(env) == [] and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_late_settlement_insert_failure_rolls_back_and_same_observation_can_retry(tmp_path, deny_wire):
    env = await setup(tmp_path)
    def fail_insert(_connection, _cursor, sql, _params, _ctx, _many):
        if sql.lstrip().upper().startswith('INSERT INTO SERVICE_API_OPERATIONS'):
            raise OSError('owned synthetic late insert failure')
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            observed = await observe(client, env, intent)
            before = await original_rows(env)
            event.listen(env['engine'].sync_engine, 'before_cursor_execute', fail_insert)
            with pytest.raises(OSError, match='owned synthetic'):
                await release(client, env, intent, observed)
            event.remove(env['engine'].sync_engine, 'before_cursor_execute', fail_insert)
            assert await settlements(env) == [] and await original_rows(env) == before
            await release(client, env, intent, observed)
            assert len(await settlements(env)) == 1 and await original_rows(env) == before and deny_wire == []
    finally:
        if event.contains(env['engine'].sync_engine, 'before_cursor_execute', fail_insert):
            event.remove(env['engine'].sync_engine, 'before_cursor_execute', fail_insert)
        await env['engine'].dispose()


def test_terminal_settlement_contract_has_no_client_trust_flag_or_implicit_acknowledgement():
    from pydantic import ValidationError
    from app.broll_internal_settlement_api import TerminalInspect, TerminalSettle
    body = {'intent_json': '{}', 'intent_sha256': 'a' * 64, 'observation_sha256': 'b' * 64, 'acknowledged': True}
    assert TerminalSettle.model_validate(body).acknowledged is True
    for change in [{'acknowledged': False}, {'acknowledged': 1}, {'trusted': True}, {'force_cancel': True},
                   {'observation_sha256': 'invalid'}, {'intent_json': {'graph': 'unapproved'}}]:
        with pytest.raises(ValidationError):
            TerminalSettle.model_validate({**body, **change})
    with pytest.raises(ValidationError):
        TerminalInspect.model_validate({'intent_json': '{}', 'intent_sha256': 'a' * 64, 'authority': {'owner': True}})


@pytest.mark.asyncio
async def test_private_completion_byte_proof_corruption_is_not_accepted_as_known_success(tmp_path, deny_wire):
    from app.broll_internal_resolution_worker import claim_id
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'succeeded')
            async with env['session_factory']() as session:
                claim = await session.get(ServiceOperationORM, claim_id(result['job']['resolution_job_id']))
                value = copy.deepcopy(claim.response_json)
                value['byte_proof']['size_bytes'] += 1
                claim.response_json, claim.response_sha256 = value, digest(value)
                await session.commit()
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code == 409, response.text
            assert await original_rows(env) == before and await settlements(env) == [] and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_malformed_saved_original_receipt_is_a_closed_conflict_not_a_server_error(tmp_path, deny_wire):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            intent, result = await admitted(client, env)
            await terminal(env, result, 'cancelled')
            async with env['session_factory']() as session:
                op = await session.get(ServiceOperationORM, result['receipt']['operation_id'])
                value = copy.deepcopy(op.response_json)
                value['receipt'] = None
                op.response_json, op.response_sha256 = value, digest(value)
                await session.commit()
            before = await original_rows(env)
            response = await client.post(settlement_url(env) + '/inspect', json=inspected_body(intent))
            assert response.status_code == 409, response.text
            assert await original_rows(env) == before and await settlements(env) == [] and deny_wire == []
    finally:
        await env['engine'].dispose()
