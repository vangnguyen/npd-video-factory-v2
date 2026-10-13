"""Actual SQL planner/resolver path with explicit HTTP and safety fixtures only."""
import asyncio
import json
import os
import subprocess
import sys
import uuid
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from test_media_intelligence import setup_media_stack, plan_request
from test_stock_media_providers import photo, video, PNG, MP4
from app.media_intelligence_service import MediaProviderBundle, MediaResolutionService
from app.media_intelligence_service import MEDIA_RESOLUTION_QUEUE_KEY, MEDIA_RESOLUTION_PROCESSING_KEY
from app.media_intelligence_models import MediaResolutionRequest
from app.media_intelligence_db import MediaResolutionJobORM
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_providers import DeterministicImageGenerationProvider, DeterministicVideoGenerationProvider
from app.provider_safety import ProviderExecutionReceipt
from app.stock_media_providers import PexelsStockMediaProvider
from app.stock_resolution_deferral import KEY, claim
from app.stock_resolution_deferral import CLAIM_SECONDS, defer, release_claim
from app.stock_wire_quota import StockWireQuotaGuard, StockWireQuotaRepository

NOW=1_800_000_000.0


class ExplicitSafetyFixture:
    """No live authorization: synthetic transport proof, false rights acceptance."""
    def __init__(self):self.executions=[]
    async def execute(self,context,operation):
        self.executions.append(context.operation_key)
        result=await operation()
        return SimpleNamespace(value=result,receipt=ProviderExecutionReceipt(operation_key=context.operation_key,
            provider_key=context.provider_key,capability=context.capability,status='succeeded',attempts=1,retries=0,
            charged_cost_vnd=0,circuit_state='closed',external_call=True,paid=False,rights_allowed=False))


async def prepared(tmp_path, mode):
    calls=[];clock=[NOW]
    def wire(request):
        calls.append((request.url.host,request.url.path))
        if request.url.path=='/v1/search':return httpx.Response(200,json={'photos':[photo()]})
        if request.url.path=='/v1/videos/search':return httpx.Response(200,json={'videos':[video()]})
        if request.url.host=='api.pexels.com':
            if mode.get('metadata_429'):return httpx.Response(429,headers={'Retry-After':'600'})
            return httpx.Response(200,json=photo() if '/photos/' in request.url.path else video(),
                headers={'X-RateLimit-Remaining':'0','X-RateLimit-Reset':str(int(NOW)+600)} if mode.get('zero_quota') else {})
        if mode.get('cdn_429'):return httpx.Response(429,headers={'Retry-After':'20'})
        return httpx.Response(200,content=PNG if request.url.host=='images.pexels.com' else MP4,
            headers={'Content-Type':'image/png' if request.url.host=='images.pexels.com' else 'video/mp4'})
    adapter=PexelsStockMediaProvider(api_key='explicit-pipeline-noncredential',enabled=True,cache_root=tmp_path/'cache',
        transport=httpx.MockTransport(wire))
    providers=MediaProviderBundle(stock=adapter,image=DeterministicImageGenerationProvider(),video=DeterministicVideoGenerationProvider())
    env=await setup_media_stack(tmp_path/'stack',providers)
    repository=StockWireQuotaRepository(env['session_factory']);await repository.ensure_state()
    adapter.wire_guard=StockWireQuotaGuard(repository,clock=lambda:clock[0]);adapter.require_wire_guard=True
    await env['platform'].seed_providers([{'provider_key':'pexels','display_name':'EXPLICIT STOCK PIPELINE FIXTURE',
        'capability':'stock_media','adapter':'http-mock','routing_mode':'primary','status':'healthy',
        'enabled':True,'supports_dry_run':True,'metadata':{'fixture':True,'real_provider_tested':False}}])
    env['planner'].allow_external_execution=True
    plan=await env['planner'].create(project_id=env['project'].project_id,payload=plan_request(env).model_copy(
        update={'selection_policy':'priority','resolver_priority':['licensed_stock']}))
    item=plan.items[0];job=await env['resolver'].enqueue(project_id=plan.project_id,media_plan_id=plan.media_plan_id,
        media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(candidate_id=item.candidates[0].candidate_id))
    safety=ExplicitSafetyFixture();env['resolver'].provider_safety=safety;env['resolver'].allow_external_execution=True
    return env,adapter,plan,job,safety,calls,clock,repository


