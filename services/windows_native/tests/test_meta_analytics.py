"""Owned Native Meta publication/read protocol fixtures; no audience/Owner claim."""
import copy,json,unittest
from datetime import timedelta
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app import analytics_meta
from services.windows_native.tests import test_meta_publish_worker as publisher_fixture
from services.windows_native.official_account_registry import AccountFactory,MetaReadAccount,Registry
from services.windows_native.official_account_tokens import MetaAccessToken,save,load,parse_token,META_PREFIX,PREFIX
from services.windows_native.official_analytics import NativeOfficialAnalytics
from services.windows_native.official_analytics_models import MetaCollect,CounterCollect,parse_collect
from services.windows_native.official_analytics_refresh import NativeOfficialAnalyticsRefresh,MetaRefreshCreate,parse_refresh
from services.windows_native.official_accounts import Verify
from services.windows_native.contracts import WorkflowError,digest


class NativeMetaAnalyticsTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):
        self.publisher=publisher_fixture.MetaPublishWorkerTests('test_exact_original_video_one_async_job_phase_order_nullable_costs_and_private_history')
        self.publisher.PLATFORM=self.PLATFORM;self.publisher.setUp();self.c=self.publisher.c
        self.completed=self.publisher.complete();self.project=self.c.project;self.store=self.c.store
        self.target=self.c.connection.profile.target;self.remote=self.completed['receipt']['remote_post_id']
        self.calls=[];self.mode=None;self.views=123
        self.account=MetaReadAccount(account_ref=self.c.connection.account.account_ref,target=self.target,
            credential_alias='explicit-meta-analytics-read',token_file=str(self.c.folder/'private'/'missing-meta-analytics.token'),
            api_version=self.c.connection.profile.api_version,page_id=self.c.connection.profile.page_id,read_enabled=True)
        self.credential=analytics_meta.MetaAnalyticsCredential(self.target,self.account.api_version,self.account.page_id,
            self.c.clock[0]+timedelta(hours=1),analytics_meta.REQUIRED_SCOPES[self.PLATFORM],
            'EXPLICIT-META-ANALYTICS-FIXTURE-NOT-A-SECRET')
        self.factory=AccountFactory(self.account,self.c.root,self.c.workspace,owner_read_enabled=True,
            transport=httpx.MockTransport(self.receive),resolver=lambda _:self.credential)
        self.publisher.service.accounts.factories[self.account.account_ref]=self.factory
        self.analytics=NativeOfficialAnalytics(self.publisher.service,enabled=True)
    def tearDown(self):self.publisher.tearDown()
    def receive(self,request):
        self.calls.append((request.method,request.url.path))
        if self.mode=='rate-limit':return httpx.Response(429,headers={'Retry-After':'45'},json={'error':{'message':'PRIVATE TOKEN'}})
        if request.url.path.endswith('/me'):
            data={'id':self.account.page_id}
            if self.PLATFORM=='instagram_reels':data['instagram_business_account']={'id':self.target.target_account_id}
            if self.mode=='foreign-account':data['id']='99999'
        elif dict(request.url.params).get('fields') in ('id,owner,media_product_type','id,from'):
            data={'id':self.remote,'owner':{'id':self.target.target_account_id},'media_product_type':'REELS'} if self.PLATFORM=='instagram_reels' else {'id':self.remote,'from':{'id':self.target.target_account_id}}
            if self.mode=='foreign-media':data['id']='99999'
        elif self.PLATFORM=='instagram_reels':
            data={'data':[{'id':f'{self.remote}/insights/{name}/lifetime','name':name,'period':'lifetime',
                'values':[{'value':value}]} for name,value in {'views':self.views,'reach':100,'likes':4,'comments':0,'shares':2,'saved':3}.items()]}
            if self.mode=='empty':data={'data':[]}
        else:
            data={'id':self.remote,'from':{'id':self.target.target_account_id},'views':self.views,
                'likes':{'data':[],'summary':{'total_count':4}},'comments':{'data':[],'summary':{'total_count':0}}}
            if self.mode=='empty':data={'id':self.remote,'from':{'id':self.target.target_account_id}}
        return httpx.Response(200,json=data)
    def request(self,**changes):
        return MetaCollect(**{'publication_id':self.completed['publication_id'],
            'expected_publication_snapshot_sha256':self.completed['snapshot_sha256'],
            'expected_receipt_sha256':digest(self.completed['receipt']),'account_ref':self.account.account_ref,
            'expected_configuration_sha256':self.factory.sha256,'platform':self.PLATFORM,'query':None,
            'remote_post_id':self.remote,'metric_scope':'lifetime_media_insights' if self.PLATFORM=='instagram_reels' else 'cumulative_video_node_counters',
            'acknowledged_read_only':True,'acknowledged_protocol_mock':True,'request_key':'explicit-native-meta-read-fixture',**changes})
    def collect(self,**changes):return self.analytics.create(self.project['id'],self.request(**changes),principal=self.c.principal)[0]
    def run_collection(self,**changes):
        value=self.collect(**changes);result=self.analytics.process()
        self.assertIsNotNone(result);self.assertEqual(result['sync_id'],value['sync_id']);return result

    def test_scoped_meta_collection_keeps_null_timing_costs_and_protocol_mock_labels(self):
        before=self.store.get(self.project['id']);value=self.run_collection()
        self.assertEqual(value['status'],'succeeded',value['failure_code']);result=value['result']
        self.assertEqual(result['schema_version'],'native-official-analytics-snapshot-v3')
        self.assertEqual(result['metrics']['views'],123);self.assertIsNone(result['publishing_time'])
        self.assertIsNone(result['metrics']['watch_time']);self.assertIsNone(result['metrics']['revenue'])
        self.assertEqual(result['source_kind'],'official_protocol_mock');self.assertFalse(result['real_audience_observation'])
        self.assertEqual(len(self.calls),3);self.assertTrue(all(method=='GET' for method,_ in self.calls))
        self.assertEqual(before,self.store.get(self.project['id']));self.assertNotIn(self.credential.token,json.dumps(value))
        costs=[v for v in self.analytics.costs.summary(self.project['id'])['records'] if v['provider']=='official-'+self.PLATFORM+'-analytics']
        self.assertEqual(len(costs),3);self.assertTrue(all(v['actual_cost'] is None and not v['paid'] and not v['external_call'] for v in costs))
        self.assertEqual(value['snapshot']['meta_read_profile'],self.account.public_profile())

    def test_refresh_and_exact_replay_preserve_immutable_history(self):
        first=self.run_collection();same,replay=self.analytics.create(self.project['id'],self.request(),principal=self.c.principal)
        self.assertTrue(replay);self.assertEqual(same['sync_id'],first['sync_id']);self.assertIsNone(self.analytics.process())
        self.views=250;second=self.run_collection(request_key='explicit-native-meta-read-second')
        self.assertNotEqual(first['result_snapshot_id'],second['result_snapshot_id'])
        self.assertEqual(self.analytics.get(self.project['id'],first['sync_id'])['result'],first['result'])
        self.assertEqual(second['result']['metrics']['views'],250)
        self.publisher.service.accounts.factories.clear();restored=NativeOfficialAnalytics(self.publisher.service)
        self.assertEqual(restored.get(self.project['id'],first['sync_id'])['result'],first['result'])
        self.assertEqual(len(self.calls),6)

    def test_foreign_account_or_media_cannot_reach_metrics(self):
        for mode,expected in [('foreign-account',1),('foreign-media',2)]:
            self.mode=mode;start=len(self.calls);value=self.run_collection(request_key='explicit-meta-'+mode)
            self.assertEqual(value['status'],'failed');self.assertIsNone(value['result'])
            self.assertEqual(len(self.calls)-start,expected)

    def test_missing_metrics_are_null_and_no_observation_window_is_inferred(self):
        self.mode='empty';value=self.run_collection();self.assertEqual(value['status'],'succeeded',value['failure_code'])
        self.assertTrue(all(v is None for v in value['result']['metrics'].values()))
        self.assertIsNone(value['result']['evidence']['query']);self.assertIsNone(value['result']['evidence']['observed_window_hours'])

    def test_receipt_wrong_post_stale_configuration_and_unknown_versions_stop_before_wire(self):
        for changes in ({'remote_post_id':'99999'},{'expected_receipt_sha256':'f'*64},{'expected_configuration_sha256':'f'*64}):
            with self.subTest(changes=changes),self.assertRaises(WorkflowError):self.collect(**changes)
        self.assertEqual(self.calls,[])
        with self.assertRaises(ValueError):parse_collect({**self.request().model_dump(),'schema_version':'native-official-analytics-request-v99'})
        with self.assertRaises(ValidationError):self.request(query={'start_date':'2026-10-01','end_date':'2026-10-07'})
        with self.assertRaises(ValidationError):self.request(metric_scope='cumulative_video_counters')
        self.assertEqual(parse_collect(self.request(remote_post_id='1'*32).model_dump()).remote_post_id,'1'*32)

    def test_default_disabled_and_missing_read_token_are_not_configured_without_decrypt(self):
        self.analytics=NativeOfficialAnalytics(self.publisher.service)
        value=self.collect();self.assertEqual(value['status'],'not_configured');self.assertIsNone(self.analytics.process())
        self.assertEqual(self.calls,[])
        self.factory=AccountFactory(self.account,self.c.root,self.c.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.receive))
        self.publisher.service.accounts.factories[self.account.account_ref]=self.factory
        self.analytics=NativeOfficialAnalytics(self.publisher.service,enabled=True)
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No startup decryption')):
            value=self.collect(request_key='explicit-meta-read-unconfigured');self.assertEqual(value['status'],'not_configured')
        self.assertEqual(self.calls,[])

    def test_meta_read_token_uses_separate_cipher_purpose_and_exact_profile(self):
        path=self.c.folder/'private'/'explicit-meta-analytics.token'
        token=MetaAccessToken(workspace_id=self.c.workspace,credential_alias=self.account.credential_alias,
            credential_binding_sha256=self.target.credential_binding_sha256,platform=self.PLATFORM,
            api_version=self.account.api_version,page_id=self.account.page_id,expires_at=self.credential.expires_at,
            scopes=list(self.credential.scopes),token=self.credential.token)
        receipt=save(path,self.c.root,token);self.assertFalse(receipt['token_returned'])
        self.assertTrue(path.read_bytes().startswith(META_PREFIX));self.assertFalse(path.read_bytes().startswith(PREFIX))
        self.assertEqual(load(path,self.c.root,self.target,self.account.credential_alias,api_version=self.account.api_version,page_id=self.account.page_id),self.credential)
        with self.assertRaises(WorkflowError):load(path,self.c.root,self.target,self.account.credential_alias,api_version='v999.0',page_id=self.account.page_id)
        with self.assertRaises(ValueError):parse_token({**token.model_dump(),'schema_version':'native-oauth-access-token-v1'})
        with self.assertRaises(ValidationError):MetaAccessToken.model_validate({**token.model_dump(),'scopes':['pages_manage_posts']})

    def refresh_request(self,**changes):
        body=self.request().model_dump(mode='python')
        body.update(schema_version='native-official-analytics-refresh-request-v3',acknowledged_background_reads=True,
            max_runs=2,interval_seconds=60,start_at=self.c.clock[0],deadline=self.c.clock[0]+timedelta(minutes=10),
            request_key='explicit-native-meta-refresh-fixture')
        body.update(changes)
        return MetaRefreshCreate.model_validate(body)

    def test_meta_finite_refresh_keeps_both_snapshots_and_never_renews_consent(self):
        refresh=NativeOfficialAnalyticsRefresh(self.analytics,enabled=True)
        plan,replay=refresh.create(self.project['id'],self.refresh_request(),principal=self.c.principal)
        self.assertFalse(replay);self.assertEqual(plan['schema_version'],'native-official-analytics-refresh-plan-v3')
        self.assertIsNotNone(refresh.tick());first=self.analytics.process();self.assertEqual(first['status'],'succeeded',first['failure_code'])
        refresh.tick();self.c.clock[0]+=timedelta(seconds=60);self.views=250
        self.assertIsNotNone(refresh.tick());second=self.analytics.process();self.assertEqual(second['status'],'succeeded',second['failure_code'])
        refresh.tick();done=refresh.get(self.project['id'],plan['plan_id'])
        self.assertEqual(done['status'],'completed');self.assertEqual(done['run_count'],2)
        self.assertEqual(len(done['occurrences']),2);self.assertFalse(done['automatic_consent_renewal'])
        self.assertNotEqual(first['result_snapshot_id'],second['result_snapshot_id']);self.assertEqual(len(self.calls),6)
        self.assertIsNone(refresh.tick());self.assertEqual(len(self.calls),6)
        self.assertEqual(self.analytics.get(self.project['id'],first['sync_id'])['result'],first['result'])

    def test_meta_refresh_requires_separate_bounded_consent_and_stays_default_off(self):
        request=self.refresh_request()
        with self.assertRaises(ValidationError):self.refresh_request(acknowledged_background_reads=False)
        with self.assertRaises(ValidationError):self.refresh_request(max_runs=101)
        with self.assertRaises(ValueError):parse_refresh({**request.model_dump(),'schema_version':'native-official-analytics-refresh-request-v99'})
        refresh=NativeOfficialAnalyticsRefresh(self.analytics)
        plan,_=refresh.create(self.project['id'],request,principal=self.c.principal)
        self.assertEqual(plan['status'],'not_configured');self.assertIsNone(refresh.tick());self.assertEqual(self.calls,[])

    def test_read_account_verification_uses_v2_profile_and_keeps_legacy_publishing_evidence_separate(self):
        accounts=self.publisher.service.accounts
        value,_=accounts.create(self.project['id'],self.account.account_ref,Verify(revision=self.project['revision'],
            expected_configuration_sha256=self.factory.sha256,acknowledged_read_only=True,
            request_key='explicit-meta-read-account-check'),actor=self.c.principal.token_id)
        self.assertEqual(value['schema_version'],'native-official-account-check-v2')
        self.assertEqual(value['snapshot']['meta_read_profile'],self.account.public_profile())
        done=accounts.process();self.assertEqual(done['status'],'succeeded',done['failure_code'])
        self.assertEqual(done['result']['schema_version'],'native-official-account-check-result-v2')
        self.assertEqual(len(self.calls),1);self.assertFalse(done['result']['publishing_enabled'])


class NativeFacebookAnalyticsTests(NativeMetaAnalyticsTests):
    PLATFORM='facebook'
