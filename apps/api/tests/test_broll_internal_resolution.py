"""Owned SQLite/storage and in-process ASGI; synthetic metadata, no provider."""
import asyncio
import copy
import json
import socket
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, func, event
from pydantic import ValidationError

from app.broll_internal_resolution_api import InternalResolutionRequest
from app.broll_internal_resolution_command import inspect_context, admit, inspect_job
from app.broll_internal_resolution_core import NAMESPACE, CLAIM_NAMESPACE, MARKER
from app.db import AssetORM
from app.media_intelligence_db import MediaResolutionJobORM, MediaAssetProvenanceORM, MediaPlanItemORM
from app.service_api_repository import ServiceOperationORM
from app.timeline_db import TimelineVersionORM
from test_broll_planner import prepare, add_asset, request as plan_request


class AtomicQueue:
    def __init__(self, *, lose_ack=False):
        self.values, self.calls, self.lose_ack = [], 0, lose_ack

    async def eval(self, script, count, key, value):
        assert count == 1 and "LREM" in script and "RPUSH" in script
        self.calls += 1
        self.values = [(k, v) for k, v in self.values if k != key or v != value]
        self.values.append((key, value))
        if self.lose_ack:
            self.lose_ack = False
            raise OSError('explicit test lost acknowledgement')
        return len(self.values)

    async def rpush(self, key, value):
        raise AssertionError('reviewed queue requires atomic handoff')


async def setup(tmp_path, *, rights='owned', queue=True):
    env = await prepare(tmp_path)
    asset = await add_asset(env, filename='reviewed-support.jpg', rights=rights)
    plan = await env['planner'].create(project_id=env['project'].project_id, payload=plan_request(env))
    env.update(review_asset=asset, review_plan=plan, review_item=plan.items[0])
    if queue:
        env['resolver'].queue = AtomicQueue()
    return env


@asynccontextmanager
async def client_for(env, **auth):
    from app.main import app
    from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
    old = dict(app.state._state)
    try:
        app.state.media_resolution_service = env['resolver']
        install_test_human_auth(app, platform_repository=env['platform'], **auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://owned-internal-resolution',
                headers=TEST_HUMAN_HEADERS) as client:
            yield app, client
    finally:
        object.__setattr__(app.state, '_state', old)


def url(env):
    return f"/api/v1/projects/{env['project'].project_id}/media-plans/{env['review_plan'].media_plan_id}/items/{env['review_item'].media_plan_item_id}/internal-resolution-review"


def request(env, value, key='reviewed-internal-intent-0001'):
    return {'asset_id': env['review_asset'].asset_id, 'context_sha256': value['context_sha256'],
        'request_key': key, 'acknowledged': True}


async def counts(env):
    async with env['session_factory']() as session:
        return {name: await session.scalar(select(func.count()).select_from(model)) for name, model in
            [('jobs', MediaResolutionJobORM), ('operations', ServiceOperationORM),
             ('versions', TimelineVersionORM), ('outputs', MediaAssetProvenanceORM)]}


