"""Local-real synthetic media, explicit crop fixture and mock review; no Owner UAT."""
import copy
import json
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch
from services.windows_native import auto_edit_timeline as timeline,source_settings
from services.windows_native.source_preview import FULL_PROFILE,PROFILE,profile_for,render_final_effects
from services.windows_native.source_approval import reviewed_preview
from services.windows_native.source_render import command_run
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.contracts import WorkflowError,file_sha
from services.windows_native.tests import test_source_preview as fixture
from app.timeline_models import TimelineSnapshot


class NativeEffectsPreviewTests(unittest.TestCase):
    setUp=fixture.NativeSourcePreviewTests.setUp
    tearDown=fixture.NativeSourcePreviewTests.tearDown
    save_analysis=fixture.NativeSourcePreviewTests.save_analysis
    real_source=fixture.NativeSourcePreviewTests.real_source

    def wait(self,manager):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            value=manager.status(self.project['id'])
            if value['status'] not in {'QUEUED','RUNNING'}:return value
            time.sleep(.05)
        self.fail('Effects preview did not finish')

    def test_real_caption_crop_audio_and_approval_binding_preserve_source_and_document(self):
        source=self.real_source(aspect_ratio='4:5');original=file_sha(source)
        self.assertEqual(profile_for(self.project),PROFILE)
        self.project=source_settings.configure(self.store,self.project['id'],self.project['revision'],{
            'expected_version':1,'preview_mode':'final_effects','subtitle_template_ref':'karaoke-gold@v1'})
        # Saved manual source-seconds crop fixture; this is not provider/subject tracking.
        with self.store.transaction() as con:
            project=self.store.editable(con,self.project['id'],self.project['revision'])
            snapshot=TimelineSnapshot.model_validate(project['document']['canonical_timeline']['snapshot'])
            clip=next(c for t in snapshot.tracks if t.kind=='source' for c in t.clips)
            clip.metadata['reframe']={'schema_version':1,'time_space':'source_seconds',
                'source_width':320,'source_height':240,'strategy':'manual_override','confidence':1.,
                'keyframes':[{'time':0,'x':0,'y':0,'width':.6,'height':1},
                    {'time':2.9,'x':.4,'y':0,'width':.6,'height':1}]}
            timeline._save(self.store,con,project,snapshot,'explicit_manual_crop_fixture')
        self.project=timeline.view(self.store,self.project['id']);before=self.store.get(self.project['id'])
        manager=PreviewManager(self.config,self.store)
        try:
            with patch('services.windows_native.asr.analyze',side_effect=AssertionError('No provider')):
                queued=manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertEqual(value['preview_profile'],FULL_PROFILE)
            for key in ('captions_included','smart_reframe_keyframes_included','canonical_audio_routing','rendering_effects_parity'):
                self.assertTrue(value['manifest'][key])
            for key in ('final_render_parity','final_approval_eligible','final_qc_verified','human_final_video_accepted'):
                self.assertFalse(value['manifest'][key])
            path=manager.video_path(self.project['id'],value['timeline_version'])
            probe=json.loads(subprocess.check_output([str(self.config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
                '-show_streams','-show_format','-of','json',str(path)],text=True))
            video=next(v for v in probe['streams'] if v['codec_type']=='video')
            sound=next(v for v in probe['streams'] if v['codec_type']=='audio')
            self.assertEqual((video['width'],video['height']),(432,540));self.assertEqual(sound['sample_rate'],'48000')
            self.assertAlmostEqual(float(probe['format']['duration']),3,delta=.15)
            self.assertEqual(manager.generate(self.project['id'],self.project['revision'])['id'],queued['id'])
            self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(file_sha(source),original)
            binding=reviewed_preview(self.root,self.project);self.assertTrue(binding['rendering_effects_parity'])
            self.assertFalse(binding['final_render_parity']);self.assertTrue(binding['final_video_review_required'])
            approved=self.store.approve(self.project['id'],self.project['revision'],'AUTOMATED MOCK — NOT OWNER UAT',True)
            self.assertEqual(approved['approval']['reviewed_preview'],binding)
            (path.parent/'render-manifest.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(WorkflowError,'PREVIEW_MANIFEST_CHANGED'):manager.status(self.project['id'])
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED'):
                reviewed_preview(self.root,self.project)
        finally:manager.close()

    def test_cancel_owned_process_does_not_wait_for_timeout_or_dispatch_provider(self):
        event=threading.Event();timer=threading.Timer(.25,event.set);timer.start();started=time.monotonic()
        try:
            with self.assertRaisesRegex(WorkflowError,'PREVIEW_CANCELLED'):
                command_run([sys.executable,'-c','import time;time.sleep(20)'],self.root,'owned-child.log',30,'FIXTURE',event)
            self.assertLess(time.monotonic()-started,8)
            with self.assertRaisesRegex(WorkflowError,'PREVIEW_CANCELLED'):
                render_final_effects(self.config,{},self.root/'cancelled.mp4',event)
            self.assertFalse((self.root/'cancelled.mp4').exists())
        finally:timer.cancel()

    def test_mode_change_invalidates_preview_and_retains_historical_identity(self):
        self.real_source();manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);old=self.wait(manager)
            self.assertEqual(old['status'],'READY',old.get('error'));path=manager.video_path(self.project['id'],1)
            preserved=file_sha(path)
            self.project=source_settings.configure(self.store,self.project['id'],self.project['revision'],{
                'expected_version':1,'preview_mode':'final_effects'})
            self.assertEqual(manager.status(self.project['id'])['status'],'STALE')
            self.assertEqual(file_sha(path),preserved)
            with self.assertRaisesRegex(WorkflowError,'AUTO_EDIT_CURRENT_PREVIEW_REVIEW_REQUIRED'):
                reviewed_preview(self.root,self.project)
            self.assertNotEqual(manager._folder(self.project['id'],self.project['shot_timeline']['sha256'],
                self.project['revision'],FULL_PROFILE),path.parent)
        finally:manager.close()


if __name__=='__main__':unittest.main()
