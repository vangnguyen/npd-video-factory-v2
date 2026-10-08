"""Opt-in canonical music repeats with measured source frames and reversible fades."""
import copy,json,math,wave
from typing import Literal
from pydantic import Field,StrictInt
from app.models import StrictModel
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,write_json

SCHEMA='native-narrated-music-loop-v1';RATE=48000;MAX_CLIPS=128

class Policy(StrictModel):
    schema_version:Literal['native-narrated-music-loop-v1']=SCHEMA
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    source_frames:StrictInt=Field(ge=2400,le=RATE*600)
    sample_rate:Literal[48000]=RATE
    channels:Literal[2]=2
    crossfade_frames:StrictInt=Field(ge=1,le=RATE)
    curve:Literal['linear_overlap']='linear_overlap'
    normalization:Literal['rms_peak_bound']='rms_peak_bound'
    target_rms_db:Literal[-19]=-19
    peak_limit:Literal[0.9]=.9
    input_mutated:Literal[False]=False

class Receipt(StrictModel):
    schema_version:Literal['native-narrated-music-loop-v1']
    canonical_timeline_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    canonical_track_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    policy_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    source_frames:StrictInt=Field(ge=2400,le=RATE*600)
    output_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    output_frames:StrictInt=Field(ge=1,le=RATE*180)
    sample_rate:Literal[48000]
    channels:Literal[2]
    repeat_count:StrictInt=Field(ge=1,le=MAX_CLIPS)
    input_rms_db:float|None=Field(le=0,allow_inf_nan=False)
    input_peak_db:float|None=Field(le=0,allow_inf_nan=False)
    normalization_gain:float=Field(gt=0,allow_inf_nan=False)
    pre_pcm_clipped_samples:StrictInt=Field(ge=0)
    curve:Literal['linear_overlap']
    source_mutated:Literal[False]
    nominal_gain_after_bed:float=Field(ge=0,le=1,allow_inf_nan=False)
    voice_sidechain_ducking:Literal[True]
    limiter:Literal[True]
    external_calls:StrictInt=Field(ge=0,le=0)
    speech_quality_accepted:Literal[False]
    rights_independently_verified:Literal[False]

def policy(music):
    value=music.get('narrated_loop')
    if value is None:return None
    try:
        parsed=Policy.model_validate(value)
        if (parsed.model_dump(mode='json')!=value or value.get('input_mutated') is not False
            or any(type(value[n]) is not int for n in ('sample_rate','channels','target_rms_db'))
            or parsed.source_sha256!=music['sha256'] or parsed.crossfade_frames*2>parsed.source_frames):raise ValueError()
        return parsed
    except (ValueError,KeyError,TypeError):raise WorkflowError('NARRATED_MUSIC_LOOP_POLICY_INVALID',400) from None

def attach(root,music,seconds):
    if type(seconds) not in (int,float) or not math.isfinite(seconds) or not 0<seconds<=1:raise WorkflowError('MUSIC_LOOP_CROSSFADE_INVALID',400)
    from .media import media_path
    from types import SimpleNamespace
    path=guard(media_path(SimpleNamespace(data_root=root),music['id']),exists=True)
    try:
        if file_sha(path)!=music['sha256'] or music.get('kind')!='music' or music.get('rights_confirmed') is not True:raise ValueError()
        with wave.open(str(path),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate())!=(2,2,RATE):raise ValueError()
            frames=wav.getnframes()
        crossfade=round(seconds*RATE)
        if crossfade*2>frames:raise WorkflowError('MUSIC_LOOP_CROSSFADE_INVALID',400)
        value=Policy(source_sha256=music['sha256'],source_frames=frames,crossfade_frames=crossfade).model_dump(mode='json')
        return {**copy.deepcopy(music),'narrated_loop':value}
    except (ValueError,KeyError,TypeError,wave.Error,EOFError,OSError):raise WorkflowError('NARRATED_MUSIC_MEASURED_PCM_REQUIRED',400) from None

