"""Rebind saved Source evidence into an independent unapproved local project.

Media bytes are reused by checksum; evidence is explicitly derived, never
represented as a fresh provider measurement. Original history remains intact.
"""
import copy
from .contracts import WorkflowError,digest
from .media import project_assets
from .auto_edit_analysis import fingerprint,validate_record
from .auto_edit_timeline import validate_document
from app.auto_edit_models import TranscriptRead
from app.media_intelligence_models import MediaPlanRead

ALGORITHM='native-source-identity-rebind-v1'

def archive_scene_reviews(document,source_id,revision):
    """Retain original reviews as lineage, without child workspace authority."""
    records=document.pop('source_scene_recommendations',[])
    for record in records:
        if record['recommendation']['project_id']!=source_id or digest(record['recommendation'])!=record['sha256']:
            raise WorkflowError('NATIVE_SCENE_REVIEW_HISTORY_INVALID')
        document.setdefault('source_scene_inherited_reviewed_history',[]).append({'source_project_id':source_id,'source_revision':revision,
            'original_record':copy.deepcopy(record),'original_record_sha256':digest(record),'authority_transferred':False,'new_review_required':True})


def rebind(document,source_id,target_id,revision,created_at,*,parent_document_sha256=None):
    state=validate_document(document)
    if state['snapshot']['metadata']['native_project_id']!=source_id:
        raise WorkflowError('AUTO_EDIT_TIMELINE_PROJECT_MISMATCH')
    assets={item['id']:item for item in project_assets(document)}
    mapping={source_id:target_id,'prj_'+source_id:'prj_'+target_id}
    origin={'algorithm':ALGORITHM,'source_project_id':source_id,'source_revision':revision,
        'source_document_sha256':parent_document_sha256 or digest(document),
        'source_binding_document_sha256':digest(document),'created_at':created_at,
        'provider_calls':0,'source_media_mutated':False,'fresh_provider_measurement':False}
    def register(identifier):
        if identifier and identifier not in mapping:
            prefix=identifier.split('_',1)[0]
            mapping[identifier]=prefix+'_'+digest([ALGORITHM,target_id,identifier])[:24]
    records=document.get('auto_edit_analyses',[])
    analysis_keys={}
    for record in records:
        asset=assets.get(record['native_asset_id'])
        if asset is None:raise WorkflowError('AUTO_EDIT_ANALYSIS_SOURCE_MISMATCH')
        value=validate_record(record,source_id,document,asset,require_current=False)
        current=value.fingerprint==fingerprint(source_id,document,asset)
        key=fingerprint(target_id,document,asset) if current else digest([ALGORITHM,target_id,value.fingerprint])
        mapping[value.analysis_id]='ana_'+key[:24];analysis_keys[value.analysis_id]=(key,current)
        for item in [*value.scenes,*value.silence_decisions,*value.highlights]:
            for keyname in ('scene_id','decision_id','highlight_id'):
                register(getattr(item,keyname,None))
    transcripts=[record['analysis']['transcript'] for record in records if record['analysis'].get('transcript')]
    transcripts+=document.get('auto_edit_transcripts',[])
    for value in transcripts:
        item=TranscriptRead.model_validate(value)
        if item.analysis_id not in analysis_keys:raise WorkflowError('AUTO_EDIT_TRANSCRIPT_SOURCE_MISMATCH')
        register(item.transcript_id)
        for segment in item.segments:
            register(segment.segment_id)
            for word in segment.words:register(word.word_id)
    plans=document.get('source_broll_plans',[])
    from .source_broll_vision import reviewed_plan
    inherited_reviewed={}
    for record in plans:
        if record['sha256']!=digest(record['plan']):raise WorkflowError('AUTO_EDIT_BROLL_PLAN_CHANGED')
        plan=MediaPlanRead.model_validate(record['plan'])
        if plan.project_id!='prj_'+source_id or plan.analysis_id not in analysis_keys:
            raise WorkflowError('AUTO_EDIT_BROLL_SOURCE_CHANGED')
        register(plan.media_plan_id)
        for item in plan.items:register(item.media_plan_item_id)
        for item in plan.media_assets:register(item.media_asset_id)
        if plan.resolution_jobs:raise WorkflowError('AUTO_EDIT_EXTERNAL_PLAN_REBINDING_UNSUPPORTED',400)
        if reviewed_plan(plan):inherited_reviewed[plan.media_plan_id]=record
    def rewrite(value):
        if isinstance(value,str):return mapping.get(value,value)
        if isinstance(value,list):return [rewrite(item) for item in value]
        if isinstance(value,dict):return {key:rewrite(item) for key,item in value.items()}
        return copy.deepcopy(value)
    output=copy.deepcopy(document)
    archive_scene_reviews(output,source_id,revision)
    if 'media_rights_declarations' in output or 'media_rights_overrides' in output:
        from .rights import clear_project_claims
        clear_project_claims(output)
    from .media_frame_analysis import rebind_records
    output['media_frame_analyses']=rebind_records(document,source_id,target_id)
    output['auto_edit_analyses']=[]
    for record in records:
        changed=rewrite(record);value=changed['analysis'];key,current=analysis_keys[record['analysis']['analysis_id']]
        value['fingerprint']=key
        value['provenance']['identity_rebinding']={**origin,'source_analysis_id':record['analysis']['analysis_id'],
            'source_record_sha256':record['sha256'],'source_analysis_was_current':current}
        if value['transcript']:
            value['transcript']['provenance']['identity_rebinding']={**origin,
                'source_transcript_id':record['analysis']['transcript']['transcript_id'],
                'source_transcript_sha256':digest(record['analysis']['transcript'])}
        changed['sha256']=digest({key:value for key,value in changed.items() if key!='sha256'})
        output['auto_edit_analyses'].append(changed)
    output['auto_edit_transcripts']=[]
    for value in document.get('auto_edit_transcripts',[]):
        changed=rewrite(value);changed['provenance']['identity_rebinding']={**origin,
            'source_transcript_id':value['transcript_id'],'source_transcript_sha256':digest(value)}
        TranscriptRead.model_validate(changed);output['auto_edit_transcripts'].append(changed)
    output['source_broll_plans']=[]
    plan_fingerprints={}
    for record in plans:
        if record['plan']['media_plan_id'] in inherited_reviewed:
            output.setdefault('source_broll_inherited_reviewed_history',[]).append({
                'source_project_id':source_id,'source_revision':revision,'original_record':copy.deepcopy(record),
                'original_record_sha256':digest(record),'authority_transferred':False,'new_plan_required':True})
            continue
        changed=rewrite(record['plan']);changed['fingerprint']=digest([ALGORITHM,target_id,record['plan']['fingerprint']])
        changed['provenance']['identity_rebinding']={**origin,'source_plan_id':record['plan']['media_plan_id'],
            'source_plan_sha256':record['sha256']}
        changed['provenance']['native_source_timeline_version']=1
        for media in changed['media_assets']:
            inherited=media['provenance'].get('owner_rights_override')
            if inherited:
                media['provenance']['inherited_owner_exception']={'override_id':inherited['override_id'],'sha256':inherited['sha256'],
                    'source_project_id':source_id,'authority_transferred':False}
                media['provenance']['owner_rights_override']=None
        changed=MediaPlanRead.model_validate(changed).model_dump(mode='json')
        output['source_broll_plans'].append({'plan':changed,'sha256':digest(changed)})
        plan_fingerprints[changed['media_plan_id']]=changed['fingerprint']
    snapshot=rewrite(state['snapshot'])
    original_selection=state['snapshot']['metadata'].get('reviewed_scene_selection')
    if original_selection is not None:
        snapshot['metadata'].pop('reviewed_scene_selection',None);snapshot['metadata'].pop('reviewed_highlight_id',None)
        snapshot['metadata']['inherited_reviewed_scene_selection']={'original_selection':copy.deepcopy(original_selection),
            'original_highlight_id':state['snapshot']['metadata'].get('reviewed_highlight_id'),
            'authority_transferred':False,'new_review_required':True}
    # Generic copies are independent projects, not registered variant members.
    snapshot['metadata'].pop('source_variant',None)
    snapshot['metadata'].update(native_project_id=target_id,human_review_required=True,
        source_identity_rebinding=origin)
    for track in snapshot['tracks']:
        for clip in track['clips']:
            meta=clip['metadata']
            if meta.get('media_plan_id') in plan_fingerprints:
                meta['media_plan_fingerprint']=plan_fingerprints[meta['media_plan_id']]
            for old,record in inherited_reviewed.items():
                if meta.get('media_plan_id')==mapping[old]:
                    meta['inherited_reviewed_vision']={'source_project_id':source_id,'source_plan_id':old,
                        'source_plan_sha256':record['sha256'],'authority_transferred':False,'new_plan_required':True}
    output['canonical_timeline']={'version':1,'snapshot':snapshot,'sha256':digest(snapshot)}
    output['source_timeline_mutations']=[{'version':1,'mutation':{'type':'edit','source_identity_rebinding':origin}}]
    output['duplication']={**origin,'source_timeline_sha256':state['sha256']}
    output['name']=document['name'][:139]+' — bản sao'
    from .source_reframe_vision import inherit
    inherit(output,source_id,revision)
    output['canonical_timeline']['sha256']=digest(output['canonical_timeline']['snapshot'])
    validate_document(output)
    return output
