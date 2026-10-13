"""Bounded copy/magic/lifecycle proofs using fresh owned files, no cleanup bypass."""
import asyncio
import hashlib
import os
import threading
import struct
import pytest
from app.object_storage import LocalObjectStorageProvider
from app.storyboard_timeline import template_png
from app.sql_variant_storyboard_copy import LocalStoryboardCopier, image_dimensions
from app.sql_variant_repository import SqlVariantError


def item(data, **changes):
    return {'object_key': 'workspaces/owned/projects/master/fixture.png',
        'target_key': 'workspaces/owned/projects/child/fixture.png', 'content_type': 'image/png',
        'size_bytes': len(data), 'checksum_sha256': hashlib.sha256(data).hexdigest(), **changes}


async def fixture(tmp_path, data=None):
    storage=LocalObjectStorageProvider(tmp_path/'objects');await storage.ensure_ready()
    data=data or template_png();path=storage._path(item(data)['object_key'])
    path.parent.mkdir(parents=True);path.write_bytes(data)
    return storage,data


@pytest.mark.asyncio
async def test_owned_unicode_long_path_copy_is_independent_and_existing_target_never_overwritten(tmp_path):
    storage,data=await fixture(tmp_path/'Tư liệu riêng')
    fields=item(data, target_key='workspaces/owned/projects/child/'+('a'*100)+'/'+('b'*100)+'/fixture.png')
    copier=LocalStoryboardCopier(storage)
    copied=await copier.copy({'ast_fixture':fields})
    source,target=storage._path(fields['object_key']),storage._path(fields['target_key'])
    assert len(str(target))>260 and target.read_bytes()==data and source.stat().st_ino != target.stat().st_ino
    assert copied['ast_fixture']['dimensions']==[270,480]
    await copier.verify_all(copied,source_items={'ast_fixture':fields})
    with pytest.raises(SqlVariantError,match='TARGET_EXISTS'):await copier.copy({'ast_fixture':fields})
    assert target.read_bytes()==data


@pytest.mark.asyncio
async def test_provider_neutral_copier_fails_closed_for_unconfigured_storage_and_declared_size_before_growth(tmp_path):
    with pytest.raises(SqlVariantError,match='STORAGE_NOT_CONFIGURED'):LocalStoryboardCopier(object())
    storage,data=await fixture(tmp_path)
    copier=LocalStoryboardCopier(storage,max_file_bytes=100,max_total_bytes=100)
    with pytest.raises(SqlVariantError,match='SIZE_LIMIT'):await copier.copy({'ast_fixture':item(data)})
    assert not storage._path(item(data)['target_key']).exists()


@pytest.mark.asyncio
async def test_storage_root_configuration_drift_cannot_relabel_copy_or_verification(tmp_path):
    storage,data=await fixture(tmp_path)
    copier=LocalStoryboardCopier(storage)
    other=tmp_path/'foreign-objects';other.mkdir()
    storage._io_root=other
    with pytest.raises(SqlVariantError,match='STORAGE_BINDING_CHANGED'):
        await copier.copy({'ast_fixture':item(data)})
    with pytest.raises(SqlVariantError,match='STORAGE_BINDING_CHANGED'):
        await copier.verify_all({})
    assert list(other.iterdir())==[]


@pytest.mark.asyncio
async def test_checksum_and_dimensions_use_same_read_snapshot_not_second_mutable_file_read(tmp_path,monkeypatch):
    storage,data=await fixture(tmp_path)
    from pathlib import Path
    def second_read_forbidden(path):
        raise AssertionError('A second open could associate a different header with an old checksum')
    monkeypatch.setattr(Path,'read_bytes',second_read_forbidden)
    fields=item(data); source=storage._path(fields['object_key'])
    assert LocalStoryboardCopier.verify(source,'image/png',len(data),hashlib.sha256(data).hexdigest())==[270,480]


@pytest.mark.asyncio
async def test_cross_scope_escape_and_source_hardlink_fail_before_copy(tmp_path):
    storage,data=await fixture(tmp_path)
    copier=LocalStoryboardCopier(storage)
    with pytest.raises(SqlVariantError,match='IO_FAILED'):
        await copier.copy({'ast_fixture':item(data,target_key='../outside.png')})
    source=storage._path(item(data)['object_key']);os.link(source,tmp_path/'owned-second-link.png')
    with pytest.raises(SqlVariantError,match='SOURCE_CHANGED'):await copier.copy({'ast_fixture':item(data)})


@pytest.mark.asyncio
async def test_symlinked_existing_target_parent_rejected_without_touching_outside(tmp_path):
    storage,data=await fixture(tmp_path)
    outside=tmp_path/'outside';outside.mkdir()
    parent=storage._path('workspaces/owned/projects/child/x.png').parent
    try:
        parent.symlink_to(outside,target_is_directory=True)
    except OSError:
        pytest.skip('Owned Windows fixture requires symlink privilege; no escalation or junction workaround')
    with pytest.raises(SqlVariantError,match='LINK_REJECTED'):
        await LocalStoryboardCopier(storage).copy({'ast_fixture':item(data)})
    assert list(outside.iterdir())==[]


