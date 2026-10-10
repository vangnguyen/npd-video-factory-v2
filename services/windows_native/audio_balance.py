"""Stream actual stereo render/stem samples; no speech inference or listening UAT."""
from contextlib import ExitStack
import json
import math,subprocess
from pathlib import Path
from typing import Literal
from pydantic import Field
from app.models import StrictModel
from .backup import guard
from .contracts import WorkflowError,digest,file_sha,write_json

RATE=48000;CHANNELS=2;FRAME_BYTES=8;WINDOW=2400;MAX_SECONDS=1800
REFERENCE='audio-reference.f32le';MUSIC='audio-music.f32le';FINAL='audio-final.f32le';REPORT='audio-balance.json'

class Policy(StrictModel):
    schema_version:Literal['native-measured-audio-balance-policy-v1']='native-measured-audio-balance-policy-v1'
    activity_threshold_dbfs:float=Field(default=-40,ge=-60,le=-20,allow_inf_nan=False,strict=True)
    minimum_reference_seconds:float=Field(default=.08,ge=.02,le=2,allow_inf_nan=False,strict=True)
    minimum_reference_to_music_db:float=Field(default=6,ge=0,le=24,allow_inf_nan=False,strict=True)
    maximum_overpowering_fraction:float=Field(default=.10,ge=0,le=.5,allow_inf_nan=False,strict=True)
    maximum_missing_mix_fraction:float=Field(default=.02,ge=0,le=.1,allow_inf_nan=False,strict=True)
    missing_mix_floor_dbfs:float=Field(default=-55,ge=-80,le=-35,allow_inf_nan=False,strict=True)
    minimum_mix_to_reference_db:float=Field(default=-18,ge=-30,le=-6,allow_inf_nan=False,strict=True)

def outputs(directory,stems,duration):
    if (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=MAX_SECONDS
        or set(stems)-{'reference','music'}):raise WorkflowError('AUDIO_BALANCE_STEM_CONFIGURATION_INVALID')
    result=[]
    for role,name in (('reference',REFERENCE),('music',MUSIC)):
        if role in stems:result+=['-map',stems[role],'-f','f32le','-ac',str(CHANNELS),'-ar',str(RATE),'-t',f'{duration:.9f}',str(guard(Path(directory)/name))]
    return result

