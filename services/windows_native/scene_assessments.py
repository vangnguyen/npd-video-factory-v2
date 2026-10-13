"""Immutable Native current-evidence assessments; original analysis stays intact."""
import copy,json,re,uuid
from datetime import datetime
from pydantic import Field,model_validator
from app.models import StrictModel
from app.auto_edit_models import AutoEditAnalysisRead
from app.scene_assessment_logic import assess,ALGORITHM
from .contracts import WorkflowError,digest,canonical

MAX_HISTORY=50
FIELD='source_scene_assessments'

class Create(StrictModel):
    revision:int=Field(ge=1,strict=True)
    analysis_id:str=Field(pattern=r'^ana_[a-f0-9]{24}$')
    asset_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    analysis_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_transcript_id:str|None=Field(default=None,pattern=r'^trn_[a-f0-9]{24}$')
    expected_transcript_version:int|None=Field(default=None,ge=1,strict=True)
    expected_transcript_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    expected_timeline_version:int|None=Field(default=None,ge=1,strict=True)
    acknowledged_saved_evidence:bool=Field(strict=True)
    @model_validator(mode='after')
    def acknowledged(self):
        if not self.acknowledged_saved_evidence:raise ValueError('explicit saved-evidence acknowledgement required')
        if len({v is None for v in (self.expected_transcript_id,self.expected_transcript_version,self.expected_transcript_sha256)})!=1:
            raise ValueError('transcript reference must be complete or absent')
        return self

class Selection(StrictModel):
    assessment_id:str=Field(pattern=r'^nsci_[a-f0-9]{32}$')
    expected_assessment_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged:bool=Field(strict=True)
    @model_validator(mode='after')
    def reviewed(self):
        if not self.acknowledged:raise ValueError('explicit recommendation review required')
        return self

def source(project,analysis_id,root,*,physical):
    from .scene_review import source as original_source
    snapshot=original_source(project,analysis_id,root,physical=physical)
    if physical:
        from .media import _verify_library_record
        _verify_library_record(type('Library',(),{'root':root})(),{'metadata':snapshot['asset'],'metadata_conflict':False})
    return snapshot

def refs(project,snapshot):
    record=next(r for r in project['document']['auto_edit_analyses'] if r['analysis']['analysis_id']==snapshot['analysis']['analysis_id'])
    transcript=snapshot['analysis'].get('transcript');asset=snapshot['asset']
    return {'analysis_id':snapshot['analysis']['analysis_id'],'asset_id':asset['id'],'asset_sha256':asset['sha256'],
        'analysis_sha256':record['sha256'],'transcript_id':transcript['transcript_id'] if transcript else None,
        'transcript_version':transcript['version'] if transcript else None,'transcript_sha256':digest(transcript) if transcript else None}

def fingerprint(snapshot):return digest({'algorithm':ALGORITHM,'source':snapshot})

def result(snapshot,key):
    value=assess(AutoEditAnalysisRead.model_validate(snapshot['analysis']),snapshot['asset']['sha256'],
        pixel_frames=snapshot['pixels']['frames'] if snapshot['pixels'] else ())
    for item in value['scene_ranking']:
        item['highlight_id']='hig_'+digest([ALGORITHM,key,item['scene_id']])[:24]
    return value

def validate(store,project,record,con,*,current=False):
    try:
        if not isinstance(record,dict) or set(record)!={'assessment','sha256'} or digest(record['assessment'])!=record['sha256']:raise ValueError()
        value=record['assessment']
        if set(value)!={'schema_version','assessment_id','version','project_id','workspace_id','source_revision','source_document_sha256',
            'input_refs','input_sha256','algorithm','result','recommendation_only','semantic_vision_state','actor_ref','created_at'}:raise ValueError()
        if value['schema_version']!='native-current-scene-assessment.v1' or value['algorithm']!=ALGORITHM or value['project_id']!=project['id']:
            raise ValueError()
        if not re.fullmatch(r'nsci_[a-f0-9]{32}',value['assessment_id']) or type(value['version']) is not int or value['version']<1:
            raise ValueError()
        if type(value['source_revision']) is not int or value['source_revision']<1 or datetime.fromisoformat(value['created_at']).utcoffset() is None:
            raise ValueError()
        if value['recommendation_only'] is not True or value['semantic_vision_state']!='NOT_CONFIGURED':raise ValueError()
        row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],value['source_revision'])).fetchone()
        if row is None:raise ValueError()
        document=json.loads(row['document'])
        if digest(document)!=value['source_document_sha256']:raise ValueError()
        historical={'id':project['id'],'revision':value['source_revision'],'document':document}
        snapshot=source(historical,value['input_refs']['analysis_id'],store.root,physical=False)
        if refs(historical,snapshot)!=value['input_refs'] or fingerprint(snapshot)!=value['input_sha256'] or result(snapshot,value['input_sha256'])!=value['result']:
            raise ValueError()
        if current:
            actual=source(project,value['input_refs']['analysis_id'],store.root,physical=True)
            if fingerprint(actual)!=value['input_sha256']:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_INPUT_CHANGED')
        return value
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_HISTORY_INVALID') from None

