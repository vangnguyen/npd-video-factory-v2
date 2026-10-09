"""Original reviewed Vision into pure Source B-roll decisions; never dispatches."""
import copy,json
from datetime import datetime,timezone
from pydantic import Field
from app.models import StrictModel
from app.platform_models import AssetRead
from app.vision_models import VisionFrameRead,VisionSceneRead
from app.media_intelligence_logic import build_plan_items
from app.broll_planner import tokens,choose_supporting_strategy
from .contracts import WorkflowError,digest
from .official_vision_evidence import ReviewedVision,build_context,validate_saved,ranking_inputs

ALGORITHM='native-source-broll-v2'
SNAPSHOT='native-reviewed-source-broll-input-v1'

class ReviewedSceneView(StrictModel):
    # Original Native intent identity, not a fabricated PostgreSQL Vision record.
    vision_analysis_id:str=Field(pattern=r'^nvoi_[a-f0-9]{32}$')
    frames:list[VisionFrameRead]
    scenes:list[VisionSceneRead]

def runtime(store,config,workspace,getter=None):
    from .official_vision import NativeOfficialVision
    from .vision import NativeVision
    value=getter() if getter is not None else NativeOfficialVision(NativeVision(store,config,workspace_id=workspace))
    if type(value) is not NativeOfficialVision or value.store is not store or value.config is not config or value.workspace!=workspace:
        raise WorkflowError('AUTO_EDIT_BROLL_VISION_SCOPE_INVALID')
    value.check();return value

def bind_reader(store,config,project_id,*,requests=None,plan_id=None,getter=None):
    """Initialize a keyless reader outside the caller's write transaction."""
    if getter is not None:return getter
    workspace=None
    with store.transaction() as con:
        if requests:
            if con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='native_official_vision_intents'").fetchone() is None:
                raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
            row=con.execute('SELECT workspace_id FROM native_official_vision_intents WHERE project_id=? AND vision_id=?',(project_id,requests[0].vision_id)).fetchone()
            if row is None:raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
            workspace=row['workspace_id']
        elif plan_id:
            row=con.execute('SELECT document FROM projects WHERE id=?',(project_id,)).fetchone()
            records=json.loads(row['document']).get('source_broll_plans',[]) if row else []
            for record in reversed(records):
                raw=record.get('plan',{});p=raw.get('provenance',{})
                if raw.get('media_plan_id')==plan_id and 'reviewed_vision' in p:
                    workspace=p['reviewed_vision']['workspace_id'];break
    if workspace is None:return None
    value=runtime(store,config,workspace);return lambda:value

def asset_facts(assets):
    return {key:{k:v for k,v in asset.model_dump(mode='json').items() if k not in {'created_at','updated_at'}} for key,asset in assets.items()}

def restore_assets(facts):
    stamp=datetime(1970,1,1,tzinfo=timezone.utc)
    return {key:AssetRead.model_validate({**value,'created_at':stamp,'updated_at':stamp}) for key,value in facts.items()}

def scene_view(analysis,assets,reviewed):
    source=assets[analysis.asset_id].provenance['native_asset_id']
    main=next((v for v in reviewed['items'] if v['asset_id']==source and not v['mock']),None)
    if main is None:return None
    return ReviewedSceneView(vision_analysis_id=main['request']['vision_id'],frames=main['frames'],scenes=main['scenes'])

def lineage(value):
    return {'request':copy.deepcopy(value['request']),'response_id':value['response_id'],'response_sha256':value['response_sha256'],
        'cost_operation_id':value['cost_operation_id'],'mock':value['mock'],'semantic_inference_performed':value['semantic_inference_performed'],
        'confidence_calibrated':False,'full_evidence_in':'plan.provenance.reviewed_vision'}

