"""Owned SQL/ASGI intake recovery; media and human identities are fixtures."""
import hashlib,json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator,FormatChecker
from sqlalchemy import select,func

from app.auto_edit_db import UploadSessionORM
from app.timeline_db import PreviewJobORM,TimelineORM
from app.production_db import ProductionApprovalORM,ProductionEventORM
from app.production_models import ProductionPackageCreateRequest,RenderCreateRequest,ApprovalRequest
from app.service_api_repository import ServiceOperationORM,digest
from app.service_outcome_events import ServiceOutcomeEventORM
from test_service_api_flows import flow,call

async def fail_completion(*_):
    raise RuntimeError('explicit lost outer receipt fixture')

def fail_event(*_):
    raise RuntimeError('explicit transaction event failure fixture')

def upload_payload(flow):
    return {'project_id':flow.project.project_id,'filename':'private-intake-fixture.mp4',
        'media_kind':'video','content_type':'video/mp4','size_bytes':100000,
        'checksum_sha256':hashlib.sha256(b'explicit offline bytes').hexdigest()}

async def prepare_timeline(flow):
    from test_auto_edit_analysis import upload_fixture,synthetic_mp4
    from app.auto_edit_models import AutoEditAnalysisRequest
    from app.timeline_models import TimelineCreateRequest
    upload=await upload_fixture(flow.app.state.upload_service,flow.project,flow.version,synthetic_mp4())
    analysis=await flow.app.state.auto_edit_analysis_service.analyze(flow.project.project_id,
        AutoEditAnalysisRequest(asset_id=upload.asset_id))
    return await flow.app.state.timeline_service.create(flow.project.project_id,TimelineCreateRequest(analysis_id=analysis.analysis_id))

async def prepare_approval(flow):
    head=await prepare_timeline(flow)
    service=flow.app.state.production_package_service
    package=await service.create_or_refresh(flow.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=head.current_version,actor_ref='explicit-editor-fixture'))
    review=await service.enqueue_review(flow.project.project_id,RenderCreateRequest(
        expected_timeline_version=head.current_version,expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version,actor_ref='explicit-editor-fixture'))
    done=await flow.processor.process(review.render_id)
    assert done.status=='awaiting_review',(done.error_code,done.failure_reason)
    return await service.request_approval(flow.project.project_id,ApprovalRequest(
        review_render_id=done.render_id,requester_ref='explicit-editor-fixture'))

async def events(flow):
    reply=await call(flow,'GET','/v1/operation-events?workspace_id='+flow.workspace.workspace_id)
    assert reply.status_code==200,reply.text
    assert reply.json()['delivery_enabled'] is False
    root=Path(__file__).resolve().parents[3]/'packages/contracts'
    items=reply.json()['items']
    for item in items:
        value=item['envelope'];version=value['contract_version']
        schema=json.loads((root/(version+'.schema.json')).read_bytes())
        Draft202012Validator(schema,format_checker=FormatChecker()).validate(value)
        assert item['envelope_sha256']==digest(value)
        assert 'private-intake' not in str(value) and 'private-comment' not in str(value)
    return items

@pytest.mark.asyncio
async def test_intake_commit_replay_does_not_allocate_another_upload_or_folder(flow,monkeypatch):
    monkeypatch.setattr(flow.app.state.service_api_repository,'complete',fail_completion)
    payload=upload_payload(flow)
    assert (await call(flow,'POST','/v1/uploads/init',payload,key='atomic-intake')).status_code==409
    replay=await call(flow,'POST','/v1/uploads/init',payload,key='atomic-intake')
    assert replay.status_code==201 and replay.headers['X-Idempotent-Replay']=='true',replay.text
    uid=replay.json()['upload_id']
    assert flow.app.state.upload_service._upload_folder(uid).is_dir()
    async with flow.factory() as session:
        assert await session.scalar(select(func.count()).select_from(UploadSessionORM))==1
        operation=await session.scalar(select(ServiceOperationORM))
        assert operation.status=='succeeded' and operation.response_json==replay.json()
    items=await events(flow)
    assert len(items)==1 and items[0]['envelope']['payload']['canonical_reference']['upload_id']==uid

