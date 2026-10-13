"""Actual child SQL/ASGI source custody and queued review asset admission.

No ASR, TTS, renderer, provider, paid call or Owner acceptance is performed.
"""
import asyncio
import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace
import httpx
import pytest
from fastapi import FastAPI,Depends
from app.human_auth import authorize_human_request
from sqlalchemy import select,func
from pydantic import ValidationError
from app.auto_edit_providers import ContractOnlyTranscriptionProvider
from app.auto_edit_source_custody import staged_trusted_video
from app.db import AssetORM,JobORM,VideoProjectORM,ProviderUsageORM
from app.models import JobRecord
from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest
from app.production_service import ProductionRenderProcessor
from app.uploaded_audio_db import UploadedAudioORM
from app.uploaded_audio_repository import UploadedAudioRepository
from app.uploaded_audio_service import UploadedAudioService
from app.uploaded_audio_models import AudioWordEdit
from app.uploaded_audio_routes import router
from app.sql_variant_import_job import VariantEvidenceImportInput
from app.sql_variant_db import SqlVariantArtifactReceiptORM
from app.sql_variant_repository import SqlVariantError
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
from test_bounded_storage_consumers import RecordingStorage,assert_frozen
from test_sql_variant_uploaded_derivation import env,uploaded,request

class NoASR(ContractOnlyTranscriptionProvider):
    def __init__(self):self.calls=0
    async def transcribe(self,*args,**kwargs):
        self.calls+=1;raise AssertionError('Imported evidence must never call ASR')

def test_import_job_is_typed_readonly_audit_and_cannot_be_queued_or_bill_a_provider():
    value=VariantEvidenceImportInput(audio_id='aud_'+'a'*24,receipt_id='vfr_'+'b'*32,source_sha256='c'*64,input_sha256='d'*64,actor_ref='fixture-editor')
    with pytest.raises(ValidationError,match='IMPORT_JOB_STATE_INVALID'):
        JobRecord.new(job_id='job_fixture',request=value)
    with pytest.raises(ValidationError):VariantEvidenceImportInput.model_validate({**value.model_dump(),'provider_calls':False})

@pytest.mark.asyncio
async def test_actual_audio_getter_word_review_and_source_http_range_use_child_namespace_without_asr(env):
    families,family,repo,service,analysis=await uploaded(env,audio=True,reviewed_audio=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id']
    async with env.factory() as session:
        parent=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==env.project.project_id))
        imported=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==child))
    provider=NoASR();storage=RecordingStorage(env.storage)
    audio=UploadedAudioService(session_factory=env.factory,platform=env.platform,object_storage=storage,
        queue=env.queue,provider=provider,staging_root=env.tmp/'derivative-audio-stage')
    first=await audio.repository.get(child,imported.audio_id)
    master_before=(await UploadedAudioRepository(env.factory).get(env.project.project_id,parent.audio_id)).model_dump(mode='json')
    assert first.job['request']['kind']=='variant_evidence_import' and first.current.version==2 and first.human_review_required
    assert first.job['request']['provider_calls']==0 and first.publishing_enabled is False
    await audio.process(first.job['job_id'])  # Awaiting-review import is outside ASR worker dispatch.
    segment=first.current.segments[0]
    edited=await audio.edit_words(child,imported.audio_id,AudioWordEdit(source_sha256=first.source_sha256,edit={
        'expected_version':2,'expected_transcript_id':first.current.transcript_id,'expected_timeline_version':1,'acknowledged':True,
        'segments':[dict(segment_id=segment.segment_id,start_seconds=segment.start_seconds,end_seconds=segment.end_seconds,
            words=[dict(word_id=w.word_id,text=('Lời' if i==0 else w.text),start_seconds=w.start_seconds,end_seconds=w.end_seconds) for i,w in enumerate(segment.words)])]}),'fixture-editor')
    assert edited.current.version==3 and edited.timeline_version==2
    original=await UploadedAudioRepository(env.factory).get(env.project.project_id,parent.audio_id)
    assert original.current.version==2 and original.model_dump(mode='json')==master_before
    app=FastAPI();app.include_router(router,dependencies=[Depends(authorize_human_request)]);app.state.uploaded_audio_service=audio
    install_test_human_auth(app,platform_repository=env.platform,platform_role=None,workspace_roles={env.workspace.workspace_id:'viewer'})
    asset=await env.assets.get_asset(imported.asset_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-fixture',headers=TEST_HUMAN_HEADERS) as client:
        read=await client.get(f'/api/v1/projects/{child}/audio-transcriptions/{imported.audio_id}')
        assert read.status_code==200 and read.json()['job']['request']['kind']=='variant_evidence_import'
        source=await client.get(f'/api/v1/projects/{child}/audio-transcriptions/{imported.audio_id}/source',headers={'Range':'bytes=0-31'})
        assert source.status_code==206 and source.content==env.storage._path(asset.object_key).read_bytes()[:32]
        assert source.headers['cache-control']=='no-store' and source.headers['content-range']==f'bytes 0-31/{asset.size_bytes}'
        before=len(storage.calls)
        foreign=await client.get(f'/api/v1/projects/{child}/audio-transcriptions/{parent.audio_id}/source')
        assert foreign.status_code==404 and len(storage.calls)==before
        segment=edited.current.segments[0]
        payload=AudioWordEdit(source_sha256=edited.source_sha256,edit={'expected_version':3,
            'expected_transcript_id':edited.current.transcript_id,'expected_timeline_version':2,'acknowledged':True,
            'segments':[dict(segment_id=segment.segment_id,start_seconds=segment.start_seconds,end_seconds=segment.end_seconds,
                words=[dict(word_id=w.word_id,text=w.text,start_seconds=w.start_seconds,end_seconds=w.end_seconds) for w in segment.words])]})
        before=len(storage.calls)
        denied=await client.post(f'/api/v1/projects/{child}/audio-transcriptions/{imported.audio_id}/transcript-words',json=payload.model_dump(mode='json'))
        assert denied.status_code==403 and len(storage.calls)==before and provider.calls==0
    assert provider.calls==0 and len(env.queue.values)==0
    assert not list(audio.staging_root.iterdir())
    assert all(c['expected_prefix']==f'workspaces/{env.workspace.workspace_id}/projects/{child}/' for c in storage.calls)
    assert (await families.get(env.workspace.workspace_id,env.project.project_id,family.family_id)).source_current
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProviderUsageORM))==0

