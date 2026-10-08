"""Actual Native worker/bridge decoding with synthetic pixels and mock GPU wires.

An independent bridge loop survives a lost submission reply. No generation
result is manually injected. Recovery uses lookup or the actual staged receipt.
"""
import argparse,asyncio,hashlib,importlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'services/comfyui-bridge'),str(ROOT/'apps/api'),str(ROOT/'scripts')]
from north_star_comfyui_http_backend import fixture_manifest,GPUWireFixture,GPU_TOKEN,sha,write,fresh
WORKSPACE='wsp_native_generation_worker_rehearsal'
TOKEN='explicit-native-worker-rehearsal-token-32-characters'


def snapshot(data):
    from services.windows_native.store import Store
    from services.windows_native.pipeline import Config
    from services.windows_native.generation_queue import NativeGenerationQueue
    from services.windows_native.generation_worker import NativeGenerationWorker
    native=Store(data/'native');queue=NativeGenerationQueue(native,workspace_id=WORKSPACE);worker=NativeGenerationWorker(queue,Config(data_root=native.root))
    with native.transaction() as con:
        projects=[native.project(r) for r in con.execute('SELECT * FROM projects ORDER BY id')]
        events=[dict(r) for r in con.execute('SELECT * FROM native_generation_events ORDER BY sequence')]
        versions=[dict(r) for r in con.execute('SELECT * FROM project_versions ORDER BY project_id,revision')]
        imports=[dict(r) for r in con.execute('SELECT * FROM native_generation_imports ORDER BY generation_id')]
        admissions=[dict(r) for r in con.execute('SELECT * FROM native_generation_reference_admissions ORDER BY generation_id,asset_id')]
        for row in admissions:queue.references.read(row,json.loads(row['snapshot_json']))
    pages=[worker.page(p['id'],limit=200) for p in projects]
    for page in pages:
        for job in page['items']:worker.asset_file(job['project_id'],job['generation_id'])
    return {'projects':projects,'pages':pages,'versions':versions,'events':events,'imports':imports,'admissions':admissions,
        'costs':[queue.costs.summary(p['id']) for p in projects],'default_execution_enabled':False}


