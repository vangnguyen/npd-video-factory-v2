"""Actual local Native PNG/MP4 intake; provider metadata and observations mocked.

No network, GPU, paid generation, success transition or attachment is claimed.
Separate-process reopen uses no configured generation factory.
"""
import argparse,hashlib,io,json,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PIL import Image
import httpx
from services.windows_native.backup import guard
from services.windows_native.contracts import file_sha,digest
from services.windows_native.store import Store
from services.windows_native.pipeline import Config
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_media import NativeGenerationMedia
from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
from services.windows_native.generation_models import GenerationCreate,NativeImageParameters,NativeVideoParameters
from services.windows_native.generation_references import api_parameters
from app.media_intelligence_providers import ProviderMaterializedMedia
from app.media_generation_routes import generation_envelope,workflow_routes
WORKSPACE='wsp_native_generation_media_fixture'


def write(path,value):
    with path.open('x',encoding='utf-8') as file:json.dump(value,file,ensure_ascii=False,indent=2,allow_nan=False);file.write('\n')


def snapshot(root):
    store=Store(root);queue=NativeGenerationQueue(store,workspace_id=WORKSPACE);media=NativeGenerationMedia(queue,Config(data_root=root))
    with store.transaction() as con:
        projects=[store.project(r) for r in con.execute('SELECT * FROM projects ORDER BY id')]
        ids=[(r['project_id'],r['generation_id']) for r in con.execute('SELECT * FROM native_generation_media ORDER BY generation_id')]
        events=[dict(r) for r in con.execute('SELECT * FROM native_generation_events ORDER BY sequence')]
        versions=[dict(r) for r in con.execute('SELECT * FROM project_versions ORDER BY project_id,revision')]
    return {'projects':projects,'pages':[queue.page(p['id'],limit=200) for p in projects],
        'staged_media':[media.get(project,identity) for project,identity in ids],'events':events,'versions':versions,
        'costs':[queue.costs.summary(p['id']) for p in projects],'factory_configured':queue.factory is not None}


def fixture_output(queue,job,payload,content,mime,width,height,duration):
    selected=job['snapshot']['selection'];modality=job['snapshot']['request']['parameters']['modality'];ticket=job['provider_job_id']
    workflow,operation,inputs=generation_envelope(modality,payload,workflow_routes(modality,'npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1'))
    definition=queue.factory.catalog['definitions'][workflow];sha=hashlib.sha256(content).hexdigest();identity=digest([WORKSPACE,ticket,sha])
    proof={'artifact_id':identity,'workspace_id':WORKSPACE,'job_id':ticket,'size_bytes':len(content),'mime_type':mime,'checksum_sha256':sha,
        'fixture':True,'rights_status':'unknown','production_eligible':False,'media':{'width':width,'height':height,'duration_seconds':duration,
            'fps':10 if duration else None,'decoded_video_frames':6 if duration else 1,'audio_streams':0,'video_codec':'h264' if duration else 'png',
            'full_decode_passed':True,'qc_passed':False},'provenance':{'provider':'comfyui','model':', '.join(definition.required_model_identifiers)[:200] or 'unspecified-reviewed-model',
            'workflow_id':workflow,'workflow_version':selected['workflow_version'],'graph_sha256':file_sha(queue.factory.manifest_path.parent/definition.graph_file),
            'server_source_sha256':'1'*64,'remote_prompt_id':'11111111-1111-4111-8111-111111111111','adapter_elapsed_seconds':.1,'source_reference_sha256':[],
            'inputs_sha256':digest(inputs),'prompt_sha256':hashlib.sha256(payload.prompt.encode()).hexdigest(),'seed':payload.seed,'estimated_cost_vnd':None,'actual_cost_vnd':None}}
    return ProviderMaterializedMedia(filename='EXPLICIT LOCAL MEDIA FIXTURE',content_type=mime,payload=content,provider_job_id=ticket,
        source_type='ai_generated',rights_status='unknown',license='provider-terms-review-required',license_url=None,provider_asset_id=ticket,
        creator='EXPLICIT MOCK METADATA, NOT REAL GPU',source_reference='vf-artifact://'+identity,attribution_requirement=None,width=width,height=height,
        duration_seconds=duration,orientation='landscape',production_eligible=False,estimated_cost_vnd=None,actual_cost_vnd=None,external_call=True,
        paid=False,real_provider_tested=False,generation_provenance={'provider':selected['provider'],'model':'workflow:'+workflow,'workflow':workflow,
            'workflow_version':selected['workflow_version'],'operation':operation,'seed':payload.seed,'bridge_job_id':ticket,'fixture':True,
            'binary_artifact_registered':True,'registered_artifact':proof})


