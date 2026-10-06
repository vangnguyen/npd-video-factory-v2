"""Inspect the real warm-scene MP4 audio, reviewed-source reuse and HTTP guards."""
import hashlib
import http.cookiejar
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request
import wave

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json
from services.windows_native.pipeline import Config, REPO
from services.windows_native.store import Store

ROOT = REPO / 'evidence/post-mvp-roadmap/phase-9/9k/audio-repair-03'
PREVIOUS = ROOT.parent / 'audio-repair-02'


def read(path): return json.loads(path.read_bytes())


def pcm(path):
    with wave.open(str(path), 'rb') as source:
        assert (source.getnchannels(), source.getsampwidth(), source.getframerate()) == (1, 2, 48000)
        return np.frombuffer(source.readframes(source.getnframes()), dtype='<i2').copy()


def main():
    config = Config(); store = Store(config.data_root); jobs = read(ROOT / 'jobs.json')['cases']
    reviewed = {(c['case'],c['scene']):c for c in read(PREVIOUS / 'onset-review-manifest.json')['pairs']}
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    with opener.open('http://127.0.0.1:8026/api/session', timeout=10) as response: response.read()
    results=[]; reused=[]
    for item in jobs:
        job=store.get_job(item['job_id']); assert job['status']=='succeeded' and job['final_review'] is None
        out=config.data_root/'jobs'/job['id']; meta=read(out/'voice.json'); raw=pcm(out/'voice.wav')
        work=Path('C:/NPD-Video-Factory/post-mvp-validation/phase9k-warm-B-03')/job['id']; work.mkdir(parents=True,exist_ok=True)
        decoded_path=work/'mp4-decoded.wav'
        decode_receipt=work/'mp4-decoded-source.json'
        final_sha256=file_sha(out/'final.mp4')
        if not decoded_path.exists():
            subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-loglevel','error','-nostdin','-n',
                '-i',str(out/'final.mp4'),'-map','0:a:0','-ac','1','-ar','48000','-c:a','pcm_s16le',str(decoded_path)],
                check=True,capture_output=True,timeout=30)
            write_json(decode_receipt,{'source_MP4_sha256':final_sha256,'decoded_WAV_sha256':file_sha(decoded_path)})
        binding=read(decode_receipt)
        assert binding=={'source_MP4_sha256':final_sha256,'decoded_WAV_sha256':file_sha(decoded_path)},'Decoded cache is not bound to this exact MP4'
        decoded=pcm(decoded_path).astype(np.float64)/32768
        part=decoded[52800:52800+len(raw)]
        assert len(part)==len(raw)
        correlation=float(np.corrcoef(raw.astype(np.float64)/32768,part)[0,1]); assert correlation>.98
        assert np.isfinite(decoded).all() and np.abs(decoded).max()<.99
        units=[]
        assert len(meta['units'])==len(meta['sources'])==5
        for unit,source in zip(meta['units'],meta['sources']):
            source_pcm=pcm(Path(source['source_wave_path']))
            assert file_sha(source['source_wave_path'])==source['source_wave_sha256']
            cut=source['boundary']['removed_samples']
            begin,end=round(unit['start_seconds']*48000),round(unit['end_seconds']*48000)
            assert np.array_equal(raw[begin:end],source_pcm[cut:]),'Trimmed scene PCM differs from its actual source'
            units.append({'scene':unit['scene'],'source_pcm_exact':True,'cut_samples':cut,'new_unit_start_seconds':unit['start_seconds']})
            pair=reviewed.get((item['case'],unit['scene']))
            if pair:
                assert source['source_wave_sha256']==pair['B_source_voice_sha256']
                assert abs(cut/48000-pair['B_context_cut_seconds'])<=1/48000
                target=pcm(PREVIOUS/f"case-{item['case']:02}/scene-{unit['scene']:02}/B-target-trial.wav")
                actual=raw[begin:end]
                assert len(target)==len(actual)
                quantization_difference=int(np.abs(actual.astype(np.int32)-target.astype(np.int32)).max())
                assert quantization_difference<=1
                reused.append({'case':item['case'],'scene':unit['scene'],'exact_reviewed_source_and_cut':True,
                               'max_PCM_difference_from_reviewed_target_LSB':quantization_difference,
                               'explanation':'Reviewed trial encoded float PCM a second time; production keeps original source PCM exact',
                               'owner_approved_onset_sample_sha256':pair['B_wave_sha256']})
        url='http://127.0.0.1:8026/api/jobs/'+job['id']
        with opener.open(url+'/video',timeout=20) as response: served=hashlib.sha256(response.read()).hexdigest()
        assert served==file_sha(out/'final.mp4')
        request=urllib.request.Request(url+'/video',headers={'Range':'bytes=100-199'})
        with opener.open(request,timeout=10) as response: ranged=response.read(); code=response.status
        with (out/'final.mp4').open('rb') as video: video.seek(100); expected=video.read(100)
        assert code==206 and ranged==expected
        try:
            opener.open(url+'/final',timeout=10)
            raise AssertionError('Unaccepted final download was unlocked')
        except urllib.error.HTTPError as error:
            denied=json.loads(error.read()); assert error.code==409 and 'HUMAN_FINAL_VIDEO_APPROVAL_REQUIRED' in json.dumps(denied)
        results.append({'case':item['case'],'job_id':job['id'],'final_sha256':served,'units':units,
                        'wav_AAC_correlation':correlation,'decoded_peak':float(np.abs(decoded).max()),
                        'decoded_cache_binding':binding,
                        'preview_byte_exact':True,'range_seek':'PASS','final_approval_guard':'PASS',
                        'full_new_audio_quality':'OWNER_LISTENING_PENDING','human_final_video_approved':False})
        print(json.dumps({'case':item['case'],'actual_MP4_checked':True,'wav_AAC_correlation':correlation}),flush=True)
    assert len(results)==5 and len(reused)==8
    write_json(ROOT/'audio-and-preview-checks.json',{'classification':'ACTUAL_PCM_CODEC_PREVIEW_AND_HUMAN_GUARD_VERIFICATION',
        'cases':results,'reviewed_B_sources_reused':reused,'actual_new_MP4s':5,'owner_B_onset_samples_accepted':8,
        'human_full_new_audio_accepted':0,'human_final_video_approvals':0,'CONTENT_INTELLIGENCE_READY':'NO'})


if __name__=='__main__': main()
