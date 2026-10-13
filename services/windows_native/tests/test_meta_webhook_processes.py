"""Actual loopback receipts in an independent process; explicit Meta fixtures.

The production HTTPS transport is unchanged. A fixture transport exercises real
HTTP and fresh producer processes without allowing private production endpoints.
"""
import hashlib,http.client,json,os,shutil,subprocess,sys,time,unittest
from pathlib import Path
from unittest.mock import patch
from app.bridge_auth import SigningKeyring,canonical_json_bytes
from app.publishing_wire import OfficialHTTPClient
from services.windows_native.bridge_transport import FixtureWebhookTransport
from services.windows_native.contracts import digest
from services.windows_native.tests.test_meta_feedback_http import MetaFeedbackHTTPFixture
from services.windows_native.qualified_bridge_sources import CONTRACT

REPO=Path(__file__).resolve().parents[3]
KEYS={'fixture-v1':b'explicit-meta-webhook-fixture-key-only-001',
      'fixture-v2':b'explicit-meta-webhook-fixture-key-only-002'}


def linux_path(path):
    value=str(Path(path).resolve()).replace('\\','/')
    return '/mnt/'+value[0].lower()+value[2:] if os.name=='nt' else value


class MetaWebhookProcessesTests(unittest.TestCase):
    PLATFORM='instagram_reels'
    def setUp(self):
        source=Path(os.environ.get('VF_META_FEEDBACK_TEST_SOURCE',
            'C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/native-meta-winners-contract-n3'))
        self.f=MetaFeedbackHTTPFixture();self.f.open(self.PLATFORM,source)
        self.receiver=None;self.case=None;self.result=None;self.port=None
        self.stamp=time.time();self.f.server.bridge.clock=lambda:self.stamp
        marker={'workspace':self.f.F['workspace_id'],'nonplayable_media_fixture':True,'real_provider_calls':0,'Owner_UAT':False}
        (self.f.root/'.vf-meta-bridge-fixture.json').write_text(json.dumps(marker),encoding='utf-8')
        self.source_sha256=hashlib.sha256((source/self.PLATFORM/'public-fixture.json').read_bytes()).hexdigest()
    def stop_receiver(self):
        if self.receiver is None:return
        if self.receiver.poll() is None:
            try:
                if self.port is not None:self.http('POST','/__fixture__/stop',headers={'X-Fixture-Control':'explicit-local-receiver-fixture-control-only'})
            except (OSError,http.client.HTTPException):pass
            try:self.receiver.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.receiver.terminate();self.receiver.wait(timeout=10)
        self.receiver_stdout,self.receiver_stderr=self.receiver.communicate(timeout=5)
        self.receiver=None
    def tearDown(self):
        self.stop_receiver()
        if self.result is not None and os.environ.get('VF_META_BRIDGE_EVIDENCE_DIR'):
            folder=Path(os.environ['VF_META_BRIDGE_EVIDENCE_DIR'])/(self.PLATFORM+'-'+self.case)
            folder.mkdir(parents=True,exist_ok=False)
            db=self.receiver_root/'receiver.sqlite3'
            if db.exists():
                shutil.copyfile(db,folder/'receiver.sqlite3')
                self.result['receiver_database_sha256']=hashlib.sha256(db.read_bytes()).hexdigest()
            self.result['source_fixture_sha256']=self.source_sha256
            self.result['real_provider_calls']=self.result['paid_calls']=0
            self.result['actual_local_HTTP']=self.result['separate_receiver_process']=True
            self.result['production_HTTPS_verified']=self.result['real_Agent_Hub']=self.result['Owner_UAT']=False
            self.result['provider_identity_publication_media_are_fixtures']=True
            self.f.close();self.result['owned_roots_cleaned']=not self.f.folder.exists()
            (folder/'evidence.json').write_text(json.dumps(self.result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        else:self.f.close()
    def start_receiver(self,scenario,*,resume=False):
        self.case=scenario;self.receiver_root=self.f.folder/'independent-recipient'
        command=[str(REPO/'scripts/fixtures/agent_hub_event_receiver.py'),'--root',str(self.receiver_root),
            '--schema',str(REPO/'packages/contracts/agent-hub-qualified-feedback.v1.schema.json'),
            '--workspace',self.f.F['workspace_id'],'--scenario',scenario]
        if resume:
            self.assertEqual(self.receiver_root.parent,self.f.folder)
            self.assertIsNotNone(self.port)
            (self.receiver_root/'ready.json').unlink();command.extend(['--resume-fixture','--port',str(self.port)])
        if os.name=='nt':
            command[0]=linux_path(command[0]);command[2]=linux_path(command[2]);command[4]=linux_path(command[4])
            runtime=os.environ.get('VF_BRIDGE_RECEIVER_PYTHON','/root/vfns-ci-20261007-c1/venv/bin/python')
            command=['wsl.exe','-d',os.environ.get('VF_BRIDGE_RECEIVER_DISTRO','Ubuntu-24.04'),'--exec','env','-u','PYTHONPATH',runtime,*command]
        else:command=[sys.executable,*command]
        self.receiver=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        deadline=time.monotonic()+30
        while not (self.receiver_root/'ready.json').exists():
            if self.receiver.poll() is not None:
                out,err=self.receiver.communicate();self.fail('Receiver exited: '+err[-1000:])
            if time.monotonic()>deadline:self.fail('Receiver readiness deadline expired; process remains owned for cleanup')
            time.sleep(.05)
        ready=json.loads((self.receiver_root/'ready.json').read_bytes());self.assertTrue(ready['fixture'])
        self.port=ready['port'];self.receiver_pid=ready['pid']
    def http(self,method,path,body=None,headers=None):
        con=http.client.HTTPConnection('127.0.0.1',self.port,timeout=10)
        try:
            con.request(method,path,body=body,headers=headers or {});response=con.getresponse();raw=response.read(65537)
            return response.status,json.loads(raw) if raw else None
        finally:con.close()
    def state(self):
        status,value=self.http('GET','/__fixture__/state');self.assertEqual(status,200);return value
    def dispatch(self,*,crash=False,key_id='fixture-v1'):
        command=[sys.executable,str(REPO/'scripts/fixtures/native_meta_bridge_dispatch.py'),'--root',str(self.f.root),
            '--workspace',self.f.F['workspace_id'],'--port',str(self.port),'--clock',str(self.stamp),'--key-id',key_id]
        if crash:command.append('--crash-after-accept')
        result=subprocess.run(command,capture_output=True,text=True,timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        self.assertEqual(result.returncode,71 if crash else 0,result.stderr[-1500:])
        report=json.loads(result.stdout.strip().splitlines()[-1]);self.assertTrue(report['fixture'])
        self.assertNotEqual(report['pid'],os.getpid());return report
    def chain_and_select(self,*,all_events=False):
        f=self.f;before=f.server.store.get(f.project);cost=f.server.official_analytics.costs.summary(f.project)
        with (patch.object(OfficialHTTPClient,'request',side_effect=AssertionError('No provider')),
              patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('No decryption'))):
            f.chain();self.assertEqual(f.server.bridge.harvest(),1);self.assertEqual(f.server.bridge.harvest(),0)
        self.assertEqual(f.server.store.get(f.project),before);self.assertEqual(f.server.official_analytics.costs.summary(f.project),cost)
        events=[e for e in f.server.bridge.page(limit=100)['items'] if e['envelope']['contract_version']==CONTRACT]
        self.assertEqual(len(events),4 if self.PLATFORM=='instagram_reels' else 3)
        self.assertEqual({e['envelope']['payload']['source_type'] for e in events},{'winner','learning','projection'})
        transport=FixtureWebhookTransport(lambda *_:self.fail('Only fresh producer process may send'))
        transport.endpoint=f'fixture-http://127.0.0.1:{self.port}/agent-hub/events/v1'
        f.server.bridge.configure_delivery(transport=transport,signing=SigningKeyring('fixture-v1',KEYS),enabled=True)
        selected=events if all_events else [next(e for e in events if e['envelope']['payload']['source_type']=='projection')]
        for event in selected:
            body={'expected_envelope_sha256':event['envelope_sha256'],'expected_destination_sha256':f.server.bridge.destination(),
                'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,
                'request_key':'explicit-meta-webhook-select-'+event['envelope']['event_id'][-16:]}
            status,value,_=f.request('POST','/api/bridge/events/'+event['envelope']['event_id']+'/enqueue',body)
            self.assertEqual(status,200,value);self.assertEqual(value['selected_status'],'queued')
        self.before=before;self.cost=cost;return selected
    def assert_preserved(self):
        self.assertEqual(self.f.server.store.get(self.f.project),self.before)
        self.assertEqual(self.f.server.official_analytics.costs.summary(self.f.project),self.cost)
        self.assertFalse(self.f.server.runner.run_one())
    def test_all_meta_source_types_deliver_schema_valid_signed_local_receipts(self):
        self.start_receiver('normal');events=self.chain_and_select(all_events=True);pids=[]
        for _ in events:pids.append(self.dispatch()['pid'])
        state=self.state();self.assertEqual(len(state['events']),len(events))
        self.assertEqual({e['body_sha256'] for e in state['events']},{e['envelope_sha256'] for e in events})
        audits=[self.f.server.bridge.audit(e['envelope']['event_id']) for e in events]
        for audit in audits:
            self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual(len(audit['attempts']),1)
            self.assertEqual(audit['attempts'][0]['response_status'],204);self.assertFalse(audit['real_hub_receipt_verified'])
            self.assertTrue(audit['fixture']);self.assertFalse(audit['attempts'][0]['external_call'])
        # A correctly re-signed conflicting event ID cannot replace its receipt.
        original=events[0]['envelope'];changed={**original,'occurred_at':'2026-10-01T00:00:00+00:00'}
        body=canonical_json_bytes(changed);identity=original['event_id']
        headers=SigningKeyring('fixture-v2',KEYS).sign(body,timestamp=int(self.stamp),event_id=identity)
        headers.update({'Content-Type':'application/json','Idempotency-Key':identity})
        self.assertEqual(self.http('POST','/agent-hub/events/v1',body,headers)[0],409)
        headers['X-NPD-Signature']='0'*64
        self.assertEqual(self.http('POST','/agent-hub/events/v1',body,headers)[0],401)
        self.assertEqual(self.state()['events'],state['events']);self.assert_preserved()
        self.result={'scenario':'normal','receiver':self.state(),'producer_pids':pids,'delivery_audits':audits,
            'conflicting_body_rejected':True,'bad_HMAC_rejected':True,'core_project_and_cost_unchanged':True}
    def test_lost_reply_reuses_event_and_key_rotation_without_duplicate_acceptance(self):
        self.start_receiver('lost_response');event=self.chain_and_select()[0];identity=event['envelope']['event_id']
        first=self.dispatch();audit=self.f.server.bridge.audit(identity)
        self.assertEqual(audit['delivery']['status'],'retry_scheduled');self.assertEqual(len(self.state()['events']),1)
        recipient_before=self.state();old_pid=self.receiver_pid;self.stop_receiver();self.start_receiver('lost_response',resume=True)
        self.assertNotEqual(old_pid,self.receiver_pid);self.assertEqual(self.state()['events'],recipient_before['events'])
        self.stamp+=10;second=self.dispatch(key_id='fixture-v2');audit=self.f.server.bridge.audit(identity);state=self.state()
        self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual(len(state['events']),1)
        self.assertEqual([r['duplicate'] for r in state['requests']],[0,1]);self.assertEqual([r['status'] for r in state['requests']],[0,204])
        self.assertEqual({r['body_sha256'] for r in state['requests']},{event['envelope_sha256']})
        self.assertEqual([a['key_id'] for a in audit['attempts']],['fixture-v1','fixture-v2'])
        self.assert_preserved();self.result={'scenario':'lost_response','receiver':state,'delivery_audit':audit,
            'producer_pids':[first['pid'],second['pid']],'receiver_pids':[old_pid,self.receiver_pid],
            'receiver_dedupe_survives_process_restart':True,'same_signed_body_and_idempotency_key':True,'core_project_and_cost_unchanged':True}
    def test_producer_crash_after_recipient_commit_recovers_lease_in_new_process(self):
        self.start_receiver('normal');self.case='producer_crash';event=self.chain_and_select()[0];identity=event['envelope']['event_id']
        first=self.dispatch(crash=True);audit=self.f.server.bridge.audit(identity)
        self.assertEqual(audit['delivery']['status'],'running');self.assertIsNone(audit['attempts'][0]['response_status'])
        self.assertEqual(len(self.state()['events']),1)
        self.stamp+=121;second=self.dispatch(key_id='fixture-v2');audit=self.f.server.bridge.audit(identity);state=self.state()
        self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual(len(state['events']),1)
        self.assertEqual([r['duplicate'] for r in state['requests']],[0,1])
        self.assertEqual(audit['attempts'][0]['failure_code'],'NATIVE_BRIDGE_INTERRUPTED_RESPONSE_UNCERTAIN')
        self.assertEqual(len(audit['attempts']),2);self.assert_preserved()
        self.result={'scenario':'producer_crash','receiver':state,'delivery_audit':audit,'producer_pids':[first['pid'],second['pid']],
            'actual_producer_exit_71_after_accept':True,'lease_recovered_in_fresh_process':True,'core_project_and_cost_unchanged':True}
    def test_retry_after_and_offline_recipient_do_not_block_core(self):
        self.start_receiver('rate_limit');event=self.chain_and_select()[0];identity=event['envelope']['event_id']
        first=self.dispatch();audit=self.f.server.bridge.audit(identity)
        self.assertEqual(audit['delivery']['status'],'retry_scheduled');self.assertEqual(audit['delivery']['next_at'],self.stamp+40)
        self.stamp+=39;early=self.dispatch();self.assertIsNone(early['event_id']);self.assertEqual(len(self.state()['requests']),1)
        self.stamp+=1;second=self.dispatch();state=self.state();audit=self.f.server.bridge.audit(identity)
        self.assertEqual(audit['delivery']['status'],'succeeded');self.assertEqual([r['status'] for r in state['requests']],[429,204])
        self.stop_receiver()
        other=next(e for e in self.f.server.bridge.page(limit=100)['items']
            if e['envelope']['contract_version']==CONTRACT and e['delivery']['status']=='disabled')
        body={'expected_envelope_sha256':other['envelope_sha256'],'expected_destination_sha256':self.f.server.bridge.destination(),
            'expected_mode':'fixture','fixture_acknowledged':True,'http_acknowledged':False,
            'request_key':'explicit-meta-offline-select-'+other['envelope']['event_id'][-16:]}
        self.assertEqual(self.f.request('POST','/api/bridge/events/'+other['envelope']['event_id']+'/enqueue',body)[0],200)
        offline=self.dispatch();offline_audit=self.f.server.bridge.audit(other['envelope']['event_id'])
        self.assertEqual(offline_audit['delivery']['status'],'retry_scheduled')
        self.assertEqual(offline_audit['attempts'][0]['failure_code'],'NATIVE_BRIDGE_TRANSPORT_UNAVAILABLE')
        # Core creation succeeds while the recipient is offline. Delivery remains
        # an independent queue; no provider, render or publishing job is created.
        created=self.f.server.store.create('Explicit offline recipient fixture','Explicit local fixture text')
        self.assertEqual(created['jobs'],[]);self.assertIsNone(created['approval']);self.assert_preserved()
        self.result={'scenario':'rate_limit','receiver':state,'delivery_audit':audit,
            'offline_delivery_audit':offline_audit,'producer_pids':[first['pid'],early['pid'],second['pid'],offline['pid']],
            'no_early_retry':True,'offline_core_creation':True,
            'core_project_and_cost_unchanged':True}


class FacebookWebhookProcessesTests(MetaWebhookProcessesTests):PLATFORM='facebook'


if __name__=='__main__':unittest.main()
