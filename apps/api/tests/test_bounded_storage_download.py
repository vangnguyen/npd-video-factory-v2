"""Actual owned files and explicit fake SDK streams; no network/credentials."""
import asyncio
import hashlib
import io
import logging
import os
from pathlib import Path
import subprocess
import threading
from types import SimpleNamespace

from botocore.exceptions import ClientError, EndpointConnectionError
import pytest
from test_source_asset_delivery import fixture as source_fixture

import app.bounded_storage_download as bounded
import app.object_storage as storage

KEY = 'workspaces/wsp_fixture/projects/prj_fixture/source/voice.wav'
PREFIX = 'workspaces/wsp_fixture/projects/prj_fixture/'


class Body(io.BytesIO):
    def __init__(self, value):
        super().__init__(value)
        self.requests = []

    def read(self, size=-1):
        self.requests.append(size)
        return super().read(size)


def fake_s3(body, *, length, config=None):
    calls = []
    def get_object(**kwargs):
        calls.append(kwargs)
        return {'Body': body, 'ContentLength': length}
    def denied_legacy(*args, **kwargs):
        raise AssertionError('Constrained requests never fall back to an unbounded SDK call')
    provider = object.__new__(storage.S3ObjectStorageProvider)
    provider.bucket = 'explicit-fixture-only'
    provider.client = SimpleNamespace(get_object=get_object, download_file=denied_legacy,
        meta=SimpleNamespace(config=config or storage.bounded_download_request_config()))
    return provider, calls


async def local_object(tmp_path, raw=b'actual owned local bytes'):
    provider = storage.LocalObjectStorageProvider(tmp_path / 'objects')
    await provider.ensure_ready()
    source = tmp_path / 'original.wav'
    source.write_bytes(raw)
    saved = await provider.put_file(object_key=KEY, path=source)
    return provider, source, saved


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['local', 's3'])
async def test_actual_exact_bytes_atomic_target_and_short_private_stage(tmp_path, kind):
    raw = b'EXPLICIT OWNED AUDIO BYTES\0' * 30000
    destination = tmp_path / ('z' * 251 + '.wav')
    destination_io = storage.filesystem_path(destination)
    destination_io.write_bytes(b'prior')
    unrelated = tmp_path / '.unrelated.tmp'
    unrelated.write_bytes(b'keep')
    if kind == 'local':
        provider, original, saved = await local_object(tmp_path, raw)
    else:
        body = Body(raw)
        provider, calls = fake_s3(body, length=len(raw))
    await provider.download_file(object_key=KEY, destination=destination, max_bytes=len(raw),
        expected_size_bytes=len(raw), expected_sha256=hashlib.sha256(raw).hexdigest(), expected_prefix=PREFIX)
    assert destination_io.read_bytes() == raw and unrelated.read_bytes() == b'keep'
    assert not list(tmp_path.glob('.vf-object-*.tmp'))
    if kind == 'local':
        assert original.read_bytes() == raw
    else:
        assert body.closed and all(0 < size <= bounded.BLOCK_BYTES for size in body.requests)
        assert calls == [{'Bucket': 'explicit-fixture-only', 'Key': KEY}]


@pytest.mark.asyncio
@pytest.mark.parametrize('kwargs', [
    {'max_bytes': True}, {'max_bytes': 0}, {'max_bytes': 1.5}, {'expected_size_bytes': False},
    {'expected_size_bytes': -1}, {'expected_size_bytes': 11, 'max_bytes': 10},
    {'expected_sha256': 'private-input-in-error'}, {'expected_sha256': 'A' * 64},
    {'expected_prefix': 'workspaces/wsp_fixture/projects/prj_other/'},
    {'expected_prefix': 'workspaces/wsp_fixture/projects/prj_fixture_extra/'},
    {'expected_prefix': PREFIX + '../'}, {'expected_prefix': '/'},
])
async def test_invalid_admission_and_component_prefix_reject_before_wire_or_destination(tmp_path, kwargs):
    body = Body(b'payload')
    provider, calls = fake_s3(body, length=7)
    with pytest.raises((bounded.StorageDownloadError, ValueError)) as error:
        await provider.download_file(object_key=KEY, destination=tmp_path / 'absent' / 'target', **kwargs)
    assert not calls and not (tmp_path / 'absent').exists()
    assert 'private-input' not in str(error.value) and not body.requests


