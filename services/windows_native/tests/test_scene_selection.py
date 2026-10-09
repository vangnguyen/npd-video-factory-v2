"""Explicit reviewed selection, real source bytes, saved ASR and Vision mocks."""
import copy,threading,unittest,uuid
from services.windows_native.tests import test_scene_review as fixture,test_access_http as http_fixture
from services.windows_native import scene_review,scene_selection,auto_edit_timeline as timeline,source_shorts as shorts,auto_edit_analysis as analysis
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.server import LocalServer
from services.windows_native.access import NativeAccess
from services.windows_native.tests.test_phase10_http import NoProviderPipeline

class NativeSceneSelectionTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.NativeSceneReviewTests();self.f.setUp();self.page=self.f.create();self.record=self.page['items'][0]
        self.source=self.f.f;self.project=self.source.project
    def tearDown(self):self.f.tearDown()
    def ref(self,**changes):
        return {'recommendation_id':self.record['recommendation']['recommendation_id'],'expected_recommendation_sha256':self.record['sha256'],
            'acknowledged_reviewed_recommendation':True,'acknowledged_protocol_mock':True,**changes}
    def body(self,**changes):
        value=self.record['recommendation'];a=value['source']['analysis']
        return {'analysis_id':a['analysis_id'],'transcript_id':a['transcript']['transcript_id'],'expected_version':self.project['shot_timeline']['version'],
            'aspect_ratio':'9:16','reviewed_scene':self.ref(),'reviewed_highlight_id':value['result']['highlights'][0]['highlight_id'],**changes}
    def short_body(self,**changes):
        body=self.body();body.pop('reviewed_highlight_id');body.update(count=3,maximum_duration_seconds=3,request_key=uuid.uuid4().hex)
        return {**body,**changes}

    def test_explicit_highlight_uses_original_rank_and_whole_speech_canonical_history(self):
        f=self.source;before=copy.deepcopy(self.project);checksum=file_sha(f.source_path)
        value=timeline.create(f.store,f.project['id'],f.project['revision'],self.body(),config=f.config,official_vision=lambda:f.official)
        metadata=value['shot_timeline']['snapshot']['metadata'];self.assertEqual(metadata['reviewed_scene_selection'],scene_selection.lineage(self.record))
        self.assertEqual(metadata['reviewed_highlight_id'],self.body()['reviewed_highlight_id'])
        self.assertEqual(value['document']['source_scene_recommendations'],before['document']['source_scene_recommendations'])
        self.assertEqual(value['shot_timeline']['version'],before['shot_timeline']['version']+1);self.assertIsNone(value['approval'])
        words=[w for s in self.record['recommendation']['source']['analysis']['transcript']['segments'] for w in s['words']]
        for point in metadata['source_selection']['word_safe_window']:self.assertFalse(any(w['start_seconds']<point<w['end_seconds'] for w in words))
        self.assertEqual(file_sha(f.source_path),checksum);self.assertEqual(len(f.calls),1)
        self.assertIn(before['document'],[v['document'] for v in f.store.versions(f.project['id'])])
        child=f.store.duplicate(value['id'],value['revision']);meta=child['shot_timeline']['snapshot']['metadata']
        self.assertNotIn('reviewed_scene_selection',meta);self.assertFalse(meta['inherited_reviewed_scene_selection']['authority_transferred'])
        self.assertEqual(meta['inherited_reviewed_scene_selection']['original_selection'],metadata['reviewed_scene_selection'])

    def test_bad_ack_hash_highlight_window_and_foreign_recommendation_refuse_without_mutation(self):
        f=self.source;before=f.store.get(f.project['id'])
        for change in ({'reviewed_scene':self.ref(acknowledged_reviewed_recommendation=1)},
            {'reviewed_scene':self.ref(acknowledged_protocol_mock=False)},
            {'reviewed_scene':self.ref(expected_recommendation_sha256='0'*64)},
            {'reviewed_highlight_id':'hig_'+'0'*24},{'source_window':(0,3)}, {'reviewed_scene':None}):
            with self.assertRaises(WorkflowError):timeline.create(f.store,f.project['id'],f.project['revision'],self.body(**change),config=f.config,official_vision=lambda:f.official)
        child=f.store.duplicate(f.project['id'],f.project['revision']);body=self.body(expected_version=1)
        with self.assertRaises(WorkflowError):timeline.create(f.store,child['id'],child['revision'],body,config=f.config,official_vision=lambda:f.official)
        self.assertEqual(f.store.get(f.project['id']),before);self.assertEqual(len(f.calls),1)

    def test_reviewed_shorts_keep_exact_parent_rank_lineage_and_idempotent_history_without_source_file(self):
        f=self.source;before=timeline.view(f.store,f.project['id']);body=self.short_body();checksum=file_sha(f.source_path)
        result=shorts.create(f.store,f.config,f.project['id'],f.project['revision'],body,official_vision=lambda:f.official)
        expected=self.record['recommendation']['result']['scene_ranking'];batch=result['batch'];proof=scene_selection.lineage(self.record)
        self.assertEqual(batch['scene_evidence']['reviewed_scene_selection'],proof)
        self.assertGreater(batch['generated_count'],0);self.assertLessEqual(batch['generated_count'],len(expected))
        self.assertEqual([v['evidence']['score'] for v in batch['drafts']],[v['highlight_score'] for v in expected[:batch['generated_count']]])
        for project,entry in zip(result['projects'],batch['drafts'],strict=True):
            self.assertEqual(entry['evidence']['reviewed_scene_selection'],proof);self.assertIsNone(project['approval']);self.assertEqual(project['jobs'],[])
            meta=project['shot_timeline']['snapshot']['metadata'];self.assertEqual(meta['highlight_draft']['reviewed_scene_selection'],proof)
            self.assertEqual(meta['source_short']['evidence']['reviewed_scene_selection'],proof)
            self.assertNotIn('source_scene_recommendations',project['document'])
            self.assertTrue(all(v['authority_transferred'] is False for v in project['document']['source_scene_inherited_reviewed_history']))
        self.assertEqual(timeline.view(f.store,f.project['id']),before);self.assertEqual(file_sha(f.source_path),checksum)
        self.assertEqual(shorts.create(f.store,f.config,f.project['id'],f.project['revision'],body),result)
        f.source_path.unlink();self.assertEqual(shorts.create(f.store,f.config,f.project['id'],f.project['revision'],body),result)
        with self.assertRaises(WorkflowError):shorts.create(f.store,f.config,f.project['id'],f.project['revision'],{**body,'request_key':uuid.uuid4().hex})
        self.assertEqual(len(f.calls),1)

    def test_changed_transcript_refuses_reviewed_short_and_timeline_but_keeps_original_history(self):
        f=self.source;a=self.record['recommendation']['source']['analysis'];transcript=a['transcript'];old=self.body();old_shorts=self.short_body()
        analysis.edit_transcript(f.store,f.project['id'],f.project['revision'],a['analysis_id'],{'expected_version':transcript['version'],
            'expected_timeline_version':f.project['shot_timeline']['version'],'segments':[{'segment_id':transcript['segments'][0]['segment_id'],'text':'Changed fixture'}]})
        project=timeline.view(f.store,f.project['id']);old['expected_version']=old_shorts['expected_version']=project['shot_timeline']['version']
        current=analysis.view(f.store,project['id'])['analyses'][0]['analysis']['transcript']['transcript_id'];old['transcript_id']=old_shorts['transcript_id']=current
        with self.assertRaises(WorkflowError):timeline.create(f.store,project['id'],project['revision'],old,config=f.config,official_vision=lambda:f.official)
        with self.assertRaises(WorkflowError):shorts.create(f.store,f.config,project['id'],project['revision'],old_shorts,official_vision=lambda:f.official)
        self.assertEqual(timeline.view(f.store,project['id']),project);self.assertEqual(scene_review.page(f.store,f.config,project['id'])['items'],self.page['items'])

    def test_signed_disabled_provider_server_accepts_explicit_shorts_and_canonical_request(self):
        f=self.source;access=NativeAccess(f.verifier,f.workspace);self.cookie,session=access.login(f.raw);self.csrf=session.csrf
        self.server=LocalServer(0,f.config,pipeline=NoProviderPipeline(),start_worker=False,access=access)
        thread=threading.Thread(target=self.server.serve_forever,daemon=True);thread.start();http=lambda *a,**kw:http_fixture.NativeAccessHTTPTests.request(self,*a,**kw)
        base='/api/projects/'+f.project['id']
        try:
            code,result,_=http('POST',base+'/auto-edit/shorts',{'revision':self.project['revision'],'payload':self.short_body()})
            self.assertEqual(code,200,result);self.assertIn('reviewed_scene_selection',result['batch']['scene_evidence'])
            code,value,_=http('POST',base+'/auto-edit/timeline',{'revision':self.project['revision'],'action':'create','payload':self.body()})
            self.assertEqual(code,200,value);self.assertEqual(value['shot_timeline']['snapshot']['metadata']['reviewed_scene_selection'],scene_selection.lineage(self.record))
        finally:self.server.shutdown();self.server.server_close();thread.join()
        self.assertEqual(len(f.calls),1)
