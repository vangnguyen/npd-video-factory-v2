"""Durable Source B-roll resolution over the existing provider consumers.

Each explicit step makes one bounded transition. Provider workers retain their
own costs, async reconciliation, bytes/rights and import authority. This module
owns no provider dispatch, second timeline, video approval or publishing switch.
"""
import copy,hashlib,json,re,uuid
from datetime import datetime,timezone
from decimal import Decimal
from .contracts import WorkflowError,digest,canonical
from .store import now
from . import source_broll as broll
from .source_broll_resolution_models import Create,Step,Apply,IDENTITY
from .stock_models import StockSearch,StockDownload,StockImport
from .generation_models import GenerationCreate,GenerationImport,NativeImageParameters,NativeVideoParameters
from .media import project_assets,_library_catalog,_verify_library_record
from .auto_edit_analysis import asset_reference
from app.broll_planner import supporting_candidates,tokens
from app.media_intelligence_models import MediaPlanRead

SCHEMA='native-source-broll-resolution.v1'
PRIORITY=['user_asset','licensed_stock','internal_library','ai_image','ai_video']
FINISHED={'resolved','unresolved'}
PHASES=FINISHED|{'choose','stock_search_wait','stock_download_wait','generation_wait','import_pending','select_imported',
    'needs_approval','recovery_required','needs_rights_review'}

def require(value,code):
    if not value:raise WorkflowError(code)

def resolution_priority(plan):
    configured=plan.configuration.resolver_priority
    ignored=configured[-1:] if configured[-1:] == ['motion_graphic'] else []
    priority=configured[:-1] if ignored else configured
    require(len(priority)==len(PRIORITY) and set(priority)==set(PRIORITY),
        'SOURCE_BROLL_RESOLUTION_PRIORITY_INVALID')
    return list(priority),[{'tier':tier,'status':'NOT_CONFIGURED','reason':'SOURCE_RESOLVER_UNSUPPORTED_OPTIONAL_TAIL','provider_calls':0} for tier in ignored]


