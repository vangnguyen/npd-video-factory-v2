"""Actual main ASGI + owned SQLite; no lifespan, renderer or provider dispatch."""
import httpx
import pytest

from app import main
from app.sql_variant_narration_runtime import create_variant_narration_runtime
from auth_test_support import TEST_HUMAN_HEADERS
from test_sql_variant_narration_proposal import prepared, all_rows
from test_sql_variant_narration_reuse import env, narration_env
from test_sql_variant_narration_activation import base


@pytest.mark.asyncio
async def test_main_proposal_route_authenticates_once_and_never_executes(prepared, monkeypatch):
    fixture = prepared
    app = main.app
    prior = dict(app.state._state)
    object.__setattr__(app.state, '_state', dict(fixture.app.state._state))
    def deny(*_args, **_kwargs):
        raise AssertionError('MAIN_PROPOSAL_READ_MUST_NOT_EXECUTE')
    for target, name in [(fixture.f.env.storage, 'download_file'),
                         (fixture.runtime.service.copier, 'copy'),
                         (fixture.runtime.loader, 'prepare'),
                         (fixture.f.env.queue, 'rpush'),
                         (fixture.f.env.platform, 'record_provider_operation')]:
        monkeypatch.setattr(target, name, deny)
    try:
        before = await all_rows(fixture)
        url = base(fixture.f) + '/narration-reuse-proposal'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app),
                                    base_url='http://owned-main-proposal') as client:
            denied = await client.get(url + '?untrusted=private-fixture')
            assert denied.status_code == 401 and denied.headers['cache-control'] == 'no-store'
            response = await client.get(url, headers=TEST_HUMAN_HEADERS)
            assert response.status_code == 200, response.text
            assert response.json()['actor_ref'] == 'usr:test-owner'
            assert response.json()['approval_transferred'] is False
            assert response.headers['cache-control'] == 'no-store'
            assert sum(app.state.human_rate_limiter.store.counts.values()) == 1
            app.state.sql_variant_narration_runtime = create_variant_narration_runtime(
                session_factory=fixture.f.env.factory, object_storage=fixture.f.env.storage,
                assets=fixture.f.env.assets)
            disabled = await client.get(url, headers=TEST_HUMAN_HEADERS)
            assert disabled.status_code == 503
            assert sum(app.state.human_rate_limiter.store.counts.values()) == 2
        assert await all_rows(fixture) == before
    finally:
        object.__setattr__(app.state, '_state', prior)
