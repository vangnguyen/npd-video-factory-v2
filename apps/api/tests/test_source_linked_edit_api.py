"""Actual isolated SQLite/ASGI with synthetic media/ASR, never provider/UAT proof."""
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, update

from app.auto_edit_db import AutoEditAnalysisORM, TranscriptORM
from app.db import Base, AssetORM
from app.human_auth import HumanPrincipal
from app.repositories import PlatformRepository
from app.source_linked_edit_api import router, SourceLinkedUpdate
from app.source_linked_edit_command import apply_source_linked_edit, SourceLinkedConflict, digest
from app.timeline_db import TimelineORM, TimelineVersionORM, PreviewJobORM
from app.timeline_models import TimelineMutationRequest, TimelineOperation, TimelineRestoreRequest, TimelineTrack
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService, TimelineContractValidator
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_transcript_editing import stack


@pytest.fixture
async def linked_api(tmp_path):
    engine, sessions, repository, project, analysis, timelines, timeline = await stack(tmp_path)
    platform = PlatformRepository(sessions)
    service = TimelineService(repository=timelines, platform=platform, auto_edit_repository=repository,
        media_repository=None, validator=TimelineContractValidator(
            Path(__file__).resolve().parents[3] / 'packages/contracts/timeline.schema.json'))
    app = FastAPI()
    app.include_router(router)  # No main/lifespan, worker or migration.
    app.state.timeline_service = service
    install_test_human_auth(app, platform_repository=platform, platform_role=None,
        workspace_roles={project.workspace_id: 'editor'})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture-source-linked') as client:
        yield SimpleNamespace(engine=engine, sessions=sessions, repository=repository, project=project,
            analysis=analysis, timelines=timelines, timeline=timeline, service=service, platform=platform,
            app=app, client=client, path=f'/api/v1/projects/{project.project_id}/timeline/source-linked-edit')
    await engine.dispose()


def source(snapshot):
    return next(t for t in snapshot.tracks if t.kind == 'source')


def audio(snapshot):
    return next(t for t in snapshot.tracks if t.kind == 'original_audio')


def body(a, operations=None, **updates):
    value = dict(expected_timeline_id=a.timeline.timeline_id, expected_version=a.timeline.current_version,
        request_key='source-linked-fixture-intent-01', acknowledged=True,
        operations=operations or [dict(type='set_clip_properties', clip_id=source(a.timeline.snapshot).clips[0].clip_id, speed=2)])
    value.update(updates)
    return value


async def put(a, value=None):
    return await a.client.put(a.path, json=value or body(a), headers=TEST_HUMAN_HEADERS)


async def state(a):
    async with a.sessions() as session:
        return {table.name: [dict(row) for row in (await session.execute(select(table))).mappings().all()]
            for table in Base.metadata.sorted_tables}


def assert_av(snapshot):
    keys = ('asset_id', 'source_start', 'source_end', 'timeline_start', 'duration', 'speed', 'disabled')
    assert [tuple(getattr(c, k) for k in keys) for c in source(snapshot).clips] == [
        tuple(getattr(c, k) for k in keys) for c in audio(snapshot).clips]


async def change_fixture(a, mutate, *, mutation=None):
    snapshot = a.timeline.snapshot.model_copy(deep=True)
    mutate(snapshot)
    a.timeline = await a.timelines.commit_mutation(project_id=a.project.project_id,
        expected_version=a.timeline.current_version, snapshot=snapshot,
        mutation=mutation or {'type': 'explicit-synthetic-test-fixture'}, actor_ref='fixture')
    return a.timeline


