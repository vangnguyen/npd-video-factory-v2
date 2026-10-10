"""Signed human current-Owner rights HTTP; no license, publication or provider."""
import unittest,threading
from unittest.mock import patch
from services.windows_native.tests import test_render_thumbnail_http as fixture
from services.windows_native.server import Handler,LocalServer
from services.windows_native.access import NativeAccess
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native.contracts import WorkflowError

class NativeRenderThumbnailRightsHTTPTests(unittest.TestCase):
    runtime=fixture.NativeRenderThumbnailHTTPTests.runtime
    bridge=fixture.NativeRenderThumbnailHTTPTests.bridge
    request=fixture.NativeRenderThumbnailHTTPTests.request
    response=fixture.NativeRenderThumbnailHTTPTests.response
    http=fixture.NativeRenderThumbnailHTTPTests.http
    account=fixture.NativeRenderThumbnailHTTPTests.account
    body=fixture.NativeRenderThumbnailHTTPTests.body
    create=fixture.NativeRenderThumbnailHTTPTests.create
    @classmethod
    def setUpClass(cls):fixture.NativeRenderThumbnailHTTPTests.setUpClass.__func__(cls)
    @classmethod
    def tearDownClass(cls):fixture.NativeRenderThumbnailHTTPTests.tearDownClass.__func__(cls)
    def setUp(self):
        fixture.NativeRenderThumbnailHTTPTests.setUp(self);self.server.shutdown();self.server.server_close();self.thread.join()
        self.server=LocalServer(0,self.config,pipeline=self.pipeline,start_worker=False,access=NativeAccess(self.verifier,self.workspace),render_thumbnail_rights_enabled=True)
        self.service=self.server.render_vision;self.cookie,session=self.server.access.login(self.raw);self.csrf=session.csrf
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.selected={k:v for k,v in self.create().items() if k!='idempotent_replay'}
        self.rights_base='/api/projects/'+self.project['id']+'/render-thumbnail-rights'
        code,self.rights_input,_=self.http('GET',self.rights_base+'/input/'+self.selected['thumbnail_asset_id']);self.assertEqual(code,200)
    def tearDown(self):fixture.NativeRenderThumbnailHTTPTests.tearDown(self)
    def review(self,**changes):
        return {'revision':self.project['revision'],'thumbnail_asset_id':self.selected['thumbnail_asset_id'],'expected_thumbnail_snapshot_sha256':self.selected['snapshot_sha256'],
            'expected_rights_input_sha256':self.rights_input['rights_input_sha256'],'action':'grant','reason':'EXPLICIT SYNTHETIC HTTP OWNER EXCEPTION — NOT REAL LEGAL ACCEPTANCE',
            'evidence_reference':'document:explicit-synthetic-http-thumbnail-exception','valid_days':7,'allow_publishing_review':True,
            'acknowledged_thumbnail_rights_exception':True,'acknowledged_not_independent_license_verification':True,'request_key':'explicit-http-thumbnail-rights-key',**changes}
    def grant(self,**changes):
        code,value,headers=self.http('POST',self.rights_base,self.review(**changes));self.assertEqual(code,200,value);self.assertEqual(headers['Cache-Control'],'no-store');return value

    def test_signed_owner_grant_original_input_finite_history_is_not_license_final_or_publishing(self):
        original=self.store.get(self.project['id']);grant=self.grant();self.assertFalse(grant['idempotent_replay']);self.assertEqual(grant['rights_status'],'unknown')
        self.assertIsNone(grant['license']);self.assertFalse(grant['rights_independently_verified']);self.assertFalse(grant['publishing_authorized'])
        active=self.server.render_thumbnail_rights.active(self.project['id'],self.selected['thumbnail_asset_id']);self.assertEqual(active['override_id'],grant['override_id'])
        self.assertFalse(active['final_video_approved']);self.assertFalse(active['source_asset_rights_granted']);self.assertFalse(active['owner_uat_accepted'])
        code,history,_=self.http('GET',self.rights_base);self.assertEqual(code,200);self.assertEqual(history['items'][0]['override_id'],grant['override_id'])
        code,read,_=self.http('GET',self.rights_base+'/'+grant['override_id']);self.assertEqual(code,200)
        self.assertEqual(read,{k:v for k,v in grant.items() if k!='idempotent_replay'});self.assertEqual(self.store.get(self.project['id']),original)
        self.assertEqual(self.server.render_thumbnails.get(self.project['id'],self.selected['thumbnail_asset_id']),self.selected);self.assertEqual(self.calls,[]);self.assertEqual(self.pipeline.calls,0)

    def test_only_owner_writes_before_body_but_other_humans_read_scoped_originals(self):
        grant=self.grant()
        for role in ('editor','reviewer','viewer'):
            self.account(role)
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO NON-OWNER RIGHTS BODY')):
                self.assertEqual(self.http('POST',self.rights_base,{'role':'owner','enabled':True})[0],403)
            self.assertEqual(self.http('GET',self.rights_base)[0],200);self.assertEqual(self.http('GET',self.rights_base+'/'+grant['override_id'])[0],200)
            self.assertEqual(self.http('GET',self.rights_base+'/input/'+self.selected['thumbnail_asset_id'])[0],200)
            self.assertEqual(self.http('GET','/api/connections/render-thumbnail-rights')[0],403)

    def test_cookie_csrf_origin_current_owner_and_raw_authority_cannot_create_or_dispatch(self):
        for headers,code in (({'Cookie':''},401),({'X-VF-CSRF':''},403),({'Origin':'https://untrusted.invalid'},403)):
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNTRUSTED RIGHTS BODY')):
                self.assertEqual(self.http('POST',self.rights_base,{},headers)[0],code)
        for changes in ({'acknowledged_thumbnail_rights_exception':1},{'acknowledged_not_independent_license_verification':False},{'allow_publishing_review':1},
            {'revision':True},{'valid_days':31},{'provider_authorized':True},{'publishing_authorized':True},{'api_key':'PRIVATE'},
            {'evidence_reference':'https://example.invalid/license?api_key=PRIVATE'}):self.assertEqual(self.http('POST',self.rights_base,self.review(**changes))[0],400)
        self.assertEqual(self.http('GET',self.rights_base)[1]['items'],[]);self.assertEqual(self.calls,[])

    def test_default_off_requires_registry_and_original_records_survive_disabled_keyless_app(self):
        grant=self.grant()
        with self.assertRaisesRegex(WorkflowError,'AUTH_REGISTRY_REQUIRED'):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,render_thumbnail_rights_enabled=True)
        with self.assertRaisesRegex(WorkflowError,'CONFIGURATION_INVALID'):LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,render_thumbnail_rights_enabled=1)
        with LocalServer(0,self.config,pipeline=NoProviderPipeline(),start_worker=False,access=NativeAccess(self.verifier,self.workspace)) as reopened:
            self.assertFalse(reopened.render_thumbnail_rights.states()['enabled'])
            self.assertEqual(reopened.render_thumbnail_rights.get(self.project['id'],grant['override_id']),{k:v for k,v in grant.items() if k!='idempotent_replay'})
            self.assertIsNone(reopened.render_thumbnail_rights.active(self.project['id'],self.selected['thumbnail_asset_id']));self.assertFalse(reopened.runner.run_one())
            with self.assertRaisesRegex(WorkflowError,'NOT_ENABLED'):
                from services.windows_native.render_thumbnail_rights import Create
                reopened.render_thumbnail_rights.record(self.project['id'],Create.model_validate(self.review(request_key='explicit-off-http-rights-key')),principal=self.principal)
        self.assertEqual(self.calls,[])

    def test_idempotent_retry_wrong_binding_and_missing_png_leave_readable_revokeable_original(self):
        original=self.grant();replay=self.grant();self.assertTrue(replay['idempotent_replay']);self.assertEqual(replay['override_id'],original['override_id'])
        self.assertEqual(self.http('POST',self.rights_base,self.review(reason='EXPLICIT CHANGED RIGHTS REASON'))[0],409)
        self.assertEqual(self.http('POST',self.rights_base,self.review(request_key='explicit-wrong-rights-input-key',expected_rights_input_sha256='a'*64))[0],409)
        path=self.root/'jobs'/self.job['id']/self.frame['evidence_frame_reference'];path.unlink()
        self.assertEqual(self.http('GET',self.rights_base+'/'+original['override_id'])[0],200)
        self.assertEqual(self.http('POST',self.rights_base,self.review(request_key='explicit-missing-rights-frame-key'))[0],409)
        code,revoked,_=self.http('POST',self.rights_base,self.review(action='revoke',allow_publishing_review=False,override_id=original['override_id'],
            expected_override_sha256=original['snapshot_sha256'],request_key='explicit-http-thumbnail-revoke-key'))
        self.assertEqual(code,200,revoked);self.assertEqual(revoked['snapshot']['request']['action'],'revoke');self.assertIsNone(self.server.render_thumbnail_rights.active(self.project['id'],self.selected['thumbnail_asset_id']))

    def test_bounded_query_scope_and_source_override_identifiers_cannot_return_or_create_rights(self):
        grant=self.grant();route=self.rights_base+'/'+grant['override_id']
        for suffix in ('?limit=0','?limit=25&limit=25','?extra=1','?cursor=bad'):self.assertEqual(self.http('GET',self.rights_base+suffix)[0],400)
        for path in (route+'?extra=1',self.rights_base+'/input/'+self.selected['thumbnail_asset_id']+'?extra=1','/api/connections/render-thumbnail-rights?extra=1'):
            self.assertEqual(self.http('GET',path)[0],400)
        self.assertEqual(self.http('GET','/api/projects/'+'a'*32+'/render-thumbnail-rights/'+grant['override_id'])[0],404)
        self.assertEqual(self.http('POST',self.rights_base,self.review(action='revoke',allow_publishing_review=False,override_id='nro_'+'a'*32,expected_override_sha256='a'*64))[0],400)
        self.assertEqual(self.calls,[])

if __name__=='__main__':unittest.main()
