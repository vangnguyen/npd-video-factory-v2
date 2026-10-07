"""Authenticated API admission never starts provider work; all approvals are fixtures."""
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.publishing_models import PublishApprovalRequest, PublishScheduleRequest
from app.publishing_scheduler import PublishingWorkQueue
from test_publishing_dispatch import fixture_stack
from test_publishing_queue import configured_service, consent_payload, headers, http_app, queued


@pytest.mark.asyncio
async def test_owner_work_enqueue_is_idempotent_viewer_readable_and_sends_no_provider_request(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    configured.service.work_queue = PublishingWorkQueue(configured.journal)
    grant = await configured.service.approve_publish(row.project_id, row.publication_id,
        principal=fixture['principals']['owner'], payload=PublishApprovalRequest.model_validate(consent_payload(fixture, row, configured)),
        idempotency_key='explicit-work-approval-fixture')
    application = http_app(fixture, configured)
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}/publishing-work'
    async with AsyncClient(transport=ASGITransport(app=application), base_url='http://explicit-test') as client:
        for role in ('editor', 'reviewer', 'viewer'):
            denied = await client.post(path, headers=headers(role), json={'publish_approval_id': grant['publish_approval_id']})
            assert denied.status_code == 403
        first = await client.post(path, headers=headers('owner'), json={'publish_approval_id': grant['publish_approval_id']})
        assert first.status_code == 200 and first.json()['status'] == 'queued'
        replay = await client.post(path, headers=headers('owner'), json={'publish_approval_id': grant['publish_approval_id']})
        assert replay.json() == first.json()
        view = await client.get(path, headers=headers('viewer'))
        assert view.status_code == 200 and view.json() == first.json() and view.headers['cache-control'] == 'no-store'
        assert 'lease_owner' not in view.text
    assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
async def test_missing_config_foreign_project_and_unknown_consent_refuse_without_work(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    application = http_app(fixture, configured)
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}/publishing-work'
    async with AsyncClient(transport=ASGITransport(app=application), base_url='http://explicit-test', headers=headers('owner')) as client:
        absent = await client.post(path, json={'publish_approval_id': 'pua_' + 'a' * 32})
        assert absent.status_code == 409 and absent.json()['detail']['error']['code'] == 'PUBLISH_WORK_NOT_CONFIGURED'
        configured.service.work_queue = PublishingWorkQueue(configured.journal)
        unknown = await client.post(path, json={'publish_approval_id': 'pua_' + 'a' * 32})
        assert unknown.status_code == 409
        foreign = await client.get(path.replace(row.project_id, 'prj_foreign_fixture'))
        assert foreign.status_code == 404
        malformed = await client.post(path, json={'publish_approval_id': 'pua_' + 'a' * 32, 'actor': 'owner'})
        assert malformed.status_code == 422
        configured.service.settings.publish_enabled = False
        disabled = await client.post(path, json={'publish_approval_id': 'pua_' + 'a' * 32})
        assert disabled.status_code == 409 and disabled.json()['detail']['error']['code'] == 'PUBLISH_WORK_OWNER_GATES_REQUIRED'
        assert await configured.service.work_queue.for_publication(row.workspace_id, row.publication_id) is None
    assert configured.provider.publish_calls == 0


def test_work_body_cannot_supply_identity_lease_or_mutable_provider_configuration():
    for payload in ({'publish_approval_id': True}, {'publish_approval_id': 'pua_' + 'a' * 32, 'lease_owner': 'secret'},
        {'publish_approval_id': 'pua_' + 'a' * 32, 'target': {}}, {'publish_approval_id': 'pua_' + 'a' * 32, 'role': 'owner'}):
        with pytest.raises(ValidationError): PublishScheduleRequest.model_validate(payload)
