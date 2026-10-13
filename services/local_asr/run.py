"""Offline subprocess ASR. stdin/output are bounded JSON, never arbitrary code."""
import hashlib,importlib.metadata,json,os,socket,sys,wave
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'apps/api'))
from app.local_asr_profile import validate_profile,model_manifest,digest
from app.local_asr_runtime import plain,file_sha

def forbidden(*_,**__):raise RuntimeError('LOCAL_ASR_NETWORK_FORBIDDEN')

def main():
    raw=sys.stdin.buffer.read(32769)
    if len(raw)>32768:raise ValueError('LOCAL_ASR_INPUT_LIMIT')
    request=json.loads(raw)
    if set(request)!={'audio','audio_sha256','model_root','profile','cpu_threads'}:
        raise ValueError('LOCAL_ASR_INPUT_INVALID')
    profile=validate_profile(request['profile'])
    if type(request['cpu_threads']) is not int or not 1<=request['cpu_threads']<=4:
        raise ValueError('LOCAL_ASR_THREADS_INVALID')
    audio=plain(request['audio']);root=plain(request['model_root'])
    if file_sha(audio)!=request['audio_sha256']:raise ValueError('LOCAL_ASR_AUDIO_CHANGED')
    for name,proof in model_manifest()['files'].items():
        item=plain(root/name)
        if item.stat().st_size!=proof['bytes'] or file_sha(item)!=proof['sha256']:raise ValueError('LOCAL_ASR_MODEL_CHANGED')
    if importlib.metadata.version('faster-whisper')!='1.2.1':raise ValueError('LOCAL_ASR_LIBRARY_CHANGED')
    with wave.open(str(audio),'rb') as source:
        if source.getnchannels()!=1 or source.getsampwidth()!=2 or source.getframerate()!=16000:
            raise ValueError('LOCAL_ASR_PCM_REQUIRED')
        count=source.getnframes()
        if not 0<count<=16000*1800:raise ValueError('LOCAL_ASR_AUDIO_DURATION_LIMIT')
        samples=source.readframes(count)
        if len(samples)!=count*2:raise ValueError('LOCAL_ASR_PCM_TRUNCATED')
    # A local-files-only loader plus a network guard: no model auto-download/upload.
    os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1')
    socket.socket.connect=forbidden;socket.create_connection=forbidden
    import numpy as np
    from faster_whisper import WhisperModel
    model=WhisperModel(str(root),device='cpu',compute_type='int8',cpu_threads=request['cpu_threads'],
        num_workers=1,local_files_only=True)
    sequence,info=model.transcribe(np.frombuffer(samples,dtype='<i2').astype(np.float32)/32768.,
        language=None if profile['language']=='auto' else profile['language'],task='transcribe',
        word_timestamps=True,vad_filter=False,beam_size=5,temperature=0.,condition_on_previous_text=False,
        initial_prompt=None)
    segments=[];words=0
    for item in sequence:
        chunk={'start_seconds':float(item.start),'end_seconds':float(item.end),'text':item.text.strip(),
            'speaker':None,'confidence':None,'words':[]}
        for word in item.words or []:
            words+=1
            if words>10000:raise ValueError('LOCAL_ASR_WORD_LIMIT')
            chunk['words'].append({'start_seconds':float(word.start),'end_seconds':float(word.end),
                'text':word.word.strip(),'confidence':float(word.probability),
                'timing_semantics':'positive_interval' if word.end>word.start else 'provider_boundary_point'})
        if chunk['text']:segments.append(chunk)
    if file_sha(audio)!=request['audio_sha256']:raise ValueError('LOCAL_ASR_AUDIO_CHANGED')
    result={'version':'local-asr-result.v1','profile_sha256':digest(profile),'source_sha256':request['audio_sha256'],
        'language':info.language,'language_confidence':float(info.language_probability) if profile['language']=='auto' else None,
        'language_probability_reported':float(info.language_probability),
        'duration_seconds':count/16000.,'segments':segments,'model_revision':profile['model_revision'],
        'library':'faster-whisper','library_version':'1.2.1','device':'cpu','compute_type':'int8',
        'external_calls':0,'paid_calls':0,'model_inferences':1,'vad_filter':False}
    encoded=json.dumps(result,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()
    if len(encoded)>4*1024*1024:raise ValueError('LOCAL_ASR_OUTPUT_LIMIT')
    sys.stdout.buffer.write(encoded)

if __name__=='__main__':
    try:main()
    except Exception:
        sys.stderr.write('LOCAL_ASR_EXECUTION_FAILED\n');sys.exit(1)
