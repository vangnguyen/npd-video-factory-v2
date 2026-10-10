"""Real owned SQLite/media fixtures; synthetic PCM is not speech or Owner UAT."""
import copy,json,unittest
from types import SimpleNamespace
from unittest.mock import patch
from services.windows_native.tests import test_narrated_media_tracks as fixture
from services.windows_native import narrated_timeline_editor as editor
from services.windows_native.contracts import WorkflowError,file_sha,digest
from services.windows_native.shot_adapter import validate_document

class NarratedTimelineEditorTests(unittest.TestCase):
    def setUp(self):fixture.prepare(self)
    def tearDown(self):self.temp.cleanup()
    start=fixture.NarratedMediaTracksTests.start;finish=fixture.NarratedMediaTracksTests.finish;body=fixture.NarratedMediaTracksTests.body
    binding=fixture.NarratedMediaTracksTests.binding;page=fixture.NarratedMediaTracksTests.page
    audio_body=fixture.NarratedMediaTracksTests.audio_body;subtitle_body=fixture.NarratedMediaTracksTests.subtitle_body;captions_body=fixture.NarratedMediaTracksTests.captions_body
    imported=fixture.NarratedMediaTracksTests.imported
    def current(self):return editor.view(self.store,self.project['id'],self.workspace)
    def request_body(self,**kwargs):
        p=self.current();return {'revision':p['revision'],'expected_version':p['timeline_version'],'timeline_sha256':p['timeline_sha256'],**kwargs}
    def mutate(self,ops):return editor.edit(self.store,self.project['id'],self.request_body(operations=ops),self.workspace)
    def restore_body(self,target):return self.request_body(restore_revision=target['revision'],restore_timeline_sha256=target['timeline_sha256'])
    def test_inert_bounded_projection_and_strict_CAS_atomic_batch(self):
        before=self.store.get(self.project['id']);p=self.current();self.assertEqual(p,self.current());self.assertTrue(p['projection_pending']);self.assertEqual(before,self.store.get(self.project['id']))
        b=self.request_body(operations=[{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':True}])
        for bad in [{**b,'revision':True},{**b,'timeline_sha256':'0'*64},{**b,'operations':[{'type':'set_clip_properties','clip_id':'clip_narrated_measured_voice','volume':True}]},
                {**b,'operations':[{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':'true'}]},{**b,'provider':'NEVER'}]:
            with self.assertRaises(WorkflowError):editor.edit(self.store,self.project['id'],bad,self.workspace)
            self.assertEqual(before,self.store.get(self.project['id']))
        out=self.mutate(b['operations']);self.assertFalse(out['projection_pending']);self.assertTrue(next(t for t in out['snapshot']['tracks'] if t['kind']=='voice')['muted'])
        with self.assertRaises(WorkflowError):editor.edit(self.store,self.project['id'],b,self.workspace)
    def test_imported_audio_structural_edits_keep_fixed_measured_canvas_and_origin(self):
        self.imported();before=self.current();track=next(t for t in before['snapshot']['tracks'] if t['kind']=='voice' and t['track_id']!='trk_narrated_measured_voice');clip=track['clips'][0]
        split=self.mutate([{'type':'split','clip_id':clip['clip_id'],'at_seconds':1.5}]);pieces=next(t for t in split['snapshot']['tracks'] if t['track_id']==track['track_id'])['clips'];self.assertEqual(len(pieces),2)
        self.assertEqual(pieces[0]['source_end'],pieces[1]['source_start']);self.assertEqual(pieces[0]['metadata']['native_media_import_id'],pieces[1]['metadata']['native_media_import_id'])
        moved=self.mutate([{'type':'move','clip_id':pieces[1]['clip_id'],'timeline_start':2.2}]);self.assertEqual(moved['duration_seconds'],3.3)
        disabled=self.mutate([{'type':'disable','clip_id':pieces[1]['clip_id'],'disabled':True}]);self.assertTrue(next(c for t in disabled['snapshot']['tracks'] for c in t['clips'] if c['clip_id']==pieces[1]['clip_id'])['disabled'])
        self.mutate([{'type':'delete','clip_id':pieces[1]['clip_id']}]);validate_document(self.store.get(self.project['id'])['document'])
    def test_generated_voice_and_outside_bounds_protected_and_no_partial_write(self):
        self.imported();before=self.store.get(self.project['id']);clip=next(c for t in self.current()['snapshot']['tracks'] if t['kind']=='music' for c in t['clips'])
        for op in [{'type':'split','clip_id':'clip_narrated_measured_voice','at_seconds':1},
            {'type':'delete','clip_id':'clip_narrated_measured_voice'}, {'type':'move','clip_id':clip['clip_id'],'timeline_start':3.3},
            {'type':'move','clip_id':clip['clip_id'],'timeline_start':600}]:
            with self.assertRaises(WorkflowError):self.mutate([{'type':'set_track_state','track_id':clip['metadata'].get('no_track','trk_narrated_measured_voice'),'muted':True},op])
            self.assertEqual(before,self.store.get(self.project['id']))
        self.mutate([{'type':'set_clip_properties','clip_id':'clip_narrated_measured_voice','volume':.8}])
    def test_caption_structural_edits_are_not_regenerated_and_word_timing_not_inferred(self):
        p=self.current();track=next(t for t in p['snapshot']['tracks'] if t['kind']=='subtitles');clip=track['clips'][0]
        out=self.mutate([{'type':'move','clip_id':clip['clip_id'],'timeline_start':.2}]);saved=next(c for t in out['snapshot']['tracks'] for c in t['clips'] if c['clip_id']==clip['clip_id'])
        self.assertTrue(saved['metadata']['human_caption_edit']);self.assertEqual(saved['metadata']['measured_source_words'],[]);self.assertEqual(saved['timeline_start'],.2)
        validate_document(self.store.get(self.project['id'])['document'])
    def test_deleting_all_generated_captions_is_explicit_reversible_and_not_regenerated(self):
        p=self.current();track=next(t for t in p['snapshot']['tracks'] if t['kind']=='subtitles');ops=[{'type':'delete','clip_id':c['clip_id']} for c in track['clips']]
        out=self.mutate(ops);saved=next(t for t in out['snapshot']['tracks'] if t['track_id']==track['track_id']);self.assertEqual(saved['clips'],[])
        self.assertIn(track['track_id'],out['snapshot']['metadata']['narrated_caption_edited_tracks']);validate_document(self.store.get(self.project['id'])['document'])
        restored=editor.restore(self.store,self.project['id'],self.restore_body(p),self.workspace);self.assertEqual(restored['timeline_sha256'],p['timeline_sha256'])
    def test_audio_and_template_settings_enforce_locks_finite_numbers_and_word_evidence(self):
        p=editor.configure(self.store,self.project['id'],self.request_body(audio_processing={'normalize_original_audio':True,'normalize_music':True,'duck_music':True,'duck_ratio':6}),self.workspace)
        self.assertEqual(p['snapshot']['metadata']['source_audio_processing']['duck_ratio'],6)
        before=self.store.get(self.project['id'])
        for kwargs in [{'audio_processing':{'duck_ratio':'8'}},{'audio_processing':{'duck_ratio':float('nan')}},{'subtitle_template_ref':self.karaoke}]:
            with self.assertRaises(WorkflowError):editor.configure(self.store,self.project['id'],self.request_body(**kwargs),self.workspace)
            self.assertEqual(before,self.store.get(self.project['id']))
        from app.subtitle_templates import load_templates
        keyword=next(t['template_ref'] for t in load_templates() if t['style']['animation']=='keyword_highlight')
        editor.configure(self.store,self.project['id'],self.request_body(subtitle_template_ref=keyword,keywords=['Vang Nguyễn']),self.workspace)
        self.mutate([{'type':'set_track_state','track_id':'trk_narrated_measured_voice','locked':True}])
        with self.assertRaisesRegex(WorkflowError,'AUDIO_TRACK_LOCKED'):editor.configure(self.store,self.project['id'],self.request_body(audio_processing={'duck_music':False}),self.workspace)
    def test_undo_redo_restore_exact_snapshot_with_monotonic_revision_and_no_authority_rewind(self):
        self.imported();original=self.current();document=self.store.get(self.project['id'])['document'];voice=file_sha(self.voice_out/'voice.wav')
        changed=editor.configure(self.store,self.project['id'],self.request_body(audio_processing={'duck_music':False}),self.workspace)
        undo=editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace)
        self.assertEqual(undo['projection_sha256'],original['projection_sha256']);self.assertGreater(undo['timeline_version'],changed['timeline_version'])
        self.assertEqual(undo['history'][-1]['mutation']['restored_from_version'],original['timeline_version'])
        redo=editor.restore(self.store,self.project['id'],self.restore_body(changed),self.workspace);self.assertEqual(redo['projection_sha256'],changed['projection_sha256'])
        current=self.store.get(self.project['id']);self.assertIsNone(current['approval']);self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice)
        for key,value in document.items():
            if key not in {'canonical_timeline','proposal','scene_media','edit_plan','narrated_timeline_mutations'}:self.assertEqual(current['document'][key],value,key)
        self.assertEqual(len(current['jobs']),1)
    def test_undo_shot_visual_edit_restores_same_canonical_projections_and_all_audio_decisions(self):
        self.imported();original=self.current();project=self.store.shot_view(self.project['id']);shot=project['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Thay đổi để hoàn tác'}})
        self.assertNotEqual(changed['document']['canonical_timeline']['sha256'],original['timeline_sha256'])
        undo=editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace);self.assertEqual(undo['timeline_sha256'],original['timeline_sha256'])
        validate_document(self.store.get(project['id'])['document'])
    def test_restore_binding_foreign_preparation_and_current_track_lock_refuse(self):
        self.imported();original=self.current();track=next(t for t in original['snapshot']['tracks'] if t['kind']=='music');clip=track['clips'][0]
        self.mutate([{'type':'set_clip_properties','clip_id':clip['clip_id'],'volume':.2},{'type':'set_track_state','track_id':track['track_id'],'locked':True}])
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'RESTORE_TRACK_LOCKED'):editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace)
        with self.assertRaises(WorkflowError):editor.restore(self.store,self.project['id'],{**self.restore_body(original),'restore_timeline_sha256':'0'*64},self.workspace)
        self.assertEqual(before,self.store.get(self.project['id']))
    def test_restore_can_undo_first_opt_in_without_deleting_uploaded_import_journal(self):
        original=self.current();self.imported();records=copy.deepcopy(self.store.get(self.project['id'])['document']['source_media_track_imports'])
        undo=editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace);self.assertTrue(undo['projection_pending'])
        self.assertEqual(undo['timeline_sha256'],original['timeline_sha256']);self.assertEqual(self.store.get(self.project['id'])['document']['source_media_track_imports'],records)
    def test_corrupt_physical_voice_prevents_edit_and_restore_without_new_dispatch(self):
        self.imported();before=self.store.get(self.project['id']);path=self.voice_out/'voice.wav';raw=path.read_bytes();path.write_bytes(b'corrupt')
        try:
            with self.assertRaises(WorkflowError):self.mutate([{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':True}])
            self.assertEqual(before,self.store.get(self.project['id']))
        finally:path.write_bytes(raw)
    def test_imported_voice_word_boundaries_protect_structural_split(self):
        self.imported();before=self.store.get(self.project['id']);clip=next(c for t in self.current()['snapshot']['tracks'] if t['kind']=='voice' and t['track_id']!='trk_narrated_measured_voice' for c in t['clips'])
        # Explicit provider-word fixture; this does not claim actual ASR acceptance.
        transcript=SimpleNamespace(segments=[SimpleNamespace(words=[SimpleNamespace(start_seconds=.7,end_seconds=1.1)])])
        with patch('services.windows_native.audio_transcripts.selected',return_value=transcript):
            with self.assertRaisesRegex(WorkflowError,'CUT_THROUGH_SPOKEN_WORD'):
                editor.edit(self.store,self.project['id'],{'revision':before['revision'],'expected_version':before['document']['canonical_timeline']['version'],
                    'timeline_sha256':before['document']['canonical_timeline']['sha256'],'operations':[{'type':'split','clip_id':clip['clip_id'],'at_seconds':1.5}]},self.workspace)
        self.assertEqual(before,self.store.get(self.project['id']))
    def test_historical_preparation_difference_never_transfers_voice_authority(self):
        self.imported();original=self.current();self.mutate([{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':True}]);before=self.store.get(self.project['id'])
        with self.store.transaction() as con:
            old=json.loads(con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(self.project['id'],original['revision'])).fetchone()[0])
            old['prepared_narration']['explicit_corrupt_fixture']=True
            con.execute('UPDATE project_versions SET document=? WHERE project_id=? AND revision=?',(json.dumps(old),self.project['id'],original['revision']))
        with self.assertRaisesRegex(WorkflowError,'REQUIRES_SAME_PREPARATION'):editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace)
        self.assertEqual(before,self.store.get(self.project['id']))
    def test_history_read_is_bounded_and_reports_truncation_without_rewriting_versions(self):
        self.imported();before=self.store.get(self.project['id']);base=before['document'];state=base['canonical_timeline'];amount=220
        with self.store.transaction() as con:
            for i in range(1,amount+1):
                doc=copy.deepcopy(base);doc['canonical_timeline']['version']=state['version']+i
                con.execute('UPDATE projects SET revision=?,document=? WHERE id=?',(before['revision']+i,json.dumps(doc),before['id']));self.store.version(con,before['id'])
        current=self.store.get(before['id']);page=self.current();self.assertTrue(page['history_truncated']);self.assertEqual(len(page['history']),100)
        self.assertEqual(page['history'][-1]['version'],state['version']+amount);self.assertEqual(current,self.store.get(before['id']))
    def test_changed_script_blocks_audio_edits_but_can_undo_to_original_verified_voice_without_inference(self):
        self.imported();original=self.current();project=self.store.shot_view(self.project['id']);shot=project['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'narration':'Lời mới chưa được tạo giọng','subtitle':shot['subtitle']}})
        page=self.current();self.assertFalse(page['voice_input_current'])
        with self.assertRaisesRegex(WorkflowError,'INPUT_CHANGED_REPREPARE'):self.mutate([{'type':'set_track_state','track_id':'trk_narrated_measured_voice','muted':True}])
        restored=editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace);self.assertTrue(restored['voice_input_current']);self.assertEqual(restored['timeline_sha256'],original['timeline_sha256'])
        self.assertEqual(self.store.get(self.project['id'])['jobs'],changed['jobs'])
    def test_changed_legacy_script_history_remains_readable_and_undo_does_not_seed_stale_voice(self):
        original=self.current();project=self.store.shot_view(self.project['id']);shot=project['shot_timeline']['shots'][0]
        self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'narration':'Lời mới chưa được tạo giọng','subtitle':shot['subtitle']}})
        before=self.store.get(self.project['id']);page=self.current();self.assertFalse(page['voice_input_current']);self.assertTrue(page['projection_pending'])
        self.assertFalse(any(t['track_id']=='trk_narrated_measured_voice' for t in page['snapshot']['tracks']));self.assertEqual(before,self.store.get(self.project['id']))
        restored=editor.restore(self.store,self.project['id'],self.restore_body(original),self.workspace);self.assertTrue(restored['voice_input_current']);self.assertEqual(restored['timeline_sha256'],original['timeline_sha256'])

if __name__=='__main__':unittest.main()
