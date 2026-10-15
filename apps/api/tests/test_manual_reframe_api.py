"""Actual isolated SQLite/ASGI; synthetic source/ASR, zero model/render/UAT."""
import copy
from unittest.mock import AsyncMock, patch

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.auto_edit_db import AutoEditAnalysisORM
from app.db import AssetORM
from app.manual_reframe_api import ManualReframeUpdate, router
from app.manual_reframe_command import read_manual_reframe, digest
from app.source_linked_edit_api import SourceLinkedUpdate
from app.source_linked_edit_command import apply_source_linked_edit
from app.timeline_db import TimelineORM, TimelineVersionORM
from app.timeline_models import TimelineTrack
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_source_linked_edit_api import linked_api, source, audio, state, change_fixture


@pytest.fixture
async def manual(linked_api):
    a = linked_api
    a.app.include_router(router)
    a.path = f'/api/v1/projects/{a.project.project_id}/timeline/manual-reframe'
    a.read = await read_manual_reframe(a.service, a.project.project_id)
    return a


def body(a, **updates):
    value = dict(expected_timeline_id=a.timeline.timeline_id, expected_version=a.timeline.current_version,
        request_key='manual-reframe-fixture-01', acknowledged=True,
        expected_source_binding_sha256=a.read['source_binding_sha256'], aspect_ratio='9:16',
        points=[dict(time=0, x=.2, y=.5, zoom=1), dict(time=8, x=.8, y=.5, zoom=1.1)])
    value.update(updates)
    return value


async def put(a, value=None):
    return await a.client.put(a.path, json=value if value is not None else body(a), headers=TEST_HUMAN_HEADERS)


@pytest.mark.parametrize('ratio', ['9:16', '16:9', '1:1', '4:5'])
async def test_actual_four_ratio_receipt_exact_replay_and_only_canonical_changes(manual, ratio):
    a = manual
    initial = await state(a)
    response = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert response.status_code == 200 and response.headers['Cache-Control'] == 'no-store'
    assert response.json()['settings'] is response.json()['receipt'] is None
    request = body(a, aspect_ratio=ratio)
    result = await put(a, request)
    assert result.status_code == 200, result.text
    data = result.json()
    saved = data['receipt']
    assert saved['schema_version'] == 'manual-reframe-v1'
    assert saved['source'] == data['source'] == a.read['source']
    assert saved['actor_ref'] == 'usr:test-owner' and saved['parent_version_id'] == a.timeline.current_version_id
    assert saved['settings'] == data['settings'] == {k: request[k] for k in ('aspect_ratio', 'points')}
    assert saved['result_snapshot_sha256'] == digest(data['timeline']['snapshot'])
    assert data['timeline']['current_version'] == 2 and data['timeline']['approval_status'] == 'draft'
    snapshot = (await a.timelines.get_timeline(a.project.project_id)).snapshot
    for old in a.timeline.snapshot.tracks:
        new = next(t for t in snapshot.tracks if t.track_id == old.track_id)
        if old.kind != 'source':
            assert new == old
        else:
            assert len(new.clips) == len(old.clips)
            for before, after in zip(old.clips, new.clips):
                assert before.model_dump(exclude={'crop','metadata'}) == after.model_dump(exclude={'crop','metadata'})
                assert after.metadata['reframe']['time_space'] == 'source_seconds'
                assert after.metadata['reframe']['keyframes'] == saved['applied_keyframes']
                assert after.metadata['reframe']['confidence'] is None
                assert after.metadata['reframe']['needs_attention'] is True
    after = await state(a)
    for name in initial:
        if name not in {'timelines', 'timeline_versions', 'preview_jobs'}:
            assert after[name] == initial[name], name
    replay = await put(a, request)
    assert replay.status_code == 200 and replay.json()['replayed'] is True
    assert replay.json()['receipt'] == saved and await state(a) == after
    reread = (await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)).json()
    assert reread['timeline'] == data['timeline'] == replay.json()['timeline']
    assert reread['settings'] == data['settings'] and reread['source_binding_sha256'] == data['source_binding_sha256']


