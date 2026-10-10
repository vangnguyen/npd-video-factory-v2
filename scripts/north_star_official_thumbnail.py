"""Retain signed Native PNG publication mocks and disabled/keyless app recovery."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.tests.test_official_thumbnail_http import OfficialThumbnailHTTPTests
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.server import LocalServer
from services.windows_native.contracts import digest,file_sha
from services.windows_native.backup import create_backup,restore_backup
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_official_vision import write,config_for
from scripts.north_star_render_frame_recovery import owned
from scripts.north_star_render_vision_http import access


def replay(args):
    root=owned(args.restore_root);out=args.output.resolve();expected=json.loads((out/'expected-publication.json').read_bytes());pipeline=NoProviderPipeline();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity) as server:
        original=server.official_publications.get(expected['project_id'],expected['publication_id']);assert original==expected
        assert server.official_publications.state(expected['project_id'],expected['publication_id'])==json.loads((out/'expected-state.json').read_bytes())
        assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes())
        assert server.store.get(expected['project_id'])==json.loads((out/'expected-project.json').read_bytes())
        original_png,snapshot=server.render_thumbnails.image(expected['project_id'],expected['snapshot']['metadata']['thumbnail_asset_id'])
        assert digest(list(original_png))==json.loads((out/'expected-png.json').read_bytes())['byte_sequence_sha256']
        assert snapshot['image']['sha256']==expected['snapshot']['thumbnail']['image']['sha256']
        assert server.official_publications.states()['profiles']==[] and not server.render_thumbnail_rights.states()['enabled']
        assert not server.runner.run_one() and pipeline.calls==0
    write(out/('new-process-replay.json' if args.reopen else 'in-process-replay.json'),{'status':'PASS','original_publication_stage_receipt_project_png_journals_exact':True,
        'new_process':args.reopen,'keys_configured':False,'human_registry':'explicit scoped fixture; not a genuine Owner acceptance','automatic_thumbnail_retry':False,
        'exceptions_automatically_reenabled':False,'external_calls':0,'paid_operations':0,'owner_uat_accepted':False})
    print(json.dumps({'status':'PASS','keyless_original_thumbnail_stage':original['thumbnail_stage']['status']}))


def run(args):
    restored=owned(args.restore_root,True);out=args.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents or out==restored or restored in out.parents:raise ValueError('Fresh distinct external evidence required')
    out.mkdir(parents=True);cls=OfficialThumbnailHTTPTests;case=cls('test_http_original_png_stage_is_explicit_and_receipt_requires_the_following_processing_poll');calls=[]
    cls.setUpClass()
    try:
        case.setUp()
        try:
            project=case.store.get(case.project['id']);png=case.root/'jobs'/case.job['id']/case.frame['evidence_frame_reference'];image=file_sha(png)
            files={p.relative_to(case.root).as_posix():file_sha(p) for base in ('assets','originals','jobs','shot-previews') for p in (case.root/base).rglob('*') if p.is_file()}
            original_request=case.request_http
            def recorded(method,path,body=None,headers=None):
                result=original_request(method,path,body,headers);calls.append({'method':method,'path':path,'request_sha256':digest(body) if body is not None else None,'status':result[0]});return result
            case.request_http=recorded;case.test_http_original_png_stage_is_explicit_and_receipt_requires_the_following_processing_poll()
            publication=case.journal.get(case.project['id'],case.value['publication_id']);state=case.state();assert publication['mock_publication_complete'] and not publication['published']
            assert case.store.get(case.project['id'])==project and file_sha(png)==image
            assert {p.relative_to(case.root).as_posix():file_sha(p) for base in ('assets','originals','jobs','shot-previews') for p in (case.root/base).rglob('*') if p.is_file()}==files
            write(out/'signed-http-observations.json',calls);write(out/'mock-wire-observations.json',case.wire)
            write(out/'expected-publication.json',publication);write(out/'expected-state.json',state);write(out/'expected-journals.json',journals(case.server.store));write(out/'expected-project.json',project)
            write(out/'expected-png.json',{'sha256':image,'byte_sequence_sha256':digest(list(png.read_bytes()))})
            costs=[r for r in case.worker.costs.summary(case.project['id'])['records'] if r['provider']=='official-youtube']
            assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for r in costs)
            write(out/'cost-observations.json',costs)
            backup=create_backup(case.config,out/'public-official-thumbnail.zip');write(out/'backup.json',backup)
            assert backup['database_status']['workflow.sqlite3']['counts']['native_official_publish_thumbnails']==1
            assert len(case.posts())==1 and sum(r['method']=='POST' and r['path']=='/upload/youtube/v3/videos' for r in case.wire)==1
        finally:case.tearDown()
    finally:cls.tearDownClass()
    write(out/'restore.json',restore_backup(out/'public-official-thumbnail.zip',restored,expected_sha256=backup['sha256']));args.reopen=False;replay(args)
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--restore-root',str(restored),'--output',str(out),'--reopen'],capture_output=True,check=True,timeout=180)
    sources=('services/windows_native/official_publication_thumbnails.py','services/windows_native/official_publications.py','services/windows_native/official_publication_worker.py','services/windows_native/backup.py',
        'services/windows_native/render_frame_evidence_cache.py','services/windows_native/render_frame_qc.py','services/windows_native/render_vision_frame_bridge.py',
        'services/windows_native/tests/test_official_publication_thumbnails.py','services/windows_native/tests/test_official_thumbnail_http.py','services/windows_native/tests/test_render_frame_evidence_cache.py',
        'apps/studio-web/native-official-publications.mjs','apps/studio-web/tests/native-official-thumbnail-stage.test.mjs','apps/studio-web/tests/native-official-publications.test.mjs','scripts/north_star_official_thumbnail.py')
    write(out/'evidence.json',{'schema_version':'north-star-official-thumbnail-rehearsal-v1','status':'PASS','source_sha256':{name:file_sha(ROOT/name) for name in sources},
        'signed_http_requests':len(calls),'mock_video_initializations':1,'mock_thumbnail_posts':1,'publication_mock_only':True,'thumbnail_stage':'response_received',
        'one_following_processing_poll_required':True,'canonical_project_source_media_png_exact':True,'keyless_new_process_recovery_exact':True,
        'public_backup_sha256':backup['sha256'],'new_process_stdout':result.stdout.decode().strip(),'paid_operations':0,'external_calls':0,'genuine_provider_keys_read':False,
        'original_rights_unknown':True,'rights_independently_verified':False,'real_owner_legal_override':False,'remote_image_bytes_verified':False,
        'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,'browser_parent_flow_completed':False,
        'cache_scope':'one reader/workspace/render directory, at most eight measured facts, physical SHA on every hit, no PNG bytes or provider/authority cached'})
    print(json.dumps({'status':'PASS','signed_http_requests':len(calls),'mock_thumbnail_posts':1,'public_backup_sha256':backup['sha256']}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    args=parser.parse_args();replay(args) if args.reopen else run(args)
