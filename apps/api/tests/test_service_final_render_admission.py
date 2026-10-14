"""Actual signed ASGI/SQLite admission; unrendered review/approval fixtures only."""
from types import SimpleNamespace
import httpx
import pytest
from fastapi import Depends
from sqlalchemy import func, select

from app.bridge_auth import ServiceIdentity
from app.content_models import StoryboardScene
from app.human_auth import authorize_human_request
from app.production_db import ProductionRenderJobORM, ProductionEventORM
from app.production_models import (ProductionPackageCreateRequest, ApprovalRequest, ApprovalDecisionRequest,
    AudioMixReplaceRequest, MixConfig, VoiceConfig)
from app.service_api_repository import ServiceOperationORM
from app.timeline_models import TimelineCreateRequest
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_mvp1_multi_input import env, image, author
from test_service_api import application, signed


@pytest.fixture
async def final_api(env):
    photo=await image(env)
    content=await author(env,original='Explicit script fixture without any synthesis.',scenes=[
        StoryboardScene(scene_id='scene_fixture',narration='Explicit script fixture without any synthesis.',
            media_strategy='user_asset',asset_id=photo.asset_id)])
    timeline=await env.service.create(env.project.project_id,TimelineCreateRequest(
        source_kind='storyboard_media',content_version_id=content.project_version_id))
    package=await env.package.create_or_refresh(env.project.project_id,ProductionPackageCreateRequest())
    from test_agent_hub_bridge import FakeRedis
    app=application(SimpleNamespace(platform=env.platform,workspace=env.workspace,redis=FakeRedis()))
    app.state.production_package_service=env.package
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-final-admission') as client:
        yield SimpleNamespace(env=env,app=app,client=client,timeline=timeline,package=package)


def body(a,approval='apr_missing_explicit_fixture'):
    return {'expected_timeline_version':a.timeline.current_version,
        'expected_subtitle_version':a.package.subtitle.version,'expected_audio_version':a.package.audio_mix.version,
        'approval_id':approval,'actor_ref':'forged-client-actor','profile':'vertical-1080x1920'}


async def approved(a):
    e=a.env
    review=await e.production.create_render(project_id=e.project.project_id,
        expected_timeline_version=a.timeline.current_version,expected_subtitle_version=a.package.subtitle.version,
        expected_audio_version=a.package.audio_mix.version,render_kind='review',profile='review-540x960',
        actor_ref='explicit-unrendered-review-fixture')
    await e.production.start_render(review.render_id)
    await e.production.complete_render(review.render_id,output_asset_id=None,
        qc_report={'fixture':True,'not_real_render_qc':True},manifest={'fixture':True,'not_owner_uat':True})
    approval=await e.package.request_approval(e.project.project_id,ApprovalRequest(review_render_id=review.render_id,
        requester_ref='explicit-fixture-reviewer'))
    await e.package.decide_approval(e.project.project_id,approval.approval_id,
        ApprovalDecisionRequest(decision='approved',reviewer_ref='explicit-fixture-reviewer',
            comment='Fixture decision, never Owner acceptance'))
    return approval.approval_id


async def finals(a):
    async with a.env.factory() as session:
        return list((await session.scalars(select(ProductionRenderJobORM).where(
            ProductionRenderJobORM.render_kind=='final'))).all())


async def test_signed_missing_approval_returns_canonical_conflict_and_replay_never_queues(final_api):
    a=final_api;path=f'/v1/projects/{a.env.project.project_id}/render';payload=body(a)
    first=await signed(a.client,'POST',path,payload,key='final-missing-approval-fixture-01')
    assert first.status_code==409,first.text
    assert first.headers['Cache-Control']=='no-store' and 'AUTH_UNAVAILABLE' not in first.text
    second=await signed(a.client,'POST',path,payload,key='final-missing-approval-fixture-01')
    assert second.status_code==409 and second.json()==first.json()
    assert second.headers['X-Idempotent-Replay']=='true'
    assert await finals(a)==[] and a.env.queue.values==[]


