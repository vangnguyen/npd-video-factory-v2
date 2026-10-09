"""Real Windows long-path object roundtrip over a preserved accepted artifact."""
import argparse,asyncio,hashlib,json,os,re,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'apps/api'))
from app.object_storage import LocalObjectStorageProvider,artifact_object_key,filesystem_path,sha256_file
from app.publishing_artifact import bounded_copy,VerifiedPublishingArtifact

def write(path,value):
    with path.open('x',encoding='utf-8',newline='\n') as h:json.dump(value,h,ensure_ascii=False,indent=2);h.write('\n')

def owned(path,fresh=False):
    path=path.resolve()
    if os.name!='nt' or path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-object-storage-paths-state-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Explicit fresh owned Windows object-storage fixture required')
    return path

def deep(root):return root/('workspace-'+('a'*60))/('project-'+('b'*60))/('job-'+('c'*60))/('artifacts-'+('d'*60))/'objects'

async def reopen(args):
    state=owned(args.state_root);out=args.output.resolve();expected=json.loads((out/'expected-object.json').read_bytes());provider=LocalObjectStorageProvider(deep(state))
    assert await provider.exists(object_key=expected['object_key'])
    destination=state/'fresh-process-recovery.mp4';assert not destination.exists();await provider.download_file(object_key=expected['object_key'],destination=destination)
    assert destination.stat().st_size==expected['bytes'] and sha256_file(destination)==expected['sha256']
    write(out/'new-process-replay.json',{'same_portable_key_and_original_bytes':True,'sha256':expected['sha256'],'bytes':expected['bytes'],
        'current_config_credentials_network_required':False,'accepted_source_unchanged':sha256_file(Path(expected['accepted_source_path']))==expected['sha256'],
        'publishing_performed':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','fresh_process_object_recovery':True}))

async def run(args):
    state=owned(args.state_root,True);out=args.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external object-storage evidence required')
    out.mkdir(parents=True);state.mkdir();root=deep(state);provider=LocalObjectStorageProvider(root);await provider.ensure_ready()
    accepted=json.loads((ROOT/'docs/north-star/accepted-artifacts.json').read_bytes());assert len(accepted)==15
    original=accepted[0];source=Path(original['path']);expected_sha=original['sha256'];assert source.is_file() and sha256_file(source)==expected_sha and source.stat().st_size==original['bytes']
    key=artifact_object_key(workspace_id='wsp_long_path_preservation',project_id='explicit-recovery-project',job_id='original-accepted-artifact-roundtrip',filename='final.mp4')
    stored=await provider.put_file(object_key=key,path=source,content_type='video/mp4')
    destination=deep(state/'recovery')/'final.mp4';await provider.download_file(object_key=key,destination=destination)
    private=deep(state/'private')/'admitted.mp4';filesystem_path(private).parent.mkdir(parents=True);bounded_copy(provider,key,private,original['bytes'])
    artifact=VerifiedPublishingArtifact(private,expected_sha256=expected_sha,expected_size=original['bytes'],binding_sha256='a'*64)
    try:
        with source.open('rb') as h:assert artifact.read(0,min(1024,original['bytes']))==h.read(min(1024,original['bytes']))
        assert artifact.sha256==expected_sha
    finally:artifact.close()
    assert stored.object_key==key and '\\' not in key and sha256_file(destination)==sha256_file(private)==expected_sha and source.stat().st_size==stored.size_bytes==original['bytes']
    assert sha256_file(source)==expected_sha and len(str(provider.root))>300 and len(str(provider._path(key)))>400
    value={'object_key':key,'sha256':expected_sha,'bytes':original['bytes'],'accepted_source_path':str(source)};write(out/'expected-object.json',value)
    source_names=('apps/api/app/object_storage.py','apps/api/app/publishing_artifact.py','apps/api/tests/test_object_storage_paths.py','scripts/north_star_windows_object_storage.py')
    write(out/'evidence.json',{'schema_version':'windows-object-storage-long-path-rehearsal-v1',
        'source_sha256':{name:sha256_file(ROOT/name) for name in source_names},'accepted_artifact':value,'portable_key_unchanged':True,
        'local_root_characters':len(str(provider.root)),'stored_private_io_characters':len(str(provider._path(key))),
        'download_path_characters':len(str(destination)),'private_admission_path_characters':len(str(private)),
        'source_stored_download_private_exact_sha256':True,'private_bounded_checksum_range_admission':True,'source_never_replaced':True,
        'object_store_reopen_simulation':True,'machine_policy_changed':False,'s3_or_other_provider_tested':False,'external_provider_calls':0,'paid_operations':0,
        'new_render_or_full_media_qc_performed':False,'original_media_acceptance_reused_only_for_bytes':True,
        'owner_uat_accepted':False,'publishing_performed':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','long_root':len(str(provider.root)),'stored_io_length':len(str(provider._path(key))),'accepted_source_unchanged':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--state-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reopen',action='store_true');args=parser.parse_args()
    asyncio.run(reopen(args) if args.reopen else run(args))
