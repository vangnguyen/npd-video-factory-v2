"""Explicit use of an original saved scene recommendation; no provider consent."""
import copy
from typing import Literal
from pydantic import Field,field_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .official_vision_evidence import ReviewedVision
from .source_broll_vision import bind_reader,runtime

class Selection(StrictModel):
    recommendation_id:str=Field(pattern=r'^nscr_[a-f0-9]{32}$')
    expected_recommendation_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_reviewed_recommendation:Literal[True]
    acknowledged_protocol_mock:bool=Field(strict=True)

    @field_validator('acknowledged_reviewed_recommendation',mode='before')
    @classmethod
    def raw_review(cls,value):
        if value is not True:raise ValueError('Explicit recommendation review required')
        return value

def record_for(project,selection):
    record=next((v for v in project['document'].get('source_scene_recommendations',[])
        if v['recommendation']['recommendation_id']==selection.recommendation_id),None)
    if record is None:raise WorkflowError('NATIVE_SCENE_SELECTION_NOT_FOUND',404)
    if record['sha256']!=selection.expected_recommendation_sha256 or digest(record['recommendation'])!=record['sha256']:
        raise WorkflowError('NATIVE_SCENE_SELECTION_CHANGED')
    return record

def reader(store,config,project_id,selection,getter=None):
    if selection is None:return None
    record=record_for(store.get(project_id),selection)
    ref=ReviewedVision.model_validate(record['recommendation']['reviewed_vision']['items'][0]['request'])
    return bind_reader(store,config,project_id,requests=[ref],getter=getter)

def selected(store,config,project,selection,analysis_id,con,getter):
    from .scene_review import validate
    record=record_for(project,selection);value=record['recommendation']
    service=runtime(store,config,value['workspace_id'],getter)
    validate(store,config,project,record,service,con,current=True)
    if value['source']['analysis']['analysis_id']!=analysis_id or selection.acknowledged_protocol_mock is not value['reviewed_vision']['items'][0]['mock']:
        raise WorkflowError('NATIVE_SCENE_SELECTION_REVIEW_REQUIRED')
    return record

def lineage(record):
    value=record['recommendation'];item=value['reviewed_vision']['items'][0]
    return {'schema_version':'native-reviewed-scene-selection-v1','recommendation_id':value['recommendation_id'],
        'recommendation_sha256':record['sha256'],'source_project_id':value['project_id'],
        'source_analysis_id':value['source']['analysis']['analysis_id'],'original_vision_request':copy.deepcopy(item['request']),
        'original_response_id':item['response_id'],'original_response_sha256':item['response_sha256'],
        'original_cost_operation_id':item['cost_operation_id'],'mock_original_result':item['mock'],
        'semantic_vision_used':value['result']['semantic_vision_used'],'prediction_confidence_calibrated':False,
        'acknowledged_reviewed_recommendation':True,'recommendation_only':True,'provider_dispatches':0,
        'publishing_authorized':False,'owner_uat_accepted':False,'automatic_application':False}

def validate_timeline(document):
    """The proof identifies initial selection, never authority for later edits."""
    metadata=document['canonical_timeline']['snapshot']['metadata'];proof=metadata.get('reviewed_scene_selection')
    if proof is not None:
        try:
            record=next(v for v in document.get('source_scene_recommendations',[]) if v['recommendation']['recommendation_id']==proof['recommendation_id'])
            if digest(proof)!=digest(lineage(record)):raise ValueError()
            highlight=metadata.get('reviewed_highlight_id')
            if highlight is not None and highlight not in {v['highlight_id'] for v in record['recommendation']['result']['scene_ranking']}:raise ValueError()
        except Exception:raise WorkflowError('NATIVE_SCENE_SELECTION_LINEAGE_INVALID') from None
