"""Checksum-bound CPU frame observations; no semantic provider is synthesized."""
import copy
from datetime import datetime,timezone
from pathlib import Path
import uuid
import json
import re
from typing import Literal
from pydantic import Field,model_validator
from .ingestion import API_ROOT
from .contracts import WorkflowError,digest,file_sha
from .media import project_assets,media_path
from .hardening import Artifacts,durable_json
from app.models import StrictModel
from app.media_frame_facts import ALGORITHM,PixelFacts,MeasuredFrame,PixelAssetSummary,pixel_facts
from app.decoded_frame_clock import DecodedFrameStamp,ALGORITHM as SAMPLER,BASIS,targets,select_filter,parse_showinfo

LEGACY_SCHEMA='native-media-frame-observations-v1'
SCHEMA='native-media-frame-observations-v2'
MAX_RECORDS=400
FRAME_COUNT=8


class FrameRead(StrictModel):
    frame_id:str=Field(pattern=r'^mfr_[a-f0-9]{24}$')
    timestamp_seconds:float=Field(ge=0,allow_inf_nan=False)
    timestamp_basis:Literal['requested_ffmpeg_source_seek; decoded_pts_unavailable','decoded_source_pts; copyts_start_at_zero','still_image']='requested_ffmpeg_source_seek; decoded_pts_unavailable'
    decoded_pts_seconds:float|None=Field(default=None,ge=0,allow_inf_nan=False)
    decoded_clock:DecodedFrameStamp|None=None
    reference:str=Field(pattern=r'^media-frame://[a-f0-9]{32}/frame-[a-f0-9]{24}\.png$')
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    decoded_pixels_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    width:int=Field(ge=1,le=7680)
    height:int=Field(ge=1,le=7680)
    pixel_facts:PixelFacts
    duplicate_sample_of:str|None=Field(default=None,pattern=r'^mfr_[a-f0-9]{24}$')

    @model_validator(mode='after')
    def coherent_clock(self):
        if self.timestamp_basis==BASIS:
            if (self.decoded_clock is None or self.decoded_pts_seconds!=self.timestamp_seconds
                or self.decoded_clock.timestamp_seconds!=self.timestamp_seconds
                or (self.decoded_clock.width,self.decoded_clock.height)!=(self.width,self.height)):
                raise ValueError('MEDIA_FRAME_DECODED_CLOCK_INVALID')
        elif self.decoded_clock is not None or self.decoded_pts_seconds is not None:
            raise ValueError('MEDIA_FRAME_UNVERIFIED_CLOCK_CANNOT_CLAIM_PTS')
        if self.timestamp_basis=='still_image' and self.timestamp_seconds!=0:
            raise ValueError('MEDIA_FRAME_STILL_IMAGE_TIME_INVALID')
        return self


class ClockEvidence(StrictModel):
    reference:str=Field(pattern=r'^media-clock://[a-f0-9]{32}/clock-[a-f0-9]{24}\.json$')
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    log_reference:str=Field(pattern=r'^media-clock://[a-f0-9]{32}/sampling-[a-f0-9]{24}\.log$')
    log_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    algorithm:Literal['single-decode-threshold-sampling-v1']
    requested_times:list[float]=Field(min_length=1,max_length=FRAME_COUNT)


class Rebinding(StrictModel):
    source_project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    source_observation_id:str=Field(pattern=r'^mfo_[a-f0-9]{24}$')
    source_record_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    fresh_measurement:Literal[False]=False


class Observation(StrictModel):
    schema_name:Literal['native-media-frame-observations-v1','native-media-frame-observations-v2']=Field(alias='schema')
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
    decoded_clock_evidence:ClockEvidence|None=None


