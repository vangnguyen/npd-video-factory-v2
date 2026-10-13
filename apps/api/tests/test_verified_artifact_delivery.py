"""Owned byte-delivery fixtures and explicit fake SDK streams, never rendered media."""
import asyncio
import hashlib
import io
from pathlib import Path
import tempfile
import threading

from fastapi import FastAPI, HTTPException
import httpx
import pytest

import app.verified_artifact_delivery as delivery
from app.object_storage import LocalObjectStorageProvider
from test_bounded_storage_download import Body, fake_s3

KEY = 'workspaces/wsp_fixture/projects/prj_fixture/outputs/review.mp4'
PREFIX = 'workspaces/wsp_fixture/projects/prj_fixture/'
RAW = b'EXPLICIT OUTPUT BYTE FIXTURE, NOT A REAL RENDER\0' * 4000


def proof(raw=RAW, **changes):
    fields = dict(object_key=KEY, workspace_id='wsp_fixture', project_id='prj_fixture',
        size_bytes=len(raw), checksum_sha256=hashlib.sha256(raw).hexdigest(), storage_provider='local')
    fields.update(changes)
    return delivery.RecordedArtifactRead(**fields)


async def local(tmp_path, raw=RAW):
    storage = LocalObjectStorageProvider(tmp_path/'objects')
    await storage.ensure_ready()
    original = tmp_path/'original.bin'; original.write_bytes(raw)
    await storage.put_file(object_key=KEY, path=original)
    return storage


async def response(tmp_path, storage, raw=RAW, **changes):
    async def current(): pass
    registered = changes.pop('proof') if 'proof' in changes else proof(raw)
    fields = dict(proof=registered, storage=storage, staging_root=tmp_path/'stage',
        basename='render.mp4', filename='review.mp4', media_type='video/mp4', current=current)
    fields.update(changes)
    return await delivery.deliver_verified_artifact(**fields)


def application(tmp_path, storage, raw=RAW, **changes):
    app = FastAPI()
    @app.api_route('/output', methods=['GET','HEAD'])
    async def output():
        try: return await response(tmp_path,storage,raw,**changes)
        except FileNotFoundError: raise HTTPException(404,detail='NOT_FOUND') from None
        except delivery.ArtifactDeliveryRejected as error:
            raise HTTPException(error.status,detail=error.code) from None
    return app


def clean(tmp_path):
    assert not list((tmp_path/'stage').glob('verified-artifact-*'))


@pytest.mark.parametrize('changes',[
    {'size_bytes':None}, {'size_bytes':False}, {'size_bytes':-1}, {'size_bytes':1.5},
    {'checksum_sha256':None}, {'checksum_sha256':'A'*64}, {'storage_provider':None},
    {'workspace_id':'wsp_fixture/../'}, {'object_key':'workspaces/wsp_other/projects/prj_fixture/x'},
    {'size_bytes':0}, {'size_bytes':0,'allow_empty':True}, {'allow_empty':1},
])
def test_incomplete_or_foreign_proof_fails_before_io(changes):
    with pytest.raises(delivery.ArtifactDeliveryRejected): proof(**changes)


def test_empty_proof_explicit_and_large_registered_output_is_not_source_capped():
    empty = proof(b'',allow_empty=True)
    assert empty.maximum==1 and empty.size_bytes==0
    assert proof(size_bytes=3*1024**3).maximum==3*1024**3


@pytest.mark.asyncio
@pytest.mark.parametrize('range_value,expected_status,expected',[
    (None,200,RAW), ('bytes=3-11',206,RAW[3:12]), ('bytes=-9',206,RAW[-9:]),
    ('bytes=10-',206,RAW[10:]), ('bytes=99999999-',416,b''), ('units=1-4',400,None),
],ids=['full','closed','suffix','open','unsatisfiable','malformed'])
async def test_real_output_bytes_range_headers_and_cleanup(tmp_path,range_value,expected_status,expected):
    storage = await local(tmp_path)
    app=application(tmp_path,storage)
    headers={} if range_value is None else {'Range':range_value}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        result=await client.get('/output',headers=headers)
    assert result.status_code==expected_status
    if expected is not None: assert result.content==expected
    assert result.headers['cache-control']=='no-store'
    assert result.headers['x-content-type-options']=='nosniff'
    if expected_status in {200,206}:
        assert result.headers['etag']=='"'+hashlib.sha256(RAW).hexdigest()+'"'
        assert int(result.headers['content-length'])==len(expected)
        assert result.headers['content-type']=='video/mp4'
    clean(tmp_path)


