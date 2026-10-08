"""Actual signed owned HTTP; upload wire/QC/rights/capability results are fixtures."""
import json,threading,unittest
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_official_publications as review_fixture
from services.windows_native.tests import test_official_publication_worker as worker_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.access import NativeAccess
from services.windows_native.pipeline import Config
from services.windows_native.server import Handler,LocalServer
from services.windows_native.official_publication_registry import PublishingFactory
from services.windows_native.official_publication_models import Gates
from services.windows_native.contracts import WorkflowError
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.youtube_upload import UNIT
from app.publishing_wire import OfficialHTTPClient

class OfficialPublicationsHTTPTests(unittest.TestCase):
    body=review_fixture.OfficialPublicationReviewTests.body
    journal=review_fixture.OfficialPublicationReviewTests.journal
    request=access_fixture.NativeAccessHTTPTests.request
    response=worker_fixture.OfficialWorkerTests.response
    def setUp(self):
        original=review_fixture.render_fixture;content=b'EXPLICIT NONPLAYABLE SIGNED HTTP FIXTURE; NOT REAL FULL QC\n'
        content+=b'X'*(2*UNIT+17-len(content))
        with patch.object(review_fixture,'render_fixture',side_effect=lambda store:original(store,final_bytes=content)):
            review_fixture.OfficialPublicationReviewTests.setUp(self)
        self.wire=[];self.ack=0;self.processing='processed';self.privacy='private';self.mode=None
        self.client.transport.handler=self.response;self.profile=self.profile.model_copy(update={'chunk_size':UNIT})
        self.factory=PublishingFactory(self.profile,self.root,self.workspace,gates=self.factory.gates,client=self.client,resolver=lambda _:self.credential)
        self.config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'secrets'/'absent-openai',assemblyai_secret_file=self.folder/'secrets'/'absent-asr',ffmpeg_bin=self.folder/'absent-ffmpeg')
        self.pipeline=NoProviderPipeline();access=NativeAccess(self.verifier,self.workspace)
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access,
            official_account_factories={self.account_factory.account.account_ref:self.account_factory},
            official_publish_factories={self.target.profile_id:self.factory},official_publish_session_directory=self.folder/'protected-sessions')
        # Explicit synthetic platform verification copied only into this owned server.
        self.server.publications.capabilities_path=self.publications.capabilities_path
        self.server.publications.capabilities=self.publications.capabilities
        self.server.publications.capabilities_sha256=self.publications.capabilities_sha256
        self.service=self.server.official_publications;self.service.clock=lambda:self.clock[0]
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.project['id']+'/official-publications'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join()
        self.assertEqual(self.pipeline.calls,0);self.temp.cleanup()
    def account(self,role):
        self.raw,data=human_fixture(role,workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace);access.bind_root(self.root)
        self.server.access=access;self.cookie,session=access.login(self.raw);self.csrf=session.csrf
    def create_http(self,**changes):
        status,value,_=self.request('POST',self.base,self.body(**changes).model_dump(mode='json'));self.assertEqual(status,200,value);return value
    def approve_http(self,value,**changes):
        body={'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True,**changes}
        status,approved,_=self.request('POST',self.base+'/'+value['publication_id']+'/approve',body);self.assertEqual(status,200,approved);return approved
    def state_http(self,value):
        status,state,headers=self.request('GET',self.base+'/'+value['publication_id']+'/state');self.assertEqual(status,200,state);self.assertEqual(headers['Cache-Control'],'no-store');return state
    def action(self,value,action='step',**changes):
        state=self.state_http(value)
        return self.request('POST',self.base+'/'+value['publication_id']+'/'+action,{'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':state['dispatch']['version'],**changes})
    def test_signed_review_explicit_upload_processing_and_history_keep_mock_qualified(self):
        session=self.request('GET','/api/session')[1];self.assertTrue(session['capabilities']['native_official_publication_review']);self.assertFalse(session['capabilities']['native_live_publishing'])
        before=self.server.store.get(self.project['id']);status,profiles,headers=self.request('GET','/api/connections/official-publishing');self.assertEqual(status,200)
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertFalse(profiles['automatic_publishing']);self.assertEqual(profiles['session_vault']['status'],'CONFIGURED');self.assertEqual(self.wire,[])
        value=self.create_http();self.assertEqual(value['status'],'awaiting_publish_approval');self.assertIsNone(value['approval_id'])
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.wire,[])
        self.approve_http(value);old=self.state_http(value)['dispatch']['version']
        for _ in range(4):self.assertEqual(self.action(value)[0],200)
        self.assertEqual(self.action(value,expected_dispatch_version=old)[0],409)
        uploaded=self.request('GET',self.base+'/'+value['publication_id'])[1];self.assertIsNone(uploaded['receipt']);self.assertFalse(uploaded['published'])
        status,done,_=self.action(value,'poll');self.assertEqual(status,200,done);self.assertTrue(done['mock_publication_complete']);self.assertFalse(done['published'])
        page=self.request('GET',self.base+'?limit=25')[1];self.assertEqual(page['items'],[done]);self.assertFalse(page['automatic_publishing'])
        self.assertEqual(sum(row['method']=='POST' for row in self.wire),1);self.assertEqual(sum(row['method']=='PUT' for row in self.wire),3)
        self.assertEqual(len(self.wire),10);self.assertEqual(self.server.store.get(self.project['id']),before)
        public=json.dumps([profiles,done,page,self.state_http(value)]);self.assertNotIn(self.credential.token,public);self.assertNotIn('upload_id',public);self.assertNotIn(str(self.folder/'protected-sessions'),public)
        costs=self.server.official_publish_worker.costs.summary(self.project['id'])['records'];self.assertTrue(all(row['actual_cost'] is None for row in costs))
    def test_roles_csrf_and_loopback_owner_are_rejected_before_body_or_provider(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            for suffix in ('','/nopu_'+'a'*32+'/approve','/nopu_'+'a'*32+'/renew','/nopu_'+'a'*32+'/revoke','/nopu_'+'a'*32+'/cancel','/nopu_'+'a'*32+'/step','/nopu_'+'a'*32+'/poll'):
                with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body must not be read')):
                    self.assertEqual(self.request('POST',self.base+suffix,{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-publishing')[0],403)
            self.assertEqual(self.request('GET',self.base)[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):
            self.assertEqual(self.request('POST',self.base,{}, {'X-VF-CSRF':''})[0],403)
            self.assertEqual(self.request('POST',self.base+'/nopu_'+'a'*32+'/revoke',{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.wire,[])
        # Existing anonymous loopback mode has no signed publish identity.
        self.server.access=None;self.cookie=self.server.session;self.csrf=self.server.csrf
        self.assertEqual(self.request('POST',self.base,{})[0],403);self.assertFalse(self.request('GET','/api/session')[1]['capabilities']['native_official_publication_review'])
    def test_typed_snapshot_and_version_fences_cannot_accept_client_tokens_or_endpoints(self):
        body=self.body().model_dump(mode='json')
        for change in ({'revision':True},{'token':'EXPLICIT NEVER ACCEPTED'},{'endpoint':'https://untrusted.invalid'},{'mode':'live'}):
            self.assertEqual(self.request('POST',self.base,{**body,**change})[0],400)
        value=self.create_http();self.assertEqual(self.request('POST',self.base+'/'+value['publication_id']+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':1})[0],400)
        self.approve_http(value)
        for change in ({'expected_dispatch_version':True},{'token':'NEVER'},{'session_uri':'https://untrusted.invalid'},{'expected_snapshot_sha256':'f'*64}):
            self.assertIn(self.action(value,**change)[0],(400,409))
        self.assertEqual(self.wire,[])
    def test_signed_revocation_preserves_dispatch_and_stops_future_send_after_source_change(self):
        value=self.create_http();self.approve_http(value);self.assertEqual(self.action(value)[0],200)
        before=self.state_http(value);calls=len(self.wire);path=self.base+'/'+value['publication_id']+'/revoke';body={'expected_snapshot_sha256':value['snapshot_sha256']}
        self.assertEqual(self.request('POST',path,{**body,'token':'NEVER'})[0],400)
        self.assertEqual(self.request('POST',path,{'expected_snapshot_sha256':'f'*64})[0],409)
        other=self.server.store.create('Other revocation fixture','No provider')
        self.assertEqual(self.request('POST','/api/projects/'+other['id']+'/official-publications/'+value['publication_id']+'/revoke',body)[0],404)
        with self.server.store.transaction() as con:con.execute('UPDATE projects SET revision=revision+1 WHERE id=?',(self.project['id'],))
        status,stopped,_=self.request('POST',path,body);self.assertEqual(status,200,stopped);self.assertEqual(stopped['failure_code'],'NATIVE_OFFICIAL_PUBLISH_CONSENT_REVOKED')
        self.assertEqual(self.request('POST',path,body)[1],stopped);self.assertEqual(self.state_http(value),before)
        self.assertEqual(self.action(value)[0],409);self.assertEqual(len(self.wire),calls)
        with self.server.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_events WHERE action='official.publication.consent.revoked'").fetchone()[0],1)
    def test_exact_create_renewal_and_cancellation_replay_do_not_send(self):
        body=self.body().model_dump(mode='json');value=self.create_http();self.assertTrue(self.request('POST',self.base,body)[1]['idempotent_replay'])
        self.approve_http(value,valid_for_seconds=60);self.clock[0]+=timedelta(seconds=61)
        self.assertEqual(self.action(value)[0],409);self.assertEqual(self.wire,[])
        state=self.state_http(value);renew={'expected_snapshot_sha256':value['snapshot_sha256'],'expected_dispatch_version':state['dispatch']['version'],
            'acknowledged_official_publication':True,'request_key':'explicit-http-renewal-fixture-key'}
        path=self.base+'/'+value['publication_id']+'/renew';status,first,_=self.request('POST',path,renew);self.assertEqual(status,200,first)
        self.assertTrue(self.request('POST',path,renew)[1]['renewal']['replayed']);self.assertFalse(first['renewal']['replayed'])
        cancel={'expected_snapshot_sha256':value['snapshot_sha256']};path=self.base+'/'+value['publication_id']+'/cancel'
        self.assertEqual(self.request('POST',path,cancel)[1]['status'],'cancelled');self.assertEqual(self.request('POST',path,cancel)[1]['status'],'cancelled');self.assertEqual(self.wire,[])
    def test_uncertain_http_init_retains_one_init_and_never_accepts_replacement(self):
        value=self.create_http();self.approve_http(value);self.mode='init-timeout'
        status,error,_=self.action(value);self.assertEqual(status,409);self.assertNotIn('SECRET',json.dumps(error))
        self.assertEqual(self.state_http(value)['dispatch']['phase'],'init_unconfirmed')
        self.assertEqual(self.action(value)[0],409)
        self.assertEqual(self.request('POST',self.base,self.body(request_key='explicit-http-no-replacement-key').model_dump(mode='json'))[0],409)
        self.assertEqual(sum(row['method']=='POST' for row in self.wire),1)
    def test_scoped_bounded_pages_reject_malformed_foreign_cursors_and_corrupt_evidence(self):
        for i in range(3):
            value=self.create_http(request_key='explicit-http-page-fixture-'+str(i))
            self.request('POST',self.base+'/'+value['publication_id']+'/cancel',{'expected_snapshot_sha256':value['snapshot_sha256']})
        first=self.request('GET',self.base+'?limit=2')[1];self.assertEqual(len(first['items']),2);self.assertTrue(first['truncated'])
        second=self.request('GET',self.base+'?limit=2&cursor='+first['next_cursor'])[1];self.assertEqual(len(second['items']),1)
        other=self.server.store.create('Other explicit HTTP fixture','No providers');otherbase='/api/projects/'+other['id']+'/official-publications'
        self.assertEqual(self.request('GET',otherbase+'?cursor='+first['next_cursor'])[0],400)
        self.assertEqual(self.request('GET',otherbase+'/'+value['publication_id'])[0],404)
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?token=NEVER'):
            self.assertEqual(self.request('GET',self.base+query)[0],400)
        with self.server.store.transaction() as con:con.execute('UPDATE native_official_publications SET snapshot_sha256=? WHERE publication_id=?',('f'*64,value['publication_id']))
        self.assertEqual(self.request('GET',self.base)[0],409);self.assertEqual(self.wire,[])
    def test_configuration_guard_rejects_network_injection_unprotected_enablement_and_conflicts(self):
        network=PublishingFactory(self.profile,self.root,self.workspace,gates=Gates(publish_enabled=True,external_execution_enabled=True,owner_gate_enabled=True),client=OfficialHTTPClient('youtube',network_enabled=True),resolver=lambda _:self.credential)
        for changes in ({'official_publish_enabled':1},{'official_publish_enabled':True},{'official_publish_factories':{self.target.profile_id:network}},
            {'official_publish_factories':{},'official_publish_registry':self.folder/'absent-registry'}, {'official_publish_session_directory':self.root/'private'}):
            with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access,**changes)
        self.assertEqual(self.wire,[])

if __name__=='__main__':unittest.main()