@pytest.mark.asyncio
async def test_video_staging_and_actual_queued_review_asset_admission_bind_exact_child_scope(env):
    families,family,repo,service,analysis=await uploaded(env)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id'];asset=await env.assets.get_asset(next(iter(result.result['asset_map'].values())))
    storage=RecordingStorage(env.storage)
    async with staged_trusted_video(env.assets,storage,child,asset.asset_id,env.tmp/'derivative-video-stage',1024*1024) as (path,snapshot):
        assert path.read_bytes()==env.storage._path(asset.object_key).read_bytes()
        assert snapshot['upload_id'] is None and snapshot['derivative_custody']['new_scan_claimed'] is False
        assert snapshot['derivative_custody']['receipt_id']==result.receipt_id
    assert_frozen(storage.calls[-1],asset,1024*1024)
    package=await env.package.create_or_refresh(child,ProductionPackageCreateRequest(expected_timeline_version=1,actor_ref='fixture-editor'))
    assert package.approval is None
    queued=await env.package.enqueue_review(child,RenderCreateRequest(expected_timeline_version=1,
        expected_subtitle_version=package.subtitle.version,expected_audio_version=package.audio_mix.version,
        profile=family.members[0].profile.review_profile,actor_ref='fixture-editor'))
    assert queued.status=='queued' and queued.render_kind=='review'
    processor=ProductionRenderProcessor.__new__(ProductionRenderProcessor)
    processor.repository=env.production;processor.asset_repository=env.assets;processor.object_storage=storage
    destination=env.tmp/'admitted-child-review-footage.mp4'
    await processor._download_render_asset(queued,asset,destination)
    assert destination.read_bytes()==env.storage._path(asset.object_key).read_bytes()
    assert storage.calls[-1]['expected_prefix']==f'workspaces/{env.workspace.workspace_id}/projects/{child}/'
    assert (await env.timeline.get_timeline(child)).approval_status=='draft'
    assert len(env.queue.values)==1  # Explicit review request only; no worker is run.