def fingerprint(project_id,asset,*,schema=SCHEMA):
    value={'schema':schema,'project_id':project_id,'asset_id':asset['id'],
        'source_sha256':asset['sha256'],'algorithm':ALGORITHM,'frames':FRAME_COUNT,'pixel_grid':64}
    if schema==SCHEMA:value.update(sampling=SAMPLER,duration_seconds=asset.get('duration_seconds') if asset['kind']=='video' else None,
        video_stream_selector=video_stream_selector(asset) if asset['kind']=='video' else None)
    elif schema!=LEGACY_SCHEMA:raise WorkflowError('MEDIA_FRAME_SCHEMA_INVALID')
    return digest(value)


def video_stream_selector(asset):
    index=asset.get('video_stream_index')
    if index is None:return '0:v:0'
    if type(index) is not int or not 0<=index<=255:raise WorkflowError('MEDIA_FRAME_STREAM_SELECTOR_INVALID',400)
    return '0:'+str(index)


def validate(record,project_id,asset):
    if set(record)!={'observation','sha256'} or record['sha256']!=digest(record['observation']):
        raise WorkflowError('MEDIA_FRAME_RECORD_CHANGED')
    value=record['observation']
    try:Observation.model_validate(value)
    except ValueError:raise WorkflowError('MEDIA_FRAME_OBSERVATIONS_INVALID') from None
    if (value.get('schema') not in {SCHEMA,LEGACY_SCHEMA} or value.get('project_id')!=project_id or value.get('asset_id')!=asset['id']
            or value.get('source_sha256')!=asset['sha256'] or value.get('fingerprint')!=fingerprint(project_id,asset,schema=value.get('schema'))
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
    clock=value.get('decoded_clock_evidence')
    if value['schema']==LEGACY_SCHEMA:
        if clock is not None or any(f.timestamp_basis!='requested_ffmpeg_source_seek; decoded_pts_unavailable' for f in frames):raise WorkflowError('MEDIA_FRAME_LEGACY_CLOCK_CHANGED')
    elif asset['kind']=='video':
        if (clock is None or clock['requested_times']!=targets(float(duration),FRAME_COUNT)
            or any(f.timestamp_basis!=BASIS or f.decoded_clock.selected_ordinal!=i for i,f in enumerate(frames))
            or any(ref.split('/')[2]!=value['job_id'] for ref in (clock['reference'],clock['log_reference']))):raise WorkflowError('MEDIA_FRAME_DECODED_CLOCK_INVALID')
    elif clock is not None or len(frames)!=1 or frames[0].timestamp_basis!='still_image':raise WorkflowError('MEDIA_FRAME_DECODED_CLOCK_INVALID')
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


def verify_clock(root,value,*,require_job=True):
    """Physical clock manifest and original decoder log; clones retain same evidence."""
    evidence=value.get('decoded_clock_evidence')
    if evidence is None:return
    try:
        if type(require_job) is not bool:raise ValueError()
        def mounted(reference,expected):
            match=re.fullmatch(r'media-clock://([a-f0-9]{32})/((?:clock-[a-f0-9]{24}\.json)|(?:sampling-[a-f0-9]{24}\.log))',reference)
            if not match or match[1]!=value['job_id']:raise ValueError()
            directory=Path(root)/'jobs'/match[1];path=directory/match[2]
            if linked(directory) or linked(path) or path.resolve().parent!=directory.resolve() or not path.is_file() or file_sha(path)!=expected:raise ValueError()
            return path
        manifest=mounted(evidence['reference'],evidence['sha256']);log=mounted(evidence['log_reference'],evidence['log_sha256'])
        if manifest.stat().st_size>65536 or log.stat().st_size>1024*1024:raise ValueError()
        stamps=parse_showinfo(log.read_text(encoding='utf-8',errors='strict'),maximum_frames=FRAME_COUNT)
        expected={'schema_version':'native-source-decoded-clock-v1','algorithm':SAMPLER,'timestamp_basis':BASIS,
            'asset_id':value['asset_id'],'source_sha256':value['source_sha256'],'job_id':value['job_id'],
            'requested_times':evidence['requested_times'],'frames':[{'reference':f['reference'],'sha256':f['sha256'],'decoded_clock':f['decoded_clock']} for f in value['frames']]}
        if digest(json.loads(manifest.read_bytes()))!=digest(expected) or [s.model_dump(mode='json') for s in stamps]!=[f['decoded_clock'] for f in value['frames']]:raise ValueError()
        if require_job:
            import sqlite3
            database=Path(root)/'workflow.sqlite3'
            if linked(database) or not database.is_file() or database.resolve().parent!=Path(root).resolve() or database.stat().st_nlink!=1:raise ValueError()
            from contextlib import closing
            with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True)) as con:
                con.row_factory=sqlite3.Row;row=con.execute('SELECT * FROM jobs WHERE id=?',(value['job_id'],)).fetchone()
            if row is None or row['kind']!='media_frames' or row['status'] not in {'running','retrying','succeeded'}:raise ValueError()
            job=dict(row);job['snapshot']=json.loads(row['snapshot'])
            try:checkpoint=Artifacts(Path(root)/'jobs'/job['id'],job).load('media_frames')
            except WorkflowError as error:
                if error.code=='CHECKPOINT_ARTIFACT_CHANGED':raise WorkflowError('MEDIA_FRAME_ARTIFACT_CHANGED') from None
                raise
            if checkpoint is None or row['result'] is not None and digest(json.loads(row['result']))!=digest(checkpoint['result']):raise ValueError()
            origin=next((r['observation'] for r in checkpoint['result']['media_frame_analyses']
                if r['observation']['asset_id']==value['asset_id'] and r['observation']['source_sha256']==value['source_sha256']),None)
            if origin is None or origin.get('decoded_clock_evidence')!=evidence:raise ValueError()
            # Project duplication changes display identity; immutable measured bytes/clock do not transfer authority.
            def facts(v):return [{k:x for k,x in f.items() if k not in {'frame_id','duplicate_sample_of'}} for f in v['frames']]
            if digest(facts(origin))!=digest(facts(value)):raise ValueError()
    except WorkflowError as error:
        if error.code=='MEDIA_FRAME_ARTIFACT_CHANGED':raise
        raise WorkflowError('MEDIA_FRAME_CLOCK_EVIDENCE_CHANGED') from None
    except Exception:raise WorkflowError('MEDIA_FRAME_CLOCK_EVIDENCE_CHANGED') from None


