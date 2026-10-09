"""Saved source scene/highlight recommendations from original reviewed Vision.

No provider dispatch and no implicit timeline edit. The original analysis,
speech-protected edit decisions and provider journals remain independent.
"""
import copy,json,uuid
from types import SimpleNamespace
from pydantic import Field
from app.models import StrictModel
from app.auto_edit_models import AutoEditAnalysisRead
from app.auto_edit_logic import build_highlights
from app.scene_evidence import combine_scene_evidence
from .contracts import WorkflowError,digest,canonical
from .official_vision_evidence import ReviewedVision,build_context,validate_saved
from .source_broll_vision import runtime,bind_reader,ReviewedSceneView
from .auto_edit_timeline import _selected
from .media_frame_analysis import asset_summary

ALGORITHM='native-reviewed-scene-recommendations-v1'
MAX_HISTORY=100

class Create(StrictModel):
    revision:int=Field(strict=True,ge=1)
    analysis_id:str=Field(pattern=r'^ana_[a-f0-9]{24}$')
    reviewed_vision:ReviewedVision

def source(project,analysis_id,root,*,physical=True):
    analysis,asset=_selected(project['document'],project['id'],analysis_id)
    measured=asset_summary(project['document'],project['id'],asset,root,verify_frames=physical)
    return {'analysis':analysis.model_dump(mode='json'),'asset':copy.deepcopy(asset),
        'pixels':measured.model_dump(mode='json') if measured else None}

def prepare(service,project,snapshot,request,con):
    reviewed=build_context(service,project,[request],source_con=con)
    binding(service,project,snapshot,reviewed,con)
    return reviewed

def binding(service,project,snapshot,reviewed,con):
    if len(reviewed['items'])!=1:raise WorkflowError('NATIVE_SCENE_REVIEW_MAIN_SOURCE_REQUIRED',400)
    item=reviewed['items'][0];analysis=AutoEditAnalysisRead.model_validate(snapshot['analysis'])
    if item['asset_id']!=snapshot['asset']['id']:raise WorkflowError('NATIVE_SCENE_REVIEW_MAIN_SOURCE_REQUIRED',400)
    row=service.read(con,service.row(con,project['id'],item['request']['vision_id']));original=row['snapshot']['source']
    transcript=analysis.transcript
    expected={'transcript_id':transcript.transcript_id,'version':transcript.version,'sha256':digest(transcript.model_dump(mode='json'))} if transcript else None
    if digest(original['asset'])!=digest(snapshot['asset']) or digest(original['scenes'])!=digest([v.model_dump(mode='json') for v in analysis.scenes]) or original['transcript_ref']!=expected:
        raise WorkflowError('NATIVE_SCENE_REVIEW_ANALYSIS_TRANSCRIPT_CHANGED')

def recommendations(snapshot,reviewed):
    """Only genuinely nonmock original evidence may affect semantic scores."""
    analysis=AutoEditAnalysisRead.model_validate(snapshot['analysis']);item=reviewed['items'][0]
    vision=None if item['mock'] else ReviewedSceneView(vision_analysis_id=item['request']['vision_id'],frames=item['frames'],scenes=item['scenes'])
    pixels=snapshot['pixels']['frames'] if snapshot['pixels'] else ()
    scenes=[v.model_dump(mode='json') for v in combine_scene_evidence(analysis,SimpleNamespace(checksum_sha256=snapshot['asset']['sha256']),vision,pixel_frames=pixels)]
    for scene in scenes:
        scene['evidence'].update(transcript_segment_count=len(scene['evidence']['transcript_segment_ids']),
            reviewed_vision_recommendation_only=True,prediction_confidence_calibrated=False,
            source_frame_time_basis='sampled requested timestamp; decoded source PTS not verified')
    scored=build_highlights(scenes=scenes,top_k=len(scenes))
    for value in scored:
        scene=scenes[value['scene_ordinal']];value['scene_id']=scene['scene_id']
        value['highlight_id']='hig_'+digest([ALGORITHM,analysis.analysis_id,scene['scene_id']])[:24]
        value['evidence'].update(prediction_confidence_calibrated=False,recommendation_only=True,automatic_application=False,
            original_vision_id=item['request']['vision_id'],original_response_sha256=item['response_sha256'],mock_original_result=item['mock'])
    return {'scenes':scenes,'scene_ranking':scored,'highlights':scored[:5],
        'semantic_vision_used':not item['mock'],'prediction_confidence_calibrated':False,'continuous_tracking_performed':False,
        'decoded_source_pts_verified':False,'recommendation_only':True,'canonical_timeline_mutated':False,
        'silence_decisions_mutated':False,'publishing_authorized':False,'owner_uat_accepted':False,'real_provider_tested':False,
        'external_dispatches':0,'paid_operations':0,'full_media_qc_replaced':False}

def fingerprint(snapshot,reviewed):
    return digest({'algorithm':ALGORITHM,'source':snapshot,'reviewed_vision':reviewed})

