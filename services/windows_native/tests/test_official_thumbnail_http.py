"""Signed actual Native routes, actual local PNG and explicit mock publication."""
import http.client,json,threading,unittest
from services.windows_native.tests import test_official_publication_thumbnails as fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer


class OfficialThumbnailHTTPTests(fixture.OfficialThumbnailWorkerTests):
    # Inherited worker cases are exercised in their original suite, not repeated.
    def setUp(self):
        super().setUp();self.raw='vf1.explicit-fixture.'+'x'*48;access=NativeAccess(self.verifier,self.workspace);self.pipeline=NoProviderPipeline()
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=access,
            official_account_factories={self.account_factory.account.account_ref:self.account_factory},official_publish_factories={self.target.profile_id:self.publish_factory},
            official_publish_session_directory=self.folder/'http-protected-sessions',render_thumbnail_rights_enabled=True)
        self.server.publications.capabilities_path=self.publications.capabilities_path;self.server.publications.capabilities=self.publications.capabilities
        self.server.publications.capabilities_sha256=self.publications.capabilities_sha256
        self.journal=self.server.official_publications;self.journal.clock=lambda:self.clock[0]
        self.worker=self.server.official_publish_worker;self.sessions=self.server.official_publish_vault
        self.server.daemon_threads=False  # Join owned in-flight handlers before fixture cleanup.
        self.cookie,session=access.login(self.raw);self.csrf=session.csrf;self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='/api/projects/'+self.project['id']+'/official-publications'
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.assertEqual(self.pipeline.calls,0);super().tearDown()
    def request_http(self,method,path,body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=180)
        outgoing={'Cookie':'vf_native_session='+self.cookie,'Origin':'http://127.0.0.1:'+str(self.server.server_port),'X-VF-CSRF':self.csrf,**(headers or {})}
        if body is not None:outgoing['Content-Type']='application/json'
        try:
            connection.request(method,path,body=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,headers=outgoing)
            response=connection.getresponse();raw=response.read();return response.status,json.loads(raw) if raw else None,dict(response.getheaders())
        finally:connection.close()
    def action(self,action):
        state=self.state();return self.request_http('POST',self.base+'/'+self.value['publication_id']+'/'+action,{
            'expected_snapshot_sha256':self.value['snapshot_sha256'],'expected_dispatch_version':state['dispatch']['version']})
    def test_http_original_png_stage_is_explicit_and_receipt_requires_the_following_processing_poll(self):
        status,value,_=self.request_http('POST',self.base,self.body().model_dump(mode='json'));self.assertEqual(status,200,value);self.value=value
        status,_,_=self.request_http('POST',self.base+'/'+value['publication_id']+'/approve',{'expected_snapshot_sha256':value['snapshot_sha256'],'acknowledged_official_publication':True});self.assertEqual(status,200)
        self.assertEqual(self.action('step')[0],200)
        for _ in range(20):
            if self.state()['dispatch']['phase']=='uploaded':break
            self.assertEqual(self.action('step')[0],200)
        status,partial,_=self.action('poll');self.assertEqual(status,200);self.assertEqual(partial['status'],'queued');self.assertEqual(partial['thumbnail_stage']['status'],'response_received');self.assertIsNone(partial['receipt'])
        status,done,_=self.action('poll');self.assertEqual(status,200);self.assertTrue(done['mock_publication_complete']);self.assertFalse(done['published']);self.assertEqual(len(self.posts()),1)
    def test_http_unknown_response_leaves_history_and_cannot_issue_a_second_post(self):
        self.upload();self.mode='timeout';status,value,_=self.action('poll');self.assertEqual(status,409)
        status,stored,_=self.request_http('GET',self.base+'/'+self.value['publication_id']);self.assertEqual(status,200);self.assertEqual(stored['thumbnail_stage']['status'],'outcome_unknown')
        before=len(self.wire);self.assertEqual(self.action('poll')[0],409);self.assertEqual(len(self.wire),before);self.assertEqual(len(self.posts()),1)


# unittest discovers inherited test methods. Retain only the two HTTP scenarios;
# the delegated setup/helpers and their original worker tests remain unchanged.
for name in dir(OfficialThumbnailHTTPTests):
    if name.startswith('test_') and not name.startswith('test_http_'):setattr(OfficialThumbnailHTTPTests,name,None)

if __name__=='__main__':unittest.main()
