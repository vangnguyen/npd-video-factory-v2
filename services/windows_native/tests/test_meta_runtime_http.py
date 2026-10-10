"""Actual isolated signed HTTP/runtime; all provider/media/eligibility fixtures explicit."""
import copy,json,os,subprocess,sys,threading,unittest
from datetime import timedelta
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_media_delivery import StorageProfile
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.contracts import WorkflowError
from services.windows_native.server import LocalServer
from services.windows_native.meta_distribution import NativeMetaPublishingFactory,ExecutionCapability
from services.windows_native.publishing_media_delivery import NativeMediaDeliveryFactory
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_meta_publish_worker import fixture
from services.windows_native.tests.media_delivery_fixture import FixtureStore


class MetaRuntimeHTTPTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        self.c=fixture(self.PLATFORM);self.root,self.folder,self.workspace=self.c.root,self.c.folder,self.c.workspace
        self.profile=StorageProfile('https://storage-fixture.invalid','vf-media-fixture','us-east-1','publishing-media-fixture')
        self.storage=FixtureStore(self.profile,lambda:self.c.clock[0]);self.media=NativeMediaDeliveryFactory(self.profile,self.root,self.workspace,
            enabled=True,directory=self.folder/'private'/'media',wire=self.storage.wire,clock=lambda:self.c.clock[0])
        self.meta=NativeMetaPublishingFactory(self.c.connection,owner_enabled=True,gates=self.c.factory.gates,execution=ExecutionCapability(media_configuration_sha256=self.media.sha256))
        self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'absent-secrets'/'openai.env',
            assemblyai_secret_file=self.folder/'absent-secrets'/'asr.dpapi',ffmpeg_bin=self.folder/'absent-ffmpeg')
        self.pipeline=NoProviderPipeline();self.raw,registry=identity('owner',workspace=self.workspace)
        self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.start_server(configured=True);self.base='/api/projects/'+self.c.project['id']+'/official-publications'
    def options(self):
        return dict(meta_account_factories={self.c.connection.account.account_ref:self.c.connection},meta_account_read_enabled=True,
            meta_distribution_factories={self.c.target.profile_id:self.meta},meta_distribution_enabled=True,publishing_media_factory=self.media,
            publishing_media_enabled=True,official_publish_session_directory=self.folder/'private'/'sessions',official_publish_queue_enabled=True)
    def start_server(self,*,configured=False):
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,
            publishing_capabilities_file=self.c.caps,**(self.options() if configured else {}))
        self.server.publications.clock=lambda:self.c.clock[0];self.server.official_publications.clock=lambda:self.c.clock[0]
        self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def stop_server(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self):self.stop_server();self.assertEqual(self.pipeline.calls,0);self.c.tearDown()
    def account(self,role):
        self.raw,registry=identity(role,workspace=self.workspace);self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.auth.bind_root(self.root);self.server.access=self.auth;self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf
    def post(self,path,body):
        status,value,headers=self.request('POST',path,body);self.assertEqual(status,200,value);return value
    def review(self):
        factory=self.server.official_publications.factories[self.c.target.profile_id]
        body={**self.c.body().model_dump(mode='json'),'schema_version':'native-official-meta-publication-request-v2',
            'expected_configuration_sha256':factory.sha256,'expected_media_configuration_sha256':self.server.publishing_media.factory.sha256}
        self.review_body=body;value=self.post(self.base,body);self.path=self.base+'/'+value['publication_id']
        self.value=self.post(self.path+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True});return self.value
    def create_media(self,**changes):
        self.media_body={'publication_id':self.value['publication_id'],'expected_publication_snapshot_sha256':self.value['snapshot_sha256'],
            'expected_configuration_sha256':self.server.publishing_media.factory.sha256,'acknowledged_external_media_delivery':True,
            'request_key':'explicit-http-meta-media-disclosure',**changes}
        return self.post(self.path+'/media-deliveries',self.media_body)
    def deliver(self):
        media=self.create_media();result=self.post(self.path+'/media-deliveries/'+media['delivery_id']+'/process',{'expected_snapshot_sha256':media['snapshot_sha256']})
        self.assertEqual(result['status'],'succeeded');return result
    def bind(self,media):
        state=self.request('GET',self.path+'/state')[1]
        self.binding_body={'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':state['dispatch']['version'],
            'media_delivery_id':media['delivery_id'],'expected_media_snapshot_sha256':media['snapshot_sha256'],'acknowledged_exact_media_selection':True,
            'request_key':'explicit-http-meta-exact-media-selection'}
        return self.post(self.path+'/media-selection',self.binding_body)
    def step(self):
        state=self.request('GET',self.path+'/state')[1];return self.post(self.path+'/step',{'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':state['dispatch']['version']})
    def complete(self):
        for _ in range(8):
            value=self.step()
            if value['receipt'] is not None:return value
        self.fail('Explicit Meta fixture not completed')
    def test_runtime_signed_review_separate_media_selection_and_async_receipt_use_one_worker(self):
        before=self.server.store.get(self.c.project['id']);calls=list(self.c.calls);self.review();media=self.deliver();binding=self.bind(media)
        self.assertEqual(self.c.calls,calls);self.assertFalse(binding['publishing_authority']);self.assertFalse(binding['url_returned'])
        result=self.complete();self.assertFalse(result['published']);self.assertTrue(result['mock_publication_complete'])
        self.assertEqual(result['provider_job']['provider_job_id'],'34567');self.assertEqual(len(self.c.mutations),3 if self.PLATFORM=='facebook' else 2)
        self.assertIs(self.server.official_publish_worker.meta.media,self.server.publishing_media);self.assertEqual(self.server.store.get(before['id']),before)
        self.assertEqual(self.storage.puts,1);self.assertNotIn('X-Amz-',json.dumps(result));self.assertNotIn(self.c.token,json.dumps(binding))
    def test_media_ack_and_selection_are_independent_of_publish_approval_and_creation_never_sends(self):
        self.review();calls=list(self.c.calls);stored=list(self.storage.calls)
        status,error,_=self.request('POST',self.path+'/step',{'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':1})
        self.assertEqual(status,409,error);self.assertEqual(self.c.calls,calls)
        media=self.create_media();self.assertEqual(media['status'],'queued');self.assertEqual(self.storage.calls,stored)
        self.assertEqual(self.request('POST',self.path+'/media-selection',{'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':1,
            'media_delivery_id':media['delivery_id'],'expected_media_snapshot_sha256':media['snapshot_sha256'],'acknowledged_exact_media_selection':True,'request_key':'explicit-incomplete-media-selection'})[0],409)
        for changes in ({'acknowledged_external_media_delivery':1},{'url':'https://unreviewed.invalid/file'},{'provider':'alternate'},{'token':'PRIVATE BODY'},
            {'max_external_cost_vnd':True},{'ttl_seconds':False}):
            self.assertEqual(self.request('POST',self.path+'/media-deliveries',{**self.media_body,**changes})[0],400)
        self.assertEqual(self.storage.calls,stored)
    def test_background_media_and_bounded_publication_queue_require_separate_requests(self):
        self.review();media=self.create_media();self.assertEqual(self.storage.calls,[]);self.assertTrue(self.server.runner.run_one())
        media=self.request('GET',self.path+'/media-deliveries/'+media['delivery_id'])[1];self.assertEqual(media['status'],'succeeded');self.bind(media)
        plan=self.post(self.path+'/queue',{'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':1,'acknowledged_background_steps':True,
            'max_steps':10,'interval_seconds':30,'start_at':self.c.clock[0].isoformat(),'deadline':(self.c.clock[0]+timedelta(seconds=600)).isoformat(),
            'request_key':'explicit-http-meta-bounded-background'})
        for _ in range(8):
            self.assertTrue(self.server.runner.run_one());self.c.clock[0]+=timedelta(seconds=30)
            saved=self.request('GET',self.path+'/queue/'+plan['plan_id'])[1]
            if saved['status']=='completed':break
        self.assertEqual(saved['status'],'completed');self.assertFalse(saved['steps'][-1]['result']['published']);self.assertEqual(self.storage.puts,1)
    def test_roles_and_csrf_block_before_body_secret_or_storage_processing(self):
        self.review();media=self.create_media();calls=list(self.storage.calls)
        paths=[self.path+'/media-deliveries',self.path+'/media-deliveries/'+media['delivery_id']+'/process',self.path+'/media-deliveries/'+media['delivery_id']+'/cancel',self.path+'/media-selection']
        for role in ('viewer','reviewer','editor'):
            self.account(role)
            for path in paths:self.assertEqual(self.request('POST',path,{'token':'PRIVATE UNPARSED BODY'})[0],403)
            self.assertEqual(self.request('GET',self.path+'/media-deliveries')[0],200)
        self.account('owner');self.csrf='invalid-csrf'
        for path in paths:self.assertEqual(self.request('POST',path,{'token':'PRIVATE UNPARSED BODY'})[0],403)
        self.assertEqual(self.storage.calls,calls)
    def test_exact_replay_and_bounded_history_foreign_scope_and_stale_process_sha(self):
        self.review();media=self.deliver();self.bind(media)
        replay=self.post(self.path+'/media-deliveries',self.media_body);self.assertTrue(replay['idempotent_replay'])
        self.assertTrue(self.post(self.path+'/media-selection',self.binding_body)['idempotent_replay']);self.assertEqual(self.storage.puts,1)
        self.assertEqual(self.request('POST',self.path+'/media-deliveries/'+media['delivery_id']+'/process',{'expected_snapshot_sha256':'f'*64})[0],409)
        for suffix in ('?limit=0','?limit=101','?cursor=foreign','?limit=1&limit=2','?provider=alternate'):
            self.assertEqual(self.request('GET',self.path+'/media-deliveries'+suffix)[0],400)
        other=self.server.store.create('Explicit foreign project','No provider');foreign=self.path.replace(self.c.project['id'],other['id'])
        self.assertEqual(self.request('GET',foreign+'/media-deliveries/'+media['delivery_id'])[0],404)
        another=self.post(self.path+'/media-deliveries',{**self.media_body,'request_key':'explicit-http-readonly-reconcile','reconcile_delivery_id':media['delivery_id']})
        self.post(self.path+'/media-deliveries/'+another['delivery_id']+'/process',{'expected_snapshot_sha256':another['snapshot_sha256']})
        first=self.request('GET',self.path+'/media-deliveries?limit=1')[1];self.assertTrue(first['truncated']);self.assertEqual(len(first['items']),1)
        second=self.request('GET',self.path+'/media-deliveries?limit=1&cursor='+first['next_cursor'])[1]
        self.assertFalse(second['truncated']);self.assertNotEqual(first['items'][0]['delivery_id'],second['items'][0]['delivery_id']);self.assertEqual(self.storage.puts,1)
    def test_default_off_cold_runtime_retains_completed_history_without_decrypt_or_replay(self):
        self.review();media=self.deliver();self.bind(media);self.complete();history=self.request('GET',self.base)[1];deliveries=self.request('GET',self.path+'/media-deliveries')[1]
        self.stop_server();self.c.path.unlink();(self.media.directory/(media['lease_ref']+'.dpapi')).unlink();calls=list(self.c.calls)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No cold key decrypt')):
            self.start_server()
            self.assertEqual(self.request('GET',self.base)[1],history);self.assertEqual(self.request('GET',self.path+'/media-deliveries')[1],deliveries)
            self.assertEqual(self.request('GET','/api/connections/publishing-media')[1]['status'],'NOT_CONFIGURED')
            self.assertEqual(self.request('GET','/api/connections/official-publishing')[1]['profiles'],[])
            self.assertFalse(self.server.official_publish_queue.enabled);self.assertFalse(self.server.runner.run_one())
            self.assertTrue(self.post(self.path+'/media-deliveries',self.media_body)['idempotent_replay'])
        self.assertEqual(self.c.calls,calls)
    def test_runtime_flag_and_config_failures_are_rejected_before_socket_allocation(self):
        cases=({'meta_distribution_enabled':1},{'publishing_media_enabled':1},{'meta_distribution_enabled':True,'meta_distribution_factories':None},
            {'publishing_media_enabled':True,'publishing_media_factory':None},{'meta_distribution_enabled':True,'meta_account_read_enabled':False},
            {'meta_distribution_enabled':True,'publishing_media_enabled':False},{'meta_distribution_enabled':True,'official_publish_session_directory':None})
        for change in cases:
            with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('Reject before socket')):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,start_worker=False,access=self.auth,**{**self.options(),**change})
    def test_disabled_runtime_masks_injected_gate_flags_without_provider_or_secret_reads(self):
        self.stop_server();calls=list(self.c.calls)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup token decrypt')):
            options={**self.options(),'meta_distribution_enabled':False,'publishing_media_enabled':False,'official_publish_queue_enabled':False}
            self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,**options)
            self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
            self.assertEqual(self.request('GET','/api/connections/publishing-media')[1]['status'],'NOT_CONFIGURED')
            config=self.request('GET','/api/connections/official-publishing')[1]['profiles'][0];self.assertFalse(config['external_actions_enabled']);self.assertEqual(config['status'],'NOT_CONFIGURED')
        self.assertEqual(self.c.calls,calls);self.assertEqual(self.storage.calls,[])
    def test_live_storage_injection_and_foreign_media_configuration_reject_before_socket(self):
        live=NativeMediaDeliveryFactory(self.profile,self.root,self.workspace,enabled=True,directory=self.folder/'private'/'live-media')
        wrong=NativeMetaPublishingFactory(self.c.connection,owner_enabled=True,gates=self.c.factory.gates,
            execution=ExecutionCapability(media_configuration_sha256='f'*64))
        for change in ({'publishing_media_factory':live},{'meta_distribution_factories':{self.c.target.profile_id:wrong}}):
            with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('No socket for invalid config')):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,start_worker=False,access=self.auth,**{**self.options(),**change})
        self.assertEqual(self.c.mutations,[]);self.assertEqual(self.storage.calls,[])
    def test_runtime_requires_human_auth_and_cli_exposes_separate_default_off_flags(self):
        with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('No unauthenticated socket')):
            with self.assertRaisesRegex(WorkflowError,'HUMAN_AUTH_REQUIRED'):LocalServer(0,self.config,start_worker=False,**self.options())
        process=subprocess.run([sys.executable,'-X','utf8','-m','services.windows_native.server','--help'],env=dict(os.environ),
            capture_output=True,text=True,encoding='utf8',timeout=30,check=True)
        for name in ('--meta-distribution-registry','--enable-meta-distribution','--publishing-media-registry','--enable-publishing-media'):
            self.assertIn(name,process.stdout)


class FacebookMetaRuntimeHTTPTests(MetaRuntimeHTTPTests):
    PLATFORM='facebook'


if __name__=='__main__':unittest.main()
