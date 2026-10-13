"""Actual frozen MediaPlan/SQL source reads, mock SDK, no stock search/generation."""
import asyncio
import copy
import threading

import httpx
import pytest

from app.db import AssetORM
from app.media_intelligence_models import MediaPlanRequest
from app.media_intelligence_providers import ContractOnlyImageGenerationProvider,ContractOnlyVideoGenerationProvider
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_service import MediaPlanningService,MediaProviderBundle
from app.stock_media_providers import PexelsStockMediaProvider
from app.stock_wire_quota import StockWireQuotaRepository,StockWireQuotaGuard
from app import stock_planner_retry as retry
from app.vision_repository import VisionRepository
from app.frozen_storage_read import MAX_SOURCE_BYTES
from test_bounded_service_sources import source
from test_bounded_storage_consumers import RecordingStorage,assert_frozen
from test_bounded_storage_download import fake_s3,Body
from test_auto_edit_analysis import synthetic_mp4


@pytest.fixture
async def planner(source,request):
    calls=[]
    def denied(request):calls.append(str(request.url));raise AssertionError('Read admission cannot search stock')
    stock=PexelsStockMediaProvider(api_key='explicit-test-noncredential',enabled=True,
        cache_root=source.tmp/'stock-cache',transport=httpx.MockTransport(denied))
    quota=StockWireQuotaRepository(source.sessions);await quota.ensure_state()
    stock.wire_guard=StockWireQuotaGuard(quota,clock=lambda:1_800_000_000.)
    stock.require_wire_guard=True
    if getattr(request,'param','local')=='s3':
        async with source.sessions() as session,session.begin():
            row=await session.get(AssetORM,source.asset.asset_id);row.storage_provider='s3'
        source.asset=await source.repo.get_asset(source.asset.asset_id)
    repository=MediaIntelligenceRepository(source.sessions)
    service=MediaPlanningService(repository=repository,auto_edit_repository=source.repo,
        vision_repository=VisionRepository(source.sessions),platform=source.platform,
        providers=MediaProviderBundle(stock=stock,image=ContractOnlyImageGenerationProvider(),video=ContractOnlyVideoGenerationProvider()),
        allow_external_execution=True,allow_paid_execution=False,object_storage=source.uploads.object_storage)
    async def hold(media_plan_id,**kwargs):return await repository.get_plan(media_plan_id)
    service.process_stock_plan=hold
    configuration=MediaPlanRequest(analysis_id=source.base.analysis_id,platform='facebook_reels',
        brand_context='Explicit fixture only',resolver_priority=['licensed_stock'],selection_policy='priority',
        allow_ai_image=False,allow_ai_video=False)
    plan=await service.create(project_id=source.project.project_id,payload=configuration)
    execution=retry.state(plan.provenance);assert execution is not None and len(execution['binding']['searches'])==1
    yield source,service,plan,execution['binding'],calls
    assert not calls and source.asr.calls==source.signals.calls==0


@pytest.mark.asyncio
async def test_frozen_stock_source_uses_counted_read_without_claim_search_or_history_rewrite(planner):
    source,service,plan,binding,calls=planner
    history=await service.stock_search_history(plan.media_plan_id)
    costs=await source.platform.list_cost_records(source.project.project_id)
    store=RecordingStorage(source.uploads.object_storage);service.object_storage=store
    await service._verify_stock_plan_inputs(plan,binding)
    assert_frozen(store.calls[0],source.asset,MAX_SOURCE_BYTES)
    assert await service.repository.get_plan(plan.media_plan_id)==plan
    assert await service.stock_search_history(plan.media_plan_id)==history
    assert await source.platform.list_cost_records(source.project.project_id)==costs and not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['bytes','version','provenance'])
async def test_frozen_stock_source_mismatch_blocks_validation_and_preserves_plan_history(planner,change):
    source,service,plan,binding,calls=planner
    before=copy.deepcopy(plan.provenance);history=await service.stock_search_history(plan.media_plan_id)
    async def after(_):
        if change!='bytes':
            async with source.sessions() as session,session.begin():
                row=await session.get(AssetORM,source.asset.asset_id)
                if change=='version':row.version+=1
                else:row.provenance={**row.provenance,'changed_fixture':True}
    store=RecordingStorage(source.uploads.object_storage,after=after);service.object_storage=store
    if change=='bytes':
        path=source.uploads.object_storage._path(source.asset.object_key)
        data=path.read_bytes();path.write_bytes(data[:-1]+b'X')
    with pytest.raises(ValueError,match='SOURCE_(FILE_CHANGED|CHANGED)'):
        await service._verify_stock_plan_inputs(plan,binding)
    assert len(store.calls)==1 and not calls
    assert (await service.repository.get_plan(plan.media_plan_id)).provenance==before
    assert await service.stock_search_history(plan.media_plan_id)==history


@pytest.mark.asyncio
@pytest.mark.parametrize('planner',['s3'],indirect=True)
async def test_stock_read_cancel_twice_drains_sdk_body_before_temporary_directory_cleanup(planner,monkeypatch):
    import app.media_intelligence_service as module
    source,service,plan,binding,calls=planner
    # The fixture registered s3 BEFORE the server froze this plan; never
    # rebind/recompute a previously frozen input or its historical fingerprint.
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    data=synthetic_mp4()
    class PausedBody(Body):
        def read(self,size=-1):entered.set();assert release.wait(10);return super().read(size)
        def close(self):super().close();closed.set()
    store,reads=fake_s3(PausedBody(data),length=len(data));service.object_storage=store
    owners=[];original=module.tempfile.TemporaryDirectory
    def owned(*args,**kwargs):
        kwargs['dir']=source.tmp
        result=original(*args,**kwargs);owners.append(result.name);return result
    monkeypatch.setattr(module.tempfile,'TemporaryDirectory',owned)
    task=asyncio.create_task(service._verify_stock_plan_inputs(plan,binding))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
        from pathlib import Path
        assert not task.done() and not closed.is_set() and all(Path(name).exists() for name in owners)
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set() and all(not Path(name).exists() for name in owners)
        assert len(reads)==1 and not calls
    finally:release.set();await asyncio.gather(task,return_exceptions=True)
