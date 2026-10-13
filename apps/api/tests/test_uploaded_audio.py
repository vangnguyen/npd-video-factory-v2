"""Owned WAV, SQLite and explicit ASR mocks; no provider/Owner acceptance."""
import asyncio
import hashlib
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import wave
from decimal import Decimal
from datetime import timedelta
import pytest
import sqlalchemy as sa
from sqlalchemy import select
from alembic.migration import MigrationContext
from alembic.operations import Operations
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.auto_edit_models import MediaMetadata, UploadInitRequest, UploadCompleteRequest
from app.auto_edit_providers import ProviderTranscript, ProviderSegment, ProviderWord, ContractOnlyTranscriptionProvider
from app.db import Base, JobORM, JobEventORM, AssetORM
from app.db import create_engine, create_session_factory, utc_now
from app.uploaded_audio_models import AudioTranscriptionCreate, AudioTextEdit, AudioWordEdit, AudioRestore
from app.uploaded_audio_db import UploadedAudioORM, UploadedAudioVersionORM
from app.uploaded_audio_repository import AudioConflict, digest
from app.uploaded_audio_service import UploadedAudioService
from app.uploaded_audio_runtime import provider_from_settings
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_auto_edit_analysis import setup_services, bytes_stream


class Queue:
    def __init__(self): self.items=[]
    async def rpush(self,key,value): self.items.append((key,value))


class WaveProbe:
    async def probe(self,path,*,detected_content_type,media_kind):
        with wave.open(str(path),'rb') as audio:
            return MediaMetadata(media_kind=media_kind,detected_content_type=detected_content_type,
                format_name='wav',duration_seconds=audio.getnframes()/audio.getframerate(),audio_codec='pcm_s16le',
                audio_channels=audio.getnchannels(),audio_sample_rate=audio.getframerate())


class MockASR:
    key='fixture-transcription';model='explicit-owned-audio-mock';external_call=False;paid=False
    credential_alias=None;estimated_cost_vnd=Decimal(0)
    def __init__(self): self.calls=0;self.started=asyncio.Event();self.release=None
    async def transcribe(self,path,*,metadata,checksum_sha256,execution_trace=None):
        assert path.suffix=='.wav'  # Declared .bin extension cannot control dispatch.
        assert metadata.media_kind=='audio' and metadata.width is None and metadata.video_codec is None
        assert hashlib.sha256(path.read_bytes()).hexdigest()==checksum_sha256
        self.calls+=1;self.started.set()
        if self.release is not None: await self.release.wait()
        return ProviderTranscript(language='vi',confidence=None,segments=(ProviderSegment(
            start_seconds=.1,end_seconds=.9,text='Xin chào.',speaker=None,confidence=None,
            words=(ProviderWord(.1,.4,'Xin',.9),ProviderWord(.4,.9,'chào.',.8))),),
            provenance={'fixture':True,'source_checksum':checksum_sha256,'original_evidence':True,
                'word_timing_rewritten':False},actual_cost_vnd=Decimal(0))


def wav_bytes():
    buf=io.BytesIO()
    with wave.open(buf,'wb') as sound:
        sound.setnchannels(1);sound.setsampwidth(2);sound.setframerate(16000)
        sound.writeframes(b'\x00\x00'*32000)
    return buf.getvalue()


async def stack(tmp_path):
    tmp_path.mkdir(parents=True,exist_ok=True)
    engine,sessions,platform,assets,uploads,_,project,version=await setup_services(tmp_path)
    uploads.media_probe=WaveProbe();raw=wav_bytes();sha=hashlib.sha256(raw).hexdigest()
    upload=await uploads.initialize(UploadInitRequest(project_id=project.project_id,
        project_version_id=version.project_version_id,filename='owned-audio.bin',media_kind='audio',
        content_type='audio/wav',size_bytes=len(raw),checksum_sha256=sha,part_size_bytes=65536))
    for part in range(1,upload.total_parts+1):
        data=raw[(part-1)*upload.part_size_bytes:part*upload.part_size_bytes]
        await uploads.store_part(upload.upload_id,part,bytes_stream(data),expected_part_sha256=hashlib.sha256(data).hexdigest())
    completed=await uploads.complete(upload.upload_id,UploadCompleteRequest(checksum_sha256=sha))
    queue=Queue();provider=MockASR()
    service=UploadedAudioService(session_factory=sessions,platform=platform,object_storage=uploads.object_storage,
        queue=queue,provider=provider,staging_root=tmp_path/'audio-staging')
    request=AudioTranscriptionCreate(asset_id=completed.asset_id,source_sha256=sha,idempotency_key='owned-audio-request-01')
    return SimpleNamespace(engine=engine,sessions=sessions,platform=platform,assets=assets,project=project,
        service=service,queue=queue,provider=provider,request=request,raw=raw,version=version)


