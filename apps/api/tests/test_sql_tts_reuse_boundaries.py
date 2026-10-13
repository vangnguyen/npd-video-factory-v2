"""Actual owned SQLite/storage boundary regressions; synthetic PCM only."""
import asyncio
import copy
import hashlib
import json
import shutil
import sqlite3
from types import SimpleNamespace
import httpx
import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from app.db import AssetORM, CostRecordORM, ProviderUsageORM
from app.production_db import AudioMixVersionORM
from app.production_models import RenderCreateRequest, ProductionPackageCreateRequest, AudioMixReplaceRequest
from app.production_repository import ProductionRepository
from app.auto_edit_repository import AutoEditRepository
from app.repositories import PlatformRepository
from app.object_storage import LocalObjectStorageProvider
from app.sql_tts_artifact_reuse import pcm, TTSReuseRejected
from app.vieneu_tts_provider import VieNeuTTSProvider
from test_sql_tts_artifact_reuse import env, ready, processor, final, entries, raw_pcm


async def ledger(env):
    async with env.factory() as session:
        result={}
        for model in (ProviderUsageORM,CostRecordORM):
            rows=(await session.scalars(select(model))).all()
            result[model.__tablename__]={getattr(r,list(model.__table__.primary_key.columns)[0].name):
                json.dumps({c.name:getattr(r,c.name) for c in model.__table__.columns},sort_keys=True,default=str)
                for r in rows}
        return result


@pytest.mark.asyncio
@pytest.mark.parametrize('drift',['replace_bytes_and_checksum','provenance'])
async def test_approved_audio_asset_mutation_cannot_be_laundered_by_updating_sql_checksum(env,drift):
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id)
    assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    asset=await env.assets.get_asset(reviewed.manifest['supporting_asset_ids']['audio-mix'])
    if drift=='replace_bytes_and_checksum':
        path=env.storage.root/asset.object_key
        original=path.read_bytes();changed=original[:-2]+b'\x7f\x00';path.write_bytes(changed)
        values={'checksum_sha256':hashlib.sha256(changed).hexdigest()}
    else:
        values={'provenance':{**asset.provenance,'explicit_fixture_tamper':True}}
    async with env.factory() as session,session.begin():
        await session.execute(update(AssetORM).where(AssetORM.asset_id==asset.asset_id).values(**values))
    complete=await job.process(target.render_id)
    assert complete.status=='failed' and 'TTS_REUSE_APPROVED_AUDIO_PROOF_CHANGED_REVIEW_REQUIRED' in complete.failure_reason
    assert len(state['calls'])==1


@pytest.mark.asyncio
async def test_final_detects_canonical_audio_change_during_owned_download(env):
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    actual=env.storage.download_file;entered=asyncio.Event();resume=asyncio.Event()
    async def paused(*,object_key,destination):
        await actual(object_key=object_key,destination=destination)
        if destination.name=='narration.wav':entered.set();await resume.wait()
    env.storage.download_file=paused
    task=asyncio.create_task(job.process(target.render_id))
    try:
        await asyncio.wait_for(entered.wait(),10)
        async with env.factory() as session,session.begin():
            row=await session.get(AudioMixVersionORM,target.audio_version_id)
            value=copy.deepcopy(row.config_json);value['voice']['gain_db']=1
            await session.execute(update(AudioMixVersionORM).where(AudioMixVersionORM.audio_version_id==row.audio_version_id)
                .values(config_json=value))
        resume.set();result=await task
        assert result.status=='failed' and 'TTS_REUSE_CANONICAL_INPUT_CHANGED' in result.failure_reason
        assert len(state['calls'])==1 and 'narration' not in result.manifest
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        env.storage.download_file=actual


