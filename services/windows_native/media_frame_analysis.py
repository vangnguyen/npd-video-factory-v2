"""Checksum-bound CPU frame observations; no semantic provider is synthesized."""
import copy
from datetime import datetime,timezone
from pathlib import Path
import uuid
from typing import Literal
from pydantic import Field
from .ingestion import API_ROOT
from .contracts import WorkflowError,digest,file_sha
from .media import project_assets,media_path
from .hardening import Artifacts,durable_json
from app.models import StrictModel
from app.media_frame_facts import ALGORITHM,PixelFacts,MeasuredFrame,PixelAssetSummary,pixel_facts

SCHEMA='native-media-frame-observations-v1'
MAX_RECORDS=400
FRAME_COUNT=8


class FrameRead(StrictModel):
    frame_id:str=Field(pattern=r'^mfr_[a-f0-9]{24}$')
    timestamp_seconds:float=Field(ge=0)
    timestamp_basis:Literal['requested_ffmpeg_source_seek; decoded_pts_unavailable']='requested_ffmpeg_source_seek; decoded_pts_unavailable'
    decoded_pts_seconds:None=None
    reference:str=Field(pattern=r'^media-frame://[a-f0-9]{32}/frame-[a-f0-9]{24}\.png$')
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    decoded_pixels_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    width:int=Field(ge=1,le=7680)
    height:int=Field(ge=1,le=7680)
    pixel_facts:PixelFacts
    duplicate_sample_of:str|None=Field(default=None,pattern=r'^mfr_[a-f0-9]{24}$')


class Rebinding(StrictModel):
    source_project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    source_observation_id:str=Field(pattern=r'^mfo_[a-f0-9]{24}$')
    source_record_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    fresh_measurement:Literal[False]=False


class Observation(StrictModel):
    schema_name:Literal['native-media-frame-observations-v1']=Field(alias='schema')
    observation_id:str=Field(pattern=r'^mfo_[a-f0-9]{24}$')
    fingerprint:str=Field(pattern=r'^[a-f0-9]{64}$')
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    asset_id:str=Field(min_length=1,max_length=100)
    source_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    provider:Literal['local_ffmpeg_pillow_pixels']
    model:Literal['pixel-quality-facts-v1']
    created_at:datetime
    semantic_provider_status:Literal['NOT_CONFIGURED']
    semantic_inference_performed:Literal[False]
    external_provider_calls:Literal[0]
    confidence:None
    rights_status:Literal['owner_upload_attestation','unknown']
    rights_independently_verified:Literal[False]
    needs_attention:Literal[True]
    frames:list[FrameRead]=Field(min_length=1,max_length=FRAME_COUNT)
    best_frame_ids:list[str]=Field(max_length=3)
    thumbnail_candidate_ids:list[str]=Field(max_length=3)
    ranking_basis:Literal['uncalibrated sampled pixel sharpness/brightness heuristic; semantic relevance unknown']
    frozen_video_detection_performed:Literal[False]
    exact_sample_duplicate_detection:Literal[True]
    identity_rebinding:Rebinding|None=None


def fingerprint(project_id,asset):
    return digest({'schema':SCHEMA,'project_id':project_id,'asset_id':asset['id'],
        'source_sha256':asset['sha256'],'algorithm':ALGORITHM,'frames':FRAME_COUNT,'pixel_grid':64})


