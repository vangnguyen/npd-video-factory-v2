"""Frozen SQL asset custody/owned bytes only; no model, TTS, DSP or renderer."""
import asyncio
import copy
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.auto_edit_source_custody import staged_trusted_video
from app.db import AssetORM, ProviderUsageORM
from app.frozen_storage_read import MAX_SOURCE_BYTES
from app.platform_models import AssetRegister
from app.production_service import ProductionRenderProcessor, RenderCancelledError
from app.production_logic import ProductionContractError
from app.sql_tts_artifact_reuse import prepared_final_audio, prepared_audio_byte_limit, TTSReuseRejected
from app.uploaded_audio_repository import AudioConflict
from test_auto_edit_analysis import setup_services, upload_fixture, synthetic_mp4
from test_mvp1_multi_input import env, image
from test_sql_tts_prepared_pcm_bounds import approved_source
from test_source_asset_delivery import fixture as source_fixture
from test_uploaded_audio import stack


class RecordingStorage:
    """The adapter signature explicitly requires every bounded argument."""
    def __init__(self,delegate,*,after=None):
        self.delegate,self.name,self.calls,self.after=delegate,delegate.name,[],after
    async def download_file(self,*,object_key,destination,max_bytes,expected_size_bytes,expected_sha256,expected_prefix):
        args=dict(object_key=object_key,destination=destination,max_bytes=max_bytes,
            expected_size_bytes=expected_size_bytes,expected_sha256=expected_sha256,expected_prefix=expected_prefix)
        self.calls.append(args.copy())
        await self.delegate.download_file(**args)
        if self.after is not None:await self.after(destination)


def assert_frozen(call,asset,maximum):
    assert call['object_key']==asset.object_key
    assert call['max_bytes']==maximum and call['expected_size_bytes']==asset.size_bytes
    assert call['expected_sha256']==asset.checksum_sha256
    assert call['expected_prefix']==f'workspaces/{asset.workspace_id}/projects/{asset.project_id}/'


@pytest.mark.asyncio
async def test_uploaded_audio_staging_uses_registered_proof_without_asr_dispatch(tmp_path):
    value=await stack(tmp_path)
    try:
        queued=await value.service.create(value.project.project_id,value.request,'usr:fixture-editor')
        asset=await value.assets.get_asset(value.request.asset_id)
        store=RecordingStorage(value.service.object_storage);value.service.object_storage=store
        owner,path,_,_=await value.service.source_file(value.project.project_id,queued.audio_id)
        try:assert path.read_bytes()==value.raw
        finally:owner.cleanup()
        assert len(store.calls)==1;assert_frozen(store.calls[0],asset,MAX_SOURCE_BYTES)
        assert value.provider.calls==0 and not list(value.service.staging_root.iterdir())
    finally:await value.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('field',['object_key','version','provenance'])
async def test_uploaded_audio_custody_change_during_download_blocks_even_with_same_bytes(tmp_path,field):
    value=await stack(tmp_path)
    try:
        queued=await value.service.create(value.project.project_id,value.request,'usr:fixture-editor')
        async def mutate(_):
            async with value.sessions() as session,session.begin():
                row=await session.get(AssetORM,value.request.asset_id)
                if field=='object_key':row.object_key=row.object_key+'.rebound'
                elif field=='version':row.version+=1
                else:row.provenance={**row.provenance,'new_fixture_provenance':True}
        store=RecordingStorage(value.service.object_storage,after=mutate);value.service.object_storage=store
        with pytest.raises(AudioConflict,match='AUDIO_SOURCE_CHANGED'):
            await value.service.source_file(value.project.project_id,queued.audio_id)
        assert len(store.calls)==1 and value.provider.calls==0
        assert not list(value.service.staging_root.iterdir())
    finally:await value.engine.dispose()


@pytest.mark.asyncio
async def test_uploaded_audio_frozen_provider_byte_limit_blocks_before_storage(tmp_path):
    value=await stack(tmp_path)
    try:
        value.provider.max_file_bytes=len(value.raw)-1
        queued=await value.service.create(value.project.project_id,value.request,'usr:fixture-editor')
        store=RecordingStorage(value.service.object_storage);value.service.object_storage=store
        with pytest.raises(AudioConflict,match='AUDIO_SOURCE_CHANGED'):
            await value.service.source_file(value.project.project_id,queued.audio_id)
        assert not store.calls and value.provider.calls==0
    finally:await value.engine.dispose()


