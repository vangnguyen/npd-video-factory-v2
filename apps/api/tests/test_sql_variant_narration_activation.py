"""Actual SQLite/ASGI/queue with explicit synthetic PCM/render/QC, no AI wire."""
import asyncio
import copy
from pathlib import Path
import sys
from types import SimpleNamespace
import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, func
from app.db import AssetORM, ProviderUsageORM
from app.platform_models import WorkspaceCreate, ProjectCreate
from app.production_db import ProductionRenderJobORM, ProductionApprovalORM
from app.production_repository import ProductionRepository, ApprovalBoundaryError
from app.production_service import ProductionPackageService, ProductionRenderProcessor, DeterministicTimelineRenderEngine
from app.production_logic import TimelineRenderContractValidator
from app.production_qc import DeterministicProductionQC
from app.production_models import RenderCreateRequest, ApprovalRequest, ApprovalDecisionRequest, FinalRenderCreateRequest
from app.sql_variant_narration_runtime import create_variant_narration_runtime, register_variant_narration_routes
from app.sql_variant_narration_activation import NarrationReviewCreateRequest
from app.sql_variant_narration_models import NarrationReuseRequest
from app.sql_variant_narration_render import VariantNarrationRenderRequest
from app.sql_variant_repository import SqlVariantError
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_sql_variant_api import CountBody
from test_sql_variant_narration_reuse import env, narration_env
from test_sql_variant_narration_terminal import child_review
from test_audio_subtitle_render_qc import DeterministicAudioEngine
from test_mvp1_multi_input import ROOT


def factory(f, enabled=True, storage=None):
    runtime = create_variant_narration_runtime(session_factory=f.env.factory, object_storage=storage or f.env.storage,
        assets=f.env.assets, enabled=enabled)
    repository = ProductionRepository(f.env.factory, variant_narration_fence=runtime.fence,
        variant_narration_admission=runtime.admission)
    service = ProductionPackageService(repository=repository, timeline_repository=f.env.timeline,
        asset_repository=f.env.assets, queue=f.env.queue, settings=SimpleNamespace(audio_tts_provider='espeak'))
    return runtime, repository, service


def app_for(f, runtime, service, role='editor'):
    app = FastAPI();register_variant_narration_routes(app)
    app.state.sql_variant_narration_runtime = runtime;app.state.production_package_service = service
    install_test_human_auth(app, platform_repository=f.env.platform, platform_role=None,
        workspace_roles={f.env.workspace.workspace_id: role})
    return app


def base(f):
    return f'/api/v1/projects/{f.env.project.project_id}/variant-families/{f.family.family_id}/children/{f.child.project_id}'