@pytest.mark.asyncio
@pytest.mark.parametrize('config', [
    SimpleNamespace(connect_timeout=60, read_timeout=30, retries={'total_max_attempts': 1}),
    SimpleNamespace(connect_timeout=5, read_timeout=60, retries={'total_max_attempts': 1}),
    SimpleNamespace(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': 2}),
    SimpleNamespace(connect_timeout=True, read_timeout=30, retries={'total_max_attempts': 1}),
    SimpleNamespace(connect_timeout=5, read_timeout=30, retries={'total_max_attempts': True}),
])
async def test_sdk_without_finite_profile_cannot_wire_or_silently_fallback(tmp_path, config):
    body = Body(b'payload')
    provider, calls = fake_s3(body, length=7, config=config)
    with pytest.raises(bounded.StorageDownloadError, match='SDK_PROFILE_REQUIRED'):
        await provider.download_file(object_key=KEY, destination=tmp_path / 'target', max_bytes=7)
    assert calls == [] and not (tmp_path / 'target').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('raw,length,kwargs,code', [
    (b'a' * 11, 11, {'max_bytes': 10}, 'SIZE_LIMIT'),
    (b'a' * 11, 10, {'max_bytes': 10}, 'SIZE_LIMIT'),
    (b'a' * 10, 9, {'max_bytes': 20}, 'SIZE_MISMATCH'),
    (b'a' * 9, 10, {'expected_size_bytes': 10}, 'SIZE_MISMATCH'),
    (b'a' * 9, None, {'max_bytes': 10}, 'STREAM_INVALID'),
    (b'a' * 9, True, {'max_bytes': 10}, 'STREAM_INVALID'),
    (b'a' * 9, 9, {'expected_sha256': 'a' * 64}, 'HASH_MISMATCH'),
])
async def test_advertised_and_actual_bytes_hash_fail_closed_keep_old_target(tmp_path, raw, length, kwargs, code):
    body = Body(raw)
    provider, calls = fake_s3(body, length=length)
    target = tmp_path / 'target'
    target.write_bytes(b'prior target')
    unrelated = tmp_path / '.unrelated.tmp'
    unrelated.write_bytes(b'keep')
    with pytest.raises(bounded.StorageDownloadError, match=code):
        await provider.download_file(object_key=KEY, destination=target, **kwargs)
    assert target.read_bytes() == b'prior target' and unrelated.read_bytes() == b'keep'
    assert body.closed and len(calls) == 1 and not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
async def test_local_size_and_sha_are_measured_from_descriptor_not_extension(tmp_path):
    provider, original, saved = await local_object(tmp_path)
    target = tmp_path / 'target'
    target.write_bytes(b'prior')
    for kwargs, code in [({'max_bytes': saved.size_bytes - 1}, 'SIZE_LIMIT'),
                         ({'expected_size_bytes': saved.size_bytes + 1}, 'SIZE_MISMATCH'),
                         ({'expected_sha256': 'f' * 64}, 'HASH_MISMATCH')]:
        with pytest.raises(bounded.StorageDownloadError, match=code):
            await provider.download_file(object_key=KEY, destination=target, **kwargs)
        assert target.read_bytes() == b'prior' and not list(tmp_path.glob('.vf-object-*.tmp'))
    assert original.read_bytes() == b'actual owned local bytes'


@pytest.mark.asyncio
async def test_zero_byte_object_has_exact_size_and_sha_without_invented_nonzero_size(tmp_path):
    provider, calls = fake_s3(Body(b''), length=0)
    target = tmp_path / 'empty'
    await provider.download_file(object_key=KEY, destination=target,
        expected_size_bytes=0, expected_sha256=hashlib.sha256(b'').hexdigest())
    assert target.read_bytes() == b'' and len(calls) == 1


@pytest.mark.asyncio
async def test_sdk_missing_object_has_bounded_code_without_private_error_message(tmp_path):
    provider, calls = fake_s3(Body(b''), length=0)
    def missing(**kwargs):
        raise ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'private-object-path-secret'}}, 'GetObject')
    provider.client.get_object = missing
    with pytest.raises(FileNotFoundError, match='NOT_FOUND') as error:
        await provider.download_file(object_key=KEY, destination=tmp_path / 'target', max_bytes=10)
    assert isinstance(error.value, bounded.StorageDownloadError)
    assert 'private-object' not in str(error.value) and not (tmp_path / 'target').exists()


