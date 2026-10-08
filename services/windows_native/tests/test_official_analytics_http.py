"""Actual owned signed HTTP/Runner; all account/media/provider acceptance is fixture."""
import json,threading,unittest
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_official_analytics as analytics_fixture
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer,Handler
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_account_registry import AccountFactory
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.observability import Observer
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry

class OfficialAnalyticsHTTPFixture(analytics_fixture.OfficialAnalyticsFixture):
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        super().setUp();self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'secrets'/'absent-openai',assemblyai_secret_file=self.folder/'secrets'/'absent-asr',ffmpeg_bin=self.folder/'absent-ffmpeg')
        self.pipeline=NoProviderPipeline();access=NativeAccess(self.verifier,self.workspace);self.operation_logs=[]
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access,
            official_account_factories={self.reader.account.account_ref:self.reader},official_analytics_enabled=True,observer=Observer(self.operation_logs.append))
        # Explicit synthetic clock injected by reconstructing the frozen kernel, never a body flag.
        self.server.official_publications.clock=lambda:self.clock[0]
        self.analytics=NativeOfficialAnalytics(self.server.official_publications,enabled=True)
        self.server.official_analytics=self.server.runner.official_analytics=self.analytics
        self.server.bridge.bind_qualified_sources(analytics=self.analytics)
        self.server.publications.capabilities_path=self.publications.capabilities_path
        self.server.publications.capabilities=self.publications.capabilities;self.server.publications.capabilities_sha256=self.publications.capabilities_sha256
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.base='/api/projects/'+self.project['id']+'/official-analytics'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();super().tearDown()
    def account(self,role):
        raw,registry=human_fixture(role,workspace=self.workspace);verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        self.server.access=NativeAccess(verifier,self.workspace);self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
    def create_http(self,**changes):
        status,value,headers=self.request('POST',self.base,self.collection(**changes).model_dump(mode='json'))
        self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');self.sync=value;return value
