"""Actual API/SQLite/AES/range integration with explicitly mock media QC/accounts/transport."""
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json

import httpx
import pytest
from sqlalchemy import select

from app.db import AssetORM, CostRecordORM, ProviderRegistryORM
from app.object_storage import LocalObjectStorageProvider
from app.publishing_credentials import PublishingOAuthCredential, READ, UPLOAD
from app.publishing_logic import request_fingerprint
from app.publishing_models import PublicationReceipt, PublishApprovalRequest
from app.publishing_profiles import PublishingProfile, PublishingProfileCatalog, PublishingProfileRegistry, PROVIDER_KEYS
from app.publishing_providers import PublishingContext, ExternalPublishingNotActivated
from app.publishing_runtime import YouTubePublishingRuntime
from app.publishing_dispatch import DispatchError
from app.publishing_session_vault import SessionEncryptionKey
from app.publishing_wire import OfficialHTTPClient
from test_publishing_artifact import blob
from test_publishing_dispatch import fixture_stack
from test_publishing_queue import configured_service, headers, http_app, request_for
from test_publishing_target import target_for
from test_publishing_worker import ExplicitReceiver


async def runtime_fixture(fixture, tmp_path, *, cap=None, source_bytes=None, **settings):
    pytest.importorskip('cryptography.hazmat.primitives.ciphers.aead')
    configured = configured_service(fixture, **settings); service = configured.service
    target = target_for(fixture, provider_key=PROVIDER_KEYS['youtube'])
    profile = PublishingProfile(target=target, category_id='27', made_for_kids=False, contains_synthetic_media=True, max_ai_cost=cap)
    profiles = PublishingProfileRegistry(PublishingProfileCatalog(profiles=[profile]))
    storage = LocalObjectStorageProvider(tmp_path / 'objects'); await storage.ensure_ready()
    source = tmp_path / ('EXPLICIT-PLACEHOLDER-NOT-PLAYABLE.mp4' if source_bytes is None else 'explicit-synthetic-source.mp4')
    source.write_bytes(blob() if source_bytes is None else source_bytes)
    key = f'workspaces/{fixture["workspace"]}/projects/{fixture["publication"].project_id}/explicit-runtime-fixture.mp4'
    stored = await storage.put_file(object_key=key, path=source, content_type='video/mp4')
    factory = fixture['stack'].repository.session_factory
    async with factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id)
            asset.object_key = key; asset.storage_provider = stored.storage_provider
            asset.checksum_sha256 = stored.checksum_sha256; asset.size_bytes = stored.size_bytes
            session.add(ProviderRegistryORM(provider_id='pvd_explicit_runtime_fixture', workspace_id=fixture['workspace'],
                provider_key=PROVIDER_KEYS['youtube'], display_name='EXPLICIT FIXTURE; NO REAL PROVIDER', capability='publishing',
                adapter='explicit.fixture', routing_mode='disabled', status='fixture', enabled=False,
                supports_dry_run=True, config_ref=None, metadata_json={'fixture_only': True}))
    work = tmp_path / 'private-work'; work.mkdir(); receiver = []
    async def handle(request):
        assert receiver, 'Installation or validation attempted a provider call'
        if request.method == 'GET' and request.url.path.endswith('/videos'):
            receiver[0].requests.append('GET')
            return httpx.Response(200, json={'items': [{'id': 'AbcD_12-345', 'status': {'privacyStatus': 'private'},
                'processingDetails': {'processingStatus': 'succeeded'}}]})
        return await receiver[0].handle(request)
    credential = PublishingOAuthCredential(target, fixture['clock'][0] + timedelta(hours=1), frozenset({READ, UPLOAD}),
        'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234')
    runtime = YouTubePublishingRuntime(service=service, profiles=profiles, storage=storage, private_root=work,
        identity_provider=lambda: fixture['verifier'], credential_resolver=lambda _: credential,
        key_provider=lambda _: SessionEncryptionKey('explicit_fixture', bytes(range(32))),
        client=OfficialHTTPClient('youtube', transport=httpx.MockTransport(handle)),
        clock=lambda: fixture['clock'][0]).install()
    async def fixture_qc(_path, **_kwargs):
        return {'status': 'passed', 'checksum_sha256': stored.checksum_sha256, 'mock_qc': True, 'publishing_blocked': True}
    runtime.guard.qc.inspect = fixture_qc
    payload = request_for(fixture['publication'].final_render_id, mode='live')
    return runtime, service, payload, receiver, stored, source, profile


async def create_and_approve(fixture, tmp_path, **options):
    runtime, service, payload, receiver, stored, source, profile = await runtime_fixture(fixture, tmp_path, **options)
    row, _ = await service.create(project_id=fixture['publication'].project_id, payload=payload, idempotency_key='explicit-runtime-publication')
    fixture_receiver = {**fixture, 'publication': row}
    receiver.append(ExplicitReceiver(fixture_receiver, runtime.journal, profile.target, source.read_bytes()))
    from app.publishing_dispatch import checksum
    grant = await service.approve_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'],
        payload=PublishApprovalRequest(expected_fingerprint=row.request_fingerprint, expected_artifact_sha256=stored.checksum_sha256,
            expected_target_sha256=checksum(profile.target.model_dump(mode='json')), acknowledged=True),
        idempotency_key='explicit-runtime-owner-consent')
    return runtime, service, row, grant, receiver[0], source, profile


