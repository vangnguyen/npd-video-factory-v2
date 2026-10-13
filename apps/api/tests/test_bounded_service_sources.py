"""Actual SQLite and owned bytes/explicit SDK fixtures; no real providers."""
import asyncio
import copy
import hashlib
import threading
from types import SimpleNamespace

import pytest

from app.auto_edit_db import AutoEditAnalysisORM
from app.auto_edit_models import AutoEditAnalysisRequest
from app.db import AssetORM
from app.content_models import StoryboardScene
from app.frozen_storage_read import MAX_SOURCE_BYTES
from app.timeline_models import PreviewCreateRequest
from app.timeline_service import PreviewService,PreviewCancelledError
from app.vision_service import VisionAnalysisService
from app.vision_repository import VisionRepository
from app.vision_providers import ContractOnlyVisionProvider
from test_auto_edit_analysis import setup_services,upload_fixture,synthetic_mp4
from test_bounded_storage_consumers import RecordingStorage,assert_frozen
from test_bounded_storage_download import Body,fake_s3
from test_mvp1_multi_input import env,author,timeline,image
from test_timeline_audio_preview import register_tone


class DeniedDispatch:
    calls=0
    async def __call__(self,*args,**kwargs):
        self.calls+=1;raise AssertionError('Source admission must not dispatch a provider/renderer')


@pytest.fixture
async def source(tmp_path):
    values=await setup_services(tmp_path)
    engine,sessions,platform,repo,uploads,service,project,version=values
    original_probe=uploads.media_probe
    class SilentHeaderFixtureProbe:
        async def probe(self,*args,**kwargs):
            metadata=await original_probe.probe(*args,**kwargs)
            return metadata.model_copy(update={'audio_codec':None,'audio_channels':None,'audio_sample_rate':None})
    uploads.media_probe=SilentHeaderFixtureProbe()
    completed=await upload_fixture(uploads,project,version,synthetic_mp4())
    asset=await repo.get_asset(completed.asset_id)
    asr,signals=DeniedDispatch(),DeniedDispatch()
    service.transcription_provider.transcribe=asr;service.signal_provider.analyze=signals
    payload=AutoEditAnalysisRequest(asset_id=asset.asset_id)
    prepared=await service.prepare(project.project_id,payload)
    # Immutable schema fixture only, no invented transcript/model evidence.
    aid,_=await repo.create_analysis(project_id=project.project_id,asset=asset,fingerprint='1'*64,
        configuration=payload,source_media=prepared['source_media'],provenance={'explicit_schema_fixture':True,
            'source_asset_checksum':asset.checksum_sha256,'provider_calls':0,'human_accepted':False})
    await repo.save_analysis_results(analysis_id=aid,asset_id=asset.asset_id,provider_key='fixture-media-signals',
        transcript=None,scenes=[{'ordinal':0,'start_seconds':0.,'end_seconds':1.,
            'semantic_label':'explicit_schema_fixture','description':'Manually seeded SQL fixture; no Vision or scene inference.',
            'subjects':[],'quality_score':0.,'motion_score':0.,'speech_score':0.,'confidence':0.,
            'evidence':{'fixture':True,'provider_calls':0,'real_quality_verified':False}}],
        silence_decisions=[],highlights=[],signal_evidence={'fixture':True})
    base=await repo.get_analysis(aid)
    vision=VisionAnalysisService(repository=VisionRepository(sessions),auto_edit_repository=repo,
        platform=platform,object_storage=uploads.object_storage,provider=ContractOnlyVisionProvider(),staging_root=tmp_path/'vision')
    yield SimpleNamespace(engine=engine,sessions=sessions,platform=platform,repo=repo,uploads=uploads,
        service=service,project=project,asset=asset,payload=payload,prepared=prepared,base=base,vision=vision,
        asr=asr,signals=signals,tmp=tmp_path)
    assert asr.calls==signals.calls==0
    await engine.dispose()


