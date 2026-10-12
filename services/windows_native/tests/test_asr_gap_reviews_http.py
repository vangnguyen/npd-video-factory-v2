"""Signed editor/read/source boundaries; no live ASR transport or worker loop."""
import http.client,json,threading,unittest,copy
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler,Runner
from services.windows_native.pipeline import Pipeline
from services.windows_native import asr
from services.windows_native.tests import test_asr_gap_reviews as review_fixture
from services.windows_native.tests import test_asr as fixture
from services.windows_native.tests.test_source_audio_gaps import GapTransport
from services.windows_native.tests.test_human_identity import fixture as human


class AsrGapReviewHTTPTests(unittest.TestCase):
    gapped=review_fixture.AsrGapReviewTests.gapped
    run_asr=review_fixture.AsrGapReviewTests.run_asr
    body=review_fixture.AsrGapReviewTests.body
    def setUp(self):
        review_fixture.AsrGapReviewTests.setUp(self);raw,data=human('editor',workspace=self.workspace)
        self.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=self.access.login(raw);self.csrf=session.csrf
        self.server=LocalServer(0,self.config,start_worker=False,access=self.access);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.path='/api/projects/'+self.project['id']+'/asr-gap-reviews';self.edit_path=self.path+'/'+self.job['id']+'/'+self.asset['id']
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();fixture.AsrTests.tearDown(self)
    def request(self,method,path,body=None,**extra):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        con.request(method,path,None if body is None else json.dumps(body),headers={'Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,'Content-Type':'application/json',**extra})
        response=con.getresponse();data=response.read();headers=dict(response.getheaders());status=response.status;con.close()
        return status,(json.loads(data) if 'json' in headers.get('Content-Type','') else data),headers
    def test_signed_read_save_and_explicit_resume_use_saved_candidate_keylessly(self):
        code,view,headers=self.request('GET',self.path);self.assertEqual(code,200,view);self.assertIn('no-store',headers.get('Cache-Control',''))
        original=copy.deepcopy(view['items'][0]['original_words']);code,saved,_=self.request('POST',self.edit_path,self.body());self.assertEqual(code,200,saved)
        self.assertEqual(saved['items'][0]['original_words'],original);self.assertEqual(saved['items'][0]['version'],1);self.assertEqual(self.store.get_job(self.job['id'])['status'],'failed')
        code,queued,_=self.request('POST','/api/jobs/'+self.job['id']+'/resume',{});self.assertEqual(code,200,queued);self.assertEqual(queued['id'],self.job['id'])
        with patch.object(asr.connection,'status',side_effect=AssertionError('No provider status read')):Runner(self.store,Pipeline(self.config)).run_one()
        self.assertEqual(self.store.get_job(self.job['id'])['status'],'succeeded');self.assertEqual(len(GapTransport.calls),3)
        code,history,_=self.request('GET',self.path);self.assertEqual(code,200,history);self.assertFalse(history['items'][0]['editable']);self.assertEqual(history['items'][0]['original_words'],original)
    def test_auth_csrf_origin_and_viewer_are_checked_before_mutation_body(self):
        before=self.store.get(self.project['id']);body=self.body()
        with patch.object(Handler,'read_body',side_effect=AssertionError('AUTH BEFORE BODY')):
            self.assertEqual(self.request('POST',self.edit_path,body,Cookie='')[0],401)
            self.assertEqual(self.request('POST',self.edit_path,body,**{'X-VF-CSRF':'wrong'})[0],403)
            self.assertEqual(self.request('POST',self.edit_path,body,Origin='https://untrusted.invalid')[0],403)
            raw,data=human('viewer',workspace=self.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
            self.cookie,session=access.login(raw);self.csrf=session.csrf;self.server.access=access
            self.assertEqual(self.request('POST',self.edit_path,body)[0],403)
        self.assertEqual(self.request('GET',self.path)[0],200);self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(len(GapTransport.calls),3)
    def test_source_range_and_scope_queries_are_guarded(self):
        code,data,headers=self.request('GET',self.edit_path+'/source',Range='bytes=0-15');self.assertEqual(code,206);self.assertEqual(len(data),16)
        self.assertEqual(self.request('GET',self.path+'?unexpected=1')[0],400)
        other=self.store.create('Other','','media');foreign='/api/projects/'+other['id']+'/asr-gap-reviews/'+self.job['id']+'/'+self.asset['id']
        self.assertEqual(self.request('POST',foreign,self.body())[0],404);self.assertEqual(self.request('GET',foreign+'/source')[0],404)
        self.assertEqual(len(GapTransport.calls),3)