@pytest.mark.asyncio
async def test_trusted_video_staging_binds_exact_custody_and_registered_byte_limits(tmp_path):
    values=await setup_services(tmp_path)
    engine,sessions,_,repository,uploads,_,project,version=values
    try:
        completed=await upload_fixture(uploads,project,version,synthetic_mp4())
        asset=await repository.get_asset(completed.asset_id)
        store=RecordingStorage(uploads.object_storage)
        async with staged_trusted_video(repository,store,project.project_id,asset.asset_id,tmp_path/'stage',1024*1024) as (path,snapshot):
            assert path.read_bytes()==synthetic_mp4() and snapshot['source_sha256']==asset.checksum_sha256
        assert len(store.calls)==1;assert_frozen(store.calls[0],asset,1024*1024)
        assert not list((tmp_path/'stage').iterdir())
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_trusted_video_registered_key_rebound_after_read_is_rejected_and_cleans(tmp_path):
    values=await setup_services(tmp_path)
    engine,sessions,_,repository,uploads,_,project,version=values
    try:
        completed=await upload_fixture(uploads,project,version,synthetic_mp4())
        async def mutate(_):
            async with sessions() as session,session.begin():
                asset=await session.get(AssetORM,completed.asset_id);asset.object_key+='.rebound'
        store=RecordingStorage(uploads.object_storage,after=mutate)
        with pytest.raises(ValueError,match='SOURCE_CUSTODY_CHANGED'):
            async with staged_trusted_video(repository,store,project.project_id,completed.asset_id,tmp_path/'stage',1024*1024):
                raise AssertionError('Changed custody cannot be yielded')
        assert len(store.calls)==1 and not list((tmp_path/'stage').iterdir())
    finally:await engine.dispose()


@pytest.mark.asyncio
async def test_prepared_review_reads_bounded_approved_sources_preserving_sql_history(env):
    reviewed,target,snapshot,package,proofs=await approved_source(env,20)
    historical=copy.deepcopy((await env.production.get_render(reviewed.render_id)).manifest)
    costs=await env.platform.list_cost_records(env.project.project_id)
    store=RecordingStorage(env.storage);workdir=env.tmp/'prepared-read';workdir.mkdir()
    narration,_=await prepared_final_audio(repository=env.production,assets=env.assets,storage=store,
        render=target,snapshot=snapshot,subtitles=package.subtitle,config=package.audio_mix.config,workdir=workdir)
    assert len(store.calls)==2
    for call,kind in zip(store.calls,['narration-track','audio-mix']):
        asset=await env.assets.get_asset(proofs[kind]['asset_id'])
        assert_frozen(call,asset,prepared_audio_byte_limit(20))
    assert (await env.production.get_render(reviewed.render_id)).manifest==historical
    assert await env.platform.list_cost_records(env.project.project_id)==costs
    async with env.factory() as session:assert not (await session.scalars(select(ProviderUsageORM))).all()
    assert narration['prepared_audio_reuse']['provider_calls']==0


@pytest.mark.asyncio
async def test_prepared_review_corrupt_storage_blocks_and_never_delegates_tts(env):
    _,target,snapshot,package,proofs=await approved_source(env,20)
    asset=await env.assets.get_asset(proofs['narration-track']['asset_id'])
    path=env.storage._path(asset.object_key);raw=path.read_bytes();path.write_bytes(raw[:-1]+b'x')
    store=RecordingStorage(env.storage);workdir=env.tmp/'prepared-read';workdir.mkdir()
    with pytest.raises(TTSReuseRejected,match='APPROVED_ASSET_UNAVAILABLE'):
        await prepared_final_audio(repository=env.production,assets=env.assets,storage=store,
            render=target,snapshot=snapshot,subtitles=package.subtitle,config=package.audio_mix.config,workdir=workdir)
    assert len(store.calls)==1 and not list(workdir.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize('kind',['image','original_audio','music'])
async def test_render_selected_asset_reads_use_registered_bytes_without_renderer_or_audio_engine(env,kind):
    asset=await image(env)
    if kind!='image':
        from test_uploaded_audio import wav_bytes
        path=env.tmp/(kind+'.wav');path.write_bytes(wav_bytes())
        stored=await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/input/{path.name}',path=path)
        asset=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='source',kind='audio',
            filename=path.name,object_key=stored.object_key,content_type='audio/wav',size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,storage_provider='local',provenance={'rights_status':'owned','explicit_fixture':True}))
    processor=object.__new__(ProductionRenderProcessor)
    processor.object_storage=RecordingStorage(env.storage);processor.asset_repository=env.assets
    async def not_cancelled(_):return False
    processor.repository=SimpleNamespace(render_cancel_requested=not_cancelled)
    render=SimpleNamespace(workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,render_id='rdr_fixture')
    target=env.tmp/'bounded-asset'
    await processor._download_render_asset(render,asset,target)
    assert_frozen(processor.object_storage.calls[0],asset,MAX_SOURCE_BYTES)
    assert target.read_bytes()==env.storage._path(asset.object_key).read_bytes()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['version','cancel'])
