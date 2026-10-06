"""Synthetic ASR alignment, real versioned storage/authorization and render contracts."""
from pathlib import Path
from types import SimpleNamespace
import copy
import pytest
from sqlalchemy import select, func
from app.production_db import SubtitleVersionORM
from app.production_models import SubtitleStyle, SubtitleCue, ProductionPackageCreateRequest, SubtitleReplaceRequest, MixConfig
from app.production_service import ProductionPackageService
from app.production_repository import ProductionRepository, ProductionConflictError
from app.production_logic import ProductionContractError, validate_subtitles, build_timeline_render_manifest, TimelineRenderContractValidator
from app.subtitle_templates import template_catalog, render_subtitle_style
from test_transcript_editing import stack
from test_audio_subtitle_render_qc import FakeQueue

CONTRACT=Path(__file__).resolve().parents[3]/'packages/contracts/timeline-render.schema.json'


def aligned_cue():
    return SubtitleCue(cue_id='sub_unicode',start_seconds=0,end_seconds=2,text='Cần Giờ, Việt Nam!',words=[
        {'text':text,'start_seconds':start,'end_seconds':end} for text,start,end in
        [('Cần',0,.3),('Giờ',.4,.8),('Việt',1,1.3),('Nam',1.4,1.8)]])


def test_catalog_and_unicode_keywords_and_missing_alignment():
    catalog=template_catalog()
    assert catalog['render_contract_version']=='2.3' and len(catalog['templates'])==7
    assert all(t['style']['template_ref']==t['template_ref'] for t in catalog['templates'])
    assert SubtitleStyle(keywords=['Cần Giờ','Cần Giờ']).keywords==['Cần Giờ']
    for animation in ['word_by_word','karaoke']:
        validate_subtitles([aligned_cue()],SubtitleStyle(animation=animation),2)
        with pytest.raises(ProductionContractError,match='WORD_ALIGNMENT_UNAVAILABLE'):
            validate_subtitles([aligned_cue().model_copy(update={'words':[]})],SubtitleStyle(animation=animation),2)
        with pytest.raises(ProductionContractError,match='TEXT_MISMATCH'):
            validate_subtitles([aligned_cue().model_copy(update={'text':'Nội dung khác'})],SubtitleStyle(animation=animation),2)
    assert 'template_ref' not in render_subtitle_style(SubtitleStyle())
    assert 'keywords' not in render_subtitle_style(SubtitleStyle())


