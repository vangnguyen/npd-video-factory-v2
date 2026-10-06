"""Explicit fixture ASR, real immutable persistence and canonical mutation checks."""
import pytest
from sqlalchemy import select,func
from app.auto_edit_db import HighlightDraftORM
from app.highlight_drafts import (HighlightDraftRequest,HighlightDraftApply,HighlightDraftConflict,
    create_drafts,list_drafts,apply_draft,protected_window)
from app.timeline_repository import TimelineConflictError
from app.transcript_editing import edit_transcript
from test_transcript_editing import stack,edit


@pytest.mark.asyncio
async def test_top3_top5_and_auto_shorts_save_idempotent_drafts_without_changing_active_timeline(tmp_path):
    engine,sessions,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        payload=HighlightDraftRequest(analysis_id=analysis.analysis_id,count=3)
        first=await create_drafts(repo,project.project_id,payload,'editor')
        repeated=await create_drafts(repo,project.project_id,payload,'editor')
        assert len(first)==3 and [d.draft_id for d in repeated]==[d.draft_id for d in first]
        payload.count=5
        top5=await create_drafts(repo,project.project_id,payload,'editor')
        assert len(top5)==len(analysis.scenes)==4  # Never fabricate a fifth candidate.
        assert set(d.draft_id for d in first)<=set(d.draft_id for d in top5)
        payload.count=3;payload.mode='auto_shorts'
        shorts=await create_drafts(repo,project.project_id,payload,'editor')
        assert len(shorts)==3
        assert all(d.snapshot.duration_seconds<=60 and d.evidence['provider_dispatches']==0 and d.evidence['human_approval_required'] for d in shorts)
        current=await timelines.get_timeline(project.project_id)
        assert current.current_version==timeline.current_version and current.snapshot==timeline.snapshot
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(HighlightDraftORM))==7
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_apply_requires_current_transcript_cas_locks_and_preserves_master_history(tmp_path):
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        drafts=await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id),'editor')
        payload=HighlightDraftApply(expected_timeline_version=1)
        selected=await apply_draft(repo,project.project_id,drafts[0].draft_id,payload,'editor')
        assert selected.current_version==2 and selected.approval_status=='draft'
        assert selected.snapshot.metadata['applied_highlight_draft_id']==drafts[0].draft_id
        assert (await timelines.get_version_by_id(timeline.current_version_id)).snapshot==timeline.snapshot
        assert selected.snapshot==drafts[0].snapshot.model_copy(update={'metadata':{**drafts[0].snapshot.metadata,'applied_highlight_draft_id':drafts[0].draft_id}})
        with pytest.raises(TimelineConflictError):await apply_draft(repo,project.project_id,drafts[1].draft_id,payload,'editor')
        changed=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,selected),'editor')
        with pytest.raises(HighlightDraftConflict,match='transcript changed'):
            await apply_draft(repo,project.project_id,drafts[0].draft_id,HighlightDraftApply(expected_timeline_version=3),'editor')
        new=await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id,transcript_id=changed.transcript.transcript_id),'editor')
        assert all(d.transcript_id==changed.transcript.transcript_id for d in new)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_foreign_project_or_transcript_cannot_read_or_apply_draft(tmp_path):
    engine,_,repo,project,analysis,_,_=await stack(tmp_path)
    try:
        draft=(await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id),'editor'))[0]
        assert await list_drafts(repo,'prj_foreign_fixture')==[]
        with pytest.raises(KeyError):await apply_draft(repo,'prj_foreign_fixture',draft.draft_id,HighlightDraftApply(),'editor')
        with pytest.raises(KeyError):await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id,transcript_id='trn_foreign_fixture'),'editor')
    finally:await engine.dispose()


def test_protected_window_uses_whole_segment_without_words_and_real_word_intervals():
    from test_auto_edit_studio import analysis_fixture
    analysis=analysis_fixture('prj_fixture','ast_fixture')
    assert protected_window(1,2,analysis.transcript,10)==(0,3)
    from app.auto_edit_models import TranscriptWordRead
    analysis.transcript.segments[0].words=[TranscriptWordRead(word_id='wrd_fixture',
        ordinal=0,text='nói',start_seconds=.9,end_seconds=1.2,confidence=.9)]
    assert protected_window(1,1.1,analysis.transcript,10)==(.9,1.2)


