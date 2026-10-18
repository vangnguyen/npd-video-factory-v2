"""Pinned official preset adapter. Inference runs offline in an isolated child process."""
import json,math,os,re,subprocess,sys,time,wave
from pathlib import Path
from .backup import guard
from .contracts import MODEL,PROFILE_SHA,WorkflowError,digest,file_sha
from .hardening import durable_json

PROVIDER='vieneu-local'
SCHEMA='native-dialogue-vieneu-preset.v1'

def presets(config):
    from .pipeline import profile
    locked=profile();source=guard(config.sdk_source/'src/vieneu/assets/voices_v3_turbo.json',exists=True)
    if source.stat().st_size>4*1024*1024 or file_sha(source)!=locked['rights']['preset_asset_sha256']:raise WorkflowError('DRAMA_VIENEU_PRESET_MANIFEST_CHANGED')
    try:
        values=json.loads(source.read_bytes())['presets']
        if not isinstance(values,dict) or not values or any(not isinstance(k,str) or not isinstance(v,dict) or not {'speaker_emb','codes'}<=set(v) for k,v in values.items()):raise ValueError()
    except (KeyError,ValueError,TypeError):raise WorkflowError('DRAMA_VIENEU_PRESET_MANIFEST_CHANGED') from None
    return locked,values

def catalog(config):
    try:
        locked,values=presets(config)
        from .voice_presets import licensed_inventory
        try:eligible={v['definition']['provider_voice_id']:v for v in licensed_inventory(config)}
        except (WorkflowError,OSError,ValueError):eligible={}
        return {'provider':PROVIDER,'status':'METADATA_AVAILABLE','model':locked['model'],'model_revision':locked['model_revision'],
            'voices':[{'provider_voice_id':name,'display_name':name,'locale':'vi-VN','source_type':'provider_preset','rights_status':'source_licensed' if name in eligible else 'unknown',
                'metadata':{k:values[name].get(k) for k in ('description','gender','region','style','featured','aliases')},'installed':True,
                'rights_evidence':eligible[name]['evidence'] if name in eligible else None,'human_listening_accepted':False} for name in sorted(values,key=lambda n:(values[n].get('featured') or 999,n))],
            'default_voice':None,'supported_speeds':[1.0],'supported_styles':['neutral'],'custom_reference_cloning':False,
            'requires_runtime_validation':True,'human_voice_uat_complete':False,'inference_calls':0,'paid':False}
    except (OSError,WorkflowError,ValueError):
        return {'provider':PROVIDER,'status':'NOT_CONFIGURED','voices':[],'inference_calls':0,'human_voice_uat_complete':False,'paid':False}

