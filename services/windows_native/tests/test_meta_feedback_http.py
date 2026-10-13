"""Signed localhost feedback/Bridge over restored explicit Meta protocol fixtures."""
import http.client,json,os,tempfile,threading,unittest,uuid
from pathlib import Path
from unittest.mock import patch
from services.windows_native.backup import restore_backup
from services.windows_native.pipeline import Config
from services.windows_native.server import LocalServer,Handler
from services.windows_native.access import NativeAccess
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.contracts import digest
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_wire import OfficialHTTPClient
from app.bridge_auth import ServiceIdentity,sign_service_request
from services.windows_native.qualified_bridge_sources import CONTRACT

KEY=b'explicit-meta-feedback-service-fixture-only-001'

class MetaFeedbackHTTPFixture:
    def open(self,platform,source):
        self.platform=platform;self.F=json.loads((Path(source)/platform/'public-fixture.json').read_bytes())
        assert self.F['Owner_UAT'] is False and self.F['nonplayable_media_fixture'] is True
        assert self.F['real_provider_calls']==self.F['paid_calls']==0
        self.temp=tempfile.TemporaryDirectory(prefix='vf-meta-feedback-http-');self.folder=Path(self.temp.name);self.root=self.folder/'state'
        backup=json.loads((Path(source)/platform/'backup.json').read_bytes())
        restore_backup(backup['backup_path'],self.root,expected_sha256=backup['sha256'])
        raw,registry=human_fixture('owner',workspace=self.F['workspace_id'])
        verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400)
        config=Config(data_root=self.root,runtime_root=self.folder/'runtime',secret_file=self.folder/'private/missing.env',
            assemblyai_secret_file=self.folder/'private/missing.dpapi',ffmpeg_bin=self.folder/'missing-ffmpeg')
        self.server=LocalServer(0,config,start_worker=False,access=NativeAccess(verifier,self.F['workspace_id']))
        self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
        self.server.bridge.configure_auth({'meta-feedback-fixture':ServiceIdentity('meta-feedback-fixture',('service',),{'fixture-v1':KEY})})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.project=self.F['project']['id'];self.winner_base='/api/projects/'+self.project+'/official-winners'
        self.learning_base='/api/projects/'+self.project+'/official-learning';self.projection_base='/api/trends/learning/qualified'
    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=10);self.temp.cleanup()
    def request(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=30)
        base={'Origin':'http://127.0.0.1:'+str(self.server.server_port),'Cookie':'vf_native_session='+self.cookie,
            'X-VF-CSRF':self.csrf,'Content-Type':'application/json'}
        try:
            con.request(method,path,json.dumps(body) if body is not None else None,headers={**base,**(headers or {})})
            response=con.getresponse();return response.status,json.loads(response.read()),dict(response.getheaders())
        finally:con.close()
    def actor(self,role):
        raw,registry=human_fixture(role,workspace=self.F['workspace_id'])
        self.server.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.F['workspace_id'])
        self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
    def service_read(self,path,headers=None):
        route,_,query=path.partition('?')
        signed=headers or sign_service_request(key=KEY,service_id='meta-feedback-fixture',key_id='fixture-v1',method='GET',path=route,
            query=query,body=b'',timestamp=int(self.server.bridge.clock()),nonce='explicit-meta-'+uuid.uuid4().hex)
        return self.request('GET',path,headers=signed),signed
    def chain(self):
        request={**self.F['request'],'request_key':'explicit-meta-feedback-signed-winner'}
        status,winner,_=self.request('POST',self.winner_base,request);assert status==200,winner
        request={**self.F['learning_request'],'assessment_id':winner['assessment_id'],
            'expected_assessment_sha256':winner['snapshot_sha256'],'request_key':'explicit-meta-feedback-signed-learning'}
        status,learning,_=self.request('POST',self.learning_base,request);assert status==200,learning
        request={'project_id':self.project,'learning_id':learning['learning_id'],'expected_learning_sha256':learning['snapshot_sha256'],
            'channel_profile_ref':'ai-education-reference@1','platform':self.platform,'acknowledged_recommendation_only':True,
            'acknowledged_protocol_mock':True,'request_key':'explicit-meta-feedback-signed-projection'}
        status,projection,_=self.request('POST',self.projection_base,request);assert status==200,projection
        return winner,learning,projection


class MetaFeedbackHTTPTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):
        # The source archive is explicit evidence input, not a production data path.
        source=Path(os.environ.get('VF_META_FEEDBACK_TEST_SOURCE',
            'C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-meta-winners-contract-n3'))
        self.f=MetaFeedbackHTTPFixture();self.f.open(self.PLATFORM,source)
    def tearDown(self):self.f.close()
    def test_signed_restored_source_chain_and_service_events_keep_mock_and_no_provider_or_project_change(self):
        f=self.f;before=f.server.store.get(f.project);cost=f.server.official_analytics.costs.summary(f.project)
        with (patch.object(OfficialHTTPClient,'request',side_effect=AssertionError('Feedback cannot call provider')),
              patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('Feedback cannot decrypt'))):
            status,source,headers=f.request('GET',f.winner_base+'/source/'+f.F['analytics']['sync_id'])
            self.assertEqual(status,200,source);self.assertEqual(source,f.F['source']);self.assertEqual(headers['Cache-Control'],'no-store')
            winner,learning,projection=f.chain()
            self.assertEqual(winner['assessment']['state'],'winner_candidate' if self.PLATFORM=='instagram_reels' else 'insufficient_data')
            self.assertEqual(learning['observation_count'],6 if self.PLATFORM=='instagram_reels' else 0)
            self.assertFalse(projection['record']['payload']['automatic_application']);self.assertTrue(projection['record']['payload']['mock'])
            self.assertFalse(f.server.runner.run_one())
            self.assertEqual(f.server.bridge.harvest(),1);self.assertEqual(f.server.bridge.harvest(),0)
            (status,page,headers),_=f.service_read('/v1/events?limit=100');self.assertEqual(status,200,page)
            events=[v for v in page['items'] if v['envelope']['contract_version']==CONTRACT]
            types={v['envelope']['payload']['source_type'] for v in events}
            self.assertEqual(types,{'winner','learning','projection'})
            self.assertEqual(len(events),4 if self.PLATFORM=='instagram_reels' else 3)
            for event in events:
                p=event['envelope']['payload'];self.assertTrue(p['mock']);self.assertFalse(p['real_audience_observation'])
                self.assertFalse(p['automatic_application']);self.assertFalse(p['real_provider_acceptance'])
                self.assertEqual(event['delivery']['status'],'disabled');self.assertEqual(event['envelope_sha256'],digest(event['envelope']))
        self.assertEqual(f.server.store.get(f.project),before);self.assertEqual(f.server.official_analytics.costs.summary(f.project),cost)
    def test_roles_and_csrf_reject_all_feedback_writes_before_body_while_history_remains_readable(self):
        f=self.f
        for role in ('editor','reviewer','viewer'):
            f.actor(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Forbidden body parsed')):
                for path in (f.winner_base,f.learning_base,f.projection_base):self.assertEqual(f.request('POST',path,{})[0],403)
            self.assertEqual(f.request('GET',f.winner_base+'/'+f.F['assessment']['assessment_id'])[0],200)
            self.assertEqual(f.request('GET',f.learning_base+'/'+f.F['learning']['learning_id'])[0],200)
        f.actor('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Invalid CSRF body parsed')):
            for path in (f.winner_base,f.learning_base,f.projection_base):self.assertEqual(f.request('POST',path,{},headers={'X-VF-CSRF':'invalid'})[0],403)
    def test_service_signature_nonce_and_human_session_do_not_grant_delivery_or_duplicate_source_events(self):
        f=self.f;f.chain();self.assertEqual(f.server.bridge.harvest(),1)
        self.assertNotEqual(f.request('GET','/v1/events?limit=100')[0],200)
        (status,page,_),signed=f.service_read('/v1/events?limit=100');self.assertEqual(status,200,page)
        self.assertNotEqual(f.service_read('/v1/events?limit=100',signed)[0][0],200)
        f.chain();self.assertEqual(f.server.bridge.harvest(),0)
        (status,again,_),_=f.service_read('/v1/events?limit=100');self.assertEqual(status,200)
        self.assertEqual(again,page);self.assertFalse(f.server.bridge.delivery_enabled)


class FacebookFeedbackHTTPTests(MetaFeedbackHTTPTests):
    PLATFORM='facebook'
