"""Original reviewed sampled subject positions; no fabricated continuous track."""
import copy,json,re,uuid
from datetime import datetime
from app.auto_edit_models import MediaMetadata
from app.vision_models import VisionFrameRead,SubjectObservationRead,ReframeKeyframeRead
from app.vision_logic import build_reframe_plans,_bounded_ema
from app.timeline_reframe import crop_keyframes
from .contracts import WorkflowError,digest,canonical
from .official_vision_evidence import ReviewedVision,validate_saved
from .source_broll_vision import runtime
from .scene_review import source,prepare,binding

SCHEMA='native-reviewed-source-reframe-v1'

def plan(snapshot,reviewed,ratio,fingerprint):
    metadata=MediaMetadata.model_validate(snapshot['analysis']['source_media'])
    fallback=build_reframe_plans(frames=[],tracks=[],metadata=metadata,aspect_ratios=[ratio],manual_overrides=[],
        minimum_tracking_confidence=.6,subtitle_safe_area_bottom=.18,maximum_jump=.12,fingerprint=fingerprint)[0]
    item=reviewed['items'][0];samples=[]
    if item['mock'] is True:return fallback,samples,'protocol_mock_center_fallback'
    if item['mock'] is not False or item['semantic_inference_performed'] is not True:raise WorkflowError('AUTO_EDIT_REFRAME_VISION_INVALID')
    for raw in item['frames']:
        frame=VisionFrameRead.model_validate(raw);box=frame.composition.primary_subject_box
        if (box is None or frame.confidence<.6 or not frame.composition.safe_crop or frame.quality.black_frame
            or frame.quality.frozen_or_duplicate or frame.timestamp_seconds>=float(metadata.duration_seconds or 0)):
            return fallback,[],'insufficient_safe_sampled_subject_evidence_center_fallback'
        samples.append({'frame_id':frame.frame_id,'timestamp_seconds':frame.timestamp_seconds,
            'evidence_frame_reference':frame.evidence_frame_reference,'bounding_box':box.model_dump(mode='json'),
            'uncalibrated_prediction_confidence':frame.confidence})
    if not samples:return fallback,[],'no_sampled_subject_evidence_center_fallback'
    observations=[SubjectObservationRead(timestamp_seconds=v['timestamp_seconds'],bounding_box=v['bounding_box'],
        confidence=v['uncalibrated_prediction_confidence']) for v in samples]
    coordinates=_bounded_ema(observations,maximum_jump=.12,subtitle_safe_area_bottom=.18)
    keys=[ReframeKeyframeRead(time=t,x=round(x,6),y=round(y,6),scale=fallback.keyframes[0].scale) for t,x,y in coordinates]
    if keys[0].time>0:keys.insert(0,keys[0].model_copy(update={'time':0.}))
    end=round(max(0.,float(metadata.duration_seconds)-.001),3)
    if keys[-1].time<end:keys.append(keys[-1].model_copy(update={'time':end}))
    result=fallback.model_copy(update={'strategy':'subject_samples','keyframes':keys,'smoothing':'bounded_ema',
        'confidence':None,'fallback':'none','needs_attention':True,'subject_track_id':None})
    # Provider's generic safe_crop flag is not proof the requested crop fits a
    # subject. Refuse sampled paths that clip the predicted box after smoothing.
    crops={v['time']:v for v in crop_keyframes(result,metadata)}
    for sample in samples:
        crop=crops[sample['timestamp_seconds']];box=sample['bounding_box']
        if (box['x']<crop['x']-1e-6 or box['y']<crop['y']-1e-6 or box['x']+box['width']>crop['x']+crop['width']+1e-6
            or box['y']+box['height']>crop['y']+crop['height']+1e-6):
            return fallback,[],'predicted_subject_does_not_fit_requested_crop_center_fallback'
    return result,samples,'reviewed_sparse_subject_positions_uncalibrated_not_continuous_tracking'

def key(snapshot,reviewed,ratio):return digest({'schema':SCHEMA,'source':snapshot,'reviewed_vision':reviewed,'aspect_ratio':ratio})

def record(project,snapshot,reviewed,ratio):
    from .store import now
    fingerprint=key(snapshot,reviewed,ratio);value,samples,basis=plan(snapshot,reviewed,ratio,fingerprint)
    value={'schema_version':SCHEMA,'review_id':'nsrf_'+uuid.uuid4().hex,'project_id':project['id'],'workspace_id':reviewed['workspace_id'],
        'source_revision':project['revision'],'source_document_sha256':digest(project['document']),'source':snapshot,
        'reviewed_vision':reviewed,'aspect_ratio':ratio,'fingerprint':fingerprint,'plan':value.model_dump(mode='json'),
        'sample_evidence':samples,'confidence_basis':basis,'tracking_confidence':None,'prediction_confidence_calibrated':False,
        'continuous_tracking_performed':False,'decoded_pts_verified':False,'external_dispatches':0,'paid_operations':0,
        'publishing_authorized':False,'owner_uat_accepted':False,'created_at':now()}
    saved={'review':value,'sha256':digest(value)};records=project['document'].get('source_reframe_reviews',[])
    if len(records)>=100 or len(canonical(saved))>1024*1024 or len(canonical(records+[saved]))>16*1024*1024:
        raise WorkflowError('AUTO_EDIT_REFRAME_VISION_HISTORY_LIMIT',400)
    return saved

