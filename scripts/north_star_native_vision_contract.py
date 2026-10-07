"""Real local video/CPU frame evidence + explicit structured Vision fixtures, never inference."""
import argparse,http.client,json,subprocess,sys,threading,uuid
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.access import NativeAccess
from services.windows_native.auto_edit_analysis import view as analysis_view
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.media import ingest_media
from services.windows_native.media_frame_analysis import view,frame_path
from services.windows_native.pipeline import Config,Pipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_auto_edit_analysis import saved_asr
from services.windows_native.tests.test_human_identity import fixture
from services.windows_native.vision import NativeVision
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier

WORKSPACE='wsp_native_vision_fixture'
def config(root):
    absent=root.parent/(root.name+'-absent-secrets')
    return Config(data_root=root,secret_file=absent/'absent-openai.env',assemblyai_secret_file=absent/'absent-asr.dpapi')

def read(root,project):
    store=Store(root);vision=NativeVision(store,config(root),workspace_id=WORKSPACE);page=vision.page(project,limit=100)
    return {'project':store.get(project),'measured_frames':view(store,project),'auto_edit':analysis_view(store,project),'vision':page,
        'details':[vision.get(project,row['vision_id']) for row in page['items']]}

def run(args):
    root=args.data_root.resolve();destination=args.restore_root.resolve();out=args.output.resolve()
    for path in [root,destination]:
        if path.parent!=Path('C:/') or not path.name.startswith('vf-native-fixture-vision-') or path.exists():raise ValueError('Fresh owned Vision fixture paths required')
    if root==destination:raise ValueError('Distinct fresh source/restore roots required')
    out.mkdir(parents=True,exist_ok=False);root.mkdir();settings=config(root);store=Store(root);pipeline=Pipeline(settings)
    source=root/'explicit-synthetic-testsrc-tone.mp4'
    subprocess.run([str(settings.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=6',
        '-f','lavfi','-i','sine=frequency=440:duration=3','-af','adelay=1000,apad=whole_dur=6','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',
        '-c:a','aac','-t','6',str(source)],check=True,timeout=30)
    asset=ingest_media(settings,source,'video/mp4','EXPLICIT SYNTHETIC VIDEO WITH TONE',rights_confirmed=True,illustration=False)
    project=store.create('Generic AI education · explicit Vision contract','','media',production_quality=True)
    project=store.append_media(project['id'],project['revision'],asset)
    with store.transaction() as con:
        document=project['document'];document['media_analysis']=[saved_asr(asset)]
        con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',(json.dumps(document,ensure_ascii=False),project['id']));store.version(con,project['id'])
    for kind in ['auto_edit_analysis','media_frames']:
        current=store.get(project['id']);queued=store.enqueue(project['id'],current['revision'],kind,uuid.uuid4().hex);claimed=store.claim()
        assert claimed['id']==queued['id'];store.finish(claimed,result=pipeline.run(claimed,lambda _:None))
    project=store.get(project['id']);before=read(root,project['id']);frames=before['measured_frames'];assert frames['observations']
    files={path.relative_to(root).as_posix():file_sha(path) for path in root.rglob('*') if path.is_file() and path.suffix not in ['.sqlite3'] and '-wal' not in path.name and '-shm' not in path.name}
    raw,registry=fixture('owner',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),WORKSPACE)
    class NoDispatch:
        def run(self,*_):raise AssertionError('No new generic pipeline/provider requests')
    server=LocalServer(0,settings,pipeline=NoDispatch(),start_worker=False,access=access);cookie,session=access.login(raw)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();calls=[]
    def request(method,path,body=None):
        connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=20)
        connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        response=connection.getresponse();headers=dict(response.getheaders());value=json.loads(response.read());connection.close()
        calls.append({'method':method,'path':path,'status':response.status});assert response.status==200,(response.status,value);assert headers['Cache-Control']=='no-store';return value
    try:
        base=f'/api/projects/{project["id"]}/vision';body={'revision':project['revision'],'observation_ids':[frames['observations'][0]['observation_id']],
            'provider_mode':'fixture','fixture_acknowledged':True,'request_key':'native-real-frame-semantic-fixture-key'}
        row=request('POST',base,body);repeat=request('POST',base,body);assert repeat['idempotent_replay'] and repeat['vision_id']==row['vision_id']
        route=base+'/'+row['vision_id'];done=request('POST',route+'/process',{'expected_fingerprint':row['request_fingerprint']})
        assert done['status']=='succeeded' and done['result']['mock'] and not done['result']['semantic_inference_performed']
        assert request('POST',route+'/process',{'expected_fingerprint':row['request_fingerprint']})==done
        result=done['result']['assets'][0];assert result['scenes'] and done['snapshot']['sources'][0]['transcript_ref']
        assert all(frame['evidence_frame_reference']==sample['reference'] for frame,sample in zip(result['frames'],frames['observations'][0]['frames']))
        assert all(plan['fallback']=='center_crop' and plan['confidence']==0 and plan['needs_attention'] for plan in result['reframe_plans'])
        assert not result['subject_tracks'] and result['broll_relevance'] is None
        official=request('POST',base,{**body,'provider_mode':'official','fixture_acknowledged':False,'request_key':'native-official-vision-not-configured-key'})
        assert official['status']=='not_configured' and official['result'] is None
        cancelled=request('POST',base,{**body,'request_key':'native-cancelled-vision-fixture-key'})
        cancelled=request('POST',base+'/'+cancelled['vision_id']+'/cancel',{'expected_fingerprint':cancelled['request_fingerprint']});assert cancelled['status']=='cancelled'
        first=request('GET',base+'?limit=2');second=request('GET',base+'?limit=2&cursor='+quote(first['next_cursor']))
        assert len(first['items'])==2 and len(second['items'])==1 and second['next_cursor'] is None
        assert server.store.get(project['id'])==before['project'] and view(server.store,project['id'])==before['measured_frames']
        assert analysis_view(server.store,project['id'])==before['auto_edit'] and all(file_sha(root/name)==sha for name,sha in files.items())
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    expected=read(root,project['id']);restored_process=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(root),'--project',project['id']],timeout=60));assert restored_process==expected
    backup=create_backup(settings,out/'native-vision-backup.zip');restore=restore_backup(out/'native-vision-backup.zip',destination,expected_sha256=backup['sha256'])
    restored=json.loads(subprocess.check_output([sys.executable,str(Path(__file__).resolve()),'--read-root',str(destination),'--project',project['id']],timeout=60));assert restored==expected
    for name,sha in files.items():assert file_sha(root/name)==sha and file_sha(destination/name)==sha
    for frame in frames['observations'][0]['frames']:assert file_sha(frame_path(destination,frame))==frame['sha256']
    outputs={'measured-cpu-frames.json':frames,'auto-edit-analysis.json':before['auto_edit'],'structured-semantic-fixture.json':done,'official-unavailable.json':official,
        'history-pages.json':[first,second],'requests.json':calls,'backup-receipt.json':backup,'restore-receipt.json':restore,'restored-state.json':restored,
        'contract.json':{'status':'PASS','source_root':str(root),'restore_root':str(destination),'project_id':project['id'],'authenticated_native_requests':len(calls),
            'real_local_video_and_frames':True,'saved_asr_is_explicit_fixture':True,'semantic_predictions_are_explicit_fixture':True,'semantic_model_saw_pixels':False,
            'fresh_process_exact_restore':True,'fresh_root_backup_restore_exact':True,'cpu_facts_and_canonical_project_unchanged':True,'source_files_unchanged':True,
            'real_provider_calls':0,'paid_calls':0,'credentials_read':0,'owner_uat_accepted':False,'tracking_available':False,'automatic_planning_eligible':False,
            'official_state':'NOT_CONFIGURED','production_deployed':False,'source_file_hashes':files}}
    for name,value in outputs.items():
        with (out/name).open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2)
    print(json.dumps({'status':'PASS','requests':len(calls),'real_frames':len(result['frames']),'fixture_scenes':len(result['scenes']),'output':str(out)}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path);parser.add_argument('--restore-root',type=Path);parser.add_argument('--output',type=Path)
    parser.add_argument('--read-root',type=Path);parser.add_argument('--project');args=parser.parse_args()
    if args.read_root:print(json.dumps(read(args.read_root,args.project),ensure_ascii=True))
    else:run(args)
