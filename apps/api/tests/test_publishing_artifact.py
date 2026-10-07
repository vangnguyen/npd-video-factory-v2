"""Real owned bytes; S3/QC/approval identities are explicitly mocked fixtures."""
import hashlib
import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.db import AssetORM
from app.object_storage import LocalObjectStorageProvider, S3ObjectStorageProvider
from app.publishing_artifact import ArtifactAdmissionError, BLOCK, PublishingArtifactGuard, VerifiedPublishingArtifact, bounded_copy, publishing_storage_config
from app.publishing_dispatch import DispatchError
from test_publishing_dispatch import fixture_stack


def blob(): return b'\x00\x00\x00\x20ftypisom' + bytes(range(256)) * 2300


def test_verified_ranges_are_exact_and_detect_same_size_changed_bytes(tmp_path):
    raw = blob(); path = tmp_path / 'owned.mp4'; path.write_bytes(raw)
    value = VerifiedPublishingArtifact(path, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_size=len(raw), binding_sha256='a' * 64)
    try:
        assert value.read(7, 600) == raw[7:607]
        assert value.read(BLOCK - 7, BLOCK + 19) == raw[BLOCK - 7:2 * BLOCK + 12]
        assert value.read(len(raw) - 11, 11) == raw[-11:]
        with path.open('r+b') as handle: handle.seek(31); handle.write(b'\xff')
        with pytest.raises(ArtifactAdmissionError, match='CHANGED'): value.read(0, 64)
    finally: value.close()
    with pytest.raises(ArtifactAdmissionError, match='CLOSED'): value.read(0, 1)


@pytest.mark.parametrize('offset,length', [(True, 1), (0, True), (-1, 1), (0, 0), (0, 16 * 1024 * 1024 + 1), (BLOCK, BLOCK * 8)])
def test_ranges_are_bounded_before_read(tmp_path, offset, length):
    raw = blob(); path = tmp_path / 'owned.mp4'; path.write_bytes(raw)
    value = VerifiedPublishingArtifact(path, expected_sha256=hashlib.sha256(raw).hexdigest(), expected_size=len(raw), binding_sha256='a' * 64)
    try:
        with pytest.raises(ArtifactAdmissionError, match='RANGE_INVALID'): value.read(offset, length)
    finally: value.close()


def test_wrong_hash_size_magic_and_linked_sources_are_refused(tmp_path):
    path = tmp_path / 'owned.mp4'; raw = blob(); path.write_bytes(raw)
    for checksum, size in (('0' * 64, len(raw)), (hashlib.sha256(raw).hexdigest(), len(raw) - 1)):
        with pytest.raises(ArtifactAdmissionError): VerifiedPublishingArtifact(path, expected_sha256=checksum, expected_size=size, binding_sha256='a' * 64)
    path.write_bytes(b'not-an-mp4')
    with pytest.raises(ArtifactAdmissionError, match='MP4_REQUIRED'):
        VerifiedPublishingArtifact(path, expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), expected_size=10, binding_sha256='a' * 64)
    hard = tmp_path / 'hard.mp4'; os.link(path, hard)
    with pytest.raises(ArtifactAdmissionError, match='PATH_INVALID'):
        VerifiedPublishingArtifact(hard, expected_sha256='a' * 64, expected_size=10, binding_sha256='a' * 64)


class Body(io.BytesIO):
    def __init__(self, raw): super().__init__(raw); self.read_sizes = []; self.did_close = False
    def read(self, size): self.read_sizes.append(size); return super().read(size)
    def close(self): self.did_close = True; super().close()


def fake_s3(raw, declared, *, retries=None):
    storage = object.__new__(S3ObjectStorageProvider); storage.bucket = 'fixture-bucket'
    body = Body(raw); calls = []
    def get_object(**kwargs): calls.append(kwargs); return {'ContentLength': declared, 'Body': body}
    storage.client = SimpleNamespace(get_object=get_object,
        meta=SimpleNamespace(config=SimpleNamespace(connect_timeout=5, read_timeout=30, retries=retries or {'total_max_attempts': 1})))
    return storage, body, calls


