"""SQL/API checks with synthetic ASR evidence; never Owner/provider acceptance."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auto_edit_db import TranscriptORM
from app.main import app
from app.production_logic import derive_subtitle_cues
from app.repositories import PlatformRepository
from app.timeline_db import PreviewJobORM, TimelineORM
from app.timeline_logic import apply_operations
from app.timeline_models import TimelineOperation
from app.timeline_repository import TimelineRepository
from app.transcript_word_editing import edit_transcript_words, TranscriptWordEditConflict
from app.transcript_word_review import WordReview
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_transcript_editing import stack, rows


def review(analysis, timeline=None):
    segment = analysis.transcript.segments[0]
    words = [dict(word_id=w.word_id, text=w.text, start_seconds=w.start_seconds, end_seconds=w.end_seconds)
        for w in segment.words]
    words[0].update(text='Vinhomes', start_seconds=words[0]['start_seconds']+.01)
    return WordReview(expected_version=analysis.transcript.version,
        expected_transcript_id=analysis.transcript.transcript_id,
        expected_timeline_version=timeline.current_version if timeline else None, acknowledged=True,
        segments=[dict(segment_id=segment.segment_id, start_seconds=segment.start_seconds,
            end_seconds=segment.end_seconds, words=words)], note='SYNTHETIC MANUAL TIMING FIXTURE')


@pytest.mark.asyncio
async def test_word_revision_preserves_asr_and_invalidates_preview_approval_atomically(tmp_path):
    engine, sessions, repo, project, analysis, timelines, timeline = await stack(tmp_path)
    try:
        original = analysis.transcript.model_dump(mode='json')
        old_snapshot = timeline.snapshot.model_dump(mode='json')
        preview, _ = await timelines.create_preview(project_id=project.project_id, timeline_version=1,
            width=540, height=960, actor_ref='SYNTHETIC FIXTURE')
        async with sessions() as session:
            t = await session.scalar(select(TimelineORM).where(TimelineORM.project_id==project.project_id))
            t.approval_status='approved';t.approved_timeline_version=1
            await session.commit()
        payload = review(analysis, timeline)
        with patch('app.auto_edit_providers.DeterministicTranscriptionProvider.transcribe',
                   new=AsyncMock(side_effect=AssertionError('word edits must not call ASR'))):
            result = await edit_transcript_words(repo, project.project_id, analysis.analysis_id, payload, 'usr:verified-editor')
        transcript = result.transcript
        assert transcript.version==2 and not transcript.is_original_evidence
        assert transcript.provenance['actor_ref']=='usr:verified-editor'
        assert transcript.provenance['timing_independently_measured'] is False
        assert transcript.provenance['remote_calls']==0
        assert transcript.confidence is None
        assert transcript.segments[0].text.startswith('Vinhomes ')
        assert all(w.confidence is None for w in transcript.segments[0].words)
        assert transcript.segments[1].words[0].confidence==original['segments'][1]['words'][0]['confidence']
        prior = await repo.get_analysis(analysis.analysis_id, transcript_id=original['transcript_id'])
        assert prior.transcript.model_dump(mode='json')==original
        current = await timelines.get_timeline(project.project_id)
        assert current.current_version==2 and current.approval_status=='draft'
        assert current.approved_timeline_version is None and current.latest_preview_id is None
        assert [t.model_dump(mode='json') for t in current.snapshot.tracks if t.kind!='subtitles']==[
            t for t in old_snapshot['tracks'] if t['kind']!='subtitles']
        old = await timelines.get_version_by_id(timeline.current_version_id)
        assert old.snapshot.model_dump(mode='json')==old_snapshot
        cues = derive_subtitle_cues(current.snapshot)
        assert cues[0].words[0].text=='Vinhomes'
        first_clip = next(c for t in current.snapshot.tracks if t.kind=='subtitles' for c in t.clips)
        assert first_clip.metadata['timing_source']=='human_supplied_source_word_intervals'
        assert first_clip.metadata['timing_independently_measured'] is False
        async with sessions() as session:
            stale = await session.get(PreviewJobORM, preview.preview_id)
            assert stale.status=='stale' and stale.cancellation_requested
        with pytest.raises(TranscriptWordEditConflict):
            await edit_transcript_words(repo, project.project_id, analysis.analysis_id, payload, 'usr:verified-editor')
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['transcript-id','transcript-version','timeline','foreign-segment','foreign-word','locked','cut'])
async def test_stale_foreign_locked_and_cut_conflicts_leave_every_history_intact(tmp_path, failure):
    engine, sessions, repo, project, analysis, timelines, timeline = await stack(tmp_path)
    try:
        payload = review(analysis, timeline)
        if failure=='transcript-id':payload.expected_transcript_id='trn_'+'f'*24
        if failure=='transcript-version':payload.expected_version+=1
        if failure=='timeline':payload.expected_timeline_version+=1
        if failure=='foreign-segment':payload.segments[0].segment_id='seg_'+'f'*24
        if failure=='foreign-word':payload.segments[0].words[0].word_id='wrd_'+'f'*24
        if failure in {'locked','cut'}:
            snapshot = timeline.snapshot.model_copy(deep=True)
            if failure=='locked':next(t for t in snapshot.tracks if t.kind=='subtitles').locked=True
            else:
                word = payload.segments[0].words[0]
                # Moving the first source boundary through a word must never
                # silently truncate that manually supplied interval.
                first = next(t for t in snapshot.tracks if t.kind=='source').clips[0]
                first.source_start=(word.start_seconds+word.end_seconds)/2
                first.duration=(first.source_end-first.source_start)/first.speed
            timeline = await timelines.commit_mutation(project_id=project.project_id, expected_version=1,
                snapshot=snapshot, mutation={'type':'SYNTHETIC TEST CHANGE'}, actor_ref='fixture')
            payload.expected_timeline_version=timeline.current_version
        before = await rows(sessions)
        with pytest.raises(TranscriptWordEditConflict):
            await edit_transcript_words(repo, project.project_id, analysis.analysis_id, payload, 'usr:editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).current_version==timeline.current_version
        assert (await repo.get_analysis(analysis.analysis_id)).transcript.version==analysis.transcript.version
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_failure_between_word_version_and_canonical_commit_rolls_back(tmp_path):
    engine, sessions, repo, project, analysis, timelines, timeline = await stack(tmp_path)
    try:
        before = await rows(sessions)
        with patch.object(TimelineRepository, 'commit_mutation_in_session',
                          new=AsyncMock(side_effect=RuntimeError('synthetic disk failure'))):
            with pytest.raises(RuntimeError, match='synthetic disk failure'):
                await edit_transcript_words(repo, project.project_id, analysis.analysis_id, review(analysis,timeline), 'usr:editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).current_version==1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_source_speed_and_offset_map_explicit_words_without_changing_media(tmp_path):
    engine, _, repo, project, analysis, timelines, timeline = await stack(tmp_path)
    try:
        snapshot = timeline.snapshot.model_copy(deep=True)
        # Source media is intentionally speed-adjusted; captions follow those
        # exact retained windows, rather than original source seconds as output.
        for track in snapshot.tracks:
            if track.kind not in {'source','original_audio'}:continue
            for clip in track.clips:
                clip.speed=2
                clip.duration/=2
                clip.timeline_start=1+clip.timeline_start/2
        timeline = await timelines.commit_mutation(project_id=project.project_id, expected_version=1,
            snapshot=snapshot, mutation={'type':'SYNTHETIC SPEED CHANGE'}, actor_ref='fixture')
        payload = review(analysis,timeline)
        result = await edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor')
        current = await timelines.get_timeline(project.project_id)
        segment = result.transcript.segments[0]
        caption = next(c for t in current.snapshot.tracks if t.kind=='subtitles' for c in t.clips
            if c.metadata.get('segment_id')==segment.segment_id)
        assert caption.speed==2
        source = next(c for t in current.snapshot.tracks if t.kind=='source' for c in t.clips
            if c.source_start<=segment.start_seconds<c.source_end)
        assert caption.timeline_start==pytest.approx(source.timeline_start+(segment.start_seconds-source.source_start)/2)
        assert caption.duration==pytest.approx((caption.source_end-caption.source_start)/2)
        assert [t.model_dump(mode='json') for t in current.snapshot.tracks if t.kind!='subtitles']==[
            t.model_dump(mode='json') for t in timeline.snapshot.tracks if t.kind!='subtitles']
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_manual_caption_move_is_preserved_by_conflict_not_silently_replaced(tmp_path):
    engine, sessions, repo, project, analysis, timelines, timeline = await stack(tmp_path)
    try:
        caption = next(t for t in timeline.snapshot.tracks if t.kind=='subtitles').clips[0]
        operation=TimelineOperation(type='move',clip_id=caption.clip_id,timeline_start=caption.timeline_start+.1)
        snapshot=apply_operations(timeline.snapshot,[operation])
        timeline=await timelines.commit_mutation(project_id=project.project_id,expected_version=1,snapshot=snapshot,
            mutation={'type':'edit','operations':[operation.model_dump(mode='json',exclude_none=True)]},actor_ref='fixture')
        before=await rows(sessions)
        with pytest.raises(TranscriptWordEditConflict,match='manually edited'):
            await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).snapshot==snapshot
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_http_auth_workspace_body_guards_verified_actor_and_stale_replay(tmp_path):
    engine, sessions, repo, project, analysis, _, timeline = await stack(tmp_path)
    try:
        platform=PlatformRepository(sessions)
        app.state.auto_edit_analysis_service=SimpleNamespace(repository=repo)
        endpoint=f'/api/v1/projects/{project.project_id}/analyses/{analysis.analysis_id}/transcript-words'
        body=review(analysis,timeline).model_dump(mode='json')
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(endpoint,json=body)).status_code==401
            assert (await client.post(endpoint,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=platform,platform_role=None,workspace_roles={'wsp_foreign':'editor'})
            assert (await client.post(endpoint,json=body,headers=TEST_HUMAN_HEADERS)).status_code==404
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            for invalid in ({**body,'actor_ref':'usr:forged'},{**body,'acknowledged':False},{**body,'acknowledged':1}):
                assert (await client.post(endpoint,json=invalid,headers=TEST_HUMAN_HEADERS)).status_code==422
            accepted=await client.post(endpoint,json=body,headers=TEST_HUMAN_HEADERS)
            assert accepted.status_code==200,accepted.text
            assert accepted.json()['transcript']['provenance']['actor_ref']=='usr:test-owner'
            assert accepted.json()['transcript']['provenance']['timing_independently_measured'] is False
            stale=await client.post(endpoint,json=body,headers=TEST_HUMAN_HEADERS)
            assert stale.status_code==409 and stale.json()['detail']['error']['code']=='TRANSCRIPT_WORD_EDIT_CONFLICT'
            foreign=f'/api/v1/projects/{project.project_id}/analyses/ana_foreign/transcript-words'
            assert (await client.post(foreign,json=body,headers=TEST_HUMAN_HEADERS)).status_code==404
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_versioned_words_before_timeline_preserve_source_and_declared_clock_gaps(tmp_path):
    from app.auto_edit_models import AutoEditAnalysisRequest
    from test_auto_edit_analysis import setup_services, upload_fixture, synthetic_mp4
    engine,sessions,_,repo,uploads,analyses,project,version=await setup_services(tmp_path)
    try:
        upload=await upload_fixture(uploads,project,version,synthetic_mp4())
        analysis=await analyses.analyze(project.project_id,AutoEditAnalysisRequest(asset_id=upload.asset_id))
        async with sessions() as session:
            row=await session.get(TranscriptORM,analysis.transcript.transcript_id)
            row.provenance_json={**row.provenance_json,'decoded_source_clock':{
                'contiguous':True,'source_start_seconds':1.,'source_end_seconds':16.}}
            await session.commit()
        payload=review(analysis)
        with pytest.raises(TranscriptWordEditConflict,match='SOURCE_AUDIO_GAP'):
            await edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor')
        async with sessions() as session:
            row=await session.get(TranscriptORM,analysis.transcript.transcript_id)
            row.provenance_json={**row.provenance_json,'decoded_source_clock':{
                'contiguous':True,'source_start_seconds':0.,'source_end_seconds':16.}}
            await session.commit()
        result=await edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor')
        assert result.transcript.version==2
        assert await TimelineRepository(sessions).get_timeline(project.project_id) is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_restore_branches_from_selected_evidence_without_reusing_revision_numbers(tmp_path):
    engine, _, repo, project, analysis, timelines, timeline=await stack(tmp_path)
    try:
        second=await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        restored=await timelines.commit_mutation(project_id=project.project_id,expected_version=2,
            snapshot=timeline.snapshot,mutation={'type':'restore','restored_from_version':1},actor_ref='usr:editor')
        payload=review(analysis,restored)
        payload.expected_version=second.transcript.version
        payload.segments[0].words[0].text='Green'
        third=await edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor')
        assert third.transcript.version==3
        assert third.transcript.provenance['derived_from_transcript_id']==analysis.transcript.transcript_id
        assert third.transcript.provenance['derived_from_version']==1
        assert (await repo.get_analysis(analysis.analysis_id,transcript_id=second.transcript.transcript_id)).transcript==second.transcript
        assert (await repo.get_analysis(analysis.analysis_id,transcript_id=analysis.transcript.transcript_id)).transcript==analysis.transcript
        assert (await timelines.get_timeline(project.project_id)).current_version==4
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_deleted_manual_captions_are_not_recreated_by_word_review(tmp_path):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        caption=next(t for t in timeline.snapshot.tracks if t.kind=='subtitles').clips[0]
        operation=TimelineOperation(type='delete',clip_id=caption.clip_id)
        snapshot=apply_operations(timeline.snapshot,[operation])
        timeline=await timelines.commit_mutation(project_id=project.project_id,expected_version=1,snapshot=snapshot,
            mutation={'type':'edit','operations':[operation.model_dump(mode='json',exclude_none=True)]},actor_ref='fixture')
        before=await rows(sessions)
        with pytest.raises(TranscriptWordEditConflict,match='manually edited'):
            await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).snapshot==snapshot
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_registered_asset_checksum_corruption_rejects_revision(tmp_path):
    from app.db import AssetORM
    engine,sessions,repo,project,analysis,_,timeline=await stack(tmp_path)
    try:
        async with sessions() as session:
            asset=await session.get(AssetORM,analysis.asset_id)
            asset.checksum_sha256='f'*64
            await session.commit()
        before=await rows(sessions)
        with pytest.raises(TranscriptWordEditConflict,match='checksum'):
            await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        assert await rows(sessions)==before
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_actual_production_approval_and_render_records_are_invalidated_by_word_revision(tmp_path):
    from app.production_repository import ProductionRepository
    from app.production_models import SubtitleStyle,MixConfig
    from app.production_db import ProductionPackageORM,ProductionApprovalORM,ProductionRenderJobORM,ProductionEventORM
    engine,sessions,repo,project,analysis,_,timeline=await stack(tmp_path)
    try:
        package,_=await ProductionRepository(sessions).create_or_refresh_package(timeline=timeline,
            cues=derive_subtitle_cues(timeline.snapshot),style=SubtitleStyle(),mix_config=MixConfig(),
            provider_status='not_configured',actor_ref='usr:fixture')
        async with sessions() as session:
            common=dict(package_id=package.package_id,project_id=project.project_id,
                timeline_version_id=timeline.current_version_id,timeline_version=1,
                subtitle_version_id=package.subtitle.subtitle_version_id,subtitle_version=1,
                audio_version_id=package.audio_mix.audio_version_id,audio_version=1)
            session.add(ProductionApprovalORM(approval_id='apr_word_fixture',**common,
                preview_render_id='rnd_word_fixture',preview_version=1,status='approved',requester_ref='usr:fixture'))
            session.add(ProductionRenderJobORM(render_id='rnd_word_fixture',version=1,**common,
                workspace_id=project.workspace_id,timeline_id=timeline.timeline_id,approval_id='apr_word_fixture',
                render_kind='final',profile='vertical-1080x1920',status='ready'))
            row=await session.get(ProductionPackageORM,package.package_id)
            row.current_approval_id='apr_word_fixture';row.latest_final_render_id='rnd_word_fixture'
            await session.commit()
        await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        async with sessions() as session:
            approval=await session.get(ProductionApprovalORM,'apr_word_fixture')
            render=await session.get(ProductionRenderJobORM,'rnd_word_fixture')
            package_row=await session.get(ProductionPackageORM,package.package_id)
            assert approval.status=='changes_requested' and approval.invalidated_reason=='timeline-version-changed'
            assert render.status=='stale' and render.cancellation_requested and render.invalidated_at is not None
            assert package_row.current_approval_id is None and package_row.latest_final_render_id is None
            event=await session.scalar(select(ProductionEventORM).where(ProductionEventORM.event_type=='production_package.invalidated'))
            assert event.actor_ref=='usr:editor'
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_explicit_add_remove_words_have_new_ids_and_no_inherited_confidence(tmp_path):
    engine,_,repo,project,analysis,_,timeline=await stack(tmp_path)
    try:
        payload=review(analysis,timeline)
        original=payload.segments[0].words[0]
        end=original.end_seconds
        middle=(original.start_seconds+end)/2
        original.end_seconds=middle
        from app.transcript_word_review import Word
        payload.segments[0].words.insert(1,Word(text='Park',start_seconds=middle,end_seconds=end))
        payload.segments[0].words.pop()
        result=await edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor')
        words=result.transcript.segments[0].words
        assert [w.text for w in words]==[w.text for w in payload.segments[0].words]
        assert [(w.start_seconds,w.end_seconds) for w in words]==[(w.start_seconds,w.end_seconds) for w in payload.segments[0].words]
        assert all(w.confidence is None for w in words)
        assert not {w.word_id for w in words}&{w.word_id for w in analysis.transcript.segments[0].words}
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_same_revision_produces_one_version_and_one_conflict(tmp_path):
    import asyncio
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        payload=review(analysis,timeline)
        results=await asyncio.gather(*[
            edit_transcript_words(repo,project.project_id,analysis.analysis_id,payload,'usr:editor') for _ in range(2)],
            return_exceptions=True)
        assert sum(isinstance(value,TranscriptWordEditConflict) for value in results)==1,results
        assert sum(not isinstance(value,BaseException) for value in results)==1,results
        assert (await rows(sessions))['transcripts']==2
        assert (await timelines.get_timeline(project.project_id)).current_version==2
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_locked_unchanged_caption_track_does_not_allow_identity_mutation(tmp_path):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        snapshot=timeline.snapshot.model_copy(deep=True)
        track=next(t for t in snapshot.tracks if t.kind=='subtitles')
        locked=track.model_copy(deep=True)
        locked.track_id='trk_locked_word_fixture'
        locked.order=len(snapshot.tracks)
        locked.locked=True
        locked.clips=locked.clips[1:]
        track.clips=track.clips[:1]
        snapshot.tracks.append(locked)
        timeline=await timelines.commit_mutation(project_id=project.project_id,expected_version=1,snapshot=snapshot,
            mutation={'type':'SYNTHETIC TRACK LOCK'},actor_ref='fixture')
        before=await rows(sessions)
        with pytest.raises(TranscriptWordEditConflict,match='locked'):
            await edit_transcript_words(repo,project.project_id,analysis.analysis_id,review(analysis,timeline),'usr:editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).snapshot==snapshot
    finally:
        await engine.dispose()
