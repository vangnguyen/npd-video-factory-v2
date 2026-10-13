"""Fixed local CPU speech profile; no provider credentials or database imports."""
import hashlib,json
from pathlib import Path

MODEL_MANIFEST=Path(__file__).resolve().parents[3]/'packages/contracts/local-asr-model.v1.json'

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()

def digest(value):return hashlib.sha256(canonical(value)).hexdigest()

def model_manifest():return json.loads(MODEL_MANIFEST.read_bytes())

def profile(language):
    if language not in ('vi','en','auto'):raise ValueError('LOCAL_ASR_LANGUAGE_INVALID')
    model=model_manifest()
    return {'provider':'faster-whisper','model':model['model'],'model_revision':model['revision'],
        'model_manifest_sha256':digest(model),'language':language,'device':'cpu','compute_type':'int8',
        'word_timestamps':True,'vad_filter':False,'beam_size':5,'temperature':0.0,
        'condition_on_previous_text':False,'initial_prompt':None,'version':'local-asr-cpu.v1'}

def validate_profile(value):
    if not isinstance(value,dict) or value!=profile(value.get('language')):raise ValueError('LOCAL_ASR_PROFILE_CHANGED')
    return value