@pytest.mark.asyncio
async def test_sql_and_object_storage_cold_restore_preserves_exact_approved_audio_without_provider(env):
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    before=await ledger(env)
    root=env.tmp/'owned-restore';root.mkdir()
    def snapshot():
        with sqlite3.connect(env.engine.url.database) as source,sqlite3.connect(root/'restored.db') as dest:
            source.backup(dest)
        shutil.copytree(env.storage.root,root/'objects')
    await asyncio.to_thread(snapshot)
    engine=create_async_engine('sqlite+aiosqlite:///'+str(root/'restored.db'))
    factory=async_sessionmaker(engine,expire_on_commit=False)
    cold=SimpleNamespace(factory=factory,platform=PlatformRepository(factory),assets=AutoEditRepository(factory),
        storage=LocalObjectStorageProvider(root/'objects'),tmp=root)
    class DeniedProvider:
        def __getattr__(self,name):raise AssertionError('No provider or secrets after restore: '+name)
    try:
        completed=await processor(cold,DeniedProvider()).process(target.render_id)
        assert completed.status=='ready',completed.failure_reason
        original=await env.assets.get_asset(reviewed.manifest['supporting_asset_ids']['audio-mix'])
        derived=await cold.assets.get_asset(completed.manifest['supporting_asset_ids']['audio-mix'])
        assert original.checksum_sha256==derived.checksum_sha256
        after=await ledger(cold)
        for table,rows in before.items():
            assert all(after[table][identity]==serialized for identity,serialized in rows.items())
        assert (await env.production.get_render(target.render_id)).status=='queued'
        assert len(state['calls'])==1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_new_review_voice_selection_is_a_new_fingerprint_and_keeps_prior_ledger_byte_exact(env):
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    old=(await entries(env))[0];original=copy.deepcopy(old.result_json);before=await ledger(env)
    package=await env.production.get_package(env.project.project_id)
    config=package.audio_mix.config.model_copy(deep=True);config.voice.voice='Thùy Dung'
    changed=await env.package.replace_audio_mix(env.project.project_id,AudioMixReplaceRequest(
        expected_timeline_version=review.timeline_version,expected_audio_version=review.audio_version,config=config))
    draft=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=review.timeline_version,
        expected_subtitle_version=changed.subtitle.version,expected_audio_version=changed.audio_mix.version))
    result=await job.process(draft.render_id)
    assert result.status=='awaiting_review',result.failure_reason
    assert len(state['calls'])==2 and len(await entries(env))==2
    assert 'raw_audio_reuse' not in result.manifest['narration']['timing'][0]
    assert state['calls'][1]['profile']['voice_id']=='Thùy Dung'
    assert next(r for r in await entries(env) if r.reuse_id==old.reuse_id).result_json==original
    after=await ledger(env)
    for table,rows in before.items():
        assert all(after[table][identity]==serialized for identity,serialized in rows.items())


@pytest.mark.asyncio
async def test_mixed_hit_and_fresh_unit_accounts_only_new_provider_evidence(env):
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    original=copy.deepcopy((await entries(env))[0].result_json);before=await ledger(env)
    previous=await env.timeline.get_timeline(env.project.project_id)
    shape=previous.snapshot.model_copy(deep=True)
    # An explicit manual timeline edit retains its content lineage; the new
    # canonical text has a different raw-unit input fingerprint.
    old_duration=shape.duration_seconds
    for track in shape.tracks:
        if not track.clips:continue
        second=track.clips[0].model_copy(deep=True)
        second.clip_id+='2';second.timeline_start=old_duration
        second.metadata['scene_index']=1;second.metadata['scene_id']='scene_fixture_02'
        if track.kind=='subtitles':second.label='Một câu khác.'
        track.clips.append(second)
    shape.duration_seconds=2*old_duration
    plan=shape.metadata['narration_plan']
    text='Một câu khác.'
    plan['units'].append({'unit_id':'narration_fixture_02','text':text,'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
        'scene_indices':[1],'script_start':None,'script_end':None})
    scene=copy.deepcopy(plan['scenes'][0]);scene['scene_id']='scene_fixture_02';plan['scenes'].append(scene)
    changed=await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=previous.current_version,
        snapshot=shape,mutation={'type':'explicit-fixture-manual-caption'},actor_ref='fixture-editor')
    package=await env.package.create_or_refresh(env.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=changed.current_version))
    draft=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=changed.current_version,
        expected_subtitle_version=package.subtitle.version,expected_audio_version=package.audio_mix.version))
    result=await job.process(draft.render_id)
    assert result.status=='awaiting_review',result.failure_reason
    assert len(state['calls'])==2
    units=result.manifest['narration']['timing']
    assert units[0]['raw_audio_reuse']['original_evidence_sha256']==original['original_evidence_sha256']
    assert units[0]['provider_evidence']==original['original_evidence']
    assert 'raw_audio_reuse' not in units[1]
    async with env.factory() as session:
        usage=await session.scalar(select(ProviderUsageORM).where(ProviderUsageORM.operation=='tts.v2-08.'+draft.render_id))
        assert usage.metadata_json['provider_evidence']==[units[1]['provider_evidence']]
        assert usage.metadata_json['additional_provider_billed_cost_vnd'] is None
        cost=await session.scalar(select(CostRecordORM).where(CostRecordORM.provider_usage_id==usage.usage_id))
        assert cost.actual_cost is None
    after=await ledger(env)
    for table,rows in before.items():
        assert all(after[table][identity]==serialized for identity,serialized in rows.items())


