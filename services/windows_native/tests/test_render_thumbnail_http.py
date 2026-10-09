"""Actual signed HTTP original PNG selection; no copied asset or publish authority."""
import hashlib,unittest
from unittest.mock import patch
from services.windows_native.tests import test_render_vision_http as fixture
from services.windows_native.server import Handler,LocalServer
from services.windows_native.access import NativeAccess
from services.windows_native.tests.test_phase10_http import NoProviderPipeline

class NativeRenderThumbnailHTTPTests(unittest.TestCase):
    runtime=fixture.NativeRenderVisionHTTPTests.runtime
    bridge=fixture.NativeRenderVisionHTTPTests.bridge
    request=fixture.NativeRenderVisionHTTPTests.request
    response=fixture.NativeRenderVisionHTTPTests.response
    http=fixture.NativeRenderVisionHTTPTests.http
    account=fixture.NativeRenderVisionHTTPTests.account
    @classmethod
    def setUpClass(cls):fixture.NativeRenderVisionHTTPTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.NativeRenderVisionHTTPTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixture.NativeRenderVisionHTTPTests.setUp(self);self.thumbnail_base='/api/projects/'+self.project['id']+'/render-thumbnails'
        self.input=self.http('GET',self.base+'/input/'+self.job['id'])[1]
        self.frame=next(f for f in self.input['binding']['record']['observation']['frames'] if not f['pixel_facts']['black_sample'])
    def tearDown(self):fixture.NativeRenderVisionHTTPTests.tearDown(self)
    def body(self,**changes):
        return {'revision':self.project['revision'],'render_job_id':self.job['id'],'expected_render_input_sha256':self.input['input_sha256'],
            'frame_id':self.frame['frame_id'],'expected_frame_sha256':self.frame['sha256'],'acknowledged_thumbnail':True,
            'request_key':'explicit-http-render-thumbnail-key',**changes}
    def create(self,**changes):
        status,value,headers=self.http('POST',self.thumbnail_base,self.body(**changes));self.assertEqual(status,200,value)
        self.assertEqual(headers['Cache-Control'],'no-store');return value

    def test_signed_human_selection_original_png_headers_history_no_project_provider_or_publication_mutation(self):
        original=self.store.get(self.project['id']);selected=self.create()
        self.assertFalse(selected['idempotent_replay']);self.assertEqual(selected['snapshot']['image']['rights_status'],'unknown')
        self.assertFalse(selected['snapshot']['publishing_authorized']);self.assertFalse(selected['snapshot']['final_video_approved'])
        route=self.thumbnail_base+'/'+selected['thumbnail_asset_id'];status,read,_=self.http('GET',route)
        self.assertEqual(status,200);self.assertEqual({k:v for k,v in selected.items() if k!='idempotent_replay'},read)
        status,pixels,headers=self.http('GET',route+'/image');self.assertEqual(status,200);self.assertEqual(headers['Content-Type'],'image/png')
        self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-VF-Thumbnail-Basis'],'explicit_reviewed_render_frame')
        self.assertEqual(headers['X-VF-Thumbnail-SHA256'],self.frame['sha256']);self.assertEqual(hashlib.sha256(pixels).hexdigest(),self.frame['sha256'])
        self.assertEqual(self.store.get(self.project['id']),original);self.assertEqual(self.calls,[]);self.assertEqual(self.pipeline.calls,0)

    def test_owner_and_editor_can_choose_reviewers_and_viewers_only_read_without_untrusted_body(self):
        for role in ('owner','editor'):
            self.account(role);selected=self.create(request_key='explicit-thumbnail-role-'+role)
        for role in ('reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO NON-EDITOR BODY')):
                self.assertEqual(self.http('POST',self.thumbnail_base,{'role':'owner'})[0],403)
            self.assertEqual(self.http('GET',self.thumbnail_base)[0],200)
            self.assertEqual(self.http('GET',self.thumbnail_base+'/'+selected['thumbnail_asset_id']+'/image')[0],200)
        self.assertEqual(self.calls,[])

    def test_missing_auth_csrf_origin_and_raw_authority_do_not_select_or_dispatch(self):
        for headers,code in (({'Cookie':''},401),({'X-VF-CSRF':''},403),({'Origin':'https://untrusted.invalid'},403)):
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNTRUSTED BODY')):
                self.assertEqual(self.http('POST',self.thumbnail_base,{},headers)[0],code)
        for changes in ({'acknowledged_thumbnail':1},{'revision':True},{'provider_authorized':True},{'publishing_authorized':True},
            {'api_key':'PRIVATE CLIENT KEY'},{'acknowledged_external_image_analysis':True}):
            self.assertEqual(self.http('POST',self.thumbnail_base,self.body(**changes))[0],400)
        self.assertEqual(self.http('GET',self.thumbnail_base)[1]['items'],[]);self.assertEqual(self.calls,[])

    def test_scoped_bounded_queries_foreign_project_and_input_cannot_return_or_select_image(self):
        selected=self.create();route=self.thumbnail_base+'/'+selected['thumbnail_asset_id']
        for suffix in ('?limit=0','?limit=25&limit=25','?extra=1','?cursor=bad'):
            self.assertEqual(self.http('GET',self.thumbnail_base+suffix)[0],400)
        self.assertEqual(self.http('GET',route+'?extra=1')[0],400);self.assertEqual(self.http('GET',route+'/image?extra=1')[0],400)
        foreign='/api/projects/'+'0'*32+'/render-thumbnails/'+selected['thumbnail_asset_id']
        self.assertEqual(self.http('GET',foreign+'/image')[0],404)
        self.assertEqual(self.http('POST',self.thumbnail_base,self.body(expected_render_input_sha256='0'*64,request_key='explicit-wrong-thumbnail-input'))[0],409)
        self.assertEqual(self.http('GET',route+'/image',headers={'Cookie':''})[0],401)

    def test_idempotent_selection_keyless_application_restart_keeps_original_current_version_review_separate(self):
        first=self.create();again=self.create();self.assertTrue(again['idempotent_replay']);self.assertEqual(first['thumbnail_asset_id'],again['thumbnail_asset_id'])
        self.assertEqual(self.http('POST',self.thumbnail_base,self.body(expected_frame_sha256='0'*64))[0],409)
        with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as reopened:
            expected={k:v for k,v in first.items() if k!='idempotent_replay'}
            self.assertEqual(reopened.render_thumbnails.get(self.project['id'],first['thumbnail_asset_id']),expected)
            pixels,_=reopened.render_thumbnails.image(self.project['id'],first['thumbnail_asset_id'])
            self.assertEqual(hashlib.sha256(pixels).hexdigest(),self.frame['sha256']);self.assertFalse(reopened.runner.run_one())
        self.assertEqual(self.calls,[])

    def test_corrupt_png_http_use_blocks_without_rewriting_original_selection_history(self):
        selected=self.create();route=self.thumbnail_base+'/'+selected['thumbnail_asset_id']
        path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];path.write_bytes(path.read_bytes()+b'EXPLICIT CORRUPTION')
        self.assertEqual(self.http('GET',route)[0],200);self.assertEqual(self.http('GET',route+'/image')[0],409)
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
