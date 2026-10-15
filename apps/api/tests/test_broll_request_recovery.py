"""Actual authenticated ASGI/SQLite settlement races; synthetic source, no wire."""
import asyncio
import copy
import hashlib
import json
from datetime import timedelta

import httpx
import pytest
from sqlalchemy import select, func

from auth_test_support import TEST_HUMAN_HEADERS, TEST_HUMAN_TOKEN
from test_broll_plan_review import prepare, server, body
from test_sql_broll_review_main import deny_wire
from app.broll_request_recovery_api import router
from app.broll_request_recovery_command import SETTLEMENT_NAMESPACE, LATE_NAMESPACE
from app.human_auth import HumanAuthVerifier
from app.service_api_repository import ServiceOperationORM, digest
from app.media_intelligence_db import MediaPlanORM
from app.db import AssetORM


def stable(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False)


def app_for(env):
    from fastapi import Depends
    from app.human_auth import authorize_human_request
    app = server(env)
    app.include_router(router, dependencies=[Depends(authorize_human_request)])
    return app


async def intent(client, env):
    path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    context = (await client.get(path)).json()
    principal = (await client.get('/api/v1/auth/session')).json()
    boundary = [env['project'].workspace_id, env['project'].project_id, principal,
        env['timeline'].model_dump(mode='json'), env['auto_edit'].model_dump(mode='json'),
        [env['source_asset'].model_dump(mode='json')], None]
    value = {'schema_version': 'broll-plan-pending.v1', 'body': body(context),
        'context': context, 'boundary': stable(boundary), 'session_sha256': digest(principal),
        'credential_sha256': hashlib.sha256(TEST_HUMAN_TOKEN.encode()).hexdigest()}
    raw = stable(value)
    return path, value, {'intent_json': raw, 'intent_sha256': hashlib.sha256(raw.encode()).hexdigest()}


def renew(app, *, role=None, actor=None, remove_old=False):
    registry = app.state.human_auth_verifier.registry
    old = registry.tokens['test-owner']
    token = 'vf1.renewed-owner.' + 'r' * 40
    changes = {'token_id': 'renewed-owner', 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'expires_at': old.expires_at + timedelta(hours=1)}
    if role:
        changes.update(platform_role=role, workspace_roles={'*': role})
    if actor:
        changes['subject'] = actor
    new = old.model_copy(update=changes)
    tokens = {} if remove_old else dict(registry.tokens)
    tokens['renewed-owner'] = new
    app.state.human_auth_verifier = HumanAuthVerifier(registry.model_copy(update={'tokens': tokens}), max_token_ttl_seconds=86400)
    return {'Authorization': 'Bearer ' + token}


async def rows(env):
    async with env['session_factory']() as s:
        values = (await s.scalars(select(ServiceOperationORM))).all()
        return {r.operation_id: {k: copy.deepcopy(getattr(r, k)) for k in ['service_id', 'status', 'request_sha256',
            'response_json', 'response_sha256', 'created_at', 'updated_at']} for r in values}