async def ready(env):
    row=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
    await env.service.process(row.job['job_id'])
    result=await env.service.repository.get(env.project.project_id,row.audio_id)
    assert result.job['status']=='awaiting_review',result.job.get('error')
    return result


def text_request(row,text='Chữ do người dùng sửa.'):
    return AudioTextEdit(source_sha256=row.source_sha256,expected_transcript_id=row.current.transcript_id,
        edit={'expected_version':row.current.version,'expected_timeline_version':row.timeline_version,
            'segments':[{'segment_id':row.current.segments[0].segment_id,'text':text}]})


def word_request(row):
    s=row.current.segments[0]
    return AudioWordEdit(source_sha256=row.source_sha256,edit={'expected_version':row.current.version,
        'expected_transcript_id':row.current.transcript_id,'expected_timeline_version':row.timeline_version,
        'acknowledged':True,'segments':[{'segment_id':s.segment_id,'start_seconds':s.start_seconds,
            'end_seconds':s.end_seconds,'words':[{'word_id':w.word_id,'text':w.text,
                'start_seconds':w.start_seconds,'end_seconds':w.end_seconds} for w in s.words] or [
                    {'text':s.text,'start_seconds':s.start_seconds,'end_seconds':s.end_seconds}]}]})


async def rows(env):
    async with env.sessions() as session:
        return (await session.scalars(select(UploadedAudioVersionORM))).all()


@pytest.mark.asyncio
async def test_async_job_normalizes_once_keeps_evidence_cost_and_reopens(tmp_path):
    env=await stack(tmp_path)
    try:
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        assert queued.current is None and queued.job['status']=='queued' and env.provider.calls==0
        same=await env.service.create(env.project.project_id,env.request,'usr:other-editor')
        assert same.audio_id==queued.audio_id
        await asyncio.gather(env.service.process(queued.job['job_id']),env.service.process(queued.job['job_id']))
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert env.provider.calls==1 and result.original==result.current and result.current.version==1
        assert result.original.is_original_evidence and result.current.confidence is None
        assert result.current.analysis_id==result.audio_id and result.job['status']=='awaiting_review'
        assert len(await rows(env))==1
        assert (await env.platform.list_cost_records(env.project.project_id))[0].actual_cost==Decimal(0)
        new=UploadedAudioService(session_factory=env.sessions,platform=env.platform,object_storage=env.service.object_storage,
            queue=env.queue,provider=env.provider,staging_root=env.service.staging_root)
        assert await new.repository.get(env.project.project_id,result.audio_id)==result
        async with env.sessions() as session:
            assert await session.scalar(select(sa.func.count()).select_from(Base.metadata.tables['auto_edit_analyses']))==0
            assert await session.scalar(select(sa.func.count()).select_from(Base.metadata.tables['transcripts']))==0
            parent=await session.get(UploadedAudioORM,result.audio_id)
            assert parent.original_evidence_sha256==digest(parent.original_evidence_json)
        assert not list(env.service.staging_root.iterdir())
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_text_word_edits_and_explicit_restore_append_without_provider_or_original_mutation(tmp_path):
    env=await stack(tmp_path)
    try:
        first=await ready(env);original=first.original.model_dump(mode='json')
        second=await env.service.edit_text(env.project.project_id,first.audio_id,text_request(first),'usr:editor')
        assert second.current.version==2 and second.current.segments[0].words==[]
        assert second.current.segments[0].confidence is None and second.original.model_dump(mode='json')==original
        # Add explicit word timing after a text-only revision; no automatic aligner.
        payload=word_request(second);payload.edit.segments[0].words=[]
        from app.transcript_word_review import Word
        payload.edit.segments[0].words=[Word(text='Xin',start_seconds=.1,end_seconds=.4),Word(text='chào.',start_seconds=.4,end_seconds=.9)]
        third=await env.service.edit_words(env.project.project_id,first.audio_id,payload,'usr:editor')
        assert third.current.version==3 and all(w.confidence is None for w in third.current.segments[0].words)
        restore=AudioRestore(source_sha256=third.source_sha256,expected_version=3,expected_transcript_id=third.current.transcript_id,
            expected_timeline_version=None,target_transcript_id=first.original.transcript_id,acknowledged=True)
        fourth=await env.service.restore(env.project.project_id,first.audio_id,restore,'usr:editor')
        assert fourth.current.version==4 and not fourth.current.is_original_evidence
        assert [w.confidence for w in fourth.current.segments[0].words]==[.9,.8]
        assert fourth.current.provenance['restored_from_transcript_id']==first.original.transcript_id
        assert fourth.original.model_dump(mode='json')==original and env.provider.calls==1
        assert len(fourth.versions)==4
        owner,path,_,sha=await env.service.source_file(env.project.project_id,first.audio_id)
        assert path.read_bytes()==env.raw and hashlib.sha256(path.read_bytes()).hexdigest()==sha
        owner.cleanup()
    finally: await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('case',['sha','version','transcript','segment','word','restore','timeline','actor'])
