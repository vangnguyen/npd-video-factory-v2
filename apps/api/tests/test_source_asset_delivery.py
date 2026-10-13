"""Actual local WAV/storage bytes; no ASR, provider or human acceptance."""
import hashlib
import io
from pathlib import Path
import wave
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI, Request

from app.object_storage import LocalObjectStorageProvider
from app.platform_models import AssetRead
from app.source_asset_delivery import deliver_source_asset


def wav():
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setnchannels(1); writer.setsampwidth(2); writer.setframerate(16000)
        writer.writeframes(b'\x10\x00\x20\x00'*16000)
    return buffer.getvalue()


@pytest.fixture
async def fixture(tmp_path):
    data = wav(); source = tmp_path/'original.wav'; source.write_bytes(data)
    store = LocalObjectStorageProvider(tmp_path/'objects')
    key = 'workspaces/wsp_fixture/projects/prj_fixture/source/recorded.wav'
    stored = await store.put_file(object_key=key, path=source, content_type='audio/wav')
    now = datetime.now(timezone.utc)
    asset = AssetRead(asset_id='ast_fixture', workspace_id='wsp_fixture', project_id='prj_fixture',
        project_version_id=None, job_id=None, asset_class='source', kind='audio', filename='recorded.wav',
        object_key=key, content_type='audio/wav', size_bytes=len(data), checksum_sha256=stored.checksum_sha256,
        storage_provider='local', version=1, provenance={'explicit_fixture':True}, created_at=now, updated_at=now)
    app = FastAPI(); state = {'asset':asset, 'calls':[], 'store':store, 'cap':2*1024**3}
    class RecordingStore:
        name = 'local'
        async def download_file(self, *, object_key, destination, max_bytes=None,
                expected_size_bytes=None, expected_sha256=None, expected_prefix=None):
            state['calls'].append(destination)
            await state['store'].download_file(object_key=object_key, destination=destination,
                max_bytes=max_bytes, expected_size_bytes=expected_size_bytes,
                expected_sha256=expected_sha256, expected_prefix=expected_prefix)
    staging = tmp_path/'staging'
    @app.get('/fixture-source')
    async def source_route(request:Request):
        return await deliver_source_asset(request, asset=state['asset'], object_storage=RecordingStore(),
            staging_root=staging, max_source_bytes=state['cap'])
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://fixture') as client:
        yield client, state, staging, data, store
    assert not staging.exists() or not list(staging.iterdir())


@pytest.mark.asyncio
async def test_full_source_matches_registered_sha_and_cleans_owned_staging(fixture):
    client, state, staging, data, _ = fixture
    response = await client.get('/fixture-source')
    assert response.status_code == 200 and response.content == data
    assert hashlib.sha256(response.content).hexdigest() == state['asset'].checksum_sha256
    assert response.headers['content-type'] == 'audio/wav'
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['accept-ranges'] == 'bytes'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['etag'] == '"sha256-'+state['asset'].checksum_sha256+'"'
    assert not list(staging.iterdir()) and len(state['calls']) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('header,interval', [('bytes=5-19',(5,20)), ('bytes=-12',(-12,None)),
    ('bytes=4-',(4,None)), ('bytes=0-999999999',(0,None)), ('BYTES=0-0',(0,1))])
async def test_single_ranges_read_actual_intervals_and_clean(fixture,header,interval):
    client, _, staging, data, _ = fixture
    response = await client.get('/fixture-source', headers={'Range':header})
    assert response.status_code == 206
    assert response.content == data[slice(*interval)]
    assert response.headers['content-range'].endswith('/'+str(len(data)))
    assert int(response.headers['content-length']) == len(response.content)
    assert not list(staging.iterdir())


@pytest.mark.asyncio
@pytest.mark.parametrize('header', ['bytes=-0','bytes=999999-','bytes=20-10','bytes=1-2,3-4',
    'items=1-2','bytes=-','bytes=+1-3','bytes=0-'+'9'*129])
async def test_invalid_range_is_416_before_storage_or_staging(fixture,header):
    client, state, staging, data, _ = fixture
    response = await client.get('/fixture-source', headers={'Range':header})
    assert response.status_code == 416 and response.headers['content-range'] == f'bytes */{len(data)}'
    assert not state['calls'] and not staging.exists()


@pytest.mark.asyncio
async def test_if_range_requires_strong_current_checksum_or_returns_full(fixture):
    client, state, _, data, _ = fixture
    matched = await client.get('/fixture-source', headers={'Range':'bytes=0-3',
        'If-Range':'"sha256-'+state['asset'].checksum_sha256+'"'})
    assert matched.status_code == 206 and matched.content == data[:4]
    for value in ('"old-checksum"', 'W/"sha256-'+state['asset'].checksum_sha256+'"', 'Mon, 12 Oct 2026 00:00:00 GMT'):
        response = await client.get('/fixture-source', headers={'Range':'bytes=0-3','If-Range':value})
        assert response.status_code == 200 and response.content == data


