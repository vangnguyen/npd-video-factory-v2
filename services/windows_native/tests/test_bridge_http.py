"""Actual loopback HMAC requests; fixture keys and no Agent Hub/network calls."""
import http.client
import json
import unittest
from unittest.mock import patch
from services.windows_native.tests import test_access_http as fixture
from services.windows_native.tests.test_bridge import KEY
from app.bridge_auth import ServiceIdentity,sign_service_request,canonical_json_bytes


class NativeBridgeHTTPTests(unittest.TestCase):
    setUp=fixture.NativeAccessHTTPTests.setUp
    tearDown=fixture.NativeAccessHTTPTests.tearDown
    stop_server=fixture.NativeAccessHTTPTests.stop_server
    start_server=fixture.NativeAccessHTTPTests.start_server
    request=fixture.NativeAccessHTTPTests.request
    account=fixture.NativeAccessHTTPTests.account

    def configure(self):
        self.server.bridge.configure_auth({'hub-fixture':ServiceIdentity('hub-fixture',('service',),{'fixture-v1':KEY})})

    def service_request(self,method,path,payload=None,*,nonce='native-http-bridge-fixture-nonce-01',extra=None,body=None):
        if body is None:body=canonical_json_bytes(payload) if payload is not None else b''
        base,_,query=path.partition('?')
        headers=sign_service_request(key=KEY,service_id='hub-fixture',key_id='fixture-v1',method=method,path=base,query=query,body=body,nonce=nonce)
        headers.update({'Content-Type':'application/json',**(extra or {})})
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=5)
        connection.request(method,path,body=body if method=='POST' else None,headers=headers)
        response=connection.getresponse();value=json.loads(response.read());metadata=dict(response.getheaders());connection.close()
        return response.status,value,metadata

    def test_service_draft_is_cookie_independent_key_replay_requires_fresh_nonce_and_no_approval_routes(self):
        self.configure();self.account('viewer');before=self.server.store.get(self.project['id'])
        self.assertEqual(self.request('GET','/v1/contract')[0],401)
        status,contract,headers=self.service_request('GET','/v1/contract')
        self.assertEqual(status,200);self.assertEqual(headers['Cache-Control'],'no-store');self.assertFalse(contract['webhook_delivery_enabled'])
        body={'workspace_id':'wsp_native_fixture','name':'Private Native HTTP draft','prompt':'Private signed Native fixture',
            'niche':'technology','channel_profile_ref':'ai-education-reference@1'}
        route='/v1/projects';options={'Idempotency-Key':'native-http-bridge-create-key'}
        status,first,_=self.service_request('POST',route,body,nonce='native-http-create-nonce-fixture01',extra=options)
        self.assertEqual(status,201);self.assertFalse(first['execution_started']);self.assertFalse(first['external_action'])
        self.assertEqual(self.service_request('POST',route,body,nonce='native-http-create-nonce-fixture01',extra=options)[0],401)
        status,replay,_=self.service_request('POST',route,body,nonce='native-http-create-nonce-fixture02',extra=options)
        self.assertEqual(status,200);self.assertTrue(replay['idempotent_replay']);self.assertEqual(first['project_id'],replay['project_id'])
        status,events,_=self.service_request('GET','/v1/events?limit=1',nonce='native-http-page-nonce-fixture001')
        self.assertEqual(status,200);self.assertEqual(len(events['items']),1)
        self.assertNotIn('Private signed Native fixture',json.dumps(events))
        status,audit,_=self.service_request('GET','/v1/events/'+events['items'][0]['envelope']['event_id']+'/delivery',nonce='native-http-audit-nonce-fixture001')
        self.assertEqual(status,200);self.assertEqual(audit['delivery']['status'],'disabled');self.assertFalse(audit['real_hub_receipt_verified'])
        self.assertEqual(self.service_request('POST','/v1/projects/'+first['project_id']+'/approve',{},nonce='native-http-noapproval-fixture001')[0],404)
        self.assertEqual(self.server.store.get(first['project_id'])['jobs'],[]);self.assertIsNone(self.server.store.get(first['project_id'])['approval'])
        status,summary,_=self.service_request('GET','/v1/projects/'+first['project_id'],nonce='native-http-summary-fixture001')
        self.assertEqual(status,200);self.assertFalse(summary['current_human_approval']);self.assertIsNone(summary['latest_job'])
        self.assertNotIn('Private signed Native fixture',json.dumps(summary))
        self.assertEqual(self.server.store.get(self.project['id']),before)

    def test_default_unconfigured_foreign_workspace_body_tamper_duplicate_json_and_origin_host_guards(self):
        self.assertEqual(self.service_request('GET','/v1/contract')[0],503);self.configure()
        body={'workspace_id':'wsp_foreign_fixture','name':'Fixture','prompt':'Private fixture'}
        self.assertEqual(self.service_request('POST','/v1/projects',body,extra={'Idempotency-Key':'native-http-wrong-workspace-key'})[0],403)
        self.assertEqual(self.service_request('GET','/v1/contract',nonce='native-http-host-nonce-fixture001',extra={'Host':'evil.invalid'})[0],403)
        self.assertEqual(self.service_request('GET','/v1/contract',nonce='native-http-origin-nonce-fixture01',extra={'Origin':'https://evil.invalid'})[0],403)
        self.assertEqual(self.service_request('GET','/v1/contract',nonce='native-http-crosssite-fixture0001',extra={'Sec-Fetch-Site':'cross-site'})[0],403)
        self.assertEqual(self.service_request('GET','/v1/events?limit=1&limit=2',nonce='native-http-duplicate-query00001')[0],400)
        self.assertEqual(self.service_request('POST','/v1/projects',nonce='native-http-duplicate-json000001',body=b'{"name":"one","name":"two"}',extra={'Idempotency-Key':'native-http-duplicate-json-key'})[0],400)
        self.assertEqual(self.service_request('POST','/v1/projects',nonce='native-http-invalid-mac-fixture01',body=b'{"invalid":true}',extra={'X-NPD-Signature':'0'*64})[0],401)
        self.assertEqual(self.service_request('GET','/v1/contract',nonce='native-http-contract-fixture001',extra={'X-NPD-Contract-Version':'v2'})[0],400)
        with self.server.store.transaction() as con:self.assertEqual(con.execute('SELECT count(*) FROM native_bridge_requests').fetchone()[0],0)


if __name__=='__main__':unittest.main()