async def test_stale_foreign_edits_rollback_everything(tmp_path,case):
    env=await stack(tmp_path)
    try:
        first=await ready(env);payload=word_request(first);who='usr:editor'
        if case=='sha':payload.source_sha256='f'*64
        if case=='version':payload.edit.expected_version=2
        if case=='transcript':payload.edit.expected_transcript_id='trn_'+'f'*24
        if case=='segment':payload.edit.segments[0].segment_id='seg_'+'f'*24
        if case=='word':payload.edit.segments[0].words[0].word_id='wrd_'+'f'*24
        if case=='timeline':payload.edit.expected_timeline_version=1
        if case=='actor':who='usr:invalid\nactor'
        with pytest.raises(AudioConflict):
            if case=='restore':
                await env.service.restore(env.project.project_id,first.audio_id,AudioRestore(
                    source_sha256=first.source_sha256,expected_version=1,expected_transcript_id=first.current.transcript_id,
                    target_transcript_id='trn_'+'f'*24,acknowledged=True),who)
            else: await env.service.edit_words(env.project.project_id,first.audio_id,payload,who)
        assert await env.service.repository.get(env.project.project_id,first.audio_id)==first
        assert len(await rows(env))==1 and env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_same_version_race_and_insert_failure_have_atomic_rollback(tmp_path):
    env=await stack(tmp_path)
    try:
        first=await ready(env)
        with patch.object(env.service.repository,'version_row',side_effect=RuntimeError('owned insertion failure')):
            with pytest.raises(RuntimeError,match='owned insertion failure'):
                await env.service.edit_words(env.project.project_id,first.audio_id,word_request(first),'usr:editor')
        assert await env.service.repository.get(env.project.project_id,first.audio_id)==first
        outcomes=await asyncio.gather(*[env.service.edit_words(env.project.project_id,first.audio_id,
            word_request(first),'usr:editor') for _ in range(2)],return_exceptions=True)
        assert sum(isinstance(value,AudioConflict) for value in outcomes)==1,outcomes
        assert len(await rows(env))==2
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_cancel_during_provider_call_wins_and_never_resurrects_transcript(tmp_path):
    env=await stack(tmp_path)
    try:
        env.provider.release=asyncio.Event()
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        task=asyncio.create_task(env.service.process(queued.job['job_id']))
        await asyncio.wait_for(env.provider.started.wait(),5)
        await env.service.cancel(env.project.project_id,queued.audio_id,'usr:editor')
        env.provider.release.set();await task
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert result.job['status']=='cancelled' and result.current is None and not await rows(env)
        await env.service.process(queued.job['job_id']);assert env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_optional_immutable_provider_binding_drift_prevents_dispatch_and_preserves_legacy(tmp_path):
    from app.uploaded_audio_service import provider_binding
    env=await stack(tmp_path)
    try:
        legacy=provider_binding(env.provider)
        assert 'immutable_binding' not in legacy
        env.provider.immutable_binding={'schema_version':'owned-runtime-proof.v1','sha256':'a'*64}
        bound=provider_binding(env.provider)
        assert {k:v for k,v in bound.items() if k!='immutable_binding'}==legacy
        bound['immutable_binding']['sha256']='f'*64
        assert env.provider.immutable_binding['sha256']=='a'*64
        row=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
        env.provider.immutable_binding={'schema_version':'owned-runtime-proof.v1','sha256':'b'*64}
        await env.service.process(row.job['job_id'])
        result=await env.service.repository.get(env.project.project_id,row.audio_id)
        assert result.current is None and result.job['status']=='failed' and env.provider.calls==0
        env.provider.immutable_binding={'bad':float('nan')}
        with pytest.raises(AudioConflict,match='BINDING_INVALID'):provider_binding(env.provider)
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_opted_in_provider_observes_durable_cancel_without_late_evidence(tmp_path):
    env=await stack(tmp_path)
    class Cancellable(MockASR):
        supports_durable_cancellation=True
        async def transcribe(self,path,*,metadata,checksum_sha256,execution_trace=None,is_cancelled=None):
            assert is_cancelled is not None
            self.calls+=1;self.started.set()
            await self.release.wait()
            assert await is_cancelled()
            raise RuntimeError('owned durable cancellation; no provider result')
    try:
        provider=Cancellable();provider.release=asyncio.Event();env.service.provider=provider
        row=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
        task=asyncio.create_task(env.service.process(row.job['job_id']))
        await asyncio.wait_for(provider.started.wait(),5)
        await env.service.cancel(env.project.project_id,row.audio_id,'usr:fixture-editor')
        provider.release.set();await task
        saved=await env.service.repository.get(env.project.project_id,row.audio_id)
        assert saved.current is None and saved.job['status']=='cancelled' and provider.calls==1
        assert not await rows(env)
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_running_crash_handoff_requires_attention_and_queued_is_recoverable(tmp_path):
    env=await stack(tmp_path)
    try:
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        assert await env.service.recover()==1
        async with env.sessions() as session:
            job=await session.get(JobORM,queued.job['job_id']);job.status='running';job.stage='analyzing_audio'
            await session.commit()
        # New worker handoff cannot replay an ambiguous claimed operation.
        assert await env.service.recover()==0
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert result.job['status']=='needs_attention' and result.job['error']['code']=='AUDIO_PROVIDER_OUTCOME_UNKNOWN'
        assert result.job['error']['retryable'] is False and result.current is None
        await env.service.process(queued.job['job_id']);assert env.provider.calls==0
        assert len(await rows(env))==0
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_unconfigured_default_and_provider_drift_do_not_create_mock_transcript(tmp_path):
    env=await stack(tmp_path)
    try:
        from app.auto_edit_providers import ProviderNotConfigured
        from app.config import Settings
        assert isinstance(provider_from_settings(Settings(_env_file=None)),ContractOnlyTranscriptionProvider)
        env.service.provider=ContractOnlyTranscriptionProvider()
        with pytest.raises(ProviderNotConfigured):await env.service.create(env.project.project_id,env.request,'usr:editor')
        assert not await env.service.repository.list(env.project.project_id)
        env.service.provider=env.provider
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        env.service.provider=ContractOnlyTranscriptionProvider()
        await env.service.process(queued.job['job_id'])
        row=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert row.job['status']=='failed' and row.current is None and env.provider.calls==0
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_physical_source_tamper_and_original_history_tamper_fail_closed(tmp_path):
    env=await stack(tmp_path)
    try:
        row=await ready(env)
        asset=await env.assets.get_asset(row.asset_id)
        file=env.service.object_storage._path(asset.object_key)
        file.write_bytes(b'tampered fixture')
        with pytest.raises(AudioConflict,match='SOURCE_CHANGED'):
            await env.service.edit_text(env.project.project_id,row.audio_id,text_request(row),'usr:editor')
        assert len(await rows(env))==1
        file.write_bytes(env.raw)
        async with env.sessions() as session:
            version=await session.get(UploadedAudioVersionORM,row.original.transcript_id)
            version.transcript_json={**version.transcript_json,'language':'en'}
            version.transcript_sha256=digest(version.transcript_json)
            await session.commit()
        with pytest.raises(AudioConflict,match='ORIGINAL_EVIDENCE_CHANGED'):
            await env.service.repository.get(env.project.project_id,row.audio_id)
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_bound_audio_captions_require_explicit_review_without_changing_timeline_or_approval(tmp_path):
    from app.timeline_db import TimelineORM
    env=await stack(tmp_path/'audio')
    try:
        row=await ready(env)
        # An independent storyboard timeline remains a video/content timeline.
        from app.timeline_models import TimelineSnapshot, TimelineTrack, TimelineClip
        from app.timeline_repository import TimelineRepository
        snapshot=TimelineSnapshot(width=540,height=960,duration_seconds=2,tracks=[TimelineTrack(
            track_id='trk_audio_caption',type='text',kind='subtitles',label='Bound audio words',order=0,locked=True,
            clips=[TimelineClip(clip_id='clip_audio_caption',kind='subtitle',label='Xin chào.',source_start=.1,
                source_end=.9,timeline_start=.1,duration=.8,metadata={'transcript_id':row.current.transcript_id,
                    'segment_id':row.current.segments[0].segment_id,'audio_transcription_id':row.audio_id})])])
        timeline,_=await TimelineRepository(env.sessions).create_timeline(project_id=env.project.project_id,
            source_analysis_id=None,source_media_plan_id=None,source_content_version_id=env.version.project_version_id,
            snapshot=snapshot,actor_ref='usr:fixture')
        async with env.sessions() as session:
            saved=await session.get(TimelineORM,timeline.timeline_id)
            saved.approval_status='approved';saved.approved_timeline_version=1
            await session.commit()
        payload=word_request(row);payload.edit.expected_timeline_version=1
        with pytest.raises(AudioConflict,match='CANONICAL_CAPTION_REVIEW_REQUIRED'):
            await env.service.edit_words(env.project.project_id,row.audio_id,payload,'usr:editor')
        assert len(await rows(env))==1
        after=await TimelineRepository(env.sessions).get_timeline(env.project.project_id)
        assert after.current_version==1 and after.approval_status=='approved' and after.snapshot==snapshot
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_http_roles_foreign_scope_actor_and_source_route(tmp_path):
    env=await stack(tmp_path)
    try:
        row=await ready(env);app.state.uploaded_audio_service=env.service
        install_test_human_auth(app,platform_repository=env.platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        endpoint=f'/api/v1/projects/{env.project.project_id}/audio-transcriptions/{row.audio_id}'
        async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as client:
            assert (await client.get(endpoint)).status_code==401
            assert (await client.get(endpoint,headers=TEST_HUMAN_HEADERS)).status_code==200
            assert (await client.post(endpoint+'/transcript',json=text_request(row).model_dump(mode='json'),headers=TEST_HUMAN_HEADERS)).status_code==403
            assert (await client.get(endpoint.replace(env.project.project_id,'prj_foreign_missing'),headers=TEST_HUMAN_HEADERS)).status_code==404
            install_test_human_auth(app,platform_repository=env.platform,platform_role='editor',workspace_roles={'*':'editor'})
            changed=await client.post(endpoint+'/transcript',json=text_request(row).model_dump(mode='json'),headers=TEST_HUMAN_HEADERS)
            assert changed.status_code==200 and changed.json()['current']['provenance']['actor_ref']=='usr:test-owner'
            assert changed.headers['cache-control']=='no-store'
            again=await client.post(endpoint+'/transcript',json=text_request(row).model_dump(mode='json'),headers=TEST_HUMAN_HEADERS)
            assert again.status_code==409
            # Playback uses the shared physical-byte helper, once provided by root.
            response=await client.get(endpoint+'/source',headers={**TEST_HUMAN_HEADERS,'Range':'bytes=0-15'})
            assert response.status_code==206 and response.content==env.raw[:16]
            assert response.headers['cache-control']=='no-store'
    finally: await env.engine.dispose()


def test_additive_migration_preserves_all_prior_rows_schema_and_video_foreign_keys(tmp_path):
    engine=sa.create_engine('sqlite:///'+(tmp_path/'owned-audio-migration.db').as_posix())
    names={'uploaded_audio_transcriptions','uploaded_audio_transcript_versions'}
    old=[t for t in Base.metadata.sorted_tables if t.name not in names]
    Base.metadata.create_all(engine,tables=old)
    path=Path(__file__).parents[1]/'migrations/versions/0027_north_star_uploaded_audio.py'
    spec=importlib.util.spec_from_file_location('owned_audio_0027',path);migration=importlib.util.module_from_spec(spec);spec.loader.exec_module(migration)
    with engine.begin() as con:
        con.exec_driver_sql('PRAGMA foreign_keys=ON')
        con.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_audio_migration_fixture',slug='audio-migration',name='OWNED FIXTURE',owner_ref='fixture'))
        rows={t.name:con.exec_driver_sql('SELECT * FROM "'+t.name+'"').fetchall() for t in old}
        schema={t.name:con.exec_driver_sql('PRAGMA table_info("'+t.name+'")').fetchall() for t in old}
        fks={t.name:con.exec_driver_sql('PRAGMA foreign_key_list("'+t.name+'")').fetchall() for t in old}
        with Operations.context(MigrationContext.configure(con)):migration.upgrade()
        for table in old:
            assert con.exec_driver_sql('SELECT * FROM "'+table.name+'"').fetchall()==rows[table.name]
            assert con.exec_driver_sql('PRAGMA table_info("'+table.name+'")').fetchall()==schema[table.name]
            assert con.exec_driver_sql('PRAGMA foreign_key_list("'+table.name+'")').fetchall()==fks[table.name]
        for name in names:
            assert {c['name'] for c in sa.inspect(con).get_columns(name)}==set(Base.metadata.tables[name].columns.keys())
        assert not con.exec_driver_sql('PRAGMA foreign_key_check').fetchall()
        with Operations.context(MigrationContext.configure(con)):
            with pytest.raises(RuntimeError,match='explicit Owner approval'):migration.downgrade()
    engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('expired',[False,True])
async def test_second_worker_database_instance_skips_live_lease_and_revokes_expired_claim(tmp_path,expired):
    env=await stack(tmp_path)
    other_engine=create_engine(str(env.engine.url))
    async with other_engine.begin() as con:
        await con.execute(sa.text('PRAGMA foreign_keys=ON'))
    other=UploadedAudioService(session_factory=create_session_factory(other_engine),platform=env.platform,
        object_storage=env.service.object_storage,queue=Queue(),provider=env.provider,staging_root=tmp_path/'second-worker')
    try:
        env.provider.release=asyncio.Event()
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        task=asyncio.create_task(env.service.process(queued.job['job_id']))
        await asyncio.wait_for(env.provider.started.wait(),5)
        if expired:
            async with env.sessions() as session:
                parent=await session.get(UploadedAudioORM,queued.audio_id)
                parent.lease_expires_at=utc_now()-timedelta(seconds=1)
                await session.commit()
        assert await other.recover(include_queued=False)==0
        observed=await other.repository.get(env.project.project_id,queued.audio_id)
        assert observed.job['status']==('needs_attention' if expired else 'running')
        env.provider.release.set();await task
        final=await other.repository.get(env.project.project_id,queued.audio_id)
        assert final.job['status']==('needs_attention' if expired else 'awaiting_review')
        assert (final.current is None)==expired
        await other.process(queued.job['job_id'])
        assert env.provider.calls==1
    finally:
        await other_engine.dispose();await env.engine.dispose()


@pytest.mark.asyncio
async def test_worker_completion_failure_rolls_back_version_and_terminal_event_but_retains_returned_evidence(tmp_path):
    env=await stack(tmp_path)
    try:
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        with patch.object(env.service.repository,'version_row',side_effect=RuntimeError('owned worker insertion failure')):
            await env.service.process(queued.job['job_id'])
        final=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert final.job['status']=='failed' and final.current is None and not await rows(env)
        async with env.sessions() as session:
            parent=await session.get(UploadedAudioORM,queued.audio_id)
            assert parent.current_version==0 and parent.original_evidence_json is not None
            assert parent.original_evidence_sha256==digest(parent.original_evidence_json)
            assert parent.claim_id is None
            events=(await session.scalars(select(JobEventORM).where(JobEventORM.job_id==queued.job['job_id']))).all()
            assert 'uploaded_audio.transcript_ready' not in {e.event_type for e in events}
            assert 'uploaded_audio.failed' in {e.event_type for e in events}
        await env.service.process(queued.job['job_id']);assert env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_transient_mock_provider_has_one_dispatch_even_when_controller_allows_retry(tmp_path):
    env=await stack(tmp_path)
    try:
        from app.provider_safety import ProviderTimeoutError
        async def timeout(*args,**kwargs):
            env.provider.calls+=1
            raise ProviderTimeoutError()
        env.provider.transcribe=timeout
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        await env.service.process(queued.job['job_id'])
        final=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert final.job['status']=='needs_attention' and final.current is None
        assert final.job['error']['code']=='AUDIO_PROVIDER_OUTCOME_UNKNOWN' and env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_physical_source_changes_during_dispatch_prevent_completion_and_keep_cost(tmp_path):
    env=await stack(tmp_path)
    try:
        env.provider.release=asyncio.Event()
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        task=asyncio.create_task(env.service.process(queued.job['job_id']))
        await asyncio.wait_for(env.provider.started.wait(),5)
        asset=await env.assets.get_asset(env.request.asset_id)
        path=env.service.object_storage._path(asset.object_key)
        path.write_bytes(b'changed owned fixture during ASR')
        env.provider.release.set();await task
        final=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert final.job['status']=='failed' and final.current is None and not await rows(env)
        assert final.job['error']['code']=='AUDIO_SOURCE_CHANGED'
        assert len(await env.platform.list_cost_records(env.project.project_id))==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_actual_worker_queue_drives_audio_job_and_duplicate_delivery_is_safe(tmp_path,monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]/'services/worker'))
    from npd_worker.main import run_uploaded_audio_queue
    env=await stack(tmp_path)
    try:
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        class Redis:
            calls=0
            async def blpop(self,key,timeout):
                self.calls+=1
                if self.calls>2:raise asyncio.CancelledError()
                return key,queued.job['job_id']
        with pytest.raises(asyncio.CancelledError):
            await run_uploaded_audio_queue(Redis(),env.service)
        final=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert final.current.version==1 and final.job['status']=='awaiting_review' and env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_idempotency_conflict_external_block_and_foreign_existing_project(tmp_path):
    from app.platform_models import ProjectCreate, WorkspaceCreate
    env=await stack(tmp_path)
    try:
        row=await env.service.create(env.project.project_id,env.request,'usr:editor')
        changed=env.request.model_copy(update={'provider_operation_key':'unapproved-new-operation'})
        with pytest.raises(AudioConflict,match='IDEMPOTENCY_CONFLICT'):
            await env.service.create(env.project.project_id,changed,'usr:editor')
        workspace=await env.platform.create_workspace(WorkspaceCreate(slug='foreign-audio',name='Foreign fixture',owner_ref='fixture'))
        project=await env.platform.create_project(workspace.workspace_id,ProjectCreate(slug='foreign-audio',name='Foreign fixture'))
        with pytest.raises(KeyError):await env.service.repository.get(project.project_id,row.audio_id)
        with pytest.raises(KeyError):await env.service.create(project.project_id,env.request,'usr:editor')
        await env.service.process(row.job['job_id']);assert env.provider.calls==1
        # Explicit external adapter flags meet the shared fail-closed controller
        # before any injected provider method is called.
        env.provider.external_call=True;env.provider.paid=True
        other=env.request.model_copy(update={'idempotency_key':'owned-external-request-02'})
        blocked=await env.service.create(env.project.project_id,other,'usr:editor')
        await env.service.process(blocked.job['job_id'])
        result=await env.service.repository.get(env.project.project_id,blocked.audio_id)
        assert result.current is None and result.job['error']['code']=='AUDIO_PROVIDER_SAFETY_BLOCKED'
        assert env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_invalid_nonfinite_provider_evidence_fails_durably_without_snapshot_or_replay(tmp_path):
    env=await stack(tmp_path)
    try:
        real_mock=env.provider.transcribe
        async def invalid(*args,**kwargs):
            from dataclasses import replace
            result=await real_mock(*args,**kwargs)
            return replace(result,confidence=float('nan'))
        env.provider.transcribe=invalid
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        await env.service.process(queued.job['job_id'])
        final=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert final.job['status']=='failed' and final.current is None and not await rows(env)
        async with env.sessions() as session:
            parent=await session.get(UploadedAudioORM,queued.audio_id)
            assert parent.current_version==0 and parent.original_evidence_json is None
        assert len(await env.platform.list_cost_records(env.project.project_id))==1
        await env.service.process(queued.job['job_id']);assert env.provider.calls==1
    finally: await env.engine.dispose()


