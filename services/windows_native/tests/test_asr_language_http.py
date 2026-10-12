"""Signed language selection; worker/external dispatch remains disabled here."""
import http.client,json,threading,unittest,uuid
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests import test_asr as fixture
from services.windows_native.tests.test_human_identity import fixture as human


class NativeAsrLanguageHTTPTests(unittest.TestCase):
    def setUp(self):
        fixture.AsrTests.setUp(self);self.workspace='wsp_asr_language_http'
        raw,data=human('editor',workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=access.login(raw);self.csrf=session.csrf
        self.server=LocalServer(0,self.config,start_worker=False,access=access)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();fixture.AsrTests.tearDown(self)
    def body(self,language='en'):
        return {'revision':self.project['revision'],'kind':'asr','request_key':uuid.uuid4().hex,'asr_request':{'language':language}}
    def request(self,body,**extra):
        con=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=10)
        con.request('POST','/api/projects/'+self.project['id']+'/jobs',json.dumps(body),
            headers={'Cookie':'vf_native_session='+self.cookie,'X-VF-CSRF':self.csrf,'Content-Type':'application/json',**extra})
        response=con.getresponse();result=json.loads(response.read());status=response.status;con.close();return status,result
    def test_editor_request_is_frozen_replayable_and_conflicting_language_is_atomic(self):
        before=self.store.get(self.project['id']);body=self.body();code,job=self.request(body)
        self.assertEqual(code,200,job);self.assertEqual(job['snapshot']['asr_request']['request'],{'language':'en'})
        self.assertEqual(self.request(body)[1]['id'],job['id'])
        body['asr_request']['language']='vi';self.assertEqual(self.request(body)[0],409)
        self.assertEqual(self.store.get(self.project['id'])['document'],before['document']);self.assertEqual(fixture.FixtureTransport.calls,[])
    def test_auth_permissions_and_invalid_selection_never_dispatch(self):
        body=self.body();before=self.store.get(self.project['id'])
        with patch.object(Handler,'read_body',side_effect=AssertionError('AUTH BEFORE BODY')):self.assertEqual(self.request(body,Cookie='')[0],401)
        self.assertEqual(self.request(body,**{'X-VF-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request(body,Origin='https://untrusted.invalid')[0],403)
        self.assertEqual(self.request(self.body('fr'))[0],400)
        raw,data=human('viewer',workspace=self.workspace);access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.cookie,session=access.login(raw);self.csrf=session.csrf;self.server.access=access
        with patch.object(Handler,'read_body',side_effect=AssertionError('VIEWER BEFORE BODY')):self.assertEqual(self.request(body)[0],403)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(fixture.FixtureTransport.calls,[])
