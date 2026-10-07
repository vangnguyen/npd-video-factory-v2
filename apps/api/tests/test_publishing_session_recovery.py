"""Real SQLite/AES crash recovery; identities, session and approvals are fixtures."""
import asyncio
from datetime import timedelta
import json

import pytest
from sqlalchemy import select

from app.publishing_db import PublicationEventORM, PublicationPrivateSessionORM
from app.publishing_dispatch import DispatchError
from app.publishing_session_vault import SessionVaultError
from test_publishing_dispatch import fixture_stack
from test_publishing_session_vault import crypto, ready, URI
from test_publishing_worker import configured_worker


@crypto
@pytest.mark.asyncio
@pytest.mark.parametrize('uncertain', [False, True])
async def test_sealed_orphan_recovers_once_after_restart_and_revocation_without_extending_receipt(fixture_stack, uncertain):
    fixture = fixture_stack; grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    async with vault.session_factory() as session:
        before = await session.get(PublicationPrivateSessionORM, reference)
        ciphertext, deadline = before.ciphertext, before.expires_at
    if uncertain: await fixture['journal'].finish(ticket, uncertain=True)
    state = await fixture['journal'].get(fixture['workspace'], value['publication_id'])
    await fixture['journal'].revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    await fixture['stack'].engine.dispose()
    done = await vault.recover_initialization(fixture['workspace'], value['publication_id'], expected_version=state['version'])
    assert done['phase'] == 'upload_ready' and done['acknowledged_bytes'] == 0 and done['remote_post_id'] is None
    assert reference not in json.dumps(done) and URI not in json.dumps(done)
    with pytest.raises(DispatchError, match='STALE_TICKET'): await fixture['journal'].finish(ticket, session_ref=reference)
    with pytest.raises(DispatchError, match='APPROVAL_REQUIRED_OR_EXPIRED'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], done['version'], 'chunk', offset=0, length=1)
    with pytest.raises(SessionVaultError, match='RECOVERY_STALE_RELOAD'):
        await vault.recover_initialization(fixture['workspace'], value['publication_id'], expected_version=state['version'])
    async with vault.session_factory() as session:
        after = await session.get(PublicationPrivateSessionORM, reference)
        assert after.ciphertext == ciphertext and after.expires_at == deadline
        events = (await session.scalars(select(PublicationEventORM).where(
            PublicationEventORM.event_type == 'publication.initialization_receipt_recovered'))).all()
        assert len(events) == 1 and events[0].payload_json['external_action'] is False


@crypto
@pytest.mark.asyncio
async def test_unknown_initialization_without_sealed_receipt_stays_uncertain(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, _upload = await ready(fixture)
    await fixture['journal'].finish(ticket, uncertain=True)
    state = await fixture['journal'].get(fixture['workspace'], value['publication_id'])
    assert await vault.recover_initialization(fixture['workspace'], value['publication_id'], expected_version=state['version']) is None
    assert await fixture['journal'].get(fixture['workspace'], value['publication_id']) == state


@crypto
@pytest.mark.asyncio
@pytest.mark.parametrize('damage', ['ciphertext', 'expiry', 'key', 'binding', 'foreign_workspace', 'version'])
async def test_recovery_refuses_tamper_expiry_keys_foreign_scope_and_stale_version(fixture_stack, damage):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    workspace = fixture['workspace']; version = ticket.version
    if damage == 'expiry': fixture['clock'][0] += timedelta(hours=2)
    elif damage == 'key': vault.key_provider = None
    elif damage == 'foreign_workspace': workspace = 'another-workspace'
    elif damage == 'version': version += 1
    else:
        async with vault.session_factory() as session:
            async with session.begin():
                row = await session.get(PublicationPrivateSessionORM, reference)
                if damage == 'ciphertext': row.ciphertext = row.ciphertext[:-1] + bytes([row.ciphertext[-1] ^ 1])
                else: row.binding_sha256 = '0' * 64
    with pytest.raises(SessionVaultError):
        await vault.recover_initialization(workspace, value['publication_id'], expected_version=version)
    assert (await fixture['journal'].get(fixture['workspace'], value['publication_id']))['phase'] == 'init_intent'


@crypto
@pytest.mark.asyncio
async def test_competing_recovery_has_one_transition_and_no_receipt_overwrite(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    await vault.save(ticket, upload)
    results = await asyncio.gather(*[vault.recover_initialization(fixture['workspace'], value['publication_id'],
        expected_version=ticket.version) for _ in range(2)], return_exceptions=True)
    assert sum(isinstance(value, dict) for value in results) == 1
    assert sum(isinstance(value, SessionVaultError) for value in results) == 1


@crypto
@pytest.mark.asyncio
async def test_worker_recovers_sealed_crash_gap_without_account_or_provider_request(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, grant, _work, _policy = await configured_worker(fixture, tmp_path)
    state = await worker.journal.get(fixture['workspace'], fixture['publication'].publication_id)
    ticket = await worker.journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
    from app.youtube_upload import UploadSession
    await worker.vault.save(ticket, UploadSession(receiver.uri, state['total_bytes']))
    await worker.journal.revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    done = await worker.step(fixture['workspace'], state['publication_id'])
    assert done['phase'] == 'upload_ready' and receiver.requests == []
    with pytest.raises(DispatchError, match='APPROVAL_REQUIRED_OR_EXPIRED'):
        await worker.step(fixture['workspace'], state['publication_id'])