@pytest.mark.asyncio
@pytest.mark.parametrize('constrained', [False, True])
async def test_local_missing_source_preserves_public_error_type_without_private_object_key(tmp_path, constrained):
    provider = storage.LocalObjectStorageProvider(tmp_path / 'objects')
    await provider.ensure_ready()
    kwargs = {'max_bytes': 100} if constrained else {}
    with pytest.raises(FileNotFoundError) as error:
        await provider.download_file(object_key=KEY, destination=tmp_path / 'target', **kwargs)
    assert isinstance(error.value, bounded.StorageDownloadError) and str(error.value) == 'STORAGE_DOWNLOAD_NOT_FOUND'
    assert KEY not in str(error.value) and str(tmp_path) not in str(error.value)
    assert not (tmp_path / 'target').exists() and not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['local', 's3', 'legacy_s3'])
async def test_actual_source_delivery_missing_object_remains_404_and_cleans_stage(source_fixture, kind):
    import httpx
    from fastapi import FastAPI, Request
    from app.source_asset_delivery import deliver_source_asset
    client, state, staging, data, local_store = source_fixture
    asset = state['asset'].model_copy(update={'object_key': KEY + '.absent'})
    if kind == 'local':
        provider = local_store
    else:
        asset = asset.model_copy(update={'storage_provider': 's3'})
        provider, calls = fake_s3(Body(b''), length=0)
        def missing(*args, **kwargs):
            raise ClientError({'Error': {'Code': 'NoSuchKey', 'Message': 'private-sdk-error-key'}}, 'GetObject')
        provider.client.get_object = missing
        provider.client.download_file = missing
        if kind == 's3':
            delegate = provider
            class ConstrainedFixture:
                name = 's3'
                async def download_file(self, *, object_key, destination):
                    await delegate.download_file(object_key=object_key, destination=destination,
                        max_bytes=asset.size_bytes, expected_size_bytes=asset.size_bytes,
                        expected_sha256=asset.checksum_sha256)
            provider = ConstrainedFixture()
    app = FastAPI()
    @app.get('/owned-source-contract')
    async def route(request: Request):
        return await deliver_source_asset(request, asset=asset, object_storage=provider, staging_root=staging)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-fixture') as actual_client:
        response = await actual_client.get('/owned-source-contract')
    assert response.status_code == 404 and response.json()['detail']['code'] == 'SOURCE_OBJECT_NOT_FOUND'
    assert 'private-sdk' not in response.text and asset.object_key not in response.text and str(staging) not in response.text
    assert not list(staging.iterdir()) and local_store._path(state['asset'].object_key).read_bytes() == data