def test_captions_preserve_words_across_visual_boundaries_and_unaligned_full_text():
    from test_auto_edit_studio import analysis_fixture
    from test_silence_word_safety import asset
    from app.auto_edit_models import TranscriptWordRead
    from app.timeline_logic import build_initial_timeline
    from app.production_logic import derive_subtitle_cues
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    analysis.silence_decisions=[]
    segment=analysis.transcript.segments[0]
    analysis.transcript.segments=[segment];segment.end_seconds=6;segment.text='Giao cảnh.'
    segment.words=[TranscriptWordRead(word_id='wrd_fixture',ordinal=0,text='Giao cảnh.',start_seconds=4.9,end_seconds=5.2,confidence=.9)]
    snapshot=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    cues=derive_subtitle_cues(snapshot)
    assert len(cues)==1 and cues[0].words[0].start_seconds==4.9 and cues[0].words[0].end_seconds==5.2
    segment.words=[];segment.text=' '.join(['Vang Nguyễn giữ dấu tiếng Việt và nguồn gốc.']*7)
    snapshot=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    cues=derive_subtitle_cues(snapshot)
    assert ' '.join(cue.text for cue in cues)==segment.text and all(not cue.words for cue in cues)


def test_highlight_migration_is_additive_and_preserves_existing_rows(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine,text,inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    engine=create_engine(f'sqlite:///{tmp_path / "migration.db"}')
    path=Path(__file__).resolve().parents[1]/'migrations/versions/0017_north_star_highlight_drafts.py'
    spec=importlib.util.spec_from_file_location('highlight_migration',path)
    migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as connection:
        for table,key in [('video_projects','project_id'),('auto_edit_analyses','analysis_id'),('transcripts','transcript_id')]:
            connection.execute(text(f'CREATE TABLE {table} ({key} VARCHAR(64) PRIMARY KEY, evidence TEXT)'))
            connection.execute(text(f'INSERT INTO {table} VALUES (:id,:evidence)'),{'id':'fixture','evidence':'preserved'})
        with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
        assert 'auto_edit_highlight_drafts' in inspect(connection).get_table_names()
        for table in ['video_projects','auto_edit_analyses','transcripts']:
            assert connection.execute(text(f'SELECT evidence FROM {table}')).scalar_one()=='preserved'
        with pytest.raises(RuntimeError,match='Owner approval'):migration.downgrade()
    engine.dispose()


@pytest.mark.asyncio
async def test_highlight_http_requires_editor_and_returns_identity_bound_idempotent_drafts(tmp_path):
    from app.main import app
    from app.repositories import PlatformRepository
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from httpx import ASGITransport,AsyncClient
    from types import SimpleNamespace
    engine,sessions,repo,project,analysis,_,timeline=await stack(tmp_path)
    try:
        platform=PlatformRepository(sessions);app.state.auto_edit_analysis_service=SimpleNamespace(repository=repo)
        url=f'/api/v1/projects/{project.project_id}/highlight-drafts'
        body={'analysis_id':analysis.analysis_id,'count':3,'mode':'auto_shorts'}
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(url,json=body)).status_code==401
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            created=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert created.status_code==200 and len(created.json())==3
            assert all(d['actor_ref']=='usr:test-owner' for d in created.json())
            repeated=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert [d['draft_id'] for d in repeated.json()]==[d['draft_id'] for d in created.json()]
            selected=await client.post(url+'/'+created.json()[0]['draft_id']+'/apply',json={'expected_timeline_version':1},headers=TEST_HUMAN_HEADERS)
            assert selected.status_code==200 and selected.json()['current_version']==2
            stale=await client.post(url+'/'+created.json()[1]['draft_id']+'/apply',json={'expected_timeline_version':1},headers=TEST_HUMAN_HEADERS)
            assert stale.status_code==409
    finally:await engine.dispose()
