"""Canonical audio mapping, SQLite transactions and explicit mock speech evidence."""
import asyncio
from pathlib import Path
from unittest.mock import patch
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.timeline_models import TimelineSnapshot, TimelineTrack, TimelineClip, TimelineOperation, TimelineMutationRequest, TimelineRestoreRequest
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService, TimelineContractValidator
from app.timeline_logic import apply_operations
from app.uploaded_audio_models import AudioCaptionApply, AudioRestore
from app.uploaded_audio_repository import AudioConflict
from app.uploaded_audio_timeline import apply, sync, refresh_after_edit, KEY
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_uploaded_audio import stack, ready, text_request, word_request, rows


def empty_timeline():
    return TimelineSnapshot(duration_seconds=2., tracks=[TimelineTrack(track_id='trk_owned_base',
        type='metadata',kind='metadata',label='Owned source clock',order=0)])


def request(row, **changes):
    return AudioCaptionApply(source_sha256=row.source_sha256,expected_transcript_id=row.current.transcript_id,
        expected_version=row.current.version,expected_timeline_version=row.timeline_version or 1,
        source_end=2.,acknowledged=True,idempotency_key='owned-caption-apply-01',**changes)


async def canonical(env):
    repo=TimelineRepository(env.sessions)
    await repo.create_timeline(project_id=env.project.project_id,source_analysis_id=None,source_media_plan_id=None,
        source_content_version_id=env.version.project_version_id,
        snapshot=empty_timeline(),actor_ref='usr:fixture-editor')
    return repo