def lineage(saved):
    value=saved['review'];item=value['reviewed_vision']['items'][0]
    return {'schema_version':SCHEMA,'review_id':value['review_id'],'review_sha256':saved['sha256'],
        'source_project_id':value['project_id'],'original_vision_request':copy.deepcopy(item['request']),
        'original_response_id':item['response_id'],'original_response_sha256':item['response_sha256'],
        'original_cost_operation_id':item['cost_operation_id'],'mock_original_result':item['mock'],
        'confidence_basis':value['confidence_basis'],'tracking_confidence':None,'prediction_confidence_calibrated':False,
        'continuous_tracking_performed':False,'decoded_pts_verified':False,'provider_dispatches':0,'publishing_authorized':False,
        'owner_uat_accepted':False,'human_review_required':True}

def validate(store,project,saved,service,con):
    try:
        if set(saved)!={'review','sha256'} or digest(saved['review'])!=saved['sha256']:raise ValueError()
        value=saved['review'];snapshot=value['source'];reviewed=value['reviewed_vision']
        if (value['schema_version']!=SCHEMA or value['project_id']!=project['id'] or value['workspace_id']!=service.workspace
            or type(value['source_revision']) is not int or value['source_revision']<1
            or not re.fullmatch(r'nsrf_[a-f0-9]{32}',value['review_id']) or datetime.fromisoformat(value['created_at']).utcoffset() is None):raise ValueError()
        row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],value['source_revision'])).fetchone()
        document=json.loads(row['document'])
        if digest(document)!=value['source_document_sha256']:raise ValueError()
        original={'id':project['id'],'revision':value['source_revision'],'document':document}
        if digest(source(original,snapshot['analysis']['analysis_id'],store.root,physical=False))!=digest(snapshot):raise ValueError()
        validate_saved(service,project,reviewed,source_con=con);binding(service,project,snapshot,reviewed,con)
        fingerprint=key(snapshot,reviewed,value['aspect_ratio']);expected,samples,basis=plan(snapshot,reviewed,value['aspect_ratio'],fingerprint)
        expected_value={'schema_version':SCHEMA,'review_id':value['review_id'],'project_id':project['id'],'workspace_id':reviewed['workspace_id'],
            'source_revision':value['source_revision'],'source_document_sha256':digest(document),'source':snapshot,'reviewed_vision':reviewed,
            'aspect_ratio':value['aspect_ratio'],'fingerprint':fingerprint,'plan':expected.model_dump(mode='json'),
            'sample_evidence':samples,'confidence_basis':basis,'tracking_confidence':None,'prediction_confidence_calibrated':False,
            'continuous_tracking_performed':False,'decoded_pts_verified':False,'external_dispatches':0,'paid_operations':0,
            'publishing_authorized':False,'owner_uat_accepted':False,'created_at':value['created_at']}
        if digest(value)!=digest(expected_value):raise ValueError()
    except WorkflowError:raise
    except Exception:raise WorkflowError('AUTO_EDIT_REFRAME_VISION_HISTORY_INVALID') from None

def history(store,config,project,*,official_vision=None):
    records=project['document'].get('source_reframe_reviews',[]);readers={}
    if not isinstance(records,list) or len(records)>100:raise WorkflowError('AUTO_EDIT_REFRAME_VISION_HISTORY_INVALID')
    try:
        for saved in records:
            workspace=saved['review']['workspace_id']
            if workspace not in readers:readers[workspace]=runtime(store,config,workspace,official_vision)
        with store.transaction() as con:
            for saved in records:validate(store,project,saved,readers[saved['review']['workspace_id']],con)
    except WorkflowError:raise
    except Exception:raise WorkflowError('AUTO_EDIT_REFRAME_VISION_HISTORY_INVALID') from None

def validate_timeline(document):
    proof=document['canonical_timeline']['snapshot']['metadata'].get('reviewed_reframe_selection')
    if proof is None:return
    try:
        saved=next(v for v in document.get('source_reframe_reviews',[]) if v['review']['review_id']==proof['review_id'])
        if digest(proof)!=digest(lineage(saved)):raise ValueError()
    except Exception:raise WorkflowError('AUTO_EDIT_REFRAME_VISION_LINEAGE_INVALID') from None

def inherit(document,source_id,revision):
    records=document.pop('source_reframe_reviews',[])
    if records:document.setdefault('source_reframe_inherited_reviewed_history',[]).extend({'source_project_id':source_id,
        'source_revision':revision,'original_record':copy.deepcopy(v),'authority_transferred':False,'new_review_required':True} for v in records)
    meta=document.get('canonical_timeline',{}).get('snapshot',{}).get('metadata',{})
    proof=meta.pop('reviewed_reframe_selection',None)
    if proof is not None:
        meta['inherited_reviewed_reframe_selection']={'original_selection':proof,'authority_transferred':False,'new_review_required':True}
        saved=meta.get('source_reframe_plan',{})
        original=saved.pop('original_vision_lineage',None)
        if original is not None:saved['inherited_original_vision_lineage']={'original_selection':original,'authority_transferred':False,'new_review_required':True}
        saved['provider_status']='INHERITED_SAMPLE_GEOMETRY_REVIEW_REQUIRED'
