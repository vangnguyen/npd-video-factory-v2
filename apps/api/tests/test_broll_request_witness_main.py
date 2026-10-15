"""Shipped router/admission with isolated actual SQLite and ephemeral VF key."""
import pytest

from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_broll_request_recovery import prepare, intent, rows
from test_broll_request_witness_api import EphemeralProvider
from test_sql_broll_review_main import actual_main, counts, deny_wire


@pytest.mark.asyncio
async def test_actual_main_witness_routes_leave_legacy_context_and_rows_unchanged(tmp_path,deny_wire):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (app,c):
            app.state.broll_witness_secret_provider=EphemeralProvider();app.state.broll_witness_ttl_seconds=3600
            path,original,_=await intent(c,env);before=await counts(env);context=(await c.get(path)).content
            issued=await c.post(path+'/witness',json=original['body']);assert issued.status_code==200,issued.text
            verified=await c.post(path+'/witness/verify',json={'request':original['body'],'witness':issued.json()['witness']})
            assert verified.status_code==200 and verified.headers['cache-control']=='no-store'
            assert verified.json()['execution_status']=='NOT_ASSERTED'
            assert await counts(env)==before and await rows(env)=={} and (await c.get(path)).content==context
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,status',[('viewer',403),('foreign',404),('unauthenticated',401),('write_off',503)])
async def test_actual_main_witness_auth_precedes_private_invalid_body(tmp_path,deny_wire,mode,status):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (app,c):
            if mode in {'viewer','foreign'}:
                install_test_human_auth(app,platform_repository=env['platform'],platform_role=None,
                    workspace_roles={env['project'].workspace_id:'viewer'} if mode=='viewer' else {'wsp_foreign':'editor'})
            elif mode=='write_off':app.state.human_write_enabled=False
            before=await counts(env)
            r=await c.post(f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/witness",json={'private_invalid_fixture':True},
                headers={'Authorization':''} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
            assert r.status_code==status,r.text
            assert await counts(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()
