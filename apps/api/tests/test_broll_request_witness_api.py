"""Actual authenticated ASGI/SQLite, ephemeral dedicated keys, zero egress."""
import copy
import json
import secrets
import time

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import select

from app.broll_request_witness import WitnessKey, WitnessKeyring
from app.broll_request_witness_api import router
from app.db import AssetORM
from app.human_auth import authorize_human_request
from app.service_api_repository import ServiceOperationORM
from test_broll_request_recovery import app_for, intent, prepare, renew, rows
from test_sql_broll_review_main import counts, deny_wire
from auth_test_support import TEST_HUMAN_HEADERS, TEST_HUMAN_TOKEN, install_test_human_auth


class EphemeralProvider:
    def __init__(self):
        now=int(time.time())
        k=WitnessKey('fixture-key-a',secrets.token_bytes(32),now-100,now+86400,now+31*86400,'active')
        self.ring=WitnessKeyring(k.key_id,{k.key_id:k})
    def load(self):return self.ring


def server(env,configured=True):
    app=app_for(env);app.include_router(router,dependencies=[Depends(authorize_human_request)])
    if configured:app.state.broll_witness_secret_provider=EphemeralProvider()
    app.state.broll_witness_ttl_seconds=3600
    return app


@pytest.mark.asyncio
async def test_issue_and_verify_are_exact_readonly_and_never_expose_raw_credentials_or_private_keys(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);before=await counts(env)
            read=(await c.get(path)).content
            issued=await c.post(path+'/witness',json=original['body']);assert issued.status_code==200,issued.text
            proof=issued.json();assert proof['execution_status']=='NOT_ASSERTED' and proof['provider_calls']==0
            assert TEST_HUMAN_TOKEN not in issued.text and TEST_HUMAN_HEADERS['Authorization'] not in issued.text
            key=app.state.broll_witness_secret_provider.ring.keys['fixture-key-a']
            assert key.secret.hex() not in issued.text
            assert json.loads(proof['witness']['claims_json'])['body']==original['body']
            verified=await c.post(path+'/witness/verify',json={'request':original['body'],'witness':proof['witness']})
            assert verified.status_code==200 and verified.json()['authorization_witness_valid'] is True,verified.text
            assert await counts(env)==before and await rows(env)=={}
            assert (await c.get(path)).content==read and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_signed_absent_authorization_survives_original_registry_pruning_without_asserting_execution(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env)
            proof=(await c.post(path+'/witness',json=original['body'])).json()
            c.headers.update(renew(app,remove_old=True))
            verified=await c.post(path+'/witness/verify',json={'request':original['body'],'witness':proof['witness']})
            assert verified.status_code==200,verified.text
            result=verified.json();assert result['original_authority_sha256']!=result['current_authority_sha256']
            assert result['execution_status']=='NOT_ASSERTED' and await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['body','key','authority','signature','actor','roles','source','revoked','expired'])
