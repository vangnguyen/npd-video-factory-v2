"""Existing locked SQL settlement plus authentic ephemeral VF authorization proof."""
import asyncio
import copy
import json
from datetime import timedelta

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import select,func

from app.broll_witnessed_recovery_api import router
from app.broll_request_recovery_command import LATE_NAMESPACE
from app.db import AssetORM
from app.human_auth import authorize_human_request
from app.media_intelligence_db import MediaPlanORM
from app.service_api_repository import ServiceOperationORM,digest
from test_broll_request_recovery import intent,prepare,renew,rows
from test_broll_request_witness_api import server as witness_server
from test_sql_broll_review_main import deny_wire
from auth_test_support import TEST_HUMAN_HEADERS


def server(env):
    app=witness_server(env);app.include_router(router,dependencies=[Depends(authorize_human_request)])
    return app


async def signed(c,env):
    path,original,payload=await intent(c,env)
    issued=await c.post(path+'/witness',json=original['body']);assert issued.status_code==200,issued.text
    return path,original,{**payload,'witness':issued.json()['witness']}


@pytest.mark.asyncio
async def test_signed_absent_renewed_pruned_seal_uses_exact_namespace_and_preserves_old_v1_contract(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await signed(c,env);old=app.state.human_auth_verifier.registry.tokens['test-owner']
            c.headers.update(renew(app,remove_old=True))
            plain={k:v for k,v in payload.items() if k!='witness'}
            assert (await c.post(path+'/recovery/inspect',json=plain)).status_code==409 and await rows(env)=={}
            observed=await c.post(path+'/witnessed-recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            assert observed.json()['recovery']['original_result'] is None and await rows(env)=={}
            request={**payload,'observation_sha256':observed.json()['recovery']['observation_sha256'],'acknowledged':True}
            sealed=await c.post(path+'/witnessed-recovery/abandon',json=request);assert sealed.status_code==200,sealed.text
            value=sealed.json();identifier=value['recovery']['settlement']['settlement_id']
            assert value['execution_status']=='NOT_ASSERTED' and value['provider_calls']==0
            assert (await c.get(path+'/witnessed-recovery/settlements/'+identifier)).json()==value
            # The old route still returns its exact v1 schema/shape, backed now
            # by a committed trusted server identity, never an unsigned fallback.
            legacy=(await c.get(path+'/recovery/settlements/'+identifier)).json()
            assert legacy==value['recovery'] and 'witness' not in legacy
            app.state.human_auth_verifier.registry.tokens['test-owner']=old
            late=await c.post(path,json=original['body'],headers=TEST_HUMAN_HEADERS)
            assert late.status_code==409 and late.json()['detail']['error']['code']=='BROLL_REQUEST_ABANDONED'
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM))==0
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM))==1
            before=await rows(env)
            assert (await c.post(path+'/witnessed-recovery/abandon',json=request)).json()==value
            assert await rows(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_signed_abandon_serializes_late_completion_to_single_immutable_plan_audit(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env);entered=asyncio.Event();resume=asyncio.Event();create=env['planner'].create;calls=[]
    async def delayed(**kwargs):
        calls.append(kwargs);entered.set();await resume.wait();return await create(**kwargs)
    env['planner'].create=delayed
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await signed(c,env)
            task=asyncio.create_task(c.post(path,json=original['body']));await asyncio.wait_for(entered.wait(),15)
            before=await rows(env);c.headers.update(renew(app,remove_old=True))
            observed=(await c.post(path+'/witnessed-recovery/inspect',json=payload)).json()
            sealed=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            resume.set();late=await task;assert late.status_code==409,late.text
            after=await rows(env)
            for key,value in before.items():assert after[key]==value
            assert len([r for r in after.values() if r['service_id']==LATE_NAMESPACE])==1 and len(calls)==1
            identifier=sealed.json()['recovery']['settlement']['settlement_id']
            audit=(await c.get(path+'/recovery/settlements/'+identifier+'/late-results')).json()
            assert len(audit)==1 and audit[0]['read_only'] is True and audit[0]['plan']
            assert deny_wire==[]
    finally:resume.set();await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['signature','body','key','authority','role','source','expired'])
