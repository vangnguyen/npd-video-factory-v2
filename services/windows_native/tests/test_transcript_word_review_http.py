"""Actual signed loopback review and Range reads with explicit human/ASR fixtures."""
import copy,threading,unittest
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.tests import test_access_http as access_fixture
from services.windows_native.tests import test_transcript_word_review as fixture
from services.windows_native.tests.test_human_identity import fixture as identity

class NativeWordReviewHTTPTests(unittest.TestCase):
    request=access_fixture.NativeAccessHTTPTests.request
    workspace='wsp_word_review_http_fixture'
    save_analysis=fixture.NativeWordReviewTests.save_analysis
    def setUp(self):
        fixture.NativeWordReviewTests.setUp(self);bundle=self.save_analysis()
        self.base='/api/projects/'+self.project['id']+'/transcript-word-review'
        raw,data=identity('editor',workspace=self.workspace)
        self.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        self.server=LocalServer(0,self.config,start_worker=False,access=self.access)
        self.cookie,session=self.access.login(raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();fixture.NativeWordReviewTests.tearDown(self)
    def body(self,value):
        item=value['items'][0]
        return {'revision':value['revision'],'asset_sha256':item['asset_sha256'],'analysis_sha256':item['analysis_sha256'],
            'review':fixture.request(item['current'],value['timeline_version'])}
    def test_signed_editor_review_and_source_range_preserve_original_and_actor(self):
        code,value,headers=self.request('GET',self.base);self.assertEqual(code,200,value)
        self.assertEqual(headers['Cache-Control'],'no-store');item=value['items'][0];body=self.body(value)
        body['review']['segments'][0]['words'][0]['text']='Vang Nguyễn'
        code,updated,_=self.request('POST',self.base+'/video/'+item['identity'],body);self.assertEqual(code,200,updated)
        current=updated['items'][0]['current'];self.assertEqual(current['version'],2)
        self.assertEqual(current['provenance']['actor_ref'],'explicit-fixture');self.assertFalse(current['is_original_evidence'])
        self.assertEqual(updated['items'][0]['versions'][0],item['versions'][0]);self.assertIsNone(self.store.get(self.project['id'])['approval'])
        code,content,headers=self.request('GET',item['source_url'],headers={'Range':'bytes=0-63'})
        self.assertEqual(code,206);self.assertEqual(len(content),64);self.assertIn('Content-Range',headers)
        self.assertEqual(self.request('POST',self.base+'/video/'+item['identity'],body)[0],409)
    def test_auth_csrf_viewer_and_source_scope_fail_before_mutation_body(self):
        code,value,_=self.request('GET',self.base);body=self.body(value);path=self.base+'/video/'+value['items'][0]['identity']
        with patch.object(Handler,'read_body',side_effect=AssertionError('AUTH BEFORE BODY')):
            self.assertEqual(self.request('POST',path,body,headers={'Cookie':''})[0],401)
            self.assertEqual(self.request('POST',path,body,headers={'X-VF-CSRF':'wrong'})[0],403)
        raw,data=identity('viewer',workspace=self.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),self.workspace)
        access.bind_root(self.root);self.server.access=access;self.cookie,session=access.login(raw);self.csrf=session.csrf
        with patch.object(Handler,'read_body',side_effect=AssertionError('ROLE BEFORE BODY')):
            self.assertEqual(self.request('POST',path,body)[0],403)
        self.assertEqual(self.request('GET',self.base)[0],200)
        other=self.store.create('Unrelated project','','media')
        foreign='/api/projects/'+other['id']+'/transcript-word-review/source/'+value['items'][0]['asset_id']
        self.assertEqual(self.request('GET',foreign)[0],404)
    def test_source_corruption_and_unknown_request_fields_do_not_write(self):
        _,value,_=self.request('GET',self.base);item=value['items'][0];body=self.body(value);body['actor_ref']='forged-owner'
        before=self.store.get(self.project['id'])
        self.assertEqual(self.request('POST',self.base+'/video/'+item['identity'],body)[0],400)
        self.assertEqual(self.store.get(self.project['id']),before)
        (self.root/'assets'/item['asset_id']).write_bytes(b'explicit corrupt fixture')
        self.assertEqual(self.request('GET',item['source_url'])[0],409)
