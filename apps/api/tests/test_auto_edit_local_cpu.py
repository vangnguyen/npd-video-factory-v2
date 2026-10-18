"""Actual isolated SQL upload/analysis with explicit mocked CPU outcomes only."""
import asyncio
import copy
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import select,text,event
from app.auto_edit_db import UploadSessionORM,AutoEditAnalysisORM
from app.auto_edit_models import AutoEditAnalysisRequest,MediaMetadata
from app.auto_edit_providers import DeterministicMediaSignalProvider,FFprobeMediaProbe,FFmpegMediaSignalProvider
from app.auto_edit_repository import AutoEditRepository
from app.auto_edit_service import AutoEditAnalysisService
from app.db import AssetORM
from app.local_asr_runtime import file_sha
from app.platform_models import WorkspaceCreate
from app.local_video_transcription_provider import LocalVideoTranscriptionProvider
from app import local_video_transcription_provider as video
from app.uploaded_audio_repository import digest
from app.bounded_storage_download import StorageDownloadError
from test_auto_edit_analysis import setup_services,upload_fixture,synthetic_mp4
from test_local_uploaded_audio_provider import custody,ExplicitCpuFixture,fixture_decoder,reset_fixture
from test_local_video_transcription_provider import FFMPEG


async def configured_sql(tmp_path,custody,monkeypatch,*,signals=None,language='vi'):
    values=await setup_services(tmp_path)
    engine,sessions,platform,repository,uploads,_,project,version=values
    await platform.seed_providers([{'provider_key':'local-faster-whisper','display_name':'Explicit CPU fixture',
        'capability':'transcription','adapter':'explicit-test-only','routing_mode':'primary','status':'degraded','enabled':True,
        'supports_dry_run':False,'metadata':{'fixture':True,'paid':False,'external_call':False}}])
    monkeypatch.setattr(video,'bounded_process',fixture_decoder())
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',ExplicitCpuFixture)
    provider=LocalVideoTranscriptionProvider(**custody.kwargs,language=language)
    service=AutoEditAnalysisService(repository=repository,platform=platform,object_storage=uploads.object_storage,
        transcription_provider=provider,signal_provider=signals or DeterministicMediaSignalProvider(),staging_root=tmp_path/'local-video-staging')
    completed=await upload_fixture(uploads,project,version,synthetic_mp4())
    return SimpleNamespace(engine=engine,sessions=sessions,platform=platform,repository=repository,uploads=uploads,
        provider=provider,service=service,project=project,version=version,completed=completed,
        request=AutoEditAnalysisRequest(asset_id=completed.asset_id))


async def count(context,name):
    async with context.sessions() as session:return await session.scalar(text('SELECT COUNT(*) FROM '+name))


