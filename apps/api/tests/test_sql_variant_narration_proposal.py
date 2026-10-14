"""Actual owned SQLite/ASGI proposals; synthetic saved PCM, no model/render wire."""
import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends
from sqlalchemy import event, select, text

from app.db import Base, AssetORM
from app.content_models import ContentDocument, ContentSaveRequest
from app.timeline_models import TimelineCreateRequest
from app.production_models import ProductionPackageCreateRequest, ApprovalRequest
from app.platform_models import ProjectVersionCreate
from app.production_routes import router as production_router
from app.timeline_routes import router as timeline_router
from app.content_routes import router as content_router
from app.platform_routes import router as platform_router
from app.human_auth import authorize_human_request
from app.sql_variant_models import canonical, digest
from app.sql_variant_repository import record_value
from app.sql_variant_narration_proposal_routes import register_variant_narration_proposal_routes
from app.sql_variant_narration_proposal import read_narration_proposal
from app.sql_variant_narration_runtime import create_variant_narration_runtime
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_sql_variant_narration_reuse import env, narration_env
from test_sql_variant_narration_activation import factory, app_for, base


@pytest.fixture
async def prepared(narration_env):
    f = narration_env
    # Independent first-party PNG rights fixture, as in the existing S5 tests.
    # No master rights/approval is inherited, and copied narration remains unknown.
    async with f.env.factory() as session, session.begin():
        assets = (await session.scalars(select(AssetORM).where(AssetORM.project_id == f.child.project_id))).all()
        for asset in assets:
            asset.provenance = {**asset.provenance, 'rights_status': 'owned', 'fixture_child_rights_decision': True}
            asset.version += 1
    version = await f.env.platform.get_version(f.request.expected_child_content_version_id)
    document = ContentDocument.model_validate(version.snapshot['content']).model_copy(update={'approved': True})
    approved = await f.env.content.save(f.child.project_id, ContentSaveRequest(
        expected_content_version_id=version.project_version_id, document=document), actor_ref='explicit-fixture-editor')
    built = await f.env.service.create(f.child.project_id, TimelineCreateRequest(source_kind='storyboard_media',
        content_version_id=approved.project_version_id, expected_timeline_version=f.child.current_version))
    package = await f.env.package.create_or_refresh(f.child.project_id, ProductionPackageCreateRequest())
    runtime, repository, service = factory(f)
    app = app_for(f, runtime, service)
    register_variant_narration_proposal_routes(app)
    app.state.timeline_service = f.env.service
    app.state.content_service = f.env.content
    app.include_router(production_router, dependencies=[Depends(authorize_human_request)])
    app.include_router(timeline_router, dependencies=[Depends(authorize_human_request)])
    app.include_router(content_router, dependencies=[Depends(authorize_human_request)])
    app.include_router(platform_router, dependencies=[Depends(authorize_human_request)])
    return SimpleNamespace(f=f, runtime=runtime, repository=repository, service=service, app=app,
                           built=built, package=package, approved=approved)


def client(a, *, authenticated=True):
    return httpx.AsyncClient(transport=httpx.ASGITransport(a.app), base_url='http://owned-proposal-fixture',
        headers=TEST_HUMAN_HEADERS if authenticated else {})


async def all_rows(a):
    async with a.f.env.factory() as session:
        return canonical({mapper.class_.__tablename__: [record_value(row) for row in
            (await session.scalars(select(mapper.class_).order_by(*mapper.class_.__table__.primary_key.columns))).all()]
            for mapper in sorted(Base.registry.mappers, key=lambda m: m.class_.__tablename__)})


async def get_proposal(a):
    async with client(a) as c:
        response = await c.get(base(a.f) + '/narration-reuse-proposal')
    assert response.status_code == 200, response.text
    return response.json()


