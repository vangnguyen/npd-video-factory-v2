"""Reviewable local source-pixel tracking jobs with decoded PTS and immutable frames."""
import copy,re,uuid,math
from pathlib import Path
from datetime import datetime,timezone
from pydantic import Field,StrictInt
from app.models import StrictModel
from app.local_subject_tracking import TrackingConfiguration,TrackingObservation,LocalTemplateTrackingProvider,ALGORITHM
from .contracts import WorkflowError,digest,file_sha
from .hardening import Artifacts
from .media_frame_analysis import checked_path,linked

SCHEMA='native-local-subject-tracking-v1'
MAX_SAMPLES=600
MAX_HISTORY=50


class Create(StrictModel):
    expected_version:StrictInt=Field(ge=1)
    analysis_id:str=Field(pattern=r'^ana_[a-f0-9]{24}$')
    configuration:TrackingConfiguration


def source(document,project_id,request):
    from .auto_edit_timeline import validate_document
    from .auto_edit_timeline import _selected
    state=validate_document(document)
    if state['version']!=request.expected_version:raise WorkflowError('LOCAL_TRACKING_TIMELINE_STALE')
    if state['snapshot']['metadata']['source_analysis_id']!=request.analysis_id:raise WorkflowError('LOCAL_TRACKING_MAIN_SOURCE_REQUIRED',400)
    analysis,asset=_selected(document,project_id,request.analysis_id)
    if asset['kind']!='video' or not 0<float(analysis.source_media.duration_seconds or 0)<=3600:raise WorkflowError('LOCAL_TRACKING_VIDEO_REQUIRED',400)
    return {'analysis_id':analysis.analysis_id,'analysis_sha256':digest(analysis.model_dump(mode='json')),'asset':copy.deepcopy(asset),
        'source_media':analysis.source_media.model_dump(mode='json'),'timeline_sha256':state['sha256']}


def fingerprint(project_id,snapshot,request):
    return digest({'schema':SCHEMA,'project_id':project_id,'source':snapshot,'request':request.model_dump(mode='json'),'algorithm':ALGORITHM,'maximum_samples':MAX_SAMPLES})


def validate(record,project_id):
    try:
        if set(record)!={'analysis','sha256'} or digest(record['analysis'])!=record['sha256']:raise ValueError()
        value=record['analysis'];request=Create.model_validate(value['request'])
        if (value['schema_version']!=SCHEMA or value['project_id']!=project_id or value['fingerprint']!=fingerprint(project_id,value['source'],request)
            or value['tracking_id']!='ltr_'+value['fingerprint'][:24] or value['provider']!=LocalTemplateTrackingProvider.provider_key or value['model']!=ALGORITHM
            or value['confidence'] is not None or value['semantic_inference_performed'] is not False or value['external_provider_calls']!=0
            or value['every_frame_tracking_performed'] is not False or value['decoded_pts_verified'] is not True or value['needs_attention'] is not True):raise ValueError()
        frames=value['frames']
        if not 1<=len(frames)<=MAX_SAMPLES or value['sample_count']!=len(frames):raise ValueError()
        previous=-1.
        for ordinal,frame in enumerate(frames):
            observation=TrackingObservation.model_validate(frame['observation']);name=f'frame-{ordinal:06d}.png'
            if (observation.timestamp_seconds<=previous or observation.timestamp_seconds>=value['source']['source_media']['duration_seconds']+.001
                or frame['reference']!=f"tracking-frame://{value['job_id']}/{name}" or not re.fullmatch(r'[a-f0-9]{64}',frame['sha256'])
                or type(frame['width']) is not int or type(frame['height']) is not int or not 16<=min(frame['width'],frame['height'])<=max(frame['width'],frame['height'])<=256):raise ValueError()
            previous=observation.timestamp_seconds
        status='tracked' if len(frames)>1 and all(f['observation']['status'] in ('seed','tracked') for f in frames) else 'fallback_required'
        if value['status']!=status or value['timestamps_basis']!='decoded source PTS after container start normalization':raise ValueError()
        return value
    except (KeyError,ValueError,TypeError):raise WorkflowError('LOCAL_TRACKING_EVIDENCE_CHANGED') from None