def main(args):
    if args.reopen:
        actual=snapshot(args.data_root);assert actual==json.loads((args.output_root/'offline-snapshot.json').read_bytes())
        write(args.output_root/'new-process-replay.json',{'exact_replay':True,'default_factory_configured':False,'external_requests':0,
            'staged_assets':len(actual['staged_media']),'project_revision':actual['projects'][0]['revision'],'rights_status':'unknown','mock_provider_metadata':True,
            'native_worker_success_attachment_http_ui_wired':False,'real_provider_tested':False})
        print(json.dumps({'status':'NATIVE_GENERATION_MEDIA_NEW_PROCESS_PASS','assets':2,'external_requests':0}));return
    for path in [args.data_root,args.output_root]:
        if not path.is_absolute() or path.exists():raise ValueError('FRESH_ABSOLUTE_ROOT_REQUIRED')
        guard(path);path.mkdir(parents=True,exist_ok=False)
    store=Store(args.data_root);project=store.create('EXPLICIT LOCAL GENERATION MEDIA INTAKE','PRIVATE SYNTHETIC INPUT');before=store.get(project['id'])
    calls=[]
    def forbidden(request):calls.append(request.method);raise AssertionError('No network permitted')
    factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-media-intake-fixture-token-32',enabled=True),
        owner_enabled=True,transport=httpx.MockTransport(forbidden))
    queue=NativeGenerationQueue(store,workspace_id=WORKSPACE,factory=factory);config=Config(data_root=args.data_root);media=NativeGenerationMedia(queue,config)
    image=io.BytesIO();Image.new('RGB',(640,360),(30,80,140)).save(image,format='PNG');video=args.output_root/'local-source-video.mp4'
    subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=10:duration=0.6',
        '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True,capture_output=True,timeout=20)
    for index,(params,content,mime,duration) in enumerate([(NativeImageParameters(prompt='EXPLICIT MOCK IMAGE INTAKE'),image.getvalue(),'image/png',None),
        (NativeVideoParameters(prompt='EXPLICIT MOCK VIDEO INTAKE',duration_seconds=.6),video.read_bytes(),'video/mp4',.6)]):
        job,_=queue.create(project['id'],GenerationCreate(revision=1,parameters=params,fixture_acknowledged=True,request_key=f'explicit-native-media-intake-{index}'),actor='explicit-editor-fixture')
        claim=queue.claim();payload=api_parameters(params,{});queue.bind_input(claim,payload)
        cost=queue.costs.begin(project_id=project['id'],provider=job['snapshot']['selection']['provider'],model='workflow:'+job['snapshot']['selection']['workflow_id'],
            operation='generation.'+job['generation_id']+'.submit',request_sha256=job['request_fingerprint'],estimated_cost=None,external_call=True,paid=False)
        queue.mark_dispatch(claim,cost);queue.observe(claim,{'schema_version':'comfyui-generation-observation-v1','phase':'polled','provider_job_id':f'cui_explicit_media_{index}',
            'workspace_id':WORKSPACE,'workflow_id':job['snapshot']['selection']['workflow_id'],'workflow_version':job['snapshot']['selection']['workflow_version'],'status':'succeeded','progress':100})
        output=fixture_output(queue,queue.get(project['id'],job['generation_id']),payload,content,mime,640,360,duration)
        receipt=media.register(claim,output);assert media.register(claim,output)==receipt
        asset=receipt['asset'];write(args.output_root/f'{params.modality}-receipt.json',receipt)
        for directory,key,label in [('assets','id','normalized'),('assets','thumbnail_id','thumbnail'),('originals','original_id','original')]:
            source=args.data_root/directory/asset[key];shutil.copyfile(source,args.output_root/f'{params.modality}-{label}{source.suffix}')
        # A separate worker will later own terminal state. End this prerequisite
        # claim honestly; the stage receipt remains immutable/recoverable.
        queue.fail(claim,'EXPLICIT_MEDIA_STAGE_REHEARSAL_NO_EXECUTING_WORKER')
    assert not calls and store.get(project['id'])==before
    write(args.output_root/'offline-snapshot.json',snapshot(args.data_root))
    sources=['services/windows_native/generation_media.py','scripts/north_star_native_generation_media.py']
    write(args.output_root/'evidence.json',{'schema_version':'north-star-native-generation-media-v1','workspace_id':WORKSPACE,'project_id':project['id'],
        'data_root':str(args.data_root),'actual_native_image_decode':True,'actual_native_ffprobe_full_video_decode':True,'actual_assets':2,
        'mock_provider_metadata_and_observations':True,'registered_bridge_service_called':False,'generation_posts':0,'external_requests':0,'paid_operations':0,'actual_cost_vnd':None,
        'rights_status':'unknown','production_eligible':False,'project_approval_timeline_mutated':False,'native_worker_success_attachment_http_ui_wired':False,
        'real_provider_tested':False,'owner_uat_accepted':False,'production_deployed':False,'source_sha256':{name:file_sha(ROOT/name) for name in sources},
        'exports':{p.name:{'sha256':file_sha(p),'bytes':p.stat().st_size} for p in args.output_root.iterdir() if p.is_file()}})
    print(json.dumps({'status':'NATIVE_GENERATION_MEDIA_INTAKE_PASS','assets':2,'external_requests':0,'project_mutated':False}))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--data-root',type=Path,required=True);parser.add_argument('--output-root',type=Path,required=True);parser.add_argument('--reopen',action='store_true')
    main(parser.parse_args())
