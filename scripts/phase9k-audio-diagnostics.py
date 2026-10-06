"""Reproducible signal measurements, not a substitute for human listening."""
from pathlib import Path
import argparse
import json
import sys
import wave

import numpy as np
import soxr

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services.windows_native.contracts import file_sha, write_json


def pitch_measurements(audio, rate):
    """YIN difference/CMNDF estimates; preserve Vietnamese tonal variation."""
    audio=soxr.resample(np.asarray(audio,dtype=np.float64),rate,8000,quality='HQ')
    length,step=400,80
    if len(audio)<length: return {'voiced_frames':0,'median_f0_hz':None}
    frames=np.lib.stride_tricks.sliding_window_view(audio,length)[::step].copy()
    frames-=frames.mean(axis=1,keepdims=True)
    rms=np.sqrt(np.mean(frames**2,axis=1))
    spectrum=np.fft.rfft(frames,n=1024,axis=1)
    autocorrelation=np.fft.irfft(spectrum*spectrum.conj(),n=1024,axis=1)[:,:length]
    sums=np.concatenate([np.zeros((len(frames),1)),np.cumsum(frames**2,axis=1)],axis=1)
    lags=np.arange(1,146)
    difference=sums[:,length-lags]+sums[:,length,None]-sums[:,lags]-2*autocorrelation[:,lags]
    cmnd=np.maximum(difference,0)*lags/np.maximum(np.cumsum(np.maximum(difference,0),axis=1),1e-12)
    pitches=[];confidences=[]
    for row,level in zip(cmnd,rms):
        if level<.005: continue
        minima=[lag for lag in range(18,144) if row[lag-1]<=row[lag-2] and row[lag-1]<row[lag] and row[lag-1]<.22]
        if not minima: continue
        lag=minima[0]
        left,center,right=row[lag-2:lag+1]
        denominator=left-2*center+right
        adjustment=.5*(left-right)/denominator if abs(denominator)>1e-12 else 0
        pitches.append(8000/(lag+float(np.clip(adjustment,-.5,.5))))
        confidences.append(1-center)
    if not pitches: return {'voiced_frames':0,'median_f0_hz':None}
    pitches=np.asarray(pitches)
    return {'voiced_frames':len(pitches),'median_f0_hz':round(float(np.median(pitches)),2),
        'p10_f0_hz':round(float(np.quantile(pitches,.1)),2),'p90_f0_hz':round(float(np.quantile(pitches,.9)),2),
        'fraction_below_130hz':round(float(np.mean(pitches<130)),4),'mean_periodicity':round(float(np.mean(confidences)),4)}


def inspect(wav_path,meta_path):
    meta=json.loads(Path(meta_path).read_bytes())
    with wave.open(str(wav_path),'rb') as source:
        assert source.getnchannels()==1 and source.getsampwidth()==2
        rate=source.getframerate();pcm=np.frombuffer(source.readframes(source.getnframes()),dtype='<i2')
    audio=pcm.astype(np.float64)/32768
    units=[]
    for unit in meta['units']:
        start,end=(unit[k] for k in ['activity_start_seconds','activity_end_seconds'])
        portion=audio[round(start*rate):round(end*rate)]
        units.append({'index':unit['index'],'scene':unit['scene'],'text':unit['text'],'start_seconds':start,
            'end_seconds':end,**pitch_measurements(portion,rate)})
    medians=[u['median_f0_hz'] for u in units if u['median_f0_hz']]
    return {'voice_sha256':file_sha(wav_path),'sample_rate':rate,'duration_seconds':len(audio)/rate,
        'peak':float(np.max(np.abs(audio))),'rms':float(np.sqrt(np.mean(audio**2))),
        'pcm_saturation_samples':int(np.count_nonzero((pcm==32767)|(pcm==-32767))),
        'unit_median_range_semitones':round(float(12*np.log2(max(medians)/min(medians))),3) if medians else None,
        'units':units,'method':'50ms YIN CMNDF windows / 10ms step / 8kHz analysis; estimates can have octave errors',
        'human_audio_quality_accepted':False}


def baseline():
    root=Path(__file__).resolve().parents[1]/'evidence/post-mvp-roadmap/phase-9/9k'
    manifest=json.loads((root/'final-video-review-manifest.json').read_bytes())
    results=[]
    for case in manifest['cases']:
        native=Path(case['final_mp4']).parent
        result={'case':case['case'],'job_id':case['job_id'],**inspect(native/'voice.wav',native/'voice.json')}
        results.append(result)
        print(json.dumps({'case':case['case'],'units':len(result['units']),'median_f0_hz':[u['median_f0_hz'] for u in result['units']],
            'median_range_semitones':result['unit_median_range_semitones'],'pcm_saturation_samples':result['pcm_saturation_samples']}),flush=True)
    output=root/'audio-repair-01';output.mkdir(exist_ok=True)
    write_json(output/'original-audio-diagnostics.json',{'scope':'Five actual original production voices reported by Owner',
        'owner_feedback':'Giọng nói giữa các câu không giữ được độ cao âm, bị rè, âm giọng bị xuống thấp',
        'owner_scope_reply':'Nhiều/cả 5 video — kiểm tra toàn bộ','cases':results,'human_acceptance':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['baseline'])
    parser.parse_args();baseline()
