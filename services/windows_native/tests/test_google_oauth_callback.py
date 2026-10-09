"""Actual external loopback HTTP; no browser or genuine OAuth acceptance."""
import asyncio,copy,http.client,json,re,unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from urllib.parse import urlencode
from unittest.mock import patch
from services.windows_native.tests.test_google_oauth_http import OAuthHTTPFixture
from services.windows_native.tests.test_google_oauth_protocol import TOKEN,REFRESH,SECRET,CODE
from services.windows_native.google_oauth_operations import Cancel,NativeGoogleOAuthOperations
from services.windows_native.contracts import WorkflowError
from services.windows_native.google_oauth_registry import load
from services.windows_native.server import Handler
from app.google_oauth_protocol import authorization
from app.human_identity import HumanAuthVerifier,HumanAuthRegistry

class GoogleOAuthCallbackTests(OAuthHTTPFixture,unittest.TestCase):
    def callback(self,query=None,headers=None):
        return self.request('GET','/oauth/google/callback?'+(self.query() if query is None else query),headers={'Cookie':'','X-VF-CSRF':'','Sec-Fetch-Site':'cross-site','Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document',**(headers or {})})
    def pending(self):return self.operations.get(self.project['id'],self.saved['authorization_id'],kind='authorization')
    def assert_private(self,body,headers):
        self.assertIsInstance(body,bytes);self.assertEqual(headers['Content-Type'],'text/html; charset=utf-8');self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['Referrer-Policy'],'no-referrer')
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy']);self.assertNotIn('Set-Cookie',headers);self.assertNotIn('Location',headers)
        public=body.decode()+json.dumps(self.logs)+json.dumps(headers)
        for value in (TOKEN,REFRESH,SECRET,CODE,self.raw,self.query()):self.assertNotIn(value,public)
        for value in (self.project['id'],self.saved['authorization_id']):self.assertNotIn(value,body.decode()+json.dumps(headers))
        for raw in self.logs:
            record=json.loads(raw)
            if record['method']=='GET' and record['route']=='other':self.assertIsNone(record['project_id']);self.assertIsNone(record['job_id'])
    def test_external_navigation_no_studio_cookie_consumes_once_and_returns_only_fixed_mock_page(self):
        before=self.store.get(self.project['id']);session=self.request('GET','/api/session')[1];self.start_http();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt'])
        self.assertRegex(flow.state,r'^'+self.saved['authorization_id']+r'\.[A-Za-z0-9_-]{64}$');self.assertEqual(len(flow.state),102)
        status,body,headers=self.callback();self.assertEqual(status,200);self.assertIn(b'Protocol mock completed',body);self.assert_private(body,headers)
        value=self.pending();self.assertEqual(value['status'],'consumed');done=self.operations.get(self.project['id'],value['operation_id']);self.assertEqual(done['status'],'succeeded')
        self.assertFalse(done['result']['credential_selected']);self.assertFalse(done['result']['grant_proof']['account_verified']);self.assertFalse(done['result']['grant_proof']['publishing_enabled'])
        self.assertEqual(len(self.calls),1);self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(self.request('GET','/api/session')[1],session);self.assertFalse(self.server.runner.run_one())
        status,body,headers=self.callback();self.assertEqual(status,400);self.assert_private(body,headers);self.assertEqual(len(self.calls),1)
    def test_wrong_random_suffix_or_foreign_identity_never_consumes_or_sends(self):
        self.start_http();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt']);wrong=flow.state[:-1]+('a' if flow.state[-1]!='a' else 'b')
        for state in (wrong,'ngoa_'+'f'*32+'.'+flow.state.split('.')[1],self.saved['authorization_id']+'.'+'x'*63,flow.state.split('.')[1]):
            status,body,headers=self.callback(urlencode({'state':state,'code':CODE}));self.assertEqual(status,400);self.assert_private(body,headers)
        self.assertEqual(self.pending()['status'],'awaiting_callback');self.assertEqual(self.calls,[]);self.assertEqual(self.operations.costs.summary(self.project['id'])['records'],[])
    def test_duplicate_unknown_code_error_both_malformed_and_oversize_query_refuse(self):
        self.start_http();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt'])
        for query in (self.query()+'&state=duplicate',self.query()+'&authority=owner',self.query()+'&error=access_denied',urlencode({'state':flow.state}),'state=%00&code=x','state=x&code='+('x'*8192),self.query()+'#fragment','invalid-field'):
            self.assertEqual(self.callback(query)[0],400)
        self.assertEqual(self.pending()['status'],'awaiting_callback');self.assertEqual(self.calls,[])
    def test_revoked_owner_refuses_before_private_decryption_even_with_exact_state(self):
        self.start_http();query=self.query();self.revoke()
        with patch.object(self.vault,'authorization',side_effect=AssertionError('NO REVOKED PRIVATE READ')),patch.object(self.vault,'client',side_effect=AssertionError('NO REVOKED CLIENT READ')):
            status,body,headers=self.callback(query);self.assertEqual(status,400)
        self.assertEqual(self.calls,[]);self.assertEqual(self.pending()['status'],'awaiting_callback')
    def test_changed_identity_revision_role_and_expiry_do_not_substitute_a_cookie_owner(self):
        self.start_http();query=self.query();original=self.verifier.registry.model_dump(mode='json')
        for change in ({'display_name':'Changed original identity'},{'workspace_roles':{self.workspace:'reviewer'}},{'expires_at':(self.clock[0]-timedelta(seconds=1)).isoformat()}):
            changed=copy.deepcopy(original);changed['tokens'][self.principal.token_id].update(change)
            self.server.access.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(changed),max_token_ttl_seconds=86400)
            with patch.object(self.vault,'authorization',side_effect=AssertionError('NO CHANGED OWNER PRIVATE READ')):self.assertEqual(self.callback(query)[0],400)
        self.assertEqual(self.calls,[])
    def test_unrelated_current_cookie_cannot_replace_saved_owner_authority(self):
        self.start_http();query=self.query();self.account('owner')
        self.assertEqual(self.callback(query,headers={'Cookie':'vf_native_session='+self.cookie})[0],400);self.assertEqual(self.calls,[])
    def test_exact_current_port_redirect_is_checked_before_private_reads(self):
        self.start_http();query=self.query()
        with patch.object(self.vault,'authorization',side_effect=AssertionError('NO WRONG PORT PRIVATE READ')):
            with self.assertRaisesRegex(WorkflowError,'CALLBACK_INVALID'):asyncio.run(self.operations.callback(query,redirect_uri='http://127.0.0.1:1/oauth/google/callback'))
        self.assertEqual(self.pending()['status'],'awaiting_callback');self.assertEqual(self.calls,[])
    def test_consent_deadline_archive_and_source_revision_before_callback_refuse(self):
        for mode in ('deadline','archive','revision'):
            self.start_http(request_key='explicit-callback-source-key-'+mode,revision=self.store.get(self.project['id'])['revision']);query=self.query()
            if mode=='deadline':self.clock[0]+=timedelta(seconds=601)
            elif mode=='archive':self.store.archive(self.project['id'],self.store.get(self.project['id'])['revision'],True)
            else:self.store.save(self.project['id'],self.store.get(self.project['id'])['revision'],prompt='Explicit changed callback project')
            with patch.object(self.vault,'authorization',side_effect=AssertionError('NO INVALID SOURCE PRIVATE READ')):self.assertEqual(self.callback(query)[0],400)
            if mode=='archive':self.store.archive(self.project['id'],self.store.get(self.project['id'])['revision'],False)
        self.assertEqual(self.calls,[])
    def test_host_origin_fetch_mode_and_get_body_reject_before_private_read(self):
        self.start_http();query=self.query()
        changes=({'Host':f'localhost:{self.server.server_port}'},{'Host':'untrusted.invalid'},{'Origin':'https://untrusted.invalid'},{'Sec-Fetch-Mode':'cors'},{'Sec-Fetch-Dest':'empty'},{'Sec-Fetch-Site':'same-site'},{'Content-Length':'1'},{'Transfer-Encoding':'chunked'})
        with patch.object(self.vault,'authorization',side_effect=AssertionError('NO FORBIDDEN PRIVATE READ')):
            for change in changes:self.assertIn(self.callback(query,headers=change)[0],(400,403))
        self.assertEqual(self.calls,[])
    def test_duplicate_host_header_is_rejected_before_dispatch(self):
        self.start_http();connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.putrequest('GET','/oauth/google/callback?'+self.query(),skip_host=True);connection.putheader('Host',f'127.0.0.1:{self.server.server_port}');connection.putheader('Host',f'127.0.0.1:{self.server.server_port}');connection.endheaders()
        response=connection.getresponse();self.assertEqual(response.status,403);response.read();connection.close();self.assertEqual(self.calls,[])
    def test_fixed_official_origin_top_navigation_supported_without_session(self):
        self.start_http();self.assertEqual(self.callback(headers={'Origin':'https://accounts.google.com'})[0],200);self.assertEqual(len(self.calls),1)
    def test_other_routes_keep_original_cross_site_csrf_and_session_boundary(self):
        self.start_http()
        with patch.object(Handler,'read_body',side_effect=AssertionError('NO BYPASSED API BODY')):
            for path in ('/api/session',self.base+'/operations','/api/connections/google-oauth'):
                self.assertEqual(self.request('GET',path,headers={'Sec-Fetch-Site':'cross-site'})[0],403)
            self.assertEqual(self.request('POST',self.base+'/authorizations',{},headers={'Sec-Fetch-Site':'cross-site'})[0],403)
            self.assertEqual(self.request('POST','/oauth/google/callback',{},headers={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.calls,[])
    def test_denial_consumes_without_cost_or_private_provider_details(self):
        self.start_http();flow=self.vault.authorization(self.saved['snapshot']['authorization_receipt']);query=urlencode({'state':flow.state,'error':'access_denied','error_description':SECRET,'error_uri':'https://untrusted.invalid/'+SECRET})
        status,body,headers=self.callback(query);self.assertEqual(status,200);self.assertIn(b'Authorization declined',body);self.assert_private(body,headers)
        value=self.operations.get(self.project['id'],self.pending()['operation_id']);self.assertEqual(value['failure_code'],'GOOGLE_OAUTH_CONSENT_DENIED');self.assertIsNone(value['cost_operation_id']);self.assertEqual(self.calls,[])
    def test_timeout_replay_and_restart_keep_unknown_without_background_retry(self):
        self.start_http();query=self.query();self.mode='timeout';status,body,headers=self.callback(query);self.assertEqual(status,409);self.assertIn(b'Authorization needs review',body);self.assert_private(body,headers)
        operation=self.pending()['operation_id'];self.assertEqual(self.operations.get(self.project['id'],operation)['status'],'outcome_unknown');self.operations.recover();self.assertEqual(self.callback(query)[0],400);self.assertEqual(len(self.calls),1);self.assertFalse(self.server.runner.run_one())
    def test_late_source_and_saved_owner_changes_preserve_receipt_without_grant(self):
        for mode in ('edit','expired','revoke'):
            self.start_http(request_key='explicit-late-callback-'+mode,revision=self.store.get(self.project['id'])['revision']);query=self.query();self.mode=mode
            self.assertEqual(self.callback(query)[0],409);value=self.operations.get(self.project['id'],self.pending()['operation_id']);self.assertEqual(value['status'],'review_required');self.assertIsNone(value['result']);self.assertIsNotNone(value['cost_operation_id']);self.mode=None
        self.assertEqual(len(self.calls),3)
    def test_concurrent_external_callbacks_have_one_durable_token_dispatch(self):
        self.start_http();query=self.query()
        with ThreadPoolExecutor(2) as pool:statuses=list(pool.map(lambda _:self.callback(query)[0],range(2)))
        self.assertEqual(sorted(statuses),[200,400]);self.assertEqual(len(self.calls),1)
    def test_cancelled_intent_cannot_receive_external_callback(self):
        self.start_http();query=self.query();self.operations.cancel(self.project['id'],self.saved['authorization_id'],Cancel(expected_snapshot_sha256=self.saved['snapshot_sha256']),principal=self.principal)
        self.assertEqual(self.callback(query)[0],400);self.assertEqual(self.calls,[])
    def test_private_cipher_drift_blocks_without_token_call(self):
        self.start_http();query=self.query();receipt=self.saved['snapshot']['authorization_receipt'];path=self.private/(receipt['reference']+'.dpapi');path.write_bytes(path.read_bytes()+b'x')
        self.assertEqual(self.callback(query)[0],400);self.assertEqual(self.calls,[]);self.assertEqual(self.pending()['status'],'awaiting_callback')
    def test_legacy_unprefixed_private_state_keeps_signed_manual_exchange(self):
        with patch('services.windows_native.google_oauth_operations.replace',side_effect=lambda flow,**_:flow):self.start_http()
        query=self.query();self.assertNotIn('.',self.vault.authorization(self.saved['snapshot']['authorization_receipt']).state)
        self.assertEqual(self.callback(query)[0],400);self.assertEqual(self.calls,[]);self.assertEqual(self.exchange_http()['status'],'succeeded');self.assertEqual(len(self.calls),1)
    def test_runtime_marks_protocol_mock_but_session_and_history_shapes_stay_original(self):
        before=self.request('GET','/api/session')[1];self.assertTrue(self.request('GET','/api/connections/google-oauth')[1]['mock']);self.start_http();query=self.query();self.assertEqual(self.callback(query)[0],200)
        self.assertEqual(self.request('GET','/api/session')[1],before);self.assertNotIn('mock',self.pending());self.assertNotIn('mock',self.operations.get(self.project['id'],self.pending()['operation_id']))
    def test_disabled_kernel_and_historical_server_have_no_private_callback_reads(self):
        self.start_http();query=self.query();self.operations=NativeGoogleOAuthOperations(self.server.official_publications,self.vault,slots=self.slots,client=self.wire,enabled=False);self.server.google_oauth=self.operations
        with patch.object(self.vault,'authorization',side_effect=AssertionError('NO DISABLED PRIVATE READ')):self.assertEqual(self.callback(query)[0],400)
        self.server.google_oauth=None;self.assertEqual(self.callback(query)[0],400);self.assertEqual(self.calls,[])
    def test_protected_registry_drift_refuses_before_callback_private_reads(self):
        path=self.registry_file();_,protected,checksum=load(path,self.root,self.workspace)
        self.operations=NativeGoogleOAuthOperations(self.server.official_publications,self.vault,slots=self.slots,client=self.wire,enabled=True,registry_file=protected,registry_sha256=checksum);self.server.google_oauth=self.operations
        self.start_http();query=self.query();path.write_bytes(path.read_bytes()+b' ')
        with patch.object(self.vault,'authorization',side_effect=AssertionError('NO DRIFT PRIVATE READ')),patch.object(self.vault,'client',side_effect=AssertionError('NO DRIFT CLIENT READ')):self.assertEqual(self.callback(query)[0],400)
        self.assertEqual(self.calls,[])
    def test_unexpected_error_is_fixed_and_does_not_reflect_private_exception_details(self):
        self.start_http();query=self.query()
        with patch.object(self.operations,'callback',side_effect=RuntimeError(SECRET+query)):
            status,body,headers=self.callback(query);self.assertEqual(status,409);self.assert_private(body,headers)
        self.assertEqual(self.calls,[]);self.assertEqual(self.pending()['status'],'awaiting_callback')