@pytest.mark.asyncio
async def test_intake_outbox_failure_rolls_back_upload_and_removes_owned_new_staging(flow,monkeypatch):
    import app.service_outcome_events as outbox
    monkeypatch.setattr(outbox,'event',fail_event)
    service=flow.app.state.upload_service
    before=set(service.staging_root.iterdir()) if service.staging_root.exists() else set()
    assert (await call(flow,'POST','/v1/uploads/init',upload_payload(flow),key='intake-rollback')).status_code==409
    assert set(service.staging_root.iterdir())==before
    async with flow.factory() as session:
        assert await session.scalar(select(func.count()).select_from(UploadSessionORM))==0
        assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==0

@pytest.mark.asyncio
async def test_preview_replay_and_existing_job_capture_do_not_duplicate_jobs_or_queue(flow,monkeypatch):
    await prepare_timeline(flow)
    service=flow.app.state.preview_service
    monkeypatch.setattr(flow.app.state.service_api_repository,'complete',fail_completion)
    path='/v1/projects/'+flow.project.project_id+'/preview'
    payload={}
    assert (await call(flow,'POST',path,payload,key='atomic-preview')).status_code==409
    replay=await call(flow,'POST',path,payload,key='atomic-preview')
    assert replay.status_code==202 and replay.json()['status']=='queued',replay.text
    identity=replay.json()['preview_id']
    assert (await call(flow,'POST',path,payload,key='existing-preview')).status_code==409
    existing=await call(flow,'POST',path,payload,key='existing-preview')
    assert existing.status_code==202 and existing.json()['preview_id']==identity,existing.text
    async with flow.factory() as session:
        assert await session.scalar(select(func.count()).select_from(PreviewJobORM))==1
    assert service.queue.queue==[identity]
    assert len(await events(flow))==2

@pytest.mark.asyncio
async def test_preview_queue_handoff_failure_keeps_receipt_and_existing_recovery_requeues_same_id(flow,monkeypatch):
    await prepare_timeline(flow)
    service=flow.app.state.preview_service
    async def unavailable(*_):raise RuntimeError('explicit Redis handoff outage fixture')
    original=service.queue.rpush
    monkeypatch.setattr(service.queue,'rpush',unavailable)
    path='/v1/projects/'+flow.project.project_id+'/preview'
    assert (await call(flow,'POST',path,{},key='preview-handoff')).status_code==409
    replay=await call(flow,'POST',path,{},key='preview-handoff')
    assert replay.status_code==202,replay.text
    monkeypatch.setattr(service.queue,'rpush',original)
    assert await service.recover_incomplete()==1
    assert service.queue.queue==[replay.json()['preview_id']]
    async with flow.factory() as session:
        assert await session.scalar(select(func.count()).select_from(PreviewJobORM))==1

@pytest.mark.asyncio
async def test_preview_requeue_outbox_failure_leaves_original_failed_job_unchanged(flow,monkeypatch):
    from app.timeline_models import PreviewCreateRequest
    import app.service_outcome_events as outbox
    await prepare_timeline(flow)
    service=flow.app.state.preview_service
    original=await service.enqueue(flow.project.project_id,PreviewCreateRequest())
    await service.repository.fail_preview(original.preview_id,code='EXPLICIT_FIXTURE',reason='explicit offline fixture')
    monkeypatch.setattr(outbox,'event',fail_event)
    path='/v1/projects/'+flow.project.project_id+'/preview'
    assert (await call(flow,'POST',path,{},key='preview-rollback')).status_code==409
    current=await service.get(flow.project.project_id,original.preview_id)
    assert current.status=='failed' and current.error_code=='EXPLICIT_FIXTURE'
    assert len(await events(flow))==0

