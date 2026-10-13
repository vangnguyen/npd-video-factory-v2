"""Atomic core outcome/receipt/outbox tests; no provider or production calls."""
import asyncio,json,os,subprocess,sys
from pathlib import Path
import pytest,httpx
from sqlalchemy import select,func
from app.db import VideoProjectORM
from app.service_api_repository import ServiceOperationORM,ServiceOperationRepository,digest
from app.service_outcome_events import ServiceOutcomeEventORM
from app.repositories import PlatformRepository
from test_service_api import api,signed,create_payload
from test_service_api_flows import flow,call

@pytest.mark.asyncio
async def test_project_commit_survives_outer_receipt_failure_without_duplicate_and_emits_atomic_event(api,monkeypatch):
    async def fail(*_):raise RuntimeError('explicit outer receipt failure')
    monkeypatch.setattr(api.app.state.service_api_repository,'complete',fail)
    payload=create_payload(api);first=await signed(api.client,'POST','/v1/projects',payload)
    assert first.status_code==409
    replay=await signed(api.client,'POST','/v1/projects',payload)
    assert replay.status_code==201,replay.text
    async with api.stack.platform.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(VideoProjectORM))==1
        operation=await session.scalar(select(ServiceOperationORM));event=await session.scalar(select(ServiceOutcomeEventORM))
        assert operation.status=='succeeded' and digest(replay.json())==operation.response_sha256
        assert event.envelope_json['payload']['response_sha256']==operation.response_sha256
        assert 'AI educational' not in str(event.envelope_json)
    endpoint='/v1/operation-events?workspace_id='+api.stack.workspace.workspace_id
    page=await signed(api.client,'GET',endpoint)
    assert page.status_code==200 and len(page.json()['items'])==1 and page.json()['delivery_enabled'] is False
    from jsonschema import Draft202012Validator,FormatChecker
    schema=json.loads((Path(__file__).resolve().parents[3]/'packages/contracts/agent-hub-service-outcomes.v1.schema.json').read_bytes())
    Draft202012Validator(schema,format_checker=FormatChecker()).validate(page.json()['items'][0]['envelope'])
    assert (await ServiceOperationRepository(api.stack.platform.session_factory).get(operation.operation_id)).response_json==replay.json()

@pytest.mark.asyncio
async def test_rehashed_event_cannot_replace_original_actor_or_canonical_outcome(api):
    assert (await signed(api.client,'POST','/v1/projects',create_payload(api))).status_code==201
    async with api.stack.platform.session_factory() as session:
        item=await session.scalar(select(ServiceOutcomeEventORM))
        item.envelope_json={**item.envelope_json,'payload':{**item.envelope_json['payload'],'actor_ref':'forged-owner-fixture'}}
        item.envelope_sha256=digest(item.envelope_json);await session.commit()
    endpoint='/v1/operation-events?workspace_id='+api.stack.workspace.workspace_id
    response=await signed(api.client,'GET',endpoint)
    assert response.status_code==409 and response.json()['detail']['error']['code']=='SERVICE_EVENT_EVIDENCE_INVALID'

@pytest.mark.asyncio
async def test_outbox_failure_rolls_back_canonical_creation_and_receipt_together(api,monkeypatch):
    import app.service_outcome_events as events
    def fail(*_):raise RuntimeError('explicit atomic event interruption')
    monkeypatch.setattr(events,'event',fail)
    reply=await signed(api.client,'POST','/v1/projects',create_payload(api));assert reply.status_code==409
    async with api.stack.platform.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(VideoProjectORM))==0
        assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==0
        assert (await session.scalar(select(ServiceOperationORM))).status=='uncertain'

@pytest.mark.asyncio
async def test_context_is_request_local_and_existing_human_core_writes_do_not_emit_service_events(api):
    from app.platform_models import ProjectCreate
    async def service():return await signed(api.client,'POST','/v1/projects',create_payload(api))
    async def core():return await api.stack.platform.create_project(api.stack.workspace.workspace_id,
        ProjectCreate(slug='unrelated-human-core-fixture',name='Unrelated core fixture'))
    service_reply,core_reply=await asyncio.gather(service(),core())
    assert service_reply.status_code==201 and core_reply.project_id!=service_reply.json()['project_id']
    async with api.stack.platform.session_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==1
        assert await session.scalar(select(func.count()).select_from(VideoProjectORM))==2