@pytest.mark.asyncio
async def test_absent_intent_seals_exact_original_namespace_and_late_post_cannot_execute(tmp_path, deny_wire):
    env = await prepare(tmp_path); app = app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://recovery', headers=TEST_HUMAN_HEADERS) as c:
            path, original, payload = await intent(c, env)
            observed = await c.post(path+'/recovery/inspect', json=payload)
            assert observed.status_code == 200, observed.text
            assert observed.json()['original_result'] is None
            assert await rows(env) == {}
            abandon = {**payload, 'observation_sha256': observed.json()['observation_sha256'], 'acknowledged': True}
            sealed = await c.post(path+'/recovery/abandon', json=abandon)
            assert sealed.status_code == 200, sealed.text
            value = sealed.json();assert value['settlement']['abandoned'] is True and value['provider_calls'] == 0
            assert (await c.post(path, json=original['body'])).status_code == 409
            assert (await c.post(path+'/recovery/abandon', json=abandon)).json() == value
            identifier=value['settlement']['settlement_id']
            assert (await c.get(path+'/recovery/settlements/'+identifier)).json() == value
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM)) == 0
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM)) == 1
            assert deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_prepared_response_and_plan_survive_renewed_session_settlement_without_old_registry(tmp_path, deny_wire):
    env = await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path, original, payload=await intent(c,env)
            prepared=await c.post(path,json=original['body']);assert prepared.status_code==201,prepared.text
            result=prepared.json();assert '_recovery_identity' not in result
            before=await rows(env);plan=await env['planner'].get(result['plan']['media_plan_id'])
            c.headers.update(renew(app,remove_old=True))
            observed=await c.post(path+'/recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            assert observed.json()['preserved_plan']==result['plan']
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed.json()['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            identifier=sealed.json()['settlement']['settlement_id']
            assert (await c.get(path+'/recovery/settlements/'+identifier)).json()==sealed.json()
            after=await rows(env)
            for key,value in before.items():assert after[key]==value
            assert await env['planner'].get(plan.media_plan_id)==plan
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_inflight_abandon_fences_late_completion_and_keeps_single_readonly_plan_audit(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env);entered=asyncio.Event();resume=asyncio.Event();calls=[]
    create=env['planner'].create
    async def delayed(**kwargs):
        calls.append(kwargs);entered.set();await resume.wait();return await create(**kwargs)
    env['planner'].create=delayed
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            work=asyncio.create_task(c.post(path,json=original['body']));await asyncio.wait_for(entered.wait(),15)
            before=await rows(env);assert len(before)==1
            observed=await c.post(path+'/recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed.json()['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            resume.set();late=await work;assert late.status_code==409,late.text
            after=await rows(env)
            for key,value in before.items():assert after[key]==value
            identifier=sealed.json()['settlement']['settlement_id']
            audit=(await c.get(path+'/recovery/settlements/'+identifier+'/late-results')).json()
            assert len(audit)==1 and audit[0]['read_only'] is True and audit[0]['plan']
            assert (await c.post(path,json=original['body'])).status_code==409 and len(calls)==1
            assert len([r for r in after.values() if r['service_id']==LATE_NAMESPACE])==1
            assert deny_wire==[]
    finally:resume.set();await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['actor','role','source','intent','legacy-pruned'])
async def test_foreign_or_unverifiable_recovery_never_writes(tmp_path,deny_wire,change):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            if change=='actor':c.headers.update(renew(app,actor='usr:another'))
            elif change=='role':c.headers.update(renew(app,role='editor'))
            elif change=='legacy-pruned':c.headers.update(renew(app,remove_old=True))
            elif change=='intent':payload['intent_sha256']='f'*64
            else:
                async with env['session_factory']() as s:
                    asset=await s.get(AssetORM,env['source_asset'].asset_id);asset.provenance={**asset.provenance,'rights_status':'restricted'};await s.commit()
            value=await c.post(path+'/recovery/inspect',json=payload);assert value.status_code in {403,409},value.text
            assert await rows(env)=={}
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_absent_legacy_intent_with_new_credential_cannot_prove_original_full_authority(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env);c.headers.update(renew(app))
            observed=await c.post(path+'/recovery/inspect',json=payload)
            assert observed.status_code==409 and observed.json()['detail']['error']['code']=='BROLL_RECOVERY_IDENTITY_UNVERIFIABLE'
            assert await rows(env)=={}
            assert (await c.post(path,json=original['body'],headers=TEST_HUMAN_HEADERS)).status_code==201
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_stale_absence_cas_cannot_abandon_a_newly_committed_original(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            prepared=await c.post(path,json=original['body']);assert prepared.status_code==201
            before=await rows(env)
            stale=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True})
            assert stale.status_code==409 and stale.json()['detail']['error']['code']=='BROLL_RECOVERY_STALE_CAS'
            assert await rows(env)==before
            fresh=(await c.post(path+'/recovery/inspect',json=payload)).json()
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':fresh['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200 and sealed.json()['preserved_plan']==prepared.json()['plan']
            for key,value in before.items():assert (await rows(env))[key]==value
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_replayed_settlement_requires_identical_original_raw_and_prepared_settings(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env);assert (await c.post(path,json=original['body'])).status_code==201
            observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            request={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True}
            assert (await c.post(path+'/recovery/abandon',json=request)).status_code==200
            before=await rows(env)
            for raw in [' '+payload['intent_json'],stable({**original,'body':{**original['body'],'settings':{**original['body']['settings'],'resolver_priority':['internal_library','user_asset']}}})]:
                changed={**request,'intent_json':raw,'intent_sha256':hashlib.sha256(raw.encode()).hexdigest()}
                assert (await c.post(path+'/recovery/abandon',json=changed)).status_code==409
                assert await rows(env)==before
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation',['ack-number','ack-false','extra','cas-type','missing-cas'])
async def test_strict_settlement_confirmation_and_cas_are_required(tmp_path,deny_wire,mutation):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await intent(c,env);observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            request={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True}
            if mutation=='ack-number':request['acknowledged']=1
            elif mutation=='ack-false':request['acknowledged']=False
            elif mutation=='extra':request['actor_ref']='usr:fake-owner'
            elif mutation=='cas-type':request['observation_sha256']=[]
            else:del request['observation_sha256']
            assert (await c.post(path+'/recovery/abandon',json=request)).status_code==422
            assert await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_expired_original_is_never_authenticated_but_fresh_same_human_can_recover(tmp_path,deny_wire,monkeypatch):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            assert (await c.post(path,json=original['body'])).status_code==201
            fresh=renew(app);before=await rows(env)
            verifier=app.state.human_auth_verifier
            now=verifier.registry.tokens['test-owner'].expires_at+timedelta(seconds=1)
            verify=verifier.verify
            monkeypatch.setattr(verifier,'verify',lambda value:verify(value,now=now))
            assert (await c.post(path+'/recovery/inspect',json=payload)).status_code==401
            assert await rows(env)==before
            c.headers.update(fresh)
            observed=await c.post(path+'/recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed.json()['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_rehashed_forged_absent_authority_cannot_seal_wrong_namespace(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);fake=copy.deepcopy(original)
            context=fake['context'];context['authority_sha256']='f'*64
            fields={k:v for k,v in context.items() if k not in {'context_json','context_sha256'}}
            context['context_json']=stable(fields);context['context_sha256']=hashlib.sha256(context['context_json'].encode()).hexdigest()
            fake['body']['context_sha256']=context['context_sha256'];raw=stable(fake)
            payload={'intent_json':raw,'intent_sha256':hashlib.sha256(raw.encode()).hexdigest()}
            observed=await c.post(path+'/recovery/inspect',json=payload)
            assert observed.status_code==409 and observed.json()['detail']['error']['code']=='BROLL_RECOVERY_IDENTITY_UNVERIFIABLE'
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':'a'*64,'acknowledged':True})
            assert sealed.status_code==409 and await rows(env)=={}
            valid=await c.post(path,json=original['body']);assert valid.status_code==201,valid.text
            assert len(await rows(env))==1 and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_old_unverified_null_authority_settlement_is_not_accepted_as_server_proof(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await intent(c,env);observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            sealed=(await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True})).json()
            identifier=sealed['settlement']['settlement_id']
            async with env['session_factory']() as s:
                row=await s.get(ServiceOperationORM,identifier);value=copy.deepcopy(row.response_json)
                value['_verified_identity']['authority']=None;value['_verified_identity']['legacy_historical_record']='test-owner'
                row.response_json=value;row.response_sha256=digest(value);await s.commit()
            before=await rows(env)
            proof=await c.get(path+'/recovery/settlements/'+identifier)
            assert proof.status_code==409 and proof.json()['detail']['error']['code']=='BROLL_RECOVERY_IDENTITY_UNVERIFIABLE'
            assert (await c.post(path+'/recovery/inspect',json=payload)).status_code==409
            assert await rows(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_late_plan_audit_failure_keeps_unknown_plan_and_original_bytes(tmp_path,deny_wire,monkeypatch):
    from app import broll_request_recovery_command as recovery
    env=await prepare(tmp_path);app=app_for(env);entered=asyncio.Event();resume=asyncio.Event();create=env['planner'].create
    async def delayed(**kwargs):
        entered.set();await resume.wait();return await create(**kwargs)
    async def fail_audit(*_args,**_kwargs):raise OSError('private database failure')
    env['planner'].create=delayed
    monkeypatch.setattr(recovery,'record_late_result',fail_audit)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app,raise_app_exceptions=False),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            task=asyncio.create_task(c.post(path,json=original['body']));await asyncio.wait_for(entered.wait(),15)
            before=await rows(env);observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200
            resume.set()
            failed=await task;assert failed.status_code==500 and 'private database' not in failed.text
            after=await rows(env)
            for key,value in before.items():assert after[key]==value
            assert not [r for r in after.values() if r['service_id']==LATE_NAMESPACE]
            async with env['session_factory']() as s:assert await s.scalar(select(func.count()).select_from(MediaPlanORM))==1
            assert (await c.post(path,json=original['body'])).status_code==409
            assert deny_wire==[]
    finally:resume.set();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_stock_already_reviewed_keeps_current_schedule_and_historical_snapshot(tmp_path,deny_wire):
    from test_broll_plan_review import stock_env
    from test_stock_planner_retry import action
    env,adapter,calls=await stock_env(tmp_path);app=app_for(env)
    from app.timeline_repository import TimelineRepository
    env['timeline']=await TimelineRepository(env['session_factory']).get_timeline(env['project'].project_id)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await intent(c,env)
            original['body']['settings']=body(original['context'],stock=True)['settings']
            payload={'intent_json':stable(original),'intent_sha256':digest(original)}
            prepared=(await c.post(path,json=original['body'])).json()
            plan=await env['planner'].get(prepared['plan']['media_plan_id'])
            current=await env['planner'].retry_stock_search(plan.media_plan_id,action(plan));assert calls
            calls_before=copy.deepcopy(calls);before=await rows(env)
            observed=await c.post(path+'/recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            assert observed.json()['preserved_plan']==prepared['plan'] and observed.json()['preserved_plan_is_original_snapshot'] is True
            sealed=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed.json()['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            assert await env['planner'].get(plan.media_plan_id)==current and calls==calls_before
            for key,value in before.items():assert (await rows(env))[key]==value
            assert deny_wire==[]
    finally:await adapter.aclose();await env['engine'].dispose()


@pytest.mark.asyncio
async def test_two_abandons_serialize_to_one_settlement_and_proof_survives_another_renewal(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=app_for(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await intent(c,env);observed=(await c.post(path+'/recovery/inspect',json=payload)).json()
            request={**payload,'observation_sha256':observed['observation_sha256'],'acknowledged':True}
            a,b=await asyncio.gather(c.post(path+'/recovery/abandon',json=request),c.post(path+'/recovery/abandon',json=request))
            assert a.status_code==b.status_code==200 and a.json()==b.json()
            before=await rows(env);assert len(before)==1
            c.headers.update(renew(app,remove_old=True))
            proof=await c.get(path+'/recovery/settlements/'+a.json()['settlement']['settlement_id'])
            assert proof.status_code==200,proof.text
            current=(await c.get(path)).json()
            assert proof.json()['current_authority_sha256']==current['authority_sha256']
            assert proof.json()['settlement']==a.json()['settlement'] and await rows(env)==before
            assert deny_wire==[]
    finally:await env['engine'].dispose()