async def test_actual_metadata_proposal_has_no_sql_mutation_or_byte_provider_queue_cost_io(prepared, monkeypatch):
    a = prepared
    def deny(*args, **kwargs):
        raise AssertionError('PROPOSAL_GET_CANNOT_DISPATCH_OR_STAGE_BYTES')
    for target, name in [(a.f.env.storage, 'download_file'), (a.runtime.service.copier, 'copy'),
                         (a.runtime.loader, 'prepare'), (a.f.env.queue, 'rpush'),
                         (a.f.env.platform, 'record_provider_operation')]:
        monkeypatch.setattr(target, name, deny)
    before = await all_rows(a)
    statements = []
    def observe(_connection, _cursor, statement, *_args):
        statements.append(statement)
        assert statement.lstrip().split()[0].upper() not in {'UPDATE', 'INSERT', 'DELETE', 'REPLACE', 'CREATE', 'DROP', 'ALTER'}
    event.listen(a.f.env.engine.sync_engine, 'before_cursor_execute', observe)
    try:
        first, second = await get_proposal(a), await get_proposal(a)
    finally:
        event.remove(a.f.env.engine.sync_engine, 'before_cursor_execute', observe)
    assert first == second and await all_rows(a) == before
    assert first['proposal_sha256'] == digest({k: v for k, v in first.items() if k != 'proposal_sha256'})
    assert first['source_current'] and first['child_script_approved']
    assert first['actor_ref'] == 'usr:test-owner' and 'request_key' not in first['request_template']
    assert first['request_template']['expected_profile_sha256s'] == [a.f.evidence.profile_sha256]
    assert first['request_template']['expected_normalization_sha256s'] == ['2' * 64]
    assert first['request_template']['expected_source_manifest_sha256'] == digest(a.f.manifest)
    assert first['downloads'] == first['copies'] == first['queue_calls'] == first['cost_writes'] == 0
    assert first['approval_transferred'] is False and first['rights_authority_transferred'] is False
    assert statements


@pytest.mark.parametrize('boundary,expected', [('no_token', 401), ('viewer', 200), ('foreign_child', 404),
    ('foreign_master', 404), ('disabled', 503), ('unknown_query', 422), ('writes_disabled', 200)])
async def test_actual_dual_scope_and_default_disabled_proposal(prepared, boundary, expected):
    a = prepared
    endpoint = base(a.f) + '/narration-reuse-proposal'
    if boundary == 'viewer':
        install_test_human_auth(a.app, platform_repository=a.f.env.platform, platform_role=None,
            workspace_roles={a.f.env.workspace.workspace_id: 'viewer'})
    if boundary == 'foreign_child':
        endpoint = endpoint.replace(a.f.child.project_id, 'prj_missing_child_fixture')
    if boundary == 'foreign_master':
        endpoint = endpoint.replace(a.f.env.project.project_id, 'prj_missing_master_fixture')
    if boundary == 'disabled':
        a.app.state.sql_variant_narration_runtime = create_variant_narration_runtime(
            session_factory=a.f.env.factory, object_storage=a.f.env.storage, assets=a.f.env.assets)
    if boundary == 'unknown_query':
        endpoint += '?actor_ref=untrusted-private-fixture'
    if boundary == 'writes_disabled':
        a.app.state.human_write_enabled = False
    before = await all_rows(a)
    async with client(a, authenticated=boundary != 'no_token') as c:
        response = await c.get(endpoint)
    assert response.status_code == expected and response.headers['cache-control'] == 'no-store'
    assert await all_rows(a) == before


async def test_proposal_request_stale_after_actual_generic_content_version_never_copies(prepared, monkeypatch):
    a = prepared
    proposal = await get_proposal(a)
    await a.f.env.platform.create_version(a.f.child.project_id, ProjectVersionCreate(label='mvp1-content',
        snapshot=copy.deepcopy(a.approved.snapshot)))
    def deny(*args, **kwargs):
        raise AssertionError('STALE_PROPOSAL_MUST_NOT_COPY')
    monkeypatch.setattr(a.runtime.service.copier, 'copy', deny)
    before = await all_rows(a)
    async with client(a) as c:
        response = await c.post(base(a.f) + '/narration-reuse', json={**proposal['request_template'],
            'request_key': 'actual-stale-proposal-key-01'})
    assert response.status_code == 409 and response.json()['detail']['error']['code'] == 'SQL_VARIANT_NARRATION_CHILD_NOT_CURRENT'
    assert await all_rows(a) == before


async def test_new_master_approval_invalidates_metadata_proposal_without_fallback(prepared, monkeypatch):
    a = prepared
    proposal = await get_proposal(a)
    await a.f.env.package.request_approval(a.f.env.project.project_id,
        ApprovalRequest(review_render_id=a.f.request.source_review_render_id))
    monkeypatch.setattr(a.runtime.service.copier, 'copy', lambda *_a, **_k: pytest.fail('No stale copy'))
    before = await all_rows(a)
    async with client(a) as c:
        read = await c.get(base(a.f) + '/narration-reuse-proposal')
        submitted = await c.post(base(a.f) + '/narration-reuse', json={**proposal['request_template'],
            'request_key': 'actual-new-master-approval-key'})
    assert read.status_code == submitted.status_code == 409
    assert await all_rows(a) == before