def pcm(directory,name,duration):
    path=guard(Path(directory)/name,exists=True);size=path.stat().st_size
    if not path.is_file() or size%FRAME_BYTES or not 0<size<=RATE*FRAME_BYTES*MAX_SECONDS or abs(size/FRAME_BYTES/RATE-duration)>.08:
        raise WorkflowError('AUDIO_BALANCE_PCM_BINDING_INVALID')
    return path,{'reference':name,'sha256':file_sha(path),'bytes':size,'frames':size//FRAME_BYTES,'sample_rate':RATE,'channels':CHANNELS,'encoding':'f32le'}

def db(value):return round(20*math.log10(value),6) if value>0 else None

def measure(directory,*,duration,final_sha256,document_sha256,manifest_sha256,reference_role,policy=None,persist=True):
    import numpy as np
    directory=guard(directory,exists=True)
    if type(persist) is not bool:raise WorkflowError('AUDIO_BALANCE_CONFIGURATION_INVALID')
    if (type(duration) not in (int,float) or not math.isfinite(duration) or not 0<duration<=MAX_SECONDS
        or reference_role not in ('narrated_voice','canonical_original_audio','no_reference')):raise WorkflowError('AUDIO_BALANCE_CONFIGURATION_INVALID')
    for value in (final_sha256,document_sha256,manifest_sha256):
        if not isinstance(value,str) or len(value)!=64 or any(c not in 'abcdef0123456789' for c in value):raise WorkflowError('AUDIO_BALANCE_CONFIGURATION_INVALID')
    p=Policy.model_validate(policy or {});names={'final':FINAL}
    if reference_role!='no_reference':names['reference']=REFERENCE
    if (Path(directory)/MUSIC).exists():names['music']=MUSIC
    facts={};paths={}
    for role,name in names.items():paths[role],facts[role]=pcm(directory,name,duration)
    frames=round(duration*RATE)
    if any(f['frames']<frames for f in facts.values()):raise WorkflowError('AUDIO_BALANCE_PCM_BINDING_INVALID')
    for role,fact in facts.items():
        if role!='final' and fact['frames']>frames+1:raise WorkflowError('AUDIO_BALANCE_PCM_BINDING_INVALID')
        fact['analyzed_frames']=frames;fact['encoding_padding_frames']=fact['frames']-frames
    active=0;overpowered=0;missing=0;minimum_margin=None;worst=[];position=0
    total_energy={role:0. for role in names};peaks={role:0. for role in names};failures=[]
    with ExitStack() as stack:
        streams={role:stack.enter_context(path.open('rb')) for role,path in paths.items()}
        while position<frames:
            count=min(WINDOW,frames-position);rms={}
            for role,stream in streams.items():
                raw=stream.read(count*FRAME_BYTES)
                if len(raw)!=count*FRAME_BYTES:raise WorkflowError('AUDIO_BALANCE_PCM_CHANGED')
                samples=np.frombuffer(raw,dtype='<f4').astype(np.float64)
                if not np.isfinite(samples).all() or np.max(np.abs(samples))>64:raise WorkflowError('AUDIO_BALANCE_PCM_INVALID')
                energy=float(np.dot(samples,samples));total_energy[role]+=energy;peaks[role]=max(peaks[role],float(np.max(np.abs(samples))));rms[role]=math.sqrt(energy/len(samples))
            reference=rms.get('reference',0)
            if reference>=10**(p.activity_threshold_dbfs/20):
                active+=count;music=rms.get('music',0);margin=20*math.log10(reference/music) if music>0 else None
                if margin is not None:minimum_margin=margin if minimum_margin is None else min(minimum_margin,margin)
                bad=margin is not None and margin<p.minimum_reference_to_music_db
                lost=rms['final']<10**(p.missing_mix_floor_dbfs/20) or rms['final']/reference<10**(p.minimum_mix_to_reference_db/20)
                if bad:overpowered+=count
                if lost:missing+=count
                if bad or lost:
                    worst.append({'start':round(position/RATE,6),'end':round((position+count)/RATE,6),'reference_rms_dbfs':db(reference),
                        'music_rms_dbfs':db(music),'final_rms_dbfs':db(rms['final']),'margin_db':round(margin,6) if margin is not None else None,
                        'music_overpowering':bad,'final_audio_missing':lost})
                    worst.sort(key=lambda v:(not v['final_audio_missing'],v['margin_db'] if v['margin_db'] is not None else 100,v['start']));del worst[8:]
            position+=count
    for role,path in paths.items():
        if file_sha(path)!=facts[role]['sha256']:raise WorkflowError('AUDIO_BALANCE_PCM_CHANGED')
    if reference_role!='no_reference':
        if active/RATE<p.minimum_reference_seconds:failures.append('REFERENCE_AUDIO_INAUDIBLE')
        elif overpowered/active>p.maximum_overpowering_fraction:failures.append('MUSIC_OVERPOWERS_REFERENCE')
        if active and missing/active>p.maximum_missing_mix_fraction:failures.append('FINAL_AUDIO_MISSING_DURING_REFERENCE')
    evidence={'schema_version':'native-measured-audio-balance-v1','status':'failed_qc' if failures else 'not_applicable' if reference_role=='no_reference' else 'passed',
        'final_sha256':final_sha256,'document_sha256':document_sha256,'manifest_sha256':manifest_sha256,'policy':p.model_dump(mode='json'),
        'policy_sha256':digest(p.model_dump(mode='json')),'reference_role':reference_role,'samples':facts,'window_seconds':WINDOW/RATE,
        'reference_active_seconds':round(active/RATE,6),'music_overpowering_seconds':round(overpowered/RATE,6),'missing_final_audio_seconds':round(missing/RATE,6),
        'overpowering_fraction':round(overpowered/active,6) if active else None,'missing_mix_fraction':round(missing/active,6) if active else None,
        'minimum_reference_to_music_db':round(minimum_margin,6) if minimum_margin is not None else None,
        'overall_rms_dbfs':{role:db(math.sqrt(energy/(frames*CHANNELS))) for role,energy in total_energy.items()},
        'sample_peak_dbfs':{role:db(value) for role,value in peaks.items()},'worst_windows':worst,'failures':failures,
        'reference_sample_basis':'post_editorial_gain_fades_normalization_and_music_ducking_before_shared_limiter',
        'reference_measurement_mode':'independent_single_output_audio_only_replay_of_physical_sources_and_canonical_dsp',
        'thresholds_calibrated_for_speech':False,
        'stereo_energy_preserved':True,'speech_detection_performed':False,'source_voice_separated':reference_role=='narrated_voice',
        'speech_intelligibility_accepted':False,'human_listening_accepted':False,'rights_independently_verified':False,'publishing_authorized':False,
        'external_provider_calls':0,'paid_operations':0}
    if persist:
        target=guard(directory/REPORT)
        if target.exists():raise WorkflowError('AUDIO_BALANCE_REPORT_ALREADY_EXISTS')
        write_json(target,evidence)
    return evidence

def _inputs(directory,manifest_name,reference_role):
    manifest=guard(directory/manifest_name,exists=True)
    try:
        body=json.loads(manifest.read_bytes());original=body['audio_balance_inputs'];filters={}
        if original['reference_role']!=reference_role:raise ValueError()
        for role,name in (('reference',REFERENCE),('music',MUSIC)):
            expected=original[role+'_sha256'];path=guard(directory/name)
            script=guard(directory/('audio-'+role+'-filter.txt'))
            if expected is None:
                if path.exists() or script.exists():raise ValueError()
            else:
                if file_sha(guard(path,exists=True))!=expected:raise ValueError()
                filters[role]=file_sha(guard(script,exists=True))
        if (original['filter_graph_sha256']!=digest(filters) or type(original['diagnostic_filter_threads']) is not int or original['diagnostic_filter_threads']!=1
            or original['diagnostic_pass']!='independent_audio_only_same_source_and_dsp'):raise ValueError()
        if manifest_name=='audio-stem-manifest.json' and file_sha(guard(directory/'timeline-render.json',exists=True))!=body['production_manifest_sha256']:raise ValueError()
    except (ValueError,KeyError,TypeError,OSError):raise WorkflowError('AUDIO_BALANCE_STEM_BINDING_CHANGED') from None
    return manifest

def inspect(config,directory,*,duration,document_sha256,manifest_name,reference_role,policy=None):
    directory=guard(directory,exists=True);video=guard(directory/'final.mp4',exists=True)
    manifest=_inputs(directory,manifest_name,reference_role)
    before=file_sha(video);manifest_sha=file_sha(manifest);destination=guard(directory/FINAL)
    try:
        result=subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-i',str(video),'-map','0:a:0','-vn',
            '-f','f32le','-ac',str(CHANNELS),'-ar',str(RATE),str(destination)],capture_output=True,timeout=min(300,max(30,duration*2)))
        if result.returncode:raise ValueError()
    except (ValueError,OSError,subprocess.TimeoutExpired):raise WorkflowError('AUDIO_BALANCE_FINAL_DECODE_FAILED') from None
    value=measure(directory,duration=duration,final_sha256=before,document_sha256=document_sha256,manifest_sha256=manifest_sha,reference_role=reference_role,policy=policy)
    if file_sha(video)!=before or file_sha(manifest)!=manifest_sha:raise WorkflowError('AUDIO_BALANCE_RENDER_CHANGED')
    if value['failures']:raise WorkflowError('AUDIO_BALANCE_MEASURED_QC_FAILED')
    return value