@pytest.mark.asyncio
async def test_sql_resolution_cooldown_wait_survives_restart_without_safety_attempt_or_cost_and_recovers_when_due(tmp_path):
    mode={};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        mode['metadata_429']=True
        waiting=await env['resolver'].process(job.resolution_job_id)
        assert waiting.status=='queued' and waiting.error_code=='STOCK_RATE_LIMITED'
        assert waiting.provenance[KEY]['completed_wire_cycles']==1
        assert waiting.provenance[KEY]['next_at']==NOW+600
        assert len(safety.executions)==1
        count=len(calls)
        restarted=MediaResolutionService(repository=env['media_repository'],platform=env['platform'],
            auto_edit_repository=env['auto_repository'],object_storage=env['storage'],providers=env['resolver'].providers,
            queue=env['queue'],staging_root=tmp_path/'restarted',allow_external_execution=True,
            allow_paid_execution=False,provider_safety=safety)
        assert await restarted.process(job.resolution_job_id)==waiting
        assert len(calls)==count and len(safety.executions)==1
        assert job.resolution_job_id not in await env['media_repository'].list_incomplete_resolution_job_ids(now=NOW+599)
        assert job.resolution_job_id in await env['media_repository'].list_incomplete_resolution_job_ids(now=NOW+601)
        clock[0]=NOW+601;mode['metadata_429']=False
        completed=await restarted.process(job.resolution_job_id)
        assert completed.status=='succeeded' and completed.actual_cost_vnd is None
        assert safety.executions[0].endswith(':stock:1') and safety.executions[1].endswith(':stock:2')
        assert completed.provenance['stock_selected_candidate']==job.provenance['stock_selected_candidate']
        asset=await env['auto_repository'].get_asset((await env['media_repository'].get_plan(plan.media_plan_id)).media_assets[0].asset_id)
        assert asset.provenance['fixture'] is True and asset.provenance['production_eligible'] is False
        count=len(calls);assert await restarted.process(job.resolution_job_id)==completed and len(calls)==count
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_zero_wire_cdn_wait_does_not_spend_cycle_and_cached_metadata_can_pass_api_quota(tmp_path):
    mode={'zero_quota':True};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        mode['cdn_429']=True
        first=await env['resolver'].process(job.resolution_job_id)
        assert first.status=='queued' and first.provenance[KEY]['completed_wire_cycles']==1
        clock[0]=NOW+1
        repeated=await env['resolver'].process(job.resolution_job_id)
        assert repeated==first and len(safety.executions)==1
        clock[0]=NOW+21;mode['cdn_429']=False
        before=len(calls)
        completed=await env['resolver'].process(job.resolution_job_id)
        assert completed.status=='succeeded'
        assert len(calls)==before+1 and calls[-1][0]!='api.pexels.com'
        assert completed.actual_cost_vnd is None
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_global_cooldown_admission_defers_a_different_job_before_safety_exec_without_consuming_cycle(tmp_path):
    mode={};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        mode['metadata_429']=True;await env['resolver'].process(job.resolution_job_id)
        other_item=plan.items[1]
        other=await env['resolver'].enqueue(project_id=plan.project_id,media_plan_id=plan.media_plan_id,
            media_plan_item_id=other_item.media_plan_item_id,payload=MediaResolutionRequest(candidate_id=other_item.candidates[0].candidate_id))
        before=len(calls);result=await env['resolver'].process(other.resolution_job_id)
        assert result.status=='queued' and result.provenance[KEY]['completed_wire_cycles']==0
        assert result.provenance[KEY]['wait_history'][-1]['wire_attempts']==0
        assert len(calls)==before and len(safety.executions)==1
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_cancelled_job_wins_and_terminal_row_is_not_rewritten_by_claim_or_process(tmp_path):
    mode={};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        async with env['session_factory']() as session:
            await session.execute(update(MediaResolutionJobORM).where(MediaResolutionJobORM.resolution_job_id==job.resolution_job_id).values(status='cancelled'))
            await session.commit()
        cancelled=await env['media_repository'].get_resolution_job(job.resolution_job_id);before=len(calls)
        assert not (await claim(env['media_repository'],job.resolution_job_id,NOW)).allowed
        assert await env['resolver'].process(job.resolution_job_id)==cancelled
        assert len(calls)==before and safety.executions==[]
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_bounded_read_retries_stop_at_three_cycles_without_inventing_media_or_charges(tmp_path):
    mode={};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        mode['metadata_429']=True
        for cycle in range(3):
            clock[0]=NOW+cycle*601
            result=await env['resolver'].process(job.resolution_job_id)
        assert result.status=='failed' and result.error_code=='STOCK_WIRE_RETRY_EXHAUSTED'
        assert result.provenance[KEY]['completed_wire_cycles']==3 and len(safety.executions)==3
        assert result.output_media_asset_id is None and result.actual_cost_vnd is None
        assert len(set(safety.executions))==3
        before=len(calls);assert await env['resolver'].process(job.resolution_job_id)==result and len(calls)==before
    finally:await adapter.aclose();await env['engine'].dispose()


