"""Actual SQL/ASGI job custody with explicit mock ASR; no model or paid wire."""
import asyncio
import copy
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch
import pytest
from fastapi import FastAPI,Depends
from httpx import AsyncClient,ASGITransport
from sqlalchemy import select,text,event
from app.auto_edit_job_service import AutoEditJobService,ANALYSIS_QUEUE,AnalysisClaim
from app.auto_edit_job_repository import AnalysisJobConflict
from app.auto_edit_job_models import AutoEditJobCreate
from app.auto_edit_job_db import AutoEditJobORM,AutoEditJobRequestORM
from app.auto_edit_db import AutoEditAnalysisORM,UploadSessionORM
from app.auto_edit_models import AutoEditAnalysisRequest
from app.auto_edit_providers import ContractOnlyTranscriptionProvider,ProviderNotConfigured
from app.db import JobORM,JobEventORM,AssetORM,ProviderUsageORM,utc_now,create_engine,create_session_factory
from app.auto_edit_repository import AutoEditRepository
from app.auto_edit_service import AutoEditAnalysisService
from app.auto_edit_job_routes import router
from app.human_auth import authorize_human_request
from app.uploaded_audio_repository import digest
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
from test_auto_edit_local_cpu import configured_sql,count
from test_local_uploaded_audio_provider import custody,ExplicitCpuFixture,reset_fixture,fixture_decoder


class Queue:
    def __init__(self):self.items=[];self.failed=False
    async def rpush(self,key,value):
        if self.failed:raise RuntimeError('Explicit failed delivery fixture')
        self.items.append((key,value))


async def stack(tmp_path,custody,monkeypatch):
    env=await configured_sql(tmp_path,custody,monkeypatch)
    env.queue=Queue()
    env.jobs=AutoEditJobService(analysis_service=env.service,queue=env.queue)
    env.payload=AutoEditJobCreate(configuration=env.request,source_sha256=env.completed.checksum_sha256,
        idempotency_key='explicit-video-job-fixture-01')
    return env


async def ready(env):
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
    await env.jobs.process(row.job.job_id)
    return await env.jobs.repository.get(env.project.project_id,row.job.job_id)


