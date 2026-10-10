"""Owned real Source media + saved ASR fixture; no provider, browser or Owner UAT."""
import copy,unittest
from services.windows_native.tests import test_source_media_tracks as fixture
from services.windows_native import source_media_tracks as media,source_linked_edit as linked,auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError

class SourceCaptionRetimingTests(unittest.TestCase):
    setUp=fixture.SourceMediaTracksTests.setUp;tearDown=fixture.SourceMediaTracksTests.tearDown
    page=fixture.SourceMediaTracksTests.page;binding=fixture.SourceMediaTracksTests.binding;subtitle_body=fixture.SourceMediaTracksTests.subtitle_body;captions_body=fixture.SourceMediaTracksTests.captions_body
    def mapped(self,**extras):return media.add_subtitles(self.store,self.project['id'],self.subtitle_body(timebase='source',
        source_video_asset_id=self.video['id'],source_video_asset_sha256=self.video['sha256'],**extras),actor_ref='OWNED SOURCE FIXTURE')
    def edit_video(self,**op):
        p=timeline.view(self.store,self.project['id']);clip=next(c for t in p['shot_timeline']['snapshot']['tracks'] if t['type']=='video' and t['kind']=='source' for c in t['clips'])
        return linked.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],'operation':{'clip_id':clip['clip_id'],**op}})
    def captions(self,p=None):
        p=p or self.store.get(self.project['id']);return [t for t in p['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='subtitles']
    def test_explicit_Source_video_selection_maps_current_canonical_windows_and_has_no_word_inference(self):
        before=self.store.get(self.project['id']);result=self.mapped();self.assertEqual(result['caption_count'],2);self.assertEqual(result['source_video_asset_id'],self.video['id'])
        self.assertTrue(all(c['source_video_mapping_mode']=='follow_video' and not c['has_word_timing'] for c in self.page()['captions']))
        self.assertEqual(self.store.get(self.project['id'])['jobs'],before['jobs']);timeline.validate_document(self.store.get(self.project['id'])['document'])
    def test_linked_speed_reflows_source_cues_preserves_import_history_and_does_not_hold_old_canvas_open(self):
        result=self.mapped();before=self.store.get(self.project['id']);history=copy.deepcopy(before['document']['source_media_track_imports'])
        after=self.edit_video(type='set_clip_properties',speed=2);caps=self.page()['captions']
        self.assertEqual([(c['timeline_start'],c['duration']) for c in caps],[(.05,.45),(.65,.45)])
        self.assertEqual(after['shot_timeline']['snapshot']['duration_seconds'],1.5);self.assertEqual(after['document']['source_media_track_imports'],history)
        self.assertTrue(all(c['import_id']==result['import_id'] for c in caps));self.assertIsNone(after['approval'])
        for track in after['shot_timeline']['snapshot']['tracks']:
            if track['kind'] in {'source','original_audio'}:self.assertTrue(all(c['speed']==2 for c in track['clips']))
    def test_linked_split_duplicate_and_reorder_reflow_same_SRT_with_new_source_windows(self):
        self.mapped();p=self.edit_video(type='split',at_seconds=1.5);self.assertEqual(len(self.page()['captions']),3)
        p=self.edit_video(type='duplicate',timeline_start=3);self.assertEqual(p['shot_timeline']['snapshot']['duration_seconds'],4.5)
        self.assertEqual(len(self.page()['captions']),5);p=self.edit_video(type='reorder',target_index=2)
        timeline.validate_document(p['document']);self.assertEqual(len(p['document']['source_media_track_imports']),1)
    def test_fixed_timeline_SRT_is_not_replaced_with_saved_ASR_on_linked_video_edit(self):
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(timebase='timeline'),actor_ref='FIXTURE')
        before=self.captions();after=self.edit_video(type='set_clip_properties',speed=2)
        self.assertEqual(self.captions(after),before);self.assertEqual([c['text'] for c in self.page()['captions']],['Vinhomes Cần Giờ','Vang Nguyễn giới thiệu'])
        self.assertFalse(after['shot_timeline']['snapshot']['metadata']['linked_source_edit']['captions_retimed_from_saved_transcript'])
    def test_caption_text_edit_retains_manual_layout_during_video_changes(self):
        self.mapped();media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='EXPLICIT HUMAN FIXTURE')
        before=self.captions();after=self.edit_video(type='set_clip_properties',speed=2)
        self.assertEqual(self.captions(after),before);self.assertTrue(all(c['source_video_mapping_mode']=='human_layout' for c in self.page()['captions']))
    def test_transcript_version_edit_keeps_explicit_caption_layout_and_its_original_word_evidence(self):
        from services.windows_native import auto_edit_analysis as analysis
        media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='FIXTURE')
        p=self.store.get(self.project['id']);before=self.captions(p);record=p['document']['auto_edit_analyses'][0]['analysis'];base=record['transcript']
        analysis.edit_transcript(self.store,p['id'],p['revision'],record['analysis_id'],{'expected_version':base['version'],
            'expected_timeline_version':p['document']['canonical_timeline']['version'],
            'segments':[{'segment_id':base['segments'][0]['segment_id'],'text':'Bản transcript chỉnh riêng.'}]})
        current=self.store.get(p['id']);self.assertEqual(self.captions(current),before)
        self.assertEqual(current['document']['canonical_timeline']['snapshot']['metadata']['transcript_revision']['version'],2)
        changed=self.edit_video(type='set_clip_properties',speed=2);self.assertEqual(self.captions(changed),before);self.assertIsNone(changed['approval'])
    def test_advanced_caption_move_preserves_layout_and_explicit_reimport_returns_to_follow_video(self):
        result=self.mapped();p=timeline.view(self.store,self.project['id']);caption=self.page()['captions'][0]
        timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'move','clip_id':caption['clip_id'],'timeline_start':.2}]})
        before=self.captions();after=self.edit_video(type='set_clip_properties',speed=2);self.assertEqual(self.captions(after),before)
        self.assertIn(result['track_id'],after['shot_timeline']['snapshot']['metadata']['source_caption_edited_tracks'])
        self.mapped();current=self.store.get(p['id']);self.assertNotIn(result['track_id'],current['document']['canonical_timeline']['snapshot']['metadata']['source_caption_edited_tracks'])
        self.assertEqual(current['document']['canonical_timeline']['snapshot']['duration_seconds'],1.5)
        self.assertEqual([(c['timeline_start'],c['duration']) for c in self.page()['captions']],[(.05,.45),(.65,.45)])
    def test_explicit_deletion_of_all_generated_captions_is_not_repopulated_by_linked_edits(self):
        p=timeline.view(self.store,self.project['id']);caps=self.page()['captions'];self.assertTrue(caps)
        p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'delete','clip_id':c['clip_id']} for c in caps]})
        self.assertEqual(self.page()['captions'],[]);self.edit_video(type='set_clip_properties',speed=2);self.assertEqual(self.page()['captions'],[])
    def test_locked_derived_track_blocks_source_timing_changes_atomically_but_locked_manual_layout_is_kept(self):
        result=self.mapped();p=timeline.view(self.store,self.project['id']);p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'set_track_state','track_id':result['track_id'],'locked':True}]});before=self.store.get(p['id'])
        with self.assertRaisesRegex(WorkflowError,'TRACK_LOCKED'):self.edit_video(type='set_clip_properties',speed=2)
        self.assertEqual(self.store.get(p['id']),before)
        p=timeline.view(self.store,p['id']);p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'set_track_state','track_id':result['track_id'],'locked':False}]})
        media.edit_captions(self.store,p['id'],self.captions_body(),actor_ref='FIXTURE');p=timeline.view(self.store,p['id'])
        p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'set_track_state','track_id':result['track_id'],'locked':True}]})
        caps=self.captions();changed=self.edit_video(type='set_clip_properties',speed=2);self.assertEqual(self.captions(changed),caps)
    def test_foreign_video_or_missing_pair_cannot_add_mapping_or_replay_authority(self):
        before=self.store.get(self.project['id']);body=self.subtitle_body(timebase='source',source_video_asset_id=self.video['id'],source_video_asset_sha256='a'*64)
        for bad in [body,{k:v for k,v in body.items() if k!='source_video_asset_sha256'}]:
            with self.assertRaises(WorkflowError):media.add_subtitles(self.store,self.project['id'],bad,actor_ref='FIXTURE')
            self.assertEqual(self.store.get(self.project['id']),before)
    def test_duplicate_retains_manual_track_decision_with_scoped_origins_without_approval_transfer(self):
        self.mapped();p=self.store.get(self.project['id']);child=self.store.duplicate(p['id'],p['revision']);timeline.validate_document(child['document'])
        self.assertIsNone(child['approval']);self.assertIsNone(child['document']['source_media_track_imports'][0]['request_key_sha256'])
        p=timeline.view(self.store,p['id']);c=self.page()['captions'][0];p=timeline.edit(self.store,p['id'],p['revision'],{'expected_version':p['shot_timeline']['version'],
            'operations':[{'type':'move','clip_id':c['clip_id'],'timeline_start':.2}]})
        child=self.store.duplicate(p['id'],p['revision']);timeline.validate_document(child['document'])
        ids=child['document']['canonical_timeline']['snapshot']['metadata']['source_caption_edited_tracks']
        self.assertEqual(len(ids),1);self.assertTrue(any(t['track_id']==ids[0] and t['kind']=='subtitles' for t in child['document']['canonical_timeline']['snapshot']['tracks']))
        self.assertEqual(child['document']['source_media_track_imports'][0]['project_id'],child['id']);self.assertIsNone(child['approval'])
