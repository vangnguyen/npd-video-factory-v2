"""Actual isolated SQLite/local storage/ASGI; renderer and QC are explicit fakes.

No model/provider/network/Remotion execution and no Owner/media-quality claim.
"""
import asyncio
import copy
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import subprocess
from types import SimpleNamespace
from botocore.config import Config

import httpx
import pytest
from sqlalchemy import select, update

from app.db import AssetORM, CostRecordORM, ProviderUsageORM
from app.main import app
from app.production_db import ProductionRenderJobORM, ProductionEventORM
from app.production_models import ProductionPackageCreateRequest, RenderCreateRequest, ApprovalRequest
from app.production_qc import ProductionQCError
from app.production_service import ProductionRenderProcessor, DeterministicTimelineRenderEngine
from app.production_logic import TimelineRenderContractValidator
from app.failed_render_evidence import (FailureEvidencePolicy, PreparedEvidence, prepare, upload, artifact_read,
    context, digest, reservation_id, RESERVATION_EVENT)
from app import failed_render_evidence as retention
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_mvp1_multi_input import env, author, timeline, ROOT
from test_audio_subtitle_render_qc import DeterministicAudioEngine


class RejectedFixtureQC:
    async def inspect(self, path, **kwargs):
        payload=path.read_bytes()
        raise ProductionQCError('EXPLICIT_FAKE_QC_FAILURE_NOT_MEDIA_ACCEPTANCE', {
            'status':'failed', 'fixture':True, 'not_real_media_QC':True, 'publishing_blocked':True,
            'checksum_sha256':hashlib.sha256(payload).hexdigest(), 'size_bytes':len(payload),
            'failures':['explicit fixture failure']})