@pytest.mark.asyncio
@pytest.mark.parametrize('changes', [{'kind':'subtitle'}, {'asset_class':'generated'},
    {'storage_provider':'another'}, {'checksum_sha256':'0'}, {'size_bytes':0}, {'object_key':'../private'}])
async def test_registered_source_metadata_guard_precedes_storage(fixture,changes):
    client, state, staging, _, _ = fixture
    state['asset'] = state['asset'].model_copy(update=changes)
    response = await client.get('/fixture-source')
    assert response.status_code == 409
    assert response.json()['detail']['code'] == 'SOURCE_ASSET_METADATA_INVALID'
    assert not state['calls'] and not staging.exists()


@pytest.mark.asyncio
async def test_requested_byte_limit_denies_before_external_storage(fixture):
    client, state, _, data, _ = fixture
    state['cap'] = len(data)-1
    response = await client.get('/fixture-source')
    assert response.status_code == 409 and not state['calls']


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,code', [('hash','SOURCE_ASSET_CHECKSUM_CHANGED'), ('size','SOURCE_ASSET_SIZE_CHANGED'),
    ('mime','SOURCE_ASSET_MIME_CHANGED')])
async def test_tampered_objects_or_wrong_registered_mime_never_stream(fixture,mode,code):
    client, state, staging, data, store = fixture
    if mode == 'mime':
        state['asset'] = state['asset'].model_copy(update={'content_type':'audio/flac'})
    else:
        corrupted = data[:-1] if mode == 'size' else data[:-1]+bytes([data[-1]^1])
        store._path(state['asset'].object_key).write_bytes(corrupted)
    response = await client.get('/fixture-source', headers={'Range':'bytes=0-3'})
    assert response.status_code == 409 and response.json()['detail']['code'] == code
    assert not list(staging.iterdir()) and str(staging) not in response.text


@pytest.mark.asyncio
async def test_missing_or_failing_storage_closes_staging_and_hides_private_error(fixture):
    client, state, staging, _, store = fixture
    store._path(state['asset'].object_key).unlink()
    response = await client.get('/fixture-source')
    assert response.status_code == 404 and not list(staging.iterdir())
    class Failed:
        async def download_file(self, **kwargs):
            raise RuntimeError('private-token-and-path-must-not-leak')
    state['store'] = Failed()
    response = await client.get('/fixture-source')
    assert response.status_code == 503 and 'private-token' not in response.text
    assert not list(staging.iterdir())


@pytest.mark.asyncio
async def test_original_filename_cannot_inject_headers_or_override_detected_mime(fixture):
    client, state, _, data, _ = fixture
    state['asset'] = state['asset'].model_copy(update={'filename':'../unsafe.html\r\nX-private: secret'})
    response = await client.get('/fixture-source')
    assert response.status_code == 200 and response.content == data
    assert response.headers['content-type'] == 'audio/wav' and 'x-private' not in response.headers
    assert '\r' not in response.headers['content-disposition'] and '\n' not in response.headers['content-disposition']


@pytest.mark.asyncio
async def test_client_disconnect_runs_private_descriptor_and_temp_cleanup(fixture):
    _, state, staging, _, store = fixture
    request = Request({'type':'http','method':'GET','path':'/','headers':[], 'query_string':b''})
    response = await deliver_source_asset(request, asset=state['asset'], object_storage=store, staging_root=staging)
    async def receive():
        return {'type':'http.disconnect'}
    async def disconnected_send(message):
        raise OSError('explicit client disconnect fixture')
    with pytest.raises(Exception):
        await response({'type':'http','asgi':{'spec_version':'2.4'}}, receive, disconnected_send)
    assert response._handle.closed and not list(staging.iterdir())


@pytest.mark.asyncio
async def test_slow_checksum_does_not_block_other_request_progress(fixture, monkeypatch):
    """A waiting disk/hash worker must leave the ASGI loop responsive."""
    import asyncio
    import threading
    from app import source_asset_delivery as delivery
    client, _, staging, data, _ = fixture
    entered, release = threading.Event(), threading.Event()
    original = delivery.verified_handle
    def gated_verification(*args):
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError('checksum fixture was not released')
        return original(*args)
    monkeypatch.setattr(delivery, 'verified_handle', gated_verification)
    task = asyncio.create_task(client.get('/fixture-source'))
    try:
        assert await asyncio.to_thread(entered.wait, 2)
        # Execute independent event-loop work while disk verification is held.
        marker = asyncio.Event()
        asyncio.get_running_loop().call_soon(marker.set)
        await asyncio.wait_for(marker.wait(), timeout=.5)
        assert not task.done()
    finally:
        release.set()
    response = await asyncio.wait_for(task, timeout=3)
    assert response.status_code == 200 and response.content == data
    assert not list(staging.iterdir())
