"""Real local image/video decode; registered bridge metadata is an explicit mock."""
from copy import deepcopy
from dataclasses import replace
import hashlib,io,json,subprocess,unittest
from pathlib import Path
from PIL import Image
from services.windows_native.tests import test_generation_queue as helpers
from services.windows_native.generation_media import NativeGenerationMedia
from services.windows_native.pipeline import Config
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.generation_models import GenerationCreate,NativeVideoParameters
from services.windows_native.generation_references import api_parameters
from app.media_intelligence_providers import ProviderMaterializedMedia
from app.media_generation_routes import generation_envelope,workflow_routes


class NativeGenerationMediaTests(unittest.TestCase):
    # Reuse only isolated setup helpers; never rerun the queue tests by inheritance.
    setUp=helpers.NativeGenerationQueueTests.setUp
    tearDown=helpers.NativeGenerationQueueTests.tearDown
    create=helpers.NativeGenerationQueueTests.create
    cost=helpers.NativeGenerationQueueTests.cost
    prepared=helpers.NativeGenerationQueueTests.prepared
    observation=helpers.NativeGenerationQueueTests.observation

    def pixels(self,size=(640,360)):
        buffer=io.BytesIO();Image.new('RGB',size,(40,90,140)).save(buffer,format='PNG');return buffer.getvalue()

    def output(self,job,content=None,*,mime='image/png',width=640,height=360,duration=None):
        content=content or self.pixels();selected=job['snapshot']['selection'];modality=job['snapshot']['request']['parameters']['modality']
        from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
        typed=(ImageGenerationInput if modality=='image' else VideoGenerationInput).model_validate(api_parameters(self.payload.parameters,{}).model_dump(mode='json'))
        workflow,operation,inputs=generation_envelope(modality,typed,workflow_routes(modality,'npd-text-to-image-v1' if modality=='image' else 'npd-video-generation-v1'))
        binary=hashlib.sha256(content).hexdigest();provider_job='cui_explicit_queue_fixture';identity=digest([self.service.workspace,provider_job,binary])
        proof={'artifact_id':identity,'workspace_id':self.service.workspace,'job_id':provider_job,'size_bytes':len(content),'mime_type':mime,
            'checksum_sha256':binary,'fixture':True,'rights_status':'unknown','production_eligible':False,
            'media':{'width':width,'height':height,'duration_seconds':duration,'fps':10 if duration else None,'decoded_video_frames':6 if duration else 1,
                'audio_streams':0,'video_codec':'h264' if duration else 'png','full_decode_passed':True,'qc_passed':False},
            'provenance':{'workflow_id':workflow,'workflow_version':selected['workflow_version'],'inputs_sha256':digest(inputs),
                'prompt_sha256':hashlib.sha256(typed.prompt.encode()).hexdigest(),'seed':typed.seed,'estimated_cost_vnd':None,'actual_cost_vnd':None,
                'provider':'comfyui','model':', '.join(self.factory.catalog['definitions'][workflow].required_model_identifiers)[:200] or 'unspecified-reviewed-model',
                'graph_sha256':file_sha(self.factory.manifest_path.parent/self.factory.catalog['definitions'][workflow].graph_file),
                'server_source_sha256':'1'*64,'remote_prompt_id':'11111111-1111-4111-8111-111111111111','adapter_elapsed_seconds':.1,'source_reference_sha256':[]}}
        return ProviderMaterializedMedia(filename='EXPLICIT MOCK REGISTERED MEDIA.png' if mime.startswith('image/') else 'EXPLICIT MOCK REGISTERED VIDEO.mp4',
            content_type=mime,payload=content,provider_job_id=provider_job,source_type='ai_generated',rights_status='unknown',license='provider-terms-review-required',
            license_url=None,provider_asset_id=provider_job,creator='EXPLICIT METADATA FIXTURE, NOT A REAL PROVIDER',source_reference='vf-artifact://'+identity,
            attribution_requirement=None,width=width,height=height,duration_seconds=duration,orientation='landscape',production_eligible=False,
            estimated_cost_vnd=None,actual_cost_vnd=None,external_call=True,paid=False,real_provider_tested=False,generation_provenance={
                'provider':selected['provider'],'model':'workflow:'+workflow,'workflow':workflow,'workflow_version':selected['workflow_version'],'operation':operation,'seed':typed.seed,
                'bridge_job_id':provider_job,'fixture':True,'binary_artifact_registered':True,'registered_artifact':proof})

    def ready(self):
        job,claim=self.prepared();self.service.observe(claim,self.observation(job,status='succeeded',progress=100));media=NativeGenerationMedia(self.service,Config(data_root=self.root));return job,claim,media

    def test_actual_png_normalization_and_original_thumbnail_receipt_preserve_project_rights_and_unknown_cost(self):
        job,claim,media=self.ready();before=self.store.get(self.project['id']);output=self.output(job);receipt=media.register(claim,output)
        asset=receipt['asset'];self.assertTrue(receipt['full_native_media_validation_passed']);self.assertEqual(asset['rights_status'],'unknown')
        self.assertFalse(asset['production_eligible']);self.assertTrue(asset['needs_attention']);self.assertTrue(asset['explicit_fixture'])
        self.assertNotEqual(asset['sha256'],asset['source_sha256']);self.assertEqual(file_sha(self.root/'originals'/asset['original_id']),hashlib.sha256(output.payload).hexdigest())
        self.assertEqual(file_sha(self.root/'assets'/asset['thumbnail_id']),receipt['thumbnail_sha256']);self.assertEqual(media.get(job['project_id'],job['generation_id']),receipt)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertIsNone(receipt['actual_cost_vnd']);self.assertFalse(receipt['automatic_attachment'])
        self.assertEqual(self.service.get(job['project_id'],job['generation_id'])['status'],'running')

    def test_exact_repeat_does_not_materialize_another_asset_and_changed_payload_conflicts(self):
        job,claim,media=self.ready();output=self.output(job);first=media.register(claim,output);files=sorted(p.name for p in (self.root/'assets').iterdir())
        self.assertEqual(media.register(claim,output),first);self.assertEqual(sorted(p.name for p in (self.root/'assets').iterdir()),files)
        with self.assertRaises(WorkflowError):media.register(claim,self.output(job,self.pixels((640,400)),height=400))

    def test_missing_binary_foreign_job_workspace_input_fixture_or_rights_promotion_rejects_before_files(self):
        job,claim,media=self.ready();original=self.output(job)
        changes=[replace(original,content_type='application/vnd.npd.comfyui-result+json'),replace(original,provider_job_id='cui_other'),replace(original,rights_status='owned'),
            replace(original,real_provider_tested=True),replace(original,width=640.0)]
        for location,key,value in [('root','workspace_id','foreign'),('provenance','inputs_sha256','0'*64),('root','fixture',False),('media','full_decode_passed',False)]:
            prov=deepcopy(original.generation_provenance);proof=prov['registered_artifact'];(proof if location=='root' else proof[location])[key]=value
            changes.append(replace(original,generation_provenance=prov))
        for output in changes:
            with self.assertRaises(WorkflowError):media.register(claim,output)
        self.assertFalse((self.root/'assets').exists())

    def test_claim_fencing_malformed_bytes_and_small_images_do_not_register_or_leave_materialized_assets(self):
        job,claim,media=self.ready();self.clock[0]+=901
        with self.assertRaises(WorkflowError):media.register(claim,self.output(job))
        self.clock[0]-=901
        for output in [self.output(job,b'not-an-image'),self.output(job,self.pixels((128,72)),width=128,height=72)]:
            with self.assertRaises(WorkflowError):media.register(claim,output)
        with self.assertRaises(WorkflowError):media.get(job['project_id'],job['generation_id'])
        self.assertFalse(list((self.root/'assets').glob('*')))

    def test_actual_native_mp4_full_decode_preserves_registered_video_original(self):
        self.payload=GenerationCreate(revision=1,parameters=NativeVideoParameters(prompt='EXPLICIT VIDEO INTAKE FIXTURE',duration_seconds=.6),fixture_acknowledged=True,request_key='explicit-native-video-intake-fixture-key')
        job,claim,media=self.ready();config=Config(data_root=self.root);path=Path(self.temp.name)/'locally-produced.mp4'
        subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=640x360:rate=10:duration=0.6',
            '-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',str(path)],check=True,timeout=20,capture_output=True)
        output=self.output(job,path.read_bytes(),mime='video/mp4',duration=.6);receipt=media.register(claim,output)
        self.assertEqual(receipt['asset']['kind'],'video');self.assertAlmostEqual(receipt['asset']['duration_seconds'],.6)
        self.assertEqual(receipt['asset']['sha256'],receipt['provider_payload_sha256']);self.assertEqual(receipt['asset']['source_mime'],'video/mp4')

    def test_physical_original_normalized_or_thumbnail_corruption_fails_and_foreign_project_cannot_read(self):
        job,claim,media=self.ready();receipt=media.register(claim,self.output(job));asset=receipt['asset'];thumbnail=self.root/'assets'/asset['thumbnail_id'];thumbnail.write_bytes(b'changed')
        with self.assertRaises(WorkflowError):media.get(job['project_id'],job['generation_id'])
        with self.assertRaises(WorkflowError):media.get(self.store.create('foreign','private')['id'],job['generation_id'])

    def test_rehashed_receipt_cannot_promote_generated_rights_or_rebind_scope(self):
        job,claim,media=self.ready();receipt=media.register(claim,self.output(job))
        for location,key,value in [('asset','rights_status','owned'),('asset','kind','video'),('asset','source_bytes',1),('asset','provider_asset_id','cui_foreign'),
            ('provenance','native_project_id','0'*32),('bridge_provenance','inputs_sha256','0'*64),('bridge_provenance','graph_sha256','0'*64),('workflow','graph_sha256','0'*64)]:
            changed=deepcopy(receipt)
            target=changed['asset'] if location=='asset' else changed['asset']['generation_provenance'] if location=='provenance' else changed['workflow_evidence'] if location=='workflow' else changed['registered_bridge_artifact']['provenance']
            target[key]=value;changed['asset_record_sha256']=digest(changed['asset'])
            with self.store.transaction() as con:con.execute('UPDATE native_generation_media SET receipt_json=?,receipt_sha256=?',(json.dumps(changed),digest(changed)))
            with self.assertRaises(WorkflowError):media.get(job['project_id'],job['generation_id'])
