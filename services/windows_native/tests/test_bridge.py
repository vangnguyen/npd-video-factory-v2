"""Real owned SQLite/replay/delivery contracts; no Hub or paid provider calls."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from services.windows_native.store import Store
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.bridge import NativeBridge,VERSION
from services.windows_native.bridge_transport import BridgeResponse,FixtureWebhookTransport,HTTPSWebhookTransport
from services.windows_native.intelligence_store import IntelligenceStore
from app.bridge_auth import ServiceIdentity,SigningKeyring,sign_service_request,canonical_json_bytes


KEY=b'fixture-key-only-not-a-production-secret-001'
KEY2=b'fixture-key-only-not-a-production-secret-002'
WORKSPACE='wsp_native_bridge_fixture'


class NativeBridgeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'state'
        self.store=Store(self.root);self.stamp=[1791410400.0]
        self.bridge=NativeBridge(self.store,workspace_id=WORKSPACE,clock=lambda:self.stamp[0])
        self.identities={'agent-hub-fixture':ServiceIdentity('agent-hub-fixture',('service',),{'fixture-v1':KEY,'fixture-v2':KEY2})}
        self.bridge.configure_auth(self.identities)
        self.signing=SigningKeyring('fixture-v1',{'fixture-v1':KEY,'fixture-v2':KEY2})
        self.request={'workspace_id':WORKSPACE,'name':'Private fixture name','prompt':'Private fixture prompt','niche':'technology',
            'channel_profile_ref':'ai-education-reference@1'}

    def tearDown(self):self.temp.cleanup()

    def signed(self,nonce='native-bridge-fixture-nonce-0001',body=b'',method='GET',path='/v1/contract',query='',key=KEY,key_id='fixture-v1',timestamp=None):
        return sign_service_request(key=key,service_id='agent-hub-fixture',key_id=key_id,method=method,path=path,query=query,
            body=body,timestamp=int(self.stamp[0]) if timestamp is None else timestamp,nonce=nonce)

    def principal(self,nonce='native-bridge-fixture-nonce-0001'):
        return self.bridge.authenticate('GET','/v1/contract','',b'',self.signed(nonce))

    def events(self):return self.bridge.page(limit=100)['items']

    def test_draft_atomic_unapproved_replay_frozen_profile_and_no_core_job(self):
        old=self.store.create('Unrelated fixture','Private existing text');before=self.store.get(old['id'])
        service=self.principal();first=self.bridge.draft(service,self.request,'native-bridge-fixture-create-key')
        project=self.store.get(first['project_id']);self.assertEqual(project['revision'],1);self.assertIsNone(project['approval']);self.assertEqual(project['jobs'],[])
        self.assertEqual(project['document']['niche'],'technology');self.assertEqual(project['document']['channel_profile']['profile']['profile_ref'],'ai-education-reference@1')
        self.assertEqual(first['document_sha256'],digest(project['document']));self.assertEqual(self.store.versions(project['id'])[0]['document'],project['document'])
        with patch('services.windows_native.channel_profiles.select',side_effect=AssertionError('Replay must not resolve current catalog')):
            again=self.bridge.draft(service,self.request,'native-bridge-fixture-create-key')
        self.assertTrue(again['idempotent_replay']);self.assertEqual(first['project_id'],again['project_id']);self.assertEqual(self.store.get(old['id']),before)
        exported=json.dumps(self.events());self.assertNotIn('Private fixture prompt',exported);self.assertNotIn('Private fixture name',exported)
        self.assertTrue(all(x['delivery']['status']=='disabled' for x in self.events()))

    def test_concurrent_draft_key_one_project_and_changed_key_conflict(self):
        service=self.principal()
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.bridge.draft(service,self.request,'native-bridge-concurrent-create-key'),range(2)))
        self.assertEqual(len({r['project_id'] for r in results}),1);self.assertEqual(sum(r['idempotent_replay'] for r in results),1)
        with self.assertRaises(WorkflowError) as error:self.bridge.draft(service,{**self.request,'prompt':'Changed private fixture'},'native-bridge-concurrent-create-key')
        self.assertEqual(error.exception.code,'NATIVE_BRIDGE_IDEMPOTENCY_CONFLICT')
        self.assertEqual(len(self.events()),1)

    def test_draft_failures_roll_back_project_history_event_receipt(self):
        service=self.principal()
        with patch.object(self.store,'version',side_effect=RuntimeError('Explicit commit interruption')):
            with self.assertRaises(RuntimeError):self.bridge.draft(service,self.request,'native-bridge-failed-create-key')
        with self.store.transaction() as con:
            for table in ('projects','project_versions','events','native_bridge_events','native_bridge_requests'):
                self.assertEqual(con.execute('SELECT count(*) FROM '+table).fetchone()[0],0)
        for payload in ({**self.request,'workspace_id':'wsp_foreign_fixture'},{**self.request,'start_pipeline':True},
            {**self.request,'publish_requested':True},{**self.request,'external_action_requested':True},
            {**self.request,'owner_approved':True},{**self.request,'start_pipeline':'false'},{**self.request,'niche':'real_estate'}):
            with self.assertRaises(WorkflowError):self.bridge.draft(service,payload,'native-bridge-invalid-create-key')
        self.assertEqual(self.events(),[])

    def test_media_draft_preserves_core_separate_source_input_guard(self):
        service=self.principal()
        result=self.bridge.draft(service,{**self.request,'input_kind':'media','prompt':''},'native-bridge-media-draft-fixture-key')
        project=self.store.get(result['project_id']);self.assertEqual(project['document']['input_kind'],'media');self.assertEqual(project['document']['prompt'],'')
        self.assertEqual(project['jobs'],[]);self.assertIsNone(project['approval'])
        with self.assertRaises(WorkflowError):self.bridge.draft(service,{**self.request,'input_kind':'media'},'native-bridge-bad-media-fixture-key')

    def test_hmac_exact_body_method_path_query_time_key_and_persistent_nonce(self):
        body=canonical_json_bytes(self.request);headers=self.signed(body=body,method='POST',path='/v1/projects',query='limit=1')
        for method,path,query,raw in [('GET','/v1/projects','limit=1',body),('POST','/v1/contract','limit=1',body),
            ('POST','/v1/projects','limit=2',body),('POST','/v1/projects','limit=1',body+b' ')]:
            with self.assertRaises(WorkflowError):self.bridge.authenticate(method,path,query,raw,headers)
        self.bridge.authenticate('POST','/v1/projects','limit=1',body,headers)
        fresh=NativeBridge(Store(self.root),workspace_id=WORKSPACE,clock=lambda:self.stamp[0]);fresh.configure_auth(self.identities)
        with self.assertRaises(WorkflowError) as error:fresh.authenticate('POST','/v1/projects','limit=1',body,headers)
        self.assertEqual(error.exception.code,'SERVICE_AUTH_REPLAY')
        self.assertEqual(fresh.authenticate('GET','/v1/contract','',b'',self.signed('native-bridge-key-rotation-nonce',key=KEY2,key_id='fixture-v2')).key_id,'fixture-v2')
        with self.assertRaises(WorkflowError):fresh.authenticate('GET','/v1/contract','',b'',self.signed('native-bridge-expired-request-nonce',timestamp=int(self.stamp[0])-301))

    def test_concurrent_auth_replay_one_winner_and_roles_cannot_be_owner(self):
        headers=self.signed()
        def attempt(_):
            try:self.bridge.authenticate('GET','/v1/contract','',b'',headers);return True
            except WorkflowError:return False
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(attempt,range(2))),1)
        with self.assertRaises(WorkflowError):self.bridge.configure_auth({'x':ServiceIdentity('x',('service','owner'),{'x':KEY})})

    def test_default_off_offline_hub_does_not_break_core_and_capture_rolls_back_with_mutation(self):
        with patch.object(HTTPSWebhookTransport,'send',side_effect=AssertionError('No default HTTP calls')):
            created=self.store.create('Offline fixture','Private source');self.assertIsNone(self.bridge.process())
        before=self.events()
        with self.assertRaises(RuntimeError):
            with self.store.transaction() as con:
                self.store.event(con,created['id'],'human_content_approved',{'reviewer':'PRIVATE REVIEWER','note':'PRIVATE NOTE'})
                raise RuntimeError('Fixture rollback')
        self.assertEqual(before,self.events())
        with self.assertRaises(WorkflowError):self.bridge.enqueue(before[0]['envelope']['event_id'])

    def test_signed_fixture_delivery_retry_receiver_dedupe_and_five_attempt_cap(self):
        self.store.create('Fixture','Private fixture');identity=self.events()[0]['envelope']['event_id'];calls=[];seen=set()
        def receiver(body,headers):
            value=json.loads(body);calls.append((body,headers))
            self.assertEqual(headers['Idempotency-Key'],identity)
            self.assertTrue(self.signing.verify(body,key_id=headers['X-NPD-Key-Id'],timestamp=int(headers['X-NPD-Timestamp']),
                event_id=identity,signature=headers['X-NPD-Signature']))
            if len(calls)==1:seen.add(value['event_id']);raise TimeoutError('Fixture ambiguous acknowledged response')
            seen.add(value['event_id']);return BridgeResponse(204)
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=self.signing,enabled=True)
        self.bridge.enqueue(identity);self.bridge.process();self.assertEqual(self.bridge.audit(identity)['delivery']['status'],'retry_scheduled')
        self.assertIsNone(self.bridge.process());self.stamp[0]+=5;self.bridge.process()
        self.assertEqual(calls[0][0],calls[1][0]);self.assertEqual(len(seen),1)
        audit=self.bridge.audit(identity);self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual(len(audit['attempts']),2)
        self.assertFalse(audit['real_hub_receipt_verified']);self.assertTrue(audit['fixture']);self.assertTrue(all(a['external_call']==0 for a in audit['attempts']))
        self.bridge.enqueue(identity);self.assertIsNone(self.bridge.process())
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(503)),signing=self.signing,enabled=True)
        self.store.create('Five retries','Fixture');second=self.events()[-1]['envelope']['event_id']
        for _ in range(5):self.bridge.process();self.stamp[0]+=4000
        self.assertEqual(self.bridge.audit(second)['delivery']['attempts'],5);self.assertEqual(self.bridge.audit(second)['delivery']['status'],'failed')

    def test_running_lease_restart_same_body_id_and_stale_completion_fence(self):
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(200)),signing=self.signing,enabled=True)
        self.store.create('Crash fixture','Fixture');identity=self.events()[0]['envelope']['event_id']
        with self.store.transaction() as con:
            con.execute("UPDATE native_bridge_deliveries SET status='running',attempts=1,lease_until=?,claim_id='expired-fixture' WHERE event_id=?",(self.stamp[0]-1,identity))
        self.bridge.process();audit=self.bridge.audit(identity)
        self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual(audit['delivery']['attempts'],2)
        with self.store.transaction() as con:
            self.assertEqual(con.execute("UPDATE native_bridge_deliveries SET status='failed' WHERE event_id=? AND claim_id='expired-fixture'",(identity,)).rowcount,0)

    def test_key_rotation_retry_429_backoff_permanent_4xx_and_http_owner_guard(self):
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(429,120)),signing=self.signing,enabled=True)
        self.store.create('429','Fixture');identity=self.events()[0]['envelope']['event_id'];self.bridge.process()
        self.assertEqual(self.bridge.audit(identity)['delivery']['next_at'],self.stamp[0]+120)
        self.stamp[0]+=120
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(400)),signing=SigningKeyring('fixture-v2',self.signing.keys),enabled=True)
        self.bridge.process();audit=self.bridge.audit(identity);self.assertEqual(audit['delivery']['status'],'failed');self.assertEqual(audit['attempts'][-1]['key_id'],'fixture-v2')
        transport=HTTPSWebhookTransport('https://hub.example.test/agent-hub/events/v1',approved_host='hub.example.test')
        with self.assertRaises(WorkflowError):self.bridge.configure_delivery(transport=transport,signing=self.signing,enabled=True)
        self.bridge.configure_delivery(transport=transport,signing=self.signing);self.assertFalse(self.bridge.delivery_enabled)

    def test_content_free_and_digest_scope_tampering_rejected(self):
        value=self.bridge.envelope('video.project.created','fixture:1',{'project_id':'a'*32},'2026-10-08T00:00:00+00:00')
        for data in ({'nested':{'secret':'PRIVATE'}},{'nested':{'prompt':'PRIVATE'}},{'text':'Bearer PRIVATE'}, {'score':float('nan')}):
            with self.assertRaises(WorkflowError):self.bridge.validate({**value,'payload':{**value['payload'],**data}})
        with self.store.transaction() as con:self.bridge.put(con,value)
        altered=deepcopy(value);altered['payload']['workspace_id']='wsp_foreign_fixture'
        with self.store.transaction() as con:con.execute('UPDATE native_bridge_events SET envelope_json=?,envelope_sha256=?',(json.dumps(altered),digest(altered)))
        with self.assertRaises(WorkflowError):self.bridge.page()

    def test_bounded_scope_pages_cursor_and_destination_change_not_retargeted(self):
        for i in range(4):self.store.create('Fixture '+str(i),'Private fixture')
        first=self.bridge.page(limit=2);second=self.bridge.page(limit=2,cursor=first['next_cursor'])
        self.assertFalse({x['sequence'] for x in first['items']} & {x['sequence'] for x in second['items']})
        for limit in (0,101,True):
            with self.assertRaises(WorkflowError):self.bridge.page(limit=limit)
        for cursor in ('invalid','e30',base64_cursor(['wsp_foreign_fixture',1])):
            with self.assertRaises(WorkflowError):self.bridge.page(cursor=cursor)
        identity=first['items'][0]['envelope']['event_id']
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(lambda b,h:BridgeResponse(200)),signing=self.signing,enabled=True)
        self.bridge.enqueue(identity)
        transport=HTTPSWebhookTransport('https://hub.example.test/agent-hub/events/v1',approved_host='hub.example.test')
        self.bridge.configure_delivery(transport=transport,signing=self.signing,enabled=True,owner_http_enabled=True)
        with patch.object(transport,'send',side_effect=AssertionError('Never retarget queued events')):self.bridge.process()
        self.assertEqual(self.bridge.audit(identity)['delivery']['status'],'failed')

    def test_intelligence_source_outbox_atomic_cursor_offline_restart_no_backfill(self):
        intelligence=IntelligenceStore(self.root);self.bridge.attach_intelligence(intelligence)
        value={'id':'a'*32,'version':1,'updated_at':'2026-10-08T00:00:00+00:00','supporting_signals':['b'*32],
            'status':'NEW','opportunity_score':65.0,'private':'Private research fixture'}
        with self.assertRaises(RuntimeError):
            with intelligence.transaction() as con:
                self.bridge.capture_intelligence(con,'Opportunity',value);raise RuntimeError('Fixture source rollback')
        self.assertEqual(self.bridge.harvest(),0)
        with intelligence.transaction() as con:self.bridge.capture_intelligence(con,'Opportunity',value)
        with patch.object(self.bridge,'put',side_effect=RuntimeError('Fixture harvest interruption')):
            with self.assertRaises(RuntimeError):self.bridge.harvest()
        self.assertEqual(self.events(),[]);self.assertEqual(self.bridge.harvest(),1);self.assertEqual(self.bridge.harvest(),0)
        event=self.events()[0]['envelope'];self.assertEqual(event['event_type'],'trend.opportunity.detected');self.assertFalse(event['payload']['global_platform_metrics_verified'])
        self.assertNotIn('Private research fixture',json.dumps(event))
        fresh=NativeBridge(Store(self.root),workspace_id=WORKSPACE);fresh.attach_intelligence(IntelligenceStore(self.root))
        self.assertEqual(fresh.harvest(),0);self.assertEqual(fresh.page()['items'][0]['envelope'],event)

    def test_actual_intelligence_service_writes_source_events_with_private_evidence_excluded(self):
        from services.windows_native.intelligence_service import IntelligenceService
        from services.windows_native.pipeline import Config
        from services.windows_native.research import PublicWebResearchProvider
        from services.windows_native.tests.test_intelligence_workflow import FixtureIdeas
        from services.windows_native.tests.test_intelligence_engines import receipt
        service=IntelligenceService(Config(data_root=self.root),self.store,
            research_provider=PublicWebResearchProvider(self.root/'research-sources',fetch=lambda url:receipt()),idea_provider=FixtureIdeas())
        self.bridge.attach_intelligence(service.store)
        bundle=service.create('Explicit fixture research','ai-education',['https://example.com/test'])
        for action in ('research','ideas'):
            service.enqueue(bundle['run']['id'],bundle['run']['version'],action,uuid_fixture())
            self.assertTrue(service.run_one());bundle=service.bundle(bundle['run']['id'])
            self.assertEqual(bundle['operations'][0]['status'],'SUCCEEDED')
        self.assertGreater(self.bridge.harvest(),0)
        types={row['envelope']['event_type'] for row in self.events()}
        self.assertTrue({'trend.opportunity.detected','idea.shortlist.ready'}<=types)
        self.assertEqual(self.bridge.harvest(),0)

    def test_native_publication_analytics_and_winner_events_keep_fixture_qualification(self):
        from services.windows_native.tests.test_publications import render_fixture,CAPABILITIES
        from services.windows_native.publications import NativePublications
        from services.windows_native.publication_models import NativePublicationCreate,NativePublishApproval
        from services.windows_native.analytics import NativeAnalytics
        from services.windows_native.analytics_models import NativeAnalyticsRequest
        project,job=render_fixture(self.store);before=self.store.get(project['id'])
        publications=NativePublications(self.store,CAPABILITIES,workspace_id=WORKSPACE)
        value,_=publications.create(project['id'],NativePublicationCreate(revision=project['revision'],final_job_id=job['id'],platform='youtube',
            metadata={'title':'EXPLICIT MOCK BRIDGE FIXTURE'},request_key='native-bridge-publication-fixture-key'),actor='fixture-editor')
        publications.approve(project['id'],value['publication_id'],NativePublishApproval(expected_fingerprint=value['request_fingerprint'],
            expected_artifact_sha256=value['snapshot']['final_sha256'],acknowledged=True),actor='fixture-owner')
        completed=publications.process();self.assertEqual(completed['status'],'dry_run_succeeded')
        analytics=NativeAnalytics(self.store,publications)
        sync,_=analytics.create(project['id'],NativeAnalyticsRequest(publication_id=value['publication_id'],provider_mode='fixture',
            fixture_acknowledged=True,fixture_profile='winner_candidate',request_key='native-bridge-analytics-winner-fixture-key'),actor='fixture-owner')
        analytics.process();self.assertEqual(analytics.get(project['id'],sync['sync_id'])['status'],'succeeded')
        relevant={row['envelope']['event_type']:row['envelope']['payload'] for row in self.events()}
        self.assertTrue({'video.render.completed','video.publish.completed','video.analytics.updated','video.winner.detected'}<=set(relevant))
        self.assertFalse(relevant['video.publish.completed']['actual_external_publication']);self.assertIsNone(relevant['video.publish.completed']['remote_post_id'])
        self.assertTrue(relevant['video.analytics.updated']['mock']);self.assertFalse(relevant['video.winner.detected']['real_audience_observation'])
        self.assertFalse(relevant['video.winner.detected']['channel_baseline_verified']);self.assertEqual(self.store.get(project['id']),before)

    def test_https_only_exact_path_and_public_address_no_redirect_or_secret_response(self):
        for endpoint in ('http://hub.example.test/agent-hub/events/v1','https://other.example.test/agent-hub/events/v1',
            'https://hub.example.test:8443/agent-hub/events/v1','https://u:p@hub.example.test/agent-hub/events/v1',
            'https://hub.example.test/agent-hub/events/v1?q=1','https://hub.example.test/other'):
            with self.assertRaises(WorkflowError):HTTPSWebhookTransport(endpoint,approved_host='hub.example.test')
        transport=HTTPSWebhookTransport('https://hub.example.test/agent-hub/events/v1',approved_host='hub.example.test')
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('127.0.0.1',443))]):
            with self.assertRaises(WorkflowError):transport.send(b'{}',{})

    def test_external_registry_scope_duplicate_keys_and_disabled_http_no_secret_in_state(self):
        import base64
        registry=Path(self.temp.name)/'explicit-external-fixture-registry.json'
        raw={'version':1,'native_workspace_id':WORKSPACE,'service_identities':{'hub-fixture':{'roles':['service'],
            'keys':{'fixture-v1':base64.b64encode(KEY).decode()}}},'webhook_signing':{'active_key_id':'fixture-v1',
            'keys':{'fixture-v1':base64.b64encode(KEY).decode()}},'destination':{'endpoint':'https://hub.example.test/agent-hub/events/v1','approved_host':'hub.example.test'}}
        registry.write_text(json.dumps(raw),encoding='utf-8');self.bridge.load_auth_registry(registry)
        self.bridge.load_webhook_registry(registry);self.assertFalse(self.bridge.delivery_enabled);self.assertEqual(self.bridge.transport.mode,'http')
        self.assertEqual(self.bridge.identities['hub-fixture'].roles,('service',))
        inside=self.root/'fixture-registry.json';inside.write_text(json.dumps(raw),encoding='utf-8')
        with self.assertRaises(WorkflowError):self.bridge.load_auth_registry(inside)
        registry.write_text('{"version":1,"version":1}',encoding='utf-8')
        with self.assertRaises(WorkflowError):self.bridge.load_auth_registry(registry)
        raw['native_workspace_id']='wsp_foreign_fixture';registry.write_text(json.dumps(raw),encoding='utf-8')
        with self.assertRaises(WorkflowError):self.bridge.load_auth_registry(registry)
        with self.store.transaction() as con:
            dump='\n'.join(con.iterdump());self.assertNotIn(base64.b64encode(KEY).decode(),dump);self.assertNotIn(KEY.decode(),dump)

    def test_http_wire_contract_is_mock_tested_and_pins_public_ip_with_hostname_tls(self):
        from unittest.mock import MagicMock
        transport=HTTPSWebhookTransport('https://hub.example.test/agent-hub/events/v1',approved_host='hub.example.test')
        response=MagicMock();response.status=302;response.read.return_value=b'PRIVATE RESPONSE NEVER STORED';response.getheader.return_value='7'
        connection=MagicMock();connection.getresponse.return_value=response
        with patch('socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443))]),patch('http.client.HTTPSConnection',return_value=connection) as factory:
            result=transport.send(b'{"explicit_mock":true}',{'Idempotency-Key':'fixture-event'})
        self.assertEqual(result,BridgeResponse(302,7));self.assertEqual(factory.call_args.args,('hub.example.test',443))
        self.assertEqual(connection.request.call_args.args,('POST','/agent-hub/events/v1'));connection.close.assert_called_once()
        with patch('socket.create_connection',return_value='MOCK SOCKET') as connect:
            self.assertEqual(connection._create_connection(('untrusted.invalid',443),10),'MOCK SOCKET')
        self.assertEqual(connect.call_args.args,(('8.8.8.8',443),10,None))

    def test_webhook_worker_offline_does_not_hold_media_store_or_force_network_when_disabled(self):
        import threading,time
        from services.windows_native.observability import Observer
        entered=threading.Event();release=threading.Event()
        def receiver(body,headers):entered.set();release.wait(2);raise TimeoutError('Explicit offline fixture')
        self.bridge.configure_delivery(transport=FixtureWebhookTransport(receiver),signing=self.signing,enabled=True)
        self.store.create('Pending fixture','Private fixture');self.bridge.start(Observer())
        try:
            self.assertTrue(entered.wait(1));started=time.monotonic();created=self.store.create('Core continues','Private fixture')
            self.assertLess(time.monotonic()-started,1);self.assertEqual(self.store.get(created['id'])['jobs'],[])
        finally:release.set();self.bridge.close()


def base64_cursor(value):
    import base64
    return base64.urlsafe_b64encode(json.dumps(value).encode()).decode().rstrip('=')


def uuid_fixture():
    import uuid
    return uuid.uuid4().hex


if __name__=='__main__':unittest.main()
