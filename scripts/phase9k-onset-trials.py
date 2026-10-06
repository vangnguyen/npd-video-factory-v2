"""Isolated decoder-context experiments on byte-bound, approved narration.

These trials are not Native production jobs and never establish listening PASS.
The baseline is regenerated first and must equal the current production WAV.
Only the decoder sees the optional prefix; all generated acoustic codes stay
identical, and the exact prefix sample count is removed from each result.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native import pipeline
from services.windows_native.contracts import digest, file_sha, write_json

REVIEW = pipeline.REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01'
TRIALS = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
NAMED = {1: {2: 'Ngày 23 tháng 4', 4: 'đây là bước', 5: 'bạn muốn tìm hiểu'},
         2: {2: 'Theo', 4: 'điều đáng theo dõi'},
         4: {3: 'Thứ hai', 4: 'thứ ba', 5: 'bạn muốn làm rõ'}}


def write_wave(path, audio, rate=48000):
    with path.open('xb') as dest, wave.open(dest, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes((np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes())


def main(case):
    current = REVIEW / f'case-{case:02}'
    out = TRIALS / f'case-{case:02}'
    out.mkdir(parents=True, exist_ok=False)
    snapshot = json.loads((current / 'input.json').read_bytes())
    assert snapshot['approval']['snapshot_sha256'] == digest(snapshot['document'])
    write_json(out / 'input.json', snapshot)
    write_json(out / 'experiment.json', {
        'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS', 'case': case,
        'owner_named_onsets': NAMED[case], 'base_wave_sha256': file_sha(current / 'voice.wav'),
        'same_acoustic_codes_for_all_decoder_variants': True,
        'new_spoken_text_added': False, 'pitch_or_speed_processing': False,
        'human_listening_pass': False, 'native_project_or_job_mutated': False})

    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.core_utils import CODEC_SAMPLES_PER_FRAME, edge_silence
    import vieneu
    frames = []
    instances = []
    original_decode = OnnxV3LiteEngine._decode_codes

    def capture(engine, codes):
        frames.append(np.array(codes, dtype=np.int32, copy=True))
        if not instances:
            instances.append(engine)
        return original_decode(engine, codes)

    OnnxV3LiteEngine._decode_codes = capture
    pipeline.synthesize(pipeline.Config(), snapshot, out)
    OnnxV3LiteEngine._decode_codes = original_decode
    if file_sha(out / 'voice.wav') != file_sha(current / 'voice.wav'):
        raise RuntimeError('REGENERATED_BASELINE_DOES_NOT_MATCH_CURRENT_VOICE')
    plan = json.loads((out / 'tts-plan.json').read_bytes())
    assert len(frames) == sum(len(u['phonemes']) for u in plan['units'])
    np.savez_compressed(out / 'generated-codes.npz', **{f'call_{i:02}': c for i, c in enumerate(frames)})
    preset_path = Path(vieneu.__file__).parent / 'assets/voices_v3_turbo.json'
    preset = json.loads(preset_path.read_bytes())['presets'][pipeline.profile()['voice_id']]
    reference = np.asarray(preset['codes'], dtype=np.int32)
    spec = importlib.util.spec_from_file_location('diagnostics', pipeline.REPO / 'scripts/phase9k-audio-diagnostics.py')
    diagnostics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(diagnostics)
    engine = instances[0]
    results, call = [], 0
    for unit in plan['units']:
        for chunk in range(len(unit['phonemes'])):
            codes = frames[call]
            if chunk == 0 and unit['scene'] in NAMED[case]:
                baseline = original_decode(engine, codes)
                variants = {'baseline': np.empty((0, 16), dtype=np.int32),
                            'reference24': reference[-24:],
                            'reference64': reference[-64:],
                            'previous24': frames[call - 1][-24:] if call else reference[-24:]}
                for variant, prefix in variants.items():
                    audio = original_decode(engine, np.concatenate([prefix, codes]))
                    prefix_samples = len(prefix) * CODEC_SAMPLES_PER_FRAME
                    assert len(audio) == (len(prefix) + len(codes)) * CODEC_SAMPLES_PER_FRAME
                    audio = audio[prefix_samples:]
                    assert audio.shape == baseline.shape and np.isfinite(audio).all()
                    path = out / f'scene-{unit["scene"]:02}-{variant}.wav'
                    write_wave(path, audio)
                    lead, tail = edge_silence(audio, 48000)
                    start = lead
                    onset = audio[start:min(start + 48000, len(audio) - tail)]
                    body = audio[min(start + 48000, len(audio) - tail):len(audio) - tail]
                    results.append({
                        'scene': unit['scene'], 'call': call, 'variant': variant,
                        'owner_phrase': NAMED[case][unit['scene']], 'text': unit['text'],
                        'wave': str(path), 'wave_sha256': file_sha(path),
                        'prefix_frames_removed': len(prefix), 'prefix_samples_removed': prefix_samples,
                        'generated_codes_sha256': digest(codes.tolist()),
                        'generated_sample_count_preserved': len(audio) == len(baseline),
                        'activity_start_samples': int(lead), 'activity_end_samples': len(audio) - int(tail),
                        'peak': float(np.abs(audio).max()),
                        'rms_difference_from_baseline': float(np.sqrt(np.mean((audio - baseline) ** 2))),
                        'first_second': diagnostics.pitch_measurements(onset, 48000),
                        'remaining_speech': diagnostics.pitch_measurements(body, 48000),
                        'human_listening_pass': False})
            call += 1
    write_json(out / 'results.json', {
        'classification': 'EXPERIMENT_NOT_PRODUCTION_PASS', 'case': case,
        'regenerated_baseline_matches_current_wave': True,
        'network_blocked_during_synthesis': True, 'preset_sha256': file_sha(preset_path),
        'generated_codes_archive_sha256': file_sha(out / 'generated-codes.npz'),
        'voice_profile_file_sha256': pipeline.PROFILE_SHA,
        'onset_analysis_seconds': 1, 'results': results,
        'measurement_is_not_a_listening_decision': True})
    for r in results:
        print(json.dumps({k: r[k] for k in ('scene', 'variant', 'owner_phrase', 'first_second', 'rms_difference_from_baseline')}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('case', type=int, choices=sorted(NAMED))
    main(parser.parse_args().case)