@pytest.mark.asyncio
@pytest.mark.parametrize('decision',['approved','changes_requested','rejected'])
async def test_human_approval_decision_replays_without_redeciding_or_spoofing_reviewer(flow,monkeypatch,decision):
    approval=await prepare_approval(flow)
    path='/v1/projects/'+flow.project.project_id+'/approve'
    payload={'approval_id':approval.approval_id,'decision':decision,'reviewer_ref':'forged-client-owner','comment':'private-comment'}
    assert (await call(flow,'POST',path,payload,key='atomic-decision')).status_code==401
    monkeypatch.setattr(flow.app.state.service_api_repository,'complete',fail_completion)
    assert (await call(flow,'POST',path,payload,key='atomic-decision',human=True)).status_code==409
    assert (await call(flow,'POST',path,payload,key='atomic-decision')).status_code==401
    replay=await call(flow,'POST',path,payload,key='atomic-decision',human=True)
    assert replay.status_code==200 and replay.json()['status']==decision,replay.text
    assert replay.json()['reviewer_ref']=='usr:test-owner'
    async with flow.factory() as session:
        row=await session.get(ProductionApprovalORM,approval.approval_id)
        assert row.status==decision and row.reviewer_ref=='usr:test-owner'
        count=await session.scalar(select(func.count()).select_from(ProductionEventORM).where(
            ProductionEventORM.event_type=='approval.'+decision))
        assert count==1
    items=await events(flow)
    assert len(items)==1 and items[0]['envelope']['payload']['actor_ref']=='usr:test-owner'
    assert items[0]['envelope']['payload']['canonical_reference']['approval_id']==approval.approval_id

@pytest.mark.asyncio
async def test_approval_outbox_failure_rolls_back_decision_timeline_and_audit(flow,monkeypatch):
    import app.service_outcome_events as outbox
    approval=await prepare_approval(flow)
    monkeypatch.setattr(outbox,'event',fail_event)
    payload={'approval_id':approval.approval_id,'decision':'approved','reviewer_ref':'forged','comment':'private-comment'}
    path='/v1/projects/'+flow.project.project_id+'/approve'
    assert (await call(flow,'POST',path,payload,key='approval-rollback',human=True)).status_code==409
    async with flow.factory() as session:
        row=await session.get(ProductionApprovalORM,approval.approval_id)
        timeline=await session.scalar(select(TimelineORM))
        assert row.status=='awaiting_review' and row.reviewer_ref is None
        assert timeline.approval_status=='awaiting_review' and timeline.approved_timeline_version is None
        assert await session.scalar(select(func.count()).select_from(ProductionEventORM).where(
            ProductionEventORM.event_type=='approval.approved'))==0
        assert await session.scalar(select(func.count()).select_from(ServiceOutcomeEventORM))==0

@pytest.mark.asyncio
async def test_legacy_and_intake_event_contracts_coexist_without_widening_legacy_schema(flow):
    created=await call(flow,'POST','/v1/projects',{'workspace_id':flow.workspace.workspace_id,
        'slug':'mixed-contract-fixture','name':'Explicit mixed contract fixture'},key='old-kind')
    assert created.status_code==201,created.text
    assert (await call(flow,'POST','/v1/uploads/init',upload_payload(flow),key='new-kind')).status_code==201
    items=await events(flow)
    assert [item['envelope']['contract_version'] for item in items]==[
        'agent-hub-service-outcomes.v1','agent-hub-service-outcomes.v2']
    discovery=await call(flow,'GET','/v1/contract')
    assert discovery.json()['outcome_event_contract_versions']==[
        'agent-hub-service-outcomes.v1','agent-hub-service-outcomes.v2']
    async with flow.factory() as session:
        item=await session.scalar(select(ServiceOutcomeEventORM).where(ServiceOutcomeEventORM.operation_id==
            items[1]['envelope']['payload']['operation_id']))
        item.envelope_json={**item.envelope_json,'payload':{**item.envelope_json['payload'],'source_kind':'approval.decide'}}
        item.envelope_sha256=digest(item.envelope_json)
        await session.commit()
    invalid=await call(flow,'GET','/v1/operation-events?workspace_id='+flow.workspace.workspace_id)
    assert invalid.status_code==409 and invalid.json()['detail']['error']['code']=='SERVICE_EVENT_EVIDENCE_INVALID'
