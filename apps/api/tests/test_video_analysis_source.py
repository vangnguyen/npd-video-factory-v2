"""Actual Local/SQLite/ASGI bytes and explicit saved-analysis fixtures.

The MP4 header fixture is not a decoded-video, ASR, scene quality, renderer or
Owner UAT result. Source playback and pure child copying make zero model calls.
"""
import asyncio
import copy
import hashlib
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import event, select

from app.auto_edit_db import AutoEditAnalysisORM, UploadSessionORM, TranscriptORM, SceneORM
from app.auto_edit_models import AutoEditAnalysisRequest
from app.auto_edit_providers import ProviderTranscript, ProviderSegment, require_positive_duration_transcript
from app.auto_edit_routes import router
from app.db import AssetORM, ProjectVersionORM, VideoProjectORM
from app.human_auth import authorize_human_request
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.sql_variant_models import canonical, digest, FamilyReserveRequest
from app.sql_variant_repository import SqlVariantFamilyRepository, record_value
from app.sql_variant_uploaded_repository import SqlUploadedDerivationRepository
from app.sql_variant_uploaded_copy import LocalEvidenceCopier
from app.sql_variant_derivation_service import SqlStoryboardDerivationService
from app.sql_variant_uploaded_models import DeriveUploadedRequest
from app.sql_variant_db import SqlVariantArtifactReceiptORM
from app.timeline_models import TimelineCreateRequest
from app.timeline_repository import TimelineRepository
from app.timeline_service import TimelineService, TimelineContractValidator
from app.media_intelligence_repository import MediaIntelligenceRepository
from app import source_asset_delivery as delivery
from app import video_analysis_source as playback
from auth_test_support import TEST_HUMAN_HEADERS, install_test_human_auth
from test_auto_edit_analysis import setup_services, upload_fixture, synthetic_mp4


class Poison:
    def __init__(self):
        self.calls = 0

    async def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError('Playback cannot dispatch analysis, ASR, signals or rendering')


async def immutable_rows(value):
    async with value.sessions() as session:
        return {model.__tablename__: canonical([record_value(row) for row in
            (await session.scalars(select(model).order_by(*model.__table__.primary_key.columns))).all()])
            for model in (VideoProjectORM, ProjectVersionORM, AssetORM, UploadSessionORM,
                AutoEditAnalysisORM, TranscriptORM, SceneORM)}


@pytest.fixture
async def source(tmp_path):
    engine, sessions, platform, repo, uploads, service, project, version = await setup_services(tmp_path)
    original_probe = uploads.media_probe
    class SilentHeaderSchemaFixture:
        async def probe(self, *args, **kwargs):
            metadata = await original_probe.probe(*args, **kwargs)
            return metadata.model_copy(update={'audio_codec': None, 'audio_channels': None, 'audio_sample_rate': None})
    uploads.media_probe = SilentHeaderSchemaFixture()
    data = synthetic_mp4(4096)
    completed = await upload_fixture(uploads, project, version, data)
    asset = await repo.get_asset(completed.asset_id)
    aid, created = await repo.create_analysis(project_id=project.project_id, asset=asset,
        fingerprint='7'*64, configuration=AutoEditAnalysisRequest(asset_id=asset.asset_id),
        source_media=completed.media_metadata, provenance={'explicit_saved_schema_fixture': True,
            'source_asset_checksum': asset.checksum_sha256, 'provider_calls': 0, 'human_accepted': False})
    assert created
    await repo.save_analysis_results(analysis_id=aid, asset_id=asset.asset_id, provider_key='fixture-saved-signals',
        transcript=None, scenes=[dict(ordinal=0, start_seconds=0., end_seconds=16.,
            semantic_label='Explicit SQL fixture', description='No scene inference or Vision claim.',
            subjects=[], quality_score=0., motion_score=0., speech_score=0., confidence=0.,
            evidence={'fixture': True, 'provider_calls': 0})], silence_decisions=[], highlights=[],
        signal_evidence={'fixture': True})
    poisons = [Poison() for _ in range(5)]
    service.prepare, service.analyze, service.get = poisons[:3]
    service.transcription_provider.transcribe, service.signal_provider.analyze = poisons[3:]
    app = FastAPI()
    app.include_router(router, dependencies=[Depends(authorize_human_request)])
    app.state.auto_edit_analysis_service = service
    install_test_human_auth(app, platform_repository=platform, platform_role=None,
        workspace_roles={project.workspace_id: 'viewer'})
    downloads = []
    original_download = service.object_storage.download_file

    async def observed_download(**kwargs):
        downloads.append(kwargs['destination'])
        await original_download(**kwargs)

    service.object_storage.download_file = observed_download
    selects = {'asset': 0, 'analysis': 0}

    def before_cursor(_, __, statement, ___, ____, _____):
        lower = statement.lower()
        selects['asset'] += int('from assets' in lower)
        selects['analysis'] += int('from auto_edit_analyses' in lower)

    event.listen(engine.sync_engine, 'before_cursor_execute', before_cursor)
    value = SimpleNamespace(app=app, engine=engine, sessions=sessions, platform=platform,
        repo=repo, uploads=uploads, service=service, storage=service.object_storage,
        project=project, version=version, asset=asset, analysis_id=aid, data=data,
        downloads=downloads, selects=selects, poisons=poisons, tmp=tmp_path,
        original_download=original_download)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-fixture',
        headers=TEST_HUMAN_HEADERS) as client:
        value.client = client
        yield value
    assert all(poison.calls == 0 for poison in poisons)
    assert not service.staging_root.exists() or not list(service.staging_root.iterdir())
    event.remove(engine.sync_engine, 'before_cursor_execute', before_cursor)
    await engine.dispose()


