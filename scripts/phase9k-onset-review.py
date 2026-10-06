"""Build byte-bound, volume-matched A/B clips for the eight actual complaints."""
import argparse
from datetime import datetime, timezone
import difflib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import canonical, digest, file_sha, write_json
from services.windows_native.pipeline import Config, REPO, verify_runtime

ROOT = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-onset-20261006')
EVIDENCE = REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-02'
CURRENT = EVIDENCE.parent / 'audio-repair-01'


def read(path): return json.loads(path.read_bytes())
def tokens(value): return re.findall(r'\w+', value.casefold())


def preserve_json(path, value):
    data = canonical(value)
    if path.exists(): assert path.read_bytes() == data
    else: path.write_bytes(data)


def copy_exact(source, target):
    target.parent.mkdir(exist_ok=True, parents=True)
    if target.exists(): assert target.read_bytes() == source.read_bytes()
    else: shutil.copyfile(source, target)


def read_wave(path):
    with wave.open(str(path), 'rb') as w:
        assert w.getnchannels() == 1 and w.getframerate() == 48000 and w.getsampwidth() == 2
        return np.frombuffer(w.readframes(w.getnframes()), dtype='<i2').astype(np.float64) / 32768


def write_wave(path, audio):
    data = (np.clip(audio, -1, 1) * 32767).astype('<i2').tobytes()
    if path.exists():
        with wave.open(str(path), 'rb') as old: assert old.readframes(old.getnframes()) == data
        return
    with path.open('xb') as dest, wave.open(dest, 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(48000); w.writeframes(data)


def quiet_gaps(audio, start, end):
    # Measured low-energy intervals, used only for experimental listening cuts
    # when the provider groups the name and the following onset ("EHG. Đây").
    begin, stop = round(start * 48000), round(end * 48000)
    size = 480
    clip = audio[begin:stop]
    frames = len(clip) // size
    levels = np.sqrt(np.mean(clip[:frames * size].reshape(frames, size) ** 2, axis=1))
    mask = levels < .0015
    edges = np.diff(np.r_[False, mask, False].astype(np.int8))
    return [{'start_seconds': (begin + a * size) / 48000, 'end_seconds': (begin + b * size) / 48000}
            for a, b in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))
            if b - a >= 6 and a > 0 and b < frames]


def collect():
    verify_runtime(Config())
    for case in (4, 1):
        copy_exact(ROOT / f'case-{case:02}/results.json', EVIDENCE / f'decoder-context-case-{case:02}.json')
    for name in ('streaming-codec-artifacts.json', 'stream-decoder-comparison.json'):
        copy_exact(ROOT / name, EVIDENCE / name)
    # The first two experimental failures occurred before durable failure logging
    # was added. Preserve their actual tool-reported outcomes explicitly.
    failed_full = {'classification': 'ACTUAL_EXPERIMENT_FAILURE', 'case': 4,
                   'command': 'phase9k-continuous-voice-trial.py 4', 'exit_code': 1,
                   'error_type': 'onnxruntime.capi.onnxruntime_pybind11_state.Fail',
                   'failed_node': '/decoder.7/transformer/layers.0/self_attn/Sub',
                   'error': 'Failed to allocate memory for requested buffer of size 4831838208',
                   'source': 'Actual exec/write_stdin result for the failed local trial',
                   'generated_frames_not_captured': True, 'human_audio_quality_pass': False,
                   'native_project_mutated': False, 'voice_file_created': False}
    preserve_json(EVIDENCE / 'continuous-full-failure.json', failed_full)
    codes = np.load(ROOT / 'continuous-stream-case-04/generated-codes.npz', allow_pickle=False)['codes']
    assert len(codes) == 768
    failed_stream = {'classification': 'ACTUAL_EXPERIMENT_FAILURE', 'case': 4,
                   'command': 'phase9k-continuous-voice-trial.py 4 --streaming', 'exit_code': 1,
                   'error': 'TRIAL_FRAME_CAP_WITHOUT_EOS_STOP', 'observed_eos': False,
                   'actual_generated_frames': len(codes), 'generated_codes_sha256': digest(codes.tolist()),
                   'source': 'Actual exec/write_stdin failure and generated-codes.npz from that trial',
                   'human_audio_quality_pass': False, 'native_project_mutated': False, 'voice_file_created': False}
    preserve_json(EVIDENCE / 'continuous-stream-failure.json', failed_stream)
    for case in (1, 2, 4):
        parent = ROOT / f'warm-sentence-case-{case:02}'
        copy_exact(parent / 'results.json', EVIDENCE / f'warm-context-case-{case:02}.json')
    print(json.dumps({'decoder_numerical_cases': 10, 'two_full_reading_failures_preserved': True,
                      'short_warm_context_trials': 8, 'production_quality_pass': False}), flush=True)


