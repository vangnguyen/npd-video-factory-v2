"""Destination configuration fixtures; no OAuth/account/provider acceptance claimed."""
import json

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.publishing_db import PublicationDispatchORM, PublicationEventORM, PublicationORM, PublishApprovalORM
from app.publishing_dispatch import DispatchError, PublishingDispatchJournal, checksum
from app.publishing_models import PublishingTargetBinding
from test_publishing_dispatch import fixture_stack


def target_for(fixture, **updates):
    return PublishingTargetBinding.model_validate({
        'workspace_id': fixture['workspace'], 'profile_id': 'ppf_explicit_fixture', 'profile_version': 1,
        'platform': fixture['publication'].platform, 'provider_key': fixture['publication'].provider_key,
        'target_account_id': 'EXPLICIT-FIXTURE-ACCOUNT', 'credential_binding_sha256': 'c' * 64, **updates})


async def bind_target(fixture, *, resolver=True):
    current = [target_for(fixture)]; calls = []
    def lookup(workspace, profile_id):
        calls.append((workspace, profile_id))
        return current[0]
    journal = PublishingDispatchJournal(fixture['stack'].repository.session_factory,
        identity_provider=lambda: fixture['verifier'], target_provider=lookup if resolver else None,
        require_target_binding=True, clock=lambda: fixture['clock'][0])
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, fixture['publication'].publication_id)
            parent.provider_validation_json = {**parent.provider_validation_json, 'credential_status': 'configured',
                'target_binding': current[0].model_dump(mode='json')}
    async def approve(**overrides):
        return await journal.approve(fixture['workspace'], fixture['publication'].publication_id,
            **{'principal': fixture['principals']['owner'], 'expected_fingerprint': fixture['publication'].request_fingerprint,
               'expected_artifact_sha256': fixture['source_sha'], 'expected_target_sha256': checksum(current[0].model_dump(mode='json')),
               'acknowledged': True, 'idempotency_key': 'explicit-destination-consent-fixture', **overrides})
    return journal, current, calls, approve


@pytest.mark.parametrize('updates', [
    {'profile_version': True}, {'profile_version': '1'}, {'profile_version': 0},
    {'profile_id': 'https://private.invalid/reference'}, {'target_account_id': 'https://private.invalid/account'},
    {'credential_binding_sha256': 'TOKEN'}, {'oauth_token': 'PRIVATE-MUST-NOT-BE-ACCEPTED'},
])
def test_public_target_is_strict_secret_free_configuration(updates):
    payload = {'workspace_id': 'wsp_explicit', 'profile_id': 'ppf_explicit', 'profile_version': 1,
        'platform': 'youtube', 'provider_key': 'explicit-fixture', 'target_account_id': 'EXPLICIT-ACCOUNT',
        'credential_binding_sha256': 'a' * 64, **updates}
    with pytest.raises(ValidationError):
        PublishingTargetBinding.model_validate(payload)


@pytest.mark.asyncio
async def test_reviewed_destination_digest_is_required_and_exact_consent_replays(fixture_stack):
    fixture = fixture_stack; journal, current, calls, approve = await bind_target(fixture)
    for digest in (None, '0' * 64):
        with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_TARGET_STALE_RELOAD'):
            await approve(expected_target_sha256=digest)
    grant = await approve(); assert await approve() == grant
    assert grant['target_binding'] == current[0].model_dump(mode='json')
    assert grant['target_binding_sha256'] == checksum(grant['target_binding'])
    state = await journal.prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    ticket = await journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
    assert ticket.phase == 'init_intent' and len(calls) == 6
    async with fixture['stack'].repository.session_factory() as session:
        grants = (await session.scalars(select(PublishApprovalORM))).all()
        assert len(grants) == 1 and 'provider_validation_sha256' in grants[0].binding_json
        events = (await session.scalars(select(PublicationEventORM))).all()
        assert 'credential_binding_sha256' not in json.dumps([e.payload_json for e in events])


@pytest.mark.asyncio
@pytest.mark.parametrize('updates', [
    {'profile_id': 'ppf_other_fixture'}, {'profile_version': 2}, {'target_account_id': 'OTHER-EXPLICIT-ACCOUNT'},
    {'credential_binding_sha256': 'd' * 64}, {'workspace_id': 'wsp_foreign'},
    {'platform': 'facebook'}, {'provider_key': 'other-fixture'},
])
async def test_fresh_server_configuration_change_blocks_unstarted_upload(fixture_stack, updates):
    fixture = fixture_stack; journal, current, _calls, approve = await bind_target(fixture)
    grant = await approve(); state = await journal.prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    current[0] = target_for(fixture, **updates)
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_CHANGED_REVALIDATE'):
        await journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
    assert (await journal.get(fixture['workspace'], state['publication_id']))['phase'] == 'init_ready'


