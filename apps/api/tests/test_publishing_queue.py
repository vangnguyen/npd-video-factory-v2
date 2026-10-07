"""Consent-gated queue/HTTP tests. Every live account/media/provider input is a fixture."""
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import select

from app.human_auth import HumanRateLimiter, authorize_human_request
from app.publishing_db import PublicationDispatchORM, PublishApprovalORM
from app.publishing_dispatch import DispatchError, PublishingDispatchJournal, checksum
from app.publishing_logic import PublishingCapabilityRegistry, validation_check
from app.publishing_models import ProviderValidationRead, PublishApprovalRequest
from app.publishing_providers import PublishingProviderRegistry
from app.publishing_repository import PublishingRepository
from app.publishing_routes import router
from app.publishing_service import PublishingBoundaryError, PublishingService
from auth_test_support import MemoryRateStore
from test_publishing import CAPABILITIES, publishing_settings, request_for
from test_publishing_dispatch import fixture_stack
from test_publishing_target import target_for


class ExplicitQueueProviderFixture:
    provider_key = 'explicit-queue-provider'
    platform = 'youtube'

    def __init__(self, target):
        self.target = target
        self.publish_calls = 0

    def validate(self):
        return ProviderValidationRead(provider_key=self.provider_key, adapter_state='ready', credential_status='configured',
            supports_dry_run=False, supports_live_publish=True, target_binding=self.target,
            checks=[validation_check('explicit-fixture', True, 'EXPLICIT_QUEUE_FIXTURE', 'Fixture only; no actual account verification.')])

    async def publish(self, _context):
        self.publish_calls += 1
        raise AssertionError('Live create/consent must never dispatch through immediate publish')


def configured_service(fixture, **overrides):
    settings = publishing_settings(**{'publish_enabled': True, 'publish_external_execution_enabled': True,
        'publish_owner_gate_enabled': True, **overrides})
    target = [target_for(fixture, provider_key=ExplicitQueueProviderFixture.provider_key)]
    provider = ExplicitQueueProviderFixture(target[0]); providers = PublishingProviderRegistry(settings)
    providers.official['youtube'] = provider
    capabilities = PublishingCapabilityRegistry(CAPABILITIES)
    # Explicit fixture of a verified contract. The on-disk production policy is untouched.
    capabilities._platforms['youtube'] = capabilities.get('youtube').model_copy(update={'verification_state': 'owner_verified_for_live'})
    journal = PublishingDispatchJournal(fixture['stack'].repository.session_factory,
        identity_provider=lambda: fixture['verifier'], target_provider=lambda workspace, profile: target[0],
        require_target_binding=True, clock=lambda: fixture['clock'][0])
    service = PublishingService(repository=PublishingRepository(fixture['stack'].repository.session_factory),
        production_repository=fixture['stack'].repository, asset_repository=fixture['stack'].asset_repository,
        capabilities=capabilities, providers=providers, settings=settings, dispatch_journal=journal)
    return SimpleNamespace(service=service, provider=provider, target=target, journal=journal)


async def queued(fixture, configured, *, key='explicit-live-queue-fixture-0001'):
    return await configured.service.create(project_id=fixture['publication'].project_id,
        payload=request_for(fixture['publication'].final_render_id, mode='live'), idempotency_key=key)


def consent_payload(fixture, row, configured):
    return {'expected_fingerprint': row.request_fingerprint, 'expected_artifact_sha256': fixture['source_sha'],
        'expected_target_sha256': checksum(configured.target[0].model_dump(mode='json')), 'acknowledged': True}


def http_app(fixture, configured):
    application = FastAPI()
    application.include_router(router, dependencies=[Depends(authorize_human_request)])
    application.state.publishing_service = configured.service
    application.state.platform_repository = fixture['stack'].platform
    application.state.human_api_enabled = True; application.state.human_write_enabled = True
    application.state.human_auth_verifier = fixture['verifier']
    application.state.human_rate_limiter = HumanRateLimiter(MemoryRateStore(), requests_per_minute=1000)
    return application


def headers(role):
    return {'Authorization': 'Bearer vf1.explicit-' + role + '.' + 'x' * 48}


@pytest.mark.asyncio
async def test_live_create_waits_for_separate_consent_and_idempotent_replay_never_calls_provider(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture)
    row, replay = await queued(fixture, configured)
    assert row.status == 'awaiting_publish_approval' and not replay
    assert row.receipt is None and not row.external_action and not row.mock and not row.dry_run
    assert row.provider_validation.target_binding == configured.target[0]
    recovered, replay = await queued(fixture, configured)
    assert replay and recovered == row and configured.provider.publish_calls == 0
    async with fixture['stack'].repository.session_factory() as session:
        assert not (await session.scalars(select(PublishApprovalORM))).all()
        assert not (await session.scalars(select(PublicationDispatchORM))).all()
    states = configured.service.platform_states()
    assert not next(state for state in states if state.platform == 'youtube').live_execution_enabled


