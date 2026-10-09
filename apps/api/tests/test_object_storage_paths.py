"""Real local bytes, atomic failure/concurrency and explicit S3 filesystem mocks."""
import asyncio,hashlib,os,pathlib,subprocess
from types import SimpleNamespace
import pytest
import app.object_storage as storage

def deep(base):
    return base/('workspace-'+('a'*60))/('project-'+('b'*60))/('job-'+('c'*60))/('artifacts-'+('d'*60))/'nguon-tieng-Viet'

@pytest.mark.asyncio
async def test_real_long_root_source_key_and_recovery_are_exact(tmp_path):
    root=deep(tmp_path/'objects');source=deep(tmp_path/'inputs')/'video.mp4'
    source_io=storage.filesystem_path(source);source_io.parent.mkdir(parents=True);raw=b'EXPLICIT LOCAL BYTES NOT A PLAYABLE VIDEO\0'*3000;source_io.write_bytes(raw)
    provider=storage.LocalObjectStorageProvider(root);await provider.ensure_ready()
    key=storage.artifact_object_key(workspace_id='wsp_long_path_fixture',project_id='p'*80,job_id='j'*80,filename='final.mp4')
    assert len(str(root))>260 and len(str(source))>260 and '\\' not in key and not key.startswith('\\\\?\\')
    result=await provider.put_file(object_key=key,path=source,content_type='video/mp4');assert result.checksum_sha256==hashlib.sha256(raw).hexdigest() and result.size_bytes==len(raw)
    assert result.object_key==key and result.content_type=='video/mp4' and await provider.exists(object_key=key)
    destination=deep(tmp_path/'recovery')/'final.mp4';await provider.download_file(object_key=key,destination=destination)
    assert storage.filesystem_path(destination).read_bytes()==raw and storage.sha256_file(destination)==result.checksum_sha256
    assert source_io.read_bytes()==raw and provider.root==root.resolve()
    assert not list(provider._io_root.glob('.readyz-*')) and not list(storage.filesystem_path(destination).parent.glob('*.tmp'))

@pytest.mark.asyncio
async def test_valid_768_byte_portable_key_is_not_reduced_to_windows_max_path(tmp_path):
    provider=storage.LocalObjectStorageProvider(tmp_path/'objects');await provider.ensure_ready();source=tmp_path/'source.txt';source.write_bytes(b'original')
    key='/'.join(['a'*127]*5+['b'*128]);assert len(key)==768
    saved=await provider.put_file(object_key=key,path=source);assert saved.object_key==key and await provider.exists(object_key=key)
    target=tmp_path/'readback.txt';await provider.download_file(object_key=key,destination=target);assert target.read_bytes()==b'original'
    overlong='/'.join(['a'*128]+['a'*127]*4+['b'*128]);assert len(overlong)==769
    with pytest.raises(ValueError,match='too long'):await provider.put_file(object_key=overlong,path=source)

@pytest.mark.parametrize('key',['../outside.txt','/outside.txt','nested/../../outside.txt','C:/outside.txt','nested\\outside.txt','\\\\?\\C:\\outside.txt'])
@pytest.mark.asyncio
async def test_traversal_and_windows_namespace_keys_cannot_escape(tmp_path,key):
    provider=storage.LocalObjectStorageProvider(tmp_path/'objects');source=tmp_path/'source.txt';source.write_bytes(b'safe')
    with pytest.raises(ValueError):await provider.put_file(object_key=key,path=source)
    assert source.read_bytes()==b'safe' and not (tmp_path/'outside.txt').exists()

def test_interrupted_copy_preserves_prior_object_and_cleans_only_owned_temporary(tmp_path,monkeypatch):
    source=tmp_path/'source';source.write_bytes(b'new');target=tmp_path/'target';target.write_bytes(b'prior');unrelated=tmp_path/'.unrelated.tmp';unrelated.write_bytes(b'keep')
    def fail(_input,output,*_args):output.write(b'partial');raise OSError('explicit disk failure fixture')
    monkeypatch.setattr(storage.shutil,'copyfileobj',fail)
    with pytest.raises(OSError):storage._copy_file(source,target)
    assert target.read_bytes()==b'prior' and source.read_bytes()==b'new' and unrelated.read_bytes()==b'keep'
    assert sorted(p.name for p in tmp_path.iterdir())==['.unrelated.tmp','source','target']