@pytest.mark.asyncio
async def test_actual_main_one_receipt_job_internal_worker_and_exact_observation(tmp_path, monkeypatch):
    env = await setup(tmp_path)
    try:
        attempts = []
        def deny_network(*args, **kwargs):
            attempts.append(True)
            raise AssertionError('external networking forbidden in internal fixture')
        monkeypatch.setattr(socket.socket, 'connect', deny_network)
        timeline = (await env['timeline_service'].get(env['project'].project_id)).model_dump(mode='json')
        async with client_for(env) as (_, client):
            before = await counts(env)
            context = await client.get(url(env))
            assert context.status_code == 200, context.text
            assert context.headers['cache-control'] == 'no-store'
            assert await counts(env) == before and env['resolver'].queue.calls == 0
            body = request(env, context.json())
            created = await client.post(url(env), json=body)
            assert created.status_code == 202, created.text
            saved = created.json()
            assert saved['handoff'] == 'enqueued' and saved['job']['status'] == 'queued'
            assert saved['job']['capability'] == 'internal_media'
            assert saved['job']['external_call'] is False and saved['job']['paid'] is False
            replay = await client.post(url(env), json=body)
            assert replay.status_code == 202 and replay.json()['receipt'] == saved['receipt']
            assert len(env['resolver'].queue.values) == 1
            assert (await counts(env)) == {**before, 'jobs': 1, 'operations': 1}
            job_id = saved['receipt']['resolution_job_id']
            result = await env['resolver'].process(job_id)
            assert result.status == 'succeeded', result.model_dump(mode='json')
            observed = await client.get(url(env) + f"/requests/{body['request_key']}/jobs/{job_id}")
            assert observed.status_code == 200, observed.text
            value = observed.json()
            assert value['can_adopt'] is True and value['receipt'] == saved['receipt']
            assert value['output']['asset_id'] == env['review_asset'].asset_id
            assert value['output']['publishing_allowed'] is False  # synthetic fixture
            assert 'byte_proof' not in observed.text and 'materialization_started' not in observed.text
            assert (await env['timeline_service'].get(env['project'].project_id)).model_dump(mode='json') == timeline
            assert (await counts(env))['versions'] == 1
            assert not list(env['resolver'].staging_root.glob('*-review-*'))
            assert attempts == []
    finally:
        # Windows pytest creates a fresh Proactor loop during teardown, whose
        # self-pipe uses loopback. Keep the test's deny policy inside the test.
        monkeypatch.undo()
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_missing_atomic_queue_lost_ack_and_read_never_handoff(tmp_path):
    env = await setup(tmp_path, queue=False)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            body = request(env, context)
            first = (await client.post(url(env), json=body)).json()
            assert first['handoff'] == 'handoff_pending'
            job_id = first['receipt']['resolution_job_id']
            queue = AtomicQueue(lose_ack=True)
            env['resolver'].queue = queue
            await client.get(url(env) + f"/requests/{body['request_key']}/jobs/{job_id}")
            assert queue.calls == 0
            lost = (await client.post(url(env), json=body)).json()
            assert lost['handoff'] == 'handoff_pending' and lost['receipt'] == first['receipt']
            resumed = (await client.post(url(env), json=body)).json()
            assert resumed['receipt'] == first['receipt'] and len(queue.values) == 1
            assert (await counts(env))['jobs'] == 1
            assert await env['resolver'].recover_pending() == 0
            assert queue.calls == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_queued_storage_provider_drift_has_no_output_or_canonical_change(tmp_path):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            saved = (await client.post(url(env), json=request(env, context))).json()
            async with env['session_factory']() as session:
                asset = await session.get(AssetORM, env['review_asset'].asset_id)
                asset.storage_provider = 's3'
                await session.commit()
            job = await env['resolver'].process(saved['receipt']['resolution_job_id'])
            assert job.status == 'failed'
            assert job.output_media_asset_id is None
            assert (await counts(env))['outputs'] == 0 and (await counts(env))['versions'] == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['size', 'version', 'provenance', 'rights', 'license', 'object-key', 'checksum', 'primary-checksum'])
async def test_queued_full_asset_custody_rejects_even_unchanged_checksum(tmp_path, mutation):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            saved = (await client.post(url(env), json=request(env, context))).json()
            async with env['session_factory']() as session:
                asset = await session.get(AssetORM, env['source_asset'].asset_id if mutation == 'primary-checksum' else env['review_asset'].asset_id)
                if mutation == 'size': asset.size_bytes += 1
                elif mutation == 'version': asset.version += 1
                elif mutation == 'object-key': asset.object_key += '.changed'
                elif mutation in {'checksum', 'primary-checksum'}: asset.checksum_sha256 = 'f' * 64
                else: asset.provenance = {**asset.provenance, **({'rights_status': 'restricted'} if mutation == 'rights'
                    else {'license': 'different-license'} if mutation == 'license' else {'after_review': True})}
                await session.commit()
            job = await env['resolver'].process(saved['receipt']['resolution_job_id'])
            assert job.status == 'failed' and job.output_media_asset_id is None
            value = (await client.get(url(env) + f"/requests/{saved['receipt']['request_key']}/jobs/{job.resolution_job_id}")).json()
            assert value['can_adopt'] is False and value['receipt'] == saved['receipt']
            assert (await counts(env))['outputs'] == 0 and (await counts(env))['versions'] == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['provenance', 'source', 'cancel'])
