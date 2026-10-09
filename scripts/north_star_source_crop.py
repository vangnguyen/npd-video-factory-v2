"""Signed Source crop review rehearsal; original journals and public recovery."""
import argparse,json,re,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.auto_edit_timeline import view
from services.windows_native.scene_review import page
from services.windows_native.source_reframe_vision import history
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-source-crop-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Fresh owned crop fixture required')
    return path
def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        expected=json.loads((out/'expected-projects.json').read_bytes())
        for p in expected:assert view(server.store,p['id'])==p
        for v in json.loads((out/'expected-scenes.json').read_bytes()):assert page(server.store,server.config,v['project_id'])==v
        for row in json.loads((out/'original-vision-history.json').read_bytes()):assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        before=json.loads((out/'expected-journals.json').read_bytes());assert journals(server.store)==before
        for name,sha in json.loads((out/'source-hashes.json').read_bytes()).items():assert file_sha(root/'assets'/name)==sha
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
        assert server.official_vision.recover()==0 and not server.runner.run_one() and database_status(server.store.db)['active_operations']==0
        assert journals(server.store)==before
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'all8_projects_original_crop_scene_results_cost_journals_source_bytes_exact':True,
        'keyless_disabled_recovery':True,'provider_retry_or_consent_renewal':False,'real_provider_tested':False,'owner_uat_accepted':False})
def run(args):
    root=owned(args.state_root,'state',True);restore=owned(args.restore_root,'restore',True);out=args.output.resolve();prior=args.prior.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external output required')
    out.mkdir(parents=True);saved=json.loads((prior/'backup.json').read_bytes());archive=prior/'public-project-thumbnail.zip';assert file_sha(archive)==saved['sha256']
    write(out/'prior-restore.json',restore_backup(archive,root,expected_sha256=saved['sha256']))
    raw,identity=access();pipeline=NoProviderPipeline();server=LocalServer(0,config_for(root),pipeline=pipeline,start_worker=False,access=identity)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        expected=json.loads((prior/'expected-projects.json').read_bytes());parent_id='aef7219b866240bebf1e355d4a07220f'
        for p in expected:assert view(server.store,p['id'])==p
        original_journals=journals(server.store)
        with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
            result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_source_crop.mjs'],cwd=ROOT,
                input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':parent_id}).encode(),stdout=stdout,stderr=stderr,timeout=60)
        assert result.returncode==0,(out/'node-controller-errors.log').read_text()
        proof=json.loads((out/'node-controller-proof.json').read_bytes());assert view(server.store,parent_id)==proof['project']
        for p in expected:
            if p['id']!=parent_id:assert view(server.store,p['id'])==p
        changed=journals(server.store)
        for name,rows in original_journals.items():
            if name=='projects':continue
            if name in {'events','project_versions'}:assert changed[name][:len(rows)]==rows
            else:assert changed[name]==rows,name
        parent=proof['project'];child=server.store.duplicate(parent_id,parent['revision']);assert child['approval'] is None
        assert 'source_reframe_reviews' not in child['document'] and 'reviewed_reframe_selection' not in child['shot_timeline']['snapshot']['metadata']
        inherited=child['document']['source_reframe_inherited_reviewed_history']
        assert [v['original_record'] for v in inherited]==parent['document']['source_reframe_reviews'] and all(v['authority_transferred'] is False and v['new_review_required'] is True for v in inherited)
        assert view(server.store,parent_id)==parent
        rows=json.loads((prior/'original-vision-history.json').read_bytes())
        for row in rows:assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        hashes=json.loads((prior/'source-hashes.json').read_bytes())
        for name,sha in hashes.items():assert file_sha(root/'assets'/name)==sha
        assert pipeline.calls==0 and not server.runner.run_one()
        projects=[view(server.store,p['id']) for p in server.store.list()];assert len(projects)==8
        write(out/'expected-projects.json',projects);write(out/'expected-scenes.json',[page(server.store,server.config,p['id']) for p in projects])
        write(out/'expected-journals.json',journals(server.store));write(out/'original-vision-history.json',rows);write(out/'source-hashes.json',hashes)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config_for(root),out/'public-source-crop.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-source-crop.zip',restore,expected_sha256=backup['sha256']));reopen(args)
    sources=('services/windows_native/source_reframe_vision.py','services/windows_native/source_reframe.py','services/windows_native/source_duplicate.py',
        'services/windows_native/auto_edit_timeline.py','services/windows_native/store.py','services/windows_native/server.py',
        'apps/api/app/vision_models.py','apps/studio-web/native-source-editor.mjs','apps/studio-web/native-source-crop-review.mjs',
        'apps/studio-web/tests/native-source-crop-review.test.mjs','services/windows_native/tests/test_source_reframe_vision.py',
        'services/windows_native/tests/test_official_vision_http.py','scripts/north_star_source_crop.py','scripts/north_star_source_crop.mjs')
    write(out/'evidence.json',{'schema_version':'native-reviewed-source-crop-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in sources},
        'signed_http_requests':len(proof['calls'])+1,'explicit_format_crop_versions':4,'unapproved_duplicate':1,'new_mock_requests':0,'new_cpu_jobs':0,
        'original_source_asr_vision':'preserved owned synthetic media and explicit fixtures, not genuine provider acceptance',
        'new_external_dispatches':0,'new_paid_operations':0,'all_previous_projects_recommendations_results_costs_source_bytes_exact':True,
        'dom_controller_tested':True,'actual_parent_browser_executed':False,'full_qc_or_new_final_render':False,
        'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,'public_backup_sha256':backup['sha256'],
        'prior_public_backup_sha256':saved['sha256'],'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_requests':len(proof['calls'])+1,'four_reviewed_crop_versions':True,'fresh8_project_restore_exact':True}))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prior',type=Path);p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