async def queued(env, *, policy=None):
    version=await author(env, original='Xin chào.')
    built=await timeline(env,version)
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    render=await env.package.enqueue_review(env.project.project_id,RenderCreateRequest(
        expected_timeline_version=built.current_version, expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    worker=ProductionRenderProcessor(repository=env.production,platform=env.platform,asset_repository=env.assets,
        object_storage=env.storage,renderer=DeterministicTimelineRenderEngine(),qc=RejectedFixtureQC(),
        tts_provider=object(),audio_engine=DeterministicAudioEngine(),
        manifest_validator=TimelineRenderContractValidator(ROOT/'packages/contracts/timeline-render.schema.json'),
        staging_root=env.tmp/'retention-stage',brand_name='EXPLICIT RETENTION FIXTURE',failed_evidence_policy=policy)
    return worker,render


async def counts(env):
    async with env.factory() as session:
        return {model.__tablename__:len((await session.scalars(select(model))).all())
            for model in (AssetORM,CostRecordORM,ProviderUsageORM,ProductionEventORM)}


async def ledger(env, render):
    async with env.factory() as session:
        row=await session.get(ProductionEventORM,reservation_id(render.render_id))
        return copy.deepcopy(row.payload_json)


async def duplicate_running(env, first, identity='rnd_other_retention_fixture'):
    async with env.factory() as session,session.begin():
        row=await session.get(ProductionRenderJobORM,first.render_id)
        values={column.name:copy.deepcopy(getattr(row,column.name)) for column in row.__table__.columns}
        values.update(render_id=identity,version=row.version+1,status='running')
        session.add(ProductionRenderJobORM(**values))
    return await env.production.get_render(identity)


@pytest.fixture
async def bound_app(env):
    old=dict(app.state._state)
    app.state.production_package_service=env.package
    app.state.auto_edit_repository=env.assets
    app.state.object_storage=env.storage
    app.state.production_render_download_root=env.tmp/'downloads'
    install_test_human_auth(app,platform_repository=env.platform)
    yield app
    object.__setattr__(app.state,'_state',old)


@pytest.mark.asyncio
async def test_worker_preserves_private_rejected_bytes_without_assets_or_approval(env):
    worker,job=await queued(env); before=await counts(env)
    result=await worker.process(job.render_id)
    assert result.status=='failed_qc' and result.error_code=='QC_FAILED'
    assert result.failure_reason=='EXPLICIT_FAKE_QC_FAILURE_NOT_MEDIA_ACCEPTANCE'
    assert result.output_asset_id is None and result.playback_url is None and not result.publishing_allowed
    evidence=result.manifest['failed_qc_evidence']; assert evidence['status']=='retained'
    assert len(evidence['artifacts'])==6 and not evidence['errors']
    saved=await ledger(env,result)
    for item in evidence['artifacts']:
        proof,_,_=artifact_read(result,saved,item['name'])
        target=env.tmp/('retained-'+item['name'])
        await proof.download(env.storage,target)
        assert hashlib.sha256(target.read_bytes()).hexdigest()==item['checksum_sha256']
    assert next(i for i in evidence['artifacts'] if i['name']=='video')['checksum_sha256']==result.qc_report['checksum_sha256']
    after=await counts(env)
    assert all(after[name]==before[name] for name in ('assets','cost_records','provider_usage'))
    assert after['production_events']==before['production_events']+2  # reservation and terminal
    assert not (worker.staging_root/job.render_id).exists()
    with pytest.raises(Exception,match='passing QC'):
        await env.package.request_approval(env.project.project_id,ApprovalRequest(review_render_id=result.render_id))
    assert (await worker.process(job.render_id)).model_dump()==result.model_dump()
    assert await counts(env)==after


@pytest.mark.asyncio
async def test_real_QC_tuple_intervals_survive_SQL_JSON_roundtrip(env):
    worker,job=await queued(env)
    async def qc(path,**kwargs):
        raise ProductionQCError('explicit tuple report fixture',{'status':'failed',
            'freeze_intervals':[(0.0,2.0)],'checksum_sha256':hashlib.sha256(path.read_bytes()).hexdigest()})
    worker.qc.inspect=qc
    result=await worker.process(job.render_id)
    assert result.status=='failed_qc' and result.error_code=='QC_FAILED'
    assert result.qc_report['freeze_intervals']==[[0.0,2.0]]
    assert result.manifest['failed_qc_evidence']['status']=='retained'
    assert result.failure_reason=='explicit tuple report fixture'


@pytest.mark.asyncio
@pytest.mark.parametrize('stage',['prepare','upload','commit'])
async def test_retention_failure_keeps_original_qc_and_conservative_charge(env,monkeypatch,stage):
    worker,job=await queued(env)
    if stage=='prepare':
        def rejected(**kwargs):raise OSError('private path or secret must not be exported')
        monkeypatch.setattr(retention,'prepare',rejected)
    elif stage=='upload':
        def rejected(*args):raise OSError('private storage path or secret must not be exported')
        monkeypatch.setattr(retention,'_local_upload',rejected)
    else:
        original=env.production.commit_failed_evidence; calls=[]
        async def failed_once(*args,**kwargs):
            calls.append(1)
            if len(calls)==1:raise OSError('simulated one-time SQL attach failure')
            return await original(*args,**kwargs)
        monkeypatch.setattr(env.production,'commit_failed_evidence',failed_once)
    result=await worker.process(job.render_id)
    assert result.status=='failed_qc' and result.error_code=='QC_FAILED'
    assert result.failure_reason=='EXPLICIT_FAKE_QC_FAILURE_NOT_MEDIA_ACCEPTANCE'
    evidence=result.manifest['failed_qc_evidence']
    assert evidence['status']=='failed' and evidence['artifacts']==[] and evidence['errors']
    assert 'secret' not in json.dumps(evidence) and 'private storage' not in json.dumps(evidence)
    assert (await ledger(env,result))['reserved_bytes']==evidence['reserved_bytes']
    before=await counts(env); await worker.process(job.render_id); assert await counts(env)==before


@pytest.mark.asyncio
async def test_reservation_transaction_failure_gets_metadata_only_QC_fallback(env,monkeypatch):
    worker,job=await queued(env);original=env.production._failed_evidence_locked;calls=[]
    async def failed_once(session,expected):
        value=await original(session,expected);calls.append(1)
        if len(calls)==1:raise OSError('explicit first writer transaction rollback')
        return value
    monkeypatch.setattr(env.production,'_failed_evidence_locked',failed_once)
    result=await worker.process(job.render_id)
    assert result.status=='failed_qc' and result.error_code=='QC_FAILED'
    value=result.manifest['failed_qc_evidence']
    assert value['status']=='failed' and value['artifacts']==[] and value['reserved_bytes']==0
    assert value['errors']==['FAILED_EVIDENCE_RESERVATION_FAILED']
    assert result.failure_reason=='EXPLICIT_FAKE_QC_FAILURE_NOT_MEDIA_ACCEPTANCE'


@pytest.mark.asyncio
@pytest.mark.parametrize('failure',['reserve','attach','unknown_reservation_commit'])
async def test_unavailable_terminal_persistence_raises_original_QC_not_storage_error(env,monkeypatch,failure):
    worker,job=await queued(env);original=env.production.reserve_failed_evidence;calls=[]
    async def unavailable(*args,**kwargs):raise OSError('EXPLICIT PRIVATE STORAGE/SQL FAILURE')
    if failure=='attach':monkeypatch.setattr(env.production,'commit_failed_evidence',unavailable)
    elif failure=='reserve':monkeypatch.setattr(env.production,'reserve_failed_evidence',unavailable)
    else:
        async def committed_then_unknown(*args,**kwargs):
            result=await original(*args,**kwargs);calls.append(result)
            if len(calls)==1:raise OSError('unknown reservation commit outcome')
            return result
        monkeypatch.setattr(env.production,'reserve_failed_evidence',committed_then_unknown)
    with pytest.raises(ProductionQCError,match='EXPLICIT_FAKE_QC_FAILURE_NOT_MEDIA_ACCEPTANCE') as caught:
        await worker.process(job.render_id)
    assert caught.value.report['not_real_media_QC'] is True
    current=await env.production.get_render(job.render_id)
    assert current.status=='running' and current.qc_status=='pending' and current.output_asset_id is None
    assert not (worker.staging_root/job.render_id).exists()
    if failure!='reserve':
        saved=await ledger(env,current);assert saved['reserved_bytes']>0
        if failure=='unknown_reservation_commit':
            assert calls[0]['owned'] and not calls[1]['owned']
            assert not list(env.storage.root.rglob('failed-output.bin'))


@pytest.mark.asyncio
async def test_project_quota_serializes_competing_reservations_and_one_owner_per_render(env):
    worker,first=await queued(env)
    await env.production.start_render(first.render_id)
    first=await env.production.get_render(first.render_id); second=await duplicate_running(env,first)
    policy=FailureEvidencePolicy(per_render_bytes=80,per_project_bytes=100)
    plan=[{'name':'qc','size_bytes':60,'checksum_sha256':'a'*64}]
    results=await asyncio.gather(*(env.production.reserve_failed_evidence(job,planned=plan,policy=policy) for job in (first,second)))
    assert all(r['owned'] for r in results)
    assert sorted(r['ledger']['claim_status'] for r in results)==['quota_exceeded','reserved']
    assert sum(r['ledger']['reserved_bytes'] for r in results)==60
    again=await env.production.reserve_failed_evidence(first,planned=plan,policy=policy)
    assert again['owned'] is False and again['ledger']==results[0]['ledger']


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',[True,'1',-1])
async def test_malformed_ledger_charge_fails_closed_without_coercion(env,bad):
    _,job=await queued(env); await env.production.start_render(job.render_id)
    job=await env.production.get_render(job.render_id)
    prior=await duplicate_running(env,job)
    claim=await env.production.reserve_failed_evidence(prior,planned=[],policy=FailureEvidencePolicy())
    async with env.factory() as session,session.begin():
        row=await session.get(ProductionEventORM,reservation_id(prior.render_id))
        row.payload_json={**row.payload_json,'reserved_bytes':bad}
    current=await env.production.reserve_failed_evidence(job,planned=[{'name':'qc','size_bytes':1,'checksum_sha256':'b'*64}],policy=FailureEvidencePolicy())
    assert current['owned'] and current['ledger']['claim_status']=='ledger_invalid'
    assert current['ledger']['reserved_bytes']==0


@pytest.mark.asyncio
@pytest.mark.parametrize('terminal',['ready','awaiting_review','failed','failed_qc','cancelled','stale'])
async def test_late_terminal_during_upload_never_overwritten(env,monkeypatch,terminal):
    worker,job=await queued(env); entered=threading.Event();resume=threading.Event()
    original=retention._local_upload
    def paused(*args):
        entered.set();assert resume.wait(15);return original(*args)
    monkeypatch.setattr(retention,'_local_upload',paused)
    task=asyncio.create_task(worker.process(job.render_id))
    try:
        assert await asyncio.to_thread(entered.wait,10)
        async with env.factory() as session,session.begin():
            await session.execute(update(ProductionRenderJobORM).where(ProductionRenderJobORM.render_id==job.render_id)
                .values(status=terminal,cancellation_requested=terminal in {'cancelled','stale'}))
        observed=await env.production.get_render(job.render_id); before=await counts(env)
        resume.set();result=await asyncio.wait_for(task,20)
        assert result.model_dump()==observed.model_dump()
        assert (await env.production.get_render(job.render_id)).model_dump()==observed.model_dump()
        assert await counts(env)==before and 'failed_qc_evidence' not in result.manifest
        assert (await ledger(env,result))['reserved_bytes']>0
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_task_cancellation_drains_owned_upload_before_stage_cleanup(env,monkeypatch):
    worker,job=await queued(env);entered=threading.Event();resume=threading.Event()
    original=retention._local_upload
    def paused(*args):
        entered.set();assert resume.wait(15);return original(*args)
    monkeypatch.setattr(retention,'_local_upload',paused)
    task=asyncio.create_task(worker.process(job.render_id))
    try:
        assert await asyncio.to_thread(entered.wait,10)
        task.cancel();await asyncio.sleep(.05);task.cancel();await asyncio.sleep(.05)
        assert not task.done() and (worker.staging_root/job.render_id).exists()
        resume.set()
        with pytest.raises(asyncio.CancelledError):await asyncio.wait_for(task,20)
        current=await env.production.get_render(job.render_id)
        assert current.status=='failed_qc' and current.error_code=='QC_FAILED'
        assert not (worker.staging_root/job.render_id).exists()
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_diagnostic_HTTP_exact_GET_HEAD_range_and_unchanged_output_gate(env,bound_app):
    worker,job=await queued(env);result=await worker.process(job.render_id)
    url=f'/api/v1/projects/{job.project_id}/renders/{job.render_id}'
    item=next(i for i in result.manifest['failed_qc_evidence']['artifacts'] if i['name']=='video')
    expected=env.storage._path(item['object_key']).read_bytes()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bound_app),base_url='http://test',headers=TEST_HUMAN_HEADERS) as client:
        response=await client.get(url+'/diagnostics/video')
        assert response.status_code==200 and response.content==expected
        assert response.headers['cache-control']=='no-store' and response.headers['x-content-type-options']=='nosniff'
        assert response.headers['etag']=='"'+item['checksum_sha256']+'"'
        assert response.headers['content-type']=='application/octet-stream'
        head=await client.head(url+'/diagnostics/video');assert head.status_code==200 and head.content==b''
        part=await client.get(url+'/diagnostics/video',headers={'Range':'bytes=0-15'})
        assert part.status_code==206 and part.content==expected[:16]
        assert (await client.get(url+'/content')).status_code==404


