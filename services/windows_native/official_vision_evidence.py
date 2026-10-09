"""Explicit reviewed original Vision lineage; pure local planning, no provider job."""
import copy
from typing import Literal
from pydantic import Field,StrictBool,field_validator
from app.models import StrictModel
from app.broll_planner import tokens
from .contracts import WorkflowError,digest

SCHEMA='native-reviewed-vision-context-v1'

class ReviewedVision(StrictModel):
    vision_id:str=Field(pattern=r'^nvoi_[a-f0-9]{32}$')
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_reviewed_result:Literal[True]
    acknowledged_protocol_mock:StrictBool=False

    @field_validator('acknowledged_reviewed_result',mode='before')
    @classmethod
    def raw_review(cls,value):
        if value is not True:raise ValueError('Explicit reviewed-result acknowledgement required')
        return value

def content(value,request):
    """Called only with an original row validated by NativeOfficialVision.read."""
    result=value['result'];source=value['snapshot']['source'];snapshot=value['snapshot']
    if (value['status']!='succeeded' or result is None or request.vision_id!=value['vision_id']
        or request.expected_snapshot_sha256!=value['snapshot_sha256'] or request.expected_result_sha256!=value['result_sha256']):
        raise WorkflowError('NATIVE_REVIEWED_VISION_RESULT_CHANGED')
    if request.acknowledged_protocol_mock is not result['mock']:
        raise WorkflowError('NATIVE_REVIEWED_VISION_MOCK_ACK_REQUIRED')
    return {'schema_version':'native-reviewed-vision-item-v1','request':request.model_dump(mode='json'),
        'workspace_id':value['workspace_id'],'project_id':value['project_id'],'asset_id':source['asset']['id'],
        'source_sha256':source['asset']['sha256'],'source_observation_sha256':source['source_observation']['sha256'],
        'source_binding_sha256':digest(source),'input_binding_sha256':digest(snapshot['input_binding']),
        'response_id':value['response_id'],'response_sha256':result['response_sha256'],'cost_operation_id':value['cost_operation_id'],
        'original_approved_at':snapshot['approved_at'],'original_deadline':snapshot['deadline'],
        'provider':'openai-vision','model':'gpt-5-mini','mock':result['mock'],'semantic_inference_performed':result['semantic_inference_performed'],
        'frames':copy.deepcopy(result['frames']),'scenes':copy.deepcopy(result['scenes']),
        'best_frame_ids':list(result['best_frame_ids']),'thumbnail_candidate_ids':list(result['thumbnail_candidate_ids']),
        'source_frame_evidence':copy.deepcopy(snapshot['input_binding']['source_frame_evidence']),
        'calculated_usage_cost_vnd':result['calculated_usage_cost_vnd'],'observed_actual_billed_cost_vnd':None,
        'prediction_confidence_calibrated':False,'continuous_tracking_performed':False,'decoded_pts_verified':False,
        'automatic_application':False,'planning_authorizes_payment':False,'full_media_qc_replaced':False,
        'publishing_authorized':False,'owner_uat_accepted':False,'real_provider_tested':False}

def build_context(service,project,requests,*,source_con,current=True):
    """One caller transaction covers original lineage and current physical source."""
    from .official_vision import NativeOfficialVision
    from .vision_models import NativeVisionRequest
    from .vision_frame_bridge import NativeEvidenceFrameExtractor
    if (type(service) is not NativeOfficialVision or service.store.root.absolute()!=service.config.data_root.absolute()
        or type(current) is not bool or not isinstance(requests,list) or not 1<=len(requests)<=50
        or any(type(v) is not ReviewedVision for v in requests) or len({v.vision_id for v in requests})!=len(requests)):
        raise WorkflowError('NATIVE_REVIEWED_VISION_SELECTION_INVALID',400)
    try:
        if any(set(v.__dict__)-set(ReviewedVision.model_fields) for v in requests):raise ValueError()
        requests=[ReviewedVision.model_validate(v.model_dump(mode='python',warnings=False)) for v in requests]
    except Exception:raise WorkflowError('NATIVE_REVIEWED_VISION_SELECTION_INVALID',400) from None
    service.check();items=[]
    for request in requests:
        # Use the caller's connection: opening a nested BEGIN IMMEDIATE would deadlock.
        value=service.read(source_con,service.row(source_con,project['id'],request.vision_id))
        item=content(value,request)
        if current:
            source=service.vision.sources(project,NativeVisionRequest(revision=project['revision'],
                observation_ids=[value['snapshot']['request']['observation_id']],request_key='internal-reviewed-vision-context'))[0]
            if source!=value['snapshot']['source'] or NativeEvidenceFrameExtractor(service.store.root,service.config,project['id'],source).binding()!=value['snapshot']['input_binding']:
                raise WorkflowError('NATIVE_REVIEWED_VISION_SOURCE_CHANGED')
        items.append(item)
    if len({v['asset_id'] for v in items})!=len(items):raise WorkflowError('NATIVE_REVIEWED_VISION_DUPLICATE_ASSET',400)
    items.sort(key=lambda v:v['asset_id'])
    return {'schema_version':SCHEMA,'workspace_id':service.workspace,'project_id':project['id'],'items':items,
        'semantic_vision_used':any(not v['mock'] for v in items),'mock_present':any(v['mock'] for v in items),
        'recommendation_only':True,'automatic_application':False,'external_dispatches':0,'paid_operations':0,
        'original_provider_consent_renewed':False,'full_media_qc_replaced':False,'publishing_authorized':False,'owner_uat_accepted':False}

def validate_saved(service,project,value,*,source_con,current=False):
    try:
        requests=[ReviewedVision.model_validate(v['request']) for v in value['items']]
        expected=build_context(service,project,requests,source_con=source_con,current=current)
        # JSON equality also preserves raw boolean/number distinctions. Python
        # dict equality alone would equate a forged 0/1 with False/True.
        if digest(value)!=digest(expected):raise ValueError()
        return expected
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_REVIEWED_VISION_CONTEXT_INVALID') from None

def ranking_inputs(item):
    """Mocks remain visible lineage and supply no real semantic/quality signal."""
    if item['mock'] is True:return {'semantic_tokens':set(),'predicted_sample_quality':None,'uncalibrated_min_confidence':None,'basis':'protocol_mock_not_semantic_ranking'}
    if item['mock'] is not False or item['semantic_inference_performed'] is not True:raise WorkflowError('NATIVE_REVIEWED_VISION_CONTEXT_INVALID')
    descriptions=[]
    for frame in item['frames']:
        descriptions.extend(frame[k] for k in ('caption','scene_description','semantic_label','environment','action'))
        descriptions.extend(v['label'] for v in frame['objects']);descriptions.extend(v['text'] for v in frame['ocr'])
    for scene in item['scenes']:descriptions.extend([scene['semantic_label'],scene['description'],*scene['subjects']])
    frames=item['frames']
    return {'semantic_tokens':tokens(' '.join(descriptions)),
        'predicted_sample_quality':sum(v['quality']['quality_score'] for v in frames)/len(frames) if frames else None,
        'uncalibrated_min_confidence':min(v['confidence'] for v in frames) if frames else None,
        'basis':'reviewed_provider_labels_lexical_overlap_and_uncalibrated_predicted_sample_quality'}
