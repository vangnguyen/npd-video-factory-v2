"""Actual SQL/auth/content routes; output bytes are explicit unaccepted fixtures."""
import hashlib
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Depends
import httpx
import pytest
from sqlalchemy import select

import app.main as main
from app.human_auth import authorize_human_request
from app.production_routes import router as production_router
from app.timeline_routes import router as timeline_router
from app.production_models import ProductionPackageCreateRequest, RenderCreateRequest
from app.timeline_models import PreviewCreateRequest
from app.timeline_service import PreviewService
from app.platform_models import AssetRegister, ProjectCreate, WorkspaceCreate
from app.production_db import (ProductionRenderJobORM, ProductionPackageORM, ProductionApprovalORM,
    ProductionEventORM, SubtitleVersionORM, AudioMixVersionORM)
from app.timeline_db import PreviewJobORM, TimelineORM, TimelineVersionORM
from app.db import AssetORM, JobORM, JobEventORM, CostRecordORM, ProviderUsageORM, ProjectVersionORM
from app.models import Artifact, JobRecord, VideoJobCreate
from app.repositories import PostgresJobStore
from app.verified_artifact_delivery import scalar_record
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_mvp1_multi_input import env, author, timeline

RAW = b'UNACCEPTED SYNTHETIC OUTPUT FIXTURE; NO RENDER OR PROVIDER\0' * 1600


@pytest.fixture
async def content_env(env,monkeypatch):
    authored=await author(env,original='Nội dung fixture do người kiểm thử cung cấp.')
    built=await timeline(env,authored)
    await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    render=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=1,expected_subtitle_version=1,expected_audio_version=1))
    preview_service=PreviewService(repository=env.timeline,platform=env.platform,auto_edit_repository=env.assets,
        object_storage=env.storage,queue=env.queue,renderer=object(),staging_root=env.tmp/'no-render')
    preview=await preview_service.enqueue(env.project.project_id,PreviewCreateRequest(timeline_version=1))
    assets={}
    for kind,name in [('av-review','render'),('proxy-preview','preview')]:
        source=env.tmp/(name+'.fixture');source.write_bytes(RAW)
        saved=await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/outputs/{name}.mp4',path=source,content_type='video/mp4')
        assets[name]=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='render',kind=kind,
            filename=name+'.mp4',object_key=saved.object_key,content_type='video/mp4',size_bytes=saved.size_bytes,
            checksum_sha256=saved.checksum_sha256,storage_provider=env.storage.name,
            provenance={'fixture':True,'rights_status':'unknown','owner_accepted':False}))
    async with env.factory() as session:
        async with session.begin():
            (await session.get(ProductionRenderJobORM,render.render_id)).output_asset_id=assets['render'].asset_id
            (await session.get(PreviewJobORM,preview.preview_id)).output_asset_id=assets['preview'].asset_id
    store=PostgresJobStore(env.factory,env.queue,platform=env.platform,object_storage=env.storage)
    request=VideoJobCreate(topic='Fixture delivery',project='fixture-delivery',
        video={'duration_seconds':15},content={'audience':'fixture','tone':'plain','cta':'fixture'},
        media={'project_asset_folder':'fixture-delivery','minimum_clips':1})
    artifact=Artifact(kind='metadata',name='manifest.json',url='/fixture/manifest.json',
        object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/legacy/manifest.json',
        size_bytes=len(RAW),checksum_sha256=hashlib.sha256(RAW).hexdigest(),storage_provider='local',content_type='application/json')
    original=env.tmp/'legacy.fixture';original.write_bytes(RAW)
    await env.storage.put_file(object_key=artifact.object_key,path=original)
    job=JobRecord.new(job_id='vid_delivery_fixture',request=request,workspace_id=env.workspace.workspace_id,
        project_id=env.project.project_id,project_version_id=authored.project_version_id).model_copy(update={'artifacts':[artifact]})
    await store.create(job)
    monkeypatch.setattr(main,'settings',main.settings.model_copy(update={'job_storage_root':env.tmp/'legacy-jobs'}))
    app=FastAPI()
    app.include_router(production_router,dependencies=[Depends(authorize_human_request)])
    app.include_router(timeline_router,dependencies=[Depends(authorize_human_request)])
    app.add_api_route('/api/v1/video-jobs/{job_id}/artifacts/{artifact_name}',main.get_video_artifact,
        methods=['GET','HEAD'],dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(app,platform_repository=env.platform,platform_role=None,
        workspace_roles={env.workspace.workspace_id:'viewer'})
    app.state.production_package_service=env.package;app.state.preview_service=preview_service
    app.state.auto_edit_repository=env.assets;app.state.object_storage=env.storage;app.state.job_store=store
    app.state.production_render_download_root=env.tmp/'render-delivery'
    app.state.preview_download_root=env.tmp/'preview-delivery'
    urls={'render':f'/api/v1/projects/{env.project.project_id}/renders/{render.render_id}/content',
        'preview':f'/api/v1/projects/{env.project.project_id}/previews/{preview.preview_id}/content',
        'legacy':'/api/v1/video-jobs/vid_delivery_fixture/artifacts/manifest.json'}
    # These rows deliberately remain unapproved/queued. No renderer/ASR/TTS/QC ran.
    yield SimpleNamespace(env=env,app=app,urls=urls,assets=assets,render=render,preview=preview,job=job,store=store,built=built)


async def get(fixture,kind,*,method='get',headers=TEST_HUMAN_HEADERS,url=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=fixture.app),base_url='http://fixture') as client:
        return await getattr(client,method)(url or fixture.urls[kind],headers=headers)