async def test_bad_witness_or_changed_binding_never_creates_a_tombstone(tmp_path,deny_wire,change,monkeypatch):
    from app import broll_request_witness_command as command
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await signed(c,env)
            if change=='signature':payload['witness']['signature']='f'*64
            elif change=='key':payload['witness']['key_id']='foreign-key'
            elif change in {'body','authority'}:
                value=json.loads(payload['witness']['claims_json'])
                if change=='body':value['body']['request_key']='different-request-key'
                else:value['original_authority_sha256']='f'*64
                payload['witness']['claims_json']=json.dumps(value)
            elif change=='role':c.headers.update(renew(app,role='editor',remove_old=True))
            elif change=='expired':
                expires=json.loads(payload['witness']['claims_json'])['expires_at']
                monkeypatch.setattr(command.time,'time',lambda:expires+1)
            else:
                async with env['session_factory']() as s:
                    asset=await s.get(AssetORM,env['source_asset'].asset_id);asset.storage_provider='s3';await s.commit()
            response=await c.post(path+'/witnessed-recovery/inspect',json=payload)
            assert response.status_code in {401,403,409},response.text
            sealed=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':'a'*64,'acknowledged':True})
            assert sealed.status_code in {401,403,409} and await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_observed_absence_cas_cannot_skip_a_committed_original_and_history_needs_no_signing_key(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,payload=await signed(c,env)
            observed=(await c.post(path+'/witnessed-recovery/inspect',json=payload)).json()
            prepared=await c.post(path,json=original['body']);assert prepared.status_code==201
            before=await rows(env)
            stale=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})
            assert stale.status_code==409 and await rows(env)==before
            fresh=(await c.post(path+'/witnessed-recovery/inspect',json=payload)).json()
            sealed=(await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':fresh['recovery']['observation_sha256'],'acknowledged':True})).json()
            for key,value in before.items():assert (await rows(env))[key]==value
            del app.state.broll_witness_secret_provider
            proof=await c.get(path+'/witnessed-recovery/settlements/'+sealed['recovery']['settlement']['settlement_id'])
            assert proof.status_code==200 and proof.json()==sealed
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_expired_original_never_authenticates_but_signed_absent_intent_seals_with_fresh_same_actor(tmp_path,deny_wire,monkeypatch):
    from app import broll_request_witness_command as command
    env=await prepare(tmp_path);app=server(env);app.state.broll_witness_ttl_seconds=7200
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await signed(c,env);old=app.state.human_auth_verifier.registry.tokens['test-owner']
            fresh=renew(app,remove_old=True);verifier=app.state.human_auth_verifier;verify=verifier.verify
            future=old.expires_at+timedelta(seconds=1)
            monkeypatch.setattr(verifier,'verify',lambda value:verify(value,now=future))
            monkeypatch.setattr(command.time,'time',lambda:future.timestamp())
            verifier.registry.tokens['test-owner']=old
            assert (await c.post(path+'/witnessed-recovery/inspect',json=payload)).status_code==401
            del verifier.registry.tokens['test-owner'];c.headers.update(fresh)
            observed=await c.post(path+'/witnessed-recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            sealed=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed.json()['recovery']['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            assert len(await rows(env))==1 and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_signature_verification_runs_inside_existing_sqlite_project_write_transaction(tmp_path,deny_wire,monkeypatch):
    from sqlalchemy import event
    from app import broll_witnessed_recovery_command as command
    env=await prepare(tmp_path);app=server(env);statements=[];checks=[];writing=False
    def statement(_conn,_cursor,text,_params,_context,_many):statements.append(text.strip().upper())
    event.listen(env['engine'].sync_engine,'before_cursor_execute',statement)
    actual=command.verify_bound_witness
    async def verify(*args,**kwargs):
        if writing:
            assert args[1].in_transaction() and 'BEGIN IMMEDIATE' in statements
            assert any(s.startswith('SELECT VIDEO_PROJECTS.') for s in statements)
            checks.append('existing_write_lock_before_crypto')
        return await actual(*args,**kwargs)
    monkeypatch.setattr(command,'verify_bound_witness',verify)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await signed(c,env)
            observed=(await c.post(path+'/witnessed-recovery/inspect',json=payload)).json();statements.clear();writing=True
            result=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})
            assert result.status_code==200,result.text
            assert checks==['existing_write_lock_before_crypto'] and deny_wire==[]
    finally:event.remove(env['engine'].sync_engine,'before_cursor_execute',statement);await env['engine'].dispose()


