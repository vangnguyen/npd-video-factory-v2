"""Synthetic speech/metadata, actual SQLite history and canonical B-roll edits."""
import copy
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.broll_planner import BrollApplyRequest, supporting_candidates, choose_supporting_strategy, apply_broll, place_broll
from app.db import AssetORM
from app.media_intelligence_models import MediaPlanRequest, MediaResolutionRequest
from app.platform_models import AssetRegister
from app.timeline_logic import build_initial_timeline, TimelineEditError
from app.timeline_models import TimelineOperation
from app.timeline_repository import TimelineRepository, TimelineConflictError
from app.timeline_service import TimelineService, TimelineContractValidator
from test_media_intelligence import setup_media_stack

SCHEMA = Path(__file__).resolve().parents[3] / 'packages/contracts/timeline.schema.json'


async def add_asset(env, *, filename='supporting.jpg', rights='owned', tier='user_upload', duration=None, tags=None):
    # These bytes deliberately remain fixture evidence; no real-media claim.
    path=env['resolver'].staging_root.parent/filename
    path.write_bytes(b'explicit synthetic asset bytes '+filename.encode())
    key=f"workspaces/{env['project'].workspace_id}/projects/{env['project'].project_id}/broll/{filename}"
    stored=await env['storage'].put_file(object_key=key,path=path,content_type='video/mp4' if duration else 'image/jpeg')
    return await env['platform'].register_asset(env['project'].project_id,AssetRegister(asset_class='source',kind='video' if duration else 'image',
        filename=filename,object_key=stored.object_key,content_type=stored.content_type,size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256,storage_provider=stored.storage_provider,
        provenance={'fixture':True,'rights_status':rights,'license':'fixture','source_type':tier,
            'tags':tags or [],'media_metadata':{'duration_seconds':duration,'width':1920,'height':1080}}))


async def prepare(tmp_path):
    env=await setup_media_stack(tmp_path)
    source=await env['auto_repository'].get_asset(env['source_asset'].asset_id)
    timelines=TimelineRepository(env['session_factory'])
    initial=build_initial_timeline(analysis=env['auto_edit'],source_asset=source,media_plan=None,media_assets={})
    timeline,_=await timelines.create_timeline(project_id=env['project'].project_id,source_analysis_id=env['auto_edit'].analysis_id,
        source_media_plan_id=None,snapshot=initial,actor_ref='fixture')
    env['timeline_service']=TimelineService(repository=timelines,platform=env['platform'],auto_edit_repository=env['auto_repository'],
        media_repository=env['media_repository'],validator=TimelineContractValidator(SCHEMA))
    env['timeline']=timeline
    return env


def request(env):
    return MediaPlanRequest(purpose='supporting_broll',analysis_id=env['auto_edit'].analysis_id,allow_stock=False,allow_ai_image=False,allow_ai_video=False)