@pytest.mark.asyncio
async def test_registered_mime_tamper_cannot_change_dispatch_or_source_playback(tmp_path):
    env=await stack(tmp_path)
    try:
        queued=await env.service.create(env.project.project_id,env.request,'usr:editor')
        async with env.sessions() as session:
            asset=await session.get(AssetORM,env.request.asset_id)
            asset.content_type='audio/mpeg'
            await session.commit()
        with pytest.raises(AudioConflict,match='METADATA_CHANGED'):
            await env.service.source_file(env.project.project_id,queued.audio_id)
        await env.service.process(queued.job['job_id'])
        async with env.sessions() as session:
            job=await session.get(JobORM,queued.job['job_id'])
            assert job.status=='failed' and job.error_json['code']=='AUDIO_METADATA_CHANGED'
        assert env.provider.calls==0 and not await rows(env)
    finally: await env.engine.dispose()


@pytest.fixture
def sql_local_custody(tmp_path):
    # Independent synthetic binaries/model are never executed or loaded.
    from test_local_uploaded_audio_provider import custody
    root=tmp_path/'synthetic-local-custody';root.mkdir()
    fixture=custody.__wrapped__(root)
    try:yield next(fixture)
    finally:fixture.close()


def rejected_cpu_fixture():
    from test_local_uploaded_audio_provider import ExplicitCpuFixture
    class RejectedCpuFixture(ExplicitCpuFixture):
        async def transcribe(self,*args,**kwargs):
            await super().transcribe(*args,**kwargs)
            raise ValueError('EXPLICIT FIXTURE NORMALIZER REJECTION, ZERO MODEL INFERENCE')
    return RejectedCpuFixture