def rank(candidates,assets,reviewed,query):
    wanted=tokens(query);result=copy.deepcopy(candidates);by_asset={v['asset_id']:v for v in reviewed['items']}
    for candidate in result:
        asset=assets[candidate['asset_id']];value=by_asset.get(asset.provenance['native_asset_id'])
        if value is None:continue
        if value['source_sha256']!=candidate['checksum_sha256']:raise WorkflowError('AUTO_EDIT_BROLL_VISION_SOURCE_CHANGED')
        candidate['reviewed_vision']=lineage(value)
        signals=ranking_inputs(value)
        if value['mock']:continue
        tags=asset.provenance.get('tags') or []
        if not isinstance(tags,list):tags=[]
        available=tokens(' '.join([asset.filename,str(asset.provenance.get('description') or ''),*[str(tag) for tag in tags]]))|signals['semantic_tokens']
        overlap=sorted(wanted&available);candidate.update(relevance_score=round(len(overlap)/max(1,len(wanted)),6),matched_tokens=overlap,
            quality_score=signals['predicted_sample_quality'],quality_basis='uncalibrated provider-predicted sampled quality',
            score_basis='lexical overlap in saved metadata and reviewed provider labels; confidence uncalibrated',
            needs_attention=not overlap or candidate['rights_status']=='unknown')
    return sorted(result,key=lambda v:(-v['relevance_score'],-v['quality_score'] if v['quality_score'] is not None else 0,v['asset_id']))

def items(identifier,fingerprint,analysis,assets,configuration,reviewed):
    vision=scene_view(analysis,assets,reviewed)
    result=build_plan_items(media_plan_id=identifier,fingerprint=fingerprint,analysis=analysis,vision=vision,payload=configuration,
        source_asset=assets[analysis.asset_id],supporting_assets=list(assets.values()),stock_candidates={},stock_available=False,
        image_available=False,video_available=False,image_cost_vnd=None,video_cost_vnd=None)
    for item in result:
        ranked=rank(item.provenance['supporting_candidates'],assets,reviewed,item.broll.search_query)
        strategy,selected=choose_supporting_strategy(configuration,ranked,stock=False,image=False,video=False,preferred_type=item.broll.preferred_media_type)
        item.provenance.update(supporting_candidates=ranked,fallback_keeps_original_footage=selected is None and strategy=='user_asset',
            reviewed_vision_recommendation_only=True,confidence_calibrated=False)
        item.broll.provenance.update(reviewed_vision_recommendation_only=True,confidence_calibrated=False,
            full_evidence_in='plan.provenance.reviewed_vision',semantic_provider_used=vision is not None)
        item.strategy=strategy;item.source_asset_id=selected['asset_id'] if selected else None
        item.needs_attention=item.needs_approval or strategy=='motion_graphic' or bool(item.broll.provenance['semantic_refresh_required']) or not selected or selected['needs_attention']
    return result

def prepare(store,config,project,analysis,assets,requests,*,source_con,getter=None):
    # References have no client-supplied configuration/authority/predictions.
    # The original workspace is read from the immutable intent, then checked
    # against the Native workspace binding by the original reader.
    if source_con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='native_official_vision_intents'").fetchone() is None:
        raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
    first=source_con.execute('SELECT workspace_id FROM native_official_vision_intents WHERE project_id=? AND vision_id=?',
        (project['id'],requests[0].vision_id)).fetchone()
    if first is None:raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_FOUND',404)
    service=runtime(store,config,first['workspace_id'],getter)
    reviewed=build_context(service,project,requests,source_con=source_con)
    source=assets[analysis.asset_id].provenance['native_asset_id']
    main=next((v for v in reviewed['items'] if v['asset_id']==source),None)
    if main is not None:
        original=service.read(source_con,service.row(source_con,project['id'],main['request']['vision_id']))['snapshot']['source']
        transcript=analysis.transcript
        expected={'transcript_id':transcript.transcript_id,'version':transcript.version,'sha256':digest(transcript.model_dump(mode='json'))} if transcript else None
        if digest(original['scenes'])!=digest([v.model_dump(mode='json') for v in analysis.scenes]) or original['transcript_ref']!=expected:
            raise WorkflowError('AUTO_EDIT_BROLL_VISION_SCENE_TRANSCRIPT_CHANGED')
    return reviewed

