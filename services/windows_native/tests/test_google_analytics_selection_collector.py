"""Selected synthetic grants through the existing receipt-bound analytics collector."""
import asyncio,json,unittest
from datetime import timedelta
from urllib.parse import urlencode
from unittest.mock import patch
import httpx
from pydantic import ValidationError
from app.analytics_official import AnalyticsHTTPClient,YT_READ,YT_ANALYTICS
from app.google_oauth_protocol import GoogleOAuthTokenClient
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault,PrivateClient
from services.windows_native.google_oauth_operations import NativeGoogleOAuthOperations,Slot,Start,Refresh
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections,Select,Revoke
from services.windows_native.official_account_registry import OAuthAccount,AccountFactory
from services.windows_native.tests.test_official_analytics import OfficialAnalyticsFixture
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE

class SelectedAnalyticsFixture(OfficialAnalyticsFixture):
    def setUp(self):
        super().setUp();self.selection_wire=[];self.token_wire=[];self.final_read_mode=None
        self.oauth_vault=NativeGoogleOAuthVault(self.folder/'private-selected-analytics',self.root,self.workspace)
        receipt=self.oauth_vault.save_client(PrivateClient(target=self.target,purpose='analytics',credential_alias='explicit-selected-analytics',
            client_id='12345-explicit-selected-analytics.apps.googleusercontent.com',scopes=sorted({YT_READ,YT_ANALYTICS}),client_secret=SECRET))
        self.slot=Slot(slot_id='ngos_'+'e'*32,target=self.target,client=receipt,client_id='12345-explicit-selected-analytics.apps.googleusercontent.com',scopes=sorted({YT_READ,YT_ANALYTICS}))
        def token_response(request):
            self.token_wire.append(request.url.path)
            return httpx.Response(200,json={'access_token':TOKEN+str(len(self.token_wire)),'refresh_token':REFRESH,'expires_in':3600,'token_type':'Bearer','scope':' '.join(self.slot.scopes)})
        self.oauth=NativeGoogleOAuthOperations(self.service,self.oauth_vault,slots={self.slot.slot_id:self.slot},enabled=True,client=GoogleOAuthTokenClient(transport=httpx.MockTransport(token_response)))
        project=self.store.get(self.project['id'])
        start=self.oauth.start(project['id'],Start(revision=project['revision'],slot_id=self.slot.slot_id,expected_configuration_sha256=self.slot.client.configuration_sha256,
            acknowledged_credential_operation=True,acknowledged_protocol_mock=True,redirect_uri='http://127.0.0.1:18047/oauth/google/callback',request_key='explicit-analytics-collector-oauth'),principal=self.principal)[0]
        flow=self.oauth_vault.authorization(start['snapshot']['authorization_receipt'])
        self.source=asyncio.run(self.oauth.exchange(project['id'],start['authorization_id'],urlencode({'state':flow.state,'code':CODE}),principal=self.principal,expected_snapshot_sha256=start['snapshot_sha256']))
        def channel_response(request):
            self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'1');self.assertEqual(request.method,'GET')
            self.selection_wire.append(request.url.path)
            return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
        self.selections=NativeGoogleOAuthSelections(self.oauth,purpose='analytics',enabled=True,client=AnalyticsHTTPClient('youtube',transport=httpx.MockTransport(channel_response)))
        pending=self.selections.create(project['id'],Select(revision=project['revision'],source_operation_id=self.source['operation_id'],expected_result_sha256=self.source['result_sha256'],
            acknowledged_account_access=True,acknowledged_credential_selection=True,acknowledged_protocol_mock=True,request_key='explicit-collector-credential-choice'),principal=self.principal)[0]
        self.selected=asyncio.run(self.selections.verify(project['id'],pending['selection_id'],principal=self.principal,expected_snapshot_sha256=pending['snapshot_sha256']))
        account=OAuthAccount(account_ref=self.reader.account.account_ref,target=self.target,credential_alias=self.slot.client.credential_alias,credential_source='google_oauth_selection',google_oauth_slot_id=self.slot.slot_id,read_enabled=True)
        self.reader=AccountFactory(account,self.root,self.workspace,owner_read_enabled=True,transport=httpx.MockTransport(self.selected_read_response))
        self.reader.resolver.attach(self.selections);self.accounts.factories[account.account_ref]=self.reader
    def selected_read_response(self,request):
        self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'1')
        if self.final_read_mode=='selection-revoke':self.revoke_selection()
        if self.final_read_mode=='grant-expire':self.clock[0]+=timedelta(seconds=3511)
        return self.read_response(request)
    def revoke_selection(self):
        return self.selections.revoke(self.project['id'],self.selected['selection_id'],Revoke(expected_snapshot_sha256=self.selected['snapshot_sha256']),principal=self.principal)

