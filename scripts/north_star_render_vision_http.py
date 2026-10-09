"""Retained signed application rendered-QC rehearsal and keyless recovery."""
import argparse,base64,hashlib,json,subprocess,sys,tempfile,threading
import http.client as http_client
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import digest,file_sha
from services.windows_native.observability import Observer
from services.windows_native.render_vision_registry import NativeRenderVisionFactory
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_render_vision_registry import profile
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot


def access():
    raw,data=human_fixture('owner',workspace='wsp_native_local')
    return raw,NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_local')


def reopen(args):
    out=args.output.resolve();root=owned(args.restore_root);raw,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        assert server.render_vision is not None and not server.render_vision.states()['enabled'] and server.render_vision.states()['profiles']==[]
        expected=json.loads((out/'expected-history.json').read_bytes())
        for row in expected:assert server.render_vision.get(row['project_id'],row['vision_id'])==row
        assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes())
        assert media_snapshot(root)==json.loads((out/'expected-media.json').read_bytes())
        assert server.render_vision.recover()==0 and not server.runner.run_one()
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{
        'status':'PASS','all_original_history_journals_projects_media_checkpoints_png_pts_exact':True,
        'application_history_default_disabled_without_private_keys_profiles':True,'consent_renewed':False,'requests_replayed':0,
        'external_dispatches':0,'paid_operations':0,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_application_histories':len(expected)}))


def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if root==restored or out.exists() or out==ROOT or ROOT in out.parents or root in out.parents or restored in out.parents:raise ValueError('Fresh fixture/evidence paths required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Original backup checksum required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    store=Store(root);original=store.get(args.project_id);prior_media=media_snapshot(root);raw,identity=access();wires=[];requests=[];logs=[]
    mode=[None]
    with tempfile.TemporaryDirectory() as private:
        vault=NativeVisionKeyVault(Path(private),root,'wsp_native_local')
        receipt=vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',api_key='sk-explicit-synthetic-render-http-not-real'))
        def mock(request):
            body=json.loads(request.content);assert body['store'] is False and str(request.url)=='https://api.openai.com/v1/responses'
            images=[i for i in body['input'][0]['content'] if i['type']=='input_image'];shas=[hashlib.sha256(base64.b64decode(i['image_url'].split(',',1)[1],validate=True)).hexdigest() for i in images]
            assert shas==[f['sha256'] for f in input_view['binding']['record']['observation']['frames']]
            wires.append({'mode':mode[0],'input_sha256':shas,'wire_request_sha256':hashlib.sha256(request.content).hexdigest(),'mock':True})
            if mode[0]=='timeout':raise httpx.ReadTimeout('sk-explicit-private-http-error',request=request)
            return httpx.Response(200,json=response_payload(len(images)))
        factory=NativeRenderVisionFactory(profile(receipt),vault,operator_enabled=True,transport=httpx.MockTransport(mock))
        pipeline=NoProviderPipeline()
        with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity,observer=Observer(logs.append),
            render_vision_directory=vault.directory,render_vision_enabled=True,render_vision_factories={factory.profile.profile_id:factory}) as server:
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                cookie,session=identity.login(raw)
                def http(method,path,body=None):
                    con=http_client.HTTPConnection('127.0.0.1',server.server_port,timeout=125)
                    con.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json',
                        'Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
                    response=con.getresponse();headers=dict(response.getheaders());data=json.loads(response.read());con.close()
                    requests.append({'method':method,'path':path,'status':response.status,'no_store':headers.get('Cache-Control')=='no-store'})
                    assert response.status==200 and headers['Cache-Control']=='no-store',(path,data)
                    return data
                base='/api/projects/'+args.project_id+'/render-vision';public=http('GET','/api/connections/render-vision')
                input_view=http('GET',base+'/input/'+args.job_id);assert input_view['input_sha256']==digest(input_view['binding'])
                prior=http('GET',base+'?limit=100')['items'];expected=list(prior)
                for kind in ('success','timeout','cancel'):
                    mode[0]=kind
                    payload={'schema_version':'native-render-vision-analyze-v1','revision':original['revision'],'render_job_id':args.job_id,
                        'profile_id':factory.profile.profile_id,'expected_configuration_sha256':factory.sha256,'expected_render_input_sha256':input_view['input_sha256'],
                        'acknowledged_rendered_frame_analysis':True,'acknowledged_protocol_mock':True,'max_operation_cost_vnd':'500','valid_for_seconds':600,
                        'request_key':'explicit-render-http-'+kind}
                    row=http('POST',base,payload);assert row['status']=='approved' and row['idempotent_replay'] is False
                    if kind=='cancel':done=http('POST',base+'/'+row['vision_id']+'/cancel',{'expected_snapshot_sha256':row['snapshot_sha256']})
                    else:done=http('POST',base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})
                    status='succeeded' if kind=='success' else 'outcome_unknown' if kind=='timeout' else 'cancelled';assert done['status']==status
                    count=len(wires);assert http('POST',base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})==done and len(wires)==count
                    assert http('GET',base+'/'+row['vision_id'])==done;expected.append(done)
                assert len(wires)==2 and not server.runner.run_one() and pipeline.calls==0
                assert server.store.get(args.project_id)==original
                costs=server.render_vision.costs.summary(args.project_id);all_journals=journals(server.store)
                after=media_snapshot(root);assert all(after[k]==prior_media[k] for k in ('projects','files','records','successful_renders'))
                write(out/'runtime-and-input.json',{'runtime':public,'input':input_view});write(out/'expected-history.json',expected)
                write(out/'expected-journals.json',all_journals);write(out/'expected-media.json',after);write(out/'cost-summary.json',costs)
            finally:server.shutdown();thread.join()
    assert not Path(private).exists() and all(raw not in json.dumps(v) and 'sk-explicit' not in json.dumps(v) for v in (logs,expected))
    write(out/'signed-http-summary.json',requests);write(out/'mock-wire-summary.json',wires);write(out/'redacted-observations.json',logs)
    backup=create_backup(config_for(root),out/'public-render-vision-http.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-vision-http.zip',restored,expected_sha256=backup['sha256']));reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('services/windows_native/server.py','services/windows_native/access.py','services/windows_native/render_vision_routes.py',
        'services/windows_native/render_vision.py','services/windows_native/tests/test_render_vision_http.py','scripts/north_star_render_vision_http.py')
    write(out/'evidence.json',{'schema_version':'native-render-vision-http-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'signed_http_requests':len(requests),'inherited_histories':len(prior),'new_histories':3,'all_histories':len(expected),'protocol_mock_requests':2,
        'original_projects_timeline_media_checkpoints_png_pts_exact':True,'all_journals_keyless_new_process_application_restore_exact':True,
        'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),'temporary_synthetic_private_keys_destroyed':True,
        'external_dispatches':0,'paid_operations':0,'live_credentials_read':False,'semantic_inference_performed':False,
        'source_asset_consent_reused':False,'hard_qc_replaced':False,'studio_ui_integrated':False,'owner_uat_accepted':False,
        'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','signed_http_requests':len(requests),'all_histories':len(expected),'public_backup_sha256':backup['sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input-bundle',type=Path);parser.add_argument('--expected-input-sha256')
    parser.add_argument('--state-root',type=Path);parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project-id');parser.add_argument('--job-id');parser.add_argument('--reopen',action='store_true');args=parser.parse_args()
    if args.reopen:reopen(args)
    else:run(args)