@pytest.mark.asyncio
async def test_parallel_copies_have_complete_objects_and_no_shared_temporary(tmp_path):
    first=tmp_path/'a';second=tmp_path/'b';first.write_bytes(b'A'*1000000);second.write_bytes(b'B'*1000000);target=tmp_path/'target'
    await asyncio.gather(asyncio.to_thread(storage._copy_file,first,target),asyncio.to_thread(storage._copy_file,second,target))
    assert target.read_bytes() in (first.read_bytes(),second.read_bytes()) and not list(tmp_path.glob('*.tmp'))

@pytest.mark.asyncio
async def test_missing_long_source_never_replaces_previous_object(tmp_path):
    provider=storage.LocalObjectStorageProvider(deep(tmp_path/'objects'));await provider.ensure_ready();source=tmp_path/'original.txt';source.write_bytes(b'prior')
    await provider.put_file(object_key='same/object.txt',path=source)
    with pytest.raises(FileNotFoundError):await provider.put_file(object_key='same/object.txt',path=deep(tmp_path/'missing')/'absent.txt')
    target=tmp_path/'target';await provider.download_file(object_key='same/object.txt',destination=target);assert target.read_bytes()==b'prior'

@pytest.mark.asyncio
async def test_object_receipt_describes_stored_bytes_when_source_changes_after_copy(tmp_path,monkeypatch):
    provider=storage.LocalObjectStorageProvider(tmp_path/'objects');await provider.ensure_ready();source=tmp_path/'source.txt';source.write_bytes(b'original stored bytes')
    copy=storage._copy_file
    def changing_source(input_path,destination):copy(input_path,destination);input_path.write_bytes(b'later changed input')
    monkeypatch.setattr(storage,'_copy_file',changing_source)
    receipt=await provider.put_file(object_key='bytes/original.txt',path=source)
    assert receipt.checksum_sha256==hashlib.sha256(b'original stored bytes').hexdigest() and receipt.size_bytes==len(b'original stored bytes')
    target=tmp_path/'download.txt';monkeypatch.setattr(storage,'_copy_file',copy);await provider.download_file(object_key=receipt.object_key,destination=target)
    assert target.read_bytes()==b'original stored bytes' and source.read_bytes()==b'later changed input'

@pytest.mark.asyncio
async def test_valid_255_character_download_filename_needs_no_overlong_temporary(tmp_path):
    provider=storage.LocalObjectStorageProvider(tmp_path/'objects');await provider.ensure_ready();source=tmp_path/'source.mp4';source.write_bytes(b'original local bytes')
    saved=await provider.put_file(object_key='same/final.mp4',path=source);filename='z'*251+'.mp4';assert len(filename)==255
    destination=tmp_path/filename;await provider.download_file(object_key=saved.object_key,destination=destination)
    assert storage.filesystem_path(destination).read_bytes()==source.read_bytes() and storage.sha256_file(destination)==saved.checksum_sha256

@pytest.mark.asyncio
async def test_resolved_symlink_cannot_write_outside_local_root(tmp_path):
    root=tmp_path/'objects';root.mkdir();outside=tmp_path/'outside';outside.mkdir();link=root/'escape'
    junction=False
    try:link.symlink_to(outside,target_is_directory=True)
    except OSError as error:
        if os.name!='nt':raise
        # Local NTFS junctions do not require changing machine symlink policy.
        assert link.absolute().parent==root.absolute() and outside.absolute().parent==tmp_path.absolute()
        result=subprocess.run(['cmd.exe','/d','/c','mklink','/J',str(link),str(outside)],cwd=tmp_path,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=10)
        if result.returncode:pytest.skip('Host cannot create either a local symlink or junction fixture')
        assert link.is_junction();junction=True
    try:
        provider=storage.LocalObjectStorageProvider(root);source=tmp_path/'safe';source.write_bytes(b'safe')
        with pytest.raises(ValueError,match='escaped'):await provider.put_file(object_key='escape/out.txt',path=source)
        assert not (outside/'out.txt').exists()
    finally:
        assert link.absolute().parent==root.absolute()
        if junction:link.rmdir()
        else:link.unlink()
    assert outside.is_dir()