@pytest.mark.asyncio
async def test_actual_sql_video_fk_original_source_and_exact_cached_replay(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        result=await context.service.analyze(context.project.project_id,context.request)
        assert result.status=='succeeded' and result.source_media.media_kind=='video'
        assert result.transcript.analysis_id==result.analysis_id and result.analysis_id.startswith('ana_')
        assert result.transcript.is_original_evidence and result.transcript.version==1
        assert result.transcript.provenance['fixture'] is True
        assert result.transcript.provenance['raw_model_result']['model_inferences']==0
        assert result.transcript.provenance['provider_pcm_transcript']['segments'][0]['words'][0]['start_seconds']==.1
        replay=await context.service.analyze(context.project.project_id,context.request)
        assert replay==result and ExplicitCpuFixture.calls==1
        assert await count(context,'auto_edit_analyses')==await count(context,'transcripts')==1
        assert await count(context,'uploaded_audio_transcriptions')==0
        assert not list(context.service.staging_root.iterdir())
        assert result.provenance['local_video_binding_sha256']==context.provider.immutable_binding['sha256']
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_local_language_binding_changes_cache_without_reusing_previous_analysis(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        first=await context.service.analyze(context.project.project_id,context.request)
        context.service.transcription_provider=LocalVideoTranscriptionProvider(**custody.kwargs,language='en')
        second=await context.service.analyze(context.project.project_id,context.request)
        assert first.analysis_id!=second.analysis_id and first.transcript.language=='vi' and second.transcript.language=='en'
        assert first.fingerprint!=second.fingerprint and ExplicitCpuFixture.calls==2
    finally:await context.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['source_bytes','model'])
async def test_cache_lookup_verifies_physical_source_and_runtime_before_replay(custody,tmp_path,monkeypatch,mutation):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        await context.service.analyze(context.project.project_id,context.request)
        if mutation=='model':(custody.model/'model.bin').write_bytes(b'changed explicit fixture')
        else:
            asset=await context.repository.get_asset(context.completed.asset_id)
            context.uploads.object_storage._path(asset.object_key).write_bytes(b'changed explicit fixture')
        expected = StorageDownloadError if mutation == 'source_bytes' else (ValueError, RuntimeError)
        with pytest.raises(expected) as rejected:
            await context.service.analyze(context.project.project_id,context.request)
        if mutation == 'source_bytes':
            assert rejected.value.code == 'STORAGE_DOWNLOAD_SIZE_MISMATCH'
        assert ExplicitCpuFixture.calls==1 and await count(context,'auto_edit_analyses')==1
        assert not list(context.service.staging_root.iterdir())
    finally:await context.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['workspace','kind','quarantine','scan','metadata','storage'])