async def read_source(value,lane,path):
    if lane=='auto':return await value.service._download_analysis_source(
        value.prepared,value.project.project_id,value.payload,path)
    return await value.vision._download_vision_source(value.base,value.asset,path)


def set_storage(value,lane,storage):
    (value.service if lane=='auto' else value.vision).object_storage=storage


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['auto','vision'])
async def test_source_read_passes_every_registered_bound_without_analysis_dispatch(source,lane):
    store=RecordingStorage(source.uploads.object_storage);set_storage(source,lane,store)
    path=source.tmp/'admitted-source.mp4';before=source.base.model_dump(mode='json')
    await read_source(source,lane,path)
    assert path.read_bytes()==synthetic_mp4() and len(store.calls)==1
    assert_frozen(store.calls[0],source.asset,MAX_SOURCE_BYTES)
    assert (await source.repo.get_analysis(source.base.analysis_id)).model_dump(mode='json')==before
    assert not await source.platform.list_cost_records(source.project.project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['auto','vision'])
@pytest.mark.parametrize('change',['bytes','version','provenance','provider'])
async def test_source_tamper_or_configuration_drift_rejects_before_provider(source,lane,change):
    async def after(_):
        if change=='provider':
            provider=source.service.transcription_provider if lane=='auto' else source.vision.provider
            provider.model='explicit-drift-after-download'
        elif change!='bytes':
            async with source.sessions() as session,session.begin():
                row=await session.get(AssetORM,source.asset.asset_id)
                if change=='version':row.version+=1
                else:row.provenance={**row.provenance,'explicit_changed_lineage':True}
    store=RecordingStorage(source.uploads.object_storage,after=after);set_storage(source,lane,store)
    if change=='bytes':
        path=source.uploads.object_storage._path(source.asset.object_key)
        data=path.read_bytes();path.write_bytes(data[:-1]+b'X')
    with pytest.raises(ValueError):await read_source(source,lane,source.tmp/'rejected-source.mp4')
    assert len(store.calls)==1 and source.asr.calls==source.signals.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['auto','vision'])
async def test_provider_binding_changed_between_frozen_prepare_and_stage_blocks_before_sdk(source,lane):
    target=source.service if lane=='auto' else source.vision
    identity=target._source_provider_identity()
    provider=source.service.transcription_provider if lane=='auto' else source.vision.provider
    provider.model='explicit-early-drift'
    store=RecordingStorage(source.uploads.object_storage);set_storage(source,lane,store)
    with pytest.raises(ValueError,match='PROVIDER_CHANGED'):
        if lane=='auto':await target._download_analysis_source(source.prepared,source.project.project_id,
            source.payload,source.tmp/'not-read',expected_provider_identity=identity)
        else:await target._download_vision_source(source.base,source.asset,source.tmp/'not-read',expected_provider_identity=identity)
    assert not store.calls


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['auto','vision'])
async def test_invalid_registered_size_or_scope_is_not_guessed_or_retried_unbounded(source,lane):
    changed=source.asset.model_copy(update={'object_key':'workspaces/wsp_foreign/projects/prj_foreign/input.mp4'})
    source.asset=changed;source.prepared={**source.prepared,'asset':changed}
    store=RecordingStorage(source.uploads.object_storage);set_storage(source,lane,store)
    with pytest.raises(ValueError,match='DOWNLOAD_FAILED'):await read_source(source,lane,source.tmp/'not-read')
    assert not store.calls


