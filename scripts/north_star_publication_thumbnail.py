"""Retained signed thumbnail metadata review, independent source-rights blocking."""
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
    root=owned(args.restore_root);out=args.output.resolve();pipeline=NoProviderPipeline();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity) as server:
        rights=json.loads((out/'expected-rights.json').read_bytes());publications=json.loads((out/'expected-publications.json').read_bytes())
        for row in rights:assert server.render_thumbnail_rights.get(row['project_id'],row['override_id'])==row
        for row in publications:assert server.publications.get(row['project_id'],row['publication_id'])==row
        for row in json.loads((out/'expected-thumbnails.json').read_bytes()):
            assert server.render_thumbnails.get(row['project_id'],row['thumbnail_asset_id'])==row
            png,snapshot=server.render_thumbnails.image(row['project_id'],row['thumbnail_asset_id'])
            assert png==(root/'jobs'/snapshot['request']['render_job_id']/snapshot['frame']['evidence_frame_reference']).read_bytes()
        for row in json.loads((out/'expected-vision.json').read_bytes()):assert server.render_vision.get(row['project_id'],row['vision_id'])==row
        assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes()) and media_snapshot(root)==json.loads((out/'expected-media.json').read_bytes())
        assert not server.render_thumbnail_rights.states()['enabled'] and not server.render_vision.states()['enabled'] and server.render_vision.states()['profiles']==[]
        assert server.publications.process() is None and not server.runner.run_one() and pipeline.calls==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{'status':'PASS','original_publications_rights_thumbnails_vision_source_cost_journals_media_png_pts_exact':True,
        'publication_count':len(publications),'rights_count':len(rights),'exceptions_automatically_reenabled':False,'provider_calls':0,'paid_operations':0,'real_owner_legal_override':False,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_original_publications':len(publications)}))


def run(args):
    root=owned(args.state_root,True);restored=owned(args.restore_root,True);out=args.output.resolve()
    if out.exists() or root==restored or out==ROOT or ROOT in out.parents or root in out.parents or restored in out.parents:raise ValueError('Fresh distinct owned evidence paths required')
    if file_sha(args.input_bundle)!=args.expected_input_sha256:raise ValueError('Exact original public backup required')
    out.mkdir(parents=True);write(out/'prior-restore.json',restore_backup(args.input_bundle,root,expected_sha256=args.expected_input_sha256))
    original_media=media_snapshot(root);raw,identity=access();pipeline=NoProviderPipeline()
    with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity,render_thumbnail_rights_enabled=True) as server:
        prior=server.render_thumbnail_rights.page(args.project_id,limit=100)['items'];thumbs=server.render_thumbnails.page(args.project_id,limit=100)['items'];vision=server.render_vision.page(args.project_id,limit=100)['items'];before=journals(server.store)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
                result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_publication_thumbnail.mjs'],cwd=ROOT,
                    input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':args.project_id,'thumbnail':prior[0]['thumbnail_asset_id'],'original_rights_count':len(prior)}).encode(),stdout=stdout,stderr=stderr,timeout=180)
            assert result.returncode==0,(out/'node-controller-errors.log').read_text();proof=json.loads((out/'node-controller-proof.json').read_bytes());assert proof['status']=='PASS' and raw not in json.dumps(proof)
            rights=prior+proof['new_rights'];assert len(proof['new_rights'])==2 and len(proof['new_publications'])==4
            for row in rights:assert server.render_thumbnail_rights.get(args.project_id,row['override_id'])==row
            publications=[server.publications.get(args.project_id,row['publication_id']) for row in proof['new_publications']]
            assert all(row['status']=='blocked' and row['receipt'] is None and row['approval'] is None for row in publications)
            for original,row in zip(proof['new_publications'],publications):assert row['snapshot']==original['snapshot']
            for row in thumbs:assert server.render_thumbnails.get(args.project_id,row['thumbnail_asset_id'])==row
            for row in vision:assert server.render_vision.get(args.project_id,row['vision_id'])==row
            current=journals(server.store)
            changed={'native_publications','native_publication_events','native_render_thumbnail_rights','render_reviews','events','native_bridge_outbox'}
            for name,rows in before.items():
                if name not in changed:assert current[name]==rows,name
            after=media_snapshot(root);assert all(after[k]==original_media[k] for k in ('files','records','successful_renders'))
            original=proof['original_project'];reviewed=server.store.get(args.project_id)
            assert original['document']==reviewed['document'] and original['revision']==reviewed['revision'] and original['approval']==reviewed['approval']
            assert len(current['render_reviews'])==len(before['render_reviews'])+1
            assert server.publications.process() is None and not server.runner.run_one() and pipeline.calls==0
            write(out/'expected-rights.json',rights);write(out/'expected-publications.json',publications);write(out/'expected-thumbnails.json',thumbs);write(out/'expected-vision.json',vision);write(out/'expected-journals.json',current);write(out/'expected-media.json',after)
        finally:server.shutdown();thread.join()
    backup=create_backup(config_for(root),out/'public-publication-thumbnail.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-publication-thumbnail.zip',restored,expected_sha256=backup['sha256']));args.reopen=False;reopen(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=120)
    sources=('services/windows_native/publication_thumbnail.py','services/windows_native/publications.py','services/windows_native/server.py','services/windows_native/tests/test_publication_thumbnail.py',
        'apps/studio-web/native-publications.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/tests/native-publication-thumbnail.test.mjs',
        'scripts/north_star_publication_thumbnail.py','scripts/north_star_publication_thumbnail.mjs')
    write(out/'evidence.json',{'schema_version':'native-publication-thumbnail-rehearsal-v1','status':'PASS','source_sha256':{s:file_sha(ROOT/s) for s in sources},
        'signed_http_requests':len(proof['calls']),'new_blocked_publications':4,'thumbnail_validation_passed_but_source_still_blocked':True,'new_synthetic_rights':2,'all_rights_records':len(rights),
        'new_synthetic_final_review':1,'original_thumbnail_selections':len(thumbs),'original_vision_histories':len(vision),'canonical_document_revision_approval_source_media_png_pts_cost_exact':True,
        'keyless_new_process_recovery_exact':True,'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),'http_and_studio_integrated':True,'dom_controller_tested':True,'actual_parent_browser_executed':False,
        'new_media_copies':0,'new_renders':0,'new_provider_calls':0,'new_paid_operations':0,'live_credentials_read':False,'thumbnail_metadata_bound':True,'official_thumbnail_transport_configured':False,
        'rights_status':'unknown','license':None,'rights_independently_verified':False,'source_asset_rights_granted':False,'publishing_authorized':False,'real_owner_legal_override':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False})
    print(json.dumps({'status':'PASS','new_blocked_publications':4,'signed_http_requests':len(proof['calls']),'public_backup_sha256':backup['sha256']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--input-bundle',type=Path);p.add_argument('--expected-input-sha256');p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project-id');p.add_argument('--reopen',action='store_true')
    args=p.parse_args();reopen(args) if args.reopen else run(args)
