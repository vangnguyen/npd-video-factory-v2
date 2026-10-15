"""Actual main/owned SQLite admission and deferred-plan receipt, not provider acceptance."""
from contextlib import asynccontextmanager

import httpx
import pytest
import pytest_asyncio
import socket
from sqlalchemy import func, select

from app import main
from app.db import CostRecordORM, ProviderUsageORM
from app.media_intelligence_db import MediaPlanORM
from app.service_api_repository import ServiceOperationORM
from app.timeline_db import TimelineORM
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_broll_plan_review import body, prepare, server


@pytest_asyncio.fixture
async def deny_wire(monkeypatch):
    attempts=[]
    def reject(*args,**kwargs):
        attempts.append('blocked_external_network_attempt')
        raise AssertionError('REVIEWED_PREPARATION_MUST_NOT_DISPATCH_NETWORK')
    for name in ('connect','connect_ex'):
        monkeypatch.setattr(socket.socket,name,reject)
    for name in ('create_connection','getaddrinfo'):
        monkeypatch.setattr(socket,name,reject)
    try:
        yield attempts
        assert attempts==[]
    finally:
        monkeypatch.undo()


@asynccontextmanager
async def actual_main(env):
    app = main.app
    prior = dict(app.state._state)
    object.__setattr__(app.state, '_state', dict(server(env).state._state))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                base_url='http://owned-broll-plan-main', headers=TEST_HUMAN_HEADERS) as client:
            yield app, client
    finally:
        object.__setattr__(app.state, '_state', prior)


async def counts(env):
    async with env['session_factory']() as session:
        return {model.__tablename__:await session.scalar(select(func.count()).select_from(model))
            for model in (MediaPlanORM, ServiceOperationORM, ProviderUsageORM, CostRecordORM)}


@pytest.mark.asyncio
async def test_main_reviewed_broll_exact_plan_receipt_replay_and_unchanged_timeline(tmp_path,deny_wire):
    env = await prepare(tmp_path)
    project = env['project']
    path = f'/api/v1/projects/{project.project_id}/broll-plan-review'
    try:
        async with actual_main(env) as (_app, client):
            before = await counts(env)
            session = await client.get('/api/v1/auth/session')
            assert session.status_code == 200
            read = await client.get(path)
            assert read.status_code == 200 and read.headers['cache-control'] == 'no-store'
            context = read.json()
            assert context['preparation_provider_calls'] == 0
            assert context['publishing_enabled'] is False and context['owner_approval_inferred'] is False
            assert await counts(env) == before
            request = body(context)
            result = await client.post(path, json=request)
            assert result.status_code == 201, result.text
            saved = result.json()
            assert saved['state'] == 'prepared' and saved['preparation_provider_calls'] == 0
            assert saved['receipt']['actor_ref'] == session.json()['subject']
            assert saved['plan']['source_media_mutated'] is False and saved['plan']['publish_requested'] is False
            plan_id = saved['plan']['media_plan_id']
            receipt = await client.get(path+'/requests/'+request['request_key'])
            canonical = await client.get(f'/api/v1/projects/{project.project_id}/media-plans/{plan_id}')
            assert receipt.status_code == canonical.status_code == 200
            assert receipt.json()['receipt'] == saved['receipt']
            assert canonical.json() == saved['plan']
            after = await counts(env)
            assert after['media_plans'] == before['media_plans']+1
            assert after['service_api_operations'] == before['service_api_operations']+1
            assert all(after[name] == before[name] for name in ('provider_usage','cost_records'))
            replay = await client.post(path,json=request)
            assert replay.status_code == 201 and replay.json()=={**saved,'replayed':True}
            assert await counts(env)==after
            async with env['session_factory']() as sql:
                row = await sql.scalar(select(TimelineORM).where(TimelineORM.project_id==project.project_id))
                assert row.current_version==context['timeline_version']
                assert row.current_version_id==context['timeline_version_id']
    finally:
        await env['engine'].dispose()


@pytest.mark.parametrize('mode,status',[('viewer',403),('write_off',503),('unauthenticated',401),('foreign',404)])
@pytest.mark.asyncio
async def test_main_reviewed_broll_admission_precedes_invalid_private_body(tmp_path,mode,status,deny_wire):
    env=await prepare(tmp_path)
    project=env['project'];path=f'/api/v1/projects/{project.project_id}/broll-plan-review'
    try:
        async with actual_main(env) as (app,client):
            if mode in {'viewer','foreign'}:
                install_test_human_auth(app,platform_repository=env['platform'],platform_role=None,
                    workspace_roles={project.workspace_id:'viewer'} if mode=='viewer' else {'wsp_foreign':'editor'})
            elif mode=='write_off':
                app.state.human_write_enabled=False
            before=await counts(env)
            response=await client.post(path,json={'invalid_private_fixture':True},
                headers={'Authorization':''} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
            assert response.status_code==status,response.text
            assert await counts(env)==before
            if mode in {'viewer','write_off'}:
                read=await client.get(path)
                assert read.status_code==200 and read.headers['cache-control']=='no-store'
    finally:
        await env['engine'].dispose()
