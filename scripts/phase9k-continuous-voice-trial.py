"""One local continuous reading of existing approved words, for Owner listening.

No Native project is mutated. The larger trial frame cap and normalization
chunk limit are recorded explicitly; the production voice profile stays locked.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import socket
import sys
import time
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.pipeline import Config, PROFILE_SHA, REPO, profile, verify_runtime
from services.windows_native.contracts import WorkflowError, digest, file_sha, write_json


def main(case, streaming=False):
    current = REPO / f'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01/case-{case:02}'
    root = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
    out = root / (f'continuous-stream-case-{case:02}' if streaming else f'continuous-case-{case:02}')
    out.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads((current / 'input.json').read_bytes())
    assert snapshot['approval']['snapshot_sha256'] == digest(snapshot['document'])
    write_json(out / 'input.json', snapshot)
    verify_runtime(Config())
    import vieneu
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps, phonemize_text_with_emotions

    text = snapshot['document']['proposal']['narration']
    chunks, gaps = normalize_to_chunks_v3_with_gaps(text, max_chars=4096)
    assert len(chunks) == 1 and not gaps, 'CONTINUOUS_TRIAL_MUST_BE_ONE_MODEL_CONTEXT'
    phonemes = phonemize_text_with_emotions(chunks[0])
    params = {k: profile()['parameters'][k] for k in ('temperature', 'top_k', 'top_p', 'repetition_penalty', 'max_new_frames')}
    params['max_new_frames'] = 768
    write_json(out / 'trial.json', {
        'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS', 'case': case,
        'approval_snapshot_sha256': snapshot['approval']['snapshot_sha256'],
        'approved_narration': text, 'normalized_text': chunks[0], 'phonemes': phonemes,
        'base_voice_profile_sha256': PROFILE_SHA, 'seed': 604,
        'effective_parameters': params, 'normalization_max_chars_override': 4096,
        'frame_cap_override': {'production': 300, 'trial': 768},
        'new_spoken_text_added': False, 'speed': 1, 'pitch_processing': False,
        'codec_decode': 'official_stateful_streaming' if streaming else 'full',
        'native_production_job': False, 'native_project_mutated': False,
        'human_listening_pass': False})

    def blocked_connect(*args, **kwargs):
        raise WorkflowError('LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED')
    socket.socket.connect = blocked_connect

    class TrialEngine(OnnxV3LiteEngine):
        def _load_denoiser(self): return None
        def _acoustic_frame(self, *args, **kwargs):
            codes, eos = super()._acoustic_frame(*args, **kwargs)
            self.observed_frames += 1
            self.observed_eos = bool(eos)
            self.generated_codes.append(np.array(codes, dtype=np.int32, copy=True))
            return codes, eos

    engine = TrialEngine(checkpoint_path='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo',
                         onnx_dir='C:/NPD-Video-Factory/runtime/models/vieneu-v3-turbo/onnx_update',
                         codec_dir=str(root / 'codec-streaming') if streaming else 'C:/NPD-Video-Factory/runtime/models/moss-codec', threads=4)
    engine.babble_retries = 0
    preset_path = Path(vieneu.__file__).parent / 'assets/voices_v3_turbo.json'
    preset = json.loads(preset_path.read_bytes())['presets'][profile()['voice_id']]
    np.random.seed(604)
    engine.observed_frames, engine.observed_eos, engine.generated_codes = 0, False, []
    started = time.perf_counter()
    try:
        kwargs = {'phonemes': phonemes, 'speaker_emb': np.asarray(preset['speaker_emb'], dtype=np.float32),
                  'ref_codes': np.asarray(preset['codes'], dtype=np.int64), **params}
        if streaming:
            assert engine.sess_codec_step is not None and engine._codec_stream_spec, 'NO_SILENT_FULL_DECODER_FALLBACK'
            audio = np.concatenate(list(engine.infer_stream(**kwargs)))
        else:
            audio = engine.infer(**kwargs)
    except Exception as error:
        write_json(out / 'failure.json', {'classification': 'ACTUAL_EXPERIMENT_FAILURE', 'error_type': type(error).__name__,
                   'message': str(error), 'observed_frames': engine.observed_frames, 'observed_eos': engine.observed_eos,
                   'native_project_mutated': False, 'human_audio_quality_pass': False})
        if engine.generated_codes:
            np.savez_compressed(out / 'generated-codes.npz', codes=np.stack(engine.generated_codes))
        raise
    np.savez_compressed(out / 'generated-codes.npz', codes=np.stack(engine.generated_codes))
    if not engine.observed_eos:
        write_json(out / 'failure.json', {'classification': 'ACTUAL_EXPERIMENT_FAILURE',
                   'code': 'TRIAL_FRAME_CAP_WITHOUT_EOS_STOP', 'observed_frames': engine.observed_frames,
                   'observed_eos': False, 'native_project_mutated': False, 'human_audio_quality_pass': False})
        raise WorkflowError('TRIAL_FRAME_CAP_WITHOUT_EOS_STOP')
    assert audio.size and np.isfinite(audio).all() and len(audio) <= 48000 * profile()['max_audio_seconds']
    with (out / 'voice.wav').open('xb') as dest, wave.open(dest, 'wb') as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(48000)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())
    spec = importlib.util.spec_from_file_location('diagnostics', REPO / 'scripts/phase9k-audio-diagnostics.py')
    diagnostics = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostics)
    result = {'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS', 'case': case,
              'voice_sha256': file_sha(out / 'voice.wav'), 'duration_seconds': len(audio) / 48000,
              'frames': engine.observed_frames, 'observed_eos': engine.observed_eos,
              'peak': float(np.abs(audio).max()), 'runtime_seconds': round(time.perf_counter() - started, 3),
              'network_blocked': True, 'inference_calls': 1, 'retries': 0,
              'same_official_preset_sha256': file_sha(preset_path),
              'speech_diagnostics': diagnostics.pitch_measurements(audio, 48000),
              'codec_decode': 'official_stateful_streaming' if streaming else 'full',
              'word_alignment': 'none', 'native_project_mutated': False, 'human_audio_accepted': False,
              'requires_human_check_for_word_omissions_repetitions_and_timbre': True}
    write_json(out / 'results.json', result)
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('case', type=int, choices=(1, 2, 4, 6, 8))
    parser.add_argument('--streaming', action='store_true')
    args = parser.parse_args(); main(args.case, args.streaming)
