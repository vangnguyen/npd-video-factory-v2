"""Actual human role/CSRF/operator selection contracts; no external delivery."""
import unittest
from unittest.mock import patch
from services.windows_native.server import Handler
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.tests.test_bridge import KEY
from services.windows_native.bridge_transport import FixtureWebhookTransport,BridgeResponse
from app.bridge_auth import SigningKeyring


class NativeBridgeOperatorHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def selected(self):
        page=self.request('GET','/api/bridge/events?limit=25')[1];row=next(r for r in page['items'] if r['delivery']['status']=='disabled')
        bridge=self.server.bridge;bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(204)),
            signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY}),enabled=True)
        return row,{'expected_envelope_sha256':row['envelope_sha256'],'expected_destination_sha256':bridge.destination(),
            'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,'request_key':'native-bridge-human-select-fixture-key'}

    def test_owner_selects_exact_event_without_network_and_can_cancel_after_config_disabled(self):
        before=self.server.store.get(self.project['id']);row,body=self.selected();identity=row['envelope']['event_id'];base='/api/bridge/events/'+identity
        status,result,headers=self.request('POST',base+'/enqueue',body)
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(result['actor_ref'],'explicit-fixture')
        self.assertEqual(result['selected_status'],'queued');self.assertFalse(result['external_call_performed'])
        again=self.request('POST',base+'/enqueue',body)[1];self.assertTrue(again['idempotent_replay']);self.assertEqual(result['request_sha256'],again['request_sha256'])
        self.server.bridge.delivery_enabled=False
        cancelled=self.request('POST',base+'/cancel',{**body,'fixture_acknowledged':False,'request_key':'native-bridge-human-cancel-fixture-key'})
        self.assertEqual(cancelled[0],200);self.assertEqual(cancelled[1]['selected_status'],'cancelled')
        self.assertIsNone(self.server.bridge.process())
        audit=self.request('GET',base+'/delivery')[1];self.assertEqual(audit['delivery']['status'],'cancelled');self.assertEqual(audit['attempts'],[])
        self.assertEqual(len(audit['operator_receipts']),2);self.assertEqual(self.server.store.get(self.project['id']),before)
        self.assertTrue(self.request('GET','/api/session')[1]['capabilities']['native_bridge_operator'])
        self.assertEqual(self.request('GET','/native-bridge.mjs')[0],200)

    def test_viewer_editor_reviewer_cannot_select_before_body_and_default_state_cannot_enable_http(self):
        row,body=self.selected();base='/api/bridge/events/'+row['envelope']['event_id']
        for role in ('viewer','editor','reviewer'):
            self.account(role);self.assertEqual(self.request('GET','/api/bridge/events')[0],200)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized operator body must not be read')):
                self.assertEqual(self.request('POST',base+'/enqueue',body)[0],403)
        self.account('owner');self.server.bridge.delivery_enabled=False
        self.assertEqual(self.request('POST',base+'/enqueue',body)[0],409)
        self.assertEqual(self.request('POST','/api/bridge/enable',{'enabled':True})[0],403)
        state=self.request('GET','/api/bridge/state')[1];self.assertFalse(state['webhook_delivery_enabled']);self.assertFalse(state['http_enablement_from_ui'])
        self.assertFalse(state['live_publishing_enabled']);self.assertEqual(self.server.bridge.audit(row['envelope']['event_id'])['operator_receipts'],[])

    def test_csrf_origin_stale_hash_destination_ack_and_changed_key_conflict_hold(self):
        row,body=self.selected();base='/api/bridge/events/'+row['envelope']['event_id']
        self.assertEqual(self.request('POST',base+'/enqueue',body,{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('POST',base+'/enqueue',body,{'Origin':'https://evil.invalid'})[0],403)
        for changed,expected in [({'expected_envelope_sha256':'0'*64},409),({'expected_destination_sha256':'0'*64},409),
            ({'fixture_acknowledged':False},400),({'http_acknowledged':True},400),({'fixture_acknowledged':1},400),({'enabled':True},400)]:
            self.assertEqual(self.request('POST',base+'/enqueue',{**body,**changed})[0],expected)
        self.assertEqual(self.request('POST',base+'/enqueue',body)[0],200)
        self.assertEqual(self.request('POST',base+'/cancel',{**body,'fixture_acknowledged':False})[0],409)
        audit=self.request('GET',base+'/delivery')[1];self.assertEqual(len(audit['operator_receipts']),1);self.assertEqual(audit['attempts'],[])
        self.assertEqual(self.request('GET','/api/bridge/events?limit=1&limit=2')[0],400)


if __name__=='__main__':unittest.main()