@pytest.mark.asyncio
@pytest.mark.parametrize('scope',['anonymous','foreign','invalid_name'])
async def test_diagnostic_auth_and_scope_reject_before_storage(env,bound_app,monkeypatch,scope):
    worker,job=await queued(env);await worker.process(job.render_id);attempts=[]
    async def forbidden(**kwargs):attempts.append(1);raise AssertionError('NO_FOREIGN_STORAGE')
    monkeypatch.setattr(env.storage,'download_file',forbidden)
    project='prj_foreign_fixture' if scope=='foreign' else job.project_id
    name='unknown' if scope=='invalid_name' else 'video'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bound_app),base_url='http://test',
            headers={} if scope=='anonymous' else TEST_HUMAN_HEADERS) as client:
        response=await client.get(f'/api/v1/projects/{project}/renders/{job.render_id}/diagnostics/{name}')
    assert response.status_code in {401,403,404} and attempts==[]


@pytest.mark.asyncio
async def test_diagnostic_byte_tamper_is_not_a_download_or_cache_miss(env,bound_app):
    worker,job=await queued(env);result=await worker.process(job.render_id)
    item=next(i for i in result.manifest['failed_qc_evidence']['artifacts'] if i['name']=='video')
    path=env.storage._path(item['object_key']);path.write_bytes(b'x'*item['size_bytes'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bound_app),base_url='http://test',headers=TEST_HUMAN_HEADERS) as client:
        response=await client.get(f'/api/v1/projects/{job.project_id}/renders/{job.render_id}/diagnostics/video')
    assert response.status_code==409 and response.json()['detail']['code']=='ARTIFACT_BYTES_CHANGED'
    assert (await env.production.get_render(job.render_id)).status=='failed_qc'


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['cancel_request','timeline_version'])
async def test_real_cancel_or_timeline_invalidation_during_retention_wins(env,monkeypatch,change):
    worker,job=await queued(env);entered=threading.Event();resume=threading.Event();original=retention._local_upload
    def paused(*args):entered.set();assert resume.wait(15);return original(*args)
    monkeypatch.setattr(retention,'_local_upload',paused)
    task=asyncio.create_task(worker.process(job.render_id))
    try:
        assert await asyncio.to_thread(entered.wait,10)
        if change=='cancel_request':
            await env.production.cancel_render(job.project_id,job.render_id,'explicit-fixture-editor')
        else:
            previous=await env.timeline.get_timeline(job.project_id)
            await env.timeline.commit_mutation(project_id=job.project_id,expected_version=previous.current_version,
                snapshot=previous.snapshot,mutation={'type':'explicit-fixture-edit'},actor_ref='fixture-editor')
        resume.set();result=await asyncio.wait_for(task,20)
        assert result.status==('cancelled' if change=='cancel_request' else 'stale')
        assert 'failed_qc_evidence' not in result.manifest and result.output_asset_id is None
        assert (await ledger(env,result))['reserved_bytes']>0
    finally:
        resume.set()
        if not task.done():task.cancel();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_late_event_failure_rolls_back_attach_then_metadata_only_fallback(env,monkeypatch):
    worker,job=await queued(env);original=env.production._event;fired=[]
    async def rejected_once(session,**kwargs):
        await original(session,**kwargs)
        if kwargs['event_type']=='render.failed_qc' and not fired:
            fired.append(1);await session.flush();raise OSError('explicit late flush fixture')
    monkeypatch.setattr(env.production,'_event',rejected_once)
    before=await counts(env);result=await worker.process(job.render_id);after=await counts(env)
    assert result.status=='failed_qc' and result.error_code=='QC_FAILED'
    assert result.manifest['failed_qc_evidence']['artifacts']==[]
    assert result.manifest['failed_qc_evidence']['errors']==['FAILED_EVIDENCE_COMMIT_FAILED']
    assert after['production_events']==before['production_events']+2
    assert (await ledger(env,result))['reserved_bytes']>0