def client(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-fixture', headers=TEST_HUMAN_HEADERS)


@pytest.fixture
async def active(narration_env):
    f=narration_env
    child=await child_review(f)  # Independently approved script/current rebuilt timeline; not Owner acceptance.
    runtime,repository,service=factory(f)
    value=await f.repo.input(f.env.workspace.workspace_id,f.env.project.project_id,f.family.family_id,child.receipt.receipt_id)
    request=NarrationReuseRequest.model_validate({**value['request'],'request_key':'actual-api-s5-explicit-import-01'})
    app=app_for(f,runtime,service)
    return SimpleNamespace(f=f,child=child,runtime=runtime,repository=repository,service=service,request=request,app=app)


async def imported(a):
    async with client(a.app) as c:
        result=await c.post(base(a.f)+'/narration-reuse',json=a.request.model_dump(mode='json'))
    assert result.status_code==201,result.text
    return result.json()['receipt']


def review_body(a, receipt):
    return NarrationReviewCreateRequest(expected_timeline_version=a.child.built.current_version,
        expected_subtitle_version=a.child.package.subtitle.version,expected_audio_version=a.child.package.audio_mix.version,
        profile='review-960x540', actor_ref='untrusted-body-actor',selection=VariantNarrationRenderRequest(enabled=True,
            receipt_id=receipt['receipt_id'],family_id=receipt['family_id'],member_id=receipt['member_id'],
            master_project_id=a.f.env.project.project_id,input_sha256=receipt['input_sha256'],result_sha256=receipt['result_sha256']))


def test_default_and_exact_storage_factory_are_pure_and_never_partial(monkeypatch):
    from app import sql_variant_narration_runtime as module
    def deny(*args,**kw):raise AssertionError('default/nonlocal cannot construct copy/SQL/provider')
    monkeypatch.setattr(module,'LocalNarrationCopier',deny)
    for enabled,storage in [(False,object()),(True,object())]:
        result=create_variant_narration_runtime(session_factory=deny,assets=object(),object_storage=storage,enabled=enabled)
        assert result.availability()['state']=='NOT_CONFIGURED' and result.loader is None and result.fence is None
    with pytest.raises(ValueError):create_variant_narration_runtime(session_factory=deny,assets=object(),object_storage=object(),enabled=1)


@pytest.mark.parametrize('denial,status',[('viewer',403),('no_token',401),('disabled',503),('foreign_child',404),('writes_off',503)])
async def test_dual_project_admission_precedes_private_body(active,denial,status):
    a=active
    if denial=='viewer':install_test_human_auth(a.app,platform_repository=a.f.env.platform,platform_role=None,workspace_roles={a.f.env.workspace.workspace_id:'viewer'})
    if denial=='disabled':a.app.state.sql_variant_narration_runtime=create_variant_narration_runtime(session_factory=a.f.env.factory,assets=a.f.env.assets,object_storage=a.f.env.storage)
    if denial=='writes_off':a.app.state.human_write_enabled=False
    endpoint=base(a.f)+'/narration-reuse'
    if denial=='foreign_child':
        wsp=await a.f.env.platform.create_workspace(WorkspaceCreate(slug='foreign-fixture',name='Foreign',owner_ref='fixture'))
        prj=await a.f.env.platform.create_project(wsp.workspace_id,ProjectCreate(slug='foreign',name='Foreign'))
        endpoint=endpoint.replace(a.f.child.project_id,prj.project_id)
    observed=CountBody(a.app)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(observed),base_url='http://owned-fixture') as c:
        response=await c.post(endpoint,content=b'{private malformed fixture',headers={} if denial=='no_token' else TEST_HUMAN_HEADERS)
    assert response.status_code==status,response.text
    assert observed.calls==0 and 'private' not in response.text and response.headers['cache-control']=='no-store'


async def test_actual_import_queue_pins_receipt_actor_before_handoff_and_get_never_dispatches(active,monkeypatch):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    a.f.env.queue.values.clear();seen=[]
    async def observe(key,render_id):
        row=await a.repository.get_render(render_id)
        assert row.manifest['variant_narration_request']==body.selection.model_dump(mode='json')
        assert row.manifest['variant_narration_admission']['actor_ref']=='usr:test-owner'
        assert row.manifest['variant_narration_handoff']['state']=='dispatching'
        seen.append(render_id)
    a.service.queue=SimpleNamespace(rpush=observe)
    async with client(a.app) as c:
        response=await c.post(base(a.f)+'/narration-review-render',json=body.model_dump(mode='json'))
        assert response.status_code==202,response.text
        again=await c.post(base(a.f)+'/narration-review-render',json=body.model_dump(mode='json'))
        assert again.status_code==202 and again.json()['render_id']==response.json()['render_id']
    assert seen==[response.json()['render_id']]
    assert again.json()['manifest']['requested_by']=='usr:test-owner'
    def deny(*args,**kw):raise AssertionError('GET cannot construct copier or download')
    from app import sql_variant_narration_runtime as module
    monkeypatch.setattr(module,'LocalNarrationCopier',deny);monkeypatch.setattr(a.f.env.storage,'download_file',deny)
    install_test_human_auth(a.app,platform_repository=a.f.env.platform,platform_role=None,workspace_roles={a.f.env.workspace.workspace_id:'viewer'})
    async with client(a.app) as c:
        read=await c.get(base(a.f)+'/narration-receipts/'+receipt['receipt_id'])
        available=await c.get(base(a.f)+'/narration-reuse-availability')
    assert read.status_code==200 and read.json()==receipt and available.json()['state']=='CONFIGURED'
    assert read.headers['cache-control']=='no-store' and len(seen)==1