async def test_actual_cas_speed_receipt_exact_replay_no_source_or_transcript_writes(linked_api):
    a = linked_api
    initial = await state(a)
    read = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert read.status_code == 200 and read.json()['receipt'] is None
    assert read.headers['Cache-Control'] == 'no-store'
    response = await put(a)
    assert response.status_code == 200, response.text
    data = response.json()
    current = await a.timelines.get_timeline(a.project.project_id)
    assert current.current_version == 2
    assert_av(current.snapshot)
    assert source(current.snapshot).clips[0].speed == 2
    saved = data['receipt']
    assert saved['actor_ref'] == 'usr:test-owner' and saved['parent_version_id'] == a.timeline.current_version_id
    assert saved['source']['transcript_id'] == a.analysis.transcript.transcript_id
    assert saved['source']['transcript_version'] == a.analysis.transcript.version
    assert saved['requested_operations'] == body(a)['operations'] == saved['applied_operations']
    assert saved['result_snapshot_sha256'] == digest(current.snapshot.model_dump(mode='json'))
    after = await state(a)
    for name in initial:
        if name not in {'timelines', 'timeline_versions', 'preview_jobs'}:
            assert after[name] == initial[name], name
    assert len(after['timeline_versions']) == len(initial['timeline_versions']) + 1
    replay = await put(a)
    assert replay.status_code == 200 and replay.json()['replayed'] is True
    assert replay.json()['receipt'] == saved and await state(a) == after
    reread = await a.client.get(a.path, headers=TEST_HUMAN_HEADERS)
    assert reread.json()['timeline'] == data['timeline'] == replay.json()['timeline']


async def test_trim_extends_complete_words_preserves_original_gain_mute_and_fades(linked_api):
    a = linked_api
    def adjust(snapshot):
        t = audio(snapshot); t.muted = True
        t.clips[0].volume = .35
        t.clips[0].transition_in.kind = 'fade'; t.clips[0].transition_in.duration_seconds = .1
        t.clips[0].transition_out.kind = 'fade'; t.clips[0].transition_out.duration_seconds = .15
    await change_fixture(a, adjust)
    clip = source(a.timeline.snapshot).clips[0]
    words = [w for s in a.analysis.transcript.segments for w in s.words
             if clip.source_start <= w.start_seconds < w.end_seconds <= clip.source_end]
    first, last = words[0], words[-1]
    request = body(a, [dict(type='trim', clip_id=clip.clip_id,
        source_start=(first.start_seconds+first.end_seconds)/2,
        source_end=(last.start_seconds+last.end_seconds)/2)])
    result = await put(a, request)
    assert result.status_code == 200, result.text
    current = await a.timelines.get_timeline(a.project.project_id)
    assert_av(current.snapshot)
    edited = source(current.snapshot).clips[0]
    assert edited.source_start == first.start_seconds and edited.source_end == last.end_seconds
    original = audio(current.snapshot)
    assert original.muted and original.clips[0].volume == .35
    assert original.clips[0].transition_out.duration_seconds == .15
    assert original.clips[0].transition_in.duration_seconds == .1
    assert result.json()['receipt']['requested_operations'] != result.json()['receipt']['applied_operations']
    captions = [c for t in current.snapshot.tracks if t.kind == 'subtitles' for c in t.clips]
    assert any(c.metadata.get('measured_source_words') for c in captions)
    assert a.analysis.transcript == (await a.repository.get_analysis(a.analysis.analysis_id,
        transcript_id=a.analysis.transcript.transcript_id)).transcript


async def test_split_inside_word_rejected_and_safe_edge_split_reorder_duplicate_disable_delete(linked_api):
    a = linked_api
    selected = source(a.timeline.snapshot).clips[0]
    first = next(w for s in a.analysis.transcript.segments for w in s.words
                 if selected.source_start < w.start_seconds < w.end_seconds < selected.source_end)
    before = await state(a)
    response = await put(a, body(a, [dict(type='split', clip_id=selected.clip_id,
        at_seconds=selected.timeline_start+((first.start_seconds+first.end_seconds)/2-selected.source_start)/selected.speed)]))
    assert response.status_code == 409 and response.json()['detail']['code'] == 'SOURCE_SPLIT_TOUCHES_SPEECH'
    assert await state(a) == before
    response = await put(a, body(a, [dict(type='split', clip_id=selected.clip_id,
        at_seconds=selected.timeline_start+(first.end_seconds-selected.source_start)/selected.speed)]))
    assert response.status_code == 200, response.text
    a.timeline = await a.timelines.get_timeline(a.project.project_id)
    assert_av(a.timeline.snapshot)
    for index, op in enumerate(('reorder', 'duplicate', 'disable', 'delete')):
        clip = source(a.timeline.snapshot).clips[-1]
        extra = {'target_index': 0} if op == 'reorder' else {'disabled': True} if op == 'disable' else {}
        request = body(a, [dict(type=op, clip_id=clip.clip_id, **extra)])
        request['request_key'] = f'source-linked-sequence-{index:02d}'
        response = await put(a, request)
        assert response.status_code == 200, response.text
        a.timeline = await a.timelines.get_timeline(a.project.project_id)
        assert_av(a.timeline.snapshot)


