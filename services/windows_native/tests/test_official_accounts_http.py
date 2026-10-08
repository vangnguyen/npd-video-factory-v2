"""Signed owned HTTP account verification; official wire results are fixtures."""
import json,threading,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
import httpx
from services.windows_native.tests import test_phase10_http as fixture,test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity
from services.windows_native.access import NativeAccess
from services.windows_native.server import Handler,LocalServer
from services.windows_native.official_account_registry import Account,AccountFactory
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_models import PublishingTargetBinding
from app.analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS

class OfficialAccountsHTTPTests(unittest.TestCase):
    setUp=fixture.Phase10HTTPTests.setUp;tearDown=fixture.Phase10HTTPTests.tearDown;stop_server=fixture.Phase10HTTPTests.stop_server
    request=access_fixture.NativeAccessHTTPTests.request;account=access_fixture.NativeAccessHTTPTests.account
    def start_server(self):
        self.raw,data=identity('owner');auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_fixture')
        self.target=PublishingTargetBinding(workspace_id=auth.workspace_id,profile_id='ppf_explicit_fixture',profile_version=1,platform='youtube',
            provider_key='youtube-data-api-publishing',target_account_id='UC_EXPLICIT_FIXTURE',credential_binding_sha256='a'*64)
        self.profile=Account(account_ref='npac_'+'a'*32,target=self.target,credential_alias='youtube-fixture-read',token_file=str(self.config.data_root.parent/'secrets'/'oauth-fixture.dpapi'),read_enabled=True)
        self.credential=AnalyticsOAuthCredential(self.target,datetime.now(timezone.utc)+timedelta(hours=1),frozenset({YT_READ,YT_ANALYTICS}),'EXPLICIT-ONLY-FIXTURE-TOKEN-0123456789')
        self.calls=[]
        def response(request):self.calls.append(request.method);return httpx.Response(200,json={'items':[{'id':self.target.target_account_id}]})
        self.factory=AccountFactory(self.profile,self.config.data_root,auth.workspace_id,owner_read_enabled=True,transport=httpx.MockTransport(response),resolver=lambda _:self.credential)
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=auth,official_account_factories={self.profile.account_ref:self.factory})
        self.cookie,session=auth.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def body(self,**changes):
        return {'revision':self.project['revision'],'expected_configuration_sha256':self.factory.sha256,'acknowledged_read_only':True,
            'request_key':'explicit-signed-account-http-fixture',**changes}
    def url(self):return '/api/projects/'+self.project['id']+'/official-accounts/'+self.profile.account_ref+'/verify'
    def test_owner_explicit_check_worker_history_and_exact_retry_never_invoke_production(self):
        before=self.server.store.get(self.project['id']);status,states,headers=self.request('GET','/api/connections/official-accounts');self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(states['accounts'][0]['mode'],'fixture');self.assertFalse(states['publishing_enabled']);self.assertEqual(self.calls,[])
        status,check,_=self.request('POST',self.url(),self.body());self.assertEqual(status,200,check);self.assertEqual(check['status'],'queued')
        self.assertTrue(self.server.runner.run_one());self.assertEqual(self.calls,['GET']);self.assertEqual(self.pipeline.calls,0)
        base='/api/projects/'+self.project['id']+'/account-checks';status,finished,_=self.request('GET',base+'/'+check['check_id']);self.assertEqual(status,200)
        self.assertEqual(finished['status'],'succeeded');self.assertFalse(finished['result']['external_call']);self.assertFalse(finished['result']['publishing_enabled'])
        self.assertEqual(self.request('GET',base)[1]['items'],[finished]);self.assertEqual(self.request('POST',self.url(),self.body())[1]['status'],'succeeded')
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.calls,['GET']);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertNotIn(self.credential.token,json.dumps(finished));self.assertNotIn(str(self.config.data_root.parent/'secrets'),json.dumps(finished))
    def test_non_owner_and_missing_csrf_are_rejected_before_reading_or_dispatching(self):
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body must not be read')):
                self.assertEqual(self.request('POST',self.url(),self.body())[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-accounts')[0],403)
            self.assertEqual(self.request('GET','/api/projects/'+self.project['id']+'/account-checks')[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):
            self.assertEqual(self.request('POST',self.url(),self.body(),{'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.calls,[]);self.assertEqual(self.server.official_accounts.page(self.project['id'])['items'],[])
    def test_unconfigured_stale_malformed_and_foreign_reads_do_not_invoke_a_provider(self):
        for changes in [{'revision':True},{'acknowledged_read_only':1},{'token':'never accepted'},{'endpoint':'https://untrusted.invalid'}]:
            self.assertEqual(self.request('POST',self.url(),self.body(**changes))[0],400)
        self.assertEqual(self.request('POST',self.url(),self.body(revision=self.project['revision']-1))[0],409)
        self.assertEqual(self.request('POST',self.url(),self.body(expected_configuration_sha256='b'*64))[0],409)
        status,check,_=self.request('POST',self.url(),self.body());self.assertEqual(status,200)
        other=self.server.store.create('Other explicit fixture','No providers')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/account-checks/'+check['check_id'])[0],404)
        self.assertEqual(self.request('GET','/api/connections/official-accounts?token=never')[0],400)
        self.assertEqual(self.request('GET','/api/projects/'+self.project['id']+'/account-checks?limit=1&limit=2')[0],400)
        self.assertEqual(self.calls,[])
    def test_pagination_cursor_is_scoped_and_only_explicit_requests_create_checks(self):
        for i in range(3):self.assertEqual(self.request('POST',self.url(),self.body(request_key='explicit-http-account-page-fixture-'+str(i)))[0],200)
        base='/api/projects/'+self.project['id']+'/account-checks';first=self.request('GET',base+'?limit=2')[1];self.assertEqual(len(first['items']),2);self.assertTrue(first['truncated'])
        second=self.request('GET',base+'?limit=2&cursor='+first['next_cursor'])[1];self.assertEqual(len(second['items']),1);self.assertIsNone(second['next_cursor'])
        self.assertEqual(len({c['check_id'] for c in first['items']+second['items']}),3)
        other=self.server.store.create('Other explicit fixture','No providers');self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/account-checks?cursor='+first['next_cursor'])[0],400)
        self.assertEqual(self.calls,[])
    def test_each_fresh_signed_owner_check_dispatches_once_with_its_own_cost_record(self):
        before=self.server.store.get(self.project['id']);completed=[]
        for index in range(2):
            body=self.body(request_key='explicit-fresh-signed-owner-check-'+str(index));status,queued,_=self.request('POST',self.url(),body);self.assertEqual(status,200)
            self.assertTrue(self.server.runner.run_one());status,value,_=self.request('GET','/api/projects/'+self.project['id']+'/account-checks/'+queued['check_id'])
            self.assertEqual(status,200);self.assertEqual(value['status'],'succeeded');completed.append(value)
            replay=self.request('POST',self.url(),body)[1];self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['check_id'],value['check_id'])
            self.assertFalse(self.server.runner.run_one());self.assertEqual(len(self.calls),index+1)
        self.assertNotEqual(completed[0]['result']['cost_operation_id'],completed[1]['result']['cost_operation_id'])
        costs=self.server.official_accounts.costs.summary(self.project['id'])['records'];self.assertEqual(len(costs),2);self.assertTrue(all(row['actual_cost'] is None for row in costs))
        self.assertEqual(self.pipeline.calls,0);self.assertEqual(self.server.store.get(self.project['id']),before)
