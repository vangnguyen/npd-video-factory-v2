"""Actual signed local HTTP; TikTok responses and final media are explicit mocks."""
import json,threading,unittest
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.pipeline import Config
from services.windows_native.contracts import WorkflowError
from services.windows_native.tests.test_tiktok_creators import TikTokCreatorFixture,TOKEN
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native import tiktok_connection as connection

class TikTokCreatorsHTTPTests(TikTokCreatorFixture,unittest.TestCase):
    request=access_fixture.NativeAccessHTTPTests.request
    def setUp(self):
        super().setUp();self.pipeline=NoProviderPipeline()
        self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'private'/'absent.env',assemblyai_secret_file=self.folder/'private'/'absent.dpapi',ffmpeg_bin=self.folder/'absent-ffmpeg')
        access=NativeAccess(self.verifier,self.workspace)
        with patch.object(connection,'load_token',side_effect=AssertionError('HTTP startup must not decrypt')):
            self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access,tiktok_creator_factories={self.target.profile_id:self.factory},tiktok_creator_reads_enabled=True)
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.store=self.server.store;self.service=self.server.tiktok_creators;self.base='/api/projects/'+self.project['id']+'/tiktok-creators'
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5);self.assertEqual(self.pipeline.calls,0);super().tearDown()
    def account(self,role):
        raw,data=human_fixture(role,workspace=self.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        access.bind_root(self.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
    def check_http(self):
        status,value,headers=self.request('POST',self.base+'/checks',self.body().model_dump(mode='json'));self.assertEqual(status,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value
    def test_signed_prepare_fetch_choices_draft_and_history_never_upload(self):
        before=self.store.get(self.project['id']);value=self.check_http();self.assertEqual(self.wire,[])
        path=self.base+'/checks/'+value['check_id'];status,result,_=self.request('POST',path+'/fetch',{'expected_snapshot_sha256':value['snapshot_sha256']});self.assertEqual(status,200,result)
        self.assertEqual(result['status'],'succeeded');self.assertEqual(len(self.wire),2);self.assertEqual(self.request('GET',path)[1],result)
        status,draft,_=self.request('POST',self.base+'/drafts',self.draft_body(result).model_dump(mode='json'));self.assertEqual(status,200,draft);self.assertFalse(draft['publishing_enabled']);self.assertTrue(draft['publish_approval_required'])
        replay=self.request('POST',self.base+'/drafts',self.draft_body(result).model_dump(mode='json'))[1];self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['draft_id'],draft['draft_id'])
        self.assertEqual(self.request('GET',self.base+'/drafts/'+draft['draft_id'])[1],{k:v for k,v in draft.items() if k!='idempotent_replay'})
        self.assertEqual(self.request('GET',self.base+'/drafts')[1]['items'][0]['draft_id'],draft['draft_id']);self.assertEqual(len(self.wire),2);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertNotIn(TOKEN,json.dumps([draft,result]));self.assertFalse(self.server.official_publish_queue.enabled)
    def test_owner_and_csrf_are_required_before_body_for_every_action(self):
        for role in ('viewer','editor','reviewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body must not be read')):
                for suffix in ('/checks','/checks/ntcr_'+'a'*32+'/fetch','/checks/ntcr_'+'a'*32+'/cancel','/drafts'):
                    self.assertEqual(self.request('POST',self.base+suffix,{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/tiktok-creators')[0],403)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('No missing CSRF body')):self.assertEqual(self.request('POST',self.base+'/checks',{},headers={'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.wire,[])
    def test_discovery_pages_and_foreign_namespaces_never_load_private_token(self):
        value=self.check_http()
        with patch.object(connection,'load_token',side_effect=AssertionError('History must not decrypt')):
            status,runtime,_=self.request('GET','/api/connections/tiktok-creators');self.assertEqual(status,200,runtime);self.assertFalse(runtime['publication_dispatch_supported'])
            self.assertEqual(self.request('GET',self.base+'/checks?limit=1')[0],200)
            for suffix in ('?limit=0','?limit=101','?cursor=ntpd_'+'f'*32,'?limit=1&limit=2','?unknown=1'):
                self.assertEqual(self.request('GET',self.base+'/checks'+suffix)[0],400)
            other=self.store.create('Foreign','No providers');self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/tiktok-creators/checks/'+value['check_id'])[0],404)
        self.assertEqual(self.wire,[])
    def test_numeric_consent_or_private_transport_fields_are_rejected(self):
        for change in ({'acknowledged_creator_read':1},{'acknowledged_protocol_mock':1},{'token':TOKEN},{'url':'https://foreign.invalid'},{'publishing_enabled':True}):
            self.assertEqual(self.request('POST',self.base+'/checks',self.body().model_dump(mode='json')|change)[0],400)
        self.assertEqual(self.wire,[])
    def test_current_owner_revocation_is_refused_before_body(self):
        data=self.server.access.verifier.registry.model_dump(mode='json');data['tokens'][self.principal.token_id]['enabled']=False
        self.server.access.verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400)
        with patch.object(Handler,'read_body',side_effect=AssertionError('Revoked Owner body must not be read')):self.assertEqual(self.request('POST',self.base+'/checks',{},headers={})[0],403)
        self.assertEqual(self.wire,[])
    def test_disabled_restart_reads_history_without_creating_or_replaying_provider(self):
        value=self.check_http();self.server.shutdown();self.server.server_close();self.thread.join()
        with patch.object(connection,'load_token',side_effect=AssertionError('Cold disabled restart must not decrypt')):
            self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access)
            self.assertIsNotNone(self.server.tiktok_creators);self.assertFalse(self.server.tiktok_creators.states()['enabled'])
            self.assertEqual(self.server.tiktok_creators.get(self.project['id'],value['check_id'])['check_id'],value['check_id']);self.assertEqual(self.server.tiktok_creators.recover(),0)
        self.cookie,session=self.server.access.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.assertEqual(self.wire,[])
    def test_raw_gate_missing_auth_and_real_client_injection_reject_before_socket(self):
        for change in ({'tiktok_creator_reads_enabled':1},{'tiktok_creator_reads_enabled':True},
            {'tiktok_creator_factories':{self.target.profile_id:connection.NativeTikTokFactory(self.binding,self.root,self.workspace,owner_read_enabled=True)}}):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access,**change)

if __name__=='__main__':unittest.main()