@pytest.mark.asyncio
@pytest.mark.parametrize('bad',['qc_hash','absent_qc_hash'])
async def test_QC_observed_hash_and_retained_hash_are_distinct_claims(env,bad):
    worker,job=await queued(env)
    async def qc(path,**kwargs):
        report={'status':'failed','fixture':True}
        if bad=='qc_hash':report['checksum_sha256']='0'*64
        raise ProductionQCError('EARLY_OR_CHANGED_FIXTURE_OUTPUT',report)
    worker.qc.inspect=qc
    result=await worker.process(job.render_id);items=result.manifest['failed_qc_evidence']['artifacts']
    assert result.status=='failed_qc' and result.failure_reason=='EARLY_OR_CHANGED_FIXTURE_OUTPUT'
    if bad=='qc_hash':assert not any(i['name']=='video' for i in items)
    else:assert any(i['name']=='video' for i in items) and 'checksum_sha256' not in result.qc_report


@pytest.mark.asyncio
async def test_oversized_files_are_skipped_without_bypassing_render_limit(env):
    policy=FailureEvidencePolicy(per_render_bytes=1024**2,per_project_bytes=2*1024**2,video_bytes=10,audio_bytes=10)
    worker,job=await queued(env,policy=policy);result=await worker.process(job.render_id)
    value=result.manifest['failed_qc_evidence']
    assert result.status=='failed_qc' and value['status']=='partial'
    assert not any(i['name'] in {'video','audio'} for i in value['artifacts'])
    assert value['reserved_bytes']<=policy.per_render_bytes and 'FAILED_EVIDENCE_FILE_REJECTED' in value['errors']