@pytest.mark.asyncio
async def test_configured_runtime_full_api_queue_upload_processing_and_provider_receipt_status(fixture_stack, tmp_path):
    fixture = fixture_stack; runtime, service, row, grant, receiver, source, profile = await create_and_approve(fixture, tmp_path)
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    assert row.status == 'awaiting_publish_approval' and row.mock and not row.external_action and receiver.requests == []
    application = http_app(fixture, type('ConfiguredFixture', (), {'service': service})())
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}/publishing-work'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://explicit-test', headers=headers('owner')) as client:
        response = await client.post(path, json={'publish_approval_id': grant['publish_approval_id']})
        assert response.status_code == 200 and response.json()['status'] == 'queued'
        work = response.json()
    provider = service.providers.for_live('youtube', workspace_id=row.workspace_id, profile_id=profile.target.profile_id)
    context = PublishingContext(platform='youtube', project_id=row.project_id, final_render_id=row.final_render_id,
        output_asset_id=row.output_asset_id, request_fingerprint=row.request_fingerprint, metadata=row.metadata,
        publication_id=row.publication_id, publish_approval_id=grant['publish_approval_id'])
    submitted = await provider.publish(context)
    assert submitted.work_id == work['work_id'] and submitted.external_action is False and submitted.mock
    assert await provider.get_status(submitted) == 'queued' and receiver.requests == []
    for _ in range(3):
        await fixture['stack'].engine.dispose()
        work = await runtime.run_one(row.workspace_id, work['work_id'], work['version'])
        fixture['clock'][0] += timedelta(seconds=2)
    assert work['status'] == 'completed' and receiver.initializations == 1 and receiver.requests == ['GET', 'POST', 'GET', 'PUT', 'GET', 'GET']
    done = await service.get(row.project_id, row.publication_id)
    assert done.mock and not done.external_action and done.receipt.remote_url is None
    assert await provider.get_status(done.receipt) == 'published'
    assert bytes(receiver.received) == source.read_bytes() and hashlib.sha256(source.read_bytes()).hexdigest() == original_sha
    assert await provider.delete_or_cancel_if_supported(done.receipt) is False
    async with runtime.session_factory() as session:
        costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
    assert len(costs) == 8 and all(cost.actual_cost is None for cost in costs)
    other = profile.model_copy(update={'target': profile.target.model_copy(update={'profile_id': 'ppf_other_channel'})})
    runtime.profiles.replace_catalog(PublishingProfileCatalog(profiles=[profile, other]))
    wrong_channel = service.providers.for_live('youtube', workspace_id=row.workspace_id, profile_id=other.target.profile_id)
    with pytest.raises(ExternalPublishingNotActivated, match='RECEIPT_SCOPE_REQUIRED'): await wrong_channel.get_status(done.receipt)
    with pytest.raises(ExternalPublishingNotActivated, match='CONTEXT_MISMATCH'): await wrong_channel.publish(context)
    assert len(receiver.requests) == 8


@pytest.mark.asyncio
async def test_disabled_installation_has_no_wire_or_secret_reads_and_does_not_enable_flags(fixture_stack, tmp_path):
    fixture = fixture_stack
    runtime, service, _payload, receiver, _stored, _source, profile = await runtime_fixture(fixture, tmp_path,
        publish_enabled=False, publish_external_execution_enabled=False, publish_owner_gate_enabled=False)
    assert not service.settings.publish_enabled and receiver == []
    provider = service.providers.for_live('youtube', workspace_id=fixture['workspace'], profile_id=profile.target.profile_id)
    assert provider.validate().adapter_state == 'not_configured' and provider.validate().mock_execution
    assert not provider.validate().supports_live_publish
    assert service.providers.for_live('facebook', workspace_id=fixture['workspace']).platform == 'facebook'


@pytest.mark.asyncio
async def test_multiple_profiles_need_explicit_selection_and_profile_change_invalidates_old_consent(fixture_stack, tmp_path):
    fixture = fixture_stack; runtime, service, row, grant, receiver, _source, profile = await create_and_approve(fixture, tmp_path)
    second = profile.model_copy(update={'target': profile.target.model_copy(update={'profile_id': 'ppf_other_channel'})})
    runtime.profiles.replace_catalog(PublishingProfileCatalog(profiles=[profile, second]))
    assert not service.providers.for_live('youtube', workspace_id=row.workspace_id).validate().supports_live_publish
    assert service.providers.for_live('youtube', workspace_id=row.workspace_id, profile_id=profile.target.profile_id).validate().supports_live_publish
    work = await service.schedule_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'],
        publish_approval_id=grant['publish_approval_id'])
    revised = profile.model_copy(update={'target': profile.target.model_copy(update={'profile_version': 2})})
    runtime.profiles.replace_catalog(PublishingProfileCatalog(profiles=[profile, second, revised]))
    with pytest.raises(DispatchError, match='TARGET_CHANGED_REVALIDATE'):
        await service.schedule_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'], publish_approval_id=grant['publish_approval_id'])
    assert receiver.requests == []
    refused = await runtime.run_one(row.workspace_id, work['work_id'], work['version'])
    assert refused['status'] == 'review_required' and refused['failure_code'] == 'PUBLISH_RUNTIME_TARGET_CHANGED'


