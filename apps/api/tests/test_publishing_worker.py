"""Owned bytes/SQLite/AES with explicit mock QC, account, OAuth and provider transport."""
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from app.db import AssetORM, CostRecordORM, ProviderUsageORM
from app.object_storage import LocalObjectStorageProvider
from app.publishing_artifact import PublishingArtifactGuard
from app.publishing_credentials import READ, UPLOAD, PublishingOAuthCredential
from app.publishing_credentials import PublishingCredentialError
from app.publishing_dispatch import DispatchError
from app.publishing_session_vault import PublishingSessionVault, SessionEncryptionKey, SessionVaultError
from app.publishing_wire import OfficialHTTPClient, PublishingWireError
from app.publishing_worker import PublishingWorkerError, YouTubePublishingWorker
from app.youtube_upload import UNIT
from test_publishing_artifact import blob
from test_publishing_dispatch import fixture_stack
from test_publishing_operations import meter_for
from test_publishing_target import bind_target


class ExplicitReceiver:
    def __init__(self, fixture, journal, target, raw, *, lose_final=False, lose_init=False, wrong_account=False):
        self.fixture, self.journal, self.target, self.raw = fixture, journal, target, raw
        self.received = bytearray(); self.requests = []; self.initializations = 0
        self.lose_final, self.lose_init, self.wrong_account = lose_final, lose_init, wrong_account
        self.uri = 'https://www.googleapis.com/upload/youtube/v3/videos?upload_id=EXPLICIT_PRIVATE_FIXTURE'

    async def handle(self, request):
        async with self.fixture['stack'].repository.session_factory() as session:
            intents = (await session.scalars(select(ProviderUsageORM).where(ProviderUsageORM.status == 'dispatch_intent',
                ProviderUsageORM.project_id == self.fixture['publication'].project_id))).all()
            assert len(intents) == 1  # cost/request intent committed before callback
        self.requests.append(request.method)
        if request.method == 'GET':
            return httpx.Response(200, json={'items': [{'id': 'OTHER-ACCOUNT' if self.wrong_account else self.target.target_account_id}]})
        state = await self.journal.get(self.fixture['workspace'], self.fixture['publication'].publication_id)
        if request.method == 'POST':
            assert state['phase'] == 'init_intent'; self.initializations += 1
            if self.lose_init: raise httpx.ReadError('EXPLICIT PRIVATE LOST RESPONSE', request=request)
            return httpx.Response(201, headers={'Location': self.uri})
        assert str(request.url) == self.uri
        if request.headers['content-range'].startswith('bytes */'):
            assert state['phase'] == 'reconcile_intent' and not request.content
            if len(self.received) == len(self.raw): return httpx.Response(200, json={'id': 'AbcD_12-345'})
            return httpx.Response(308, headers={'Range': 'bytes=0-' + str(len(self.received) - 1)} if self.received else {})
        assert state['phase'] == 'chunk_intent'
        self.received.extend(request.content)
        if len(self.received) == len(self.raw):
            if self.lose_final:
                self.lose_final = False
                raise httpx.ReadError('EXPLICIT PRIVATE LOST RESPONSE', request=request)
            return httpx.Response(200, json={'id': 'AbcD_12-345'})
        return httpx.Response(308, headers={'Range': 'bytes=0-' + str(len(self.received) - 1)})


async def configured_worker(fixture, tmp_path, **receiver_options):
    pytest.importorskip('cryptography.hazmat.primitives.ciphers.aead')
    journal, target, _calls, approve = await bind_target(fixture)
    source_bytes = receiver_options.pop('source_bytes', None)
    raw = blob() if source_bytes is None else source_bytes
    source = tmp_path / ('EXPLICIT-PLACEHOLDER-NOT-PLAYABLE.mp4' if source_bytes is None else 'explicit-synthetic-source.mp4')
    source.write_bytes(raw)
    storage = LocalObjectStorageProvider(tmp_path / 'objects'); await storage.ensure_ready()
    key = f'workspaces/{fixture["workspace"]}/projects/{fixture["publication"].project_id}/publish/fixture.mp4'
    stored = await storage.put_file(object_key=key, path=source, content_type='video/mp4')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id)
            asset.object_key = key; asset.storage_provider = stored.storage_provider
            asset.checksum_sha256 = stored.checksum_sha256; asset.size_bytes = stored.size_bytes
    grant = await approve(expected_artifact_sha256=stored.checksum_sha256)
    await journal.prepare(fixture['workspace'], fixture['publication'].publication_id, grant['publish_approval_id'])
    work = tmp_path / 'private-work'; work.mkdir(); guard = PublishingArtifactGuard(journal, storage, work)
    async def fixture_qc(_path, **_kwargs):
        return {'status': 'passed', 'checksum_sha256': stored.checksum_sha256, 'mock_qc': True, 'publishing_blocked': True}
    guard.qc.inspect = fixture_qc
    meter = await meter_for(fixture)
    vault = PublishingSessionVault(journal.session_factory, key_provider=lambda _: SessionEncryptionKey('explicit_fixture', bytes(range(32))),
        clock=lambda: fixture['clock'][0])
    receiver = ExplicitReceiver(fixture, journal, target[0], raw, **receiver_options)
    client = OfficialHTTPClient('youtube', transport=httpx.MockTransport(receiver.handle))
    credential = PublishingOAuthCredential(target[0], fixture['clock'][0] + timedelta(hours=1), frozenset({UPLOAD, READ}),
        'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234')
    policy = {'publish_enabled': True, 'publish_external_execution_enabled': True, 'publish_owner_gate_enabled': True}
    options = dict(journal=journal, vault=vault, artifact_guard=guard, meter=meter, client=client,
        credential_resolver=lambda _: credential, policy_provider=lambda: policy, category_id='27', made_for_kids=False,
        contains_synthetic_media=True, chunk_size=UNIT)
    return YouTubePublishingWorker(**options), options, receiver, grant, work, policy


