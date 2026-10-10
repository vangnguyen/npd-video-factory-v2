"""Actual signed loopback Meta account API; all platform/Owner results mocked."""
import json, subprocess, sys, threading, unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
import httpx
from app.human_identity import HumanAuthRegistry, HumanAuthVerifier
from app.meta_publishing_credentials import REQUIRED
from app.publishing_models import PublishingTargetBinding
from services.windows_native.access import NativeAccess
from services.windows_native.server import Handler, LocalServer
from services.windows_native import meta_connection as meta
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests import test_phase10_http as fixture, test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as identity


class MetaAccountsHTTPTests(unittest.TestCase):
    setUp=fixture.Phase10HTTPTests.setUp;tearDown=fixture.Phase10HTTPTests.tearDown;stop_server=fixture.Phase10HTTPTests.stop_server
    request=access_fixture.NativeAccessHTTPTests.request;account=access_fixture.NativeAccessHTTPTests.account

    def start_server(self):
        self.raw,data=identity('owner');self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),'wsp_native_fixture')
        self.calls=[];self.factories={};self.secret_paths=[];self.mock_token='META-EXPLICIT-SIGNED-HTTP-MOCK-ONLY-1234567890'
        self.transport=httpx.MockTransport(self.response)
        for letter,platform,target_id in (('a','facebook','12345'),('b','instagram_reels','23456')):
            target=PublishingTargetBinding(workspace_id=self.auth.workspace_id,profile_id='ppf_http_'+platform,profile_version=1,platform=platform,
                provider_key={'facebook':'facebook-graph-api-publishing','instagram_reels':'instagram-graph-api-publishing'}[platform],
                target_account_id=target_id,credential_binding_sha256=letter*64)
            profile=meta.Profile(target=target,page_id='12345',api_version='v24.0');path=self.config.data_root.parent/'meta-private'/('http-'+platform+'.dpapi');self.secret_paths.append(path)
            meta.save_token(path,self.config.data_root,{'profile':profile.model_dump(mode='json'),'credential_alias':'meta-http-fixture',
                'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),'scopes':sorted(REQUIRED[platform]),'token':self.mock_token})
            binding=meta.Binding(account_ref='npac_'+letter*32,profile=profile,credential_alias='meta-http-fixture',token_file=str(path),read_enabled=True)
            self.factories[binding.account_ref]=meta.NativeMetaAccountFactory(binding,self.config.data_root,self.auth.workspace_id,owner_read_enabled=True,transport=self.transport)
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,meta_account_factories=self.factories,meta_account_read_enabled=True)
        self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()

    def response(self,request):
        self.calls.append((request.method,request.url.path))
        return httpx.Response(200,json={'id':'12345','instagram_business_account':{'id':'23456'}} if request.url.path.endswith('/me') else {'id':'23456'})

    def body(self,account_ref='npac_'+'b'*32,**changes):
        return {'revision':self.project['revision'],'expected_configuration_sha256':self.server.official_accounts.factories[account_ref].sha256,
            'acknowledged_read_only':True,'request_key':'explicit-meta-signed-http-fixture-key',**changes}

    def url(self,account_ref='npac_'+'b'*32):
        return '/api/projects/'+self.project['id']+'/official-accounts/'+account_ref+'/verify'

    def test_signed_owner_intents_share_history_worker_costs_without_media_or_publication(self):
        before=self.server.store.get(self.project['id']);status,states,_=self.request('GET','/api/connections/official-accounts');self.assertEqual(status,200)
        self.assertEqual(len(states['accounts']),2);self.assertEqual(self.calls,[])
        for account_ref in self.factories:
            status,value,_=self.request('POST',self.url(account_ref),self.body(account_ref,request_key='explicit-meta-'+account_ref));self.assertEqual(status,200)
            self.assertEqual(value['status'],'queued');result=self.server.official_accounts.process(project=self.project['id'],identity=value['check_id'],fingerprint=value['request_fingerprint'])
            self.assertEqual(result['status'],'succeeded');status,history,_=self.request('GET','/api/projects/'+self.project['id']+'/account-checks/'+value['check_id'])
            self.assertEqual(status,200);self.assertEqual(history,result);self.assertFalse(result['result']['meta']['provider_permissions_verified'])
            status,replay,_=self.request('POST',self.url(account_ref),self.body(account_ref,request_key='explicit-meta-'+account_ref));self.assertEqual(status,200);self.assertTrue(replay['idempotent_replay'])
        self.assertEqual(self.calls,[('GET','/v24.0/me'),('GET','/v24.0/me'),('GET','/v24.0/23456')]);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertEqual(len(self.server.official_accounts.costs.summary(self.project['id'])['records']),3);self.assertEqual(self.pipeline.calls,0)
        self.assertEqual(self.server.official_publications.factories,{});self.assertFalse(self.server.official_publish_queue.enabled)

    def test_roles_and_csrf_reject_before_body_and_viewer_reads_public_history(self):
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body must not be read')):
                self.assertEqual(self.request('POST',self.url(),self.body())[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-accounts')[0],403)
            self.assertEqual(self.request('GET','/api/projects/'+self.project['id']+'/account-checks')[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):
            self.assertEqual(self.request('POST',self.url(),self.body(),{'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.calls,[])

    def test_bad_scope_secret_raw_ack_and_private_endpoint_body_are_never_admitted(self):
        for change in ({'revision':True},{'acknowledged_read_only':1},{'token':'never accepted'},{'page_id':'99999'},{'api_version':'v1.0'},{'endpoint':'https://untrusted.invalid'}):
            self.assertEqual(self.request('POST',self.url(),self.body(**change))[0],400)
        self.assertEqual(self.request('POST',self.url(),self.body(expected_configuration_sha256='f'*64))[0],409)
        self.assertEqual(self.request('POST',self.url(),self.body(revision=self.project['revision']-1))[0],409)
        self.assertEqual(self.calls,[])

    def test_disabled_flag_clones_mock_bindings_to_inert_state_without_decrypt(self):
        self.stop_server()
        with patch.object(meta,'load_token',side_effect=AssertionError('No startup secret read')):
            self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,meta_account_factories=self.factories)
            self.assertTrue(all(f.public()['status']=='NOT_CONFIGURED' for f in self.server.official_accounts.factories.values()))
        self.cookie,session=self.auth.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        status,value,_=self.request('POST',self.url(),self.body());self.assertEqual(status,200);self.assertEqual(value['status'],'not_configured')
        self.assertIsNone(self.server.official_accounts.process());self.assertEqual(self.calls,[])

    def test_mock_injection_and_registry_flags_require_exact_human_workspace_root_and_explicit_version(self):
        with self.assertRaisesRegex(WorkflowError,'HUMAN_AUTH_REQUIRED'):
            LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,meta_account_factories=self.factories)
        with self.assertRaisesRegex(WorkflowError,'HUMAN_AUTH_REQUIRED'):
            LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,meta_account_read_enabled=True)
        registry=self.config.data_root.parent/'meta-private'/'registry.json'
        registry.write_text(json.dumps({'schema_version':'native-meta-account-registry-v1','version':1,'workspace_id':self.auth.workspace_id,
            'accounts':[f.account.model_dump(mode='json') for f in self.factories.values()]}),encoding='utf8')
        with patch.object(meta,'load_token',side_effect=AssertionError('No protected registry startup decrypt')):
            cold=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,meta_account_registry=registry)
            try:self.assertTrue(all(f.public()['status']=='NOT_CONFIGURED' for f in cold.official_accounts.factories.values()))
            finally:cold.server_close()
        registry.write_text(json.dumps({'schema_version':'native-meta-account-registry-v1','workspace_id':self.auth.workspace_id,'accounts':[]}),encoding='utf8')
        with self.assertRaisesRegex(WorkflowError,'REGISTRY_INVALID'):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.auth,meta_account_registry=registry)
        result=subprocess.run([sys.executable,'-m','services.windows_native.server','--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0);self.assertIn('--meta-account-registry',result.stdout);self.assertIn('--enable-meta-account-reads',result.stdout)
        self.assertEqual(self.calls,[])

    def test_meta_configuration_does_not_become_youtube_analytics_or_publish_factory(self):
        state=self.server.official_analytics.states();self.assertEqual(state['accounts'],[])
        self.assertEqual(self.server.official_publications.factories,{});self.assertEqual(self.server.official_accounts.states()['supported_read_contracts'],['youtube','tiktok','facebook','instagram_reels'])
        self.assertFalse(self.server.official_publish_queue.enabled);self.assertEqual(self.calls,[])
