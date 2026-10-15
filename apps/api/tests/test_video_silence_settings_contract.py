"""Actual SQLite/ASGI queue contract; mocked probe/runtime, no worker/ASR/provider calls."""
from fastapi import FastAPI, Depends
from httpx import AsyncClient, ASGITransport
import pytest
from app.auto_edit_job_routes import router
from app.human_auth import authorize_human_request
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_auto_edit_jobs import stack
from test_auto_edit_local_cpu import count
from test_local_uploaded_audio_provider import custody, reset_fixture, ExplicitCpuFixture


SETTINGS = dict(silence_threshold_db=-42.0, minimum_silence_duration=.75, padding_before=.12, padding_after=.2)


def web(env):
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(authorize_human_request)])
    app.state.auto_edit_job_service = env.jobs
    install_test_human_auth(app, platform_repository=env.platform, platform_role='editor', workspace_roles={'*': 'editor'})
    return app


def body(env):
    payload = env.payload.model_dump(mode='json')
    payload['configuration'].update(SETTINGS)
    return payload


@pytest.mark.asyncio
async def test_custom_silence_settings_survive_202_get_and_exact_key_replay_without_worker(custody, tmp_path, monkeypatch):
    env = await stack(tmp_path, custody, monkeypatch)
    endpoint = f'/api/v1/projects/{env.project.project_id}/analysis-jobs'
    before = (await env.repository.get_asset(env.completed.asset_id)).model_dump(mode='json')
    try:
        async with AsyncClient(transport=ASGITransport(web(env)), base_url='http://owned-silence-fixture') as client:
            payload = body(env)
            first = await client.post(endpoint, json=payload, headers=TEST_HUMAN_HEADERS)
            assert first.status_code == 202, first.text
            value = first.json()
            assert value['analysis']['configuration'] == payload['configuration']
            assert value['job']['status'] == 'queued' and value['analysis']['status'] == 'pending'
            assert value['analysis']['transcript'] is None
            assert not value['timeline_mutated'] and not value['source_media_mutated'] and not value['publishing_enabled']
            job_id = value['job']['job_id']
            read = await client.get(endpoint + '/' + job_id, headers=TEST_HUMAN_HEADERS)
            assert read.status_code == 200 and read.json()['analysis']['configuration'] == payload['configuration']
            replay = await client.post(endpoint, json=payload, headers=TEST_HUMAN_HEADERS)
            assert replay.status_code == 202 and replay.json()['job']['job_id'] == job_id
            assert replay.json()['analysis']['configuration'] == payload['configuration']
            assert ExplicitCpuFixture.calls == 0
            assert await count(env, 'auto_edit_analyses') == await count(env, 'jobs') == 1
            assert await count(env, 'transcripts') == await count(env, 'timelines') == 0
            assert (await env.repository.get_asset(env.completed.asset_id)).model_dump(mode='json') == before
    finally:
        await env.engine.dispose()


@pytest.mark.asyncio
async def test_setting_drift_cannot_reuse_key_and_invalid_ranges_create_no_authoritative_rows(custody, tmp_path, monkeypatch):
    env = await stack(tmp_path, custody, monkeypatch)
    endpoint = f'/api/v1/projects/{env.project.project_id}/analysis-jobs'
    try:
        async with AsyncClient(transport=ASGITransport(web(env)), base_url='http://owned-silence-fixture') as client:
            payload = body(env)
            first = await client.post(endpoint, json=payload, headers=TEST_HUMAN_HEADERS)
            assert first.status_code == 202, first.text
            original = first.json()
            for key, value in dict(silence_threshold_db=-40, minimum_silence_duration=.8, padding_before=.15, padding_after=.3).items():
                changed = body(env)
                changed['configuration'][key] = value
                conflict = await client.post(endpoint, json=changed, headers=TEST_HUMAN_HEADERS)
                assert conflict.status_code == 409, conflict.text
                assert await count(env, 'jobs') == await count(env, 'auto_edit_analyses') == 1
            for key, value in dict(silence_threshold_db=-81, minimum_silence_duration=.09, padding_before=-.01, padding_after=2.01).items():
                invalid = body(env)
                invalid['idempotency_key'] = 'invalid-range-' + key
                invalid['configuration'][key] = value
                rejected = await client.post(endpoint, json=invalid, headers=TEST_HUMAN_HEADERS)
                assert rejected.status_code == 422, rejected.text
            read = await client.get(endpoint + '/' + original['job']['job_id'], headers=TEST_HUMAN_HEADERS)
            assert read.json()['analysis']['configuration'] == payload['configuration']
            assert ExplicitCpuFixture.calls == 0
            assert await count(env, 'jobs') == await count(env, 'auto_edit_analyses') == 1
            assert await count(env, 'transcripts') == await count(env, 'timelines') == 0
    finally:
        await env.engine.dispose()


@pytest.mark.asyncio
async def test_each_custom_setting_changes_the_analysis_fingerprint_instead_of_reusing_other_configuration(custody, tmp_path, monkeypatch):
    env = await stack(tmp_path, custody, monkeypatch)
    endpoint = f'/api/v1/projects/{env.project.project_id}/analysis-jobs'
    try:
        async with AsyncClient(transport=ASGITransport(web(env)), base_url='http://owned-silence-fixture') as client:
            original = await client.post(endpoint, json=body(env), headers=TEST_HUMAN_HEADERS)
            assert original.status_code == 202, original.text
            fingerprints = {original.json()['analysis']['fingerprint']}
            identifiers = {original.json()['analysis']['analysis_id']}
            for key, value in dict(silence_threshold_db=-40, minimum_silence_duration=.8, padding_before=.15, padding_after=.3).items():
                changed = body(env)
                changed['idempotency_key'] = 'explicit-new-config-' + key
                changed['configuration'][key] = value
                result = await client.post(endpoint, json=changed, headers=TEST_HUMAN_HEADERS)
                assert result.status_code == 202, result.text
                saved = result.json()['analysis']
                assert saved['configuration'] == changed['configuration']
                assert saved['fingerprint'] not in fingerprints and saved['analysis_id'] not in identifiers
                fingerprints.add(saved['fingerprint'])
                identifiers.add(saved['analysis_id'])
            assert len(fingerprints) == len(identifiers) == 5 and ExplicitCpuFixture.calls == 0
            assert await count(env, 'jobs') == await count(env, 'auto_edit_analyses') == 5
            assert await count(env, 'transcripts') == await count(env, 'timelines') == 0
    finally:
        await env.engine.dispose()
