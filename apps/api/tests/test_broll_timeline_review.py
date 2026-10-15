"""Owned SQL/ASGI fixtures; no provider, model, render or human UAT."""
import asyncio
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, select

from app.broll_timeline_review_api import BrollTimelineUpdate
from app.broll_timeline_review_command import BrollTimelineConflict, apply_broll_timeline, read_broll_timeline
from app.db import AssetORM, VideoProjectORM
from app.media_intelligence_db import MediaPlanItemORM, MediaPlanORM, MediaAssetProvenanceORM
from app.media_intelligence_models import MediaResolutionRequest
from app.platform_models import ProjectCreate
from app.timeline_db import TimelineORM, TimelineVersionORM
from test_broll_planner import prepare, add_asset, request as plan_request


ACTOR = 'usr:test-owner'


async def ready(tmp_path, rights='owned'):
    env = await prepare(tmp_path)
    asset = await add_asset(env, filename='review-support.jpg', rights=rights)
    plan = await env['planner'].create(project_id=env['project'].project_id, payload=plan_request(env))
    item = plan.items[0]
    job = await env['resolver'].enqueue(project_id=env['project'].project_id, media_plan_id=plan.media_plan_id,
        media_plan_item_id=item.media_plan_item_id, payload=MediaResolutionRequest(asset_id=asset.asset_id))
    assert (await env['resolver'].process(job.resolution_job_id)).status == 'succeeded'
    env.update(review_plan=plan, review_asset=asset, review_item=item)
    return env


async def read(env, actor=ACTOR):
    return await read_broll_timeline(env['timeline_service'], env['project'].project_id,
        env['review_plan'].media_plan_id, actor_ref=actor)


def body(context, *, key='review-broll-apply-0001', replace=False):
    return dict(expected_timeline_id=context['timeline_id'], expected_version=context['timeline_version'],
        expected_context_sha256=context['context_sha256'], request_key=key,
        item_ids=[context['ready_item_ids'][0]], replace_plan_clips=replace, acknowledged=True)


async def apply(env, payload, actor=ACTOR):
    return await apply_broll_timeline(env['timeline_service'], env['project'].project_id,
        env['review_plan'].media_plan_id, BrollTimelineUpdate.model_validate(payload), actor_ref=actor)


@asynccontextmanager
async def main_client(env, **auth):
    from app.main import app
    from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
    old = dict(app.state._state)
    try:
        app.state.timeline_service = env['timeline_service']
        install_test_human_auth(app, platform_repository=env['platform'], **auth)
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://owned-broll-timeline',
                headers=TEST_HUMAN_HEADERS) as client:
            yield app, client
    finally:
        object.__setattr__(app.state, '_state', old)


@pytest.mark.asyncio
async def test_exact_atomic_history_receipt_replay_preserves_other_tracks_and_invalidates_preview(tmp_path):
    env = await ready(tmp_path)
    try:
        before = await read(env)
        preview, _ = await env['timeline_service'].repository.create_preview(project_id=env['project'].project_id,
            timeline_version=1, width=540, height=960, actor_ref=ACTOR)
        request = body(before)
        result = await apply(env, request)
        timeline = result['timeline']
        assert timeline['timeline_id'] == before['timeline_id'] and timeline['current_version'] == 2
        assert timeline['approval_status'] == 'draft' and timeline['latest_preview_id'] is None
        assert result['provider_calls'] == 0 and result['publishing_enabled'] is False
        assert result['owner_approval_inferred'] is False and result['replayed'] is False
        assert result['media_binding_sha256'] == before['media_binding_sha256']
        assert result['receipt']['context_sha256'] == before['context_sha256']
        assert result['receipt']['actor_ref'] == ACTOR and result['receipt']['result_version'] == 2
        for track in before['timeline']['snapshot']['tracks']:
            if track['kind'] != 'broll':
                assert next(t for t in timeline['snapshot']['tracks'] if t['track_id'] == track['track_id']) == track
        clips = next(t for t in timeline['snapshot']['tracks'] if t['kind'] == 'broll')['clips']
        assert clips and all(c['asset_id'] == env['review_asset'].asset_id and c['volume'] == 0 for c in clips)
        assert timeline['snapshot']['duration_seconds'] == before['timeline']['snapshot']['duration_seconds']
        saved_parent = await env['timeline_service'].repository.get_version(before['timeline_id'], 1)
        assert saved_parent.snapshot.model_dump(mode='json') == before['timeline']['snapshot']
        assert (await env['timeline_service'].repository.get_preview(preview.preview_id)).status == 'stale'
        replay = await apply(env, request)
        assert replay == {**result, 'replayed': True}
        assert (await read(env))['receipt'] == result['receipt']
        async with env['session_factory']() as session:
            assert await session.scalar(select(func.count()).select_from(TimelineVersionORM)) == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['asset-provider', 'asset-size', 'asset-version', 'asset-provenance',
    'source-provider', 'plan-provenance', 'plan-item-placement', 'project-provenance'])