def url(value, project=None, analysis=None):
    return f'/api/v1/projects/{project or value.project.project_id}/analyses/{analysis or value.analysis_id}/source'


def code(response):
    return response.json()['detail']['code']


def track_owned(monkeypatch):
    created = []
    original = delivery.OwnedSourceResponse

    class Observed(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            created.append(self)

    monkeypatch.setattr(delivery, 'OwnedSourceResponse', Observed)
    return created


@pytest.mark.asyncio
async def test_viewer_full_get_head_range_if_range_preserves_exact_source_and_sql(source):
    before = await immutable_rows(source)
    response = await source.client.get(url(source))
    assert response.status_code == 200 and response.content == source.data
    assert hashlib.sha256(response.content).hexdigest() == source.asset.checksum_sha256
    assert response.headers['content-type'] == 'video/mp4'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    etag = '"sha256-'+source.asset.checksum_sha256+'"'
    assert response.headers['etag'] == etag
    head = await source.client.head(url(source))
    assert head.status_code == 200 and head.content == b''
    assert head.headers['content-length'] == str(len(source.data))
    for method in ('GET', 'HEAD'):
        ranged = await source.client.request(method, url(source), headers={'Range': 'bytes=16-35', 'If-Range': etag})
        assert ranged.status_code == 206 and ranged.headers['content-range'] == 'bytes 16-35/4096'
        assert ranged.headers['content-length'] == '20'
        assert ranged.content == (source.data[16:36] if method == 'GET' else b'')
    stale = await source.client.get(url(source), headers={'Range': 'bytes=0-3', 'If-Range': '"old"'})
    assert stale.status_code == 200 and stale.content == source.data
    assert await immutable_rows(source) == before


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['unauthenticated', 'foreign-workspace', 'api-disabled', 'missing-project'])
async def test_auth_and_scope_deny_before_analysis_asset_or_staging(source, mode):
    path = url(source)
    headers = dict(TEST_HUMAN_HEADERS)
    if mode == 'unauthenticated':
        headers['Authorization'] = 'Bearer invalid-explicit-fixture'
    elif mode == 'foreign-workspace':
        other = await source.platform.create_workspace(WorkspaceCreate(slug='foreign-video', name='Fixture', owner_ref='fixture'))
        project = await source.platform.create_project(other.workspace_id, ProjectCreate(slug='foreign', name='Fixture'))
        path = url(source, project=project.project_id)
    elif mode == 'api-disabled':
        source.app.state.human_api_enabled = False
    else:
        path = url(source, project='prj_missing_explicit_fixture')
    source.selects.update(asset=0, analysis=0)
    response = await source.client.get(path, headers=headers)
    assert response.status_code == {'unauthenticated': 401, 'api-disabled': 503}.get(mode, 404)
    assert response.headers['cache-control'] == 'no-store'
    assert source.selects == {'asset': 0, 'analysis': 0} and not source.downloads
    assert not source.service.staging_root.exists()


