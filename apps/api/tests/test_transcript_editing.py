"""Synthetic provider evidence; immutable/atomic transcript editing, no provider calls."""
import copy
from unittest.mock import AsyncMock,patch
import pytest
from sqlalchemy import select,func
from app.auto_edit_models import AutoEditAnalysisRequest,TranscriptEditRequest
from app.auto_edit_db import TranscriptORM,TranscriptSegmentORM,TranscriptWordORM
from app.timeline_db import TimelineORM,PreviewJobORM
from app.timeline_logic import build_initial_timeline
from app.timeline_repository import TimelineRepository
from app.timeline_models import TimelineSnapshot,TimelineMutationRequest,TimelineOperation
from app.transcript_editing import edit_transcript,TranscriptEditConflict
from app.production_logic import derive_subtitle_cues
from test_auto_edit_analysis import setup_services,upload_fixture,synthetic_mp4


async def stack(tmp_path):
    engine,sessions,platform,repository,uploads,analyses,project,version=await setup_services(tmp_path)
    upload=await upload_fixture(uploads,project,version,synthetic_mp4())
    result=await analyses.analyze(project.project_id,AutoEditAnalysisRequest(asset_id=upload.asset_id))
    source=await repository.get_asset(upload.asset_id)
    snapshot=build_initial_timeline(analysis=result,source_asset=source,media_plan=None,media_assets={})
    timelines=TimelineRepository(sessions)
    timeline,_=await timelines.create_timeline(project_id=project.project_id,source_analysis_id=result.analysis_id,source_media_plan_id=None,
        snapshot=snapshot,actor_ref='SYNTHETIC FIXTURE')
    return engine,sessions,repository,project,result,timelines,timeline


def edit(analysis,timeline,**values):
    return TranscriptEditRequest(expected_version=analysis.transcript.version,expected_timeline_version=timeline.current_version,
        segments=[{'segment_id':analysis.transcript.segments[0].segment_id,'text':'Nội dung do người biên tập sửa.'}],**values)


async def rows(sessions):
    async with sessions() as s:
        return {'transcripts':await s.scalar(select(func.count()).select_from(TranscriptORM)),
                'segments':await s.scalar(select(func.count()).select_from(TranscriptSegmentORM)),
                'words':await s.scalar(select(func.count()).select_from(TranscriptWordORM))}


@pytest.mark.asyncio
async def test_immutable_versions_atomically_change_canonical_subtitles_and_invalidate_preview(tmp_path):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        original=analysis.transcript.model_dump(mode='json');old_snapshot=copy.deepcopy(timeline.snapshot.model_dump(mode='json'))
        preview,_=await timelines.create_preview(project_id=project.project_id,timeline_version=1,width=540,height=960,actor_ref='fixture')
        async with sessions() as s:
            row=await s.scalar(select(TimelineORM).where(TimelineORM.project_id==project.project_id))
            row.approval_status='approved';row.approved_timeline_version=1;await s.commit()
        result=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,timeline),'editor-fixture')
        self_transcript=result.transcript
        assert self_transcript.version==original['version']+1 and not self_transcript.is_original_evidence
        assert self_transcript.segments[0].text=='Nội dung do người biên tập sửa.'
        assert self_transcript.segments[0].words==[] and self_transcript.segments[0].confidence is None
        assert self_transcript.segments[1].words
        assert self_transcript.provenance['remote_calls']==0
        newer=await timelines.get_timeline(project.project_id)
        assert newer.current_version==2 and newer.approval_status=='draft' and newer.approved_timeline_version is None
        assert newer.latest_preview_id is None
        cues=derive_subtitle_cues(newer.snapshot)
        assert cues[0].text=='Nội dung do người biên tập sửa.' and cues[0].words==[]
        old=await timelines.get_version_by_id(timeline.current_version_id)
        assert old.snapshot.model_dump(mode='json')==old_snapshot
        async with sessions() as s:
            first=await s.get(TranscriptORM,original['transcript_id'])
            assert first.is_original_evidence and first.version==original['version']
            first_segments=(await s.scalars(select(TranscriptSegmentORM).where(TranscriptSegmentORM.transcript_id==first.transcript_id).order_by(TranscriptSegmentORM.ordinal))).all()
            assert [x.text for x in first_segments]==[x['text'] for x in original['segments']]
            words=await s.scalar(select(func.count()).select_from(TranscriptWordORM).where(TranscriptWordORM.transcript_id==first.transcript_id))
            assert words==sum(len(x['words']) for x in original['segments'])
            stale=await s.get(PreviewJobORM,preview.preview_id)
            assert stale.status=='stale' and stale.cancellation_requested
        second=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(result,newer),'editor-fixture')
        assert second.transcript.version==result.transcript.version  # No-op creates no spurious version.
    finally:await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['transcript','timeline','foreign-segment','locked'])
