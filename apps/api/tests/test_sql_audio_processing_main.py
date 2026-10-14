"""Actual main routes and owned SQLite, without lifespan/provider/media calls."""
import httpx
import pytest

from app import main
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_timeline_audio_processing_api import processing_api, body, state
from test_mvp1_multi_input import env


@pytest.mark.asyncio
async def test_main_processing_read_revision_and_exact_replay(processing_api):
    a, app = processing_api, main.app
    prior = dict(app.state._state)
    object.__setattr__(app.state, '_state', dict(a.app.state._state))
    try:
        before = await state(a)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-processing-main') as client:
            session = await client.get('/api/v1/auth/session', headers=TEST_HUMAN_HEADERS)
            assert session.status_code == 200
            assert set(session.json()) == {'subject', 'display_name', 'platform_role', 'workspace_roles',
                                         'expires_at', 'human_write_enabled'}
            read = await client.get(a.path, headers=TEST_HUMAN_HEADERS)
            assert read.status_code == 200 and read.headers['cache-control'] == 'no-store'
            assert read.json()['receipt'] is None
            assert read.json()['configuration']['duck_music'] is False
            assert read.json()['configuration']['duck_threshold'] == .02
            assert await state(a) == before
            update = await client.put(a.path, json=body(a), headers=TEST_HUMAN_HEADERS)
            assert update.status_code == 200, update.text
            assert update.json()['timeline']['current_version'] == 2
            assert update.json()['receipt']['actor_ref'] == 'usr:test-owner'
            after = await state(a)
            replay = await client.put(a.path, json=body(a), headers=TEST_HUMAN_HEADERS)
            assert replay.status_code == 200 and replay.json()['replayed'] is True
            assert replay.json()['receipt'] == update.json()['receipt']
            assert await state(a) == after
            assert sum(app.state.human_rate_limiter.store.counts.values()) == 4
        assert a.env.queue.values == []
    finally:
        object.__setattr__(app.state, '_state', prior)


@pytest.mark.parametrize('mode,status', [('viewer', 403), ('write_off', 503),
                                      ('unauthenticated', 401), ('foreign', 404)])
@pytest.mark.asyncio
async def test_main_processing_admission_precedes_invalid_body(processing_api, mode, status):
    a, app = processing_api, main.app
    prior = dict(app.state._state)
    object.__setattr__(app.state, '_state', dict(a.app.state._state))
    try:
        before = await state(a)
        if mode in {'viewer', 'foreign'}:
            install_test_human_auth(app, platform_repository=a.env.platform, platform_role=None,
                workspace_roles={a.env.workspace.workspace_id: 'viewer'} if mode == 'viewer'
                else {'wsp_foreign': 'editor'})
        elif mode == 'write_off':
            app.state.human_write_enabled = False
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-processing-main') as client:
            response = await client.put(a.path, json={'invalid_private_fixture': True},
                headers={} if mode == 'unauthenticated' else TEST_HUMAN_HEADERS)
            assert response.status_code == status, response.text
            if mode in {'viewer', 'write_off'}:
                read = await client.get(a.path, headers=TEST_HUMAN_HEADERS)
                assert read.status_code == 200 and read.headers['cache-control'] == 'no-store'
        assert await state(a) == before and a.env.queue.values == []
    finally:
        object.__setattr__(app.state, '_state', prior)