@pytest.mark.asyncio
async def test_foreign_or_missing_analysis_never_reads_asset(source):
    another = await source.platform.create_project(source.project.workspace_id, ProjectCreate(slug='other-video', name='Fixture'))
    for path in (url(source, analysis='ana_missing_fixture'), url(source, project=another.project_id)):
        source.selects.update(asset=0, analysis=0)
        response = await source.client.get(path)
        assert response.status_code == 404 and response.headers['cache-control'] == 'no-store'
        assert source.selects['asset'] == 0 and not source.downloads


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['pending', 'failed', 'checksum', 'configuration', 'media', 'untrusted', 'upload-hash', 'foreign-version'])
async def test_analysis_intake_and_clock_bindings_reject_before_bytes(source, mutation):
    async with source.sessions() as session, session.begin():
        row = await session.get(AutoEditAnalysisORM, source.analysis_id)
        upload = await session.get(UploadSessionORM, source.asset.provenance['source_reference'])
        if mutation in {'pending', 'failed'}:
            row.status = mutation
        elif mutation == 'checksum':
            row.provenance_json = {**row.provenance_json, 'source_asset_checksum': '0'*64}
        elif mutation == 'configuration':
            row.configuration_json = {**row.configuration_json, 'asset_id': 'ast_foreign_fixture'}
        elif mutation == 'media':
            row.source_media_json = {**row.source_media_json, 'duration_seconds': 15.9}
        elif mutation == 'untrusted':
            upload.quarantine_state = 'pending'
        elif mutation == 'upload-hash':
            upload.scan_checksum_sha256 = '0'*64
        elif mutation == 'foreign-version':
            other = await source.platform.create_project(source.project.workspace_id, ProjectCreate(slug='foreign-version', name='Fixture'))
            version = await source.platform.ensure_initial_version(other.project_id, snapshot={'fixture': True})
            row.project_version_id = version.project_version_id
    response = await source.client.get(url(source))
    assert response.status_code == 409 and response.headers['cache-control'] == 'no-store'
    assert code(response) in {'VIDEO_SOURCE_ANALYSIS_NOT_SUCCEEDED', 'VIDEO_SOURCE_ANALYSIS_BINDING_CHANGED', 'VIDEO_SOURCE_CUSTODY_INVALID'}
    assert not source.downloads and not source.service.staging_root.exists()


@pytest.mark.asyncio
async def test_invalid_range_and_query_never_download_or_stage(source):
    response = await source.client.get(url(source), headers={'Range': 'bytes=1-2,4-5'})
    assert response.status_code == 416 and response.headers['content-range'] == 'bytes */4096'
    assert response.headers['cache-control'] == 'no-store'
    queried = await source.client.get(url(source)+'?path=forbidden-fixture')
    assert queried.status_code == 422 and code(queried) == 'VIDEO_SOURCE_QUERY_NOT_SUPPORTED'
    assert not source.downloads and not source.service.staging_root.exists()


@pytest.mark.asyncio
async def test_existing_auth_dependency_counts_once_and_writes_off_still_allows_viewer(source):
    source.app.state.human_write_enabled = False
    response = await source.client.get(url(source))
    assert response.status_code == 200
    assert sum(source.app.state.human_rate_limiter.store.counts.values()) == 1
    before = await immutable_rows(source)
    denied = await source.client.post(url(source), content=b'explicit unsupported mutation')
    assert denied.status_code == 405 and await immutable_rows(source) == before