def validate(record,project_id,asset):
    if set(record)!={'observation','sha256'} or record['sha256']!=digest(record['observation']):
        raise WorkflowError('MEDIA_FRAME_RECORD_CHANGED')
    value=record['observation']
    try:Observation.model_validate(value)
    except ValueError:raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID') from None
    if (value.get('schema')!=SCHEMA or value.get('project_id')!=project_id or value.get('asset_id')!=asset['id']
            or value.get('source_sha256')!=asset['sha256'] or value.get('fingerprint')!=fingerprint(project_id,asset)
            or value.get('semantic_provider_status')!='NOT_CONFIGURED' or value.get('external_provider_calls')!=0):
        raise WorkflowError('MEDIA_FRAME_SOURCE_BINDING_MISMATCH')
    frames=[FrameRead.model_validate(frame) for frame in value['frames']]
    if not frames or len(frames)>FRAME_COUNT or len({frame.frame_id for frame in frames})!=len(frames):
        raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID')
    duration=asset.get('duration_seconds') if asset['kind']=='video' else None
    if duration is not None and any(frame.timestamp_seconds>=duration for frame in frames):
        raise WorkflowError('MEDIA_FRAME_TIME_INVALID')
    if value['observation_id']!='mfo_'+value['fingerprint'][:24]:
        raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID')
    previous=-1;seen={}
    for index,frame in enumerate(frames):
        if frame.frame_id!='mfr_'+digest([value['fingerprint'],index])[:24]:
            raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID')
        if (frame.timestamp_seconds<=previous or frame.duplicate_sample_of is not None and
                (frame.duplicate_sample_of not in seen or seen[frame.duplicate_sample_of]!=frame.decoded_pixels_sha256)):
            raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID')
        if frame.reference.split('/')[2]!=value['job_id']:
            raise WorkflowError('MEDIA_FRAME_ARTIFACT_BINDING_MISMATCH')
        if not value.get('identity_rebinding') and frame.reference.split('/')[-1]!='frame-'+frame.frame_id[4:]+'.png':
            raise WorkflowError('MEDIA_FRAME_ARTIFACT_BINDING_MISMATCH')
        previous=frame.timestamp_seconds;seen[frame.frame_id]=frame.decoded_pixels_sha256
    eligible={frame.frame_id for frame in frames if not frame.pixel_facts.black_sample and not frame.duplicate_sample_of}
    if (not set(value['best_frame_ids']+value['thumbnail_candidate_ids'])<=eligible or
            any(len(ids)!=len(set(ids)) for ids in (value['best_frame_ids'],value['thumbnail_candidate_ids']))):
        raise WorkflowError('MEDIA_FRAME_CANDIDATES_INVALID')
    return value


def pending(document,project_id):
    output=[]
    for asset in project_assets(document):
        if asset['kind'] not in {'video','image'}:continue
        found=False
        for record in document.get('media_frame_analyses',[]):
            if record['observation'].get('asset_id')==asset['id'] and record['observation'].get('source_sha256')==asset['sha256']:
                validate(record,project_id,asset);found=True
        if not found:output.append(asset)
    return output


def linked(path):
    return any(p.is_symlink() or getattr(p,'is_junction',lambda:False)() for p in [path,*path.parents])


def checked_path(config,asset):
    path=media_path(config,asset['id']);root=config.data_root/'assets'
    if linked(root) or linked(path) or path.resolve().parent!=root.resolve() or not path.is_file() or file_sha(path)!=asset['sha256']:
        raise WorkflowError('SOURCE_MEDIA_CHANGED_OR_MISSING')
    return path


def frame_path(root,frame):
    value=FrameRead.model_validate(frame)
    job_id,name=value.reference.removeprefix('media-frame://').split('/')
    directory=Path(root)/'jobs'/job_id;path=directory/name
    if (linked(directory) or linked(path) or path.resolve().parent!=directory.resolve()
            or not path.is_file() or file_sha(path)!=value.sha256):
        raise WorkflowError('MEDIA_FRAME_ARTIFACT_CHANGED')
    return path


def view(store,project_id):
    project=store.get(project_id);assets={a['id']:a for a in project_assets(project['document'])}
    observations=[]
    for record in project['document'].get('media_frame_analyses',[]):
        asset=assets.get(record['observation']['asset_id'])
        if asset is None or record['observation']['source_sha256']!=asset['sha256']:continue
        value=validate(record,project_id,asset)
        for frame in value['frames']:frame_path(store.root,frame)
        observations.append(value)
    return {'project_id':project_id,'revision':project['revision'],'observations':observations,
        'pending_asset_ids':[asset['id'] for asset in pending(project['document'],project_id)],
        'semantic_provider_status':'NOT_CONFIGURED','provider_calls':0,'semantic_inference_performed':False}


def image_path(store,project_id,frame_id):
    bundle=view(store,project_id)
    for value in bundle['observations']:
        for frame in value['frames']:
            if frame['frame_id']==frame_id:return frame_path(store.root,frame)
    raise WorkflowError('MEDIA_FRAME_NOT_FOUND',404)