@pytest.mark.asyncio
async def test_apply_edit_restore_atomic_canonical_and_preview_invalidation(tmp_path):
    env=await stack(tmp_path)
    try:
        first=await ready(env);repo=await canonical(env)
        first=await env.service.repository.get(env.project.project_id,first.audio_id)
        receipt=await env.service.apply_captions(env.project.project_id,first.audio_id,request(first),'usr:editor')
        assert receipt['applied_timeline_version']==2 and not receipt['replayed']
        assert (await repo.get_timeline(env.project.project_id)).source_analysis_id is None
        assert (await env.service.apply_captions(env.project.project_id,first.audio_id,request(first),'usr:editor'))['replayed']
        preview,_=await repo.create_preview(project_id=env.project.project_id,timeline_version=2,width=270,height=480,actor_ref='usr:editor')
        original=first.original.model_dump(mode='json')
        second=await env.service.repository.get(env.project.project_id,first.audio_id)
        edited=await env.service.edit_text(env.project.project_id,first.audio_id,text_request(second,'Lời mới.'),'usr:editor')
        timeline=await repo.get_timeline(env.project.project_id)
        assert timeline.current_version==3 and edited.timeline_version==3
        assert timeline.snapshot.tracks[-1].clips[0].metadata['subtitle_text']=='Lời mới.'
        assert not timeline.snapshot.tracks[-1].clips[0].metadata.get('measured_source_words')
        assert (await repo.get_preview(preview.preview_id)).status=='stale'
        restored=await env.service.restore(env.project.project_id,first.audio_id,AudioRestore(
            source_sha256=edited.source_sha256,expected_version=2,expected_transcript_id=edited.current.transcript_id,
            expected_timeline_version=3,target_transcript_id=first.original.transcript_id,acknowledged=True),'usr:editor')
        assert restored.timeline_version==4 and restored.original.model_dump(mode='json')==original
        assert env.provider.calls==1
        assert (await repo.get_timeline(env.project.project_id)).snapshot.tracks[-1].clips[0].metadata['measured_source_words'][0]['text']=='Xin'
        assert len(await repo.list_versions(env.project.project_id))==4
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['locked','manual','foreign','restored','rollback'])
async def test_bound_word_revision_conflict_rolls_back_transcript_and_timeline(tmp_path,failure):
    env=await stack(tmp_path)
    try:
        row=await ready(env);repo=await canonical(env)
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        await env.service.apply_captions(env.project.project_id,row.audio_id,request(row),'usr:editor')
        timeline=await repo.get_timeline(env.project.project_id)
        changed=timeline.snapshot.model_copy(deep=True)
        if failure=='locked':changed.tracks[-1].locked=True
        if failure=='manual':changed.tracks[-1].clips[0].metadata['human_caption_edit']=True
        if failure=='foreign':changed.tracks[-1].clips[0].metadata['audio_binding_id']='foreign'
        if failure=='restored':changed.metadata[KEY][row.audio_id]['transcript_id']='trn_'+'f'*24
        if failure!='rollback':
            await repo.commit_mutation(project_id=env.project.project_id,expected_version=2,snapshot=changed,
                mutation={'type':'edit','operations':[]},actor_ref='usr:editor')
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        before=len(await repo.list_versions(env.project.project_id))
        if failure=='rollback':
            with patch.object(TimelineRepository,'commit_mutation_in_session',side_effect=AudioConflict('OWNED_ROLLBACK')):
                with pytest.raises(AudioConflict):await env.service.edit_words(env.project.project_id,row.audio_id,word_request(row),'usr:editor')
        else:
            with pytest.raises(AudioConflict):await env.service.edit_words(env.project.project_id,row.audio_id,word_request(row),'usr:editor')
        assert len(await rows(env))==1 and len(await repo.list_versions(env.project.project_id))==before
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_voice_split_move_speed_reflows_actual_word_clock_and_rejects_speech_cuts(tmp_path):
    env=await stack(tmp_path)
    try:
        row=await ready(env)
        base,_=apply(empty_timeline(),row.current,request(row),source_duration=2.)
        voice=base.tracks[-2].clips[0]
        operations=[TimelineOperation(type='split',clip_id=voice.clip_id,at_seconds=1.),
            TimelineOperation(type='set_clip_properties',clip_id=voice.clip_id,speed=2.)]
        after=refresh_after_edit(base,apply_operations(base,operations),operations)
        cue=after.tracks[-1].clips[0]
        assert cue.speed==2. and cue.timeline_start==.05 and cue.duration==.4
        cut=[TimelineOperation(type='trim',clip_id=voice.clip_id,source_start=.2)]
        with pytest.raises(AudioConflict,match='CUT_THROUGH_SPEECH'):
            refresh_after_edit(base,apply_operations(base,cut),cut)
        manual=base.model_copy(deep=True);manual.tracks[-1].clips[0].label='Manual caption'
        with pytest.raises(AudioConflict,match='CAPTION_REVIEW'):
            refresh_after_edit(manual,apply_operations(manual,operations),operations)
        foreign=TimelineTrack(track_id='trk_other_voice',type='audio',kind='voice',label='Other voice',order=3)
        base.tracks.append(foreign)
        move=[TimelineOperation(type='move',clip_id=voice.clip_id,target_track_id=foreign.track_id)]
        with pytest.raises(AudioConflict):refresh_after_edit(base,apply_operations(base,move),move)
        base.tracks[-2].locked=True  # subtitle track, with foreign voice now last
        lock=[TimelineOperation(type='set_track_state',track_id=base.tracks[1].track_id,locked=True)]
        unchanged=refresh_after_edit(base,apply_operations(base,lock),lock)
        assert unchanged.tracks[2].model_dump(mode='json')==base.tracks[2].model_dump(mode='json')
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_apply_http_auth_scope_no_store_stale_duplicate_and_physical_tamper(tmp_path):
    env=await stack(tmp_path)
    try:
        row=await ready(env);await canonical(env)
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        app.state.uploaded_audio_service=env.service
        install_test_human_auth(app,platform_repository=env.platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        url=f'/api/v1/projects/{env.project.project_id}/audio-transcriptions/{row.audio_id}/apply-captions'
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://owned.fixture') as client:
            payload=request(row).model_dump(mode='json')
            assert (await client.post(url,json=payload,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=env.platform,platform_role='editor',workspace_roles={'*':'editor'})
            response=await client.post(url,json=payload,headers=TEST_HUMAN_HEADERS)
            assert response.status_code==200,response.text
            assert response.headers['cache-control']=='no-store'
            assert (await client.post(url,json=payload,headers=TEST_HUMAN_HEADERS)).json()['replayed']
            assert (await client.post(url,json={**payload,'speed':2},headers=TEST_HUMAN_HEADERS)).status_code==409
            asset=await env.assets.get_asset(row.asset_id)
            env.service.object_storage._path(asset.object_key).write_bytes(b'tampered')
            assert (await client.post(url,json=payload,headers=TEST_HUMAN_HEADERS)).status_code==409
            assert len(await rows(env))==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_real_timeline_service_edits_and_explicit_audio_restore_after_undo(tmp_path):
    env=await stack(tmp_path)
    try:
        row=await ready(env);repo=await canonical(env)
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        await env.service.apply_captions(env.project.project_id,row.audio_id,request(row),'usr:editor')
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        edited=await env.service.edit_text(env.project.project_id,row.audio_id,text_request(row,'Bản sửa.'),'usr:editor')
        service=TimelineService(repository=repo,platform=env.platform,auto_edit_repository=None,media_repository=None,
            validator=TimelineContractValidator(Path(__file__).parents[3]/'packages/contracts/timeline.schema.json'))
        restored=await service.restore(env.project.project_id,TimelineRestoreRequest(expected_version=3,restore_version=2,actor_ref='usr:editor'))
        row=await env.service.repository.get(env.project.project_id,row.audio_id)
        with pytest.raises(AudioConflict,match='CANONICAL_TRANSCRIPT_CHANGED'):
            await env.service.edit_text(env.project.project_id,row.audio_id,text_request(row),'usr:editor')
        selected=await env.service.restore(env.project.project_id,row.audio_id,AudioRestore(source_sha256=row.source_sha256,
            expected_version=2,expected_transcript_id=row.current.transcript_id,expected_timeline_version=4,
            target_transcript_id=row.original.transcript_id,acknowledged=True),'usr:editor')
        assert selected.current.version==3 and selected.timeline_version==5 and env.provider.calls==1
        timeline=await repo.get_timeline(env.project.project_id);voice=timeline.snapshot.tracks[-2].clips[0]
        changed=await service.mutate(env.project.project_id,TimelineMutationRequest(expected_version=5,
            operations=[TimelineOperation(type='set_clip_properties',clip_id=voice.clip_id,speed=2)],actor_ref='usr:editor'))
        assert changed.current_version==6 and changed.snapshot.tracks[-1].clips[0].timeline_start==.05
        assert (await env.service.repository.get(env.project.project_id,row.audio_id)).current.version==3
    finally:await env.engine.dispose()
