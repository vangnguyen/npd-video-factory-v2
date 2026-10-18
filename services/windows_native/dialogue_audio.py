"""Measured per-line PCM and workspace cache. Provider adapters are injected, never invented."""
import json,math,re,shutil,uuid,wave
from pathlib import Path
from typing import Protocol
from pydantic import Field,StrictInt,StrictStr,model_validator
from app.models import StrictModel
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,normalize
from .hardening import durable_json
from .source_audio_cache import lease
from .store import now
from .drama_casting import saved
from .dialogue_plan import build

SCHEMA='native-dialogue-audio.v1'
RATE=48000

class DialogueTTSAdapter(Protocol):
    configuration_sha256:str
    evidence_mode:str
    paid:bool
    def validate(self,voice:dict,line:dict)->None:...
    def synthesize(self,*,text:str,voice:dict,line:dict,take:str|None,request_key:str,target:Path)->dict:...

class ProviderReceipt(StrictModel):
    operation_id:StrictStr|None=Field(default=None,min_length=1,max_length=200)
    inference_calls:StrictInt|None=Field(default=None,ge=1)
    seed:StrictInt|None=Field(default=None,ge=0,le=4294967295)
    model_revision:StrictStr|None=Field(default=None,min_length=1,max_length=150)
    normalization_gain:float|None=Field(default=None,gt=0,le=1,strict=True)
    generation_seconds:float|None=Field(default=None,ge=0,strict=True)
    @model_validator(mode='after')
    def finite(self):
        if any(value is not None and not math.isfinite(value) for value in (self.normalization_gain,self.generation_seconds)):raise ValueError('finite provider measurements required')
        return self

def recover_interrupted(library):
    """Reclassify abandoned intents after their OS lease is free; never bless outputs or replay."""
    library.scope();root=guard(library.store.root,exists=True)
    with library.store.transaction() as con:
        if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='native_dialogue_clips'").fetchone():return {'recovered':0,'active':0,'automatic_provider_calls':0}
        keys=[r[0] for r in con.execute("SELECT input_sha256 FROM native_dialogue_clips WHERE workspace_id=? AND state='preparing'",(library.workspace,))]
    cache=guard(root/'cache'/SCHEMA/digest(library.workspace));cache.mkdir(parents=True,exist_ok=True);recovered=active=0
    for key in keys:
        if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{64}',key):raise WorkflowError('DRAMA_CLIP_CACHE_SCOPE_INVALID')
        try:
            with lease(guard(cache/(key+'.lock')),timeout=.05):
                library.scope()
                with library.store.transaction() as con:
                    result=con.execute("UPDATE native_dialogue_clips SET state='outcome_unknown',error_code='INTERRUPTED_DIALOGUE_NO_AUTOMATIC_REPLAY' WHERE workspace_id=? AND input_sha256=? AND state='preparing'",(library.workspace,key))
                    recovered+=result.rowcount
        except WorkflowError as error:
            if error.code!='SOURCE_AUDIO_CACHE_LOCK_TIMEOUT':raise
            active+=1
    return {'recovered':recovered,'active':active,'automatic_provider_calls':0}

def measure(path):
    import numpy as np
    from .north_star_quality import audio_activity
    path=guard(path,exists=True)
    try:
        if not 44<=path.stat().st_size<=RATE*2*180+4096:raise ValueError()
        with path.open('rb') as raw:
            with wave.open(raw,'rb') as wav:
                if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getcomptype())!=(1,2,RATE,'NONE'):raise ValueError()
                frames=wav.getnframes()
                if not 1<=frames<=RATE*180:raise ValueError()
                data=wav.readframes(frames)
        if not 1<=frames<=RATE*180 or len(data)!=frames*2:raise ValueError()
        samples=np.frombuffer(data,dtype='<i2').astype(np.float64)/32768
        activity=audio_activity(samples,RATE)
        if not activity['audio_activity_detected'] or math.sqrt(float(np.mean(samples*samples)))<.005:raise WorkflowError('DRAMA_LINE_AUDIO_INAUDIBLE')
        if float(np.max(np.abs(samples)))>=.999:raise WorkflowError('DRAMA_LINE_AUDIO_CLIPPING')
        if activity['trailing_silence_seconds']>2:raise WorkflowError('DRAMA_LINE_AUDIO_TRAILING_SILENCE')
        return {'sha256':file_sha(path),'bytes':path.stat().st_size,'sample_rate':RATE,'channels':1,'sample_width':2,'frames':frames,
            'duration_seconds':frames/RATE,'activity':activity,'speech_detected':False,'human_listening_accepted':False}
    except (OSError,EOFError,wave.Error,ValueError):raise WorkflowError('DRAMA_LINE_PCM_INVALID') from None

