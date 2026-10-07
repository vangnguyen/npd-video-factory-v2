"""Native source/rights binding to authenticated bridge intake and mock GPU wires.

Real local pixels, image decoding, SQLite journals, bridge FFmpeg decoding and
binary output registration. No Native generation queue/UI, actual AI model,
licensed external media, paid operation, Owner UAT or live provider acceptance.
"""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib,json,os,sqlite3,subprocess,sys,uuid
from dataclasses import asdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'services/comfyui-bridge'),str(ROOT/'apps/api'),str(ROOT/'scripts')]
from north_star_comfyui_http_backend import fixture_manifest,GPUWireFixture,GPU_TOKEN,sha,write,fresh
WORKSPACE='wsp_native_generation_reference_rehearsal'
TOKEN='explicit-native-reference-rehearsal-token-32-characters'


def current(data,ffmpeg,ffprobe):
    from services.windows_native.store import Store
    from services.windows_native.contracts import digest,file_sha
    from services.windows_native.generation_references import NativeGenerationReferences
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
    from npd_comfyui_bridge.binary_artifacts import BinaryArtifactStore,FFmpegMediaValidator
    from npd_comfyui_bridge.reference_store import ReferenceStore
    native=Store(data/'native');service=NativeGenerationReferences(native,workspace_id=WORKSPACE)
    with native.transaction() as con:
        projects=[native.project(row) for row in con.execute('SELECT * FROM projects ORDER BY id')]
        rows=[dict(row) for row in con.execute('SELECT * FROM native_generation_reference_admissions ORDER BY generation_id,asset_id')]
        for row in rows:service.read(row,json.loads(row['snapshot_json']))
        versions=[dict(row) for row in con.execute('SELECT * FROM project_versions ORDER BY project_id,revision')]
    for project in projects:
        for asset in project['document']['assets']:assert file_sha(native.root/'assets'/asset['id'])==asset['sha256']
    validator=FFmpegMediaValidator(ffmpeg=str(ffmpeg),ffprobe=str(ffprobe));bridge=SQLiteBridgeJobStore(data/'bridge/jobs.sqlite3')
    artifacts=BinaryArtifactStore(data/'bridge/artifacts',validator=validator);references=ReferenceStore(data/'bridge/references',validator=validator,enabled=True)
    try:
        jobs=[];outputs=[];inputs=[]
        for job,request in bridge.load():
            assert job.status=='succeeded' and job.project_id==projects[0]['id'] and request.workspace_id==WORKSPACE
            artifact=artifacts.read(workspace_id=WORKSPACE,job_id=job.job_id,artifact_id=job.result['artifact_reference'].removeprefix('vf-artifact://'))
            document,path=artifact.document,artifact.path
            outputs.append({'document':document,'sha256':sha(path),'size_bytes':path.stat().st_size});jobs.append(job.model_dump(mode='json'))
        for row in rows:
            metadata,path=references.read(workspace_id=WORKSPACE,project_id=row['project_id'],source_reference='vf-reference://'+row['reference_id'])
            assert metadata==json.loads(row['metadata_json']) and sha(path)==metadata['admission']['content_sha256']
            inputs.append({'document':metadata,'sha256':sha(path)})
        uploads=[json.loads(raw) for raw, in bridge.connection.execute('SELECT document FROM bridge_reference_uploads ORDER BY identity')]
        return {'projects':projects,'versions':versions,'native_reference_admissions':rows,'bridge_jobs':sorted(jobs,key=lambda r:r['job_id']),
            'decoded_outputs':sorted(outputs,key=lambda r:r['sha256']),'decoded_inputs':inputs,'gpu_reference_uploads':uploads}
    finally:bridge.close()


