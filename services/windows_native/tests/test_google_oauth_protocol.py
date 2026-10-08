"""Portable dedicated Desktop OAuth contracts; all credentials and wires are mocks."""
import asyncio,base64,hashlib,json,logging,unittest
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from io import StringIO
from unittest.mock import patch
from urllib.parse import parse_qs,urlencode
import httpx
from services.windows_native import ingestion
from app.google_oauth_protocol import GoogleDesktopClient,GoogleTokenRequest,GoogleTokenResponse,GoogleOAuthGrant,GoogleOAuthTokenClient,GoogleOAuthError,authorization,exchange_request,refresh_request,parse_tokens,loopback,TOKEN_URL
from app.analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS,YT_MONEY
from app.publishing_credentials import PublishingOAuthCredential,UPLOAD,READ
from app.publishing_models import PublishingTargetBinding

NOW=datetime(2026,10,8,22,0,tzinfo=timezone.utc)
TOKEN='EXPLICIT_SYNTHETIC_ACCESS_TOKEN_123456789'
REFRESH='EXPLICIT_SYNTHETIC_REFRESH_TOKEN_123456789'
SECRET='EXPLICIT_SYNTHETIC_CLIENT_SECRET_123456789'
CODE='4/EXPLICIT_SYNTHETIC_AUTHORIZATION_CODE_12345'

