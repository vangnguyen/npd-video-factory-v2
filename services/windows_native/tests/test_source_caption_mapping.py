"""Actual synthetic video/SRT ingestion; source mapping is not ASR or Owner UAT."""
import copy,json,subprocess,unittest
from services.windows_native.tests import test_narrated_media_tracks as fixture,test_source_media_tracks as uploads
from services.windows_native import source_media_tracks as media,narrated_timeline_editor as editor
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.shot_adapter import validate_document

def prepare(case):
    fixture.prepare(case);path=case.owned/'owned-moving-footage.mp4'
    subprocess.run([str(case.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-f','lavfi','-i','testsrc2=s=320x240:r=30:d=2',
        '-an','-c:v','libx264','-preset','ultrafast','-pix_fmt','yuv420p',str(path)],capture_output=True,check=True,timeout=30)
    case.video=uploads.upload(case,path.read_bytes(),'video','video/mp4')
    for index in range(2):
        p=case.store.shot_view(case.project['id']);shot=p['shot_timeline']['shots'][index]
        case.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':case.video['id'],'source_start':.4 if index==0 else .1,'motion':'none'}})

class SourceCaptionMappingTests(unittest.TestCase):
    def setUp(self):prepare(self)
    def tearDown(self):self.temp.cleanup()
    start=fixture.NarratedMediaTracksTests.start;finish=fixture.NarratedMediaTracksTests.finish;body=fixture.NarratedMediaTracksTests.body
    binding=fixture.NarratedMediaTracksTests.binding;page=fixture.NarratedMediaTracksTests.page
    subtitle_body=fixture.NarratedMediaTracksTests.subtitle_body;captions_body=fixture.NarratedMediaTracksTests.captions_body
    def mapped_body(self,**kwargs):return self.subtitle_body(timebase='source',source_video_asset_id=self.video['id'],source_video_asset_sha256=self.video['sha256'],**kwargs)
    def add(self,**kwargs):return media.add_subtitles(self.store,self.project['id'],self.mapped_body(**kwargs),actor_ref='explicit-synthetic-source-mapping-fixture')
    def test_actual_source_windows_map_trim_loop_and_reused_video_without_word_inference(self):
        before=self.store.get(self.project['id']);page=self.page();self.assertTrue(page['source_video_mapping_available']);self.assertEqual(page['source_video_assets'][0]['asset_id'],self.video['id'])
        out=self.add();self.assertEqual(out['caption_count'],4);p=self.store.get(self.project['id']);state=p['document']['canonical_timeline'];clips=next(t for t in state['snapshot']['tracks'] if t['track_id']==out['track_id'])['clips']
        self.assertEqual([(c['timeline_start'],c['duration']) for c in clips],[(0,.6),(.9,.7),(1.7,.9),(2.9,.4)])
        self.assertTrue(all(c['metadata']['measured_source_words']==[] for c in clips));self.assertEqual(before['jobs'],p['jobs']);validate_document(p['document'])
        self.assertTrue(all(c['source_video_mapping_mode']=='follow_video' for c in self.page()['captions']))
    def test_missing_wrong_foreign_or_incomplete_binding_is_atomic(self):
        before=self.store.get(self.project['id']);valid=self.mapped_body()
        for bad in [{k:v for k,v in valid.items() if k not in {'source_video_asset_id','source_video_asset_sha256'}},
            {**valid,'source_video_asset_sha256':'0'*64},{**valid,'source_video_asset_id':self.voice['id'],'source_video_asset_sha256':self.voice['sha256']},
            {**valid,'source_video_asset_id':'a'*32+'.mp4'},{**valid,'source_video_asset_sha256':None},{**valid,'timebase':'timeline'},{**valid,'source_mapping_graph':{}}]:
            with self.assertRaises(WorkflowError):media.add_subtitles(self.store,self.project['id'],bad,actor_ref='fixture')
            self.assertEqual(before,self.store.get(self.project['id']))
    def test_shot_source_trim_reflows_same_canonical_cues_without_new_import_or_audio_changes(self):
        result=self.add();before=self.store.shot_view(self.project['id']);history=copy.deepcopy(before['document']['source_media_track_imports']);audio=[t for t in before['document']['canonical_timeline']['snapshot']['tracks'] if t['type']=='audio']
        shot=before['shot_timeline']['shots'][0];after=self.store.mutate_shots(before['id'],before['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':.2}})
        clips=next(t['clips'] for t in after['document']['canonical_timeline']['snapshot']['tracks'] if t['track_id']==result['track_id'])
        self.assertEqual(clips[0]['timeline_start'],0);self.assertEqual(clips[0]['duration'],.8);self.assertEqual(clips[1]['timeline_start'],1.1)
        self.assertEqual(after['document']['source_media_track_imports'],history);self.assertEqual([t for t in after['document']['canonical_timeline']['snapshot']['tracks'] if t['type']=='audio'],audio);validate_document(after['document'])
    def test_locked_mapping_refuses_timing_change_but_allows_unrelated_shot_text(self):
        result=self.add();page=editor.view(self.store,self.project['id'],self.workspace)
        editor.edit(self.store,self.project['id'],{'revision':page['revision'],'expected_version':page['timeline_version'],'timeline_sha256':page['timeline_sha256'],
            'operations':[{'type':'set_track_state','track_id':result['track_id'],'locked':True}]},self.workspace)
        p=self.store.shot_view(self.project['id']);shot=p['shot_timeline']['shots'][0]
        with self.assertRaisesRegex(WorkflowError,'TRACK_LOCKED'):self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':.2}})
        self.assertEqual(p,self.store.shot_view(self.project['id']))
        self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Chỉ đổi nhãn hình'}})
    def test_actual_loop_repeats_only_intersecting_source_cues_on_the_same_shot(self):
        p=self.store.shot_view(self.project['id']);shot=p['shot_timeline']['shots'][0]
        self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':1.5}})
        result=self.add();p=self.store.get(p['id']);clips=next(t['clips'] for t in p['document']['canonical_timeline']['snapshot']['tracks'] if t['track_id']==result['track_id'])
        self.assertEqual([(c['timeline_start'],c['duration']) for c in clips],[(0,.5),(.6,.9),(1.7,.9),(2.9,.4)])
        self.assertNotEqual(clips[0]['metadata']['source_video_mapping']['video_clip']['clip_id'],clips[1]['metadata']['source_video_mapping']['video_clip']['clip_id']);validate_document(p['document'])
    def test_offset_outside_canvas_requires_explicit_trim_and_retains_adjusted_source_evidence(self):
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'OUT_OF_BOUNDS'):self.add(offset_seconds=.1)
        self.assertEqual(before,self.store.get(self.project['id']))
        result=self.add(offset_seconds=-.2,trim_to_timeline=True);self.assertEqual(result['clipped_intervals'],1)
        p=self.store.get(self.project['id']);clips=next(t['clips'] for t in p['document']['canonical_timeline']['snapshot']['tracks'] if t['track_id']==result['track_id'])
        self.assertEqual((clips[0]['timeline_start'],clips[0]['duration'],clips[0]['source_start']),(0,.4,.6));validate_document(p['document'])
    def test_variants_rebind_deterministic_cues_without_transferring_review_or_replay(self):
        from services.windows_native.narrated_variants import NativeNarratedVariants
        from services.windows_native.narrated_variants_models import Create
        result=self.add();before=self.store.get(self.project['id']);state=before['document']['canonical_timeline']
        batch,_=NativeNarratedVariants(self.store).create(before['id'],Create(revision=before['revision'],expected_version=state['version'],
            expected_prepared_reference_sha256=digest(before['document']['prepared_narration']),profile_refs=['social-square@1'],request_key='explicit-source-caption-variant-fixture'),actor='FIXTURE')
        child=self.store.get(batch['result']['variants'][0]['project_id']);validate_document(child['document'])
        self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[]);self.assertEqual(self.store.get(before['id']),before)
        row=child['document']['source_media_track_imports'][0];self.assertNotEqual(row['import_id'],result['import_id']);self.assertIsNone(row['request_key_sha256'])
        self.assertTrue(all(c['metadata']['native_media_import_id']==row['import_id'] for t in child['document']['canonical_timeline']['snapshot']['tracks'] for c in t['clips'] if c['metadata'].get('source_video_mapping')))
    def test_human_layout_keeps_source_video_in_publishing_rights_even_when_removed_from_shots(self):
        from services.windows_native.source_assets import used_timeline_asset_ids
        self.add();media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='FIXTURE')
        for index in range(2):
            p=self.store.shot_view(self.project['id']);image=next(v for v in p['document']['assets'] if v['kind']=='image');shot=p['shot_timeline']['shots'][index]
            self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':image['id'],'source_start':0,'motion':'none'}})
        snapshot=self.store.get(self.project['id'])['document']['canonical_timeline']['snapshot']
        self.assertTrue(all(c['metadata'].get('native_asset_id')!=self.video['id'] for t in snapshot['tracks'] if t['type']=='video' for c in t['clips']))
        self.assertIn(self.video['id'],used_timeline_asset_ids(snapshot));validate_document(self.store.get(self.project['id'])['document'])
    def test_human_caption_layout_is_explicit_and_does_not_reflow_or_infer_words(self):
        self.add();payload=self.captions_body();media.edit_captions(self.store,self.project['id'],payload,actor_ref='explicit-human-layout-fixture')
        before=self.store.shot_view(self.project['id']);caps=[t for t in before['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles'];shot=before['shot_timeline']['shots'][0]
        after=self.store.mutate_shots(before['id'],before['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':.2}})
        self.assertEqual([t for t in after['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles'],caps);self.assertTrue(all(c['source_video_mapping_mode']=='human_layout' for c in self.page()['captions']))
    def test_explicit_new_source_import_resets_advanced_manual_layout_without_rewriting_its_history(self):
        result=self.add();page=editor.view(self.store,self.project['id'],self.workspace);clip=self.page()['captions'][0]['clip_id']
        editor.edit(self.store,self.project['id'],{'revision':page['revision'],'expected_version':page['timeline_version'],'timeline_sha256':page['timeline_sha256'],
            'operations':[{'type':'move','clip_id':clip,'timeline_start':.05}]},self.workspace)
        manual=self.store.get(self.project['id']);self.assertIn(result['track_id'],manual['document']['canonical_timeline']['snapshot']['metadata']['narrated_caption_edited_tracks'])
        history=copy.deepcopy(manual['document']['source_media_track_imports']);self.add()
        new=self.store.shot_view(self.project['id']);self.assertNotIn(result['track_id'],new['document']['canonical_timeline']['snapshot']['metadata']['narrated_caption_edited_tracks'])
        self.assertEqual(new['document']['source_media_track_imports'][:-1],history);self.assertTrue(all(c['source_video_mapping_mode']=='follow_video' for c in self.page()['captions']))
        shot=new['shot_timeline']['shots'][0];after=self.store.mutate_shots(new['id'],new['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'source_start':.2}})
        first=self.page()['captions'][0];self.assertEqual((first['timeline_start'],first['duration']),(0,.8));validate_document(after['document'])
    def test_video_disappearance_requires_review_and_disabled_mapping_retains_evidence(self):
        result=self.add();p=self.store.shot_view(self.project['id']);original=next(v for v in p['document']['assets'] if v['kind']=='image')
        for index in range(2):
            current=self.store.shot_view(self.project['id']);shot=current['shot_timeline']['shots'][index]
            if index==1:
                with self.assertRaisesRegex(WorkflowError,'NO_VIDEO_REVIEW_REQUIRED'):self.store.mutate_shots(current['id'],current['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':original['id'],'motion':'none','source_start':0}})
                page=editor.view(self.store,current['id'],self.workspace);editor.edit(self.store,current['id'],{'revision':page['revision'],'expected_version':page['timeline_version'],'timeline_sha256':page['timeline_sha256'],
                    'operations':[{'type':'set_track_state','track_id':result['track_id'],'disabled':True}]},self.workspace)
                current=self.store.shot_view(self.project['id']);shot=current['shot_timeline']['shots'][index]
            self.store.mutate_shots(current['id'],current['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':original['id'],'motion':'none','source_start':0}})
        self.assertTrue(all(c['source_video_mapping_mode']=='disabled' for c in self.page()['captions']))
    def test_duplicate_rebinds_mapping_without_replay_or_approval_authority(self):
        result=self.add();p=self.store.get(self.project['id']);child=self.store.duplicate(p['id'],p['revision']);self.assertIsNone(child['approval']);validate_document(child['document'])
        row=child['document']['source_media_track_imports'][0];self.assertIsNone(row['request_key_sha256']);self.assertNotEqual(row['import_id'],result['import_id']);self.assertEqual(row['source_video_reference']['asset_sha256'],self.video['sha256'])
    def test_original_video_bytes_are_verified_before_replay_edit_and_render(self):
        body=self.mapped_body();self.add();path=self.root/'assets'/self.video['id'];before=path.read_bytes();path.write_bytes(b'corrupt owned fixture')
        try:
            with self.assertRaises(WorkflowError):media.add_subtitles(self.store,self.project['id'],body,actor_ref='fixture')
            from services.windows_native.narrated_media_mix import verify
            with self.assertRaises(WorkflowError):verify(self.config,self.store.get(self.project['id'])['document'])
        finally:path.write_bytes(before)
    def test_snapshot_mapping_tamper_is_not_accepted_even_with_new_snapshot_digest(self):
        self.add();doc=copy.deepcopy(self.store.get(self.project['id'])['document']);clip=next(c for t in doc['canonical_timeline']['snapshot']['tracks'] for c in t['clips'] if c['metadata'].get('source_video_mapping'))
        clip['metadata']['source_video_mapping']['video_clip']['source_start']=.3;doc['canonical_timeline']['sha256']=digest(doc['canonical_timeline']['snapshot'])
        with self.assertRaises(WorkflowError):validate_document(doc)
    def test_historical_timeline_payload_hash_remains_unchanged_when_new_binding_is_absent(self):
        from services.windows_native.source_media_track_models import Subtitles
        body=self.subtitle_body();old=Subtitles.model_validate(body).model_dump(mode='json',exclude={'request_key','source_video_asset_id','source_video_asset_sha256'})
        self.assertEqual(media._request(Subtitles.model_validate(body)),old)
        first=media.add_subtitles(self.store,self.project['id'],body,actor_ref='fixture');replay=media.add_subtitles(self.store,self.project['id'],body,actor_ref='fixture');self.assertTrue(replay['replayed']);self.assertEqual(first['request_sha256'],digest(old))

if __name__=='__main__':unittest.main()
