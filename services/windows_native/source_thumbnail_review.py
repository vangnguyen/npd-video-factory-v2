"""Explicit original Source thumbnail suggestions; no publication or QC authority."""
import copy,json,re,uuid
from datetime import datetime
from typing import Literal
from pydantic import Field,StrictBool,field_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest,canonical
from .official_vision_evidence import ReviewedVision,validate_saved
from .scene_review import source,prepare,binding
from .source_broll_vision import runtime,bind_reader

SCHEMA='native-reviewed-source-thumbnail-v1'
MAX_HISTORY=100

class Create(StrictModel):
    revision:int=Field(strict=True,ge=1)
    analysis_id:str=Field(pattern=r'^ana_[a-f0-9]{24}$')
    reviewed_vision:ReviewedVision

class Select(StrictModel):
    revision:int=Field(strict=True,ge=1)
    recommendation_id:str=Field(pattern=r'^nstr_[a-f0-9]{32}$')
    expected_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    frame_id:str=Field(pattern=r'^mfr_[a-f0-9]{24}$')
    acknowledged_thumbnail:Literal[True]
    acknowledged_protocol_mock:StrictBool=False

    @field_validator('acknowledged_thumbnail',mode='before')
    @classmethod
    def raw_review(cls,value):
        if value is not True:raise ValueError('Explicit thumbnail review required')
        return value

def candidates(snapshot,reviewed):
    item=reviewed['items'][0];mock=item['mock'];output=[]
    if type(mock) is not bool or not mock and item['semantic_inference_performed'] is not True:
        raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_CONTEXT_INVALID')
    predictions={(v['evidence_frame_reference'],v['timestamp_seconds']):v for v in item['frames']}
    seen=set()
    for frame in item['source_frame_evidence']:
        if frame['pixel_facts']['black_sample'] or frame['decoded_pixels_sha256'] in seen:continue
        seen.add(frame['decoded_pixels_sha256'])
        predicted=predictions.get((frame['reference'],frame['timestamp_seconds']))
        if predicted is None:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_FRAME_BINDING_INVALID')
        if not mock and (predicted['quality']['black_frame'] or predicted['quality']['frozen_or_duplicate']):continue
        output.append({'frame_id':frame['frame_id'],'source_frame':copy.deepcopy(frame),
            'pixel_quality_heuristic':frame['pixel_facts']['heuristic_quality_score'],
            'original_vision_frame_id':predicted['frame_id'],
            'provider_thumbnail_suggestion':None if mock else predicted['frame_id'] in item['thumbnail_candidate_ids'],
            'predicted_sample_quality':None if mock else predicted['quality']['quality_score'],
            'uncalibrated_prediction_confidence':None if mock else predicted['confidence'],
            'provider_caption':None if mock else predicted['caption'],
            'predicted_watermark_or_logo':None if mock else predicted['quality']['watermark_or_logo_detected'],
            'confidence':None,'needs_attention':True,'publishing_authorized':False,'full_media_qc_replaced':False,
            'basis':'measured sampled pixel heuristic only; mock semantics excluded' if mock else
                'original provider suggestion and uncalibrated sampled quality, then measured pixel heuristic'})
    output.sort(key=lambda v:(-(v['provider_thumbnail_suggestion'] or False),-(v['predicted_sample_quality'] or 0),
        -v['pixel_quality_heuristic'],v['source_frame']['timestamp_seconds'],v['frame_id']))
    return [{**v,'rank':i+1} for i,v in enumerate(output[:3])]

def fingerprint(snapshot,reviewed):return digest({'schema':SCHEMA,'source':snapshot,'reviewed_vision':reviewed})