@pytest.mark.asyncio
async def test_non_missing_failures_are_not_misclassified_as_file_not_found(tmp_path):
    provider, original, saved = await local_object(tmp_path)
    for kwargs in ({'max_bytes': 1}, {'expected_sha256': 'f' * 64}):
        with pytest.raises(bounded.StorageDownloadError) as error:
            await provider.download_file(object_key=KEY, destination=tmp_path / 'target', **kwargs)
        assert not isinstance(error.value, FileNotFoundError)
    source, calls = fake_s3(Body(b''), length=0)
    def no_bucket(**kwargs):
        raise ClientError({'Error': {'Code': 'NoSuchBucket', 'Message': 'private-sdk-error-key'}}, 'GetObject')
    source.client.get_object = no_bucket
    with pytest.raises(bounded.StorageDownloadError) as error:
        await source.download_file(object_key=KEY, destination=tmp_path / 'target', max_bytes=100)
    assert not isinstance(error.value, FileNotFoundError) and str(error.value) == 'STORAGE_DOWNLOAD_READ_FAILED'


@pytest.mark.asyncio
async def test_stream_ignoring_requested_block_cannot_write_oversized_chunk(tmp_path):
    class InvalidBody(Body):
        def read(self, size=-1):
            return b'a' * (size + 1)
    body = InvalidBody(b'')
    provider, calls = fake_s3(body, length=10)
    target = tmp_path / 'target'; target.write_bytes(b'prior')
    with pytest.raises(bounded.StorageDownloadError, match='STREAM_INVALID'):
        await provider.download_file(object_key=KEY, destination=target, max_bytes=10)
    assert body.closed and target.read_bytes() == b'prior' and not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
async def test_parallel_verified_downloads_use_distinct_stages_and_complete_destination(tmp_path):
    raw_a, raw_b = b'a' * 300000, b'b' * 300000
    first, calls_a = fake_s3(Body(raw_a), length=len(raw_a))
    second, calls_b = fake_s3(Body(raw_b), length=len(raw_b))
    target = tmp_path / 'new' / 'nested' / 'target'
    await asyncio.gather(*(provider.download_file(object_key=KEY, destination=target,
        expected_size_bytes=len(raw), expected_sha256=hashlib.sha256(raw).hexdigest())
        for provider, raw in [(first, raw_a), (second, raw_b)]))
    assert target.read_bytes() in {raw_a, raw_b} and len(calls_a) == len(calls_b) == 1
    assert not list(target.parent.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
async def test_actual_oversize_stream_never_writes_beyond_limit(tmp_path):
    limit = bounded.BLOCK_BYTES + 8
    raw = b'a' * (limit + 1)
    class ObservedBody(Body):
        def read(self, size=-1):
            for path in tmp_path.glob('.vf-object-*.tmp'):
                assert path.stat().st_size <= limit
            return super().read(size)
    body = ObservedBody(raw)
    provider, calls = fake_s3(body, length=limit)
    target = tmp_path / 'target'
    target.write_bytes(b'prior')
    with pytest.raises(bounded.StorageDownloadError, match='SIZE_LIMIT'):
        await provider.download_file(object_key=KEY, destination=target, max_bytes=limit)
    assert body.requests == [bounded.BLOCK_BYTES, 9]
    assert target.read_bytes() == b'prior' and body.closed and not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['client', 'endpoint', 'stream', 'timeout'])
