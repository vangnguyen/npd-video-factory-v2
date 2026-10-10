"""Real measured PCM/upload/timeline/render; saved synthetic speech is not UAT."""
import copy,json,tempfile,unittest,uuid,wave
from pathlib import Path
from unittest.mock import patch
import numpy as np
from services.windows_native.tests import test_narration as fixture,test_source_media_tracks as source_fixture,test_source_music as music_fixture
from services.windows_native.tests.test_shot_production import prepared
from services.windows_native.branding import FIT_NARRATION_POLICY
from services.windows_native.contracts import WorkflowError,digest,file_sha
from services.windows_native.multipart_ingestion import NativeMultipartIngestion
from services.windows_native.narration import apply
from services.windows_native import source_media_tracks as media,narrated_media_timeline as tracks
from services.windows_native.shot_adapter import validate_document
from services.windows_native.pipeline import Pipeline
from services.windows_native.hardening import Artifacts

def prepare(case):
    case.temp=tempfile.TemporaryDirectory(dir='C:/' if getattr(case,'short_owned_root',False) else None,
        prefix='vf-nv-' if getattr(case,'short_owned_root',False) else 'tmp');case.owned=Path(case.temp.name);case.root=case.owned/'state'
    case.config,case.store,case.project=prepared(case.root)
    case.workspace='wsp_narrated_media_tracks_fixture'
    case.project=case.store.set_brand(case.project['id'],case.project['revision'],'vang-nguyen','personal-30',duration_mode=FIT_NARRATION_POLICY)
    case.source,case.voice_out,case.result=case.finish()
    case.project=apply(case.store,case.project['id'],case.source['id'],case.body(case.result))
    case.uploads=NativeMultipartIngestion(case.store,case.config,workspace_id=case.workspace)
    path=case.owned/'explicit-tone-not-speech.wav'
    samples=(np.sin(np.arange(32000)*2*np.pi*440/16000)*3000).astype('<i2')
    with wave.open(str(path),'wb') as wav:
        wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(samples.tobytes())
    case.voice=source_fixture.upload(case,path.read_bytes(),'audio','audio/wav')
    case.music_asset=source_fixture.upload(case,path.read_bytes(),'music','audio/wav')
    case.subtitle=source_fixture.upload(case,'1\n00:00:00,100 --> 00:00:01,000\nVinhomes Cần Giờ\n\n2\n00:00:01,300 --> 00:00:02,200\nVang Nguyễn giới thiệu\n'.encode(),'subtitle','application/x-subrip')
    from app.subtitle_templates import load_templates
    case.sentence=next(v['template_ref'] for v in load_templates() if not v['requires_word_timestamps'])
    case.karaoke=next(v['template_ref'] for v in load_templates() if v['style']['animation']=='karaoke')

