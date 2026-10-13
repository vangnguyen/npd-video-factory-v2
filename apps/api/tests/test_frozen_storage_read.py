"""Owned local bytes and explicit SDK streams; no credentials/network/model."""
import asyncio
import hashlib
import threading
from types import SimpleNamespace

import pytest

from app.frozen_storage_read import FrozenStorageRead, FrozenReadRejected, completed_read
from app.object_storage import LocalObjectStorageProvider, create_object_storage, download_cancellation_is_drained
from app.bounded_storage_download import StorageDownloadError
from test_bounded_storage_download import fake_s3, Body, KEY, PREFIX


def proof(data, *, provider='local', **updates):
    values=dict(object_key=KEY,workspace_id='wsp_fixture',project_id='prj_fixture',size_bytes=len(data),
        checksum_sha256=hashlib.sha256(data).hexdigest(),storage_provider=provider,maximum=len(data)+10)
    return FrozenStorageRead(**{**values,**updates})


def test_cancellation_claim_is_explicit_and_not_inherited_by_an_override(tmp_path):
    native=LocalObjectStorageProvider(tmp_path)
    assert download_cancellation_is_drained(native)
    class UnknownOverride(LocalObjectStorageProvider):
        async def download_file(self,**kwargs):
            await asyncio.to_thread(lambda: None)
    assert not download_cancellation_is_drained(UnknownOverride(tmp_path))


@pytest.mark.asyncio
@pytest.mark.parametrize('provider',['local','s3'])
async def test_actual_byte_proof_is_consumed_by_counted_storage_without_legacy_fallback(tmp_path,provider):
    data=b'owned frozen bytes'*10000
    if provider=='local':
        store=LocalObjectStorageProvider(tmp_path/'objects');source=tmp_path/'source';source.write_bytes(data)
        await store.put_file(object_key=KEY,path=source)
    else:store,calls=fake_s3(Body(data),length=len(data))
    target=tmp_path/'target'
    await proof(data,provider=provider).download(store,target)
    assert target.read_bytes()==data
    if provider=='s3':assert calls==[{'Bucket':'explicit-fixture-only','Key':KEY}]


@pytest.mark.asyncio
@pytest.mark.parametrize('updates',[{'size_bytes':None},{'size_bytes':True},{'maximum':2**31+1},
    {'checksum_sha256':None},{'object_key':KEY.replace('prj_fixture','prj_another')},
    {'object_key':KEY.replace('voice.wav','../voice.wav')},{'workspace_id':'wsp_fixture/../other'}])
async def test_unproven_scope_or_bytes_are_rejected_before_any_adapter_access(tmp_path,updates):
    class Denied:
        def __getattr__(self,name):raise AssertionError('Proof failure must precede adapter access')
    with pytest.raises(FrozenReadRejected):await proof(b'data',**updates).download(Denied(),tmp_path/'target')
    assert not (tmp_path/'target').exists()


@pytest.mark.asyncio
async def test_legacy_adapter_signature_is_not_retried_as_unbounded(tmp_path):
    class Legacy:
        name='local';calls=0
        async def download_file(self,*,object_key,destination):self.calls+=1
    store=Legacy()
    with pytest.raises(TypeError):await proof(b'data').download(store,tmp_path/'target')
    assert store.calls==0


@pytest.mark.asyncio
@pytest.mark.parametrize('mutated',['extra','changed'])
async def test_s3_stream_cannot_exceed_or_change_registered_bytes_despite_lying_length(tmp_path,mutated):
    data=b'owned bytes';body=Body(data+b'x' if mutated=='extra' else b'Owned bytes')
    store,calls=fake_s3(body,length=len(data));target=tmp_path/'target';target.write_bytes(b'prior')
    with pytest.raises(StorageDownloadError):await proof(data,provider='s3').download(store,target)
    assert target.read_bytes()==b'prior' and body.closed and len(calls)==1


@pytest.mark.asyncio
async def test_repeated_cancel_drains_actual_worker_and_disposes_its_private_handle(tmp_path):
    path=tmp_path/'owned';path.write_bytes(b'data')
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    def work():
        handle=path.open('rb');entered.set();assert release.wait(10)
        return handle
    def dispose(handle):handle.close();closed.set()
    task=asyncio.create_task(completed_read(asyncio.to_thread(work),dispose_cancelled_result=dispose))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set() and path.read_bytes()==b'data'
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_is_forwarded_once_to_bounded_storage_then_drained_before_cleanup(tmp_path):
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    data=b'owned bytes'
    class PausedBody(Body):
        def read(self,size=-1):
            entered.set();assert release.wait(10)
            return super().read(size)
        def close(self):super().close();closed.set()
    store,_=fake_s3(PausedBody(data),length=len(data))
    target=tmp_path/'target';target.write_bytes(b'prior')
    task=asyncio.create_task(proof(data,provider='s3').download(store,target))
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set() and target.read_bytes()==b'prior'
        assert set(value.name for value in tmp_path.iterdir())=={'target'}
    finally:
        release.set();await asyncio.gather(task,return_exceptions=True)


def test_factory_explicitly_wires_finite_sdk_config_without_constructing_sdk(monkeypatch):
    import app.object_storage as module
    captured={}
    def factory(**kwargs):captured.update(kwargs);return object()
    monkeypatch.setattr(module,'S3ObjectStorageProvider',factory)
    settings=SimpleNamespace(object_storage_provider='s3',object_storage_endpoint_url='https://fixture.invalid',
        object_storage_bucket='fixture',object_storage_region='fixture',object_storage_access_key=None,
        object_storage_secret_key=None,object_storage_auto_create_bucket=False)
    create_object_storage(settings)
    config=captured['request_config']
    assert config.connect_timeout==5 and config.read_timeout==30
    assert config.retries=={'total_max_attempts':1}
    assert captured['access_key'] is None and captured['secret_key'] is None