@pytest.mark.asyncio
async def test_styles_preserve_alignment_cas_history_and_reject_stale_or_invented_words(tmp_path):
    engine,sessions,assets,project,analysis,timelines,timeline=await stack(tmp_path)
    try:
        repository=ProductionRepository(sessions)
        service=ProductionPackageService(repository=repository,timeline_repository=timelines,asset_repository=assets,
            queue=FakeQueue(),settings=SimpleNamespace(audio_tts_provider='contract'))
        package=await service.create_or_refresh(project.project_id,ProductionPackageCreateRequest())
        assert all(cue.words for cue in package.subtitle.cues)
        original=copy.deepcopy(package.subtitle.cues)
        kwargs=dict(expected_timeline_version=1,expected_subtitle_version=1,cues=original,
                    style=SubtitleStyle(animation='karaoke',template_ref='karaoke-gold@v1'),actor_ref='editor')
        changed=await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(**kwargs))
        assert changed.subtitle.version==2 and changed.subtitle.cues==original
        assert changed.subtitle.style.template_ref=='karaoke-gold@v1'
        with pytest.raises(ProductionConflictError):
            await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(**kwargs))
        altered=copy.deepcopy(original);altered[0].text='Câu mới do người sửa.'
        with pytest.raises(ProductionContractError,match='WORD_ALIGNMENT_STALE'):
            await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
                expected_subtitle_version=2,cues=altered,style=SubtitleStyle(animation='none')))
        forged=copy.deepcopy(original);forged[0].words[0].text='giả'
        with pytest.raises(ProductionContractError,match='WORD_ALIGNMENT_STALE'):
            await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
                expected_subtitle_version=2,cues=forged,style=SubtitleStyle(animation='none')))
        altered[0].words=[]
        with pytest.raises(ProductionContractError,match='WORD_ALIGNMENT_UNAVAILABLE'):
            await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
                expected_subtitle_version=2,cues=altered,style=SubtitleStyle(animation='karaoke')))
        with pytest.raises(ProductionContractError,match='SUBTITLE_TEMPLATE_UNKNOWN'):
            await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
                expected_subtitle_version=2,cues=original,style=SubtitleStyle(animation='none',template_ref='missing-one@v1')))
        final=await service.replace_subtitles(project.project_id,SubtitleReplaceRequest(expected_timeline_version=1,
            expected_subtitle_version=2,cues=altered,style=SubtitleStyle(animation='keyword_highlight',
                template_ref='keyword-accent@v1',keywords=['người sửa'])))
        assert final.subtitle.version==3 and not final.subtitle.cues[0].words
        assert (await timelines.get_timeline(project.project_id)).snapshot==timeline.snapshot
        async with sessions() as session:
            assert await session.scalar(select(func.count()).select_from(SubtitleVersionORM))==3
            old=await session.get(SubtitleVersionORM,package.subtitle.subtitle_version_id)
            assert old.cues_json==[cue.model_dump(mode='json') for cue in original]
        source=await assets.get_asset(analysis.asset_id)
        manifest=build_timeline_render_manifest(snapshot=timeline.snapshot,subtitles=final.subtitle,mix_config=MixConfig(),
            mixed_audio_path=tmp_path/'mix.wav',asset_paths={source.asset_id:(source,tmp_path/'source.mp4')},
            profile='review-540x960',project_name='Fixture',project_slug='fixture',niche='technology',brand_name='Fixture')
        assert manifest['version']=='2.3'
        validator=TimelineRenderContractValidator(CONTRACT);validator.validate(manifest)
        image=source.model_copy(update={'content_type':'image/png'})
        image_manifest=build_timeline_render_manifest(snapshot=timeline.snapshot,subtitles=final.subtitle,mix_config=MixConfig(),
            mixed_audio_path=tmp_path/'mix.wav',asset_paths={source.asset_id:(image,tmp_path/'source.png')},
            profile='review-540x960',project_name='Fixture',project_slug='fixture',niche='technology',brand_name='Fixture')
        assert image_manifest['visual_clips'][0]['source_end'] is None
        assert image_manifest['visual_clips'][0]['source_start']==0
        validator.validate(image_manifest)
        manifest['version']='2.2'
        with pytest.raises(ProductionContractError,match='v2.3'):validator.validate(manifest)
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_template_and_subtitle_http_roles_scope_and_actor_binding(tmp_path):
    from fastapi import FastAPI, Depends
    from httpx import AsyncClient, ASGITransport
    from app.production_routes import router
    from app.human_auth import authorize_human_request
    from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
    from test_audio_subtitle_render_qc import setup_stack
    env=await setup_stack(tmp_path)
    try:
        package=await env.service.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
        api=FastAPI();api.state.production_package_service=env.service
        api.include_router(router,dependencies=[Depends(authorize_human_request)])
        install_test_human_auth(api,platform_repository=env.platform,platform_role=None,workspace_roles={'*':'viewer'})
        path=f'/api/v1/projects/{env.project.project_id}'
        body=SubtitleReplaceRequest(expected_timeline_version=1,expected_subtitle_version=1,cues=package.subtitle.cues,
            style=SubtitleStyle(animation='keyword_highlight',template_ref='keyword-accent@v1',keywords=['Vịnh Tiên']),
            actor_ref='spoofed-owner').model_dump(mode='json')
        async with AsyncClient(transport=ASGITransport(app=api),base_url='http://test') as client:
            assert (await client.get(path+'/subtitle-templates')).status_code==401
            assert (await client.get(path+'/subtitle-templates',headers=TEST_HUMAN_HEADERS)).status_code==200
            assert (await client.put(path+'/subtitles',json=body,headers=TEST_HUMAN_HEADERS)).status_code==403
            install_test_human_auth(api,platform_repository=env.platform,platform_role=None,workspace_roles={'slug:other':'editor'})
            assert (await client.get(path+'/subtitle-templates',headers=TEST_HUMAN_HEADERS)).status_code==404
            install_test_human_auth(api,platform_repository=env.platform)
            response=await client.put(path+'/subtitles',json=body,headers=TEST_HUMAN_HEADERS)
            assert response.status_code==200
            assert response.json()['subtitle']['actor_ref']=='usr:test-owner'
            assert response.json()['subtitle']['version']==2
    finally:await env.engine.dispose()