def client(purpose='analytics',money=False,secret=True):
    return GoogleDesktopClient(PublishingTargetBinding(workspace_id='wsp_google_oauth_fixture',profile_id='ppf_google_oauth_fixture',profile_version=1,platform='youtube',
        provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_SYNTHETIC_CHANNEL',credential_binding_sha256='a'*64),purpose,
        '12345-explicit-vf-fixture.apps.googleusercontent.com',frozenset({UPLOAD,READ} if purpose=='publishing' else {YT_READ,YT_ANALYTICS,*([YT_MONEY] if money else [])}),SECRET if secret else None)
def initial(c=None,now=NOW):
    c=client() if c is None else c;flow=authorization(c,'http://127.0.0.1:18047/oauth/google/callback',now=now)
    return c,flow,exchange_request(flow,urlencode({'state':flow.state,'code':CODE}),now=now)
def response(c,status=200,**values):
    return GoogleTokenResponse(status,True,json.dumps({'access_token':TOKEN,'refresh_token':REFRESH,'expires_in':3600,'token_type':'Bearer','scope':' '.join(sorted(c.scopes)),**values}).encode())
def grant(c=None,now=NOW,**changes):
    c,flow,request=initial(c,now);return c,parse_tokens(c,request,response(c,**changes),now=now)

class GoogleOAuthProtocolTests(unittest.TestCase):
    def test_construction_and_authorization_are_inert_pkce_s256_exact_loopback_scope_state_and_no_secret(self):
        c,flow,request=initial();p=parse_qs(flow.url(NOW).partition('?')[2]);expected=base64.urlsafe_b64encode(hashlib.sha256(flow.verifier.encode()).digest()).decode().rstrip('=')
        self.assertEqual(p['code_challenge'],[expected]);self.assertEqual(p['code_challenge_method'],['S256']);self.assertEqual(p['response_type'],['code'])
        self.assertEqual(p['state'],[flow.state]);self.assertEqual(p['redirect_uri'],[flow.redirect_uri]);self.assertEqual(set(p['scope'][0].split()),c.scopes)
        for private in (SECRET,flow.verifier,CODE,TOKEN,REFRESH):self.assertNotIn(private,flow.url(NOW))
        other=authorization(c,flow.redirect_uri,now=NOW);self.assertNotEqual(flow.state,other.state);self.assertNotEqual(flow.verifier,other.verifier)
    def test_dedicated_analytics_and_upload_scope_sets_cannot_mix_broaden_or_use_another_platform(self):
        for purpose,scopes in (('analytics',frozenset({UPLOAD,READ})),('publishing',frozenset({UPLOAD,READ,YT_ANALYTICS})),('analytics',frozenset({YT_READ})),('analytics',frozenset({YT_READ,YT_ANALYTICS,'openid'})),('service',client().scopes)):
            with self.assertRaises(GoogleOAuthError):replace(client(),purpose=purpose,scopes=scopes)
        c=client(money=True);self.assertIn(YT_MONEY,c.scopes);self.assertEqual(client('publishing').scopes,frozenset({UPLOAD,READ}))
        with self.assertRaises(GoogleOAuthError):replace(client(),target=client().target.model_copy(update={'platform':'tiktok'}))
        with self.assertRaises(GoogleOAuthError):replace(client(),scopes=set(client().scopes))
    def test_public_target_is_cloned_and_client_id_secret_and_schema_are_validated(self):
        c=client();original=c.target;copied=GoogleDesktopClient(original,c.purpose,c.client_id,c.scopes,c.client_secret);object.__setattr__(original,'profile_version',2)
        self.assertEqual(copied.target.profile_version,1)
        for changes in ({'client_id':'arbitrary.invalid'},{'client_secret':'line\nSECRET'},{'client_secret':True},{'purpose':True},{'target':{}}):
            with self.assertRaises(GoogleOAuthError):replace(copied,**changes)
    def test_exact_loopback_only_no_localhost_userinfo_query_fragment_encoded_path_or_remote(self):
        self.assertEqual(loopback('http://[::1]:8047/'),'http://[::1]:8047/')
        for v in ('http://localhost:8047/','https://127.0.0.1:8047/','http://127.0.0.1/','http://127.0.0.1:0/','http://127.0.0.1:65536/','http://127.0.0.2:8047/',
            'http://owner@127.0.0.1:8047/','http://127.0.0.1:8047/?code=unsafe','http://127.0.0.1:8047/#unsafe','http://127.0.0.1:8047/%2f','http://127.0.0.1:08047/','http://127.0.0.1:8047\\@remote.invalid/'):
            with self.assertRaises(GoogleOAuthError):loopback(v)
    def test_bounded_authorization_times_raw_integers_and_expiry_never_create_exchange(self):
        c=client()
        for seconds in (True,59,901,'600',600.0):
            with self.assertRaises(GoogleOAuthError):authorization(c,'http://127.0.0.1:8047/',now=NOW,valid_for_seconds=seconds)
        with self.assertRaises(GoogleOAuthError):authorization(c,'http://127.0.0.1:8047/',now=NOW.replace(tzinfo=None))
        c,flow,request=initial()
        for t in (NOW-timedelta(seconds=1),flow.expires_at):
            with self.assertRaises(GoogleOAuthError):exchange_request(flow,urlencode({'state':flow.state,'code':CODE}),now=t)
    def test_callback_state_wrong_missing_duplicate_and_untrusted_extra_never_produce_body(self):
        c,flow,request=initial();base=urlencode({'state':flow.state,'code':CODE})
        for q in (urlencode({'state':'wrong','code':CODE}),urlencode({'code':CODE}),base+'&state='+flow.state,base+'&code=OTHER',base+'&endpoint=https%3A%2F%2Funtrusted.invalid','state='+flow.state+'&code=',base+'\n',None,'x='+'z'*8193):
            with self.assertRaises(GoogleOAuthError):exchange_request(flow,q,now=NOW)
    def test_denied_consent_sanitizes_provider_error_text_and_refuses_code_error_ambiguity(self):
        c,flow,request=initial()
        with self.assertRaises(GoogleOAuthError) as caught:exchange_request(flow,urlencode({'state':flow.state,'error':'access_denied','error_description':TOKEN,'error_uri':'https://untrusted.invalid/'+REFRESH}),now=NOW)
        self.assertTrue(caught.exception.needs_reauthorization);self.assertNotIn(TOKEN,str(caught.exception));self.assertNotIn(REFRESH,str(caught.exception))
        for q in ({'state':flow.state,'code':CODE,'error':'access_denied'},{'state':flow.state}):
            with self.assertRaises(GoogleOAuthError):exchange_request(flow,urlencode(q),now=NOW)
    def test_exchange_is_fixed_form_body_not_bearer_query_and_optional_client_secret(self):
        c,flow,request=initial();value=request.check(c)
        self.assertEqual(value,{'client_id':c.client_id,'client_secret':SECRET,'grant_type':'authorization_code','code':CODE,'code_verifier':flow.verifier,'redirect_uri':flow.redirect_uri})
        c,flow,request=initial(client(secret=False));self.assertNotIn('client_secret',request.check(c))
        for private in (SECRET,CODE,flow.verifier):self.assertNotIn(private,repr(request))
    def test_configuration_target_scope_and_secret_change_invalidate_flow_and_request(self):
        c,flow,request=initial()
        for changed in (replace(c,client_secret=SECRET+'NEW'),replace(c,client_id='12345-other-client.apps.googleusercontent.com'),replace(c,target=c.target.model_copy(update={'profile_version':2})),client(money=True)):
            with self.assertRaises(GoogleOAuthError):request.check(changed)
        object.__setattr__(c.target,'profile_version',2)
        with self.assertRaises(GoogleOAuthError):flow.url(NOW)
    def test_successful_grant_has_zero_account_or_publish_authority_and_only_existing_purpose_credential(self):
        for purpose,kind in (('analytics',AnalyticsOAuthCredential),('publishing',PublishingOAuthCredential)):
            c,g=grant(client(purpose));proof=g.public(c);self.assertIs(type(g.credential(c,now=NOW)),kind)
            self.assertEqual(g.expires_at,NOW+timedelta(hours=1));self.assertIsNone(g.refresh_expires_at);self.assertTrue(proof['mock'])
            for k in ('token_returned','account_verified','publishing_enabled','production_consent_renewed','real_provider_tested'):self.assertIs(proof[k],False)
            for private in (TOKEN,REFRESH,SECRET):self.assertNotIn(private,json.dumps(proof)+repr(g)+repr(c))
    def test_token_parser_preserves_original_bound_grant_and_ignores_unrecognized_provider_metadata(self):
        c,flow,request=initial();g=parse_tokens(c,request,response(c,extra={'untrusted':'not evidence'},id_token='IGNORED_IDENTITY_VALUE'),now=NOW+timedelta(seconds=20))
        self.assertEqual(g.obtained_at,NOW+timedelta(seconds=20));self.assertEqual(g.expires_at,NOW+timedelta(hours=1));self.assertFalse(g.public(c)['account_verified'])
        self.assertNotIn('id_token',g.public(c))
    def test_missing_reduced_broader_duplicate_or_wrong_scopes_expiry_tokens_fail_closed(self):
        c,flow,request=initial()
        for values in ({'scope':YT_READ},{'scope':' '.join(sorted(c.scopes))+' '+UPLOAD},{'scope':' '.join(sorted(c.scopes))+' '+YT_READ},{'scope':True},{'scope':None},
            {'expires_in':True},{'expires_in':'3600'},{'expires_in':3600.0},{'expires_in':90},{'expires_in':86401},{'access_token':'bad'},{'access_token':TOKEN+'\n'},{'token_type':'bearer'},{'refresh_token':None},
            {'refresh_token_expires_in':True},{'refresh_token_expires_in':0},{'refresh_token_expires_in':None}):
            with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c,**values),now=NOW)
    def test_duplicate_json_nonobject_nan_and_success_with_error_are_rejected(self):
        c,flow,request=initial()
        for raw in (b'[]',b'{"access_token":"A","access_token":"B"}',b'{"expires_in":NaN}',b'not json'):
            with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,GoogleTokenResponse(200,True,raw),now=NOW)
        with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c,error='invalid_grant'),now=NOW)
    def test_provider_errors_require_reauthorization_or_review_without_private_error_output(self):
        c,flow,request=initial()
        for status,error,reauth in ((400,'invalid_grant',True),(400,'invalid_client',True),(401,'unauthorized_client',True),(429,'rate_limited',False),(503,'backend_error',False)):
            with self.assertRaises(GoogleOAuthError) as caught:parse_tokens(c,request,GoogleTokenResponse(status,True,json.dumps({'error':error,'error_description':TOKEN,'refresh_token':REFRESH}).encode()),now=NOW)
            self.assertIs(caught.exception.needs_reauthorization,reauth);self.assertIs(caught.exception.uncertain,status in (429,503));self.assertNotIn(TOKEN,str(caught.exception));self.assertNotIn(REFRESH,str(caught.exception))
    def test_expired_access_is_not_returned_and_late_response_does_not_gain_full_new_lifetime(self):
        c,g=grant()
        with self.assertRaises(GoogleOAuthError):g.credential(c,now=g.expires_at-timedelta(seconds=90))
        c,flow,request=initial()
        with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c,expires_in=120),now=NOW+timedelta(seconds=31))
        for t in (NOW-timedelta(seconds=1),NOW+timedelta(minutes=15)):
            with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c),now=t)
    def test_explicit_refresh_reuses_original_refresh_when_omitted_and_rotates_when_returned(self):
        c,g=grant();stamp=NOW+timedelta(hours=2);request=refresh_request(c,g,now=stamp)
        self.assertEqual(request.check(c),{'client_id':c.client_id,'client_secret':SECRET,'grant_type':'refresh_token','refresh_token':REFRESH})
        payload=json.loads(response(c).body);del payload['refresh_token'];fresh=parse_tokens(c,request,GoogleTokenResponse(200,True,json.dumps(payload).encode()),now=stamp,previous=g)
        self.assertEqual(fresh.refresh_token,REFRESH);rotated=parse_tokens(c,request,response(c,refresh_token=REFRESH+'ROTATED'),now=stamp,previous=g)
        self.assertEqual(rotated.refresh_token,REFRESH+'ROTATED');self.assertFalse(rotated.public(c)['production_consent_renewed']);self.assertEqual(g.access_token,TOKEN);self.assertEqual(g.refresh_token,REFRESH)
    def test_refresh_source_target_transport_and_exact_token_cannot_be_rebound(self):
        c,g=grant();request=refresh_request(c,g,now=NOW)
        for prior in (None,replace(g,refresh_token=REFRESH+'WRONG'),replace(g,mock=False),replace(g,target=g.target.model_copy(update={'profile_version':2}))):
            with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c),now=NOW,previous=prior)
        changed=replace(c,client_secret=SECRET+'ROTATED')
        with self.assertRaises(GoogleOAuthError):refresh_request(changed,g,now=NOW)
        c,flow,request=initial()
        with self.assertRaises(GoogleOAuthError):parse_tokens(c,request,response(c),now=NOW,previous=g)
    def test_optional_refresh_expiry_remains_null_or_bounded_without_renewing_old_expiry(self):
        c,g=grant(refresh_token_expires_in=7200);self.assertEqual(g.refresh_expires_at,NOW+timedelta(hours=2))
        stamp=NOW+timedelta(hours=1);r=refresh_request(c,g,now=stamp);fresh=parse_tokens(c,r,response(c,refresh_token_expires_in=86400),now=stamp,previous=g)
        self.assertEqual(fresh.refresh_expires_at,g.refresh_expires_at)
        with self.assertRaises(GoogleOAuthError):refresh_request(c,g,now=g.refresh_expires_at)
        with self.assertRaises(GoogleOAuthError):parse_tokens(c,r,response(c),now=g.refresh_expires_at,previous=g)
        c,unknown=grant();r=refresh_request(c,unknown,now=NOW);fresh=parse_tokens(c,r,response(c),now=NOW,previous=unknown);self.assertIsNone(fresh.refresh_expires_at)

class GoogleOAuthHTTPTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):self.client,self.flow,self.request=initial(now=NOW);self.calls=[]
    def transport(self,handler=None):
        def wire(request):
            self.calls.append(request)
            return handler(request) if handler else httpx.Response(200,json=json.loads(response(self.client).body))
        return httpx.MockTransport(wire)
    async def test_default_disabled_no_transport_socket_or_secret_resolution(self):
        with patch('app.google_oauth_protocol.httpx.AsyncHTTPTransport',side_effect=AssertionError('NO DEFAULT SOCKET')):
            with self.assertRaises(GoogleOAuthError) as caught:await GoogleOAuthTokenClient().send(self.client,self.request,now=NOW)
        self.assertEqual(caught.exception.code,'GOOGLE_OAUTH_TOKEN_EXCHANGE_DISABLED');self.assertEqual(self.calls,[])
    async def test_mock_wire_fixed_https_origin_post_form_identity_response_and_no_token_query(self):
        http=GoogleOAuthTokenClient(transport=self.transport());raw=await http.send(self.client,self.request,now=NOW);g=parse_tokens(self.client,self.request,raw,now=NOW)
        self.assertEqual(len(self.calls),1);r=self.calls[0];self.assertEqual(str(r.url),TOKEN_URL);self.assertEqual(r.method,'POST');self.assertNotIn('Authorization',r.headers)
        self.assertEqual(r.headers['content-type'],'application/x-www-form-urlencoded');self.assertEqual(r.headers['accept-encoding'],'identity')
        self.assertEqual(dict(parse_qs(r.content.decode())),{k:[v] for k,v in self.request.check(self.client).items()});self.assertTrue(g.mock);self.assertFalse(g.public(self.client)['account_verified'])
    async def test_stale_operation_config_and_transport_change_refuse_before_any_wire(self):
        http=GoogleOAuthTokenClient(transport=self.transport())
        for t in (NOW-timedelta(seconds=1),NOW+timedelta(minutes=15)):
            with self.assertRaises(GoogleOAuthError):await http.send(self.client,self.request,now=t)
        with self.assertRaises(GoogleOAuthError):await http.send(replace(self.client,client_secret=SECRET+'CHANGED'),self.request,now=NOW)
        http.network_enabled=True
        with self.assertRaises(GoogleOAuthError):await http.send(self.client,self.request,now=NOW)
        self.assertEqual(self.calls,[])
    async def test_redirect_response_type_compression_dpop_and_size_never_follow_or_parse_tokens(self):
        cases=(lambda r:httpx.Response(302,headers={'location':'https://untrusted.invalid/'+REFRESH}),lambda r:httpx.Response(200,text=TOKEN),
            lambda r:httpx.Response(200,headers={'content-encoding':'gzip'},json=json.loads(response(self.client).body)),
            lambda r:httpx.Response(200,headers={'dpop-nonce':TOKEN},json=json.loads(response(self.client).body)),
            lambda r:httpx.Response(200,headers={'content-type':'application/json','content-length':'32769'},content=b'{}'),
            lambda r:httpx.Response(200,headers={'content-type':'application/json'},content=b'x'*32769))
        for handler in cases:
            count=len(self.calls)
            with self.assertRaises(GoogleOAuthError) as caught:await GoogleOAuthTokenClient(transport=self.transport(handler)).send(self.client,self.request,now=NOW)
            self.assertTrue(caught.exception.uncertain);self.assertEqual(len(self.calls),count+1);self.assertNotIn(TOKEN,str(caught.exception));self.assertNotIn(REFRESH,str(caught.exception))
    async def test_known_and_unknown_errors_make_one_attempt_never_auto_retry_or_expose_details(self):
        for mode in ('timeout','private_exception','rate-limit'):
            def handler(r):
                if mode=='timeout':raise httpx.ReadTimeout(TOKEN+' '+SECRET)
                if mode=='private_exception':raise RuntimeError(REFRESH)
                return httpx.Response(429,json={'error':'rate_limited','error_description':TOKEN})
            count=len(self.calls)
            with self.assertRaises(GoogleOAuthError) as caught:
                raw=await GoogleOAuthTokenClient(transport=self.transport(handler)).send(self.client,self.request,now=NOW);parse_tokens(self.client,self.request,raw,now=NOW)
            self.assertEqual(len(self.calls),count+1);self.assertTrue(caught.exception.uncertain);self.assertNotIn(TOKEN,str(caught.exception));self.assertNotIn(REFRESH,str(caught.exception));self.assertNotIn(SECRET,str(caught.exception))
    async def test_sensitive_transport_logs_are_filtered_only_during_request(self):
        stream=StringIO();handler=logging.StreamHandler(stream);logger=logging.getLogger('httpcore.connection');old=logger.level;logger.setLevel(logging.INFO);logger.addHandler(handler)
        try:
            def wire(r):logger.info(TOKEN+' '+REFRESH+' '+SECRET);return httpx.Response(200,json=json.loads(response(self.client).body))
            await GoogleOAuthTokenClient(transport=self.transport(wire)).send(self.client,self.request,now=NOW);logger.info('nonprivate-control-after-operation')
            value=stream.getvalue();self.assertIn('nonprivate-control-after-operation',value)
            for private in (TOKEN,REFRESH,SECRET):self.assertNotIn(private,value)
        finally:logger.removeHandler(handler);logger.setLevel(old)

    async def test_response_time_transport_or_configuration_change_never_relabels_or_returns_grant(self):
        for change in ('transport','gate','config'):
            c,flow,request=initial(now=NOW);http=None
            def wire(r):
                if change=='transport':http.transport=None
                elif change=='gate':http.network_enabled=True
                else:object.__setattr__(c,'client_secret',SECRET+'CHANGED')
                return httpx.Response(200,json=json.loads(response(c).body))
            count=len(self.calls);http=GoogleOAuthTokenClient(transport=self.transport(wire))
            with self.assertRaises(GoogleOAuthError):await http.send(c,request,now=NOW)
            self.assertEqual(len(self.calls),count+1)

    async def test_owned_tls_transport_has_no_environment_proxy_or_retry_and_fixed_timeouts(self):
        transport=self.transport()
        with patch('app.google_oauth_protocol.httpx.AsyncHTTPTransport',return_value=transport) as constructor:
            raw=await GoogleOAuthTokenClient(network_enabled=True).send(self.client,self.request,now=NOW)
        options=constructor.call_args.kwargs;self.assertIs(options['verify'],True);self.assertIs(options['trust_env'],False);self.assertIs(options['http2'],False);self.assertEqual(options['retries'],0)
        self.assertEqual(self.calls[-1].extensions['timeout'],{'connect':5.0,'read':15.0,'write':15.0,'pool':5.0});self.assertEqual(raw.status,200)
        # A constructor-only synthetic transport is not provider acceptance.
        self.assertFalse(parse_tokens(self.client,self.request,raw,now=NOW).public(self.client)['real_provider_tested'])

    async def test_stream_close_failure_is_unknown_and_restores_nonprivate_logging_context(self):
        class BrokenClose(httpx.AsyncByteStream):
            async def __aiter__(self):yield response(client()).body
            async def aclose(self):raise RuntimeError(TOKEN+' '+REFRESH)
        wire=self.transport(lambda r:httpx.Response(200,headers={'content-type':'application/json'},stream=BrokenClose()))
        with self.assertRaises(GoogleOAuthError) as caught:await GoogleOAuthTokenClient(transport=wire).send(self.client,self.request,now=NOW)
        self.assertEqual(caught.exception.code,'GOOGLE_OAUTH_NETWORK_OUTCOME_UNKNOWN');self.assertTrue(caught.exception.uncertain);self.assertNotIn(TOKEN,str(caught.exception))
        from app.publishing_wire import _sensitive
        self.assertFalse(_sensitive.get())

if __name__=='__main__':unittest.main()