@pytest.mark.asyncio
async def test_same_text_in_another_workspace_cannot_reuse_project_pcm(env):
    from app.platform_models import WorkspaceCreate,ProjectCreate
    state,job,_,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    workspace=await env.platform.create_workspace(WorkspaceCreate(slug='second-fixture-workspace',name='Fixture',owner_ref='fixture'))
    project=await env.platform.create_project(workspace.workspace_id,ProjectCreate(slug='other',name='Fixture'))
    other=SimpleNamespace(**{**vars(env),'project':project,'workspace':workspace})
    second_state,second_job,_,second_review=await ready(other)
    complete=await second_job.process(second_review.render_id)
    assert complete.status=='awaiting_review',complete.failure_reason
    assert len(state['calls'])==len(second_state['calls'])==1 and len(await entries(env))==2
    assert 'raw_audio_reuse' not in complete.manifest['narration']['timing'][0]
    assert len({r.workspace_id for r in await entries(env)})==2


def test_raw_pcm_unavailable_error_contains_no_private_path_or_input(tmp_path):
    from app.tts_evidence import TTSArtifactEvidence,SpeechTimingEvidence,ProductionTTSProfile
    private=tmp_path/'private-example-client'/'missing.wav'
    selected=ProductionTTSProfile(provider_key='openai-tts',model='fixture',voice_id='fixture')
    evidence=TTSArtifactEvidence(profile=selected,profile_sha256=selected.sha256,
        text_sha256=hashlib.sha256(b'EXPLICIT PRIVATE FIXTURE').hexdigest(),audio_sha256='b'*64,
        request_sha256='c'*64,decoded_duration_seconds=.5,latency_seconds=0,
        timing=SpeechTimingEvidence(source='ESTIMATED_SEGMENT',reference_text='EXPLICIT PRIVATE FIXTURE',audio_sha256='b'*64,duration_seconds=.5))
    with pytest.raises(TTSReuseRejected) as error:pcm(private,evidence)
    assert str(error.value)=='TTS_REUSE_PCM_UNAVAILABLE'
    assert 'private' not in str(error.value) and str(tmp_path) not in str(error.value)


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['raw_cache','approved_pcm','approved_raw_unit'])
@pytest.mark.parametrize('field',['asset_class','project_version_id'])
async def test_asset_lineage_rebind_during_download_blocks_final_and_raw_cache_receipts(env,lane,field):
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    if lane=='raw_cache':
        source=(await entries(env))[0].result_json['asset_id']
        target=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=1,
            expected_subtitle_version=1,expected_audio_version=1,profile='review-960x540'))
    else:
        source=reviewed.manifest['supporting_asset_ids']['audio-mix'] if lane=='approved_pcm' \
            else reviewed.manifest['narration']['timing'][0]['provider_audio_asset_id']
        target=await final(env,reviewed)
    asset=await env.assets.get_asset(source)
    key=asset.object_key
    actual=env.storage.download_file;entered=asyncio.Event();resume=asyncio.Event()
    async def paused(*,object_key,destination):
        await actual(object_key=object_key,destination=destination)
        if object_key==key:entered.set();await resume.wait()
    env.storage.download_file=paused
    task=asyncio.create_task(job.process(target.render_id))
    try:
        await asyncio.wait_for(entered.wait(),10)
        value='source' if field=='asset_class' else None if asset.project_version_id is not None else version.project_version_id
        async with env.factory() as session,session.begin():
            await session.execute(update(AssetORM).where(AssetORM.asset_id==source).values(**{field:value}))
        resume.set();result=await task
        assert result.status=='failed' and 'TTS_REUSE_' in result.failure_reason
        assert len(state['calls'])==1 and 'narration' not in result.manifest
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        env.storage.download_file=actual


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['before_final','during_final_download'])
async def test_public_generic_content_version_blocks_stale_approved_audio_without_provider(env,phase,monkeypatch):
    from app.main import app
    from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
    state,job,version,review=await ready(env)
    reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
    target=await final(env,reviewed)
    monkeypatch.setattr(app.state,'platform_repository',env.platform,raising=False)
    install_test_human_auth(app,platform_repository=env.platform)
    entered=asyncio.Event();resume=asyncio.Event();actual=env.storage.download_file
    async def paused(*,object_key,destination):
        await actual(object_key=object_key,destination=destination)
        if destination.name=='narration.wav':entered.set();await resume.wait()
    async def append_uninvalidated_version():
        value=copy.deepcopy(version.snapshot);value['content']['script']='Explicit changed fixture content.'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture',
                headers=TEST_HUMAN_HEADERS) as client:
            response=await client.post(f'/api/v1/projects/{env.project.project_id}/versions',
                json={'label':'mvp1-content','snapshot':value,'provenance':{'fixture':True}})
        assert response.status_code==201,response.text
        assert response.json()['project_version_id']!=version.project_version_id
        package=await env.production.get_package(env.project.project_id)
        assert package.approval.status=='approved'  # Reproduce the generic route's lack of invalidation.
        pending=await env.production.get_render(target.render_id)
        assert pending.status in {'queued','running'} and pending.cancellation_requested is False
    class DeniedProvider:
        def __getattr__(self,name):raise AssertionError('Stale final must not touch provider: '+name)
    task=None
    try:
        if phase=='during_final_download':
            env.storage.download_file=paused
            task=asyncio.create_task(processor(env,DeniedProvider()).process(target.render_id))
            await asyncio.wait_for(entered.wait(),10)
        await append_uninvalidated_version()
        if task is not None:
            resume.set();result=await task
        else:result=await processor(env,DeniedProvider()).process(target.render_id)
        assert result.status=='failed' and 'TTS_REUSE_CONTENT_VERSION_STALE' in result.failure_reason
        assert len(state['calls'])==1 and 'narration' not in result.manifest
    finally:
        resume.set()
        if task is not None and not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)
        env.storage.download_file=actual


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['raw_cache','approved_pcm','raw_store'])
@pytest.mark.parametrize('sdk_error',['ClientError','EndpointConnectionError'])
async def test_storage_sdk_exceptions_are_bounded_and_never_expose_object_or_endpoint(env,lane,sdk_error):
    from botocore.exceptions import ClientError,EndpointConnectionError
    error=ClientError({'Error':{'Code':'NoSuchKey','Message':'EXPLICIT PRIVATE SDK FIXTURE'},
        'ResponseMetadata':{'HTTPStatusCode':404}},'GetObject') if sdk_error=='ClientError' \
        else EndpointConnectionError(endpoint_url='https://private-example.invalid/private-fixture')
    state,job,_,review=await ready(env)
    actual_download=env.storage.download_file;actual_put=env.storage.put_file
    if lane=='raw_store':
        async def broken_put(**kwargs):
            if '/tts-reuse/' in kwargs['object_key']:raise error
            return await actual_put(**kwargs)
        env.storage.put_file=broken_put
        target=review
    else:
        reviewed=await job.process(review.render_id);assert reviewed.status=='awaiting_review',reviewed.failure_reason
        if lane=='raw_cache':
            target=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(expected_timeline_version=1,
                expected_subtitle_version=1,expected_audio_version=1,profile='review-960x540'))
        else:target=await final(env,reviewed)
        async def broken_download(*,object_key,destination):
            if '/tts-reuse/' in object_key or destination.name=='narration.wav':raise error
            await actual_download(object_key=object_key,destination=destination)
        env.storage.download_file=broken_download
    try:
        result=await job.process(target.render_id)
        assert result.status=='failed' and 'TTS_REUSE_' in result.failure_reason
        assert 'private-example' not in result.failure_reason and 'PRIVATE SDK' not in result.failure_reason
        assert 'GetObject' not in result.failure_reason and '/workspaces/' not in result.failure_reason
        assert len(state['calls'])==1
        if lane=='raw_store':assert (await entries(env))[0].state=='unknown'
    finally:
        env.storage.download_file=actual_download;env.storage.put_file=actual_put