async def test_exact_context_rejects_metadata_drift_without_one_new_version(tmp_path, mutation):
    env = await ready(tmp_path)
    try:
        request = body(await read(env))
        async with env['session_factory']() as session:
            if mutation.startswith('asset-') or mutation == 'source-provider':
                a = await session.get(AssetORM, env['source_asset'].asset_id if mutation == 'source-provider' else env['review_asset'].asset_id)
                if mutation in {'asset-provider', 'source-provider'}:
                    a.storage_provider = 's3'
                elif mutation == 'asset-size':
                    a.size_bytes += 1
                elif mutation == 'asset-version':
                    a.version += 1
                else:
                    a.provenance = {**a.provenance, 'changed_after_review': True}
            elif mutation == 'plan-provenance':
                p = await session.get(MediaPlanORM, env['review_plan'].media_plan_id)
                p.provenance_json = {**p.provenance_json, 'changed_after_review': True}
            elif mutation == 'plan-item-placement':
                item = await session.get(MediaPlanItemORM, env['review_item'].media_plan_item_id)
                item.broll_json = {**item.broll_json, 'search_query': 'different reviewed intent'}
            else:
                p = await session.get(VideoProjectORM, env['project'].project_id)
                p.provenance = {**p.provenance, 'changed_after_review': True}
            await session.commit()
        with pytest.raises(BrollTimelineConflict, match='BROLL_REVIEW_CONTEXT_CHANGED'):
            await apply(env, request)
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['checksum', 'rights', 'license', 'restricted', 'foreign-scope', 'forged-publish'])
async def test_invalid_resolved_provenance_is_not_admitted_even_on_new_read(tmp_path, mutation):
    env = await ready(tmp_path)
    try:
        foreign = await env['platform'].create_project(env['project'].workspace_id,
            ProjectCreate(slug='foreign-broll-review', name='Explicit foreign project fixture', niche='technology')) if mutation == 'foreign-scope' else None
        async with env['session_factory']() as session:
            asset = await session.get(AssetORM, env['review_asset'].asset_id)
            if mutation == 'checksum':
                asset.checksum_sha256 = 'f' * 64
            elif mutation == 'foreign-scope':
                asset.project_id = foreign.project_id
            elif mutation == 'forged-publish':
                e = await session.scalar(select(MediaAssetProvenanceORM).where(MediaAssetProvenanceORM.asset_id == asset.asset_id))
                e.publishing_allowed = True  # synthetic fixture can never become production eligible
                e.production_eligible = True
            else:
                asset.provenance = {**asset.provenance, **({'license': 'changed'} if mutation == 'license' else
                    {'rights_status': 'restricted' if mutation == 'restricted' else 'unknown'})}
            await session.commit()
        with pytest.raises(BrollTimelineConflict):
            await read(env)
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_unknown_rights_remain_review_only_and_explicit_replace_is_separate_version(tmp_path):
    env = await ready(tmp_path, rights='unknown')
    try:
        result = await apply(env, body(await read(env)))
        clips = next(t for t in result['timeline']['snapshot']['tracks'] if t['kind'] == 'broll')['clips']
        assert all(c['metadata']['rights_status'] == 'unknown' and c['metadata']['publishing_allowed'] is False for c in clips)
        next_context = await read(env)
        with pytest.raises(BrollTimelineConflict, match='BROLL_REVIEW_SOURCE_OR_PLACEMENT_INVALID'):
            await apply(env, body(next_context, key='review-broll-apply-0002'))
        replaced = await apply(env, body(next_context, key='review-broll-apply-0003', replace=True))
        assert replaced['timeline']['current_version'] == 3
        assert len(next(t for t in replaced['timeline']['snapshot']['tracks'] if t['kind'] == 'broll')['clips']) == len(clips)
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_same_key_payload_actor_drift_and_superseded_receipts_fail_closed(tmp_path):
    env = await ready(tmp_path)
    try:
        request = body(await read(env))
        first = await apply(env, request)
        for changed, actor in [({**request, 'replace_plan_clips': True}, ACTOR), (request, 'usr:other-editor')]:
            with pytest.raises(BrollTimelineConflict, match='BROLL_TIMELINE_KEY_CONFLICT'):
                await apply(env, changed, actor)
        next_context = await read(env)
        await apply(env, body(next_context, key='review-broll-replace-0002', replace=True))
        with pytest.raises(BrollTimelineConflict, match='BROLL_TIMELINE_RECEIPT_SUPERSEDED'):
            await apply(env, request)
        assert first['timeline']['current_version'] == 2
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 3
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_concurrent_identical_retries_have_one_canonical_mutation(tmp_path):
    env = await ready(tmp_path)
    try:
        request = body(await read(env))
        values = await asyncio.gather(apply(env, request), apply(env, request))
        assert sorted(v['replayed'] for v in values) == [False, True]
        assert values[0]['receipt'] == values[1]['receipt']
        async with env['session_factory']() as session:
            assert await session.scalar(select(func.count()).select_from(TimelineVersionORM)) == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_transaction_failure_rolls_back_canonical_history_preview_and_receipt(tmp_path, monkeypatch):
    env = await ready(tmp_path)
    try:
        before = await read(env)
        preview, _ = await env['timeline_service'].repository.create_preview(project_id=env['project'].project_id,
            timeline_version=1, width=540, height=960, actor_ref=ACTOR)
        repository = env['timeline_service'].repository
        original = repository.commit_mutation_in_session

        async def fail_after_mutation(**kwargs):
            await original(**kwargs)
            await kwargs['session'].flush()
            raise RuntimeError('injected owned transaction failure')

        monkeypatch.setattr(repository, 'commit_mutation_in_session', fail_after_mutation)
        with pytest.raises(RuntimeError, match='injected owned'):
            await apply(env, body(before))
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 1
        assert (await env['timeline_service'].repository.get_preview(preview.preview_id)).status == 'queued'
        async with env['session_factory']() as session:
            assert await session.scalar(select(func.count()).select_from(TimelineVersionORM)) == 1
        monkeypatch.setattr(repository, 'commit_mutation_in_session', original)
        assert (await apply(env, body(before)))['timeline']['current_version'] == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('workspace_id', 'wsp_foreign'), ('parent_version_id', 'tlv_missing')])
