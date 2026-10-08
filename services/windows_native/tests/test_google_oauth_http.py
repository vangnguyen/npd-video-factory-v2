"""Signed local HTTP/protected public registries; all OAuth values are synthetic."""
import copy,json,threading,unittest
from pathlib import Path
from unittest.mock import patch
from services.windows_native.tests.test_google_oauth_operations import OAuthOperationsFixture
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Start,Refresh
from services.windows_native.google_oauth_registry import Registry,load
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer,Handler
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.observability import Observer
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry

class OAuthHTTPFixture(OAuthOperationsFixture):
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        super().setUp();self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'secrets'/'absent-openai',assemblyai_secret_file=self.folder/'secrets'/'absent-asr',ffmpeg_bin=self.folder/'absent-ffmpeg')
        self.logs=[];access=NativeAccess(self.verifier,self.workspace)
        self.server=LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=access,observer=Observer(self.logs.append),
            google_oauth_slots=self.slots,google_oauth_client=self.wire,google_oauth_directory=self.private,google_oauth_enabled=True)
        self.server.official_publications.clock=lambda:self.clock[0]
        self.operations=NativeGoogleOAuthOperations(self.server.official_publications,self.vault,slots=self.slots,client=self.wire,enabled=True)
        self.server.google_oauth=self.server.runner.google_oauth=self.operations
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='/api/projects/'+self.project['id']+'/google-oauth'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    def account(self,role):
        raw,registry=human_fixture(role,workspace=self.workspace);self.server.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
    def revoke(self):
        super().revoke();self.server.access=NativeAccess(self.verifier,self.workspace)
    def start_http(self,purpose='analytics',**changes):
        body={**self.start_payload(purpose).model_dump(mode='json'),'redirect_uri':f'http://127.0.0.1:{self.server.server_port}/oauth/google/callback',**changes}
        status,value,headers=self.request('POST',self.base+'/authorizations',body);self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store')
        self.saved=value;self.start_request=Start.model_validate(body);return value
    def exchange_http(self):
        path=self.base+'/authorizations/'+self.saved['authorization_id']+'/exchange'
        status,value,headers=self.request('POST',path,{'expected_snapshot_sha256':self.saved['snapshot_sha256'],'callback_query':self.query()});self.assertEqual(status,200,value);return value
    def registry(self,enabled=False):
        return Registry(version=1,workspace_id=self.workspace,token_exchange_enabled=enabled,slots=list(self.slots.values()))
    def registry_file(self,value=None,name='public-oauth-registry.json'):
        path=self.folder/name;path.write_text(json.dumps((value or self.registry()).model_dump(mode='json')),encoding='utf-8');return path