@pytest.mark.parametrize('mode,status', [('viewer',403),('foreign',404),('write_off',503),('api_off',503),('unauthenticated',401)])
async def test_own_router_admission_before_invalid_body_and_zero_writes(linked_api, mode, status):
    a = linked_api; before = await state(a)
    if mode in {'viewer','foreign'}:
        install_test_human_auth(a.app, platform_repository=a.platform, platform_role=None,
            workspace_roles={a.project.workspace_id:'viewer'} if mode=='viewer' else {'wsp_other':'editor'})
    elif mode=='write_off':a.app.state.human_write_enabled=False
    elif mode=='api_off':a.app.state.human_api_enabled=False
    response = await a.client.put(a.path,json={'bad':'fixture'},
        headers={} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
    assert response.status_code == status and await state(a) == before
    if mode in {'viewer','write_off'}:
        assert (await a.client.get(a.path,headers=TEST_HUMAN_HEADERS)).status_code == 200


@pytest.mark.parametrize('changes', [
    {'acknowledged':False}, {'acknowledged':1}, {'expected_version':True}, {'expected_version':'1'},
    {'actor_ref':'forged'}, {'transcript':{'text':'forged'}}, {'request_key':'short'},
    {'operations':[]}, {'operations':[{'type':'set_track_state','track_id':'trk_1234','locked':False}]},
    {'operations':[{'type':'trim','clip_id':'clip_test','source_start':'1'}]},
    {'operations':[{'type':'set_clip_properties','clip_id':'clip_test','speed':True}]},
    {'operations':[{'type':'set_clip_properties','clip_id':'clip_test','speed':.01}]},
    {'operations':[{'type':'move','clip_id':'clip_test','timeline_start':1,'target_track_id':'trk_other'}]},
    {'operations':[{'type':'set_clip_properties','clip_id':'clip_test','volume':1}]},
    {'operations':[{'type':[],'clip_id':'clip_test'}]},
    {'operations':[{'type':{},'clip_id':'clip_test'}]},
])
async def test_strict_request_never_enters_a_write(linked_api, changes):
    a=linked_api; before=await state(a); value=body(a); value.update(changes)
    response=await put(a,value)
    assert response.status_code==422, response.text
    assert await state(a)==before


@pytest.mark.parametrize('mode', ['source-lock','audio-lock','caption-lock','audio-offset','audio-missing','audio-two','foreign-caption'])
async def test_locked_diverged_missing_multiple_tracks_are_not_silently_reset(linked_api, mode):
    a=linked_api
    def adjust(s):
        if mode=='source-lock':source(s).locked=True
        elif mode=='audio-lock':audio(s).locked=True
        elif mode=='caption-lock':next(t for t in s.tracks if t.kind=='subtitles').locked=True
        elif mode=='audio-offset':audio(s).clips[0].timeline_start+=.1;s.duration_seconds+=.1
        elif mode=='audio-missing':audio(s).clips=[]
        elif mode=='audio-two':
            t=audio(s).model_copy(deep=True);t.track_id='trk_extra_audio';t.order=len(s.tracks)
            for i,c in enumerate(t.clips):c.clip_id=f'clip_extra_audio_{i}'
            s.tracks.append(t)
        else:next(t for t in s.tracks if t.kind=='subtitles').clips[0].metadata['transcript_id']='trn_foreign'
    await change_fixture(a,adjust); before=await state(a)
    response=await put(a)
    assert response.status_code==409,response.text
    assert await state(a)==before


async def test_manual_imported_locked_captions_stay_exact_while_derived_follow_source(linked_api):
    a=linked_api
    preserved={}
    def adjust(s):
        generated=next(t for t in s.tracks if t.kind=='subtitles')
        for i,marker in enumerate(('human_caption_edit','native_media_import_id','audio_binding_id')):
            track=generated.model_copy(deep=True);track.track_id=f'trk_preserved_{i}';track.order=len(s.tracks);track.locked=True
            for j,c in enumerate(track.clips):c.clip_id=f'clip_preserved_{i}_{j}';c.metadata[marker]=True
            s.tracks.append(track);preserved[track.track_id]=track.model_dump(mode='json')
    await change_fixture(a,adjust)
    result=await put(a)
    assert result.status_code==200,result.text
    current=await a.timelines.get_timeline(a.project.project_id)
    assert_av(current.snapshot)
    for t in current.snapshot.tracks:
        if t.track_id in preserved:assert t.model_dump(mode='json')==preserved[t.track_id]


async def test_batch_invalid_second_operation_and_late_commit_failure_roll_back_every_table(linked_api):
    a=linked_api;before=await state(a);ops=body(a)['operations']
    request=body(a,ops+[dict(type='delete',clip_id='clip_foreign_fixture')])
    result=await put(a,request)
    assert result.status_code==409 and await state(a)==before
    original=TimelineRepository.commit_mutation_in_session
    async def fail(self,**kwargs):
        await original(self,**kwargs)
        await kwargs['session'].flush()
        raise RuntimeError('explicit late storage failure')
    with patch.object(TimelineRepository,'commit_mutation_in_session',new=fail):
        with pytest.raises(RuntimeError,match='explicit late storage failure'):
            await apply_source_linked_edit(a.service,a.project.project_id,SourceLinkedUpdate(**body(a)),actor_ref='usr:test-owner')
    assert await state(a)==before


async def test_actual_concurrent_cas_one_winner_and_exact_key_conflict(linked_api):
    a=linked_api;first=body(a);second=copy.deepcopy(first);second['request_key']='source-linked-concurrent-two'
    results=await asyncio.gather(put(a,first),put(a,second))
    assert sorted(r.status_code for r in results)==[200,409],[r.text for r in results]
    current=await a.timelines.get_timeline(a.project.project_id)
    assert current.current_version==2 and len(await a.timelines.list_versions(a.project.project_id))==2
    winning=first if results[0].status_code==200 else second
    before=await state(a);changed=copy.deepcopy(winning);changed['operations'][0]['speed']=3
    assert (await put(a,changed)).status_code==409 and await state(a)==before
    with pytest.raises(SourceLinkedConflict,match='KEY_CONFLICT'):
        await apply_source_linked_edit(a.service,a.project.project_id,SourceLinkedUpdate(**winning),actor_ref='usr:other-editor')
    assert await state(a)==before
    await a.service.restore(a.project.project_id,TimelineRestoreRequest(expected_version=2,restore_version=1))
    restored=await state(a)
    assert (await put(a,winning)).status_code==409 and await state(a)==restored


@pytest.mark.parametrize('mode', ['transcript-id','transcript-version','analysis-source-hash','clip-source-hash','source-object'])
async def test_persisted_source_and_exact_revision_are_checked_before_any_write(linked_api, mode):
    a=linked_api
    if mode in {'analysis-source-hash','source-object'}:
        async with a.sessions() as session:
            if mode=='analysis-source-hash':
                row=await session.get(AutoEditAnalysisORM,a.analysis.analysis_id)
                row.provenance_json={**row.provenance_json,'source_asset_checksum':'f'*64}
            else:
                row=await session.get(AssetORM,a.analysis.asset_id);row.object_key='changed-object-with-same-asset'
            await session.commit()
    else:
        def adjust(s):
            if mode=='transcript-id':s.metadata['transcript_revision']['transcript_id']='trn_foreign_revision'
            elif mode=='transcript-version':s.metadata['transcript_revision']['version']+=99
            else:source(s).clips[0].metadata['source_checksum_sha256']='f'*64
        await change_fixture(a,adjust)
    before=await state(a)
    result=await put(a)
    assert result.status_code==409,result.text
    assert await state(a)==before


async def test_restored_old_selected_transcript_is_used_instead_of_latest_revision(linked_api):
    from app.transcript_editing import edit_transcript
    from app.auto_edit_models import TranscriptEditRequest
    a=linked_api; original=a.analysis.transcript
    derived=await edit_transcript(a.repository,a.project.project_id,a.analysis.analysis_id,
        TranscriptEditRequest(expected_version=1,expected_timeline_version=1,
            segments=[{'segment_id':original.segments[0].segment_id,'text':'NEWER FIXTURE TEXT MUST NOT REPLACE OLD SELECTION'}]),
        'usr:fixture-editor')
    assert derived.transcript.version==2
    a.timeline=await a.service.restore(a.project.project_id,TimelineRestoreRequest(expected_version=2,restore_version=1))
    result=await put(a)
    assert result.status_code==200,result.text
    saved=result.json()['receipt']['source']
    assert saved['transcript_id']==original.transcript_id and saved['transcript_version']==1
    assert (await a.repository.get_analysis(a.analysis.analysis_id)).transcript.version==2
    current=await a.timelines.get_timeline(a.project.project_id)
    assert all('NEWER FIXTURE' not in c.label for t in current.snapshot.tracks if t.kind=='subtitles' for c in t.clips)


async def test_silent_measured_source_allows_empty_audio_and_no_transcript_without_fabrication(linked_api):
    a=linked_api
    async with a.sessions() as session:
        row=await session.get(AutoEditAnalysisORM,a.analysis.analysis_id)
        row.source_media_json={**row.source_media_json,'audio_codec':None,'audio_channels':None,'audio_sample_rate':None}
        await session.commit()
    def adjust(s):
        audio(s).clips=[];s.metadata['transcript_revision']=None
        next(t for t in s.tracks if t.kind=='subtitles').clips=[]
    await change_fixture(a,adjust)
    result=await put(a)
    assert result.status_code==200,result.text
    saved=result.json()['receipt']['source']
    assert saved['has_audio'] is False and saved['transcript_id'] is None
    current=await a.timelines.get_timeline(a.project.project_id)
    assert audio(current.snapshot).clips==[]
    assert all(not t.clips for t in current.snapshot.tracks if t.kind=='subtitles')


@pytest.mark.parametrize('kind',['original_audio','subtitles'])
async def test_silent_source_empty_locked_track_is_not_touched(linked_api,kind):
    a=linked_api
    async with a.sessions() as session:
        row=await session.get(AutoEditAnalysisORM,a.analysis.analysis_id)
        row.source_media_json={**row.source_media_json,'audio_codec':None,'audio_channels':None,'audio_sample_rate':None}
        await session.commit()
    def adjust(s):
        audio(s).clips=[];s.metadata['transcript_revision']=None
        next(t for t in s.tracks if t.kind=='subtitles').clips=[]
        next(t for t in s.tracks if t.kind==kind).locked=True
    await change_fixture(a,adjust)
    kept=next(t for t in a.timeline.snapshot.tracks if t.kind==kind).model_dump(mode='json')
    result=await put(a)
    assert result.status_code==200,result.text
    current=await a.timelines.get_timeline(a.project.project_id)
    assert next(t for t in current.snapshot.tracks if t.kind==kind).model_dump(mode='json')==kept


async def test_tail_trim_preserves_unchanged_locked_derived_caption_bytes(linked_api):
    a=linked_api
    await change_fixture(a,lambda s:setattr(next(t for t in s.tracks if t.kind=='subtitles'),'locked',True))
    kept=next(t for t in a.timeline.snapshot.tracks if t.kind=='subtitles').model_dump(mode='json')
    clip=max(source(a.timeline.snapshot).clips,key=lambda c:c.source_end)
    end=max(s.end_seconds for s in a.analysis.transcript.segments)+.1
    assert clip.source_start < end < clip.source_end
    result=await put(a,body(a,[dict(type='trim',clip_id=clip.clip_id,source_end=end)]))
    assert result.status_code==200,result.text
    current=await a.timelines.get_timeline(a.project.project_id)
    assert next(t for t in current.snapshot.tracks if t.kind=='subtitles').model_dump(mode='json')==kept
    assert current.snapshot.metadata['linked_source_edit']['captions_retimed_from_saved_transcript'] is False
    assert_av(current.snapshot)


async def test_independent_caption_edit_history_is_preserved_and_its_lock_does_not_block_other_tracks(linked_api):
    a=linked_api
    caption=next(t for t in a.timeline.snapshot.tracks if t.kind=='subtitles').clips[0]
    a.timeline=await a.service.mutate(a.project.project_id,TimelineMutationRequest(expected_version=1,
        operations=[TimelineOperation(type='move',clip_id=caption.clip_id,timeline_start=caption.timeline_start+.1)]))
    target=next(t for t in a.timeline.snapshot.tracks if t.kind=='subtitles')
    a.timeline=await a.service.mutate(a.project.project_id,TimelineMutationRequest(expected_version=2,
        operations=[TimelineOperation(type='set_track_state',track_id=target.track_id,locked=True)]))
    kept=next(t for t in a.timeline.snapshot.tracks if t.track_id==target.track_id).model_dump(mode='json')
    result=await put(a)
    assert result.status_code==200,result.text
    current=await a.timelines.get_timeline(a.project.project_id)
    assert next(t for t in current.snapshot.tracks if t.track_id==target.track_id).model_dump(mode='json')==kept
    assert_av(current.snapshot)


async def test_audio_fade_too_long_for_new_window_rejects_without_resetting_it(linked_api):
    a=linked_api
    def adjust(s):
        clip=audio(s).clips[0]
        clip.transition_out.kind='fade';clip.transition_out.duration_seconds=clip.duration
    await change_fixture(a,adjust); before=await state(a)
    result=await put(a)
    assert result.status_code==409 and result.json()['detail']['code']=='SOURCE_AUDIO_TRANSITION_REVIEW_REQUIRED'
    assert await state(a)==before


async def test_late_reservation_loss_rolls_back_without_history_or_preview_changes(linked_api):
    from sqlalchemy.ext.asyncio import AsyncSession
    a=linked_api;before=await state(a);original=AsyncSession.execute
    async def lose(self,statement,*args,**kwargs):
        if getattr(statement,'is_update',False) and getattr(statement,'table',None).name=='timelines':
            return SimpleNamespace(rowcount=0)
        return await original(self,statement,*args,**kwargs)
    with patch.object(AsyncSession,'execute',new=lose):
        result=await put(a)
    assert result.status_code==409 and await state(a)==before


def test_ram_float_word_edges_and_speed_use_measured_source_clock_without_losing_words():
    """Pure helper evidence only: representational rounding, not SQL/media/ASR."""
    from datetime import datetime,timezone
    from app.auto_edit_models import TranscriptRead
    from app.timeline_models import TimelineSnapshot,TimelineClip
    from app.source_linked_edit import apply_linked_operations,SourceLinkedEditError
    transcript=TranscriptRead(transcript_id='trn_float_fixture',analysis_id='ana_float_fixture',asset_id='ast_float_fixture',
        version=1,is_original_evidence=True,provider_key='SYNTHETIC_FLOAT_INTERVALS',language='vi',confidence=None,
        segments=[dict(segment_id='seg_float',ordinal=0,start_seconds=1.359999999999999,end_seconds=2.7,
            text='Văn Nguyễn',speaker=None,confidence=None,words=[
                dict(word_id='wrd_first',ordinal=0,start_seconds=1.359999999999999,end_seconds=1.9199999999999995,text='Văn',confidence=None),
                dict(word_id='wrd_second',ordinal=1,start_seconds=1.92,end_seconds=2.7,text='Nguyễn',confidence=None)])],
        provenance={'fixture':True},created_at=datetime.now(timezone.utc))
    def snapshot(speed):
        fields=dict(asset_id='ast_float_fixture',source_start=1.2,source_end=3.2,timeline_start=0,duration=2/speed,speed=speed)
        return TimelineSnapshot(duration_seconds=2/speed,tracks=[
            TimelineTrack(track_id='trk_source',type='video',kind='source',label='Source',order=0,
                clips=[TimelineClip(clip_id='clip_source',kind='source',label='Source',**fields)]),
            TimelineTrack(track_id='trk_audio',type='audio',kind='original_audio',label='Audio',order=1,
                clips=[TimelineClip(clip_id='clip_audio',kind='original_audio',label='Audio',**fields)]),
            TimelineTrack(track_id='trk_caps',type='text',kind='subtitles',label='Captions',order=2,clips=[])])
    for speed in (1,2):
        for point in (1.359999999999999,1.36,1.9199999999999995,1.92):
            result,_=apply_linked_operations(snapshot(speed),[TimelineOperation(type='split',clip_id='clip_source',
                at_seconds=(point-1.2)/speed)],transcript=transcript,source_asset_id='ast_float_fixture',source_duration=4,has_audio=True)
            assert_av(result)
            words=[w for t in result.tracks if t.kind=='subtitles' for c in t.clips for w in c.metadata['measured_source_words']]
            assert [w['text'] for w in words]==['Văn','Nguyễn']
            assert words[0]['start_seconds']==1.359999999999999
        with pytest.raises(SourceLinkedEditError,match='SOURCE_SPLIT_TOUCHES_SPEECH'):
            apply_linked_operations(snapshot(speed),[TimelineOperation(type='split',clip_id='clip_source',at_seconds=(1.64-1.2)/speed)],
                transcript=transcript,source_asset_id='ast_float_fixture',source_duration=4,has_audio=True)


async def test_duplicate_explicit_ripple_position_follows_selected_shot_and_preserves_gain(linked_api):
    a=linked_api
    def adjust(s):
        for kind in ('source','original_audio'):
            track=next(t for t in s.tracks if t.kind==kind);template=track.clips[0]
            track.clips=[]
            for i,(start,end) in enumerate(((0.,3.),(3.,6.),(6.,16.))):
                clip=template.model_copy(deep=True,update={'clip_id':f'clip_position_{kind}_{i}',
                    'source_start':start,'source_end':end,'timeline_start':start,'duration':end-start,
                    'speed':1.,'volume':.2*(i+1) if kind=='original_audio' else template.volume})
                track.clips.append(clip)
    await change_fixture(a,adjust)
    first=source(a.timeline.snapshot).clips[0]
    result=await put(a,body(a,[dict(type='duplicate',clip_id=first.clip_id,timeline_start=3)]))
    assert result.status_code==200,result.text
    current=await a.timelines.get_timeline(a.project.project_id)
    clips=source(current.snapshot).clips
    assert [c.source_start for c in clips]==[0.,0.,3.,6.]
    assert clips[1].timeline_start==3. and clips[1].clip_id!=first.clip_id
    assert [c.volume for c in audio(current.snapshot).clips]==pytest.approx([.2,.2,.4,.6])
    assert_av(current.snapshot)


@pytest.mark.parametrize('method',['GET','PUT'])
async def test_explicit_sqlite_read_snapshot_precedes_source_timeline_select(linked_api,method):
    from sqlalchemy import event
    a=linked_api;observed=[]
    def audit(conn,cursor,statement,parameters,context,executemany):
        normalized=' '.join(statement.split()).lower()
        if normalized.startswith('select') and 'from timelines' in normalized:
            observed.append(conn.connection.driver_connection.in_transaction)
    event.listen(a.engine.sync_engine,'before_cursor_execute',audit)
    try:
        result=await (a.client.get(a.path,headers=TEST_HUMAN_HEADERS) if method=='GET' else put(a))
    finally:event.remove(a.engine.sync_engine,'before_cursor_execute',audit)
    assert result.status_code==200,result.text
    assert observed and all(observed),observed
