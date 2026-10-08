"""Actual Native worker/bridge decoding with synthetic pixels and mock GPU wires.

An independent bridge loop survives a lost submission reply. No generation
result is manually injected. Recovery uses lookup or the actual staged receipt.
"""
import argparse,asyncio,hashlib,http.client,importlib,json,os,shutil,subprocess,sys,threading,time
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
        tables={row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        resolutions=[dict(row) for row in con.execute('SELECT * FROM native_media_resolutions ORDER BY resolution_id')] if 'native_media_resolutions' in tables else []
        from services.windows_native.studio_media_resolution import Binding
        from services.windows_native.contracts import digest
        for row in resolutions:
            value=Binding.model_validate(json.loads(row['binding_json']));assert digest(value.model_dump(mode='json'))==row['binding_sha256'] and value.workspace_id==WORKSPACE
    pages=[worker.page(p['id'],limit=200) for p in projects]
    for row in resolutions:
        value=json.loads(row['binding_json']);child=worker.get(value['project_id'],value['child_id'])
        assert child['request_fingerprint']==value['child_fingerprint'] and digest(child['snapshot']['request'])==value['child_request_sha256']
    for page in pages:
        for job in page['items']:worker.asset_file(job['project_id'],job['generation_id'])
    return {'projects':projects,'pages':pages,'versions':versions,'events':events,'imports':imports,'admissions':admissions,'storyboard_resolutions':resolutions,
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
    if args.studio_plan and not args.native_http:raise ValueError('Storyboard resolution rehearsal requires actual Native HTTP')
    if args.reopen:
        actual=snapshot(args.data_root);assert actual==json.loads((args.output_root/'offline-snapshot.json').read_bytes())
        if args.native_http:
            assert args.restore_root and snapshot(args.restore_root)==actual
        write(args.output_root/'new-process-replay.json',{'exact_replay':True,'default_execution_enabled':False,'external_requests':0,
            'generation_results':sum(len(p['items']) for p in actual['pages']),'imports':len(actual['imports']),'physical_media_hashes_verified':True,
            'actual_backup_restore_verified':args.native_http,'storyboard_resolutions':len(actual['storyboard_resolutions']),
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
    native=Store(args.data_root/'native');config=Config(data_root=native.root,ffmpeg_bin=args.ffmpeg.parent,runtime_root=args.data_root/'absent-fixture-runtime',
        secret_file=args.data_root/'absent-fixture-secrets/openai.env',assemblyai_secret_file=args.data_root/'absent-fixture-secrets/assemblyai.dpapi')
    project=native.create('EXPLICIT WORKER REHEARSAL','EXPLICIT SYNTHETIC INPUT')
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
    server=None;http_calls=[];operation_logs=[];cookie=None;session=None
    if args.native_http:
        from services.windows_native.server import LocalServer
        from services.windows_native.access import NativeAccess
        from services.windows_native.observability import Observer
        from services.windows_native.tests.test_human_identity import fixture as human_fixture
        from app.human_identity import HumanAuthVerifier,HumanAuthRegistry
        def account(role):
            nonlocal cookie,session
            raw,document=human_fixture(role,workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(document),max_token_ttl_seconds=86400),WORKSPACE)
            access.bind_root(native.root);server.access=access;cookie,session=access.login(raw)
        raw,document=human_fixture('editor',workspace=WORKSPACE);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(document),max_token_ttl_seconds=86400),WORKSPACE)
        class ForbiddenCorePipeline:
            def run(self,*_,**__):raise AssertionError('No core paid provider permitted in generation rehearsal')
        server=LocalServer(0,config,access=access,pipeline=ForbiddenCorePipeline(),start_worker=False,generation_factory=factory,observer=Observer(operation_logs.append))
        queue,worker=server.generation.queue,server.generation;worker.start(server.observer);server_thread=threading.Thread(target=server.serve_forever,daemon=True);server_thread.start();account('editor')
        def send_http(method,path,body=None,status=200):
            connection=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            connection.request(method,path,body=json.dumps(body) if body is not None else None,headers={'Content-Type':'application/json','Cookie':'vf_native_session='+cookie,'X-VF-CSRF':session.csrf})
            response=connection.getresponse();content=response.read();headers=dict(response.getheaders());connection.close()
            value=json.loads(content) if headers.get('Content-Type','').startswith('application/json') else {'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()}
            http_calls.append({'method':method,'path':path,'status':response.status});assert response.status==status,(response.status,value)
            assert headers.get('Cache-Control')=='no-store';return value
        async def http_request(*values,**options):return await asyncio.to_thread(send_http,*values,**options)
        async def wait(identity,expected):
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                value=await http_request('GET',f'/api/projects/{project["id"]}/generation/{identity}')
                if value['status']==expected:return value
                if value['status'] in {'failed','not_configured','cancelled','needs_approval'}:raise AssertionError(value)
                await asyncio.sleep(.08)
            raise AssertionError('Bounded Native generation worker deadline')
        configured=await http_request('GET','/api/generation/providers');assert len(configured['items'])==8 and not configured['ui_enablement_supported']
    ref=lambda asset:{'asset_id':asset['id'],'asset_sha256':asset['sha256']}
    cases=[NativeImageParameters(prompt='EXPLICIT LOST-REPLY IMAGE FIXTURE',aspect_ratio='16:9',seed=51),
        NativeVideoParameters(prompt='EXPLICIT VIDEO WORKER FIXTURE',mode='image_to_video',references=[ref(assets[0])],aspect_ratio='16:9',seed=29,duration_seconds=.6),
        NativeImageParameters(prompt='EXPLICIT INPAINT WORKER FIXTURE',operation='inpaint',references=[ref(assets[0]),ref(assets[0])],mask=ref(assets[1]),aspect_ratio='16:9',seed=52)]
    plan_record=None;resolution=None;resolve_body=None
    if args.studio_plan:
        base=f'/api/projects/{project["id"]}'
        proposal={'narration':'Explicit authored storyboard fixture. No research or script provider is claimed.',
            'visual_brief':[{'scene':1,'visual':'Original technology teaching illustration','on_screen_text':'EXPLICIT RESOLUTION FIXTURE','narration_excerpt':'Explicit authored storyboard fixture. No research or script provider is claimed.'}],
            'facts_needing_source':['Authored fixture only; no provider research']}
        project=await http_request('POST',base+'/draft',{'revision':project['revision'],'proposal':proposal,'scene_media':[]})
        view=await http_request('GET',base+'/shots');project=await http_request('POST',base+'/shots',{'revision':view['revision'],
            'operation':{'type':'update','shot_id':view['shot_timeline']['shots'][0]['shot_id'],'values':{'duration':.6}}})
        view=await http_request('GET',base+'/shots');page=await http_request('POST',base+'/media-plans',{'revision':view['revision'],'expected_timeline_version':view['shot_timeline']['version'],
            'options':{'resolver_priority':['ai_image','user_asset'],'preferred_media_type':'image','aspect_ratio':'16:9'}})
        plan_record=page['items'][-1];project=native.get(project['id']);before=project;item=plan_record['plan']['items'][0]
        assert item['strategy']=='ai_image' and item['status']=='requires_provider' and item['estimated_cost_vnd'] is None
        resolve_body={'revision':project['revision'],'expected_plan_version':plan_record['plan']['version'],'expected_plan_sha256':plan_record['sha256'],
            'shot_id':item['shot_id'],'seed':51,'fixture_acknowledged':True,'request_key':'explicit-storyboard-resolve-key-01'}
        cases[0]=NativeImageParameters(prompt=item['generation_prompt'],aspect_ratio='16:9',seed=51)
        write(args.output_root/'storyboard-media-plan.json',page)
    jobs=[];recoveries=[]
    try:
        for index,value in enumerate(cases):
            original_finish=worker.finish
            if index==2:
                def crash(*_,**__):raise WorkflowError('EXPLICIT_CRASH_AFTER_PERSISTED_MEDIA_STAGE')
                worker.finish=crash
            payload=GenerationCreate(revision=project['revision'],parameters=value,fixture_acknowledged=True,request_key=f'explicit-generation-worker-case-{index}')
            if args.native_http:
                path=f'/api/projects/{project["id"]}/generation';body=payload.model_dump(mode='json')
                if args.studio_plan and index==0:path=f'/api/projects/{project["id"]}/media-plans/{plan_record["plan"]["media_plan_id"]}/resolve/generate';body=resolve_body
                if index==0:
                    account('viewer');await http_request('POST',path,body,status=403);account('editor')
                job=await http_request('POST',path,body)
                if args.studio_plan and index==0:resolution=job;job=job['child']
                await wait(job['generation_id'],'recovery_required' if index in (0,2) else 'succeeded')
            else:
                job,_=queue.create(project['id'],payload,actor='explicit-editor-fixture');await asyncio.to_thread(worker.process)
            jobs.append(job);worker.finish=original_finish
            if index in (0,2):
                interrupted=worker.get(project['id'],job['generation_id']);assert interrupted['status']=='recovery_required'
                if index==0:assert interrupted['provider_job_id'] is None
                write(args.output_root/f'{index}-interrupted-job.json',interrupted)
                recovery=GenerationRecovery(expected_fingerprint=job['request_fingerprint'],acknowledged=True,request_key=f'explicit-worker-read-only-recovery-{index}');before_calls=len(calls)
                if args.native_http:
                    recoveries.append(await http_request('POST',f'/api/projects/{project["id"]}/generation/{job["generation_id"]}/recover',recovery.model_dump(mode='json')))
                    await wait(job['generation_id'],'succeeded')
                else:
                    recoveries.append(queue.recover(project['id'],job['generation_id'],recovery,actor='explicit-editor-fixture'));await asyncio.to_thread(worker.process)
                if index==2:assert len(calls)==before_calls
            result=worker.get(project['id'],job['generation_id']);assert result['status']=='succeeded' and result['result']['asset']['rights_status']=='unknown'
            assert result['result']['mode']==['reconcile','create','local_stage_recovery'][index] and not result['result']['production_eligible']
            write(args.output_root/f'{index}-completed-job.json',result);asset=result['result']['asset']
            if args.studio_plan and index==0:
                path=f'/api/projects/{project["id"]}/media-plans/{plan_record["plan"]["media_plan_id"]}/resolve/generate'
                replay=await http_request('POST',path,resolve_body);assert replay['idempotent_replay'] and replay['binding']==resolution['binding']
                assert replay['child']['result']['asset']['sha256']==asset['sha256'];write(args.output_root/'storyboard-resolution-ready.json',replay)
            for directory,key,label in [('assets','id','normalized'),('originals','original_id','original'),('assets','thumbnail_id','thumbnail')]:
                source=native.root/directory/asset[key];shutil.copyfile(source,args.output_root/f'{index}-{label}{source.suffix}')
        assert native.get(project['id'])==before
        write(args.output_root/'pre-attachment-project.json',before);attachments=[]
        for job in jobs:
            result=worker.get(project['id'],job['generation_id']);current=native.get(project['id']);request=GenerationImport(revision=current['revision'],
                expected_fingerprint=job['request_fingerprint'],expected_asset_sha256=result['result']['asset']['sha256'],acknowledged=True,request_key='explicit-generation-worker-import-'+job['generation_id'])
            if args.native_http:
                path=f'/api/projects/{project["id"]}/generation/{job["generation_id"]}'
                account('viewer');media=await http_request('GET',path+'/file');assert media['sha256']==result['result']['asset']['sha256']
                body=request.model_dump(mode='json');import_path=path+'/import'
                storyboard=args.studio_plan and job['generation_id']==resolution['binding']['child_id']
                if storyboard:import_path=f'/api/projects/{project["id"]}/media-resolutions/{resolution["binding"]["resolution_id"]}/import';body['expected_binding_sha256']=resolution['binding_sha256']
                await http_request('POST',import_path,body,status=403);account('editor')
                receipt=await http_request('POST',import_path,body);replay=await http_request('POST',import_path,body)
                if storyboard:
                    assert receipt['replan_required'] and replay['import_receipt']['idempotent_replay'];write(args.output_root/'storyboard-resolution-imported.json',receipt);receipt=receipt['import_receipt']
                else:assert replay['idempotent_replay']
                assert (await http_request('GET',path))['attachment']==receipt
            else:
                receipt=worker.attach(project['id'],job['generation_id'],request,actor='explicit-editor-fixture');assert worker.attach(project['id'],job['generation_id'],request,actor='explicit-editor-fixture')['idempotent_replay']
            attachments.append(receipt)
        current=native.get(project['id']);assert current['revision']==before['revision']+3 and current['approval'] is None
        prior_timeline=before['document'].get('canonical_timeline');current_timeline=current['document'].get('canonical_timeline')
        assert (current_timeline.get('snapshot'),current_timeline.get('sha256'))==(prior_timeline.get('snapshot'),prior_timeline.get('sha256')) if prior_timeline else current_timeline is None
        assert sum(c['path']=='/v1/jobs' and c['method']=='POST' for c in calls)==3
        assert sum(c['path'].startswith('/v1/jobs/by-client-request/') for c in calls)==1
        assert sum(c['path']=='/v1/references' and c['method']=='POST' for c in calls)==3
        assert sum(c['path']=='/prompt' for c in wire.calls)==3 and sum(c['path']=='/upload/image' for c in wire.calls)==3
        costs=queue.costs.summary(project['id']);assert len(costs['records'])==6 and all(r['actual_cost'] is None and not r['paid'] for r in costs['records'])
        write(args.output_root/'recovery-requests.json',recoveries);write(args.output_root/'attachment-receipts.json',attachments)
        write(args.output_root/'native-service-wires.json',calls);write(args.output_root/'gpu-fixture-wires.json',wire.calls)
        if args.studio_plan:
            base=f'/api/projects/{project["id"]}';page=await http_request('GET',base+'/media-plans');assert not page['items'][0]['input_current']
            view=await http_request('GET',base+'/shots');replan=await http_request('POST',base+'/media-plans',{'revision':view['revision'],'expected_timeline_version':view['shot_timeline']['version'],
                'options':{'resolver_priority':['ai_image','user_asset'],'preferred_media_type':'image','aspect_ratio':'16:9'}})
            imported_ids={receipt['asset_id'] for receipt in attachments};candidates=[candidate for item in replan['items'][-1]['plan']['items'] for candidate in item['candidates'] if candidate['asset_id'] in imported_ids]
            assert candidates and all(not candidate['selectable'] for candidate in candidates)
            assert native.get(project['id'])['document']['canonical_timeline']['snapshot']==before['document']['canonical_timeline']['snapshot'];write(args.output_root/'storyboard-replan-rights-blocked.json',replan)
    finally:
        if server is not None:await asyncio.to_thread(server.shutdown);server.server_close();server_thread.join(timeout=2)
        await bridge.service.close()
    if args.native_http:
        from services.windows_native.backup import create_backup,restore_backup
        assert args.restore_root;fresh(args.restore_root)
        backup=create_backup(config,args.output_root/'native-generation-backup.zip');restore=restore_backup(args.output_root/'native-generation-backup.zip',args.restore_root/'native',expected_sha256=backup['sha256'])
        assert backup['database_status']['workflow.sqlite3']['counts']['native_generation_results']==3
        if args.studio_plan:assert backup['database_status']['workflow.sqlite3']['counts']['native_media_resolutions']==1
        assert snapshot(args.restore_root)==snapshot(args.data_root)
        write(args.output_root/'backup-restore.json',{'backup':backup,'restore':restore,'exact_native_generation_restore':True})
        write(args.output_root/'human-http-wires.json',http_calls);write(args.output_root/'content-free-operations.json',operation_logs)
    write(args.output_root/'offline-snapshot.json',snapshot(args.data_root))
    files=['services/windows_native/generation_worker.py','services/windows_native/generation_queue.py','services/windows_native/generation_media.py',
        'services/windows_native/observability.py','scripts/north_star_native_generation_worker.py']
    if args.native_http:files+=['services/windows_native/generation_routes.py','services/windows_native/generation_registry.py','services/windows_native/server.py','services/windows_native/access.py','services/windows_native/backup.py',
        'apps/studio-web/native-generation.mjs','apps/studio-web/native-source-broll.mjs','apps/studio-web/native.mjs','apps/studio-web/native.html','apps/studio-web/native.css']
    if args.studio_plan:files+=['services/windows_native/studio_media_resolution.py','services/windows_native/studio_media_resolution_routes.py','services/windows_native/studio_media_planner.py','services/windows_native/stock.py',
        'apps/studio-web/native-media-planner.mjs','apps/studio-web/native-media-resolution.mjs']
    write(args.output_root/'evidence.json',{'schema_version':'north-star-native-generation-worker-v1','explicit_fixture':True,'workspace_id':WORKSPACE,
        'project_id':project['id'],'data_root':str(args.data_root),'actual_local_decoded_outputs':3,'native_reference_admissions':3,'native_worker_wired':True,
        'generation_submission_writes':3,'mock_gpu_prompt_writes':3,'mock_gpu_reference_uploads':3,'mock_native_reference_intake_writes':3,'read_only_lookup_count':1,
        'lost_submission_reply_reconciled_without_second_submit':True,'persisted_stage_crash_recovered_without_provider_calls':True,'duplicate_reference_hash_binding_passed':True,
        'generation_results_manually_injected':False,'explicit_attachment_receipts':3,'cost_operations':6,'actual_cost_vnd':None,'paid_operations':0,
        'automatic_attachment':False,'canonical_timeline_auto_edited':False,'rights_independently_verified':False,'rights_status':'unknown','production_eligible':False,
        'native_http_assets_ui_wired':args.native_http,'human_http_requests':len(http_calls),'actual_backup_restore_verified':args.native_http,
        'storyboard_media_resolution_wired':args.studio_plan,'storyboard_resolution_results_manually_injected':False,'storyboard_explicit_import_and_replan_rights_block_verified':args.studio_plan,
        'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{name:sha(ROOT/name) for name in files},'exports':{p.name:{'sha256':sha(p),'bytes':p.stat().st_size} for p in args.output_root.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_GENERATION_WORKER_REAL_BYTES_MOCK_GPU_PASS','outputs':3,'submissions':3,'explicit_imports':3,'real_provider':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True);parser.add_argument('--ffprobe',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    parser.add_argument('--native-http',action='store_true');parser.add_argument('--restore-root',type=Path)
    parser.add_argument('--studio-plan',action='store_true')
    parser.add_argument('--native-site-packages',type=Path);options=parser.parse_args()
    if options.native_site_packages:sys.path.append(str(options.native_site_packages))
    asyncio.run(run(options))
