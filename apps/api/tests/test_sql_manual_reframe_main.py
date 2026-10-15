"""Actual main/owned SQLite, no lifespan/media/ASR/provider or Owner acceptance."""
from contextlib import asynccontextmanager

import httpx
import pytest

from app import main
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_source_linked_edit_api import linked_api, state
from test_manual_reframe_api import manual, body


@asynccontextmanager
async def actual_main(a):
    app = main.app
    prior = dict(app.state._state)
    object.__setattr__(app.state, '_state', dict(a.app.state._state))
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-manual-reframe-main') as client:
            yield app, client
    finally:
        object.__setattr__(app.state, '_state', prior)


@pytest.mark.asyncio
async def test_main_manual_reframe_exact_roundtrip_history_replay_and_stale_cas(manual):
    a = manual
    async with actual_main(a) as (app, client):
        before = await state(a)
        session = await client.get('/api/v1/auth/session', headers=TEST_HUMAN_HEADERS)
        assert session.status_code == 200
        assert set(session.json()) == {'subject', 'display_name', 'platform_role', 'workspace_roles',
                                      'expires_at', 'human_write_enabled'}
        read = await client.get(a.path, headers=TEST_HUMAN_HEADERS)
        assert read.status_code == 200 and read.headers['cache-control'] == 'no-store'
        assert read.json()['receipt'] is None and await state(a) == before
        update = await client.put(a.path, json=body(a), headers=TEST_HUMAN_HEADERS)
        assert update.status_code == 200, update.text
        saved = update.json()
        assert saved['receipt']['actor_ref'] == 'usr:test-owner'
        current = await client.get(a.path, headers=TEST_HUMAN_HEADERS)
        canonical = await client.get(f'/api/v1/projects/{a.project.project_id}/timeline', headers=TEST_HUMAN_HEADERS)
        history = await client.get(f'/api/v1/projects/{a.project.project_id}/timeline/versions', headers=TEST_HUMAN_HEADERS)
        assert current.status_code == canonical.status_code == history.status_code == 200
        assert saved['timeline'] == current.json()['timeline'] == canonical.json()
        assert saved['timeline']['created_at'].endswith('Z') and saved['timeline']['updated_at'].endswith('Z')
        head = next(v for v in history.json() if v['version'] == saved['timeline']['current_version'])
        assert head['timeline_version_id'] == saved['timeline']['current_version_id']
        assert head['snapshot'] == saved['timeline']['snapshot']
        assert head['actor_ref'] == saved['receipt']['actor_ref']
        assert head['mutation'] == {'type': 'manual-reframe', 'receipt': saved['receipt'],
                                    'source_media_mutated': False, 'publish_requested': False}
        after = await state(a)
        replay = await client.put(a.path, json=body(a), headers=TEST_HUMAN_HEADERS)
        assert replay.status_code == 200 and replay.json()['replayed'] is True
        assert replay.json()['receipt'] == saved['receipt'] and replay.json()['timeline'] == canonical.json()
        assert await state(a) == after
        assert sum(app.state.human_rate_limiter.store.counts.values()) == 7
        stale = await client.put(a.path, json=body(a, request_key='different-manual-reframe-intent'), headers=TEST_HUMAN_HEADERS)
        assert stale.status_code == 409 and await state(a) == after


@pytest.mark.parametrize('mode,status', [('viewer', 403), ('write_off', 503),
                                      ('unauthenticated', 401), ('foreign', 404)])
@pytest.mark.asyncio
async def test_main_manual_reframe_admission_before_invalid_private_body(manual, mode, status):
    a = manual
    async with actual_main(a) as (app, client):
        before = await state(a)
        if mode in {'viewer', 'foreign'}:
            install_test_human_auth(app, platform_repository=a.platform, platform_role=None,
                workspace_roles={a.project.workspace_id: 'viewer'} if mode == 'viewer'
                else {'wsp_foreign': 'editor'})
        elif mode == 'write_off':
            app.state.human_write_enabled = False
        response = await client.put(a.path, json={'invalid_private_fixture': True},
            headers={} if mode == 'unauthenticated' else TEST_HUMAN_HEADERS)
        assert response.status_code == status, response.text
        if mode in {'viewer', 'write_off'}:
            read = await client.get(a.path, headers=TEST_HUMAN_HEADERS)
            assert read.status_code == 200 and read.headers['cache-control'] == 'no-store'
        assert await state(a) == before