def frame_path(root,frame):
    match=re.fullmatch(r'tracking-frame://([a-f0-9]{32})/(frame-[0-9]{6}\.png)',frame.get('reference',''))
    if not match:raise WorkflowError('LOCAL_TRACKING_FRAME_REFERENCE_INVALID')
    directory=Path(root)/'jobs'/match[1];path=directory/match[2]
    if linked(directory) or linked(path) or path.resolve().parent!=directory.resolve() or not path.is_file() or file_sha(path)!=frame['sha256']:
        raise WorkflowError('LOCAL_TRACKING_FRAME_CHANGED')
    return path


def analyze(config,job,out,stage):
    from PIL import Image
    import numpy as np
    from .source_render import command_run
    request=Create.model_validate(job['snapshot']['tracking_request']);snapshot=source(job['snapshot']['document'],job['project_id'],request)
    asset=snapshot['asset'];path=checked_path(config,asset);artifacts=Artifacts(out,job)
    cached=artifacts.load('source_tracking')
    if cached:
        validate(cached['result']['source_tracking_analysis'],job['project_id'])
        for frame in cached['result']['source_tracking_analysis']['analysis']['frames']:frame_path(config.data_root,frame)
        return cached['result']
    directory=out/'attempts'/('source-tracking-'+uuid.uuid4().hex);directory.mkdir(parents=True)
    duration=float(snapshot['source_media']['duration_seconds'])
    interval=max(request.configuration.sample_interval_seconds,duration/(MAX_SAMPLES-2))
    stage('local_subject_tracking_decode')
    command=[str(config.ffmpeg_bin/'ffmpeg.exe'),'-hide_banner','-nostdin','-n','-copyts','-start_at_zero',
        '-protocol_whitelist','file,pipe','-i',str(path),'-map','0:v:0','-an',
        '-vf',f"select='isnan(prev_selected_t)+gte(t-prev_selected_t,{interval:.9f})',scale=256:256:force_original_aspect_ratio=decrease:force_divisible_by=2,format=gray,showinfo",
        '-fps_mode','passthrough','-frames:v',str(MAX_SAMPLES+1),str(directory/'decoded-%06d.png')]
    command_run(command,directory,'decode.log',180,'LOCAL_TRACKING_DECODE_FAILED')
    times=[float(t) for t in re.findall(r'\bn:\s*\d+\s+pts:\s*-?\d+\s+pts_time:\s*([-+0-9.e]+)',(directory/'decode.log').read_text(encoding='utf-8',errors='replace'))]
    files=sorted(directory.glob('decoded-*.png'))
    if (not files or len(files)!=len(times) or len(files)>MAX_SAMPLES or not all(math.isfinite(t) and t>=0 for t in times)
        or times[-1]>=duration+.001 or times[0]>interval+.25 or duration-times[-1]>2*interval+.25):raise WorkflowError('LOCAL_TRACKING_DECODE_PTS_COVERAGE_INVALID')
    model=LocalTemplateTrackingProvider(request.configuration);frames=[];published=[]
    for ordinal,(file,timestamp) in enumerate(zip(files,times)):
        stage('local_subject_tracking_measure')
        with Image.open(file) as image:
            if not 16<=min(image.size)<=max(image.size)<=256:raise WorkflowError('LOCAL_TRACKING_DECODE_GEOMETRY_INVALID')
            image.load();pixels=np.asarray(image.convert('L'));width,height=image.size
        try:observation=model.observe(pixels,timestamp)
        except ValueError:raise WorkflowError('LOCAL_TRACKING_PIXELS_OR_SEED_INVALID',400) from None
        name=f'frame-{ordinal:06d}.png';published.append(artifacts.publish(file,name))
        frames.append({'observation':observation.model_dump(mode='json'),'reference':f"tracking-frame://{job['id']}/{name}",
            'sha256':file_sha(file),'width':width,'height':height})
    checked_path(config,asset);key=fingerprint(job['project_id'],snapshot,request)
    value={'schema_version':SCHEMA,'tracking_id':'ltr_'+key[:24],'fingerprint':key,'project_id':job['project_id'],'job_id':job['id'],
        'source_revision':job['revision'],'source_document_sha256':digest(job['snapshot']['document']),'source':snapshot,'request':request.model_dump(mode='json'),
        'provider':model.provider_key,'model':ALGORITHM,'status':'tracked' if len(frames)>1 and all(f['observation']['status'] in ('seed','tracked') for f in frames) else 'fallback_required',
        'frames':frames,'sample_count':len(frames),'effective_sample_interval_seconds':interval,'timestamps_basis':'decoded source PTS after container start normalization',
        'decoded_pts_verified':True,'every_frame_tracking_performed':False,'temporal_template_tracking_performed':any(f['observation']['status'] in ('tracked','lost','ambiguous') for f in frames),
        'confidence':None,'semantic_inference_performed':False,'external_provider_calls':0,'needs_attention':True,
        'seed_origin':'explicit_editor_region_on_first_decoded_frame','confidence_basis':'measured template similarity; not calibrated confidence',
        'source_media_mutated':False,'publishing_authorized':False,'owner_uat_accepted':False,'created_at':datetime.now(timezone.utc).isoformat()}
    record={'analysis':value,'sha256':digest(value)};validate(record,job['project_id'])
    result={'source_tracking_analysis':record,'provider_calls':0,'local_template_tracking':True}
    from .hardening import durable_json
    durable_json(directory/'source-tracking-result.json',result)
    published.append(artifacts.publish(directory/'source-tracking-result.json','source-tracking-result.json'))
    artifacts.commit('source_tracking',published,result);return result