async def test_tamper_or_changed_boundaries_cannot_validate_authorization(tmp_path,deny_wire,mode):
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);proof=(await c.post(path+'/witness',json=original['body'])).json()
            body={'request':copy.deepcopy(original['body']),'witness':copy.deepcopy(proof['witness'])}
            if mode=='body':body['request']['settings']['resolver_priority'].reverse()
            elif mode=='key':body['witness']['key_id']='foreign-key'
            elif mode=='authority':
                value=json.loads(body['witness']['claims_json']);value['original_authority_sha256']='f'*64;body['witness']['claims_json']=json.dumps(value)
            elif mode=='signature':body['witness']['signature']='f'*64
            elif mode=='actor':c.headers.update(renew(app,actor='usr:foreign'))
            elif mode=='roles':c.headers.update(renew(app,role='editor'))
            elif mode=='source':
                async with env['session_factory']() as s:
                    asset=await s.get(AssetORM,env['source_asset'].asset_id);asset.storage_provider='s3';await s.commit()
            else:
                provider=app.state.broll_witness_secret_provider;old=provider.ring.keys['fixture-key-a'];now=int(time.time())
                new=WitnessKey('fixture-key-b',secrets.token_bytes(32),now-100,now+86400,now+31*86400,'active')
                changed=WitnessKey(old.key_id,old.secret,old.not_before,old.sign_until,
                    old.verify_until if mode=='revoked' else now-1,'revoked' if mode=='revoked' else 'verify_only') if mode=='revoked' else None
                # Expiry fixture keeps valid key ordering while revoking its verification window.
                if mode=='expired':changed=WitnessKey(old.key_id,old.secret,now-10000,now-100,now-1,'verify_only')
                provider.ring=WitnessKeyring(new.key_id,{old.key_id:changed,new.key_id:new})
            before=await rows(env);response=await c.post(path+'/witness/verify',json=body)
            assert response.status_code in {403,409},response.text
            assert await rows(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
async def test_default_not_configured_is_safe_and_invalid_prepare_context_never_signs(tmp_path,deny_wire):
    env=await prepare(tmp_path);app=server(env,configured=False)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);r=await c.post(path+'/witness',json=original['body'])
            assert r.status_code==503 and r.json()['detail']['error']['code']=='BROLL_WITNESS_NOT_CONFIGURED'
            app.state.broll_witness_secret_provider=EphemeralProvider();bad=copy.deepcopy(original['body']);bad['context_sha256']='f'*64
            r=await c.post(path+'/witness',json=bad);assert r.status_code==409
            bad=copy.deepcopy(original['body']);bad['settings']['allow_ai_image']=True
            assert (await c.post(path+'/witness',json=bad)).status_code==422
            assert await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['revoked','expired'])
async def test_key_or_clock_drift_during_sql_read_cannot_return_verified_capability(tmp_path,deny_wire,monkeypatch,mode):
    from app import broll_request_witness_command as command
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);proof=(await c.post(path+'/witness',json=original['body'])).json()
            context=command._context
            async def drift(*args,**kwargs):
                value=await context(*args,**kwargs)
                if mode=='expired':
                    expires=json.loads(proof['witness']['claims_json'])['expires_at']
                    monkeypatch.setattr(command.time,'time',lambda:expires+1)
                else:
                    provider=app.state.broll_witness_secret_provider;old=provider.ring.keys['fixture-key-a'];now=int(time.time())
                    new=WitnessKey('fixture-key-b',secrets.token_bytes(32),now-100,now+86400,now+31*86400,'active')
                    revoked=WitnessKey(old.key_id,old.secret,old.not_before,old.sign_until,old.verify_until,'revoked')
                    provider.ring=WitnessKeyring(new.key_id,{old.key_id:revoked,new.key_id:new})
                return value
            monkeypatch.setattr(command,'_context',drift)
            response=await c.post(path+'/witness/verify',json={'request':original['body'],'witness':proof['witness']})
            assert response.status_code in {403,409},response.text
            assert await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['revoked','roles','write_off'])
async def test_current_auth_revocation_during_sql_read_never_returns_witness_proof(tmp_path,deny_wire,monkeypatch,mode):
    from app import broll_request_witness_command as command
    env=await prepare(tmp_path);app=server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-witness',headers=TEST_HUMAN_HEADERS) as c:
            path,original,_=await intent(c,env);proof=(await c.post(path+'/witness',json=original['body'])).json()
            context=command._context
            async def drift(*args,**kwargs):
                value=await context(*args,**kwargs)
                if mode=='write_off':app.state.human_write_enabled=False
                else:
                    tokens=app.state.human_auth_verifier.registry.tokens;old=tokens['test-owner']
                    tokens['test-owner']=old.model_copy(update={'enabled':False} if mode=='revoked' else {'platform_role':'editor'})
                return value
            monkeypatch.setattr(command,'_context',drift)
            response=await c.post(path+'/witness/verify',json={'request':original['body'],'witness':proof['witness']})
            assert response.status_code==403,response.text
            assert await rows(env)=={} and deny_wire==[]
    finally:await env['engine'].dispose()