@pytest.mark.asyncio
@pytest.mark.parametrize('tamper',['bool_charge','output_pointer','pending_qc'])
async def test_diagnostic_descriptor_or_state_tamper_rejected_before_storage(env,bound_app,monkeypatch,tamper):
    worker,job=await queued(env);await worker.process(job.render_id)
    async with env.factory() as session,session.begin():
        row=await session.get(ProductionRenderJobORM,job.render_id)
        if tamper=='bool_charge':
            value=copy.deepcopy(row.manifest_json);value['failed_qc_evidence']['reserved_bytes']=True;row.manifest_json=value
        elif tamper=='output_pointer':row.output_asset_id=await session.scalar(select(AssetORM.asset_id).limit(1))
        else:row.qc_status='pending'
    calls=[]
    async def forbidden(**kwargs):calls.append(1);raise AssertionError('TAMPER_MUST_FAIL_BEFORE_STORAGE')
    monkeypatch.setattr(env.storage,'download_file',forbidden)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bound_app),base_url='http://test',headers=TEST_HUMAN_HEADERS) as client:
        response=await client.get(f'/api/v1/projects/{job.project_id}/renders/{job.render_id}/diagnostics/video')
    assert response.status_code==409 and not calls


@pytest.mark.asyncio
async def test_diagnostic_parent_change_after_download_rejects_before_body(env,bound_app,monkeypatch):
    worker,job=await queued(env);await worker.process(job.render_id);original=env.storage.download_file
    async def changed(**kwargs):
        await original(**kwargs)
        async with env.factory() as session,session.begin():
            await session.execute(update(ProductionRenderJobORM).where(ProductionRenderJobORM.render_id==job.render_id)
                .values(status='ready'))  # explicit adversarial SQL fixture, not acceptance
    monkeypatch.setattr(env.storage,'download_file',changed)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(bound_app),base_url='http://test',headers=TEST_HUMAN_HEADERS) as client:
        response=await client.get(f'/api/v1/projects/{job.project_id}/renders/{job.render_id}/diagnostics/video')
    assert response.status_code==409 and response.json()['detail']['code']=='FAILED_EVIDENCE_CHANGED'