def validate(store,project,saved,service,con,*,current=False):
    try:
        if set(saved)!={'recommendation','sha256'} or digest(saved['recommendation'])!=saved['sha256']:raise ValueError()
        v=saved['recommendation'];snapshot=v['source'];context=v['reviewed_vision']
        if (v['schema_version']!=SCHEMA or v['project_id']!=project['id'] or v['workspace_id']!=service.workspace
            or type(v['source_revision']) is not int or v['source_revision']<1
            or not re.fullmatch(r'nstr_[a-f0-9]{32}',v['recommendation_id']) or datetime.fromisoformat(v['created_at']).utcoffset() is None):raise ValueError()
        row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],v['source_revision'])).fetchone()
        document=json.loads(row['document'])
        if digest(document)!=v['source_document_sha256']:raise ValueError()
        original={'id':project['id'],'revision':v['source_revision'],'document':document}
        if digest(source(original,snapshot['analysis']['analysis_id'],store.root,physical=False))!=digest(snapshot):raise ValueError()
        validate_saved(service,project,context,source_con=con);binding(service,project,snapshot,context,con)
        expected={'schema_version':SCHEMA,'recommendation_id':v['recommendation_id'],'project_id':project['id'],
            'workspace_id':service.workspace,'source_revision':v['source_revision'],'source_document_sha256':digest(document),
            'source':snapshot,'reviewed_vision':context,'fingerprint':fingerprint(snapshot,context),'candidates':candidates(snapshot,context),
            'external_dispatches':0,'paid_operations':0,'canonical_timeline_mutated':False,'full_media_qc_replaced':False,
            'publishing_authorized':False,'owner_uat_accepted':False,'created_at':v['created_at']}
        if digest(v)!=digest(expected):raise ValueError()
        if current:
            actual=source(project,snapshot['analysis']['analysis_id'],store.root)
            request=ReviewedVision.model_validate(context['items'][0]['request'])
            if digest(actual)!=digest(snapshot) or digest(prepare(service,project,actual,request,con))!=digest(context):
                raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_INPUT_CHANGED')
        return v
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_HISTORY_INVALID') from None

def readers(store,config,project,getter=None):
    if config.data_root.absolute()!=store.root.absolute():raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_SCOPE_INVALID')
    records=project['document'].get('source_thumbnail_reviews',[]);values={}
    if not isinstance(records,list) or len(records)>MAX_HISTORY:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_HISTORY_INVALID')
    try:
        for saved in records:
            workspace=saved['recommendation']['workspace_id']
            if workspace not in values:values[workspace]=runtime(store,config,workspace,getter)
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_HISTORY_INVALID') from None
    return values

def selection(saved,frame_id):
    v=saved['recommendation'];candidate=next((c for c in v['candidates'] if c['frame_id']==frame_id),None)
    if candidate is None:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_CANDIDATE_REQUIRED',400)
    item=v['reviewed_vision']['items'][0]
    return {'schema_version':SCHEMA,'recommendation_id':v['recommendation_id'],'recommendation_sha256':saved['sha256'],
        'frame_id':frame_id,'candidate_sha256':digest(candidate),'source_asset_id':v['source']['asset']['id'],
        'original_vision_id':item['request']['vision_id'],'original_response_id':item['response_id'],
        'original_response_sha256':item['response_sha256'],'original_cost_operation_id':item['cost_operation_id'],
        'mock_original_result':item['mock'],'acknowledged_thumbnail':True,'acknowledged_protocol_mock':item['mock'],
        'confidence':None,'publishing_authorized':False,'full_media_qc_replaced':False,'owner_uat_accepted':False}

def validate_selection(project):
    selected=project['document'].get('source_thumbnail_selection')
    if selected is None:return None
    try:
        saved=next(v for v in project['document'].get('source_thumbnail_reviews',[]) if v['recommendation']['recommendation_id']==selected['recommendation_id'])
        if digest(selected)!=digest(selection(saved,selected['frame_id'])):raise ValueError()
        return saved
    except Exception:raise WorkflowError('NATIVE_THUMBNAIL_SELECTION_INVALID') from None

def page(store,config,project_id,*,official_vision=None):
    project=store.get(project_id);services=readers(store,config,project,official_vision)
    with store.transaction() as con:
        for saved in project['document'].get('source_thumbnail_reviews',[]):
            validate(store,project,saved,services[saved['recommendation']['workspace_id']],con)
    validate_selection(project)
    return {'schema_version':'native-reviewed-source-thumbnail-page-v1','project_id':project_id,'revision':project['revision'],
        'items':copy.deepcopy(project['document'].get('source_thumbnail_reviews',[])),
        'selection':copy.deepcopy(project['document'].get('source_thumbnail_selection')),
        'provider_dispatches':0,'canonical_timeline_mutated':False,'publishing_authorized':False,'full_media_qc_replaced':False}

def save(store,con,project,document,action,evidence):
    from .store import now
    con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
        (project['revision']+1,json.dumps(document,ensure_ascii=False),now(),project['id']))
    store.version(con,project['id']);store.event(con,project['id'],action,{**evidence,'provider_dispatches':0,
        'canonical_timeline_mutated':False,'approval_invalidated':True,'publishing_authorized':False})