async def test_late_materialization_change_cannot_commit_stale_success(tmp_path, monkeypatch, mutation):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            saved = (await client.post(url(env), json=request(env, context))).json()
            identifier = saved['receipt']['resolution_job_id']
            original = env['resolver']._materialize
            async def changed(*args, **kwargs):
                result = await original(*args, **kwargs)
                async with env['session_factory']() as session:
                    if mutation == 'cancel':
                        job = await session.get(MediaResolutionJobORM, identifier)
                        job.status = 'cancelled'
                    else:
                        asset = await session.get(AssetORM, env['source_asset'].asset_id if mutation == 'source' else env['review_asset'].asset_id)
                        asset.provenance = {**asset.provenance, 'changed_during_materialization': True}
                    await session.commit()
                return result
            monkeypatch.setattr(env['resolver'], '_materialize', changed)
            job = await env['resolver'].process(identifier)
            assert job.status == ('cancelled' if mutation == 'cancel' else 'failed')
            assert job.output_media_asset_id is None and (await counts(env))['outputs'] == 0
            assert (await counts(env))['versions'] == 1
            async with env['session_factory']() as session:
                claim = await session.scalar(select(ServiceOperationORM).where(ServiceOperationORM.service_id == CLAIM_NAMESPACE))
                assert claim.status != 'succeeded'
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_corrupt_bytes_are_rejected_and_no_private_exception_is_published(tmp_path):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            saved = (await client.post(url(env), json=request(env, context))).json()
            env['storage']._path(env['review_asset'].object_key).write_bytes(b'changed physical bytes')
            job = await env['resolver'].process(saved['receipt']['resolution_job_id'])
            assert job.status == 'failed' and job.output_media_asset_id is None
            assert str(tmp_path) not in job.failure_reason
            assert not list(env['resolver'].staging_root.glob('*-review-*'))
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_concurrent_admission_and_worker_delivery_have_one_job_attempt_and_output(tmp_path):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            body = request(env, context)
            responses = await asyncio.gather(client.post(url(env), json=body), client.post(url(env), json=body))
            assert all(v.status_code == 202 for v in responses)
            assert responses[0].json()['receipt'] == responses[1].json()['receipt']
            identifier = responses[0].json()['receipt']['resolution_job_id']
            await asyncio.gather(env['resolver'].process(identifier), env['resolver'].process(identifier))
            assert (await env['resolver'].get(identifier)).status == 'succeeded'
            assert (await counts(env)) == {'jobs': 1, 'operations': 2, 'versions': 1, 'outputs': 1}
            assert (await env['resolver'].process(identifier)).status == 'succeeded'
            assert (await counts(env))['outputs'] == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_exact_observation_cannot_substitute_latest_or_foreign_job(tmp_path):
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            context = (await client.get(url(env))).json()
            body = request(env, context)
            saved = (await client.post(url(env), json=body)).json()
            wrong = await client.get(url(env) + f"/requests/{body['request_key']}/jobs/mrj_foreign_job_0001")
            assert wrong.status_code == 409
            wrong_key = await client.get(url(env) + f"/requests/foreign_intent_0001/jobs/{saved['job']['resolution_job_id']}")
            assert wrong_key.status_code == 404
            calls = env['resolver'].queue.calls
            await client.get(url(env))
            assert env['resolver'].queue.calls == calls
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_running_crash_is_observable_and_never_automatically_resumed(tmp_path):
    from app.broll_internal_resolution_worker import claim
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            body = request(env, (await client.get(url(env))).json())
            saved = (await client.post(url(env), json=body)).json()
            identifier = saved['job']['resolution_job_id']
            assert await claim(env['resolver'], identifier) is not None
            calls = env['resolver'].queue.calls
            observed = await client.get(url(env) + f"/requests/{body['request_key']}/jobs/{identifier}")
            assert observed.json()['job']['status'] == 'running' and observed.json()['needs_attention'] is True
            assert observed.json()['can_adopt'] is False
            await client.post(url(env), json=body)
            assert await env['resolver'].recover_pending() == 0
            assert env['resolver'].queue.calls == calls
            assert (await env['resolver'].process(identifier)).status == 'running'
            assert (await counts(env))['outputs'] == 0
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_legacy_admission_cannot_take_item_while_reviewed_job_owned(tmp_path):
    from app.media_intelligence_models import MediaResolutionRequest
    env = await setup(tmp_path)
    try:
        async with client_for(env) as (_, client):
            body = request(env, (await client.get(url(env))).json())
            saved = (await client.post(url(env), json=body)).json()
            with pytest.raises(ValueError, match='BROLL_INTERNAL_REVIEWED_ITEM_OWNED'):
                await env['resolver'].enqueue(project_id=env['project'].project_id,
                    media_plan_id=env['review_plan'].media_plan_id,
                    media_plan_item_id=env['review_item'].media_plan_item_id,
                    payload=MediaResolutionRequest(asset_id=env['review_asset'].asset_id))
            assert (await counts(env))['jobs'] == 1
            assert (await env['resolver'].process(saved['job']['resolution_job_id'])).status == 'succeeded'
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,status', [('viewer', 403), ('disabled', 503), ('unauthenticated', 401)])
async def test_auth_denies_writes_before_malformed_body(tmp_path, mode, status):
    env = await setup(tmp_path)
    try:
        auth = {'platform_role': 'viewer', 'workspace_roles': {'*': 'viewer'}} if mode == 'viewer' else {}
        async with client_for(env, **auth) as (app, client):
            if mode == 'disabled': app.state.human_write_enabled = False
            response = await client.post(url(env), json={'invalid': 'graph'},
                headers={'Authorization': 'Bearer wrong'} if mode == 'unauthenticated' else {})
            assert response.status_code == status
            assert (await counts(env))['jobs'] == 0 and env['resolver'].queue.calls == 0
    finally:
        await env['engine'].dispose()


