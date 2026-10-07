"""Fresh-root durable Native queue rehearsal; no worker or external call.

Provider observations are explicit fixtures. Only SQLite/admission/claim/cost
intent/cancel/reconciliation/reopen behavior is local-real evidence here.
"""
import argparse,hashlib,json,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from services.windows_native.contracts import file_sha
from services.windows_native.backup import guard
from services.windows_native.store import Store
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_registry import GenerationCredential,GenerationFactory
from services.windows_native.generation_models import GenerationCreate,GenerationAction,GenerationRecovery,NativeImageParameters
from services.windows_native.generation_references import api_parameters
import httpx
WORKSPACE='wsp_native_generation_queue_rehearsal'
TOKEN='explicit-queue-rehearsal-fixture-token-32'


def write(path,value):
    with path.open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2,allow_nan=False);file.write('\n')


def snapshot(root):
    store=Store(root);service=NativeGenerationQueue(store,workspace_id=WORKSPACE)
    with store.transaction() as con:
        projects=[store.project(row) for row in con.execute('SELECT * FROM projects ORDER BY id')]
        events=[dict(row) for row in con.execute('SELECT * FROM native_generation_events ORDER BY sequence')]
        requests=[dict(row) for row in con.execute('SELECT * FROM native_generation_recovery_requests ORDER BY generation_id,key_sha256')]
        versions=[dict(row) for row in con.execute('SELECT * FROM project_versions ORDER BY project_id,revision')]
    return {'projects':projects,'pages':[service.page(p['id'],limit=200) for p in projects],'events':events,'reconciliation_requests':requests,
        'versions':versions,'costs':[service.costs.summary(p['id']) for p in projects],'default_claim':service.claim()}


def main(args):
    if args.reopen:
        actual=snapshot(args.data_root);expected=json.loads((args.output_root/'offline-snapshot.json').read_bytes());assert actual==expected
        write(args.output_root/'new-process-replay.json',{'exact_replay':True,'default_execution_enabled':False,'external_calls':0,
            'native_worker_http_ui_wired':False,'mock_provider_observations':True,'projects':len(actual['projects']),'generation_jobs':sum(len(p['items']) for p in actual['pages'])})
        print(json.dumps({'status':'NATIVE_GENERATION_QUEUE_NEW_PROCESS_REPLAY_PASS','external_calls':0}));return
    for path in [args.data_root,args.output_root]:
        if not path.is_absolute() or path.exists():raise ValueError('FRESH_ABSOLUTE_ROOT_REQUIRED')
        guard(path);path.mkdir(parents=True,exist_ok=False)
    store=Store(args.data_root);project=store.create('EXPLICIT QUEUE REHEARSAL','EXPLICIT PRIVATE SYNTHETIC INPUT');before=store.get(project['id'])
    default=NativeGenerationQueue(store,workspace_id=WORKSPACE);params=NativeImageParameters(prompt='EXPLICIT DURABLE QUEUE FIXTURE, NOT AI')
    inactive,_=default.create(project['id'],GenerationCreate(revision=1,parameters=params,external_acknowledged=True,request_key='explicit-not-configured-queue-rehearsal'),actor='explicit-editor-fixture')
    assert inactive['status']=='not_configured' and default.claim() is None
    calls=[]
    def forbidden(request):calls.append(request.method);raise AssertionError('External requests are forbidden in queue rehearsal')
    factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,transport=httpx.MockTransport(forbidden))
    clock=[time.time()];service=NativeGenerationQueue(store,workspace_id=WORKSPACE,factory=factory,clock=lambda:clock[0]);receipts=[]
    for index in range(2):
        request=GenerationCreate(revision=1,parameters=params,fixture_acknowledged=True,request_key=f'explicit-active-queue-rehearsal-{index}')
        job,replay=service.create(project['id'],request,actor='explicit-editor-fixture');assert not replay
        again,yes=service.create(project['id'],request,actor='explicit-editor-fixture');assert yes and again==job
        claim=service.claim();assert claim['mode']=='create' and service.claim() is None
        service.bind_input(claim,api_parameters(params,{}));operation=service.costs.begin(project_id=project['id'],provider='comfyui-image',
            model='workflow:'+job['snapshot']['selection']['workflow_id'],operation='generation.'+job['generation_id']+'.submit',
            request_sha256=job['request_fingerprint'],estimated_cost=None,external_call=True,paid=False)
        service.mark_dispatch(claim,operation)
        observation={'schema_version':'comfyui-generation-observation-v1','phase':'submitted','provider_job_id':f'cui_explicit_queue_rehearsal_{index}',
            'workspace_id':WORKSPACE,'workflow_id':job['snapshot']['selection']['workflow_id'],'workflow_version':job['snapshot']['selection']['workflow_version'],
            'status':'running','progress':15}
        service.observe(claim,observation);assert service.observe(claim,observation) is False
        if index==0:
            pending=service.cancel(project['id'],job['generation_id'],GenerationAction(expected_fingerprint=job['request_fingerprint']),actor='explicit-editor-fixture')
            assert pending['status']=='running' and pending['cancel_requested']
            service.observe(claim,{**observation,'phase':'cancel_response','status':'cancelled'});service.fail(claim,'EXPLICIT_MOCK_CANCEL_CONFIRMED')
        else:
            clock[0]+=901;assert service.claim() is None
            receipt=service.recover(project['id'],job['generation_id'],GenerationRecovery(expected_fingerprint=job['request_fingerprint'],acknowledged=True,
                request_key='explicit-read-only-recovery-rehearsal'),actor='explicit-editor-fixture');receipts.append(receipt)
            assert not receipt['generation_submission_authorized'];recovered=service.claim();assert recovered['mode']=='reconcile'
            service.observe(recovered,{**observation,'phase':'reconciled'});service.fail(recovered,'EXPLICIT_MOCK_RECONCILIATION_PAUSED')
    assert not calls and store.get(project['id'])==before
    write(args.output_root/'reconciliation-receipts.json',receipts);write(args.output_root/'offline-snapshot.json',snapshot(args.data_root))
    sources=['services/windows_native/generation_queue.py','services/windows_native/generation_models.py','scripts/north_star_native_generation_queue.py']
    write(args.output_root/'evidence.json',{'schema_version':'north-star-native-generation-queue-v1','workspace_id':WORKSPACE,'project_id':project['id'],
        'data_root':str(args.data_root),'local_real_sqlite_and_claims':True,'mock_provider_observations':True,'external_requests':0,'generation_posts':0,
        'generation_result_assets':0,'paid_operations':0,'actual_cost_vnd':None,'canonical_project_mutated':False,'native_worker_http_ui_wired':False,
        'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
        'exports':{path.name:{'sha256':file_sha(path),'bytes':path.stat().st_size} for path in args.output_root.iterdir() if path.is_file()}})
    print(json.dumps({'status':'NATIVE_GENERATION_QUEUE_DURABLE_CONTRACT_PASS','generation_jobs':3,'external_requests':0}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    main(parser.parse_args())