def save_result(store,con,project,result,job_id):
    record=result['source_tracking_analysis'];value=validate(record,project['id'])
    if value['job_id']!=job_id or value['source_revision']!=project['revision'] or value['source_document_sha256']!=digest(project['document']):raise WorkflowError('LOCAL_TRACKING_STALE_RESULT')
    for frame in value['frames']:frame_path(store.root,frame)
    history=project['document'].get('source_tracking_analyses',[])
    if len(history)>=MAX_HISTORY or any(v['analysis']['tracking_id']==value['tracking_id'] for v in history):raise WorkflowError('LOCAL_TRACKING_HISTORY_LIMIT_OR_CONFLICT')
    document=copy.deepcopy(project['document']);document['source_tracking_analyses']=history+[record]
    from .auto_edit_analysis import _save
    _save(store,con,project,document,'local_subject_tracking_saved',{'tracking_id':value['tracking_id']},timeline_mutated=False)


def read_saved(store,con,project,tracking_id,expected_sha256):
    record=next((v for v in project['document'].get('source_tracking_analyses',[]) if v['analysis']['tracking_id']==tracking_id),None)
    if record is None:raise WorkflowError('LOCAL_TRACKING_NOT_FOUND',404)
    value=validate(record,project['id'])
    if record['sha256']!=expected_sha256:raise WorkflowError('LOCAL_TRACKING_BINDING_STALE')
    row=con.execute('SELECT * FROM jobs WHERE id=?',(value['job_id'],)).fetchone()
    if row is None:raise WorkflowError('LOCAL_TRACKING_JOB_CHANGED')
    job=store.job(row,con)
    if job['project_id']!=project['id'] or job['kind']!='source_tracking' or job['status']!='succeeded' or job['result'].get('source_tracking_analysis')!=record:
        raise WorkflowError('LOCAL_TRACKING_JOB_CHANGED')
    request=Create.model_validate(value['request'])
    if source(job['snapshot']['document'],project['id'],request)!=value['source'] or digest(job['snapshot']['document'])!=value['source_document_sha256']:
        raise WorkflowError('LOCAL_TRACKING_SOURCE_CHANGED')
    from .auto_edit_timeline import _selected
    analysis,asset=_selected(project['document'],project['id'],value['source']['analysis_id'])
    if digest(analysis.model_dump(mode='json'))!=value['source']['analysis_sha256'] or digest(asset)!=digest(value['source']['asset']):raise WorkflowError('LOCAL_TRACKING_SOURCE_CHANGED')
    for frame in value['frames']:frame_path(store.root,frame)
    return record


