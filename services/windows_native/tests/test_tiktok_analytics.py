"""Real owned SQLite/DPAPI and protocol mocks; no audience/provider/Owner acceptance."""
import copy,json,unittest,uuid
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.analytics_official import AnalyticsOAuthCredential
from services.windows_native.tests import test_tiktok_publish_worker as worker_fixture
from services.windows_native.tests import test_tiktok_creators as creator_fixture
from services.windows_native.tests.test_publications import render_fixture
from services.windows_native.channel_profiles import select
from services.windows_native.official_account_registry import Account,AccountFactory
from services.windows_native.official_account_tokens import save
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_analytics_models import CounterCollect,Cancel,parse_collect
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh,CounterRefreshCreate,RefreshCancel
from services.windows_native.contracts import WorkflowError,digest

POST='7391000000000000001'
OTHER='7391000000000000002'

class TikTokAnalyticsFixture:
    def setUp(self):
        self.pub=worker_fixture.TikTokPublishWorkerTests('test_public_moderation_wait_then_single_actual_post_id')
        def configured_render(store,**kwargs):
            project=store.create('EXPLICIT MOCK TIKTOK ANALYTICS TECH PROFILE','','media',channel_profile=select('ai-education-reference@1'))
            return render_fixture(store,project=project,**kwargs)
        with patch.object(creator_fixture,'render_fixture',side_effect=configured_render):self.pub.setUp()
        self.pub.step();self.pub.step();self.pub.status='PUBLISH_COMPLETE';self.pub.ids=[int(POST),int(OTHER)]
        self.completed=self.pub.poll();self.c=self.pub.c;self.store=self.c.store;self.project=self.c.project
        self.wires=[];self.mode=None;self.counts={'view_count':0,'like_count':3,'comment_count':1,'share_count':0}
        path=self.c.folder/'private'/'analytics-read.dpapi';self.token='EXPLICIT-TIKTOK-ANALYTICS-READ-FIXTURE-0123456789'
        save(path,self.c.root,{'workspace_id':self.c.workspace,'credential_alias':'tiktok-analytics-fixture',
            'credential_binding_sha256':self.c.target.credential_binding_sha256,'platform':'tiktok',
            'expires_at':(self.c.clock[0]+timedelta(hours=1)).isoformat(),'scopes':['user.info.basic','video.list'],'token':self.token})
        self.reader=AccountFactory(Account(account_ref='npac_'+uuid.uuid4().hex,target=self.c.target,credential_alias='tiktok-analytics-fixture',token_file=str(path),read_enabled=True),
            self.c.root,self.c.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.response))
        self.c.official.accounts.factories[self.reader.account.account_ref]=self.reader
        self.analytics=NativeOfficialAnalytics(self.c.official,enabled=True)
        self.refresh=NativeOfficialAnalyticsRefresh(self.analytics,enabled=True)
    def tearDown(self):self.pub.tearDown()
    def response(self,request):
        self.assertEqual(request.headers['authorization'],'Bearer '+self.token)
        self.wires.append({'method':request.method,'path':request.url.path})
        if self.mode=='timeout':raise httpx.ReadTimeout('EXPLICIT-PRIVATE-ERROR',request=request)
        if self.mode=='rate-limit':return httpx.Response(429,headers={'retry-after':'45'})
        if self.mode=='expire':self.c.clock[0]+=timedelta(seconds=901)
        if request.url.path=='/v2/user/info/':
            self.assertEqual(request.method,'GET');self.assertEqual(request.url.params['fields'],'open_id')
            return httpx.Response(200,json={'data':{'user':{'open_id':'FOREIGN' if self.mode=='foreign-account' else self.c.target.target_account_id}},'error':{'code':'ok'}})
        self.assertEqual(request.url.path,'/v2/video/query/');self.assertEqual(request.method,'POST')
        remote=json.loads(request.content)['filters']['video_ids'];self.assertEqual(len(remote),1);self.assertIn(remote[0],[POST,OTHER])
        videos=[] if self.mode=='empty' else [{'id':'7391000000000000003' if self.mode=='foreign-video' else remote[0],**self.counts}]
        return httpx.Response(200,json={'data':{'videos':videos},'error':{'code':'ok'}})
    def request(self,**changes):
        return CounterCollect.model_validate({'publication_id':self.completed['publication_id'],'expected_publication_snapshot_sha256':self.completed['snapshot_sha256'],
            'expected_receipt_sha256':digest(self.completed['receipt']),'account_ref':self.reader.account.account_ref,
            'expected_configuration_sha256':self.reader.sha256,'query':None,'metric_scope':'cumulative_video_counters','remote_post_id':POST,
            'acknowledged_read_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-tiktok-analytics-fixture-key',**changes})
    def collect(self,**changes):return self.analytics.create(self.project['id'],self.request(**changes),principal=self.c.principal)[0]
    def run_collection(self,**changes):self.sync=self.collect(**changes);return self.analytics.process()
    def plan_request(self,**changes):
        body=self.request().model_dump(mode='json');body.update(schema_version='native-official-analytics-refresh-request-v2',acknowledged_background_reads=True,
            max_runs=2,interval_seconds=60,start_at=self.c.clock[0],deadline=self.c.clock[0]+timedelta(seconds=600),request_key='explicit-tiktok-finite-refresh-fixture-key')
        body.update(changes)
        return CounterRefreshCreate.model_validate(body)

