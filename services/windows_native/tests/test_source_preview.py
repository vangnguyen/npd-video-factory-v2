"""Actual local source proxy with synthetic tone; no speech/UAT/provider claim."""
from copy import deepcopy
import array
import asyncio
import json
import math
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import patch

from services.windows_native import auto_edit_timeline as timeline
from services.windows_native.contracts import WorkflowError, file_sha
from services.windows_native.shot_preview import PreviewManager
from services.windows_native.source_preview import PROFILE
from services.windows_native.tests import test_auto_edit_analysis as fixture
from app.timeline_proxy import PreviewCancelledError


class NativeSourcePreviewTests(unittest.TestCase):
    setUp=fixture.NativeAutoEditTests.setUp
    tearDown=fixture.NativeAutoEditTests.tearDown
    save_analysis=fixture.NativeAutoEditTests.save_analysis

    def real_source(self, **selection):
        directory=self.root/'assets';directory.mkdir(exist_ok=True)
        path=directory/self.asset['id']
        subprocess.run([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n',
            '-f','lavfi','-i','testsrc2=s=320x240:r=30:d=3','-f','lavfi','-i','sine=frequency=880:duration=1',
            '-af','adelay=1000,apad=whole_dur=3','-c:v','libx264','-preset','ultrafast',
            '-pix_fmt','yuv420p','-c:a','aac','-t','3',str(path)],check=True,capture_output=True,timeout=30)
        self.asset['sha256']=file_sha(path)
        with self.store.transaction() as con:
            doc=deepcopy(self.project['document'])
            doc['assets']=[self.asset];doc['media_analysis']=[fixture.saved_asr(self.asset)]
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?',
                (json.dumps(doc),self.project['id']))
            self.store.version(con,self.project['id'])
        self.project=self.store.get(self.project['id'])
        bundle=self.save_analysis();analysis=bundle['analyses'][0]['analysis']
        self.project=timeline.create(self.store,self.project['id'],bundle['revision'],{
            'analysis_id':analysis['analysis_id'],'transcript_id':analysis['transcript']['transcript_id'],**selection})
        return path

    def wait(self, manager):
        until=time.monotonic()+20
        while time.monotonic()<until:
            value=manager.status(self.project['id'])
            if value['status'] not in {'QUEUED','RUNNING'}:return value
            time.sleep(.05)
        self.fail('Source preview did not finish')

    def test_real_window_audio_hash_cache_and_originals_with_no_provider_or_approval(self):
        source=self.real_source(source_window=(.3,1.1),aspect_ratio='4:5')
        original=file_sha(source);before=self.store.get(self.project['id'])
        manager=PreviewManager(self.config,self.store)
        try:
            with patch('services.windows_native.asr.analyze',side_effect=AssertionError('No ASR dispatch')):
                queued=manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertEqual(value['audio_mode'],'canonical_timeline_proxy')
            self.assertEqual(value['preview_profile'],PROFILE)
            self.assertTrue(value['manifest']['audio_included'])
            for key in ('captions_included','music_ducking','smart_reframe_keyframes_included','final_render_parity','final_approval_eligible'):
                self.assertFalse(value['manifest'][key])
            self.assertEqual((value['provider_calls'],value['tts_calls']),(0,0))
            output=manager.video_path(self.project['id'],value['timeline_version'])
            probe=json.loads(subprocess.check_output([str(self.config.ffmpeg_bin/'ffprobe.exe'),'-v','error',
                '-show_streams','-show_format','-of','json',str(output)],text=True))
            video=next(stream for stream in probe['streams'] if stream['codec_type']=='video')
            audio=next(stream for stream in probe['streams'] if stream['codec_type']=='audio')
            self.assertEqual((video['width'],video['height']),(432,540))
            self.assertEqual(audio['codec_name'],'aac');self.assertAlmostEqual(float(probe['format']['duration']),1.,delta=.05)
            pcm=subprocess.check_output([str(self.config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-i',str(output),
                '-map','0:a:0','-ac','1','-ar','48000','-f','s16le','pipe:1'])
            samples=array.array('h');samples.frombytes(pcm)
            def rms(start,end):
                window=samples[round(start*48000):round(end*48000)]
                return math.sqrt(sum(float(n)**2 for n in window)/len(window))/32768
            self.assertLess(rms(.1,.3),.001);self.assertGreater(rms(.85,.95),.02)
            self.assertEqual(manager.generate(self.project['id'],self.project['revision'])['id'],queued['id'])
            self.assertEqual(self.store.get(self.project['id']),before);self.assertEqual(file_sha(source),original)
            self.assertIsNone(before['approval'])
            folder=output.parent
            (folder/'render-manifest.json').write_text('{}',encoding='utf-8')
            with self.assertRaisesRegex(WorkflowError,'PREVIEW_MANIFEST_CHANGED'):manager.status(self.project['id'])
        finally:manager.close()

    def test_muting_is_canonical_and_timeline_change_invalidates_playback(self):
        self.real_source();manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);first=self.wait(manager)
            self.assertEqual(first['status'],'READY',first.get('error'))
            track=next(t for t in self.project['shot_timeline']['snapshot']['tracks'] if t['type']=='audio')
            self.project=timeline.edit(self.store,self.project['id'],self.project['revision'],{
                'expected_version':1,'operations':[{'type':'set_track_state','track_id':track['track_id'],'muted':True}]})
            self.assertEqual(manager.status(self.project['id'])['status'],'STALE')
            with self.assertRaisesRegex(WorkflowError,'PREVIEW_STALE_OR_NOT_READY'):manager.video_path(self.project['id'],1)
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertFalse(value['manifest']['audio_included'])
            self.assertFalse(value['manifest']['canonical_source_audio'])
            self.assertTrue(value['manifest']['canonical_audio_routing'])
            self.assertNotEqual(value['id'],first['id'])
            self.assertIsNone(self.store.get(self.project['id'])['approval'])
        finally:manager.close()

    def test_shared_proxy_import_has_no_repository_or_sqlalchemy_dependency(self):
        subprocess.run([sys.executable,'-c',
            "import sys;sys.path.insert(0,'apps/api');import app.timeline_proxy;"
            "assert not any(name.startswith('sqlalchemy') or name in {'app.repositories','app.timeline_repository','app.timeline_service'} for name in sys.modules)"],
            check=True,capture_output=True,timeout=10)

    def test_cancellation_restart_and_explicit_retry_never_replay_providers(self):
        self.real_source();manager=PreviewManager(self.config,self.store);entered=threading.Event()
        async def blocked(config,project,output,event):
            entered.set()
            while not event.is_set():await asyncio.sleep(.02)
            raise PreviewCancelledError('Explicit cancellation fixture')
        try:
            with patch('services.windows_native.shot_preview.render_source',side_effect=blocked):
                manager.generate(self.project['id'],self.project['revision']);self.assertTrue(entered.wait(3))
                manager.cancel(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'CANCELLED');self.assertEqual(value['error']['code'],'PREVIEW_CANCELLED')
            manager.close();manager=PreviewManager(self.config,self.store)
            self.assertEqual(manager.status(self.project['id'])['status'],'CANCELLED')
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            self.assertEqual(value['provider_calls'],0);self.assertFalse(value['final_approval_eligible'])
        finally:manager.close()

    def test_source_drift_is_rejected_before_render_and_before_replaying_ready_media(self):
        source=self.real_source();manager=PreviewManager(self.config,self.store)
        try:
            manager.generate(self.project['id'],self.project['revision']);value=self.wait(manager)
            self.assertEqual(value['status'],'READY',value.get('error'))
            source.write_bytes(b'explicit isolated corrupt source')
            with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):manager.status(self.project['id'])
            with self.assertRaisesRegex(WorkflowError,'SOURCE_MEDIA_CHANGED_OR_MISSING'):manager.generate(self.project['id'],self.project['revision'])
        finally:manager.close()


if __name__=='__main__':unittest.main()
