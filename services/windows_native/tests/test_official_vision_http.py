"""Signed actual local HTTP, actual CPU PNG/DPAPI, explicitly synthetic Vision."""
import base64,copy,json,re,threading,unittest
from urllib.parse import urljoin
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests.test_official_vision import OfficialVisionFixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.vision import NativeVision
from services.windows_native.vision_registry import VisionRegistry,NativeVisionFactory
from services.windows_native.official_vision import TABLES
from services.windows_native.official_vision_models import Action
from services.windows_native.contracts import WorkflowError
from services.windows_native.observability import Observer


class OfficialVisionHTTPFixture(OfficialVisionFixture):
    http = access_fixture.NativeAccessHTTPTests.request

    def setUpFrames(self):
        OfficialVisionFixture.setUpFrames(self)
        self.service=NativeVision(self.store,self.config,workspace_id='wsp_official_vision_fixture')

    def setUp(self):
        super().setUp();self.logs=[];self.pipeline=NoProviderPipeline()
        access=NativeAccess(self.verifier,self.workspace)
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access,observer=Observer(self.logs.append),
            official_vision_directory=self.vault.directory,official_vision_enabled=True,official_vision_factories={self.factory.profile.profile_id:self.factory})
        self.official=self.server.official_vision
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.project['id']+'/official-vision'

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()

    def account(self,role):
        self.raw,data=human_fixture(role,workspace=self.workspace)
        self.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        access=NativeAccess(self.verifier,self.workspace);access.bind_root(self.root);self.server.access=access
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf;self.principal=session.principal

    def revoke(self):
        super().revoke();access=NativeAccess(self.verifier,self.workspace);access.bind_root(self.root);self.server.access=access

    def create_http(self,**changes):
        status,value,headers=self.http('POST',self.base,self.request(**changes).model_dump(mode='json'))
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');self.pending=value;return value

    def process_http(self,row):
        status,value,headers=self.http('POST',self.base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':row['snapshot_sha256']})
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value


class NativeOfficialVisionHTTPTests(OfficialVisionHTTPFixture,unittest.TestCase):
    def test_explicit_finite_mock_http_one_send_history_no_worker_project_or_session_change(self):
        before=self.store.get(self.project['id']);session=self.http('GET','/api/session')[1]
        row=self.create_http();self.assertEqual(row['status'],'approved');self.assertEqual(self.calls,[])
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.calls,[])
        done=self.process_http(row);self.assertEqual(done['status'],'succeeded');self.assertEqual(len(self.calls),1)
        self.assertTrue(done['result']['mock']);self.assertFalse(done['result']['semantic_inference_performed'])
        self.assertFalse(done['result']['automatic_planning_eligible']);self.assertFalse(done['owner_uat_accepted'])
        self.assertEqual(self.process_http(row),done);self.assertEqual(len(self.calls),1)
        self.assertEqual(self.http('GET',self.base+'/'+row['vision_id'])[1],done)
        self.assertEqual(self.http('GET','/api/session')[1],session);self.assertFalse(session['capabilities']['native_official_vision'])
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.pipeline.calls,0)
        cost=self.official.costs.summary(self.project['id'])['records'][0]
        self.assertFalse(cost['paid']);self.assertFalse(cost['external_call']);self.assertIsNone(cost['actual_cost'])
        public=json.dumps(done)+json.dumps(self.logs)
        self.assertNotIn(self.raw,public);self.assertNotIn('sk-explicit-synthetic-native-runtime-only',public)

    def test_all_non_owner_writes_denied_before_body_and_scoped_history_allowed(self):
        row=self.create_http()
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNAUTHORIZED VISION BODY')):
                for route in (self.base,self.base+'/'+row['vision_id']+'/process',self.base+'/'+row['vision_id']+'/cancel'):
                    self.assertEqual(self.http('POST',route,{'role':'owner'})[0],403)
            self.assertEqual(self.http('GET',self.base)[0],200);self.assertEqual(self.http('GET',self.base+'/'+row['vision_id'])[0],200)
            self.assertEqual(self.http('GET','/api/connections/official-vision')[0],403)
        self.assertEqual(self.calls,[])

    def test_csrf_origin_unauthenticated_guards_precede_body(self):
        for headers,expected in (({'X-VF-CSRF':''},403),({'Cookie':''},401),({'Origin':'https://untrusted.invalid'},403)):
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN VISION BODY')):
                self.assertEqual(self.http('POST',self.base,{},headers)[0],expected)
        self.assertEqual(self.calls,[])

    def test_strict_ack_budget_authority_key_url_and_unknown_fields_refused(self):
        body=self.request().model_dump(mode='json')
        for change in ({'acknowledged_external_image_analysis':1},{'acknowledged_protocol_mock':1},{'revision':True},
            {'max_operation_cost_vnd':500.0},{'max_operation_cost_vnd':'NaN'},{'max_operation_cost_vnd':'100'},
            {'valid_for_seconds':901},{'authority':{}},{'api_key':'sk-private'},{'endpoint':'https://untrusted.invalid'},
            {'enabled':True},{'expected_configuration_sha256':'f'*64},{'acknowledged_protocol_mock':False}):
            self.assertIn(self.http('POST',self.base,{**body,**change})[0],(400,409))
        self.assertEqual(self.calls,[])

    def test_idempotency_replays_without_new_consent_and_conflicts(self):
        row=self.create_http();again=self.create_http();self.assertTrue(again['idempotent_replay']);self.assertEqual(again['snapshot_sha256'],row['snapshot_sha256'])
        self.assertEqual(self.http('POST',self.base,{**self.request().model_dump(mode='json'),'valid_for_seconds':601})[0],409)
        self.assertEqual(self.http('POST',self.base+'/'+row['vision_id']+'/process',{'expected_snapshot_sha256':'f'*64})[0],409)
        self.assertEqual(self.calls,[])

    def test_bounded_pagination_cursors_and_project_scope(self):
        rows=[self.create_http(request_key='explicit-vision-page-'+str(i)) for i in range(3)]
        page=self.http('GET',self.base+'?limit=1')[1];seen=[page['items'][0]['vision_id']]
        while page['next_cursor']:
            page=self.http('GET',self.base+'?limit=1&cursor='+page['next_cursor'])[1];seen.extend(v['vision_id'] for v in page['items'])
        self.assertEqual(set(seen),{v['vision_id'] for v in rows});self.assertEqual(len(seen),3)
        for query in ('limit=0','limit=101','limit=-1','limit=1&limit=2','limit=1.0','cursor=','cursor=[]','unknown=secret'):
            self.assertEqual(self.http('GET',self.base+'?'+query)[0],400)
        cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,'f'*32,rows[0]['created_at'],rows[0]['vision_id']]).encode()).decode().rstrip('=')
        self.assertEqual(self.http('GET',self.base+'?cursor='+cursor)[0],400)
        other=self.store.create('Other scoped Vision HTTP fixture','','media')
        self.assertEqual(self.http('GET',self.base.replace(self.project['id'],other['id'])+'/'+rows[0]['vision_id'])[0],404)
        self.assertEqual(self.http('GET',self.base+'/'+rows[0]['vision_id']+'?limit=1')[0],400)
        self.assertEqual(self.calls,[])

    def test_cancel_is_local_no_remote_rollback_or_worker_dispatch(self):
        row=self.create_http();status,done,_=self.http('POST',self.base+'/'+row['vision_id']+'/cancel',{'expected_snapshot_sha256':row['snapshot_sha256']})
        self.assertEqual(status,200);self.assertEqual(done['status'],'cancelled');self.assertEqual(self.process_http(row),done)
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.calls,[])

    def test_known_response_survives_late_owner_revocation(self):
        self.mode='revoke';row=self.create_http();done=self.process_http(row)
        self.assertEqual(done['status'],'review_required');self.assertIsNotNone(done['response']);self.assertIsNone(done['result'])
        self.assertEqual(len(self.calls),1);self.account('viewer');self.assertEqual(self.http('GET',self.base+'/'+row['vision_id'])[1],done)

    def test_ambiguous_timeout_is_never_retried_by_http_or_worker(self):
        self.mode='timeout';row=self.create_http();done=self.process_http(row);self.assertEqual(done['status'],'outcome_unknown')
        self.assertIsNone(done['response']);self.assertEqual(self.process_http(row),done);self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.calls),1)
        self.assertNotIn('sk-private-runtime-timeout-message',json.dumps(done)+json.dumps(self.logs))

    def test_restart_unconfigured_keeps_history_and_no_secret_mount_or_renewal(self):
        done=self.process_http(self.create_http());absent=Path(self.temp.name)/'absent-vision-private'
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO RESTART DECRYPT')):
            with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as restored:
                self.assertEqual(restored.official_vision.get(self.project['id'],done['vision_id']),done)
                self.assertEqual(restored.official_vision.recover(),0);self.assertFalse(restored.runner.run_one())
                self.assertFalse(restored.official_vision.states()['enabled']);self.assertEqual(restored.official_vision.states()['profiles'],[])
        self.assertFalse(absent.exists());self.assertEqual(len(self.calls),1)

    def test_runner_start_recovers_claim_only_never_decrypts_resends_or_renews(self):
        row=self.create_http()
        with self.store.transaction() as con:
            con.execute("UPDATE native_official_vision_intents SET status='claimed',claim_id=? WHERE vision_id=?",('nvoc_'+'a'*32,row['vision_id']))
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO STARTUP DECRYPT')):
            self.server.runner.start();self.server.runner.stop.set();self.server.runner.wake.set();self.server.runner.thread.join(timeout=5)
        done=self.http('GET',self.base+'/'+row['vision_id'])[1]
        self.assertEqual(done['status'],'outcome_unknown');self.assertEqual(done['snapshot'],row['snapshot']);self.assertEqual(self.calls,[])

    def test_protected_registry_only_public_startup_separate_raw_gate(self):
        path=Path(self.temp.name)/'public-vision-registry.json'
        path.write_text(json.dumps(VisionRegistry(version=1,workspace_id=self.workspace,profiles=[self.factory.profile]).model_dump(mode='json')),encoding='utf-8')
        for enabled in (False,True):
            with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO CONFIG STARTUP DECRYPT')):
                with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),
                    official_vision_registry=path,official_vision_directory=self.vault.directory,official_vision_enabled=enabled) as configured:
                    value=configured.official_vision.states();self.assertIs(value['enabled'],enabled);self.assertFalse(value['profiles'][0]['mock'])
                    self.assertEqual(value['profiles'][0]['status'],'CONFIGURED' if enabled else 'NOT_CONFIGURED')
                    self.assertFalse(configured.runner.run_one())
        self.assertEqual(self.calls,[])

    def test_server_rejects_coerced_conflicting_unprotected_and_network_injected_configs(self):
        path=Path(self.temp.name)/'absent-public-registry.json'
        real=NativeVisionFactory(self.factory.profile,self.vault,operator_enabled=True)
        bad=({'official_vision_enabled':1},{'official_vision_enabled':True}, {'official_vision_directory':self.vault.directory},
            {'official_vision_registry':path},{'official_vision_registry':path,'official_vision_directory':self.vault.directory,'official_vision_factories':{}},
            {'official_vision_factories':{real.profile.profile_id:real},'official_vision_directory':self.vault.directory,'official_vision_enabled':True},
            {'official_vision_factories':{self.factory.profile.profile_id:self.factory},'official_vision_directory':self.vault.directory},
            {'official_vision_factories':{},'official_vision_directory':self.root/'private'})
        for kwargs in bad:
            with self.assertRaises(WorkflowError):
                LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace),**kwargs)
        with self.assertRaises(WorkflowError):
            LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,official_vision_registry=path,official_vision_directory=self.vault.directory)
        self.assertEqual(self.calls,[])

    def test_default_fresh_server_creates_no_journal_vault_decryption_or_capability_change(self):
        fresh=replace(self.config,data_root=Path(self.temp.name)/'fresh-state')
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO DEFAULT DECRYPT')):
            with LocalServer(0,fresh,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as default:
                self.assertIsNone(default.official_vision);self.assertIsNone(default.runner.official_vision)
                with default.store.transaction() as con:
                    for table in TABLES:self.assertIsNone(con.execute('SELECT name FROM sqlite_master WHERE name=?',(table,)).fetchone())
                self.assertFalse(default.runner.run_one())
        self.assertFalse((fresh.secret_file.parent/'vision-private').exists());self.assertEqual(self.calls,[])

    def test_default_fresh_signed_routes_are_inert_without_creating_journals(self):
        fresh=replace(self.config,data_root=Path(self.temp.name)/'fresh-signed-state');original=(self.server,self.cookie,self.csrf)
        with LocalServer(0,fresh,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as default:
            cookie,session=default.access.login(self.raw);thread=threading.Thread(target=default.serve_forever,daemon=True);thread.start()
            self.server,self.cookie,self.csrf=default,cookie,session.csrf
            try:
                project=default.store.create('Default inert official Vision fixture','','media');base='/api/projects/'+project['id']+'/official-vision'
                self.assertFalse(self.http('GET','/api/connections/official-vision')[1]['enabled'])
                self.assertEqual(self.http('GET',base)[1]['items'],[]);self.assertEqual(self.http('POST',base,{})[0],503)
                self.assertEqual(self.http('GET',base+'?cursor=')[0],400);self.assertEqual(self.http('GET',base+'?limit=101')[0],400)
                with default.store.transaction() as con:
                    for table in TABLES:self.assertIsNone(con.execute('SELECT name FROM sqlite_master WHERE name=?',(table,)).fetchone())
            finally:
                default.shutdown();thread.join();self.server,self.cookie,self.csrf=original

    def test_studio_module_and_separate_card_are_served_without_analysis_or_capability_enablement(self):
        for path,expected in (('/native-official-vision.mjs',b'initializeNativeOfficialVision'),('/native.html',b'id="native-official-vision-card" hidden'),('/native.mjs',b'officialVisionUI?.sync()')):
            status,value,_=self.http('GET',path);self.assertEqual(status,200);self.assertIn(expected,value)
        self.assertFalse(self.http('GET','/api/session')[1]['capabilities']['native_official_vision']);self.assertEqual(self.calls,[])

    def test_actual_main_page_module_dependencies_load_with_javascript_mime(self):
        status,html,_=self.http('GET','/native.html');self.assertEqual(status,200)
        pending=re.findall(r'<script[^>]*src="([^"]+)"',html.decode('utf-8'));seen=set()
        self.assertIn('/native.mjs',pending)
        while pending:
            path=pending.pop()
            if path in seen:continue
            self.assertTrue(path.startswith('/'));self.assertLess(len(seen),128)
            status,value,headers=self.http('GET',path);self.assertEqual(status,200,path);self.assertTrue(headers['Content-Type'].startswith(('text/javascript','application/javascript')),path)
            seen.add(path)
            for reference in re.findall(r'(?:from\s*|import\s*\(\s*|import\s*)[\'\"]([^\'\"]+)[\'\"]',value.decode('utf-8')):
                if reference.startswith('./') and reference.endswith('.mjs'):pending.append(urljoin(path,reference))
        self.assertIn('/project-quality.mjs',seen);self.assertIn('/native-official-vision.mjs',seen);self.assertGreater(len(seen),20);self.assertEqual(self.calls,[])


if __name__=='__main__':unittest.main()