def asset_summary(document,project_id,asset,root):
    for record in reversed(document.get('media_frame_analyses',[])):
        value=record['observation']
        if value['asset_id']!=asset['id'] or value['source_sha256']!=asset['sha256']:continue
        validate(record,project_id,asset)
        for frame in value['frames']:frame_path(root,frame)
        measured=[MeasuredFrame(frame_id=frame['frame_id'],timestamp_seconds=frame['timestamp_seconds'],
            reference=frame['reference'],sha256=frame['sha256'],source_sha256=value['source_sha256'],
            provider=value['provider'],model=value['model'],pixel_facts=frame['pixel_facts']) for frame in value['frames']]
        return PixelAssetSummary(source_sha256=asset['sha256'],observation_sha256=record['sha256'],
            provider=value['provider'],model=value['model'],sample_count=len(measured),
            heuristic_quality_score=sum(frame.pixel_facts.heuristic_quality_score for frame in measured)/len(measured),
            black_sample_fraction=sum(frame.pixel_facts.black_sample for frame in measured)/len(measured),frames=measured)
    return None


def rebind_records(document,source_id,target_id):
    assets={asset['id']:asset for asset in project_assets(document)};output=[]
    for record in document.get('media_frame_analyses',[]):
        asset=assets.get(record['observation']['asset_id'])
        # Historical observations for removed/replaced assets are not transferable.
        if asset is None or record['observation']['source_sha256']!=asset['sha256']:continue
        original=validate(record,source_id,asset);changed=copy.deepcopy(original)
        key=fingerprint(target_id,asset)
        ids={frame['frame_id']:'mfr_'+digest([key,index])[:24] for index,frame in enumerate(changed['frames'])}
        changed.update(project_id=target_id,fingerprint=key,observation_id='mfo_'+key[:24],
            identity_rebinding={'source_project_id':source_id,'source_observation_id':original['observation_id'],
                'source_record_sha256':record['sha256'],'fresh_measurement':False})
        for frame in changed['frames']:
            frame['frame_id']=ids[frame['frame_id']]
            if frame['duplicate_sample_of']:frame['duplicate_sample_of']=ids[frame['duplicate_sample_of']]
        for field in ('best_frame_ids','thumbnail_candidate_ids'):changed[field]=[ids[item] for item in changed[field]]
        rebound={'observation':changed,'sha256':digest(changed)};validate(rebound,target_id,asset);output.append(rebound)
    return output


