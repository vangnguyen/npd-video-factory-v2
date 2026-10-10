"""Signed existing HTTP routes with explicitly bound inert Meta admission fixtures."""
import threading, unittest
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer
from services.windows_native.meta_distribution import NativeMetaPublishingFactory
from services.windows_native.tests import test_meta_distribution as admission_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity


class MetaAdmissionHTTPTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    request=access_fixture.NativeAccessHTTPTests.request

    def setUp(self):
        kind=admission_fixture.FacebookAdmissionTests if self.PLATFORM=='facebook' else admission_fixture.MetaAdmissionTests
        self.c=kind('test_separate_owner_grant_binds_current_account_dry_run_final_and_metadata_without_wire');self.c.setUp()
        self.workspace,self.root,self.folder=self.c.workspace,self.c.root,self.c.folder
        self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'absent-secrets'/'openai.env',
            assemblyai_secret_file=self.folder/'absent-secrets'/'asr.dpapi',ffmpeg_bin=self.folder/'absent-ffmpeg')
        self.pipeline=NoProviderPipeline();self.raw,registry=identity('owner',workspace=self.workspace)
        self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.start_server(configured=True);self.base='/api/projects/'+self.c.project['id']+'/official-publications'

    def start_server(self,*,configured=False):
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,
            meta_account_factories={self.c.connection.account.account_ref:self.c.connection} if configured else None,
            meta_account_read_enabled=configured,official_publish_session_directory=self.folder/'private'/'sessions')
        # Explicit synthetic capability verification is scoped only to this fixture.
        self.server.publications.capabilities_path=self.c.publications.capabilities_path
        self.server.publications.capabilities=self.c.publications.capabilities
        self.server.publications.capabilities_sha256=self.c.publications.capabilities_sha256
        self.server.official_publications.clock=lambda:self.c.clock[0]
        if configured:
            connection=self.server.official_accounts.factories[self.c.connection.account.account_ref]
            factory=NativeMetaPublishingFactory(connection,owner_enabled=True,gates=self.c.factory.gates)
            self.assertEqual(factory.sha256,self.c.factory.sha256)
            self.server.official_publications.bind_meta_accounts(factories={self.c.target.profile_id:factory})
        self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def stop_server(self):self.server.shutdown();self.server.server_close();self.thread.join()
    def tearDown(self):self.stop_server();self.assertEqual(self.pipeline.calls,0);self.c.tearDown()
    def account(self,role):
        self.raw,registry=identity(role,workspace=self.workspace)
        self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace);self.auth.bind_root(self.root)
        self.server.access=self.auth;self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf
    def create_http(self):
        status,value,_=self.request('POST',self.base,self.c.body().model_dump(mode='json'));self.assertEqual(status,200,value);return value
    def approve_http(self,value):
        status,result,_=self.request('POST',self.base+'/'+value['publication_id']+'/approve',{
            'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True})
        self.assertEqual(status,200,result);return result

    def test_existing_signed_review_approval_status_is_inert_and_cannot_send(self):
        status,config,_=self.request('GET','/api/connections/official-publishing');self.assertEqual(status,200,config)
        self.assertFalse(config['profiles'][0]['execution_supported']);value=self.create_http();approved=self.approve_http(value)
        path=self.base+'/'+value['publication_id'];status,state,_=self.request('GET',path+'/state');self.assertEqual(status,200,state)
        self.assertEqual(state['dispatch']['phase'],'prepared');self.assertFalse(approved['published']);self.assertIsNone(state['dispatch']['remote_post_id'])
        status,error,_=self.request('POST',path+'/step',{'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':1})
        self.assertEqual(status,409,error);self.assertEqual(error['code'],'NATIVE_OFFICIAL_PUBLISH_EXECUTION_NOT_IMPLEMENTED')
        status,replay,_=self.request('POST',self.base,self.c.body().model_dump(mode='json'));self.assertEqual(status,200,replay);self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(len(self.c.calls),1 if self.PLATFORM=='facebook' else 2)

    def test_roles_and_csrf_reject_before_admission_and_viewer_reads_history(self):
        value=self.create_http()
        for role in ('viewer','editor','reviewer'):
            self.account(role);status,error,_=self.request('POST',self.base,{'token':'PRIVATE BODY MUST NOT BE PARSED'})
            self.assertEqual(status,403,error);self.assertEqual(self.request('GET',self.base+'/'+value['publication_id'])[0],200)
        self.account('owner');saved=self.csrf;self.csrf='invalid-csrf'
        self.assertEqual(self.request('POST',self.base,{'token':'PRIVATE BODY MUST NOT BE PARSED'})[0],403);self.csrf=saved

    def test_fields_config_fingerprints_and_foreign_project_are_fenced(self):
        body=self.c.body().model_dump(mode='json')
        for changes in ({'revision':True},{'metadata':{'privacy':'private'}},{'token':'no client tokens'},{'api_version':'v1.0'}):
            self.assertEqual(self.request('POST',self.base,{**body,**changes})[0],400)
        self.assertEqual(self.request('POST',self.base,{**body,'expected_account_result_sha256':'f'*64})[0],409)
        value=self.create_http();other=self.server.store.create('Foreign project','No publication')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/official-publications/'+value['publication_id'])[0],404)

    def test_default_off_cold_server_reads_exact_history_without_factory_or_private_token(self):
        value=self.create_http();self.approve_http(value);status,history,_=self.request('GET',self.base);self.assertEqual(status,200)
        self.stop_server();self.c.path.unlink();self.start_server()
        self.assertEqual(self.request('GET',self.base)[1],history)
        self.assertEqual(self.request('GET','/api/connections/official-publishing')[1]['profiles'],[])
        self.assertFalse(self.server.official_publish_queue.enabled);self.assertIsNone(self.server.official_accounts.process())
        self.assertEqual(len(self.c.calls),1 if self.PLATFORM=='facebook' else 2)


class FacebookAdmissionHTTPTests(MetaAdmissionHTTPTests):
    PLATFORM='facebook'