async def test_ambiguous_queue_outcome_holds_same_render_and_never_replays(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt);calls=[]
    async def lost(*args):calls.append(args);raise OSError('PRIVATE queue transport fixture')
    a.service.queue=SimpleNamespace(rpush=lost)
    async with client(a.app) as c:
        first=await c.post(base(a.f)+'/narration-review-render',json=body.model_dump(mode='json'))
        retry=await c.post(base(a.f)+'/narration-review-render',json=body.model_dump(mode='json'))
    assert first.status_code==503 and 'PRIVATE' not in first.text
    assert retry.status_code==202 and retry.json()['manifest']['variant_narration_handoff']['state']=='unknown'
    assert len(calls)==1
    async with a.f.env.factory() as s:
        selected=[r for r in (await s.scalars(select(ProductionRenderJobORM).where(ProductionRenderJobORM.project_id==a.f.child.project_id))).all() if r.manifest_json.get('variant_narration_request')]
        assert len(selected)==1 and selected[0].status=='queued'
    assert await a.repository.start_render(retry.json()['render_id']) is None
    assert retry.json()['render_id'] not in await a.repository.filter_variant_recovery([retry.json()['render_id']])


@pytest.mark.parametrize('drift',['receipt','family','binding','version','partial','actor'])
async def test_selected_intent_drift_never_becomes_normal_provider_render(active,drift):
    a=active;receipt=await imported(a);body=review_body(a,receipt);raw=body.model_dump(mode='json')
    if drift=='receipt':raw['selection']['receipt_id']='missing-fixture'
    if drift=='family':raw['selection']['family_id']='vff_wrong_fixture'
    if drift=='binding':raw['selection']['result_sha256']='9'*64
    if drift=='version':raw['expected_audio_version']+=1
    if drift=='partial':a.service.repository=ProductionRepository(a.f.env.factory)
    if drift=='actor':
        await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='first-verified-editor')
    prior=len(a.f.env.queue.values)
    async with client(a.app) as c:response=await c.post(base(a.f)+'/narration-review-render',json=raw)
    assert response.status_code in {404,409,503},response.text
    assert len(a.f.env.queue.values)==prior


async def test_late_source_change_rolls_back_queued_selection_before_handoff(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt);event=a.repository._event
    async def changed(session,**kw):
        await event(session,**kw)
        source=await session.get(ProductionApprovalORM,a.f.request.source_approval_id)
        source.status='changes_requested';await session.flush()
    a.repository._event=changed
    before=len(a.f.env.queue.values)
    with pytest.raises(SqlVariantError):await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    assert len(a.f.env.queue.values)==before
    async with a.f.env.factory() as s:
        assert (await s.get(ProductionApprovalORM,a.f.request.source_approval_id)).status=='approved'
        assert not any(r.manifest_json.get('variant_narration_request') for r in (await s.scalars(select(ProductionRenderJobORM))).all())


