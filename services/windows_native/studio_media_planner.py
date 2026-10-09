"""Versioned Mode A storyboard decisions over existing assets and canonical shots.

Planning performs no network/AI work. Stock/generation execution remains in the
existing explicit, cost-gated Assets consumers. No second editing database.
"""
import copy,json,uuid
from decimal import Decimal
from .contracts import WorkflowError,digest,canonical
from .store import now
from . import shot_adapter as shots
from .auto_edit_timeline import is_auto_edit
from .backup import guard
from .media import media_path
from .source_broll import shared_assets
from .studio_media_models import Options,Create,Select,Revise,Apply,Plan,Item,Candidate
from .costs import CostLedger,amount,wire
from app.broll_planner import tokens
from app.media_intelligence_logic import platform_aspect_ratio,_compact_query
from app.media_frame_facts import PixelAssetSummary

ALGORITHM='native-storyboard-media-planner-v2'
VISION_ALGORITHM='native-storyboard-media-planner-v3'
SUPPORTED_ALGORITHMS={ALGORITHM,VISION_ALGORITHM}
MAX_VERSIONS=100
MAX_PLAN_BYTES=1024*1024
MAX_HISTORY_BYTES=16*1024*1024


class NativeStudioMediaPlanner:
    def __init__(self,store,config,*,workspace_id,providers,official_vision=lambda:None):
        self.store,self.config,self.workspace,self.providers=store,config,workspace_id,providers
        self.official_vision=official_vision
        CostLedger(store)

    def context(self,con,project,reviewed_vision=None):
        doc=project['document']
        if is_auto_edit(doc):raise WorkflowError('STUDIO_MEDIA_PLAN_USE_SOURCE_BROLL',400)
        if not doc.get('proposal'):raise WorkflowError('STUDIO_MEDIA_PLAN_SCRIPT_REQUIRED',400)
        state,_=shots._state(project);cards=shots.shots_from_snapshot(state['snapshot'])
        assets=shared_assets(project,self.config,rights_overrides=getattr(self.store,'rights_overrides',None))
        facts={}
        for asset in assets.values():
            identifier=asset.provenance['native_asset_id'];guard(media_path(self.config,identifier),exists=True)
            facts[identifier]={'asset_id':identifier,'sha256':asset.checksum_sha256,'filename':asset.filename,
                'kind':'video' if asset.content_type.startswith('video/') else 'image','size_bytes':asset.size_bytes,
                'provenance':copy.deepcopy(asset.provenance)}
        records=[dict(row) for row in con.execute('SELECT estimated_cost,actual_cost,status,paid FROM native_cost_operations WHERE project_id=? ORDER BY id',(project['id'],))]
        attempted=[row for row in records if row['status']!='needs_approval' and row['paid']]
        exposure=sum((amount(row['actual_cost'] if row['actual_cost'] is not None else row['estimated_cost']) or Decimal(0) for row in attempted),Decimal(0))
        limit=amount((doc.get('cost_policy') or {}).get('max_ai_cost_vnd'))
        provider=self.providers()
        if provider.get('workspace_id')!=self.workspace:raise WorkflowError('STUDIO_MEDIA_PLAN_PROVIDER_SCOPE_INVALID')
        context={'schema_version':'native-storyboard-media-input-v1','workspace_id':self.workspace,'project_id':project['id'],
            'script':copy.deepcopy(doc['proposal']),'script_sha256':digest(doc['proposal']),
            'storyboard':cards,'timeline_version':state['version'],'timeline_sha256':state['sha256'],
            'niche':doc.get('niche') or (doc.get('content_profile') or {}).get('niche'),
            'content_profile':copy.deepcopy(doc.get('content_profile')),'channel_profile':copy.deepcopy(doc.get('channel_profile')),
            'brand':copy.deepcopy(doc.get('brand_template')),'canvas':{key:state['snapshot'][key] for key in ('width','height','fps','aspect_ratio')},
            'assets':facts,'provider_availability':provider,
            'budget':{'max_ai_cost_vnd':wire(limit),'known_paid_exposure_vnd':wire(exposure),
                'remaining_known_budget_vnd':wire(max(Decimal(0),limit-exposure)) if limit is not None else None,
                'unknown_paid_estimates':sum(row['estimated_cost'] is None for row in attempted),
                'unknown_paid_actual_costs':sum(row['actual_cost'] is None for row in attempted),
                'historical_capture_complete':False,'planning_authorizes_payment':False}}
        from .qualified_learning_feedback import from_run_context,qualified_context
        feedback=from_run_context((doc.get('content_intelligence') or {}).get('run',{}).get('context'))
        if feedback is not None:
            qualified_context(getattr(self.store,'qualified_learning',None),feedback,source_con=con)
            selection=doc.get('channel_profile') or {};scope=feedback['scope']
            if scope['channel_profile_ref']!=(selection.get('profile') or {}).get('profile_ref') or scope['channel_profile_sha256']!=selection.get('profile_sha256'):
                raise WorkflowError('NATIVE_QUALIFIED_LEARNING_SCOPE_MISMATCH',409)
            context['channel_history_recommendations']={'schema_version':'native-qualified-media-recommendations-v1',
                'projection_id':feedback['projection_id'],'projection_sha256':feedback['projection_sha256'],
                'source_binding':feedback['source_binding'],'mock':feedback['mock'],
                'real_audience_observation':feedback['real_audience_observation'],
                'dimensions':feedback['consumers']['media_planner'],'recommendation_only':True,
                'automatic_application':False,'planning_authorizes_payment':False,'limitation':feedback['limitations'][0]}
        if reviewed_vision:
            from .official_vision_evidence import build_context
            service=self.official_vision()
            if service is None or service.store is not self.store or service.config is not self.config or service.workspace!=self.workspace:
                raise WorkflowError('STUDIO_MEDIA_PLAN_VISION_SCOPE_INVALID')
            context['schema_version']='native-storyboard-media-input-v2'
            context['reviewed_vision']=build_context(service,project,reviewed_vision,source_con=con)
        return context,state

    @staticmethod
    def selectable(asset):
        p=asset['provenance']
        # Upload attestation is explicitly attributed by the existing shared boundary.
        override=p.get('owner_rights_override')
        return p['rights_status']!='restricted' and (p['rights_status'] in {'owned','licensed','verified'} or bool(override)) and (p.get('production_eligible') is not False or bool(override))

    @staticmethod
    def asset_strategy(asset):
        p=asset['provenance'];source=p['source_type']
        return ('stock_'+asset['kind'] if source=='stock' else 'ai_'+asset['kind'] if source=='ai_generated' else 'user_asset'),(
            'licensed_stock' if source=='stock' else 'ai_'+asset['kind'] if source=='ai_generated' else 'internal_library' if source=='internal_library' else 'user_asset')

    def candidates(self,context,query):
        wanted=tokens(query);result=[]
        reviewed={v['asset_id']:v for v in (context.get('reviewed_vision') or {}).get('items',[])}
        for asset in context['assets'].values():
            p=asset['provenance'];tags=p.get('tags',[])
            available=tokens(' '.join([asset['filename'],str(p.get('description') or ''),*[str(tag) for tag in tags if isinstance(tag,str)]]))
            measured=PixelAssetSummary.model_validate(p['pixel_quality_summary']) if p.get('pixel_quality_summary') else None
            quality=measured.heuristic_quality_score if measured else None
            basis='saved_filename_description_tags_and_uncalibrated_pixel_tiebreak';vision=reviewed.get(asset['asset_id']);lineage=None
            if vision is not None:
                from .official_vision_evidence import ranking_inputs
                if vision['source_sha256']!=asset['sha256']:raise WorkflowError('STUDIO_MEDIA_PLAN_VISION_SOURCE_CHANGED')
                signals=ranking_inputs(vision);available|=signals['semantic_tokens']
                if not vision['mock']:
                    quality=signals['predicted_sample_quality'];basis='reviewed_provider_labels_and_uncalibrated_predicted_sample_quality'
                lineage={'request':copy.deepcopy(vision['request']),'response_id':vision['response_id'],'response_sha256':vision['response_sha256'],
                    'cost_operation_id':vision['cost_operation_id'],'mock':vision['mock'],'semantic_inference_performed':vision['semantic_inference_performed'],
                    'confidence_calibrated':False,'full_evidence_in':'input.reviewed_vision'}
            strategy,tier=self.asset_strategy(asset)
            result.append(Candidate(asset_id=asset['asset_id'],sha256=asset['sha256'],filename=asset['filename'],kind=asset['kind'],strategy=strategy,resolver_tier=tier,
                relevance_score=round(len(wanted&available)/max(1,len(wanted)),6),quality_score=quality,
                score_basis=basis,selectable=self.selectable(asset),fixture=bool(p.get('fixture')),
                provenance={**{key:copy.deepcopy(p.get(key)) for key in ('source_type','rights_status','actual_native_rights_status','license','license_url','provider','source_reference','rights_verification_basis','owner_rights_override','production_eligible')},
                    'asset_provenance_sha256':digest(p),'generation_provenance_sha256':digest(p.get('generation_provenance',{})),'full_evidence_in':'input.assets',
                    **({'reviewed_vision':lineage} if lineage is not None else {})}))
        return sorted(result,key=lambda value:(-value.relevance_score,-(value.quality_score or 0),value.asset_id))

    @staticmethod
    def availability(context,options):
        providers=context['provider_availability'];generation=providers['generation'];stock=providers['stock']
        return {'user_asset':True,'internal_library':True,
            'licensed_stock':options.allow_stock and any(value['status']=='CONFIGURED' for value in stock['items']),
            'ai_image':options.allow_ai_image and any(value['status']=='CONFIGURED' and value['modality']=='image' and value['operation']=='generate' for value in generation['items']),
            'ai_video':options.allow_ai_video and any(value['status']=='CONFIGURED' and value['modality']=='video' and value['operation']=='text_to_video' for value in generation['items']),
            'motion_graphic':False}

    def items(self,context,options):
        available=self.availability(context,options);items=[]
        # Generation estimates are unavailable in the protected Native catalog.
        # The cost ledger rejects an unknown estimate under every finite limit.
        blocked=[strategy for strategy in ('ai_image','ai_video') if available[strategy] and context['budget']['max_ai_cost_vnd'] is not None]
        for ordinal,shot in enumerate(context['storyboard'],1):
            query=_compact_query(shot['visual']+' '+shot['narration']+' '+shot['on_screen_text'])[:500]
            candidates=self.candidates(context,query);selected=None;strategy=None;deferred=None
            tiers=options.resolver_priority
            for tier in tiers:
                matching=[value for value in candidates if value.selectable and value.resolver_tier==tier and (value.relevance_score>0 or value.asset_id==shot['asset_id'])]
                if matching:
                    selected=next((value for value in matching if value.asset_id==shot['asset_id']),matching[0]);strategy=selected.strategy;break
                if tier in {'licensed_stock','ai_image','ai_video'} and available[tier]:
                    if tier in blocked:
                        deferred=deferred or tier
                        continue
                    strategy='stock_'+options.preferred_media_type if tier=='licensed_stock' else tier;break
            strategy=strategy or deferred or ('motion_graphic' if 'motion_graphic' in tiers else 'user_asset')
            fallback=[]
            for tier in tiers:
                if any(value.selectable and value.resolver_tier==tier for value in candidates) or available.get(tier) and tier not in {'user_asset','internal_library',*blocked}:
                    fallback.append('stock_'+options.preferred_media_type if tier=='licensed_stock' else 'user_asset' if tier=='internal_library' else tier)
            fallback=list(dict.fromkeys(value for value in fallback if value!=strategy))
            items.append(Item(shot_id=shot['shot_id'],ordinal=ordinal,visual_brief=shot['visual'],narration=shot['narration'],on_screen_text=shot['on_screen_text'],
                duration_seconds=shot['duration'],duration_basis='draft_shot_duration_requires_measured_voice_fit',target_aspect_ratio=options.aspect_ratio or platform_aspect_ratio(options.platform),strategy=strategy,fallback=fallback,query=query,
                generation_prompt=(' '.join([shot['visual'],shot['narration'],'Original supporting visual; review brands, rights and factual accuracy.']))[:4000],
                candidates=candidates,selected_asset_id=selected.asset_id if selected else None,selected_asset_sha256=selected.sha256 if selected else None,
                status='selected' if selected else 'requires_approval' if strategy in blocked else 'requires_implementation' if strategy=='motion_graphic' else 'requires_asset' if strategy=='user_asset' else 'requires_provider',
                new_generation_budget_blocked=blocked,
                needs_approval=selected is None and strategy in {'ai_image','ai_video'},
                decision_basis='existing project media selected as feasible fallback; unpriced new generation blocked under finite budget' if selected and deferred else 'existing owned project media; manual review before timeline apply' if selected else 'unknown generation estimate under finite budget; approval/pricing required and no feasible fallback selected' if strategy in blocked else 'configured provider path requires separate Assets request; unknown price is not zero' if strategy in {'stock_image','stock_video','ai_image','ai_video'} else 'no executable fallback selected; human media required'))
        return items

    def records(self,document,identity=None,*,source_con=None):
        records=document.get('studio_media_plans',[])
        if not isinstance(records,list) or len(records)>MAX_VERSIONS or len(canonical(records))>MAX_HISTORY_BYTES:raise WorkflowError('STUDIO_MEDIA_PLAN_HISTORY_INVALID')
        parsed=[];last={}
        try:
            for record in records:
                plan=Plan.model_validate(record['plan'])
                if record['sha256']!=digest(record['plan']) or plan.workspace_id!=self.workspace or plan.input_sha256!=digest(plan.input) or plan.fingerprint!=digest({'algorithm':plan.algorithm,'input_sha256':plan.input_sha256,'options':plan.options.model_dump(mode='json')}) or plan.version!=last.get(plan.media_plan_id,0)+1 or plan.input.get('project_id')!=plan.project_id or plan.input.get('workspace_id')!=self.workspace:raise ValueError()
                if plan.algorithm==VISION_ALGORITHM:
                    from .official_vision_evidence import validate_saved
                    service=self.official_vision()
                    if source_con is None or service is None or service.store is not self.store or service.config is not self.config or service.workspace!=self.workspace:raise ValueError()
                    validate_saved(service,{'id':plan.project_id},plan.input['reviewed_vision'],source_con=source_con)
                    if any(record['plan'].get(k) is not False for k in ('publishing_enabled','real_provider_tested')) or record['plan'].get('recommendation_only') is not True:raise ValueError()
                    # Recompute the visible attribution/scores from the exact saved
                    # reviewed projection. Rehashing a plan must not promote a mock.
                    for item,raw in zip(plan.items,record['plan']['items'],strict=True):
                        expected=[value.model_dump(mode='json') for value in self.candidates(plan.input,item.query)[:50]]
                        if digest(raw['candidates'])!=digest(expected):raise ValueError()
                last[plan.media_plan_id]=plan.version;parsed.append((plan,record['sha256']))
        except (ValueError,KeyError,TypeError):raise WorkflowError('STUDIO_MEDIA_PLAN_HISTORY_INVALID') from None
        return [(plan,sha) for plan,sha in parsed if identity is None or plan.media_plan_id==identity]

    def bound(self,con,project,identity,payload):
        records=self.records(project['document'],identity,source_con=con)
        if not records:raise WorkflowError('STUDIO_MEDIA_PLAN_NOT_FOUND',404)
        plan,sha=records[-1]
        if plan.project_id!=project['id']:raise WorkflowError('STUDIO_MEDIA_PLAN_NOT_FOUND',404)
        if plan.version!=payload.expected_plan_version or sha!=payload.expected_plan_sha256:raise WorkflowError('STUDIO_MEDIA_PLAN_VERSION_CHANGED')
        if plan.algorithm not in SUPPORTED_ALGORITHMS:raise WorkflowError('STUDIO_MEDIA_PLAN_POLICY_CHANGED')
        context,state=self.context(con,project,self.reviewed_requests(plan))
        if plan.input_sha256!=digest(context) or plan.application is not None:raise WorkflowError('STUDIO_MEDIA_PLAN_INPUT_CHANGED')
        return plan,context,state

    def persist(self,con,project,plan,*,document=None,action='studio_media_plan_saved_review_required'):
        doc=copy.deepcopy(document or project['document']);records=doc.get('studio_media_plans',[])
        if len(records)>=MAX_VERSIONS:raise WorkflowError('STUDIO_MEDIA_PLAN_HISTORY_LIMIT',400)
        value=Plan.model_validate(plan.model_dump(mode='json')).model_dump(mode='json')
        if len(canonical(value))>MAX_PLAN_BYTES:raise WorkflowError('STUDIO_MEDIA_PLAN_SIZE_LIMIT',400)
        records.append({'plan':value,'sha256':digest(value)})
        if len(canonical(records))>MAX_HISTORY_BYTES:raise WorkflowError('STUDIO_MEDIA_PLAN_HISTORY_LIMIT',400)
        doc['studio_media_plans']=records
        con.execute('UPDATE projects SET revision=?,document=?,approval=NULL,updated_at=? WHERE id=?',(project['revision']+1,json.dumps(doc,ensure_ascii=False),now(),project['id']))
        self.store.version(con,project['id']);self.store.event(con,project['id'],action,{'media_plan_id':plan.media_plan_id,'plan_version':plan.version,'plan_sha256':digest(value),
            'revision':project['revision']+1,'provider_calls':0,'paid_operations':0,'human_review_required':True,'canonical_timeline_mutated':document is not None})

    def create(self,project_id,payload):
        with self.store.transaction() as con:
            project=self.store.editable(con,project_id,payload.revision);context,state=self.context(con,project,payload.reviewed_vision)
            if state['version']!=payload.expected_timeline_version:raise WorkflowError('STUDIO_MEDIA_PLAN_TIMELINE_CHANGED')
            algorithm=VISION_ALGORITHM if payload.reviewed_vision else ALGORITHM
            options=payload.options;input_sha=digest(context);fingerprint=digest({'algorithm':algorithm,'input_sha256':input_sha,'options':options.model_dump(mode='json')})
            records=self.records(project['document'],source_con=con);same=[plan for plan,sha in records if plan.fingerprint==fingerprint and plan.project_id==project_id and plan.application is None]
            if not same:
                stamp=now();plan=Plan(schema_version='native-storyboard-media-plan-v2' if payload.reviewed_vision else 'native-storyboard-media-plan-v1',algorithm=algorithm,workspace_id=self.workspace,project_id=project_id,media_plan_id='nmp_'+uuid.uuid4().hex,
                    version=1,fingerprint=fingerprint,input_sha256=input_sha,input=context,options=options,items=self.items(context,options),created_at=stamp,updated_at=stamp,
                    semantic_vision_used=(context.get('reviewed_vision') or {}).get('semantic_vision_used',False))
                self.persist(con,project,plan)
        return self.page(project_id)

    def change(self,project_id,identity,payload):
        with self.store.transaction() as con:
            project=self.store.editable(con,project_id,payload.revision);plan,context,state=self.bound(con,project,identity,payload)
            item=next((value for value in plan.items if value.shot_id==payload.shot_id),None)
            if item is None:raise WorkflowError('STUDIO_MEDIA_PLAN_SHOT_NOT_FOUND',404)
            if isinstance(payload,Select):
                candidate=next((value for value in item.candidates if value.asset_id==payload.asset_id),None)
                if candidate is None or not candidate.selectable or candidate.sha256!=payload.expected_asset_sha256:raise WorkflowError('STUDIO_MEDIA_PLAN_ASSET_NOT_SELECTABLE')
                values={'selected_asset_id':candidate.asset_id,'selected_asset_sha256':candidate.sha256,'strategy':candidate.strategy,'status':'selected','needs_approval':False,
                    'decision_basis':'explicit human choice of existing project asset; rights evidence remains attributed'}
            else:
                if not payload.query.strip() or not payload.generation_prompt.strip():raise WorkflowError('STUDIO_MEDIA_PLAN_BRIEF_REQUIRED',400)
                values={'strategy':payload.strategy,'query':payload.query,'generation_prompt':payload.generation_prompt,'selected_asset_id':None,'selected_asset_sha256':None,
                    'status':'requires_approval' if payload.strategy in item.new_generation_budget_blocked else 'requires_implementation' if payload.strategy=='motion_graphic' else 'requires_asset' if payload.strategy=='user_asset' else 'requires_provider',
                    'needs_approval':payload.strategy in {'ai_image','ai_video'},'decision_basis':'explicit human planning preference; provider execution and payment not authorized'}
                if plan.algorithm==VISION_ALGORITHM:
                    values['candidates']=self.candidates(context,payload.query)[:50]
            values['fallback']=[value for value in item.fallback if value!=values['strategy']]
            changed=Item.model_validate({**item.model_dump(mode='json'),**values});plan.items=[changed if value.shot_id==item.shot_id else value for value in plan.items]
            plan.version+=1;plan.updated_at=now();self.persist(con,project,plan)
        return self.page(project_id)

    def apply(self,project_id,identity,payload):
        with self.store.transaction() as con:
            project=self.store.editable(con,project_id,payload.revision);plan,context,state=self.bound(con,project,identity,payload)
            before=shots.shots_from_snapshot(state['snapshot']);after=copy.deepcopy(before);items={value.shot_id:value for value in plan.items}
            for identifier in payload.shot_ids:
                item=items.get(identifier)
                if item is None or item.status!='selected':raise WorkflowError('STUDIO_MEDIA_PLAN_SELECTION_REQUIRED',400)
                after=shots._apply(after,project['document'],{'type':'update','shot_id':identifier,'values':{'asset_id':item.selected_asset_id}},self.store,project,con)
            for item in after:shots._check_shot(item,shots._assets(project['document']))
            scope=shots.scope_changes(before,after);doc=shots.project_projection(project['document'],after)
            snapshot=shots.snapshot_from_shots(after,doc,canvas=state['snapshot']);doc['canonical_timeline']={'version':state['version']+1,'snapshot':snapshot,'sha256':digest(snapshot)}
            shots.validate_document(doc);plan.application={'revision':project['revision']+1,'shot_ids':payload.shot_ids,'timeline_version':state['version']+1,
                'timeline_sha256':digest(snapshot),'scope':scope,'acknowledged':True,'automatic_render':False,'provider_calls':0,'approval_invalidated':True}
            plan.version+=1;plan.updated_at=now();self.persist(con,project,plan,document=doc,action='studio_media_plan_applied_approval_invalidated')
        return self.page(project_id)

    def page(self,project_id):
        with self.store.transaction() as con:
            project=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project_id,)).fetchone());records=self.records(project['document'],source_con=con);latest={}
            for plan,sha in records:
                if plan.project_id!=project_id:raise WorkflowError('STUDIO_MEDIA_PLAN_SCOPE_INVALID')
                latest[plan.media_plan_id]=(plan,sha)
            try:context,state=self.context(con,project);input_sha=digest(context);reason=None
            except WorkflowError as error:
                if error.code not in {'STUDIO_MEDIA_PLAN_SCRIPT_REQUIRED','STUDIO_MEDIA_PLAN_USE_SOURCE_BROLL','SOURCE_MEDIA_CHANGED_OR_MISSING'}:raise
                context=None;input_sha=None;reason=error.code
            raw_records={(record['plan']['media_plan_id'],record['plan']['version']):record['plan'] for record in project['document'].get('studio_media_plans',[])}
            return {'schema_version':'native-storyboard-media-page-v1','current_algorithm':ALGORITHM,'supported_algorithms':sorted(SUPPORTED_ALGORITHMS),'workspace_id':self.workspace,'project_id':project_id,'revision':project['revision'],
                'timeline_version':state['version'] if context is not None else None,'input_sha256':input_sha,'input':context,'unavailable_reason':reason,
                # Return the exact hashed historical JSON, without adding new DTO defaults.
                'items':[{'plan':copy.deepcopy(raw_records[(plan.media_plan_id,plan.version)]),'sha256':sha,
                    'input_current':self.input_current(con,project,plan,input_sha) and plan.application is None,
                    'policy_current':plan.algorithm in SUPPORTED_ALGORITHMS} for plan,sha in latest.values()],
                'history_versions':len(records),'external_dispatches':0,'paid_operations':0,'publishing_enabled':False,'real_provider_tested':False}

    @staticmethod
    def reviewed_requests(plan):
        from .official_vision_evidence import ReviewedVision
        return [ReviewedVision.model_validate(v['request']) for v in (plan.input.get('reviewed_vision') or {}).get('items',[])]

    def input_current(self,con,project,plan,default_sha):
        if plan.algorithm not in SUPPORTED_ALGORITHMS:return False
        if plan.algorithm==ALGORITHM:return plan.input_sha256==default_sha
        try:
            context,_=self.context(con,project,self.reviewed_requests(plan))
            return plan.input_sha256==digest(context)
        except WorkflowError:return False