@pytest.mark.parametrize('changes', [
    {'acknowledged':False}, {'acknowledged':1}, {'expected_version':True}, {'expected_version':'1'},
    {'expected_source_binding_sha256':'broken'}, {'request_key':'short'}, {'actor_ref':'forged'},
    {'aspect_ratio':['9:16']}, {'points':[]}, {'points':{}}, {'points':[{'time':0,'x':.5,'y':.5}]},
    {'points':[{'time':0,'x':.5,'y':.5,'zoom':1,'metadata':{}}]},
    {'points':[{'time':2,'x':.5,'y':.5,'zoom':1},{'time':1,'x':.5,'y':.5,'zoom':1}]},
    {'points':[{'time':0,'x':.5,'y':.5,'zoom':1}]*2},
    {'points':[{'time':0,'x':.5,'y':.5,'zoom':1}]*201},
])
def test_strict_request_shape_no_coercion(changes):
    value = dict(expected_timeline_id='tml_fixture1234',expected_version=1,request_key='fixture-key-001',
        acknowledged=True,expected_source_binding_sha256='a'*64,aspect_ratio='9:16',
        points=[dict(time=0,x=.5,y=.5,zoom=1)])
    value.update(changes)
    with pytest.raises(ValidationError): ManualReframeUpdate.model_validate(value)


@pytest.mark.parametrize('field,value', [('time',True),('time','0'),('time',float('nan')),('time',float('inf')),
    ('time',10**400),('time',-1),('x',True),('x',{}),('x',[]),('x',1.1),('y',-.1),('zoom',.9),('zoom',4.1)])
def test_strict_coordinate_finite_ranges(field,value):
    point=dict(time=0,x=.5,y=.5,zoom=1);point[field]=value
    request=dict(expected_timeline_id='tml_fixture1234',expected_version=1,request_key='fixture-key-001',
        acknowledged=True,expected_source_binding_sha256='a'*64,aspect_ratio='9:16',points=[point])
    with pytest.raises(ValidationError):ManualReframeUpdate.model_validate(request)


