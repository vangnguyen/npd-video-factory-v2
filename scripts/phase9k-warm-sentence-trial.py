"""Try an approved preceding sentence before each Owner-named onset.

Only local trial files are created. The additional context consists entirely
of existing approved narration; it is not part of the final target scene.
Untrimmed trial audio is deliberately labelled until timing can be verified.
"""
import argparse
import json
from pathlib import Path
import socket
import sys
import time
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config, PROFILE_SHA, REPO, profile, sentence_units, verify_runtime
from services.windows_native.contracts import Proposal, WorkflowError, digest, file_sha, normalize, write_json

ROOT = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
NAMED = {1: {2: 'Ngày 23 tháng 4', 4: 'đây là bước', 5: 'bạn muốn tìm hiểu'},
         2: {2: 'Theo', 4: 'điều đáng theo dõi'},
         4: {3: 'Thứ hai', 4: 'thứ ba', 5: 'bạn muốn làm rõ'}}


def main(case):
    current = REPO / f'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-{case:02}'
    out = ROOT / f'warm-sentence-case-{case:02}'
    out.mkdir(exist_ok=False)
    snapshot = json.loads((current / 'input.json').read_bytes())
    assert snapshot['approval']['snapshot_sha256'] == digest(snapshot['document'])
    write_json(out / 'input.json', snapshot)
    verify_runtime(Config())
    import vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions
    from vieneu_utils.core_utils import edge_silence

    def blocked_connect(*args, **kwargs): raise WorkflowError('LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED')
    socket.socket.connect = blocked_connect
    class TrialEngine(OnnxV3LiteEngine):
        def _load_denoiser(self): return None
        def _acoustic_frame(self, *args, **kwargs):
            codes, eos = super()._acoustic_frame(*args, **kwargs)
            self.observed_frames += 1; self.observed_eos = bool(eos)
            return codes, eos
    engine = TrialEngine(checkpoint_path='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo',
                         onnx_dir='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo/onnx_update',
                         codec_dir='C:/NPD-Video-Factory/runtime/models/moss-codec', threads=4)
    engine.babble_retries = 0
    preset_path = Path(vieneu.__file__).parent / 'assets/voices_v3_turbo.json'
    preset = json.loads(preset_path.read_bytes())['presets'][profile()['voice_id']]
    params = {k: profile()['parameters'][k] for k in ('temperature', 'top_k', 'top_p', 'repetition_penalty', 'max_new_frames')}
    proposal = Proposal.model_validate(snapshot['document']['proposal'])
    legacy_units = sentence_units(proposal)
    results = []
    for scene, phrase in NAMED[case].items():
        target = next(s.narration_excerpt for s in proposal.visual_brief if s.scene == scene)
        previous = [u for u in legacy_units if u['scene'] < scene][-1]['text']
        text = normalize(previous + ' ' + target)
        chunks, gaps = normalize_to_chunks_v3_with_gaps(text, max_chars=4096)
        assert len(chunks) == 1 and not gaps and len(text) < 512
        phonemes = phonemize_text_with_emotions(chunks[0])
        folder = out / f'scene-{scene:02}'; folder.mkdir()
        write_json(folder / 'trial.json', {'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS',
                   'case': case, 'scene': scene, 'owner_phrase': phrase, 'target_text': target,
                   'approved_previous_sentence_context': previous, 'combined_text': text,
                   'normalized_text': chunks[0], 'phonemes': phonemes,
                   'approval_snapshot_sha256': snapshot['approval']['snapshot_sha256'],
                   'base_voice_profile_sha256': PROFILE_SHA, 'seed': 604, 'effective_parameters': params,
                   'normalization_max_chars_override': 4096, 'sample_rate': 48000, 'speed': 1,
                   'native_project_mutated': False, 'automatic_retry': False, 'human_audio_accepted': False,
                   'audio_contains_extra_approved_context_until_verified_trim': True})
        np.random.seed(604)
        engine.observed_frames, engine.observed_eos = 0, False
        started = time.perf_counter()
        try:
            audio = engine.infer(phonemes=phonemes, speaker_emb=np.asarray(preset['speaker_emb'], dtype=np.float32),
                                 ref_codes=np.asarray(preset['codes'], dtype=np.int64), **params)
            if not engine.observed_eos: raise WorkflowError('TRIAL_FRAME_CAP_WITHOUT_EOS_STOP')
            assert audio.size and np.isfinite(audio).all()
            with (folder / 'with-context.wav').open('xb') as dest, wave.open(dest, 'wb') as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
                wav.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
            lead, tail = edge_silence(audio, 48000)
            result = {'classification': 'ACTUAL_LOCAL_TRIAL_AWAITS_TIMING_AND_HUMAN_LISTENING', 'scene': scene,
                      'duration_seconds': len(audio) / 48000, 'observed_eos': True, 'frames': engine.observed_frames,
                      'audio_sha256': file_sha(folder / 'with-context.wav'), 'peak': float(np.abs(audio).max()),
                      'activity_start_seconds': lead / 48000, 'activity_end_seconds': (len(audio) - tail) / 48000,
                      'runtime_seconds': round(time.perf_counter() - started, 3),
                      'word_alignment': 'none', 'retries': 0, 'network_blocked': True, 'human_audio_accepted': False}
        except Exception as error:
            result = {'classification': 'ACTUAL_EXPERIMENT_FAILURE', 'scene': scene,
                      'error_type': type(error).__name__, 'message': str(error),
                      'observed_eos': engine.observed_eos, 'frames': engine.observed_frames,
                      'retries': 0, 'human_audio_accepted': False}
        write_json(folder / 'results.json', result)
        results.append(result); print(json.dumps({'case': case, **result}, ensure_ascii=False), flush=True)
    write_json(out / 'results.json', {'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS', 'case': case,
               'source_input_sha256': file_sha(out / 'input.json'), 'same_official_preset_sha256': file_sha(preset_path),
               'results': results, 'native_project_mutated': False, 'human_audio_accepted': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('case', type=int, choices=sorted(NAMED))
    main(parser.parse_args().case)
