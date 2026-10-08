"""Signed local service/human reads; synthetic source, no actual Hub/provider."""
import copy,json,unittest,uuid
from pathlib import Path
from services.windows_native.tests.test_qualified_learning_feedback_http import QualifiedFeedbackHTTPFixture
from services.windows_native.contracts import digest
from app.bridge_auth import ServiceIdentity,sign_service_request
from services.windows_native.qualified_bridge_sources import CONTRACT,VERSION

KEY=b'explicit-qualified-http-fixture-key-only-001'
class QualifiedBridgeHTTPTests(QualifiedFeedbackHTTPFixture,unittest.TestCase):
    def setUp(self):
        super().setUp();self.bridge=self.server.bridge
        self.bridge.configure_auth({'agent-hub-fixture':ServiceIdentity('agent-hub-fixture',('service',),{'fixture-v1':KEY})})
    def service_read(self,path):
        route,_,query=path.partition('?')
        headers=sign_service_request(key=KEY,service_id='agent-hub-fixture',key_id='fixture-v1',method='GET',path=route,query=query,body=b'',timestamp=int(self.bridge.clock()),nonce='explicit-qa-'+uuid.uuid4().hex)
        return self.request('GET',path,headers=headers)
    def test_signed_contract_and_source_events_keep_original_hash_null_mock_and_disabled_delivery(self):
        wire=self.read_wire.copy();before=self.server.store.get(self.project['id']);status,contract,headers=self.service_read('/v1/contract')
        self.assertEqual(status,200);self.assertEqual(contract['event_contract_versions'],['agent-hub-bridge.v1',CONTRACT]);self.assertFalse(contract['webhook_delivery_enabled'])
        status,page,headers=self.service_read('/v1/events?limit=25');self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store')
        events=[e for e in page['items'] if e['envelope']['contract_version']==CONTRACT];self.assertEqual(len(events),3)
        self.assertEqual({e['envelope']['payload']['source_type'] for e in events},{'analytics','winner','learning'})
        for e in events:
            p=e['envelope']['payload'];self.assertEqual(p['payload_schema_version'],VERSION);self.assertTrue(p['mock']);self.assertFalse(p['real_audience_observation']);self.assertIsNone(p['assessment_score'])
            self.assertEqual(e['delivery']['status'],'disabled');self.assertEqual(e['envelope_sha256'],digest(e['envelope']))
        self.assertNotIn('video.winner.detected',[e['envelope']['event_type'] for e in events]);self.assertEqual(self.read_wire,wire);self.assertEqual(self.server.store.get(self.project['id']),before)
    def test_human_session_does_not_grant_service_auth_and_viewer_can_read_scoped_evidence(self):
        self.assertEqual(self.request('GET','/v1/events')[0],401);self.account('viewer')
        self.assertEqual(self.request('GET','/api/bridge/events?limit=25')[0],200)
        event=self.bridge.page()['items'][0]
        self.assertEqual(self.request('POST','/api/bridge/events/'+event['envelope']['event_id']+'/enqueue',{})[0],403)
        self.assertEqual(self.request('GET','/v1/events')[0],401)
    def test_projection_harvest_is_one_immutable_new_contract_event_without_provider_dispatch(self):
        wire=self.read_wire.copy();value=self.project_feedback();self.assertEqual(self.bridge.harvest(),1);self.assertEqual(self.bridge.harvest(),0)
        status,page,_=self.service_read('/v1/events?limit=25');self.assertEqual(status,200)
        items=[e for e in page['items'] if e['envelope']['payload'].get('source_type')=='projection'];self.assertEqual(len(items),1)
        p=items[0]['envelope']['payload'];self.assertEqual(p['source_ref'],value['record']['id']);self.assertEqual(p['source_sha256'],value['record_sha256']);self.assertEqual(p['observation_count'],0)
        self.assertEqual(self.read_wire,wire);self.assertFalse(self.server.runner.wake.is_set());self.assertIsNone(self.bridge.process())
    def test_rehashed_source_qualifier_and_changed_original_read_cost_refuse_service_history(self):
        event=self.bridge.page()['items'][0];value=copy.deepcopy(event['envelope']);value['payload']['mock']=1
        with self.server.store.transaction() as con:con.execute('UPDATE native_bridge_events SET envelope_json=?,envelope_sha256=? WHERE event_id=?',(json.dumps(value),digest(value),value['event_id']))
        self.assertEqual(self.service_read('/v1/events?limit=25')[0],409)
        with self.server.store.transaction() as con:
            con.execute('UPDATE native_bridge_events SET envelope_json=?,envelope_sha256=? WHERE event_id=?',(json.dumps(event['envelope']),event['envelope_sha256'],value['event_id']))
            con.execute("UPDATE native_cost_operations SET paid=1 WHERE provider='official-youtube-analytics'")
        self.assertEqual(self.service_read('/v1/events?limit=25')[0],409)
    def test_source_contract_ui_static_bytes_and_default_disabled_enqueue(self):
        status,value,_=self.request('GET','/native-bridge.mjs');self.assertEqual(status,200)
        self.assertEqual(value,(Path(__file__).resolve().parents[3]/'apps/studio-web/native-bridge.mjs').read_bytes())
        event=self.bridge.page()['items'][0];body={'expected_envelope_sha256':event['envelope_sha256'],'expected_destination_sha256':'f'*64,'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,'request_key':'explicit-default-disabled-qualified-enqueue'}
        self.assertEqual(self.request('POST','/api/bridge/events/'+event['envelope']['event_id']+'/enqueue',body)[0],409)
        self.assertIsNone(self.bridge.process());self.assertFalse(self.bridge.delivery_enabled)

if __name__=='__main__':unittest.main()