@pytest.mark.asyncio
async def test_saved_transcript_edit_does_not_replace_original_video_clock_or_bytes(source):
    from app.transcript_editing import edit_transcript
    from app.auto_edit_models import TranscriptEditRequest
    # Explicit saved-schema transcription only; there is no ASR invocation.
    from app.auto_edit_models import MediaMetadata
    aid, _ = await source.repo.create_analysis(project_id=source.project.project_id, asset=source.asset,
        fingerprint='9'*64, configuration=AutoEditAnalysisRequest(asset_id=source.asset.asset_id),
        source_media=MediaMetadata.model_validate(source.asset.provenance['media_metadata']),
        provenance={'explicit_saved_schema_fixture': True, 'source_asset_checksum': source.asset.checksum_sha256,
            'provider_calls': 0})
    transcript = require_positive_duration_transcript(ProviderTranscript(language='vi', confidence=None,
        segments=(ProviderSegment(.125, 1.375, 'Chữ fixture gốc.', None, None, ()),),
        provenance={'explicit_schema_fixture': True, 'provider_calls': 0}))
    await source.repo.save_analysis_results(analysis_id=aid, asset_id=source.asset.asset_id,
        provider_key='explicit-saved-transcript-fixture', transcript=transcript,
        scenes=[], silence_decisions=[], highlights=[])
    current = await source.repo.get_analysis(aid)
    original = current.transcript.model_dump(mode='json')
    payload = TranscriptEditRequest(expected_version=1, base_transcript_id=current.transcript.transcript_id,
        segments=[{'segment_id': current.transcript.segments[0].segment_id, 'text': 'Chữ fixture sửa tay.'}])
    updated = await edit_transcript(source.repo, source.project.project_id, aid, payload, 'fixture-editor')
    assert updated.transcript.version == 2
    response = await source.client.get(url(source, analysis=aid))
    assert response.status_code == 200 and response.content == source.data
    preserved = await source.repo.get_analysis(aid, transcript_id=original['transcript_id'])
    assert preserved.transcript.model_dump(mode='json') == original
    assert updated.source_media == preserved.source_media
    assert (await source.repo.get_asset(source.asset.asset_id)).checksum_sha256 == source.asset.checksum_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['hash', 'size', 'magic'])
async def test_original_bytes_must_match_size_sha_and_magic_without_private_error(source, mode):
    path = source.storage._path(source.asset.object_key)
    raw = source.data[:-1] if mode == 'size' else source.data[:-1]+b'Z'
    if mode == 'magic':
        raw = b'not-video-'+source.data[10:]
        sha = hashlib.sha256(raw).hexdigest()
        async with source.sessions() as session, session.begin():
            asset = await session.get(AssetORM, source.asset.asset_id)
            asset.checksum_sha256 = sha
            upload = await session.get(UploadSessionORM, source.asset.provenance['source_reference'])
            upload.scan_checksum_sha256 = sha
            analysis = await session.get(AutoEditAnalysisORM, source.analysis_id)
            analysis.provenance_json = {**analysis.provenance_json, 'source_asset_checksum': sha}
    path.write_bytes(raw)
    response = await source.client.get(url(source))
    assert response.status_code == 409
    assert code(response) == {'hash': 'SOURCE_ASSET_CHECKSUM_CHANGED', 'size': 'SOURCE_ASSET_SIZE_CHANGED', 'magic': 'SOURCE_ASSET_MIME_CHANGED'}[mode]
    assert str(source.tmp) not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['analysis', 'asset', 'upload', 'trust-stamp', 'project', 'storage', 'session',
    'service', 'repository', 'staging', 'api-disabled'])
