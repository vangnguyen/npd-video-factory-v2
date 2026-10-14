"""Actual main ASGI registration and verified final actor; no lifespan/AI wire."""
import httpx
import pytest
from pydantic import ValidationError
from app.config import Settings
from app import main
from app.production_models import FinalRenderCreateRequest
from auth_test_support import install_test_human_auth,TEST_HUMAN_HEADERS
from test_sql_variant_narration_activation import env,narration_env,active,base,review_body


def test_activation_config_flag_is_default_off_and_finite_boolean_only():
    assert Settings(_env_file=None).sql_variant_narration_reuse_enabled is False
    assert Settings(_env_file=None,sql_variant_narration_reuse_enabled='true').sql_variant_narration_reuse_enabled is True
    for value in (1,0,'yes',None):
        with pytest.raises(ValidationError):Settings(_env_file=None,sql_variant_narration_reuse_enabled=value)


async def test_actual_main_uses_paired_routes_and_final_actor_before_repository_create(active):
    a=active;app=main.app;prior=dict(app.state._state)
    try:
        app.state.sql_variant_narration_runtime=a.runtime;app.state.production_package_service=a.service
        install_test_human_auth(app,platform_repository=a.f.env.platform,platform_role=None,
            workspace_roles={a.f.env.workspace.workspace_id:'editor'})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),base_url='http://owned-main-fixture',headers=TEST_HUMAN_HEADERS) as c:
            available=await c.get(base(a.f)+'/narration-reuse-availability')
            imported=await c.post(base(a.f)+'/narration-reuse',json=a.request.model_dump(mode='json'))
            assert available.status_code==200 and imported.status_code==201,imported.text
            assert imported.json()['receipt']['actor_ref']=='usr:test-owner'
            assert sum(app.state.human_rate_limiter.store.counts.values())==2
            payload=FinalRenderCreateRequest(expected_timeline_version=2,expected_subtitle_version=1,expected_audio_version=1,
                approval_id='apr_fixture_actor_check',actor_ref='forged-body-author',profile='landscape-1920x1080')
            captured=[]
            async def observe(project_id,body):
                captured.append((project_id,body.actor_ref));raise KeyError('fixture terminal stop before create')
            a.service.enqueue_final=observe
            stopped=await c.post(f'/api/v1/projects/{a.f.child.project_id}/final-render',json=payload.model_dump(mode='json'))
            assert stopped.status_code==404 and captured==[(a.f.child.project_id,'usr:test-owner')]
    finally:app.state._state=prior