async def test_trusted_intake_and_media_identity_are_checked_before_dispatch(custody,tmp_path,monkeypatch,mutation):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        foreign_workspace=await context.platform.create_workspace(WorkspaceCreate(
            slug='foreign-local-fixture',name='Foreign local fixture',owner_ref='fixture-only')) if mutation=='workspace' else None
        async with context.sessions() as session:
            asset=await session.get(AssetORM,context.completed.asset_id)
            upload=await session.get(UploadSessionORM,context.completed.upload.upload_id)
            if mutation=='workspace':asset.workspace_id=foreign_workspace.workspace_id
            elif mutation=='kind':asset.kind='audio'
            elif mutation=='quarantine':upload.quarantine_state='quarantined'
            elif mutation=='scan':upload.scan_checksum_sha256='a'*64
            elif mutation=='storage':asset.storage_provider='s3'
            else:asset.provenance={**asset.provenance,'media_metadata':{**asset.provenance['media_metadata'],'duration_seconds':15}}
            await session.commit()
        with pytest.raises(ValueError):await context.service.analyze(context.project.project_id,context.request)
        assert ExplicitCpuFixture.calls==0 and await count(context,'auto_edit_analyses')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_two_repository_instances_same_fingerprint_only_dispatch_once(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event()
    async def started():
        while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
    first=asyncio.create_task(context.service.analyze(context.project.project_id,context.request))
    try:
        await asyncio.wait_for(started(),10)
        second=AutoEditAnalysisService(repository=AutoEditRepository(context.sessions),platform=context.platform,
            object_storage=context.uploads.object_storage,transcription_provider=LocalVideoTranscriptionProvider(**custody.kwargs,language='vi'),
            signal_provider=DeterministicMediaSignalProvider(),staging_root=tmp_path/'second-repository-staging')
        waiting=await second.analyze(context.project.project_id,context.request)
        assert waiting.status=='analyzing' and ExplicitCpuFixture.calls==1
        ExplicitCpuFixture.wait.set();finished=await first
        assert finished.analysis_id==waiting.analysis_id and await count(context,'transcripts')==1
    finally:
        ExplicitCpuFixture.wait.set();await asyncio.gather(first,return_exceptions=True);await context.engine.dispose()


@pytest.mark.asyncio
async def test_failed_boundary_raw_is_immutable_and_cached_without_model_replay(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch);ExplicitCpuFixture.boundary=True
    try:
        with pytest.raises(ValueError):await context.service.analyze(context.project.project_id,context.request)
        failed=(await context.service.list(context.project.project_id))[0]
        assert failed.status=='failed' and failed.transcript is None and failed.scenes==[]
        evidence=failed.provenance['local_video_rejected_evidence'];assert evidence['sha256']==digest(evidence['evidence'])
        assert evidence['evidence']['model_result']['fixture'] is True
        original=copy.deepcopy(evidence)
        replay=await context.service.analyze(context.project.project_id,context.request)
        assert replay==failed and ExplicitCpuFixture.calls==1
        assert await count(context,'transcripts')==await count(context,'scenes')==0
        assert replay.provenance['local_video_rejected_evidence']==original
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_unknown_timeout_is_not_replayed_on_cached_analysis(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    class Unknown(ExplicitCpuFixture):
        attempts=0
        async def transcribe(self,*args,**kwargs):type(self).attempts+=1;raise TimeoutError('explicit unknown CPU fixture')
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',Unknown)
    try:
        with pytest.raises(TimeoutError):await context.service.analyze(context.project.project_id,context.request)
        failed=(await context.service.list(context.project.project_id))[0]
        assert failed.error_code=='AUTO_EDIT_LOCAL_OUTCOME_UNKNOWN'
        assert (await context.service.analyze(context.project.project_id,context.request))==failed
        assert Unknown.attempts==1 and await count(context,'transcripts')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_signal_failure_cancels_and_drains_live_cpu_and_owned_staging(custody,tmp_path,monkeypatch):
    class FailedSignals(DeterministicMediaSignalProvider):
        async def analyze(self,*args,**kwargs):
            while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
            raise ValueError('explicit signal fixture failure')
    context=await configured_sql(tmp_path,custody,monkeypatch,signals=FailedSignals());ExplicitCpuFixture.wait=asyncio.Event()
    try:
        with pytest.raises(ValueError):await context.service.analyze(context.project.project_id,context.request)
        assert ExplicitCpuFixture.cancelled and ExplicitCpuFixture.calls==1
        assert not list(context.service.staging_root.iterdir()) and await count(context,'transcripts')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_parent_cancel_terminalizes_unknown_and_replay_does_not_dispatch(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event()
    async def started():
        while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
    task=asyncio.create_task(context.service.analyze(context.project.project_id,context.request))
    try:
        await asyncio.wait_for(started(),10);task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        result=(await context.service.list(context.project.project_id))[0]
        assert result.status=='failed' and result.error_code=='AUTO_EDIT_LOCAL_OUTCOME_UNKNOWN'
        assert (await context.service.analyze(context.project.project_id,context.request))==result
        assert ExplicitCpuFixture.cancelled and ExplicitCpuFixture.calls==1 and not list(context.service.staging_root.iterdir())
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_sql_transcript_commit_rollback_retains_request_evidence_without_partial_results(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    @event.listens_for(context.engine.sync_engine,'before_cursor_execute')
    def reject_insert(connection,cursor,statement,*args):
        if statement.startswith('INSERT INTO transcripts '):raise RuntimeError('explicit commit rollback fixture')
    try:
        with pytest.raises(RuntimeError):await context.service.analyze(context.project.project_id,context.request)
        failed=(await context.service.list(context.project.project_id))[0]
        assert failed.status=='failed' and failed.transcript is None
        assert failed.provenance['local_video_rejected_evidence']['evidence']['source_projection_validated'] is True
        assert await count(context,'transcripts')==await count(context,'transcript_words')==await count(context,'scenes')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_original_object_tamper_after_cpu_result_blocks_authoritative_transcript(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    asset=await context.repository.get_asset(context.completed.asset_id);target=context.uploads.object_storage._path(asset.object_key)
    class Tamper(ExplicitCpuFixture):
        async def transcribe(self,*args,**kwargs):
            result=await super().transcribe(*args,**kwargs);target.write_bytes(b'changed owned source object');return result
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',Tamper)
    try:
        with pytest.raises(StorageDownloadError) as rejected:
            await context.service.analyze(context.project.project_id,context.request)
        assert rejected.value.code == 'STORAGE_DOWNLOAD_SIZE_MISMATCH'
        failed=(await context.service.list(context.project.project_id))[0]
        assert failed.transcript is None and failed.provenance['local_video_rejected_evidence']['evidence']['model_result']['fixture']
        assert await count(context,'transcripts')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_no_audio_stream_has_visual_analysis_without_mock_cpu_or_transcript(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        # Update both trusted intake snapshots coherently; this is an explicit
        # no-audio metadata fixture, not a second model result or live source.
        async with context.sessions() as session:
            asset=await session.get(AssetORM,context.completed.asset_id)
            upload=await session.get(UploadSessionORM,context.completed.upload.upload_id)
            metadata={**asset.provenance['media_metadata'],'audio_codec':None,'audio_channels':None,'audio_sample_rate':None}
            asset.provenance={**asset.provenance,'media_metadata':metadata};upload.media_metadata_json=metadata;await session.commit()
        result=await context.service.analyze(context.project.project_id,context.request)
        assert result.status=='succeeded' and result.transcript is None and ExplicitCpuFixture.calls==0
        assert result.provenance['asr_state']=='no_audio_stream' and await count(context,'transcripts')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_normalizer_rejections_retain_distinct_video_source_custody(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    second=await upload_fixture(context.uploads,context.project,context.version,synthetic_mp4(100003))
    class Rejected(ExplicitCpuFixture):
        calls=0
        async def transcribe(self,*args,**kwargs):
            await super().transcribe(*args,**kwargs)
            while type(self).calls<2:await asyncio.sleep(.01)
            raise ValueError('explicit per-request normalizer failure')
    monkeypatch.setattr(video,'LocalCpuTranscriptionProvider',Rejected)
    try:
        results=await asyncio.wait_for(asyncio.gather(
            context.service.analyze(context.project.project_id,context.request),
            context.service.analyze(context.project.project_id,AutoEditAnalysisRequest(asset_id=second.asset_id)),
            return_exceptions=True),10)
        assert all(isinstance(value,ValueError) for value in results)
        rows=await context.service.list(context.project.project_id)
        evidence={row.asset_id:row.provenance['local_video_rejected_evidence']['evidence'] for row in rows}
        assert evidence[context.completed.asset_id]['source_sha256']==context.completed.checksum_sha256
        assert evidence[second.asset_id]['source_sha256']==second.checksum_sha256
        assert evidence[context.completed.asset_id]['source_size_bytes']==100000 and evidence[second.asset_id]['source_size_bytes']==100003
        assert Rejected.calls==2 and await count(context,'transcripts')==0
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_actual_trusted_mp4_sql_analysis_preserves_measured_source_and_mock_label(custody,tmp_path,monkeypatch):
    if not FFMPEG.is_file():pytest.skip('Owned Windows FFmpeg unavailable; physical SQL acceptance not claimed')
    import subprocess
    context=await configured_sql(tmp_path,custody,monkeypatch)
    try:
        path=tmp_path/'owned-physical-sql.mp4'
        subprocess.run([str(FFMPEG),'-v','error','-nostdin','-f','lavfi','-i','color=black:s=160x90:r=25:d=3',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=1','-c:v','libx264',
            '-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True,timeout=30)
        context.uploads.media_probe=FFprobeMediaProbe(str(FFMPEG.with_name('ffprobe.exe')))
        complete=await upload_fixture(context.uploads,context.project,context.version,path.read_bytes())
        from app.local_uploaded_audio_provider import bounded_process
        monkeypatch.setattr(video,'bounded_process',bounded_process)
        context.service.transcription_provider=LocalVideoTranscriptionProvider(**{**custody.kwargs,'decoder':FFMPEG,
            'decoder_sha256':file_sha(FFMPEG)},language='vi')
        context.service.signal_provider=FFmpegMediaSignalProvider(str(FFMPEG))
        await context.platform.seed_providers([{'provider_key':'ffmpeg-media-signals','display_name':'Measured FFmpeg signals',
            'capability':'media_analysis','adapter':'ffmpeg','routing_mode':'primary','status':'healthy','enabled':True,
            'supports_dry_run':False,'metadata':{'fixture':False,'paid':False}}])
        result=await context.service.analyze(context.project.project_id,AutoEditAnalysisRequest(asset_id=complete.asset_id))
        assert result.status=='succeeded' and result.source_media.video_codec=='h264' and result.source_media.audio_codec=='aac'
        assert result.transcript.provenance['fixture'] is True and result.transcript.provenance['raw_model_result']['model_inferences']==0
        assert result.provenance['media_signals']['fixture'] is False and result.provenance['media_signals']['scene_decoded_clock_verified']
        assert result.transcript.provenance['source_checksum']==complete.checksum_sha256
        assert await count(context,'uploaded_audio_transcriptions')==0 and file_sha(path)==complete.checksum_sha256
        assert result.provenance['local_video_execution']=='synchronous_partial' and not result.provenance['production_acceptance_verified']
    finally:await context.engine.dispose()


@pytest.mark.asyncio
async def test_cancel_during_download_drains_owned_file_io_before_cleanup(custody,tmp_path,monkeypatch):
    context=await configured_sql(tmp_path,custody,monkeypatch)
    began=asyncio.Event();release=asyncio.Event();finished=[]
    original=context.uploads.object_storage
    class SlowRead:
        name='local'
        async def download_file(self,**kwargs):
            began.set();await release.wait();await original.download_file(**kwargs);finished.append(True)
    context.service.object_storage=SlowRead()
    task=asyncio.create_task(context.service.analyze(context.project.project_id,context.request))
    try:
        await asyncio.wait_for(began.wait(),10);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and list(context.service.staging_root.iterdir())
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished==[True] and not list(context.service.staging_root.iterdir())
        assert ExplicitCpuFixture.calls==0 and await count(context,'auto_edit_analyses')==0
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True);await context.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['download','hash'])
async def test_double_cancel_waits_for_blocking_source_file_io_before_cleanup(custody,tmp_path,monkeypatch,phase):
    import threading,hashlib
    import app.auto_edit_source_custody as source_custody
    context=await configured_sql(tmp_path,custody,monkeypatch)
    began=threading.Event();release=threading.Event();finished=threading.Event()
    asset=await context.repository.get_asset(context.completed.asset_id)
    source=context.uploads.object_storage._path(asset.object_key)
    def blocked_io(target,write=False):
        with target.open('wb' if write else 'rb') as stream:
            began.set()
            if not release.wait(10):raise AssertionError('Blocking I/O fixture was not released')
            if write:stream.write(source.read_bytes());value=None
            else:value=hashlib.sha256(stream.read()).hexdigest()
        finished.set();return value
    if phase=='download':
        class SlowRead:
            name='local'
            async def download_file(self,**kwargs):await asyncio.to_thread(blocked_io,kwargs['destination'],True)
        context.service.object_storage=SlowRead()
    else:monkeypatch.setattr(source_custody,'sha256_file',blocked_io)
    async def started():
        while not began.is_set():await asyncio.sleep(.01)
    task=asyncio.create_task(context.service.analyze(context.project.project_id,context.request))
    try:
        await asyncio.wait_for(started(),10);task.cancel();await asyncio.sleep(.01);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not finished.is_set(),'Repeated cancellation must not abandon live file I/O'
        assert list(context.service.staging_root.iterdir())
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert finished.is_set() and not list(context.service.staging_root.iterdir())
        assert ExplicitCpuFixture.calls==0 and await count(context,'auto_edit_analyses')==0
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True)
        for _ in range(100):
            if finished.is_set():break
            await asyncio.sleep(.01)
        await context.engine.dispose()