@pytest.mark.parametrize('change', [{'acknowledged': False}, {'acknowledged': 1},
    {'request_key': 'short'}, {'context_sha256': 'bad'}, {'asset_id': True}, {'provider_graph': {}}])
def test_closed_internal_admission_contract(change):
    body = dict(request_key='reviewed-internal-contract-01', context_sha256='a' * 64,
        asset_id='ast_registered_fixture', acknowledged=True)
    with pytest.raises(ValidationError):
        InternalResolutionRequest.model_validate({**body, **change})


@pytest.mark.asyncio
async def test_unknown_rights_remain_review_only_and_non_candidate_never_admitted(tmp_path):
    env = await setup(tmp_path, rights='unknown')
    try:
        async with client_for(env) as (_, client):
            body = request(env, (await client.get(url(env))).json())
            bad = await client.post(url(env), json={**body, 'asset_id': env['source_asset'].asset_id})
            assert bad.status_code == 409 and (await counts(env))['jobs'] == 0
            first = (await client.post(url(env), json=body)).json()
            changed = await client.post(url(env), json={**body, 'asset_id': env['source_asset'].asset_id})
            assert changed.status_code == 409
            identifier = first['job']['resolution_job_id']
            assert (await env['resolver'].process(identifier)).status == 'succeeded'
            value = (await client.get(url(env) + f"/requests/{body['request_key']}/jobs/{identifier}")).json()
            assert value['output']['rights_status'] == 'unknown'
            assert value['output']['publishing_allowed'] is False
            assert value['publishing_enabled'] is False and value['owner_approval_inferred'] is False
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_late_admission_insert_failure_rolls_back_job_receipt_and_item(tmp_path):
    env = await setup(tmp_path)
    statements = []
    def fail_receipt(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith('INSERT'):
            statements.append(statement.split('(')[0])
        if statement.lstrip().upper().startswith('INSERT INTO SERVICE_API_OPERATIONS'):
            raise RuntimeError('owned late receipt insert failure')
    try:
        async with client_for(env) as (_, client):
            body = request(env, (await client.get(url(env))).json())
            event.listen(env['engine'].sync_engine, 'before_cursor_execute', fail_receipt)
            with pytest.raises(RuntimeError, match='owned late receipt'):
                await client.post(url(env), json=body)
            event.remove(env['engine'].sync_engine, 'before_cursor_execute', fail_receipt)
            assert any('media_resolution_jobs' in v.lower() for v in statements)
            assert (await counts(env)) == {'jobs': 0, 'operations': 0, 'versions': 1, 'outputs': 0}
            assert env['resolver'].queue.calls == 0
            async with env['session_factory']() as session:
                item = await session.get(MediaPlanItemORM, env['review_item'].media_plan_item_id)
                assert item.status == env['review_item'].status
            assert (await client.post(url(env), json=body)).status_code == 202
    finally:
        if event.contains(env['engine'].sync_engine, 'before_cursor_execute', fail_receipt):
            event.remove(env['engine'].sync_engine, 'before_cursor_execute', fail_receipt)
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_reviewed_and_legacy_concurrent_admissions_have_one_item_owner(tmp_path):
    from app.media_intelligence_models import MediaResolutionRequest
    env = await setup(tmp_path)
    try:
        async def ordinary_push(key, value):
            env['resolver'].queue.values.append((key, value))
        env['resolver'].queue.rpush = ordinary_push
        async with client_for(env) as (_, client):
            body = request(env, (await client.get(url(env))).json())
            async def legacy():
                try:
                    return await env['resolver'].enqueue(project_id=env['project'].project_id,
                        media_plan_id=env['review_plan'].media_plan_id,
                        media_plan_item_id=env['review_item'].media_plan_item_id,
                        payload=MediaResolutionRequest(asset_id=env['review_asset'].asset_id))
                except ValueError:
                    return None
            reviewed, ordinary = await asyncio.gather(client.post(url(env), json=body), legacy())
            assert reviewed.status_code in {202, 409}
            assert (reviewed.status_code == 202) is (ordinary is None)
            assert (await counts(env))['jobs'] == 1
    finally:
        await env['engine'].dispose()