class VieNeuDialoguePresetAdapter:
    paid=False
    evidence_mode='local-real'
    def __init__(self,config):
        self.config=config;self.locked,self.voices=presets(config)
        self.configuration_sha256=digest({'schema_version':SCHEMA,'runtime_profile_sha256':PROFILE_SHA,
            'preset_asset_sha256':self.locked['rights']['preset_asset_sha256'],'adapter_source_sha256':file_sha(Path(__file__))})

    def validate(self,voice,line):
        if voice.get('rights_status') not in ('owner_declared','source_licensed') or not all(voice.get(k) for k in ('license','source_reference','permission_reference')):raise WorkflowError('VOICE_RIGHTS_CONFIRMATION_REQUIRED')
        # Retain immutable historical Owner definitions which incorrectly used the content LLM label.
        accepted_models={self.locked['model']}
        if voice.get('rights_status')=='owner_declared':accepted_models.add(MODEL)
        if (voice.get('provider')!=PROVIDER or voice.get('model') not in accepted_models or voice.get('locale') not in {'vi','vi-VN'}
            or voice.get('source_type')!='provider_preset' or voice.get('provider_voice_id') not in self.voices):raise WorkflowError('DRAMA_VIENEU_VOICE_NOT_CONFIGURED')
        if voice.get('rights_status') not in ('owner_declared','source_licensed') or not all(voice.get(k) for k in ('license','source_reference','permission_reference')):raise WorkflowError('VOICE_RIGHTS_CONFIRMATION_REQUIRED')
        if voice.get('rights_status')=='source_licensed':
            from .voice_presets import verify_definition
            verify_definition(self.config,voice)
        if type(line.get('speed')) not in (int,float) or line['speed']!=1 or line.get('style')!='neutral':raise WorkflowError('DRAMA_VIENEU_DELIVERY_NOT_SUPPORTED')

    def synthesize(self,*,text,voice,line,take,request_key,target):
        self.validate(voice,line);target=guard(Path(target));root=guard(self.config.data_root,exists=True)
        if not isinstance(text,str) or not 1<=len(text.strip())<=4000:raise WorkflowError('DRAMA_VIENEU_REQUEST_INVALID')
        if root not in target.parents or target.name!='line.wav' or target.exists():raise WorkflowError('DRAMA_VIENEU_OUTPUT_SCOPE_INVALID')
        if not isinstance(request_key,str) or not re.fullmatch(r'[a-f0-9]{64}',request_key):raise WorkflowError('DRAMA_VIENEU_REQUEST_INVALID')
        directory=guard(target.parent,exists=True);seed=int(request_key[:8],16)
        durable_json(directory/'runtime-config.json',self.config.dump())
        durable_json(directory/'provider-request.json',{'schema_version':SCHEMA,'configuration_sha256':self.configuration_sha256,
            'voice':voice,'line':{'speed':line['speed'],'style':line['style']},'text':text,'request_key':request_key,'seed':seed})
        interpreter=self.config.runtime_root/'venv/Scripts/python.exe'
        if not interpreter.is_file():raise WorkflowError('DRAMA_VIENEU_RUNTIME_NOT_CONFIGURED')
        repo=Path(__file__).resolve().parents[2]
        env={**os.environ,'PYTHONPATH':os.pathsep.join((str(repo/'apps/api'),str(repo))), 'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
        try:
            result=subprocess.run([str(interpreter),'-X','utf8','-m','services.windows_native.dialogue_vieneu','--directory',str(directory)],
                cwd=repo,env=env,capture_output=True,timeout=300,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        except subprocess.TimeoutExpired:raise WorkflowError('DRAMA_VIENEU_CHILD_TIMEOUT') from None
        # SDK stdout is intentionally neither logged nor returned; it may contain text.
        if result.returncode!=0:raise WorkflowError('DRAMA_VIENEU_CHILD_FAILED')
        receipt=guard(directory/'provider-receipt.json',exists=True)
        if receipt.stat().st_size>16*1024:raise WorkflowError('DRAMA_VIENEU_RECEIPT_INVALID')
        from .dialogue_audio import ProviderReceipt
        try:return ProviderReceipt.model_validate_json(receipt.read_bytes()).model_dump(mode='json')
        except ValueError:raise WorkflowError('DRAMA_VIENEU_RECEIPT_INVALID') from None

def child(directory):
    import socket
    def blocked(*args,**kwargs):raise WorkflowError('LOCAL_TTS_OUTBOUND_NETWORK_BLOCKED')
    socket.socket.connect=blocked
    from .pipeline import Config,verify_runtime
    directory=guard(Path(directory),exists=True);config=Config.load(directory/'runtime-config.json');config.validate_data_root()
    if config.data_root.absolute() not in directory.parents:raise WorkflowError('DRAMA_VIENEU_OUTPUT_SCOPE_INVALID')
    request_file=guard(directory/'provider-request.json',exists=True)
    if request_file.stat().st_size>64*1024:raise WorkflowError('DRAMA_VIENEU_REQUEST_INVALID')
    request=json.loads(request_file.read_bytes());adapter=VieNeuDialoguePresetAdapter(config)
    if (set(request)!={'schema_version','configuration_sha256','voice','line','text','request_key','seed'} or request['schema_version']!=SCHEMA
        or request['configuration_sha256']!=adapter.configuration_sha256 or not isinstance(request['text'],str) or not 1<=len(request['text'])<=4000
        or not re.fullmatch(r'[a-f0-9]{64}',request['request_key']) or type(request['seed']) is not int or request['seed']!=int(request['request_key'][:8],16)):
        raise WorkflowError('DRAMA_VIENEU_REQUEST_INVALID')
    from .voice_library import VoiceDefinition
    voice=VoiceDefinition.model_validate(request['voice']).model_dump(mode='json')
    adapter.validate(voice,request['line']);verify_runtime(config,full=True)
    import numpy as np
    from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
    from vieneu_utils.phonemize_text import normalize_to_chunks_v3_with_gaps,phonemize_text_with_emotions
    from vieneu_utils.core_utils import join_audio_chunks,gaps_to_silence
    class PresetEngine(OnnxV3LiteEngine):
        def _load_denoiser(self):return None
        def _acoustic_frame(self,*args,**kwargs):
            codes,eos=super()._acoustic_frame(*args,**kwargs);self.observed_eos=bool(eos);return codes,eos
    started=time.monotonic();engine=PresetEngine(checkpoint_path=str(config.runtime_root/'models/vieneu-v3-turbo'),
        onnx_dir=str(config.runtime_root/'models/vieneu-v3-turbo/onnx_update'),codec_dir=str(config.runtime_root/'models/moss-codec'),threads=4)
    engine.babble_retries=0;np.random.seed(request['seed']);locked=adapter.locked;preset=adapter.voices[request['voice']['provider_voice_id']]
    chunks,gaps=normalize_to_chunks_v3_with_gaps(request['text'],max_chars=locked['parameters']['max_chars']);waves=[]
    params={k:locked['parameters'][k] for k in ('temperature','top_k','top_p','repetition_penalty','max_new_frames')}
    for text in chunks:
        engine.observed_eos=False
        audio=engine.infer(phonemes=phonemize_text_with_emotions(text),speaker_emb=np.array(preset['speaker_emb'],dtype=np.float32),ref_codes=np.array(preset['codes'],dtype=np.int64),**params)
        if not engine.observed_eos:raise WorkflowError('SYNTHESIS_FRAME_CAP_WITHOUT_EOS_STOP')
        if not np.isfinite(audio).all() or not audio.size:raise WorkflowError('INVALID_TTS_AUDIO')
        waves.append(audio)
    audio=join_audio_chunks(waves,48000,silence_ps=gaps_to_silence(gaps))
    if not audio.size or audio.size>48000*180:raise WorkflowError('DRAMA_LINE_DURATION_EXCEEDS_LIMIT')
    peak=float(np.max(np.abs(audio)))
    if not math.isfinite(peak) or peak<=0:raise WorkflowError('INVALID_TTS_AUDIO')
    gain=min(1.0,.9/peak);audio=audio*gain
    target=guard(directory/'line.wav')
    with target.open('xb') as raw:
        with wave.open(raw,'wb') as wav:
            wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(48000);wav.writeframes((audio*32767).astype('<i2').tobytes())
    durable_json(directory/'provider-receipt.json',{'operation_id':'local-vieneu:'+request['request_key'],'inference_calls':len(waves),
        'seed':request['seed'],'model_revision':locked['model_revision'],'normalization_gain':gain,'generation_seconds':time.monotonic()-started})

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--directory',required=True);args=parser.parse_args()
    try:child(args.directory)
    except Exception as error:
        print(json.dumps({'code':error.code if isinstance(error,WorkflowError) else 'DRAMA_VIENEU_CHILD_FAILED'}));raise SystemExit(1) from None