@pytest.mark.asyncio
async def test_vision_analysis_changed_while_download_waits_blocks_source_admission(source):
    async def after(_):
        async with source.sessions() as session,session.begin():
            row=await session.get(AutoEditAnalysisORM,source.base.analysis_id)
            row.provenance_json={**row.provenance_json,'explicit_changed_base':True}
    store=RecordingStorage(source.uploads.object_storage,after=after);source.vision.object_storage=store
    with pytest.raises(ValueError,match='CUSTODY_CHANGED'):
        await source.vision._download_vision_source(source.base,source.asset,source.tmp/'changed-base')
    assert len(store.calls)==1


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['auto','vision'])
async def test_repeated_cancel_drains_counted_sdk_worker_before_returning_source_failure(source,lane):
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    data=synthetic_mp4()
    class PausedBody(Body):
        def read(self,size=-1):entered.set();assert release.wait(10);return super().read(size)
        def close(self):super().close();closed.set()
    store,calls=fake_s3(PausedBody(data),length=len(data));set_storage(source,lane,store)
    source.asset=source.asset.model_copy(update={'storage_provider':'s3'})
    source.prepared={**source.prepared,'asset':source.asset}
    path=source.tmp/'cancelled-source'
    task=asyncio.create_task(read_source(source,lane,path))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set() and not path.exists() and len(calls)==1
    finally:release.set();await asyncio.gather(task,return_exceptions=True)


async def preview_fixture(value):
    content=await author(value,original='Explicit preview-source fixture.')
    built=await timeline(value,content);asset=await image(value)
    renderer=SimpleNamespace(render=DeniedDispatch())
    service=PreviewService(repository=value.timeline,platform=value.platform,auto_edit_repository=value.assets,
        object_storage=value.storage,queue=value.queue,renderer=renderer,staging_root=value.tmp/'preview')
    preview=await service.enqueue(value.project.project_id,PreviewCreateRequest(timeline_version=built.current_version))
    await value.timeline.start_preview(preview.preview_id)
    return service,preview,asset,renderer


@pytest.mark.asyncio
async def test_preview_asset_admission_is_bounded_without_rendering(env):
    service,preview,asset,renderer=await preview_fixture(env)
    store=RecordingStorage(env.storage);service.object_storage=store
    await service._download_preview_asset(preview,asset,env.tmp/'preview-source')
    assert_frozen(store.calls[0],asset,MAX_SOURCE_BYTES)
    assert renderer.render.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['asset_version','cancel','timeline'])
async def test_preview_post_download_sql_change_or_late_cancel_blocks_before_renderer(env,change):
    service,preview,asset,renderer=await preview_fixture(env)
    async def after(_):
        if change=='cancel':await env.timeline.cancel_preview(preview.preview_id)
        elif change=='asset_version':
            async with env.factory() as session,session.begin():
                row=await session.get(AssetORM,asset.asset_id);row.version+=1
        else:
            current=await env.timeline.get_timeline(env.project.project_id)
            shape=current.snapshot.model_copy(deep=True);shape.metadata['explicit_changed']=True
            await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=current.current_version,
                snapshot=shape,mutation={'type':'explicit-cancel-source-fixture'},actor_ref='fixture-editor')
    store=RecordingStorage(env.storage,after=after);service.object_storage=store
    with pytest.raises((RuntimeError,PreviewCancelledError)):
        await service._download_preview_asset(preview,asset,env.tmp/'rejected-preview-source')
    assert len(store.calls)==1 and renderer.render.calls==0


@pytest.mark.asyncio
async def test_preview_cancel_committed_at_final_coherent_read_is_not_missed(env):
    service,preview,asset,renderer=await preview_fixture(env)
    original=env.assets.read_source_snapshot
    async def late(**kwargs):
        await env.timeline.cancel_preview(preview.preview_id)
        return await original(**kwargs)
    env.assets.read_source_snapshot=late
    with pytest.raises(PreviewCancelledError,match='CANCELLED'):
        await service._download_preview_asset(preview,asset,env.tmp/'source')
    assert renderer.render.calls==0 and await env.timeline.preview_cancel_requested(preview.preview_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['cancel','timeline','asset_version','staged_bytes'])