class OfficialAnalyticsHTTPTests(OfficialAnalyticsHTTPFixture,unittest.TestCase):
    def test_explicit_signed_create_stores_only_then_runner_collects_three_read_proofs(self):
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.read_wire,[])
        status,runtime,headers=self.request('GET','/api/connections/official-analytics');self.assertEqual(status,200);self.assertTrue(runtime['enabled'])
        self.assertFalse(runtime['default_enabled']);self.assertFalse(runtime['publishing_enabled']);self.assertEqual(headers['Cache-Control'],'no-store')
        before=self.server.store.get(self.project['id']);value=self.create_http();self.assertEqual(value['status'],'queued');self.assertEqual(self.read_wire,[])
        self.assertTrue(self.server.runner.wake.is_set());self.assertTrue(self.server.runner.run_one());self.assertFalse(self.server.runner.run_one())
        status,done,headers=self.request('GET',self.base+'/'+value['sync_id']);self.assertEqual(status,200);self.assertEqual(done['status'],'succeeded')
        self.assertEqual(len(self.read_wire),3);self.assertTrue(done['result']['mock']);self.assertFalse(done['result']['real_audience_observation'])
        self.assertEqual(before,self.server.store.get(self.project['id']));self.assertNotIn(self.read_credential.token,json.dumps(done));self.assertEqual(headers['Cache-Control'],'no-store')
        steps=[json.loads(r) for r in self.operation_logs if json.loads(r)['event']=='worker_step'];self.assertEqual(len(steps),1)
        self.assertEqual(steps[0]['job_id'],value['sync_id']);self.assertEqual(steps[0]['project_id'],self.project['id']);self.assertEqual(steps[0]['stage'],'official_analytics_read')
        self.assertEqual(steps[0]['provider'],'youtube-analytics-api');self.assertNotIn(self.read_credential.token,json.dumps(self.operation_logs))
    def test_roles_and_csrf_are_enforced_before_body_or_provider_read(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must not be read')):
                self.assertEqual(self.request('POST',self.base,{})[0],403)
                self.assertEqual(self.request('POST',self.base+'/noas_'+'a'*32+'/cancel',{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-analytics')[0],403);self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):
            self.assertEqual(self.request('POST',self.base,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.read_wire,[])

    def test_completed_exact_key_replay_returns_qualified_result_without_more_reads(self):
        value=self.create_http();self.assertIsNone(value['result']);self.assertTrue(self.server.runner.run_one())
        stored=self.request('GET',self.base+'/'+value['sync_id'])[1];replayed=self.create_http()
        self.assertTrue(replayed.pop('idempotent_replay'));self.assertEqual(replayed,stored)
        self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.read_wire),3)

    def test_read_only_source_binding_uses_server_receipt_hash_without_publish_authority(self):
        self.account('viewer');path=self.base+'/source/'+self.completed['publication_id']
        status,binding,headers=self.request('GET',path);self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertEqual(binding['receipt_sha256'],digest(self.completed['receipt']));self.assertEqual(binding['publication_snapshot_sha256'],self.completed['snapshot_sha256'])
        self.assertTrue(binding['mock']);self.assertFalse(binding['published']);self.assertFalse(binding['publishing_enabled']);self.assertTrue(binding['receipt_qualified'])
        self.assertEqual(self.request('GET',path+'?token=NEVER')[0],400);self.assertEqual(self.read_wire,[])
    def test_strict_idempotent_consent_and_local_cancel_have_no_provider_requests(self):
        body=self.collection().model_dump(mode='json')
        for changes in ({'acknowledged_read_only':1},{'acknowledged_protocol_mock':1},{'max_attempts':True},{'enabled':True},{'token':'NEVER'},{'endpoint':'https://untrusted.invalid'}):
            self.assertEqual(self.request('POST',self.base,{**body,**changes})[0],400)
        value=self.create_http();self.assertTrue(self.request('POST',self.base,body)[1]['idempotent_replay'])
        self.assertEqual(self.request('POST',self.base,{**body,'valid_for_seconds':600})[0],409)
        path=self.base+'/'+value['sync_id']+'/cancel';payload={'expected_snapshot_sha256':value['snapshot_sha256']}
        self.assertEqual(self.request('POST',path,{'expected_snapshot_sha256':'f'*64})[0],409)
        cancelled=self.request('POST',path,payload)[1];self.assertEqual(cancelled['status'],'cancelled');self.assertEqual(self.request('POST',path,payload)[1],cancelled)
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.read_wire,[])
    def test_scoped_bounded_pages_reject_foreign_ids_cursors_and_query_fields(self):
        for i in range(3):
            value=self.create_http(request_key='explicit-http-analytics-page-'+str(i));self.request('POST',self.base+'/'+value['sync_id']+'/cancel',{'expected_snapshot_sha256':value['snapshot_sha256']})
        first=self.request('GET',self.base+'?limit=2')[1];self.assertEqual(len(first['items']),2);self.assertTrue(first['truncated'])
        self.assertEqual(len(self.request('GET',self.base+'?limit=2&cursor='+first['next_cursor'])[1]['items']),1)
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?publication=npub_'+'a'*32,'?token=NEVER'):
            self.assertEqual(self.request('GET',self.base+query)[0],400)
        other=self.server.store.create('Other analytics fixture','', 'media');foreign='/api/projects/'+other['id']+'/official-analytics'
        self.assertEqual(self.request('GET',foreign+'/'+value['sync_id'])[0],404)
        self.assertEqual(self.request('GET',foreign+'?cursor='+first['next_cursor'])[0],400);self.assertEqual(self.read_wire,[])
    def test_known_backoff_survives_runner_calls_without_early_reads(self):
        self.read_mode='rate-limit';value=self.create_http(max_attempts=2,acknowledged_bounded_retries=True)
        self.assertTrue(self.server.runner.run_one());done=self.request('GET',self.base+'/'+value['sync_id'])[1]
        self.assertEqual(done['status'],'retry_scheduled');self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.read_wire),1)
        self.clock[0]+=timedelta(seconds=45);self.read_mode=None;self.assertTrue(self.server.runner.run_one())
        self.assertEqual(self.request('GET',self.base+'/'+value['sync_id'])[1]['status'],'succeeded');self.assertEqual(len(self.read_wire),4)
    def test_default_disabled_runtime_never_consumes_queued_read_consent(self):
        value=self.create_http()
        with LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access) as disabled:
            self.assertFalse(disabled.official_analytics.states()['enabled']);self.assertFalse(disabled.runner.run_one())
            self.assertEqual(disabled.official_analytics.get(self.project['id'],value['sync_id'])['status'],'queued')
        self.assertEqual(self.read_wire,[])
    def test_unsafe_enablement_and_nonmock_injection_are_refused_before_socket(self):
        real=AccountFactory(self.reader.account,self.root,self.workspace,owner_read_enabled=True,resolver=lambda _:self.read_credential)
        options=({'official_analytics_enabled':1},{'official_analytics_enabled':True},{'official_analytics_enabled':True,'access':self.server.access},
            {'official_analytics_enabled':True,'access':self.server.access,'official_account_factories':{real.account.account_ref:real}})
        for values in options:
            with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('Unsafe socket must not be allocated')):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,**values)
        self.assertEqual(self.read_wire,[])
    def test_invalid_protected_registry_is_refused_before_socket_and_token_read(self):
        path=self.folder/'invalid-read-registry.json';path.write_text('{"version":1,"version":1}',encoding='utf-8')
        with (patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('Invalid registry must not allocate socket')),
            patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('No startup token read'))):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access,
                official_account_registry=path,official_account_read_enabled=True,official_analytics_enabled=True)
        self.assertEqual(self.read_wire,[])
    def test_runner_startup_recovers_owned_analytics_before_thread_start_without_reads(self):
        events=[]
        with (patch.object(self.server.store,'recover',side_effect=lambda:events.append('store')),patch.object(self.server.official_accounts,'recover',side_effect=lambda:events.append('account')),
            patch.object(self.server.official_publish_worker,'recover',side_effect=lambda:events.append('publication')),patch.object(self.server.official_publish_queue,'recover',side_effect=lambda:events.append('queue')),
            patch.object(self.analytics,'recover',side_effect=lambda:events.append('analytics')),patch.object(self.server.runner.thread,'start',side_effect=lambda:events.append('thread'))):
            self.server.runner.start()
        self.assertEqual(events,['store','account','publication','queue','analytics','thread']);self.assertEqual(self.read_wire,[])

if __name__=='__main__':unittest.main()