def clean(fixture):
    for root in [fixture.app.state.production_render_download_root,fixture.app.state.preview_download_root,
            main.settings.job_storage_root/'.artifact-downloads']:
        assert not list(Path(root).glob('verified-artifact-*'))


async def records(fixture):
    async with fixture.env.factory() as session:
        return {
                model.__tablename__:[scalar_record(row) for row in (await session.scalars(select(model))).all()]
                for model in [AssetORM,JobORM,JobEventORM,CostRecordORM,ProviderUsageORM,ProjectVersionORM,
                    TimelineORM,TimelineVersionORM,ProductionPackageORM,ProductionApprovalORM,
                    ProductionEventORM,SubtitleVersionORM,AudioMixVersionORM,ProductionRenderJobORM,PreviewJobORM]}


@pytest.mark.parametrize('kind',['render','preview','legacy'])
async def test_actual_sql_viewer_range_head_and_no_history_mutation(content_env,kind):
    fixture=content_env;before=await records(fixture);calls=[];download=fixture.env.storage.download_file
    async def capture(**kwargs):calls.append(kwargs);await download(**kwargs)
    fixture.env.storage.download_file=capture
    result=await get(fixture,kind,headers={**TEST_HUMAN_HEADERS,'Range':'bytes=7-24'})
    assert result.status_code==206,result.text
    assert result.content==RAW[7:25] and result.headers['content-range']==f'bytes 7-24/{len(RAW)}'
    assert result.headers['etag']=='"'+hashlib.sha256(RAW).hexdigest()+'"'
    assert result.headers['cache-control']=='no-store'
    head=await get(fixture,kind,method='head')
    assert head.status_code==200 and head.content==b'' and int(head.headers['content-length'])==len(RAW)
    assert before==await records(fixture)
    assert len(calls)==2
    for kwargs in calls:
        assert kwargs['max_bytes']==len(RAW) and kwargs['expected_size_bytes']==len(RAW)
        assert kwargs['expected_sha256']==hashlib.sha256(RAW).hexdigest()
        assert kwargs['expected_prefix']==f'workspaces/{fixture.env.workspace.workspace_id}/projects/{fixture.env.project.project_id}/'
        assert kwargs['destination'].name=={'render':'render.mp4','preview':'preview.mp4','legacy':'artifact.bin'}[kind]
    clean(fixture)


