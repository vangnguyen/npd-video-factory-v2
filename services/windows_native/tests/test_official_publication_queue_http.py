"""Signed finite queue routes/Runner; protected runtime and wire are mock fixtures."""
import json,unittest
from pathlib import Path
from datetime import timedelta
from unittest.mock import patch
from services.windows_native.tests import test_official_publications_http as fixture_module
from services.windows_native.server import LocalServer,Handler
from services.windows_native.official_publication_queue import QueueCreate
from services.windows_native.contracts import WorkflowError

class OfficialQueueHTTPTests(unittest.TestCase):
    body=fixture_module.OfficialPublicationsHTTPTests.body
    journal=fixture_module.OfficialPublicationsHTTPTests.journal
    response=fixture_module.OfficialPublicationsHTTPTests.response
    request=fixture_module.OfficialPublicationsHTTPTests.request
    account=fixture_module.OfficialPublicationsHTTPTests.account
    create_http=fixture_module.OfficialPublicationsHTTPTests.create_http
    approve_http=fixture_module.OfficialPublicationsHTTPTests.approve_http
    state_http=fixture_module.OfficialPublicationsHTTPTests.state_http
    tearDown=fixture_module.OfficialPublicationsHTTPTests.tearDown
    def setUp(self):
        with patch.object(fixture_module,'LocalServer',side_effect=lambda *args,**options:LocalServer(*args,**options,official_publish_queue_enabled=True)):
            fixture_module.OfficialPublicationsHTTPTests.setUp(self)
        self.queue=self.server.official_publish_queue;self.value=self.create_http();self.approve_http(self.value)
        self.queue_base=self.base+'/'+self.value['publication_id']+'/queue'
    def queue_body(self,**changes):
        return QueueCreate.model_validate({'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':self.state_http(self.value)['dispatch']['version'],
            'acknowledged_background_steps':True,'max_steps':10,'interval_seconds':30,'start_at':self.clock[0],'deadline':self.clock[0]+timedelta(seconds=600),
            'request_key':'explicit-signed-queue-http-fixture',**changes}).model_dump(mode='json')
    def create_queue(self,body=None):
        status,value,_=self.request('POST',self.queue_base,body or self.queue_body());self.assertEqual(status,200,value);return value
    def test_runtime_flag_and_separate_approval_queue_only_one_step_per_due_runner_call(self):
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.wire,[])
        status,runtime,headers=self.request('GET','/api/connections/official-publish-queue');self.assertEqual(status,200);self.assertTrue(runtime['enabled']);self.assertFalse(runtime['default_enabled']);self.assertEqual(headers['Cache-Control'],'no-store')
        before=self.server.store.get(self.project['id']);plan=self.create_queue();self.assertEqual(self.wire,[]);self.assertTrue(self.server.runner.wake.is_set())
        for _ in range(5):
            self.assertTrue(self.server.runner.run_one());self.assertFalse(self.server.runner.run_one());self.clock[0]+=timedelta(seconds=30)
        status,done,headers=self.request('GET',self.queue_base+'/'+plan['plan_id']);self.assertEqual(status,200);self.assertEqual(done['status'],'completed');self.assertEqual(done['step_count'],5);self.assertEqual(headers['Cache-Control'],'no-store')
        self.assertTrue(done['steps'][-1]['result']['mock_publication_complete']);self.assertFalse(done['steps'][-1]['result']['published']);self.assertEqual(len(self.wire),10)
        self.assertEqual(self.server.store.get(self.project['id']),before);self.assertNotIn('upload_id',json.dumps(done));self.assertNotIn(self.credential.token,json.dumps(done))
    def test_roles_and_csrf_are_enforced_before_queue_body_or_provider(self):
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('Unauthorized body must not be read')):
                self.assertEqual(self.request('POST',self.queue_base,{})[0],403)
                self.assertEqual(self.request('POST',self.queue_base+'/nopq_'+'a'*32+'/cancel',{})[0],403)
            self.assertEqual(self.request('GET','/api/connections/official-publish-queue')[0],403);self.assertEqual(self.request('GET',self.queue_base)[0],200)
        self.account('owner')
        with patch.object(Handler,'read_body',side_effect=AssertionError('Missing CSRF body must not be read')):self.assertEqual(self.request('POST',self.queue_base,{}, {'X-VF-CSRF':''})[0],403)
        self.assertEqual(self.wire,[])
    def test_typed_payload_idempotent_replay_scope_and_queue_cancel_preserve_grant(self):
        body=self.queue_body()
        for changes in ({'acknowledged_background_steps':1},{'max_steps':True},{'token':'NEVER'},{'enabled':True},{'endpoint':'https://untrusted.invalid'}):self.assertEqual(self.request('POST',self.queue_base,{**body,**changes})[0],400)
        plan=self.create_queue(body);self.assertTrue(self.request('POST',self.queue_base,body)[1]['idempotent_replay']);self.assertEqual(self.request('POST',self.queue_base,{**body,'max_steps':11})[0],409)
        other=self.server.store.create('Foreign signed queue fixture','No provider')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/official-publications/'+self.value['publication_id']+'/queue/'+plan['plan_id'])[0],404)
        self.assertEqual(self.request('GET',self.base+'/nopu_'+'f'*32+'/queue/'+plan['plan_id'])[0],404)
        path=self.queue_base+'/'+plan['plan_id']+'/cancel';cancel={'expected_policy_sha256':plan['policy_sha256']}
        self.assertEqual(self.request('POST',path,{'expected_policy_sha256':'f'*64})[0],409)
        first=self.request('POST',path,cancel)[1];self.assertEqual(first['status'],'cancelled');self.assertEqual(self.request('POST',path,cancel)[1],first)
        self.assertFalse(self.server.runner.run_one());self.assertEqual(self.wire,[])
        with self.server.store.transaction() as con:self.assertEqual(con.execute("SELECT count(*) FROM native_official_publish_approvals WHERE status='active'").fetchone()[0],1)
    def test_bounded_scoped_pages_and_invalid_cursors_are_rejected(self):
        for i in range(3):
            plan=self.create_queue(self.queue_body(request_key='explicit-http-queue-page-'+str(i)))
            self.request('POST',self.queue_base+'/'+plan['plan_id']+'/cancel',{'expected_policy_sha256':plan['policy_sha256']})
        first=self.request('GET',self.queue_base+'?limit=2')[1];self.assertEqual(len(first['items']),2);self.assertTrue(first['truncated'])
        second=self.request('GET',self.queue_base+'?limit=2&cursor='+first['next_cursor'])[1];self.assertEqual(len(second['items']),1)
        for query in ('?limit=0','?limit=101','?limit=1&limit=2','?cursor=[]','?token=NEVER'):
            self.assertEqual(self.request('GET',self.queue_base+query)[0],400)
        other=self.server.store.create('Other queue page fixture','No provider')
        self.assertEqual(self.request('GET','/api/projects/'+other['id']+'/official-publications/'+self.value['publication_id']+'/queue?cursor='+first['next_cursor'])[0],400)
        self.assertEqual(self.wire,[])
    def test_restart_orders_local_worker_recovery_before_queue_recovery_and_thread_start(self):
        events=[]
        with (patch.object(self.server.store,'recover',side_effect=lambda:events.append('store')),patch.object(self.server.official_accounts,'recover',side_effect=lambda:events.append('account')),
            patch.object(self.server.official_publish_worker,'recover',side_effect=lambda:events.append('publication-worker')),patch.object(self.queue,'recover',side_effect=lambda:events.append('queue')),
            patch.object(self.server.runner.thread,'start',side_effect=lambda:events.append('thread'))):
            self.server.runner.start()
        self.assertEqual(events,['store','account','publication-worker','queue','thread']);self.assertEqual(self.wire,[])
    def test_invalid_runtime_enablement_is_refused_before_socket_allocation(self):
        for options in ({'official_publish_queue_enabled':1},{'official_publish_queue_enabled':True},{'official_publish_queue_enabled':True,'access':self.server.access}):
            with patch('services.windows_native.server.ThreadingHTTPServer.__init__',side_effect=AssertionError('Unsafe socket must not be allocated')):
                with self.assertRaises(WorkflowError):LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,**options)
        self.assertEqual(self.wire,[])
    def test_default_runtime_refuses_queue_creation_and_never_consumes_publication_approval(self):
        with LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=self.server.access) as disabled:
            self.assertFalse(disabled.official_publish_queue.states()['enabled']);self.assertFalse(disabled.runner.run_one())
            with self.assertRaisesRegex(WorkflowError,'NOT_ENABLED'):
                disabled.official_publish_queue.create(self.project['id'],self.value['publication_id'],QueueCreate.model_validate(self.queue_body()),principal=self.principal)
        self.assertEqual(self.wire,[])
    def test_queue_studio_bytes_are_served_and_reuse_shot_review_shell(self):
        root=Path(__file__).resolve().parents[3]
        for name in ('native-official-publication-queue.mjs','native-official-publications.mjs','native.mjs','native.html','shot-studio.mjs'):
            status,value,_=self.request('GET','/'+name);self.assertEqual(status,200);self.assertEqual(value,(root/'apps/studio-web'/name).read_bytes())
        self.assertEqual(self.wire,[])
