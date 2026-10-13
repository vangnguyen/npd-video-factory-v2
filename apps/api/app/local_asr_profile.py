"""Fixed local CPU speech profile; no provider credentials or database imports."""
import hashlib,json
from pathlib import Path

MODEL_MANIFEST=Path(__file__).resolve().parents[3]/'packages/contracts/local-asr-model.v1.json'
SMALL_MODEL_MANIFEST=MODEL_MANIFEST.with_name('local-asr-small-model.v1.json')
PHO_MODEL_MANIFEST=MODEL_MANIFEST.with_name('local-asr-phowhisper-model.v1.json')

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def model_manifest(model_key='base'):
    files={'base':MODEL_MANIFEST,'small':SMALL_MODEL_MANIFEST,'phowhisper-small':PHO_MODEL_MANIFEST}
    if model_key not in files:raise ValueError('LOCAL_ASR_MODEL_NOT_APPROVED')
    return json.loads(files[model_key].read_bytes())

def profile(language,model_key='base'):
    if language not in ('vi','en','auto'):raise ValueError('LOCAL_ASR_LANGUAGE_INVALID')
    if model_key=='phowhisper-small' and language!='vi':raise ValueError('LOCAL_ASR_MODEL_LANGUAGE_UNSUPPORTED')
    model=model_manifest(model_key)
    value={'provider':'faster-whisper','model':model['model'],'model_revision':model['revision'],
        'model_manifest_sha256':digest(model),'language':language,'device':'cpu','compute_type':'int8',
        'word_timestamps':True,'vad_filter':False,'beam_size':5,'temperature':0.0,
        'condition_on_previous_text':False,'initial_prompt':None,'version':'local-asr-cpu.v1'}
    if model_key!='base':value.update(model_key=model_key,version='local-asr-cpu.v2')
    if model_key=='phowhisper-small':value.update(vad_filter=True,without_timestamps=True,
        vad_parameters={'threshold':0.5,'min_speech_duration_ms':250,'min_silence_duration_ms':500,'speech_pad_ms':200})
    return value

def validate_profile(value):
    if not isinstance(value,dict) or value!=profile(value.get('language'),value.get('model_key','base')):raise ValueError('LOCAL_ASR_PROFILE_CHANGED')
    return value