async def test_actual_post_download_custody_changes_close_response_before_handoff(source, monkeypatch, mutation):
    owned = track_owned(monkeypatch)
    async def changed_download(**kwargs):
        await source.original_download(**kwargs)
        if mutation == 'storage':
            source.storage.root = source.tmp/'other-root'
        elif mutation == 'service':
            source.app.state.auto_edit_analysis_service = object()
        elif mutation == 'repository':
            source.service.repository = SimpleNamespace(session_factory=source.sessions)
        elif mutation == 'staging':
            source.service.staging_root = source.tmp/'other-staging'
        elif mutation == 'api-disabled':
            source.app.state.human_api_enabled = False
        elif mutation == 'session':
            registry = source.app.state.human_auth_verifier.registry
            registry.tokens['test-owner'] = registry.tokens['test-owner'].model_copy(update={'enabled': False})
        else:
            async with source.sessions() as session, session.begin():
                if mutation == 'analysis':
                    row = await session.get(AutoEditAnalysisORM, source.analysis_id)
                    row.fingerprint = '8'*64
                elif mutation == 'asset':
                    row = await session.get(AssetORM, source.asset.asset_id)
                    row.version += 1
                elif mutation == 'upload':
                    row = await session.get(UploadSessionORM, source.asset.provenance['source_reference'])
                    row.status = 'completed_duplicate'
                elif mutation == 'trust-stamp':
                    from datetime import timedelta
                    row = await session.get(UploadSessionORM, source.asset.provenance['source_reference'])
                    row.trusted_at += timedelta(seconds=1)
                elif mutation == 'project':
                    row = await session.get(VideoProjectORM, source.project.project_id)
                    row.version += 1
    source.storage.download_file = changed_download
    response = await source.client.get(url(source))
    assert response.status_code == (401 if mutation == 'session' else 409)
    assert owned and all(item._closed and item._handle.closed for item in owned)
    assert not list((source.tmp/'analysis').iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['service', 'storage', 'session', 'principal'])
async def test_initial_sql_await_runtime_drift_refuses_before_byte_admission(source, monkeypatch, mutation):
    original = playback.source_snapshot
    async def changed_snapshot(*args, **kwargs):
        result = await original(*args, **kwargs)
        if mutation == 'service':
            source.app.state.auto_edit_analysis_service = object()
        elif mutation == 'storage':
            source.storage._download_root = source.tmp/'foreign-source-root'
        elif mutation == 'session':
            registry = source.app.state.human_auth_verifier.registry
            registry.tokens['test-owner'] = registry.tokens['test-owner'].model_copy(update={'enabled': False})
        else:
            kwargs['principal'].workspace_roles[source.project.workspace_id] = 'editor'
        return result
    monkeypatch.setattr(playback, 'source_snapshot', changed_snapshot)
    response = await source.client.get(url(source))
    assert response.status_code == (401 if mutation == 'session' else 409)
    assert not source.downloads and not source.service.staging_root.exists()


@pytest.mark.asyncio
async def test_repeated_request_cancel_drains_delivery_and_closes_owned_result(source, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    owned = track_owned(monkeypatch)
    async def paused_download(**kwargs):
        entered.set()
        await release.wait()
        await source.original_download(**kwargs)
    source.storage.download_file = paused_download
    task = asyncio.create_task(source.client.get(url(source)))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    await asyncio.sleep(.02)
    assert not task.done()
    task.cancel()
    await asyncio.sleep(.02)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 3)
    assert owned and all(item._closed and item._handle.closed for item in owned)
    assert not list(source.service.staging_root.iterdir())


