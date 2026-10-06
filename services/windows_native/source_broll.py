"""Saved supporting-media plans over Native history and the one source timeline.

Pure API planning/placement engines are reused without their database/services.
This bridge dispatches no external providers. Missing tiers remain explicit.
"""
import copy
from datetime import datetime,timezone
from decimal import Decimal
import json
import uuid
from pydantic import Field
from .auto_edit_timeline import _cas,_save,validate_document,view as timeline_view
from .auto_edit_analysis import asset_reference,validate_record
from .source_linked_edit import transcript_for
from .media import project_assets,media_path
from .contracts import WorkflowError,digest,file_sha
from .source_preview import resolve_assets
from app.models import StrictModel
from app.platform_models import AssetRead
from app.timeline_models import TimelineSnapshot
from app.timeline_logic import TimelineEditError
from app.media_intelligence_models import MediaPlanRequest,MediaPlanRead,MediaAssetProvenanceRead
from app.media_intelligence_logic import build_plan_items
from app.broll_planner import place_broll

ALGORITHM='native-source-broll-v1'
MAX_PLAN_VERSIONS=100


class Create(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    brand_context:str=Field(default='Video Factory',min_length=1,max_length=500)


class Select(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    media_plan_id:str=Field(pattern=r'^mpl_[a-f0-9]{24}$')
    expected_plan_version:int=Field(ge=1,strict=True)
    item_id:str=Field(min_length=1,max_length=80)
    asset_id:str=Field(pattern=r'^ast_[a-f0-9]{32}$')


class Apply(StrictModel):
    expected_version:int=Field(ge=1,strict=True)
    media_plan_id:str=Field(pattern=r'^mpl_[a-f0-9]{24}$')
    expected_plan_version:int=Field(ge=1,strict=True)
    item_ids:list[str]=Field(min_length=1,max_length=200)
    replace_plan_clips:bool=Field(default=False,strict=True)


def shared_assets(project,config):
    """Attribute owner attestation precisely; never infer an external license."""
    output={};timestamp=datetime.now(timezone.utc)
    for item in project_assets(project['document']):
        if item['kind'] not in {'image','video'}:continue
        path=media_path(config,item['id']);directory=config.data_root/'assets'
        if (directory.is_symlink() or path.is_symlink() or path.resolve().parent!=directory.resolve()
                or not path.is_file() or file_sha(path)!=item['sha256']):
            raise WorkflowError('SOURCE_MEDIA_CHANGED_OR_MISSING')
        content_type=('video/quicktime' if item['id'].endswith('.mov') else 'video/mp4') if item['kind']=='video' else (
            'image/png' if item['id'].endswith('.png') else 'image/jpeg')
        confirmed=item.get('rights_confirmed') is True
        output[asset_reference(item)]=AssetRead(asset_id=asset_reference(item),workspace_id='native-local',
            project_id='prj_'+project['id'],project_version_id=None,job_id=None,asset_class='source',kind=item['kind'],
            filename=item['filename'],object_key='assets/'+item['id'],content_type=content_type,
            size_bytes=path.stat().st_size,checksum_sha256=item['sha256'],storage_provider='native-local',version=1,
            provenance={'source_type':'user_upload','rights_status':'verified' if confirmed else 'unknown',
                'license':'owner_upload_rights_attestation' if confirmed else 'unknown',
                'rights_verification_basis':'explicit owner upload attestation; no independent license verification',
                'provider':'user-upload','source_reference':'assets/'+item['id'],'native_asset_id':item['id'],
                'tags':item.get('tags',[]),'description':item.get('description',''),
                'media_metadata':{key:item.get(key) for key in ('duration_seconds','width','height')},
                'fixture':bool(item.get('explicit_fixture'))},created_at=timestamp,updated_at=timestamp)
    return output


def context(project):
    state=validate_document(project['document']);snapshot=TimelineSnapshot.model_validate(state['snapshot'])
    record=next(value for value in project['document']['auto_edit_analyses']
        if value['analysis']['analysis_id']==snapshot.metadata['source_analysis_id'])
    asset=next(value for value in project_assets(project['document']) if value['id']==record['native_asset_id'])
    analysis=validate_record(record,project['id'],project['document'],asset,require_current=False)
    transcript=transcript_for(project['document'],snapshot)
    changed=bool(transcript and analysis.transcript and transcript.transcript_id!=analysis.transcript.transcript_id)
    analysis=analysis.model_copy(update={'transcript':transcript,
        'provenance':{**analysis.provenance,'semantic_analysis_refresh_required':changed}})
    return snapshot,analysis


def _plan(document,identifier,version):
    records=[item for item in document.get('source_broll_plans',[]) if item['plan']['media_plan_id']==identifier]
    if not records:raise WorkflowError('AUTO_EDIT_BROLL_PLAN_NOT_FOUND',404)
    record=max(records,key=lambda item:item['plan']['version'])
    if record['sha256']!=digest(record['plan']):raise WorkflowError('AUTO_EDIT_BROLL_PLAN_CHANGED')
    plan=MediaPlanRead.model_validate(record['plan'])
    if plan.version!=version:raise WorkflowError('AUTO_EDIT_BROLL_PLAN_VERSION_CHANGED')
    return plan


def _bound(plan,analysis):
    if plan.analysis_id!=analysis.analysis_id or plan.provenance.get('transcript_id')!=(
            analysis.transcript.transcript_id if analysis.transcript else None):
        raise WorkflowError('AUTO_EDIT_BROLL_TRANSCRIPT_CHANGED',400)
    if plan.provenance['source_asset_sha256']!=analysis.provenance['source_asset_checksum']:
        raise WorkflowError('AUTO_EDIT_BROLL_SOURCE_CHANGED')


def _persist(store,con,project,plan,action):
    from .store import now
    document=copy.deepcopy(project['document']);records=document.get('source_broll_plans',[])
    if len(records)>=MAX_PLAN_VERSIONS:raise WorkflowError('AUTO_EDIT_BROLL_HISTORY_LIMIT',400)
    value=plan.model_dump(mode='json');records.append({'plan':value,'sha256':digest(value)})
    document['source_broll_plans']=records
    con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',
        (project['revision']+1,json.dumps(document,ensure_ascii=False),now(),project['id']))
    store.version(con,project['id']);store.event(con,project['id'],action,{
        'plan_id':plan.media_plan_id,'plan_version':plan.version,'provider_calls':0,
        'canonical_timeline_mutated':False,'approval_invalidated':True,'source_media_mutated':False})


def create(store,config,project_id,revision,body):
    try:payload=Create.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_BROLL_REQUEST_INVALID',400) from None
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);_cas(project,payload.expected_version)
        snapshot,analysis=context(project);assets=shared_assets(project,config)
        configuration=MediaPlanRequest(analysis_id=analysis.analysis_id,
            transcript_id=analysis.transcript.transcript_id if analysis.transcript else None,
            purpose='supporting_broll',brand_context=payload.brand_context,max_ai_cost_vnd=Decimal('0'))
        fingerprint=digest({'algorithm':ALGORITHM,'analysis':analysis.model_dump(mode='json'),
            'configuration':configuration.model_dump(mode='json'),
            'assets':{identifier:{'sha256':asset.checksum_sha256,'filename':asset.filename,'provenance':asset.provenance}
                for identifier,asset in assets.items()}})
        existing=[record for record in project['document'].get('source_broll_plans',[]) if record['plan']['fingerprint']==fingerprint]
        if existing:
            cached=max(existing,key=lambda item:item['plan']['version'])
            _plan(project['document'],cached['plan']['media_plan_id'],cached['plan']['version'])
        identifier='mpl_'+uuid.uuid4().hex[:24]
        items=build_plan_items(media_plan_id=identifier,fingerprint=fingerprint,analysis=analysis,vision=None,
            payload=configuration,source_asset=assets[analysis.asset_id],supporting_assets=list(assets.values()),
            stock_candidates={},stock_available=False,image_available=False,video_available=False,
            image_cost_vnd=None,video_cost_vnd=None)
        timestamp=datetime.now(timezone.utc)
        plan=MediaPlanRead(media_plan_id=identifier,workspace_id='native-local',project_id='prj_'+project_id,
            project_version_id=None,analysis_id=analysis.analysis_id,vision_analysis_id=None,status='draft',
            fingerprint=fingerprint,version=1,configuration=configuration,
            provider_status={key:'NOT_CONFIGURED' for key in ('stock','ai_image','ai_video','semantic_vision')},
            items=items,media_assets=[],resolution_jobs=[],projected_ai_cost_vnd=0,max_ai_cost_vnd=0,
            needs_approval=False,publishing_blocked=True,unresolved_items=len(items),error_code=None,
            provenance={'algorithm':ALGORITHM,'source_asset_sha256':analysis.provenance['source_asset_checksum'],
                'transcript_id':analysis.transcript.transcript_id if analysis.transcript else None,
                'provider_dispatches':0,'recommendation_only':True,'requires_manual_selection_and_apply':True,
                'candidate_ranking':'saved filename/description/tags lexical overlap; no semantic Vision',
                'native_source_timeline_version':project['document']['canonical_timeline']['version']},
            created_at=timestamp,updated_at=timestamp)
        if not existing:_persist(store,con,project,plan,'auto_edit_broll_plan_saved')
    return timeline_view(store,project_id)


