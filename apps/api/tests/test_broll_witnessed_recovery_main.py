"""Actual main newroute with reviewed legacy and witness dependencies present."""
import pytest

from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_broll_request_recovery import prepare, renew
from test_broll_request_witness_api import EphemeralProvider
from test_broll_witnessed_recovery import signed
from test_sql_broll_review_main import actual_main,counts,deny_wire


@pytest.mark.asyncio
async def test_actual_main_witnessed_absent_renewal_seal_and_legacy_proof(tmp_path,deny_wire):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (app,c):
            app.state.broll_witness_secret_provider=EphemeralProvider();app.state.broll_witness_ttl_seconds=3600
            path,_,payload=await signed(c,env);c.headers.update(renew(app,remove_old=True));before=await counts(env)
            observed=await c.post(path+'/witnessed-recovery/inspect',json=payload);assert observed.status_code==200,observed.text
            assert await counts(env)==before
            result=await c.post(path+'/witnessed-recovery/abandon',json={**payload,'observation_sha256':observed.json()['recovery']['observation_sha256'],'acknowledged':True})
            assert result.status_code==200,result.text
            saved=result.json();identifier=saved['recovery']['settlement']['settlement_id']
            assert (await c.get(path+'/witnessed-recovery/settlements/'+identifier)).json()==saved
            assert (await c.get(path+'/recovery/settlements/'+identifier)).json()==saved['recovery']
            assert await counts(env)=={**before,'service_api_operations':before['service_api_operations']+1}
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,status',[('viewer',403),('foreign',404),('unauthenticated',401),('write_off',503)])
async def test_actual_main_witnessed_recovery_admission_before_private_body(tmp_path,deny_wire,mode,status):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (app,c):
            if mode in {'viewer','foreign'}:
                install_test_human_auth(app,platform_repository=env['platform'],platform_role=None,
                    workspace_roles={env['project'].workspace_id:'viewer'} if mode=='viewer' else {'wsp_foreign':'editor'})
            elif mode=='write_off':app.state.human_write_enabled=False
            before=await counts(env)
            r=await c.post(f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/witnessed-recovery/inspect",json={'invalid_private_fixture':True},
                headers={'Authorization':''} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
            assert r.status_code==status,r.text
            assert await counts(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()
