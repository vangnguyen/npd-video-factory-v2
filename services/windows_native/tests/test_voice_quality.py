import copy
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest.mock import patch

from services.windows_native.contracts import Proposal, WorkflowError, digest
from services.windows_native.pipeline import Config, profile, sentence_units, speech_units, synthesize
from services.windows_native.store import Store
from services.windows_native.voice_quality import policy_reference, resolve_policy


def proposal():
    text = ['Câu đầu tiên. Câu thứ hai.', 'Dữ kiện cần đối chiếu.', 'Xin cảm ơn.']
    return {'narration': ' '.join(text), 'facts_needing_source': ['Nguồn gốc'],
            'visual_brief': [{'scene': i + 1, 'visual': 'Ảnh', 'on_screen_text': 'Tìm hiểu',
                              'narration_excerpt': t} for i, t in enumerate(text)]}


class VoiceQualityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Config(data_root=Path(self.temp.name))
        self.store = Store(self.config.data_root)
        p = self.store.create('Voice review', 'Input')
        p = self.store.save(p['id'], p['revision'], proposal=proposal(),
                            asset={'id': 'image.jpg', 'sha256': 'fixture', 'rights_confirmed': True, 'illustration': True})
        self.project = self.store.approve(p['id'], p['revision'], 'Owner', True)

    def tearDown(self):
        self.temp.cleanup()

    def test_selection_invalidates_approval_preserves_history_and_never_dispatches(self):
        old = copy.deepcopy(self.project)
        p = self.store.set_voice_quality(old['id'], old['revision'], 'scene-context-v1')
        self.assertIsNone(p['approval'])
        self.assertEqual(p['revision'], old['revision'] + 1)
        self.assertEqual(p['document']['proposal'], old['document']['proposal'])
        self.assertEqual(p['jobs'], [])
        with self.assertRaisesRegex(WorkflowError, 'HUMAN_APPROVAL_REQUIRED_BEFORE_TTS'):
            self.store.enqueue(p['id'], p['revision'], 'render', uuid.uuid4().hex)
        reopened = Store(self.config.data_root).get(p['id'])
        self.assertEqual(reopened['document'], p['document'])
        original = next(v for v in self.store.versions(p['id']) if v['revision'] == old['revision'])
        self.assertEqual(original['document'], old['document'])
        p = self.store.approve(p['id'], p['revision'], 'Owner', True)
        same = self.store.set_voice_quality(p['id'], p['revision'], 'scene-context-v1')
        self.assertEqual(same['revision'], p['revision'])
        self.assertEqual(same['approval'], p['approval'])

    def test_unknown_policy_stale_revision_and_busy_project_are_rejected(self):
        p = self.project
        with self.assertRaisesRegex(WorkflowError, 'UNKNOWN_VOICE_QUALITY_POLICY'):
            self.store.set_voice_quality(p['id'], p['revision'], 'made-up')
        with self.assertRaisesRegex(WorkflowError, 'STALE_VERSION_RELOAD'):
            self.store.set_voice_quality(p['id'], p['revision'] - 1, 'scene-context-v1')
        self.store.enqueue(p['id'], p['revision'], 'render', uuid.uuid4().hex)
        with self.assertRaisesRegex(WorkflowError, 'PROJECT_BUSY'):
            self.store.set_voice_quality(p['id'], p['revision'], 'scene-context-v1')

    def test_policy_drift_fails_before_runtime_or_inference(self):
        doc = copy.deepcopy(self.project['document'])
        doc['voice_quality'] = policy_reference('scene-context-v1')
        doc['voice_quality']['sha256'] = 'tampered'
        snapshot = {'document': doc, 'approval': {'snapshot_sha256': digest(doc)}}
        with patch('services.windows_native.pipeline.verify_runtime') as runtime:
            with self.assertRaisesRegex(WorkflowError, 'VOICE_QUALITY_POLICY_CHANGED'):
                synthesize(self.config, snapshot, self.config.data_root)
            runtime.assert_not_called()

    def test_grouping_preserves_exact_text_and_legacy_sentence_default(self):
        obj = Proposal.model_validate(proposal())
        self.assertEqual(speech_units(obj, {}), sentence_units(obj))
        self.assertEqual(len(sentence_units(obj)), 4)
        units = speech_units(obj, {'voice_quality': policy_reference('scene-context-v1')})
        self.assertEqual(len(units), 3)
        self.assertEqual(' '.join(u['text'] for u in units), obj.narration)

    def test_seeded_synthesis_keeps_locked_sampling_and_records_real_policy(self):
        import numpy as np
        p = self.store.set_voice_quality(self.project['id'], self.project['revision'], 'scene-context-v1')
        p = self.store.approve(p['id'], p['revision'], 'Owner', True)
        captured = []
        class FakeEngine:
            def __init__(self, **kwargs): pass
            def infer(self, **kwargs):
                captured.append(kwargs)
                self.observed_eos = True
                return (np.sin(np.arange(48000) * .05) * (.1 + np.random.random() * .1)).astype(np.float32)
        voices = []
        for i in range(2):
            out = self.config.data_root / f'trial-{i}'
            out.mkdir()
            with patch('services.windows_native.pipeline.verify_runtime'), \
                 patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine', FakeEngine), \
                 patch('socket.socket.connect'):
                synthesize(self.config, {'document': p['document'], 'approval': p['approval']}, out)
            meta = json.loads((out / 'voice.json').read_bytes())
            plan = json.loads((out / 'tts-plan.json').read_bytes())
            self.assertEqual(meta['inference_calls'], 3)
            self.assertEqual(meta['quality_policy'], resolve_policy(p['document']))
            self.assertEqual(meta['quality_policy_sha256'], p['document']['voice_quality']['sha256'])
            self.assertEqual(plan['quality_policy'], meta['quality_policy'])
            self.assertTrue(meta['network_blocked'])
            self.assertEqual(meta['speed'], 1)
            voices.append((out / 'voice.wav').read_bytes())
        self.assertEqual(voices[0], voices[1])
        for kwargs in captured:
            for key in ('temperature', 'top_k', 'top_p', 'repetition_penalty', 'max_new_frames'):
                self.assertEqual(kwargs[key], profile()['parameters'][key])


if __name__ == '__main__':
    unittest.main()