def select(store,config,project_id,revision,body):
    try:payload=Select.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_BROLL_REQUEST_INVALID',400) from None
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);_cas(project,payload.expected_version)
        _,analysis=context(project);plan=_plan(project['document'],payload.media_plan_id,payload.expected_plan_version)
        _bound(plan,analysis);assets=shared_assets(project,config);asset=assets.get(payload.asset_id)
        item=next((item for item in plan.items if item.media_plan_item_id==payload.item_id),None)
        if item is None or asset is None or asset.asset_id==analysis.asset_id:
            raise WorkflowError('AUTO_EDIT_BROLL_SELECTION_INVALID',400)
        if asset.provenance['rights_status']=='unknown':raise WorkflowError('MEDIA_RIGHTS_CONFIRMATION_REQUIRED',400)
        timestamp=datetime.now(timezone.utc);evidence_id='mas_'+uuid.uuid4().hex[:24]
        meta=asset.provenance['media_metadata']
        evidence=MediaAssetProvenanceRead(media_asset_id=evidence_id,workspace_id='native-local',project_id='prj_'+project_id,
            project_version_id=None,media_plan_id=plan.media_plan_id,media_plan_item_id=item.media_plan_item_id,
            asset_id=asset.asset_id,source_type='user_upload',rights_status='verified',license=asset.provenance['license'],
            license_url=None,provider='user-upload',provider_asset_id=asset.asset_id,creator=None,
            source_reference=asset.provenance['source_reference'],attribution_requirement=None,
            generation_provenance={'source':'immutable-user-upload','checksum_sha256':asset.checksum_sha256},
            width=meta['width'],height=meta['height'],duration_seconds=meta['duration_seconds'],orientation='unknown',
            production_eligible=not asset.provenance['fixture'],publishing_allowed=False,downloaded_at=None,
            provenance={'asset_checksum_sha256':asset.checksum_sha256,
                'rights_verification_basis':asset.provenance['rights_verification_basis'],'fixture':asset.provenance['fixture']},
            created_at=timestamp,updated_at=timestamp)
        plan.media_assets.append(evidence);item.selected_media_asset_id=evidence_id;item.source_asset_id=asset.asset_id
        item.strategy='user_asset';item.status='resolved';item.needs_approval=False
        item.provenance['explicit_manual_selection']=True;plan.version+=1;plan.updated_at=timestamp
        plan.unresolved_items=sum(item.status!='resolved' for item in plan.items)
        _persist(store,con,project,plan,'auto_edit_broll_selection_saved')
    return timeline_view(store,project_id)


