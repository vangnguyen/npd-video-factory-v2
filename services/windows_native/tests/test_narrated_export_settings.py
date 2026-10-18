"""Actual local narrated output variants; synthetic PCM and fixture approval, no Owner UAT."""
import copy,json,unittest,uuid
from unittest.mock import patch
from services.windows_native.tests import test_narrated_media_tracks as fixture
from services.windows_native import narrated_timeline_editor as editor
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.pipeline import Pipeline
from services.windows_native.manual_delivery import NativeManualDelivery,DeliveryCreate


class NarratedExportSettingsTests(unittest.TestCase):
    setUp=lambda self:fixture.prepare(self)
    tearDown=lambda self:self.temp.cleanup()
    start=fixture.NarratedMediaTracksTests.start
    finish=fixture.NarratedMediaTracksTests.finish
    body=fixture.NarratedMediaTracksTests.body
    audible=fixture.NarratedMediaTracksTests.audible

    def configure(self,**options):
        page=editor.view(self.store,self.project['id'],self.workspace)
        return editor.configure(self.store,self.project['id'],{'revision':page['revision'],'expected_version':page['timeline_version'],
            'timeline_sha256':page['timeline_sha256'],**options},self.workspace)

    def test_invalid_options_do_not_change_approval_tracks_or_measured_voice(self):
        before=self.store.get(self.project['id']);voice=file_sha(self.voice_out/'voice.wav')
        for options in [{'fps':True},{'fps':30.0},{'fps':29},{'quality_preset':'ultra'},{'audio_included':'false'},{'burn_subtitles':1}]:
            with self.subTest(options=options),self.assertRaises(WorkflowError):self.configure(**options)
        self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice)

    def render_variant(self,**options):
        before=self.store.get(self.project['id']);voice=file_sha(self.voice_out/'voice.wav')
        self.configure(**options);project=self.store.get(self.project['id'])
        self.assertIsNone(project['approval']);self.assertGreater(project['revision'],before['revision'])
        self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice)
        with self.assertRaises(WorkflowError):self.store.enqueue(project['id'],project['revision'],'render',uuid.uuid4().hex)
        self.audible(project)
        approved=self.store.approve(project['id'],project['revision'],'AUTOMATED EXPORT SETTINGS PREVIEW — NOT OWNER UAT',True)
        self.store.enqueue(approved['id'],approved['revision'],'render',uuid.uuid4().hex);job=self.store.claim()
        with patch('services.windows_native.pipeline.synthesize',side_effect=AssertionError('No TTS inference for export variants')):
            result=Pipeline(self.config).run(job,lambda _:None)
        self.store.finish(job,result=result)
        with self.store.transaction() as con:self.store.verified_render(job['id'],con)
        self.assertEqual(result['qc']['full_quality']['full_production_qc']['fps'],options['fps']);self.assertTrue(result['qc']['passed'])
        self.assertEqual(file_sha(self.voice_out/'voice.wav'),voice)
        return approved,job,result

    def test_actual_24fps_high_quality_narrated_preview_final_and_full_qc(self):
        project,job,result=self.render_variant(fps=24,quality_preset='high')
        directory=self.root/'jobs'/job['id'];manifest=json.loads((directory/'render-manifest.json').read_bytes())
        self.assertEqual(manifest['export_options']['crf'],18)
        self.assertTrue(all(s['actual_libass_pixels'] for s in result['qc']['full_quality']['subtitle_bounds']['samples']))
        self.assertGreater(result['qc']['full_quality']['full_production_qc']['measured_audio_balance']['samples']['final']['analyzed_frames'],0)
        view=self.store.shot_view(project['id']);shot=view['shot_timeline']['shots'][0]
        edited=self.store.mutate_shots(project['id'],project['revision'],{'type':'update','shot_id':shot['shot_id'],'values':{'on_screen_text':'Chỉnh hình, giữ cài đặt xuất'}})
        self.assertIsNone(edited['approval']);self.assertEqual(edited['document']['canonical_timeline']['snapshot']['fps'],24)
        self.assertEqual(edited['document']['canonical_timeline']['snapshot']['metadata']['native_export_encoder']['quality_preset'],'high')
        self.assertEqual(file_sha(directory/'final.mp4'),result['qc']['final_sha256'])

    def test_actual_silent_unburned_narrated_export_retains_srt_and_editable_tracks(self):
        page=editor.view(self.store,self.project['id'],self.workspace);tracks=copy.deepcopy(page['snapshot']['tracks'])
        project,job,result=self.render_variant(fps=25,quality_preset='small',audio_included=False,burn_subtitles=False)
        self.assertEqual(project['document']['canonical_timeline']['snapshot']['tracks'],tracks)
        full=result['qc']['full_quality'];self.assertFalse(full['subtitle_bounds']['actual_libass_pixels'])
        self.assertEqual(full['full_production_qc']['measured_audio_balance']['reference_role'],'no_reference')
        self.store.review_render(job['id'],project['revision'],'AUTOMATED SILENT FINAL — NOT OWNER UAT',True,'approve')
        delivered=NativeManualDelivery(self.store,self.config).create(project['id'],DeliveryCreate(revision=project['revision'],render_job_id=job['id'],
            expected_video_sha256=result['qc']['final_sha256'],cover=False,separate_subtitle=True,request_key='narrated-silent-separate-srt-fixture'))
        self.assertIn('subtitle.srt',delivered['files'])


if __name__=='__main__':unittest.main()