@pytest.mark.parametrize('kind',['render','preview','legacy'])
async def test_actual_auth_missing_or_other_workspace_rejects_before_wire(content_env,kind):
    fixture=content_env;calls=[]
    async def forbidden(**kwargs):calls.append(kwargs);raise AssertionError('unauthorized wire')
    fixture.env.storage.download_file=forbidden
    assert (await get(fixture,kind,headers={})).status_code==401
    install_test_human_auth(fixture.app,platform_repository=fixture.env.platform,platform_role=None,
        workspace_roles={'wsp_other_fixture':'viewer'})
    assert (await get(fixture,kind)).status_code in {403,404}
    assert not calls;clean(fixture)


@pytest.mark.parametrize('kind',['render','preview','legacy'])
@pytest.mark.parametrize('change',['missing','hash','version','owner','namespace','pointer','cancel'])
async def test_actual_sql_changes_after_bounded_read_fail_closed(content_env,kind,change):
    fixture=content_env;download=fixture.env.storage.download_file;calls=[]
    async def mutate(**kwargs):
        calls.append(kwargs)
        if change=='missing':raise FileNotFoundError('private storage path')
        await download(**kwargs)
        if change=='hash':kwargs['destination'].write_bytes(b'late bytes')
        else:
            async with fixture.env.factory() as session:
                async with session.begin():
                    if kind=='legacy':
                        row=await session.get(JobORM,fixture.job.job_id)
                        if change=='owner':row.workspace_id=None
                        elif change=='cancel':row.status='cancelled'
                        elif change=='pointer':row.artifacts_json=[]
                        elif change=='namespace':row.artifacts_json=[{**row.artifacts_json[0],'object_key':'workspaces/wsp_other/projects/prj_other/x'}]
                        else:row.record_version+=1
                    else:
                        model=ProductionRenderJobORM if kind=='render' else PreviewJobORM
                        identity=fixture.render.render_id if kind=='render' else fixture.preview.preview_id
                        row=await session.get(model,identity);asset=await session.get(AssetORM,fixture.assets[kind].asset_id)
                        if change=='owner':asset.workspace_id=None
                        elif change=='cancel':row.cancellation_requested=True
                        elif change=='pointer':row.output_asset_id=None
                        elif change=='namespace':asset.object_key='workspaces/wsp_other/projects/prj_other/x'
                        else:asset.version+=1
    # A different real workspace keeps foreign-key integrity in the owner race.
    if change=='owner' and kind!='legacy':
        workspace=await fixture.env.platform.create_workspace(WorkspaceCreate(slug='foreign',name='Foreign',owner_ref='fixture'))
        # Metadata owner mutation must use an existing FK, not a schema violation.
        async def mutate(**kwargs):
            calls.append(kwargs);await download(**kwargs)
            async with fixture.env.factory() as session:
                async with session.begin():
                    (await session.get(AssetORM,fixture.assets[kind].asset_id)).workspace_id=workspace.workspace_id
    fixture.env.storage.download_file=mutate
    result=await get(fixture,kind)
    assert result.status_code==(404 if kind=='legacy' or change=='missing' else 409),result.text
    assert 'private storage' not in result.text and len(calls)==1
    clean(fixture)


@pytest.mark.parametrize('kind',['render','preview'])
async def test_foreign_parent_and_asset_owner_are_rejected_before_wire(content_env,kind):
    fixture=content_env;workspace=await fixture.env.platform.create_workspace(WorkspaceCreate(slug='foreign',name='Foreign',owner_ref='fixture'))
    async with fixture.env.factory() as session:
        async with session.begin():
            parent=await session.get(ProductionRenderJobORM if kind=='render' else PreviewJobORM,
                fixture.render.render_id if kind=='render' else fixture.preview.preview_id)
            parent.workspace_id=workspace.workspace_id
            (await session.get(AssetORM,fixture.assets[kind].asset_id)).workspace_id=workspace.workspace_id
    calls=[]
    async def forbidden(**kwargs):calls.append(kwargs);raise AssertionError('foreign SQL owner wire')
    fixture.env.storage.download_file=forbidden
    assert (await get(fixture,kind)).status_code==404 and not calls;clean(fixture)


