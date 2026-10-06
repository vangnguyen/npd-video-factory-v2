"""Measure actual repaired audio and AAC transport; never replace Owner listening."""
from pathlib import Path
import argparse
import hashlib
import http.cookiejar
import importlib.util
import json
import subprocess
import sys
import urllib.error
import urllib.request
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json
from services.windows_native.pipeline import Config
from services.windows_native.store import Store

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-01'
spec = importlib.util.spec_from_file_location('diagnostics', REPO / 'scripts/phase9k-audio-diagnostics.py')
diagnostics = importlib.util.module_from_spec(spec); spec.loader.exec_module(diagnostics)


def pcm(path):
    with wave.open(str(path), 'rb') as source:
        assert source.getnchannels() == 1 and source.getsampwidth() == 2 and source.getframerate() == 48000
        return np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').astype(np.float64) / 32768


def check(case, config, opener):
    job = Store(config.data_root).get_job(case['job_id'])
    assert job['status'] == 'succeeded' and job['final_review'] is None
    out = config.data_root / 'jobs' / job['id']
    work = Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-audio-repair-20261006') / f"decoded-case-{case['case']:02}"
    work.mkdir(exist_ok=True)
    dest = work / 'mp4-decoded.wav'
    if not dest.exists():
        subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-hide_banner', '-loglevel', 'error', '-nostdin', '-n',
                        '-i', str(out / 'final.mp4'), '-map', '0:a:0', '-ac', '1', '-ar', '48000', '-c:a', 'pcm_s16le', str(dest)],
                       check=True, capture_output=True, timeout=30)
    raw = pcm(out / 'voice.wav'); decoded = pcm(dest)
    start = round(1.1 * 48000)
    assert len(decoded) >= start + len(raw)
    portion = decoded[start:start + len(raw)]
    correlation = float(np.corrcoef(raw, portion)[0, 1])
    assert correlation > .98, 'MP4 audio is not the same waveform at the existing 1.1-second offset'
    assert np.isfinite(decoded).all() and np.max(np.abs(decoded)) < .99
    meta = json.loads((out / 'voice.json').read_bytes())
    seams = []
    for unit in meta['units'][1:]:
        n = round(unit['start_seconds'] * 48000)
        seams.append({'scene': unit['scene'], 'seconds': unit['start_seconds'],
                      'sample_jump': float(abs(raw[n] - raw[n - 1])),
                      'peak_5ms_around_join': float(np.max(np.abs(raw[max(0, n - 240):n + 240])))})
    final_sha = file_sha(out / 'final.mp4')
    url = 'http://127.0.0.1:8026/api/jobs/' + job['id']
    with opener.open(url + '/video', timeout=20) as response:
        served_sha = hashlib.sha256(response.read()).hexdigest()
    assert served_sha == final_sha
    req = urllib.request.Request(url + '/video', headers={'Range': 'bytes=100-199'})
    with opener.open(req, timeout=20) as response:
        ranged = response.read(); code = response.status
    with (out / 'final.mp4').open('rb') as source: source.seek(100); expected = source.read(100)
    assert code == 206 and ranged == expected
    try:
        opener.open(url + '/final', timeout=10)
        raise AssertionError('Final download was unguarded')
    except urllib.error.HTTPError as error:
        denied = json.loads(error.read())
        assert error.code == 409 and 'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED' in json.dumps(denied)
    return {'case': case['case'], 'job_id': job['id'], 'final_sha256': final_sha,
            'raw_voice': diagnostics.inspect(out / 'voice.wav', out / 'voice.json'),
            'decoded_mp4_voice': diagnostics.pitch_measurements(portion, 48000),
            'decoded_mp4_peak': float(np.max(np.abs(decoded))), 'decoded_pcm_saturation_samples': int(np.count_nonzero(np.abs(decoded) >= 32767 / 32768)),
            'wav_aac_correlation_at_1_1_second_offset': correlation, 'decoded_audio_sha256': file_sha(dest),
            'scene_join_measurements': seams, 'preview_byte_exact': True, 'range_seek': 'PASS', 'final_approval_guard': 'PASS',
            'subjective_roughness_resolved': 'UNCONFIRMED_REQUIRES_OWNER_LISTENING', 'human_audio_accepted': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--ready-only', action='store_true')
    args = parser.parse_args(); config = Config(); jobs = json.loads((ROOT / 'jobs.json').read_bytes())['cases']
    store = Store(config.data_root)
    ready = [case for case in jobs if store.get_job(case['job_id'])['status'] == 'succeeded']
    if not args.ready_only: assert len(ready) == 5, 'All five actual jobs must succeed before final verification'
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open('http://127.0.0.1:8026/api/session', timeout=10) as response: response.read()
    results = []
    for case in ready:
        item = check(case, config, opener); results.append(item)
        print(json.dumps({'case': item['case'], 'wav_aac_correlation': item['wav_aac_correlation_at_1_1_second_offset'],
                          'raw_unit_median_range_semitones': item['raw_voice']['unit_median_range_semitones'],
                          'raw_unit_f0_hz': [u['median_f0_hz'] for u in item['raw_voice']['units']],
                          'decoded_peak': item['decoded_mp4_peak'], 'human_accepted': False}), flush=True)
    write_json(ROOT / ('partial-audio-checks.json' if args.ready_only else 'audio-and-preview-checks.json'),
               {'scope': 'Signal/codec/transport verification only, not listening quality acceptance',
                'cases': results, 'actual_videos_checked': len(results), 'human_audio_accepted': 0, 'CONTENT_INTELLIGENCE_READY': 'NO'})