@pytest.mark.asyncio
async def test_client_trust_flags_and_missing_human_acknowledgement_cannot_enter_locked_settlement(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await signed(c,env)
            for extra in [{'trusted':True},{'witness_scope':{'verified':True}},{'authority_guard':True}]:
                assert (await c.post(path+'/witnessed-recovery/inspect',json={**payload,**extra})).status_code==422
            assert (await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':'a'*64,'acknowledged':False})).status_code==422
            assert await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_witness_substitution_cas_and_replay_keep_original_envelope_after_key_rotation(tmp_path,deny_wire):
    import secrets,time
    from app.broll_request_witness import WitnessKey,WitnessKeyring
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,original,a=await signed(c,env)
            provider=app.state.broll_witness_secret_provider;old=provider.ring.keys['fixture-key-a'];now=int(time.time())
            new=WitnessKey('fixture-key-b',secrets.token_bytes(32),now-100,now+86400,now+31*86400,'active')
            retired=WitnessKey(old.key_id,old.secret,old.not_before,old.sign_until,old.verify_until,'verify_only')
            provider.ring=WitnessKeyring(new.key_id,{old.key_id:retired,new.key_id:new})
            b={**a,'witness':(await c.post(path+'/witness',json=original['body'])).json()['witness']}
            assert a['witness']!=b['witness']
            observed=(await c.post(path+'/witnessed-recovery/inspect',json=a)).json()
            wrong=await c.post(path+'/witnessed-recovery/abandon',json={**b,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})
            assert wrong.status_code==409 and wrong.json()['detail']['error']['code']=='BROLL_RECOVERY_STALE_CAS'
            assert await rows(env)=={}
            sealed=await c.post(path+'/witnessed-recovery/abandon',json={**a,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})
            assert sealed.status_code==200,sealed.text
            accepted=sealed.json();before=await rows(env)
            revoked=WitnessKey(old.key_id,old.secret,old.not_before,old.sign_until,old.verify_until,'revoked')
            provider.ring=WitnessKeyring(new.key_id,{old.key_id:revoked,new.key_id:new})
            replay=await c.post(path+'/witnessed-recovery/abandon',json={**b,'observation_sha256':'a'*64,'acknowledged':True})
            assert replay.status_code==200 and replay.json()==accepted,replay.text
            assert replay.json()['key_id']=='fixture-key-a' and await rows(env)==before
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('corrupt',['hash','signature_and_hash'])
async def test_corrupt_stored_witness_cannot_relabel_valid_original_settlement_receipt(tmp_path,deny_wire,corrupt):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witnessed-recovery',headers=TEST_HUMAN_HEADERS) as c:
            path,_,payload=await signed(c,env);observed=(await c.post(path+'/witnessed-recovery/inspect',json=payload)).json()
            sealed=(await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed['recovery']['observation_sha256'],'acknowledged':True})).json()
            identifier=sealed['recovery']['settlement']['settlement_id']
            async with env['session_factory']() as s:
                row=await s.get(ServiceOperationORM,identifier);value=copy.deepcopy(row.response_json)
                audit=value['_verified_identity']['authorization_witness']
                if corrupt=='hash':audit['witness_sha256']='f'*64
                else:
                    audit['envelope']['signature']='f'*64;audit['witness_sha256']=digest(audit['envelope'])
                row.response_json=value;row.response_sha256=digest(value);await s.commit()
            before=await rows(env)
            read=await c.get(path+'/witnessed-recovery/settlements/'+identifier)
            assert read.status_code==409,read.text
            assert await rows(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()