async def test_read_rejects_corrupt_receipt_workspace_and_parent(tmp_path, field, value):
    env = await ready(tmp_path)
    try:
        result = await apply(env, body(await read(env)))
        async with env['session_factory']() as session:
            version = await session.get(TimelineVersionORM, result['timeline']['current_version_id'])
            version.mutation_json = {**version.mutation_json, 'receipt': {**version.mutation_json['receipt'], field: value}}
            await session.commit()
        with pytest.raises(BrollTimelineConflict, match='BROLL_TIMELINE_RECEIPT_INVALID'):
            await read(env)
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
async def test_actual_main_auth_no_store_exact_receipt_and_read_only_get(tmp_path):
    env = await ready(tmp_path)
    try:
        url = f"/api/v1/projects/{env['project'].project_id}/timeline/broll-review/{env['review_plan'].media_plan_id}"
        async with main_client(env) as (_, client):
            before = await client.get(url)
            assert before.status_code == 200 and before.headers['cache-control'] == 'no-store'
            assert before.json()['receipt'] is None
            request = body(before.json())
            saved = await client.put(url, json=request)
            assert saved.status_code == 200 and saved.headers['cache-control'] == 'no-store'
            assert saved.json()['receipt']['actor_ref'] == ACTOR
            replay = await client.put(url, json=request)
            assert replay.json() == {**saved.json(), 'replayed': True}
            assert (await client.get(url)).json()['receipt'] == saved.json()['receipt']
            assert (await client.get(url.replace(env['project'].project_id, 'prj_foreign'))).status_code == 404
            assert (await client.get(url, headers={'Authorization': 'Bearer wrong'})).status_code == 401
        async with env['session_factory']() as session:
            assert await session.scalar(select(func.count()).select_from(TimelineVersionORM)) == 2
    finally:
        await env['engine'].dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,status', [('viewer', 403), ('write-disabled', 503), ('unauthenticated', 401)])
async def test_actual_main_denies_write_before_invalid_private_body(tmp_path, mode, status):
    env = await ready(tmp_path)
    try:
        auth = dict(platform_role='viewer', workspace_roles={'*': 'viewer'}) if mode == 'viewer' else {}
        async with main_client(env, **auth) as (app, client):
            if mode == 'write-disabled':
                app.state.human_write_enabled = False
            headers = {'Authorization': 'Bearer wrong'} if mode == 'unauthenticated' else {}
            url = f"/api/v1/projects/{env['project'].project_id}/timeline/broll-review/{env['review_plan'].media_plan_id}"
            assert (await client.put(url, json={'arbitrary': 'invalid body'}, headers=headers)).status_code == status
        assert (await env['timeline_service'].get(env['project'].project_id)).current_version == 1
    finally:
        await env['engine'].dispose()


@pytest.mark.parametrize('change', [{'acknowledged': False}, {'acknowledged': 1}, {'expected_version': True},
    {'expected_version': '1'}, {'replace_plan_clips': 1}, {'item_ids': ['item_a', 'item_a']},
    {'expected_context_sha256': 'not-a-hash'}, {'provider_graph': {}}, {'item_ids': []}])
def test_closed_review_contract(change):
    valid = dict(expected_timeline_id='tml_fixture_0001', expected_version=1, expected_context_sha256='a' * 64,
        request_key='review-fixture-0001', item_ids=['item_a'], replace_plan_clips=False, acknowledged=True)
    with pytest.raises(ValidationError):
        BrollTimelineUpdate.model_validate({**valid, **change})