@pytest.mark.asyncio
@pytest.mark.parametrize('reason',['projection','normalization'])
async def test_local_rejected_result_keeps_request_scoped_raw_evidence_in_sql(tmp_path,sql_local_custody,reason):
    from app import local_uploaded_audio_provider as local
    from test_local_uploaded_audio_provider import fixture_decoder, ExplicitCpuFixture
    env=await stack(tmp_path/'sql')
    try:
        provider=local.LocalUploadedAudioProvider(**sql_local_custody.kwargs)
        env.service.provider=provider
        cpu=ExplicitCpuFixture if reason=='projection' else rejected_cpu_fixture()
        cpu.calls=0;cpu.wait=None;cpu.outside=reason=='projection'
        with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',cpu):
            queued=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
            await env.service.process(queued.job['job_id'])
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert result.job['status']=='failed' and result.current is None and not await rows(env)
        async with env.sessions() as session:
            parent=await session.get(UploadedAudioORM,queued.audio_id)
            evidence=parent.original_evidence_json
            assert parent.original_evidence_sha256==digest(evidence)
            assert parent.current_version==0 and parent.claim_id is None
            assert evidence['source_sha256']==env.request.source_sha256 and evidence['source_size_bytes']==len(env.raw)
            assert evidence['immutable_binding']==parent.configuration_json['provider']['immutable_binding']
        assert evidence['schema_version']=='sql-local-audio-evidence.v1' and evidence['model_result']['fixture']
        assert evidence['model_result_sha256']==digest(evidence['model_result'])
        assert evidence['decoded_audio_clock_sha256']==digest(evidence['decoded_audio_clock'])
        assert evidence['source_projection_validated'] is False and evidence['human_accepted'] is False
        assert evidence['publishing_enabled'] is False
        assert evidence['provider_result_normalized']==(reason=='projection')
        assert evidence['source_checksum_verified_before_inference'] is True
        assert evidence['source_checksum_verified_after_result']==(True if reason=='projection' else None)
        assert evidence['rejection_code']==('LOCAL_AUDIO_PROVIDER_OUTSIDE_DECODED_CLOCK' if reason=='projection' else 'LOCAL_AUDIO_NORMALIZATION_REJECTED')
        provider.raw_result={'unrelated_job_diagnostic':True}
        await env.service.process(queued.job['job_id'])
        async with env.sessions() as session:
            assert (await session.get(UploadedAudioORM,queued.audio_id)).original_evidence_json==evidence
        assert cpu.calls==1
    finally:
        cpu.outside=False
        await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper',['source','size','binding','digest','nonfinite','approval','model_digest'])