async def test_last_progress_await_cannot_dispatch_renderer_after_current_inputs_change(env,change):
    asset=await image(env)
    content=await author(env,[StoryboardScene(scene_id='scene_fixture',narration='Explicit image fixture.',
        media_strategy='user_asset',asset_id=asset.asset_id)])
    built=await timeline(env,content)
    renderer=SimpleNamespace(render=DeniedDispatch())
    service=PreviewService(repository=env.timeline,platform=env.platform,auto_edit_repository=env.assets,
        object_storage=env.storage,queue=env.queue,renderer=renderer,staging_root=env.tmp/'preview')
    preview=await service.enqueue(env.project.project_id,PreviewCreateRequest(timeline_version=built.current_version))
    original=env.timeline.set_preview_progress
    async def progress(preview_id,value):
        result=await original(preview_id,value)
        if value==35:
            if change=='cancel':await env.timeline.cancel_preview(preview_id)
            elif change=='timeline':
                current=await env.timeline.get_timeline(env.project.project_id)
                updated=current.snapshot.model_copy(deep=True);updated.metadata['changed_fixture']=True
                await env.timeline.commit_mutation(project_id=env.project.project_id,
                    expected_version=current.current_version,snapshot=updated,
                    mutation={'type':'explicit-pre-render-fixture'},actor_ref='fixture-editor')
            elif change=='asset_version':
                async with env.factory() as session,session.begin():
                    row=await session.get(AssetORM,asset.asset_id);row.version+=1
            else:
                path=service.staging_root/preview_id/f'{asset.asset_id}.png'
                data=path.read_bytes();path.write_bytes(data[:-1]+b'X')
        return result
    env.timeline.set_preview_progress=progress
    result=await service.process(preview.preview_id)
    assert renderer.render.calls==0, result.failure_reason
    assert result.status in {'cancelled','stale','failed'}


@pytest.mark.asyncio
async def test_registered_local_legacy_key_is_bounded_without_rewriting_source_history(env):
    service,preview,_,renderer=await preview_fixture(env)
    asset,source_path=await register_tone(env)
    original=env.storage.download_file;calls=[]
    async def recorded(**kwargs):
        calls.append(dict(kwargs));return await original(**kwargs)
    env.storage.download_file=recorded
    before=asset.model_dump(mode='json')
    target=env.tmp/'admitted-legacy.wav'
    await service._download_preview_asset(preview,asset,target)
    assert target.read_bytes()==source_path.read_bytes() and len(calls)==1
    assert calls[0]['object_key']==asset.object_key
    assert calls[0]['max_bytes']==MAX_SOURCE_BYTES
    assert calls[0]['expected_size_bytes']==asset.size_bytes
    assert calls[0]['expected_sha256']==asset.checksum_sha256
    assert calls[0]['expected_prefix']==f'projects/{env.project.project_id}/'
    assert (await env.assets.get_asset(asset.asset_id)).model_dump(mode='json')==before
    assert renderer.render.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('changed',['workspace','project_prefix','size','storage'])
async def test_legacy_prefix_never_admits_foreign_or_unbounded_or_s3_source(env,changed):
    service,preview,_,renderer=await preview_fixture(env)
    asset,_=await register_tone(env)
    original=env.storage.download_file;calls=[]
    async def recorded(**kwargs):calls.append(dict(kwargs));return await original(**kwargs)
    env.storage.download_file=recorded
    if changed=='workspace':asset=asset.model_copy(update={'workspace_id':'wsp_foreign'})
    elif changed=='project_prefix':asset=asset.model_copy(update={'object_key':'projects/prj_foreign/source.wav'})
    elif changed=='size':asset=asset.model_copy(update={'size_bytes':0})
    else:
        storage,sdk_calls=fake_s3(Body(b'explicit owned mock bytes'),length=25)
        service.object_storage=storage;asset=asset.model_copy(update={'storage_provider':'s3'})
    with pytest.raises(RuntimeError,match='DOWNLOAD_FAILED'):
        await service._download_preview_asset(preview,asset,env.tmp/'not-admitted')
    assert not calls and renderer.render.calls==0
    if changed=='storage':assert not sdk_calls
