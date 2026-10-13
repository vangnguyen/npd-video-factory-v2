"""Actual SQL planner/API jobs; explicit mock HTTP, never a real credential."""
import asyncio
import copy
import json
import os
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal
import httpx
import pytest
from sqlalchemy import update, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_media_intelligence import setup_media_stack, plan_request
from test_stock_media_providers import photo, video
from app.main import app
from app.media_intelligence_service import MediaProviderBundle, MediaPlanningService
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_db import MediaPlanORM
from app.db import ProviderUsageORM, CostRecordORM
from app.media_intelligence_providers import (ContractOnlyImageGenerationProvider, ContractOnlyVideoGenerationProvider,
    ContractOnlyStockMediaProvider)
from app.stock_media_providers import PexelsStockMediaProvider
from app.stock_wire_quota import StockWireQuotaRepository, StockWireQuotaGuard
from app.stock_planner_models import StockPlannerAction
from app import stock_planner_retry as retry
from app.auto_edit_db import TranscriptSegmentORM
from app.vision_db import VisionAnalysisORM

NOW = 1_800_000_000.0


async def prepared(tmp_path, mode):
    calls = [];stamp = [NOW]
    async def wire(request):
        calls.append((request.url.path, str(request.url.query)))
        if mode.get('pause'):
            mode['entered'].set();await mode['resume'].wait()
        fail = mode.get('all_429') or mode.get('after_first') and len(calls) > 1
        if fail:
            return httpx.Response(429, headers={'Retry-After':'60'})
        return httpx.Response(200, json={'photos':[photo()]} if request.url.path == '/v1/search' else {'videos':[video()]},
            headers={'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(int(NOW)+60)} if mode.get('quota_zero') else {})
    adapter = PexelsStockMediaProvider(api_key='explicit-planner-noncredential', enabled=True,
        cache_root=tmp_path/'cache', transport=httpx.MockTransport(wire))
    providers = MediaProviderBundle(stock=adapter, image=ContractOnlyImageGenerationProvider(), video=ContractOnlyVideoGenerationProvider())
    env = await setup_media_stack(tmp_path/'stack', providers)
    quota = StockWireQuotaRepository(env['session_factory']);await quota.ensure_state()
    adapter.wire_guard = StockWireQuotaGuard(quota, clock=lambda:stamp[0]);adapter.require_wire_guard = True
    await env['platform'].seed_providers([{'provider_key':'pexels','display_name':'EXPLICIT MOCK STOCK PLANNER',
        'capability':'stock_media','adapter':'http-mock','routing_mode':'primary','status':'healthy',
        'enabled':True,'supports_dry_run':True,'metadata':{'fixture':True,'real_provider_tested':False}}])
    env['planner'].allow_external_execution = True;env['planner'].object_storage = env['storage']
    payload = plan_request(env).model_copy(update={'resolver_priority':['licensed_stock'],
        'selection_policy':'priority','allow_ai_image':False,'allow_ai_video':False})
    return env, adapter, payload, calls, stamp


def action(plan):
    return StockPlannerAction(expected_version=plan.version, binding_sha256=plan.stock_planning.binding_sha256)


@pytest.mark.asyncio
async def test_partial_results_resume_same_plan_without_replacing_history_or_consuming_zero_wire_wait(tmp_path):
    mode={'after_first':True};env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    try:
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        assert plan.status=='stock_waiting' and plan.stock_planning.completed_searches==1
        assert plan.items==[] and plan.stock_planning.provider_calls==2
        assert sum(plan.stock_planning.failed_wire_cycles.values())==1
        history=await env['planner'].stock_search_history(plan.media_plan_id)
        frozen=copy.deepcopy(retry.state(plan.provenance)['results'])
        count=len(calls);costs=await env['platform'].list_cost_records(plan.project_id)
        assert await env['planner'].retry_stock_search(plan.media_plan_id,action(plan))==plan
        assert await env['planner'].recover_due_stock_plans()==0
        assert len(calls)==count and await env['platform'].list_cost_records(plan.project_id)==costs
        stamp[0]=NOW+61;mode['after_first']=False
        assert await env['planner'].recover_due_stock_plans()==1
        completed=await env['planner'].get(plan.media_plan_id)
        assert completed.status=='draft' and completed.stock_planning.status=='succeeded' and len(completed.items)==4
        assert completed.media_plan_id==plan.media_plan_id and completed.version>plan.version
        for scene,result in frozen.items():assert retry.state(completed.provenance)['results'][scene]==result
        later=await env['planner'].stock_search_history(plan.media_plan_id)
        assert later[:len(history)]==history and later[-1].action=='completed'
        assert all(event.evidence['after']['version']==event.version for event in later)
        assert all(candidate.provenance['fixture'] and not candidate.production_eligible for item in completed.items for candidate in item.candidates)
        assert completed.stock_planning.actual_cost_vnd is None and completed.paid_external_call is False
        count=len(calls);assert await env['planner'].process_stock_plan(plan.media_plan_id)==completed and len(calls)==count
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_global_quota_zero_wire_wait_and_three_real_failure_cycles_are_bounded(tmp_path):
    mode={'all_429':True};env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    try:
        first=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        second=await env['planner'].create(project_id=env['project'].project_id,payload=payload.model_copy(update={'brand_context':'second explicit fixture'}))
        assert second.stock_planning.provider_calls==0 and second.stock_planning.failed_wire_cycles=={}
        assert second.stock_planning.status=='waiting' and len(calls)==1
        async with env['session_factory']() as session:
            usages=(await session.scalars(select(ProviderUsageORM).where(
                ProviderUsageORM.operation.like('stock-planner:%')))).all()
            assert len(usages)==1 and usages[0].status=='failed' and usages[0].metadata_json['paid'] is False
            cost=await session.scalar(select(CostRecordORM).where(CostRecordORM.provider_usage_id==usages[0].usage_id))
            assert cost.actual_cost is None and cost.estimated_cost==0
        assert (await env['planner'].stock_search_history(second.media_plan_id))[-1].evidence['details']['retry_cycle_consumed'] is False
        for index in (1,2):
            stamp[0]=NOW+index*61
            first=await env['planner'].process_stock_plan(first.media_plan_id)
        assert first.status=='failed' and first.stock_planning.error_code=='STOCK_PLANNER_RETRY_EXHAUSTED'
        assert first.stock_planning.provider_calls==3 and sum(first.stock_planning.failed_wire_cycles.values())==3
        assert first.items==[] and first.media_assets==[] and first.resolution_jobs==[]
        count=len(calls);assert await env['planner'].process_stock_plan(first.media_plan_id)==first and len(calls)==count
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('changed',['source_bytes','transcript','vision','provider','budget'])
async def test_changed_frozen_inputs_fail_closed_before_provider_wire(tmp_path,changed):
    mode={'all_429':True};env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    try:
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        if changed=='source_bytes':
            asset=await env['auto_repository'].get_asset(env['source_asset'].asset_id)
            (env['storage'].root/asset.object_key).write_bytes(b'EXPLICIT MUTATED OWNED SOURCE FIXTURE')
        elif changed=='provider':
            env['planner'].providers=replace(env['planner'].providers,stock=PexelsStockMediaProvider(
                api_key='explicit-rotated-noncredential',enabled=True,cache_root=adapter.cache_root,
                transport=httpx.MockTransport(lambda request: (_ for _ in ()).throw(AssertionError('DeniedWire'))),
                wire_guard=adapter.wire_guard,require_wire_guard=True))
        else:
            async with env['session_factory']() as session:
                if changed=='transcript':await session.execute(update(TranscriptSegmentORM).where(
                    TranscriptSegmentORM.transcript_id==env['auto_edit'].transcript.transcript_id).values(text='Explicit changed transcript'))
                elif changed=='vision':await session.execute(update(VisionAnalysisORM).where(
                    VisionAnalysisORM.vision_analysis_id==env['vision'].vision_analysis_id).values(fingerprint='b'*64))
                else:
                    row=await session.get(MediaPlanORM,plan.media_plan_id)
                    row.configuration_json={**row.configuration_json,'max_ai_cost_vnd':'1'}
                await session.commit()
        stamp[0]=NOW+61;mode['all_429']=False;count=len(calls)
        result=await env['planner'].process_stock_plan(plan.media_plan_id)
        assert result.status=='failed' and result.stock_planning.error_code.startswith('STOCK_PLANNER_')
        assert len(calls)==count and result.items==[] and result.stock_planning.provider_calls==1
    finally:
        if env['planner'].providers.stock is not adapter:await env['planner'].providers.stock.aclose()
        await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_cancel_and_new_worker_claim_fence_late_old_search_result(tmp_path):
    mode={'pause':True,'entered':asyncio.Event(),'resume':asyncio.Event()}
    env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    second_engine=create_async_engine(env['engine'].url)
    other=MediaIntelligenceRepository(async_sessionmaker(second_engine,expire_on_commit=False))
    try:
        task=asyncio.create_task(env['planner'].create(project_id=env['project'].project_id,payload=payload))
        await asyncio.wait_for(mode['entered'].wait(),10)
        running=(await env['planner'].list(env['project'].project_id))[0]
        old=retry.state(running.provenance)['claim_id']
        stamp[0]=NOW+retry.LEASE_SECONDS+1
        new=await retry.claim(other,running.media_plan_id,stamp[0]);assert new and new!=old
        new_state=await other.get_plan(running.media_plan_id)
        assert not await retry.fail(env['media_repository'],running.media_plan_id,old,'LATE_OLD_ERROR')
        assert not await retry.checkpoint(env['media_repository'],running.media_plan_id,old,
            env['auto_edit'].scenes[0].scene_id,[],1)
        assert await other.get_plan(running.media_plan_id)==new_state
        cancelled=await env['planner'].cancel_stock_search(running.media_plan_id,action(new_state))
        assert cancelled.status=='cancelled'
        mode['resume'].set();assert await task==cancelled
        assert await other.get_plan(running.media_plan_id)==cancelled and len(calls)==1
        assert await env['planner'].recover_due_stock_plans()==0
    finally:mode['resume'].set();await adapter.aclose();await second_engine.dispose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_source_changed_while_one_search_is_inflight_prevents_all_later_searches(tmp_path):
    mode={'pause':True,'entered':asyncio.Event(),'resume':asyncio.Event()}
    env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    try:
        task=asyncio.create_task(env['planner'].create(project_id=env['project'].project_id,payload=payload))
        await asyncio.wait_for(mode['entered'].wait(),10)
        asset=await env['auto_repository'].get_asset(env['source_asset'].asset_id)
        (env['storage'].root/asset.object_key).write_bytes(b'EXPLICIT OWNED SOURCE MUTATED DURING FIRST SEARCH')
        mode['resume'].set();result=await task
        assert len(calls)==1 and result.stock_planning.provider_calls==1
        assert result.stock_planning.completed_searches==1 and result.items==[]
        assert result.status=='failed' and result.error_code=='STOCK_PLANNER_SOURCE_FILE_CHANGED'
        history=await env['planner'].stock_search_history(result.media_plan_id)
        assert [event.action for event in history][-2:]==['search_checkpointed','failed']
        count=len(calls);assert await env['planner'].process_stock_plan(result.media_plan_id)==result and len(calls)==count
    finally:mode['resume'].set();await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_transcript_edit_during_awaited_source_verification_prevents_first_wire(tmp_path):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{})
    entered=asyncio.Event();resume=asyncio.Event();actual=env['storage']
    class WaitingStorageFixture:
        name=actual.name
        async def download_file(self, *, object_key, destination, max_bytes=None,
                expected_size_bytes=None, expected_sha256=None, expected_prefix=None):
            await actual.download_file(object_key=object_key,destination=destination,max_bytes=max_bytes,
                expected_size_bytes=expected_size_bytes,expected_sha256=expected_sha256,expected_prefix=expected_prefix)
            entered.set();await resume.wait()
    env['planner'].object_storage=WaitingStorageFixture()
    try:
        task=asyncio.create_task(env['planner'].create(project_id=env['project'].project_id,payload=payload))
        await asyncio.wait_for(entered.wait(),10)
        async with env['session_factory']() as session:
            await session.execute(update(TranscriptSegmentORM).where(
                TranscriptSegmentORM.transcript_id==env['auto_edit'].transcript.transcript_id).values(text='Explicit edit during source check'))
            await session.commit()
        resume.set();result=await task
        assert result.status=='failed' and result.error_code=='STOCK_PLANNER_SOURCE_CHANGED'
        assert not calls and result.stock_planning.provider_calls==0 and result.items==[]
    finally:resume.set();await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_api_scheduled_202_read_history_stale_and_viewer_cannot_retry_or_cancel(tmp_path):
    mode={'all_429':True};env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    app.state.media_planning_service=env['planner'];app.state.media_resolution_service=env['resolver']
    install_test_human_auth(app,platform_repository=env['platform'])
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',headers=TEST_HUMAN_HEADERS) as client:
            base=f"/api/v1/projects/{env['project'].project_id}/media-plans"
            response=await client.post(base,json=payload.model_dump(mode='json'))
            assert response.status_code==202,response.text
            plan=response.json();endpoint=base+'/'+plan['media_plan_id']+'/stock-search'
            assert plan['status']=='stock_waiting' and plan['stock_planning']['actual_cost_vnd'] is None
            assert (await client.get(endpoint)).json()==plan['stock_planning']
            history=await client.get(endpoint+'/history');assert history.status_code==200 and history.json()
            body={'expected_version':plan['version'],'binding_sha256':plan['stock_planning']['binding_sha256']}
            unchanged=await client.post(endpoint+'/retry',json=body)
            assert unchanged.status_code==202 and unchanged.json()==plan and len(calls)==1
            stale=await client.post(endpoint+'/cancel',json={**body,'expected_version':1})
            assert stale.status_code==409
            install_test_human_auth(app,platform_repository=env['platform'],platform_role=None,
                workspace_roles={env['project'].workspace_id:'viewer'})
            assert (await client.get(endpoint)).status_code==200
            assert (await client.post(endpoint+'/retry',json=body)).status_code==403
            assert (await client.post(endpoint+'/cancel',json=body)).status_code==403
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('later_transition', ['deferred', 'cancelled'])
async def test_http_review_race_is_fenced_inside_claim_before_any_new_wire(tmp_path, monkeypatch, later_transition):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{'all_429':True})
    second_engine=create_async_engine(env['engine'].url)
    other=MediaIntelligenceRepository(async_sessionmaker(second_engine,expire_on_commit=False))
    original_claim=retry.claim
    entered=asyncio.Event();resume=asyncio.Event();request_task=None
    try:
        reviewed=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        stamp[0]=NOW+61
        # Stop the HTTP request after its prior reads, just before the locked
        # claim. Another actual database instance changes the reviewed version.
        async def paused_claim(repository, identity, current_stamp, **review):
            assert review['expected_version']==reviewed.version
            assert review['binding_sha256']==reviewed.stock_planning.binding_sha256
            entered.set();await resume.wait()
            return await original_claim(repository,identity,current_stamp,**review)
        monkeypatch.setattr(retry,'claim',paused_claim)
        app.state.media_planning_service=env['planner'];app.state.media_resolution_service=env['resolver']
        install_test_human_auth(app,platform_repository=env['platform'])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test',
                                    headers=TEST_HUMAN_HEADERS) as client:
            endpoint=f"/api/v1/projects/{reviewed.project_id}/media-plans/{reviewed.media_plan_id}/stock-search/retry"
            request_task=asyncio.create_task(client.post(endpoint,json=action(reviewed).model_dump(mode='json')))
            await asyncio.wait_for(entered.wait(),10)
            other_claim=await original_claim(other,reviewed.media_plan_id,stamp[0])
            assert other_claim
            running=await other.get_plan(reviewed.media_plan_id)
            execution=retry.state(running.provenance)
            if later_transition=='deferred':
                assert await retry.wait(other,reviewed.media_plan_id,other_claim,
                    scene_id=execution['binding']['searches'][0]['scene_id'],code='STOCK_PROVIDER_GLOBAL_WAIT',
                    next_at=stamp[0],calls=0,stamp=stamp[0])
            else:
                await retry.cancel(other,reviewed.media_plan_id,running.version,running.stock_planning.binding_sha256)
            changed=await other.get_plan(reviewed.media_plan_id)
            history=await retry.history(other,reviewed.media_plan_id)
            costs=await env['platform'].list_cost_records(reviewed.project_id)
            wires=len(calls)
            resume.set();response=await asyncio.wait_for(request_task,20)
            assert response.status_code==409,response.text
            assert response.json()['detail']['error']['code']=='STOCK_PLANNER_REVIEW_STALE'
            assert len(calls)==wires and changed.version>reviewed.version
            assert await other.get_plan(reviewed.media_plan_id)==changed
            assert await retry.history(other,reviewed.media_plan_id)==history
            assert await env['platform'].list_cost_records(reviewed.project_id)==costs
    finally:
        resume.set()
        if request_task is not None and not request_task.done():
            request_task.cancel();await asyncio.gather(request_task,return_exceptions=True)
        await adapter.aclose();await second_engine.dispose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_reviewed_disabled_provider_checks_atomic_version_without_claim_or_dispatch(tmp_path):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{'all_429':True})
    try:
        reviewed=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        history=await env['planner'].stock_search_history(reviewed.media_plan_id)
        wires=len(calls);stamp[0]=NOW+61
        env['planner'].providers=replace(env['planner'].providers,stock=ContractOnlyStockMediaProvider())
        assert await env['planner'].retry_stock_search(reviewed.media_plan_id,action(reviewed))==reviewed
        assert await env['planner'].process_stock_plan(reviewed.media_plan_id)==reviewed
        assert await env['planner'].stock_search_history(reviewed.media_plan_id)==history and len(calls)==wires
        with pytest.raises(retry.StockPlannerConflict,match='STOCK_PLANNER_REVIEW_STALE'):
            await retry.claim(env['media_repository'],reviewed.media_plan_id,stamp[0],allow_claim=False,
                expected_version=reviewed.version,binding_sha256='b'*64)
        with pytest.raises(ValueError,match='STOCK_PLANNER_REVIEW_INVALID'):
            await retry.claim(env['media_repository'],reviewed.media_plan_id,stamp[0],expected_version=reviewed.version)
        assert await env['planner'].stock_search_history(reviewed.media_plan_id)==history and len(calls)==wires
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_successful_quota_zero_keeps_prior_results_and_waits_without_failed_cycle(tmp_path):
    mode={'quota_zero':True};env,adapter,payload,calls,stamp=await prepared(tmp_path,mode)
    try:
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        assert plan.status=='stock_waiting' and plan.stock_planning.completed_searches==1
        assert plan.stock_planning.provider_calls==1 and plan.stock_planning.failed_wire_cycles=={}
        assert plan.stock_planning.next_at==NOW+60 and len(calls)==1
        frozen=copy.deepcopy(retry.state(plan.provenance)['results'])
        stamp[0]=NOW+61;mode['quota_zero']=False
        assert await env['planner'].recover_due_stock_plans()==1
        result=await env['planner'].get(plan.media_plan_id)
        assert result.stock_planning.status=='succeeded'
        for scene,value in frozen.items():assert retry.state(result.provenance)['results'][scene]==value
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_missing_source_storage_is_not_configured_and_cannot_dispatch_stock(tmp_path):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{})
    try:
        env['planner'].object_storage=None
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        assert plan.status=='failed' and plan.stock_planning.error_code=='STOCK_PLANNER_SOURCE_STORAGE_NOT_CONFIGURED'
        assert plan.stock_planning.provider_calls==0 and not calls
        assert await env['planner'].recover_due_stock_plans()==0
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_cold_process_preserves_schedule_source_binding_and_history_without_wire(tmp_path):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{'all_429':True})
    try:
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=payload)
        history=await env['planner'].stock_search_history(plan.media_plan_id)
        script='''
import asyncio,json,sys,httpx
from pathlib import Path
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.auto_edit_repository import AutoEditRepository
from app.vision_repository import VisionRepository
from app.repositories import PlatformRepository
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_service import MediaPlanningService,MediaProviderBundle
from app.media_intelligence_providers import ContractOnlyImageGenerationProvider,ContractOnlyVideoGenerationProvider
from app.object_storage import LocalObjectStorageProvider
from app.stock_media_providers import PexelsStockMediaProvider
from app.stock_wire_quota import StockWireQuotaRepository,StockWireQuotaGuard
async def run():
    database,cache,objects,identity,stamp=sys.argv[1:]
    engine=create_async_engine(database);factory=async_sessionmaker(engine,expire_on_commit=False)
    calls=[]
    def denied(request):
        calls.append(request.url.host);raise AssertionError('DeniedWire cold planner')
    stock=PexelsStockMediaProvider(api_key='explicit-planner-noncredential',enabled=True,cache_root=Path(cache),
        transport=httpx.MockTransport(denied),wire_guard=StockWireQuotaGuard(StockWireQuotaRepository(factory),
        clock=lambda:float(stamp)),require_wire_guard=True)
    service=MediaPlanningService(repository=MediaIntelligenceRepository(factory),auto_edit_repository=AutoEditRepository(factory),
        vision_repository=VisionRepository(factory),platform=PlatformRepository(factory),
        providers=MediaProviderBundle(stock=stock,image=ContractOnlyImageGenerationProvider(),video=ContractOnlyVideoGenerationProvider()),
        allow_external_execution=True,allow_paid_execution=False,object_storage=LocalObjectStorageProvider(Path(objects)))
    try:
        plan=await service.process_stock_plan(identity)
        due=await service.recover_due_stock_plans()
        history=await service.stock_search_history(identity)
        print(json.dumps({'status':plan.status,'binding_sha256':plan.stock_planning.binding_sha256,
            'next_at':plan.stock_planning.next_at,'due':due,'wire_calls':len(calls),'history_hashes':[event.sha256 for event in history]}))
    finally:await stock.aclose();await engine.dispose()
asyncio.run(run())
'''
        arguments=[sys.executable,'-c',script,str(env['engine'].url),str(adapter.cache_root),str(env['storage'].root),
            plan.media_plan_id,str(NOW+1)]
        completed=await asyncio.to_thread(subprocess.run,arguments,capture_output=True,text=True,
            timeout=45,env=os.environ.copy())
        assert completed.returncode==0,completed.stderr
        assert json.loads(completed.stdout)=={'status':'stock_waiting','binding_sha256':plan.stock_planning.binding_sha256,
            'next_at':NOW+60,'due':0,'wire_calls':0,'history_hashes':[event.sha256 for event in history]}
        assert await env['planner'].get(plan.media_plan_id)==plan
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_truthful_failed_read_usage_is_idempotent_and_cannot_modify_paid_flow(tmp_path):
    env,adapter,payload,calls,stamp=await prepared(tmp_path,{})
    try:
        arguments={'workspace_id':env['project'].workspace_id,'project_id':env['project'].project_id,'job_id':None,
            'provider_key':'pexels','capability':'stock_media','operation':'explicit-failed-read-fixture',
            'estimated_cost':Decimal('0'),'actual_cost':None,
            'metadata':{'external_call':True,'paid':False,'fixture':True}}
        first=await env['platform'].record_provider_operation(**arguments,status='failed')
        assert first[0].status=='failed' and first[1].actual_cost is None
        # SQLite removes timezone information on reload; compare durable rows,
        # and use the reloaded DTO for subsequent idempotency checks.
        async with env['session_factory']() as session:
            before_usage=(await session.execute(select(ProviderUsageORM.__table__).where(
                ProviderUsageORM.usage_id==first[0].usage_id))).one()._asdict()
            before_cost=(await session.execute(select(CostRecordORM.__table__).where(
                CostRecordORM.cost_id==first[1].cost_id))).one()._asdict()
        reloaded=await env['platform'].record_provider_operation(**arguments,status='failed')
        assert reloaded[0].usage_id==first[0].usage_id and reloaded[1].cost_id==first[1].cost_id
        assert await env['platform'].record_provider_operation(**arguments)==reloaded
        with pytest.raises(ValueError,match='unpaid external'):
            await env['platform'].record_provider_operation(**{**arguments,'operation':'explicit-paid-fixture',
                'metadata':{'external_call':True,'paid':True}},status='failed')
        with pytest.raises(ValueError,match='unsupported'):
            await env['platform'].record_provider_operation(**arguments,status='unknown')
        async with env['session_factory']() as session:
            assert (await session.execute(select(ProviderUsageORM.__table__).where(
                ProviderUsageORM.usage_id==first[0].usage_id))).one()._asdict()==before_usage
            assert (await session.execute(select(CostRecordORM.__table__).where(
                CostRecordORM.cost_id==first[1].cost_id))).one()._asdict()==before_cost
        assert not calls
    finally:await adapter.aclose();await env['engine'].dispose()