@pytest.mark.asyncio
async def test_real_verified_bytes_aes_sqlite_and_cost_intents_cross_mock_wire_then_lost_final_reconciles(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, options, receiver, grant, work, _policy = await configured_worker(fixture, tmp_path, lose_final=True)
    workspace, pub = fixture['workspace'], fixture['publication'].publication_id
    assert (await worker.step(workspace, pub))['phase'] == 'upload_ready'
    assert (await worker.step(workspace, pub))['acknowledged_bytes'] == UNIT
    assert (await worker.step(workspace, pub))['acknowledged_bytes'] == 2 * UNIT
    with pytest.raises(PublishingWireError, match='PUBLISHING_NETWORK_OUTCOME_UNKNOWN'):
        await worker.step(workspace, pub)
    assert (await worker.journal.get(workspace, pub))['phase'] == 'chunk_uncertain'
    await worker.journal.revoke(workspace, grant['publish_approval_id'], principal=fixture['principals']['owner'])
    await fixture['stack'].engine.dispose()
    restarted = YouTubePublishingWorker(**options)
    done = await restarted.step(workspace, pub)
    assert done['phase'] == 'uploaded' and done['remote_post_id'] == 'AbcD_12-345'
    assert bytes(receiver.received) == receiver.raw and receiver.initializations == 1 and list(work.iterdir()) == []
    state = await restarted.step(workspace, pub)
    assert state['published'] is False and state['processing_acceptance'] == 'NOT_CHECKED'
    async with fixture['stack'].repository.session_factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
        assert len(costs) == len(receiver.requests) and all(cost.actual_cost is None for cost in costs)


@pytest.mark.asyncio
async def test_ambiguous_initialization_never_reposts_even_after_new_worker(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, options, receiver, _grant, _work, _policy = await configured_worker(fixture, tmp_path, lose_init=True)
    with pytest.raises(PublishingWireError): await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    with pytest.raises(PublishingWorkerError, match='PUBLISH_INITIALIZATION_REVIEW_REQUIRED'):
        await YouTubePublishingWorker(**options).step(fixture['workspace'], fixture['publication'].publication_id)
    assert receiver.initializations == 1


@pytest.mark.asyncio
async def test_default_missing_owner_gates_and_unknown_budget_block_before_wire(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, options, receiver, _grant, _work, policy = await configured_worker(fixture, tmp_path)
    absent = YouTubePublishingWorker(**{**options, 'policy_provider': None})
    with pytest.raises(PublishingWorkerError, match='PUBLISH_WORKER_OWNER_GATES_REQUIRED'):
        await absent.step(fixture['workspace'], fixture['publication'].publication_id)
    policy['max_ai_cost'] = Decimal('100')
    with pytest.raises(PublishingWorkerError, match='PUBLISH_COST_APPROVAL_REQUIRED'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    assert receiver.requests == [] and (await worker.journal.get(fixture['workspace'], fixture['publication'].publication_id))['phase'] == 'init_ready'


@pytest.mark.asyncio
async def test_missing_encryption_key_refuses_before_even_account_lookup(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, _grant, _work, _policy = await configured_worker(fixture, tmp_path)
    worker.vault.key_provider = None
    with pytest.raises(SessionVaultError, match='PUBLISH_SESSION_KEY_NOT_CONFIGURED'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    assert not receiver.requests and receiver.initializations == 0


@pytest.mark.asyncio
async def test_known_configured_estimates_fit_cap_without_fabricating_actual_billing(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, _grant, _work, policy = await configured_worker(fixture, tmp_path)
    policy.update(max_ai_cost=Decimal('100'), estimated_costs={'account_lookup': Decimal('1'), 'initialize': Decimal('1')})
    assert (await worker.step(fixture['workspace'], fixture['publication'].publication_id))['phase'] == 'upload_ready'
    async with fixture['stack'].repository.session_factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
        assert len(costs) == 2 and all(cost.actual_cost is None and cost.estimated_cost == Decimal('1') for cost in costs)
    assert receiver.initializations == 1


@pytest.mark.asyncio
async def test_consent_revoked_before_start_prevents_all_account_and_mutation_requests(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, grant, _work, _policy = await configured_worker(fixture, tmp_path)
    await worker.journal.revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    with pytest.raises(DispatchError, match='PUBLISH_APPROVAL_REQUIRED_OR_EXPIRED'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    assert not receiver.requests


@pytest.mark.asyncio
async def test_refreshed_token_after_qc_is_checked_again_against_the_exact_account(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, _grant, _work, _policy = await configured_worker(fixture, tmp_path)
    credential = worker.credential_resolver(None); calls = []
    def rotate(_target):
        calls.append(True)
        return PublishingOAuthCredential(credential.target, credential.expires_at, credential.scopes,
            credential.token if len(calls) == 1 else 'EXPLICIT_ROTATED_WRONG_ACCOUNT_FIXTURE_1234')
    async def qc(_path, **_kwargs):
        receiver.wrong_account = True
        async with fixture['stack'].repository.session_factory() as session:
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id)
            return {'status': 'passed', 'checksum_sha256': asset.checksum_sha256, 'mock_qc': True, 'publishing_blocked': True}
    worker.credential_resolver = rotate; worker.guard.qc.inspect = qc
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_ACCOUNT_NOT_CONFIRMED'):
        await worker.step(fixture['workspace'], fixture['publication'].publication_id)
    assert receiver.requests == ['GET', 'GET'] and receiver.initializations == 0
