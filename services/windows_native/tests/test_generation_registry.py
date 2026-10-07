"""Typed Native generation admission/factory fixtures; no GPU or live key file."""
import asyncio,hashlib,json,tempfile,unittest
from pathlib import Path
import httpx
from pydantic import ValidationError
from services.windows_native.generation_models import GenerationCreate,NativeImageParameters,NativeVideoParameters
from services.windows_native.generation_registry import GenerationCredential,GenerationFactory,load,MANIFEST
from services.windows_native.contracts import WorkflowError
from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
from app.media_intelligence_providers import MediaProviderNotConfigured
from app.media_generation_scope import media_generation_scope

TOKEN='explicit-native-generation-fixture-service-token-32'
REF={'asset_id':'a'*32+'.jpg','asset_sha256':'b'*64}


class NativeGenerationRegistryTests(unittest.TestCase):
    def test_strict_request_discriminator_reference_mask_mode_and_no_client_graph_uri_or_result(self):
        base={'revision':1,'parameters':{'modality':'image','prompt':'EXPLICIT NATIVE REQUEST FIXTURE'},'request_key':'native-generation-fixture-request-key'}
        self.assertEqual(GenerationCreate.model_validate(base).parameters.modality,'image')
        for change in [{'graph':{}},{'bridge_url':'http://client.test'},{'rights_status':'owned'},{'provider_result':{}},{'external_acknowledged':1}]:
            with self.assertRaises(ValidationError):GenerationCreate.model_validate({**base,**change})
        for change in [{'seed':True},{'references':['https://client.test/private.png']},{'references':[{'asset_id':'../secret','asset_sha256':'b'*64}]},
            {'operation':'inpaint'},{'mask':REF},{'operation':'upscale','references':[REF],'upscale_factor':3},{'modality':'video','mode':'image_to_video'}]:
            with self.assertRaises(ValidationError):GenerationCreate.model_validate({**base,'parameters':{**base['parameters'],**change}})

    def test_nine_typed_modes_match_existing_allowlisted_routes_and_placeholder_graphs_stay_officially_unconfigured(self):
        credential=GenerationCredential(bridge_url='http://127.0.0.1:8011',service_token=TOKEN,enabled=True)
        factory=GenerationFactory(credential,owner_enabled=True)
        cases=[('image',{'operation':'generate'},'npd-text-to-image-v1'),('image',{'operation':'generate','reference_images':['asset://fixture']},'npd-image-to-image-v1'),
            ('image',{'operation':'image_to_image','reference_images':['asset://fixture']},'npd-image-to-image-v1'),
            ('image',{'operation':'variation','reference_images':['asset://fixture']},'npd-image-to-image-v1'),
            ('image',{'operation':'inpaint','reference_images':['asset://fixture'],'mask_reference':'asset://mask'},'npd-inpaint-v1'),
            ('image',{'operation':'upscale','reference_images':['asset://fixture']},'npd-upscale-v1'),
            ('video',{'mode':'text_to_video'},'npd-video-generation-v1'),('video',{'mode':'image_to_video','reference_images':['asset://fixture']},'npd-image-to-video-v1'),
            ('video',{'mode':'reference_assisted','reference_images':['asset://fixture']},'npd-image-to-video-v1')]
        for modality,options,key in cases:
            payload=(ImageGenerationInput if modality=='image' else VideoGenerationInput)(prompt='EXPLICIT ROUTE FIXTURE',**options)
            selected=factory.selection(modality,payload);self.assertEqual(selected['workflow_id'],key);self.assertEqual(selected['status'],'NOT_CONFIGURED')
            self.assertFalse(selected['executable_workflow_reviewed']);self.assertFalse(factory.create(modality,payload).configured)
        self.assertNotIn(TOKEN,factory.sha256);self.assertNotIn(TOKEN,repr(credential))

    def test_typed_native_reference_dependent_modes_require_owned_ids_and_hashes(self):
        for operation in ['image_to_image','variation','inpaint','upscale']:
            options={'operation':operation,'references':[REF],**({'mask':REF} if operation=='inpaint' else {})}
            value=NativeImageParameters(prompt='EXPLICIT REFERENCE FIXTURE',**options);self.assertEqual(value.references[0].asset_sha256,REF['asset_sha256'])
        self.assertEqual(NativeImageParameters(prompt='upscale fixture',operation='upscale',references=[REF]).upscale_factor,2)
        with self.assertRaises(ValidationError):NativeImageParameters(prompt='upscale fixture',operation='upscale',references=[REF],upscale_factor=2.0)
        for mode in ['image_to_video','reference_assisted']:self.assertEqual(NativeVideoParameters(prompt='video fixture',mode=mode,references=[REF]).mode,mode)
        for duration in [True,0,31,float('nan')]:
            with self.assertRaises(ValidationError):NativeVideoParameters(prompt='video fixture',duration_seconds=duration)

    def test_registry_read_is_disabled_without_owner_flag_and_never_enables_placeholder_graphs(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);root=base/'state';root.mkdir();path=base/'explicit-fixture-registry.json'
            raw={'version':1,'native_workspace_id':'workspace-fixture','comfyui':{'bridge_url':'http://comfyui-bridge:8011','service_token':TOKEN,'enabled':True}}
            path.write_text(json.dumps(raw));factory=load(path,root,'workspace-fixture');self.assertFalse(factory.enabled)
            enabled=load(path,root,'workspace-fixture',owner_enabled=True);self.assertTrue(enabled.enabled)
            self.assertEqual(enabled.selection('image',ImageGenerationInput(prompt='fixture'))['status'],'NOT_CONFIGURED')
            with self.assertRaises(WorkflowError):load(path,root,'foreign-workspace')
            inside=root/'registry.json';inside.write_text(json.dumps(raw))
            with self.assertRaises(WorkflowError):load(inside,root,'workspace-fixture')
            for value in ['{"version":1,"version":1}',json.dumps({**raw,'version':True}),json.dumps({**raw,'graphs':{}})]:
                path.write_text(value)
                with self.assertRaises(WorkflowError) as error:load(path,root,'workspace-fixture')
                self.assertNotIn(TOKEN,str(error.exception))

    def test_bridge_origin_cannot_retarget_secret_to_arbitrary_server_or_client_url(self):
        for endpoint in ['https://attacker.test:8011','file:///secret','http://127.0.0.1','http://u:p@localhost:8011',
            'http://localhost:8011/path','http://localhost:8011/?token=secret','http://localhost:8011/#fragment']:
            with self.assertRaises(ValidationError):GenerationCredential(bridge_url=endpoint,service_token=TOKEN)
        for endpoint in ['http://127.0.0.1:8011','http://[::1]:8011','http://localhost:8011','http://comfyui-bridge:8011']:
            self.assertEqual(GenerationCredential(bridge_url=endpoint,service_token=TOKEN).bridge_url,endpoint)

    def test_duplicate_manifest_and_changed_review_graph_cannot_become_configured(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory);raw=json.loads(MANIFEST.read_bytes());row=raw['workflows'][0]
            # Test-only reviewed metadata intentionally mismatches actual graph.
            row['execution']={'graph_sha256':'0'*64,'approval_reference':'EXPLICIT OWNER GRAPH FIXTURE','approval_kind':'owner_approved',
                'allowed_node_classes':['FixtureNode'],'bindings':[{'parameter':'prompt','node_id':'1','input_name':'text'}],'output_nodes':['1']}
            for item in raw['workflows']:(base/item['graph_file']).write_bytes((MANIFEST.parent/item['graph_file']).read_bytes())
            path=base/'manifest.json';path.write_text(json.dumps(raw));credential=GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True)
            factory=GenerationFactory(credential,owner_enabled=True,manifest_path=path)
            self.assertEqual(factory.selection('image',ImageGenerationInput(prompt='fixture'))['status'],'NOT_CONFIGURED')
            row['execution']['graph_sha256']=hashlib.sha256((base/row['graph_file']).read_bytes()).hexdigest();path.write_text(json.dumps(raw))
            # A matching digest for an empty placeholder is still not executable.
            factory=GenerationFactory(credential,owner_enabled=True,manifest_path=path)
            self.assertEqual(factory.selection('image',ImageGenerationInput(prompt='fixture'))['status'],'NOT_CONFIGURED')
            (base/row['graph_file']).write_text(json.dumps({'prompt':{'1':{'class_type':'FixtureNode','inputs':{'text':''}}}}))
            row['execution']['graph_sha256']=hashlib.sha256((base/row['graph_file']).read_bytes()).hexdigest();path.write_text(json.dumps(raw))
            reviewed=GenerationFactory(credential,owner_enabled=True,manifest_path=path)
            self.assertEqual(reviewed.selection('image',ImageGenerationInput(prompt='fixture'))['status'],'CONFIGURED')
            (base/row['graph_file']).write_text('EXPLICIT DRIFT FIXTURE')
            with self.assertRaises(WorkflowError):reviewed.selection('image',ImageGenerationInput(prompt='fixture'))
            raw['workflows'].append(raw['workflows'][0]);path.write_text(json.dumps(raw))
            with self.assertRaises(WorkflowError):GenerationFactory(credential,owner_enabled=True,manifest_path=path)

    def test_explicit_wire_factory_reuses_scope_and_lifecycle_without_promoting_rights_cost_or_real_provider(self):
        events=[]
        async def observe(value):events.append(value)
        def handler(request):
            body=json.loads(request.content);self.assertEqual(body['workspace_id'],'workspace-fixture');self.assertEqual(request.headers['Authorization'],'Bearer '+TOKEN)
            self.assertNotIn('graph',body['inputs']);return httpx.Response(202,json={'job_id':'cui_native_generation_fixture','workspace_id':body['workspace_id'],
                'workflow_id':body['workflow_id'],'workflow_version':'1.0.0','status':'succeeded','progress':100,
                'result':{'artifact_reference':'fixture://native-lifecycle-only','fixture':True}})
        factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token=TOKEN,enabled=True),owner_enabled=True,transport=httpx.MockTransport(handler))
        payload=ImageGenerationInput(prompt='EXPLICIT NATIVE FACTORY FIXTURE');self.assertEqual(factory.selection('image',payload)['mode'],'fixture')
        with media_generation_scope(workspace_id='workspace-fixture',project_id='project-fixture',job_id='job-fixture'):
            result=asyncio.run(factory.create('image',payload,on_job=observe).generate(payload))
        self.assertEqual(events[0]['provider_job_id'],result.provider_job_id);self.assertEqual(events[0]['progress'],100)
        self.assertTrue(result.generation_provenance['fixture']);self.assertEqual(result.rights_status,'unknown');self.assertFalse(result.production_eligible)
        self.assertIsNone(result.actual_cost_vnd);self.assertFalse(result.real_provider_tested)