def create(store,config,project_id,body,*,official_vision=None):
    try:payload=Create.model_validate(body)
    except ValueError:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_REQUEST_INVALID',400) from None
    getter=bind_reader(store,config,project_id,requests=[payload.reviewed_vision],getter=official_vision)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);snapshot=source(project,payload.analysis_id,store.root)
        row=con.execute('SELECT workspace_id FROM native_official_vision_intents WHERE project_id=? AND vision_id=?',
            (project_id,payload.reviewed_vision.vision_id)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
        service=runtime(store,config,row['workspace_id'],getter);reviewed=prepare(service,project,snapshot,payload.reviewed_vision,con)
        key=fingerprint(snapshot,reviewed);records=project['document'].get('source_thumbnail_reviews',[])
        if not isinstance(records,list) or len(records)>MAX_HISTORY:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_HISTORY_INVALID')
        for saved in records:validate(store,project,saved,service,con)
        cached=next((v for v in records if v['recommendation']['fingerprint']==key),None)
        if cached is not None:validate(store,project,cached,service,con,current=True)
        else:
            from .store import now
            v={'schema_version':SCHEMA,'recommendation_id':'nstr_'+uuid.uuid4().hex,'project_id':project_id,'workspace_id':service.workspace,
                'source_revision':project['revision'],'source_document_sha256':digest(project['document']),'source':snapshot,
                'reviewed_vision':reviewed,'fingerprint':key,'candidates':candidates(snapshot,reviewed),'external_dispatches':0,'paid_operations':0,
                'canonical_timeline_mutated':False,'full_media_qc_replaced':False,'publishing_authorized':False,'owner_uat_accepted':False,'created_at':now()}
            saved={'recommendation':v,'sha256':digest(v)}
            if len(records)>=MAX_HISTORY or len(canonical(saved))>1024*1024 or len(canonical(records+[saved]))>16*1024*1024:
                raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_HISTORY_LIMIT',400)
            document=copy.deepcopy(project['document']);document['source_thumbnail_reviews']=records+[saved]
            save(store,con,project,document,'source_thumbnail_candidates_saved_review_required',{'recommendation_id':v['recommendation_id'],'sha256':saved['sha256']})
    return page(store,config,project_id,official_vision=official_vision)

def select(store,config,project_id,body,*,official_vision=None):
    try:payload=Select.model_validate(body)
    except ValueError:raise WorkflowError('NATIVE_THUMBNAIL_SELECTION_REQUEST_INVALID',400) from None
    previous=store.get(project_id);services=readers(store,config,previous,official_vision)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision)
        if digest(project['document'])!=digest(previous['document']):raise WorkflowError('STALE_VERSION_RELOAD')
        for old in project['document'].get('source_thumbnail_reviews',[]):validate(store,project,old,services[old['recommendation']['workspace_id']],con)
        saved=next((v for v in project['document'].get('source_thumbnail_reviews',[]) if v['recommendation']['recommendation_id']==payload.recommendation_id),None)
        if saved is None:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_NOT_FOUND',404)
        if saved['sha256']!=payload.expected_sha256:raise WorkflowError('NATIVE_THUMBNAIL_REVIEW_CHANGED')
        validate(store,project,saved,services[saved['recommendation']['workspace_id']],con,current=True)
        chosen=selection(saved,payload.frame_id)
        if payload.acknowledged_protocol_mock is not chosen['mock_original_result']:raise WorkflowError('NATIVE_THUMBNAIL_MOCK_ACK_REQUIRED')
        if digest(project['document'].get('source_thumbnail_selection'))!=digest(chosen):
            document=copy.deepcopy(project['document']);document['source_thumbnail_selection']=chosen
            save(store,con,project,document,'source_thumbnail_selected_review_required',chosen)
    return page(store,config,project_id,official_vision=official_vision)

def selected_image(store,config,project):
    saved=validate_selection(project)
    if saved is None:return None
    services=readers(store,config,project)
    with store.transaction() as con:validate(store,project,saved,services[saved['recommendation']['workspace_id']],con,current=True)
    chosen=project['document']['source_thumbnail_selection'];candidate=next(v for v in saved['recommendation']['candidates'] if v['frame_id']==chosen['frame_id'])
    from .media_frame_analysis import frame_path
    from .project_thumbnail import image
    frame=candidate['source_frame'];return image(frame_path(store.root,frame),store.root/'jobs',expected_size=(frame['width'],frame['height']))

def inherit(document,source_id,revision):
    records=document.pop('source_thumbnail_reviews',[]);chosen=document.pop('source_thumbnail_selection',None)
    if records:document.setdefault('source_thumbnail_inherited_reviewed_history',[]).extend({'source_project_id':source_id,
        'source_revision':revision,'original_record':copy.deepcopy(v),'authority_transferred':False,'new_review_required':True} for v in records)
    if chosen is not None:document['source_thumbnail_inherited_selection']={'original_selection':chosen,'authority_transferred':False,'new_review_required':True}
