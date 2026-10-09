"""Retained signed Native B-roll rehearsal: real media, explicit ASR/Vision mocks."""
import argparse,copy,http.client,json,re,sys,threading,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import MediaSignals
from services.windows_native.tests.test_source_broll import SourceBrollTests
from services.windows_native.tests.test_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.pipeline import Pipeline
from services.windows_native.auto_edit_timeline import view
from services.windows_native.auto_edit_analysis import asset_reference
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.vision_registry import NativeVisionFactory
from services.windows_native.costs import CostLedger
from services.windows_native.contracts import file_sha,digest
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write,WORKSPACE
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-source-broll-vision-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned Source B-roll Vision fixture required')
    return path

def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        expected=json.loads((out/'expected-projects.json').read_bytes())
        for project in expected:assert view(server.store,project['id'])==project
        row=json.loads((out/'original-vision.json').read_bytes());assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        before=json.loads((out/'expected-journals.json').read_bytes());assert journals(server.store)==before
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
        assert server.official_vision.recover()==0 and not server.runner.run_one() and database_status(server.store.db)['active_operations']==0
        assert journals(server.store)==before
        for asset,value in json.loads((out/'source-hashes.json').read_bytes()).items():assert file_sha(root/'assets'/asset)==value
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all_original_vision_plan_versions_projects_journals_source_bytes_exact':True,'keyless_disabled_provider_history':True,
        'provider_consent_renewed':False,'provider_retry_or_dispatch':False,'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
    state=owned(args.state_root,'state',True);restore=owned(args.restore_root,'restore',True);private=owned(args.private_root,'private',True);out=args.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);config=config_for(state);store=Store(state);raw,identity=access();identity.bind_root(state)
    # Explicit retained fixture helpers: spoken words/semantic scene signals are
    # saved mock evidence. The source is a real three-second test pattern/tone.
    fixture=SourceBrollTests();fixture.root=state;fixture.config=config;fixture.store=store
    fixture.project=store.create('Technology AI educational SOURCE B-roll fixture','','media')
    fixture.asset={'id':uuid.uuid4().hex+'.mp4','kind':'video','filename':'EXPLICIT SYNTHETIC test pattern and tone.mp4','sha256':'a'*64,
        'rights_confirmed':True,'illustration':False,'duration_seconds':3.,'width':320,'height':240,'has_audio':True,'explicit_fixture':True}
    fixture.project=store.append_media(fixture.project['id'],fixture.project['revision'],fixture.asset)
    fixture.metadata=MediaMetadata(media_kind='video',detected_content_type='video/mp4',duration_seconds=3.,width=320,height=240,fps=30,video_codec='h264',audio_codec='aac')
    fixture.signals=MediaSignals(((1.5,.7),),((.55,.9,None),(1.3,1.95,None)),{'fixture':True})
    source=fixture.real_source();support=fixture.image();project=fixture.project
    job=store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex);job=store.claim()
    store.finish(job,result=Pipeline(config).run(job,lambda _:None));project=view(store,project['id'])
    CostLedger(store).set_budget(project['id'],project['revision'],'1000')
    vault=NativeVisionKeyVault(private,state,WORKSPACE)
    receipt=vault.save(PrivateVisionKey(workspace_id=WORKSPACE,credential_alias='explicit-source-broll-vision',api_key='sk-explicit-synthetic-source-broll-vision-not-real'))
    selected=profile(receipt);wire=[]
    def response(request):
        body=json.loads(request.content);count=sum(v['type']=='input_image' for v in body['input'][0]['content'])
        assert str(request.url)=='https://api.openai.com/v1/responses' and body['store'] is False
        wire.append({'mock':True,'frame_count':count,'fixed_endpoint':True});return httpx.Response(200,json=response_payload(count))
    factory=NativeVisionFactory(selected,vault,operator_enabled=True,transport=httpx.MockTransport(response));pipeline=NoProviderPipeline()
    server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity,official_vision_directory=private,
        official_vision_enabled=True,official_vision_factories={selected.profile_id:factory})
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();cookie,session=identity.login(raw);calls=[]
    def request(method,path,body=None):
        conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=15)
        conn.request(method,path,body=json.dumps(body) if body is not None else None,headers={
            'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
        reply=conn.getresponse();value=json.loads(reply.read());conn.close();assert reply.status==200,(path,value)
        calls.append({'method':method,'route':path,'status':reply.status});return value
    try:
        base='/api/projects/'+project['id'];project=request('GET',base+'/auto-edit/timeline');frames=request('GET',base+'/media-frames')
        observation=next(v for v in frames['observations'] if v['asset_id']==support['id'])
        row=request('POST',base+'/official-vision',{'revision':project['revision'],'profile_id':selected.profile_id,'expected_configuration_sha256':factory.sha256,
            'observation_id':observation['observation_id'],'acknowledged_external_image_analysis':True,'acknowledged_protocol_mock':True,
            'max_operation_cost_vnd':'500','valid_for_seconds':600,'request_key':'retained-source-broll-vision-finite-mock'})
        row=request('POST',base+'/official-vision/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})
        assert row['status']=='succeeded' and row['result']['mock'] and not row['result']['semantic_inference_performed']
        before=copy.deepcopy(project['shot_timeline']['snapshot'])
        def broll(action,extra=None):
            nonlocal project
            project=request('POST',base+'/auto-edit/broll',{'revision':project['revision'],'action':action,
                'payload':{'expected_version':project['shot_timeline']['version'],**(extra or {})}})
            return project['document']['source_broll_plans'][-1]['plan']
        baseline=broll('create');reviewed=broll('create',{'reviewed_vision':[{'vision_id':row['vision_id'],'expected_snapshot_sha256':row['snapshot_sha256'],
            'expected_result_sha256':row['result_sha256'],'acknowledged_reviewed_result':True,'acknowledged_protocol_mock':True}]})
        assert reviewed['provenance']['algorithm']=='native-source-broll-v2' and not reviewed['provenance']['semantic_vision_used']
        assert project['shot_timeline']['snapshot']==before
        for actual,original in zip(reviewed['items'],baseline['items'],strict=True):
            candidates=copy.deepcopy(actual['provenance']['supporting_candidates'])
            for candidate in candidates:candidate.pop('reviewed_vision',None)
            assert candidates==original['provenance']['supporting_candidates']
        item=reviewed['items'][0];chosen=broll('select',{'media_plan_id':reviewed['media_plan_id'],'expected_plan_version':reviewed['version'],
            'item_id':item['media_plan_item_id'],'asset_id':asset_reference(support)})
        broll('apply',{'media_plan_id':chosen['media_plan_id'],'expected_plan_version':chosen['version'],'item_ids':[item['media_plan_item_id']]})
        after=project['shot_timeline']['snapshot'];assert after['duration_seconds']==before['duration_seconds']
        for track in before['tracks']:
            if track['kind']!='broll':assert track==next(v for v in after['tracks'] if v['track_id']==track['track_id'])
        assert project['approval'] is None and any(v['kind']=='broll' and v['clips'] for v in after['tracks'])
        child=request('POST',base+'/duplicate',{'revision':project['revision']})
        assert len(child['document']['source_broll_plans'])==1 # only the baseline is rebound
        assert len(child['document']['source_broll_inherited_reviewed_history'])==2
        assert all(v['authority_transferred'] is False for v in child['document']['source_broll_inherited_reviewed_history'])
        assert request('GET',base+'/auto-edit/timeline')==project and request('GET',base+'/official-vision/'+row['vision_id'])==row
        costs=server.official_vision.costs.summary(project['id']);assert len(costs['records'])==1 and costs['records'][0]['actual_cost'] is None and not costs['records'][0]['paid']
        hashes={fixture.asset['id']:file_sha(source),support['id']:file_sha(state/'assets'/support['id'])}
        assert hashes[fixture.asset['id']]==fixture.asset['sha256'] and hashes[support['id']]==support['sha256']
        assert len(wire)==1 and pipeline.calls==0 and not server.runner.run_one()
        write(out/'expected-projects.json',[project,child]);write(out/'original-vision.json',row);write(out/'expected-journals.json',journals(server.store))
        write(out/'cost-summary.json',costs);write(out/'source-hashes.json',hashes);write(out/'signed-http-summary.json',calls);write(out/'mock-wire-summary.json',wire)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config,out/'public-source-broll-vision.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-source-broll-vision.zip',restore,expected_sha256=backup['sha256']));reopen(args)
    names=('services/windows_native/source_broll_vision.py','services/windows_native/source_broll.py','services/windows_native/source_duplicate.py',
        'services/windows_native/store.py','services/windows_native/auto_edit_timeline.py','services/windows_native/media_frame_analysis.py',
        'services/windows_native/server.py','services/windows_native/tests/test_source_broll_vision.py','scripts/north_star_source_broll_vision.py')
    write(out/'evidence.json',{'schema_version':'native-source-broll-vision-rehearsal-v1','source_sha256':{name:file_sha(ROOT/name) for name in names},
        'signed_http_requests':len(calls),'actual_source_video_seconds':3,'actual_source_dimensions':[320,240],'actual_source_audio':'synthetic test tone, not speech',
        'asr_and_source_analysis':'explicit saved fixtures, not genuine spoken-media acceptance','new_cpu_frame_jobs':1,'new_mock_requests':1,
        'plan_history_versions':3,'explicit_canonical_apply':1,'duplicate_preserves_original_review_without_authority_transfer':True,
        'source_audio_tracks_and_bytes_unchanged':True,'original_source_response_cost_binding_exact':True,'mock_semantic_ranking_used':False,
        'new_external_dispatches':0,'new_paid_operations':0,'new_studio_ui_integrated':False,'actual_parent_browser_executed':False,
        'full_media_qc_or_final_render':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,
        'public_backup_sha256':backup['sha256'],'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_http_requests':len(calls),'mock_requests':1,'plan_history_versions':3,'fresh_recovery_exact':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--private-root',type=Path);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
