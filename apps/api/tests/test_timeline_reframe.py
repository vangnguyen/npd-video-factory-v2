"""Measured-geometry contract; Vision fixtures are never real-provider acceptance."""
from types import SimpleNamespace
import pytest
from app.timeline_reframe import ASPECT_DIMENSIONS,crop_keyframes,bind_reframe,apply_reframe,ReframeApplyRequest
from app.timeline_logic import TimelineEditError
from app.vision_logic import build_reframe_plans
from app.timeline_repository import TimelineConflictError
from test_auto_edit_studio import analysis_fixture
from test_silence_word_safety import asset
from app.timeline_logic import build_initial_timeline
from test_transcript_editing import stack


def fallback(metadata,aspect):
    return build_reframe_plans(frames=[],tracks=[],metadata=metadata,aspect_ratios=[aspect],manual_overrides=[],
        minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,maximum_jump=.12,fingerprint='fixture')[0]


@pytest.mark.parametrize('source_size',[(1920,1080),(1080,1920)])
@pytest.mark.parametrize('aspect',list(ASPECT_DIMENSIONS))
def test_four_ratios_keep_exact_geometry_and_mark_no_vision_fallback(source_size,aspect):
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    analysis.source_media.width,analysis.source_media.height=source_size
    plan=fallback(analysis.source_media,aspect)
    snapshot=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    result=bind_reframe(snapshot,asset_id=source.asset_id,metadata=analysis.source_media,plan=plan,vision_analysis_id=None)
    assert (result.width,result.height)==ASPECT_DIMENSIONS[aspect]
    assert result.aspect_ratio==aspect
    assert result.metadata['reframe']['fallback']=='center_crop' and result.metadata['reframe']['needs_attention']
    clip=next(c for t in result.tracks if t.kind=='source' for c in t.clips)
    for keyframe in clip.metadata['reframe']['keyframes']:
        assert source_size[0]/source_size[1]*keyframe['width']/keyframe['height']==pytest.approx(result.width/result.height,abs=1e-6)
        assert 0<=keyframe['x']<=1-keyframe['width']+1e-6
        assert 0<=keyframe['y']<=1-keyframe['height']+1e-6
    assert snapshot.metadata.get('reframe') is None


@pytest.mark.asyncio
async def test_apply_reframe_uses_immutable_cas_and_preserves_source_clip_identity(tmp_path):
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        service=SimpleNamespace(repository=timelines,auto_edit_repository=repo,validator=SimpleNamespace(validate=lambda _:None))
        result=await apply_reframe(service,None,project.project_id,ReframeApplyRequest(expected_version=1,aspect_ratio='4:5'),'editor')
        assert result.current_version==2 and result.approval_status=='draft'
        assert [c.clip_id for t in result.snapshot.tracks for c in t.clips]==[c.clip_id for t in timeline.snapshot.tracks for c in t.clips]
        assert (await timelines.get_version_by_id(timeline.current_version_id)).snapshot==timeline.snapshot
        with pytest.raises(TimelineConflictError):
            await apply_reframe(service,None,project.project_id,ReframeApplyRequest(expected_version=1,aspect_ratio='1:1'),'editor')
        locked=result.snapshot.model_copy(deep=True);next(t for t in locked.tracks if t.kind=='source').locked=True
        await timelines.commit_mutation(project_id=project.project_id,expected_version=2,snapshot=locked,mutation={'type':'fixture-lock'},actor_ref='fixture')
        with pytest.raises(TimelineEditError,match='unlock'):
            await apply_reframe(service,None,project.project_id,ReframeApplyRequest(expected_version=3,aspect_ratio='9:16'),'editor')
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_saved_subject_plan_is_source_bound_and_manual_crop_supersedes_tracking(tmp_path):
    from unittest.mock import AsyncMock
    from app.timeline_logic import apply_operations
    from app.timeline_models import TimelineOperation
    engine,_,repo,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        plan=fallback(analysis.source_media,'9:16').model_copy(update={'strategy':'subject_track','fallback':'none',
            'confidence':.91,'needs_attention':False})
        saved=SimpleNamespace(project_id=project.project_id,analysis_id=analysis.analysis_id,asset_id=analysis.asset_id,
            status='succeeded',source_media=analysis.source_media,provenance=analysis.provenance,reframe_plans=[plan])
        visions=SimpleNamespace(get_analysis=AsyncMock(return_value=saved))
        service=SimpleNamespace(repository=timelines,auto_edit_repository=repo,validator=SimpleNamespace(validate=lambda _:None))
        payload=ReframeApplyRequest(expected_version=1,aspect_ratio='9:16',vision_analysis_id='vis_fixture')
        result=await apply_reframe(service,visions,project.project_id,payload,'editor')
        assert result.snapshot.metadata['reframe']['confidence']==.91
        clip=next(c for t in result.snapshot.tracks if t.kind=='source' for c in t.clips)
        manual=apply_operations(result.snapshot,[TimelineOperation(type='set_clip_properties',clip_id=clip.clip_id,
            crop={'x':0,'y':0,'width':1,'height':1})])
        edited=next(c for t in manual.tracks for c in t.clips if c.clip_id==clip.clip_id)
        assert 'reframe' not in edited.metadata and edited.metadata['reframe_manual_override']
        assert manual.metadata['reframe']['needs_attention']
        saved.project_id='other-project'
        with pytest.raises(KeyError):await apply_reframe(service,visions,project.project_id,payload,'editor')
        saved.project_id=project.project_id;saved.provenance={'source_asset_checksum':'wrong'}
        with pytest.raises(TimelineEditError,match='measured source'):
            await apply_reframe(service,visions,project.project_id,payload,'editor')
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_reframe_http_requires_editor_identity_and_rejects_stale_versions(tmp_path):
    from app.main import app
    from app.repositories import PlatformRepository
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    from httpx import ASGITransport,AsyncClient
    engine,sessions,repo,project,_,timelines,_=await stack(tmp_path)
    try:
        app.state.timeline_service=SimpleNamespace(repository=timelines,auto_edit_repository=repo,
            validator=SimpleNamespace(validate=lambda _:None))
        url=f'/api/v1/projects/{project.project_id}/timeline/reframe'
        body={'expected_version':1,'aspect_ratio':'4:5'}
        platform=PlatformRepository(sessions)
        install_test_human_auth(app,platform_repository=platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.post(url,json=body)).status_code==401
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(app,platform_repository=platform,platform_role='editor',workspace_roles={'*':'editor'})
            result=await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)
            assert result.status_code==200 and result.json()['current_version']==2
            assert result.json()['snapshot']['metadata']['reframe']['provider_dispatches']==0
            assert (await client.post(url,json=body,headers=TEST_HUMAN_HEADERS)).status_code==409
    finally:await engine.dispose()


