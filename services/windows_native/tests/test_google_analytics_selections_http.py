"""Signed local analytics-grant choice; no statistics/publishing consent implied."""
import json,unittest
from unittest.mock import patch
import httpx
from app.analytics_official import AnalyticsHTTPClient
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault
from services.windows_native.official_account_registry import OAuthAccount,AccountFactory
from services.windows_native.tests.test_google_oauth_http import OAuthHTTPFixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE
from services.windows_native.server import LocalServer,Handler
from services.windows_native.contracts import WorkflowError

class GoogleAnalyticsSelectionHTTPTests(OAuthHTTPFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.start_http('analytics');self.done=self.exchange_http();self.slot=self.slots['ngos_'+'a'*32];self.account_calls=[]
        def wire(request):
            self.account_calls.append({'method':request.method,'path':request.url.path})
            self.assertEqual(request.method,'GET');self.assertEqual(request.headers['authorization'],'Bearer '+TOKEN+'1')
            return httpx.Response(200,json={'items':[{'id':self.slot.target.target_account_id}]})
        self.client=AnalyticsHTTPClient('youtube',transport=httpx.MockTransport(wire));self.selections=NativeGoogleOAuthSelections(self.operations,purpose='analytics',enabled=True,client=self.client)
        self.server.google_analytics_selections=self.server.runner.google_analytics_selections=self.selections
        self.selection_base=self.base+'/analytics-selections'
    def body(self,**changes):return {'revision':self.project['revision'],'source_operation_id':self.done['operation_id'],'expected_result_sha256':self.done['result_sha256'],
        'acknowledged_account_access':True,'acknowledged_credential_selection':True,'acknowledged_protocol_mock':True,'request_key':'explicit-http-analytics-selection',**changes}
    def create_selection(self):
        status,value,headers=self.request('POST',self.selection_base,self.body());self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value
    def test_signed_prepare_verify_revoke_history_do_not_create_stats_jobs(self):
        before=self.store.get(self.project['id']);value=self.create_selection();self.assertEqual(self.account_calls,[])
        path=self.selection_base+'/'+value['selection_id'];binding={'expected_snapshot_sha256':value['snapshot_sha256']}
        status,result,_=self.request('POST',path+'/verify',binding);self.assertEqual(status,200,result);self.assertEqual(result['status'],'active')
        self.assertEqual(len(self.account_calls),1);self.assertFalse(result['publishing_enabled']);self.assertTrue(result['result']['mock'])
        self.assertEqual(self.request('GET',path)[1],result);self.assertEqual(len(self.request('GET',self.selection_base+'?limit=1')[1]['items']),1)
        self.assertEqual(self.request('POST',path+'/revoke',binding)[1]['status'],'revoked');self.assertEqual(len(self.account_calls),1)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_official_analytics_syncs').fetchone()[0],0)
        self.assertEqual(self.store.get(self.project['id']),before)
        for secret in (TOKEN,REFRESH,SECRET,CODE,self.raw):self.assertNotIn(secret,json.dumps([result,self.logs]))
    def test_roles_and_csrf_refuse_before_body_and_private_read(self):
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No forbidden body')):
                for suffix in ('','/ngasel_'+'d'*32+'/verify','/ngasel_'+'d'*32+'/revoke'):self.assertEqual(self.request('POST',self.selection_base+suffix,{})[0],403)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('No missing CSRF body')):self.assertEqual(self.request('POST',self.selection_base,{},headers={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.account_calls,[])
    def test_purpose_cannot_be_body_switched_and_id_namespaces_do_not_cross(self):
        for extra in ({'purpose':'publishing'},{'analytics_enabled':True},{'token':TOKEN},{'acknowledged_account_access':1},{'acknowledged_protocol_mock':1}):
            self.assertEqual(self.request('POST',self.selection_base,self.body(**extra))[0],400)
        value=self.create_selection();self.assertEqual(self.request('GET',self.base+'/selections/'+value['selection_id'])[0],400)
        with patch.object(Handler,'read_body',side_effect=AssertionError('No mismatched-purpose body')):
            self.assertEqual(self.request('POST',self.base+'/selections/'+value['selection_id']+'/verify',{'expected_snapshot_sha256':value['snapshot_sha256']})[0],403)
        self.assertEqual(self.account_calls,[])
    def test_scoped_pages_defaults_and_runtime_discovery_never_decrypt(self):
        with patch.object(self.vault,'grant',side_effect=AssertionError('No discovery decrypt')):
            status,value,_=self.request('GET','/api/connections/google-oauth-analytics-selections');self.assertEqual(status,200,value);self.assertEqual(len(value['slots']),1)
            self.assertEqual(value['schema_version'],'native-google-analytics-selection-runtime-v1');self.assertFalse(value['publishing_enabled'])
        for query in ('?limit=0','?limit=101','?unknown=1','?limit=1&limit=2','?cursor=ngosel_'+'d'*32):self.assertEqual(self.request('GET',self.selection_base+query)[0],400)
        self.assertEqual(self.account_calls,[])
    def test_actual_constructor_attaches_readonly_account_resolver_and_keeps_flags_off(self):
        account=OAuthAccount(account_ref='npac_'+'d'*32,target=self.slot.target,credential_alias=self.slot.client.credential_alias,credential_source='google_oauth_selection',google_oauth_slot_id=self.slot.slot_id,read_enabled=True)
        factory=AccountFactory(account,self.root,self.workspace,transport=self.client.wire.transport)
        with patch.object(NativeGoogleOAuthVault,'grant',side_effect=AssertionError('No startup decrypt')):
            server=LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=self.server.access,
                google_oauth_slots=self.slots,google_oauth_client=self.wire,google_oauth_directory=self.private,google_oauth_enabled=True,
                google_analytics_selection_client=self.client,official_account_factories={account.account_ref:factory})
            try:
                self.assertIs(factory.resolver.service,server.google_analytics_selections);self.assertFalse(server.google_analytics_selections.states()['enabled'])
                self.assertFalse(server.official_analytics.enabled);self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
                self.assertEqual(server.google_oauth_selections.purpose,'publishing')
            finally:server.server_close()
    def test_raw_gate_network_injection_and_missing_oauth_reject_before_socket(self):
        for change in ({'google_analytics_selection_enabled':1},{'google_analytics_selection_enabled':True},
            {'google_analytics_selection_client':AnalyticsHTTPClient('youtube',network_enabled=True)}):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=self.server.access,**change)

if __name__=='__main__':unittest.main()
