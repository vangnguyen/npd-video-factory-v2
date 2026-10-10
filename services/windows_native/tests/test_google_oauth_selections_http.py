"""Signed local credential-selection HTTP; only explicit synthetic accounts."""
import json,unittest
from unittest.mock import patch
import httpx
from app.publishing_wire import OfficialHTTPClient
from services.windows_native.google_oauth_selections import NativeGoogleOAuthSelections
from services.windows_native.google_oauth_vault import NativeGoogleOAuthVault
from services.windows_native.official_publication_registry import OAuthBinding,PublishingFactory
from services.windows_native.official_publication_models import Profile
from services.windows_native.tests.test_google_oauth_http import OAuthHTTPFixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE
from services.windows_native.server import LocalServer,Handler
from services.windows_native.contracts import WorkflowError


class GoogleOAuthSelectionHTTPTests(OAuthHTTPFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.start_http('publishing');self.done=self.exchange_http();self.slot=self.slots['ngos_'+'b'*32];self.channel_calls=[]
        def wire(request):
            self.channel_calls.append({'method':request.method,'host':request.url.host,'path':request.url.path})
            return httpx.Response(200,json={'items':[{'id':self.slot.target.target_account_id}]})
        self.channel_wire=OfficialHTTPClient('youtube',transport=httpx.MockTransport(wire))
        self.selections=NativeGoogleOAuthSelections(self.operations,enabled=True,client=self.channel_wire)
        self.server.google_oauth_selections=self.server.runner.google_oauth_selections=self.selections

    def selection_body(self,**changes):
        return {'revision':self.project['revision'],'source_operation_id':self.done['operation_id'],'expected_result_sha256':self.done['result_sha256'],
            'acknowledged_account_access':True,'acknowledged_credential_selection':True,'acknowledged_protocol_mock':True,'request_key':'explicit-http-selection-key',**changes}

    def create_selection(self):
        status,value,headers=self.request('POST',self.base+'/selections',self.selection_body());self.assertEqual(status,200,value)
        self.assertEqual(headers['Cache-Control'],'no-store');return value

    def test_signed_selection_verify_history_revoke_and_no_publish_enablement(self):
        before=self.store.get(self.project['id']);value=self.create_selection();self.assertEqual(self.channel_calls,[])
        path=self.base+'/selections/'+value['selection_id'];binding={'expected_snapshot_sha256':value['snapshot_sha256']}
        status,active,_=self.request('POST',path+'/verify',binding);self.assertEqual(status,200,active);self.assertEqual(active['status'],'active')
        self.assertEqual(len(self.channel_calls),1);self.assertFalse(active['publishing_enabled']);self.assertFalse(active['result']['real_provider_tested'])
        self.assertEqual(self.request('GET',path)[1],active);self.assertEqual(len(self.request('GET',self.base+'/selections?limit=1')[1]['items']),1)
        status,result,_=self.request('POST',path+'/revoke',binding);self.assertEqual(status,200,result);self.assertEqual(result['status'],'revoked')
        self.assertEqual(len(self.channel_calls),1);self.assertEqual(self.store.get(self.project['id']),before)
        public=json.dumps([active,result,self.logs])
        for secret in (TOKEN,REFRESH,SECRET,CODE,self.raw):self.assertNotIn(secret,public)

    def test_owner_roles_and_csrf_refuse_before_body_and_private_decrypt(self):
        for role in ('viewer','reviewer','editor'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('No forbidden body')):
                for suffix in ('/selections','/selections/ngosel_'+'c'*32+'/verify','/selections/ngosel_'+'c'*32+'/revoke'):
                    self.assertEqual(self.request('POST',self.base+suffix,{})[0],403)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('No missing CSRF body')):self.assertEqual(self.request('POST',self.base+'/selections',{},headers={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.channel_calls,[])

    def test_unknown_fields_raw_flags_and_scope_pagination_fail_closed(self):
        for change in ({'token':TOKEN},{'enabled':True},{'authority':{}},{'acknowledged_account_access':1},{'acknowledged_credential_selection':'true'},
            {'acknowledged_protocol_mock':1},{'expected_result_sha256':'e'*64}):
            self.assertIn(self.request('POST',self.base+'/selections',self.selection_body(**change))[0],(400,409))
        value=self.create_selection();path=self.base+'/selections/'+value['selection_id']
        self.assertEqual(self.request('POST',path+'/verify',{'expected_snapshot_sha256':'e'*64})[0],409)
        for query in ('?limit=0','?limit=101','?limit=true','?cursor=not-a-selection','?unknown=1','?limit=1&limit=2'):self.assertEqual(self.request('GET',self.base+'/selections'+query)[0],400)
        self.assertEqual(self.request('GET','/api/projects/'+'f'*32+'/google-oauth/selections/'+value['selection_id'])[0],404)
        self.assertEqual(self.channel_calls,[])

    def test_default_runtime_is_inert_and_claim_recovery_is_not_a_publish_job(self):
        with patch.object(self.vault,'grant',side_effect=AssertionError('No discovery decryption')):
            status,value,_=self.request('GET','/api/connections/google-oauth-selections');self.assertEqual(status,200,value)
            self.assertTrue(value['enabled']);self.assertEqual(len(value['slots']),1);self.assertFalse(value['publishing_enabled']);self.assertFalse(value['startup_decryption'])
        self.assertEqual(self.channel_calls,[]);self.assertFalse(self.server.official_publish_queue.enabled)

    def test_actual_constructor_attaches_resolver_and_default_keeps_selection_off(self):
        binding=OAuthBinding(credential_source='google_oauth_selection',profile=Profile(target=self.slot.target,category_id='28',made_for_kids=False,contains_synthetic_media=True),
            credential_alias=self.slot.client.credential_alias,google_oauth_slot_id=self.slot.slot_id)
        factory=PublishingFactory(binding.profile,self.root,self.workspace,binding=binding,client=self.channel_wire)
        with patch.object(NativeGoogleOAuthVault,'grant',side_effect=AssertionError('No constructor decryption')):
            server=LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=self.server.access,
                google_oauth_slots=self.slots,google_oauth_client=self.wire,google_oauth_directory=self.private,google_oauth_enabled=True,
                google_oauth_selection_client=self.channel_wire,official_publish_factories={binding.profile.target.profile_id:factory})
            try:
                self.assertIs(factory.resolver.service,server.google_oauth_selections);self.assertFalse(server.google_oauth_selections.states()['enabled'])
                self.assertEqual(factory.public()['status'],'NOT_CONFIGURED')
            finally:server.server_close()
        self.assertEqual(self.channel_calls,[])

    def test_selection_runtime_rejects_network_injection_and_raw_gate(self):
        for changes in ({'google_oauth_selection_enabled':1},{'google_oauth_selection_enabled':True},
            {'google_oauth_selection_client':OfficialHTTPClient('youtube',network_enabled=True)}):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=self.server.access,**changes)
        self.assertEqual(self.channel_calls,[])


if __name__=='__main__':unittest.main()