@pytest.mark.asyncio
async def test_queued_to_actual_video_transcript_original_and_idempotent_job_receipts(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        queued=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        assert queued.job.status=='queued' and queued.analysis.status=='pending' and queued.analysis.transcript is None
        assert ExplicitCpuFixture.calls==0 and env.queue.items==[(ANALYSIS_QUEUE,queued.job.job_id)]
        await env.jobs.process(queued.job.job_id)
        result=await env.jobs.repository.get(env.project.project_id,queued.job.job_id)
        assert result.job.status=='awaiting_review' and result.analysis.status=='succeeded'
        transcript=result.analysis.transcript
        assert transcript.analysis_id==result.analysis.analysis_id and transcript.is_original_evidence and transcript.version==1
        assert transcript.provenance['fixture'] is True and transcript.provenance['raw_model_result']['model_inferences']==0
        assert result.human_review_required and not result.timeline_mutated and ExplicitCpuFixture.calls==1
        await env.jobs.process(queued.job.job_id)
        replay=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        second=env.payload.model_copy(update={'idempotency_key':'explicit-video-job-fixture-02'})
        other=await env.jobs.create(env.project.project_id,second,'usr:other-editor')
        assert other.job.job_id==replay.job.job_id==queued.job.job_id and ExplicitCpuFixture.calls==1
        assert await count(env,'auto_edit_analyses')==await count(env,'transcripts')==1
        assert await count(env,'auto_edit_analysis_job_requests')==2 and await count(env,'uploaded_audio_transcriptions')==0
        assert not list(env.service.staging_root.iterdir())
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['actor','request'])
async def test_same_key_rejects_actor_or_payload_drift(custody,tmp_path,monkeypatch,change):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        payload=env.payload if change=='actor' else env.payload.model_copy(update={'configuration':env.request.model_copy(update={'top_highlights':5})})
        with pytest.raises(AnalysisJobConflict):
            await env.jobs.create(env.project.project_id,payload,'usr:other-editor' if change=='actor' else 'usr:fixture-editor')
        assert await count(env,'jobs')==1 and await count(env,'auto_edit_analyses')==1 and ExplicitCpuFixture.calls==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_queue_handoff_failure_and_duplicate_worker_delivery_use_durable_sql(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        env.queue.failed=True
        with pytest.raises(RuntimeError):await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        rows=await env.jobs.repository.list(env.project.project_id);assert len(rows)==1 and rows[0].job.status=='queued'
        env.queue.failed=False
        await env.jobs.recover();await env.jobs.recover()
        await asyncio.gather(*(env.jobs.process(job_id) for key,job_id in env.queue.items))
        row=await env.jobs.repository.get(env.project.project_id,rows[0].job.job_id)
        assert row.job.status=='awaiting_review' and ExplicitCpuFixture.calls==1
        assert await count(env,'transcripts')==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_running_async_custody_cannot_be_taken_by_legacy_sync(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        queued=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        legacy=await env.service.analyze(env.project.project_id,env.request)
        assert legacy.analysis_id==queued.analysis.analysis_id and legacy.status=='pending' and ExplicitCpuFixture.calls==0
        with pytest.raises(ValueError):await env.repository.mark_analysis_running(legacy.analysis_id)
        await env.jobs.process(queued.job.job_id)
        assert (await env.jobs.repository.get(env.project.project_id,queued.job.job_id)).job.status=='awaiting_review'
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('expired',[False,True])
async def test_actual_second_worker_skips_live_lease_and_stale_completion(custody,tmp_path,monkeypatch,expired):
    env=await stack(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event()
    second_engine=create_engine('sqlite+aiosqlite:///'+(tmp_path/'auto-edit.db').as_posix())
    second_sessions=create_session_factory(second_engine)
    other=AutoEditAnalysisService(repository=AutoEditRepository(second_sessions),platform=env.platform,
        object_storage=env.service.object_storage,transcription_provider=env.provider,
        signal_provider=env.service.signal_provider,staging_root=tmp_path/'second-staging')
    second=AutoEditJobService(analysis_service=other,queue=Queue())
    async def started():
        while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
    work=asyncio.create_task(env.jobs.process(row.job.job_id))
    try:
        await asyncio.wait_for(started(),10)
        if expired:
            async with env.sessions() as session:
                parent=await session.scalar(select(AutoEditJobORM));parent.lease_expires_at=utc_now()-timedelta(seconds=1);await session.commit()
        await second.recover(include_queued=False);await second.process(row.job.job_id)
        ExplicitCpuFixture.wait.set();await work
        result=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert result.job.status==('needs_attention' if expired else 'awaiting_review') and ExplicitCpuFixture.calls==1
        assert await count(env,'transcripts')==(0 if expired else 1)
        await second.recover();await second.process(row.job.job_id);assert ExplicitCpuFixture.calls==1
    finally:
        ExplicitCpuFixture.wait.set();await asyncio.gather(work,return_exceptions=True);await second_engine.dispose();await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('running',[False,True])
async def test_cancel_wins_no_late_transcript_no_new_key_replay(custody,tmp_path,monkeypatch,running):
    env=await stack(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event()
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor');work=None
    try:
        if running:
            work=asyncio.create_task(env.jobs.process(row.job.job_id))
            while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
        cancelled=await env.jobs.cancel(env.project.project_id,row.job.job_id,'usr:cancel-editor')
        assert cancelled.job.status=='cancelled'
        ExplicitCpuFixture.wait.set()
        if work:await work
        await env.jobs.process(row.job.job_id);await env.jobs.recover()
        replay=await env.jobs.create(env.project.project_id,env.payload.model_copy(update={'idempotency_key':'explicit-cancel-replay-key'}),'usr:fixture-editor')
        assert replay.job.status=='cancelled' and await count(env,'transcripts')==0
        assert ExplicitCpuFixture.calls==(1 if running else 0)
        assert not list(env.service.staging_root.iterdir())
    finally:
        ExplicitCpuFixture.wait.set()
        if work:await asyncio.gather(work,return_exceptions=True)
        await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['source','runtime','configuration','actor','request'])
async def test_sql_completion_rejects_drift_and_preserves_no_authoritative_rows(custody,tmp_path,monkeypatch,mutation):
    env=await stack(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event()
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor');work=asyncio.create_task(env.jobs.process(row.job.job_id))
    try:
        while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
        if mutation=='runtime':(custody.model/'model.bin').write_bytes(b'explicit fixture drift')
        else:
            async with env.sessions() as session:
                relation=await session.scalar(select(AutoEditJobORM));job=await session.get(JobORM,row.job.job_id)
                if mutation=='source':
                    asset=await session.get(AssetORM,env.completed.asset_id);asset.checksum_sha256='a'*64
                elif mutation=='configuration':relation.configuration_json={**relation.configuration_json,'top_highlights':5}
                elif mutation=='actor':relation.actor_ref='usr:tampered'
                else:job.request_json={**job.request_json,'actor_ref':'usr:tampered'}
                await session.commit()
        ExplicitCpuFixture.wait.set();await work
        async with env.sessions() as session:
            job=await session.get(JobORM,row.job.job_id)
            assert job.status in {'failed','needs_attention'} and not job.error_json['retryable']
        assert await count(env,'transcripts')==await count(env,'scenes')==0 and ExplicitCpuFixture.calls==1
    finally:
        ExplicitCpuFixture.wait.set();await asyncio.gather(work,return_exceptions=True);await env.engine.dispose()


@pytest.mark.asyncio
async def test_terminal_event_insert_failure_rolls_back_transcript_scene_and_job_together(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        def reject_terminal(mapper,connection,target):
            if target.event_type=='video_analysis.ready':raise RuntimeError('Explicit terminal insertion failure')
        event.listen(JobEventORM,'before_insert',reject_terminal)
        try:await env.jobs.process(row.job.job_id)
        finally:event.remove(JobEventORM,'before_insert',reject_terminal)
        result=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert result.job.status=='failed' and result.analysis.transcript is None
        assert result.analysis.provenance['local_video_rejected_evidence']['evidence']['model_result']['model_inferences']==0
        costs=await env.platform.list_cost_records(env.project.project_id)
        assert len(costs)==2 and all(c.actual_cost==0 and c.job_id==row.job.job_id for c in costs)
        assert await count(env,'transcripts')==await count(env,'scenes')==await count(env,'highlights')==0
        async with env.sessions() as session:
            events=(await session.scalars(select(JobEventORM.event_type))).all()
            assert 'video_analysis.ready' not in events and 'video_analysis.failed' in events
        await env.jobs.process(row.job.job_id);assert ExplicitCpuFixture.calls==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_http_202_actual_auth_roles_scope_actor_and_read_has_no_model(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch);app=FastAPI();app.include_router(router,dependencies=[Depends(authorize_human_request)])
    app.state.auto_edit_job_service=env.jobs
    endpoint=f'/api/v1/projects/{env.project.project_id}/analysis-jobs'
    try:
        install_test_human_auth(app,platform_repository=env.platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app),base_url='http://owned-fixture') as client:
            assert (await client.get(endpoint)).status_code==401
            assert (await client.post(endpoint,json=env.payload.model_dump(mode='json'),headers=TEST_HUMAN_HEADERS)).status_code==403
            assert (await client.get(endpoint.replace(env.project.project_id,'prj_foreign_missing'),headers=TEST_HUMAN_HEADERS)).status_code==404
            install_test_human_auth(app,platform_repository=env.platform,platform_role='editor',workspace_roles={'*':'editor'})
            response=await client.post(endpoint,json=env.payload.model_dump(mode='json'),headers=TEST_HUMAN_HEADERS)
            assert response.status_code==202,response.text
            job_id=response.json()['job']['job_id'];assert response.json()['job']['request']['actor_ref']=='usr:test-owner'
            assert response.headers['cache-control']=='no-store' and ExplicitCpuFixture.calls==0
            install_test_human_auth(app,platform_repository=env.platform,platform_role='viewer',workspace_roles={'*':'viewer'})
            for route in (endpoint,endpoint+'/'+job_id):assert (await client.get(route,headers=TEST_HUMAN_HEADERS)).status_code==200
            assert (await client.post(endpoint+'/'+job_id+'/cancel',headers=TEST_HUMAN_HEADERS)).status_code==403
            assert ExplicitCpuFixture.calls==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_unconfigured_is_real_block_without_creating_fake_analysis(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        env.service.transcription_provider=ContractOnlyTranscriptionProvider()
        with pytest.raises(ProviderNotConfigured):await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        assert await count(env,'jobs')==await count(env,'auto_edit_analyses')==0 and ExplicitCpuFixture.calls==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['timeout','boundary'])
async def test_unknown_or_rejected_raw_are_durable_terminal_and_never_replayed(custody,tmp_path,monkeypatch,failure):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        if failure=='boundary':ExplicitCpuFixture.boundary=True
        else:
            async def unknown(*args,**kwargs):
                ExplicitCpuFixture.calls+=1
                raise TimeoutError('Explicit unknown mock ASR outcome')
            monkeypatch.setattr(ExplicitCpuFixture,'transcribe',unknown)
        row=await ready(env)
        assert row.job.status==('needs_attention' if failure=='timeout' else 'failed')
        assert row.analysis.transcript is None and not row.job.error.retryable
        if failure=='boundary':
            raw=row.analysis.provenance['local_video_rejected_evidence']
            assert raw['sha256']==digest(raw['evidence']) and raw['evidence']['model_result']['model_inferences']==0
            assert raw['evidence']['human_accepted'] is False
        await env.jobs.recover();await env.jobs.process(row.job.job_id)
        newkey=env.payload.model_copy(update={'idempotency_key':'explicit-unknown-replay-key'})
        replay=await env.jobs.create(env.project.project_id,newkey,'usr:fixture-editor')
        assert replay.job.job_id==row.job.job_id and ExplicitCpuFixture.calls==1 and await count(env,'transcripts')==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_heartbeat_renews_live_claim_and_cannot_revive_expired_custody(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        value,token,fingerprint=await env.jobs.repository.claim(row.job.job_id)
        guard=AnalysisClaim(env.jobs,value,token,fingerprint)
        async with env.sessions() as session:
            parent=await session.scalar(select(AutoEditJobORM));previous=parent.lease_expires_at
        from app import auto_edit_job_service as job_module
        sleep=asyncio.sleep
        async def quick(seconds):await sleep(.01 if seconds==30 else seconds)
        monkeypatch.setattr(job_module.asyncio,'sleep',quick)
        heart=asyncio.create_task(env.jobs.heartbeat(guard))
        try:
            await sleep(.05)
            async with env.sessions() as session:
                parent=await session.scalar(select(AutoEditJobORM));assert parent.lease_expires_at>previous
                parent.lease_expires_at=utc_now()-timedelta(seconds=1);expired=parent.lease_expires_at;await session.commit()
            await sleep(.03);await heart
            async with env.sessions() as session:
                parent=await session.scalar(select(AutoEditJobORM));assert parent.lease_expires_at.replace(tzinfo=None)==expired.replace(tzinfo=None)
            await env.jobs.recover(include_queued=False)
            assert (await env.jobs.repository.get(env.project.project_id,row.job.job_id)).job.status=='needs_attention'
        finally:
            heart.cancel();await asyncio.gather(heart,return_exceptions=True)
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['decoder','cpu'])
async def test_durable_cancel_reaches_video_decoder_or_cpu_and_drains_child(custody,tmp_path,monkeypatch,phase):
    env=await stack(tmp_path,custody,monkeypatch)
    from app import local_video_transcription_provider as video
    began=asyncio.Event();stopped=asyncio.Event()
    async def blocked(*args,**kwargs):
        began.set()
        try:await asyncio.Future()
        finally:
            await asyncio.sleep(.02);stopped.set()
    if phase=='decoder':monkeypatch.setattr(video,'bounded_process',blocked)
    else:monkeypatch.setattr(ExplicitCpuFixture,'transcribe',blocked)
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
    work=asyncio.create_task(env.jobs.process(row.job.job_id))
    try:
        await asyncio.wait_for(began.wait(),10)
        await env.jobs.cancel(env.project.project_id,row.job.job_id,'usr:cancel-editor')
        await asyncio.wait_for(work,10)
        assert stopped.is_set() and not list(env.service.staging_root.iterdir())
        result=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert result.job.status=='cancelled' and result.analysis.transcript is None
        assert await count(env,'transcripts')==0
    finally:
        work.cancel();await asyncio.gather(work,return_exceptions=True);await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('phase',['download','hash','cpu'])
async def test_repeated_process_cancel_drains_owned_io_and_preserves_unknown_without_replay(custody,tmp_path,monkeypatch,phase):
    env=await stack(tmp_path,custody,monkeypatch)
    import threading,hashlib
    import app.auto_edit_source_custody as source_module
    began=threading.Event();release=threading.Event();closed=threading.Event()
    asset=await env.repository.get_asset(env.completed.asset_id)
    original=env.uploads.object_storage._path(asset.object_key)
    def blocking(path,write=False):
        with path.open('wb' if write else 'rb') as stream:
            began.set()
            assert release.wait(10),'Explicit owned blocking I/O timeout'
            if write:stream.write(original.read_bytes());answer=None
            else:answer=hashlib.sha256(stream.read()).hexdigest()
        closed.set();return answer
    if phase=='download':
        class Storage:
            name='local'
            async def download_file(self,**kw):await asyncio.to_thread(blocking,kw['destination'],True)
        env.service.object_storage=Storage()
    elif phase=='hash':monkeypatch.setattr(source_module,'sha256_file',blocking)
    else:
        async def cpu(*args,**kwargs):
            ExplicitCpuFixture.calls+=1
            from app.local_video_transcription_provider import completed_io
            path=args[1] if len(args)>1 else args[0]
            with path.open('rb') as stream:
                began.set()
                try:await asyncio.Future()
                finally:
                    await completed_io(asyncio.to_thread(release.wait,10))
                    stream.close();closed.set()
        monkeypatch.setattr(ExplicitCpuFixture,'transcribe',cpu)
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
    work=asyncio.create_task(env.jobs.process(row.job.job_id))
    try:
        while not began.is_set():await asyncio.sleep(.01)
        work.cancel();await asyncio.sleep(.01);work.cancel();await asyncio.sleep(.02)
        assert not work.done() and not closed.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):await work
        assert closed.is_set() and not list(env.service.staging_root.iterdir())
        result=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert result.job.status=='needs_attention' and result.analysis.transcript is None
        await env.jobs.process(row.job.job_id);await env.jobs.recover()
        assert ExplicitCpuFixture.calls==(1 if phase=='cpu' else 0)
    finally:
        release.set();await asyncio.gather(work,return_exceptions=True);await env.engine.dispose()


def test_additive_video_job_migration_preserves_existing_tables_and_real_foreign_keys(tmp_path):
    import importlib.util
    import sqlalchemy as sa
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from app.db import Base
    names={'auto_edit_analysis_jobs','auto_edit_analysis_job_requests'}
    engine=sa.create_engine('sqlite:///'+(tmp_path/'owned-job-migration.sqlite').as_posix())
    prior=[table for table in Base.metadata.sorted_tables if table.name not in names]
    Base.metadata.create_all(engine,tables=prior)
    with engine.begin() as connection:
        connection.execute(Base.metadata.tables['workspaces'].insert().values(workspace_id='wsp_retained',slug='retained',
            name='Retained fixture',owner_ref='usr:fixture'))
        before={table.name:connection.execute(sa.select(table)).mappings().all() for table in prior}
        module_path=Path(__file__).parents[1]/'migrations/versions/0031_sql_auto_edit_analysis_jobs.py'
        spec=importlib.util.spec_from_file_location('owned_video_job_migration',module_path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        assert module.revision=='0031_ns_video_jobs' and module.down_revision=='0030_sql_tts_reuse'
        with Operations.context(MigrationContext.configure(connection)):module.upgrade()
        assert names<=set(sa.inspect(connection).get_table_names())
        for table in prior:assert connection.execute(sa.select(table)).mappings().all()==before[table.name]
        foreign=sa.inspect(connection).get_foreign_keys('auto_edit_analysis_jobs')
        assert any(f['referred_table']=='auto_edit_analyses' and f['constrained_columns']==['analysis_id'] for f in foreign)
        assert any(f['referred_table']=='jobs' and f['constrained_columns']==['job_id'] for f in foreign)
        assert sa.inspect(connection).get_foreign_keys('transcripts')[0]['referred_table']=='auto_edit_analyses'
        with pytest.raises(RuntimeError):module.downgrade()
    engine.dispose()


@pytest.mark.asyncio
async def test_actual_worker_queue_dispatch_and_duplicate_delivery_are_safe(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    monkeypatch.syspath_prepend(str(Path(__file__).parents[3]/'services/worker'))
    from npd_worker.main import run_analysis_queue
    row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
    class Redis:
        def __init__(self):self.calls=0
        async def blpop(self,key,timeout):
            assert key==ANALYSIS_QUEUE and timeout==5
            self.calls+=1
            if self.calls<=2:return key,row.job.job_id
            raise asyncio.CancelledError()
    try:
        with pytest.raises(asyncio.CancelledError):await run_analysis_queue(Redis(),env.jobs)
        saved=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert saved.job.status=='awaiting_review' and ExplicitCpuFixture.calls==1 and await count(env,'transcripts')==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('offset',[0,.35])
async def test_real_mp4_upload_probe_decode_clock_in_async_job_with_explicit_mock_cpu(custody,tmp_path,monkeypatch,offset):
    import subprocess
    from test_local_video_transcription_provider import FFMPEG
    from test_auto_edit_analysis import upload_fixture
    from app.auto_edit_providers import FFprobeMediaProbe,FFmpegMediaSignalProvider
    from app.local_video_transcription_provider import LocalVideoTranscriptionProvider
    from app.local_asr_runtime import file_sha
    from app.local_uploaded_audio_provider import bounded_process
    from app import local_video_transcription_provider as video
    if not FFMPEG.is_file():pytest.skip('Held FFmpeg unavailable; measured source acceptance not claimed')
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        path=tmp_path/'owned-async-source.mp4'
        subprocess.run([str(FFMPEG),'-v','error','-nostdin','-f','lavfi','-i','color=black:s=160x90:r=25:d=3',
            '-itsoffset',str(offset),'-f','lavfi','-i','sine=frequency=440:sample_rate=16000:duration=1',
            '-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(path)],check=True,capture_output=True,timeout=30)
        env.uploads.media_probe=FFprobeMediaProbe(str(FFMPEG.with_name('ffprobe.exe')))
        complete=await upload_fixture(env.uploads,env.project,env.version,path.read_bytes())
        monkeypatch.setattr(video,'bounded_process',bounded_process)
        env.service.transcription_provider=LocalVideoTranscriptionProvider(**{**custody.kwargs,'decoder':FFMPEG,
            'decoder_sha256':file_sha(FFMPEG)},language='vi')
        env.service.signal_provider=FFmpegMediaSignalProvider(str(FFMPEG))
        await env.platform.seed_providers([{'provider_key':'ffmpeg-media-signals','display_name':'Measured fixture',
            'capability':'media_analysis','adapter':'ffmpeg','routing_mode':'primary','status':'healthy','enabled':True,'supports_dry_run':False}])
        payload=AutoEditJobCreate(configuration=AutoEditAnalysisRequest(asset_id=complete.asset_id),
            source_sha256=complete.checksum_sha256,idempotency_key='physical-async-source-fixture')
        queued=await env.jobs.create(env.project.project_id,payload,'usr:fixture-editor')
        assert ExplicitCpuFixture.calls==0
        await env.jobs.process(queued.job.job_id)
        saved=await env.jobs.repository.get(env.project.project_id,queued.job.job_id)
        assert saved.job.status=='awaiting_review',saved.job.error
        transcript=saved.analysis.transcript
        clock=transcript.provenance['decoded_audio_clock']
        raw_word=transcript.provenance['provider_pcm_transcript']['segments'][0]['words'][0]
        assert transcript.provenance['fixture'] is True and transcript.provenance['raw_model_result']['model_inferences']==0
        assert transcript.segments[0].words[0].start_seconds==raw_word['start_seconds']+clock['source_start_seconds']
        assert saved.analysis.provenance['media_signals']['fixture'] is False and file_sha(path)==complete.checksum_sha256
        assert not transcript.provenance['source_clock_projection']['bounds_clipped'] and await count(env,'uploaded_audio_transcriptions')==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_concurrent_request_keys_share_one_analysis_and_reservation_receipts(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        other=env.payload.model_copy(update={'idempotency_key':'concurrent-video-key-02'})
        rows=await asyncio.gather(env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor'),
            env.jobs.create(env.project.project_id,other,'usr:fixture-editor'))
        assert rows[0].job.job_id==rows[1].job.job_id and ExplicitCpuFixture.calls==0
        assert await count(env,'auto_edit_analyses')==await count(env,'auto_edit_analysis_jobs')==1
        assert await count(env,'auto_edit_analysis_job_requests')==2
        await asyncio.gather(*(env.jobs.process(row.job.job_id) for row in rows))
        assert ExplicitCpuFixture.calls==1 and await count(env,'transcripts')==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['source','actor'])
async def test_drift_before_claim_is_durable_attention_not_hot_queue_replay(custody,tmp_path,monkeypatch,mutation):
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        async with env.sessions() as session:
            if mutation=='source':
                asset=await session.get(AssetORM,env.completed.asset_id);asset.checksum_sha256='a'*64
            else:
                relation=await session.scalar(select(AutoEditJobORM));relation.actor_ref='usr:changed'
            await session.commit()
        await env.jobs.process(row.job.job_id)
        async with env.sessions() as session:
            job=await session.get(JobORM,row.job.job_id)
            assert job.status=='needs_attention' and job.error_json['retryable'] is False
        before=len(env.queue.items)
        await env.jobs.recover();await env.jobs.process(row.job.job_id)
        assert len(env.queue.items)==before and ExplicitCpuFixture.calls==0
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_real_elapsed_expired_lease_after_awaited_result_flush_rolls_back_all_authoritative_rows(custody,tmp_path,monkeypatch):
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.auto_edit_db import TranscriptORM
    env=await stack(tmp_path,custody,monkeypatch);env.jobs.lease_seconds=30
    flush=AsyncSession.flush;complete=AnalysisClaim.complete
    paused=False;observed={}
    async def delayed(session,*args,**kwargs):
        nonlocal paused
        results=not paused and any(isinstance(row,TranscriptORM) for row in session.new)
        answer=await flush(session,*args,**kwargs)
        if results:
            paused=True
            await asyncio.sleep(34)  # Real elapsed SQL transition delay; no clock override.
        return answer
    async def inspect(guard,session,analysis):
        from app.auto_edit_job_repository import live_lease
        observed['live']=live_lease(guard.row)
        return await complete(guard,session,analysis)
    monkeypatch.setattr(AsyncSession,'flush',delayed);monkeypatch.setattr(AnalysisClaim,'complete',inspect)
    try:
        row=await ready(env)
        assert paused and observed['live'] is False
        assert row.job.status=='needs_attention' and row.job.error.code=='VIDEO_PROVIDER_OUTCOME_UNKNOWN'
        assert row.analysis.status=='failed' and row.analysis.transcript is None
        assert await count(env,'transcripts')==await count(env,'scenes')==await count(env,'highlights')==0
        rejected=row.analysis.provenance['local_video_rejected_evidence']
        assert rejected['sha256']==digest(rejected['evidence']) and rejected['evidence']['human_accepted'] is False
        async with env.sessions() as session:
            assert 'video_analysis.ready' not in (await session.scalars(select(JobEventORM.event_type))).all()
        costs=await env.platform.list_cost_records(env.project.project_id)
        assert len(costs)==2 and all(c.job_id==row.job.job_id and c.actual_cost==0 for c in costs)
        await env.jobs.recover();await env.jobs.process(row.job.job_id)
        assert ExplicitCpuFixture.calls==1 and not list(env.service.staging_root.iterdir())
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_dynamic_saved_analysis_endpoint_has_no_fake_bytes_checksum(custody,tmp_path,monkeypatch):
    from app.auto_edit_routes import router as analysis_router
    env=await stack(tmp_path,custody,monkeypatch)
    try:
        row=await ready(env);artifact=row.job.artifacts[0]
        assert artifact.checksum_sha256 is None and len(row.custody_sha256)==64
        app=FastAPI();app.state.auto_edit_analysis_service=env.service
        app.include_router(analysis_router,dependencies=[Depends(authorize_human_request)])
        install_test_human_auth(app,platform_repository=env.platform,platform_role='viewer',workspace_roles={'*':'viewer'})
        async with AsyncClient(transport=ASGITransport(app),base_url='http://owned-fixture') as client:
            response=await client.get(artifact.url,headers=TEST_HUMAN_HEADERS)
        assert response.status_code==200 and response.json()['analysis_id']==row.analysis.analysis_id
        assert artifact.checksum_sha256 is None and ExplicitCpuFixture.calls==1
    finally:await env.engine.dispose()


@pytest.mark.asyncio
async def test_result_ledger_binds_frozen_invocation_after_live_provider_replacement(custody,tmp_path,monkeypatch):
    env=await stack(tmp_path,custody,monkeypatch);ExplicitCpuFixture.wait=asyncio.Event();work=None
    try:
        row=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        await env.platform.seed_providers([{'provider_key':'explicit-swapped-fixture','display_name':'Never executed fixture',
            'capability':'transcription','adapter':'explicit-test-only','routing_mode':'primary','status':'degraded','enabled':True,
            'supports_dry_run':False,'metadata':{'fixture':True,'paid':False,'external_call':False}}])
        work=asyncio.create_task(env.jobs.process(row.job.job_id))
        while not ExplicitCpuFixture.calls:await asyncio.sleep(.01)
        swapped=copy.copy(env.provider);swapped.key='explicit-swapped-fixture';swapped.model='never-executed-model'
        env.service.transcription_provider=swapped
        ExplicitCpuFixture.wait.set();await work
        async with env.sessions() as session:
            rows=(await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.operation=='auto-edit-transcript:'+row.analysis.analysis_id))).all()
            assert len(rows)==1 and rows[0].provider_key=='local-faster-whisper' and rows[0].model==env.provider.model
            assert rows[0].metadata_json['receipt']['provider_key']==rows[0].provider_key
            assert rows[0].metadata_json['human_accepted'] is False
        result=await env.jobs.repository.get(env.project.project_id,row.job.job_id)
        assert result.job.status=='failed' and await count(env,'transcripts')==0 and ExplicitCpuFixture.calls==1
        costs=await env.platform.list_cost_records(env.project.project_id)
        assert len(costs)==2 and all(c.job_id==row.job.job_id and c.actual_cost==0 for c in costs)
    finally:
        ExplicitCpuFixture.wait.set()
        if work:await asyncio.gather(work,return_exceptions=True)
        await env.engine.dispose()


@pytest.mark.asyncio
async def test_nullable_frozen_estimate_remains_unknown_without_rebinding_or_model_replay(custody,tmp_path,monkeypatch):
    from dataclasses import replace
    from app.auto_edit_providers import DeterministicTranscriptionProvider
    class NullableMockCPU(DeterministicTranscriptionProvider):
        estimated_cost_vnd=None
        calls=0
        async def transcribe(self,*args,**kwargs):
            self.calls+=1
            value=await super().transcribe(*args,**kwargs)
            return replace(value,provenance={**value.provenance,'explicit_mock_cpu':True,'model_inferences':0})
    env=await stack(tmp_path,custody,monkeypatch);provider=NullableMockCPU()
    env.service.transcription_provider=provider
    try:
        queued=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        async with env.sessions() as session:
            before=await session.scalar(select(AutoEditJobORM))
            binding=copy.deepcopy(before.provider_json);custody_sha=before.custody_sha256
        assert binding['transcription']['estimated_cost_vnd']=='None'
        await env.jobs.process(queued.job.job_id)
        row=await env.jobs.repository.get(env.project.project_id,queued.job.job_id)
        assert row.job.status=='awaiting_review',row.job.error
        assert row.analysis.transcript.provenance['explicit_mock_cpu'] is True
        assert row.analysis.transcript.provenance['model_inferences']==0 and provider.calls==1
        async with env.sessions() as session:
            after=await session.scalar(select(AutoEditJobORM))
            assert after.provider_json==binding and after.custody_sha256==custody_sha
            usages=(await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.provider_key==provider.key))).all()
            assert len(usages)==1 and usages[0].metadata_json['receipt']['provider_key']==provider.key
        costs=await env.platform.list_cost_records(env.project.project_id)
        asr=[c for c in costs if c.provider_usage_id==usages[0].usage_id]
        assert len(asr)==1 and asr[0].estimated_cost is None and asr[0].actual_cost==0
        await env.jobs.process(row.job.job_id)
        replay=await env.jobs.create(env.project.project_id,env.payload,'usr:fixture-editor')
        assert replay.job.job_id==row.job.job_id and provider.calls==1
    finally:await env.engine.dispose()
