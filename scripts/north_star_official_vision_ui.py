"""Retained Studio controller/real local HTTP plus public-only fresh recovery."""
import argparse,json,re,subprocess,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from scripts.north_star_official_vision import config_for,write,WORKSPACE
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals
from services.windows_native.server import LocalServer
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.vision_registry import VisionProfile,NativeVisionFactory
from services.windows_native.vision_credentials import NativeVisionKeyVault
from services.windows_native.vision import NativeVision
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status

def owned(path,kind,fresh=False):
 path=path.resolve()
 if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-official-vision-ui-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():raise ValueError('Fresh owned official Vision UI fixture required')
 return path

def reopen(args):
 root=owned(args.restore_root,'restore');out=args.output.resolve();raw,identity=access()
 with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
  rows=json.loads((out/'expected-all-official-history.json').read_bytes())
  for row in rows:assert server.official_vision.get(row['project_id'],row['vision_id'])==row
  for project in json.loads((out/'expected-projects.json').read_bytes()):assert server.store.get(project['id'])==project
  legacy=NativeVision(server.store,server.config)
  for row in json.loads((out/'expected-legacy-history.json').read_bytes()):assert legacy.get(row['project_id'],row['vision_id'])==row
  before=journals(server.store);assert before==json.loads((out/'expected-all-journals.json').read_bytes())
  assert server.official_vision.recover()==0 and not server.runner.run_one() and journals(server.store)==before and database_status(server.store.db)['active_operations']==0
  assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
 write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{'all_current_journals_exact':True,'journal_count':len(before),'all_official_histories_exact':len(rows),
  'original_projects_legacy_history_exact':True,'current_credentials_config_identity_required_for_history':False,'startup_decryption':False,'retry_dispatch_consent_renewal':False,'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
 state=owned(args.state_root,'state',True);restored=owned(args.restore_root,'restore',True);out=args.output.resolve();prior=args.http_input.resolve()
 if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
 out.mkdir(parents=True);archive=prior/'public-official-vision-http.zip';write(out/'prior-restore.json',restore_backup(archive,state,expected_sha256=file_sha(archive)))
 projects=json.loads((prior/'expected-projects.json').read_bytes());old=json.loads((prior/'expected-all-official-history.json').read_bytes());legacy=json.loads((prior/'expected-legacy-history.json').read_bytes());before_journals=json.loads((prior/'expected-all-journals.json').read_bytes())
 files={p.relative_to(state).as_posix():file_sha(p) for p in state.rglob('*') if p.is_file() and p.suffix!='.sqlite3' and not p.name.endswith(('-wal','-shm'))}
 private=Path('C:/vf-native-fixture-vision-registry-secrets-01');private_hashes={p.name:file_sha(p) for p in private.glob('*.dpapi')}
 raw,identity=access();config=config_for(state);vault=NativeVisionKeyVault(private,state,WORKSPACE);profile=VisionProfile.model_validate(json.loads((private/'public-vision-registry.json').read_bytes())['profiles'][0]);wire=[]
 def response(request):
  body=json.loads(request.content);count=sum(v['type']=='input_image' for v in body['input'][0]['content']);assert str(request.url)=='https://api.openai.com/v1/responses' and body['store'] is False
  wire.append({'frame_count':count,'mock':True,'fixed_endpoint':True});payload=response_payload(count)
  if len(wire)==3:payload['output'][0]['content'][0]['text']='INVALID EXPLICIT STUDIO STRUCTURED MOCK'
  return httpx.Response(200,json=payload)
 factory=NativeVisionFactory(profile,vault,operator_enabled=True,transport=httpx.MockTransport(response));pipeline=NoProviderPipeline()
 server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity,official_vision_directory=private,official_vision_enabled=True,official_vision_factories={profile.profile_id:factory})
 thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
 try:
  with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
   result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_official_vision_ui.mjs'],cwd=ROOT,
    input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'projects':[p['id'] for p in projects]}).encode(),stdout=stdout,stderr=stderr,timeout=60)
  assert result.returncode==0;proof=json.loads((out/'node-controller-proof.json').read_bytes());assert len(proof['rows'])==4 and proof['signed_http'] and not proof['actual_parent_browser_executed']
  new=[server.official_vision.get(row['project_id'],row['vision_id']) for row in proof['rows']];assert new==proof['rows'];assert len(wire)==3 and sum(v['result'] is not None for v in new)==2 and sum(v['response'] is not None for v in new)==3
  for row in old:assert server.official_vision.get(row['project_id'],row['vision_id'])==row
  for project in projects:assert server.store.get(project['id'])==project
  fixture=NativeVision(server.store,config)
  for row in legacy:assert fixture.get(row['project_id'],row['vision_id'])==row
  current=journals(server.store)
  for table,rows in before_journals.items():assert all(row in current[table] for row in rows),table
  assert all(file_sha(state/name)==value for name,value in files.items()) and all(file_sha(private/name)==value for name,value in private_hashes.items())
  assert not server.runner.run_one() and pipeline.calls==0
  costs=[server.official_vision.costs.summary(p['id']) for p in projects];assert all(r['actual_cost'] is None and not r['paid'] and not r['external_call'] for p in costs for r in p['records'])
  write(out/'expected-all-official-history.json',old+new);write(out/'expected-projects.json',projects);write(out/'expected-legacy-history.json',legacy);write(out/'expected-all-journals.json',current);write(out/'mock-wire-summary.json',wire);write(out/'cost-summary.json',costs)
 finally:server.shutdown();server.server_close();thread.join()
 backup=create_backup(config,out/'public-official-vision-ui.zip');write(out/'backup.json',backup);write(out/'restore.json',restore_backup(out/'public-official-vision-ui.zip',restored,expected_sha256=backup['sha256']));reopen(args)
 names=('apps/studio-web/native-official-vision.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/tests/native-official-vision.test.mjs','apps/studio-web/tests/fixtures/native-official-vision-v1.json','services/windows_native/server.py','services/windows_native/tests/test_official_vision_http.py','scripts/north_star_official_vision_ui.py','scripts/north_star_official_vision_ui.mjs')
 write(out/'evidence.json',{'schema_version':'native-official-vision-ui-rehearsal-v1','source_sha256':{n:file_sha(ROOT/n) for n in names},'signed_http_requests':len(proof['calls'])+1,
  'new_finite_intents':4,'new_mock_requests':3,'new_complete_responses':3,'new_mock_results':2,'all_current_journals':len(current),'all_official_histories':len(old+new),
  'reused_unique_pngs':9,'new_cpu_jobs':0,'original_projects_media_histories_private_generations_exact':True,'session_shape_default_false_flag_exact':True,
  'explicit_source_finite_budget_raw_mock_consent_separate_manual_process_cancel_review_history':True,'parent_source_and_static_checked':True,'actual_browser_executed':False,
  'current_keys_or_config_for_restored_history_required':False,'real_credentials':False,'external_provider_calls':0,'paid_operations':0,'semantic_inference_performed':False,'owner_uat_accepted':False,
  'publishing_enabled':False,'real_provider_tested':False,'production_deployed':False,'public_backup_sha256':backup['sha256'],
  'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
 print(json.dumps({'status':'PASS','signed_http_requests':len(proof['calls'])+1,'new_mock_requests':3,'all_current_journals':len(current),'all_official_histories':len(old+new)}))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--http-input',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--state-root',type=Path);p.add_argument('--restore-root',type=Path,required=True);p.add_argument('--new-process',action='store_true');args=p.parse_args()
 reopen(args) if args.new_process else run(args)