def profile_signature(plan):
    voices=sorted({(v['voice_id'],v['voice_version'],v['voice_sha256'],v['provider_configuration_sha256']) for v in plan['lines']})
    return digest({'schema_version':SCHEMA,'workspace_id':plan['workspace_id'],'voice_bindings':voices})

def prepare(config,library,snapshot,providers,output,*,authorization_check=lambda:None,on_progress=lambda index,total:None):
    """Use a fresh private output; cache replay verifies bytes before reuse.

    No adapter is configured by this module. Paid providers are disabled here.
    A production caller must obtain its snapshot from trusted human approval.
    """
    library.scope();authorization_check()
    if config.data_root.absolute()!=library.store.root.absolute():raise WorkflowError('DRAMA_WORKSPACE_INVALID')
    document=snapshot['document'];approval=snapshot.get('approval');casting=saved(document)
    if (not casting or not approval or approval.get('snapshot_sha256')!=digest(document)
        or approval.get('approval_scope')!='narration_only' or approval.get('source')!='local_ui_human_review'):
        raise WorkflowError('DRAMA_NARRATION_APPROVAL_REQUIRED')
    signatures={key:adapter.configuration_sha256 for key,adapter in providers.items()}
    plan=build(casting['configuration'],library,provider_signatures=signatures)
    if plan['needs_attention']:raise WorkflowError('DRAMA_DELIVERY_PLAN_NOT_READY')
    takes=document.get('dialogue_delivery_takes',{})
    if not isinstance(takes,dict) or set(takes)-{v['line_id'] for v in plan['lines']} or any(not isinstance(v,str) or not re.fullmatch(r'take_[a-f0-9]{32}',v) for v in takes.values()):
        raise WorkflowError('DRAMA_DELIVERY_TAKE_INVALID',400)
    from .shot_adapter import shots
    canonical_shots=shots(document);scene_ids={shot['shot_id']:i+1 for i,shot in enumerate(canonical_shots)}
    if any(v['shot_id'] not in scene_ids for v in plan['lines']):raise WorkflowError('DRAMA_SHOT_BINDING_CHANGED')
    order=[scene_ids[v['shot_id']] for v in plan['lines']]
    if order!=sorted(order):raise WorkflowError('DRAMA_LINE_ORDER_REVIEW_REQUIRED')
    for shot in canonical_shots:
        text=normalize(' '.join(v['tts_text'] for v in plan['lines'] if v['shot_id']==shot['shot_id']))
        if text!=(normalize(shot['narration']) if shot['narration_enabled'] else ''):raise WorkflowError('DRAMA_SCRIPT_BINDING_CHANGED')
    selected={}
    for line in plan['lines']:
        voice=library.get(line['voice_id'],version=line['voice_version'],for_generation=True)
        if voice['definition_sha256']!=line['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
        adapter=providers[voice['definition']['provider']]
        if type(adapter.paid) is not bool or adapter.paid:raise WorkflowError('DRAMA_PAID_PROVIDER_NOT_ENABLED')
        if adapter.evidence_mode not in {'explicit-mock','local-real','real-provider'}:raise WorkflowError('DRAMA_PROVIDER_EVIDENCE_MODE_INVALID')
        adapter.validate(voice['definition'],line)
        selected[line['line_id']]=(voice,adapter)
    output=guard(Path(output));root=guard(library.store.root,exists=True)
    if root not in output.parents:raise WorkflowError('DRAMA_OUTPUT_SCOPE_INVALID')
    if output.exists() and any(output.iterdir()):raise WorkflowError('DRAMA_OUTPUT_COLLISION')
    authorization_check();output.mkdir(parents=True,exist_ok=True)
    cache=guard(root/'cache'/SCHEMA/digest(library.workspace));cache.mkdir(parents=True,exist_ok=True)
    with library.store.transaction() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS native_dialogue_clips (
            workspace_id TEXT NOT NULL,input_sha256 TEXT NOT NULL,relative_directory TEXT NOT NULL,
            state TEXT NOT NULL,manifest_sha256 TEXT,error_code TEXT,created_at TEXT NOT NULL,
            PRIMARY KEY(workspace_id,input_sha256))''')
    records=[]
    for line_index,line in enumerate(plan['lines']):
        on_progress(line_index+1,len(plan['lines']))
        voice,adapter=selected[line['line_id']];key=digest({'synthesis_input_sha256':line['synthesis_input_sha256'],'take':takes.get(line['line_id'])})
        with lease(guard(cache/(key+'.lock'))):
            authorization_check();current=library.get(line['voice_id'],version=line['voice_version'],for_generation=True)
            if current['definition_sha256']!=line['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
            with library.store.transaction() as con:
                row=con.execute('SELECT * FROM native_dialogue_clips WHERE workspace_id=? AND input_sha256=?',(library.workspace,key)).fetchone()
            if row:
                if row['state']!='ready':raise WorkflowError('DRAMA_CLIP_RECOVERY_REQUIRED')
                directory=guard(root/row['relative_directory'],exists=True)
                if directory.parent!=cache:raise WorkflowError('DRAMA_CLIP_CACHE_SCOPE_INVALID')
                manifest_path=guard(directory/'manifest.json',exists=True)
                if file_sha(manifest_path)!=row['manifest_sha256']:raise WorkflowError('DRAMA_CLIP_MANIFEST_CHANGED')
                manifest=json.loads(manifest_path.read_bytes())
                if (manifest.get('input_sha256')!=key or manifest.get('provider_configuration_sha256')!=adapter.configuration_sha256 or manifest.get('evidence_mode')!=adapter.evidence_mode
                    or manifest.get('pcm')!=measure(directory/'line.wav')):raise WorkflowError('DRAMA_CLIP_BYTES_CHANGED')
                reused=True
            else:
                directory=guard(cache/uuid.uuid4().hex);directory.mkdir();stamp=now()
                with library.store.transaction() as con:con.execute('INSERT INTO native_dialogue_clips VALUES(?,?,?,?,?,?,?)',
                    (library.workspace,key,directory.relative_to(root).as_posix(),'preparing',None,None,stamp))
                try:
                    authorization_check()
                    durable_json(directory/'request-intent.json',{'schema_version':SCHEMA,'request_key':key,'workspace_id':library.workspace,
                        'snapshot_sha256':digest(document),'voice_id':voice['voice_id'],'voice_version':voice['version'],'voice_sha256':voice['definition_sha256'],
                        'provider_configuration_sha256':adapter.configuration_sha256,'text_sha256':digest(line['tts_text']),'take':takes.get(line['line_id']),'created_at':stamp})
                    receipt=ProviderReceipt.model_validate(adapter.synthesize(text=line['tts_text'],voice=voice['definition'],line=line,
                        take=takes.get(line['line_id']),request_key=key,target=directory/'line.wav')).model_dump(mode='json')
                    pcm=measure(directory/'line.wav');authorization_check()
                    latest=library.get(line['voice_id'],version=line['voice_version'],for_generation=True)
                    if latest['definition_sha256']!=line['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
                    manifest={'schema_version':SCHEMA,'input_sha256':key,'provider_configuration_sha256':adapter.configuration_sha256,
                        'source_voice_id':voice['voice_id'],'source_voice_version':voice['version'],'source_voice_sha256':voice['definition_sha256'],
                        'pcm':pcm,'provider_receipt':receipt,'evidence_mode':adapter.evidence_mode,'created_at':stamp,'actual_cost':None,
                        'human_voice_uat_complete':False}
                    durable_json(directory/'manifest.json',manifest)
                    with library.store.transaction() as con:con.execute("UPDATE native_dialogue_clips SET state='ready',manifest_sha256=? WHERE workspace_id=? AND input_sha256=?",
                        (file_sha(directory/'manifest.json'),library.workspace,key))
                    reused=False
                except Exception as error:
                    code=error.code if isinstance(error,WorkflowError) else 'DRAMA_TTS_OUTCOME_UNKNOWN'
                    with library.store.transaction() as con:con.execute("UPDATE native_dialogue_clips SET state='failed',error_code=? WHERE workspace_id=? AND input_sha256=?",(code,library.workspace,key))
                    raise WorkflowError(code) from None
            records.append({'line':line,'cache_key':key,'path':directory/'line.wav','manifest':manifest,'reused':reused})
    def current_cast():
        authorization_check();library.scope()
        for item in records:
            line=item['line'];fresh=library.get(line['voice_id'],version=line['voice_version'],for_generation=True)
            if fresh['definition_sha256']!=line['voice_sha256']:raise WorkflowError('DRAMA_VOICE_BINDING_CHANGED')
    current_cast()
    private=guard(output/'dialogue-clips');private.mkdir()
    for item in records:
        target=guard(private/(item['line']['line_id']+'.wav'))
        with guard(item['path'],exists=True).open('rb') as source,target.open('xb') as destination:shutil.copyfileobj(source,destination,1024*1024)
        if measure(target)!=item['manifest']['pcm']:raise WorkflowError('DRAMA_CLIP_COPY_CHANGED')
        item['private_path']=target
    units=[];offset=0;profile_sha=profile_signature(plan);previous=None
    with (output/'voice.wav').open('xb') as raw:
        with wave.open(raw,'wb') as mixed:
            mixed.setnchannels(1);mixed.setsampwidth(2);mixed.setframerate(RATE)
            for index,item in enumerate(records):
                line=item['line'];pcm=item['manifest']['pcm'];leading=pcm['activity'].get('leading_silence_seconds',0)
                gap=max(0,previous['line']['pause_after_seconds']-previous['manifest']['pcm']['activity']['trailing_silence_seconds']-leading) if previous else 0
                gap_frames=round(gap*RATE)
                if offset+gap_frames+pcm['frames']>180*RATE:raise WorkflowError('DRAMA_DIALOGUE_DURATION_EXCEEDS_LIMIT')
                mixed.writeframes(b'\0\0'*gap_frames);offset+=gap_frames;start=offset/RATE
                with wave.open(str(guard(item['private_path'],exists=True)),'rb') as source:mixed.writeframes(source.readframes(pcm['frames']))
                offset+=pcm['frames']
                units.append({'index':index,'scene':scene_ids[line['shot_id']],'line_id':line['line_id'],'character_id':line['character_id'],
                    'speaker_name':line['character_name'],'voice_id':line['voice_id'],'voice_version':line['voice_version'],'text':line['tts_text'],
                    'start_seconds':start,'end_seconds':offset/RATE,'activity_start_seconds':start+leading,
                    'activity_end_seconds':offset/RATE-pcm['activity']['trailing_silence_seconds'],'cache_key':item['cache_key'],'reused':item['reused']})
                previous=item
    current_cast()
    if any(file_sha(item['private_path'])!=item['manifest']['pcm']['sha256'] for item in records):raise WorkflowError('DRAMA_CLIP_COPY_CHANGED')
    measured=measure(output/'voice.wav')
    if measured['frames']!=offset:raise WorkflowError('DRAMA_DIALOGUE_SAMPLE_BINDING_CHANGED')
    metadata={'schema_version':SCHEMA,'audio_sha256':measured['sha256'],'profile_sha256':profile_sha,'duration_seconds':offset/RATE,'units':units,
        'voice':'project-dialogue','speed':1,'word_alignment':'none','provider_adapter_calls':sum(not r['reused'] for r in records),
        'reused_line_clips':sum(r['reused'] for r in records),'evidence_modes':sorted({r['manifest']['evidence_mode'] for r in records}),
        'speech_detected':False,'human_voice_uat_complete':False,'actual_cost':None,'snapshot_sha256':digest(document)}
    durable_json(output/'voice.json',metadata)
    durable_json(output/'tts-plan.json',{'schema_version':SCHEMA,'profile_sha256':profile_sha,'delivery_plan':plan,'delivery_takes':takes})
    durable_json(output/'dialogue-audio.json',{'schema_version':SCHEMA,'metadata':metadata,'pcm':measured,
        'cache_manifests':[{'line_id':r['line']['line_id'],'cache_key':r['cache_key'],'manifest_sha256':file_sha(r['path'].parent/'manifest.json')} for r in records]})
    return metadata
