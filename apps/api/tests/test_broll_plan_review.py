"""Actual SQLite/HTTP, explicit synthetic metadata and mock stock transport.

No model, genuine provider credential, paid operation, browser or real media.
"""
import asyncio
import copy
from dataclasses import replace

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import func, select, update

from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_broll_planner import prepare
from test_stock_planner_retry import prepared, action
from app.broll_plan_review_api import router, BrollPlanPrepare
from app.db import AssetORM
from app.human_auth import authorize_human_request
from app.media_intelligence_db import MediaPlanORM
from app.service_api_repository import ServiceOperationORM
from app.timeline_db import TimelineORM
from app.timeline_logic import build_initial_timeline
from app.timeline_repository import TimelineRepository


def server(env, role='owner'):
    api = FastAPI()
    api.include_router(router, dependencies=[Depends(authorize_human_request)])
    api.state.media_planning_service = env['planner']
    from app.main import human_session
    api.add_api_route('/api/v1/auth/session', human_session, methods=['GET'], dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(api, platform_repository=env['platform'], platform_role=role,
        workspace_roles={'*': role})
    return api


def body(context, *, stock=False, key='reviewed-broll-request-0001'):
    return {'request_key': key, 'context_sha256': context['context_sha256'], 'acknowledged': True,
        'learning_snapshot_id': None,
        'settings': {'allow_stock': stock, 'allow_ai_image': False, 'allow_ai_video': False,
            'max_ai_cost_vnd': '0', 'resolver_priority': ['licensed_stock'] if stock else ['user_asset', 'internal_library']}}


async def client_for(env, role='owner'):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=server(env, role)),
        base_url='http://test', headers=TEST_HUMAN_HEADERS)


async def stock_env(tmp_path):
    env, adapter, payload, calls, stamp = await prepared(tmp_path, {})
    source = await env['auto_repository'].get_asset(env['source_asset'].asset_id)
    timeline = build_initial_timeline(analysis=env['auto_edit'], source_asset=source, media_plan=None, media_assets={})
    await TimelineRepository(env['session_factory']).create_timeline(project_id=env['project'].project_id,
        source_analysis_id=env['auto_edit'].analysis_id, source_media_plan_id=None, snapshot=timeline, actor_ref='fixture')
    return env, adapter, calls


@pytest.mark.asyncio
async def test_context_and_local_plan_are_read_only_provider_zero_and_exact_replay(tmp_path):
    env = await prepare(tmp_path)
    path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    try:
        async with await client_for(env) as client:
            c = (await client.get(path)).json()
            assert c['preparation_provider_calls'] == 0 and not c['licensed_stock_enabled']
            assert c['source']['transcript_id'] == env['auto_edit'].transcript.transcript_id
            r = await client.post(path, json=body(c))
            assert r.status_code == 201, r.text
            value = r.json()
            assert value['state'] == 'prepared' and value['preparation_provider_calls'] == 0
            assert value['plan']['configuration']['allow_stock'] is False
            assert value['receipt']['timeline_version'] == 1
            replay = (await client.post(path, json=body(c))).json()
            assert replay == {**value, 'replayed': True}
            assert (await client.get(path + '/requests/reviewed-broll-request-0001')).json() == replay
            conflict = body(c); conflict['settings']['resolver_priority'].reverse()
            assert (await client.post(path, json=conflict)).status_code == 409
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM)) == 1
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM)) == 1
                assert (await s.scalar(select(TimelineORM))).current_version == 1
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_stock_preparation_persists_review_gate_worker_and_direct_process_cannot_dispatch(tmp_path):
    env, adapter, calls = await stock_env(tmp_path)
    path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    try:
        async with await client_for(env) as client:
            c = (await client.get(path)).json()
            assert c['licensed_stock_enabled']
            result = await client.post(path, json=body(c, stock=True))
            assert result.status_code == 201, result.text
            p = await env['planner'].get(result.json()['plan']['media_plan_id'])
            assert p.stock_planning.status == 'waiting' and p.stock_planning.provider_calls == 0
            assert p.provenance['stock_planner_execution']['review_required'] is True
            assert calls == [] and await env['planner'].recover_due_stock_plans() == 0
            await env['planner'].process_stock_plan(p.media_plan_id)
            assert calls == []
            approved = await env['planner'].retry_stock_search(p.media_plan_id, action(p))
            assert approved.stock_planning.status == 'succeeded' and calls
            assert approved.provenance['stock_planner_execution']['review_required'] is False
    finally:
        await adapter.aclose(); await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('drift', ['source', 'timeline', 'provider', 'authority', 'transcript', 'rights'])