async def test_sdk_and_stream_errors_are_bounded_and_private(tmp_path, caplog, monkeypatch, failure):
    private = 'SECRET_TOKEN/private-user-content/object-key/endpoint.invalid'
    class FailedBody(Body):
        def read(self, size=-1):
            logging.getLogger('botocore.new.download.child').error(private)
            if failure == 'stream':
                raise EndpointConnectionError(endpoint_url=private)
            if failure == 'timeout':
                # The deadline was frozen before I/O; move the clock beyond it.
                monkeypatch.setattr(bounded, '_clock', lambda: 10**12)
            return super().read(size)
    body = FailedBody(b'payload')
    provider, calls = fake_s3(body, length=7)
    original_get = provider.client.get_object
    def get(**kwargs):
        logging.getLogger('botocore.endpoint').error(private)
        if failure == 'client':
            raise ClientError({'Error': {'Code': 'AccessDenied', 'Message': private}}, 'GetObject')
        if failure == 'endpoint':
            raise EndpointConnectionError(endpoint_url=private)
        return original_get(**kwargs)
    provider.client.get_object = get
    target = tmp_path / 'target'
    target.write_bytes(b'prior')
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(bounded.StorageDownloadError) as error:
            await provider.download_file(object_key=KEY, destination=target, max_bytes=7)
        logging.getLogger('botocore.endpoint').warning('Public unrelated SDK diagnostic retained')
    assert private not in str(error.value) and private not in caplog.text
    assert 'Public unrelated SDK diagnostic retained' in caplog.text
    assert target.read_bytes() == b'prior' and not list(tmp_path.glob('.vf-object-*.tmp'))
    if failure in {'stream', 'timeout'}:
        assert body.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['s3', 'legacy_s3', 'local'])
async def test_double_cancel_drains_owned_writer_before_caller_can_cleanup(tmp_path, monkeypatch, kind):
    entered = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    target = tmp_path / 'staging' / 'target'
    target.parent.mkdir()
    target.write_bytes(b'prior')
    unrelated = target.parent / '.unrelated.tmp'
    unrelated.write_bytes(b'keep')
    raw = b'actual owned bytes'
    class PausedBody(Body):
        def read(self, size=-1):
            entered.set()
            assert release.wait(10), 'owned blocking stream fixture timeout'
            return super().read(size)
        def close(self):
            super().close()
            closed.set()
    body = PausedBody(raw)
    if kind == 'local':
        provider, source, saved = await local_object(tmp_path, raw)
        source_key_path = provider._path(KEY)
        original_open = Path.open
        def open_file(path, *args, **kwargs):
            if path == source_key_path and args and args[0] == 'rb':
                actual = original_open(path, *args, **kwargs)
                class OwnedPausedLocal:
                    def read(self, size):
                        entered.set()
                        assert release.wait(10)
                        return actual.read(size)
                    def fileno(self):
                        return actual.fileno()
                    def close(self):
                        actual.close(); closed.set()
                return OwnedPausedLocal()
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr(Path, 'open', open_file)
    else:
        provider, calls = fake_s3(body, length=len(raw))
        if kind == 'legacy_s3':
            def legacy(bucket, key, destination):
                path = Path(destination)
                path.write_bytes(b'partial')
                entered.set()
                assert release.wait(10)
                path.write_bytes(raw)
                closed.set()
            provider.client.download_file = legacy
    kwargs = {} if kind == 'legacy_s3' else {'max_bytes': len(raw)}
    work = asyncio.create_task(provider.download_file(object_key=KEY, destination=target, **kwargs))
    try:
        async def began():
            while not entered.is_set():
                await asyncio.sleep(.005)
        await asyncio.wait_for(began(), 5)
        work.cancel(); await asyncio.sleep(.02)
        work.cancel(); await asyncio.sleep(.02)
        assert not work.done() and not closed.is_set()
        assert target.read_bytes() == b'prior' and list(target.parent.glob('.vf-object-*.tmp'))
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(work, 5)
        assert closed.is_set() and target.read_bytes() == b'prior' and unrelated.read_bytes() == b'keep'
        assert not list(target.parent.glob('.vf-object-*.tmp'))
        await asyncio.sleep(.02)
        assert target.read_bytes() == b'prior'
    finally:
        release.set()
        await asyncio.gather(work, return_exceptions=True)


