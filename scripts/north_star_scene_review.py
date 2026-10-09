"""Reviewed Source scene/highlight backend; finite explicit mock and keyless restore."""
import argparse,copy,http.client,json,re,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.vision_registry import NativeVisionFactory
from services.windows_native.auto_edit_timeline import view
from services.windows_native.scene_review import page
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write,WORKSPACE
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-scene-review-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned scene review fixture required')
    return path

def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        for project in json.loads((out/'expected-projects.json').read_bytes()):assert view(server.store,project['id'])==project
        for expected in json.loads((out/'expected-scenes.json').read_bytes()):assert page(server.store,server.config,expected['project_id'])==expected
        for row in json.loads((out/'original-vision-history.json').read_bytes()):assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        before=json.loads((out/'expected-journals.json').read_bytes());assert journals(server.store)==before
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
        assert server.official_vision.recover()==0 and not server.runner.run_one() and database_status(server.store.db)['active_operations']==0
        assert journals(server.store)==before
        for key,value in json.loads((out/'source-hashes.json').read_bytes()).items():assert file_sha(root/'assets'/key)==value
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all_original_scene_highlight_projects_vision_journals_source_bytes_exact':True,'keyless_disabled_provider_history':True,
        'provider_consent_renewed':False,'provider_retry_or_dispatch':False,'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
    state=owned(args.state_root,'state',True);restore=owned(args.restore_root,'restore',True);private=owned(args.private_root,'private',True)
    out=args.output.resolve();prior=args.prior.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);archive=prior/'public-source-broll-review.zip';saved=json.loads((prior/'backup.json').read_bytes())
    assert file_sha(archive)==saved['sha256'];write(out/'prior-restore.json',restore_backup(archive,state,expected_sha256=saved['sha256']))
    expected=json.loads((prior/'expected-projects.json').read_bytes());config=config_for(state);raw,identity=access()
    vault=NativeVisionKeyVault(private,state,WORKSPACE)
    receipt=vault.save(PrivateVisionKey(workspace_id=WORKSPACE,credential_alias='explicit-scene-review',api_key='sk-explicit-synthetic-scene-review-not-real'))
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
        for project in expected:assert view(server.store,project['id'])==project
        base='/api/projects/'+expected[0]['id'];project=request('GET',base+'/auto-edit/timeline');before=copy.deepcopy(project)
        old_rows=server.official_vision.page(project['id'])['items']
        frames=request('GET',base+'/media-frames');analysis_id=project['document']['canonical_timeline']['snapshot']['metadata']['source_analysis_id']
        analysis_record=next(v for v in project['document']['auto_edit_analyses'] if v['analysis']['analysis_id']==analysis_id)
        asset_id=analysis_record['native_asset_id']
        observation=next(v for v in frames['observations'] if v['asset_id']==asset_id)
        row=request('POST',base+'/official-vision',{'revision':project['revision'],'profile_id':selected.profile_id,'expected_configuration_sha256':factory.sha256,
            'observation_id':observation['observation_id'],'acknowledged_external_image_analysis':True,'acknowledged_protocol_mock':True,
            'max_operation_cost_vnd':'500','valid_for_seconds':600,'request_key':'retained-reviewed-scene-finite-mock'})
        row=request('POST',base+'/official-vision/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})
        assert row['status']=='succeeded' and row['result']['mock'] and not row['result']['semantic_inference_performed']
        ref={'vision_id':row['vision_id'],'expected_snapshot_sha256':row['snapshot_sha256'],'expected_result_sha256':row['result_sha256'],
            'acknowledged_reviewed_result':True,'acknowledged_protocol_mock':True}
        def save():
            return request('POST',base+'/auto-edit/scene-reviews',{'revision':project['revision'],'analysis_id':analysis_id,'reviewed_vision':ref})
        scene_page=save();project=request('GET',base+'/auto-edit/timeline');assert save()==scene_page
        assert request('GET',base+'/auto-edit/scene-reviews')==scene_page
        for key in ('canonical_timeline','auto_edit_analyses','source_broll_plans','assets'):assert project['document'][key]==before['document'][key]
        assert project['shot_timeline']==before['shot_timeline'] and project['approval'] is None
        result=scene_page['items'][0]['recommendation']['result'];assert not result['semantic_vision_used'] and result['recommendation_only']
        assert not result['canonical_timeline_mutated'] and not result['silence_decisions_mutated']
        child=request('POST',base+'/duplicate',{'revision':project['revision']})
        assert 'source_scene_recommendations' not in child['document']
        archived=child['document']['source_scene_inherited_reviewed_history'];assert [v['original_record'] for v in archived]==scene_page['items']
        assert all(v['authority_transferred'] is False and v['new_review_required'] is True for v in archived)
        assert request('GET',base+'/auto-edit/timeline')==project and view(server.store,expected[1]['id'])==expected[1]
        for old in old_rows:assert server.official_vision.get(old['project_id'],old['vision_id'])==old
        assert request('GET',base+'/official-vision/'+row['vision_id'])==row
        costs=server.official_vision.costs.summary(project['id']);assert len(costs['records'])==2
        assert all(v['actual_cost'] is None and not v['paid'] for v in costs['records'])
        hashes=json.loads((prior/'source-hashes.json').read_bytes())
        for key,value in hashes.items():assert file_sha(state/'assets'/key)==value
        assert len(wire)==1 and pipeline.calls==0 and not server.runner.run_one()
        projects=[project,expected[1],child]
        write(out/'expected-projects.json',projects);write(out/'expected-scenes.json',[page(server.store,config,v['id']) for v in projects])
        write(out/'original-vision-history.json',old_rows+[row]);write(out/'expected-journals.json',journals(server.store))
        write(out/'cost-summary.json',costs);write(out/'source-hashes.json',hashes);write(out/'signed-http-summary.json',calls);write(out/'mock-wire-summary.json',wire)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config,out/'public-scene-review.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-scene-review.zip',restore,expected_sha256=backup['sha256']));reopen(args)
    names=('services/windows_native/scene_review.py','services/windows_native/access.py','services/windows_native/server.py',
        'services/windows_native/auto_edit_timeline.py','services/windows_native/source_duplicate.py','services/windows_native/store.py',
        'services/windows_native/tests/test_scene_review.py','scripts/north_star_scene_review.py')
    write(out/'evidence.json',{'schema_version':'native-reviewed-scene-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in names},
        'signed_http_requests':len(calls),'new_mock_requests':1,'new_cpu_jobs':0,'reused_source_video_seconds':3,
        'asr_source_analysis_and_vision':'explicit saved fixtures, not genuine speech/provider acceptance','saved_recommendations':1,
        'deduplicated_create_exact':True,'source_audio_tracks_duration_bytes_original_results_costs_exact':True,
        'inherited_history_without_authority_transfer':True,'new_external_dispatches':0,'new_paid_operations':0,
        'new_studio_ui_integrated':False,'actual_parent_browser_executed':False,'full_media_qc_or_final_render':False,
        'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,'public_backup_sha256':backup['sha256'],
        'prior_public_backup_sha256':saved['sha256'],'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_requests':len(calls),'new_mock_requests':1,'saved_recommendations':1,'fresh_restore_exact':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prior',type=Path);p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--private-root',type=Path);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
