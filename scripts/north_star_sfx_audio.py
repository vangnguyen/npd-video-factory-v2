"""Independent decoded tone placement check; fixture evidence, never speech/UAT."""
import argparse,hashlib,json,subprocess
from pathlib import Path
import numpy as np
from services.windows_native.pipeline import Config

def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True);parser.add_argument('--evidence-dir',type=Path,required=True);args=parser.parse_args()
    bundle=args.bundle.resolve();out=args.evidence_dir.resolve();repo=Path(__file__).resolve().parents[1]
    if out.exists() or out==repo or repo in out.parents or out==bundle or bundle in out.parents:raise ValueError('Fresh external evidence directory required')
    proof=json.loads((bundle/'sfx-controller.json').read_bytes());project=json.loads((bundle/'project.json').read_bytes())
    if not proof['fixture_human'] or proof['provider_calls']!=0 or proof['owner_UAT']:raise ValueError('Only explicit owned SFX fixtures supported')
    snapshot=project['document']['canonical_timeline']['snapshot'];track=next(t for t in snapshot['tracks'] if t['track_id']==proof['saved']['mutation']['track_id'])
    if track['kind']!='sfx' or track['type']!='audio' or track['disabled'] or track['muted'] or len(track['clips'])!=1:raise ValueError('Active single SFX fixture required')
    clip=track['clips'][0]
    if clip['disabled'] or clip['kind']!='sfx' or abs(clip['timeline_start']-.9)>1e-6 or abs(clip['duration']-.5)>1e-6:raise ValueError('Expected saved SFX window differs')
    source=bundle/'assets'/clip['metadata']['native_asset_id']
    if sha(source)!=proof['saved']['mutation']['asset_sha256']:raise ValueError('Retained physical SFX source differs')
    mix=bundle/('narrated-mix.wav' if proof['initial']['timeline_mode']=='narrated' else 'audio-mix.wav')
    ffmpeg=str(Config().ffmpeg_bin/'ffmpeg.exe');rate=48000
    def decode(path):
        result=subprocess.run([ffmpeg,'-v','error','-nostdin','-i',str(path),'-map','0:a:0','-ac','1','-ar',str(rate),'-f','f32le','pipe:1'],capture_output=True,check=True,timeout=30)
        values=np.frombuffer(result.stdout,dtype='<f4').astype('float64')
        if len(values)<rate*.8 or not np.isfinite(values).all():raise ValueError('Decoded audio unavailable')
        return values
    def band_rms(samples,start,end,frequency=3000):
        signal=samples[round(start*rate):round(end*rate)];window=np.hanning(len(signal))
        if len(signal)<rate*.1:raise ValueError('Audio window too short')
        spectrum=np.fft.rfft(signal*window);freq=np.fft.rfftfreq(len(signal),1/rate);band=(freq>=frequency-70)&(freq<=frequency+70)
        return float(np.sqrt(2*np.sum(np.abs(spectrum[band])**2)/(len(signal)*np.sum(window**2))))
    measurements={};files={}
    for name,path in [('PCM',mix),('preview',bundle/'preview.mp4'),('final',bundle/'final.mp4')]:
        samples=decode(path);windows={'before':(.2,.6),'inside':(1.05,1.25),'after':(1.65,2.1)}
        levels={label:band_rms(samples,*interval) for label,interval in windows.items()}
        if levels['inside']<.005 or levels['inside']<=max(levels['before'],levels['after'])*10+.0001:raise AssertionError(name+' has no independently measured SFX in its saved window')
        measurements[name]={'frequency_hz':3000,'windows_seconds':windows,'band_RMS':levels,'saved_SFX_window':[clip['timeline_start'],clip['timeline_start']+clip['duration']],
            'inside_to_outside_ratio':levels['inside']/max(levels['before'],levels['after'],1e-12),'decoded_seconds':len(samples)/rate}
        files[name]={'path':str(path),'sha256':sha(path),'bytes':path.stat().st_size}
    source_level=band_rms(decode(source),.2,.4)
    if source_level<.05:raise AssertionError('Synthetic uploaded source tone is not present')
    out.mkdir(parents=True)
    receipt={'schema_version':'owned-SFX-decoded-audio-proof-v1','method':'independent FFmpeg mono float32 decode, Hann FFT energy in 2930-3070Hz band; saved placement compared with before/after controls',
        'measurements':measurements,'files':files,'physical_source':{'path':str(source),'sha256':sha(source),'3000Hz_band_RMS':source_level},
        'actual_uploaded_SFX_detected_in_PCM_preview_final':True,'synthetic_tone_not_speech':True,'fake_DOM':True,'browser_rendered':False,'owner_UAT':False,
        'provider_calls':0,'paid_calls':0,'complete_Mode_A_B_or_A_B_C_acceptance':False,'whole_mix_perceptual_or_speech_quality_accepted':False}
    (out/'evidence.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(json.dumps({'status':'PASS','bundle':str(bundle),'PCM_preview_final_tone_placement':True,'receipt':str(out/'evidence.json')}))

if __name__=='__main__':main()