@pytest.mark.asyncio
async def test_publish_only_consent_does_not_dispatch_and_prepare_atomically_admits_queue(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    grant = await configured.service.approve_publish(row.project_id, row.publication_id,
        principal=fixture['principals']['owner'], payload=PublishApprovalRequest.model_validate(consent_payload(fixture, row, configured)),
        idempotency_key='explicit-queued-owner-consent')
    assert (await configured.service.get(row.project_id, row.publication_id)).status == 'awaiting_publish_approval'
    state = await configured.journal.prepare(row.workspace_id, row.publication_id, grant['publish_approval_id'])
    assert state['phase'] == 'init_ready' and state['version'] == 1
    assert (await configured.service.get(row.project_id, row.publication_id)).status == 'publishing'
    assert await configured.journal.prepare(row.workspace_id, row.publication_id, grant['publish_approval_id']) == state
    events = await configured.service.history(row.project_id)
    assert sum(event.event_type == 'publication.publish_consent_admitted' for event in events) == 1
    assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('gate', ['publish_enabled', 'publish_external_execution_enabled', 'publish_owner_gate_enabled'])
async def test_live_service_gates_cannot_be_bypassed_by_ready_fixture_provider(fixture_stack, gate):
    fixture = fixture_stack; configured = configured_service(fixture)
    setattr(configured.service.settings, gate, False)
    with pytest.raises(PublishingBoundaryError) as raised:
        await queued(fixture, configured)
    assert raised.value.publication.failure_code == 'PUBLISH_GATES_DISABLED'
    assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('target_change', ['missing', 'workspace', 'provider', 'platform', 'unchecked_revision'])
async def test_live_queue_rejects_missing_foreign_or_unvalidated_targets(fixture_stack, target_change):
    fixture = fixture_stack; configured = configured_service(fixture)
    changes = {'workspace': {'workspace_id': 'wsp_foreign'}, 'provider': {'provider_key': 'other-fixture'},
        'platform': {'platform': 'facebook'}, 'unchecked_revision': {'profile_version': True}}
    configured.provider.target = None if target_change == 'missing' else configured.target[0].model_copy(update=changes[target_change])
    with pytest.raises(PublishingBoundaryError) as raised:
        await queued(fixture, configured)
    assert raised.value.publication.failure_code == 'PUBLISH_TARGET_BINDING_REQUIRED'
    assert configured.provider.publish_calls == 0


@pytest.mark.parametrize('acknowledged', [False, 1, 'true', None])
def test_consent_body_requires_explicit_boolean_and_has_no_actor_or_role(acknowledged):
    payload = {'expected_fingerprint': 'a' * 64, 'expected_artifact_sha256': 'b' * 64,
        'expected_target_sha256': 'c' * 64, 'acknowledged': acknowledged}
    with pytest.raises(ValidationError):
        PublishApprovalRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        PublishApprovalRequest.model_validate({**payload, 'acknowledged': True, 'actor_ref': 'owner'})


@pytest.mark.asyncio
async def test_owner_http_consent_replay_revocation_and_private_dispatch_projection(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}'
    async with AsyncClient(transport=ASGITransport(app=http_app(fixture, configured)), base_url='http://explicit-test') as client:
        for role in ('editor', 'reviewer', 'viewer'):
            refused = await client.post(path + '/publish-approval', headers=headers(role), json={})
            assert refused.status_code == 403
        approved = await client.post(path + '/publish-approval', headers={**headers('owner'), 'Idempotency-Key': 'explicit-http-owner-consent'},
            json=consent_payload(fixture, row, configured))
        assert approved.status_code == 200 and approved.headers['Cache-Control'] == 'no-store'
        replay = await client.post(path + '/publish-approval', headers={**headers('owner'), 'Idempotency-Key': 'explicit-http-owner-consent'},
            json=consent_payload(fixture, row, configured))
        assert replay.json() == approved.json()
        grant = approved.json(); state = await configured.journal.prepare(row.workspace_id, row.publication_id, grant['publish_approval_id'])
        ticket = await configured.journal.intent(row.workspace_id, row.publication_id, state['version'], 'init')
        read = await client.get(path + '/dispatch', headers=headers('viewer'))
        assert read.status_code == 200 and read.json()['phase'] == 'init_intent'
        assert 'intent_id' not in read.text and ticket.intent_id not in read.text and 'private_session_ref' not in read.text
        refused = await client.post(path + '/publish-approval/revoke', headers=headers('editor'),
            json={'publish_approval_id': grant['publish_approval_id']})
        assert refused.status_code == 403
        revoked = await client.post(path + '/publish-approval/revoke', headers=headers('owner'),
            json={'publish_approval_id': grant['publish_approval_id']})
        assert revoked.status_code == 200 and revoked.json()['revoked'] is True
        # Consent revocation records no remote cancellation/deletion.
        assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
async def test_http_foreign_project_stale_target_missing_dispatch_config_and_publication_scoped_revoke(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}'
    application = http_app(fixture, configured)
    async with AsyncClient(transport=ASGITransport(app=application), base_url='http://explicit-test', headers=headers('owner')) as client:
        payload = consent_payload(fixture, row, configured)
        stale = await client.post(path + '/publish-approval', headers={'Idempotency-Key': 'explicit-stale-http-target'},
            json={**payload, 'expected_target_sha256': '0' * 64})
        assert stale.status_code == 409 and stale.json()['detail']['error']['code'] == 'PUBLISH_APPROVAL_TARGET_STALE_RELOAD'
        foreign = await client.get('/api/v1/projects/prj_foreign_fixture/publications/' + row.publication_id + '/dispatch')
        assert foreign.status_code == 404
        grant = await configured.service.approve_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'],
            payload=PublishApprovalRequest.model_validate(payload), idempotency_key='explicit-scoped-revoke-target')
        with pytest.raises(DispatchError, match='PUBLISH_SCOPE_NOT_FOUND'):
            await configured.service.revoke_publish(row.project_id, fixture['publication'].publication_id,
                principal=fixture['principals']['owner'], publish_approval_id=grant['publish_approval_id'])
        configured.service.dispatch_journal = None
        missing = await client.post(path + '/publish-approval', headers={'Idempotency-Key': 'explicit-unconfigured-dispatch'}, json=payload)
        assert missing.status_code == 409 and missing.json()['detail']['error']['code'] == 'PUBLISH_DISPATCH_NOT_CONFIGURED'
    assert configured.provider.publish_calls == 0