async def test_drift_rejects_before_any_plan_or_receipt(tmp_path, drift):
    env = await prepare(tmp_path)
    path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    api = server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url='http://test', headers=TEST_HUMAN_HEADERS) as client:
            c = (await client.get(path)).json()
            if drift == 'provider': env['planner'].allow_external_execution = True
            elif drift == 'authority': install_test_human_auth(api, platform_repository=env['platform'], platform_role='editor', workspace_roles={'*': 'editor'})
            else:
                async with env['session_factory']() as s:
                    if drift == 'source':
                        asset = await s.get(AssetORM, env['source_asset'].asset_id); asset.checksum_sha256 = 'f' * 64
                    elif drift == 'rights':
                        asset = await s.get(AssetORM, env['source_asset'].asset_id); asset.provenance = {**asset.provenance, 'rights_status': 'restricted'}
                    elif drift == 'transcript':
                        from app.auto_edit_db import TranscriptSegmentORM
                        segment = await s.scalar(select(TranscriptSegmentORM)); segment.text = 'Changed exact saved speech'
                    else:
                        timeline = await s.scalar(select(TimelineORM)); timeline.current_version = 99
                    await s.commit()
            r = await client.post(path, json=body(c))
            assert r.status_code == 409, r.text
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM)) == 0
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM)) == 0
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_unknown_attempt_is_never_redispatched_and_concurrent_request_observes_same_receipt(tmp_path):
    env = await prepare(tmp_path)
    path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    entered, resume = asyncio.Event(), asyncio.Event()
    attempts = []
    async def uncertain(**kwargs):
        attempts.append(kwargs); entered.set(); await resume.wait(); raise OSError('private detail never exposed')
    env['planner'].create = uncertain
    try:
        async with await client_for(env) as client:
            c = (await client.get(path)).json(); request = body(c)
            task = asyncio.create_task(client.post(path, json=request))
            await asyncio.wait_for(entered.wait(), 10)
            observed = await client.post(path, json=request)
            assert observed.status_code == 202 and observed.json()['state'] == 'unknown'
            resume.set(); failed = await task
            assert failed.status_code == 503 and 'private detail' not in failed.text
            again = await client.post(path, json=request)
            assert again.status_code == 202 and len(attempts) == 1
            assert (await client.get(path + '/requests/' + request['request_key'])).json()['state'] == 'unknown'
    finally: resume.set(); await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['ack', 'boolean', 'ai', 'paid', 'stock', 'extra'])
