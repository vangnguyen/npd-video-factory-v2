"""Six real local encodes from a synthetic technology master; all human/ASR reviews are fixtures."""
import argparse,http.client,json,shutil,subprocess,sys,threading,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha,digest
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native import auto_edit_analysis as analysis,auto_edit_timeline as timeline
from services.windows_native.source_settings import configure
from services.windows_native.source_variants import SourceVariants,catalog
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.tests.test_human_identity import fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_variants_fixture'
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')
def read(root,master):
    store=Store(root);variants=SourceVariants(store,workspace_id=WORKSPACE);page=variants.page(master,limit=100)
    return {'master':store.get(master),'families':page,'children':[store.get(item['project_id']) for batch in page['items'] for item in batch['result']['variants']]}
def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not path.name.startswith('vf-native-fixture-variants-') or path.exists():raise ValueError('Fresh owned variant roots required')
    if root==destination:raise ValueError('Distinct roots required')
    out.mkdir(parents=True,exist_ok=False);root.mkdir();settings=config(root);store=Store(root);pipeline=Pipeline(settings)
    source=root/'explicit-synthetic-ai-education-tone.mp4'
    subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3',
        '-f','lavfi','-i','sine=frequency=880:duration=3','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p','-c:a','aac','-t','3',str(source)],check=True,timeout=30)
    asset=ingest_media(settings,source,'video/mp4','EXPLICIT SYNTHETIC AI EDUCATION SOURCE',rights_confirmed=True,illustration=False)
    project=store.create('AI education · explicit six-format fixture','','media',production_quality=True);project=store.append_media(project['id'],project['revision'],asset)
    example=json.loads((ROOT/'examples/technology-explainer.request.json').read_text(encoding='utf-8'))
    with store.transaction() as con:
        document=project['document'];document['media_analysis']=[saved_asr(asset)];document['niche']=example['niche']
        document['fixture_niche_configuration']={'source':'examples/technology-explainer.request.json','sha256':digest(example),'explicit_fixture':True,'native_channel_profile_selected_through_ui':False}
        con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document,ensure_ascii=False),project['id']));store.version(con,project['id'])
    for kind in ['auto_edit_analysis','media_frames']:
        current=store.get(project['id']);job=store.enqueue(project['id'],current['revision'],kind,uuid.uuid4().hex);claimed=store.claim()
        assert claimed['id']==job['id'];store.finish(claimed,result=pipeline.run(claimed,lambda _:None))
    current=analysis.view(store,project['id']);item=current['analyses'][0]['analysis']
    project=timeline.create(store,project['id'],current['revision'],{'analysis_id':item['analysis_id'],'transcript_id':item['transcript']['transcript_id']})
    project=configure(store,project['id'],project['revision'],{'expected_version':project['shot_timeline']['version'],'preview_mode':'final_effects'})
    before=store.get(project['id']);versions=store.versions(project['id']);source_files={path.relative_to(root).as_posix():file_sha(path) for folder in ['assets','originals'] for path in (root/folder).rglob('*') if path.is_file()}
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    server=LocalServer(0,settings,pipeline=pipeline,start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();requests=[];rendered=[]
    def request(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=30)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();headers=dict(response.getheaders());value=json.loads(response.read());connection.close()
        requests.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    try:
        profiles=request('GET','/api/auto-edit/variant-profiles');base=f'/api/projects/{project["id"]}/variants'
        body={'revision':project['revision'],'expected_version':project['shot_timeline']['version'],'profile_refs':[item['profile_ref'] for item in profiles['profiles']],
            'crop_policy':'center_attention','request_key':'native-six-format-playable-fixture-key'}
        batch=request('POST',base,body);assert len(batch['result']['variants'])==6
        replay=request('POST',base,body);assert replay['idempotent_replay'] and replay['batch_id']==batch['batch_id']
        for variant in batch['result']['variants']:
            child=store.get(variant['project_id']);assert child['approval'] is None and not child['jobs']
            server.previews.generate(child['id'],child['revision']);deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                preview=server.previews.status(child['id'])
                if preview['status'] not in ['QUEUED','RUNNING']:break
                time.sleep(.1)
            assert preview['status']=='READY',preview
            request('POST',f'/api/projects/{child["id"]}/approve',{'revision':child['revision'],'reviewer':'EXPLICIT AUTOMATED FIXTURE — NOT OWNER UAT','acknowledged':True})
            job=request('POST',f'/api/projects/{child["id"]}/jobs',{'revision':child['revision'],'kind':'render','request_key':'native-variant-render-'+child['id']})
            assert server.runner.run_one();job=store.get_job(job['id']);assert job['status']=='succeeded' and job['result']['qc']['passed'],job.get('error')
            final_folder=root/'jobs'/job['id'];manifest=json.loads((final_folder/'timeline-render.json').read_bytes());probe=json.loads((final_folder/'ffprobe.json').read_bytes())
            video=next(stream for stream in probe['streams'] if stream['codec_type']=='video');profile=variant['profile']
            assert (video['width'],video['height'])==(profile['width'],profile['height']);assert manifest['metadata']['niche']=='technology'
            final_manifest=json.loads((final_folder/'render-manifest.json').read_bytes())
            assert final_manifest['canonical_timeline']==child['document']['canonical_timeline']
            assert final_manifest['external_provider_calls']==0 and final_manifest['publishing_allowed'] is False
            folder=out/profile['profile_ref'];folder.mkdir()
            for name in ['final.mp4','timeline.json','timeline-render.json','subtitles.json','audio-analysis.json','render-manifest.json','cost.json','qc-report.json','ffprobe.json','checkpoint-render.json']:
                shutil.copyfile(final_folder/name,folder/name)
            shutil.copyfile(server.previews.video_path(child['id'],preview['timeline_version']),folder/'preview.mp4')
            rendered.append({'profile':profile,'project_id':child['id'],'job_id':job['id'],'final_sha256':file_sha(folder/'final.mp4'),'preview_sha256':file_sha(folder/'preview.mp4'),
                'timeline_sha256':child['document']['canonical_timeline']['sha256'],'canonical_pcm_sha256':file_sha(Path(manifest['audio']['mix_uri'])),
                'local_real_full_qc':True,'fixture_approval':True,'owner_uat':False,'external_provider_calls':0,'paid_operations':0})
            print(json.dumps({'rendered_profile':profile['profile_ref'],'qc':'PASS'}),flush=True)
        assert store.get(project['id'])==before and store.versions(project['id'])==versions
        assert all(file_sha(root/name)==sha for name,sha in source_files.items())
        assert len({item['canonical_pcm_sha256'] for item in rendered})==1
        history=request('GET',base+'?limit=1');assert history['items'][0]['batch_id']==batch['batch_id']
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    expected=read(root,project['id']);restarted=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root),'--project',project['id']],timeout=60));assert restarted==expected
    backup=create_backup(settings,out/'native-variant-backup.zip');restore=restore_backup(out/'native-variant-backup.zip',destination,expected_sha256=backup['sha256'])
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination),'--project',project['id']],timeout=60));assert restored==expected
    for item in rendered:assert file_sha(destination/'jobs'/item['job_id']/'final.mp4')==item['final_sha256']
    summary={'status':'PASS','master_project_id':project['id'],'source_root':str(root),'restore_root':str(destination),'formats':6,'local_real_full_qc_renders':6,
        'authenticated_native_requests':len(requests),'master_and_source_unchanged':True,'initial_analysis_and_frame_evidence_reused':True,'fresh_process_restore_exact':True,
        'fresh_root_backup_restore_exact':True,'same_canonical_pcm_across_formats':True,'audio_or_render_intermediate_cache_reused':False,
        'niche_configuration':'examples/technology-explainer.request.json','niche':'technology','native_channel_profile_ui_tested':False,
        'saved_asr_fixture':True,'real_semantic_vision':False,'real_subject_tracking':False,'actual_provider_calls':0,'paid_operations':0,'real_credentials_read':0,
        'owner_uat_accepted':False,'browser_acceptance':False,'real_publication':False,'render_after_restore_tested':False,'production_deployed':False,'variants':rendered,'source_files':source_files}
    for name,value in [('contract.json',summary),('variant-batch.json',batch),('requests.json',requests),('backup-receipt.json',backup),('restore-receipt.json',restore),('restored-state.json',restored)]:
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    print(json.dumps({'status':'PASS','formats':6,'qc_passed':6,'output':str(out)}),flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--read-root',type=Path);parser.add_argument('--project');args=parser.parse_args()
    if args.read_root:print(json.dumps(read(args.read_root,args.project),ensure_ascii=True))
    else:run(args)