async def test_sqlite_wal_proposal_is_coherent_old_snapshot_and_post_still_fences_new_content(prepared, monkeypatch):
    a = prepared
    async with a.f.env.engine.connect() as connection:
        await connection.execute(text('PRAGMA journal_mode=WAL'))
    expected = await get_proposal(a)
    capture = a.runtime.service.repository._capture
    changed = False
    async def change_between_reads(*args, **kwargs):
        nonlocal changed
        if not changed:
            changed = True
            await a.f.env.platform.create_version(a.f.child.project_id,
                ProjectVersionCreate(label='mvp1-content', snapshot=copy.deepcopy(a.approved.snapshot)))
        return await capture(*args, **kwargs)
    monkeypatch.setattr(a.runtime.service.repository, '_capture', change_between_reads)
    coherent = await get_proposal(a)
    assert changed and coherent == expected
    monkeypatch.setattr(a.runtime.service.repository, '_capture', capture)
    async with client(a) as c:
        response = await c.post(base(a.f) + '/narration-reuse', json={**coherent['request_template'],
            'request_key': 'actual-late-content-proposal-key'})
    assert response.status_code == 409


async def test_actual_proposal_import_and_review_intent_fixture(prepared):
    a = prepared
    before = await all_rows(a)
    async with client(a) as c:
        available = await c.get(base(a.f) + '/narration-reuse-availability')
        proposal_reply = await c.get(base(a.f) + '/narration-reuse-proposal')
        proposal = proposal_reply.json()
        assert proposal_reply.status_code == 200 and await all_rows(a) == before
        request = {**proposal['request_template'], 'request_key': 'actual-ui-narration-import-01'}
        imported = await c.post(base(a.f) + '/narration-reuse', json=request)
        assert imported.status_code == 201, imported.text
        receipt = imported.json()['receipt']
        fetched = await c.get(base(a.f) + '/narration-receipts/' + receipt['receipt_id'])
        # Explicit current-shell default when this rebuilt timeline has no reframe.
        profile = 'review-540x960'
        review_request = dict(expected_timeline_version=a.built.current_version,
            expected_subtitle_version=a.package.subtitle.version, expected_audio_version=a.package.audio_mix.version,
            profile=profile, selection=dict(enabled=True, receipt_id=receipt['receipt_id'], family_id=receipt['family_id'],
                member_id=receipt['member_id'], master_project_id=a.f.env.project.project_id,
                input_sha256=receipt['input_sha256'], result_sha256=receipt['result_sha256']))
        old_queue_count = len(a.f.env.queue.values)
        review = await c.post(base(a.f) + '/narration-review-render', json=review_request)
        assert review.status_code == 202, review.text
        replayed = await c.post(base(a.f) + '/narration-review-render', json=review_request)
        assert replayed.status_code == 202 and replayed.json()['render_id'] == review.json()['render_id']
        assert len(a.f.env.queue.values) == old_queue_count + 1
        child_package = await c.get(f'/api/v1/projects/{a.f.child.project_id}/production-package')
        child_project = await c.get(f'/api/v1/projects/{a.f.child.project_id}')
    assert fetched.json() == receipt and receipt['approval_transferred'] is False
    assert review.json()['approval_id'] is None and review.json()['manifest']['requested_by'] == 'usr:test-owner'
    output = os.environ.get('VF_NARRATION_UI_CAPTURE_PATH')
    if output:
        target = Path(output)
        target.mkdir(parents=True, exist_ok=False)
        value = dict(schema_version='actual-sql-variant-narration-ui-fixture.v1',
            fixture_notice='Actual SQLite/ASGI with manually saved synthetic PCM/source review/QC/approval; not genuine TTS, actual renderer, listening or Owner UAT.',
            context=dict(workspace_id=a.f.env.workspace.workspace_id, master_project_id=a.f.env.project.project_id,
                project_id=a.f.child.project_id, family_id=a.f.family.family_id, member_id=a.f.family.members[0].member_id,
                actor_ref='usr:test-owner'), project=child_project.json(), timeline=a.built.model_dump(mode='json'),
            package_before=a.package.model_dump(mode='json'), package_after=child_package.json(),
            availability=available.json(), proposal=proposal, import_request=request,
            import_response=imported.json(), receipt_read=fetched.json(), review_request=review_request,
            review_response=review.json(), review_replayed=replayed.json(),
            new_model_inferences=0, provider_calls=0, real_renderer_calls=0,
            explicit_review_queue_intents=1, publishing_enabled=False, owner_uat_accepted=False)
        with (target/'asgi.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2);stream.write('\n')
        raw = (target/'asgi.json').read_bytes()
        with (target/'manifest.json').open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(dict(schema_version='sql-variant-narration-ui-fixture-manifest.v1',
                files=[dict(name='asgi.json', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())],
                new_model_inferences=0, provider_calls=0, real_renderer_calls=0, external_network_calls=0,
                paid_operations=0, owner_uat_accepted=False), stream, indent=2);stream.write('\n')