@pytest.mark.asyncio
async def test_actual_producer_exit_after_core_commit_recovers_in_fresh_process_without_reexecution(tmp_path):
    from test_agent_hub_bridge import bridge_stack
    stack=await bridge_stack(tmp_path)
    (tmp_path/'fixture.json').write_text(json.dumps({'workspace_id':stack.workspace.workspace_id,'real_provider_calls':0,'Owner_UAT':False}),encoding='utf-8')
    script=Path(__file__).with_name('service_outcome_process_fixture.py')
    try:
        first=await asyncio.to_thread(subprocess.run,[sys.executable,str(script),str(tmp_path),'crash'],capture_output=True,text=True,timeout=40)
        assert first.returncode==71,first.stderr
        second=await asyncio.to_thread(subprocess.run,[sys.executable,str(script),str(tmp_path),'replay'],capture_output=True,text=True,timeout=40)
        assert second.returncode==0,second.stderr
        result=json.loads(second.stdout.strip().splitlines()[-1]);assert result['status']==201 and result['idempotent_replay']=='true'
        async with stack.platform.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(VideoProjectORM))==1
            assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==1
            assert (await session.scalar(select(ServiceOperationORM))).status=='succeeded'
        if os.environ.get('VF_SERVICE_OUTCOMES_EVIDENCE_DIR'):
            folder=Path(os.environ['VF_SERVICE_OUTCOMES_EVIDENCE_DIR']);folder.mkdir(parents=True,exist_ok=True)
            path=folder/'actual-process-recovery.json';assert not path.exists()
            path.write_text(json.dumps({'first_exit':71,'fresh_process':result,'unique_projects':1,'unique_events':1,
                'provider_and_identity_are_fixtures':True,'paid_calls':0,'Owner_UAT':False},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    finally:await stack.engine.dispose()

@pytest.mark.asyncio
async def test_timeline_commit_receipt_and_event_survive_lost_outer_response_without_new_version(flow,monkeypatch):
    from test_auto_edit_analysis import upload_fixture,synthetic_mp4
    from app.auto_edit_models import AutoEditAnalysisRequest
    from app.timeline_models import TimelineCreateRequest
    completed=await upload_fixture(flow.app.state.upload_service,flow.project,flow.version,synthetic_mp4())
    analysis=await flow.app.state.auto_edit_analysis_service.analyze(flow.project.project_id,
        AutoEditAnalysisRequest(asset_id=completed.asset_id))
    head=await flow.app.state.timeline_service.create(flow.project.project_id,TimelineCreateRequest(analysis_id=analysis.analysis_id))
    clip=next(c for t in head.snapshot.tracks for c in t.clips if c.asset_id)
    async def fail(*_):raise RuntimeError('explicit outer completion loss')
    monkeypatch.setattr(flow.app.state.service_api_repository,'complete',fail)
    path='/v1/projects/'+flow.project.project_id+'/timeline'
    payload={'expected_version':head.current_version,'operations':[{'type':'set_clip_properties','clip_id':clip.clip_id,'volume':.6}]}
    assert (await call(flow,'PUT',path,payload,key='atomic-timeline')).status_code==409
    replay=await call(flow,'PUT',path,payload,key='atomic-timeline')
    assert replay.status_code==200 and replay.json()['current_version']==head.current_version+1,replay.text
    assert (await flow.app.state.timeline_service.get(flow.project.project_id)).current_version==head.current_version+1
    async with flow.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==1

@pytest.mark.asyncio
async def test_render_and_dry_run_publication_recover_exact_queued_and_validated_records_without_new_job_or_post(tmp_path,monkeypatch):
    from test_publishing import approved_stack,request_for
    from test_agent_hub_bridge import FakeRedis
    from test_service_api import application
    from app.production_db import ProductionRenderJobORM
    from app.publishing_db import PublicationORM
    from types import SimpleNamespace
    from auth_test_support import TEST_HUMAN_HEADERS
    stack,final,publishing=await approved_stack(tmp_path)
    workspace=await stack.platform.get_workspace(stack.project.workspace_id)
    app=application(SimpleNamespace(platform=stack.platform,workspace=workspace,redis=FakeRedis()))
    app.state.production_package_service=stack.service;app.state.publishing_service=publishing
    async def fail(*_):raise RuntimeError('explicit outer completion loss')
    monkeypatch.setattr(app.state.service_api_repository,'complete',fail)
    base='/v1/projects/'+stack.project.project_id
    try:
        async with stack.platform.session_factory() as session:
            before=await session.scalar(select(func.count()).select_from(ProductionRenderJobORM))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://explicit-atomic-fixture') as client:
            request=request_for(final.render_id).model_dump(mode='json')
            assert (await signed(client,'POST',base+'/publish',request,key='atomic-publication-fixture-key',extra=TEST_HUMAN_HEADERS)).status_code==409
            replay=await signed(client,'POST',base+'/publish',request,key='atomic-publication-fixture-key',extra=TEST_HUMAN_HEADERS)
            assert replay.status_code==201 and replay.json()['mode']=='dry_run' and replay.json()['external_action'] is False,replay.text
            payload={'expected_timeline_version':final.timeline_version,'expected_subtitle_version':final.subtitle_version,
                'expected_audio_version':final.audio_version,'approval_id':final.approval_id,'profile':'square-1080x1080'}
            assert (await signed(client,'POST',base+'/render',payload,key='atomic-render-fixture-key')).status_code==409
            queued=await signed(client,'POST',base+'/render',payload,key='atomic-render-fixture-key')
            assert queued.status_code==202 and queued.json()['status']=='queued',queued.text
        async with stack.platform.session_factory() as session:
            assert await session.scalar(select(func.count()).select_from(ProductionRenderJobORM))==before+1
            assert await session.scalar(select(func.count()).select_from(PublicationORM))==1
            assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==2
    finally:await stack.engine.dispose()