@pytest.mark.asyncio
async def test_changed_saved_destination_requires_fresh_consent_and_never_rebinds_dispatch(fixture_stack):
    fixture = fixture_stack; journal, current, _calls, approve = await bind_target(fixture)
    grant = await approve(); state = await journal.prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    current[0] = target_for(fixture, profile_version=2, target_account_id='OTHER-EXPLICIT-ACCOUNT')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, state['publication_id'])
            parent.provider_validation_json = {**parent.provider_validation_json, 'target_binding': current[0].model_dump(mode='json')}
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_STALE_RELOAD'):
        await journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_IDEMPOTENCY_CONFLICT'):
        await approve()
    fresh = await approve(idempotency_key='explicit-new-reviewed-target')
    assert fresh['binding_sha256'] != grant['binding_sha256']
    with pytest.raises(DispatchError, match='PUBLISH_DISPATCH_BINDING_CONFLICT'):
        await journal.prepare(fixture['workspace'], state['publication_id'], fresh['publish_approval_id'])
    async with fixture['stack'].repository.session_factory() as session:
        row = await session.get(PublicationDispatchORM, state['publication_id'])
        assert row.publish_approval_id == grant['publish_approval_id'] and row.phase == 'init_ready'


@pytest.mark.asyncio
@pytest.mark.parametrize('updates', [
    {'workspace_id': 'wsp_foreign'}, {'platform': 'facebook'}, {'provider_key': 'other-fixture'},
    {'profile_version': True}, {'private_token': 'SECRET-FIXTURE-MUST-NOT-ESCAPE'},
])
async def test_invalid_saved_destination_fails_before_resolver_or_consent(fixture_stack, updates):
    fixture = fixture_stack; journal, current, calls, approve = await bind_target(fixture)
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, fixture['publication'].publication_id)
            parent.provider_validation_json = {**parent.provider_validation_json,
                'target_binding': {**current[0].model_dump(mode='json'), **updates}}
            # bool True compares equal to int 1; force this deliberately corrupt
            # stored fixture to be written rather than testing an unchanged row.
            flag_modified(parent, 'provider_validation_json')
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_BINDING_INVALID') as raised:
        await approve()
    assert not calls and 'SECRET' not in str(raised.value)


@pytest.mark.asyncio
async def test_resolver_errors_missing_configuration_and_unvalidated_model_copy_fail_closed(fixture_stack):
    fixture = fixture_stack; journal, current, _calls, approve = await bind_target(fixture, resolver=False)
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_REVALIDATION_REQUIRED'):
        await approve()
    def unavailable(*_args):
        raise RuntimeError('PRIVATE-CONFIGURATION-MUST-NOT-ESCAPE')
    journal.target_provider = unavailable
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_REVALIDATION_REQUIRED') as raised:
        await approve()
    assert 'PRIVATE' not in str(raised.value)
    journal.target_provider = lambda *_args: current[0].model_copy(update={'profile_version': True})
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_REVALIDATION_REQUIRED'):
        await approve()


@pytest.mark.asyncio
async def test_provider_validation_revision_and_configured_credentials_are_bound(fixture_stack):
    fixture = fixture_stack; journal, _current, _calls, approve = await bind_target(fixture)
    grant = await approve(); state = await journal.prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, state['publication_id'])
            value = {**parent.provider_validation_json}; value['checks'] = [dict(check) for check in value['checks']]
            value['checks'][0]['message'] = 'EXPLICITLY CHANGED VALIDATION REVISION'
            parent.provider_validation_json = value
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_STALE_RELOAD'):
        await journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, state['publication_id'])
            parent.provider_validation_json = {**parent.provider_validation_json, 'credential_status': 'not_configured'}
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_BINDING_INVALID'):
        await approve(idempotency_key='explicit-revalidation-without-credentials')


@pytest.mark.asyncio
async def test_legacy_consent_remains_readable_but_strict_worker_policy_rejects_unbound_target(fixture_stack):
    fixture = fixture_stack; legacy = await fixture['approve']()
    assert 'target_binding' not in legacy
    strict = PublishingDispatchJournal(fixture['stack'].repository.session_factory,
        identity_provider=lambda: fixture['verifier'], require_target_binding=True, clock=lambda: fixture['clock'][0])
    with pytest.raises(DispatchError, match='PUBLISH_TARGET_BINDING_REQUIRED'):
        await strict.prepare(fixture['workspace'], fixture['publication'].publication_id, legacy['publish_approval_id'])
    state = await fixture['journal'].prepare(fixture['workspace'], fixture['publication'].publication_id, legacy['publish_approval_id'])
    assert state['phase'] == 'init_ready'