class AtomicQueueFixture:
    def __init__(self, values):
        self.values = list(values)
        self.scripts = []

    async def eval(self, script, keys, key, identifier):
        assert keys == 1 and key == MEDIA_RESOLUTION_QUEUE_KEY
        assert "'LREM'" in script and "'RPUSH'" in script
        assert MEDIA_RESOLUTION_PROCESSING_KEY not in script
        self.scripts.append((key, identifier))
        self.values = [(old_key, value) for old_key, value in self.values
            if (old_key, value) != (key, identifier)]
        self.values.append((key, identifier))


@pytest.mark.asyncio
async def test_periodic_recovery_only_requeues_due_unpaid_stock_waits_and_preserves_processing(tmp_path):
    env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,{})
    try:
        base_state={'schema_version':'sql-stock-wire-job.v1','completed_wire_cycles':0,
            'next_at':NOW-1,'claim_id':None,'lease_until':None,'wait_history':[]}
        cases={
            'due':{}, 'expired':{'status':'running','state':{**base_state,'next_at':None,'claim_id':'a'*32,'lease_until':NOW-1}},
            'future':{'state':{**base_state,'next_at':NOW+60}},
            'live':{'status':'running','state':{**base_state,'claim_id':'b'*32,'lease_until':NOW+60}},
            'paid':{'paid':True}, 'generation':{'capability':'video_generation','paid':True},
            'initial':{'state':None}, 'terminal':{'status':'cancelled'},
        }
        identifiers={}
        async with env['session_factory']() as session:
            row=await session.get(MediaResolutionJobORM,job.resolution_job_id)
            source={column.name:getattr(row,column.name) for column in MediaResolutionJobORM.__table__.columns}
            for label, overrides in cases.items():
                identity='mres_'+uuid.uuid4().hex;identifiers[label]=identity
                value=dict(source);value.update(resolution_job_id=identity,fingerprint=uuid.uuid4().hex+'a'*32,
                    status=overrides.get('status','queued'),paid=overrides.get('paid',False),
                    capability=overrides.get('capability','stock_media'))
                evidence=overrides.get('state',base_state)
                value['provenance_json']={**source['provenance_json']}
                if evidence is None:value['provenance_json'].pop(KEY,None)
                else:value['provenance_json'][KEY]=evidence
                session.add(MediaResolutionJobORM(**value))
            await session.commit()
        queue=AtomicQueueFixture([(MEDIA_RESOLUTION_QUEUE_KEY,identifiers['due'])]*2+
            [(MEDIA_RESOLUTION_PROCESSING_KEY,identifiers['expired']),('other:queue','unchanged')])
        env['resolver'].queue=queue
        before=len(calls)
        assert await env['resolver'].recover_due_stock()==2
        assert await env['resolver'].recover_due_stock()==2
        assert set(identifier for _,identifier in queue.scripts)=={identifiers['due'],identifiers['expired']}
        assert queue.values.count((MEDIA_RESOLUTION_QUEUE_KEY,identifiers['due']))==1
        assert queue.values.count((MEDIA_RESOLUTION_QUEUE_KEY,identifiers['expired']))==1
        assert (MEDIA_RESOLUTION_PROCESSING_KEY,identifiers['expired']) in queue.values
        assert ('other:queue','unchanged') in queue.values
        assert len(calls)==before and not safety.executions
        for label in ('paid','generation','future','live','initial','terminal'):
            assert identifiers[label] not in [identifier for _,identifier in queue.scripts]
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_cancel_while_safety_waits_prevents_wire_and_terminal_result_is_immutable(tmp_path):
    env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,{})
    entered=asyncio.Event();resume=asyncio.Event()
    class WaitingSafetyFixture(ExplicitSafetyFixture):
        async def execute(self,context,operation):
            entered.set();await resume.wait()
            return await super().execute(context,operation)
    env['resolver'].provider_safety=WaitingSafetyFixture()
    try:
        before=len(calls);task=asyncio.create_task(env['resolver'].process(job.resolution_job_id))
        await asyncio.wait_for(entered.wait(),5)
        async with env['session_factory']() as session:
            await session.execute(update(MediaResolutionJobORM).where(
                MediaResolutionJobORM.resolution_job_id==job.resolution_job_id).values(status='cancelled'))
            await session.commit()
        cancelled=await env['media_repository'].get_resolution_job(job.resolution_job_id)
        resume.set();assert await task==cancelled
        assert await env['media_repository'].get_resolution_job(job.resolution_job_id)==cancelled
        assert await env['resolver'].recover_due_stock()==0
        assert len(calls)==before and cancelled.output_media_asset_id is None
        assert cancelled.actual_cost_vnd is None
    finally:resume.set();await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_late_old_worker_failure_cannot_change_new_claim_or_completed_result(tmp_path):
    env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,{})
    entered=asyncio.Event();resume=asyncio.Event()
    class LateFailureSafetyFixture(ExplicitSafetyFixture):
        async def execute(self,context,operation):
            entered.set();await resume.wait()
            raise RuntimeError('explicit old worker failure before wire')
    env['resolver'].provider_safety=LateFailureSafetyFixture()
    second_engine=create_async_engine(env['engine'].url)
    second=MediaIntelligenceRepository(async_sessionmaker(second_engine,expire_on_commit=False))
    try:
        task=asyncio.create_task(env['resolver'].process(job.resolution_job_id))
        await asyncio.wait_for(entered.wait(),5)
        old=await env['media_repository'].get_resolution_job(job.resolution_job_id)
        old_claim=old.provenance[KEY]['claim_id']
        clock[0]=NOW+CLAIM_SECONDS+1
        replacement=await claim(second,job.resolution_job_id,clock[0]);assert replacement.allowed
        current=await second.get_resolution_job(job.resolution_job_id)
        resume.set();assert await task==current
        assert await second.get_resolution_job(job.resolution_job_id)==current
        assert not await env['media_repository'].mark_resolution_running(job.resolution_job_id,
            expected_stock_claim_id=old_claim)
        assert not await defer(env['media_repository'],job.resolution_job_id,old_claim,code='STOCK_PROVIDER_COOLDOWN',
            next_at=clock[0]+30,wire_attempts=0,stamp=clock[0])
        await release_claim(second,job.resolution_job_id,replacement.claim_id)
        env['resolver'].provider_safety=safety
        completed=await env['resolver'].process(job.resolution_job_id)
        assert completed.status=='succeeded'
        await env['media_repository'].mark_resolution_failed(job.resolution_job_id,error_code='OLD_FAILURE',
            reason='Late explicit fixture',expected_stock_claim_id=old_claim)
        assert await second.get_resolution_job(job.resolution_job_id)==completed
    finally:
        resume.set();await adapter.aclose();await second_engine.dispose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_cold_process_preserves_job_wait_and_provider_cooldown_without_wire(tmp_path):
    mode={};env,adapter,plan,job,safety,calls,clock,repository=await prepared(tmp_path,mode)
    try:
        mode['metadata_429']=True
        waiting=await env['resolver'].process(job.resolution_job_id)
        assert waiting.status=='queued'
        script='''
import asyncio,json,sys,httpx
from sqlalchemy.ext.asyncio import create_async_engine,async_sessionmaker
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.stock_media_providers import PexelsStockMediaProvider,stock_request_scope
from app.stock_wire_context import stock_wire_operation
from app.stock_wire_quota import StockWireQuotaRepository,StockWireQuotaGuard,StockWireDeferred
async def run():
    database,cache,job_id,workspace,project,stamp=sys.argv[1:]
    engine=create_async_engine(database);factory=async_sessionmaker(engine,expire_on_commit=False)
    media=MediaIntelligenceRepository(factory);repo=StockWireQuotaRepository(factory)
    calls=[]
    def denied(request):
        calls.append(request.url.host)
        raise AssertionError('DeniedWire: cold child must not call a provider')
    adapter=PexelsStockMediaProvider(api_key='explicit-pipeline-noncredential',enabled=True,
        cache_root=__import__('pathlib').Path(cache),transport=httpx.MockTransport(denied),
        wire_guard=StockWireQuotaGuard(repo,clock=lambda:float(stamp)),require_wire_guard=True)
    try:
        row=await media.get_resolution_job(job_id)
        due=await media.list_due_stock_resolution_job_ids(now=float(stamp))
        with stock_request_scope(workspace),stock_wire_operation(workspace_id=workspace,project_id=project,
                source_ref='cold-explicit-stock-fixture',budget_sha256='b'*64):
            try:await adapter.search_images('not-cached-cold-fixture',orientation='any',limit=1)
            except StockWireDeferred as wait:
                print(json.dumps({'status':row.status,'next_at':row.provenance['stock_wire_execution']['next_at'],
                    'due':job_id in due,'wire_calls':len(calls),'provider_next_at':wait.next_at}))
            else:raise AssertionError('durable provider cooldown was lost')
    finally:await adapter.aclose();await engine.dispose()
asyncio.run(run())
'''
        arguments=[sys.executable,'-c',script,str(env['engine'].url),str(adapter.cache_root),
            job.resolution_job_id,plan.workspace_id,plan.project_id,str(NOW+1)]
        completed=await asyncio.to_thread(subprocess.run,arguments,capture_output=True,text=True,
            timeout=45,check=False,env=os.environ.copy())
        assert completed.returncode==0,completed.stderr
        observed=json.loads(completed.stdout)
        assert observed=={'status':'queued','next_at':NOW+600,'due':False,'wire_calls':0,'provider_next_at':NOW+600}
        assert await env['media_repository'].get_resolution_job(job.resolution_job_id)==waiting
    finally:await adapter.aclose();await env['engine'].dispose()
