"""Signed thumbnail UI, original PNG reads and exact keyless application recovery."""
import argparse,json,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.backup import create_backup,restore_backup
from services.windows_native.contracts import file_sha
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_render_frame_recovery import owned,snapshot as media_snapshot
from scripts.north_star_render_vision_http import access

def reopen(args):
    root=owned(args.restore_root);out=args.output.resolve();pipeline=NoProviderPipeline()
    _,identity=access()
    with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity) as server:
        expected=json.loads((out/'expected-thumbnails.json').read_bytes())
        for row in expected:
            assert server.render_thumbnails.get(row['project_id'],row['thumbnail_asset_id'])==row
            pixels,snapshot=server.render_thumbnails.image(row['project_id'],row['thumbnail_asset_id'])
            assert pixels==(root/'jobs'/snapshot['request']['render_job_id']/snapshot['frame']['evidence_frame_reference']).read_bytes()
        for row in json.loads((out/'expected-vision.json').read_bytes()):assert server.render_vision.get(row['project_id'],row['vision_id'])==row
        assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes())
        assert media_snapshot(root)==json.loads((out/'expected-media.json').read_bytes())
        assert not server.render_vision.states()['enabled'] and server.render_vision.states()['profiles']==[] and not server.runner.run_one() and pipeline.calls==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{'status':'PASS','keyless_original_thumbnails_vision_cost_journals_media_png_pts_exact':True,
        'all_thumbnail_selections':len(expected),'new_provider_calls':0,'new_paid_operations':0,'publishing_authorized':False,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_application_original_thumbnail_selections':len(expected)}))

def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if out.exists() or root==restored or out==ROOT or ROOT in out.parents or root in out.parents or restored in out.parents:raise ValueError('Fresh owned fixture and output paths required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Original public backup checksum required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    original_media=media_snapshot(root);raw,identity=access();pipeline=NoProviderPipeline()
    with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity) as server:
        prior=server.render_thumbnails.page(args.project_id,limit=100)['items'];histories=server.render_vision.page(args.project_id,limit=100)['items'];before=journals(server.store)
        reviewed=next(v for v in histories if v['status']=='succeeded' and v['result']['render_job_id']==args.job_id and v['result']['mock'])
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
                result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_render_thumbnail_studio.mjs'],cwd=ROOT,
                    input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':args.project_id,'job':args.job_id,'vision':reviewed['vision_id'],
                        'inherited_selections':len(prior)}).encode(),stdout=stdout,stderr=stderr,timeout=180)
            assert result.returncode==0,(out/'node-controller-errors.log').read_text()
            proof=json.loads((out/'node-controller-proof.json').read_bytes());assert proof['status']=='PASS' and raw not in json.dumps(proof)
            expected=prior+proof['new_selections'];assert len(proof['new_selections'])==3
            for row in expected:assert server.render_thumbnails.get(args.project_id,row['thumbnail_asset_id'])==row
            for row in histories:assert server.render_vision.get(args.project_id,row['vision_id'])==row
            current=journals(server.store)
            for name,rows in before.items():
                if name!='native_render_thumbnails':assert current[name]==rows,name
            after=media_snapshot(root);assert all(after[k]==original_media[k] for k in ('projects','files','records','successful_renders'))
            assert not server.runner.run_one() and pipeline.calls==0
            write(out/'expected-thumbnails.json',expected);write(out/'expected-vision.json',histories);write(out/'expected-journals.json',current);write(out/'expected-media.json',after)
        finally:server.shutdown();thread.join()
    backup=create_backup(config_for(root),out/'public-render-thumbnail-studio.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-render-thumbnail-studio.zip',restored,expected_sha256=backup['sha256']));args.reopen=False;reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('services/windows_native/server.py','services/windows_native/access.py','services/windows_native/render_thumbnail_routes.py','services/windows_native/tests/test_render_thumbnail_http.py',
        'services/windows_native/tests/test_phase10_http.py','apps/studio-web/native-render-thumbnail.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/native.css','apps/studio-web/shot-studio.mjs',
        'apps/studio-web/tests/native-render-thumbnail.test.mjs','apps/studio-web/tests/fixtures/native-render-thumbnail-v1.json','scripts/north_star_render_thumbnail_studio.py','scripts/north_star_render_thumbnail_studio.mjs')
    write(out/'evidence.json',{'schema_version':'native-render-thumbnail-studio-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'signed_http_requests':len(proof['calls']),'new_thumbnail_selections':3,'inherited_thumbnail_selections':len(prior),'all_thumbnail_selections':len(expected),'unchanged_original_vision_histories':len(histories),
        'exact_rendered_png_http_reads':len(proof['frame_proofs']),'exact_selected_png_http_reads':len(proof['selected_image_proofs']),
        'all_original_projects_timeline_media_checkpoints_png_pts_exact':True,'original_cost_and_vision_journals_exact':True,'keyless_new_process_application_recovery_exact':True,
        'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),'http_and_studio_integrated':True,'dom_controller_tested':True,'actual_parent_browser_executed':False,
        'new_media_copies':0,'new_renders':0,'new_provider_calls':0,'new_paid_operations':0,'live_credentials_read':False,'semantic_inference_performed':False,
        'rights_status':'unknown','rights_independently_verified':False,'publishing_authorized':False,'thumbnail_publication_transport_bound':False,
        'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','signed_http_requests':len(proof['calls']),'all_thumbnail_selections':len(expected),'public_backup_sha256':backup['sha256']}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-bundle',type=Path);p.add_argument('--expected-input-sha256');p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id');p.add_argument('--job-id');p.add_argument('--reopen',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