@pytest.mark.asyncio
async def test_s3_explicit_sdk_mock_receives_portable_key_and_long_private_io_names(tmp_path):
    source=deep(tmp_path/'input')/'voice.wav';source_io=storage.filesystem_path(source);source_io.parent.mkdir(parents=True);source_io.write_bytes(b'EXPLICIT MOCK AUDIO BYTES')
    calls=[];objects={}
    def upload(filename,bucket,key,ExtraArgs):
        calls.append(('upload',bucket,key));objects[key]=pathlib.Path(filename).read_bytes();assert ExtraArgs['Metadata']['sha256']==hashlib.sha256(objects[key]).hexdigest()
    def download(bucket,key,filename):calls.append(('download',bucket,key));pathlib.Path(filename).write_bytes(objects[key])
    provider=storage.S3ObjectStorageProvider.__new__(storage.S3ObjectStorageProvider);provider.bucket='explicit-sdk-mock';provider.client=SimpleNamespace(upload_file=upload,download_file=download)
    key='workspaces/wsp_fixture/audio/voice.wav';saved=await provider.put_file(object_key=key,path=source)
    target=deep(tmp_path/'recovery')/'voice.wav';await provider.download_file(object_key=key,destination=target)
    assert calls==[('upload','explicit-sdk-mock',key),('download','explicit-sdk-mock',key)] and saved.object_key==key and storage.filesystem_path(target).read_bytes()==source_io.read_bytes()

@pytest.mark.parametrize('raw,expected',[
    (r'C:/objects/a/../b/file.txt',r'\\?\C:\objects\b\file.txt'),
    (r'\\server\share\a\..\b\file.txt',r'\\?\UNC\server\share\b\file.txt'),
    (r'\\?\C:\objects\b\file.txt',r'\\?\C:\objects\b\file.txt'),
    (r'\\?\UNC\server\share\file.txt',r'\\?\UNC\server\share\file.txt')])
def test_extended_windows_names_normalize_before_prefix_without_unc_network(raw,expected):
    assert storage.extended_windows_path(raw)==expected

@pytest.mark.parametrize('raw',[r'\\.\PhysicalDrive0',r'\\?\GLOBALROOT\Device\HarddiskVolume1\file',r'C:relative.txt','relative.txt'])
def test_device_and_relative_names_are_not_extended_filesystem_paths(raw):
    with pytest.raises(ValueError):storage.extended_windows_path(raw)

@pytest.mark.asyncio
async def test_long_local_object_still_passes_bounded_private_read_and_exact_range_checks(tmp_path):
    from app.publishing_artifact import bounded_copy,VerifiedPublishingArtifact,ArtifactAdmissionError
    provider=storage.LocalObjectStorageProvider(deep(tmp_path/'objects'));await provider.ensure_ready()
    source=tmp_path/'explicit-header-only-not-playable.mp4';raw=b'\x00\x00\x00\x18ftypisom'+b'EXPLICIT RANGE BYTES'*20000;source.write_bytes(raw)
    key='workspaces/wsp_fixture/projects/project_fixture/jobs/job_fixture/final.mp4';saved=await provider.put_file(object_key=key,path=source)
    target=deep(tmp_path/'private')/'artifact.mp4';storage.filesystem_path(target).parent.mkdir(parents=True)
    bounded_copy(provider,key,target,len(raw));assert storage.filesystem_path(target).read_bytes()==raw
    snapshot=VerifiedPublishingArtifact(target,expected_sha256=saved.checksum_sha256,expected_size=len(raw),binding_sha256='a'*64)
    try:
        assert snapshot.read(260000,10000)==raw[260000:270000]
        with storage.filesystem_path(target).open('r+b') as handle:handle.seek(260010);handle.write(b'!')
        with pytest.raises(ArtifactAdmissionError,match='CHANGED'):snapshot.read(260000,10000)
    finally:snapshot.close()
    assert source.read_bytes()==raw and storage.sha256_file(provider._path(key))==saved.checksum_sha256

def test_long_guard_still_refuses_parent_traversal_and_multiple_hard_links(tmp_path):
    from app.publishing_artifact import guarded_path,ArtifactAdmissionError
    directory=storage.filesystem_path(deep(tmp_path/'private'));directory.mkdir(parents=True);source=directory/'one.mp4';source.write_bytes(b'explicit fixture')
    with pytest.raises(ArtifactAdmissionError,match='PATH_INVALID'):guarded_path(deep(tmp_path/'private')/'..'/'one.mp4')
    alias=directory/'two.mp4';os.link(source,alias)
    with pytest.raises(ArtifactAdmissionError,match='PATH_INVALID'):guarded_path(source)
    assert source.read_bytes()==alias.read_bytes()==b'explicit fixture'