async def test_strict_options_fail_closed(tmp_path, change):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    try:
        async with await client_for(env) as client:
            c = (await client.get(path)).json(); request = body(c)
            if change == 'ack': request['acknowledged'] = 1
            elif change == 'boolean': request['settings']['allow_stock'] = 'false'
            elif change == 'ai': request['settings']['allow_ai_image'] = True
            elif change == 'paid': request['settings']['max_ai_cost_vnd'] = '1'
            elif change == 'stock': request['settings']['resolver_priority'].append('licensed_stock')
            else: request['actor_ref'] = 'fake-owner'
            assert (await client.post(path, json=request)).status_code == 422
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_viewer_read_only_and_absent_auth_cannot_prepare(tmp_path):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    try:
        async with await client_for(env, 'viewer') as client:
            c = (await client.get(path)).json()
            assert c['can_prepare'] is False
            assert (await client.post(path, json=body(c))).status_code == 403
            assert (await client.get(path, headers={'Authorization': ''})).status_code == 401
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_disabled_ai_estimates_never_execute_even_when_providers_configured(tmp_path):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    calls = []
    async def deny(*args, **kwargs):
        calls.append('estimate'); raise AssertionError('Disabled AI must not call estimate')
    env['planner'].providers.image.estimate_cost = deny
    env['planner'].providers.video.estimate_cost = deny
    try:
        async with await client_for(env) as client:
            context = (await client.get(path)).json()
            result = await client.post(path, json=body(context))
            assert result.status_code == 201, result.text
            assert calls == []
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_postflight_canonical_drift_rejects_receipt_and_does_not_redispatch(tmp_path):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    create = env['planner'].create; calls = []
    async def drift(**kwargs):
        result = await create(**kwargs); calls.append(result.media_plan_id)
        async with env['session_factory']() as s:
            asset = await s.get(AssetORM, env['source_asset'].asset_id)
            asset.filename = 'changed-after-prepare.mp4'; await s.commit()
        return result
    env['planner'].create = drift
    try:
        async with await client_for(env) as client:
            context = (await client.get(path)).json(); request = body(context)
            result = await client.post(path, json=request)
            assert result.status_code == 409 and result.json()['state'] == 'rejected'
            assert result.json()['plan'] is None
            assert (await client.post(path, json=request)).status_code == 409 and len(calls) == 1
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_opted_in_learning_uses_existing_scoped_reader_and_invalid_snapshot_is_rejected_before_reservation(tmp_path):
    from app.learning_service import LearningError
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    calls = []
    class ExplicitLearningReaderFixture:
        async def feedback(self, workspace, identity, *, niche):
            calls.append((workspace, identity, niche))
            if identity == 'lsn_missing_fixture': raise LearningError('LEARNING_SNAPSHOT_NOT_FOUND')
            if identity == 'lsn_wrong_niche': raise LearningError('LEARNING_NICHE_MISMATCH')
            return {'learning_snapshot_id': identity, 'content_sha256': 'a' * 64, 'recommendation_only': True,
                'autonomous_execution': False, 'recommendations': [], 'mock_feedback_reader': True}
    env['planner'].learning = ExplicitLearningReaderFixture()
    try:
        async with await client_for(env) as client:
            c = (await client.get(path)).json()
            for identity, status in [('lsn_missing_fixture', 404), ('lsn_wrong_niche', 409)]:
                request = body(c); request['learning_snapshot_id'] = identity
                assert (await client.post(path, json=request)).status_code == status
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM)) == 0
            request = body(c); request['learning_snapshot_id'] = 'lsn_selected_fixture'
            result = await client.post(path, json=request)
            assert result.status_code == 201, result.text
            assert result.json()['receipt']['learning_snapshot_id'] == request['learning_snapshot_id']
            assert result.json()['plan']['provenance']['learning_feedback']['recommendation_only']
            assert all(workspace == env['project'].workspace_id and niche == env['project'].niche for workspace, _, niche in calls)
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_foreign_authority_cannot_read_or_replay_held_receipt(tmp_path):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    api = server(env)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api), base_url='http://test', headers=TEST_HUMAN_HEADERS) as client:
            context = (await client.get(path)).json(); request = body(context)
            assert (await client.post(path, json=request)).status_code == 201
            # Different still-authorized identity. The original receipt stays private.
            old = api.state.human_auth_verifier.registry
            record = old.tokens['test-owner'].model_copy(update={'subject': 'usr:other-editor'})
            from app.human_auth import HumanAuthVerifier
            api.state.human_auth_verifier = HumanAuthVerifier(old.model_copy(update={'tokens': {'test-owner': record}}), max_token_ttl_seconds=86400)
            assert (await client.get(path + '/requests/' + request['request_key'])).status_code == 404
            assert (await client.post(path, json=request)).status_code == 409
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
async def test_get_has_real_sqlite_snapshot_and_zero_dml_post_reserves_before_planning(tmp_path):
    from sqlalchemy import event
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    statements = []
    @event.listens_for(env['engine'].sync_engine, 'before_cursor_execute')
    def record(_conn, _cursor, statement, _parameters, _context, _many):
        statements.append(statement.strip().upper())
    create = env['planner'].create
    async def check_reservation(**kwargs):
        async with env['session_factory']() as s:
            row = await s.scalar(select(ServiceOperationORM))
            assert row is not None and row.status == 'running' and row.response_json['receipt']['actor_ref'] == 'usr:test-owner'
        return await create(**kwargs)
    env['planner'].create = check_reservation
    try:
        async with await client_for(env) as client:
            result = await client.get(path); assert result.status_code == 200
            # Human RBAC SELECTs precede the command-owned transaction; BEGIN
            # still precedes all coherent timeline/source reads in that command.
            starts = [i for i, value in enumerate(statements) if value == 'BEGIN']
            timeline_select = next(i for i, value in enumerate(statements) if value.startswith('SELECT') and 'FROM TIMELINES' in value)
            assert starts and starts[0] < timeline_select
            assert not any(value.startswith(('INSERT ', 'UPDATE ', 'DELETE ')) for value in statements)
            statements.clear()
            assert (await client.post(path, json=body(result.json()))).status_code == 201
            begin = statements.index('BEGIN IMMEDIATE')
            reserve = next(i for i, value in enumerate(statements) if value.startswith('INSERT INTO SERVICE_API_OPERATIONS'))
            assert begin < reserve
    finally: await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('interrupted', ['failed', 'cancelled_before_item_commit'])
