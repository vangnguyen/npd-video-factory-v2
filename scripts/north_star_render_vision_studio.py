"""Signed rendered-QC Studio controller, original PNGs and keyless exact restore."""
import argparse,base64,hashlib,json,subprocess,sys,tempfile,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.render_vision_registry import NativeRenderVisionFactory
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_render_vision_registry import profile
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot
from scripts.north_star_render_vision_http import access,reopen

def run(args):
    root=owned(args.state_root,True);restore=owned(args.restore_root,True);out=args.output.resolve()
    if root==restore or out.exists() or out==ROOT or ROOT in out.parents or root in out.parents or restore in out.parents:raise ValueError('Fresh owned output required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Exact original bundle required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    prior_media=media_snapshot(root);raw,identity=access();wires=[]
    with tempfile.TemporaryDirectory() as private:
        vault=NativeVisionKeyVault(Path(private),root,'wsp_native_local')
        receipt=vault.save(PrivateVisionKey(workspace_id='wsp_native_local',credential_alias='explicit-render-vision-key',api_key='sk-explicit-synthetic-studio-render-not-real'))
        def mock(request):
            body=json.loads(request.content);assert body['store'] is False and str(request.url)=='https://api.openai.com/v1/responses'
            images=[v for v in body['input'][0]['content'] if v['type']=='input_image'];shas=[hashlib.sha256(base64.b64decode(v['image_url'].split(',',1)[1],validate=True)).hexdigest() for v in images]
            wires.append({'mock':True,'frame_sha256':shas,'request_sha256':hashlib.sha256(request.content).hexdigest()})
            return httpx.Response(200,json=response_payload(len(images)))
        factory=NativeRenderVisionFactory(profile(receipt),vault,operator_enabled=True,transport=httpx.MockTransport(mock));pipeline=NoProviderPipeline()
        with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity,render_vision_directory=vault.directory,
            render_vision_enabled=True,render_vision_factories={factory.profile.profile_id:factory}) as server:
            prior=server.render_vision.page(args.project_id,limit=100)['items'];thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            try:
                with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
                    result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_render_vision_studio.mjs'],cwd=ROOT,
                        input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':args.project_id,'job':args.job_id}).encode(),stdout=stdout,stderr=stderr,timeout=180)
                assert result.returncode==0,(out/'node-controller-errors.log').read_text()
                proof=json.loads((out/'node-controller-proof.json').read_bytes());assert proof['status']=='PASS' and len(wires)==1
                assert wires[0]['frame_sha256']==[v['sha256'] for v in proof['input']['binding']['record']['observation']['frames']]
                after=media_snapshot(root);assert all(after[k]==prior_media[k] for k in ('projects','files','records','successful_renders'))
                expected=prior+[proof['done'],proof['cancelled']]
                for row in expected:assert server.render_vision.get(args.project_id,row['vision_id'])==row
                assert not server.runner.run_one() and pipeline.calls==0
                write(out/'expected-history.json',expected);write(out/'expected-journals.json',journals(server.store));write(out/'expected-media.json',after)
                write(out/'cost-summary.json',server.render_vision.costs.summary(args.project_id))
            finally:server.shutdown();thread.join()
    assert not Path(private).exists() and raw not in json.dumps(proof) and 'sk-explicit' not in json.dumps(proof)
    write(out/'mock-wire-summary.json',wires);backup=create_backup(config_for(root),out/'public-render-vision-studio.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-vision-studio.zip',restore,expected_sha256=backup['sha256']))
    args.reopen=False;reopen(args)
    result=subprocess.run([sys.executable,str(ROOT/'scripts/north_star_render_vision_http.py'),'--restore-root',str(restore),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('apps/studio-web/native-render-vision.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/native.css','apps/studio-web/shot-studio.mjs',
        'apps/studio-web/tests/native-render-vision.test.mjs','apps/studio-web/tests/fixtures/native-render-vision-v1.json',
        'services/windows_native/render_vision_routes.py','services/windows_native/server.py','services/windows_native/tests/test_render_vision_http.py','services/windows_native/tests/test_phase10_http.py',
        'scripts/north_star_render_vision_studio.py','scripts/north_star_render_vision_studio.mjs')
    write(out/'evidence.json',{'schema_version':'native-render-vision-studio-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'signed_http_requests':len(proof['calls']),'inherited_histories':len(prior),'new_histories':2,'all_histories':len(expected),'protocol_mock_requests':1,
        'exact_rendered_png_http_reads':len(proof['frame_proofs']),'original_projects_timeline_media_checkpoints_png_pts_exact':True,
        'all_journals_keyless_new_process_application_restore_exact':True,'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),
        'temporary_synthetic_private_keys_destroyed':True,'studio_ui_integrated':True,'dom_controller_tested':True,'actual_parent_browser_executed':False,
        'external_dispatches':0,'paid_operations':0,'live_credentials_read':False,'semantic_inference_performed':False,'source_asset_consent_reused':False,
        'hard_qc_replaced':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','signed_http_requests':len(proof['calls']),'all_histories':len(expected),'public_backup_sha256':backup['sha256']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-bundle',type=Path,required=True);p.add_argument('--expected-input-sha256',required=True)
    p.add_argument('--state-root',type=Path,required=True);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--project-id',required=True);p.add_argument('--job-id',required=True);run(p.parse_args())