def build():
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps
    spec = importlib.util.spec_from_file_location('diagnostics', REPO / 'scripts/phase9k-audio-diagnostics.py')
    diagnostics = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostics)
    pairs, montage, offset = [], [], 0
    for case in (1, 2, 4):
        base = CURRENT / f'case-{case:02}'
        base_audio, base_meta = read_wave(base / 'voice.wav'), read(base / 'voice.json')
        parent = ROOT / f'warm-sentence-case-{case:02}'
        for source in sorted(parent.glob('scene-*/transcript.json')):
            trial = read(source.with_name('trial.json'))
            record = read(source)
            full = source.with_name('with-context.wav')
            assert record['voice_sha256'] == file_sha(full)
            assert record['trial_sha256'] == file_sha(source.with_name('trial.json'))
            words = record['transcript']['segments'][0]['words']
            expanded = [(token, index) for index, word in enumerate(words) for token in tokens(word['text'])]
            normalized, _ = normalize_to_chunks_v3_with_gaps(trial['target_text'], max_chars=4096)
            expected_tokens = tokens(' '.join(normalized))
            matches = [i for i in range(len(expanded) - 1)
                       if [t for t, _ in expanded[i:i + 2]] == expected_tokens[:2]]
            assert len(matches) == 1, f'UNIQUE_TARGET_ONSET_REQUIRED: {case}/{trial["scene"]}'
            flat = matches[0]; first_index = expanded[flat][1]
            assert first_index > 0
            previous, first = words[first_index - 1], words[first_index]
            gap = first['start_seconds'] - previous['end_seconds']
            grouped = flat > 0 and expanded[flat - 1][1] == first_index
            whole_audio = read_wave(full)
            if grouped:
                pauses = quiet_gaps(whole_audio, first['start_seconds'], first['end_seconds'])
                assert len(pauses) == 1, f'GROUPED_ASR_BOUNDARY_REQUIRES_HUMAN_TIMING_REVIEW: {case}/{trial["scene"]}/{pauses}'
                cut = (pauses[0]['start_seconds'] + pauses[0]['end_seconds']) / 2
                method = 'Unique measured >=60ms quiet gap inside an ASR group spanning approved context and target; experimental listening cut'
            else:
                if gap < .04:
                    pauses = quiet_gaps(whole_audio, previous['start_seconds'], first['end_seconds'])
                    pauses = [p for p in pauses if abs((p['start_seconds'] + p['end_seconds']) / 2 - first['start_seconds']) <= .25]
                    assert len(pauses) == 1, f'ASR_TOUCHING_INTERVALS_REQUIRE_HUMAN_TIMING_REVIEW: {case}/{trial["scene"]}/{pauses}'
                    cut = (pauses[0]['start_seconds'] + pauses[0]['end_seconds']) / 2
                    method = 'Unique measured >=60ms quiet gap near touching ASR word intervals; experimental listening cut'
                else:
                    pauses = []
                    assert gap <= 2, f'ASR_BOUNDARY_REQUIRES_HUMAN_TIMING_REVIEW: {case}/{trial["scene"]}/{gap}'
                    cut = (previous['end_seconds'] + first['start_seconds']) / 2
                    method = 'Two unique opening tokens matched to real provider-native word intervals; midpoint of the preceding gap'
            candidate = whole_audio[round(cut * 48000):]
            unit = next(u for u in base_meta['units'] if u['scene'] == trial['scene'])
            original_start = max(unit['start_seconds'], unit['activity_start_seconds'] - .03)
            original = base_audio[round(original_start * 48000):round(unit['end_seconds'] * 48000)]
            # Match duration and volume for listening. Preserve the attack of both
            # starts; only the final 10ms of a short excerpt gets the same fade.
            size = min(3 * 48000, len(original), len(candidate))
            excerpts, gains = [], []
            for audio in (original[:size], candidate[:size]):
                gain = min(.14 / max(float(np.sqrt(np.mean(audio ** 2))), 1e-9), .85 / max(float(np.abs(audio).max()), 1e-9))
                adjusted = audio.copy() * gain
                adjusted[-480:] *= np.linspace(1, 0, 480)
                excerpts.append(adjusted); gains.append(gain)
            folder = EVIDENCE / f'case-{case:02}' / f'scene-{trial["scene"]:02}'
            folder.mkdir(parents=True, exist_ok=True)
            for name in ('trial.json', 'results.json', 'transcript.json'):
                copy_exact(source.with_name(name), folder / name)
            write_wave(folder / 'A-current-onset.wav', excerpts[0])
            write_wave(folder / 'B-warm-onset.wav', excerpts[1])
            write_wave(folder / 'B-target-trial.wav', candidate)
            boundary = {'method': method,
                        'provider_native_timestamps_are_approximate': True,
                        'previous_word': previous, 'first_target_word': first, 'gap_seconds': gap,
                        'removed_samples': round(cut * 48000), 'cut_seconds': cut,
                        'matched_opening_tokens': expected_tokens[:2], 'input_wave_sha256': file_sha(full),
                        'removed_context': trial['approved_previous_sentence_context'],
                        'full_target_word_accuracy_confirmed': False, 'human_audio_accepted': False}
            if grouped:
                boundary.update(asr_group_spans_context_and_target=True, measured_quiet_gaps=pauses)
            elif pauses:
                boundary.update(asr_word_intervals_touch=True, measured_quiet_gaps=pauses)
            preserve_json(folder / 'boundary.json', boundary)
            target_asr = ' '.join(t for t, _ in expanded[flat:])
            ratio = difflib.SequenceMatcher(a=expected_tokens, b=tokens(target_asr), autojunk=False).ratio()
            provider_dir = source.parent / 'provider'
            original_provider = read(provider_dir / 'provider-completed.json')['payload']
            assert digest(original_provider) == record['transcript']['provenance']['raw_response_sha256']
            provenance = {'upload_requests': int((provider_dir / 'upload.intent.json').exists()),
                          'transcript_create_requests': int((provider_dir / 'create-transcript.intent.json').exists()),
                          'observe_requests': len(list(provider_dir.glob('observe-*.intent.json'))),
                          'model': record['transcript']['provenance']['model'], 'language': record['transcript']['language'],
                          'raw_response_sha256': record['transcript']['provenance']['raw_response_sha256'],
                          'raw_response_path': str(provider_dir / 'provider-completed.json'),
                          'transcript_id': record['transcript']['provenance']['transcript_id'],
                          'new_provider_added': False, 'automatic_paid_replay': False, 'fixture_provider': False,
                          'billing_receipt_available': original_provider.get('credit_debit') is not None}
            preserve_json(folder / 'provider-evidence.json', provenance)
            a_start = offset / 48000; montage += [excerpts[0], np.zeros(24000)]
            offset += size + 24000
            b_start = offset / 48000; montage += [excerpts[1], np.zeros(48000)]
            offset += size + 48000
            pairs.append({'case': case, 'scene': trial['scene'], 'owner_phrase': trial['owner_phrase'],
                          'A_start_seconds': round(a_start, 3), 'B_start_seconds': round(b_start, 3),
                          'excerpt_duration_seconds': size / 48000, 'A_volume_gain': gains[0], 'B_volume_gain': gains[1],
                          'A_source_voice_sha256': file_sha(base / 'voice.wav'), 'B_source_voice_sha256': file_sha(full),
                          'A_original_start_seconds': original_start, 'B_context_cut_seconds': cut,
                          'A_wave_sha256': file_sha(folder / 'A-current-onset.wav'), 'B_wave_sha256': file_sha(folder / 'B-warm-onset.wav'),
                          'B_target_wave_sha256': file_sha(folder / 'B-target-trial.wav'),
                          'expected_target_text': trial['target_text'], 'actual_target_asr_text': target_asr,
                          'raw_text_token_similarity_diagnostic': round(ratio, 4),
                          'asr_disagreement_is_not_proof_of_an_audio_word_error': True,
                          'A_first_second': diagnostics.pitch_measurements(excerpts[0][:48000], 48000),
                          'B_first_second': diagnostics.pitch_measurements(excerpts[1][:48000], 48000),
                          'human_audio_quality_accepted': False, 'production_audio_replaced': False})
    assert len(pairs) == 8
    output = EVIDENCE / 'eight-onsets-A-then-B.wav'
    write_wave(output, np.concatenate(montage))
    preserve_json(EVIDENCE / 'onset-review-manifest.json', {'classification': 'LOCAL_AUDIO_TRIAL_OWNER_LISTENING_REQUIRED',
                  'owner_feedback_sha256': file_sha(EVIDENCE / 'owner-onset-feedback.json'),
                  'audio': str(output), 'audio_sha256': file_sha(output), 'duration_seconds': offset / 48000,
                  'order': 'For each named onset: A current, 0.5s gap, B warm context, 1s gap',
                  'processing': 'Gain only to RMS 0.14 with peak limit 0.85; same final 10ms fade; no attack fade, pitch or speed change',
                  'pairs': pairs, 'native_video_jobs_created': 0, 'human_accepted_final_videos': 0,
                  'CONTENT_INTELLIGENCE_READY': 'NO'})
    rows = ['# Nghe so sánh tám chỗ lỗi đầu câu', '',
            'Mỗi cặp phát **A: giọng hiện tại**, nghỉ nửa giây, rồi **B: mẫu đọc có câu trước làm ngữ cảnh**. Nghỉ một giây giữa hai cặp.', '',
            f'![Nghe tám cặp A rồi B]({output.as_posix()})', '',
            '| Ca | Chỗ bạn báo lỗi | A bắt đầu | B bắt đầu |', '|---|---|---:|---:|']
    rows += [f'| {p["case"]:02} | {p["owner_phrase"]} | {p["A_start_seconds"]:.1f}s | {p["B_start_seconds"]:.1f}s |' for p in pairs]
    rows += ['', 'Các mẫu B là thử nghiệm giọng, chưa thay âm thanh của MP4. Câu làm ngữ cảnh được tách theo mốc AssemblyAI và khoảng nghỉ đo trên âm thanh; khi ASR gộp tên với đầu câu, cách cắt vẫn cần bạn nghe kiểm tra.', '',
             'Bản nhận diện có một số từ khác lời duyệt, gồm CTA “Để lại câu hỏi”, một số tên quốc tế và ca 04 “tách/dữ kiện”. Đây là bất đồng của ASR với lời duyệt, chưa chứng minh giọng thực sự đọc sai. Chưa có word-accuracy hoặc naturalness PASS.', '',
             '01/02/04 đã lưu phản hồi cần sửa gắn đúng ba MP4 hiện tại. 06/08 vẫn PENDING; không suy diễn được duyệt. Phase 8 và mọi video cũ giữ nguyên.', '',
             'Nếu B cải thiện đầu câu khi bạn nghe, bước tiếp theo là kiểm tra đủ lời đọc, cách cắt và thử tiếp trên cả năm ca trước khi tạo MP4 mới.', '',
             'CONTENT_INTELLIGENCE_READY = NO', '']
    bundle = EVIDENCE / 'onset-listening-bundle.md'
    bundle.write_text('\n'.join(rows), encoding='utf-8')
    print(json.dumps({'real_pairs': len(pairs), 'audio_duration_seconds': offset / 48000,
                      'audio_sha256': file_sha(output), 'human_audio_quality_accepted': False}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('action', choices=('collect', 'build'))
    args = parser.parse_args(); collect() if args.action == 'collect' else build()
