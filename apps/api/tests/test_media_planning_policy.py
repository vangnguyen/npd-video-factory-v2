"""Priority/caching/persistence tests use explicitly synthetic ASR/Vision/media providers."""
import copy
import pytest
from sqlalchemy import select,func
from app.db import AssetORM
from app.media_intelligence_db import MediaPlanORM
from app.media_intelligence_models import MediaPlanRequest
from app.media_intelligence_logic import select_strategy
from app.transcript_editing import edit_transcript
from app.auto_edit_models import TranscriptEditRequest
from test_media_intelligence import setup_media_stack,plan_request
from app.media_intelligence_providers import DeterministicStockMediaProvider,DeterministicImageGenerationProvider,DeterministicVideoGenerationProvider
from app.media_intelligence_service import MediaProviderBundle


def test_strict_priority_applies_to_every_scene_and_variety_remains_explicit():
    request=MediaPlanRequest(analysis_id='ana_fixture',resolver_priority=['user_asset','licensed_stock','ai_image','ai_video'])
    inputs=dict(payload=request,preferred_media_type='video',stock_available=True,image_available=True,
                video_available=True,has_source_asset=True)
    assert [select_strategy(ordinal=i,**inputs) for i in range(10)]==['user_asset']*10
    inputs['has_source_asset']=False
    assert [select_strategy(ordinal=i,**inputs) for i in range(4)]==['stock_video']*4
    inputs['stock_available']=False
    assert select_strategy(ordinal=8,**inputs)=='ai_image'
    inputs['payload']=request.model_copy(update={'selection_policy':'scene_variety'})
    assert select_strategy(ordinal=3,**inputs)=='ai_video'


@pytest.mark.asyncio
async def test_current_and_historical_transcripts_produce_distinct_immutable_plans_and_legacy_config_reads(tmp_path):
    env=await setup_media_stack(tmp_path)
    try:
        request=MediaPlanRequest(analysis_id=env['auto_edit'].analysis_id)
        first=await env['planner'].create(project_id=env['project'].project_id,payload=request)
        assert all(item.strategy=='user_asset' for item in first.items)
        assert all(not item.candidates for item in first.items)
        assert all(item.broll.provenance['vision_analysis_id'] is None for item in first.items)
        assert all(item.broll.confidence<=.65 and 'no Vision evidence' in item.broll.provenance['confidence_basis'] for item in first.items)
        original=copy.deepcopy(first.model_dump(mode='json'))
        transcript=env['auto_edit'].transcript
        updated=await edit_transcript(env['auto_repository'],env['project'].project_id,env['auto_edit'].analysis_id,
            TranscriptEditRequest(expected_version=transcript.version,segments=[{
                'segment_id':transcript.segments[0].segment_id,'text':'Thông tin mới cần kiểm chứng bằng nguồn gốc.'}]),'editor')
        second=await env['planner'].create(project_id=env['project'].project_id,payload=request)
        assert second.media_plan_id!=first.media_plan_id
        assert second.provenance['transcript_id']==updated.transcript.transcript_id
        assert second.items[0].broll.provenance['semantic_refresh_required'] and second.items[0].needs_attention
        assert 'Thông tin mới' in second.items[0].broll.generation_prompt
        historical=await env['planner'].create(project_id=env['project'].project_id,
            payload=request.model_copy(update={'transcript_id':transcript.transcript_id}))
        assert historical.items[0].broll.provenance['transcript_id']==transcript.transcript_id
        assert (await env['media_repository'].get_plan(first.media_plan_id)).model_dump(mode='json')==original
        legacy=await env['planner'].create(project_id=env['project'].project_id,payload=plan_request(env))
        assert [item.strategy for item in legacy.items]==['user_asset','stock_video','ai_image','ai_video']
        async with env['session_factory']() as session:
            row=await session.get(MediaPlanORM,legacy.media_plan_id)
            row.configuration_json={key:value for key,value in row.configuration_json.items() if key not in {'selection_policy','transcript_id'}}
            await session.commit()
        assert (await env['media_repository'].get_plan(legacy.media_plan_id)).configuration.selection_policy=='scene_variety'
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_stale_source_and_vision_are_refused_before_planning_or_provider_calls(tmp_path):
    env=await setup_media_stack(tmp_path)
    try:
        source=env['source_asset']
        async with env['session_factory']() as session:
            asset=await session.get(AssetORM,source.asset_id);asset.checksum_sha256='f'*64;await session.commit()
        with pytest.raises(ValueError,match='checksum'):
            await env['planner'].create(project_id=env['project'].project_id,payload=plan_request(env))
        async with env['session_factory']() as session:
            asset=await session.get(AssetORM,source.asset_id);asset.checksum_sha256=source.checksum_sha256;await session.commit()
        from unittest.mock import AsyncMock
        vision=env['vision'].model_copy(update={'provenance':{**env['vision'].provenance,'source_asset_checksum':'f'*64}})
        env['planner'].vision_repository.get_analysis=AsyncMock(return_value=vision)
        with pytest.raises(ValueError,match='Vision checksum'):
            await env['planner'].create(project_id=env['project'].project_id,payload=plan_request(env))
        async with env['session_factory']() as session:
            assert await session.scalar(select(func.count()).select_from(MediaPlanORM))==0
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('rights_mode',['empty','unknown','restricted'])
async def test_empty_or_unlicensed_stock_falls_back_to_existing_assets_in_strict_priority(tmp_path,rights_mode):
    class EmptyStock(DeterministicStockMediaProvider):
        def __init__(self):super().__init__();self.calls=0
        async def search_videos(self,*args,**kwargs):
            self.calls+=1
            return [] if rights_mode=='empty' else [candidate.model_copy(update={'rights_status':rights_mode})
                for candidate in await super().search_videos(*args,**kwargs)]
        async def search_images(self,*args,**kwargs):
            self.calls+=1
            return [] if rights_mode=='empty' else [candidate.model_copy(update={'rights_status':rights_mode})
                for candidate in await super().search_images(*args,**kwargs)]
    stock=EmptyStock()
    env=await setup_media_stack(tmp_path,MediaProviderBundle(stock=stock,
        image=DeterministicImageGenerationProvider(),video=DeterministicVideoGenerationProvider()))
    try:
        request=MediaPlanRequest(analysis_id=env['auto_edit'].analysis_id,resolver_priority=['licensed_stock','user_asset','ai_image'])
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=request)
        assert stock.calls==len(plan.items)
        assert all(item.strategy=='user_asset' and not item.candidates for item in plan.items)
        count=0 if rights_mode=='empty' else 3
        assert all(item.provenance['stock_result_count']==count and not item.provenance['stock_tier_available'] for item in plan.items)
        assert all(item.provenance['stock_rejected_rights_count']==count for item in plan.items)
        assert plan.projected_ai_cost_vnd==0 and not plan.needs_approval
    finally:await env['engine'].dispose()
