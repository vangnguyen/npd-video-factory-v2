"""Actual protected runtime and signed HTTP over explicit nonplayable protocol fixtures."""
import json,threading,unittest
from datetime import timedelta
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests.test_tiktok_analytics import TikTokAnalyticsFixture,POST,OTHER
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer,Handler
from services.windows_native.contracts import digest
from services.windows_native.observability import Observer

class TikTokAnalyticsHTTPTests(TikTokAnalyticsFixture,unittest.TestCase):
    request_http=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        super().setUp();c=self.c;self.pipeline=NoProviderPipeline();self.records=[]
        self.config=Config(data_root=c.root,runtime_root=c.folder/'runtime',secret_file=c.folder/'private'/'absent.env',assemblyai_secret_file=c.folder/'private'/'absent.dpapi',ffmpeg_bin=c.folder/'absent-ffmpeg')
        self.access=NativeAccess(c.verifier,c.workspace)
        with patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('No startup token read')):
            self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.access,
                official_account_factories={self.reader.account.account_ref:self.reader},official_analytics_enabled=True,
                official_analytics_refresh_enabled=True,observer=Observer(self.records.append))
        self.cookie,session=self.access.login(c.raw);self.csrf=session.csrf
        self.analytics=self.server.official_analytics;self.refresh=self.server.official_analytics_refresh
        self.base='/api/projects/'+self.project['id']+'/official-analytics';self.plan_base=self.base+'-refresh'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)
        self.assertEqual(self.pipeline.calls,0);super().tearDown()
    def call(self,method,path,body=None,**kw):return self.request_http(method,path,body,**kw)
    def create_http(self,**changes):
        status,value,_=self.call('POST',self.base,self.request(**changes).model_dump(mode='json'));self.assertEqual(status,200,value);return value
    def test_current_runtime_route_and_worker_use_exact_cumulative_binding_and_provider_log(self):
        for path,marker in [('/native-platform-analytics.mjs','analyticsCounterResult'),('/native-official-analytics.mjs','ID bài đăng thực có'),('/native-official-refresh.mjs','Bộ đếm TikTok')]:
            status,body,_=self.call('GET',path);self.assertEqual(status,200);self.assertIn(marker,body.decode('utf-8'))
        status,caps,_=self.call('GET','/api/connections/official-analytics');self.assertEqual(status,200);self.assertEqual(caps['supported_platforms'],['youtube','tiktok']);self.assertFalse(caps['publishing_enabled'])
        status,source,_=self.call('GET',self.base+'/source/'+self.completed['publication_id']);self.assertEqual(status,200,source)
        self.assertIsNone(source['remote_post_id']);self.assertEqual(source['remote_post_ids'],[POST,OTHER]);self.assertEqual(self.wires,[])
        value=self.create_http();self.assertEqual(self.wires,[]);self.assertTrue(self.server.runner.run_one())
        status,done,headers=self.call('GET',self.base+'/'+value['sync_id']);self.assertEqual(status,200);self.assertEqual(done['status'],'succeeded',done)
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(len(self.wires),2)
        logs=[json.loads(x) for x in self.records if json.loads(x)['stage']=='official_analytics_read'];self.assertEqual(len(logs),1);self.assertEqual(logs[0]['provider'],'tiktok-video-insights-api')
        self.assertNotIn(self.token,json.dumps(self.records));self.assertEqual(self.server.store.get(self.project['id']),self.store.get(self.project['id']))
        events=[e for e in self.server.bridge.page(limit=100)['items'] if e['envelope']['payload'].get('source_type')=='analytics']
        self.assertEqual(len(events),1);event=events[0];self.assertEqual(event['envelope']['event_type'],'video.analytics.updated')
        self.server.bridge.sources.validate(event['envelope']);self.assertTrue(event['envelope']['payload']['mock'])
        self.assertFalse(event['envelope']['payload']['real_audience_observation']);self.assertFalse(event['envelope']['payload']['automatic_application'])
        self.assertEqual(event['delivery']['status'],'disabled');self.assertIsNone(self.server.bridge.process());self.assertEqual(len(self.wires),2)
    def test_scope_unknown_versions_dates_and_provider_job_inputs_fail_without_read(self):
        body=self.request().model_dump(mode='json')
        for change in [{'schema_version':'unknown'},{'schema_version':'native-official-analytics-request-v1'},{'query':{'start_date':'2026-10-01','end_date':'2026-10-07'}},
                       {'remote_post_id':self.completed['receipt']['provider_job_id']},{'remote_post_id':'7391000000000000003'},{'token':'EXPLICIT_INVALID_INPUT'}]:
            self.assertIn(self.call('POST',self.base,body|change)[0],[400,409])
        value=self.create_http();other=self.server.store.create('Foreign owned fixture','No providers')
        self.assertEqual(self.call('GET','/api/projects/'+other['id']+'/official-analytics/'+value['sync_id'])[0],404);self.assertEqual(self.wires,[])
    def test_role_and_csrf_guards_apply_before_body_to_counter_and_plan_routes(self):
        original=self.server.access
        for role in ['viewer','reviewer','editor']:
            raw,data=human_fixture(role,workspace=self.c.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.c.workspace)
            access.bind_root(self.c.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
            with patch.object(Handler,'read_body',side_effect=AssertionError('No forbidden body read')):
                self.assertEqual(self.call('POST',self.base,{})[0],403);self.assertEqual(self.call('POST',self.plan_base,{})[0],403)
        self.server.access=original;self.cookie,session=original.login(self.c.raw);self.csrf=session.csrf
        with patch.object(Handler,'read_body',side_effect=AssertionError('No CSRF-less body read')):self.assertEqual(self.call('POST',self.base,{},headers={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.wires,[])
    def test_counter_finite_plan_is_local_separate_and_cancellation_keeps_original_request(self):
        start=self.analytics.clock()+timedelta(seconds=2)
        request=self.plan_request(start_at=start,deadline=start+timedelta(seconds=600),remote_post_id=OTHER).model_dump(mode='json')
        status,plan,_=self.call('POST',self.plan_base,request);self.assertEqual(status,200,plan);self.assertEqual(plan['schema_version'],'native-official-analytics-refresh-plan-v2')
        self.assertEqual(plan['policy']['source']['remote_post_id'],OTHER);self.assertEqual(self.wires,[])
        status,stopped,_=self.call('POST',self.plan_base+'/'+plan['plan_id']+'/cancel',{'expected_policy_sha256':plan['policy_sha256'],'expected_version':plan['version'],'cancel_pending_read':True})
        self.assertEqual(status,200,stopped);self.assertEqual(stopped['status'],'cancelled');self.assertEqual(stopped['policy'],plan['policy']);self.assertEqual(self.wires,[])
    def test_cold_runtime_keeps_completed_counter_history_without_keys_replay_or_publish(self):
        value=self.create_http();self.server.runner.run_one();done=self.call('GET',self.base+'/'+value['sync_id'])[1];count=len(self.wires)
        with patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('No cold token read')):
            cold=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.access)
            try:
                self.assertFalse(cold.official_analytics.enabled);self.assertFalse(cold.official_analytics_refresh.enabled);self.assertFalse(cold.official_publish_queue.enabled)
                self.assertEqual(cold.official_analytics.get(self.project['id'],value['sync_id']),done);self.assertFalse(cold.runner.run_one())
            finally:cold.server_close()
        self.assertEqual(len(self.wires),count)