def capture(project,analysis,assets):
    return {'schema_version':SNAPSHOT,'source_revision':project['revision'],'source_document_sha256':digest(project['document']),
        'analysis':analysis.model_dump(mode='json'),'assets':asset_facts(assets)}

def reviewed_plan(plan):
    return plan.provenance.get('algorithm')==ALGORITHM or 'reviewed_vision' in plan.provenance or 'reviewed_input' in plan.provenance

def validate(store,config,project,plan,*,source_con,current=False,getter=None):
    if not reviewed_plan(plan):return
    from .source_broll import context,shared_assets,asset_projection,selected_evidence
    from .media import project_assets
    try:
        p=plan.provenance;snapshot=p['reviewed_input'];reviewed=p['reviewed_vision']
        if (p['algorithm']!=ALGORITHM or snapshot['schema_version']!=SNAPSHOT or type(snapshot['source_revision']) is not int
            or p['recommendation_only'] is not True or type(p['provider_dispatches']) is not int or p['provider_dispatches']!=0
            or p['requires_manual_selection_and_apply'] is not True or plan.publishing_blocked is not True or p['prediction_confidence_calibrated'] is not False
            or p['semantic_vision_used'] is not reviewed['semantic_vision_used']):raise ValueError()
        row=source_con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project['id'],snapshot['source_revision'])).fetchone()
        if row is None:raise ValueError()
        document=json.loads(row['document'])
        if digest(document)!=snapshot['source_document_sha256']:raise ValueError()
        original={'id':project['id'],'revision':snapshot['source_revision'],'document':document}
        _,analysis=context(original)
        if digest(analysis.model_dump(mode='json'))!=digest(snapshot['analysis']):raise ValueError()
        assets=restore_assets(snapshot['assets']);native={v['id']:v for v in project_assets(document) if v['kind'] in {'image','video'}}
        if digest(asset_facts(assets))!=digest(snapshot['assets']):raise ValueError()
        if len(native)!=len(assets):raise ValueError()
        from .rights_override import validate_document,fixture,rights_sha
        validate_document(document,project_id=project['id'],workspace_id=reviewed['workspace_id'])
        for key,asset in assets.items():
            raw=native[asset.provenance['native_asset_id']]
            if (key!=asset.asset_id or asset.project_id!='prj_'+project['id'] or asset.workspace_id!='native-local'
                or asset.checksum_sha256!=raw['sha256'] or asset.filename!=raw['filename'] or asset.kind!=raw['kind']
                or asset.object_key!='assets/'+raw['id'] or asset.provenance.get('tags',[])!=raw.get('tags',[])
                or asset.provenance.get('description','')!=raw.get('description','')):raise ValueError()
            from .media_frame_analysis import asset_summary
            measured=asset_summary(document,project['id'],raw,store.root,verify_frames=False)
            override=asset.provenance.get('owner_rights_override')
            if override is not None:
                records=document.get('media_rights_overrides',[])
                if (not isinstance(override,dict) or not any(digest(override)==digest(v) for v in records)
                    or override['request']['action']!='grant' or override['asset_id']!=raw['id'] or override['asset_sha256']!=raw['sha256']
                    or override['request']['expected_rights_sha256']!=rights_sha(raw) or fixture(raw) or raw.get('rights_status')=='restricted'
                    or any(v['request']['action']=='revoke' and v['request']['override_id']==override['override_id'] for v in records)):
                    raise ValueError()
            expected_asset=asset_projection(original,raw,size_bytes=raw.get('bytes',asset.size_bytes),timestamp=asset.created_at,override=override,measured=measured)
            if digest(asset_facts({key:asset}))!=digest(asset_facts({key:expected_asset})):raise ValueError()
        service=runtime(store,config,reviewed['workspace_id'],getter)
        validate_saved(service,project,reviewed,source_con=source_con)
        fingerprint=digest({'algorithm':ALGORITHM,'analysis':analysis.model_dump(mode='json'),'configuration':plan.configuration.model_dump(mode='json'),
            'assets':{key:{'sha256':asset.checksum_sha256,'filename':asset.filename,'provenance':asset.provenance} for key,asset in assets.items()},'reviewed_vision':reviewed})
        if plan.fingerprint!=fingerprint:raise ValueError()
        if (plan.status!='draft' or plan.needs_approval is not False or plan.projected_ai_cost_vnd!=0 or plan.max_ai_cost_vnd!=0
            or plan.resolution_jobs or plan.provider_status!={key:'NOT_CONFIGURED' for key in ('stock','ai_image','ai_video','semantic_vision')}
            or plan.unresolved_items!=sum(v.status!='resolved' for v in plan.items)):raise ValueError()
        expected=items(plan.media_plan_id,plan.fingerprint,analysis,assets,plan.configuration,reviewed)
        if len(expected)!=len(plan.items):raise ValueError()
        media={v.media_asset_id:v for v in plan.media_assets}
        if len(media)!=len(plan.media_assets):raise ValueError()
        for evidence in plan.media_assets:
            asset=assets[evidence.asset_id];item=next(v for v in plan.items if v.media_plan_item_id==evidence.media_plan_item_id)
            computed=selected_evidence(project['id'],plan,item,asset,evidence.media_asset_id,evidence.created_at)
            if evidence.asset_id==analysis.asset_id or digest(evidence.model_dump(mode='json'))!=digest(computed.model_dump(mode='json')):raise ValueError()
        for actual,computed in zip(plan.items,expected,strict=True):
            if actual.status=='resolved':
                selected=media[actual.selected_media_asset_id];asset=assets[selected.asset_id]
                if selected.media_plan_item_id!=actual.media_plan_item_id or (asset.provenance['rights_status'] not in {'owned','licensed','verified'} and not asset.provenance.get('owner_rights_override')):raise ValueError()
                computed.selected_media_asset_id=selected.media_asset_id;computed.source_asset_id=asset.asset_id
                computed.strategy='licensed_stock' if asset.provenance['source_type']=='stock' else 'user_asset'
                computed.status='resolved';computed.needs_approval=False;computed.provenance['explicit_manual_selection']=True
            if digest(actual.model_dump(mode='json'))!=digest(computed.model_dump(mode='json')):raise ValueError()
        if plan.vision_analysis_id!=(scene_view(analysis,assets,reviewed).vision_analysis_id if scene_view(analysis,assets,reviewed) else None):raise ValueError()
        if current:
            requests=[ReviewedVision.model_validate(v['request']) for v in reviewed['items']]
            if digest(prepare(store,config,project,analysis,assets,requests,source_con=source_con,getter=lambda:service))!=digest(reviewed):raise ValueError()
            _,actual_analysis=context(project)
            if digest(actual_analysis.model_dump(mode='json'))!=digest(snapshot['analysis']):raise WorkflowError('AUTO_EDIT_BROLL_INPUT_CHANGED')
            current_assets=shared_assets(project,config,rights_overrides=getattr(store,'rights_overrides',None))
            if digest(asset_facts(current_assets))!=digest(snapshot['assets']):raise WorkflowError('AUTO_EDIT_BROLL_INPUT_CHANGED')
    except WorkflowError:raise
    except Exception:raise WorkflowError('AUTO_EDIT_BROLL_REVIEWED_VISION_INVALID') from None

def history(store,project):
    from .pipeline import Config
    from app.media_intelligence_models import MediaPlanRead
    config=Config(data_root=store.root)
    records=[];readers={}
    for record in project['document'].get('source_broll_plans',[]):
        plan=MediaPlanRead.model_validate(record['plan'])
        if reviewed_plan(plan):
            if digest(record['plan'])!=record['sha256'] or digest(record['plan'])!=digest(plan.model_dump(mode='json')):
                raise WorkflowError('AUTO_EDIT_BROLL_PLAN_CHANGED')
            workspace=plan.provenance['reviewed_vision']['workspace_id']
            if workspace not in readers:readers[workspace]=runtime(store,config,workspace)
            records.append(plan)
    with store.transaction() as con:
        for plan in records:
            validate(store,config,project,plan,source_con=con,getter=lambda:readers[plan.provenance['reviewed_vision']['workspace_id']])