def apply(store,config,project_id,revision,body):
    try:payload=Apply.model_validate(body)
    except ValueError:raise WorkflowError('AUTO_EDIT_BROLL_REQUEST_INVALID',400) from None
    if len(set(payload.item_ids))!=len(payload.item_ids):raise WorkflowError('AUTO_EDIT_BROLL_REQUEST_INVALID',400)
    with store.transaction() as con:
        project=store.editable(con,project_id,revision);_cas(project,payload.expected_version)
        snapshot,analysis=context(project);plan=_plan(project['document'],payload.media_plan_id,payload.expected_plan_version)
        _bound(plan,analysis);assets=shared_assets(project,config);selections=[]
        for identifier in payload.item_ids:
            item=next((item for item in plan.items if item.media_plan_item_id==identifier),None)
            evidence=next((value for value in plan.media_assets if item and value.media_asset_id==item.selected_media_asset_id),None)
            asset=assets.get(evidence.asset_id) if evidence else None
            if item is None or item.status!='resolved' or evidence is None or asset is None:
                raise WorkflowError('AUTO_EDIT_BROLL_SELECTION_INVALID',400)
            if evidence.provenance['asset_checksum_sha256']!=asset.checksum_sha256:
                raise WorkflowError('AUTO_EDIT_BROLL_SOURCE_CHANGED')
            if asset.provenance['rights_status']!='verified':raise WorkflowError('MEDIA_RIGHTS_CONFIRMATION_REQUIRED',400)
            selections.append((item,evidence))
        try:changed=place_broll(snapshot,plan,selections,assets,replace_plan_clips=payload.replace_plan_clips)
        except (TimelineEditError,ValueError):raise WorkflowError('AUTO_EDIT_BROLL_PLACEMENT_INVALID',400) from None
        native={asset_reference(value):value for value in project_assets(project['document'])}
        for track in changed.tracks:
            for clip in track.clips:
                if track.kind=='broll' and clip.metadata.get('media_plan_id')==plan.media_plan_id:
                    source=native[clip.asset_id];clip.metadata.update(native_asset_id=source['id'],source_checksum_sha256=source['sha256'])
        # Reuse the actual path/hash/rights scope before any timeline is saved.
        check=copy.deepcopy(project);check['document']['canonical_timeline']={
            'version':project['document']['canonical_timeline']['version'],'snapshot':changed.model_dump(mode='json'),
            'sha256':digest(changed.model_dump(mode='json'))}
        resolve_assets(config,check)
        _save(store,con,project,changed,'auto_edit_broll_applied_review_required')
    return timeline_view(store,project_id)