def plan(value,ratio):
    from app.auto_edit_models import MediaMetadata
    from app.vision_models import SubjectObservationRead,ReframeKeyframeRead
    from app.vision_logic import build_reframe_plans,_bounded_ema
    from app.timeline_reframe import crop_keyframes
    metadata=MediaMetadata.model_validate(value['source']['source_media'])
    fallback=build_reframe_plans(frames=[],tracks=[],metadata=metadata,aspect_ratios=[ratio],manual_overrides=[],
        minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,maximum_jump=.12,fingerprint=value['fingerprint']+'-'+ratio)[0]
    if value['status']!='tracked':return fallback,'local_template_loss_or_ambiguity_center_fallback'
    samples=[SubjectObservationRead(timestamp_seconds=f['observation']['timestamp_seconds'],bounding_box=f['observation']['bounding_box'],
        confidence=max(0.,f['observation']['normalized_cross_correlation'])) for f in value['frames']]
    coordinates=_bounded_ema(samples,maximum_jump=.12,subtitle_safe_area_bottom=.18)
    keys=[ReframeKeyframeRead(time=t,x=round(x,6),y=round(y,6),scale=fallback.keyframes[0].scale) for t,x,y in coordinates]
    if keys[0].time>0:keys.insert(0,keys[0].model_copy(update={'time':0.}))
    end=max(0.,float(metadata.duration_seconds)-.001)
    if keys[-1].time<end:keys.append(keys[-1].model_copy(update={'time':end}))
    result=fallback.model_copy(update={'strategy':'subject_track','subject_track_id':value['tracking_id'],'keyframes':keys,
        'smoothing':'bounded_ema','confidence':None,'fallback':'none','needs_attention':True})
    crops={f['time']:f for f in crop_keyframes(result,metadata)}
    for sample in samples:
        crop=crops[sample.timestamp_seconds];box=sample.bounding_box
        if box.x<crop['x']-1e-6 or box.y<crop['y']-1e-6 or box.x+box.width>crop['x']+crop['width']+1e-6 or box.y+box.height>crop['y']+crop['height']+1e-6:
            return fallback,'local_tracked_subject_does_not_fit_smoothed_crop_center_fallback'
    return result,'decoded_sample_template_similarity_uncalibrated; motion_between_samples_unmeasured'


def selection(record):
    value=record['analysis']
    return {'schema_version':SCHEMA,'tracking_id':value['tracking_id'],'record_sha256':record['sha256'],'job_id':value['job_id'],
        'source_sha256':value['source']['asset']['sha256'],'confidence':None,'semantic_inference_performed':False,'human_review_required':True}


def validate_timeline(document):
    meta=document['canonical_timeline']['snapshot']['metadata'];proof=meta.get('local_tracking_selection')
    if proof is None:return
    try:
        record=next(v for v in document.get('source_tracking_analyses',[]) if v['analysis']['tracking_id']==proof['tracking_id'])
        value=validate(record,meta['native_project_id']);ratio=document['canonical_timeline']['snapshot']['aspect_ratio']
        expected,basis=plan(value,ratio)
        if proof!=selection(record) or meta['source_reframe_plan']['plan']!=expected.model_dump(mode='json') or meta['source_reframe_plan']['confidence_basis']!=basis:raise ValueError()
    except Exception:raise WorkflowError('LOCAL_TRACKING_TIMELINE_LINEAGE_CHANGED') from None


def inherit(document,source_id,revision):
    records=document.pop('source_tracking_analyses',[])
    if records:document.setdefault('source_tracking_inherited_history',[]).extend({'source_project_id':source_id,'source_revision':revision,
        'original_record':copy.deepcopy(v),'authority_transferred':False,'new_review_required':True} for v in records)
    meta=document.get('canonical_timeline',{}).get('snapshot',{}).get('metadata',{})
    proof=meta.pop('local_tracking_selection',None)
    if proof:meta['inherited_local_tracking_selection']={'original_selection':proof,'authority_transferred':False,'new_review_required':True}
    if proof:meta.get('source_reframe_plan',{}).update(provider_status='INHERITED_LOCAL_GEOMETRY_REVIEW_REQUIRED',fresh_provider_measurement=False)