class NarratedMediaTracksTests(unittest.TestCase):
    def setUp(self):prepare(self)
    def tearDown(self):self.temp.cleanup()
    start=fixture.NarrationTests.start;finish=fixture.NarrationTests.finish;body=fixture.NarrationTests.body;audible=fixture.NarrationTests.audible
    music=music_fixture.SourceMusicTests.music
    page=source_fixture.SourceMediaTracksTests.page
    binding=source_fixture.SourceMediaTracksTests.binding
    audio_body=source_fixture.SourceMediaTracksTests.audio_body
    subtitle_body=source_fixture.SourceMediaTracksTests.subtitle_body
    captions_body=source_fixture.SourceMediaTracksTests.captions_body
    def imported(self):
        media.add_audio(self.store,self.project['id'],self.audio_body(timeline_start=.5,volume=.8),actor_ref='explicit-editor-fixture')
        media.add_audio(self.store,self.project['id'],self.audio_body(self.music_asset,role='music',volume=.1,repeat_until=3.3,crossfade_seconds=.2,
            fade_in_seconds=.1,fade_out_seconds=.1),actor_ref='explicit-editor-fixture')
        media.add_subtitles(self.store,self.project['id'],self.subtitle_body(),actor_ref='explicit-editor-fixture')
        media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='explicit-editor-fixture')
        return self.store.shot_view(self.project['id'])
    def test_catalog_is_inert_deterministic_measured_projection_and_first_caption_edit_is_CAS(self):
        before=self.store.get(self.project['id']);first=self.page();second=self.page()
        self.assertEqual(first,second);self.assertEqual(self.store.get(self.project['id']),before)
        self.assertEqual((first['timeline_mode'],first['pending_generated_tracks']),('narrated',True))
        self.assertEqual(first['captions_total'],2);self.assertTrue(all(not c['has_word_timing'] for c in first['captions']))
        media.edit_captions(self.store,self.project['id'],self.captions_body(),actor_ref='explicit-caption-editor')
        after=self.store.get(self.project['id']);self.assertEqual(after['revision'],before['revision']+1);self.assertIsNone(after['approval'])
        self.assertTrue(tracks.enabled(after['document']));self.assertFalse(self.page()['pending_generated_tracks']);self.assertEqual(self.page()['captions'][0]['text'],'Chữ Việt đã sửa trên timeline')
        self.assertEqual(after['document']['prepared_narration'],before['document']['prepared_narration']);validate_document(after['document'])
    def test_imports_replay_preserve_measured_voice_originals_and_caption_evidence(self):
        before=file_sha(self.voice_out/'voice.wav');request=self.audio_body(timeline_start=.5)
        first=media.add_audio(self.store,self.project['id'],request,actor_ref='explicit-editor-fixture')
        current=self.store.get(self.project['id']);replay=media.add_audio(self.store,self.project['id'],request,actor_ref='explicit-editor-fixture')
        self.assertTrue(replay['replayed']);self.assertEqual(replay['clip_ids'],first['clip_ids']);self.assertEqual(current,self.store.get(self.project['id']))
        with self.assertRaisesRegex(WorkflowError,'IDEMPOTENCY_CONFLICT'):media.add_audio(self.store,self.project['id'],{**request,'volume':.7},actor_ref='explicit-editor-fixture')
        self.assertEqual(file_sha(self.voice_out/'voice.wav'),before)
        self.assertEqual(current['document']['canonical_timeline']['snapshot']['metadata']['narrated_generated_voice_reference'],tracks.reference(current['document']))
        self.assertEqual(len(current['jobs']),1)
    def test_shot_visual_edit_retains_all_audio_and_human_caption_decisions_but_shortening_refuses_implicit_cut(self):
        project=self.imported();old=copy.deepcopy(project['document']['canonical_timeline']['snapshot']);shot=project['shot_timeline']['shots'][0]
        changed=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Hình đã sửa'}})
        self.assertEqual(changed['document']['canonical_timeline']['snapshot']['tracks'][1:],old['tracks'][1:]);validate_document(changed['document'])
        before=self.store.get(project['id'])
        with self.assertRaisesRegex(WorkflowError,'OVERRIDES_EXCEED_NEW_TIMELINE'):
            self.store.mutate_shots(project['id'],changed['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':.5}})
        self.assertEqual(self.store.get(project['id']),before)
    def test_locked_generated_voice_refuses_duration_rebind_and_locked_caption_refuses_edit(self):
        media.add_audio(self.store,self.project['id'],self.audio_body(),actor_ref='explicit-editor-fixture')
        with self.store.transaction() as con:
            p=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(self.project['id'],)).fetchone());doc=p['document']
            for t in doc['canonical_timeline']['snapshot']['tracks']:
                if t['track_id'] in {tracks.VOICE_TRACK,tracks.CAPTION_TRACK}:t['locked']=True
            doc['canonical_timeline']['sha256']=digest(doc['canonical_timeline']['snapshot'])
            con.execute('UPDATE projects SET document=? WHERE id=?',(json.dumps(doc),p['id']))
        before=self.store.shot_view(self.project['id']);shot=before['shot_timeline']['shots'][0]
        with self.assertRaisesRegex(WorkflowError,'TRACK_LOCKED'):
            self.store.mutate_shots(before['id'],before['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'duration':2.7}})
        with self.assertRaisesRegex(WorkflowError,'TRACK_LOCKED'):media.edit_captions(self.store,before['id'],self.captions_body(),actor_ref='explicit-editor-fixture')
        self.assertEqual(self.store.shot_view(before['id']),before)
    def test_legacy_music_controls_still_mutate_own_canonical_track_preserve_uploaded_music_and_disable(self):
        project=self.imported();explicit=next(t for t in project['document']['canonical_timeline']['snapshot']['tracks'] if t['kind']=='music')
        asset=self.music();changed=self.store.set_music(project['id'],project['revision'],asset,loop_crossfade_seconds=.25)
        state=changed['document']['canonical_timeline']['snapshot'];self.assertEqual(next(t for t in state['tracks'] if t['track_id']==explicit['track_id']),explicit)
        legacy=next(t for t in state['tracks'] if t['track_id']=='trk_native_music');self.assertEqual(len(legacy['clips']),5);validate_document(changed['document'])
        disabled=self.store.save(changed['id'],changed['revision'],music_enabled=False)
        self.assertNotIn('trk_native_music',[t['track_id'] for t in disabled['document']['canonical_timeline']['snapshot']['tracks']])
        self.assertIn(explicit['track_id'],[t['track_id'] for t in disabled['document']['canonical_timeline']['snapshot']['tracks']]);validate_document(disabled['document'])
    def test_no_measured_narration_word_alignment_or_ambiguous_video_source_mapping_is_invented(self):
        other=self.store.create('Unprepared project','No inference')
        self.assertFalse(media.catalog(self.store,other['id'],self.workspace)['timeline_available'])
        before=self.store.get(self.project['id'])
        with self.assertRaisesRegex(WorkflowError,'WORD_ALIGNMENT_UNAVAILABLE'):media.edit_captions(self.store,self.project['id'],self.captions_body(subtitle_template_ref=self.karaoke),actor_ref='explicit-editor-fixture')
        with self.assertRaisesRegex(WorkflowError,'EXPLICIT_VIDEO_MAPPING'):media.add_subtitles(self.store,self.project['id'],self.subtitle_body(timebase='source'),actor_ref='explicit-editor-fixture')
        self.assertEqual(self.store.get(self.project['id']),before)
    def test_duplicate_inherits_immutable_import_origins_without_prepared_authority_or_replay(self):
        project=self.imported();duplicate=self.store.duplicate(project['id'],project['revision']);validate_document(duplicate['document'])
        self.assertNotIn('prepared_narration',duplicate['document']);self.assertFalse(self.page_for(duplicate)['timeline_available'])
        meta=duplicate['document']['canonical_timeline']['snapshot']['metadata'];self.assertEqual(meta['native_project_id'],duplicate['id'])
        from services.windows_native.source_media_track_origins import records
        self.assertEqual(len(records(duplicate['document'])),3);self.assertTrue(all(v['inherited_original'] for v in records(duplicate['document']).values()))
    def page_for(self,p):return media.catalog(self.store,p['id'],self.workspace)
    def test_default_shot_subtitle_edits_are_rendered_and_import_override_requires_caption_editor(self):
        p=self.store.shot_view(self.project['id']);shot=p['shot_timeline']['shots'][0]
        p=self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'subtitle':'Tên riêng Cần Giờ đã sửa'}})
        self.assertEqual(self.page()['captions'][0]['text'],'Tên riêng Cần Giờ đã sửa')
        media.add_audio(self.store,p['id'],self.audio_body(),actor_ref='explicit-editor-fixture');p=self.store.shot_view(p['id'])
        changed=self.store.mutate_shots(p['id'],p['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'subtitle':'Vang Nguyễn giới thiệu'}})
        self.assertEqual(self.page()['captions'][0]['text'],'Vang Nguyễn giới thiệu');validate_document(changed['document'])
        media.add_subtitles(self.store,p['id'],self.subtitle_body(),actor_ref='explicit-editor-fixture');before=self.store.get(p['id'])
        with self.assertRaisesRegex(WorkflowError,'USE_CAPTION_EDITOR'):
            self.store.mutate_shots(p['id'],before['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'subtitle':'Không được âm thầm bỏ qua'}})
        self.assertEqual(self.store.get(p['id']),before)
    def test_new_measured_preparation_rebinds_voice_and_plan_without_repeating_uploaded_operations(self):
        p=self.imported();before=copy.deepcopy(p['document']);p=self.store.approve(p['id'],p['revision'],'EXPLICIT REPREPARATION FIXTURE',True,purpose='narration')
        self.store.enqueue(p['id'],p['revision'],'narration',uuid.uuid4().hex);job=self.store.claim();out=self.root/'jobs'/job['id']
        from services.windows_native.tests.test_shot_production import voice
        from services.windows_native.contracts import write_json
        voice(out);write_json(out/'tts-plan.json',{'explicit_synthetic_pcm_fixture':True});Artifacts(out,job).commit('tts',[out/'voice.wav',out/'voice.json',out/'tts-plan.json'])
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No provider inference')):result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);updated=apply(self.store,p['id'],job['id'],{'revision':p['revision'],'expected_plan_sha256':result['plan_sha256'],'acknowledged':True})
        from services.windows_native.narrated_media_mix import verify
        verify(self.config,updated['document']);self.assertEqual(len(updated['jobs']),2);self.assertEqual(self.page()['imports_total'],3)
        self.assertNotEqual(tracks.reference(updated['document']),tracks.reference(before));self.assertEqual(updated['document']['canonical_timeline']['snapshot']['tracks'][2:],before['canonical_timeline']['snapshot']['tracks'][2:])
    def test_six_variants_reuse_tracks_and_physical_imports_but_change_project_voice_reference_without_approval(self):
        p=self.imported();from services.windows_native.narrated_variants import NativeNarratedVariants,catalog
        from services.windows_native.narrated_variants_models import Create
        payload=Create(revision=p['revision'],expected_version=p['document']['canonical_timeline']['version'],expected_prepared_reference_sha256=digest(p['document']['prepared_narration']),
            profile_refs=[v['profile_ref'] for v in catalog()['profiles']],request_key='explicit-narrated-media-six-formats-fixture')
        service=NativeNarratedVariants(self.store);batch,_=service.create(p['id'],payload,actor='explicit-fixture');self.assertEqual(len(batch['result']['variants']),6)
        from services.windows_native.narrated_media_mix import verify
        for variant in batch['result']['variants']:
            child=self.store.get(variant['project_id']);verify(self.config,child['document']);self.assertIsNone(child['approval']);self.assertEqual(child['jobs'],[])
            self.assertEqual(child['document']['canonical_timeline']['snapshot']['metadata']['native_project_id'],child['id'])
            self.assertEqual(self.page_for(child)['imports_total'],3)
        (self.root/'originals'/self.subtitle['original_id']).write_bytes(b'EXPLICIT IMPORT DRIFT FIXTURE')
        with self.assertRaises(WorkflowError):service.create(p['id'],payload.model_copy(update={'request_key':'explicit-drift-new-family'}),actor='explicit-fixture')
        self.assertEqual(len(service.page(p['id'])['items']),1)
    def test_actual_preview_final_mix_subtitles_full_QC_checkpoint_and_physical_drift(self):
        project=self.imported();original=file_sha(self.voice_out/'voice.wav');preview=self.audible(project);folder=self.root/'shot-previews'/preview['id']
        self.assertTrue(preview['manifest']['qc']['passed']);preview_mix=file_sha(folder/'narrated-mix.wav')
        self.assertIn('Chữ Việt đã sửa trên timeline',(folder/'subtitles.ass').read_text(encoding='utf-8'))
        project=self.store.approve(project['id'],project['revision'],'EXPLICIT CANONICAL MEDIA FIXTURE',True)
        self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No new inference')):result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result);out=self.root/'jobs'/job['id'];self.assertTrue(result['qc']['passed'])
        self.assertEqual(file_sha(out/'narrated-mix.wav'),preview_mix);self.assertEqual(file_sha(self.voice_out/'voice.wav'),original)
        self.assertEqual(file_sha(out/'subtitles.ass'),file_sha(folder/'subtitles.ass'))
        checkpoint=Artifacts(out,job).load('render');names={v['path'] for v in checkpoint['artifacts']}
        self.assertTrue({'narrated-media-mix.json','narrated-mix.wav','timeline-render.json','source-media-imports.json','subtitles.json','fonts/NotoSans.ttf'}<=names)
        from services.windows_native.narrated_media_mix import validate_bundle
        validate_bundle(self.config,project['document'],out)
        self.assertEqual(Pipeline(self.config).run(job,lambda _:None),result)
        with self.store.transaction() as con:self.store.verified_render(job['id'],con)
        raw=self.root/'originals'/self.voice['original_id'];raw.write_bytes(b'EXPLICIT OWNED CORRUPTION')
        with self.assertRaises(WorkflowError):Pipeline(self.config).run(job,lambda _:None)
        with self.store.transaction() as con,self.assertRaises(WorkflowError):self.store.verified_render(job['id'],con)