@pytest.mark.asyncio
async def test_sealed_descriptor_never_reopens_replaced_renderer_path(env,tmp_path):
    work=tmp_path/'sealed';work.mkdir();source=work/'review.mp4';source.write_bytes(b'original rejected fixture bytes')
    report={'status':'failed','checksum_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
    prepared=prepare(workdir=work,render_kind='review',qc_report=report,manifest={},evidence={},policy=FailureEvidencePolicy())
    outside=tmp_path/'outside';outside.write_bytes(b'PRIVATE BYTES MUST NEVER BE REOPENED')
    source.unlink();os.link(outside,source)
    fake=SimpleNamespace(workspace_id=env.workspace.workspace_id,project_id=env.project.project_id,render_id='rnd_sealed_fixture')
    try:
        items,errors=await upload(storage=env.storage,prepared=prepared,render=fake,attempt_id='a'*32,policy=FailureEvidencePolicy())
        item=next(i for i in items if i['name']=='video')
        assert env.storage._path(item['object_key']).read_bytes()==b'original rejected fixture bytes'
        assert outside.read_bytes()==b'PRIVATE BYTES MUST NEVER BE REOPENED'
    finally:prepared.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('profile',['bounded','unbounded','unsupported'])
async def test_S3_held_descriptor_contract_and_unknown_adapter_fail_closed(tmp_path,profile):
    work=tmp_path/'s3-fixture';work.mkdir()
    prepared=prepare(workdir=work,render_kind='review',qc_report={'status':'failed'},manifest={},evidence={},policy=FailureEvidencePolicy())
    calls=[]
    def put(**kwargs):
        body=kwargs.pop('Body');payload=b''
        while chunk:=body.read(32768):payload+=chunk
        assert kwargs['ACL']=='private' and len(payload)==kwargs['ContentLength']
        calls.append((payload,kwargs))
    storage=retention.S3ObjectStorageProvider.__new__(retention.S3ObjectStorageProvider)
    storage.bucket='explicit-fixture-no-network'
    storage.client=SimpleNamespace(meta=SimpleNamespace(config=Config(connect_timeout=5 if profile=='bounded' else 60,
        read_timeout=30,retries={'total_max_attempts':1})),put_object=put)
    if profile=='unsupported':storage=SimpleNamespace(name='unknown-fixture')
    render=SimpleNamespace(workspace_id='wsp_fixture',project_id='prj_fixture',render_id='rnd_fixture')
    try:
        items,errors=await upload(storage=storage,prepared=prepared,render=render,attempt_id='b'*32,policy=FailureEvidencePolicy())
        if profile=='bounded':assert len(calls)==len(items)==3
        else:assert calls==[] and items==[] and errors
    finally:prepared.close()


@pytest.mark.asyncio
async def test_S3_SDK_diagnostics_do_not_leak_private_object_keys(tmp_path):
    work=tmp_path/'sdk-privacy';work.mkdir();records=[]
    logger=logging.getLogger('botocore.endpoint')
    class Sink(logging.Handler):
        def emit(self,record):records.append(record.getMessage())
    sink=Sink();oldlevel=logger.level;logger.addHandler(sink);logger.setLevel(logging.DEBUG)
    def put(**kwargs):
        logger.debug('EXPLICIT_PRIVATE_FIXTURE_KEY %s',kwargs['Key'])
        while kwargs['Body'].read(32768):pass
    storage=retention.S3ObjectStorageProvider.__new__(retention.S3ObjectStorageProvider)
    storage.bucket='explicit-fixture-no-network';storage.client=SimpleNamespace(meta=SimpleNamespace(
        config=Config(connect_timeout=5,read_timeout=30,retries={'total_max_attempts':1})),put_object=put)
    prepared=prepare(workdir=work,render_kind='review',qc_report={'status':'failed'},manifest={},evidence={},policy=FailureEvidencePolicy())
    render=SimpleNamespace(workspace_id='wsp_fixture',project_id='prj_fixture',render_id='rnd_fixture')
    try:
        items,_=await upload(storage=storage,prepared=prepared,render=render,attempt_id='c'*32,policy=FailureEvidencePolicy())
        assert len(items)==3 and records==[]
        logger.debug('EXPLICIT_PUBLIC_CONTROL')
        assert records==['EXPLICIT_PUBLIC_CONTROL']
    finally:
        prepared.close();logger.removeHandler(sink);logger.setLevel(oldlevel)


@pytest.mark.asyncio
async def test_unresolved_in_root_junction_cannot_redirect_private_upload(env,tmp_path):
    work=tmp_path/'junction-source';work.mkdir()
    prepared=prepare(workdir=work,render_kind='review',qc_report={'status':'failed'},manifest={},evidence={},policy=FailureEvidencePolicy())
    parent=env.storage.root/'workspaces';parent.mkdir(exist_ok=True)
    junction=parent/'wsp_redirect_fixture';target=env.storage.root/'other-project-redirect';target.mkdir()
    assert env.storage.root in junction.absolute().parents and env.storage.root in target.absolute().parents
    if os.name=='nt':
        quoted=lambda p:"'"+str(p).replace("'","''")+"'"
        subprocess.run(['pwsh','-NoProfile','-Command',f'New-Item -ItemType Junction -Path {quoted(junction)} -Target {quoted(target)} -ErrorAction Stop | Out-Null'],
            check=True,capture_output=True,timeout=15)
    else:os.symlink(target,junction,target_is_directory=True)
    render=SimpleNamespace(workspace_id='wsp_redirect_fixture',project_id='prj_fixture',render_id='rnd_fixture')
    try:
        items,errors=await upload(storage=env.storage,prepared=prepared,render=render,attempt_id='d'*32,policy=FailureEvidencePolicy())
        assert items==[] and 'FAILED_EVIDENCE_UPLOAD_FAILED' in errors
        assert list(target.rglob('*'))==[]
    finally:prepared.close()


@pytest.mark.parametrize('field,value',[('per_render_bytes',True),('per_project_bytes','128'),('video_bytes',-1),('metadata_bytes',0),('retention_days',31)])
def test_policy_requires_strict_bounded_units(field,value):
    with pytest.raises(ValueError,match='POLICY_INVALID'):FailureEvidencePolicy(**{field:value})