async def run(args):
    import httpx
    from services.windows_native.store import Store
    from services.windows_native.pipeline import Config
    from services.windows_native.media import ingest_media
    from services.windows_native.generation_models import NativeImageParameters,NativeVideoParameters
    from services.windows_native.generation_registry import GenerationCredential,GenerationFactory
    from services.windows_native.generation_references import NativeGenerationReferences
    from services.windows_native.contracts import WorkflowError
    if args.reopen:
        actual=current(args.data_root,args.ffmpeg,args.ffprobe);expected=json.loads((args.output_root/'offline-snapshot.json').read_bytes());assert actual==expected
        default=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),manifest_path=args.data_root/'explicit-fixture-workflows/manifest.json')
        assert not default.enabled
        write(args.output_root/'new-process-replay.json',{'exact_replay':True,'actual_asset_hashes_verified':True,'default_owner_enabled':False,
            'native_jobs_or_ui_wired':False,'generation_jobs':len(actual['bridge_jobs']),'admissions':len(actual['native_reference_admissions']),
            'real_provider_tested':False,'external_requests':0})
        print(json.dumps({'status':'NATIVE_REFERENCE_NEW_PROCESS_OFFLINE_REPLAY_PASS','outputs':len(actual['bridge_jobs'])}));return
    fresh(args.data_root);fresh(args.output_root);manifest=fixture_manifest(args.data_root,references=True)
    from PIL import Image
    source=args.data_root/'locally-owned-source.png';mask=args.data_root/'locally-owned-mask.png'
    Image.new('RGB',(320,240),(30,85,145)).save(source);Image.new('RGB',(320,240),(255,255,255)).save(mask)
    native=Store(args.data_root/'native');config=Config(data_root=native.root);references=NativeGenerationReferences(native,workspace_id=WORKSPACE)
    project=native.create('EXPLICIT NATIVE REFERENCE REHEARSAL','EXPLICIT SYNTHETIC INPUT, NOT A REAL PROVIDER')
    assets=[]
    for path in [source,mask]:
        asset=ingest_media(config,path,'image/png',path.name,rights_confirmed=True,illustration=False)
        asset.update(source_type='synthetic_fixture',rights_status='owned',license='locally_generated_synthetic_fixture',provider='local-pillow-fixture',
            generation_provenance={'fixture':True,'creator':'local-synthetic-rehearsal'},explicit_fixture=True,production_eligible=False)
        project=native.append_media(project['id'],project['revision'],asset);assets.append(asset)
    before=native.get(project['id']);binaries={}
    for suffix in ['png','mp4']:
        path=args.data_root/('synthetic-output.'+suffix)
        command=[str(args.ffmpeg),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=128x72:rate=10:duration=0.6']
        command+=['-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart'] if suffix=='mp4' else ['-frames:v','1']
        subprocess.run([*command,str(path)],check=True,timeout=20,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE);binaries[suffix]=path.read_bytes()
    os.environ.update({'COMFYUI_BACKEND':'disabled','COMFYUI_EXECUTION_ENABLED':'false','APP_ENV':'development','COMFYUI_BRIDGE_TOKEN':TOKEN,
        'COMFYUI_WORKFLOW_MANIFEST':str(manifest),'COMFYUI_JOB_STORE_PATH':str(args.data_root/'bridge/jobs.sqlite3'),
        'COMFYUI_ARTIFACT_ROOT':str(args.data_root/'bridge/artifacts'),'COMFYUI_REFERENCE_ROOT':str(args.data_root/'bridge/references'),
        'COMFYUI_REFERENCE_INTAKE_ENABLED':'true','COMFYUI_FFMPEG_PATH':str(args.ffmpeg),'COMFYUI_FFPROBE_PATH':str(args.ffprobe)})
    from npd_comfyui_bridge.http_backend import ReviewedHTTPComfyUIBackend
    from npd_comfyui_bridge.http_transport import ComfyHTTPTransport
    from npd_comfyui_bridge.reference_stager import ScopedReferenceStager
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    from app.media_generation_scope import media_generation_scope
    bridge=importlib.import_module('npd_comfyui_bridge.main');await bridge.service.close();wire=GPUWireFixture(binaries)
    store=SQLiteBridgeJobStore(args.data_root/'bridge/jobs.sqlite3')
    gpu=ComfyHTTPTransport(origin='http://127.0.0.1:8188',server_source_sha256='0'*64,enabled=True,bearer_token=GPU_TOKEN,transport=httpx.MockTransport(wire.handle))
    backend=ReviewedHTTPComfyUIBackend(registry=bridge.registry,transport=gpu,job_store=store,artifacts=bridge.app.state.binary_artifact_store,poll_seconds=.01,
        reference_resolver=ScopedReferenceStager(references=bridge.app.state.reference_store,transport=gpu,job_store=store))
    bridge.backend=backend;bridge.service=ComfyUIBridgeService(bridge.registry,backend,job_store=store);bridge.app.state.bridge_service=bridge.service
    calls=[];lost=[True];observations=[]
    async def observe(value):observations.append(value)
    async def native_wire(request):
        assert request.headers['Authorization']=='Bearer '+TOKEN and request.headers['X-VF-Workspace-Id']==WORKSPACE
        calls.append({'method':request.method,'path':request.url.path})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=bridge.app),base_url='http://fixture') as client:
            response=await client.request(request.method,request.url.path,content=request.content,headers=dict(request.headers))
        if request.method=='POST' and request.url.path=='/v1/references' and lost[0]:
            lost[0]=False;raise httpx.ReadError('EXPLICIT LOST NATIVE INTAKE REPLY')
        return response
    factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,
        transport=httpx.MockTransport(native_wire),manifest_path=manifest)
    ref=lambda a:{'asset_id':a['id'],'asset_sha256':a['sha256']}
    cases=[NativeImageParameters(prompt='EXPLICIT INPAINT PIXEL FIXTURE, NOT AI',operation='inpaint',references=[ref(assets[0])],mask=ref(assets[1]),aspect_ratio='16:9',seed=51),
        NativeVideoParameters(prompt='EXPLICIT IMAGE TO VIDEO FIXTURE, NOT AI',mode='image_to_video',references=[ref(assets[0])],aspect_ratio='16:9',seed=29,duration_seconds=.6)]
    try:
        for index,value in enumerate(cases):
            identity=uuid.uuid4().hex;snapshot=references.freeze(project['id'],project['revision'],value,factory,fixture_acknowledged=True)
            payload=await references.stage(identity,snapshot,factory);write(args.output_root/f'{index}-native-reference-snapshot.json',snapshot)
            write(args.output_root/f'{index}-scoped-provider-input.json',payload.model_dump(mode='json'))
            with media_generation_scope(workspace_id=WORKSPACE,project_id=project['id'],job_id=identity):result=await factory.create(value.modality,payload,on_job=observe).generate(payload)
            assert result.rights_status=='unknown' and not result.production_eligible and result.actual_cost_vnd is None and not result.real_provider_tested
            recorded=asdict(result);recorded.pop('payload');recorded['payload_sha256']=hashlib.sha256(result.payload).hexdigest()
            write(args.output_root/f'{index}-generation-result.json',recorded)
            artifact=bridge.app.state.binary_artifact_store.read(workspace_id=WORKSPACE,job_id=result.provider_job_id,artifact_id=result.source_reference.removeprefix('vf-artifact://'))
            document,path=artifact.document,artifact.path
            write(args.output_root/f'{index}-artifact-metadata.json',document);write(args.output_root/(f'{index}-output'+path.suffix),path.read_bytes())
        assert native.get(project['id'])==before and sum(c['path']=='/v1/references' and c['method']=='POST' for c in calls)==3
        assert sum(c['path']=='/prompt' for c in wire.calls)==2 and sum(c['path']=='/upload/image' for c in wire.calls)==3
        # A second generation job has a separately timed source receipt; its
        # bytes remain immutable, independently scope-bound and hash checked.
        write(args.output_root/'native-service-wires.json',calls);write(args.output_root/'gpu-fixture-wires.json',wire.calls)
        write(args.output_root/'lifecycle.json',observations)
    finally:await bridge.service.close()
    snapshot=current(args.data_root,args.ffmpeg,args.ffprobe);write(args.output_root/'offline-snapshot.json',snapshot)
    files=['services/windows_native/generation_references.py','services/windows_native/generation_registry.py','services/windows_native/generation_models.py',
        'services/comfyui-bridge/npd_comfyui_bridge/reference_models.py','scripts/north_star_native_generation_references.py']
    write(args.output_root/'evidence.json',{'schema_version':'north-star-native-generation-reference-evidence-v1','explicit_fixture':True,'workspace_id':WORKSPACE,
        'project_id':project['id'],'data_root':str(args.data_root),'actual_local_decoded_outputs':2,'native_reference_admissions':3,
        'mock_gpu_prompt_writes':2,'mock_gpu_reference_upload_writes':3,'mock_native_intake_writes':3,'lost_native_intake_reply_reconciled':True,
        'canonical_timeline_mutated':False,'native_generation_queue_or_ui_wired':False,'real_provider_tested':False,'paid_operations':0,
        'rights_independently_verified':False,'owner_uat_accepted':False,'production_deployed':False,
        'source_sha256':{file:sha(ROOT/file) for file in files},'exports':{p.name:{'sha256':sha(p),'size_bytes':p.stat().st_size} for p in args.output_root.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_REFERENCE_REAL_BYTES_MOCK_GPU_PASS','outputs':2,'intake_writes':3,'owner_uat':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--ffmpeg',type=Path,required=True);parser.add_argument('--ffprobe',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    # The bridge test runtime owns FastAPI/jsonschema. Only missing modules are
    # resolved from the separate installed Native runtime; no runtime is edited.
    parser.add_argument('--native-site-packages',type=Path)
    options=parser.parse_args()
    if options.native_site_packages:sys.path.append(str(options.native_site_packages))
    asyncio.run(run(options))
