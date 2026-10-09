"""Actual CPU/media/SQLite/DPAPI; all speech/Vision semantics are explicit fixtures."""
import copy,json,threading,unittest
from unittest.mock import patch
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from services.windows_native.tests import test_source_broll_vision as fixture,test_access_http as http_fixture
from services.windows_native.tests.test_human_identity import fixture as human_fixture
from services.windows_native.tests.test_phase10_http import NoProviderPipeline
from services.windows_native import scene_review as review,auto_edit_timeline as timeline,auto_edit_analysis as analysis
from services.windows_native.contracts import WorkflowError,digest
from services.windows_native.store import Store
from services.windows_native.access import NativeAccess
from services.windows_native.server import LocalServer,Handler
from services.windows_native.media_frame_analysis import frame_path

class NativeSceneReviewTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SourceBrollVisionTests();self.f.setUp();self.row=self.f.complete(main=True)
    def tearDown(self):
        self.f.tearDown();self.f.doCleanups()
    def body(self,row=None,**change):
        f=self.f;f.project=timeline.view(f.store,f.project['id']);identifier=f.project['document']['canonical_timeline']['snapshot']['metadata']['source_analysis_id']
        return {'revision':f.project['revision'],'analysis_id':identifier,'reviewed_vision':f.ref(row or self.row),**change}
    def create(self,**change):
        f=self.f;result=review.create(f.store,f.config,f.project['id'],self.body(**change),official_vision=lambda:f.official)
        f.project=timeline.view(f.store,f.project['id']);return result

    def test_reviewed_mock_scores_match_local_baseline_and_deduplicate_without_edit_or_dispatch(self):
        f=self.f;before=copy.deepcopy(f.project['document']);page=self.create();value=page['items'][0]['recommendation'];result=value['result']
        self.assertFalse(result['semantic_vision_used']);self.assertFalse(result['prediction_confidence_calibrated'])
        self.assertEqual(value['reviewed_vision']['items'][0]['response_sha256'],self.row['response']['response_sha256'])
        self.assertEqual(value['reviewed_vision']['items'][0]['cost_operation_id'],self.row['cost_operation_id'])
        baseline=analysis.view(f.store,f.project['id'])['analyses'][0]
        for actual,original in zip(result['scenes'],baseline['scenes'],strict=True):
            for key in ('scene_id','start_seconds','end_seconds','semantic_label','description','subjects','quality_score','motion_score','speech_score','confidence'):
                self.assertEqual(actual[key],original[key])
        self.assertEqual([v['highlight_score'] for v in result['highlights']],[v['highlight_score'] for v in baseline['highlights']])
        self.assertEqual(f.project['document']['canonical_timeline'],before['canonical_timeline'])
        self.assertEqual(f.project['document']['auto_edit_analyses'],before['auto_edit_analyses']);self.assertIsNone(f.project['approval'])
        self.assertEqual(self.create(),page);self.assertEqual(len(f.calls),1)

    def test_supporting_result_cannot_replace_main_source_semantics(self):
        f=self.f;support=f.complete();before=f.store.get(f.project['id'])
        with self.assertRaisesRegex(WorkflowError,'NATIVE_SCENE_REVIEW_MAIN_SOURCE_REQUIRED'):self.create(row=support)
        self.assertEqual(f.store.get(f.project['id']),before);self.assertEqual(len(f.calls),2)

    def test_forged_raw_acknowledgement_hash_foreign_or_stale_request_refuses_atomically(self):
        f=self.f;before=f.store.get(f.project['id'])
        for change in ({'acknowledged_reviewed_result':1},{'acknowledged_protocol_mock':False},{'expected_result_sha256':'0'*64}):
            with self.assertRaises(WorkflowError):self.create(reviewed_vision=f.ref(self.row,**change))
        with self.assertRaises(WorkflowError):self.create(revision=f.project['revision']-1)
        other=f.store.duplicate(f.project['id'],f.project['revision']);body=self.body();body['revision']=other['revision']
        with self.assertRaises(WorkflowError):review.create(f.store,f.config,other['id'],body,official_vision=lambda:f.official)
        self.assertEqual(f.store.get(f.project['id']),before);self.assertEqual(len(f.calls),1)

    def test_rehashed_frozen_input_scores_source_and_mock_promotions_are_rejected(self):
        f=self.f;self.create();original=copy.deepcopy(f.project['document'])
        for mutate in (lambda v:v['source']['asset'].update(license='invented'),
            lambda v:v['source']['analysis']['scenes'][0].update(confidence=.99),
            lambda v:v['reviewed_vision']['items'][0].update(mock=False,semantic_inference_performed=True),
            lambda v:v['result']['scene_ranking'][0].update(highlight_score=.99),
            lambda v:v['result'].update(recommendation_only=1,prediction_confidence_calibrated=True),
            lambda v:v['result']['scenes'][0]['evidence'].update(vision_used=True)):
            document=copy.deepcopy(original);record=document['source_scene_recommendations'][0];value=record['recommendation'];mutate(value)
            value['fingerprint']=review.fingerprint(value['source'],value['reviewed_vision']);record['sha256']=digest(value)
            with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(document),f.project['id']))
            with self.assertRaises(WorkflowError):review.page(f.store,f.config,f.project['id'],official_vision=lambda:f.official)
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),f.project['id']))
        self.assertEqual(timeline.view(f.store,f.project['id']),f.project);self.assertEqual(len(f.calls),1)

    def test_missing_video_png_and_current_keys_do_not_prevent_original_history(self):
        f=self.f;page=self.create();project=copy.deepcopy(f.project)
        for frame in self.row['snapshot']['input_binding']['source_frame_evidence']:frame_path(f.root,frame).unlink()
        f.source_path.unlink()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY ACCESS')):
            reopened=Store(f.root);self.assertEqual(review.page(reopened,f.config,f.project['id']),page)
            self.assertEqual(timeline.view(reopened,f.project['id']),project)
        with self.assertRaises(WorkflowError):self.create()
        self.assertEqual(f.store.get(f.project['id'])['document'],project['document']);self.assertEqual(len(f.calls),1)

    def test_transcript_edit_blocks_new_old_result_reuse_but_keeps_original_recommendations(self):
        f=self.f;page=self.create();value=page['items'][0]['recommendation'];transcript=value['source']['analysis']['transcript']
        analysis.edit_transcript(f.store,f.project['id'],f.project['revision'],transcript['analysis_id'],{
            'expected_version':transcript['version'],'expected_timeline_version':f.project['shot_timeline']['version'],
            'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Explicit changed transcript fixture.'}]})
        f.project=timeline.view(f.store,f.project['id']);before=copy.deepcopy(f.project)
        self.assertEqual(review.page(f.store,f.config,f.project['id'])['items'],page['items'])
        with self.assertRaises(WorkflowError):self.create()
        self.assertEqual(f.store.get(f.project['id'])['document'],before['document']);self.assertEqual(len(f.calls),1)

    def test_duplicate_archives_original_recommendations_without_transfer_or_parent_mutation(self):
        f=self.f;page=self.create();before=copy.deepcopy(f.project);child=f.store.duplicate(f.project['id'],f.project['revision'])
        self.assertNotIn('source_scene_recommendations',child['document'])
        archived=child['document']['source_scene_inherited_reviewed_history'];self.assertEqual([v['original_record'] for v in archived],page['items'])
        self.assertTrue(all(v['authority_transferred'] is False and v['new_review_required'] is True for v in archived))
        self.assertEqual(review.page(f.store,f.config,child['id'])['items'],[])
        self.assertEqual(timeline.view(f.store,f.project['id']),before);self.assertEqual(len(f.calls),1)

    def test_signed_editor_saves_default_disabled_history_while_viewer_is_refused_before_body(self):
        f=self.f;raw,data=human_fixture('editor',workspace=f.workspace)
        access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),f.workspace)
        self.server=LocalServer(0,f.config,pipeline=NoProviderPipeline(),start_worker=False,access=access)
        self.cookie,session=access.login(raw);self.csrf=session.csrf;thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start()
        route='/api/projects/'+f.project['id']+'/auto-edit/scene-reviews';http=lambda *a,**kw:http_fixture.NativeAccessHTTPTests.request(self,*a,**kw)
        try:
            status,page,_=http('POST',route,self.body());self.assertEqual(status,200,page);self.assertEqual(len(page['items']),1)
            raw,data=human_fixture('viewer',workspace=f.workspace);self.server.access=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),f.workspace)
            self.server.access.bind_root(f.root);self.cookie,session=self.server.access.login(raw);self.csrf=session.csrf
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO FORBIDDEN REVIEW BODY')):self.assertEqual(http('POST',route,{})[0],403)
            self.assertEqual(http('GET',route)[1],page)
        finally:self.server.shutdown();self.server.server_close();thread.join()
        self.assertEqual(len(f.calls),1)

    def test_pure_nonmock_vector_changes_scene_semantics_but_never_admits_or_certifies_provider(self):
        f=self.f;page=self.create();value=page['items'][0]['recommendation'];synthetic=copy.deepcopy(value['reviewed_vision'])
        item=synthetic['items'][0];item['mock']=False;item['semantic_inference_performed']=True
        for scene in item['scenes']:scene['semantic_label']='Synthetic calculation only';scene['description']='Important neural network education'
        result=review.recommendations(value['source'],synthetic);self.assertTrue(result['semantic_vision_used'])
        self.assertTrue(any(v['evidence']['vision_used'] for v in result['scenes']));self.assertFalse(result['prediction_confidence_calibrated'])
        self.assertEqual(f.official.get(f.project['id'],self.row['vision_id']),self.row);self.assertTrue(self.row['result']['mock']);self.assertEqual(len(f.calls),1)