def test_s3_is_streamed_bounded_and_closed_with_exact_bytes(tmp_path):
    raw = blob(); storage, body, calls = fake_s3(raw, len(raw)); destination = tmp_path / 'private.mp4'
    bounded_copy(storage, 'workspaces/fixture/object.mp4', destination, len(raw))
    assert destination.read_bytes() == raw and body.did_close and max(body.read_sizes) <= BLOCK
    assert calls == [{'Bucket': 'fixture-bucket', 'Key': 'workspaces/fixture/object.mp4'}]
    storage, body, calls = fake_s3(raw + b'extra', len(raw))
    with pytest.raises(ArtifactAdmissionError, match='SIZE_MISMATCH'): bounded_copy(storage, 'fixture', tmp_path / 'oversized', len(raw))
    assert body.did_close


def test_s3_private_sdk_logging_is_scoped_and_does_not_hide_other_logs(tmp_path, caplog):
    import logging
    logger = logging.getLogger('botocore.endpoint'); raw = blob()
    storage, body, _calls = fake_s3(raw, len(raw))
    def get_object(**_kwargs):
        logger.warning('PRIVATE_SDK_SIGNATURE_FIXTURE')
        return {'ContentLength': len(raw), 'Body': body}
    storage.client.get_object = get_object
    with caplog.at_level(logging.WARNING):
        logger.warning('public_before_fixture')
        bounded_copy(storage, 'fixture', tmp_path / 'private-sdk.mp4', len(raw))
        logger.warning('public_after_fixture')
    assert 'PRIVATE_SDK_SIGNATURE_FIXTURE' not in caplog.text
    assert 'public_before_fixture' in caplog.text and 'public_after_fixture' in caplog.text


def test_s3_unknown_size_retries_and_read_timeouts_fail_closed(tmp_path):
    storage, body, calls = fake_s3(blob(), None)
    with pytest.raises(ArtifactAdmissionError, match='SIZE_MISMATCH'): bounded_copy(storage, 'fixture', tmp_path / 'missing', 10)
    assert body.did_close
    for retries in ({'total_max_attempts': 2}, {'max_attempts': 3}):
        storage, body, calls = fake_s3(blob(), 10, retries=retries)
        with pytest.raises(ArtifactAdmissionError, match='BOUNDED_CLIENT_REQUIRED'): bounded_copy(storage, 'fixture', tmp_path / 'retry', 10)
        assert calls == []
    storage, body, calls = fake_s3(blob(), 10); storage.client.meta.config.read_timeout = 60
    with pytest.raises(ArtifactAdmissionError, match='BOUNDED_CLIENT_REQUIRED'): bounded_copy(storage, 'fixture', tmp_path / 'timeout', 10)
    assert calls == []


def test_real_sdk_accepts_explicit_bounded_profile_without_any_request(tmp_path, monkeypatch):
    import boto3
    # Fresh session cannot consult an account/profile or instance credentials.
    monkeypatch.setenv('AWS_CONFIG_FILE', str(tmp_path / 'absent-config'))
    monkeypatch.setenv('AWS_SHARED_CREDENTIALS_FILE', str(tmp_path / 'absent-credentials'))
    monkeypatch.setenv('AWS_EC2_METADATA_DISABLED', 'true')
    session = boto3.session.Session()
    monkeypatch.setattr('app.object_storage.boto3.client', session.client)
    storage = S3ObjectStorageProvider(endpoint_url='https://explicit-s3-fixture.invalid', bucket='fixture', region='us-east-1',
        access_key='EXPLICIT_FIXTURE_ACCESS', secret_key='EXPLICIT_FIXTURE_SECRET', auto_create_bucket=False,
        request_config=publishing_storage_config())
    try:
        assert storage.client.meta.config.connect_timeout == 5 and storage.client.meta.config.read_timeout == 30
        assert storage.client.meta.config.retries['total_max_attempts'] == 1
    finally: storage.client.close()


@pytest.mark.parametrize('size', [0, -1, True, 512 * 1024 * 1024 + 1])
def test_copy_rejects_unbounded_sizes_before_storage_call(tmp_path, size):
    storage, body, calls = fake_s3(blob(), len(blob()))
    with pytest.raises(ArtifactAdmissionError, match='SIZE_MISMATCH'):
        bounded_copy(storage, 'fixture', tmp_path / 'unbounded', size)
    assert calls == []