@pytest.mark.asyncio
async def test_replaced_owned_temporary_is_not_deleted_as_cleanup(tmp_path, monkeypatch):
    body = Body(b'payload')
    provider, calls = fake_s3(body, length=7)
    target = tmp_path / 'target'; target.write_bytes(b'prior')
    foreign = tmp_path / 'foreign'
    foreign.write_bytes(b'foreign retained bytes')
    def replacement(control, temporary, destination, **kwargs):
        temporary.unlink()
        foreign.rename(temporary)
        raise OSError('explicit temporary replacement fixture')
    monkeypatch.setattr(bounded.DownloadControl, 'replace', replacement)
    with pytest.raises(bounded.StorageDownloadError, match='PATH_CHANGED'):
        await provider.download_file(object_key=KEY, destination=target, max_bytes=7)
    remaining = list(tmp_path.glob('.vf-object-*.tmp'))
    assert len(remaining) == 1 and remaining[0].read_bytes() == b'foreign retained bytes'
    assert target.read_bytes() == b'prior'


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['local', 's3', 'legacy_s3'])
async def test_closed_stage_substitution_is_rejected_before_commit_and_foreign_stage_retained(tmp_path, monkeypatch, kind):
    raw, foreign, old = b'correct', b'foreign', b'prior target'
    target = tmp_path / 'target'; target.write_bytes(old)
    if kind == 'local':
        provider, original, saved = await local_object(tmp_path, raw)
    else:
        provider, calls = fake_s3(Body(raw), length=len(raw))
        if kind == 'legacy_s3':
            provider.client.download_file = lambda bucket, key, path: Path(path).write_bytes(raw)
    original_guard = bounded.guarded_destination
    calls = 0
    def substitute_after_output_closed(path, io_path):
        nonlocal calls
        result = original_guard(path, io_path); calls += 1
        if calls == 2:
            stage = next(tmp_path.glob('.vf-object-*.tmp'))
            retained = tmp_path / 'retained-verified-stage'
            previous = stage.stat().st_ino
            stage.replace(retained)
            stage.write_bytes(foreign)
            assert previous != stage.stat().st_ino and retained.read_bytes() == raw
        return result
    monkeypatch.setattr(bounded, 'guarded_destination', substitute_after_output_closed)
    kwargs = {} if kind == 'legacy_s3' else {
        'max_bytes': len(raw), 'expected_size_bytes': len(raw), 'expected_sha256': hashlib.sha256(raw).hexdigest()}
    with pytest.raises(bounded.StorageDownloadError, match='PATH_CHANGED'):
        await provider.download_file(object_key=KEY, destination=target, **kwargs)
    assert calls >= 2 and target.read_bytes() == old
    remaining = list(tmp_path.glob('.vf-object-*.tmp'))
    assert len(remaining) == 1 and remaining[0].read_bytes() == foreign
    assert (tmp_path / 'retained-verified-stage').read_bytes() == raw


@pytest.mark.asyncio
async def test_precommit_same_inode_truncation_and_hardlink_are_rejected(tmp_path, monkeypatch):
    for attack in ('truncate', 'hardlink'):
        folder = tmp_path / attack; folder.mkdir()
        body = Body(b'correct')
        provider, sdk_calls = fake_s3(body, length=7)
        target = folder / 'target'; target.write_bytes(b'prior')
        original_guard = bounded.guarded_destination
        count = 0
        def change(path, io_path):
            nonlocal count
            result = original_guard(path, io_path); count += 1
            if count == 2:
                stage = next(folder.glob('.vf-object-*.tmp'))
                if attack == 'truncate':
                    stage.write_bytes(b'bad')
                else:
                    os.link(stage, folder / 'retained-stage-alias')
            return result
        with monkeypatch.context() as scope:
            scope.setattr(bounded, 'guarded_destination', change)
            with pytest.raises(bounded.StorageDownloadError, match='PATH_CHANGED'):
                await provider.download_file(object_key=KEY, destination=target, expected_size_bytes=7)
        assert target.read_bytes() == b'prior'
        if attack == 'hardlink':
            assert (folder / 'retained-stage-alias').read_bytes() == b'correct'