async def test_stale_foreign_or_locked_edit_changes_nothing(tmp_path,failure):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        payload=edit(analysis,timeline)
        if failure=='transcript':payload.expected_version+=1
        if failure=='timeline':payload.expected_timeline_version+=1
        if failure=='foreign-segment':payload.segments[0].segment_id='seg_foreign_fixture'
        if failure=='locked':
            snap=timeline.snapshot.model_copy(deep=True)
            next(t for t in snap.tracks if t.kind=='subtitles').locked=True
            timeline=await timelines.commit_mutation(project_id=project.project_id,expected_version=1,snapshot=snap,mutation={'type':'fixture-lock'},actor_ref='fixture')
            payload.expected_timeline_version=timeline.current_version
        before=await rows(sessions)
        with pytest.raises(TranscriptEditConflict):await edit_transcript(repo,project.project_id,analysis.analysis_id,payload,'editor')
        assert await rows(sessions)==before
        assert (await timelines.get_timeline(project.project_id)).current_version==timeline.current_version
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_failure_between_transcript_and_timeline_rolls_back_both(tmp_path):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        before=await rows(sessions)
        with patch.object(TimelineRepository,'commit_mutation_in_session',new=AsyncMock(side_effect=RuntimeError('storage fixture failure'))):
            with pytest.raises(RuntimeError,match='storage fixture failure'):
                await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,timeline),'editor')
        assert await rows(sessions)==before
        assert (await repo.get_analysis(analysis.analysis_id)).transcript.version==analysis.transcript.version
        assert (await timelines.get_timeline(project.project_id)).current_version==1
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_long_vietnamese_edit_is_not_truncated_or_given_fake_word_alignment(tmp_path):
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        text=' '.join(['Tôn trọng dấu tiếng Việt và kiểm tra nguồn.']*7)
        payload=edit(analysis,timeline);payload.segments[0].text=text
        result=await edit_transcript(repo,project.project_id,analysis.analysis_id,payload,'editor')
        newer=await timelines.get_timeline(project.project_id)
        segment_id=result.transcript.segments[0].segment_id
        changed=[c for t in newer.snapshot.tracks for c in t.clips if c.metadata.get('segment_id')==segment_id]
        assert changed[0].metadata['subtitle_text']==text
        only=newer.snapshot.model_copy(deep=True)
        only.tracks=[t.model_copy(update={'clips':changed}) for t in only.tracks if t.kind=='subtitles']
        cues=derive_subtitle_cues(only)
        assert ' '.join(c.text for c in cues)==text and all(not c.words for c in cues)
        assert len(cues)>1
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_http_editor_required_and_authenticated_identity_recorded(tmp_path):
    from httpx import ASGITransport,AsyncClient
    from types import SimpleNamespace
    from app.main import app
    from app.repositories import PlatformRepository
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    engine,sessions,repo,project,analysis,_,timeline=await stack(tmp_path)
    try:
        platform=PlatformRepository(sessions)
        app.state.auto_edit_analysis_service=SimpleNamespace(repository=repo)
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        endpoint=f'/api/v1/projects/{project.project_id}/analyses/{analysis.analysis_id}/transcript'
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(endpoint,json=edit(analysis,timeline).model_dump())).status_code==401
            denied=await client.post(endpoint,json=edit(analysis,timeline).model_dump(),headers=TEST_HUMAN_HEADERS)
            assert denied.status_code==403
            assert (await repo.get_analysis(analysis.analysis_id)).transcript.version==analysis.transcript.version
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            accepted=await client.post(endpoint,json=edit(analysis,timeline).model_dump(),headers=TEST_HUMAN_HEADERS)
            assert accepted.status_code==200
            assert accepted.json()['transcript']['provenance']['actor_ref']=='usr:test-owner'
            replay=await client.post(endpoint,json=edit(analysis,timeline).model_dump(),headers=TEST_HUMAN_HEADERS)
            assert replay.status_code==409 and replay.json()['detail']['error']['code']=='TRANSCRIPT_EDIT_CONFLICT'
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_restore_selects_original_transcript_and_new_edit_branches_without_rewriting_history(tmp_path):
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        result=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,timeline),'editor')
        restored=await timelines.commit_mutation(project_id=project.project_id,expected_version=2,snapshot=timeline.snapshot,
            mutation={'type':'restore','restored_from_version':1},actor_ref='editor')
        original=await repo.get_analysis(analysis.analysis_id,transcript_id=analysis.transcript.transcript_id)
        assert original.transcript.version==1 and original.transcript.is_original_evidence
        assert original.provenance['human_transcript_revision']==2
        payload=edit(original,restored);payload.expected_version=2;payload.base_transcript_id=original.transcript.transcript_id
        payload.segments[0].text='Một bản sửa khác sau khi hoàn tác.'
        newest=await edit_transcript(repo,project.project_id,analysis.analysis_id,payload,'editor')
        assert newest.transcript.version==3 and newest.transcript.provenance['derived_from_version']==1
        prior=await repo.get_analysis(analysis.analysis_id,transcript_id=result.transcript.transcript_id)
        assert prior.transcript.segments[0].text=='Nội dung do người biên tập sửa.'
        assert await repo.get_analysis(analysis.analysis_id,transcript_id='trn_foreign_missing') is None
    finally:await engine.dispose()