def test_render_manifest_carries_crop_paths_and_rejects_mismatched_aspect():
    from pathlib import Path
    from app.production_logic import build_timeline_render_manifest,TimelineRenderContractValidator,ProductionContractError
    from app.production_logic import derive_subtitle_cues
    from app.production_models import MixConfig,SubtitleStyle
    source=asset();analysis=analysis_fixture(source.project_id,source.asset_id)
    snapshot=build_initial_timeline(analysis=analysis,source_asset=source,media_plan=None,media_assets={})
    reframed=bind_reframe(snapshot,asset_id=source.asset_id,metadata=analysis.source_media,
        plan=fallback(analysis.source_media,'4:5'),vision_analysis_id=None)
    arguments=dict(snapshot=reframed,subtitles=SimpleNamespace(cues=derive_subtitle_cues(reframed),style=SubtitleStyle()),
        mix_config=MixConfig(),mixed_audio_path=Path('/fixture/audio.wav'),asset_paths={source.asset_id:(source,Path('/fixture/source.mp4'))},
        project_name='Fixture',project_slug='fixture',niche='technology',brand_name='Fixture')
    manifest=build_timeline_render_manifest(**arguments,profile='review-432x540')
    validator=TimelineRenderContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json')
    validator.validate(manifest)
    assert manifest['version']=='2.2' and manifest['visual_clips'][0]['crop_keyframes']
    with pytest.raises(ProductionContractError,match='aspect ratio'):
        build_timeline_render_manifest(**arguments,profile='review-540x960')
    manifest['visual_clips'][0]['crop_keyframes'][0]['x']=1
    with pytest.raises(ProductionContractError,match='source bounds'):validator.validate(manifest)


@pytest.mark.asyncio
async def test_reframed_review_profile_is_checked_before_queue_or_provider_dispatch(tmp_path):
    from test_audio_subtitle_render_qc import setup_stack
    from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
    from app.production_logic import ProductionContractError
    fixture=await setup_stack(tmp_path)
    try:
        snapshot=fixture.timeline.snapshot.model_copy(deep=True)
        snapshot.width,snapshot.height=1080,1350
        snapshot.metadata['reframe']={'aspect_ratio':'4:5','fallback':'center_crop','needs_attention':True}
        await fixture.timeline_repository.commit_mutation(project_id=fixture.project.project_id,expected_version=1,
            snapshot=snapshot,mutation={'type':'fixture-reframe'},actor_ref='fixture')
        await fixture.service.create_or_refresh(fixture.project.project_id,ProductionPackageCreateRequest(expected_timeline_version=2))
        base=dict(expected_timeline_version=2,expected_subtitle_version=1,expected_audio_version=1)
        with pytest.raises(ProductionContractError,match='aspect ratio'):
            await fixture.service.enqueue_review(fixture.project.project_id,RenderCreateRequest(**base,profile='review-540x960'))
        assert fixture.queue.items==[]
        render=await fixture.service.enqueue_review(fixture.project.project_id,RenderCreateRequest(**base,profile='review-432x540'))
        assert len(fixture.queue.items)==1 and render.profile=='review-432x540'
        completed=await fixture.processor.process(render.render_id)
        assert completed.status=='awaiting_review' and completed.qc_status=='passed'
        assert (completed.qc_report['width'],completed.qc_report['height'])==(432,540)
    finally:await fixture.engine.dispose()