@pytest.mark.parametrize('mode,status', [('viewer',403),('foreign',404),('write_off',503),('api_off',503),('unauthenticated',401)])
async def test_actual_auth_before_invalid_body_zero_writes(manual, mode,status):
    a=manual;before=await state(a)
    if mode in {'viewer','foreign'}:
        install_test_human_auth(a.app,platform_repository=a.platform,platform_role=None,
            workspace_roles={a.project.workspace_id:'viewer'} if mode=='viewer' else {'wsp_foreign':'editor'})
    elif mode=='write_off':a.app.state.human_write_enabled=False
    elif mode=='api_off':a.app.state.human_api_enabled=False
    response=await a.client.put(a.path,json={'bad':'fixture'},headers={} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
    assert response.status_code==status and await state(a)==before


@pytest.mark.parametrize('mode', ['locked','disabled','all-clips-disabled','time','stale','identity','source-hash','fingerprint','fps','width','object-key','source-clock','asset-size','asset-metadata'])
async def test_stale_locked_foreign_or_unmeasured_source_rejects_no_write(manual,mode):
    a=manual;request=body(a)
    if mode in {'locked','disabled','all-clips-disabled'}:
        def mutate(snapshot):
            t=source(snapshot)
            if mode=='locked':t.locked=True
            elif mode=='disabled':t.disabled=True
            elif mode=='all-clips-disabled':
                for c in t.clips:c.disabled=True
        await change_fixture(a,mutate)
        request['expected_version']=a.timeline.current_version
    elif mode=='source-clock':
        async with a.sessions() as session:
            row=await session.get(TimelineVersionORM,a.timeline.current_version_id)
            changed=copy.deepcopy(row.snapshot_json);changed['tracks'][0]['clips'][0]['speed']=2
            row.snapshot_json=changed;await session.commit()
    elif mode=='time':request['points'][-1]['time']=a.read['source']['duration_seconds']+.001
    elif mode=='stale':request['expected_version']=2
    elif mode=='identity':request['expected_timeline_id']='tml_foreign1234'
    else:
        async with a.sessions() as session:
            if mode in {'source-hash','object-key','asset-size','asset-metadata'}:
                row=await session.get(AssetORM,a.analysis.asset_id)
                if mode=='source-hash':row.checksum_sha256='f'*64
                elif mode=='object-key':row.object_key+='-changed'
                elif mode=='asset-size':row.size_bytes+=1
                else:row.provenance={**row.provenance,'media_metadata':{**row.provenance['media_metadata'],'fps':31}}
            else:
                row=await session.get(AutoEditAnalysisORM,a.analysis.analysis_id)
                if mode=='fingerprint':row.fingerprint='e'*64
                else:row.source_media_json={**row.source_media_json,mode:0 if mode=='fps' else row.source_media_json['width']+1}
            await session.commit()
    before=await state(a)
    response=await put(a,request)
    assert response.status_code==409,response.text
    assert await state(a)==before


async def test_preview_approval_invalidation_and_insertion_failure_rollback(manual):
    a=manual
    preview,_=await a.timelines.create_preview(project_id=a.project.project_id,timeline_version=1,width=540,height=960,actor_ref='fixture')
    async with a.sessions() as session:
        row=await session.get(TimelineORM,a.timeline.timeline_id)
        row.approval_status='approved';row.approved_timeline_version=1;await session.commit()
    before=await state(a)
    with patch.object(a.timelines,'commit_mutation_in_session',new=AsyncMock(side_effect=RuntimeError('synthetic storage failure'))):
        with pytest.raises(RuntimeError,match='storage failure'):await put(a)
    assert await state(a)==before
    response=await put(a)
    assert response.status_code==200,response.text
    current=await a.timelines.get_timeline(a.project.project_id)
    assert current.approval_status=='draft' and current.approved_timeline_version is None and current.latest_preview_id is None
    old=await a.timelines.get_version_by_id(a.timeline.current_version_id)
    assert old.snapshot==a.timeline.snapshot
    stale=await a.timelines.get_preview(preview.preview_id)
    assert stale.status=='stale' and stale.cancellation_requested


async def test_locked_independent_same_asset_track_and_audio_captions_preserved(manual):
    a=manual
    def mutate(snapshot):
        independent=source(snapshot).model_copy(deep=True)
        independent.track_id='trk_independent';independent.kind='overlay';independent.order=len(snapshot.tracks);independent.locked=True
        for i,c in enumerate(independent.clips):c.clip_id=f'clip_independent_{i}';c.kind='overlay'
        snapshot.tracks.append(independent)
        for t in snapshot.tracks:
            if t.kind in {'subtitles','original_audio'}:t.locked=True;t.muted=True
    await change_fixture(a,mutate)
    response=await put(a)
    assert response.status_code==200,response.text
    current=await a.timelines.get_timeline(a.project.project_id)
    for t in a.timeline.snapshot.tracks:
        if t.kind!='source':assert next(n for n in current.snapshot.tracks if n.track_id==t.track_id)==t


async def test_key_collision_actor_and_superseded_exact_replay_fail_closed(manual):
    a=manual;request=body(a)
    assert (await put(a,request)).status_code==200
    before=await state(a)
    other=copy.deepcopy(request);other['points'][0]['x']=.3
    assert (await put(a,other)).status_code==409 and await state(a)==before
    from app.manual_reframe_command import apply_manual_reframe, ManualReframeConflict
    with pytest.raises(ManualReframeConflict,match='KEY_CONFLICT'):
        await apply_manual_reframe(a.service,a.project.project_id,ManualReframeUpdate.model_validate(request),actor_ref='usr:other')
    a.timeline=await a.timelines.get_timeline(a.project.project_id)
    await change_fixture(a,lambda snapshot:None)
    after=await state(a)
    response=await put(a,request)
    assert response.status_code==409 and response.json()['detail']['code']=='MANUAL_REFRAME_RECEIPT_SUPERSEDED'
    assert await state(a)==after


async def test_source_linked_trim_split_move_speed_duplicate_preserves_manual_points_and_all_source_clocks(manual):
    a=manual
    assert (await put(a)).status_code==200
    a.timeline=await a.timelines.get_timeline(a.project.project_id)
    c=source(a.timeline.snapshot).clips[0]
    last=source(a.timeline.snapshot).clips[-1]
    first_word=a.analysis.transcript.segments[0].words[0]
    operations=[dict(type='trim',clip_id=last.clip_id,source_start=last.source_start+.32,source_end=last.source_end-.48),
        dict(type='set_clip_properties',clip_id=c.clip_id,speed=2),
        dict(type='split',clip_id=c.clip_id,at_seconds=first_word.end_seconds/2),
        dict(type='move',clip_id=c.clip_id,timeline_start=99),dict(type='duplicate',clip_id=c.clip_id)]
    for index,operation in enumerate(operations):
        request=SourceLinkedUpdate(expected_timeline_id=a.timeline.timeline_id,expected_version=a.timeline.current_version,
            request_key=f'manual-linked-fixture-{index}',acknowledged=True,operations=[operation])
        await apply_source_linked_edit(a.service,a.project.project_id,request,actor_ref='usr:test-owner')
        a.timeline=await a.timelines.get_timeline(a.project.project_id)
        read=await read_manual_reframe(a.service,a.project.project_id)
        assert read['settings']=={k:body(a)[k] for k in ('aspect_ratio','points')}
        assert read['receipt'] is None
        for clip in source(a.timeline.snapshot).clips:
            assert clip.metadata['reframe']['keyframes'][0]['time']==0
            assert abs(clip.duration-(clip.source_end-clip.source_start)/clip.speed)<.00001


@pytest.mark.parametrize('mode',['snapshot-hash','source','applied-path'])
async def test_corrupt_saved_receipt_cannot_be_read_or_replayed(manual,mode):
    a=manual;request=body(a)
    assert (await put(a,request)).status_code==200
    current=await a.timelines.get_timeline(a.project.project_id)
    async with a.sessions() as session:
        row=await session.get(TimelineVersionORM,current.current_version_id)
        mutation=copy.deepcopy(row.mutation_json)
        if mode=='snapshot-hash':mutation['receipt']['result_snapshot_sha256']='a'*64
        elif mode=='source':mutation['receipt']['source']['analysis_fingerprint']='b'*64
        else:mutation['receipt']['applied_keyframes'][0]['x']=.123
        row.mutation_json=mutation;await session.commit()
    before=await state(a)
    assert (await a.client.get(a.path,headers=TEST_HUMAN_HEADERS)).status_code==409
    assert (await put(a,request)).status_code==409
    assert await state(a)==before


@pytest.mark.parametrize('mode',['one-static-clip','all-static-clips','auto-reframe'])
async def test_get_does_not_promote_stale_manual_settings_after_crop_or_auto_reframe(manual,mode):
    a=manual
    assert (await put(a)).status_code==200
    a.timeline=await a.timelines.get_timeline(a.project.project_id)
    if mode=='auto-reframe':
        from app.timeline_reframe import apply_reframe,ReframeApplyRequest
        await apply_reframe(a.service,None,a.project.project_id,
            ReframeApplyRequest(expected_version=a.timeline.current_version,aspect_ratio='9:16'),'usr:test-owner')
    else:
        clips=source(a.timeline.snapshot).clips if mode=='all-static-clips' else source(a.timeline.snapshot).clips[:1]
        request=SourceLinkedUpdate(expected_timeline_id=a.timeline.timeline_id,expected_version=a.timeline.current_version,
            request_key='manual-static-override-fixture',acknowledged=True,operations=[dict(type='set_clip_properties',
                clip_id=c.clip_id,crop=dict(x=0,y=0,width=1,height=1)) for c in clips])
        await apply_source_linked_edit(a.service,a.project.project_id,request,actor_ref='usr:test-owner')
    before=await state(a)
    result=await a.client.get(a.path,headers=TEST_HUMAN_HEADERS)
    assert result.status_code==200,result.text
    assert result.json()['settings'] is None and result.json()['receipt'] is None
    assert await state(a)==before


def test_ultrawide_zoom_is_relative_to_aspect_fit_without_fake_vision_confidence():
    from app.manual_reframe_api import ManualReframeSettings
    from app.manual_reframe_command import _plan
    from app.timeline_reframe import crop_keyframes
    from app.auto_edit_models import MediaMetadata
    source_identity=dict(width=8192,height=480,duration_seconds=8)
    settings=ManualReframeSettings(aspect_ratio='9:16',points=[dict(time=0,x=.1,y=.5,zoom=4),dict(time=8,x=.9,y=.5,zoom=1)])
    plan=_plan(settings,source_identity)
    assert plan.keyframes[0].scale>20 and plan.confidence is None and plan.needs_attention
    media=MediaMetadata(media_kind='video',detected_content_type='video/mp4',width=8192,height=480,duration_seconds=8,fps=30)
    points=crop_keyframes(plan,media)
    for point in points:
        assert source_identity['width']/source_identity['height']*point['width']/point['height']==pytest.approx(9/16)
        assert 0<=point['x']<=1-point['width'] and 0<=point['y']<=1-point['height']
