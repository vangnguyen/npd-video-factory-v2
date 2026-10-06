"""Unit-only synthetic fixtures; these never claim real provider or audio PASS."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

from services.windows_native.contracts import PROFILE_SHA, Proposal, WorkflowError, digest, file_sha
from services.windows_native.hardening import durable_json
from services.windows_native.pipeline import Config, measured_scene_units, profile, speech_units, synthesize
from services.windows_native.voice_quality import policy_reference, registered_policy
from services.windows_native import warm_voice as warm


def proposal():
    parts = ['Câu mở đầu. Nguồn gốc rõ ràng.', 'Đây là thông tin cần đối chiếu.', 'Bạn muốn tìm hiểu thêm?']
    return Proposal.model_validate({'narration': ' '.join(parts), 'facts_needing_source': ['Nguồn'],
        'visual_brief': [{'scene': index + 1, 'visual': 'Ảnh', 'on_screen_text': 'Tìm hiểu',
                         'narration_excerpt': text} for index, text in enumerate(parts)]})


def write_wave(path, pcm):
    with wave.open(str(path), 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(warm.RATE)
        wav.writeframes(pcm.astype('<i2').tobytes())


def synthetic_timing(plan, words):
    raw = {'id': 'unit-only-synthetic', 'status': 'completed', 'words': [
        {'text': w['text'], 'start': round(w['start_seconds'] * 1000),
         'end': round(w['end_seconds'] * 1000)} for w in words]}
    return {'schema_version': 1, 'plan_sha256': warm.cache_key(plan), 'source_wave_sha256': 'unit-fixture',
        'transcript': {'segments': [{'words': words}], 'provenance': {'provider': 'assemblyai-transcription',
                      'raw_response_sha256': digest(raw), 'transcript_id': raw['id'],
                      'word_timing_source': 'provider_native_word_timestamps'}}, 'raw_response': raw,
        'origin': {'classification': 'UNIT_TEST_SYNTHETIC_NOT_REAL_PROVIDER'}}


class WarmVoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = Config(data_root=self.root / 'data')
        self.policy = registered_policy(warm.POLICY_ID)
        self.proposal = proposal()
        self.plans = warm.build_plan(self.proposal, self.policy)

    def tearDown(self):
        self.temp.cleanup()

    def source(self, plan):
        folder = warm.cache_directory(self.config, plan)
        folder.mkdir(parents=True, exist_ok=True)
        durable_json(folder / 'plan.json', plan)
        pcm = (np.sin(np.arange(warm.RATE) * .03) * 12000).astype('<i2')
        write_wave(folder / 'source.wav', pcm)
        generated = {'schema_version': 1, 'plan_sha256': warm.cache_key(plan),
                     'source_wave_sha256': file_sha(folder / 'source.wav'), 'duration_seconds': 1,
                     'observed_eos': True, 'network_blocked': True, 'retries': 0,
                     'origin': {'classification': 'UNIT_TEST_SYNTHETIC_NOT_REAL_PROVIDER'}}
        durable_json(folder / 'generated.json', generated)
        return folder, generated

    def snapshot(self):
        doc = {'proposal': self.proposal.model_dump(), 'voice_quality': policy_reference(warm.POLICY_ID)}
        return {'document': doc, 'approval': {'snapshot_sha256': digest(doc)}}

    def generation_input(self, out):
        durable_json(out / 'input.json', self.snapshot())
        durable_json(out / 'runtime-config.json', self.config.dump())
        entries = [{'plan': plan, 'folder': str(warm.cache_directory(self.config, plan))} for plan in self.plans]
        durable_json(out / 'warm-generation.json', {'entries': entries})
        return entries

    def test_plans_keep_exact_narration_and_only_previous_approved_last_sentence(self):
        self.assertEqual(self.plans[0]['context_text'], '')
        self.assertEqual(self.plans[1]['context_text'], 'Nguồn gốc rõ ràng.')
        self.assertEqual(self.plans[2]['context_text'], 'Đây là thông tin cần đối chiếu.')
        self.assertEqual(' '.join(p['target_text'] for p in self.plans), self.proposal.narration)
        self.assertTrue(all(p['seed'] == 604 and p['normalization_max_chars'] == 4096 for p in self.plans))
        self.assertTrue(all(p['profile_sha256'] == PROFILE_SHA for p in self.plans))
        for key, value in self.plans[0]['effective_sampling_parameters'].items():
            self.assertEqual(value, profile()['parameters'][key])
        original = warm.cache_key(self.plans[1])
        changed = {**self.plans[1], 'context_text': 'Khác.'}
        self.assertNotEqual(original, warm.cache_key(changed))

    def test_long_context_fails_without_splitting_or_sampling_override(self):
        item = self.proposal.model_dump()
        item['visual_brief'][0]['narration_excerpt'] = 'Nội dung ' * 70 + '.'
        item['narration'] = ' '.join(s['narration_excerpt'] for s in item['visual_brief'])
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_CONTEXT_TOO_LONG'):
            warm.build_plan(Proposal.model_validate(item), self.policy)

    def test_new_policy_only_routes_opted_in_synthesis(self):
        doc = {'proposal': self.proposal.model_dump(), 'voice_quality': policy_reference(warm.POLICY_ID)}
        snapshot = {'document': doc, 'approval': {'snapshot_sha256': digest(doc)}}
        with patch('services.windows_native.pipeline.verify_runtime'), \
             patch.object(warm, 'synthesize_warm') as route, patch('socket.socket.connect') as network:
            synthesize(self.config, snapshot, self.root)
            route.assert_called_once()
            network.assert_not_called()
        legacy = speech_units(self.proposal, {})
        scene = speech_units(self.proposal, {'voice_quality': policy_reference('scene-context-v1')})
        self.assertEqual(len(legacy), 4)
        self.assertEqual(len(scene), 3)
        self.assertEqual(' '.join(u['text'] for u in legacy), self.proposal.narration)

    def test_generated_cache_rejects_wave_mutation_and_eos_failure(self):
        plan = self.plans[1]
        folder, generated = self.source(plan)
        self.assertEqual(warm.generated_record(folder, plan), generated)
        generated['observed_eos'] = False
        durable_json(folder / 'generated.json', generated)
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_GENERATED_BINDING_CHANGED'):
            warm.generated_record(folder, plan)
        generated['observed_eos'] = True
        durable_json(folder / 'generated.json', generated)
        write_wave(folder / 'source.wav', np.ones(48000, dtype='<i2'))
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_GENERATED_BINDING_CHANGED'):
            warm.generated_record(folder, plan)

    def test_timing_requires_actual_raw_digest_and_word_intervals(self):
        plan = self.plans[1]
        folder, generated = self.source(plan)
        words = [{'text': 'Nguồn.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'Đây', 'start_seconds': .4, 'end_seconds': .5},
                 {'text': 'là', 'start_seconds': .5, 'end_seconds': .6}]
        timing = synthetic_timing(plan, words)
        timing['source_wave_sha256'] = generated['source_wave_sha256']
        durable_json(folder / 'timing.json', timing)
        self.assertEqual(warm.timing_record(folder, plan, generated), timing)
        timing['raw_response']['words'][0]['text'] = 'Changed'
        durable_json(folder / 'timing.json', timing)
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_TIMING_BINDING_CHANGED'):
            warm.timing_record(folder, plan, generated)

    def test_normal_boundary_preserves_target_attack_and_reports_asr_disagreement(self):
        plan = self.plans[1]
        words = [{'text': 'Nguồn.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'Đây', 'start_seconds': .4, 'end_seconds': .5},
                 {'text': 'là', 'start_seconds': .5, 'end_seconds': .6},
                 {'text': 'khác', 'start_seconds': .6, 'end_seconds': .8}]
        boundary = warm.trim_boundary(plan, np.ones(48000) * .1, synthetic_timing(plan, words))
        self.assertAlmostEqual(boundary['cut_seconds'], .3)
        self.assertEqual(boundary['removed_samples'], 14400)
        self.assertFalse(boundary['full_target_word_accuracy_confirmed'])
        self.assertTrue(boundary['asr_disagreement_is_not_proof_of_an_audio_word_error'])
        self.assertLess(boundary['raw_text_token_similarity_diagnostic'], 1)

    def test_repeated_or_missing_onset_fails_explicitly(self):
        words = [{'text': 'Nguồn.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'Đây là', 'start_seconds': .3, 'end_seconds': .4},
                 {'text': 'Đây là', 'start_seconds': .5, 'end_seconds': .6}]
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'):
            warm.trim_boundary(self.plans[1], np.ones(48000) * .1, synthetic_timing(self.plans[1], words))
        words[1]['text'], words[2]['text'] = 'Khác', 'Thêm'
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'):
            warm.trim_boundary(self.plans[1], np.ones(48000) * .1, synthetic_timing(self.plans[1], words))

    def test_duplicate_first_two_tokens_extend_to_unique_exact_approved_prefix(self):
        words = [{'text': 'Đây là khác.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'Nguồn.', 'start_seconds': .3, 'end_seconds': .4},
                 {'text': 'Đây là', 'start_seconds': .6, 'end_seconds': .7},
                 {'text': 'thông tin', 'start_seconds': .7, 'end_seconds': .8}]
        boundary = warm.trim_boundary(self.plans[1], np.ones(48000) * .1, synthetic_timing(self.plans[1], words))
        self.assertEqual(boundary['matched_opening_tokens'], ['đây', 'là', 'thông'])
        self.assertAlmostEqual(boundary['cut_seconds'], .5)
        self.assertEqual(boundary['first_target_word']['text'], 'Đây là')

    def test_original_approved_abbreviation_matches_actual_asr_without_rewriting_audio(self):
        plan = {**self.plans[1], 'target_text': 'KMAC được giới thiệu.'}
        words = [{'text': 'Trước.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'KMAC', 'start_seconds': .4, 'end_seconds': .5},
                 {'text': 'được', 'start_seconds': .5, 'end_seconds': .6},
                 {'text': 'giới thiệu.', 'start_seconds': .6, 'end_seconds': .8}]
        boundary = warm.trim_boundary(plan, np.ones(48000) * .1, synthetic_timing(plan, words))
        self.assertEqual(boundary['matched_opening_tokens'], ['kmac', 'được'])
        self.assertEqual(boundary['opening_matches'][0]['representation'], 'original_approved_target_spelling')
        self.assertAlmostEqual(boundary['cut_seconds'], .3)
        self.assertFalse(boundary['full_target_word_accuracy_confirmed'])

    def test_conflicting_exact_spelling_variants_fail_without_guessing(self):
        plan = {**self.plans[1], 'target_text': 'KMAC được giới thiệu.'}
        words = [{'text': 'Trước.', 'start_seconds': .0, 'end_seconds': .1},
                 {'text': 'ca mờ a xê', 'start_seconds': .1, 'end_seconds': .3},
                 {'text': 'được giới thiệu.', 'start_seconds': .3, 'end_seconds': .5},
                 {'text': 'KMAC', 'start_seconds': .6, 'end_seconds': .7},
                 {'text': 'được giới thiệu.', 'start_seconds': .7, 'end_seconds': .9}]
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_TARGET_VARIANTS_DISAGREE'):
            warm.trim_boundary(plan, np.ones(48000) * .1, synthetic_timing(plan, words))

    def test_disputed_single_onset_requires_exact_context_and_continuation_plus_quiet_gap(self):
        plan = {**self.plans[1], 'context_text': 'Chưa chắc phản ánh hiện tại.',
                'target_text': 'Vang Nguyễn gợi ý một cách đọc tin.'}
        words = [{'text': 'phản ánh', 'start_seconds': .1, 'end_seconds': .3},
                 {'text': 'hiện tại', 'start_seconds': .3, 'end_seconds': .6},
                 {'text': 'và', 'start_seconds': .6, 'end_seconds': .8},
                 {'text': 'Nguyễn gợi ý', 'start_seconds': .8, 'end_seconds': .9},
                 {'text': 'một cách', 'start_seconds': .9, 'end_seconds': .95}]
        audio = np.ones(48000) * .1
        timing = synthetic_timing(plan, words)
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'):
            warm.trim_boundary(plan, audio, timing)
        audio[round(.5 * 48000):round(.65 * 48000)] = 0
        boundary = warm.trim_boundary(plan, audio, timing)
        self.assertTrue(boundary['onset_asr_disputed'])
        self.assertEqual(boundary['opening_matches'][0]['actual_disputed_head_tokens'], ['và'])
        self.assertEqual(boundary['opening_matches'][0]['approved_head_tokens'], ['vang'])
        self.assertAlmostEqual(boundary['cut_seconds'], .575)
        self.assertFalse(boundary['full_target_word_accuracy_confirmed'])
        self.assertEqual(boundary['first_target_word']['text'], 'và')

    def test_disputed_two_onset_tokens_keep_actual_words_and_fail_ambiguous_context(self):
        plan = {**self.plans[1], 'context_text': 'Từ riêng lượng giao dịch.',
                'target_text': 'Đây là dữ liệu lịch sử.'}
        words = [{'text': 'riêng lượng', 'start_seconds': .1, 'end_seconds': .3},
                 {'text': 'giao dịch', 'start_seconds': .3, 'end_seconds': .6},
                 {'text': 'Để', 'start_seconds': .6, 'end_seconds': .7},
                 {'text': 'lại', 'start_seconds': .7, 'end_seconds': .8},
                 {'text': 'dữ liệu lịch', 'start_seconds': .8, 'end_seconds': .9}]
        audio = np.ones(48000) * .1
        audio[round(.5 * 48000):round(.65 * 48000)] = 0
        boundary = warm.trim_boundary(plan, audio, synthetic_timing(plan, words))
        self.assertEqual(boundary['opening_matches'][0]['actual_disputed_head_tokens'], ['để', 'lại'])
        self.assertEqual(boundary['opening_matches'][0]['approved_head_tokens'], ['đây', 'là'])
        duplicate = [dict(w, start_seconds=w['start_seconds'] + 1, end_seconds=w['end_seconds'] + 1) for w in words]
        longer = np.ones(96000) * .1
        longer[round(.5 * 48000):round(.65 * 48000)] = 0
        longer[round(1.5 * 48000):round(1.65 * 48000)] = 0
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'):
            warm.trim_boundary(plan, longer, synthetic_timing(plan, words + duplicate))

    def test_disputed_head_without_both_exact_anchors_is_not_guessed(self):
        plan = {**self.plans[1], 'context_text': 'Chưa chắc phản ánh hiện tại.',
                'target_text': 'Vang Nguyễn gợi ý một cách đọc tin.'}
        words = [{'text': 'khác ánh', 'start_seconds': .1, 'end_seconds': .3},
                 {'text': 'hiện tại', 'start_seconds': .3, 'end_seconds': .6},
                 {'text': 'và', 'start_seconds': .6, 'end_seconds': .8},
                 {'text': 'Nguyễn gợi ý', 'start_seconds': .8, 'end_seconds': .9}]
        audio = np.ones(48000) * .1
        audio[round(.5 * 48000):round(.65 * 48000)] = 0
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_UNIQUE_TARGET_ONSET_REQUIRED'):
            warm.trim_boundary(plan, audio, synthetic_timing(plan, words))

    def test_grouped_or_touching_word_boundary_requires_unique_actual_quiet_gap(self):
        words = [{'text': 'Trước.', 'start_seconds': .1, 'end_seconds': .2},
                 {'text': 'Nguồn. Đây', 'start_seconds': .2, 'end_seconds': .6},
                 {'text': 'là', 'start_seconds': .6, 'end_seconds': .8}]
        timing = synthetic_timing(self.plans[1], words)
        audio = np.ones(48000) * .1
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_GROUPED_BOUNDARY_REVIEW_REQUIRED'):
            warm.trim_boundary(self.plans[1], audio, timing)
        audio[round(.35 * 48000):round(.45 * 48000)] = 0
        boundary = warm.trim_boundary(self.plans[1], audio, timing)
        self.assertTrue(boundary['asr_group_spans_context_and_target'])
        self.assertAlmostEqual(boundary['cut_seconds'], .4)
        audio[round(.5 * 48000):round(.57 * 48000)] = 0
        with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_GROUPED_BOUNDARY_REVIEW_REQUIRED'):
            warm.trim_boundary(self.plans[1], audio, timing)

    def test_unknown_generation_intent_never_replays_inference(self):
        plan = self.plans[0]
        folder = warm.cache_directory(self.config, plan)
        folder.mkdir(parents=True)
        durable_json(folder / 'plan.json', plan)
        durable_json(folder / 'generation.intent.json', {'plan_sha256': warm.cache_key(plan)})
        out = self.root / 'attempt'; out.mkdir()
        self.generation_input(out)
        with patch('services.windows_native.pipeline.verify_runtime'), \
             patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine') as engine:
            with self.assertRaisesRegex(WorkflowError, 'WARM_TTS_OUTCOME_UNKNOWN_NO_REPLAY'):
                warm.generate_offline(out)
            engine.assert_not_called()

    def test_separate_offline_child_resets_seed_per_scene_and_blocks_network(self):
        out = self.root / 'attempt'; out.mkdir()
        self.generation_input(out)
        samples = []
        class UnitEngine:
            def __init__(self, **kwargs): pass
            def infer(self, **kwargs):
                import socket
                with socket.socket() as conn:
                    with self_test.assertRaisesRegex(WorkflowError, 'LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED'):
                        conn.connect(('127.0.0.1', 1))
                samples.append(np.random.random())
                self.observed_eos = True
                self.observed_frames = 2
                return (np.sin(np.arange(4800) * .02) * .1).astype(np.float32)
        self_test = self
        with patch('services.windows_native.pipeline.verify_runtime'), \
             patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine', UnitEngine), \
             patch('socket.socket.connect'):
            warm.generate_offline(out)
        self.assertEqual(len(samples), 3)
        self.assertEqual(len(set(samples)), 1)
        self.assertEqual(json.loads((out / 'warm-generation-result.json').read_bytes())['new_inference_calls'], 3)
        for plan in self.plans:
            self.assertTrue(warm.generated_record(warm.cache_directory(self.config, plan), plan)['network_blocked'])

    def test_direct_child_unapproved_or_changed_input_never_loads_runtime_or_infers(self):
        out = self.root / 'attempt'; out.mkdir()
        self.generation_input(out)
        for changed in (None, {'snapshot_sha256': 'changed'}):
            snapshot = self.snapshot()
            snapshot['approval'] = changed
            durable_json(out / 'input.json', snapshot)
            with patch('services.windows_native.pipeline.verify_runtime') as runtime, \
                 patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine') as engine:
                with self.assertRaisesRegex(WorkflowError, 'HUMAN_APPROVAL_REQUIRED_BEFORE_TTS'):
                    warm.generate_offline(out)
                runtime.assert_not_called()
                engine.assert_not_called()

    def test_direct_child_tampered_plan_or_cache_destination_never_infers(self):
        out = self.root / 'attempt'; out.mkdir()
        entries = self.generation_input(out)
        altered_plan = copy.deepcopy(entries)
        altered_plan[1]['plan']['target_text'] = 'Unapproved speech.'
        altered_folder = copy.deepcopy(entries)
        altered_folder[1]['folder'] = str(self.root / 'different-cache')
        for changed in (altered_plan, altered_folder, entries[:-1]):
            durable_json(out / 'warm-generation.json', {'entries': changed})
            with patch('services.windows_native.pipeline.verify_runtime') as runtime, \
                 patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine') as engine:
                with self.assertRaisesRegex(WorkflowError, 'WARM_VOICE_GENERATION_PLAN_BINDING_CHANGED'):
                    warm.generate_offline(out)
                runtime.assert_not_called()
                engine.assert_not_called()

    def test_direct_child_changed_registered_policy_reference_never_infers(self):
        out = self.root / 'attempt'; out.mkdir()
        self.generation_input(out)
        snapshot = self.snapshot()
        snapshot['document']['voice_quality']['sha256'] = 'changed-policy'
        snapshot['approval']['snapshot_sha256'] = digest(snapshot['document'])
        durable_json(out / 'input.json', snapshot)
        with patch('services.windows_native.pipeline.verify_runtime') as runtime, \
             patch('vieneu._v3_turbo_engine.onnx_runtime_lite.OnnxV3LiteEngine') as engine:
            with self.assertRaisesRegex(WorkflowError, 'VOICE_QUALITY_POLICY_CHANGED'):
                warm.generate_offline(out)
            runtime.assert_not_called()
            engine.assert_not_called()

    def test_coordinator_keeps_asr_outside_offline_subprocess_and_emits_renderer_contract(self):
        out = self.root / 'attempt'; out.mkdir()
        for plan in self.plans:
            self.source(plan)
        doc = {'proposal': self.proposal.model_dump(), 'voice_quality': policy_reference(warm.POLICY_ID)}
        snapshot = {'document': doc, 'approval': {'snapshot_sha256': digest(doc)}}
        events = []
        def child(*args, **kwargs):
            events.append('offline_child')
            durable_json(out / 'warm-generation-result.json', {'new_inference_calls': 0, 'plan_keys': []})
            return type('Done', (), {'returncode': 0})()
        def timing(*args):
            events.append('asr_coordinator')
            return {'fixture': 'UNIT_ONLY'}
        def boundary(plan, audio, timing):
            return {'removed_samples': 4800, 'cut_seconds': .1, 'human_audio_accepted': False}
        with patch.object(warm.subprocess, 'run', side_effect=child), \
             patch.object(warm, 'observe_timing', side_effect=timing), \
             patch.object(warm, 'trim_boundary', side_effect=boundary), \
             patch('socket.socket.connect') as socket_connect:
            warm.synthesize_warm(self.config, snapshot, out, self.policy)
            socket_connect.assert_not_called()
        self.assertEqual(events, ['offline_child', 'asr_coordinator', 'asr_coordinator'])
        meta = json.loads((out / 'voice.json').read_bytes())
        self.assertEqual(meta['new_inference_calls'], 0)
        self.assertEqual(meta['reused_inference_calls'], 3)
        self.assertEqual(meta['word_alignment'], 'none')
        self.assertEqual(meta['network_scope'], 'local_inference_subprocess_only')
        self.assertEqual(' '.join(u['text'] for u in meta['units']), self.proposal.narration)
        self.assertEqual(len(measured_scene_units(self.proposal, meta)), 3)
        self.assertTrue(meta['human_listening_required'])
        self.assertEqual(meta['source_document_sha256'], digest(doc))


if __name__ == '__main__':
    unittest.main()
