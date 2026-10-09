"""Retained real local PNG/SQLite/DPAPI + signed Studio DOM controllers/recovery."""
import argparse,json,re,subprocess,sys,threading,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'apps/api'))
import httpx
from PIL import Image
from services.windows_native.server import LocalServer
from services.windows_native.store import Store
from services.windows_native.pipeline import Pipeline
from services.windows_native.media import ingest_media
from services.windows_native.vision_credentials import NativeVisionKeyVault,PrivateVisionKey
from services.windows_native.vision_registry import NativeVisionFactory
from services.windows_native.tests.test_vision_registry import profile
from services.windows_native.tests.test_workflow import proposal
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.costs import CostLedger
from services.windows_native.contracts import file_sha
from services.windows_native.backup import create_backup,restore_backup,database_status
from scripts.north_star_official_vision import config_for,write,WORKSPACE
from scripts.north_star_official_vision_http import access
from scripts.north_star_vision_registry import journals

def owned(path,kind,fresh=False):
    path=path.resolve()
    if path.parent!=Path('C:/') or not re.fullmatch(r'vf-native-fixture-reviewed-vision-'+kind+r'-[0-9]{2}',path.name) or fresh and path.exists():
        raise ValueError('Fresh owned reviewed Vision fixture required')
    return path

def reopen(args):
    root=owned(args.restore_root,'restore');out=args.output.resolve();_,identity=access()
    with LocalServer(0,config_for(root),pipeline=NoProviderPipeline(),start_worker=False,access=identity) as server:
        proof=json.loads((out/'node-controller-proof.json').read_bytes());project=proof['project'];row=proof['original_vision']
        assert server.store.get(project['id'])==project and server.media_planner.page(project['id'])==proof['applied_page']
        assert server.official_vision.get(project['id'],row['vision_id'])==row
        assert journals(server.store)==json.loads((out/'expected-journals.json').read_bytes())
        assert not server.official_vision.states()['enabled'] and server.official_vision.states()['profiles']==[]
        assert not server.runner.run_one() and server.official_vision.recover()==0 and database_status(server.store.db)['active_operations']==0
    write(out/('new-process-replay.json' if args.new_process else 'restored-in-process.json'),{
        'original_vision_and_all_plan_versions_current_project_journals_exact':True,'keyless_disabled_provider_history':True,
        'provider_consent_renewed':False,'provider_retry_or_dispatch':False,'real_provider_tested':False,'owner_uat_accepted':False})