@pytest.mark.asyncio
async def test_head_if_range_and_multipart_preserve_file_response_protocol(tmp_path):
    storage=await local(tmp_path); app=application(tmp_path,storage,filename='../private\r\nInjected: yes.mp4')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        head=await client.head('/output',headers={'Range':'bytes=3-8'})
        assert head.status_code==206 and head.content==b'' and head.headers['content-length']=='6'
        assert head.headers['content-range']==f'bytes 3-8/{len(RAW)}'
        assert '\r' not in head.headers['content-disposition'] and '%0D%0A' in head.headers['content-disposition']
        stale=await client.get('/output',headers={'Range':'bytes=3-8','If-Range':'"other"'})
        assert stale.status_code==200 and stale.content==RAW
        same=await client.get('/output',headers={'Range':'bytes=3-8','If-Range':head.headers['etag']})
        assert same.status_code==206 and same.content==RAW[3:9]
        multi=await client.get('/output',headers={'Range':'bytes=1-3,9-11'})
        assert multi.status_code==206 and int(multi.headers['content-length'])==len(multi.content)
        assert b'Content-Range: bytes 1-3/' in multi.content and b'Content-Range: bytes 9-11/' in multi.content
        assert RAW[1:4]+b'\r\n' in multi.content and RAW[9:12]+b'\r\n' in multi.content
    clean(tmp_path)