class GoogleOAuthHTTPTests(OAuthHTTPFixture,unittest.TestCase):
    def test_signed_start_url_exchange_refresh_history_no_worker_or_session_enablement(self):
        before=self.store.get(self.project['id']);session_before=self.request('GET','/api/session')[1];self.start_http();self.assertEqual(self.calls,[])
        path=self.base+'/authorizations/'+self.saved['authorization_id']
        binding={'expected_snapshot_sha256':self.saved['snapshot_sha256']};status,url,_=self.request('POST',path+'/authorization-url',binding);self.assertEqual(status,200);self.assertTrue(url['external_human_browser_required']);self.assertNotIn(SECRET,json.dumps(url))
        done=self.exchange_http();self.assertEqual(done['status'],'succeeded');self.assertEqual(len(self.calls),1);self.done=done
        status,value,_=self.request('POST',self.base+'/refresh',self.refresh_payload().model_dump(mode='json'));self.assertEqual(status,200,value);self.assertEqual(value['status'],'succeeded');self.assertEqual(len(self.calls),2)
        self.assertEqual(self.request('GET',self.base+'/operations/'+done['operation_id'])[1],done);self.assertEqual(len(self.request('GET',self.base+'/operations')[1]['items']),2)
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.request('GET','/api/session')[1],session_before);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertNotIn('native_google_oauth',session_before['capabilities'])
    def test_roles_csrf_and_missing_sessions_refuse_before_private_body_or_decrypt(self):
        for role in ('viewer','reviewer','editor'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN CALLBACK BODY')):
                for suffix in ('/authorizations','/refresh','/authorizations/ngoa_'+'a'*32+'/exchange','/authorizations/ngoa_'+'a'*32+'/authorization-url','/authorizations/ngoa_'+'a'*32+'/cancel'):
                    self.assertEqual(self.request('POST',self.base+suffix,{})[0],403)
            self.assertEqual(self.request('GET',self.base+'/operations')[0],200);self.assertEqual(self.request('GET','/api/connections/google-oauth')[0],403)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('NO MISSING CSRF BODY')):
            self.assertEqual(self.request('POST',self.base+'/authorizations',{},headers={'X-VF-CSRF':''})[0],403)
            self.assertEqual(self.request('POST',self.base+'/refresh',{},headers={'Cookie':''})[0],401)
        self.assertEqual(self.calls,[])
    def test_callback_private_values_not_allowed_in_get_queries_logs_or_error_replies(self):
        self.start_http();path=self.base+'/authorizations/'+self.saved['authorization_id']
        self.assertEqual(self.request('GET',path+'?'+self.query())[0],400)
        self.assertEqual(self.request('POST',path+'/exchange',{'expected_snapshot_sha256':self.saved['snapshot_sha256'],'callback_query':'state=foreign&code='+CODE})[0],400)
        self.mode='timeout';done=self.exchange_http();self.assertEqual(done['status'],'outcome_unknown')
        self.assertEqual(self.request('POST',path+'/exchange',{'expected_snapshot_sha256':self.saved['snapshot_sha256'],'callback_query':self.query()})[0],409)
        public=json.dumps(self.logs)+json.dumps(done)
        for value in (TOKEN,REFRESH,SECRET,CODE,self.raw,self.query()):self.assertNotIn(value,public)
        self.assertEqual(len(self.calls),1);self.assertFalse(self.server.runner.run_one())
    def test_strict_fields_fixed_server_redirect_and_config_key_conflicts(self):
        body={**self.start_payload().model_dump(mode='json'),'redirect_uri':f'http://127.0.0.1:{self.server.server_port}/oauth/google/callback'}
        for change in ({'acknowledged_credential_operation':1},{'acknowledged_protocol_mock':1},{'authority':{}},{'token':TOKEN},{'client_secret':SECRET},{'enabled':True},{'endpoint':'https://untrusted.invalid'},
            {'redirect_uri':'http://127.0.0.1:1/oauth/google/callback'},{'redirect_uri':'http://localhost:18047/'}):self.assertEqual(self.request('POST',self.base+'/authorizations',{**body,**change})[0],400)
        first=self.start_http();self.assertTrue(self.request('POST',self.base+'/authorizations',body)[1]['idempotent_replay']);self.assertEqual(self.request('POST',self.base+'/authorizations',{**body,'valid_for_seconds':601})[0],409)
        self.assertEqual(first['status'],'awaiting_callback');self.assertEqual(self.calls,[])
    def test_explicit_cancellation_and_scoped_history_no_provider(self):
        self.start_http();path=self.base+'/authorizations/'+self.saved['authorization_id']+'/cancel';binding={'expected_snapshot_sha256':self.saved['snapshot_sha256']}
        self.assertEqual(self.request('POST',path,{'expected_snapshot_sha256':'f'*64})[0],409);self.assertEqual(self.request('POST',path,binding)[1]['status'],'cancelled')
        self.account('viewer');self.assertEqual(self.request('GET',self.base+'/authorizations')[0],200)
        for query in ('?limit=0','?limit=101','?limit=-1','?limit=1&limit=2','?cursor=[]','?token=secret'):self.assertEqual(self.request('GET',self.base+'/authorizations'+query)[0],400)
        other=self.store.create('Other OAuth HTTP fixture','','media');self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/google-oauth/authorizations/'+self.saved['authorization_id'])[0],404)
        self.assertEqual(self.request('GET',self.base+'/operations/'+self.saved['authorization_id'])[0],400);self.assertEqual(self.calls,[])
    def test_protected_registry_loads_public_only_double_disabled_gates_without_startup_decrypt(self):
        path=self.registry_file()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP SECRET READ')):
            registry,protected,checksum=load(path,self.root,self.workspace);self.assertEqual(registry,self.registry());self.assertEqual(protected,path);self.assertEqual(len(checksum),64)
            with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),google_oauth_registry=path,google_oauth_directory=self.private,google_oauth_enabled=True) as disabled:
                self.assertFalse(disabled.google_oauth.configured());self.assertFalse(disabled.google_oauth.client.network_enabled);self.assertEqual(disabled.google_oauth.states()['registry_sha256'],checksum)
        self.assertEqual(self.calls,[])
    def test_registry_duplicate_numeric_gate_foreign_workspace_source_state_relative_and_size_refuse(self):
        value=self.registry().model_dump(mode='json')
        for change in ({'token_exchange_enabled':1},{'version':True},{'workspace_id':'wsp_foreign'},{'slots':[value['slots'][0],value['slots'][0]]},{'secret':SECRET}):
            path=self.folder/'invalid-registry.json';path.write_text(json.dumps({**value,**change}),encoding='utf-8')
            with self.assertRaises(WorkflowError):load(path,self.root,self.workspace)
        path=self.folder/'duplicate-keys.json';path.write_text('{"version":1,"version":1}',encoding='utf-8')
        with self.assertRaises(WorkflowError):load(path,self.root,self.workspace)
        for path in (self.root/'registry.json',Path(__file__).resolve().parents[3]/'invalid-google-registry.json',Path('relative.json')):
            with self.assertRaises(WorkflowError):load(path,self.root,self.workspace)
        path=self.folder/'oversize.json';path.write_bytes(b' '*262145)
        with self.assertRaises(WorkflowError):load(path,self.root,self.workspace)
    def test_unsafe_flags_and_real_client_injection_refuse_before_socket_or_decrypt(self):
        from app.google_oauth_protocol import GoogleOAuthTokenClient
        options=({'google_oauth_enabled':1},{'google_oauth_enabled':True},{'google_oauth_enabled':True,'access':self.server.access},
            {'google_oauth_slots':self.slots,'google_oauth_directory':self.private,'access':self.server.access},
            {'google_oauth_slots':self.slots,'google_oauth_client':GoogleOAuthTokenClient(network_enabled=True),'google_oauth_directory':self.private,'access':self.server.access},
            {'google_oauth_registry':self.registry_file(),'google_oauth_slots':self.slots,'access':self.server.access})
        with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('NO UNSAFE SOCKET')),patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP DECRYPT')):
            for values in options:
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,**values)
    def test_registry_revision_drift_fences_new_action_and_legacy_history_reopens_without_registry(self):
        path=self.registry_file();registry,protected,checksum=load(path,self.root,self.workspace)
        operations=NativeGoogleOAuthOperations(self.server.official_publications,self.vault,slots=self.slots,client=self.wire,enabled=True,registry_file=protected,registry_sha256=checksum)
        self.operations=self.server.google_oauth=self.server.runner.google_oauth=operations;self.start_http();self.done=self.exchange_http()
        self.assertEqual(self.done['snapshot']['registry_sha256'],checksum);path.write_bytes(path.read_bytes()+b'\n')
        self.assertEqual(self.request('GET','/api/connections/google-oauth')[0],409)
        with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as historical:
            self.assertFalse(historical.google_oauth.configured());self.assertEqual(historical.google_oauth.get(self.project['id'],self.done['operation_id']),self.done);self.assertEqual(historical.google_oauth.states()['slots'],[])
        self.assertEqual(len(self.calls),1)
    def test_fresh_default_server_does_not_initialize_oauth_journal_or_private_directory(self):
        config=Config(data_root=self.folder/'fresh-state',runtime_root=self.folder/'runtime',secret_file=self.folder/'fresh-private'/'absent-openai',assemblyai_secret_file=self.folder/'fresh-private'/'absent-asr',ffmpeg_bin=self.folder/'absent-ffmpeg')
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO DEFAULT DECRYPT')):
            with LocalServer(0,config,pipeline=NoProviderPipeline(),start_worker=False) as fresh:
                self.assertIsNone(fresh.google_oauth);self.assertIsNone(fresh.runner.google_oauth);self.assertFalse(fresh.runner.run_one())
                with fresh.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'native_google_oauth_%'").fetchone()[0],0)
        self.assertFalse((self.folder/'fresh-private').exists());self.assertEqual(self.calls,[])