@pytest.mark.asyncio
async def test_supporting_ranking_excludes_primary_restricted_and_unmeasured_video_and_respects_internal_priority(tmp_path):
    env=await prepare(tmp_path)
    try:
        upload=await add_asset(env,filename='ocean.jpg',tags=['ocean'])
        internal=await add_asset(env,filename='library.jpg',tier='internal_library',tags=['ocean'])
        unknown=await add_asset(env,filename='unknown.jpg',rights='unknown',tags=['ocean'])
        restricted=await add_asset(env,filename='restricted.jpg',rights='restricted',tags=['ocean'])
        unreadable=upload.model_copy(update={'asset_id':'ast_no_duration','content_type':'video/mp4'})
        source=await env['auto_repository'].get_asset(env['source_asset'].asset_id)
        ranked=supporting_candidates([source,restricted,unreadable,internal,unknown,upload],env['auto_edit'],'ocean')
        assert {item['asset_id'] for item in ranked}=={upload.asset_id,internal.asset_id,unknown.asset_id}
        assert all(item['confidence'] is None and item['provider_dispatches']==0 for item in ranked)
        assert next(item for item in ranked if item['asset_id']==unknown.asset_id)['needs_attention']
        strategy,selected=choose_supporting_strategy(request(env),ranked,stock=True,image=True,video=True,preferred_type='video')
        assert strategy=='user_asset' and selected['source_type']=='user_asset'
        custom=request(env).model_copy(update={'resolver_priority':['internal_library','user_asset']})
        assert choose_supporting_strategy(custom,ranked,stock=False,image=False,video=False,preferred_type='video')[1]['asset_id']==internal.asset_id
        assert choose_supporting_strategy(request(env),supporting_candidates([upload],env['auto_edit'],'unrelated'),
            stock=False,image=False,video=False,preferred_type='image')==('user_asset',None)
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_explicit_picker_resolves_review_only_and_applies_to_same_timeline_with_history_and_approval_invalidation(tmp_path):
    env=await prepare(tmp_path)
    try:
        asset=await add_asset(env,rights='unknown')
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=request(env))
        item=plan.items[0]
        assert item.source_asset_id is None and item.provenance['fallback_keeps_original_footage']
        assert asset.asset_id in {entry['asset_id'] for entry in item.provenance['supporting_candidates']}
        job=await env['resolver'].enqueue(project_id=env['project'].project_id,media_plan_id=plan.media_plan_id,
            media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(asset_id=asset.asset_id))
        replay=await env['resolver'].enqueue(project_id=env['project'].project_id,media_plan_id=plan.media_plan_id,
            media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(asset_id=asset.asset_id))
        assert replay.resolution_job_id==job.resolution_job_id and job.capability=='internal_media' and not job.external_call
        completed=await env['resolver'].process(job.resolution_job_id)
        assert completed.status=='succeeded' and completed.actual_cost_vnd==0
        resolved=await env['media_repository'].get_plan(plan.media_plan_id)
        assert resolved.media_assets[0].rights_status=='unknown' and not resolved.media_assets[0].publishing_allowed
        before=copy.deepcopy(env['timeline'].snapshot)
        preview,_=await env['timeline_service'].repository.create_preview(project_id=env['project'].project_id,timeline_version=1,
            width=540,height=960,actor_ref='fixture')
        applied=await apply_broll(env['timeline_service'],env['project'].project_id,plan.media_plan_id,
            BrollApplyRequest(expected_version=1,item_ids=[item.media_plan_item_id]),'editor')
        assert applied.current_version==2 and applied.timeline_id==env['timeline'].timeline_id and applied.approval_status=='draft'
        for track in before.tracks:
            if track.kind!='broll':assert next(t for t in applied.snapshot.tracks if t.track_id==track.track_id)==track
        clips=next(t for t in applied.snapshot.tracks if t.kind=='broll').clips
        assert clips and all(clip.asset_id==asset.asset_id and clip.volume==0 and clip.kind=='image' for clip in clips)
        assert all(not clip.metadata['publishing_allowed'] and clip.metadata['original_audio_preserved'] for clip in clips)
        assert applied.snapshot.duration_seconds==before.duration_seconds and applied.snapshot.schema_version=='1.1'
        assert (await env['timeline_service'].repository.get_version(applied.timeline_id,1)).snapshot==before
        assert (await env['timeline_service'].repository.get_preview(preview.preview_id)).status=='stale'
        with pytest.raises(TimelineEditError,match='already exists'):
            await apply_broll(env['timeline_service'],env['project'].project_id,plan.media_plan_id,
                BrollApplyRequest(expected_version=2,item_ids=[item.media_plan_item_id]),'editor')
        replaced=await apply_broll(env['timeline_service'],env['project'].project_id,plan.media_plan_id,
            BrollApplyRequest(expected_version=2,item_ids=[item.media_plan_item_id],replace_plan_clips=True),'editor')
        assert replaced.current_version==3
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_selection_checksum_scope_and_stale_timeline_reject_without_source_mutation(tmp_path):
    env=await prepare(tmp_path)
    try:
        asset=await add_asset(env,filename='support.mp4',duration=1.25)
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=request(env))
        item=plan.items[0]
        with pytest.raises(ValueError,match='from this plan'):
            await env['resolver'].enqueue(project_id=env['project'].project_id,media_plan_id=plan.media_plan_id,
                media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(asset_id=env['source_asset'].asset_id))
        job=await env['resolver'].enqueue(project_id=env['project'].project_id,media_plan_id=plan.media_plan_id,
            media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(asset_id=asset.asset_id))
        assert (await env['resolver'].process(job.resolution_job_id)).status=='succeeded'
        with pytest.raises(TimelineConflictError):
            await apply_broll(env['timeline_service'],env['project'].project_id,plan.media_plan_id,
                BrollApplyRequest(expected_version=99,item_ids=[item.media_plan_item_id]),'editor')
        async with env['session_factory']() as session:
            row=await session.get(AssetORM,asset.asset_id);row.checksum_sha256='f'*64;await session.commit()
        with pytest.raises(TimelineEditError,match='checksum'):
            await apply_broll(env['timeline_service'],env['project'].project_id,plan.media_plan_id,
                BrollApplyRequest(expected_version=1,item_ids=[item.media_plan_item_id]),'editor')
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version==1
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_source_placement_follows_trim_move_speed_and_broll_lock(tmp_path):
    env=await prepare(tmp_path)
    try:
        asset=await add_asset(env,filename='short-support.mp4',duration=.4)
        plan=await env['planner'].create(project_id=env['project'].project_id,payload=request(env))
        item=plan.items[0]
        item.broll=item.broll.model_copy(update={'placement_start_seconds':1.,'placement_end_seconds':2.})
        evidence=SimpleNamespace(asset_id=asset.asset_id,media_asset_id='mas_fixture',rights_status='owned',license='fixture',
            generation_provenance={},source_reference=f'asset://{asset.asset_id}',publishing_allowed=False,production_eligible=False)
        snapshot=env['timeline'].snapshot.model_copy(deep=True)
        source=next(t for t in snapshot.tracks if t.kind=='source')
        clip=source.clips[0].model_copy(update={'source_start':.5,'source_end':2.5,'speed':2.,'duration':1.,'timeline_start':4.})
        source.clips=[clip]
        result=place_broll(snapshot,plan,[(item,evidence)],{asset.asset_id:asset})
        added=next(t for t in result.tracks if t.kind=='broll').clips[0]
        assert added.timeline_start==4.25 and added.duration==.4 and added.source_end==.4
        assert source.clips==next(t for t in result.tracks if t.kind=='source').clips
        next(t for t in snapshot.tracks if t.kind=='broll').locked=True
        with pytest.raises(TimelineEditError,match='unlock'):place_broll(snapshot,plan,[(item,evidence)],{asset.asset_id:asset})
        next(t for t in snapshot.tracks if t.kind=='broll').locked=False
        source.clips=[]
        with pytest.raises(TimelineEditError,match='overlaps'):place_broll(snapshot,plan,[(item,evidence)],{asset.asset_id:asset})
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_reused_registry_asset_is_readable_across_plan_versions_and_http_apply_requires_scoped_editor(tmp_path):
    from app.main import app
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from httpx import ASGITransport,AsyncClient
    env=await prepare(tmp_path)
    try:
        asset=await add_asset(env)
        async def resolve(plan):
            item=plan.items[0]
            job=await env['resolver'].enqueue(project_id=env['project'].project_id,media_plan_id=plan.media_plan_id,
                media_plan_item_id=item.media_plan_item_id,payload=MediaResolutionRequest(asset_id=asset.asset_id))
            assert (await env['resolver'].process(job.resolution_job_id)).status=='succeeded'
            return await env['media_repository'].get_plan(plan.media_plan_id)
        first=await resolve(await env['planner'].create(project_id=env['project'].project_id,payload=request(env)))
        second_request=request(env).model_copy(update={'brand_context':'new immutable plan version'})
        second=await resolve(await env['planner'].create(project_id=env['project'].project_id,payload=second_request))
        assert second.media_plan_id!=first.media_plan_id
        assert second.media_assets[0].media_asset_id==first.media_assets[0].media_asset_id
        assert second.items[0].selected_media_asset_id==first.items[0].selected_media_asset_id
        app.state.timeline_service=env['timeline_service']
        install_test_human_auth(app,platform_repository=env['platform'],platform_role='viewer',workspace_roles={'*':'viewer'})
        url=f'/api/v1/projects/{env["project"].project_id}/media-plans/{second.media_plan_id}/apply-broll'
        body={'expected_version':1,'item_ids':[second.items[0].media_plan_item_id]}
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(url,json=body)).status_code==401
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=env['platform'],platform_role='editor',workspace_roles={'*':'editor'})
            result=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert result.status_code==200 and result.json()['current_version']==2
            version=await env['timeline_service'].repository.get_version(env['timeline'].timeline_id,2)
            assert version.actor_ref=='usr:test-owner'
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==409
            assert (await client.post(url.replace(env['project'].project_id,'prj_foreign'),json=body,headers=TEST_HUMAN_HEADERS)).status_code==404
    finally:await env['engine'].dispose()