@pytest.mark.asyncio
async def test_explicit_empty_artifact_get_and_head(tmp_path):
    storage=await local(tmp_path,b'')
    app=application(tmp_path,storage,b'',proof=proof(b'',allow_empty=True),media_type='application/json')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        for method in ['get','head']:
            result=await getattr(client,method)('/output')
            assert result.status_code==200 and result.content==b'' and result.headers['content-length']=='0'
    clean(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode',['missing','bytes','old_signature','private_failure','current'])
async def test_failures_do_not_expose_paths_replay_or_leave_staging(tmp_path,mode):
    storage=await local(tmp_path); calls=[]
    real=storage.download_file
    async def download(**kwargs):
        calls.append(kwargs)
        if mode=='missing': raise FileNotFoundError('PRIVATE PATH')
        if mode=='private_failure': raise RuntimeError('PRIVATE CREDENTIAL')
        await real(**kwargs)
        if mode=='bytes': kwargs['destination'].write_bytes(b'tampered')
    storage.download_file=download
    if mode=='old_signature':
        async def old(object_key,destination): calls.append('unbounded')
        storage.download_file=old
    async def current():
        if mode=='current': raise delivery.ArtifactDeliveryRejected('ARTIFACT_OUTPUT_CHANGED')
    app=application(tmp_path,storage,current=current)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        result=await client.get('/output')
    assert result.status_code==({'missing':404,'bytes':409,'current':409}.get(mode,503))
    assert 'PRIVATE' not in result.text and str(tmp_path) not in result.text
    assert len(calls)==(0 if mode=='old_signature' else 1)
    clean(tmp_path)


@pytest.mark.asyncio
async def test_same_size_staged_tamper_during_final_await_cannot_use_verified_sha_etag(tmp_path):
    storage=await local(tmp_path);calls=[];download=storage.download_file
    async def capture(**kwargs):calls.append(kwargs);await download(**kwargs)
    storage.download_file=capture
    async def current():
        await asyncio.sleep(0)
        staged=next((tmp_path/'stage').glob('verified-artifact-*/render.mp4'))
        # Real private file, same size; SQL metadata and recorded SHA remain intact.
        staged.write_bytes(b'X'*len(RAW))
        await asyncio.sleep(0)
    app=application(tmp_path,storage,current=current)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        result=await client.get('/output')
    assert result.status_code==409 and result.json()['detail']=='ARTIFACT_BYTES_CHANGED'
    assert 'etag' not in result.headers and len(calls)==1
    clean(tmp_path)


@pytest.mark.asyncio
async def test_closed_verified_descriptor_during_final_guard_is_typed_conflict(tmp_path,monkeypatch):
    storage=await local(tmp_path);held=[];verify=delivery.verified_output_handle
    def capture(path,registered):
        result=verify(path,registered);held.append(result[0]);return result
    monkeypatch.setattr(delivery,'verified_output_handle',capture)
    async def current():held[0].close()
    app=application(tmp_path,storage,current=current)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        result=await client.get('/output')
    assert result.status_code==409 and result.json()['detail']=='ARTIFACT_BYTES_CHANGED'
    assert 'etag' not in result.headers and held[0].closed;clean(tmp_path)


@pytest.mark.asyncio
async def test_actual_s3_configured_bounded_stream_has_exact_proof(tmp_path):
    body=Body(RAW); storage,calls=fake_s3(body,length=len(RAW))
    app=application(tmp_path,storage,proof=proof(storage_provider=storage.name))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://fixture') as client:
        result=await client.get('/output')
    assert result.content==RAW and len(calls)==1 and body.closed
    assert all(0<value<=1024*1024 for value in body.requests)
    assert storage.client.meta.config.read_timeout>0 and storage.client.meta.config.connect_timeout>0
    clean(tmp_path)


class PausedBody(Body):
    def __init__(self,value):
        super().__init__(value); self.entered=threading.Event(); self.release=threading.Event()
    def read(self,size=-1):
        self.entered.set(); assert self.release.wait(5)
        return super().read(size)


@pytest.mark.asyncio
async def test_double_cancel_download_drains_sdk_before_cleanup(tmp_path):
    body=PausedBody(RAW); storage,calls=fake_s3(body,length=len(RAW))
    task=asyncio.create_task(response(tmp_path,storage,proof=proof(storage_provider=storage.name)))
    assert await asyncio.to_thread(body.entered.wait,3)
    task.cancel(); await asyncio.sleep(.02); task.cancel(); await asyncio.sleep(.02)
    assert not task.done() and list((tmp_path/'stage').glob('verified-artifact-*'))
    body.release.set()
    with pytest.raises(asyncio.CancelledError): await task
    assert body.closed and len(calls)==1
    clean(tmp_path)


@pytest.mark.asyncio
async def test_unknown_thread_adapter_is_not_cancelled_before_its_writer_drains(tmp_path):
    entered=threading.Event();release=threading.Event();finished=threading.Event();calls=[]
    class GenericAdapter:
        name='local'
        async def download_file(self,**kwargs):
            calls.append(kwargs)
            def write():
                entered.set();assert release.wait(5)
                kwargs['destination'].write_bytes(RAW);finished.set()
            # Explicit legacy thread adapter has no cancellation-drain contract.
            await asyncio.to_thread(write)
    task=asyncio.create_task(response(tmp_path,GenericAdapter()))
    assert await asyncio.to_thread(entered.wait,3)
    task.cancel();await asyncio.sleep(.02);task.cancel();await asyncio.sleep(.02)
    assert not task.done() and not finished.is_set()
    assert list((tmp_path/'stage').glob('verified-artifact-*'))
    release.set()
    with pytest.raises(asyncio.CancelledError):await task
    assert finished.is_set() and len(calls)==1;clean(tmp_path)


@pytest.mark.asyncio
async def test_double_cancel_hash_disposes_completed_descriptor_before_cleanup(tmp_path,monkeypatch):
    storage=await local(tmp_path); entered=threading.Event(); release=threading.Event(); held=[]
    original=delivery.verified_output_handle
    def paused(path,value):
        result=original(path,value);held.append(result[0]);entered.set();assert release.wait(5);return result
    monkeypatch.setattr(delivery,'verified_output_handle',paused)
    task=asyncio.create_task(response(tmp_path,storage))
    assert await asyncio.to_thread(entered.wait,3)
    task.cancel(); await asyncio.sleep(.02); task.cancel(); await asyncio.sleep(.02)
    assert not task.done() and not held[0].closed
    release.set()
    with pytest.raises(asyncio.CancelledError): await task
    assert held[0].closed;clean(tmp_path)


@pytest.mark.asyncio
@pytest.mark.parametrize('termination',['cancel_twice','disconnect','send_error'])
async def test_stream_termination_drains_owned_descriptor_and_temp(tmp_path,termination):
    storage=await local(tmp_path); result=await response(tmp_path,storage)
    original=result._handle; entered=threading.Event(); release=threading.Event(); sent=[]
    class PausedFile:
        def seek(self,*args): return original.seek(*args)
        def read(self,*args): entered.set();assert release.wait(5);return original.read(*args)
        def close(self): original.close()
    result._handle=PausedFile()
    scope={'type':'http','method':'GET','headers':[], 'asgi':{'spec_version':'2.0' if termination=='disconnect' else '2.4'},
        'extensions':{'http.response.pathsend':{}}}
    async def receive():
        assert await asyncio.to_thread(entered.wait,3)
        return {'type':'http.disconnect'}
    async def send(message):
        sent.append(message)
        if termination=='send_error' and message['type']=='http.response.body': raise OSError('client closed')
    task=asyncio.create_task(result(scope,receive,send))
    assert await asyncio.to_thread(entered.wait,3)
    if termination=='cancel_twice': task.cancel();await asyncio.sleep(.02);task.cancel()
    await asyncio.sleep(.03)
    assert not task.done() and not original.closed
    release.set()
    if termination=='cancel_twice':
        with pytest.raises(asyncio.CancelledError):await task
    elif termination=='send_error':
        with pytest.raises(OSError):await task
    else: await task
    assert original.closed and not any(m['type']=='http.response.pathsend' for m in sent)
    clean(tmp_path)