async def test_signed_approved_final_uses_verified_service_actor_without_human_or_redispatch(final_api):
    a=final_api;approval=await approved(a);path=f'/v1/projects/{a.env.project.project_id}/render'
    # Final queueing is service capability admission; decisions/publication and
    # private playback keep their own human policies.
    a.app.state.human_write_enabled=False;a.app.state.human_auth_verifier=None
    payload=body(a,approval)
    first=await signed(a.client,'POST',path,payload,key='final-approved-service-fixture-01')
    assert first.status_code==202,first.text
    value=first.json();assert value['manifest']['requested_by']=='svc:agent-hub'
    assert value['status']=='queued' and value['publishing_allowed'] is False
    assert len(a.env.queue.values)==1
    second=await signed(a.client,'POST',path,payload,key='final-approved-service-fixture-01')
    assert second.status_code==202 and second.json()==value and second.headers['X-Idempotent-Replay']=='true'
    assert len(a.env.queue.values)==1 and len(await finals(a))==1
    async with a.env.factory() as session:
        event=await session.scalar(select(ProductionEventORM).where(
            ProductionEventORM.entity_id==value['render_id'],ProductionEventORM.event_type=='render.final_queued'))
        assert event.actor_ref=='svc:agent-hub'


@pytest.mark.parametrize('denial,status',[('capability',403),('workspace',404),('signature',401)])
async def test_signed_final_admission_denial_precedes_canonical_queue(final_api,denial,status):
    a=final_api;identity=a.app.state.bridge_auth_verifier.identities['agent-hub'];extra=None
    if denial!='signature':
        grants={a.env.workspace.workspace_id:('project.read',)} if denial=='capability' else {}
        a.app.state.bridge_auth_verifier.identities={'agent-hub':ServiceIdentity(identity.service_id,
            identity.roles,identity.keys,grants)}
    else:extra={'X-NPD-Signature':'0'*64}
    response=await signed(a.client,'POST',f'/v1/projects/{a.env.project.project_id}/render',body(a),
        key='final-denied-service-fixture-'+denial,extra=extra)
    assert response.status_code==status,response.text
    assert await finals(a)==[] and a.env.queue.values==[]
    async with a.env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ServiceOperationORM))==0


async def test_stale_approval_still_rejected_without_final_queue(final_api):
    a=final_api;approval=await approved(a)
    a.package=await a.env.package.replace_audio_mix(a.env.project.project_id,AudioMixReplaceRequest(
        expected_timeline_version=a.timeline.current_version,expected_audio_version=a.package.audio_mix.version,
        config=MixConfig(voice=VoiceConfig(speed=1.05))))
    response=await signed(a.client,'POST',f'/v1/projects/{a.env.project.project_id}/render',body(a,approval),
        key='final-stale-service-fixture-01')
    assert response.status_code==409,response.text
    assert await finals(a)==[] and a.env.queue.values==[]


@pytest.mark.parametrize('role,status',[('editor',202),('viewer',403)])
async def test_existing_human_final_handler_keeps_role_and_verified_actor(final_api,role,status):
    from app.production_routes import router
    a=final_api;approval=await approved(a)
    a.app.include_router(router,dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(a.app,platform_repository=a.env.platform,platform_role=None,
        workspace_roles={a.env.workspace.workspace_id:role})
    response=await a.client.post(f'/api/v1/projects/{a.env.project.project_id}/final-render',
        json=body(a,approval),headers=TEST_HUMAN_HEADERS)
    assert response.status_code==status,response.text
    if role=='editor':
        assert response.json()['manifest']['requested_by']=='usr:test-owner' and len(a.env.queue.values)==1
    else:assert a.env.queue.values==[] and await finals(a)==[]


@pytest.mark.parametrize('action',['approve','publish'])
async def test_service_capability_never_becomes_human_review_or_publication_authority(final_api,action):
    a=final_api
    payload={'approval_id':'apr_explicit_fixture_approval','decision':'approved',
        'reviewer_ref':'forged-human-reviewer'} if action=='approve' else {
        'platform':'youtube','final_render_id':'rnd_explicit_fixture_final','mode':'dry_run',
        'metadata':{'title':'Explicit no-publishing admission fixture','privacy':'private'},
        'actor_ref':'forged-human-owner'}
    response=await signed(a.client,'POST',f'/v1/projects/{a.env.project.project_id}/{action}',payload,
        key='final-human-authority-fixture-'+action)
    assert response.status_code==401,response.text
    assert a.env.queue.values==[] and await finals(a)==[]
    async with a.env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ServiceOperationORM))==0