async def test_local_exception_mixed_request_or_invalid_evidence_never_persists(tmp_path,sql_local_custody,tamper):
    from app import local_uploaded_audio_provider as local
    from test_local_uploaded_audio_provider import fixture_decoder
    env=await stack(tmp_path/'sql')
    try:
        provider=local.LocalUploadedAudioProvider(**sql_local_custody.kwargs);env.service.provider=provider
        original=provider.transcribe;cpu=rejected_cpu_fixture();cpu.calls=0;cpu.wait=None
        async def mixed(*args,**kwargs):
            try:return await original(*args,**kwargs)
            except local.LocalAudioEvidenceRejected as exc:
                if tamper=='source':exc.evidence['source_sha256']='f'*64
                elif tamper=='size':exc.evidence['source_size_bytes']+=1
                elif tamper=='binding':exc.evidence['immutable_binding']['cpu_threads']=4
                elif tamper=='nonfinite':exc.evidence['model_result']['invalid']=float('nan')
                elif tamper=='approval':exc.evidence['human_accepted']=True
                elif tamper=='model_digest':exc.evidence['model_result_sha256']='f'*64
                if tamper not in {'digest','nonfinite'}:exc.evidence_sha256=digest(exc.evidence)
                if tamper=='digest':exc.evidence_sha256='f'*64
                # Wrong shared diagnostics must never repair this carrier.
                provider.raw_result={'unrelated_shared_result':True}
                raise
        provider.transcribe=mixed
        with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',cpu):
            queued=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
            await env.service.process(queued.job['job_id'])
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert result.job['status']=='failed' and result.current is None and not await rows(env)
        async with env.sessions() as session:
            parent=await session.get(UploadedAudioORM,queued.audio_id)
            assert parent.original_evidence_json is None and parent.original_evidence_sha256 is None
        assert cpu.calls==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('revoke',['cancel','lease'])
