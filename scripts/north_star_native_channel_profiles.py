"""Two configured niches through Native HTTP and the same real local Source engine."""
import argparse,http.client,json,re,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native import auto_edit_analysis as analysis
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_channel_profiles_fixture'
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
def state(root):
    store=Store(root);return {'projects':[store.get(project['id']) for project in store.list()],
        'versions':{project['id']:store.versions(project['id']) for project in store.list()}}
def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-channel-profiles-[a-z0-9-]+',path.name) or path.exists():raise ValueError('Fresh owned channel-profile roots required')
    if root==destination:raise ValueError('Distinct roots required')
    out.mkdir(parents=True,exist_ok=False);root.mkdir();settings=config(root);pipeline=Pipeline(settings);store=Store(root)
    source=root/'explicit-synthetic-profile-source.mp4'
    subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3',
        '-f','lavfi','-i','sine=frequency=880:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(source)],check=True,timeout=30)
    source_sha=file_sha(source);raw,registry=fixture('owner',workspace=WORKSPACE)
    access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=pipeline,start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];rendered=[]
    def request(method,path,body=None,status=200,binary=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=binary if binary is not None else json.dumps(body) if body is not None else None,
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf,**(headers or {})})
        response=connection.getresponse();value=json.loads(response.read());metadata=dict(response.getheaders());connection.close()
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value);assert metadata['Cache-Control']=='no-store';return value
    try:
        catalog=request('GET','/api/channel-profiles');assert len(catalog['selections'])==2
        for selection in catalog['selections']:
            profile=selection['profile'];project=request('POST','/api/projects',{'name':profile['name']+' · EXPLICIT SYNTHETIC FIXTURE','prompt':'','input_kind':'media',
                'channel_profile_ref':profile['profile_ref']},status=201)
            frozen=project['document']['channel_profile'];assert frozen['profile']==profile and project['document']['niche']==profile['niche_profile']['niche']
            assert project['approval'] is None and not project['jobs']
            project=request('POST',f'/api/projects/{project["id"]}/media',status=201,binary=source.read_bytes(),headers={'Content-Type':'video/mp4',
                'X-VF-Revision':str(project['revision']),'X-VF-Rights':'confirmed','X-VF-Illustration':'false','X-VF-Filename':'explicit-profile-source.mp4'})
            asset=project['document']['assets'][0];assert asset['sha256']==source_sha
            # Import an explicitly saved ASR fixture, never claim transcript inference on tone.
            job=store.enqueue(project['id'],project['revision'],'asr',uuid.uuid4().hex);claimed=store.claim();assert claimed['id']==job['id']
            store.finish(claimed,result={'media_analysis':[saved_asr(asset)]})
            for kind in ['auto_edit_analysis','media_frames']:
                current=store.get(project['id']);job=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':current['revision'],'kind':kind,'request_key':uuid.uuid4().hex})
                assert server.runner.run_one();finished=store.get_job(job['id']);assert finished['status']=='succeeded',finished.get('error')
            current=analysis.view(store,project['id']);measured=current['analyses'][0]['analysis']
            project=request('POST',f'/api/projects/{project["id"]}/auto-edit/timeline',{'revision':current['revision'],'action':'create','payload':{
                'analysis_id':measured['analysis_id'],'transcript_id':measured['transcript']['transcript_id']}})
            metadata=project['document']['canonical_timeline']['snapshot']['metadata'];assert metadata['channel_selection_sha256']==frozen['selection_sha256']
            assert metadata['subtitle_template_ref']==profile['source_preferences']['subtitle_template_ref'] and metadata['source_preview_mode']=='final_effects'
            denied=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex},status=409)
            assert denied['code']=='AUTO_EDIT_HUMAN_APPROVAL_REQUIRED_BEFORE_RENDER'
            request('POST',f'/api/projects/{project["id"]}/preview',{'revision':project['revision'],'action':'generate'});deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                preview=server.previews.status(project['id'])
                if preview['status'] not in ['QUEUED','RUNNING']:break
                time.sleep(.1)
            assert preview['status']=='READY',preview
            request('POST',f'/api/projects/{project["id"]}/approve',{'revision':project['revision'],'reviewer':'EXPLICIT CHANNEL PROFILE FIXTURE — NOT OWNER UAT','acknowledged':True})
            job=request('POST',f'/api/projects/{project["id"]}/jobs',{'revision':project['revision'],'kind':'render','request_key':uuid.uuid4().hex})
            with patch('services.windows_native.pipeline.verify_runtime',side_effect=AssertionError('No locked TTS/provider dispatch')):assert server.runner.run_one()
            job=store.get_job(job['id']);assert job['status']=='succeeded' and job['result']['qc']['passed'],job.get('error')
            final_folder=root/'jobs'/job['id'];manifest=json.loads((final_folder/'timeline-render.json').read_bytes());audio=json.loads((final_folder/'audio-analysis.json').read_bytes())
            assert manifest['metadata']['niche']==profile['niche_profile']['niche'] and manifest['brand']['name']==frozen['brand_template']['brand']['name']
            assert audio['intermediate_cache']['status']=='hit' and preview['manifest']['audio_intermediate_cache']['status']=='built'
            final_manifest=json.loads((final_folder/'render-manifest.json').read_bytes());assert final_manifest['canonical_timeline']==project['document']['canonical_timeline']
            current=store.get(project['id']);assert current['document']['channel_profile']==frozen and current['document']==project['document']
            folder=out/profile['profile_ref'];folder.mkdir()
            for name in ['final.mp4','qc-report.json','ffprobe.json','render-manifest.json','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json','cost.json','checkpoint-render.json']:
                shutil.copyfile(final_folder/name,folder/name)
            shutil.copyfile(server.previews.video_path(project['id'],preview['timeline_version']),folder/'preview.mp4')
            with (folder/'project.json').open('x',encoding='utf-8') as file:json.dump(current,file,ensure_ascii=False,indent=2)
            rendered.append({'profile_ref':profile['profile_ref'],'niche':profile['niche_profile']['niche'],'project_id':project['id'],'job_id':job['id'],
                'selection_sha256':frozen['selection_sha256'],'final_sha256':file_sha(folder/'final.mp4'),'actual_local_full_qc':True,
                'actual_provider_calls':0,'saved_asr_fixture':True,'fixture_approval':True,'owner_uat':False})
            print(json.dumps({'profile':profile['profile_ref'],'niche':profile['niche_profile']['niche'],'qc':'PASS'}),flush=True)
        assert file_sha(source)==source_sha
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    before=state(root);restarted=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root)],timeout=60));assert restarted==before
    backup=create_backup(settings,out/'native-channel-backup.zip');restore=restore_backup(out/'native-channel-backup.zip',destination,expected_sha256=backup['sha256'])
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination)],timeout=60));assert restored==before
    for value in rendered:assert file_sha(destination/'jobs'/value['job_id']/'final.mp4')==value['final_sha256']
    summary={'status':'PASS','configured_niches':2,'http_selected_profiles':True,'same_source_engine':True,'manual_niche_seed':False,
        'local_real_full_qc_renders':2,'local_real_effects_previews':2,'authenticated_requests':len(requests),'source_unchanged':True,'frozen_profiles_unchanged':True,
        'fresh_process_exact':True,'fresh_root_restore_exact':True,'actual_provider_calls':0,'paid_operations':0,'real_credentials_read':0,
        'browser_acceptance':False,'owner_uat_accepted':False,'narrated_mode_a_render_acceptance':False,'published':False,'production_deployed':False,'rendered':rendered}
    for name,value in [('contract.json',summary),('catalog.json',catalog),('requests.json',requests),('backup.json',backup),('restore.json',restore),('restored-state.json',restored)]:
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    print(json.dumps(summary),flush=True)
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--read-root',type=Path)
    args=parser.parse_args()
    if args.read_root:print(json.dumps(state(args.read_root),ensure_ascii=True))
    else:run(args)