def run(args):
    state=owned(args.state_root,'state',True);restore=owned(args.restore_root,'restore',True);private=owned(args.private_root,'private',True);out=args.output.resolve()
    if out.exists() or out==ROOT or ROOT in out.parents:raise ValueError('Fresh external evidence required')
    out.mkdir(parents=True);config=config_for(state);store=Store(state);raw,identity=access();identity.bind_root(state)
    source=out/'explicit-owned-technology-fixture.png';Image.new('RGB',(480,270),(22,112,195)).save(source)
    asset=ingest_media(config,source,'image/png','Technology AI educational owned synthetic fixture',rights_confirmed=True,illustration=True)
    project=store.create('Technology AI education reviewed Vision fixture','','media');project=store.append_media(project['id'],project['revision'],asset)
    draft=proposal('AI technology education')
    for scene in draft['visual_brief']:scene['visual']='Technology AI educational supporting image'
    project=store.save(project['id'],project['revision'],proposal=draft,scene_media=[{'scene':i+1,'asset_id':asset['id']} for i in range(3)])
    job=store.enqueue(project['id'],project['revision'],'media_frames',uuid.uuid4().hex);job=store.claim()
    store.finish(job,result=Pipeline(config).run(job,lambda _:None));project=store.get(project['id'])
    CostLedger(store).set_budget(project['id'],project['revision'],'1000')
    vault=NativeVisionKeyVault(private,state,WORKSPACE);receipt=vault.save(PrivateVisionKey(workspace_id=WORKSPACE,credential_alias='explicit-reviewed-vision',api_key='sk-explicit-synthetic-reviewed-vision-not-real'))
    selected=profile(receipt);wire=[]
    def response(request):
        body=json.loads(request.content);count=sum(v['type']=='input_image' for v in body['input'][0]['content'])
        assert str(request.url)=='https://api.openai.com/v1/responses' and body['store'] is False
        wire.append({'mock':True,'frame_count':count,'fixed_endpoint':True});return httpx.Response(200,json=response_payload(count))
    factory=NativeVisionFactory(selected,vault,operator_enabled=True,transport=httpx.MockTransport(response));pipeline=NoProviderPipeline()
    server=LocalServer(0,config,pipeline=pipeline,start_worker=False,access=identity,official_vision_directory=private,
        official_vision_enabled=True,official_vision_factories={selected.profile_id:factory})
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with (out/'node-controller-proof.json').open('xb') as stdout,(out/'node-controller-errors.log').open('xb') as stderr:
            result=subprocess.run(['C:/Program Files/nodejs/node.exe','scripts/north_star_reviewed_vision.mjs'],cwd=ROOT,
                input=json.dumps({'origin':'http://127.0.0.1:'+str(server.server_port),'token':raw,'project':project['id']}).encode(),stdout=stdout,stderr=stderr,timeout=60)
        assert result.returncode==0,(out/'node-controller-errors.log').read_text()
        proof=json.loads((out/'node-controller-proof.json').read_bytes());assert proof['signed_http'] and len(wire)==1 and pipeline.calls==0
        assert server.media_planner.page(project['id'])==proof['applied_page'];assert server.store.get(project['id'])==proof['project']
        original=proof['original_vision'];assert server.official_vision.get(project['id'],original['vision_id'])==original
        assert original['result']['mock'] and not original['result']['semantic_inference_performed']
        versions=proof['project']['document']['studio_media_plans'];assert len(versions)==3
        assert versions[0]['plan']['algorithm']=='native-storyboard-media-planner-v2' and versions[1]['plan']['algorithm']==versions[2]['plan']['algorithm']=='native-storyboard-media-planner-v3'
        assert all(not v['plan']['semantic_vision_used'] for v in versions)
        cost=server.official_vision.costs.summary(project['id']);assert len(cost['records'])==1 and cost['records'][0]['actual_cost'] is None and not cost['records'][0]['paid']
        assert file_sha(state/'assets'/asset['id'])==asset['sha256'] and not server.runner.run_one()
        write(out/'expected-journals.json',journals(server.store));write(out/'cost-summary.json',cost);write(out/'mock-wire-summary.json',wire)
    finally:server.shutdown();server.server_close();thread.join()
    backup=create_backup(config,out/'public-reviewed-vision.zip');write(out/'backup.json',backup)
    write(out/'restore.json',restore_backup(out/'public-reviewed-vision.zip',restore,expected_sha256=backup['sha256']));reopen(args)
    names=('services/windows_native/official_vision_evidence.py','services/windows_native/studio_media_planner.py','services/windows_native/studio_media_models.py',
        'services/windows_native/server.py','services/windows_native/tests/test_official_vision_evidence.py','services/windows_native/tests/test_studio_reviewed_vision.py',
        'apps/studio-web/native-media-planner.mjs','apps/studio-web/native.mjs','apps/studio-web/tests/native-media-planner.test.mjs',
        'scripts/north_star_reviewed_vision.py','scripts/north_star_reviewed_vision.mjs')
    write(out/'evidence.json',{'schema_version':'native-reviewed-vision-rehearsal-v1','source_sha256':{name:file_sha(ROOT/name) for name in names},
        'signed_http_requests':len(proof['calls'])+1,'new_cpu_png_measurement_jobs':1,'actual_owned_source_dimensions':[480,270],
        'new_mock_requests':1,'new_complete_responses':1,'plan_history_versions':3,'explicit_canonical_apply':1,
        'original_source_response_cost_binding_exact':True,'mock_semantic_ranking_used':False,'new_external_dispatches':0,'new_paid_operations':0,
        'actual_parent_browser_executed':False,'full_media_qc_or_final_render':False,'owner_uat_accepted':False,'real_provider_tested':False,'production_deployed':False,
        'public_backup_sha256':backup['sha256'],'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status':'PASS','signed_http_requests':len(proof['calls'])+1,'mock_requests':1,'plan_history_versions':3,'fresh_recovery_exact':True}))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--state-root',type=Path)
    parser.add_argument('--restore-root',type=Path,required=True);parser.add_argument('--private-root',type=Path);parser.add_argument('--new-process',action='store_true');args=parser.parse_args()
    reopen(args) if args.new_process else run(args)
