"""Signed Source review controllers from exact prior public state; keyless recovery."""
import argparse,json,re,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.contracts import file_sha
from services.windows_native.auto_edit_timeline import view
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-source-broll-review-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned Source B-roll review fixture required')
    return path

def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        proof=json.loads((out/'node-controller-proof.json').read_bytes())
        for project in json.loads((out/'expected-projects.json').read_bytes()):assert view(server.store,project['id'])==project
        row=proof['original_vision'];assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        before=json.loads((out/'expected-journals.json').read_bytes());assert journals(server.store)==before
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
        assert server.official_vision.recover()==0 and not server.runner.run_one() and database_status(server.store.db)['active_operations']==0
        assert journals(server.store)==before
        for key,value in json.loads((out/'source-hashes.json').read_bytes()).items():assert file_sha(root/'assets'/key)==value
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'all_original_results_plan_versions_projects_journals_source_bytes_exact':True,'keyless_disabled_provider_history':True,
        'provider_consent_renewed':False,'provider_retry_or_dispatch':False,'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
    state=owned(args.state_root,'state',True);restore=owned(args.restore_root,'restore',True);out=args.output.resolve();prior=args.prior.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);archive=prior/'public-source-broll-vision.zip';backup=json.loads((prior/'backup.json').read_bytes())
    assert file_sha(archive)==backup['sha256'];write(out/'prior-restore.json',restore_backup(archive,state,expected_sha256=backup['sha256']))
    expected=json.loads((prior/'expected-projects.json').read_bytes());config=config_for(state);raw,identity=access();pipeline=NoProviderPipeline()
    server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        for project in expected:assert view(server.store,project['id'])==project
        with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
            result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_source_broll_review.mjs'],cwd=ROOT,
                input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':expected[0]['id']}).encode(),stdout=stdout,stderr=stderr,timeout=60)
        assert result.returncode==0,(out/'node-controller-errors.log').read_text()
        proof=json.loads((out/'node-controller-proof.json').read_bytes());assert proof['original_project']==expected[0]
        assert view(server.store,expected[0]['id'])==proof['project'] and view(server.store,expected[1]['id'])==expected[1]
        row=proof['original_vision'];assert server.official_vision.get(row['project_id'],row['vision_id'])==row
        for record in expected[0]['document']['source_broll_plans']:assert record in proof['project']['document']['source_broll_plans']
        hashes=json.loads((prior/'source-hashes.json').read_bytes())
        for key,value in hashes.items():assert file_sha(state/'assets'/key)==value
        costs=server.official_vision.costs.summary(expected[0]['id']);assert costs==json.loads((prior/'cost-summary.json').read_bytes())
        assert not server.runner.run_one() and pipeline.calls==0
        write(out/'expected-projects.json',[proof['project'],expected[1]]);write(out/'expected-journals.json',journals(server.store))
        write(out/'source-hashes.json',hashes);write(out/'cost-summary.json',costs)
    finally:server.shutdown();server.server_close();thread.join()
    saved=create_backup(config,out/'public-source-broll-review.zip');write(out/'backup.json',saved)
    write(out/'restore.json',restore_backup(out/'public-source-broll-review.zip',restore,expected_sha256=saved['sha256']));reopen(args)
    names=('apps/studio-web/native-source-broll-review.mjs','apps/studio-web/native-source-broll.mjs','apps/studio-web/native-source-editor.mjs',
        'apps/studio-web/native-media-planner.mjs','apps/studio-web/native.mjs','apps/studio-web/shot-studio.mjs',
        'apps/studio-web/tests/native-source-broll-review.test.mjs','apps/studio-web/tests/native-source-broll.test.mjs',
        'apps/studio-web/tests/fixtures/native-source-broll-reviewed-v1.json','services/windows_native/server.py',
        'services/windows_native/tests/test_official_vision_http.py','scripts/north_star_source_broll_review.py','scripts/north_star_source_broll_review.mjs')
    write(out/'evidence.json',{'schema_version':'native-source-broll-review-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in names},
        'signed_http_requests':len(proof['calls'])+1,'new_mock_requests':0,'new_cpu_jobs':0,'reused_source_video_seconds':3,
        'asr_source_analysis_and_vision':'preserved explicit fixtures, not genuine speech/provider acceptance',
        'plan_history_versions':4,'deduplicated_create_preserves_original_plan':True,'explicit_select_and_replace_apply':True,
        'source_audio_tracks_duration_bytes_original_result_and_cost_exact':True,'new_external_dispatches':0,'new_paid_operations':0,
        'dom_controller_tested':True,'actual_parent_browser_executed':False,'full_media_qc_or_final_render':False,
        'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,'public_backup_sha256':saved['sha256'],
        'prior_public_backup_sha256':backup['sha256'],'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_requests':len(proof['calls'])+1,'new_mock_requests':0,'plan_history_versions':4,'fresh_restore_exact':True}))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--prior',type=Path);p.add_argument('--state-root',type=Path)
    p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--new-process',action='store_true');args=p.parse_args()
    reopen(args) if args.new_process else run(args)
