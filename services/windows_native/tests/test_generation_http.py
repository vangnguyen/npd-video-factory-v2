"""Actual isolated human/CSRF HTTP and media pixels, provider execution mocked."""
import hashlib,unittest
from unittest.mock import patch
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.server import Handler,LocalServer
from services.windows_native.generation_registry import GenerationFactory,GenerationCredential
from services.windows_native.generation_queue import NativeGenerationQueue
from services.windows_native.generation_worker import NativeGenerationWorker
from services.windows_native.contracts import WorkflowError
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
from scripts import north_star_native_generation_media as media_fixture
import httpx,io
from PIL import Image


class GenerationHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def payload(self,*,mock=False):
        return {'revision':self.project['revision'],'parameters':{'modality':'image','prompt':'EXPLICIT NATIVE HTTP GENERATION FIXTURE'},
            'external_acknowledged':not mock,'fixture_acknowledged':mock,'request_key':'explicit-http-generation-fixture-key'}

    def configured(self):
        def forbidden(request):raise AssertionError('No external request permitted in HTTP suite')
        factory=GenerationFactory(GenerationCredential(bridge_url='http://localhost:8011',service_token='explicit-http-generation-fixture-token-32',enabled=True),
            owner_enabled=True,transport=httpx.MockTransport(forbidden))
        queue=NativeGenerationQueue(self.server.store,workspace_id=self.server.publications.workspace_id,factory=factory)
        self.server.generation=NativeGenerationWorker(queue,self.config)
        async def generate(adapter,payload):
            job=queue.page(self.project['id'])['items'][0];selected=job['snapshot']['selection']
            await adapter.on_job({'schema_version':'comfyui-generation-observation-v1','phase':'polled','provider_job_id':'cui_explicit_native_http_fixture',
                'workspace_id':queue.workspace,'workflow_id':selected['workflow_id'],'workflow_version':selected['workflow_version'],'status':'succeeded','progress':100})
            pixels=io.BytesIO();Image.new('RGB',(640,360),(40,90,140)).save(pixels,format='PNG')
            with patch.object(media_fixture,'WORKSPACE',queue.workspace):return media_fixture.fixture_output(queue,queue.get(self.project['id'],job['generation_id']),payload,pixels.getvalue(),'image/png',640,360,None)
        return patch.object(ComfyUIBridgeGenerationProvider,'generate',generate)

    def test_default_inactive_catalog_eight_operations_and_editor_records_not_configured_no_project_change(self):
        before=self.server.store.get(self.project['id']);self.account('editor');base='/api/projects/'+self.project['id']+'/generation'
        status,config,headers=self.request('GET','/api/generation/providers');self.assertEqual(status,200);self.assertEqual(len(config['items']),8)
        self.assertTrue(all(item['status']=='NOT_CONFIGURED' for item in config['items']));self.assertFalse(config['owner_enabled']);self.assertFalse(config['ui_enablement_supported'])
        self.assertNotIn('service_token',str(config));self.assertNotIn('bridge_url',str(config));self.assertEqual(headers['Cache-Control'],'no-store')
        status,row,_=self.request('POST',base,self.payload());self.assertEqual(status,200);self.assertEqual(row['status'],'not_configured');self.assertIsNone(row['result'])
        self.assertTrue(row['worker_wired']);self.assertEqual(self.server.store.get(self.project['id']),before);self.assertIsNone(self.server.generation.process())
        self.assertTrue(self.request('POST',base,self.payload())[1]['idempotent_replay'])
        self.assertEqual(self.request('GET',base+'/invalid-identity')[0],404)

    def test_human_roles_csrf_service_header_and_extra_provider_or_graph_fields_fail_before_execution(self):
        base='/api/projects/'+self.project['id']+'/generation'
        for role in ['reviewer','viewer']:
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized generation body must not be read')):
                for path in [base,base+'/'+'0'*32+'/cancel',base+'/'+'0'*32+'/recover',base+'/'+'0'*32+'/import']:self.assertEqual(self.request('POST',path,self.payload())[0],403)
            self.assertEqual(self.request('GET',base)[0],200)
        self.account('editor');self.assertEqual(self.request('POST',base,self.payload(),{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',base,self.payload(),{'Cookie':'','Authorization':'Bearer explicit-service-fixture-token'})[0],401)
        for changes in [{'graph':{}},{'bridge_url':'http://untrusted.example'},{'result':{}},{'service_token':'private'},{'provider':'comfyui'}]:
            self.assertEqual(self.request('POST',base,{**self.payload(),**changes})[0],400)
        self.assertEqual(self.request('POST','/api/generation/enable',{'enabled':True})[0],403)
        for query in ['?limit=0','?limit=201','?limit=x','?limit=1&limit=2','?cursor=private']:self.assertEqual(self.request('GET',base+query)[0],400)
        self.assertEqual(self.request('GET','/api/generation/providers?secret=x')[0],400)

    def test_actual_generated_image_editor_import_viewer_read_and_foreign_scope_hash_match(self):
        base='/api/projects/'+self.project['id']+'/generation';before=self.server.store.get(self.project['id']);self.account('editor')
        with self.configured():
            status,row,_=self.request('POST',base,self.payload(mock=True));self.assertEqual(status,200);self.assertEqual(row['status'],'queued');self.server.generation.process()
        status,result,_=self.request('GET',base+'/'+row['generation_id']);self.assertEqual(status,200);self.assertEqual(result['status'],'succeeded')
        self.assertEqual(result['result']['asset']['rights_status'],'unknown');self.assertFalse(result['result']['real_provider_tested']);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.account('viewer');status,content,_=self.request('GET',base+'/'+row['generation_id']+'/file');self.assertEqual(status,200)
        self.assertEqual(hashlib.sha256(content).hexdigest(),result['result']['asset']['sha256'])
        request={'revision':self.project['revision'],'expected_fingerprint':row['request_fingerprint'],'expected_asset_sha256':result['result']['asset']['sha256'],
            'acknowledged':True,'request_key':'explicit-http-generation-import-key'}
        with patch.object(Handler,'read_body',side_effect=AssertionError('Viewer cannot import')):self.assertEqual(self.request('POST',base+'/'+row['generation_id']+'/import',request)[0],403)
        other=self.server.store.create('FOREIGN','PRIVATE')['id'];self.assertEqual(self.request('GET','/api/projects/'+other+'/generation/'+row['generation_id'])[0],404)
        self.account('editor');status,receipt,_=self.request('POST',base+'/'+row['generation_id']+'/import',request);self.assertEqual(status,200);self.assertTrue(receipt['approval_invalidated'])
        self.assertFalse(receipt['rights_independently_verified']);self.assertIsNone(self.server.store.get(self.project['id'])['approval'])
        self.assertTrue(self.request('POST',base+'/'+row['generation_id']+'/import',request)[1]['idempotent_replay'])
        self.assertEqual(self.request('GET',base+'/'+row['generation_id'])[1]['attachment'],receipt)
        self.assertEqual(self.request('GET',base+'?limit=25')[1]['items'][0]['attachment'],receipt)
        self.assertEqual(self.request('GET',base+'/'+row['generation_id']+'/file?path=private')[0],400)

    def test_editor_cancels_unstarted_request_and_recovers_only_after_dispatch_with_explicit_ack(self):
        base='/api/projects/'+self.project['id']+'/generation';self.account('editor')
        with self.configured():status,row,_=self.request('POST',base,self.payload(mock=True))
        action={'expected_fingerprint':row['request_fingerprint']};identity=row['generation_id']
        self.assertEqual(self.request('POST',base+'/'+identity+'/recover',{**action,'acknowledged':True,'request_key':'explicit-http-recovery-key'})[0],409)
        self.assertEqual(self.request('POST',base+'/'+identity+'/cancel',action)[1]['status'],'cancelled')
        self.assertEqual(self.request('POST',base+'/'+identity+'/cancel',action)[1]['status'],'cancelled')

    def test_enablement_requires_protected_registry_human_auth_and_cli_can_never_enable_from_body(self):
        with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,generation_api_enabled=True)
        self.assertIn('native_generation_media',self.request('GET','/api/session')[1]['capabilities'])
        self.assertEqual(self.request('GET','/native-generation.mjs')[0],200)
        self.account('owner');self.assertEqual(self.request('POST','/api/generation/enable',{'enabled':True})[0],403)


if __name__=='__main__':unittest.main()