class TikTokAnalyticsTests(TikTokAnalyticsFixture,unittest.TestCase):
    def test_exact_selected_actual_post_two_reads_zero_nulls_cost_and_source_unchanged(self):
        before=self.store.get(self.project['id']);done=self.run_collection();self.assertEqual(done['status'],'succeeded',done)
        self.assertEqual(done['schema_version'],'native-official-analytics-sync-v2');r=done['result']
        self.assertEqual(r['remote_post_id'],POST);self.assertEqual(r['platform'],'tiktok');self.assertEqual(r['provider_key'],'tiktok-video-insights-api')
        self.assertEqual(r['metrics']['views'],0);self.assertEqual(r['metrics']['likes'],3)
        self.assertTrue(all(v is None for k,v in r['metrics'].items() if k not in {'views','likes','comments','shares'}))
        self.assertIsNone(r['evidence']['query']);self.assertTrue(r['evidence']['owned_video_returned']);self.assertFalse(r['real_audience_observation'])
        self.assertEqual(len(r['response_refs']),2);self.assertEqual([w['path'] for w in self.wires],['/v2/user/info/','/v2/video/query/'])
        costs=[x for x in self.analytics.costs.summary(self.project['id'])['records'] if x['provider']=='official-tiktok-analytics'];self.assertEqual(len(costs),2)
        self.assertTrue(all(x['status']=='response_received' and x['actual_cost'] is None and not x['paid'] and not x['external_call'] for x in costs))
        self.assertNotIn(self.token,json.dumps(done));self.assertEqual(before,self.store.get(self.project['id']))
    def test_each_actual_post_is_explicit_and_history_deduplicates_no_provider_job_substitution(self):
        first=self.run_collection();second=self.run_collection(remote_post_id=OTHER,request_key='explicit-second-tiktok-post-fixture-key')
        self.assertEqual(second['result']['remote_post_id'],OTHER);self.assertEqual(self.analytics.get(self.project['id'],first['sync_id'])['result'],first['result'])
        with self.assertRaisesRegex(WorkflowError,'ACTUAL_RECEIPT_POST_REQUIRED'):self.collect(remote_post_id='7391000000000000003',request_key='explicit-foreign-actual-post-key')
        with self.assertRaises(ValidationError):self.request(remote_post_id=self.completed['receipt']['provider_job_id'])
        replay,flag=self.analytics.create(self.project['id'],self.request(),principal=self.c.principal);self.assertTrue(flag);self.assertEqual(replay['sync_id'],first['sync_id']);self.assertIsNone(self.analytics.process())
        self.assertEqual(len(self.wires),4)
    def test_counter_query_scope_versions_and_raw_types_are_closed(self):
        for changes in [{'query':{'start_date':'2026-10-01','end_date':'2026-10-07'}},{'metric_scope':'date_report'},{'remote_post_id':int(POST)},
                        {'remote_post_id':str(2**63)},{'acknowledged_read_only':1},{'schema_version':'native-official-analytics-request-v1'}]:
            with self.subTest(changes=changes),self.assertRaises((ValidationError,ValueError)):self.request(**changes)
        with self.assertRaises(ValueError):parse_collect({**self.request().model_dump(mode='json'),'schema_version':'unknown'})
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.analytics.create(self.project['id'],self.request().model_copy(update={'query':{}}),principal=self.c.principal)
        with self.assertRaisesRegex(WorkflowError,'FIELDS_INVALID'):self.analytics.create(self.project['id'],self.request().model_copy(update={'schema_version':'unknown'}),principal=self.c.principal)
        self.assertEqual(self.wires,[])
    def test_empty_and_missing_provider_values_stay_null_without_owned_video_claim(self):
        self.mode='empty';first=self.run_collection();self.assertTrue(all(v is None for v in first['result']['metrics'].values()));self.assertFalse(first['result']['evidence']['owned_video_returned'])
        self.mode=None;self.counts={};second=self.run_collection(request_key='explicit-tiktok-missing-fields-key');self.assertTrue(all(v is None for v in second['result']['metrics'].values()));self.assertTrue(second['result']['evidence']['owned_video_returned'])
    def test_foreign_account_and_video_reject_before_accepting_snapshot(self):
        self.mode='foreign-account';first=self.run_collection();self.assertEqual(first['status'],'failed');self.assertIsNone(first['result']);self.assertEqual(len(self.wires),1)
        self.mode='foreign-video';second=self.run_collection(request_key='explicit-tiktok-foreign-video-key');self.assertEqual(second['status'],'failed');self.assertIsNone(second['result']);self.assertEqual(len(self.wires),3)
    def test_finite_backoff_and_unknown_outcome_never_renew_or_auto_replay(self):
        self.mode='rate-limit';self.sync=self.collect(max_attempts=2,acknowledged_bounded_retries=True);first=self.analytics.process();self.assertEqual(first['status'],'retry_scheduled')
        self.assertIsNone(self.analytics.process());self.c.clock[0]+=timedelta(seconds=46);self.mode=None;done=self.analytics.process();self.assertEqual(done['status'],'succeeded');self.assertEqual(done['attempts'],2)
        self.mode='timeout';unknown=self.run_collection(request_key='explicit-tiktok-unknown-read-key');self.assertEqual(unknown['status'],'outcome_unknown');self.assertIsNone(self.analytics.process())
    def test_disabled_cold_history_needs_no_factories_or_token_and_keeps_all_proofs(self):
        done=self.run_collection();self.c.official.accounts.factories={};cold=NativeOfficialAnalytics(self.c.official)
        with patch('services.windows_native.official_account_registry.token_load',side_effect=AssertionError('No cold private read')):
            self.assertEqual(cold.get(self.project['id'],done['sync_id']),done);self.assertIsNone(cold.process());self.assertEqual(cold.states()['supported_platforms'],['youtube','tiktok'])
        self.assertEqual(len(self.wires),2)
    def test_finite_refresh_retains_selected_post_and_two_immutable_counter_snapshots(self):
        plan,replay=self.refresh.create(self.project['id'],self.plan_request(remote_post_id=OTHER),principal=self.c.principal);self.assertFalse(replay)
        self.assertEqual(plan['schema_version'],'native-official-analytics-refresh-plan-v2');self.assertEqual(self.wires,[])
        admitted=self.refresh.tick();self.assertEqual(admitted['occurrences'][0]['schema_version'],'native-official-analytics-refresh-occurrence-v2')
        first=self.analytics.process();self.counts['view_count']=8;self.c.clock[0]+=timedelta(seconds=61);self.refresh.tick();second=self.analytics.process();done=self.refresh.tick()
        self.assertEqual(done['status'],'completed');self.assertEqual(done['run_count'],2);self.assertEqual(len(self.wires),4)
        self.assertEqual(first['result']['remote_post_id'],OTHER);self.assertEqual(second['result']['metrics']['views'],8);self.assertEqual(done['occurrences'][0]['sync']['result']['metrics']['views'],0)
        self.assertIsNone(self.refresh.tick());self.assertIsNone(self.analytics.process())
    def test_rehashed_counter_semantics_or_cost_history_cannot_fabricate_retention(self):
        done=self.run_collection();original=done['result']
        for change in [{'metrics':{**original['metrics'],'completion_rate':0.9}},{'evidence':{**original['evidence'],'query':{'start_date':'2026-10-01'}}},{'platform':'youtube'}]:
            result={**copy.deepcopy(original),**change}
            with self.store.transaction() as con:con.execute('UPDATE native_official_analytics_snapshots SET result_json=?,result_sha256=? WHERE result_snapshot_id=?',(json.dumps(result),digest(result),done['result_snapshot_id']))
            with self.assertRaisesRegex(WorkflowError,'RESULT_CHANGED'):self.analytics.get(self.project['id'],done['sync_id'])
        with self.store.transaction() as con:con.execute('UPDATE native_official_analytics_snapshots SET result_json=?,result_sha256=? WHERE result_snapshot_id=?',(json.dumps(original),digest(original),done['result_snapshot_id']))
        with self.store.transaction() as con:con.execute("UPDATE native_cost_operations SET provider='official-youtube-analytics' WHERE provider='official-tiktok-analytics'")
        with self.assertRaisesRegex(WorkflowError,'RESULT_CHANGED'):self.analytics.get(self.project['id'],done['sync_id'])
