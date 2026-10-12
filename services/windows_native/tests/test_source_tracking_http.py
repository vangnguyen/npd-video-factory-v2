"""Signed local queue boundaries; no external provider or render approval."""
import http.client,json,threading,unittest,uuid
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests.test_human_identity import fixture as human
from services.windows_native.tests import test_source_preview as source_fixture


class TrackingHTTPTests(unittest.TestCase):
    save_analysis=source_fixture.NativeSourcePreviewTests.save_analysis
    real_source=source_fixture.NativeSourcePreviewTests.real_source
    def setUp(self):
        source_fixture.NativeSourcePreviewTests.setUp(self);self.real_source();self.workspace='wsp_subject_tracking_http'
        raw,registry=human('editor',workspace=self.workspace);self.auth=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=self.auth.login(raw);self.csrf=session.csrf;self.server=LocalServer(0,self.config,start_worker=False,access=self.auth)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();source_fixture.NativeSourcePreviewTests.tearDown(self)
    def body(self):
        state=self.project['document']['canonical_timeline'];return {'revision':self.project['revision'],'kind':'source_tracking','request_key':uuid.uuid4().hex,
            'tracking_request':{'expected_version':state['version'],'analysis_id':state['snapshot']['metadata']['source_analysis_id'],
                'configuration':{'seed_box':{'x':.2,'y':.25,'width':.2,'height':.25}}}}
    def request(self,body,**headers):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10);connection.request('POST','/api/projects/'+self.project['id']+'/jobs',json.dumps(body),
            headers={'Content-Type':'application/json','Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,**headers});response=connection.getresponse();value=json.loads(response.read());status=response.status;connection.close();return status,value
    def test_editor_queue_exact_replay_and_changed_region_conflict_do_not_edit_timeline(self):
        before=self.store.get(self.project['id']);body=self.body();code,job=self.request(body);self.assertEqual(code,200,job)
        self.assertEqual(job['kind'],'source_tracking');self.assertEqual(job['snapshot']['tracking_request']['configuration']['seed_box']['x'],.2)
        self.assertEqual(self.request(body)[1]['id'],job['id']);body['tracking_request']['configuration']['seed_box']['x']=.4;self.assertEqual(self.request(body)[0],409)
        current=self.store.get(self.project['id']);self.assertEqual(current['document'],before['document']);self.assertEqual(current['approval'],before['approval'])
    def test_auth_csrf_origin_and_viewer_reject_before_mutation_or_body_read(self):
        before=self.store.get(self.project['id']);body=self.body()
        with patch.object(Handler,'read_body',side_effect=AssertionError('AUTH BEFORE BODY')):self.assertEqual(self.request(body,Cookie='')[0],401)
        self.assertEqual(self.request(body,**{'X-VF-CSRF':'wrong'})[0],403);self.assertEqual(self.request(body,Origin='https://wrong.example')[0],403)
        raw,registry=human('viewer',workspace=self.workspace);viewer=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(registry),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=viewer.login(raw);self.csrf=session.csrf;self.server.access=viewer
        with patch.object(Handler,'read_body',side_effect=AssertionError('VIEWER BEFORE BODY')):self.assertEqual(self.request(body)[0],403)
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_invalid_region_and_stale_timeline_create_no_jobs(self):
        before=self.store.get(self.project['id']);body=self.body();body['tracking_request']['configuration']['seed_box']['width']=1.
        self.assertEqual(self.request(body)[0],400);body=self.body();body['tracking_request']['expected_version']+=1;self.assertEqual(self.request(body)[0],409)
        self.assertEqual(self.store.get(self.project['id']),before)
