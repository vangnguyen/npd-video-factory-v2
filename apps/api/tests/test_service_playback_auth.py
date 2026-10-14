"""Actual signed ASGI auth; delegate bytes are explicit bounded fixtures."""
import pytest
from fastapi.responses import Response
from app import service_api_routes as routes
from app.bridge_auth import ServiceIdentity
from app.human_auth import HumanPrincipal
from app.platform_models import ProjectCreate
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_service_api import api, signed


@pytest.fixture(params=['preview', 'render'])
def playback(api, request, monkeypatch):
    kind = request.param
    calls = []
    async def admitted(project_id, media_id, incoming):
        principal = incoming.state.human_principal
        assert isinstance(principal, HumanPrincipal)
        assert principal.subject == 'usr:test-owner'
        assert incoming.state.service_actor.subject == 'svc:agent-hub'
        calls.append((project_id, media_id))
        return Response(b'EXPLICIT_AUTH_DELEGATE_FIXTURE', media_type='application/octet-stream')
    module, name = (routes.editing, 'preview_content') if kind == 'preview' else (routes.production, 'render_content')
    monkeypatch.setattr(module, name, admitted)
    async def get(extra=None):
        project = await api.stack.platform.create_project(api.stack.workspace.workspace_id,
            ProjectCreate(
                slug='playback-auth-fixture-'+kind, name='Private playback auth fixture', niche='technology'))
        api.playback_project = project
        plural = 'previews' if kind == 'preview' else 'renders'
        return await signed(api.client, 'GET', f'/v1/projects/{project.project_id}/{plural}/fixture/content',extra=extra)
    return get, calls


async def test_service_signature_alone_does_not_admit_private_media(playback):
    get, calls = playback
    response = await get()
    assert response.status_code == 401
    assert response.json()['detail']['error']['code'] == 'AUTHENTICATION_REQUIRED'
    assert response.headers['Cache-Control'] == 'no-store' and not calls


async def test_invalid_human_credential_never_reaches_private_media_delegate(playback):
    get, calls = playback
    response = await get({'Authorization': 'Bearer EXPLICIT_INVALID_FIXTURE'})
    assert response.status_code == 401 and not calls
    assert response.headers['Cache-Control'] == 'no-store'


async def test_real_human_viewer_and_service_grant_work_with_human_writes_disabled(api, playback):
    install_test_human_auth(api.app, platform_role=None,workspace_roles={api.stack.workspace.workspace_id:'viewer'})
    api.app.state.human_write_enabled = False
    get, calls = playback
    response = await get(TEST_HUMAN_HEADERS)
    assert response.status_code == 200 and response.content == b'EXPLICIT_AUTH_DELEGATE_FIXTURE'
    assert response.headers['Cache-Control'] == 'no-store'
    assert response.headers['X-NPD-Service-API-Version'] == 'video-factory-service.v1'
    assert len(calls) == 1


async def test_human_emergency_switch_keeps_private_bytes_closed(api, playback):
    api.app.state.human_api_enabled = False
    get, calls = playback
    response = await get(TEST_HUMAN_HEADERS)
    assert response.status_code == 503 and not calls
    assert response.headers['Cache-Control'] == 'no-store'


async def test_human_workspace_grant_is_independent_from_service_grant(api, playback):
    install_test_human_auth(api.app, platform_role=None,workspace_roles={'wsp_foreign_fixture':'viewer'})
    get, calls = playback
    response = await get(TEST_HUMAN_HEADERS)
    assert response.status_code in (403, 404) and not calls
    assert response.headers['Cache-Control'] == 'no-store'


async def test_service_capability_revocation_is_checked_before_human_or_media_delegate(api, playback):
    identity = api.app.state.bridge_auth_verifier.identities['agent-hub']
    api.app.state.bridge_auth_verifier.identities={'agent-hub':ServiceIdentity(identity.service_id,identity.roles,identity.keys,
        {api.stack.workspace.workspace_id:('project.write',)})}
    get, calls = playback
    response = await get(TEST_HUMAN_HEADERS)
    assert response.status_code == 403 and not calls
    assert response.headers['Cache-Control'] == 'no-store'