async def test_render_selected_asset_recheck_after_await_does_not_transfer_stale_custody(env,mutation):
    asset=await image(env);cancelled=False
    async def after(_):
        nonlocal cancelled
        if mutation=='cancel':cancelled=True
        else:
            async with env.factory() as session,session.begin():
                row=await session.get(AssetORM,asset.asset_id);row.version+=1
    processor=object.__new__(ProductionRenderProcessor)
    processor.object_storage=RecordingStorage(env.storage,after=after);processor.asset_repository=env.assets
    async def is_cancelled(_):return cancelled
    processor.repository=SimpleNamespace(render_cancel_requested=is_cancelled)
    render=SimpleNamespace(workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,render_id='rdr_fixture')
    with pytest.raises(RenderCancelledError if mutation=='cancel' else ProductionContractError):
        await processor._download_render_asset(render,asset,env.tmp/'bounded-asset')
    assert len(processor.object_storage.calls)==1


@pytest.mark.asyncio
async def test_source_http_foreign_namespace_is_rejected_before_storage(source_fixture):
    client,state,staging,_,_=source_fixture
    state['asset']=state['asset'].model_copy(update={'object_key':'workspaces/wsp_foreign/projects/prj_fixture/source/audio.wav'})
    response=await client.get('/fixture-source')
    assert response.status_code==409 and response.json()['detail']['code']=='SOURCE_ASSET_METADATA_INVALID'
    assert not state['calls'] and not staging.exists()


@pytest.mark.asyncio
async def test_source_delivery_cancel_twice_drains_mock_sdk_body_before_private_staging_cleanup(source_fixture,tmp_path):
    from fastapi import Request
    from app.source_asset_delivery import deliver_source_asset
    from test_bounded_storage_download import Body,fake_s3
    _,state,_,data,_=source_fixture
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    class PausedBody(Body):
        def read(self,size=-1):
            entered.set();assert release.wait(10)
            return super().read(size)
        def close(self):super().close();closed.set()
    store,calls=fake_s3(PausedBody(data),length=len(data))
    asset=state['asset'].model_copy(update={'storage_provider':'s3'})
    staging=tmp_path/'cancelled-source-delivery'
    request=Request({'type':'http','method':'GET','path':'/','headers':[], 'query_string':b''})
    task=asyncio.create_task(deliver_source_asset(request,asset=asset,object_storage=store,staging_root=staging))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set() and list(staging.iterdir())
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set() and not list(staging.iterdir()) and len(calls)==1
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['uploaded_audio','render_asset'])
async def test_storage_sdk_private_error_is_bounded_at_selected_consumer(env,tmp_path,lane):
    from botocore.exceptions import EndpointConnectionError
    class FailedStorage:
        name='local'
        async def download_file(self,*,object_key,destination,max_bytes,expected_size_bytes,expected_sha256,expected_prefix):
            raise EndpointConnectionError(endpoint_url='https://explicit-private-fixture.invalid/private-key')
    if lane=='uploaded_audio':
        value=await stack(tmp_path/'audio-sdk')
        try:
            queued=await value.service.create(value.project.project_id,value.request,'usr:fixture-editor')
            value.service.object_storage=FailedStorage()
            with pytest.raises(AudioConflict) as error:await value.service.source_file(value.project.project_id,queued.audio_id)
            assert str(error.value)=='AUDIO_SOURCE_DOWNLOAD_FAILED' and value.provider.calls==0
            assert not list(value.service.staging_root.iterdir())
        finally:await value.engine.dispose()
    else:
        asset=await image(env)
        processor=object.__new__(ProductionRenderProcessor);processor.object_storage=FailedStorage()
        processor.asset_repository=env.assets
        render=SimpleNamespace(workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,render_id='rdr_fixture')
        with pytest.raises(ProductionContractError) as error:await processor._download_render_asset(render,asset,env.tmp/'not-created')
        assert str(error.value)=='RENDER_ASSET_DOWNLOAD_FAILED'