@pytest.mark.asyncio
async def test_precommit_same_inode_same_size_bytes_are_reverified_without_second_sdk_call(tmp_path, monkeypatch):
    body = Body(b'correct'); provider, sdk_calls = fake_s3(body, length=7)
    target = tmp_path / 'target'; target.write_bytes(b'prior')
    original_guard = bounded.guarded_destination
    count = 0
    def same_file_changed(path, io_path):
        nonlocal count
        result = original_guard(path, io_path); count += 1
        if count == 2:
            stage = next(tmp_path.glob('.vf-object-*.tmp'))
            identity, size = stage.stat().st_ino, stage.stat().st_size
            stage.write_bytes(b'foreign')
            assert (stage.stat().st_ino, stage.stat().st_size) == (identity, size)
        return result
    monkeypatch.setattr(bounded, 'guarded_destination', same_file_changed)
    with pytest.raises(bounded.StorageDownloadError, match='STAGE_HASH_MISMATCH'):
        await provider.download_file(object_key=KEY, destination=target,
            expected_sha256=hashlib.sha256(b'correct').hexdigest(), expected_size_bytes=7)
    assert target.read_bytes() == b'prior' and len(sdk_calls) == 1 and body.closed
    assert not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
@pytest.mark.parametrize('denial', ['once', 'persistent', 'tampered'])
async def test_windows_rename_retry_is_bounded_reverifies_bytes_and_never_reopens_sdk(tmp_path, monkeypatch, denial):
    if os.name != 'nt':
        pytest.skip('Windows sharing-error policy only; other OS permission errors fail closed')
    provider, sdk_calls = fake_s3(Body(b'correct'), length=7)
    target = tmp_path / 'target'; target.write_bytes(b'prior')
    original_replace = Path.replace
    attempts = 0
    def sharing_denial(path, destination):
        nonlocal attempts
        if path.name.startswith('.vf-object-'):
            attempts += 1
            if attempts == 1 or denial == 'persistent':
                if denial == 'tampered':
                    path.write_bytes(b'foreign')
                raise PermissionError(13, 'private transient OS message', None, 5)
        return original_replace(path, destination)
    monkeypatch.setattr(Path, 'replace', sharing_denial)
    request = provider.download_file(object_key=KEY, destination=target, expected_size_bytes=7,
        expected_sha256=hashlib.sha256(b'correct').hexdigest())
    if denial == 'once':
        await request
        assert attempts == 2 and target.read_bytes() == b'correct'
    else:
        code = 'READ_FAILED' if denial == 'persistent' else 'STAGE_HASH_MISMATCH'
        with pytest.raises(bounded.StorageDownloadError, match=code) as error:
            await request
        assert 'private transient' not in str(error.value) and target.read_bytes() == b'prior'
        assert attempts == (4 if denial == 'persistent' else 1)
    assert len(sdk_calls) == 1 and not list(tmp_path.glob('.vf-object-*.tmp'))


@pytest.mark.asyncio
async def test_legacy_sdk_successful_own_atomic_replacement_is_admitted_and_cancelled_replacement_is_drained(tmp_path):
    raw = b'legacy explicit unbounded SDK mock'
    entered, release = threading.Event(), threading.Event()
    target = tmp_path / 'target'; target.write_bytes(b'prior')
    provider, calls = fake_s3(Body(b''), length=0)
    block = False
    def sdk_atomic_replace(bucket, key, path):
        path = Path(path)
        sdk_stage = path.with_name(path.name + '.sdk-owned')
        sdk_stage.write_bytes(raw)
        sdk_stage.replace(path)
        entered.set()
        if block:
            assert release.wait(10)
    provider.client.download_file = sdk_atomic_replace
    await provider.download_file(object_key=KEY, destination=target)
    assert target.read_bytes() == raw and not list(tmp_path.glob('.vf-object-*'))
    target.write_bytes(b'prior'); entered.clear(); block = True
    work = asyncio.create_task(provider.download_file(object_key=KEY, destination=target))
    try:
        async def began():
            while not entered.is_set(): await asyncio.sleep(.005)
        await asyncio.wait_for(began(), 5)
        work.cancel(); await asyncio.sleep(.02); work.cancel(); await asyncio.sleep(.02)
        assert not work.done() and target.read_bytes() == b'prior'
        release.set()
        with pytest.raises(asyncio.CancelledError): await asyncio.wait_for(work, 5)
        assert target.read_bytes() == b'prior' and not list(tmp_path.glob('.vf-object-*'))
    finally:
        release.set(); await asyncio.gather(work, return_exceptions=True)


