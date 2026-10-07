"""Real SQLite transactions/restart; every media/provider/human input is a fixture."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import select

from app.db import AssetORM
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from app.publishing_db import PublicationDispatchORM, PublicationEventORM, PublicationORM, PublishApprovalORM
from app.publishing_dispatch import DispatchError, DispatchTicket, PublishingDispatchJournal
from app.timeline_db import TimelineORM
from test_publishing import approved_stack, request_for


@pytest.fixture
async def fixture_stack(tmp_path):
    stack, final, publishing = await approved_stack(tmp_path)
    publication, _replay = await publishing.create(project_id=stack.project.project_id,
        payload=request_for(final.render_id), idempotency_key='explicit-dispatch-fixture-reservation')
    workspace = publication.workspace_id; now = [datetime.now(timezone.utc)]
    registry = {'version': 1, 'tokens': {}}; raw = {}
    for role in ('owner', 'editor', 'reviewer', 'viewer'):
        identifier = 'explicit-' + role; token = 'vf1.' + identifier + '.' + 'x' * 48; raw[role] = token
        registry['tokens'][identifier] = {'token_id': identifier, 'token_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'subject': 'usr:' + identifier, 'display_name': 'EXPLICIT FIXTURE; NOT OWNER UAT', 'platform_role': None,
            'workspace_roles': {workspace: role}, 'issued_at': (now[0] - timedelta(seconds=60)).isoformat(),
            'expires_at': (now[0] + timedelta(hours=2)).isoformat(), 'enabled': True}
    verifier = HumanAuthVerifier(HumanAuthRegistry.model_validate(registry), max_token_ttl_seconds=86400)
    principals = {role: verifier.verify('Bearer ' + token) for role, token in raw.items()}
    # Explicitly simulated validated LIVE parent; no real provider/factory enables.
    async with stack.repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, publication.publication_id)
            parent.mode = 'live'; parent.status = 'publishing'; parent.receipt_json = None
            parent.dry_run = False; parent.mock = True
            parent.provider_validation_json = {**parent.provider_validation_json, 'adapter_state': 'ready', 'supports_live_publish': True}
            asset = await session.get(AssetORM, final.output_asset_id)
            source_sha = asset.checksum_sha256; total_bytes = asset.size_bytes
    journal = PublishingDispatchJournal(stack.repository.session_factory, identity_provider=lambda: verifier, clock=lambda: now[0])
    async def approve(**overrides):
        return await journal.approve(workspace, publication.publication_id, **{
            'principal': principals['owner'], 'expected_fingerprint': publication.request_fingerprint,
            'expected_artifact_sha256': source_sha, 'acknowledged': True,
            'idempotency_key': 'explicit-owner-publish-only-fixture', **overrides})
    try:
        yield {'stack': stack, 'publication': publication, 'workspace': workspace, 'journal': journal, 'approve': approve,
            'principals': principals, 'verifier': verifier, 'clock': now, 'total_bytes': total_bytes, 'source_sha': source_sha, 'db': tmp_path / 'production.db'}
    finally:
        await stack.engine.dispose()


async def prepared(fixture):
    grant = await fixture['approve']()
    value = await fixture['journal'].prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    return grant, value


@pytest.mark.asyncio
async def test_separate_owner_consent_is_exact_idempotent_and_does_not_change_production_approval(fixture_stack):
    fixture = fixture_stack; first = await fixture['approve']()
    fixture['clock'][0] += timedelta(seconds=5); second = await fixture['approve']()
    assert first == second and first['scope'] == 'PUBLISH_ONLY'
    async with fixture['stack'].repository.session_factory() as session:
        grants = (await session.scalars(select(PublishApprovalORM))).all(); assert len(grants) == 1
        assert grants[0].owner_token_id == 'explicit-owner'
        parent = await session.get(PublicationORM, fixture['publication'].publication_id)
        assert parent.approval_id == fixture['publication'].approval_id and parent.receipt_json is None
    assert not hasattr(grants[0], 'token') and 'artifact_sha256' in grants[0].binding_json


@pytest.mark.asyncio
async def test_roles_forged_identity_missing_ack_stale_hash_and_foreign_scope_cannot_consent(fixture_stack):
    fixture = fixture_stack
    for role in ('editor', 'reviewer', 'viewer'):
        with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'):
            await fixture['approve'](principal=fixture['principals'][role])
    forged = replace(fixture['principals']['editor'], workspace_roles={fixture['workspace']: 'owner'})
    with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'):
        await fixture['approve'](principal=forged)
    with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'): await fixture['approve'](acknowledged=False)
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_STALE_RELOAD'): await fixture['approve'](expected_artifact_sha256='0' * 64)
    with pytest.raises(DispatchError, match='PUBLISH_SCOPE_NOT_FOUND'):
        await fixture['journal'].get('wsp_foreign_fixture', fixture['publication'].publication_id)


@pytest.mark.asyncio
async def test_init_intent_is_committed_before_ticket_and_process_restart_cannot_repeat_post(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture)
    journal = fixture['journal']; identifier = fixture['publication'].publication_id
    ticket = await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    async with fixture['stack'].repository.session_factory() as session:
        row = await session.get(PublicationDispatchORM, identifier)
        assert row.phase == 'init_intent' and row.intent_id == ticket.intent_id and row.version == ticket.version
    await fixture['stack'].engine.dispose()
    source = ('import asyncio,json; from app.db import create_engine,create_session_factory; '
        'from app.publishing_dispatch import PublishingDispatchJournal; '
        f'engine=create_engine({str("sqlite+aiosqlite:///" + str(fixture["db"])).__repr__()}); '
        'journal=PublishingDispatchJournal(create_session_factory(engine)); '
        'async def_run_placeholder')
    source = source.replace('async def_run_placeholder', f'\nasync def run():\n print(json.dumps(await journal.get({fixture["workspace"]!r},{identifier!r})))\n await engine.dispose()\nasyncio.run(run())')
    restarted = json.loads(subprocess.check_output([sys.executable, '-c', source], cwd=Path(__file__).parents[1], timeout=20))
    assert restarted['phase'] == 'init_intent' and 'intent_id' not in restarted and 'private_session_ref' not in restarted
    fixture['clock'][0] += timedelta(minutes=10)
    with pytest.raises(DispatchError, match='PUBLISH_INITIALIZATION_MUST_NOT_REPEAT'):
        await journal.intent(fixture['workspace'], identifier, ticket.version, 'init')
    unknown = await journal.finish(ticket, uncertain=True); assert unknown['phase'] == 'init_uncertain'
    with pytest.raises(DispatchError, match='PUBLISH_INITIALIZATION_MUST_NOT_REPEAT'):
        await journal.intent(fixture['workspace'], identifier, unknown['version'], 'init')


@pytest.mark.asyncio
async def test_only_one_concurrent_init_claim_succeeds_and_late_ticket_cannot_overwrite(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    results = await asyncio.gather(*(journal.intent(fixture['workspace'], identifier, value['version'], 'init') for _ in range(2)), return_exceptions=True)
    winners = [result for result in results if not isinstance(result, Exception)]; assert len(winners) == 1
    assert isinstance(next(result for result in results if isinstance(result, Exception)), DispatchError)
    ticket = winners[0]; saved = await journal.finish(ticket, session_ref='pss_' + 'a' * 32)
    assert saved['phase'] == 'upload_ready' and 'private_session_ref' not in saved
    with pytest.raises(DispatchError, match='PUBLISH_DISPATCH_STALE_TICKET'):
        await journal.finish(ticket, session_ref='pss_' + 'b' * 32)


@pytest.mark.asyncio
async def test_chunk_crash_lease_requires_reconciliation_and_fences_previous_worker(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    start = await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    saved = await journal.finish(start, session_ref='pss_' + 'a' * 32)
    chunk = await journal.intent(fixture['workspace'], identifier, saved['version'], 'chunk', offset=0, length=fixture['total_bytes'])
    with pytest.raises(DispatchError, match='PUBLISH_RECONCILIATION_LEASE_OR_SCOPE_INVALID'):
        await journal.intent(fixture['workspace'], identifier, chunk.version, 'reconcile')
    fixture['clock'][0] += timedelta(seconds=181)
    query = await journal.intent(fixture['workspace'], identifier, chunk.version, 'reconcile')
    with pytest.raises(DispatchError, match='PUBLISH_DISPATCH_STALE_TICKET'):
        await journal.finish(chunk, acknowledged_bytes=fixture['total_bytes'], remote_post_id='AbcD_12-345')
    done = await journal.finish(query, acknowledged_bytes=fixture['total_bytes'], remote_post_id='AbcD_12-345')
    assert done['phase'] == 'uploaded' and done['remote_post_id'] == 'AbcD_12-345'
    with pytest.raises(DispatchError, match='PUBLISH_INITIALIZATION_MUST_NOT_REPEAT'):
        await journal.intent(fixture['workspace'], identifier, done['version'], 'init')


@pytest.mark.asyncio
async def test_unknown_chunk_outcome_queries_same_session_without_receipt_assumptions(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    start = await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    ready = await journal.finish(start, session_ref='pss_' + 'c' * 32)
    chunk = await journal.intent(fixture['workspace'], identifier, ready['version'], 'chunk', offset=0, length=fixture['total_bytes'])
    uncertain = await journal.finish(chunk, uncertain=True); assert uncertain['acknowledged_bytes'] == 0
    query = await journal.intent(fixture['workspace'], identifier, uncertain['version'], 'reconcile')
    with pytest.raises(DispatchError, match='PUBLISH_REMOTE_RECEIPT_REQUIRED'):
        await journal.finish(query, acknowledged_bytes=fixture['total_bytes'])
    state = await journal.finish(query, acknowledged_bytes=0)
    assert state['phase'] == 'upload_ready' and state['remote_post_id'] is None
    with pytest.raises(DispatchError, match='PUBLISH_CHUNK_RECONCILIATION_REQUIRED'):
        await journal.intent(fixture['workspace'], identifier, state['version'], 'chunk', offset=1, length=1)


@pytest.mark.asyncio
async def test_raw_upload_uri_and_noninteger_progress_are_never_persisted(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    start = await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    with pytest.raises(DispatchError, match='PUBLISH_PRIVATE_SESSION_REFERENCE_REQUIRED'):
        await journal.finish(start, session_ref='https://www.googleapis.com/upload?PRIVATE_TOKEN')
    ready = await journal.finish(start, session_ref='pss_' + 'a' * 32)
    chunk = await journal.intent(fixture['workspace'], identifier, ready['version'], 'chunk', offset=0, length=1)
    for progress in (True, -1, fixture['total_bytes']):
        with pytest.raises(DispatchError): await journal.finish(chunk, acknowledged_bytes=progress)
    async with fixture['stack'].repository.session_factory() as session:
        events = (await session.scalars(select(PublicationEventORM))).all()
        text = json.dumps([event.payload_json for event in events])
        assert 'PRIVATE_TOKEN' not in text and 'pss_' not in text and chunk.intent_id not in text


@pytest.mark.asyncio
async def test_expired_or_changed_owner_authority_blocks_future_dispatch(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture)
    owner = fixture['verifier'].registry.tokens['explicit-owner']
    fixture['verifier'].registry.tokens['explicit-owner'] = owner.model_copy(update={'enabled': False})
    with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], value['version'], 'init')
    fixture['verifier'].registry.tokens['explicit-owner'] = owner.model_copy(update={'token_sha256': 'b' * 64})
    with pytest.raises(DispatchError, match='PUBLISH_OWNER_IDENTITY_CHANGED'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], value['version'], 'init')
    assert (await fixture['journal'].get(fixture['workspace'], value['publication_id']))['phase'] == 'init_ready'


@pytest.mark.asyncio
async def test_approval_expiry_source_hash_and_timeline_changes_fail_closed(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, identifier); asset = await session.get(AssetORM, parent.output_asset_id)
            original = asset.checksum_sha256; asset.checksum_sha256 = 'b' * 64
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_STALE_RELOAD'): await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id); asset.checksum_sha256 = original
            timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == fixture['publication'].project_id))
            timeline.current_version += 1
    with pytest.raises(DispatchError, match='PUBLISH_CURRENT_APPROVAL_QC_REQUIRED'): await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    fixture['clock'][0] += timedelta(hours=1, seconds=1)
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_REQUIRED_OR_EXPIRED'): await journal.intent(fixture['workspace'], identifier, value['version'], 'init')


@pytest.mark.asyncio
async def test_no_identity_provider_or_unready_official_provider_cannot_start(fixture_stack):
    fixture = fixture_stack
    no_identity = PublishingDispatchJournal(fixture['stack'].repository.session_factory)
    with pytest.raises(DispatchError, match='PUBLISH_OWNER_IDENTITY_REVALIDATION_REQUIRED'):
        await no_identity.approve(fixture['workspace'], fixture['publication'].publication_id,
            principal=fixture['principals']['owner'], expected_fingerprint=fixture['publication'].request_fingerprint,
            expected_artifact_sha256=fixture['source_sha'], acknowledged=True, idempotency_key='explicit-missing-owner-authority')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            parent = await session.get(PublicationORM, fixture['publication'].publication_id)
            parent.provider_validation_json = {**parent.provider_validation_json, 'adapter_state': 'contract_only', 'supports_live_publish': False}
    with pytest.raises(DispatchError, match='PUBLISH_PROVIDER_NOT_READY'): await fixture['approve']()


@pytest.mark.asyncio
async def test_concurrent_same_key_consent_replays_one_grant_and_owner_revocation_blocks_intent(fixture_stack):
    fixture = fixture_stack
    grants = await asyncio.gather(fixture['approve'](), fixture['approve']())
    assert grants[0] == grants[1]
    value = await fixture['journal'].prepare(fixture['workspace'], fixture['publication'].publication_id, grants[0]['publish_approval_id'])
    with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'):
        await fixture['journal'].revoke(fixture['workspace'], grants[0]['publish_approval_id'], principal=fixture['principals']['editor'])
    revoked = await fixture['journal'].revoke(fixture['workspace'], grants[0]['publish_approval_id'], principal=fixture['principals']['owner'])
    assert revoked['revoked'] is True
    assert await fixture['journal'].revoke(fixture['workspace'], grants[0]['publish_approval_id'], principal=fixture['principals']['owner']) == revoked
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_REQUIRED_OR_EXPIRED'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], value['version'], 'init')


@pytest.mark.asyncio
async def test_reconciliation_crash_can_repeat_only_safe_query_after_lease_and_stale_reply_is_fenced(fixture_stack):
    fixture = fixture_stack; _grant, value = await prepared(fixture); journal = fixture['journal']; identifier = value['publication_id']
    start = await journal.intent(fixture['workspace'], identifier, value['version'], 'init')
    saved = await journal.finish(start, session_ref='pss_' + 'a' * 32)
    first = await journal.intent(fixture['workspace'], identifier, saved['version'], 'reconcile')
    with pytest.raises(DispatchError, match='PUBLISH_RECONCILIATION_LEASE_OR_SCOPE_INVALID'):
        await journal.intent(fixture['workspace'], identifier, first.version, 'reconcile')
    fixture['clock'][0] += timedelta(seconds=181)
    second = await journal.intent(fixture['workspace'], identifier, first.version, 'reconcile')
    with pytest.raises(DispatchError, match='PUBLISH_DISPATCH_STALE_TICKET'):
        await journal.finish(first, acknowledged_bytes=0)
    assert (await journal.finish(second, acknowledged_bytes=0))['phase'] == 'upload_ready'


def test_public_state_cannot_be_turned_into_unclaimed_or_invalid_dispatch_ticket():
    for phase, version, nonce in [('init_ready', 1, None), ('uploaded', 4, 'a' * 32), ('init_intent', True, 'a' * 32), ('init_intent', 2, '')]:
        with pytest.raises(DispatchError, match='PUBLISH_DISPATCH_TICKET_INVALID'):
            DispatchTicket('wsp_fixture', 'pub_fixture', phase, version, nonce)
