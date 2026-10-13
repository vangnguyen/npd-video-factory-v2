"""Real main-router registration with owned SQLite, no lifespan/provider dispatch."""
import httpx
import pytest
from app import main
from app.sql_variant_api_service import configure_sql_variant_api
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
from test_sql_variant_family import env,ready

@pytest.mark.asyncio
async def test_main_registered_family_routes_authenticate_once_and_preserve_verified_actor(env):
    app=main.app;prior=dict(app.state._state)
    try:
        configure_sql_variant_api(app,session_factory=env.factory,object_storage=env.storage,
            uploaded_enabled=True,register_routes=False)
        install_test_human_auth(app,platform_repository=env.platform,platform_role=None,
            workspace_roles={env.workspace.workspace_id:'editor'})
        _,payload,_,_,_=await ready(env)
        root=f'/api/v1/projects/{env.project.project_id}/variant-families'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-main-fixture',headers=TEST_HUMAN_HEADERS) as client:
            available=await client.get(root+'/availability')
            assert available.status_code==200,available.text
            assert available.json()['derivation']['state']=='CONFIGURED'
            assert sum(app.state.human_rate_limiter.store.counts.values())==1
            result=await client.post(root,json=payload.model_dump(mode='json'))
            assert result.status_code==201,result.text
            assert result.json()['family']['actor_ref']=='usr:test-owner'
            assert result.headers['cache-control']=='no-store'
            assert sum(app.state.human_rate_limiter.store.counts.values())==2
            app.state.human_write_enabled=False
            refused=await client.post(root,content=b'{"private-invalid-body":')
            assert refused.status_code==503 and 'HUMAN_WRITES_DISABLED' in refused.text
        assert app.state.sql_variant_api_service.uploaded_enabled is True
    finally:
        app.state._state=prior