@pytest.mark.parametrize('kind',['render','preview'])
@pytest.mark.parametrize('field,value',[
    ('asset_class','source'),('kind','unknown-output'),('content_type','audio/wav'),('size_bytes',0),
])
async def test_non_output_asset_is_not_relabelled_or_downloaded(content_env,kind,field,value):
    fixture=content_env
    async with fixture.env.factory() as session:
        async with session.begin():
            setattr(await session.get(AssetORM,fixture.assets[kind].asset_id),field,value)
    calls=[]
    async def forbidden(**kwargs):calls.append(kwargs);raise AssertionError('non-output artifact wire')
    fixture.env.storage.download_file=forbidden
    result=await get(fixture,kind)
    assert result.status_code==409 and not calls;clean(fixture)


@pytest.mark.parametrize('field',['size_bytes','checksum_sha256','storage_provider','object_key'])
async def test_remote_legacy_incomplete_proof_stays_404_without_wire(content_env,field):
    fixture=content_env
    async with fixture.env.factory() as session:
        async with session.begin():
            row=await session.get(JobORM,fixture.job.job_id)
            row.artifacts_json=[{**row.artifacts_json[0],field:None}]
    calls=[]
    async def forbidden(**kwargs):calls.append(kwargs);raise AssertionError('nullable proof wire')
    fixture.env.storage.download_file=forbidden
    assert (await get(fixture,'legacy')).status_code==404 and not calls;clean(fixture)


async def test_legal_empty_legacy_is_exact_zero_byte_proof_and_not_source(content_env):
    fixture=content_env;artifact=fixture.job.artifacts[0];empty=fixture.env.tmp/'empty.fixture';empty.write_bytes(b'')
    await fixture.env.storage.put_file(object_key=artifact.object_key,path=empty)
    async with fixture.env.factory() as session:
        async with session.begin():
            row=await session.get(JobORM,fixture.job.job_id)
            row.artifacts_json=[{**row.artifacts_json[0],'size_bytes':0,'checksum_sha256':hashlib.sha256(b'').hexdigest()}]
    calls=[];download=fixture.env.storage.download_file
    async def capture(**kwargs):calls.append(kwargs);await download(**kwargs)
    fixture.env.storage.download_file=capture
    result=await get(fixture,'legacy')
    assert result.status_code==200 and result.content==b'' and result.headers['content-length']=='0'
    assert calls[0]['max_bytes']==1 and calls[0]['expected_size_bytes']==0
    assert (await fixture.store.get(fixture.job.job_id)).artifacts[0].kind=='metadata'
    clean(fixture)


async def test_local_legacy_resolver_remains_compatible_without_remote_proof(content_env):
    fixture=content_env;root=main.settings.job_storage_root/fixture.job.job_id;root.mkdir(parents=True)
    retained=root/'manifest.json';retained.write_bytes(b'retained local original')
    async with fixture.env.factory() as session:
        async with session.begin():
            row=await session.get(JobORM,fixture.job.job_id)
            row.artifacts_json=[{**row.artifacts_json[0],'size_bytes':None,'checksum_sha256':None}]
    calls=[]
    async def forbidden(**kwargs):calls.append(kwargs);raise AssertionError('local artifact recovery')
    fixture.env.storage.download_file=forbidden
    result=await get(fixture,'legacy');assert result.status_code==200 and result.content==b'retained local original'
    result=await get(fixture,'legacy',url=fixture.urls['legacy'].replace('manifest.json','unrecorded.json'))
    assert result.status_code==404 and retained.read_bytes()==b'retained local original' and not calls
    clean(fixture)


async def test_render_filename_does_not_choose_staging_path(content_env):
    fixture=content_env
    async with fixture.env.factory() as session:
        async with session.begin():
            (await session.get(AssetORM,fixture.assets['render'].asset_id)).filename='../escaped.mp4'
    calls=[];download=fixture.env.storage.download_file
    async def capture(**kwargs):calls.append(kwargs);await download(**kwargs)
    fixture.env.storage.download_file=capture
    result=await get(fixture,'render')
    assert result.status_code==200 and result.content==RAW
    assert calls[0]['destination'].name=='render.mp4' and not (fixture.env.tmp/'escaped.mp4').exists()
    clean(fixture)