def page(store,project_id,workspace):
    project=store.get(project_id);records=project['document'].get(FIELD,[])
    if not isinstance(records,list) or len(records)>MAX_HISTORY:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_HISTORY_INVALID')
    available=[];keys={}
    for record in project['document'].get('auto_edit_analyses',[]):
        try:
            snapshot=source(project,record['analysis']['analysis_id'],store.root,physical=True)
        except WorkflowError:continue
        ref=refs(project,snapshot);available.append({**ref,'filename':snapshot['asset'].get('filename',ref['asset_id'])})
        keys[ref['analysis_id']]=fingerprint(snapshot)
    items=[]
    with store.transaction() as con:
        for record in records:
            value=validate(store,project,record,con)
            if value['workspace_id']!=workspace:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_WORKSPACE_CHANGED')
            items.append({**copy.deepcopy(record),'current':keys.get(value['input_refs']['analysis_id'])==value['input_sha256']})
    return {'schema_version':'native-current-scene-page.v1','workspace_id':workspace,'project_id':project_id,
        'revision':project['revision'],'timeline_version':(project['document'].get('canonical_timeline') or {}).get('version'),
        'available_sources':available,'items':items,'provider_calls':0,'source_media_mutated':False,
        'canonical_timeline_mutated':False,'publishing_enabled':False}

def create(store,project_id,body,*,workspace,actor_ref):
    try:payload=Create.model_validate(body)
    except ValueError:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_REQUEST_INVALID',400) from None
    if not isinstance(actor_ref,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,160}',actor_ref):
        raise WorkflowError('NATIVE_SCENE_ASSESSMENT_ACTOR_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,payload.revision);document=project['document']
        if document.get('input_kind')!='media' or document.get('proposal') is not None:
            raise WorkflowError('AUTO_EDIT_SEPARATE_MEDIA_PROJECT_REQUIRED',400)
        if payload.expected_timeline_version!=(document.get('canonical_timeline') or {}).get('version'):
            raise WorkflowError('NATIVE_SCENE_ASSESSMENT_TIMELINE_CHANGED')
        snapshot=source(project,payload.analysis_id,store.root,physical=True);ref=refs(project,snapshot)
        expected={'asset_sha256':payload.asset_sha256,'analysis_sha256':payload.analysis_sha256,
            'transcript_id':payload.expected_transcript_id,'transcript_version':payload.expected_transcript_version,
            'transcript_sha256':payload.expected_transcript_sha256}
        if any(ref[k]!=v for k,v in expected.items()):raise WorkflowError('NATIVE_SCENE_ASSESSMENT_INPUT_CHANGED')
        key=fingerprint(snapshot);records=document.get(FIELD,[])
        if not isinstance(records,list) or len(records)>MAX_HISTORY:
            raise WorkflowError('NATIVE_SCENE_ASSESSMENT_HISTORY_INVALID')
        for historical in records:
            value=validate(store,project,historical,con)
            if value['workspace_id']!=workspace:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_WORKSPACE_CHANGED')
        cached=next((r for r in records if r['assessment']['input_sha256']==key),None)
        if cached:validate(store,project,cached,con,current=True)
        else:
            if len(records)>=MAX_HISTORY:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_HISTORY_LIMIT',400)
            from .store import now
            value={'schema_version':'native-current-scene-assessment.v1','assessment_id':'nsci_'+uuid.uuid4().hex,
                'version':1+sum(r['assessment']['input_refs']['analysis_id']==payload.analysis_id for r in records),
                'project_id':project_id,'workspace_id':workspace,'source_revision':project['revision'],
                'source_document_sha256':digest(document),'input_refs':ref,'input_sha256':key,'algorithm':ALGORITHM,
                'result':result(snapshot,key),'recommendation_only':True,'semantic_vision_state':'NOT_CONFIGURED',
                'actor_ref':actor_ref,'created_at':now()}
            record={'assessment':value,'sha256':digest(value)}
            if len(canonical(record))>1024*1024 or len(canonical(records+[record]))>16*1024*1024:
                raise WorkflowError('NATIVE_SCENE_ASSESSMENT_HISTORY_LIMIT',400)
            updated=copy.deepcopy(document);updated[FIELD]=records+[record]
            from .auto_edit_analysis import _save
            _save(store,con,project,updated,'source_scene_assessment_saved',{
                'assessment_id':value['assessment_id'],'sha256':record['sha256'],'actor_ref':actor_ref},timeline_mutated=False)
    return page(store,project_id,workspace)

def selected(store,project,selection,analysis_id,con):
    record=next((r for r in project['document'].get(FIELD,[]) if r['assessment']['assessment_id']==selection.assessment_id),None)
    if record is None:raise WorkflowError('NATIVE_SCENE_ASSESSMENT_NOT_FOUND',404)
    value=validate(store,project,record,con,current=True)
    if record['sha256']!=selection.expected_assessment_sha256 or value['input_refs']['analysis_id']!=analysis_id:
        raise WorkflowError('NATIVE_SCENE_ASSESSMENT_SELECTION_CHANGED')
    return record

def lineage(record):
    value=record['assessment']
    return {'schema_version':'native-current-scene-selection.v1','assessment_id':value['assessment_id'],
        'assessment_sha256':record['sha256'],'source_project_id':value['project_id'],'input_refs':copy.deepcopy(value['input_refs']),
        'input_sha256':value['input_sha256'],'recommendation_only':True,'automatic_application':False,
        'semantic_vision_state':'NOT_CONFIGURED','prediction_confidence_calibrated':False,'owner_uat_accepted':False}

def validate_lineage(document):
    metadata=document['canonical_timeline']['snapshot']['metadata'];proof=metadata.get('reviewed_local_scene_selection')
    if proof is None:return
    record=next((r for r in document.get(FIELD,[]) if r['assessment']['assessment_id']==proof.get('assessment_id')),None)
    if record is None or digest(record['assessment'])!=record['sha256'] or proof!=lineage(record):
        raise WorkflowError('NATIVE_SCENE_ASSESSMENT_LINEAGE_INVALID')
    highlight=metadata.get('reviewed_highlight_id')
    if highlight is not None and highlight not in {h['highlight_id'] for h in record['assessment']['result']['scene_ranking']}:
        raise WorkflowError('NATIVE_SCENE_ASSESSMENT_LINEAGE_INVALID')