async def test_failed_or_incomplete_cached_plan_is_not_reported_prepared(tmp_path, monkeypatch, interrupted):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    original = env['media_repository'].save_plan_items
    async def fail(**kwargs):
        if interrupted == 'failed': raise OSError('Explicit local item commit failure')
        raise asyncio.CancelledError()
    try:
        async with await client_for(env) as client:
            context = (await client.get(path)).json()
            monkeypatch.setattr(env['media_repository'], 'save_plan_items', fail)
            if interrupted == 'failed':
                assert (await client.post(path, json=body(context))).status_code == 503
            else:
                with pytest.raises(asyncio.CancelledError): await client.post(path, json=body(context))
            monkeypatch.setattr(env['media_repository'], 'save_plan_items', original)
            result = await client.post(path, json=body(context, key='second-reviewed-intent-0002'))
            assert result.status_code == 503, result.text
            assert result.json()['detail']['error']['code'] == 'BROLL_PREPARATION_OUTCOME_UNKNOWN'
            observed = await client.get(path + '/requests/second-reviewed-intent-0002')
            assert observed.json()['state'] == 'unknown' and observed.json()['plan'] is None
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM)) == 1
                plan = await s.scalar(select(MediaPlanORM))
                assert plan.status == ('failed' if interrupted == 'failed' else 'draft')
    finally: await env['engine'].dispose()


async def secondary_project(env, tmp_path):
    """Same-workspace independent graph, based on the reviewer's valid repro."""
    from app.platform_models import ProjectCreate, AssetRegister
    from app.auto_edit_service import AutoEditAnalysisService
    from app.auto_edit_models import AutoEditAnalysisRequest
    from app.auto_edit_providers import DeterministicTranscriptionProvider, DeterministicMediaSignalProvider
    project = await env['platform'].create_project(env['project'].workspace_id,
        ProjectCreate(slug='second-broll-project', name='Second synthetic B-roll fixture', niche='real_estate'))
    await env['platform'].ensure_initial_version(project.project_id, snapshot={'fixture': True})
    old = await env['auto_repository'].get_asset(env['source_asset'].asset_id)
    key = f'workspaces/{project.workspace_id}/projects/{project.project_id}/uploads/second.mp4'
    stored = await env['storage'].put_file(object_key=key, path=env['storage']._path(old.object_key), content_type=old.content_type)
    asset = await env['platform'].register_asset(project.project_id, AssetRegister(asset_class='source', kind='video',
        filename='second.mp4', object_key=key, content_type=stored.content_type, size_bytes=stored.size_bytes,
        checksum_sha256=stored.checksum_sha256, storage_provider=stored.storage_provider, provenance=copy.deepcopy(old.provenance)))
    service = AutoEditAnalysisService(repository=env['auto_repository'], platform=env['platform'], object_storage=env['storage'],
        transcription_provider=DeterministicTranscriptionProvider(), signal_provider=DeterministicMediaSignalProvider(), staging_root=tmp_path/'second-analysis')
    analysis = await service.analyze(project.project_id, AutoEditAnalysisRequest(asset_id=asset.asset_id, top_highlights=3))
    snapshot = build_initial_timeline(analysis=analysis, source_asset=asset, media_plan=None, media_assets={})
    await TimelineRepository(env['session_factory']).create_timeline(project_id=project.project_id,
        source_analysis_id=analysis.analysis_id, source_media_plan_id=None, snapshot=snapshot, actor_ref='fixture')
    return project


@pytest.mark.asyncio
async def test_identical_logical_key_is_independent_for_two_authorized_projects(tmp_path):
    env = await prepare(tmp_path); path = f"/api/v1/projects/{env['project'].project_id}/broll-plan-review"
    try:
        async with await client_for(env) as client:
            first_context = (await client.get(path)).json(); first = await client.post(path, json=body(first_context))
            assert first.status_code == 201
            second_project = await secondary_project(env, tmp_path)
            second_path = f'/api/v1/projects/{second_project.project_id}/broll-plan-review'
            second_context = (await client.get(second_path)).json()
            second = await client.post(second_path, json=body(second_context))
            assert second.status_code == 201, second.text
            assert first.json()['receipt']['operation_id'] != second.json()['receipt']['operation_id']
            assert first.json()['plan']['project_id'] != second.json()['plan']['project_id']
            async with env['session_factory']() as s:
                assert await s.scalar(select(func.count()).select_from(ServiceOperationORM)) == 2
                assert await s.scalar(select(func.count()).select_from(MediaPlanORM)) == 2
    finally: await env['engine'].dispose()
