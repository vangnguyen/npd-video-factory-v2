"""Original Source/Vision fixture lineage; sparse-position branch is pure synthetic."""
import copy,json,unittest,http.client,threading
from unittest.mock import patch
from services.windows_native.tests import test_source_broll_vision as fixture
from services.windows_native import source_reframe as reframe,source_reframe_vision as review,auto_edit_timeline as timeline,auto_edit_analysis as analysis
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.media_frame_analysis import frame_path
from services.windows_native.store import Store
from app.timeline_reframe import crop_keyframes
from app.auto_edit_models import MediaMetadata

class SourceReframeVisionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.SourceBrollVisionTests();self.f.setUp();self.row=self.f.complete(main=True)
    def tearDown(self):self.f.tearDown();self.f.doCleanups()
    def body(self,**changes):
        f=self.f;f.project=timeline.view(f.store,f.project['id'])
        return {'expected_version':f.project['shot_timeline']['version'],'aspect_ratio':'9:16','mode':'reviewed_vision',
            'reviewed_vision':f.ref(self.row),**changes}
    def apply(self,**changes):
        f=self.f;body=self.body(**changes);f.project=reframe.apply(f.store,f.project['id'],f.project['revision'],body,config=f.config,official_vision=lambda:f.official)
        return f.project
    def test_mock_four_ratios_keep_center_fallback_original_cost_media_audio_captions_and_nullable_tracking(self):
        f=self.f;before=copy.deepcopy(f.project);audio=[v for v in before['shot_timeline']['snapshot']['tracks'] if v['type']!='video'];sha=file_sha(f.source_path)
        for ratio in ('9:16','16:9','1:1','4:5'):
            p=self.apply(aspect_ratio=ratio);meta=p['shot_timeline']['snapshot']['metadata'];saved=p['document']['source_reframe_reviews'][-1]
            self.assertEqual(meta['source_reframe_plan']['plan']['strategy'],'center_crop');self.assertEqual(meta['source_reframe_plan']['plan']['fallback'],'center_crop')
            self.assertTrue(meta['reframe_review']['needs_attention']);self.assertIsNone(meta['reframe_review']['tracking_confidence'])
            self.assertEqual(meta['reviewed_reframe_selection'],review.lineage(saved));self.assertEqual(saved['review']['sample_evidence'],[])
            self.assertEqual(saved['review']['reviewed_vision']['items'][0]['response_sha256'],self.row['response']['response_sha256'])
            self.assertEqual(saved['review']['reviewed_vision']['items'][0]['cost_operation_id'],self.row['cost_operation_id'])
            self.assertEqual([v for v in p['shot_timeline']['snapshot']['tracks'] if v['type']!='video'],audio);self.assertIsNone(p['approval'])
        self.assertEqual(file_sha(f.source_path),sha);self.assertEqual(f.official.get(f.project['id'],self.row['vision_id']),self.row);self.assertEqual(len(f.calls),1)
    def test_raw_reviews_supporting_hash_scope_modes_stale_and_locks_refuse_atomically(self):
        f=self.f;before=copy.deepcopy(f.project)
        for change in ({'reviewed_vision':f.ref(self.row,acknowledged_reviewed_result=1)},
            {'reviewed_vision':f.ref(self.row,acknowledged_protocol_mock=False)},
            {'reviewed_vision':f.ref(self.row,expected_result_sha256='0'*64)},
            {'mode':'center_crop'},{'points':[{'time':0,'x':.5,'y':.5}]},{'expected_version':999}):
            with self.assertRaises(WorkflowError):self.apply(**change)
            self.assertEqual(timeline.view(f.store,f.project['id']),before)
        support=f.complete();
        with self.assertRaisesRegex(WorkflowError,'MAIN_SOURCE_REQUIRED'):self.apply(reviewed_vision=f.ref(support))
        self.assertEqual(timeline.view(f.store,f.project['id']),before)
        track=next(v for v in before['shot_timeline']['snapshot']['tracks'] if v['kind']=='source')
        f.project=timeline.edit(f.store,f.project['id'],f.project['revision'],{'expected_version':f.project['shot_timeline']['version'],
            'operations':[{'type':'set_track_state','track_id':track['track_id'],'locked':True}]});before=copy.deepcopy(f.project)
        with self.assertRaisesRegex(WorkflowError,'PLAN_INVALID_OR_LOCKED'):self.apply()
        self.assertEqual(timeline.view(f.store,f.project['id']),before)
    def test_changed_transcript_and_pixels_block_new_selection_original_history_remains_keyless(self):
        f=self.f;self.apply();records=copy.deepcopy(f.project['document']['source_reframe_reviews']);saved=records[-1]['review'];transcript=saved['source']['analysis']['transcript']
        analysis.edit_transcript(f.store,f.project['id'],f.project['revision'],transcript['analysis_id'],{
            'expected_version':transcript['version'],'expected_timeline_version':f.project['shot_timeline']['version'],
            'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Explicit changed transcript fixture.'}]})
        f.project=timeline.view(f.store,f.project['id']);before=copy.deepcopy(f.project)
        with self.assertRaises(WorkflowError):self.apply()
        self.assertEqual(timeline.view(f.store,f.project['id']),before)
        for frame in self.row['snapshot']['input_binding']['source_frame_evidence']:frame_path(f.root,frame).unlink()
        f.source_path.unlink()
        with patch('services.windows_native.assemblyai_connection._dpapi',side_effect=AssertionError('NO HISTORY KEY')):
            self.assertEqual(timeline.view(Store(f.root),f.project['id']),before)
        with self.assertRaises(WorkflowError):self.apply()
        self.assertEqual(f.store.get(f.project['id'])['document'],before['document']);self.assertEqual(len(f.calls),1)
    def test_rehashed_history_mock_confidence_authority_plan_and_original_source_promotions_refuse(self):
        f=self.f;self.apply();original=copy.deepcopy(f.project['document'])
        for mutate in (lambda v:v.update(tracking_confidence=.9),lambda v:v.update(continuous_tracking_performed=True),
            lambda v:v['plan'].update(strategy='subject_samples',confidence=.9,fallback='none'),
            lambda v:v['reviewed_vision']['items'][0].update(mock=False,semantic_inference_performed=True),
            lambda v:v['source']['asset'].update(license='invented'),lambda v:v.update(publishing_authorized=1)):
            doc=copy.deepcopy(original);saved=doc['source_reframe_reviews'][-1];mutate(saved['review']);saved['sha256']=digest(saved['review'])
            meta=doc['canonical_timeline']['snapshot']['metadata'];meta['reviewed_reframe_selection']=review.lineage(saved)
            doc['canonical_timeline']['sha256']=digest(doc['canonical_timeline']['snapshot'])
            with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),f.project['id']))
            with self.assertRaises(WorkflowError):timeline.view(f.store,f.project['id'])
        with f.store.transaction() as con:con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(original),f.project['id']))
        self.assertEqual(timeline.view(f.store,f.project['id']),f.project)
    def test_manual_replace_restore_and_duplicate_do_not_transfer_review_authority(self):
        f=self.f;before=copy.deepcopy(f.project);self.apply();saved=copy.deepcopy(f.project)
        child=f.store.duplicate(f.project['id'],f.project['revision']);meta=child['shot_timeline']['snapshot']['metadata']
        self.assertNotIn('source_reframe_reviews',child['document']);self.assertNotIn('reviewed_reframe_selection',meta)
        inherited=child['document']['source_reframe_inherited_reviewed_history']
        self.assertEqual(inherited[0]['original_record'],saved['document']['source_reframe_reviews'][0]);self.assertFalse(inherited[0]['authority_transferred'])
        self.assertTrue(inherited[0]['new_review_required']);self.assertFalse(meta['inherited_reviewed_reframe_selection']['authority_transferred'])
        f.project=reframe.apply(f.store,f.project['id'],f.project['revision'],{'expected_version':f.project['shot_timeline']['version'],
            'aspect_ratio':'9:16','mode':'manual_override','points':[{'time':0,'x':.5,'y':.5}]})
        self.assertNotIn('reviewed_reframe_selection',f.project['shot_timeline']['snapshot']['metadata'])
        self.assertEqual(f.project['document']['source_reframe_reviews'],saved['document']['source_reframe_reviews'])
        f.project=timeline.restore(f.store,f.project['id'],f.project['revision'],{'expected_version':f.project['shot_timeline']['version'],'restore_revision':before['revision']})
        self.assertEqual(f.project['shot_timeline']['snapshot'],before['shot_timeline']['snapshot']);self.assertEqual(len(f.calls),1)
    def test_pure_synthetic_nonmock_samples_bind_nullable_confidence_and_geometric_fallback(self):
        # Pure algorithm branch only. Never stored as genuine journal/provider acceptance.
        f=self.f;source=review.source(f.project,f.project['shot_timeline']['snapshot']['metadata']['source_analysis_id'],f.root)
        item={'mock':False,'semantic_inference_performed':True,'frames':copy.deepcopy(self.row['result']['frames'])};context={'items':[item]}
        for frame in item['frames']:
            frame['confidence']=.9;frame['composition']['safe_crop']=True;frame['composition']['primary_subject_box']={'x':.2,'y':.4,'width':.1,'height':.1}
        result,samples,basis=review.plan(source,context,'9:16','explicit_pure_synthetic_crop')
        self.assertEqual(result.strategy,'subject_samples');self.assertIsNone(result.confidence);self.assertIsNone(result.subject_track_id);self.assertTrue(result.needs_attention)
        self.assertEqual(len(samples),len(item['frames']));self.assertIn('not_continuous_tracking',basis)
        points=crop_keyframes(result,MediaMetadata.model_validate(source['analysis']['source_media']))
        self.assertEqual(points[0]['time'],0);self.assertGreater(points[-1]['time'],2.9)
        item['frames'][0]['composition']['primary_subject_box']['width']=.7
        result,samples,basis=review.plan(source,context,'9:16','explicit_pure_synthetic_crop')
        self.assertEqual(result.fallback,'center_crop');self.assertEqual(samples,[]);self.assertIn('does_not_fit',basis)
        item['frames'][0]['confidence']=.2
        self.assertEqual(review.plan(source,context,'9:16','explicit_pure_synthetic_crop')[0].fallback,'center_crop')
    def test_signed_default_disabled_editor_reuses_original_result_and_viewer_is_refused_before_body(self):
        from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
        from services.windows_native.tests.test_human_identity import fixture as human
        from services.windows_native.tests.test_phase10_http import NoProviderPipeline
        from services.windows_native.access import NativeAccess
        from services.windows_native.server import LocalServer,Handler
        f=self.f;raw,data=human('editor',workspace=f.workspace)
        identity=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(data),max_token_ttl_seconds=86400),f.workspace)
        cookie,session=identity.login(raw);pipeline=NoProviderPipeline();server=LocalServer(0,f.config,pipeline=pipeline,start_worker=False,access=identity)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();route='/api/projects/'+f.project['id']+'/auto-edit/timeline'
        def send(body,cookie_value=cookie,csrf=session.csrf):
            conn=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=10)
            conn.request('POST',route,json.dumps(body),headers={'Cookie':'vf_native_session='+cookie_value,'X-VF-CSRF':csrf,'Content-Type':'application/json'})
            response=conn.getresponse();result=(response.status,json.loads(response.read()));conn.close();return result
        try:
            body={'revision':f.project['revision'],'action':'reframe','payload':self.body()};before=f.store.get(f.project['id'])
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO UNAUTHENTICATED BODY')):self.assertEqual(send(body,cookie_value='')[0],401)
            self.assertEqual(send(body,csrf='invalid')[0],403);self.assertEqual(f.store.get(f.project['id']),before)
            self.assertFalse(server.official_vision.states()['enabled']);code,value=send(body);self.assertEqual(code,200,value)
            self.assertEqual(value['shot_timeline']['snapshot']['metadata']['reviewed_reframe_selection']['original_response_sha256'],self.row['response']['response_sha256'])
            self.assertEqual(send(body)[0],409);self.assertEqual(pipeline.calls,0);self.assertEqual(len(f.calls),1)
            viewer_raw,viewer_data=human('viewer',workspace=f.workspace)
            viewer=NativeAccess(HumanAuthVerifier(HumanAuthRegistry.model_validate(viewer_data),max_token_ttl_seconds=86400),f.workspace)
            viewer_cookie,viewer_session=viewer.login(viewer_raw);server.access=viewer
            with patch.object(Handler,'read_body',side_effect=AssertionError('NO VIEWER BODY')):self.assertEqual(send(body,cookie_value=viewer_cookie,csrf=viewer_session.csrf)[0],403)
        finally:server.shutdown();server.server_close();thread.join()