@pytest.mark.asyncio
@pytest.mark.parametrize('case',['hit','corrupt','oversize','late_cancel_asset','late_cancel_content','early_cancel_content'])
async def test_raw_tts_cache_registered_read_is_bounded_without_synthesis_or_ledger_rewrite(env,case):
    import hashlib
    from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
    from app.sql_tts_artifact_reuse import (ReusingTTSProvider,TTSArtifactReuseRepository,asset_proof,
        canonical_audio_binding,digest,SCHEMA,MAX_BYTES)
    from app.sql_tts_artifact_reuse_db import TTSArtifactReuseORM
    from app.tts_evidence import ProductionTTSProfile,TTSArtifactEvidence,SpeechTimingEvidence
    from test_mvp1_multi_input import author,timeline
    from test_sql_tts_artifact_reuse import raw_pcm
    version=await author(env,original='Explicit synthetic cached PCM fixture.')
    built=await timeline(env,version)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    review=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=built.current_version,expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    await env.production.start_render(review.render_id)
    target=canonical_audio_binding(review,built.snapshot.model_dump(mode='json'),package.subtitle,package.audio_mix.config)
    profile=ProductionTTSProfile(provider_key='explicit-fixture-tts',model='no-inference-synthetic-cache',voice_id='fixture')
    adapter={'profile_sha256':profile.sha256,'server_source_sha256':'1'*64,'transport_mode':'explicit-fixture'}
    calls=[]
    async def denied(**kwargs):calls.append(kwargs);raise AssertionError('A cached read cannot synthesize')
    provider=SimpleNamespace(model=profile.model,voice=profile.voice_id,artifact_reuse_binding=adapter,synthesize=denied)
    async def guard():await env.production.assert_audio_reuse_current(review.render_id,target)
    store=RecordingStorage(env.storage)
    wrapped=ReusingTTSProvider(provider,repository=TTSArtifactReuseRepository(env.factory),platform=env.platform,
        assets=env.assets,storage=store,render=review,content=version,voice_config=package.audio_mix.config.voice,
        guard=guard,target_binding=target)
    text='Explicit cached text.'
    binding={**wrapped._scope,'language':'vi','text_sha256':hashlib.sha256(text.encode()).hexdigest()}
    path=env.tmp/'raw-fixture.wav';data=raw_pcm();path.write_bytes(data)
    saved=await env.storage.put_file(object_key=f'workspaces/{env.workspace.workspace_id}/projects/{env.project.project_id}/tts-reuse/raw-fixture.wav',path=path)
    asset=await env.platform.register_asset(env.project.project_id,AssetRegister(asset_class='generated',kind='tts-reuse-source',
        project_version_id=version.project_version_id,filename=path.name,object_key=saved.object_key,content_type='audio/wav',
        size_bytes=MAX_BYTES+1 if case=='oversize' else saved.size_bytes,checksum_sha256=saved.checksum_sha256,
        storage_provider='local',provenance={'explicit_synthetic_fixture':True,'human_accepted':False}))
    evidence=TTSArtifactEvidence(profile=profile,profile_sha256=profile.sha256,text_sha256=binding['text_sha256'],
        audio_sha256=saved.checksum_sha256,request_sha256='3'*64,decoded_duration_seconds=.5,latency_seconds=0,
        timing=SpeechTimingEvidence(source='NONE',duration_seconds=.5),
        usage={'server_source_sha256':'1'*64,'normalization_record_sha256':'2'*64,'fixture':True})
    result={'schema_version':SCHEMA,'input_fingerprint':digest(binding),'source_render_id':review.render_id,
        'asset_id':asset.asset_id,'object_key':asset.object_key,'size_bytes':asset.size_bytes,'asset_proof':asset_proof(asset),
        'original_evidence':evidence.model_dump(mode='json'),'original_evidence_sha256':digest(evidence.model_dump(mode='json')),
        'normalization_record_sha256':'2'*64,'provider':'explicit-fixture-tts','voice':'fixture'}
    reuse_id='ttr_'+digest(binding)
    async with env.factory() as session,session.begin():
        session.add(TTSArtifactReuseORM(reuse_id=reuse_id,workspace_id=env.workspace.workspace_id,
            project_id=env.project.project_id,content_version_id=version.project_version_id,fingerprint=digest(binding),
            binding_json=binding,state='ready',source_render_id=review.render_id,result_json=result,result_sha256=digest(result)))
    if case=='corrupt':env.storage._path(asset.object_key).write_bytes(data[:-1]+b'x')
    costs=await env.platform.list_cost_records(env.project.project_id)
    target_path=env.tmp/'unit-001-raw.wav'
    if case=='late_cancel_asset':
        class LateAssetRead:
            calls=0
            async def get_asset(self,asset_id):
                self.calls+=1;value=await env.assets.get_asset(asset_id)
                if self.calls==2:
                    await env.production.cancel_render(env.project.project_id,review.render_id,'usr:explicit-fixture-editor')
                return value
        wrapped.assets=LateAssetRead()
    elif case in {'late_cancel_content','early_cancel_content'}:
        class LateContentRead:
            calls=0
            async def get_version(self,version_id):
                self.calls+=1;value=await env.platform.get_version(version_id)
                if self.calls==(1 if case=='early_cancel_content' else 2):
                    await env.production.cancel_render(env.project.project_id,review.render_id,'usr:explicit-fixture-editor')
                return value
        wrapped.platform=LateContentRead()
    if case=='hit':
        reused=await wrapped.synthesize(text=text,language='vi',output_path=target_path)
        assert reused.path.read_bytes()==data and reused.reuse['provider_calls']==0
        assert_frozen(store.calls[0],asset,MAX_BYTES)
    elif 'cancel' in case:
        from app.production_repository import ApprovalBoundaryError
        with pytest.raises(ApprovalBoundaryError,match='TTS_REUSE_RENDER_NOT_CURRENT'):
            await wrapped.synthesize(text=text,language='vi',output_path=target_path)
        assert await env.production.render_cancel_requested(review.render_id)
    else:
        with pytest.raises(TTSReuseRejected,match='SOURCE_UNAVAILABLE'):
            await wrapped.synthesize(text=text,language='vi',output_path=target_path)
        assert not target_path.exists()
    assert len(store.calls)==(0 if case in {'oversize','early_cancel_content'} else 1) and not calls
    assert await env.platform.list_cost_records(env.project.project_id)==costs
    async with env.factory() as session:
        row=await session.get(TTSArtifactReuseORM,reuse_id)
        assert row.state=='ready' and row.result_json==result and row.result_sha256==digest(result)
        assert not (await session.scalars(select(ProviderUsageORM))).all()


