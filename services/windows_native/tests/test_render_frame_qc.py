"""Actual owned decoded frames; synthetic video is not semantic/Owner acceptance."""
import copy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from services.windows_native.contracts import WorkflowError, digest, file_sha
from services.windows_native.pipeline import Config
from services.windows_native import render_frame_qc as module


class RenderFrameQCTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root, secret_file=self.root / 'absent-secret', assemblyai_secret_file=self.root / 'absent-asr')
        (self.root / 'render-manifest.json').write_text('{"explicit_synthetic_fixture":true}', encoding='utf-8')
        self.document_sha = digest({'synthetic': True})
        subprocess.run([str(self.config.ffmpeg_bin / 'ffmpeg.exe'), '-hide_banner', '-nostdin', '-v', 'error',
            '-f', 'lavfi', '-i', 'testsrc2=s=320x180:r=30:d=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
            '-output_ts_offset', '4', str(self.root / 'final.mp4')], capture_output=True, check=True, timeout=30)

    def tearDown(self):
        self.temp.cleanup()

    def build(self):
        return module.build(self.config, self.root, document_sha256=self.document_sha, manifest_name='render-manifest.json')

    def test_actual_written_pngs_have_original_nonzero_decoded_pts_and_exact_render_hash(self):
        original = file_sha(self.root / 'final.mp4')
        record = self.build()
        value = module.validate(self.root, record, document_sha256=self.document_sha)
        self.assertEqual(value['rendered_video_sha256'], original)
        self.assertEqual(file_sha(self.root / 'final.mp4'), original)
        self.assertEqual(value['render_stream_start_seconds'], 4.)
        self.assertEqual(len(value['frames']), 8)
        self.assertEqual(value['frames'][0]['decoded_render_pts_seconds'], 4.)
        self.assertEqual(value['frames'][0]['timestamp_seconds'], 0.)
        self.assertLess(value['frames'][-1]['timestamp_seconds'], 2.)
        self.assertGreater(value['frames'][-1]['decoded_render_pts_seconds'], 5.)
        self.assertFalse(value['semantic_inference_performed'])
        self.assertEqual(value['semantic_provider_status'], 'NOT_REQUESTED')
        self.assertIsNone(value['confidence'])
        self.assertFalse(value['owner_uat_accepted'])
        self.assertFalse(value['publishing_authorized'])
        for frame in value['frames']:
            self.assertEqual(file_sha(self.root / frame['evidence_frame_reference']), frame['sha256'])
            self.assertIsNone(frame['pixel_facts']['frame_caption'])
        self.assertEqual(json.loads((self.root / module.REPORT).read_bytes()), record)
        self.assertEqual(len(module.artifact_names(self.root)), 10)

    def test_final_manifest_and_document_changes_reject_current_evidence(self):
        record = self.build()
        with self.assertRaisesRegex(WorkflowError, 'RECORD_INVALID'):
            module.validate(self.root, record, document_sha256='0' * 64)
        for name in ('final.mp4', 'render-manifest.json'):
            path = self.root / name; original = path.read_bytes()
            path.write_bytes(b'EXPLICIT ISOLATED CORRUPTION FIXTURE')
            with self.assertRaisesRegex(WorkflowError, 'INPUT_CHANGED'):
                module.validate(self.root, record)
            path.write_bytes(original)
        self.assertEqual(module.validate(self.root, record)['rendered_video_sha256'], file_sha(self.root / 'final.mp4'))

    def test_modified_png_and_rehashed_forged_pixel_claims_fail(self):
        record = self.build(); changed = copy.deepcopy(record)
        changed['observation']['frames'][0]['pixel_facts']['luma_mean'] = 0.
        changed['sha256'] = digest(changed['observation'])
        with self.assertRaisesRegex(WorkflowError, 'IMAGE_CHANGED'):
            module.validate(self.root, changed)
        image = self.root / record['observation']['frames'][0]['evidence_frame_reference']
        image.write_bytes(b'NOT PNG')
        with self.assertRaisesRegex(WorkflowError, 'IMAGE_INVALID'):
            module.validate(self.root, record)

    def test_raw_authority_timestamp_path_order_and_pts_substitution_cannot_pass_rehash(self):
        record = self.build()
        mutations = [lambda v: v.update(semantic_inference_performed=0), lambda v: v.update(publishing_authorized=1),
            lambda v: v.update(owner_uat_accepted=True), lambda v: v['frames'][0].update(decoded_render_pts=True),
            lambda v: v['frames'][0].update(decoded_render_pts_seconds=0.),
            lambda v: v['frames'][0].update(evidence_frame_reference='../outside.png'),
            lambda v: v['frames'].reverse()]
        for mutate in mutations:
            changed = copy.deepcopy(record); mutate(changed['observation']); changed['sha256'] = digest(changed['observation'])
            with self.assertRaisesRegex(WorkflowError, 'RECORD_INVALID'):
                module.validate(self.root, changed, physical=False)

    def test_existing_evidence_is_not_overwritten_and_hardlinks_are_rejected(self):
        record = self.build(); report = (self.root / module.REPORT).read_bytes()
        with self.assertRaisesRegex(WorkflowError, 'ALREADY_EXISTS'):
            self.build()
        self.assertEqual((self.root / module.REPORT).read_bytes(), report)
        with self.assertRaisesRegex(WorkflowError,'ARTIFACT_INVALID'):
            module.checked(self.root/module.FOLDER,'../final.mp4')
        frame = self.root / record['observation']['frames'][0]['evidence_frame_reference']
        os.link(frame, self.root / 'explicit-link.png')
        with self.assertRaisesRegex(WorkflowError, 'ARTIFACT_INVALID'):
            module.validate(self.root, record)

    def test_decode_failure_and_foreign_manifest_never_write_successful_evidence(self):
        with self.assertRaisesRegex(WorkflowError, 'INPUT_INVALID'):
            module.build(self.config, self.root, document_sha256=self.document_sha, manifest_name='../outside.json')
        with patch.object(module.subprocess, 'run', side_effect=subprocess.TimeoutExpired('explicit mock tool', 30)):
            with self.assertRaisesRegex(WorkflowError, 'DECODE_FAILED'):
                self.build()
        self.assertFalse((self.root / module.REPORT).exists())

    def test_self_consistent_rehashed_pts_and_changed_decoder_log_cannot_replace_original_timing(self):
        record=self.build();changed=copy.deepcopy(record);value=changed['observation']
        num,den=map(int,value['render_stream_time_base'].split('/'))
        for index,frame in enumerate(value['frames']):
            frame['decoded_render_pts']+=1;frame['decoded_render_pts_seconds']+=num/den;frame['timestamp_seconds']+=num/den
            frame['frame_id']='rqf_'+digest([value['rendered_video_sha256'],index,frame['decoded_render_pts'],frame['sha256']])[:24]
        changed['sha256']=digest(value)
        self.assertEqual(module.validate(self.root,changed,physical=False)['frames'][0]['timestamp_seconds'],num/den)
        with self.assertRaisesRegex(WorkflowError,'TIMESTAMPS_CHANGED'):module.validate(self.root,changed)
        (self.root/'render-frame-qc.log').write_text('EXPLICIT DECODER LOG CORRUPTION',encoding='utf-8')
        with self.assertRaisesRegex(WorkflowError,'TIMESTAMPS_INVALID'):module.validate(self.root,record)


if __name__ == '__main__':
    unittest.main()
