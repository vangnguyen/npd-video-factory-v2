"""Owned SQLite + signed ASGI orchestration; no provider/Owner/deploy acceptance."""
import base64,json,time,uuid
from types import SimpleNamespace
import pytest,httpx
from fastapi import FastAPI,Depends
from sqlalchemy import select,func
from app.bridge_auth import ServiceAuthVerifier,ServiceIdentity,sign_service_request,canonical_json_bytes
from app.service_api_routes import router
from app.service_api_contract import CAPABILITIES,grants
from app.service_api_repository import ServiceOperationRepository,ServiceOperationORM
from app.db import VideoProjectORM
from app.platform_models import WorkspaceCreate,ProjectCreate
from auth_test_support import TEST_HUMAN_HEADERS,install_test_human_auth
from test_agent_hub_bridge import bridge_stack,KEY_V1

def application(stack,capabilities=CAPABILITIES):
    app=FastAPI();app.include_router(router)
    app.state.service_api_enabled=True;app.state.platform_repository=stack.platform
    app.state.service_api_repository=ServiceOperationRepository(stack.platform.session_factory)
    app.state.bridge_auth_verifier=ServiceAuthVerifier({'agent-hub':ServiceIdentity('agent-hub',('service',),{'v1':KEY_V1},
        grants({stack.workspace.workspace_id:list(capabilities)}))},stack.redis)
    install_test_human_auth(app,platform_repository=stack.platform)
    return app

async def signed(client,method,path,payload=None,*,key='service-api-fixture-idempotent-key',raw=None,extra=None):
    body=canonical_json_bytes(payload) if payload is not None else b'' if raw is None else raw
    route,_,query=path.partition('?')
    headers=sign_service_request(key=KEY_V1,service_id='agent-hub',key_id='v1',method=method,path=route,query=query,body=body,
        timestamp=int(time.time()),nonce='service-api-fixture-'+uuid.uuid4().hex)
    if method in ('POST','PUT'):headers.update({'Content-Type':'application/json','Idempotency-Key':key})
    headers.update(extra or {})
    return await client.request(method,path,content=body,headers=headers)

@pytest.fixture
async def api(tmp_path):
    stack=await bridge_stack(tmp_path);app=application(stack)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://explicit-service-fixture') as client:
            yield SimpleNamespace(stack=stack,app=app,client=client)
    finally:await stack.engine.dispose()

def create_payload(api,slug='ai-service-fixture'):
    return {'workspace_id':api.stack.workspace.workspace_id,'slug':slug,'name':'AI educational service fixture','niche':'technology'}

@pytest.mark.asyncio
async def test_project_scope_idempotence_conflict_and_current_grant_revocation(api):
    payload=create_payload(api);first=await signed(api.client,'POST','/v1/projects',payload)
    assert first.status_code==201,first.text
    replay=await signed(api.client,'POST','/v1/projects',payload)
    assert replay.status_code==201 and replay.json()==first.json() and replay.headers['X-Idempotent-Replay']=='true'
    pid=first.json()['project_id'];read=await signed(api.client,'GET','/v1/projects/'+pid)
    assert read.status_code==200 and read.headers['Cache-Control']=='no-store'
    assert {k:v for k,v in read.json().items() if k not in ('created_at','updated_at')}=={
        k:v for k,v in first.json().items() if k not in ('created_at','updated_at')}
    conflict=await signed(api.client,'POST','/v1/projects',{**payload,'name':'different'})
    assert conflict.status_code==409 and conflict.json()['detail']['error']['code']=='SERVICE_IDEMPOTENCY_CONFLICT'
    foreign=await api.stack.platform.create_workspace(WorkspaceCreate(slug='foreign-fixture',name='Foreign fixture',owner_ref='foreign'))
    denied=await signed(api.client,'POST','/v1/projects',{**payload,'workspace_id':foreign.workspace_id},key='service-api-foreign-fixture-key')
    assert denied.status_code==404
    identity=api.app.state.bridge_auth_verifier.identities['agent-hub']
    api.app.state.bridge_auth_verifier.identities={'agent-hub':ServiceIdentity(identity.service_id,identity.roles,identity.keys,{})}
    assert (await signed(api.client,'GET','/v1/projects/'+pid)).status_code==404
    assert (await signed(api.client,'POST','/v1/projects',payload)).status_code==404