async def test_worker_pair_and_actual_queue_fixture_review_final_never_synthesize(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    queued=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    assert await a.repository.filter_variant_recovery([queued.render_id])==[queued.render_id]
    calls=[]
    class PoisonTTS:
        async def synthesize(self,**kw):calls.append('TTS');raise AssertionError('No inference')
    class FixtureAudio(DeterministicAudioEngine):
        async def synthesize_narration(self,*args,**kw):calls.append('synth');raise AssertionError('No synthesis')
        async def synthesize_planned_narration(self,*args,**kw):calls.append('planned');raise AssertionError('No synthesis')
    await a.f.env.platform.seed_providers([{'provider_key':'explicit-fixture-tts','display_name':'Manual fixture','capability':'tts',
        'adapter':'manual-evidence','routing_mode':'primary','status':'healthy','enabled':True,'supports_dry_run':True,'metadata':{'paid':False,'fixture':True}}])
    processor=ProductionRenderProcessor(repository=a.repository,platform=a.f.env.platform,asset_repository=a.f.env.assets,
        object_storage=a.f.env.storage,renderer=DeterministicTimelineRenderEngine(),qc=DeterministicProductionQC(),
        tts_provider=PoisonTTS(),audio_engine=FixtureAudio(),manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=a.f.env.tmp/'explicit-render-fixture',brand_name='Fixture',variant_narration_loader=a.runtime.loader)
    sys.path.insert(0,str(ROOT/'services/worker'))
    from npd_worker.main import run_production_render_queue
    class Queue:
        count=0
        async def brpoplpush(self,*args,**kw):
            self.count+=1
            if self.count==1:return queued.render_id
            raise asyncio.CancelledError()
        async def lrem(self,*args):pass
    with pytest.raises(asyncio.CancelledError):await run_production_render_queue(Queue(),processor)
    reviewed=await a.repository.get_render(queued.render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    assert reviewed.manifest['variant_narration_admission']['actor_ref']=='usr:test-owner'
    assert (await processor.process(queued.render_id)).status=='awaiting_review'
    approval=await a.service.request_approval(a.f.child.project_id,ApprovalRequest(review_render_id=reviewed.render_id))
    approval=await a.service.decide_approval(a.f.child.project_id,approval.approval_id,ApprovalDecisionRequest(
        decision='approved',reviewer_ref='explicit-fixture-reviewer',comment='Fixture, not Owner/UAT'))
    final=await a.service.enqueue_final(a.f.child.project_id,FinalRenderCreateRequest(expected_timeline_version=body.expected_timeline_version,
        expected_subtitle_version=body.expected_subtitle_version,expected_audio_version=body.expected_audio_version,
        approval_id=approval.approval_id,profile='landscape-1920x1080'))
    finished=await processor.process(final.render_id)
    assert finished.status=='ready',finished.failure_reason
    assert finished.manifest['narration']['variant_narration_reuse']==reviewed.manifest['narration']['variant_narration_reuse']
    assert calls==[] and not finished.publishing_allowed
    assert finished.manifest['variant_narration_admission']['actor_ref']==final.manifest['requested_by']
    async with a.f.env.factory() as s:
        rows=(await s.scalars(select(ProviderUsageORM).where(ProviderUsageORM.project_id==a.f.child.project_id,ProviderUsageORM.capability=='tts'))).all()
        assert len(rows)==2 and all(r.metadata_json['provider_call_performed'] is False for r in rows)


async def test_recovery_holds_running_and_dispatching_without_mutating_active_source(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    queued=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    await a.repository.start_render(queued.render_id)
    assert await a.repository.filter_variant_recovery([queued.render_id])==[]
    assert (await a.repository.get_render(queued.render_id)).status=='running'
    async with a.f.env.factory() as s,s.begin():
        row=await s.get(ProductionRenderJobORM,queued.render_id)
        row.status='queued';row.manifest_json={**row.manifest_json,'variant_narration_handoff':{'state':'dispatching','token':'fixture'}}
    assert await a.repository.filter_variant_recovery([queued.render_id])==[]


async def test_second_cancel_drains_handoff_marker_and_same_intent_never_enqueues_again(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    entered=asyncio.Event();marked=asyncio.Event();release=asyncio.Event();calls=[]
    async def pending(*args):calls.append(args);entered.set();await asyncio.Event().wait()
    finish=a.repository.finish_variant_handoff
    async def slow_finish(*args,**kw):
        marked.set();await release.wait();return await finish(*args,**kw)
    a.service.queue=SimpleNamespace(rpush=pending);a.repository.finish_variant_handoff=slow_finish
    task=asyncio.create_task(a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner'))
    await entered.wait();task.cancel();await marked.wait();task.cancel();await asyncio.sleep(.03)
    assert not task.done();release.set()
    with pytest.raises(asyncio.CancelledError):await task
    a.repository.finish_variant_handoff=finish
    observed=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    assert observed.manifest['variant_narration_handoff']['state']=='unknown' and len(calls)==1


@pytest.mark.parametrize('malformed',['extra_proof','numeric_flag','duplicate'])
async def test_strict_body_never_accepts_arbitrary_manifest_or_coerced_authority(active,malformed):
    a=active;payload=a.request.model_dump(mode='json')
    if malformed=='extra_proof':payload['variant_narration_reuse']={'source_approval_transferred':True}
    if malformed=='numeric_flag':payload['enabled']=1
    async with client(a.app) as c:
        if malformed=='duplicate':
            response=await c.post(base(a.f)+'/narration-reuse',content=b'{"enabled":true,"enabled":false}',headers={'Content-Type':'application/json'})
        else:response=await c.post(base(a.f)+'/narration-reuse',json=payload)
    assert response.status_code==422


async def test_partial_host_pair_is_not_advertised_and_rejected_before_body(active):
    a=active;a.service.repository=ProductionRepository(a.f.env.factory)
    async with client(a.app) as c:available=await c.get(base(a.f)+'/narration-reuse-availability')
    assert available.json()['state']=='NOT_CONFIGURED'
    observed=CountBody(a.app)
    async with client(observed) as c:response=await c.post(base(a.f)+'/narration-reuse',content=b'{private body')
    assert response.status_code==503 and observed.calls==0


async def test_failed_selected_intent_is_observation_not_new_job_or_dispatch(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    first=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    await a.repository.fail_render(first.render_id,code='EXPLICIT_OUTCOME_UNKNOWN',reason='Fixture unknown renderer outcome')
    before=len(a.f.env.queue.values)
    observed=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    assert observed.render_id==first.render_id and observed.status=='failed' and len(a.f.env.queue.values)==before


async def test_worker_partial_pair_fails_before_source_storage_or_synthesis(active,monkeypatch):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    queued=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner');calls=[]
    def denied(*args,**kw):calls.append('wire');raise AssertionError('No source/provider/renderer IO')
    monkeypatch.setattr(a.f.env.storage,'download_file',denied)
    processor=ProductionRenderProcessor(repository=ProductionRepository(a.f.env.factory),platform=a.f.env.platform,
        asset_repository=a.f.env.assets,object_storage=a.f.env.storage,renderer=SimpleNamespace(render=denied),
        qc=SimpleNamespace(inspect=denied),tts_provider=SimpleNamespace(synthesize=denied),audio_engine=SimpleNamespace(),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=a.f.env.tmp/'not-created',brand_name='Fixture',variant_narration_loader=a.runtime.loader)
    result=await processor.process(queued.render_id)
    assert result.status=='failed' and 'NOT_CONFIGURED' in result.failure_reason
    assert calls==[] and not (a.f.env.tmp/'not-created').exists()


async def test_two_sql_repository_instances_share_one_pinned_render_and_handoff(active):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    from app.db import create_session_factory
    from app.auto_edit_repository import AutoEditRepository
    other_factory=create_session_factory(a.f.env.engine)
    runtime=create_variant_narration_runtime(session_factory=other_factory,object_storage=a.f.env.storage,
        assets=AutoEditRepository(other_factory),enabled=True)
    repository=ProductionRepository(other_factory,variant_narration_fence=runtime.fence,variant_narration_admission=runtime.admission)
    entered=asyncio.Event();release=asyncio.Event();calls=[]
    async def wire(*args):calls.append(args);entered.set();await release.wait()
    queue=SimpleNamespace(rpush=wire)
    a.service.queue=queue
    other=ProductionPackageService(repository=repository,timeline_repository=a.f.env.timeline,
        asset_repository=runtime.loader.assets,queue=queue,settings=a.service.settings)
    first=asyncio.create_task(a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner'))
    await asyncio.wait_for(entered.wait(),10)
    try:
        second=await asyncio.wait_for(other.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner'),10)
    finally:release.set()
    result=await first
    assert result.render_id==second.render_id and len(calls)==1
    assert result.manifest['variant_narration_handoff']['state']=='sent'


@pytest.mark.parametrize('terminal', ['failed', 'awaiting_review', 'ready'])
async def test_selected_terminal_commit_during_start_is_observed_without_io_or_mutation(active, monkeypatch, terminal):
    a=active;receipt=await imported(a);body=review_body(a,receipt)
    queued=await a.service.enqueue_variant_review(a.f.child.project_id,body,actor_ref='usr:test-owner')
    entered=asyncio.Event();release=asyncio.Event();original_start=a.repository.start_render;calls=[]
    async def paused_start(render_id):
        entered.set();await release.wait();return await original_start(render_id)
    monkeypatch.setattr(a.repository,'start_render',paused_start)
    def denied(*args,**kw):
        calls.append('IO');raise AssertionError('An authoritative terminal render cannot perform work')
    monkeypatch.setattr(a.repository,'assert_variant_admission',denied)
    monkeypatch.setattr(a.f.env.assets,'get_asset',denied)
    monkeypatch.setattr(a.f.env.storage,'download_file',denied)
    processor=ProductionRenderProcessor(repository=a.repository,platform=a.f.env.platform,
        asset_repository=a.f.env.assets,object_storage=a.f.env.storage,renderer=SimpleNamespace(render=denied),
        qc=SimpleNamespace(inspect=denied),tts_provider=SimpleNamespace(synthesize=denied),
        audio_engine=SimpleNamespace(mix=denied,synthesize_narration=denied,synthesize_planned_narration=denied),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=a.f.env.tmp/'terminal-not-created',brand_name='Explicit fixture',variant_narration_loader=a.runtime.loader)
    task=asyncio.create_task(processor.process(queued.render_id))
    await asyncio.wait_for(entered.wait(),10)
    try:
        if terminal=='failed':
            first=await a.repository.fail_render(queued.render_id,code='FIRST_WORKER_FIXTURE_FAILURE',
                reason='Independent SQL terminal commit while second start awaits')
        else:
            # The winning worker's terminal transaction is an explicit SQL fixture;
            # this exercises observation, not renderer/QC acceptance.
            async with a.f.env.factory() as session,session.begin():
                row=await session.get(ProductionRenderJobORM,queued.render_id)
                row.status=terminal;row.progress=100
                row.manifest_json={**row.manifest_json,'terminal_fixture_marker':terminal}
            first=await a.repository.get_render(queued.render_id)
        # Compare two SQL-hydrated snapshots: SQLite reloads datetimes without
        # tzinfo even when the just-committed Python object still carries UTC.
        first=await a.repository.get_render(queued.render_id)
        before=first.model_dump(mode='json')
        events=[e.model_dump(mode='json') for e in await a.repository.list_events(a.f.child.project_id)]
        async with a.f.env.factory() as session:
            usage=await session.scalar(select(func.count()).select_from(ProviderUsageORM))
    finally:
        release.set()
    result=await asyncio.wait_for(task,10)
    assert result.model_dump(mode='json')==before
    assert (await a.repository.get_render(queued.render_id)).model_dump(mode='json')==before
    assert [e.model_dump(mode='json') for e in await a.repository.list_events(a.f.child.project_id)]==events
    async with a.f.env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProviderUsageORM))==usage
    assert calls==[] and not (a.f.env.tmp/'terminal-not-created').exists()
