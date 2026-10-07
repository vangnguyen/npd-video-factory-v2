"""Verified human Owner controls over owned SQLite, with fixture-only scheduling."""
from datetime import timedelta

from fastapi import Depends
import httpx
import pytest

from app.analytics_refresh_routes import router
from app.db import utc_now
from app.human_auth import authorize_human_request
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_publication_api import application
from test_analytics_runtime import runtime_stack


def refresh_app(stack, role='owner'):
    app = application(stack, role=role); app.include_router(router, dependencies=[Depends(authorize_human_request)])
    return app


@pytest.mark.asyncio
async def test_owner_creates_disabled_plan_enables_revokes_and_reads_verified_audit(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    base = f'/api/v1/projects/{stack.publication.project_id}/analytics/refresh-plans'
    body = {'publication_id': stack.publication.publication_id, 'first_run_at': (utc_now() + timedelta(hours=1)).isoformat()}
    headers = {'Idempotency-Key': 'refresh-api-owned-fixture-key'}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=refresh_app(stack)), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        result = await client.post(base, json=body, headers=headers)
        assert result.status_code == 201 and result.headers['Cache-Control'] == 'no-store'
        plan = result.json(); assert plan['enabled'] is False and plan['created_by'] == 'usr:test-owner'
        assert (await client.post(base, json=body, headers=headers)).headers['X-Idempotent-Replay'] == 'true'
        endpoint = base + '/' + plan['plan_id']
        assert (await client.post(endpoint + '/state', json={'expected_revision': 1, 'enabled': True})).status_code == 422
        enable = {'expected_revision': 1, 'enabled': True, 'acknowledged_read_only': True}
        denied = await client.post(endpoint + '/state', json=enable)
        assert denied.status_code == 409 and 'ANALYTICS_SCHEDULED_REFRESH_DISABLED' in denied.text
        assert denied.headers['Cache-Control'] == 'no-store'
        stack.settings.analytics_scheduled_refresh_enabled = True
        enabled = await client.post(endpoint + '/state', json=enable)
        assert enabled.status_code == 200 and enabled.json()['revision'] == 2
        assert (await client.post(endpoint + '/state', json=enable)).status_code == 409
        disabled = await client.post(endpoint + '/state', json={'expected_revision': 2, 'enabled': False})
        assert disabled.status_code == 200 and disabled.json()['enabled'] is False
        history = (await client.get(endpoint + '/history')).json()
        assert len(history) == 3 and all(event['actor_ref'] == 'usr:test-owner' for event in history)
        assert len((await client.get(base)).json()) == 1
        assert (await client.get(base + '/arp_missing_fixture')).status_code == 404
    assert calls == []


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['editor', 'reviewer', 'viewer'])
async def test_other_roles_can_read_but_cannot_create_refresh_intent(runtime_stack, role):
    stack, _, _, calls, _, _ = runtime_stack
    base = f'/api/v1/projects/{stack.publication.project_id}/analytics/refresh-plans'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=refresh_app(stack, role)), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        response = await client.post(base, json={'publication_id': stack.publication.publication_id,
            'first_run_at': (utc_now() + timedelta(hours=1)).isoformat()}, headers={'Idempotency-Key': 'role-denied-refresh-owned-fixture'})
        assert response.status_code == 403
        assert (await client.get(base)).status_code == 200
    assert await stack.repository.list_syncs(stack.publication.project_id) == [] and calls == []