async def configured(fixture, tmp_path):
    raw = blob(); path = tmp_path / 'explicit-placeholder-not-playable.mp4'; path.write_bytes(raw)
    storage = LocalObjectStorageProvider(tmp_path / 'admission-objects'); await storage.ensure_ready()
    parent = fixture['publication']; key = f'workspaces/{fixture["workspace"]}/projects/{parent.project_id}/publish-source/fixture.mp4'
    stored = await storage.put_file(object_key=key, path=path, content_type='video/mp4')
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, parent.output_asset_id)
            asset.object_key = key; asset.storage_provider = stored.storage_provider
            asset.size_bytes = stored.size_bytes; asset.checksum_sha256 = stored.checksum_sha256
    grant = await fixture['approve'](expected_artifact_sha256=stored.checksum_sha256)
    await fixture['journal'].prepare(fixture['workspace'], parent.publication_id, grant['publish_approval_id'])
    work = tmp_path / 'private-work'; work.mkdir()
    guard = PublishingArtifactGuard(fixture['journal'], storage, work)
    async def explicit_mock_qc(_path, **_kwargs): return {'status': 'passed', 'checksum_sha256': stored.checksum_sha256, 'mock_qc': True, 'publishing_blocked': True}
    guard.qc.inspect = explicit_mock_qc
    return raw, guard, work, storage, key


@pytest.mark.asyncio
async def test_guard_uses_private_copy_and_cleans_owned_only_with_fixture_qc(fixture_stack, tmp_path):
    fixture = fixture_stack; raw, guard, work, storage, key = await configured(fixture, tmp_path)
    source = storage.root / Path(key); source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    async with guard.open(fixture['workspace'], fixture['publication'].publication_id) as value:
        assert value.read(1, 123) == raw[1:124] and value.qc_report['mock_qc']
        assert len(list(work.iterdir())) == 1
    assert list(work.iterdir()) == [] and hashlib.sha256(source.read_bytes()).hexdigest() == source_hash


@pytest.mark.asyncio
async def test_foreign_storage_prefix_and_stale_grant_are_refused(fixture_stack, tmp_path):
    fixture = fixture_stack; _raw, guard, work, _storage, key = await configured(fixture, tmp_path)
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id)
            asset.object_key = 'workspaces/wsp_foreign_fixture/projects/prj_foreign/secret.mp4'
    with pytest.raises(ArtifactAdmissionError, match='STORAGE_SCOPE_INVALID'):
        async with guard.open(fixture['workspace'], fixture['publication'].publication_id): pass
    assert list(work.iterdir()) == []
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            asset = await session.get(AssetORM, fixture['publication'].output_asset_id); asset.object_key = key
    owner = fixture['verifier'].registry.tokens['explicit-owner']
    fixture['verifier'].registry.tokens['explicit-owner'] = owner.model_copy(update={'enabled': False})
    with pytest.raises(DispatchError, match='HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED'):
        async with guard.open(fixture['workspace'], fixture['publication'].publication_id): pass
    assert list(work.iterdir()) == []


@pytest.mark.asyncio
async def test_missing_qc_tool_is_fixed_private_error_and_cleans_snapshot(fixture_stack, tmp_path):
    fixture = fixture_stack; _raw, guard, work, _storage, _key = await configured(fixture, tmp_path)
    async def unavailable(_path, **_kwargs): raise OSError('PRIVATE_TOOL_PATH_FIXTURE')
    guard.qc.inspect = unavailable
    with pytest.raises(ArtifactAdmissionError, match='QC_TOOLS_NOT_CONFIGURED') as caught:
        async with guard.open(fixture['workspace'], fixture['publication'].publication_id): pass
    assert 'PRIVATE_TOOL_PATH_FIXTURE' not in str(caught.value) and list(work.iterdir()) == []


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_owned_thread_before_private_cleanup(fixture_stack, tmp_path, monkeypatch):
    import asyncio
    import threading
    import app.publishing_artifact as module
    fixture = fixture_stack; _raw, guard, work, _storage, _key = await configured(fixture, tmp_path)
    entered, release, ended = threading.Event(), threading.Event(), threading.Event()
    def slow_copy(_storage, _key, destination, _size, cancellation):
        assert destination.parent.exists(); entered.set()
        try:
            assert release.wait(10)
            assert cancellation.is_set() and destination.parent.exists()
        finally: ended.set()
    monkeypatch.setattr(module, 'bounded_copy', slow_copy)
    async def execute():
        async with guard.open(fixture['workspace'], fixture['publication'].publication_id):
            raise AssertionError('Cancelled download was admitted')
    task = asyncio.create_task(execute())
    try:
        assert await asyncio.to_thread(entered.wait, 10)
        task.cancel(); await asyncio.sleep(0); task.cancel(); await asyncio.sleep(0)
        assert not task.done() and len(list(work.iterdir())) == 1
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError): await task
    assert ended.is_set() and list(work.iterdir()) == []
