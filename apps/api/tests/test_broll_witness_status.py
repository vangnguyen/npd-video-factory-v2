"""Explicit optional capability read: real ASGI/SQL, no sign/reserve/provider."""
import time

import httpx
import pytest

from app.broll_request_witness import WitnessKey, WitnessKeyring
from auth_test_support import TEST_HUMAN_HEADERS, TEST_HUMAN_TOKEN, install_test_human_auth
from test_broll_request_witness_api import server, prepare
from test_sql_broll_review_main import counts, deny_wire


@pytest.mark.asyncio
@pytest.mark.parametrize('configured', [False, True])
async def test_status_is_explicit_readonly_without_signing_or_changing_old_context(tmp_path, deny_wire, monkeypatch, configured):
    env = await prepare(tmp_path); app = server(env, configured=configured)
    def no_sign(*args, **kwargs):
        raise AssertionError('STATUS_MUST_NOT_SIGN')
    monkeypatch.setattr(WitnessKeyring, 'sign', no_sign)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-status', headers=TEST_HUMAN_HEADERS) as c:
            path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
            before = await counts(env); context = (await c.get(path)).content
            r = await c.get(path+'/witness/status'); assert r.status_code == 200, r.text
            v = r.json()
            assert v == {'schema_version': 'vf-broll-request-witness-capability.v1',
                'workspace_id': env['project'].workspace_id, 'project_id': env['project'].project_id,
                'actor_ref': 'usr:test-owner', 'status': 'READY' if configured else 'NOT_CONFIGURED',
                'issuance_available': configured, 'optional': True,
                'witness_schema_version': 'vf-broll-request-witness.v1', 'algorithm': 'HMAC-SHA256',
                'execution_status': 'NOT_ASSERTED', 'provider_calls': 0,
                'source_media_mutated': False, 'publish_requested': False, 'owner_approval_inferred': False}
            assert r.headers['cache-control'] == 'no-store' and TEST_HUMAN_TOKEN not in r.text
            assert 'fixture-key-a' not in r.text and 'secret' not in r.text
            assert (await c.get(path)).content == context and await counts(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['expired', 'future', 'verification_window', 'bad_policy', 'private_provider_error'])
async def test_status_reports_unavailable_without_revealing_provider_failure(tmp_path, deny_wire, change):
    env = await prepare(tmp_path); app = server(env); now = int(time.time())
    try:
        provider = app.state.broll_witness_secret_provider
        old = provider.ring.keys['fixture-key-a']
        if change == 'bad_policy':
            app.state.broll_witness_ttl_seconds = True
        elif change == 'private_provider_error':
            def private_error():
                raise RuntimeError('PRIVATE_KEY_MUST_NEVER_BE_RETURNED')
            provider.load = private_error
        else:
            before, sign, verify = now-100, now+86400, now+31*86400
            if change == 'expired':
                sign, verify = now-1, now+86400
            elif change == 'future':
                before, sign, verify = now+10, now+86400, now+31*86400
            else:
                sign, verify = now+1, now+2
            key = WitnessKey(old.key_id, old.secret, before, sign, verify, 'active')
            provider.ring = WitnessKeyring(key.key_id, {key.key_id: key})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-status', headers=TEST_HUMAN_HEADERS) as c:
            before = await counts(env)
            r = await c.get(f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/witness/status")
            assert r.status_code == 200 and r.json()['status'] == 'UNAVAILABLE'
            assert r.json()['issuance_available'] is False and 'PRIVATE' not in r.text
            assert await counts(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,code', [('viewer', 403), ('foreign', 404), ('unauthenticated', 401), ('writes_off', 403)])
async def test_status_admission_does_not_read_any_private_key(tmp_path, deny_wire, mode, code):
    env = await prepare(tmp_path); app = server(env); loads = []
    def no_load():
        loads.append('unexpected_key_read')
        raise AssertionError('ADMISSION_MUST_PRECEDE_SECRET_READ')
    app.state.broll_witness_secret_provider.load = no_load
    if mode == 'viewer':
        install_test_human_auth(app, platform_repository=env['platform'], platform_role='viewer', workspace_roles={'*': 'viewer'})
    elif mode == 'foreign':
        install_test_human_auth(app, platform_repository=env['platform'], platform_role=None, workspace_roles={'wsp_foreign_only': 'owner'})
    elif mode == 'writes_off':
        app.state.human_write_enabled = False
    headers = {'Authorization': 'Bearer invalid'} if mode == 'unauthenticated' else TEST_HUMAN_HEADERS
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-status', headers=headers) as c:
            before = await counts(env)
            r = await c.get(f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/witness/status")
            assert r.status_code == code, r.text
            assert loads == [] and await counts(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['credential', 'writes_off'])
async def test_status_rechecks_authority_after_project_await_before_loading_key(tmp_path, deny_wire, change, monkeypatch):
    env = await prepare(tmp_path); app = server(env); get = env['platform'].get_project; calls = []; loads = []
    async def scoped(project):
        result = await get(project); calls.append(project)
        if len(calls) == 3:
            if change == 'credential':
                app.state.human_auth_verifier.registry.tokens.clear()
            else:
                app.state.human_write_enabled = False
        return result
    monkeypatch.setattr(env['platform'], 'get_project', scoped)
    def no_load():
        loads.append('unexpected_key_read'); raise AssertionError('EXPIRED_ADMISSION')
    app.state.broll_witness_secret_provider.load = no_load
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-status', headers=TEST_HUMAN_HEADERS) as c:
            before = await counts(env)
            r = await c.get(f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/witness/status")
            assert r.status_code == 403, r.text
            assert len(calls) == 3 and loads == [] and await counts(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('route', ['status', 'issue', 'verify'])
async def test_live_api_switch_after_sql_stops_witness_routes_before_further_key_reads(tmp_path, deny_wire, route, monkeypatch):
    from app import broll_request_witness_command as command
    from test_broll_plan_review import body
    env = await prepare(tmp_path); app = server(env); key_reads = []
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-status', headers=TEST_HUMAN_HEADERS) as c:
            path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
            request = body((await c.get(path)).json())
            payload = request
            if route == 'verify':
                issued = await c.post(path+'/witness', json=request); assert issued.status_code == 200
                payload = {'request': request, 'witness': issued.json()['witness']}
            provider = app.state.broll_witness_secret_provider; load = provider.load
            def observed_load():
                key_reads.append(app.state.human_api_enabled)
                return load()
            monkeypatch.setattr(provider, 'load', observed_load)
            if route == 'status':
                get = env['platform'].get_project; project_reads = []
                async def scoped(project):
                    value = await get(project); project_reads.append(project)
                    if len(project_reads) == 3:
                        app.state.human_api_enabled = False
                    return value
                monkeypatch.setattr(env['platform'], 'get_project', scoped)
            else:
                context = command._context
                async def scoped(*args, **kwargs):
                    value = await context(*args, **kwargs)
                    app.state.human_api_enabled = False
                    return value
                monkeypatch.setattr(command, '_context', scoped)
            before = await counts(env)
            r = await c.get(path+'/witness/status') if route == 'status' else await c.post(
                path+('/witness' if route == 'issue' else '/witness/verify'), json=payload)
            assert r.status_code == 403, r.text
            assert r.json()['detail']['error']['code'] == 'BROLL_WITNESS_AUTHORITY_CHANGED'
            assert key_reads == ([True] if route == 'verify' else [])
            assert await counts(env) == before and deny_wire == []
    finally:
        await env['engine'].dispose()