@pytest.mark.asyncio
async def test_unknown_cost_with_configured_profile_cap_blocks_before_wire(fixture_stack, tmp_path):
    fixture = fixture_stack; runtime, service, row, grant, receiver, _source, _profile = await create_and_approve(fixture, tmp_path, cap=Decimal('100'))
    work = await service.schedule_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'], publish_approval_id=grant['publish_approval_id'])
    work = await runtime.run_one(row.workspace_id, work['work_id'], work['version'])
    assert work['status'] == 'review_required' and work['failure_code'] == 'PUBLISH_COST_APPROVAL_REQUIRED' and receiver.requests == []


@pytest.mark.asyncio
async def test_missing_key_after_consent_cannot_make_an_account_request(fixture_stack, tmp_path):
    fixture = fixture_stack; runtime, service, row, grant, receiver, _source, _profile = await create_and_approve(fixture, tmp_path)
    work = await service.schedule_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'], publish_approval_id=grant['publish_approval_id'])
    runtime.vault.key_provider = None
    work = await runtime.run_one(row.workspace_id, work['work_id'], work['version'])
    assert work['status'] == 'review_required' and work['failure_code'] == 'PUBLISH_SESSION_KEY_NOT_CONFIGURED' and receiver.requests == []


@pytest.mark.asyncio
async def test_provider_context_and_forged_receipts_cannot_admit_or_read_foreign_work(fixture_stack, tmp_path):
    fixture = fixture_stack; runtime, service, row, grant, receiver, _source, profile = await create_and_approve(fixture, tmp_path)
    provider = service.providers.for_live('youtube', workspace_id=row.workspace_id, profile_id=profile.target.profile_id)
    context = PublishingContext(platform='youtube', project_id=row.project_id, final_render_id=row.final_render_id,
        output_asset_id=row.output_asset_id, request_fingerprint=row.request_fingerprint, metadata=row.metadata)
    with pytest.raises(ExternalPublishingNotActivated, match='SCOPED_CONSENT_REQUIRED'): await provider.publish(context)
    foreign = replace(context, publication_id=row.publication_id, publish_approval_id=grant['publish_approval_id'], project_id='prj_foreign_fixture')
    with pytest.raises(ExternalPublishingNotActivated, match='CONTEXT_MISMATCH'): await provider.publish(foreign)
    receipt = PublicationReceipt(receipt_id='EXPLICIT-FORGED', provider_key=provider.provider_key, platform='youtube', mode='live',
        request_fingerprint=row.request_fingerprint, mock=True, external_action=False, created_at=fixture['clock'][0])
    with pytest.raises(ExternalPublishingNotActivated, match='RECEIPT_SCOPE_REQUIRED'): await provider.get_status(receipt)
    assert receiver.requests == []


def test_optional_profile_selection_preserves_preexisting_request_fingerprint():
    from app.publishing_models import PublicationCreateRequest, PublicationMetadata
    payload = PublicationCreateRequest(platform='youtube', final_render_id='rnd_explicit_fixture', metadata=PublicationMetadata(title='EXPLICIT FIXTURE'))
    legacy = payload.model_dump(mode='json'); legacy.pop('publishing_profile_id')
    expected = hashlib.sha256(json.dumps(legacy, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    assert request_fingerprint(payload) == expected
    assert request_fingerprint(payload.model_copy(update={'publishing_profile_id': 'ppf_explicit_profile'})) != expected


@pytest.mark.asyncio
async def test_due_scan_keeps_processing_after_one_item_was_claimed_by_another_worker():
    from types import SimpleNamespace
    runtime = object.__new__(YouTubePublishingRuntime)
    items = [{'work_id': 'first', 'version': 1, 'status': 'queued'}, {'work_id': 'second', 'version': 1, 'status': 'queued'}]
    async def due(_workspace, **_kwargs): return items
    calls = []
    async def one(_workspace, work_id, _version):
        calls.append(work_id)
        if work_id == 'first': raise DispatchError('PUBLISH_WORK_NOT_DUE_OR_STALE')
        return {**items[1], 'status': 'completed'}
    runtime.queue = SimpleNamespace(due=due); runtime.run_one = one
    result = await runtime.run_due('fixture')
    assert calls == ['first', 'second'] and result[0]['status'] == 'queued'
    assert result[0]['execution_status'] == 'not_claimed' and result[1]['status'] == 'completed'