def validate(store,config,project,record,service,con,*,current=False):
    try:
        if (not isinstance(record,dict) or set(record)!={'recommendation','sha256'} or digest(record['recommendation'])!=record['sha256']):raise ValueError()
        value=record['recommendation'];snapshot=value['source'];reviewed=value['reviewed_vision']
        if (set(value)!={'schema_version','recommendation_id','project_id','workspace_id','source_revision','source_document_sha256',
            'source','reviewed_vision','fingerprint','result','created_at'} or value['schema_version']!=ALGORITHM
            or value['project_id']!=project['id'] or value['workspace_id']!=service.workspace
            or type(value['source_revision']) is not int or value['source_revision']<1):raise ValueError()
        import re
        from datetime import datetime
        if not re.fullmatch(r'nscr_[a-f0-9]{32}',value['recommendation_id']) or datetime.fromisoformat(value['created_at']).utcoffset() is None:raise ValueError()
        row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],value['source_revision'])).fetchone()
        if row is None:raise ValueError()
        document=json.loads(row['document'])
        if digest(document)!=value['source_document_sha256']:raise ValueError()
        original={'id':project['id'],'document':document,'revision':value['source_revision']}
        expected=source(original,snapshot['analysis']['analysis_id'],store.root,physical=False)
        if digest(expected)!=digest(snapshot):raise ValueError()
        validate_saved(service,project,reviewed,source_con=con)
        binding(service,project,snapshot,reviewed,con)
        if value['fingerprint']!=fingerprint(snapshot,reviewed) or digest(value['result'])!=digest(recommendations(snapshot,reviewed)):raise ValueError()
        if current:
            actual=source(project,snapshot['analysis']['analysis_id'],store.root)
            request=ReviewedVision.model_validate(reviewed['items'][0]['request'])
            if digest(actual)!=digest(snapshot) or digest(prepare(service,project,actual,request,con))!=digest(reviewed):
                raise WorkflowError('NATIVE_SCENE_REVIEW_INPUT_CHANGED')
        return value
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_INVALID') from None

def create(store,config,project_id,body,*,official_vision=None):
    try:payload=Create.model_validate(body)
    except ValueError:raise WorkflowError('NATIVE_SCENE_REVIEW_REQUEST_INVALID',400) from None
    getter=bind_reader(store,config,project_id,requests=[payload.reviewed_vision],getter=official_vision)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);snapshot=source(project,payload.analysis_id,store.root)
        first=con.execute('SELECT workspace_id FROM native_official_vision_intents WHERE project_id=? AND vision_id=?',
            (project_id,payload.reviewed_vision.vision_id)).fetchone()
        if first is None:raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
        service=runtime(store,config,first['workspace_id'],getter);reviewed=prepare(service,project,snapshot,payload.reviewed_vision,con)
        key=fingerprint(snapshot,reviewed);records=project['document'].get('source_scene_recommendations',[])
        cached=next((v for v in records if v['recommendation']['fingerprint']==key),None)
        if cached is not None:validate(store,config,project,cached,service,con,current=True)
        else:
            if len(records)>=MAX_HISTORY:raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_LIMIT',400)
            from .store import now
            value={'schema_version':ALGORITHM,'recommendation_id':'nscr_'+uuid.uuid4().hex,'project_id':project_id,'workspace_id':service.workspace,
                'source_revision':project['revision'],'source_document_sha256':digest(project['document']),'source':snapshot,
                'reviewed_vision':reviewed,'fingerprint':key,'result':recommendations(snapshot,reviewed),'created_at':now()}
            record={'recommendation':value,'sha256':digest(value)}
            if len(canonical(record))>1024*1024 or len(canonical(records+[record]))>16*1024*1024:
                raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_LIMIT',400)
            document=copy.deepcopy(project['document']);document['source_scene_recommendations']=records+[record]
            con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
                (project['revision']+1,json.dumps(document,ensure_ascii=False),now(),project_id))
            store.version(con,project_id);store.event(con,project_id,'source_scene_recommendations_saved_review_required',{
                'recommendation_id':value['recommendation_id'],'sha256':record['sha256'],'provider_dispatches':0,'canonical_timeline_mutated':False,
                'silence_decisions_mutated':False,'approval_invalidated':True})
    return page(store,config,project_id,official_vision=official_vision)

def page(store,config,project_id,*,official_vision=None):
    project=store.get(project_id);records=project['document'].get('source_scene_recommendations',[]);readers={}
    if not isinstance(records,list) or len(records)>MAX_HISTORY:raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_INVALID')
    try:
        for record in records:
            workspace=record['recommendation']['workspace_id']
            if workspace not in readers:readers[workspace]=runtime(store,config,workspace,official_vision)
        with store.transaction() as con:
            for record in records:validate(store,config,project,record,readers[record['recommendation']['workspace_id']],con)
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_INVALID') from None
    return {'schema_version':'native-reviewed-scene-page-v1','project_id':project_id,'revision':project['revision'],'items':copy.deepcopy(records),
        'provider_dispatches':0,'canonical_timeline_mutated':False,'silence_decisions_mutated':False,'recommendation_only':True,
        'publishing_enabled':False,'owner_uat_accepted':False,'real_provider_tested':False}
