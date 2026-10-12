"""Actual localhost signed HTTP/worker path, explicit Meta/identity fixtures."""
import http.client,json,threading,unittest
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_meta_analytics as fixture
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.pipeline import Config
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier


class MetaAnalyticsHTTPTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):
        self.case=fixture.NativeMetaAnalyticsTests('test_scoped_meta_collection_keeps_null_timing_costs_and_protocol_mock_labels')
        self.case.PLATFORM=self.PLATFORM;self.case.setUp();self.c=self.case.c
        config=Config(data_root=self.c.root,runtime_root=self.c.folder/'runtime',secret_file=self.c.folder/'private/absent.env',
            assemblyai_secret_file=self.c.folder/'private/absent-asr.dpapi',ffmpeg_bin=self.c.folder/'absent-ffmpeg')
        self.server=LocalServer(0,config,start_worker=False,access=NativeAccess(self.c.verifier,self.c.workspace),
            official_account_factories={self.case.account.account_ref:self.case.factory},official_analytics_enabled=True,
            official_analytics_refresh_enabled=True)
        self.server.publications.capabilities_path=self.c.publications.capabilities_path
        self.server.publications.capabilities=self.c.publications.capabilities
        self.server.publications.capabilities_sha256=self.c.publications.capabilities_sha256
        self.server.official_publications.clock=lambda:self.c.clock[0]
        self.analytics=NativeOfficialAnalytics(self.server.official_publications,enabled=True)
        self.refresh=NativeOfficialAnalyticsRefresh(self.analytics,enabled=True)
        self.server.official_analytics=self.server.runner.official_analytics=self.analytics
        self.server.official_analytics_refresh=self.server.runner.official_analytics_refresh=self.refresh
        self.server.bridge.bind_qualified_sources(analytics=self.analytics)
        self.cookie,session=self.server.access.login('vf1.explicit-fixture.'+'x'*48);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.case.project['id']+'/official-analytics'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10);self.case.tearDown()
    def request(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=15)
        data=json.dumps(body) if body is not None else None
        base={'Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,'Content-Type':'application/json'}
        try:
            con.request(method,path,data,headers={**base,**(headers or {})});response=con.getresponse();raw=response.read()
            return response.status,json.loads(raw),dict(response.getheaders())
        finally:con.close()
    def actor(self,role):
        raw,registry=human_fixture(role,workspace=self.c.workspace)
        verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        self.server.access=NativeAccess(verifier,self.c.workspace);self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
    def test_signed_queue_actual_worker_and_read_only_source_keep_mock_and_bridge_history(self):
        status,source,_=self.request('GET',self.base+'/source/'+self.case.completed['publication_id'])
        self.assertEqual(status,200,source);self.assertEqual(source['schema_version'],'native-official-analytics-publication-binding-v3')
        before=self.server.store.get(self.case.project['id'])
        status,value,headers=self.request('POST',self.base,self.case.request().model_dump(mode='json'))
        self.assertEqual(status,200,value);self.assertEqual(value['status'],'queued');self.assertEqual(self.case.calls,[])
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertTrue(self.server.runner.run_one())
        status,done,_=self.request('GET',self.base+'/'+value['sync_id'])
        self.assertEqual(status,200,done);self.assertEqual(done['status'],'succeeded',done['failure_code'])
        self.assertEqual(len(self.case.calls),3);self.assertFalse(done['result']['real_audience_observation'])
        self.assertEqual(before,self.server.store.get(self.case.project['id']))
        status,replay,_=self.request('POST',self.base,self.case.request().model_dump(mode='json'))
        self.assertEqual(status,200,replay);self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['result'],done['result'])
        self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.case.calls),3)
    def test_roles_and_csrf_reject_before_body_and_provider_and_viewer_can_read_source(self):
        for role in ('editor','reviewer','viewer'):
            self.actor(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body parsed')):
                self.assertEqual(self.request('POST',self.base,{})[0],403)
            self.assertEqual(self.request('GET',self.base+'/source/'+self.case.completed['publication_id'])[0],200)
            self.assertEqual(self.request('GET','/api/connections/official-analytics')[0],403)
        self.actor('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Invalid CSRF body parsed')):
            self.assertEqual(self.request('POST',self.base,{},headers={'X-VF-CSRF':'invalid'})[0],403)
        self.assertEqual(self.case.calls,[])
    def test_signed_meta_finite_plan_and_default_scope_do_not_authorize_publishing(self):
        body=self.case.refresh_request().model_dump(mode='json')
        status,plan,_=self.request('POST','/api/projects/'+self.case.project['id']+'/official-analytics-refresh',body)
        self.assertEqual(status,200,plan);self.assertEqual(plan['schema_version'],'native-official-analytics-refresh-plan-v3')
        self.assertFalse(plan['publishing_enabled']);self.assertEqual(self.case.calls,[])
        self.assertTrue(self.server.runner.run_one());self.assertFalse(self.server.runner.run_one())
        status,stored,_=self.request('GET','/api/projects/'+self.case.project['id']+'/official-analytics-refresh/'+plan['plan_id'])
        self.assertEqual(status,200,stored);self.assertEqual(stored['run_count'],1)
        self.assertEqual(stored['occurrences'][0]['sync']['status'],'succeeded')
        self.assertEqual(len(self.case.calls),3)
        self.c.clock[0]+=timedelta(seconds=60);self.case.views=250
        self.assertTrue(self.server.runner.run_one());self.assertTrue(self.server.runner.run_one())
        status,finished,_=self.request('GET','/api/projects/'+self.case.project['id']+'/official-analytics-refresh/'+plan['plan_id'])
        self.assertEqual(status,200,finished);self.assertEqual(finished['status'],'completed')
        self.assertEqual(finished['run_count'],2);self.assertEqual(len(self.case.calls),6)
        self.assertFalse(self.server.runner.run_one())


class FacebookAnalyticsHTTPTests(MetaAnalyticsHTTPTests):
    PLATFORM='facebook'