@pytest.mark.asyncio
async def test_source_job_mutation_during_copy_fails_closed_and_records_unknown_without_replay(env):
    from test_sql_variant_storyboard_derivation import PausedCopier
    from app.sql_variant_derivation_service import SqlStoryboardDerivationService
    families,family,repo,service,analysis=await uploaded(env,audio=True)
    paused=PausedCopier(service.copier);service=SqlStoryboardDerivationService(repo,paused)
    running=asyncio.create_task(service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor'))
    await asyncio.wait_for(paused.entered.wait(),10)
    async with env.factory() as session,session.begin():
        parent=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==env.project.project_id))
        job=await session.get(JobORM,parent.job_id);job.progress=99
    paused.release.set()
    with pytest.raises(SqlVariantError,match='MASTER_BINDING_CHANGED'):await running
    async with env.factory() as session:
        receipt=await session.scalar(select(SqlVariantArtifactReceiptORM).where(SqlVariantArtifactReceiptORM.kind=='uploaded_evidence_derivation'))
        assert receipt.state=='unknown' and receipt.error_code=='SQL_VARIANT_MASTER_BINDING_CHANGED'
        assert await session.get(VideoProjectORM,family.members[0].planned_project_id) is None
    replay,replayed=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    assert replayed and replay.state=='unknown' and paused.calls==1

@pytest.mark.asyncio
async def test_actual_async_video_relation_is_archived_exactly_and_never_aliased_into_child(env):
    from app.auto_edit_job_db import AutoEditJobORM
    from app.sql_variant_models import digest
    from app.sql_variant_repository import record_value
    families,family,repo,service,analysis=await uploaded(env,async_video=True)
    async with env.factory() as session:
        relation=await session.scalar(select(AutoEditJobORM).where(AutoEditJobORM.analysis_id==analysis))
        original=record_value(relation);job=record_value(await session.get(JobORM,relation.job_id))
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    async with env.factory() as session:
        receipt=await session.get(SqlVariantArtifactReceiptORM,result.receipt_id)
        assert receipt.input_json['source_job_relations']==[original]
        assert receipt.input_json['source_jobs']=={original['job_id']:job}
        assert result.result['original_job_relations_sha256']==digest([original])
        assert await session.scalar(select(func.count()).select_from(AutoEditJobORM))==1
        assert await session.scalar(select(AutoEditJobORM).where(AutoEditJobORM.project_id==result.result['child_project_id'])) is None
        assert await session.scalar(select(func.count()).select_from(JobORM))==1
        assert record_value(await session.get(AutoEditJobORM,original['relation_id']))==original

@pytest.mark.asyncio
async def test_derivative_video_metadata_version_drift_after_bounded_download_is_rejected(env):
    families,family,repo,service,analysis=await uploaded(env)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id'];new=next(iter(result.result['asset_map'].values()))
    async def mutate(_):
        async with env.factory() as session,session.begin():
            asset=await session.get(AssetORM,new);asset.version+=1
    storage=RecordingStorage(env.storage,after=mutate)
    with pytest.raises(ValueError,match='CUSTODY_CHANGED'):
        async with staged_trusted_video(env.assets,storage,child,new,env.tmp/'drift-source-stage',1024*1024):
            raise AssertionError('Changed source metadata must not enter an edit/model consumer')
    assert len(storage.calls)==1 and not list((env.tmp/'drift-source-stage').iterdir())

@pytest.mark.asyncio
async def test_real_flac_ingest_import_and_staging_preserves_pcm_source_metadata_without_asr(env):
    families,family,repo,service,analysis=await uploaded(env,audio=True,flac=True)
    result,_=await service.derive(env.workspace.workspace_id,env.project.project_id,family.family_id,request(family),actor_ref='fixture-editor')
    child=result.result['child_project_id']
    async with env.factory() as session:
        audio=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==child))
        original=await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id==env.project.project_id))
        assert audio.media_metadata_json==original.media_metadata_json and audio.media_metadata_json['audio_codec']=='flac'
    provider=NoASR();storage=RecordingStorage(env.storage)
    service=UploadedAudioService(session_factory=env.factory,platform=env.platform,object_storage=storage,
        queue=env.queue,provider=provider,staging_root=env.tmp/'derivative-flac-stage')
    asset=await env.assets.get_asset(audio.asset_id)
    owner,path,mime,sha=await service.source_file(child,audio.audio_id)
    try:
        assert path.suffix=='.flac' and path.read_bytes()[:4]==b'fLaC' and mime=='audio/flac'
        assert sha==hashlib.sha256(path.read_bytes()).hexdigest()==asset.checksum_sha256
    finally:owner.cleanup()
    assert provider.calls==0 and not env.queue.values and len(storage.calls)==1
    assert storage.calls[0]['expected_prefix']==f'workspaces/{env.workspace.workspace_id}/projects/{child}/'
    assert not list(service.staging_root.iterdir())