@pytest.mark.asyncio
async def test_signed_body_validation_is_before_core_and_human_session_is_not_service_auth(api):
    assert (await api.client.get('/v1/contract',headers=TEST_HUMAN_HEADERS)).status_code==400
    malformed=await signed(api.client,'POST','/v1/projects',raw=b'PRIVATE_NOT_JSON',extra={'X-NPD-Signature':'0'*64})
    assert malformed.status_code==401 and 'PRIVATE_NOT_JSON' not in malformed.text
    duplicate=await signed(api.client,'POST','/v1/projects',raw=b'{"name":"first","name":"second"}')
    assert duplicate.status_code==400
    route='/v1/contract';headers=sign_service_request(key=KEY_V1,service_id='agent-hub',key_id='v1',method='GET',path=route,
        body=b'',timestamp=int(time.time()),nonce='service-api-replay-fixture-'+uuid.uuid4().hex)
    assert (await api.client.get(route,headers=headers)).status_code==200
    assert (await api.client.get(route,headers=headers)).status_code==401
    async with api.stack.platform.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ServiceOperationORM))==0

@pytest.mark.asyncio
async def test_service_roles_and_response_integrity_cannot_be_promoted_or_rehashed_by_callers(api):
    first=await signed(api.client,'POST','/v1/projects',create_payload(api));assert first.status_code==201
    identity=api.app.state.bridge_auth_verifier.identities['agent-hub']
    api.app.state.bridge_auth_verifier.identities={'agent-hub':ServiceIdentity('agent-hub',('service','owner'),identity.keys,identity.workspace_grants)}
    assert (await signed(api.client,'GET','/v1/contract')).status_code==403
    api.app.state.bridge_auth_verifier.identities={'agent-hub':identity}
    async with api.stack.platform.session_factory() as session:
        row=await session.scalar(select(ServiceOperationORM));row.response_json={**row.response_json,'name':'tampered fixture'};await session.commit()
    rejected=await signed(api.client,'POST','/v1/projects',create_payload(api))
    assert rejected.status_code==409 and rejected.json()['detail']['error']['code']=='SERVICE_OPERATION_EVIDENCE_INVALID'

def test_scoped_service_grants_load_from_existing_key_custody_without_exposing_keys(tmp_path):
    from test_agent_hub_bridge import FakeRedis
    path=tmp_path/'explicit-service-keys.json'
    raw={'version':1,'service_identities':{'agent-hub':{'roles':['service'],'keys':{'v1':base64.b64encode(KEY_V1).decode()},
        'workspace_grants':{'wsp_scoped_fixture':['project.read','timeline.read']}}}}
    path.write_text(json.dumps(raw),encoding='utf-8')
    verifier=ServiceAuthVerifier.from_file(path,FakeRedis())
    assert verifier.identities['agent-hub'].workspace_grants['wsp_scoped_fixture']==('project.read','timeline.read')
    raw['service_identities']['agent-hub']['workspace_grants']={'*':['owner']};path.write_text(json.dumps(raw),encoding='utf-8')
    with pytest.raises(ValueError,match='SERVICE_API_GRANTS_INVALID'):ServiceAuthVerifier.from_file(path,FakeRedis())

