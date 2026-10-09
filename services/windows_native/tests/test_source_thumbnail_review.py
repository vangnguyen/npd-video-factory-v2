"""Original fixture provenance plus actual sampled PNGs; no genuine inference."""
import copy,json,unittest,http.client,threading
from unittest.mock import patch
from services.windows_native.tests import test_source_broll_vision as fixture
from services.windows_native import source_thumbnail_review as review,auto_edit_timeline as timeline,auto_edit_analysis as analysis
from services.windows_native.project_thumbnail import thumbnail
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.media_frame_analysis import frame_path
from services.windows_native.store import Store

class SourceThumbnailReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SourceBrollVisionTests();self.f.setUp();self.row=self.f.complete(main=True)
    def tearDown(self):self.f.tearDown();self.f.doCleanups()
    def create(self,**changes):
        f=self.f;f.project=timeline.view(f.store,f.project['id'])
        result=review.create(f.store,f.config,f.project['id'],{'revision':f.project['revision'],
            'analysis_id':f.project['shot_timeline']['snapshot']['metadata']['source_analysis_id'],
            'reviewed_vision':f.ref(self.row),**changes},official_vision=lambda:f.official)
        f.project=timeline.view(f.store,f.project['id']);return result['items'][-1]
    def body(self,saved,**changes):
        f=self.f;return {'revision':f.project['revision'],'recommendation_id':saved['recommendation']['recommendation_id'],
            'expected_sha256':saved['sha256'],'frame_id':saved['recommendation']['candidates'][0]['frame_id'],
            'acknowledged_thumbnail':True,'acknowledged_protocol_mock':True,**changes}
    def select(self,saved,**changes):
        f=self.f;result=review.select(f.store,f.config,f.project['id'],self.body(saved,**changes),official_vision=lambda:f.official)
        f.project=timeline.view(f.store,f.project['id']);return result
    def test_actual_pixel_candidates_selection_and_dedup_preserve_timeline_source_original_cost(self):
        f=self.f;before=copy.deepcopy(f.project['document']['canonical_timeline']);source_sha=file_sha(f.source_path);saved=self.create()
        self.assertTrue(saved['recommendation']['candidates']);self.assertLessEqual(len(saved['recommendation']['candidates']),3)
        for candidate in saved['recommendation']['candidates']:
            self.assertIsNone(candidate['provider_caption']);self.assertIsNone(candidate['predicted_sample_quality']);self.assertIsNone(candidate['confidence'])
            self.assertIsNone(candidate['provider_thumbnail_suggestion']);self.assertFalse(candidate['publishing_authorized'])
            self.assertEqual(file_sha(frame_path(f.root,candidate['source_frame'])),candidate['source_frame']['sha256'])
        unchanged=copy.deepcopy(f.project);self.assertEqual(self.create(),saved);self.assertEqual(f.project,unchanged)
        chosen=saved['recommendation']['candidates'][-1];result=self.select(saved,frame_id=chosen['frame_id'])
        self.assertEqual(result['selection'],review.selection(saved,chosen['frame_id']));self.assertEqual(f.project['document']['canonical_timeline'],before)
        path,basis=thumbnail(f.store,f.config,f.project['id'],f.asset['id']);self.assertEqual(basis,'explicit_reviewed_source_frame')
        self.assertEqual(path.read_bytes(),frame_path(f.root,chosen['source_frame']).read_bytes());self.assertEqual(file_sha(f.source_path),source_sha)
        unchanged=copy.deepcopy(f.project);self.select(saved,frame_id=chosen['frame_id']);self.assertEqual(f.project,unchanged)
        self.assertIsNone(f.project['approval']);self.assertEqual(f.official.get(f.project['id'],self.row['vision_id']),self.row);self.assertEqual(len(f.calls),1)
    def test_raw_review_wrong_mock_hash_foreign_frame_stale_and_supporting_refuse_atomically(self):
        f=self.f;saved=self.create();before=copy.deepcopy(f.project)
        for changes in ({'acknowledged_thumbnail':1},{'acknowledged_thumbnail':False},{'acknowledged_protocol_mock':1},
            {'acknowledged_protocol_mock':False},{'expected_sha256':'0'*64},{'frame_id':'mfr_'+'f'*24},{'revision':1}):
            with self.assertRaises(WorkflowError):self.select(saved,**changes)
            self.assertEqual(timeline.view(f.store,f.project['id']),before)
        support=f.complete()
        for row in (support,{**self.row,'result_sha256':'0'*64}):
            with self.assertRaises(WorkflowError):self.create(reviewed_vision=f.ref(row))
        with self.assertRaises(WorkflowError):self.create(reviewed_vision=f.ref(self.row,acknowledged_reviewed_result=1))
        self.assertEqual(timeline.view(f.store,f.project['id']),before)
    def test_changed_transcript_blocks_new_selection_but_original_history_is_keyless(self):
        f=self.f;saved=self.create();self.select(saved);transcript=saved['recommendation']['source']['analysis']['transcript']
        analysis.edit_transcript(f.store,f.project['id'],f.project['revision'],transcript['analysis_id'],{
            'expected_version':transcript['version'],'expected_timeline_version':f.project['shot_timeline']['version'],
            'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Explicit changed thumbnail transcript fixture.'}]})
        f.project=timeline.view(f.store,f.project['id']);before=copy.deepcopy(f.project)
        with self.assertRaises(WorkflowError):self.select(saved)
        with self.assertRaises(WorkflowError):self.create()
        for frame in self.row['snapshot']['input_binding']['source_frame_evidence']:frame_path(f.root,frame).unlink()
        f.source_path.unlink()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY')):
            self.assertEqual(timeline.view(Store(f.root),f.project['id']),before)
            self.assertEqual(review.page(Store(f.root),f.config,f.project['id'])['items'],[saved])
        with self.assertRaises(WorkflowError):thumbnail(f.store,f.config,f.project['id'],f.asset['id'])
        self.assertEqual(f.store.get(f.project['id'])['document'],before['document']);self.assertEqual(len(f.calls),1)
    def test_rehashed_candidates_pixels_mock_rights_and_authority_promotions_refuse(self):
        f=self.f;self.create();original=copy.deepcopy(f.project['document'])
        for change in (lambda v:v.update(publishing_authorized=1),lambda v:v['candidates'][0].update(confidence=.99),
            lambda v:v['candidates'][0]['source_frame'].update(sha256='0'*64),lambda v:v['candidates'][0].update(provider_caption='invented genuine'),
            lambda v:v['reviewed_vision']['items'][0].update(mock=False,semantic_inference_performed=True),
            lambda v:v['source']['asset'].update(license='invented commercial license')):
            doc=copy.deepcopy(original);saved=doc['source_thumbnail_reviews'][0];change(saved['recommendation']);saved['sha256']=digest(saved['recommendation'])
            with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),f.project['id']))
            with self.assertRaises(WorkflowError):timeline.view(f.store,f.project['id'])
            revision=f.store.get(f.project['id'])['revision']
            with self.assertRaises(WorkflowError):review.create(f.store,f.config,f.project['id'],{'revision':revision,
                'analysis_id':original['canonical_timeline']['snapshot']['metadata']['source_analysis_id'],'reviewed_vision':f.ref(self.row)},official_vision=lambda:f.official)
            self.assertEqual(f.store.get(f.project['id'])['revision'],revision)
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),f.project['id']))
        self.assertEqual(timeline.view(f.store,f.project['id']),f.project)
    def test_selected_pointer_forgery_or_original_pixel_loss_cannot_serve_or_select(self):
        f=self.f;saved=self.create();self.select(saved);original=copy.deepcopy(f.project['document'])
        for changes in ({'candidate_sha256':'0'*64},{'publishing_authorized':True},{'mock_original_result':1},{'frame_id':'mfr_'+'f'*24}):
            doc=copy.deepcopy(original);doc['source_thumbnail_selection'].update(changes)
            with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),f.project['id']))
            with self.assertRaises(WorkflowError):timeline.view(f.store,f.project['id'])
            with self.assertRaises(WorkflowError):thumbnail(f.store,f.config,f.project['id'],f.asset['id'])
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),f.project['id']))
        frame_path(f.root,saved['recommendation']['candidates'][0]['source_frame']).write_bytes(b'changed fixture PNG')
        before=f.store.get(f.project['id'])
        with self.assertRaises(WorkflowError):self.select(saved)
        with self.assertRaises(WorkflowError):thumbnail(f.store,f.config,f.project['id'],f.asset['id'])
        self.assertEqual(f.store.get(f.project['id']),before)
    def test_duplicate_archives_original_reviews_without_active_selection_or_authority(self):
        f=self.f;saved=self.create();self.select(saved);before=copy.deepcopy(f.project)
        child=f.store.duplicate(f.project['id'],f.project['revision'])
        self.assertNotIn('source_thumbnail_reviews',child['document']);self.assertNotIn('source_thumbnail_selection',child['document'])
        record=child['document']['source_thumbnail_inherited_reviewed_history'][0]
        self.assertEqual(record['original_record'],saved);self.assertFalse(record['authority_transferred']);self.assertTrue(record['new_review_required'])
        self.assertEqual(child['document']['source_thumbnail_inherited_selection']['original_selection'],before['document']['source_thumbnail_selection'])
        self.assertEqual(timeline.view(f.store,f.project['id']),before);self.assertIsNone(child['approval'])
        with self.assertRaises(WorkflowError):review.select(f.store,f.config,child['id'],self.body(saved,revision=child['revision']))
    def test_pure_nonmock_algorithm_uses_original_suggestions_and_nullable_confidence_without_genuine_claim(self):
        # Never admitted as a genuine provider result/journal.
        f=self.f;snapshot=review.source(f.project,f.project['shot_timeline']['snapshot']['metadata']['source_analysis_id'],f.root)
        from services.windows_native.official_vision_evidence import build_context,ReviewedVision
        with f.store.transaction() as con:context=build_context(f.official,f.project,[ReviewedVision.model_validate(f.ref(self.row))],source_con=con)
        baseline=review.candidates(snapshot,context);item=context['items'][0];item['mock']=False;item['semantic_inference_performed']=True
        item['thumbnail_candidate_ids']=[item['frames'][-1]['frame_id']]
        values=review.candidates(snapshot,context);self.assertEqual(values[0]['original_vision_frame_id'],item['frames'][-1]['frame_id'])
        self.assertTrue(values[0]['provider_thumbnail_suggestion']);self.assertIsNone(values[0]['confidence']);self.assertIsNotNone(values[0]['provider_caption'])
        item['mock']=True;self.assertEqual(review.candidates(snapshot,context),baseline)
        item['mock']=False;item['frames'][-1]['quality']['black_frame']=True
        self.assertNotIn(item['frames'][-1]['frame_id'],[v['original_vision_frame_id'] for v in review.candidates(snapshot,context)])
    def test_signed_disabled_editor_routes_and_viewer_before_body_preserve_provider_gates(self):
        from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
        from services.windows_native.tests.test_human_identity import fixture as human
        from services.windows_native.tests.test_phase10_http import NoProviderPipeline
        from services.windows_native.access import NativeAccess
        from services.windows_native.server import LocalServer,Handler
        f=self.f;raw,data=human('editor',workspace=f.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),f.workspace)
        cookie,session=access.login(raw);pipeline=NoProviderPipeline();server=LocalServer(0,f.config,pipeline=pipeline,start_worker=False,access=access)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base='/api/projects/'+f.project['id']
        def request(path,body=None,cookie_value=cookie,csrf=session.csrf):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('GET' if body is None else 'POST',path,None if body is None else json.dumps(body),
                headers={'Cookie':'vf_native_session='+cookie_value,'X-VF-CSRF':csrf,'Content-Type':'application/json'})
            response=conn.getresponse();result=(response.status,response.read(),dict(response.getheaders()));conn.close();return result
        try:
            route=base+'/auto-edit/thumbnail-reviews';body={'revision':f.project['revision'],
                'analysis_id':f.project['shot_timeline']['snapshot']['metadata']['source_analysis_id'],'reviewed_vision':f.ref(self.row)}
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNAUTHENTICATED BODY')):self.assertEqual(request(route,body,cookie_value='')[0],401)
            self.assertEqual(request(route,body,csrf='invalid')[0],403)
            code,data,_=request(route,body);self.assertEqual(code,200,data);saved=json.loads(data)['items'][0]
            f.project=timeline.view(f.store,f.project['id']);code,data,_=request(route+'/select',self.body(saved));self.assertEqual(code,200,data)
            code,pixels,headers=request(base+'/media/'+f.asset['id']+'/thumbnail');self.assertEqual(code,200,pixels)
            self.assertEqual(headers['Content-Type'],'image/png');self.assertEqual(headers['X-VF-Thumbnail-Basis'],'explicit_reviewed_source_frame')
            self.assertEqual(pixels,frame_path(f.root,saved['recommendation']['candidates'][0]['source_frame']).read_bytes())
            self.assertEqual(request(route)[0],200);self.assertEqual(request(route,body)[0],409)
            viewer_raw,viewer_data=human('viewer',workspace=f.workspace)
            viewer=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(viewer_data),max_token_ttl_seconds=86400),f.workspace)
            viewer_cookie,viewer_session=viewer.login(viewer_raw);server.access=viewer
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO VIEWER BODY')):
                self.assertEqual(request(route+'/select',self.body(saved),cookie_value=viewer_cookie,csrf=viewer_session.csrf)[0],403)
            self.assertEqual(request(route,cookie_value=viewer_cookie)[0],200);self.assertEqual(pipeline.calls,0);self.assertEqual(len(f.calls),1)
            self.assertFalse(server.official_vision.states()['enabled'])
        finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