def track(document,duration):
    music=document.get('music') if document.get('music_enabled',True) else None
    if not music:return None
    p=policy(music)
    if p is None:return None
    if type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=180:raise WorkflowError('NARRATED_MUSIC_TIMELINE_DURATION_INVALID',400)
    from .branding import resolve
    brand,_=resolve(document);target=round(duration*RATE);step=p.source_frames-p.crossfade_frames
    count=max(1,(max(0,target-p.source_frames)+step-1)//step+1)
    if count>MAX_CLIPS:raise WorkflowError('PREVIEW_AUDIO_CLIP_LIMIT',400)
    clips=[]
    for i in range(count):
        start=i*step;length=min(p.source_frames,target-start)
        incoming=min(RATE//2,length) if i==0 else min(p.crossfade_frames,length)
        outgoing=min(RATE,length) if i==count-1 else min(p.crossfade_frames,length)
        clips.append({'clip_id':'clip_native_music_'+str(i),'kind':'music','label':music['filename'][:120],
            'asset_id':'ast_'+digest(music['id'])[:32],'source_start':0,'source_end':round(length/RATE,6),
            'timeline_start':round(start/RATE,6),'duration':round(length/RATE,6),'volume':brand.music_profile.nominal_gain,
            'transition_in':{'kind':'fade' if i==0 else 'crossfade','duration_seconds':round(incoming/RATE,6)},
            'transition_out':{'kind':'fade' if i==count-1 else 'crossfade','duration_seconds':round(outgoing/RATE,6)},
            'metadata':{'schema_version':SCHEMA,'native_asset_id':music['id'],'source_sha256':p.source_sha256,
                'source_frames':p.source_frames,'start_frame':start,'frame_count':length,'fade_in_frames':incoming,'fade_out_frames':outgoing,
                'repeat_index':i,'input_mutated':False,'rights_status':music.get('rights_status','unknown'),
                'license':music.get('license'),'source_type':music.get('source_type','user_upload'),'provider':music.get('provider'),
                'source_reference':music.get('source_reference'),'generation_provenance':copy.deepcopy(music.get('generation_provenance',{}))}})
    return {'track_id':'trk_native_music','type':'audio','kind':'music','label':'Nhạc nền','order':1,'clips':clips}

def decision_metadata(document,duration):
    music=document.get('music') if document.get('music_enabled',True) else None
    p=policy(music) if music else None
    if p is None:return None
    return {'schema_version':SCHEMA,'policy_sha256':digest(p.model_dump(mode='json')),'sample_rate':RATE,
        'target_frames':round(duration*RATE),'normalization':'rms_peak_bound','voice_sidechain_ducking':True,'limiter':True,'input_mutated':False}

def verify_source(config,document):
    music=document.get('music') if document.get('music_enabled',True) else None
    p=policy(music) if music else None
    if p is None:return None
    from .media import media_path
    source=guard(media_path(config,music['id']),exists=True)
    if music.get('rights_confirmed') is not True or file_sha(source)!=p.source_sha256:raise WorkflowError('MUSIC_ARTIFACT_CHANGED_OR_RIGHTS_MISSING')
    try:
        with wave.open(str(source),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())!=(2,2,RATE,p.source_frames):raise ValueError()
    except (ValueError,wave.Error,EOFError):raise WorkflowError('NARRATED_MUSIC_MEASURED_PCM_CHANGED') from None
    return source,p

def verify_bundle(config,document,directory,manifest=None):
    source=verify_source(config,document)
    if source is None:return None
    from .shot_adapter import validate_document
    from app.timeline_models import TimelineTrack
    state=validate_document(document);expected=TimelineTrack.model_validate(track(document,state['snapshot']['duration_seconds'])).model_dump(mode='json')
    try:
        receipt=json.loads(guard(directory/'music-loop.json',exists=True).read_bytes())
        parsed=Receipt.model_validate(receipt).model_dump(mode='json')
        if (parsed!=receipt or any(receipt[n] is not False for n in ('source_mutated','speech_quality_accepted','rights_independently_verified'))
            or any(receipt[n] is not True for n in ('voice_sidechain_ducking','limiter'))
            or any(type(receipt[n]) is not int for n in ('sample_rate','channels'))
            or receipt['nominal_gain_after_bed']!=expected['clips'][0]['volume']):raise ValueError()
        if manifest is None:manifest=json.loads(guard(directory/'render-manifest.json',exists=True).read_bytes())
        if not isinstance(manifest,dict):raise ValueError()
        path=guard(directory/'music-loop.wav',exists=True);p=source[1];target=round(state['snapshot']['duration_seconds']*RATE)
        if (manifest.get('canonical_music_loop')!=receipt or receipt['schema_version']!=SCHEMA or receipt['canonical_timeline_sha256']!=state['sha256']
            or receipt['canonical_track_sha256']!=digest(expected) or receipt['policy_sha256']!=digest(p.model_dump(mode='json'))
            or receipt['source_sha256']!=p.source_sha256 or receipt['source_frames']!=p.source_frames or receipt['output_frames']!=target
            or receipt['repeat_count']!=len(expected['clips']) or receipt['output_sha256']!=file_sha(path)
            or receipt['source_mutated'] is not False or receipt['speech_quality_accepted'] is not False or receipt['rights_independently_verified'] is not False
            or type(receipt['pre_pcm_clipped_samples']) is not int or receipt['pre_pcm_clipped_samples']!=0 or receipt['external_calls']!=0):raise ValueError()
        with wave.open(str(path),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())!=(2,2,RATE,target):raise ValueError()
        return receipt
    except (ValueError,KeyError,TypeError,wave.Error,EOFError,OSError):raise WorkflowError('NARRATED_MUSIC_RENDER_BINDING_CHANGED') from None

def materialize(config,document,out):
    """Use exact canonical frame decisions; preview and final share this function."""
    import numpy as np
    from .shot_adapter import validate_document
    state=validate_document(document)
    if state is None:raise WorkflowError('NARRATED_MUSIC_CANONICAL_TIMELINE_REQUIRED',400)
    expected=track(document,state['snapshot']['duration_seconds'])
    if expected is None:return None
    # TimelineSnapshot inserts defaults. Compare the complete normalized projection.
    from app.timeline_models import TimelineTrack
    expected=TimelineTrack.model_validate(expected).model_dump(mode='json')
    registered=[t for t in state['snapshot']['tracks'] if t['track_id']=='trk_native_music']
    if registered!=[expected]:raise WorkflowError('NARRATED_MUSIC_CANONICAL_TRACK_CHANGED')
    music=document['music'];source,p=verify_source(config,document)
    try:
        with wave.open(str(source),'rb') as wav:
            if (wav.getnchannels(),wav.getsampwidth(),wav.getframerate(),wav.getnframes())!=(2,2,RATE,p.source_frames):raise ValueError()
            samples=np.frombuffer(wav.readframes(p.source_frames),dtype='<i2').reshape(-1,2).astype(np.float64)/32768
        if not np.isfinite(samples).all():raise ValueError()
    except (ValueError,wave.Error,EOFError):raise WorkflowError('NARRATED_MUSIC_MEASURED_PCM_CHANGED') from None
    rms=float(np.sqrt(np.mean(samples*samples)));peak=float(np.max(np.abs(samples)))
    gain=min(10**(p.target_rms_db/20)/rms,p.peak_limit/peak) if rms>1e-9 and peak>1e-9 else 1.
    metadata=decision_metadata(document,state['snapshot']['duration_seconds'])
    if state['snapshot']['metadata'].get('narrated_music_loop')!=metadata:raise WorkflowError('NARRATED_MUSIC_CANONICAL_TRACK_CHANGED')
    samples*=gain;bed=np.zeros((metadata['target_frames'],2),dtype=np.float64)
    for clip in expected['clips']:
        m=clip['metadata'];length=m['frame_count'];envelope=np.ones(length,dtype=np.float64)
        incoming,outgoing=m['fade_in_frames'],m['fade_out_frames']
        envelope[:incoming]*=np.arange(incoming,dtype=np.float64)/incoming
        envelope[-outgoing:]*=1-np.arange(outgoing,dtype=np.float64)/outgoing
        start=m['start_frame'];bed[start:start+length]+=samples[:length]*envelope[:,None]
    clipped=int(np.count_nonzero(np.abs(bed)>1));pcm=np.rint(np.clip(bed,-1,32767/32768)*32768).astype('<i2')
    destination=out/'music-loop.wav'
    with destination.open('xb') as handle:
        with wave.open(handle,'wb') as wav:wav.setnchannels(2);wav.setsampwidth(2);wav.setframerate(RATE);wav.writeframes(pcm.tobytes())
    receipt={'schema_version':SCHEMA,'canonical_timeline_sha256':state['sha256'],'canonical_track_sha256':digest(expected),
        'policy_sha256':digest(p.model_dump(mode='json')),'source_sha256':p.source_sha256,'source_frames':p.source_frames,
        'output_sha256':file_sha(destination),'output_frames':len(pcm),'sample_rate':RATE,'channels':2,'repeat_count':len(expected['clips']),
        'input_rms_db':20*math.log10(rms) if rms>0 else None,'input_peak_db':20*math.log10(peak) if peak>0 else None,
        'normalization_gain':gain,'pre_pcm_clipped_samples':clipped,'curve':'linear_overlap','source_mutated':False,
        'nominal_gain_after_bed':expected['clips'][0]['volume'],'voice_sidechain_ducking':True,'limiter':True,'external_calls':0,
        'speech_quality_accepted':False,'rights_independently_verified':False}
    write_json(out/'music-loop.json',receipt);return destination,receipt