async def run(args):
    import httpx
    from PIL import Image
    from services.windows_native.store import Store
    from services.windows_native.pipeline import Config
    from services.windows_native.media import ingest_media
    from services.windows_native.contracts import WorkflowError
    from services.windows_native.generation_models import GenerationCreate,GenerationRecovery,GenerationImport,NativeImageParameters,NativeVideoParameters
    from services.windows_native.generation_registry import GenerationCredential,GenerationFactory
    from services.windows_native.generation_queue import NativeGenerationQueue
    from services.windows_native.generation_worker import NativeGenerationWorker
    if args.reopen:
        actual=snapshot(args.data_root);assert actual==json.loads((args.output_root/'offline-snapshot.json').read_bytes())
        write(args.output_root/'new-process-replay.json',{'exact_replay':True,'default_execution_enabled':False,'external_requests':0,
            'generation_results':sum(len(p['items']) for p in actual['pages']),'imports':len(actual['imports']),'physical_media_hashes_verified':True,
            'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False})
        print(json.dumps({'status':'NATIVE_GENERATION_WORKER_NEW_PROCESS_PASS','results':3,'external_requests':0}));return
    fresh(args.data_root);fresh(args.output_root);manifest=fixture_manifest(args.data_root,references=True)
    # Existing bridge fixtures use 128x72 pixels. This new consumer rehearsal
    # uses a distinct manifest and 640x360 outputs meeting Native image limits.
    definitions=json.loads(manifest.read_bytes())
    for definition in definitions['workflows']:
        graph_path=manifest.parent/definition['graph_file'];graph=json.loads(graph_path.read_bytes());graph['prompt']['2']['inputs'].update(width=640,height=360)
        graph_path.write_text(json.dumps(graph),encoding='utf-8');definition['execution']['graph_sha256']=sha(graph_path);definition['execution']['aspect_dimensions']={'16:9':[640,360]}
    manifest.write_text(json.dumps(definitions),encoding='utf-8')
    native=Store(args.data_root/'native');config=Config(data_root=native.root);project=native.create('EXPLICIT WORKER REHEARSAL','EXPLICIT SYNTHETIC INPUT')
    assets=[]
    for name,color in [('source',(30,90,140)),('mask',(255,255,255))]:
        path=args.data_root/(name+'.png');Image.new('RGB',(320,240),color).save(path)
        asset=ingest_media(config,path,'image/png',path.name,rights_confirmed=True,illustration=False)
        asset.update(source_type='synthetic_fixture',rights_status='owned',license='locally_generated_synthetic_fixture',provider='local-pillow-fixture',
            generation_provenance={'fixture':True,'creator':'local-synthetic-rehearsal'},explicit_fixture=True,production_eligible=False)
        project=native.append_media(project['id'],project['revision'],asset);assets.append(asset)
    before=native.get(project['id']);binaries={}
    for suffix in ['png','mp4']:
        path=args.data_root/('synthetic-output.'+suffix);command=[str(args.ffmpeg),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=10:duration=0.6']
        command+=['-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart'] if suffix=='mp4' else ['-frames:v','1']
        subprocess.run([*command,str(path)],check=True,timeout=20,capture_output=True);binaries[suffix]=path.read_bytes()
    os.environ.update({'COMFYUI_BACKEND':'disabled','COMFYUI_EXECUTION_ENABLED':'false','APP_ENV':'development','COMFYUI_BRIDGE_TOKEN':TOKEN,
        'COMFYUI_WORKFLOW_MANIFEST':str(manifest),'COMFYUI_JOB_STORE_PATH':str(args.data_root/'bridge/jobs.sqlite3'),
        'COMFYUI_ARTIFACT_ROOT':str(args.data_root/'bridge/artifacts'),'COMFYUI_REFERENCE_ROOT':str(args.data_root/'bridge/references'),
        'COMFYUI_REFERENCE_INTAKE_ENABLED':'true','COMFYUI_FFMPEG_PATH':str(args.ffmpeg),'COMFYUI_FFPROBE_PATH':str(args.ffprobe)})
    from npd_comfyui_bridge.http_backend import ReviewedHTTPComfyUIBackend
    from npd_comfyui_bridge.http_transport import ComfyHTTPTransport
    from npd_comfyui_bridge.reference_stager import ScopedReferenceStager
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    bridge=importlib.import_module('npd_comfyui_bridge.main');await bridge.service.close();wire=GPUWireFixture(binaries)
    store=SQLiteBridgeJobStore(args.data_root/'bridge/jobs.sqlite3')
    gpu=ComfyHTTPTransport(origin='http://127.0.0.1:8188',server_source_sha256='0'*64,enabled=True,bearer_token=GPU_TOKEN,transport=httpx.MockTransport(wire.handle))
    backend=ReviewedHTTPComfyUIBackend(registry=bridge.registry,transport=gpu,job_store=store,artifacts=bridge.app.state.binary_artifact_store,poll_seconds=.01,
        reference_resolver=ScopedReferenceStager(references=bridge.app.state.reference_store,transport=gpu,job_store=store))
    bridge.backend=backend;bridge.service=ComfyUIBridgeService(bridge.registry,backend,job_store=store);bridge.app.state.bridge_service=bridge.service
    calls=[];lost=[True];bridge_loop=asyncio.get_running_loop()
    async def dispatch(request):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=bridge.app),base_url='http://fixture') as client:
            return await client.request(request.method,request.url.path,content=request.content,headers=dict(request.headers))
    async def native_wire(request):
        assert request.headers['Authorization']=='Bearer '+TOKEN and request.headers['X-VF-Workspace-Id']==WORKSPACE
        calls.append({'method':request.method,'path':request.url.path})
        response=await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(dispatch(request),bridge_loop))
        if request.method=='POST' and request.url.path=='/v1/jobs' and lost[0]:lost[0]=False;raise httpx.ReadError('EXPLICIT LOST GENERATION REPLY')
        return response
    factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,
        transport=httpx.MockTransport(native_wire),manifest_path=manifest)
    queue=NativeGenerationQueue(native,workspace_id=WORKSPACE,factory=factory);worker=NativeGenerationWorker(queue,config)
    ref=lambda asset:{'asset_id':asset['id'],'asset_sha256':asset['sha256']}
    cases=[NativeImageParameters(prompt='EXPLICIT LOST-REPLY IMAGE FIXTURE',aspect_ratio='16:9',seed=51),
        NativeVideoParameters(prompt='EXPLICIT VIDEO WORKER FIXTURE',mode='image_to_video',references=[ref(assets[0])],aspect_ratio='16:9',seed=29,duration_seconds=.6),
        NativeImageParameters(prompt='EXPLICIT INPAINT WORKER FIXTURE',operation='inpaint',references=[ref(assets[0]),ref(assets[0])],mask=ref(assets[1]),aspect_ratio='16:9',seed=52)]
    jobs=[];recoveries=[]
    try:
        for index,value in enumerate(cases):
            job,_=queue.create(project['id'],GenerationCreate(revision=project['revision'],parameters=value,fixture_acknowledged=True,
                request_key=f'explicit-generation-worker-case-{index}'),actor='explicit-editor-fixture');jobs.append(job)
            original_finish=worker.finish
            if index==2:
                def crash(*_,**__):raise WorkflowError('EXPLICIT_CRASH_AFTER_PERSISTED_MEDIA_STAGE')
                worker.finish=crash
            await asyncio.to_thread(worker.process);worker.finish=original_finish
            if index in (0,2):
                interrupted=worker.get(project['id'],job['generation_id']);assert interrupted['status']=='recovery_required'
                if index==0:assert interrupted['provider_job_id'] is None
                write(args.output_root/f'{index}-interrupted-job.json',interrupted)
                recoveries.append(queue.recover(project['id'],job['generation_id'],GenerationRecovery(expected_fingerprint=job['request_fingerprint'],
                    acknowledged=True,request_key=f'explicit-worker-read-only-recovery-{index}'),actor='explicit-editor-fixture'))
                before_calls=len(calls);await asyncio.to_thread(worker.process)
                if index==2:assert len(calls)==before_calls
            result=worker.get(project['id'],job['generation_id']);assert result['status']=='succeeded' and result['result']['asset']['rights_status']=='unknown'
            assert result['result']['mode']==['reconcile','create','local_stage_recovery'][index] and not result['result']['production_eligible']
            write(args.output_root/f'{index}-completed-job.json',result);asset=result['result']['asset']
            for directory,key,label in [('assets','id','normalized'),('originals','original_id','original'),('assets','thumbnail_id','thumbnail')]:
                source=native.root/directory/asset[key];shutil.copyfile(source,args.output_root/f'{index}-{label}{source.suffix}')
        assert native.get(project['id'])==before
        write(args.output_root/'pre-attachment-project.json',before);attachments=[]
        for job in jobs:
            result=worker.get(project['id'],job['generation_id']);current=native.get(project['id']);request=GenerationImport(revision=current['revision'],
                expected_fingerprint=job['request_fingerprint'],expected_asset_sha256=result['result']['asset']['sha256'],acknowledged=True,request_key='explicit-generation-worker-import-'+job['generation_id'])
            receipt=worker.attach(project['id'],job['generation_id'],request,actor='explicit-editor-fixture');assert worker.attach(project['id'],job['generation_id'],request,actor='explicit-editor-fixture')['idempotent_replay']
            attachments.append(receipt)
        current=native.get(project['id']);assert current['revision']==before['revision']+3 and current['approval'] is None
        assert current['document'].get('canonical_timeline')==before['document'].get('canonical_timeline')
        assert sum(c['path']=='/v1/jobs' and c['method']=='POST' for c in calls)==3
        assert sum(c['path'].startswith('/v1/jobs/by-client-request/') for c in calls)==1
        assert sum(c['path']=='/v1/references' and c['method']=='POST' for c in calls)==3
        assert sum(c['path']=='/prompt' for c in wire.calls)==3 and sum(c['path']=='/upload/image' for c in wire.calls)==3
        costs=queue.costs.summary(project['id']);assert len(costs['records'])==6 and all(r['actual_cost'] is None and not r['paid'] for r in costs['records'])
        write(args.output_root/'recovery-requests.json',recoveries);write(args.output_root/'attachment-receipts.json',attachments)
        write(args.output_root/'native-service-wires.json',calls);write(args.output_root/'gpu-fixture-wires.json',wire.calls)
    finally:await bridge.service.close()
    write(args.output_root/'offline-snapshot.json',snapshot(args.data_root))
    files=['services/windows_native/generation_worker.py','services/windows_native/generation_queue.py','services/windows_native/generation_media.py',
        'services/windows_native/observability.py','scripts/north_star_native_generation_worker.py']
    write(args.output_root/'evidence.json',{'schema_version':'north-star-native-generation-worker-v1','explicit_fixture':True,'workspace_id':WORKSPACE,
        'project_id':project['id'],'data_root':str(args.data_root),'actual_local_decoded_outputs':3,'native_reference_admissions':3,'native_worker_wired':True,
        'generation_submission_writes':3,'mock_gpu_prompt_writes':3,'mock_gpu_reference_uploads':3,'mock_native_reference_intake_writes':3,'read_only_lookup_count':1,
        'lost_submission_reply_reconciled_without_second_submit':True,'persisted_stage_crash_recovered_without_provider_calls':True,'duplicate_reference_hash_binding_passed':True,
        'generation_results_manually_injected':False,'explicit_attachment_receipts':3,'cost_operations':6,'actual_cost_vnd':None,'paid_operations':0,
        'automatic_attachment':False,'canonical_timeline_auto_edited':False,'rights_independently_verified':False,'rights_status':'unknown','production_eligible':False,
        'native_http_assets_ui_wired':False,'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{name:sha(ROOT/name) for name in files},'exports':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in args.output_root.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_GENERATION_WORKER_REAL_BYTES_MOCK_GPU_PASS','outputs':3,'submissions':3,'explicit_imports':3,'real_provider':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True);parser.add_argument('--ffprobe',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    parser.add_argument('--native-site-packages',type=Path);options=parser.parse_args()
    if options.native_site_packages:sys.path.append(str(options.native_site_packages))
    asyncio.run(run(options))