@pytest.mark.asyncio
async def test_uncertain_completion_never_redispatches_a_committed_canonical_mutation(api,monkeypatch):
    created=await signed(api.client,'POST','/v1/projects',create_payload(api));assert created.status_code==201
    pid=created.json()['project_id'];path='/v1/projects/'+pid+'/versions'
    async def fail(*_):raise RuntimeError('explicit receipt completion interruption')
    monkeypatch.setattr(api.app.state.service_api_repository,'complete',fail)
    payload={'label':'explicit-uncaptured-version','snapshot':{'fixture':True}}
    first=await signed(api.client,'POST',path,payload,key='service-api-uncertain-version-fixture-key')
    assert first.status_code==409 and first.json()['detail']['error']['code']=='SERVICE_OPERATION_UNCERTAIN'
    again=await signed(api.client,'POST',path,payload,key='service-api-uncertain-version-fixture-key');assert again.status_code==409
    async with api.stack.platform.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(VideoProjectORM))==1
        operation=await session.scalar(select(ServiceOperationORM).where(ServiceOperationORM.action=='project.write'))
        assert operation.status=='uncertain' and operation.response_json is None
    assert len(await api.stack.platform.list_versions(pid))==1
    status=await signed(api.client,'GET','/v1/operations/'+operation.operation_id)
    assert status.status_code==200 and status.json()['automatic_redispatch'] is False

@pytest.mark.parametrize('bad',[{'*':['project.read']},{'wsp_fixture':['owner']},{'wsp_fixture':['project.read','project.read']},
    {'wsp_fixture':'project.read'},{'wsp_fixture':[True]}])
def test_service_grants_never_create_human_roles_or_wildcard_workspaces(bad):
    with pytest.raises(ValueError,match='SERVICE_API_GRANTS_INVALID'):grants(bad)

def test_master_endpoint_coverage_is_full_not_draft_only():
    paths=FastAPI();paths.include_router(router);actual=paths.openapi()['paths']
    required={'/v1/trends/refresh':{'post'},'/v1/trends':{'get'},'/v1/opportunities':{'get'},'/v1/ideas/generate':{'post'},
        '/v1/projects':{'post'},'/v1/projects/{project_id}':{'get'},'/v1/projects/{project_id}/generate':{'post'},
        '/v1/uploads/init':{'post'},'/v1/uploads/complete':{'post'},'/v1/projects/{project_id}/analyze':{'post'},
        '/v1/projects/{project_id}/timeline':{'get','put'},'/v1/projects/{project_id}/preview':{'post'},
        '/v1/projects/{project_id}/approve':{'post'},'/v1/projects/{project_id}/render':{'post'},
        '/v1/projects/{project_id}/publish':{'post'},'/v1/projects/{project_id}/publications':{'get'},
        '/v1/projects/{project_id}/analytics':{'get'}}
    assert sum(map(len,required.values()))==18
    assert all(methods<=actual[path].keys() for path,methods in required.items())

@pytest.mark.asyncio
async def test_optional_hub_custody_failure_disables_only_the_boundary_and_retains_core(api,tmp_path):
    from app.service_api_runtime import configure
    settings=SimpleNamespace(agent_hub_bridge_enabled=True,agent_hub_service_keys_file=tmp_path/'missing-keys.json',
        service_auth_max_clock_skew_seconds=300,service_auth_replay_ttl_seconds=600)
    before=api.app.state.platform_repository
    configure(api.app,settings=settings,factory=api.stack.platform.session_factory,queue=api.stack.redis,
        platform=api.stack.platform,publishing=None,analytics=None,default_workspace_id=api.stack.workspace.workspace_id)
    assert api.app.state.service_api_configuration_state=='not_configured' and api.app.state.service_api_enabled is False
    assert api.app.state.platform_repository is before and api.app.state.agent_hub_bridge_service is None
    assert (await signed(api.client,'GET','/v1/contract')).status_code==503
    from app.platform_routes import router as platform_router
    from app.human_auth import authorize_human_request
    api.app.include_router(platform_router,dependencies=[Depends(authorize_human_request)])
    created=await before.create_project(api.stack.workspace.workspace_id,
        ProjectCreate(slug='offline-core-fixture',name='Offline core fixture'))
    assert created.project_id and created.status=='draft'
    read=await api.client.get('/api/v1/projects/'+created.project_id,headers=TEST_HUMAN_HEADERS)
    assert read.status_code==200 and read.json()['project_id']==created.project_id