@pytest.mark.asyncio
async def test_render_cancel_committed_during_final_asset_read_blocks_consumer_return(env):
    from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
    from test_mvp1_multi_input import author,timeline
    version=await author(env,original='Actual SQL cancellation fixture, no rendering.')
    built=await timeline(env,version)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    render=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=built.current_version,expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    await env.production.start_render(render.render_id)
    asset=await image(env)
    class LateAssetRead:
        calls=0
        async def get_asset(self,asset_id):
            self.calls+=1;current=await env.assets.get_asset(asset_id)
            await env.production.cancel_render(env.project.project_id,render.render_id,'usr:explicit-fixture-editor')
            return current
    processor=object.__new__(ProductionRenderProcessor)
    processor.asset_repository=LateAssetRead();processor.repository=env.production
    processor.object_storage=RecordingStorage(env.storage)
    costs=await env.platform.list_cost_records(env.project.project_id)
    with pytest.raises(RenderCancelledError):await processor._download_render_asset(render,asset,env.tmp/'owned-source-copy')
    assert await env.production.render_cancel_requested(render.render_id)
    assert processor.asset_repository.calls==1 and len(processor.object_storage.calls)==1
    assert await env.platform.list_cost_records(env.project.project_id)==costs
    async with env.factory() as session:assert not (await session.scalars(select(ProviderUsageORM))).all()
