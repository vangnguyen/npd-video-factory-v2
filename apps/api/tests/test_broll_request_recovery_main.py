"""Actual shipped router/auth admission, owned SQLite, network denied."""
import pytest
from test_sql_broll_review_main import actual_main,counts,deny_wire
from test_broll_request_recovery import prepare,intent
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS


@pytest.mark.asyncio
async def test_actual_main_settles_one_owned_request_without_media_or_timeline_write(tmp_path,deny_wire):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (_app,c):
            path,original,payload=await intent(c,env);before=await counts(env)
            observed=await c.post(path+'/recovery/inspect',json=payload)
            assert observed.status_code==200 and observed.headers['cache-control']=='no-store'
            assert await counts(env)==before
            settled=await c.post(path+'/recovery/abandon',json={**payload,'observation_sha256':observed.json()['observation_sha256'],'acknowledged':True})
            assert settled.status_code==200,settled.text
            proof=await c.get(path+'/recovery/settlements/'+settled.json()['settlement']['settlement_id'])
            assert proof.json()==settled.json()
            assert (await c.post(path,json=original['body'])).status_code==409
            after=await counts(env)
            assert after=={**before,'service_api_operations':before['service_api_operations']+1}
            assert deny_wire==[]
    finally:await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,status',[('viewer',403),('write_off',503),('unauthenticated',401),('foreign',404)])
async def test_actual_main_recovery_auth_before_private_body(tmp_path,deny_wire,mode,status):
    env=await prepare(tmp_path)
    try:
        async with actual_main(env) as (app,c):
            if mode in {'viewer','foreign'}:
                install_test_human_auth(app,platform_repository=env['platform'],platform_role=None,
                    workspace_roles={env['project'].workspace_id:'viewer'} if mode=='viewer' else {'wsp_foreign':'editor'})
            elif mode=='write_off':app.state.human_write_enabled=False
            before=await counts(env)
            path=f"/api/v1/projects/{env['project'].project_id}/broll-plan-review/recovery"
            r=await c.post(path+'/inspect',json={'invalid_private_fixture':True},headers={'Authorization':''} if mode=='unauthenticated' else TEST_HUMAN_HEADERS)
            assert r.status_code==status,r.text
            assert await counts(env)==before and deny_wire==[]
    finally:await env['engine'].dispose()
