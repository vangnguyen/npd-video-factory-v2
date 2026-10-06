"""Saved fixture provider evidence and real immutable persistence; no provider acceptance."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from app.scene_intelligence import (SceneIntelligenceRequest,SceneIntelligenceConflict,
    create_assessment,list_assessments,get_assessment)
from app.highlight_drafts import HighlightDraftRequest,HighlightDraftConflict,create_drafts
from app.transcript_editing import edit_transcript
from test_transcript_editing import stack,edit


@pytest.mark.asyncio
async def test_immutable_idempotent_assessment_keeps_missing_measurements_null_and_original_rows(tmp_path):
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        original=copy.deepcopy(analysis.model_dump(mode='json'))
        request=SceneIntelligenceRequest(analysis_id=analysis.analysis_id)
        first=await create_assessment(repo,None,project.project_id,request,'editor')
        repeat=await create_assessment(repo,None,project.project_id,request,'editor')
        assert repeat.assessment_id==first.assessment_id
        assert first.provenance['fixture_asr'] and first.provenance['provider_dispatches']==0
        assert all(s.motion_score is None and s.quality_score is None and s.subjects==[] and s.needs_attention for s in first.scenes)
        assert (await repo.get_analysis(analysis.analysis_id)).model_dump(mode='json')==original
        assert (await timelines.get_timeline(project.project_id)).snapshot==timeline.snapshot
        assert (await get_assessment(repo,project.project_id,first.assessment_id))==first
        edited=await edit_transcript(repo,project.project_id,analysis.analysis_id,edit(analysis,timeline),'editor')
        second=await create_assessment(repo,None,project.project_id,request,'editor')
        assert second.assessment_id!=first.assessment_id and second.transcript_id==edited.transcript.transcript_id
        assert len(await list_assessments(repo,project.project_id))==2
        assert (await get_assessment(repo,project.project_id,first.assessment_id)).scenes==first.scenes
        with pytest.raises(HighlightDraftConflict,match='source/transcript'):
            await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id,
                scene_intelligence_id=first.assessment_id),'editor')
        drafts=await create_drafts(repo,project.project_id,HighlightDraftRequest(analysis_id=analysis.analysis_id,
            scene_intelligence_id=second.assessment_id),'editor')
        assert all(d.evidence['scene_intelligence_id']==second.assessment_id for d in drafts)
        assert all(d.evidence['factors']['factors']['motion'] is None for d in drafts)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_saved_vision_fusion_retains_frame_model_confidence_and_source_provenance(tmp_path):
    from test_media_intelligence import setup_media_stack
    from app.vision_repository import VisionRepository
    fixture=await setup_media_stack(tmp_path)
    try:
        repo=fixture['auto_repository'];visions=VisionRepository(fixture['session_factory'])
        payload=SceneIntelligenceRequest(analysis_id=fixture['auto_edit'].analysis_id,
            vision_analysis_id=fixture['vision'].vision_analysis_id)
        original=copy.deepcopy(fixture['auto_edit'].model_dump(mode='json'))
        result=await create_assessment(repo,visions,fixture['project'].project_id,payload,'editor')
        assert result.provenance['vision_provider_evidence']['fixture'] is True
        observed=[scene for scene in result.scenes if scene.evidence['vision_used']]
        assert observed and all(scene.quality_score is not None for scene in observed)
        assert any(scene.subjects for scene in observed)
        for scene in observed:
            assert scene.confidence is not None
            for frame in scene.evidence['frame_evidence']:
                assert frame['provider']=='fixture-vision' and frame['model'] and frame['evidence_frame_reference']
                assert frame['timestamp_seconds']>=scene.start_seconds and frame['timestamp_seconds']<scene.end_seconds
        assert (await repo.get_analysis(fixture['auto_edit'].analysis_id)).model_dump(mode='json')==original
        drafts=await create_drafts(repo,fixture['project'].project_id,HighlightDraftRequest(
            analysis_id=fixture['auto_edit'].analysis_id,scene_intelligence_id=result.assessment_id),'editor')
        assert any(d.evidence['factors']['vision_used'] for d in drafts)
        assert all(d.evidence['scene_intelligence_fingerprint']==result.fingerprint for d in drafts)
        foreign=fixture['vision'].model_copy(update={'project_id':'prj_foreign'})
        with pytest.raises(KeyError):await create_assessment(repo,SimpleNamespace(get_analysis=AsyncMock(return_value=foreign)),
            fixture['project'].project_id,payload,'editor')
        stale=fixture['vision'].model_copy(update={'provenance':{'source_asset_checksum':'wrong'}})
        with pytest.raises(SceneIntelligenceConflict,match='checksum'):
            await create_assessment(repo,SimpleNamespace(get_analysis=AsyncMock(return_value=stale)),fixture['project'].project_id,payload,'editor')
    finally:await fixture['engine'].dispose()


@pytest.mark.asyncio
async def test_scene_http_requires_editor_and_project_scoped_reads(tmp_path):
    from app.main import app
    from app.repositories import PlatformRepository
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from httpx import ASGITransport,AsyncClient
    engine,sessions,repo,project,analysis,_,_=await stack(tmp_path)
    try:
        platform=PlatformRepository(sessions);app.state.auto_edit_analysis_service=SimpleNamespace(repository=repo)
        url=f'/api/v1/projects/{project.project_id}/scene-intelligence'
        body={'analysis_id':analysis.analysis_id}
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(url,json=body)).status_code==401
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            created=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert created.status_code==200 and created.json()['actor_ref']=='usr:test-owner'
            item=created.json()['assessment_id']
            assert (await client.get(url+'/'+item,headers=TEST_HUMAN_HEADERS)).status_code==200
            assert (await client.get(url,headers=TEST_HUMAN_HEADERS)).json()[0]['assessment_id']==item
            assert (await client.get('/api/v1/projects/prj_missing/scene-intelligence/'+item,headers=TEST_HUMAN_HEADERS)).status_code==404
    finally:await engine.dispose()


def test_additive_scene_assessment_migration_preserves_existing_evidence():
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine,inspect,text
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path=Path(__file__).resolve().parents[1]/'migrations/versions/0018_north_star_scene_intelligence.py'
    spec=importlib.util.spec_from_file_location('scene_migration',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    engine=create_engine('sqlite://')
    with engine.begin() as connection:
        for table,key in [('video_projects','project_id'),('auto_edit_analyses','analysis_id'),('transcripts','transcript_id'),('vision_analyses','vision_analysis_id')]:
            connection.execute(text(f'CREATE TABLE {table} ({key} VARCHAR(64) PRIMARY KEY,evidence TEXT)'))
            connection.execute(text(f'INSERT INTO {table} VALUES (:id,:evidence)'),{'id':'fixture','evidence':'preserved'})
        with Operations.context(MigrationContext.configure(connection)):migration.upgrade()
        assert 'auto_edit_scene_intelligence' in inspect(connection).get_table_names()
        for table in ['video_projects','auto_edit_analyses','transcripts','vision_analyses']:
            assert connection.execute(text(f'SELECT evidence FROM {table}')).scalar_one()=='preserved'
        with pytest.raises(RuntimeError,match='Owner approval'):migration.downgrade()
    engine.dispose()