def validate(directory,expected,*,duration,document_sha256,manifest_name,reference_role,video_name='final.mp4'):
    """Recompute preserved PCM facts offline, with no decoding or new outputs."""
    directory=guard(directory,exists=True);video=guard(directory/video_name,exists=True)
    manifest=_inputs(directory,manifest_name,reference_role)
    try:
        saved=json.loads(guard(directory/REPORT,exists=True).read_bytes())
        if saved!=expected:raise ValueError()
        measured=measure(directory,duration=duration,final_sha256=file_sha(video),document_sha256=document_sha256,
            manifest_sha256=file_sha(manifest),reference_role=reference_role,policy=saved['policy'],persist=False)
        if measured!=saved or measured['failures']:raise ValueError()
    except (OSError,ValueError,KeyError,TypeError):raise WorkflowError('AUDIO_BALANCE_EVIDENCE_CHANGED') from None
    return measured

def validate_qc(directory,qc,document_sha256,*,video_name='final.mp4'):
    source='measured_audio_balance' in qc
    expected=qc.get('measured_audio_balance') if source else ((qc.get('full_quality') or {}).get('full_production_qc') or {}).get('measured_audio_balance')
    if expected is None:
        if (Path(directory)/REPORT).exists():raise WorkflowError('AUDIO_BALANCE_EVIDENCE_CHANGED')
        return None  # Historical accepted checkpoints retain their original contract.
    try:
        return validate(directory,expected,duration=expected['samples']['final']['analyzed_frames']/RATE,
            document_sha256=document_sha256,manifest_name='audio-stem-manifest.json' if source else 'render-manifest.json',
            reference_role=expected['reference_role'],video_name=video_name)
    except (OSError,ValueError,KeyError,TypeError):raise WorkflowError('AUDIO_BALANCE_EVIDENCE_CHANGED') from None

def artifact_names(directory):
    directory=Path(directory)
    return tuple(name for name in (REPORT,REFERENCE,MUSIC,FINAL,'audio-stem-manifest.json',
        'audio-reference-filter.txt','audio-music-filter.txt') if (directory/name).is_file())