async def test_local_rejected_evidence_after_revocation_cannot_commit_late(tmp_path,sql_local_custody,revoke):
    from app import local_uploaded_audio_provider as local
    from test_local_uploaded_audio_provider import fixture_decoder
    env=await stack(tmp_path/'sql');release=asyncio.Event();captured=asyncio.Event()
    try:
        provider=local.LocalUploadedAudioProvider(**sql_local_custody.kwargs);env.service.provider=provider
        original=provider.transcribe;cpu=rejected_cpu_fixture();cpu.calls=0;cpu.wait=None
        async def paused(*args,**kwargs):
            try:return await original(*args,**kwargs)
            except local.LocalAudioEvidenceRejected:
                captured.set();await release.wait();raise
        provider.transcribe=paused
        with patch.object(local,'bounded_process',side_effect=fixture_decoder()),patch.object(local,'LocalCpuTranscriptionProvider',cpu):
            queued=await env.service.create(env.project.project_id,env.request,'usr:fixture-editor')
            work=asyncio.create_task(env.service.process(queued.job['job_id']))
            await asyncio.wait_for(captured.wait(),5)
            if revoke=='cancel':await env.service.cancel(env.project.project_id,queued.audio_id,'usr:fixture-editor')
            else:
                async with env.sessions() as session:
                    parent=await session.get(UploadedAudioORM,queued.audio_id)
                    parent.lease_expires_at=utc_now()-timedelta(seconds=1);await session.commit()
            release.set();await work
        result=await env.service.repository.get(env.project.project_id,queued.audio_id)
        assert result.job['status']==('cancelled' if revoke=='cancel' else 'failed')
        assert result.current is None and not await rows(env)
        async with env.sessions() as session:
            parent=await session.get(UploadedAudioORM,queued.audio_id)
            assert parent.original_evidence_json is None and parent.current_version==0
        assert cpu.calls==1
    finally:
        release.set()
        await env.engine.dispose()