def view(store,project_id):
    project=store.get(project_id);assets={a['id']:a for a in project_assets(project['document'])}
    observations=[]
    for record in project['document'].get('media_frame_analyses',[]):
        asset=assets.get(record['observation']['asset_id'])
        if asset is None or record['observation']['source_sha256']!=asset['sha256']:continue
        value=validate(record,project_id,asset)
        for frame in value['frames']:frame_path(store.root,frame)
        verify_clock(store.root,value)
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


def asset_summary(document,project_id,asset,root,*,verify_frames=True):
    # Historical consumers may reconstruct typed metadata from an immutable
    # project version; current media/ranking callers still verify physical PNGs.
    if type(verify_frames) is not bool:raise WorkflowError('MEDIA_FRAME_VERIFICATION_FLAG_INVALID')
    for record in reversed(document.get('media_frame_analyses',[])):
        value=record['observation']
        if value['asset_id']!=asset['id'] or value['source_sha256']!=asset['sha256']:continue
        validate(record,project_id,asset)
        if verify_frames:
            for frame in value['frames']:frame_path(root,frame)
            verify_clock(root,value)
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
        key=fingerprint(target_id,asset,schema=original['schema'])
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
        sample_dir=directory/key[:24];sample_dir.mkdir();stage('media_frame_local_pixel_sampling')
        size_filter='scale=480:480:force_original_aspect_ratio=decrease:force_divisible_by=2,format=rgb24'
        command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-n']
        if asset['kind']=='video':
            requested=targets(duration,FRAME_COUNT)
            command+=['-copyts','-start_at_zero','-protocol_whitelist','file,pipe','-i',str(path),'-map',video_stream_selector(asset),'-an',
                '-vf',select_filter(requested)+','+size_filter+',showinfo','-fps_mode','passthrough',
                '-frames:v',str(FRAME_COUNT+1),str(sample_dir/'decoded-%06d.png')]
        else:
            command+=['-protocol_whitelist','file,pipe','-i',str(path),'-frames:v','1','-vf',size_filter,str(sample_dir/'decoded-000001.png')]
        command_run(command,sample_dir,'sampling.log',180,'MEDIA_FRAME_DECODE_FAILED')
        decoded=sorted(sample_dir.glob('decoded-*.png'))
        if asset['kind']=='video':
            try:stamps=parse_showinfo((sample_dir/'sampling.log').read_text(encoding='utf-8'),maximum_frames=FRAME_COUNT)
            except ValueError:raise WorkflowError('MEDIA_FRAME_DECODED_CLOCK_INVALID') from None
            if len(stamps)!=len(decoded):raise WorkflowError('MEDIA_FRAME_DECODED_CLOCK_COUNT_MISMATCH')
        else:stamps=[None]
        if not 1<=len(decoded)<=FRAME_COUNT or len(decoded)!=len(stamps):raise WorkflowError('MEDIA_FRAME_DECODED_CLOCK_COUNT_MISMATCH')
        for index,(target,clock) in enumerate(zip(decoded,stamps,strict=True)):
            identifier='mfr_'+digest([key,index])[:24];name='frame-'+identifier[4:]+'.png'
            with Image.open(target) as image:
                image.load();rgb=image.convert('RGB');width,height=rgb.size
                pixels_sha=sha256(f'{width}x{height}:'.encode()+rgb.tobytes()).hexdigest()
                grid=rgb.convert('L').resize((64,64),Image.Resampling.BOX)
                facts=pixel_facts(grid.tobytes(),64,64)
            frame=FrameRead(frame_id=identifier,timestamp_seconds=clock.timestamp_seconds if clock else 0.,
                timestamp_basis=BASIS if clock else 'still_image',decoded_pts_seconds=clock.timestamp_seconds if clock else None,decoded_clock=clock,
                reference=f"media-frame://{job['id']}/{name}",sha256=file_sha(target),
                decoded_pixels_sha256=pixels_sha,width=width,height=height,pixel_facts=facts,
                duplicate_sample_of=seen.get(pixels_sha))
            seen.setdefault(pixels_sha,identifier);frames.append(frame)
            published.append(artifacts.publish(target,name))
        clock_evidence=None
        if asset['kind']=='video':
            log_name='sampling-'+key[:24]+'.log';clock_name='clock-'+key[:24]+'.json'
            log=artifacts.publish(sample_dir/'sampling.log',log_name);published.append(log)
            manifest={'schema_version':'native-source-decoded-clock-v1','algorithm':SAMPLER,'timestamp_basis':BASIS,
                'asset_id':asset['id'],'source_sha256':asset['sha256'],'job_id':job['id'],'requested_times':requested,
                'frames':[{'reference':f.reference,'sha256':f.sha256,'decoded_clock':f.decoded_clock.model_dump(mode='json')} for f in frames]}
            durable_json(sample_dir/clock_name,manifest);clock_file=artifacts.publish(sample_dir/clock_name,clock_name);published.append(clock_file)
            clock_evidence={'reference':f"media-clock://{job['id']}/{clock_name}",'sha256':file_sha(clock_file),
                'log_reference':f"media-clock://{job['id']}/{log_name}",'log_sha256':file_sha(log),'algorithm':SAMPLER,'requested_times':requested}
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
            'frozen_video_detection_performed':False,'exact_sample_duplicate_detection':True,'decoded_clock_evidence':clock_evidence}
        record={'observation':value,'sha256':digest(value)};validate(record,job['project_id'],asset);verify_clock(config.data_root,value,require_job=False);records.append(record)
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
        verify_clock(store.root,record['observation'])
    document['media_frame_analyses']=history+incoming
    from .auto_edit_analysis import _save
    _save(store,con,project,document,'media_frame_observations_saved',{'assets':len(incoming)},timeline_mutated=False)