def narrated_stems(config,directory,*,duration,voice_file,music_file,voice_filters,music_gain,canonical_fades):
    """Read the render's physical audio sources; do not alter the mixed render."""
    directory=guard(directory,exists=True);voice=guard(directory/voice_file,exists=True)
    video=guard(directory/'final.mp4',exists=True);before=file_sha(video)
    sources=[voice]+([guard(music_file,exists=True)] if music_file is not None else [])
    hashes=[file_sha(path) for path in sources]
    voice_filters=voice_filters.replace('[1:a]','[0:a]')
    graphs={'reference':voice_filters.replace('[a]','[qc_reference]')}
    if music_file is not None:
        fade='' if canonical_fades else f",afade=t=out:st={max(duration-1,0):.4f}:d=1"
        graphs['music']=voice_filters.replace('[a]','[reference]')+f';[reference]apad=pad_dur=0.25,asetnsamples=n=1024:p=1[sidechain];[1:a]volume={music_gain:.6f},apad,atrim=duration={duration:.4f}{fade},apad=pad_dur=0.25,asetnsamples=n=1024:p=1[bed];[bed][sidechain]sidechaincompress=threshold=0.015:ratio=8:attack=20:release=250,atrim=duration={duration:.9f},asetpts=PTS-STARTPTS[qc_music]'
    for role,filters in graphs.items():
        path=guard(directory/('audio-'+role+'-filter.txt'));path.write_text(filters,encoding='utf-8')
        command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-filter_complex_threads','1','-i',str(voice)]
        if role=='music':command+=['-stream_loop','-1','-i',str(sources[1])]
        command+=['-/filter_complex',str(path),*outputs(directory,{role:'[qc_'+role+']'},duration)]
        try:
            result=subprocess.run(command,capture_output=True,timeout=min(300,max(30,duration*2)))
            if result.returncode:raise ValueError()
        except (ValueError,OSError,subprocess.TimeoutExpired):raise WorkflowError('AUDIO_BALANCE_STEM_EXPORT_FAILED') from None
    if file_sha(video)!=before or hashes!=[file_sha(source) for source in sources]:raise WorkflowError('AUDIO_BALANCE_SOURCE_CHANGED')
    return {role:file_sha(directory/('audio-'+role+'-filter.txt')) for role in graphs}

def source_stems(config,snapshot,assets,directory):
    """Replay the exact canonical DSP on the already staged input bytes, no remix."""
    from app.timeline_audio_processing import build_processed_audio_graph
    staged={}
    for identifier,(asset,path) in assets.items():
        original=guard(directory/'media'/(identifier+path.suffix.lower()),exists=True)
        if file_sha(original)!=asset.checksum_sha256:raise WorkflowError('AUDIO_BALANCE_SOURCE_CHANGED')
        staged[identifier]=(asset,original)
    graph=build_processed_audio_graph(snapshot,staged,first_input_index=0,processing=snapshot.metadata.get('source_audio_processing'),stem_outputs=True)
    reference_role='canonical_original_audio' if 'reference' in graph.stems else 'no_reference'
    for role,components in graph.stem_graphs.items():
        filters=guard(directory/('audio-'+role+'-filter.txt'));filters.write_text(';'.join(components),encoding='utf-8')
        try:
            result=subprocess.run([str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n','-filter_complex_threads','1',*graph.inputs,'-/filter_complex',str(filters),
                *outputs(directory,{role:graph.stems[role]},snapshot.duration_seconds)],capture_output=True,timeout=min(300,max(30,snapshot.duration_seconds*2)))
            if result.returncode:raise ValueError()
        except (ValueError,OSError,subprocess.TimeoutExpired):raise WorkflowError('AUDIO_BALANCE_STEM_EXPORT_FAILED') from None
    for identifier,(asset,path) in staged.items():
        if file_sha(path)!=asset.checksum_sha256:raise WorkflowError('AUDIO_BALANCE_SOURCE_CHANGED')
    original=guard(directory/'timeline-render.json',exists=True)
    binding={'schema_version':'native-canonical-audio-stem-manifest-v1','production_manifest_sha256':file_sha(original),
        'canonical_audio_configuration':graph.processing,'source_sha256':{identifier:asset.checksum_sha256 for identifier,(asset,path) in staged.items()},
        'audio_balance_inputs':{'reference_role':reference_role,'reference_sha256':file_sha(directory/REFERENCE) if 'reference' in graph.stems else None,
            'music_sha256':file_sha(directory/MUSIC) if 'music' in graph.stems else None,
            'filter_graph_sha256':digest({role:file_sha(directory/('audio-'+role+'-filter.txt')) for role in graph.stem_graphs}),
            'diagnostic_filter_threads':1,'diagnostic_pass':'independent_audio_only_same_source_and_dsp'}}
    write_json(directory/'audio-stem-manifest.json',binding);return reference_role
