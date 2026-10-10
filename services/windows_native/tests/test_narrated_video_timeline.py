"""Owned real video/saved measured PCM; visual edits do not synthesize speech."""
import copy,unittest
from services.windows_native.tests import test_source_caption_mapping as fixture
from services.windows_native import narrated_timeline_editor as editor,narrated_video_timeline as video
from services.windows_native.shot_adapter import validate_document
from services.windows_native.contracts import WorkflowError,digest

class NarratedVideoTimelineTests(unittest.TestCase):
    def setUp(self):fixture.prepare(self)
    def tearDown(self):self.temp.cleanup()
    start=fixture.SourceCaptionMappingTests.start;finish=fixture.SourceCaptionMappingTests.finish;body=fixture.SourceCaptionMappingTests.body
    binding=fixture.SourceCaptionMappingTests.binding;page=fixture.SourceCaptionMappingTests.page;subtitle_body=fixture.SourceCaptionMappingTests.subtitle_body
    def current(self):return editor.view(self.store,self.project['id'],self.workspace)
    def edit(self,operations):
        p=self.current();return editor.edit(self.store,p['project_id'],{'revision':p['revision'],'expected_version':p['timeline_version'],
            'timeline_sha256':p['timeline_sha256'],'operations':operations},self.workspace)
    def test_split_move_speed_and_reorder_change_actual_visual_windows_without_changing_measured_voice(self):
        initial=self.current();clip=initial['snapshot']['tracks'][0]['clips'][0]
        out=self.edit([{'type':'split','clip_id':clip['clip_id'],'at_seconds':.8}]);self.assertTrue(video.enabled(out['snapshot']))
        self.assertEqual(len(out['snapshot']['tracks'][0]['clips']),len(initial['snapshot']['tracks'][0]['clips'])+1);voice=copy.deepcopy(next(t for t in out['snapshot']['tracks'] if t['kind']=='voice'))
        out=self.edit([{'type':'set_clip_properties','clip_id':clip['clip_id'],'speed':2}]);c=out['snapshot']['tracks'][0]['clips'][0]
        self.assertEqual(c['duration'],.4);out=self.edit([{'type':'move','clip_id':clip['clip_id'],'timeline_start':.4}])
        self.assertEqual(out['snapshot']['tracks'][0]['clips'][0]['timeline_start'],.4)
        out=self.edit([{'type':'reorder','clip_id':clip['clip_id'],'target_index':2}]);pieces=out['snapshot']['tracks'][0]['clips']
        self.assertEqual(pieces[0]['timeline_start'],0)
        for a,b in zip(pieces,pieces[1:]):self.assertAlmostEqual(b['timeline_start'],a['timeline_start']+a['duration'],places=6)
        self.assertEqual(out['duration_seconds'],3.3);self.assertEqual(next(t for t in out['snapshot']['tracks'] if t['kind']=='voice'),voice)
        p=self.store.get(self.project['id']);validate_document(p['document']);self.assertIsNone(p['approval'])
    def test_video_delete_disable_duplicate_and_crop_are_canonical_and_missing_coverage_is_explicit(self):
        p=self.current();c=p['snapshot']['tracks'][0]['clips'][0]
        self.edit([{'type':'duplicate','clip_id':c['clip_id'],'timeline_start':0}]);out=self.edit([{'type':'set_clip_properties','clip_id':c['clip_id'],
            'crop':{'x':.1,'y':.1,'width':.8,'height':.8},'opacity':.8,'transform':{'x':.1,'y':0,'scale':1.1,'rotation_degrees':0}}])
        self.assertEqual(out['snapshot']['tracks'][0]['clips'][0]['crop']['x'],.1)
        clips=out['snapshot']['tracks'][0]['clips'];out=self.edit([{'type':'delete','clip_id':c['clip_id']} for c in clips])
        self.assertEqual(out['snapshot']['tracks'][0]['clips'],[]);self.assertEqual(video.coverage(self.store.get(self.project['id'])['document'])['status'],'failed')
        self.assertEqual(len(self.store.shot_view(self.project['id'])['shot_timeline']['shots']),2)
    def test_locked_video_track_blocks_edits_and_foreign_window_is_atomic(self):
        p=self.current();c=p['snapshot']['tracks'][0]['clips'][0];before=self.store.get(self.project['id'])
        for op in [{'type':'trim','clip_id':c['clip_id'],'source_end':100},{'type':'set_clip_properties','clip_id':c['clip_id'],'crop':{'x':'0','y':0,'width':1,'height':1}}]:
            with self.assertRaises(WorkflowError):self.edit([op])
            self.assertEqual(self.store.get(self.project['id']),before)
        self.edit([{'type':'set_track_state','track_id':'trk_native_video','locked':True}]);before=self.store.get(self.project['id'])
        with self.assertRaises(WorkflowError):self.edit([{'type':'move','clip_id':c['clip_id'],'timeline_start':.1}])
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_new_visual_properties_cannot_bypass_generated_voice_timing_fence(self):
        p=self.current();voice=next(t for t in p['snapshot']['tracks'] if t['kind']=='voice').get('clips')[0];before=self.store.get(self.project['id'])
        for values in ({'duration':1},{'crop':{'x':0,'y':0,'width':1,'height':1}},{'opacity':.5}):
            with self.assertRaises(WorkflowError):self.edit([{'type':'set_clip_properties','clip_id':voice['clip_id'],'volume':1,**values}])
            self.assertEqual(self.store.get(self.project['id']),before)
    def test_default_shot_title_edit_preserves_advanced_source_windows(self):
        c=self.current()['snapshot']['tracks'][0]['clips'][0];self.edit([{'type':'split','clip_id':c['clip_id'],'at_seconds':.8}])
        p=self.store.shot_view(self.project['id']);before=[{k:c[k] for k in ('clip_id','source_start','source_end','timeline_start','duration')} for c in p['shot_timeline']['snapshot']['tracks'][0]['clips']]
        changed=self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':p['shot_timeline']['shots'][0]['shot_id'],'values':{'on_screen_text':'Tiêu đề đã sửa'}})
        self.assertEqual([{k:c[k] for k in ('clip_id','source_start','source_end','timeline_start','duration')} for c in changed['shot_timeline']['snapshot']['tracks'][0]['clips']],before)
        self.assertEqual(changed['shot_timeline']['shots'][0]['on_screen_text'],'Tiêu đề đã sửa');validate_document(changed['document'])
    def test_old_snapshot_restore_is_exact_and_clears_approval_without_jobs(self):
        old=self.current();c=old['snapshot']['tracks'][0]['clips'][0];now=self.edit([{'type':'split','clip_id':c['clip_id'],'at_seconds':.8}]);before=self.store.get(self.project['id'])
        restored=editor.restore(self.store,self.project['id'],{'revision':now['revision'],'expected_version':now['timeline_version'],'timeline_sha256':now['timeline_sha256'],
            'restore_revision':old['revision'],'restore_timeline_sha256':old['timeline_sha256']},self.workspace)
        self.assertEqual(restored['timeline_sha256'],old['timeline_sha256']);self.assertEqual(self.store.get(self.project['id'])['jobs'],before['jobs']);self.assertIsNone(self.store.get(self.project['id'])['approval'])
    def test_following_source_captions_retime_and_locked_caption_rejects_whole_video_batch(self):
        from services.windows_native import source_media_tracks as media
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(timebase='source',source_video_asset_id=self.video['id'],source_video_asset_sha256=self.video['sha256']),actor_ref='owned video fixture')
        before=self.store.get(self.project['id']);history=copy.deepcopy(before['document']['source_media_track_imports'])
        initial=self.current();clip=initial['snapshot']['tracks'][0]['clips'][0]
        out=self.edit([{'type':'set_clip_properties','clip_id':clip['clip_id'],'speed':2}])
        mapped=next(t for t in out['snapshot']['tracks'] if any(c['metadata'].get('source_video_mapping') for c in t['clips']))
        first=next(c for c in mapped['clips'] if c['metadata']['source_video_mapping']['video_clip']['clip_id']==clip['clip_id'])
        self.assertAlmostEqual(first['duration'],.3,places=6);self.assertEqual(self.store.get(self.project['id'])['document']['source_media_track_imports'],history)
        self.edit([{'type':'set_track_state','track_id':mapped['track_id'],'locked':True}]);saved=self.store.get(self.project['id'])
        with self.assertRaises(WorkflowError):self.edit([{'type':'set_clip_properties','clip_id':clip['clip_id'],'speed':1}])
        self.assertEqual(self.store.get(self.project['id']),saved)
    def test_manual_caption_windows_survive_actual_video_speed_change(self):
        from services.windows_native import source_media_tracks as media
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(timebase='source',source_video_asset_id=self.video['id'],source_video_asset_sha256=self.video['sha256']),actor_ref='owned video fixture')
        p=self.current();track=next(t for t in p['snapshot']['tracks'] if any(c['metadata'].get('source_video_mapping') for c in t['clips']))
        edited=self.edit([{'type':'move','clip_id':track['clips'][0]['clip_id'],'timeline_start':.1}])
        manual=copy.deepcopy([t for t in edited['snapshot']['tracks'] if t['type']=='text'])
        video_clip=edited['snapshot']['tracks'][0]['clips'][0]
        out=self.edit([{'type':'set_clip_properties','clip_id':video_clip['clip_id'],'speed':2}])
        self.assertEqual([t for t in out['snapshot']['tracks'] if t['type']=='text'],manual)
    def test_default_source_replacement_changes_only_its_group_and_shot_view_reports_actual_windows(self):
        initial=self.current();c=initial['snapshot']['tracks'][0]['clips'][0];count=sum(v['metadata']['shot_id']==c['metadata']['shot_id'] for v in initial['snapshot']['tracks'][0]['clips'])
        self.edit([{'type':'split','clip_id':c['clip_id'],'at_seconds':.8}])
        p=self.store.shot_view(self.project['id']);first,second=p['shot_timeline']['shots'];self.assertEqual(len(first['advanced_visual_windows']),count+1)
        other=[c for c in p['shot_timeline']['snapshot']['tracks'][0]['clips'] if c['metadata']['shot_id']==second['shot_id']]
        changed=self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':first['shot_id'],'values':{'source_start':.6}})
        self.assertEqual([c for c in changed['shot_timeline']['snapshot']['tracks'][0]['clips'] if c['metadata']['shot_id']==second['shot_id']],other)
        self.assertEqual(changed['shot_timeline']['shots'][0]['advanced_visual_windows'][0]['source_start'],.6);validate_document(changed['document'])
    def test_image_display_duration_and_split_have_no_fabricated_source_clock(self):
        p=self.store.shot_view(self.project['id']);image=next(a for a in p['document']['assets'] if a['kind']=='image');shot=p['shot_timeline']['shots'][0]
        self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'asset_id':image['id'],'source_start':0,'motion':'zoom_in'}})
        clip=self.current()['snapshot']['tracks'][0]['clips'][0]
        out=self.edit([{'type':'trim','clip_id':clip['clip_id'],'duration':1.2}]);self.assertEqual(out['snapshot']['tracks'][0]['clips'][0]['duration'],1.2)
        out=self.edit([{'type':'split','clip_id':clip['clip_id'],'at_seconds':.6}])
        self.assertTrue(all(c['source_start']==0 and c['source_end'] is None and c['speed']==1 for c in out['snapshot']['tracks'][0]['clips'] if c['kind']=='image'))
        before=self.store.get(self.project['id'])
        with self.assertRaises(WorkflowError):self.edit([{'type':'set_clip_properties','clip_id':clip['clip_id'],'speed':2}])
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_duplicate_and_six_variants_preserve_visual_decisions_without_approval_or_new_jobs(self):
        from services.windows_native.narrated_variants import NativeNarratedVariants,catalog
        from services.windows_native.narrated_variants_models import Create
        c=self.current()['snapshot']['tracks'][0]['clips'][0];self.edit([{'type':'split','clip_id':c['clip_id'],'at_seconds':.8}])
        p=self.store.get(self.project['id']);primary=copy.deepcopy(p['document']['canonical_timeline']['snapshot']['tracks'][0])
        duplicate=self.store.duplicate(p['id'],p['revision']);validate_document(duplicate['document']);self.assertIsNone(duplicate['approval']);self.assertEqual(duplicate['jobs'],[])
        self.assertEqual(duplicate['document']['canonical_timeline']['snapshot']['tracks'][0],primary);self.assertNotIn('prepared_narration',duplicate['document'])
        from services.windows_native.hardening import durable_json
        durable_json(self.root/'.vf-auth-workspace.json',{'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace})
        service=NativeNarratedVariants(self.store,workspace_id=self.workspace)
        payload=Create(revision=p['revision'],expected_version=p['document']['canonical_timeline']['version'],
            expected_prepared_reference_sha256=digest(p['document']['prepared_narration']),profile_refs=[v['profile_ref'] for v in catalog()['profiles']],request_key='owned-edited-video-six-formats')
        batch,replay=service.create(p['id'],payload,actor='OWNED SYNTHETIC FIXTURE');self.assertFalse(replay)
        self.assertEqual(len(batch['result']['variants']),6)
        for item in batch['result']['variants']:
            child=self.store.get(item['project_id']);validate_document(child['document']);self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
            self.assertEqual(child['document']['canonical_timeline']['snapshot']['tracks'][0],primary)
        self.assertEqual(self.store.get(p['id']),p)