class NativeSourceBrollResolution:
    def __init__(self,store,config,stock,generation,*,workspace_id,official_vision=lambda:None):
        self.store,self.config,self.stock,self.generation,self.workspace=store,config,stock,generation,workspace_id
        self.official_vision=official_vision
        require(stock.store is store and stock.workspace==workspace_id and generation.queue.store is store
            and generation.queue.workspace==workspace_id and config.data_root.resolve()==store.root.resolve(),
            'SOURCE_BROLL_RESOLUTION_SCOPE_INVALID')
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_source_broll_resolution_bindings(name TEXT PRIMARY KEY,workspace_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_source_broll_resolutions(resolution_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                version INTEGER NOT NULL,state_json TEXT NOT NULL,state_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_source_broll_resolution_events(sequence INTEGER PRIMARY KEY AUTOINCREMENT,resolution_id TEXT NOT NULL,
                project_id TEXT NOT NULL,action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_source_broll_resolution_requests(resolution_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                PRIMARY KEY(resolution_id,key_sha256));''')
            old=con.execute("SELECT workspace_id FROM native_source_broll_resolution_bindings WHERE name='workspace'").fetchone()
            require(not old or old[0]==workspace_id,'SOURCE_BROLL_RESOLUTION_WORKSPACE_CHANGED')
            require(not con.execute('SELECT 1 FROM native_source_broll_resolutions WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone(),
                'SOURCE_BROLL_RESOLUTION_WORKSPACE_CHANGED')
            con.execute("INSERT OR IGNORE INTO native_source_broll_resolution_bindings VALUES('workspace',?)",(workspace_id,))

    def provider_snapshot(self):
        # Constructing the existing adapters performs their immutable credential/
        # mode binding checks. It issues no request and opens no worker.
        for factory in self.stock.factories.values():factory.create(self.store.root,self.stock.cache_scope)
        return {'stock':self.stock.providers(),'image':self.generation.queue.selection(NativeImageParameters(prompt='B-roll capability inspection')),
            'video':self.generation.queue.selection(NativeVideoParameters(prompt='B-roll capability inspection'))}

    def planning_context(self,*,max_ai_cost_vnd='0',resolver_priority=None):
        providers=self.provider_snapshot()
        return {'workspace_id':self.workspace,'max_ai_cost_vnd':max_ai_cost_vnd,'provider_status':{
            'stock':'CONFIGURED' if any(value['status']=='CONFIGURED' for value in providers['stock']['items']) else 'NOT_CONFIGURED',
            'ai_image':providers['image']['status'],'ai_video':providers['video']['status'],'semantic_vision':'NOT_CONFIGURED'},
            **({'resolver_priority':copy.deepcopy(resolver_priority)} if resolver_priority is not None else {})}

    @staticmethod
    def source_proof(project):
        snapshot,analysis=broll.context(project);transcript=analysis.transcript
        record=next(r for r in project['document']['auto_edit_analyses'] if r['analysis']['analysis_id']==analysis.analysis_id)
        return {'analysis_id':analysis.analysis_id,'analysis_sha256':record['sha256'],
            'source_asset_sha256':analysis.provenance['source_asset_checksum'],
            'transcript_id':transcript.transcript_id if transcript else None,
            'transcript_sha256':digest(transcript.model_dump(mode='json')) if transcript else None,
            'canonical_version':project['document']['canonical_timeline']['version'],
            'canonical_sha256':project['document']['canonical_timeline']['sha256']}

    def library(self,con):
        result={}
        for identity,record in _library_catalog(self.store,con).items():
            asset=record['metadata']
            if asset.get('kind') not in {'image','video'}:continue
            try:_verify_library_record(self.store,record)
            except WorkflowError:continue
            result[identity]={'metadata':copy.deepcopy(asset),'metadata_sha256':digest(asset),
                'source_projects':copy.deepcopy(record['source_projects']),'metadata_conflict':False}
        return result

    def row(self,con,project,identity):
        row=con.execute('SELECT * FROM native_source_broll_resolutions WHERE resolution_id=? AND workspace_id=? AND project_id=?',
            (identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('SOURCE_BROLL_RESOLUTION_NOT_FOUND',404)
        return row

    def read(self,row):
        try:
            snapshot=json.loads(row['snapshot_json']);state=json.loads(row['state_json'])
            require(re.fullmatch(IDENTITY,row['resolution_id']) and row['workspace_id']==self.workspace
                and snapshot['schema_version']==SCHEMA and snapshot['resolution_id']==row['resolution_id']
                and snapshot['workspace_id']==self.workspace and snapshot['project_id']==row['project_id']
                and digest(snapshot)==row['snapshot_sha256'] and digest(state)==row['state_sha256']
                and snapshot['request_sha256']==row['request_sha256'] and row['version']>=1,
                'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
            require(set(state['items'])==set(snapshot['items']) and state['expected']['revision']>=snapshot['source_revision'],
                'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
            plan=MediaPlanRead.model_validate(snapshot['plan'])
            priority,ignored=resolution_priority(plan)
            require(digest(plan.model_dump(mode='json'))==snapshot['plan_sha256'] and snapshot['priority']==priority
                and snapshot.get('unsupported_resolution_tiers',ignored)==ignored
                and digest(snapshot['request'])==snapshot['request_sha256']
                and plan.project_id=='prj_'+row['project_id'] and plan.analysis_id==snapshot['source']['analysis_id']
                and state['expected']['media_plan_id']==plan.media_plan_id
                and {v.media_plan_item_id:v.model_dump(mode='json') for v in plan.items if v.media_plan_item_id in snapshot['items']}==snapshot['items']
                and str(plan.max_ai_cost_vnd)==snapshot['budget']['max_ai_cost_vnd'] and snapshot['budget']['planning_authorizes_payment'] is False,
                'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
            for value in state['items'].values():
                require(value['phase'] in PHASES and type(value['tier_index']) is int and 0<=value['tier_index']<=len(priority)
                    and type(value['stock_provider_index']) is int and 0<=value['stock_provider_index']<=len(snapshot['request']['stock_providers'])
                    and isinstance(value['children'],list) and isinstance(value['attempts'],list)
                    and (value['phase']!='resolved' or isinstance(value['selected_asset_id'],str)),
                    'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
                for child in value['children']:
                    require(child['kind'] in {'stock_search','stock_download','generation'}
                        and re.fullmatch(r'[a-f0-9]{32}' if child['kind']=='generation' else r'nstk_[a-f0-9]{32}',child['id'])
                        and all(re.fullmatch(r'[a-f0-9]{64}',child[k]) for k in ('fingerprint','request_sha256','document_sha256')),
                        'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
            require(state['status']==self.overall(state) or state['status']=='applied_review_required' and state['applied_receipt'] is not None,
                'SOURCE_BROLL_RESOLUTION_HISTORY_INVALID')
            return {'schema_version':SCHEMA,'resolution_id':row['resolution_id'],'workspace_id':self.workspace,'project_id':row['project_id'],
                'version':row['version'],'snapshot':snapshot,'snapshot_sha256':row['snapshot_sha256'],'state':state,'state_sha256':row['state_sha256'],
                'automatic_video_approval':False,'publishing_enabled':False,'provider_calls_at_creation':0}
        except (ValueError,TypeError,KeyError):raise WorkflowError('SOURCE_BROLL_RESOLUTION_HISTORY_INVALID') from None

    def get(self,project,identity):
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            return self.read(self.row(con,project,identity))

    def page(self,project):
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            values=[self.read(row) for row in con.execute('SELECT * FROM native_source_broll_resolutions WHERE workspace_id=? AND project_id=? ORDER BY created_at,resolution_id',
                (self.workspace,project))]
        return {'schema_version':'native-source-broll-resolution-page.v1','workspace_id':self.workspace,'project_id':project,'items':values,
            'provider_calls':0,'publishing_enabled':False}

    def event(self,con,identity,project,action,actor,evidence):
        con.execute('INSERT INTO native_source_broll_resolution_events(resolution_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (identity,project,action,actor,json.dumps(evidence),now()))

    @staticmethod
    def expected(project,plan):
        return {'revision':project['revision'],'document_sha256':digest(project['document']),
            'media_plan_id':plan.media_plan_id,'plan_version':plan.version,'plan_sha256':digest(plan.model_dump(mode='json'))}

    def create(self,project,payload,*,actor):
        require(type(payload) is Create and isinstance(actor,str) and 1<=len(actor)<=100,'SOURCE_BROLL_RESOLUTION_REQUEST_INVALID')
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();request_sha=digest(request)
        providers=self.provider_snapshot()
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_source_broll_resolutions WHERE workspace_id=? AND project_id=? AND key_sha256=?',
                (self.workspace,project,key)).fetchone()
            if old:
                require(old['request_sha256']==request_sha,'SOURCE_BROLL_RESOLUTION_IDEMPOTENCY_CONFLICT')
                return self.read(old),True
            current=self.store.editable(con,project,payload.revision);source=self.source_proof(current)
            require(source['canonical_version']==payload.expected_timeline_version,'SOURCE_BROLL_RESOLUTION_TIMELINE_CHANGED')
            plan=broll._plan(current['document'],payload.media_plan_id,payload.expected_plan_version)
            require(digest(plan.model_dump(mode='json'))==payload.expected_plan_sha256,'SOURCE_BROLL_RESOLUTION_PLAN_CHANGED')
            _,analysis=broll.context(current);broll._bound(plan,analysis)
            require(set(payload.item_ids)<={item.media_plan_item_id for item in plan.items},'SOURCE_BROLL_RESOLUTION_ITEM_INVALID')
            broll.reviewed.validate(self.store,self.config,current,plan,source_con=con,current=True,getter=self.official_vision)
            priority,ignored=resolution_priority(plan)
            require(con.execute('SELECT count(*) FROM native_source_broll_resolutions WHERE project_id=?',(project,)).fetchone()[0]<100,
                'SOURCE_BROLL_RESOLUTION_HISTORY_LIMIT')
            identity='nbr_'+uuid.uuid4().hex
            original_plan=plan.model_dump(mode='json');requested=list(payload.item_ids)
            if broll.reviewed.reviewed_plan(plan):
                # Retain exact reviewed history. The derivative uses its bound
                # source intent; no imported asset acquires fresh Vision review.
                original_id=plan.media_plan_id;plan=plan.model_copy(deep=True)
                plan.media_plan_id='mpl_'+uuid.uuid4().hex[:24];plan.version=1
                plan.fingerprint=digest({'algorithm':SCHEMA,'original_plan_sha256':digest(original_plan),'source':source,'resolution_id':identity})
                mapping={value.media_plan_item_id:'mpi_'+digest([identity,value.media_plan_item_id])[:24] for value in plan.items}
                for value in plan.items:
                    value.media_plan_item_id=mapping[value.media_plan_item_id];value.media_plan_id=plan.media_plan_id
                    value.provenance['inherited_reviewed_source_intent_only']=True
                media_mapping={value.media_asset_id:'mas_'+digest([identity,value.media_asset_id])[:24] for value in plan.media_assets}
                for evidence in plan.media_assets:
                    evidence.media_asset_id=media_mapping[evidence.media_asset_id]
                    evidence.media_plan_id=plan.media_plan_id;evidence.media_plan_item_id=mapping[evidence.media_plan_item_id]
                for value in plan.items:
                    if value.selected_media_asset_id:value.selected_media_asset_id=media_mapping[value.selected_media_asset_id]
                p=plan.provenance;p['algorithm']=SCHEMA
                reviewed_context=p.pop('reviewed_vision');reviewed_input=p.pop('reviewed_input')
                p['inherited_reviewed_source_history']={'original_plan_id':original_id,'original_plan':original_plan,
                    'original_plan_sha256':digest(original_plan),'reviewed_vision':reviewed_context,'reviewed_input':reviewed_input,
                    'new_asset_semantic_review_performed':False,'source_intent_recommendation_only':True}
                p['inherited_source_semantic_vision_used']=p.get('semantic_vision_used',False)
                p['semantic_vision_used']=False;plan.vision_analysis_id=None
                p['semantic_vision_used_for_new_assets']=False
                broll._persist(self.store,con,current,plan,'auto_edit_broll_reviewed_derivative_created')
                current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
                requested=[mapping[value] for value in requested]
            library=self.library(con)
            items={item.media_plan_item_id:item.model_dump(mode='json') for item in plan.items if item.media_plan_item_id in requested}
            snapshot={'schema_version':SCHEMA,'resolution_id':identity,'workspace_id':self.workspace,'project_id':project,
                'source_revision':current['revision'],'source_document_sha256':digest(current['document']),'source':source,
                'request':request,'request_sha256':request_sha,'plan':plan.model_dump(mode='json'),'plan_sha256':digest(plan.model_dump(mode='json')),
                'original_requested_plan_sha256':payload.expected_plan_sha256,
                'items':items,'library':library,'providers':providers,'priority':priority,'unsupported_resolution_tiers':ignored,
                'budget':{'max_ai_cost_vnd':str(plan.max_ai_cost_vnd),'cost_policy':copy.deepcopy(current['document'].get('cost_policy')),
                    'planning_authorizes_payment':False},'actor_ref':actor,'created_at':now()}
            state={'status':'queued','expected':self.expected(current,plan),'items':{item:{'tier_index':0,'phase':'choose',
                'stock_provider_index':0,'children':[],'attempts':[],'selected_asset_id':None,'error_code':None} for item in items},
                'applied_receipt':None}
            require(len(canonical(snapshot))<=2*1024*1024,'SOURCE_BROLL_RESOLUTION_HISTORY_LIMIT')
            con.execute('INSERT INTO native_source_broll_resolutions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,key,request_sha,json.dumps(snapshot),digest(snapshot),1,json.dumps(state),digest(state),now(),now()))
            self.event(con,identity,project,'created',actor,{'snapshot_sha256':digest(snapshot),'provider_calls':0,'paid_operations':0,'canonical_timeline_mutated':False})
            return self.read(self.row(con,project,identity)),False

    def replay(self,con,identity,key,request_sha):
        row=con.execute('SELECT * FROM native_source_broll_resolution_requests WHERE resolution_id=? AND key_sha256=?',(identity,key)).fetchone()
        if row is None:return None
        require(row['request_sha256']==request_sha,'SOURCE_BROLL_RESOLUTION_IDEMPOTENCY_CONFLICT')
        receipt=json.loads(row['receipt_json']);require(digest(receipt)==row['receipt_sha256'],'SOURCE_BROLL_RESOLUTION_RECEIPT_INVALID')
        return receipt

    def bound(self,con,project,session,revision):
        current=self.store.editable(con,project,revision);snapshot=session['snapshot'];state=session['state'];expected=state['expected']
        source_row=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',
            (project,snapshot['source_revision'])).fetchone()
        require(source_row is not None,'SOURCE_BROLL_RESOLUTION_SOURCE_HISTORY_MISSING')
        source_document=json.loads(source_row['document'])
        require(digest(source_document)==snapshot['source_document_sha256'] and self.source_proof({'id':project,'revision':snapshot['source_revision'],
            'document':source_document})==snapshot['source'],'SOURCE_BROLL_RESOLUTION_SOURCE_HISTORY_CHANGED')
        frozen_plan=broll._plan(source_document,snapshot['plan']['media_plan_id'],snapshot['plan']['version'])
        require(digest(frozen_plan.model_dump(mode='json'))==snapshot['plan_sha256'],'SOURCE_BROLL_RESOLUTION_PLAN_HISTORY_CHANGED')
        require(current['revision']==expected['revision'] and digest(current['document'])==expected['document_sha256'],
            'SOURCE_BROLL_RESOLUTION_PROJECT_CHANGED')
        require(self.source_proof(current)==snapshot['source'],'SOURCE_BROLL_RESOLUTION_SOURCE_CHANGED')
        require(self.provider_snapshot()==snapshot['providers'],'SOURCE_BROLL_RESOLUTION_PROVIDER_CHANGED')
        plan=broll._plan(current['document'],expected['media_plan_id'],expected['plan_version'])
        require(digest(plan.model_dump(mode='json'))==expected['plan_sha256'],'SOURCE_BROLL_RESOLUTION_PLAN_CHANGED')
        _,analysis=broll.context(current);broll._bound(plan,analysis)
        broll.shared_assets(current,self.config,rights_overrides=getattr(self.store,'rights_overrides',None))
        return current,plan

    def persist(self,con,session,state,actor,action,key,request_sha,*,extra=None):
        identity=session['resolution_id'];project=session['project_id'];version=session['version']+1
        require(len(canonical(state))<=2*1024*1024,'SOURCE_BROLL_RESOLUTION_HISTORY_LIMIT')
        changed=con.execute('UPDATE native_source_broll_resolutions SET version=?,state_json=?,state_sha256=?,updated_at=? WHERE resolution_id=? AND version=?',
            (version,json.dumps(state),digest(state),now(),identity,session['version']))
        require(changed.rowcount==1,'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
        receipt={'schema_version':'native-source-broll-resolution-transition.v1','resolution_id':identity,'project_id':project,'workspace_id':self.workspace,
            'version':version,'state_sha256':digest(state),'status':state['status'],'expected':copy.deepcopy(state['expected']),
            'action':action,'source_media_mutated':False,'automatic_video_approval':False,'publishing_enabled':False,**(extra or {})}
        con.execute('INSERT INTO native_source_broll_resolution_requests VALUES(?,?,?,?,?,?)',
            (identity,key,request_sha,json.dumps(receipt),digest(receipt),now()))
        self.event(con,identity,project,action,actor,{'receipt_sha256':digest(receipt),'state_sha256':digest(state)})
        return receipt

    @staticmethod
    def overall(state):
        phases={value['phase'] for value in state['items'].values()}
        if phases=={'resolved'}:return 'ready'
        for phase in ('recovery_required','needs_approval','waiting_provider','needs_rights_review'):
            if phase in phases:return phase
        if any(phase.endswith('_wait') for phase in phases):return 'waiting_provider'
        return 'unresolved' if phases<=FINISHED else 'queued'

    @staticmethod
    def allowed(asset):
        # No override or fixture metadata can grant new legal authority here.
        return asset.provenance.get('rights_status') in {'owned','licensed','verified'} or bool(
            asset.provenance.get('owner_rights_override') and not asset.provenance.get('fixture'))

    def ranked(self,current,plan,item,tier,snapshot):
        _,analysis=broll.context(current)
        assets=broll.shared_assets(current,self.config,rights_overrides=getattr(self.store,'rights_overrides',None))
        if tier=='internal_library':
            for identity,record in snapshot['library'].items():
                if identity in {a['id'] for a in project_assets(current['document'])}:continue
                live=_library_catalog(self.store).get(identity)
                require(live is not None and digest(live['metadata'])==record['metadata_sha256'],'SOURCE_BROLL_RESOLUTION_LIBRARY_CHANGED')
                _verify_library_record(self.store,live)
                raw=copy.deepcopy(live['metadata'])
                # A library reference retains its recorded rights/source. Its
                # rank is local lexical evidence, never a new provider result.
                projected=broll.asset_projection(current,raw,size_bytes=(self.store.root/'assets'/identity).stat().st_size,
                    timestamp=datetime.now(timezone.utc))
                projected.provenance['source_type']='internal_library'
                assets[asset_reference(raw)]=projected
        candidates=supporting_candidates(list(assets.values()),analysis,item.broll.search_query)
        result=[]
        for candidate in candidates:
            asset=assets[candidate['asset_id']];source=asset.provenance['source_type']
            actual='user_asset' if source=='user_upload' else 'internal_library' if source=='internal_library' else 'licensed_stock' if source=='stock' else (
                'ai_video' if asset.kind=='video' else 'ai_image')
            if actual==tier and candidate['relevance_score']>0 and self.allowed(asset):result.append((candidate,asset))
        return result

    def select_asset(self,con,current,plan,item,asset,state,item_state,tier):
        # Reuse the canonical plan evidence constructor; all writes share this
        # transaction with the resolution receipt/version.
        evidence=broll.selected_evidence(current['id'],plan,item,asset,'mas_'+uuid.uuid4().hex[:24],datetime.now(timezone.utc))
        plan.media_assets.append(evidence);item.selected_media_asset_id=evidence.media_asset_id;item.source_asset_id=asset.asset_id
        item.strategy='licensed_stock' if tier=='licensed_stock' else tier if tier in {'ai_image','ai_video'} else 'user_asset'
        item.status='resolved';item.needs_approval=False
        item.provenance.update(automatic_resolution_recommendation=True,resolution_tier=tier,
            resolution_source_evidence_sha256=digest(evidence.model_dump(mode='json')),video_approval_granted=False)
        plan.version+=1;plan.updated_at=datetime.now(timezone.utc);plan.unresolved_items=sum(value.status!='resolved' for value in plan.items)
        broll._persist(self.store,con,current,plan,'auto_edit_broll_resolution_selected')
        changed=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(current['id'],)).fetchone())
        state['expected']=self.expected(changed,plan);item_state.update(phase='resolved',selected_asset_id=asset.provenance['native_asset_id'],error_code=None)

    def child(self,project,value):
        service=self.generation if value['kind']=='generation' else self.stock
        child=service.get(project,value['id'])
        require(child['request_fingerprint']==value['fingerprint'] and digest(child['snapshot']['request'])==value['request_sha256']
            and child['snapshot']['document_sha256']==value['document_sha256'],'SOURCE_BROLL_RESOLUTION_CHILD_CHANGED')
        return child

    def recover_import(self,project,session):
        # An existing consumer's immutable import receipt is the only evidence
        # that may advance expected refs after a lost reply. Foreign edits fail.
        state=copy.deepcopy(session['state']);current=self.store.get(project)
        if current['revision']==state['expected']['revision'] and digest(current['document'])==state['expected']['document_sha256']:return session
        for value in state['items'].values():
            if value['phase']!='import_pending' or not value['children']:continue
            child=self.child(project,value['children'][-1]);receipt=child.get('attachment')
            if receipt and receipt['revision']==current['revision'] and receipt['document_sha256']==digest(current['document']):
                require(self.source_proof(current)==session['snapshot']['source'],'SOURCE_BROLL_RESOLUTION_SOURCE_CHANGED')
                state['expected'].update(revision=current['revision'],document_sha256=digest(current['document']))
                value.update(phase='select_imported',import_receipt=copy.deepcopy(receipt),imported_asset_id=receipt['asset_id'])
                with self.store.transaction() as con:
                    live=self.read(self.row(con,project,session['resolution_id']))
                    require(live['version']==session['version'],'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
                    con.execute('UPDATE native_source_broll_resolutions SET version=version+1,state_json=?,state_sha256=?,updated_at=? WHERE resolution_id=?',
                        (json.dumps(state),digest(state),now(),session['resolution_id']))
                    self.event(con,session['resolution_id'],project,'import_reply_recovered','native-source-resolver',{'import_receipt_sha256':digest(receipt)})
                    return self.read(self.row(con,project,session['resolution_id']))
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_PROJECT_CHANGED')

    def step(self,project,identity,payload,*,actor):
        require(type(payload) is Step and isinstance(actor,str) and 1<=len(actor)<=100,'SOURCE_BROLL_RESOLUTION_REQUEST_INVALID')
        request={'operation':'step',**payload.model_dump(mode='json')};key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();request_sha=digest(request)
        with self.store.transaction() as con:
            session=self.read(self.row(con,project,identity));old=self.replay(con,identity,key,request_sha)
            if old:return old,True
            require(session['version']==payload.expected_resolution_version,'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
        previous=session;session=self.recover_import(project,session)
        require(payload.revision in {previous['state']['expected']['revision'],session['state']['expected']['revision']},
            'SOURCE_BROLL_RESOLUTION_PROJECT_CHANGED')
        state=copy.deepcopy(session['state']);target=next((item for item,value in state['items'].items() if value['phase'] not in FINISHED),None)
        require(target is not None,'SOURCE_BROLL_RESOLUTION_ALREADY_FINISHED')
        value=state['items'][target];snapshot=session['snapshot'];priority=snapshot['priority'];tier=priority[min(value['tier_index'],len(priority)-1)]
        with self.store.transaction() as con:
            current,plan=self.bound(con,project,session,state['expected']['revision'])
        item=next(item for item in plan.items if item.media_plan_item_id==target)
        if value['phase'] in {'recovery_required','needs_approval'} and value['children']:
            # Owner/provider recovery belongs to the existing child consumer.
            # An explicit step only observes its durable status; it never issues
            # another submission or grants new cost approval.
            binding=value['children'][-1];child=self.child(project,binding)
            if child['status'] in {'queued','running','retry_scheduled','succeeded'}:
                value['phase']={'generation':'generation_wait','stock_search':'stock_search_wait','stock_download':'stock_download_wait'}[binding['kind']]
                value['error_code']=None
        if value['phase']=='choose':
            ranked=self.ranked(current,plan,item,tier,snapshot)
            if ranked:
                candidate,asset=ranked[0]
                if asset.provenance['native_asset_id'] not in {a['id'] for a in project_assets(current['document'])}:
                    raw=copy.deepcopy(snapshot['library'][asset.provenance['native_asset_id']]['metadata'])
                    with self.store.transaction() as con:
                        current,plan=self.bound(con,project,session,state['expected']['revision'])
                        self.store.append_media_in_transaction(con,project,current['revision'],raw)
                        current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
                        state['expected']=self.expected(current,plan)
                        value.update(phase='select_imported',imported_asset_id=raw['id'],import_receipt={'source':'internal_library',
                            'metadata_sha256':snapshot['library'][raw['id']]['metadata_sha256'],'source_projects':snapshot['library'][raw['id']]['source_projects']})
                        state['status']=self.overall(state)
                        return self.persist(con,session,state,actor,'library_attached',key,request_sha),False
                with self.store.transaction() as con:
                    current,plan=self.bound(con,project,session,state['expected']['revision']);item=next(i for i in plan.items if i.media_plan_item_id==target)
                    self.select_asset(con,current,plan,item,asset,state,value,tier)
                    state['status']=self.overall(state)
                    return self.persist(con,session,state,actor,'asset_selected',key,request_sha),False
            if tier in {'user_asset','internal_library'}:return self.fallback(project,session,state,target,tier,'NO_ELIGIBLE_MATCH',actor,key,request_sha)
            if tier=='licensed_stock':
                providers=snapshot['request']['stock_providers'];index=value['stock_provider_index']
                if index>=len(providers):return self.fallback(project,session,state,target,tier,'STOCK_PROVIDERS_EXHAUSTED',actor,key,request_sha)
                provider=providers[index];available=next(p for p in snapshot['providers']['stock']['items'] if p['provider']==provider)
                if available['status']!='CONFIGURED':
                    value['attempts'].append({'tier':tier,'provider':provider,'status':'NOT_CONFIGURED','provider_calls':0})
                    value['stock_provider_index']+=1
                    return self.save_transition(project,session,state,actor,'provider_not_configured',key,request_sha)
                mode=available['mode'];native=StockSearch(revision=current['revision'],provider=provider,
                    query=' '.join(item.broll.search_query.split())[:200],media_type=item.broll.preferred_media_type,
                    orientation='landscape' if current['document']['canonical_timeline']['snapshot']['aspect_ratio']=='16:9' else 'square' if
                    current['document']['canonical_timeline']['snapshot']['aspect_ratio']=='1:1' else 'portrait',limit=5,
                    external_acknowledged=snapshot['request']['external_acknowledged'],fixture_acknowledged=snapshot['request']['fixture_acknowledged'],
                    request_key=self.child_key(identity,target,'search-'+provider))
                phase='stock_search_wait';kind='stock_search'
            else:
                modality='image' if tier=='ai_image' else 'video';available=snapshot['providers'][modality]
                if available['status']!='CONFIGURED':return self.fallback(project,session,state,target,tier,'NOT_CONFIGURED',actor,key,request_sha)
                mode=available['mode']
                if mode=='official':
                    value.update(phase='needs_approval',error_code='AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH')
                    return self.save_transition(project,session,state,actor,'paid_generation_approval_required',key,request_sha)
                aspect=current['document']['canonical_timeline']['snapshot']['aspect_ratio']
                parameters=NativeImageParameters(prompt=item.broll.generation_prompt,aspect_ratio=aspect,seed=snapshot['request']['seed']) if modality=='image' else (
                    NativeVideoParameters(prompt=item.broll.generation_prompt,aspect_ratio=aspect,seed=snapshot['request']['seed'],duration_seconds=min(30.,float(item.broll.duration_seconds))))
                native=GenerationCreate(revision=current['revision'],parameters=parameters,fixture_acknowledged=snapshot['request']['fixture_acknowledged'],
                    external_acknowledged=snapshot['request']['external_acknowledged'],request_key=self.child_key(identity,target,tier))
                phase='generation_wait';kind='generation'
            require(snapshot['request']['fixture_acknowledged']==(mode=='fixture') and snapshot['request']['external_acknowledged']==(mode=='official'),
                'SOURCE_BROLL_RESOLUTION_PROVIDER_ACK_REQUIRED')
            return self.admit(project,session,state,target,native,kind,phase,actor,key,request_sha)
        if value['phase'] in {'stock_search_wait','stock_download_wait','generation_wait'}:
            child=self.child(project,value['children'][-1]);status=child['status']
            if status in {'queued','running','retry_scheduled'}:
                return self.save_transition(project,session,state,actor,'provider_wait_observed',key,request_sha,extra={'provider_status':status,'provider_calls':0})
            if status in {'recovery_required','needs_approval'}:
                value.update(phase=status,error_code=child.get('failure_code'))
                return self.save_transition(project,session,state,actor,'provider_requires_attention',key,request_sha)
            if status!='succeeded':return self.fallback(project,session,state,target,tier,status.upper(),actor,key,request_sha)
            if value['phase']=='stock_search_wait':
                from app.media_intelligence_logic import rank_stock_candidates
                from app.media_intelligence_models import StockMediaCandidateRead
                # Fixture bytes may exercise the complete download/import path;
                # their unknown rights remain unchanged and fail selection later.
                fixture=snapshot['request']['fixture_acknowledged'] and child['snapshot']['provider_mode']=='fixture'
                raw_candidates=child['result']['candidates']
                if any(v['rights_status']=='unknown' for v in raw_candidates):value['had_rights_unknown']=True
                candidates=[StockMediaCandidateRead.model_validate(v) for v in raw_candidates
                    if v['rights_status'] in {'owned','licensed','verified'} or fixture]
                candidates=rank_stock_candidates(candidates,query=item.broll.search_query,vision_description='')
                if not candidates:
                    value['stock_provider_index']+=1;value['phase']='choose'
                    return self.save_transition(project,session,state,actor,'stock_empty_fallback',key,request_sha)
                candidate=candidates[0].model_dump(mode='json')
                native=StockDownload(revision=current['revision'],search_id=child['stock_id'],candidate_id=candidate['candidate_id'],
                    expected_result_sha256=child['result_sha256'],expected_candidate_sha256=digest(candidate),
                    fixture_acknowledged=snapshot['request']['fixture_acknowledged'],external_acknowledged=snapshot['request']['external_acknowledged'],
                    request_key=self.child_key(identity,target,'download-'+str(value['stock_provider_index'])))
                value['selected_candidate_sha256']=digest(candidate)
                return self.admit(project,session,state,target,native,'stock_download','stock_download_wait',actor,key,request_sha)
            value['phase']='import_pending'
            return self.save_transition(project,session,state,actor,'provider_asset_ready',key,request_sha)
        if value['phase']=='import_pending':
            binding=value['children'][-1];child=self.child(project,binding);asset=child['result']['asset']
            payload_cls=GenerationImport if binding['kind']=='generation' else StockImport
            native=payload_cls(revision=current['revision'],expected_fingerprint=child['request_fingerprint'],expected_asset_sha256=asset['sha256'],
                acknowledged=True,request_key=self.child_key(identity,target,'import-'+str(len(value['children']))))
            consumer=self.generation if binding['kind']=='generation' else self.stock
            receipt=consumer.attach(project,binding['id'],native,actor=actor)
            current=self.store.get(project);require(receipt['document_sha256']==digest(current['document']),'SOURCE_BROLL_RESOLUTION_IMPORT_CHANGED')
            state['expected'].update(revision=current['revision'],document_sha256=digest(current['document']))
            value.update(phase='select_imported',imported_asset_id=asset['id'],import_receipt=copy.deepcopy(receipt))
            return self.save_transition(project,session,state,actor,'provider_asset_imported',key,request_sha,owned_import=True)
        if value['phase']=='select_imported':
            assets=broll.shared_assets(current,self.config,rights_overrides=getattr(self.store,'rights_overrides',None))
            raw=next((a for a in project_assets(current['document']) if a['id']==value['imported_asset_id']),None)
            asset=assets.get(asset_reference(raw)) if raw else None
            require(asset is not None,'SOURCE_BROLL_RESOLUTION_IMPORTED_ASSET_MISSING')
            if not self.allowed(asset):
                value['had_rights_unknown']=True
                return self.fallback(project,session,state,target,tier,'RIGHTS_NOT_CLEARED',actor,key,request_sha)
            with self.store.transaction() as con:
                current,plan=self.bound(con,project,session,state['expected']['revision']);item=next(i for i in plan.items if i.media_plan_item_id==target)
                self.select_asset(con,current,plan,item,asset,state,value,tier);state['status']=self.overall(state)
                return self.persist(con,session,state,actor,'imported_asset_selected',key,request_sha),False
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_ATTENTION_REQUIRED')

    @staticmethod
    def child_key(identity,item,stage):return 'source-broll-'+digest([identity,item,stage])[:48]

    def save_transition(self,project,session,state,actor,action,key,request_sha,*,extra=None,owned_import=False):
        state['status']=self.overall(state)
        with self.store.transaction() as con:
            live=self.read(self.row(con,project,session['resolution_id']));require(live['version']==session['version'],'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
            if owned_import:
                current=self.store.editable(con,project,state['expected']['revision'])
                require(digest(current['document'])==state['expected']['document_sha256'] and self.source_proof(current)==session['snapshot']['source'],
                    'SOURCE_BROLL_RESOLUTION_IMPORT_CHANGED')
            else:self.bound(con,project,session,session['state']['expected']['revision'])
            return self.persist(con,session,state,actor,action,key,request_sha,extra=extra),False

    def fallback(self,project,session,state,target,tier,reason,actor,key,request_sha):
        value=state['items'][target];value['attempts'].append({'tier':tier,'status':reason,'provider_calls_by_resolver':0})
        if tier=='licensed_stock' and reason!='STOCK_PROVIDERS_EXHAUSTED':value['stock_provider_index']+=1
        else:value['tier_index']+=1
        value['phase']='choose';value['error_code']=reason
        if value['tier_index']>=len(session['snapshot']['priority']):value['phase']='needs_rights_review' if value.get('had_rights_unknown') else 'unresolved'
        return self.save_transition(project,session,state,actor,'fallback_recorded',key,request_sha)

    def admit(self,project,session,state,target,native,kind,phase,actor,key,request_sha):
        def admitted(con,current,child):
            live=self.read(self.row(con,project,session['resolution_id']));require(live['version']==session['version'],'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
            self.bound(con,project,session,session['state']['expected']['revision'])
            state['items'][target]['children'].append({'kind':kind,'id':child['generation_id'] if kind=='generation' else child['stock_id'],
                'fingerprint':child['request_fingerprint'],'request_sha256':digest(child['snapshot']['request']),
                'document_sha256':child['snapshot']['document_sha256']})
            state['items'][target]['phase']=phase;state['status']='waiting_provider'
            self.persist(con,session,state,actor,'provider_job_admitted',key,request_sha,extra={'provider_calls':0,'paid_operations':0})
        if kind=='generation':
            _,replayed=self.generation.queue.create(project,native,actor=actor,on_admitted=admitted)
            if not replayed:self.generation.wake.set()
        else:_,replayed=self.stock.create(project,native,actor=actor,on_admitted=admitted)
        with self.store.transaction() as con:
            receipt=self.replay(con,session['resolution_id'],key,request_sha)
            require(receipt is not None,'SOURCE_BROLL_RESOLUTION_ADMISSION_RECEIPT_MISSING')
            return receipt,replayed

    def apply(self,project,identity,payload,*,actor):
        require(type(payload) is Apply,'SOURCE_BROLL_RESOLUTION_REQUEST_INVALID')
        request={'operation':'apply',**payload.model_dump(mode='json')};key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();request_sha=digest(request)
        with self.store.transaction() as con:
            session=self.read(self.row(con,project,identity));old=self.replay(con,identity,key,request_sha)
            if old:return old,True
            require(session['version']==payload.expected_resolution_version and session['state']['status']=='ready',
                'SOURCE_BROLL_RESOLUTION_NOT_READY')
            current,plan=self.bound(con,project,session,payload.revision)
            require(payload.expected_timeline_version==session['snapshot']['source']['canonical_version'],'SOURCE_BROLL_RESOLUTION_TIMELINE_CHANGED')
        state=copy.deepcopy(session['state']);result=[]
        def applied(con,current,canonical_state):
            live=self.read(self.row(con,project,identity));require(live['version']==session['version'],'SOURCE_BROLL_RESOLUTION_VERSION_CHANGED')
            state['expected']=self.expected(current,plan);state['status']='applied_review_required'
            state['applied_receipt']={'revision':current['revision'],'canonical_version':canonical_state['version'],'canonical_sha256':canonical_state['sha256'],
                'media_plan_id':plan.media_plan_id,'item_ids':sorted(state['items']),'human_preview_required':True,'video_approval_granted':False}
            result.append(self.persist(con,session,state,actor,'canonical_broll_applied',key,request_sha,extra=state['applied_receipt']))
        broll.apply(self.store,self.config,project,payload.revision,{'expected_version':payload.expected_timeline_version,'media_plan_id':plan.media_plan_id,
            'expected_plan_version':plan.version,'item_ids':list(state['items']),'replace_plan_clips':payload.replace_plan_clips},
            official_vision=self.official_vision,on_applied=applied)
        require(result,'SOURCE_BROLL_RESOLUTION_APPLY_RECEIPT_MISSING')
        return result[0],False