@pytest.mark.asyncio
async def test_cancel_during_final_sql_snapshot_closes_verified_response(source, monkeypatch):
    entered, release = asyncio.Event(), asyncio.Event()
    original, calls = playback.source_snapshot, 0
    owned = track_owned(monkeypatch)
    async def paused_snapshot(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            entered.set()
            await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(playback, 'source_snapshot', paused_snapshot)
    task = asyncio.create_task(source.client.get(url(source)))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert owned and all(item._closed and item._handle.closed for item in owned)
    assert not list(source.service.staging_root.iterdir())


async def derived_child(source, *, member_index=0, family=None):
    from pathlib import Path
    if family is None:
        timeline = TimelineService(repository=TimelineRepository(source.sessions), platform=source.platform,
            auto_edit_repository=source.repo, media_repository=MediaIntelligenceRepository(source.sessions),
            object_storage=source.storage,
            validator=TimelineContractValidator(Path(__file__).resolve().parents[3]/'packages/contracts/timeline.schema.json'))
        await timeline.create(source.project.project_id, TimelineCreateRequest(analysis_id=source.analysis_id))
        families = SqlVariantFamilyRepository(source.sessions)
        available = await families.availability(source.project.workspace_id, source.project.project_id)
        family, _ = await families.reserve(source.project.workspace_id, source.project.project_id,
            FamilyReserveRequest(expected_project_version=available.binding.project_version,
                expected_timeline_version=available.binding.timeline_version,
                expected_timeline_version_id=available.binding.timeline_version_id,
                expected_binding_sha256=available.binding_sha256, catalog_ref=available.catalog.catalog_ref,
                catalog_sha256=available.catalog_sha256, profile_refs=[p.profile_ref for p in available.catalog.profiles],
                request_key='explicit-playback-family-fixture', acknowledge_draft_derivation=True), actor_ref='fixture-editor')
    else:
        families = SqlVariantFamilyRepository(source.sessions)
        family = await families.get(source.project.workspace_id, source.project.project_id, family.family_id)
    service = SqlStoryboardDerivationService(SqlUploadedDerivationRepository(families), LocalEvidenceCopier(source.storage))
    receipt, replayed = await service.derive(source.project.workspace_id, source.project.project_id, family.family_id,
        DeriveUploadedRequest(expected_version=family.version, expected_snapshot_sha256=family.snapshot_sha256,
            member_id=family.members[member_index].member_id, request_key=f'explicit-playback-child-{member_index}',
            acknowledge_unapproved_child=True), actor_ref='fixture-editor')
    assert receipt.state == 'ready' and not replayed and receipt.safety.provider_calls == 0
    return receipt, family


@pytest.mark.asyncio
async def test_actual_child_typed_receipt_source_plays_without_fake_upload_or_approval(source):
    receipt, _ = await derived_child(source)
    child = receipt.result['child_project_id']
    aid = receipt.result['identity_map'][source.analysis_id]
    before = await immutable_rows(source)
    response = await source.client.get(url(source, project=child, analysis=aid))
    assert response.status_code == 200 and response.content == source.data
    assert await immutable_rows(source) == before
    async with source.sessions() as session:
        uploads = (await session.scalars(select(UploadSessionORM))).all()
        assert len(uploads) == 1 and uploads[0].project_id == source.project.project_id
        asset = await session.get(AssetORM, receipt.result['asset_map'][source.asset.asset_id])
        assert asset.provenance['source_type'] == 'verified_variant_derivative'
        assert asset.provenance['approval_inherited'] is False and asset.provenance['rights_status'] == 'unknown'


@pytest.mark.asyncio
@pytest.mark.parametrize('mode', ['rehash-before', 'foreign-receipt', 'rehash-after-download'])
async def test_derivative_receipt_relation_is_verified_before_and_after_delivery(source, monkeypatch, mode):
    receipt, family = await derived_child(source)
    child, aid = receipt.result['child_project_id'], receipt.result['identity_map'][source.analysis_id]
    owned = track_owned(monkeypatch)
    async def corrupt():
        async with source.sessions() as session, session.begin():
            row = await session.get(SqlVariantArtifactReceiptORM, receipt.receipt_id)
            result = copy.deepcopy(row.result_json)
            result['asset_map'][source.asset.asset_id] = 'ast_foreign_rehashed_fixture'
            row.result_json, row.result_sha256 = result, digest(result)
    if mode == 'foreign-receipt':
        other, _ = await derived_child(source, member_index=1, family=family)
        async with source.sessions() as session, session.begin():
            asset = await session.get(AssetORM, receipt.result['asset_map'][source.asset.asset_id])
            asset.provenance = {**asset.provenance, 'derivation_receipt_id': other.receipt_id}
    elif mode == 'rehash-before':
        await corrupt()
    else:
        async def changed(**kwargs):
            await source.original_download(**kwargs)
            await corrupt()
        source.storage.download_file = changed
    response = await source.client.get(url(source, project=child, analysis=aid))
    assert response.status_code == 409 and code(response) == 'VIDEO_SOURCE_CUSTODY_INVALID'
    if mode == 'rehash-after-download':
        assert owned and all(item._closed and item._handle.closed for item in owned)
        assert not list(source.service.staging_root.iterdir())
    else:
        assert not source.downloads