def analyze(config,job,out,stage):
    from PIL import Image
    from .source_render import command_run
    from hashlib import sha256
    document=job['snapshot']['document'];assets=pending(document,job['project_id'])[:16]
    if not assets:raise WorkflowError('MEDIA_FRAME_NO_PENDING_ASSET',400)
    artifacts=Artifacts(out,job)
    for asset in assets:checked_path(config,asset)
    cached=artifacts.load('media_frames')
    if cached:return cached['result']
    directory=out/'attempts'/('media-frames-'+uuid.uuid4().hex);directory.mkdir(parents=True)
    records=[];published=[]
    for asset in assets:
        path=checked_path(config,asset);key=fingerprint(job['project_id'],asset);frames=[];seen={}
        duration=float(asset.get('duration_seconds') or 0)
        if asset['kind']=='video' and not 0<duration<=3600:raise WorkflowError('MEDIA_FRAME_SOURCE_DURATION_INVALID',400)
        times=[duration*(index+.5)/FRAME_COUNT for index in range(FRAME_COUNT)] if asset['kind']=='video' else [0.]
        for index,timestamp in enumerate(times):
            stage('media_frame_local_pixel_sampling')
            identifier='mfr_'+digest([key,index])[:24];name='frame-'+identifier[4:]+'.png';target=directory/name
            command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-v','error','-nostdin','-n']
            if asset['kind']=='video':command+=['-ss',f'{timestamp:.9f}']
            command+=['-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1',
                '-vf',"scale=480:480:force_original_aspect_ratio=decrease:force_divisible_by=2,format=rgb24",str(target)]
            command_run(command,directory,'sampling.log',30,'MEDIA_FRAME_DECODE_FAILED')
            with Image.open(target) as image:
                image.load();rgb=image.convert('RGB');width,height=rgb.size
                pixels_sha=sha256(f'{width}x{height}:'.encode()+rgb.tobytes()).hexdigest()
                grid=rgb.convert('L').resize((64,64),Image.Resampling.BOX)
                facts=pixel_facts(grid.tobytes(),64,64)
            frame=FrameRead(frame_id=identifier,timestamp_seconds=timestamp,
                reference=f"media-frame://{job['id']}/{name}",sha256=file_sha(target),
                decoded_pixels_sha256=pixels_sha,width=width,height=height,pixel_facts=facts,
                duplicate_sample_of=seen.get(pixels_sha))
            seen.setdefault(pixels_sha,identifier);frames.append(frame)
            published.append(artifacts.publish(target,name))
        checked_path(config,asset)
        ranked=sorted((f for f in frames if not f.pixel_facts.black_sample and not f.duplicate_sample_of),
            key=lambda frame:(-frame.pixel_facts.heuristic_quality_score,frame.timestamp_seconds))
        value={'schema':SCHEMA,'observation_id':'mfo_'+key[:24],'fingerprint':key,'project_id':job['project_id'],
            'asset_id':asset['id'],'source_sha256':asset['sha256'],'job_id':job['id'],
            'provider':'local_ffmpeg_pillow_pixels','model':ALGORITHM,'created_at':datetime.now(timezone.utc).isoformat(),
            'semantic_provider_status':'NOT_CONFIGURED','semantic_inference_performed':False,'external_provider_calls':0,
            'confidence':None,'rights_status':'owner_upload_attestation' if asset.get('rights_confirmed') is True else 'unknown',
            'rights_independently_verified':False,'needs_attention':True,'frames':[f.model_dump(mode='json') for f in frames],
            'best_frame_ids':[frame.frame_id for frame in ranked[:3]],'thumbnail_candidate_ids':[frame.frame_id for frame in ranked[:3]],
            'ranking_basis':'uncalibrated sampled pixel sharpness/brightness heuristic; semantic relevance unknown',
            'frozen_video_detection_performed':False,'exact_sample_duplicate_detection':True}
        record={'observation':value,'sha256':digest(value)};validate(record,job['project_id'],asset);records.append(record)
    for asset in assets:checked_path(config,asset)
    result={'media_frame_analyses':records,'provider_calls':0,'paid_operations':0,'actual_local_compute_cost':None,
        'semantic_provider_status':'NOT_CONFIGURED','canonical_timeline_mutated':False}
    durable_json(directory/'media-frame-result.json',result)
    published.append(artifacts.publish(directory/'media-frame-result.json','media-frame-result.json'))
    artifacts.commit('media_frames',published,result)
    return result


def save_result(store,con,project,result,job_id):
    document=copy.deepcopy(project['document']);assets={asset['id']:asset for asset in project_assets(document)}
    incoming=result.get('media_frame_analyses',[])
    if not incoming or len(incoming)>16 or len({record['observation']['asset_id'] for record in incoming})!=len(incoming):
        raise WorkflowError('MEDIA_FRAME_RESULT_INVALID')
    history=document.get('media_frame_analyses',[])
    if len({record['observation']['observation_id'] for record in history+incoming})!=len(history+incoming):
        raise WorkflowError('MEDIA_FRAME_IMMUTABLE_RECORD_CONFLICT')
    if len(history)+len(incoming)>MAX_RECORDS:raise WorkflowError('MEDIA_FRAME_HISTORY_LIMIT')
    for record in incoming:
        if record['observation']['job_id']!=job_id or record['observation'].get('identity_rebinding'):
            raise WorkflowError('MEDIA_FRAME_RESULT_JOB_MISMATCH')
        asset=assets.get(record['observation']['asset_id'])
        if asset is None:raise WorkflowError('MEDIA_FRAME_SOURCE_BINDING_MISMATCH')
        validate(record,project['id'],asset)
        for frame in record['observation']['frames']:frame_path(store.root,frame)
    document['media_frame_analyses']=history+incoming
    from .auto_edit_analysis import _save
    _save(store,con,project,document,'media_frame_observations_saved',{'assets':len(incoming)},timeline_mutated=False)