@pytest.mark.asyncio
async def test_actual_background_io_is_drained_on_cancellation_and_keeps_owned_partial_bytes(tmp_path):
    storage,data=await fixture(tmp_path)
    entered,release=threading.Event(),threading.Event()
    class Paused(LocalStoryboardCopier):
        def _copy(self,items,stop):
            source,target=self._paths(item(data)['object_key'],item(data)['target_key'])
            target.write_bytes(data[:8]);entered.set();release.wait(10)
            if stop.is_set():raise SqlVariantError('SQL_VARIANT_COPY_CANCELLED')
            return super()._copy(items,stop)
    copier=Paused(storage);task=asyncio.create_task(copier.copy({'ast_fixture':item(data)}))
    assert await asyncio.to_thread(entered.wait,5)
    task.cancel();await asyncio.sleep(.02)
    assert not task.done()  # No return while owned IO may still mutate storage.
    release.set()
    with pytest.raises(asyncio.CancelledError):await task
    target=storage._path(item(data)['target_key'])
    assert target.read_bytes()==data[:8]
    with pytest.raises(SqlVariantError,match='TARGET_EXISTS'):
        await LocalStoryboardCopier(storage).copy({'ast_fixture':item(data)})


@pytest.mark.asyncio
@pytest.mark.parametrize('operation',['copy','verify'])
async def test_actual_reader_writer_is_drained_through_repeated_cancellation(tmp_path,monkeypatch,operation):
    from pathlib import Path
    storage,data=await fixture(tmp_path)
    copier=LocalStoryboardCopier(storage)
    copied=await copier.copy({'ast_fixture':item(data)}) if operation=='verify' else None
    path=storage._path(item(data)['target_key'] if operation=='verify' else item(data)['object_key'])
    entered,release,closed=threading.Event(),threading.Event(),threading.Event()
    original_open=Path.open
    def paused_open(open_path,*args,**kwargs):
        actual=original_open(open_path,*args,**kwargs)
        if open_path!=path or not args or args[0]!='rb':return actual
        class Reader:
            def __enter__(self):return self
            def __exit__(self,*exc):actual.close();closed.set()
            def fileno(self):return actual.fileno()
            def read(self,size=-1):
                value=actual.read(size);entered.set()
                assert release.wait(10),'owned read fixture timed out'
                return value
        return Reader()
    monkeypatch.setattr(Path,'open',paused_open)
    call=copier.copy({'ast_fixture':item(data)}) if operation=='copy' else copier.verify_all(copied)
    task=asyncio.create_task(call)
    try:
        assert await asyncio.to_thread(entered.wait,5)
        task.cancel();await asyncio.sleep(.02)
        task.cancel();await asyncio.sleep(.02)
        assert not task.done() and not closed.is_set()
        release.set()
        with pytest.raises(asyncio.CancelledError):await task
        assert closed.is_set()
        target=storage._path(item(data)['target_key'])
        saved=target.stat().st_size
        await asyncio.sleep(.03)
        assert target.stat().st_size==saved
    finally:
        release.set()
        await asyncio.gather(task,return_exceptions=True)
        await asyncio.to_thread(closed.wait,5)


@pytest.mark.parametrize('corruption',['crc','extension_only','truncated','pixel_bomb'])
def test_png_headers_are_magic_crc_and_dimensions_bound_without_claiming_decoded_qc(corruption):
    data=template_png()
    if corruption=='crc':data=data[:30]+bytes([data[30]^1])+data[31:]
    elif corruption=='extension_only':data=b'file.png is not image bytes'
    elif corruption=='truncated':data=data[:-1]
    else:
        import zlib
        block=struct.pack('>IIBBBBB',32768,32768,8,2,0,0,0)
        data=data[:16]+block+struct.pack('>I',zlib.crc32(b'IHDR'+block)&0xffffffff)+data[33:]
    with pytest.raises(SqlVariantError,match='MEDIA_INVALID'):image_dimensions(data,'image/png')


def test_magic_uses_mime_and_bounded_jpeg_webp_headers_not_filename_or_quality_claim():
    png=template_png()
    for mime in ('image/jpeg','image/webp'):
        with pytest.raises(SqlVariantError):image_dimensions(png,mime)
    # Explicit structural fixtures, not decoded frames/provider output.
    jpeg=b'\xff\xd8\xff\xc0'+struct.pack('>H',11)+b'\x08'+struct.pack('>HH',480,270)+b'\x01\x01\x11\x00'+b'\xff\xd9'
    assert image_dimensions(jpeg,'image/jpeg')==[270,480]
    chunk=b'\x2f'+((269)|479<<14).to_bytes(4,'little')+b'\x00'
    webp=b'RIFF'+struct.pack('<I',12+len(chunk))+b'WEBPVP8L'+struct.pack('<I',len(chunk))+chunk
    assert image_dimensions(webp,'image/webp')==[270,480]