@pytest.mark.asyncio
async def test_existing_destination_hardlink_and_parent_escape_are_rejected_before_wire(tmp_path):
    body = Body(b'payload'); provider, calls = fake_s3(body, length=7)
    original = tmp_path / 'original'; original.write_bytes(b'prior')
    alias = tmp_path / 'alias'; os.link(original, alias)
    with pytest.raises(bounded.StorageDownloadError, match='PATH_INVALID'):
        await provider.download_file(object_key=KEY, destination=alias, max_bytes=7)
    with pytest.raises(bounded.StorageDownloadError, match='PATH_INVALID'):
        await provider.download_file(object_key=KEY, destination=tmp_path / '..' / 'escape', max_bytes=7)
    assert not calls and original.read_bytes() == alias.read_bytes() == b'prior'


@pytest.mark.asyncio
async def test_local_in_root_link_is_rejected_without_mutating_original(tmp_path):
    provider, original, saved = await local_object(tmp_path)
    actual = provider._path(KEY)
    alias = actual.with_name('aliased.wav')
    try:
        alias.symlink_to(actual)
    except OSError:
        pytest.skip('Host lacks file symlink permission; junction test covers Windows directory reparse elsewhere')
    with pytest.raises(bounded.StorageDownloadError, match='LINK_REJECTED'):
        await provider.download_file(object_key=KEY.replace('voice.wav', 'aliased.wav'),
            destination=tmp_path / 'target', max_bytes=saved.size_bytes)
    assert original.read_bytes() == b'actual owned local bytes' and not (tmp_path / 'target').exists()


@pytest.mark.asyncio
async def test_in_root_directory_junction_or_symlink_cannot_hide_behind_resolution(tmp_path):
    provider, original, saved = await local_object(tmp_path)
    source_directory = provider._path(KEY).parent
    alias = provider._io_root / 'aliased-source'
    try:
        alias.symlink_to(source_directory, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(alias), str(source_directory)],
            cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=10)
        if result.returncode:
            pytest.skip('Host cannot create owned symlink/junction fixture')
        assert alias.is_junction()
    with pytest.raises(bounded.StorageDownloadError, match='LINK_REJECTED'):
        await provider.download_file(object_key='aliased-source/voice.wav', destination=tmp_path / 'target', max_bytes=saved.size_bytes)
    assert original.read_bytes() == b'actual owned local bytes' and not (tmp_path / 'target').exists()


@pytest.mark.asyncio
async def test_windows_long_path_with_bounded_exact_download(tmp_path):
    root = tmp_path / ('a' * 100) / ('b' * 100) / ('c' * 100)
    provider = storage.LocalObjectStorageProvider(root)
    await provider.ensure_ready()
    original = tmp_path / 'source'; original.write_bytes(b'owned long path fixture')
    saved = await provider.put_file(object_key=KEY, path=original)
    target = tmp_path / ('d' * 100) / ('e' * 100) / ('f' * 100) / 'result'
    await provider.download_file(object_key=KEY, destination=target,
        max_bytes=saved.size_bytes, expected_size_bytes=saved.size_bytes,
        expected_sha256=saved.checksum_sha256, expected_prefix=PREFIX)
    assert len(str(target)) > 260 and storage.filesystem_path(target).read_bytes() == original.read_bytes()
    assert not list(storage.filesystem_path(target).parent.glob('.vf-object-*.tmp'))
