"""Source/publication isolation over authenticated ASGI and owned SQLite."""
from fastapi import Depends, FastAPI
import httpx
import pytest

from app.analytics_models import AnalyticsSyncRequest
from app.analytics_routes import router
from app.human_auth import authorize_human_request
from app.publishing_db import PublicationORM
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_analytics_runtime import runtime_stack, reserve


def application(stack, *, role='owner'):
    app = FastAPI(); app.include_router(router, dependencies=[Depends(authorize_human_request)])
    app.state.analytics_service = stack.service
    install_test_human_auth(app, platform_repository=stack.production.platform, platform_role=None,
        workspace_roles={stack.publication.workspace_id: role, 'wsp_foreign': 'owner'})
    return app


@pytest.mark.asyncio
async def test_report_history_assessment_and_learning_are_filtered_by_publication_and_source(runtime_stack):
    stack, _, _, _, _, _ = runtime_stack
    official = await reserve(stack); await stack.processor.process(official.sync_id)
    fixture, _ = await stack.service.create_sync(project_id=official.project_id,
        payload=AnalyticsSyncRequest(publication_id=official.publication_id, provider_mode='fixture'),
        idempotency_key='publication-source-fixture-first')
    await stack.processor.process(fixture.sync_id)
    async with stack.repository.session_factory() as session:
        parent = await session.get(PublicationORM, official.publication_id)
        values = {column.name: getattr(parent, column.name) for column in PublicationORM.__table__.columns}
        values.update(publication_id='pub_second_analytics_fixture', idempotency_key_hash='e' * 64)
        session.add(PublicationORM(**values)); await session.commit()
    other, _ = await stack.service.create_sync(project_id=official.project_id,
        payload=AnalyticsSyncRequest(publication_id='pub_second_analytics_fixture', provider_mode='fixture', fixture_profile='normal'),
        idempotency_key='publication-source-fixture-second')
    await stack.processor.process(other.sync_id)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(stack)), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        base = f'/api/v1/projects/{official.project_id}/publications/{official.publication_id}/analytics'
        for mode, expected_views in [('official', 1000), ('fixture', 120000)]:
            report = await client.get(base, params={'provider_mode': mode})
            assert report.status_code == 200 and report.headers['Cache-Control'] == 'no-store'
            body = report.json(); assert body['publication_id'] == official.publication_id and body['history_count'] == 1
            assert body['latest_snapshot']['metrics']['views'] == expected_views
            assert body['latest_sync']['provider_mode'] == mode
            assert body['latest_assessment']['snapshot_id'] == body['latest_snapshot']['snapshot_id']
            assert all(insight['snapshot_id'] == body['latest_snapshot']['snapshot_id'] for insight in body['learning_insights'])
            history = await client.get(base + '/snapshots', params={'provider_mode': mode})
            assert history.status_code == 200 and len(history.json()) == 1
            assert history.json()[0]['publication_id'] == official.publication_id
        missing = await client.get(base.replace(official.publication_id, 'pub_missing_fixture'))
        assert missing.status_code == 404
    assert (await stack.repository.report(official.project_id)).history_count == 3


@pytest.mark.asyncio
async def test_viewer_with_foreign_owner_role_can_read_but_cannot_sync(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    project = stack.publication.project_id; publication = stack.publication.publication_id
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(stack, role='viewer')), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        response = await client.get(f'/api/v1/projects/{project}/publications/{publication}/analytics')
        assert response.status_code == 200 and response.json()['history_count'] == 0
        denied = await client.post(f'/api/v1/projects/{project}/analytics/syncs', headers={'Idempotency-Key': 'viewer-sync-must-be-rejected'},
            json={'publication_id': publication, 'provider_mode': 'fixture'})
        assert denied.status_code == 403 and calls == []


@pytest.mark.asyncio
async def test_unknown_source_is_rejected_without_collection(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(stack)), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        path = f'/api/v1/projects/{stack.publication.project_id}/publications/{stack.publication.publication_id}/analytics'
        result = await client.get(path, params={'provider_mode': 'unknown'})
        assert result.status_code == 422 and calls == []
