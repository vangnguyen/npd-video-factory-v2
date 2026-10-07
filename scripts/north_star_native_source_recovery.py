"""Offline checksum restore -> new source edit/preview/fixture approval/render/QC."""
import argparse,http.client,json,os,re,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup,guard
from services.windows_native.contracts import file_sha,digest
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.source_variants import SourceVariants
from services.windows_native import source_render
from services.windows_native.source_preview import resolve_assets
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_variants_fixture'
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
def immutable_files(root):
    return {path.relative_to(root).as_posix():file_sha(path) for folder in ['assets','originals','jobs','shot-previews'] for path in (root/folder).rglob('*') if path.is_file()}
def state(root,master):
    store=Store(root);page=SourceVariants(store,workspace_id=WORKSPACE).page(master,limit=100)
    return {'master':store.get(master),'families':page,'children':[store.get(item['project_id']) for batch in page['items'] for item in batch['result']['variants']]}
def run(args):
    seed=args.seed_root.resolve();root=args.data_root.resolve();offline=seed.with_name(seed.name+'-offline');out=args.output.resolve()
    for path in [seed,root,offline]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-source-recovery-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh explicitly owned recovery roots required')
    if len({seed,root,offline})!=3:raise ValueError('Distinct fixture roots required')
    if not re.fullmatch(r'[a-f0-9]{64}',args.expected_sha256) or not re.fullmatch(r'[a-f0-9]{32}',args.master_project_id):raise ValueError('Exact trusted checksum/project required')
    out.mkdir(parents=True,exist_ok=False)
    initial=restore_backup(args.backup,seed,expected_sha256=args.expected_sha256);before=state(seed,args.master_project_id);files=immutable_files(seed)
    selected=next(item for batch in before['families']['items'] for item in batch['result']['variants'] if item['profile']['profile_ref']=='youtube-shorts@1');identifier=selected['project_id']
    second=create_backup(config(seed),out/'owned-recovery-seed.zip');restored=restore_backup(out/'owned-recovery-seed.zip',root,expected_sha256=second['sha256'])
    assert state(root,args.master_project_id)==before and immutable_files(root)==files
    # Retain the newly created seed intact, but make its old operational root unavailable.
    guard(seed,exists=True);guard(offline);os.rename(seed,offline);assert not seed.exists() and offline.is_dir()
    settings=config(root);store=Store(root);pipeline=Pipeline(settings);raw,registry=fixture('owner',workspace=WORKSPACE)
    access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=pipeline,start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];commands=[]
    def request(method,path,body=None,status=200):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();value=json.loads(response.read());headers=dict(response.getheaders());connection.close()
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    try:
        project=request('GET',f'/api/projects/{identifier}');before_selected=store.get(identifier);before_versions=store.versions(identifier)
        assert project['approval'] is not None and project['document']['canonical_timeline']['snapshot']['metadata']['source_preview_mode']=='final_effects'
        state_timeline=project['document']['canonical_timeline'];track=next(track for track in state_timeline['snapshot']['tracks'] if track['kind']=='subtitles')
        edited=request('POST',f'/api/projects/{identifier}/auto-edit/timeline',{'revision':project['revision'],'action':'edit','payload':{
            'expected_version':state_timeline['version'],'operations':[{'type':'set_track_state','track_id':track['track_id'],'locked':True}]}})
        assert edited['approval'] is None and edited['revision']==project['revision']+1 and edited['document']['canonical_timeline']!=state_timeline
        denied=request('POST',f'/api/projects/{identifier}/jobs',{'revision':edited['revision'],'kind':'render','request_key':'recovery-unapproved-fixture-'+identifier},status=409)
        assert denied['code']=='AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'
        queued=request('POST',f'/api/projects/{identifier}/preview',{'revision':edited['revision'],'action':'generate'});deadline=time.monotonic()+180
        while time.monotonic()<deadline:
            preview=server.previews.status(identifier)
            if preview['status'] not in ['QUEUED','RUNNING']:break
            time.sleep(.1)
        assert preview['status']=='READY' and preview['id']!=project['approval']['reviewed_preview'].get('id'),preview
        request('POST',f'/api/projects/{identifier}/approve',{'revision':edited['revision'],'reviewer':'EXPLICIT RECOVERY FIXTURE — NOT OWNER UAT','acknowledged':True})
        job=request('POST',f'/api/projects/{identifier}/jobs',{'revision':edited['revision'],'kind':'render','request_key':'recovery-render-fixture-'+identifier})
        original=source_render.command_run
        def record(command,*args,**kwargs):commands.append([str(value) for value in command]);return original(command,*args,**kwargs)
        with patch.object(source_render,'command_run',side_effect=record),patch('services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No locked TTS/provider dispatch')):
            assert server.runner.run_one()
        job=store.get_job(job['id']);assert job['status']=='succeeded' and job['result']['qc']['passed'],job.get('error')
        folder=root/'jobs'/job['id'];manifest=json.loads((folder/'render-manifest.json').read_bytes());render=json.loads((folder/'timeline-render.json').read_bytes())
        audio=json.loads((folder/'audio-analysis.json').read_bytes());assert manifest['canonical_timeline']==edited['document']['canonical_timeline']
        assert audio['intermediate_cache']['status']=='hit' and preview['manifest']['audio_intermediate_cache']['status']=='built'
        assert audio['intermediate_cache']['pcm']['sha256']==preview['manifest']['audio_intermediate_cache']['pcm']['sha256']
        _,assets=resolve_assets(settings,store.get(identifier));assert all(root in path.resolve().parents for _,path in assets.values())
        assert root in Path(render['audio']['mix_uri']).resolve().parents
        for command in commands:
            for index,value in enumerate(command[:-1]):
                if value=='-i':assert root in Path(command[index+1]).resolve().parents
        assert manifest['external_provider_calls']==0 and manifest['tts_calls']==0 and manifest['publishing_allowed'] is False
        assert job['result']['qc']['human_final_video_accepted'] is False
        after=state(root,args.master_project_id);assert after['master']==before['master'] and after['families']==before['families']
        assert all(child==next(old for old in before['children'] if old['id']==child['id']) for child in after['children'] if child['id']!=identifier)
        assert store.versions(identifier)[1:]==before_versions
        assert all(file_sha(root/name)==sha for name,sha in files.items()) and all(file_sha(offline/name)==sha for name,sha in files.items())
        for name in ['final.mp4','qc-report.json','ffprobe.json','render-manifest.json','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json','cost.json','checkpoint-render.json']:
            shutil.copyfile(folder/name,out/name)
        shutil.copyfile(server.previews.video_path(identifier,preview['timeline_version']),out/'preview.mp4')
        final_hash=file_sha(out/'final.mp4')
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    exported=state(root,args.master_project_id);restarted=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root),'--master-project-id',args.master_project_id],timeout=60));assert restarted==exported
    summary={'status':'PASS','restored_root':str(root),'seed_root_unavailable':not seed.exists(),'retained_seed':str(offline),
        'master_project_id':args.master_project_id,'edited_project_id':identifier,'new_final_job_id':job['id'],'new_final_sha256':final_hash,
        'new_preview_after_restore':True,'new_canonical_edit_after_restore':True,'unapproved_render_blocked':True,'fixture_approval_required':True,
        'new_render_after_restore_tested':True,'new_render_local_real_full_qc':True,'render_sources_all_restored_root':True,
        'fresh_process_state_exact':True,'old_media_and_history_unchanged':True,'master_and_other_variants_unchanged':True,
        'historical_absolute_result_paths_rewritten':False,'authenticated_native_requests':len(requests),'provider_calls':0,'paid_operations':0,
        'real_credentials_read':0,'owner_uat_accepted':False,'browser_acceptance':False,'published':False,'production_deployed':False}
    for name,value in [('contract.json',summary),('initial-restore.json',initial),('seed-backup.json',second),('operational-restore.json',restored),
        ('requests.json',requests),('commands.json',commands),('before.json',before),('after.json',exported),('preserved-files.json',files),('preview-evidence.json',preview)]:
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    print(json.dumps(summary),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--backup',type=Path);parser.add_argument('--expected-sha256');parser.add_argument('--seed-root',type=Path)
    parser.add_argument('--data-root',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--master-project-id');parser.add_argument('--read-root',type=Path)
    args=parser.parse_args()
    if args.read_root:print(json.dumps(state(args.read_root,args.master_project_id),ensure_ascii=True))
    else:run(args)
