"""Temporary Native SQLite/media; synthetic tone and explicit saved ASR fixtures."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import uuid
from unittest.mock import patch

from services.windows_native import auto_edit_analysis as edit
from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.server import Runner
from services.windows_native.store import Store
from app.auto_edit_models import MediaMetadata
from app.auto_edit_providers import MediaSignals


def saved_asr(asset):
    record = {'asset_id': asset['id'], 'source_sha256': asset['sha256'],
        'media': {}, 'provider_calls': 0, 'transcript': {
            'language': 'vi', 'confidence': .9, 'provenance': {'provider': 'explicit-asr-fixture', 'fixture': True},
            'segments': [
                {'start_seconds': .2, 'end_seconds': 1.2, 'text': 'Xin chào.', 'speaker': None, 'confidence': .9,
                 'words': [{'start_seconds': .2, 'end_seconds': .6, 'text': 'Xin', 'confidence': .9},
                           {'start_seconds': .7, 'end_seconds': 1.2, 'text': 'chào.', 'confidence': .8}]},
                {'start_seconds': 2., 'end_seconds': 2.6, 'text': 'Cơ hội mới.', 'speaker': None, 'confidence': .8,
                 'words': [{'start_seconds': 2., 'end_seconds': 2.3, 'text': 'Cơ', 'confidence': .8},
                           {'start_seconds': 2.31, 'end_seconds': 2.45, 'text': 'hội', 'confidence': .8},
                           {'start_seconds': 2.46, 'end_seconds': 2.6, 'text': 'mới.', 'confidence': .8}]}]}}
    record['analysis_sha256'] = digest(record)
    return record


class NativeAutoEditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root)
        self.store = Store(self.root)
        self.project = self.store.create('Explicit auto-edit fixture', '', 'media')
        self.asset = {'id': uuid.uuid4().hex + '.mp4', 'kind': 'video', 'filename': 'Fixture <script>.mp4',
            'sha256': 'a' * 64, 'rights_confirmed': True, 'illustration': False,
            'duration_seconds': 3., 'width': 320, 'height': 240, 'has_audio': True}
        self.project = self.store.append_media(self.project['id'], self.project['revision'], self.asset)
        record = saved_asr(self.asset)
        with self.store.transaction() as con:
            doc = self.project['document']; doc['media_analysis'] = [record]
            con.execute('UPDATE projects SET revision=revision+1,document=? WHERE id=?', (json.dumps(doc), self.project['id']))
            self.store.version(con, self.project['id'])
        self.project = self.store.get(self.project['id'])
        self.metadata = MediaMetadata(media_kind='video', detected_content_type='video/mp4',
            duration_seconds=3., width=320, height=240, fps=30, video_codec='h264', audio_codec='aac')
        self.signals = MediaSignals(((1.5, .7),), ((.55, .9, None), (1.3, 1.95, None)), {'fixture': True})

    def tearDown(self):
        self.temp.cleanup()

    def save_analysis(self):
        job = self.store.enqueue(self.project['id'], self.project['revision'], 'auto_edit_analysis', uuid.uuid4().hex)
        job = self.store.claim()
        result = {'auto_edit_analyses': [edit.make_analysis(self.project['id'], self.project['document'], self.asset, self.metadata, self.signals)], 'provider_calls': 0}
        self.store.finish(job, result=result)
        self.project = self.store.get(self.project['id'])
        return edit.view(self.store, self.project['id'])

    def edit(self, bundle, text='Vang Nguyễn chào bạn.', **values):
        item = bundle['analyses'][0]; current = item['analysis']['transcript']
        return edit.edit_transcript(self.store, self.project['id'], bundle['revision'], item['analysis']['analysis_id'], {
            'expected_version': current['version'], 'segments': [{'segment_id': current['segments'][0]['segment_id'], 'text': text}], **values})

    def test_read_is_nonwriting_and_saved_evidence_is_normalized(self):
        before = self.store.versions(self.project['id'])
        self.assertEqual(edit.view(self.store, self.project['id'])['analyses'], [])
        self.assertEqual(self.store.versions(self.project['id']), before)
        bundle = self.save_analysis(); item = bundle['analyses'][0]
        transcript = item['analysis']['transcript']
        self.assertEqual(transcript['version'], 1); self.assertTrue(transcript['is_original_evidence'])
        self.assertEqual(len(transcript['segments'][0]['words']), 2)
        self.assertEqual(item['analysis']['provenance']['provider_calls'], 0)
        self.assertTrue(item['analysis']['silence_decisions'][0]['conflicts_with_speech'])
        self.assertFalse(item['analysis']['silence_decisions'][0]['enabled'])
        self.assertIsNone(item['scenes'][0]['motion_score'])
        self.assertIsNone(item['scenes'][0]['quality_score'])
        self.assertEqual(self.project['document']['media_analysis'][0], saved_asr(self.asset))
        self.assertNotIn('canonical_timeline', self.project['document'])
        self.assertIn('auto_edit_evidence_version', self.store.versions(self.project['id'])[0]['components'])

    def test_text_edit_cas_preserves_raw_and_other_alignment_then_restores_as_new(self):
        original = self.save_analysis(); evidence = deepcopy(self.project['document']['auto_edit_analyses'])
        result = self.edit(original); current = result['analyses'][0]['analysis']['transcript']
        self.assertEqual(current['version'], 2); self.assertFalse(current['is_original_evidence'])
        self.assertEqual(current['segments'][0]['words'], [])
        self.assertEqual(len(current['segments'][1]['words']), 3)
        self.assertIsNone(current['segments'][0]['confidence'])
        self.assertIn('Vang Nguyễn', result['analyses'][0]['scenes'][0]['transcript_excerpt'])
        with self.assertRaisesRegex(WorkflowError, '') as failed:
            self.edit(original)
        self.assertEqual(failed.exception.code, 'STALE_VERSION_RELOAD')
        self.project = self.store.get(self.project['id'])
        self.assertEqual(self.project['document']['auto_edit_analyses'], evidence)
        self.assertIsNone(self.project['approval'])
        base = original['analyses'][0]['analysis']['transcript']
        restored = edit.edit_transcript(self.store, self.project['id'], result['revision'], base['analysis_id'], {
            'expected_version': 2, 'base_transcript_id': base['transcript_id'],
            'segments': [{'segment_id': base['segments'][0]['segment_id'], 'text': base['segments'][0]['text']}]})
        self.assertEqual(restored['analyses'][0]['analysis']['transcript']['version'], 3)
        self.assertEqual(len(restored['analyses'][0]['analysis']['transcript']['segments'][0]['words']), 2)
        self.assertEqual(len(restored['analyses'][0]['transcript_history']), 3)
        self.assertEqual(edit.view(Store(self.root), self.project['id']), restored)

    def test_unchanged_text_has_no_write_or_nested_transaction(self):
        bundle = self.save_analysis(); before = self.store.versions(self.project['id'])
        self.assertEqual(self.edit(bundle, text='Xin chào.'), bundle)
        self.assertEqual(self.store.versions(self.project['id']), before)

    def test_invalid_scope_version_actor_fields_and_timing_are_rejected(self):
        bundle = self.save_analysis()
        for values, code in [({'expected_version': 999}, 'AUTO_EDIT_TRANSCRIPT_VERSION_CHANGED'),
                ({'actor_ref': 'forged'}, 'AUTO_EDIT_TRANSCRIPT_EDIT_INVALID'),
                ({'expected_timeline_version': 1}, 'AUTO_EDIT_TIMELINE_APPLICATION_NOT_AVAILABLE'),
                ({'base_transcript_id': 'trn_foreign'}, 'AUTO_EDIT_TRANSCRIPT_BASE_NOT_FOUND'),
                ({'segments': [{'segment_id': 'seg_foreign', 'text': 'Text'}]}, 'AUTO_EDIT_TRANSCRIPT_SEGMENT_NOT_FOUND')]:
            with self.assertRaises(WorkflowError) as failed:
                self.edit(bundle, **values)
            self.assertEqual(failed.exception.code, code)
        bad = saved_asr(self.asset)['transcript']; bad['segments'][0]['words'][0]['end_seconds'] = .2
        with self.assertRaises(ValueError):
            edit.normalize_transcript(bad, analysis_id='ana_test', asset_id='ast_test', duration=3, created_at=edit.stamp())
        bad['segments'][0]['words'][0]['end_seconds'] = float('nan')
        with self.assertRaises(ValueError):
            edit.normalize_transcript(bad, analysis_id='ana_test', asset_id='ast_test', duration=3, created_at=edit.stamp())

    def test_no_asr_does_not_propose_silence_or_text_highlights(self):
        doc = deepcopy(self.project['document']); doc.pop('media_analysis')
        record = edit.make_analysis(self.project['id'], doc, self.asset, self.metadata, self.signals)
        self.assertIsNone(record['analysis']['transcript'])
        self.assertEqual(record['analysis']['silence_decisions'], [])
        self.assertTrue(record['analysis']['provenance']['silence_cuts_blocked_without_transcript'])
        self.assertIsNone(record['analysis']['highlights'][0]['evidence']['factors']['information_density'])

    def test_idempotent_queue_tamper_stale_result_and_duplicate_binding(self):
        key = uuid.uuid4().hex
        one = self.store.enqueue(self.project['id'], self.project['revision'], 'auto_edit_analysis', key)
        self.assertEqual(self.store.enqueue(self.project['id'], self.project['revision'], 'auto_edit_analysis', key)['id'], one['id'])
        with self.assertRaises(WorkflowError) as failed:
            self.store.append_media(self.project['id'], self.project['revision'], self.asset)
        self.assertEqual(failed.exception.code, 'PROJECT_BUSY')
        job = self.store.claim()
        record = edit.make_analysis(self.project['id'], self.project['document'], self.asset, self.metadata, self.signals)
        changed = deepcopy(record); changed['analysis']['provenance']['source_asset_checksum'] = 'b' * 64
        changed['sha256'] = digest({key: value for key, value in changed.items() if key != 'sha256'})
        with self.assertRaises(WorkflowError) as failed:
            self.store.finish(job, result={'auto_edit_analyses': [changed]})
        self.assertEqual(failed.exception.code, 'AUTO_EDIT_ANALYSIS_STALE')
        self.store.finish(job, result={'auto_edit_analyses': [record]})
        self.project = self.store.get(self.project['id'])
        copied = self.store.duplicate(self.project['id'], self.project['revision'])
        self.assertEqual(edit.view(self.store, copied['id'])['analyses'], [])
        self.assertEqual(len(edit.view(self.store, self.project['id'])['analyses']), 1)

    def test_actual_local_job_measures_media_without_any_asr_call(self):
        source = self.root / 'synthetic-tone-not-speech.mp4'
        subprocess.run([str(self.config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n',
            '-f', 'lavfi', '-i', 'testsrc2=s=320x240:r=30:d=3', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-af', 'adelay=1000,apad=whole_dur=3', '-c:v', 'libx264', '-preset', 'ultrafast',
            '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-t', '3', str(source)], check=True, capture_output=True, timeout=30)
        asset = ingest_media(self.config, source, 'video/mp4', 'Source with misleading.jpg', rights_confirmed=True, illustration=False)
        local = self.store.create('Local measurement fixture', '', 'media')
        local = self.store.append_media(local['id'], local['revision'], asset)
        job = self.store.enqueue(local['id'], local['revision'], 'auto_edit_analysis', uuid.uuid4().hex)
        with patch('services.windows_native.asr.analyze', side_effect=AssertionError('ASR dispatch forbidden')):
            Runner(self.store, Pipeline(self.config)).run_one()
        finished = self.store.get_job(job['id']); self.assertEqual(finished['status'], 'succeeded', finished['error'])
        analysis = edit.view(self.store, local['id'])['analyses'][0]['analysis']
        self.assertTrue(analysis['provenance']['media_signals']['waveform']['measured'])
        self.assertGreater(len(analysis['provenance']['media_signals']['visual']['frames']), 0)
        self.assertIsNone(analysis['transcript']); self.assertEqual(analysis['silence_decisions'], [])
        self.assertEqual(analysis['provenance']['provider_calls'], 0)
        self.assertEqual(file_sha(source), asset['source_sha256'])
        checkpoint = self.root / 'jobs' / job['id'] / 'checkpoint-auto_edit_analysis.json'
        self.assertTrue(checkpoint.is_file())
        # A valid local checkpoint never permits reuse after external source drift.
        path = self.root / 'assets' / asset['id']
        with path.open('ab') as handle:
            handle.write(b'EXPLICIT_FIXTURE_SOURCE_DRIFT')
        with self.assertRaises(WorkflowError) as failed:
            Pipeline(self.config).run(finished, lambda stage: None)
        self.assertEqual(failed.exception.code, 'SOURCE_MEDIA_CHANGED_OR_MISSING')


if __name__ == '__main__':
    unittest.main()