class SelectedAnalyticsCollectorTests(SelectedAnalyticsFixture,unittest.TestCase):
    def test_selected_readonly_grant_runs_original_collector_without_fabricating_metrics(self):
        before=self.store.get(self.project['id']);self.assertEqual(self.read_wire,[])
        with self.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_syncs').fetchone()[0],0)
        done=self.run_collection();self.assertEqual(done['status'],'succeeded',done)
        self.assertEqual(self.selection_wire,['/youtube/v3/channels']);self.assertEqual([r['path'] for r in self.read_wire],['/youtube/v3/channels','/youtube/v3/videos','/v2/reports'])
        self.assertTrue(all(r['method']=='GET' for r in self.read_wire));self.assertEqual(done['result']['metrics']['views'],0);self.assertIsNone(done['result']['metrics']['completion_rate'])
        self.assertFalse(done['result']['real_audience_observation']);self.assertTrue(done['result']['mock']);self.assertEqual(self.store.get(self.project['id']),before)
        for secret in (TOKEN,REFRESH,SECRET,CODE):self.assertNotIn(secret,json.dumps(done))
        costs=[r for r in self.analytics.costs.summary(self.project['id'])['records'] if r['provider']=='official-youtube-analytics']
        self.assertEqual(len(costs),3);self.assertTrue(all(not r['paid'] and not r['external_call'] and r['actual_cost'] is None for r in costs))
    def test_separate_read_consent_and_revenue_scope_are_checked_before_network(self):
        with self.assertRaises(ValidationError):self.collect(acknowledged_read_only=False)
        done=self.run_collection(query={'start_date':'2026-10-01','end_date':'2026-10-07','include_revenue':True})
        self.assertNotEqual(done['status'],'succeeded')
        self.assertEqual(self.read_wire,[]);self.assertEqual(len(self.selection_wire),1)
    def test_local_selection_revoke_prevents_pending_collector_reads(self):
        self.collect();self.revoke_selection();done=self.analytics.process()
        self.assertNotEqual(done['status'],'succeeded');self.assertEqual(self.read_wire,[])
    def test_last_private_read_rechecks_selection_before_any_stats_wire(self):
        self.collect();load=self.oauth_vault.grant
        def revoke(receipt):value=load(receipt);self.revoke_selection();return value
        with patch.object(self.oauth_vault,'grant',side_effect=revoke):done=self.analytics.process()
        self.assertNotEqual(done['status'],'succeeded');self.assertEqual(self.read_wire,[])
    def test_revocation_after_first_read_blocks_video_and_report(self):
        self.final_read_mode='selection-revoke';done=self.run_collection()
        self.assertNotEqual(done['status'],'succeeded');self.assertEqual([r['path'] for r in self.read_wire],['/youtube/v3/channels'])
    def test_grant_expiry_after_first_read_blocks_video_and_report(self):
        self.final_read_mode='grant-expire';done=self.run_collection()
        self.assertNotEqual(done['status'],'succeeded');self.assertEqual([r['path'] for r in self.read_wire],['/youtube/v3/channels'])
    def test_refresh_supersession_never_renews_selection_or_pending_stats_consent(self):
        self.collect();project=self.store.get(self.project['id'])
        refreshed=asyncio.run(self.oauth.refresh(project['id'],Refresh(revision=project['revision'],slot_id=self.slot.slot_id,expected_configuration_sha256=self.slot.client.configuration_sha256,
            acknowledged_credential_operation=True,acknowledged_protocol_mock=True,source_operation_id=self.source['operation_id'],expected_result_sha256=self.source['result_sha256'],request_key='explicit-collector-refresh-grant'),principal=self.principal))
        self.assertEqual(refreshed['status'],'succeeded');done=self.analytics.process();self.assertNotEqual(done['status'],'succeeded');self.assertEqual(self.read_wire,[])
    def test_statistics_history_is_append_only_and_mock_backoff_keeps_selection(self):
        first=self.run_collection();self.assertEqual(first['status'],'succeeded');self.metric_values[0]=7
        second=self.run_collection(request_key='explicit-collector-second-snapshot');self.assertEqual(second['status'],'succeeded')
        self.assertNotEqual(first['result']['result_snapshot_id'],second['result']['result_snapshot_id']);self.assertEqual(self.analytics.get(self.project['id'],first['sync_id']),first)
        self.read_mode='rate-limit';limited=self.run_collection(request_key='explicit-collector-rate-limit-snapshot',max_attempts=2,acknowledged_bounded_retries=True)
        self.assertEqual(limited['status'],'retry_scheduled');self.assertIsNone(limited['result']);self.assertEqual(self.selections.get(self.project['id'],self.selected['selection_id'])['status'],'active')

if __name__=='__main__':unittest.main()
