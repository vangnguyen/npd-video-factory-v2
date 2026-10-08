"""Atomic storyboard-to-existing-provider job bindings; explicit work only.

This journal owns no worker, provider result, edit state or billing authority.
Existing stock/generation consumers retain all dispatch/import safeguards.
"""
import copy,hashlib,json,re,uuid
from typing import Literal
from pydantic import Field,StrictBool
from .contracts import WorkflowError,digest
from .store import now
from .studio_media_models import Action,SHOT,HASH,PLAN
from .generation_models import GenerationCreate,NativeImageParameters,NativeVideoParameters
from .stock_models import StockSearch,StockDownload
from .generation_models import GenerationImport
from .stock_models import StockImport
from app.models import StrictModel

IDENTITY=r'^nmr_[a-f0-9]{32}$'

class Generate(Action):
    shot_id:str=Field(pattern=SHOT)
    seed:int=Field(default=1,strict=True,ge=0,le=2147483647)
    external_acknowledged:StrictBool=False
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

class Search(Action):
    shot_id:str=Field(pattern=SHOT)
    provider:Literal['pexels','pixabay']
    external_acknowledged:StrictBool=False
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

class Download(Action):
    parent_resolution_id:str=Field(pattern=IDENTITY)
    expected_result_sha256:str=Field(pattern=HASH)
    candidate_id:str=Field(pattern=r'^smc_[a-f0-9]{24}$')
    expected_candidate_sha256:str=Field(pattern=HASH)
    external_acknowledged:StrictBool=False
    fixture_acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

class Import(StrictModel):
    revision:int=Field(ge=1,strict=True)
    expected_binding_sha256:str=Field(pattern=HASH)
    expected_fingerprint:str=Field(pattern=HASH)
    expected_asset_sha256:str=Field(pattern=HASH)
    acknowledged:StrictBool=False
    request_key:str=Field(min_length=16,max_length=100,pattern=r'^[A-Za-z0-9_-]+$')

class Binding(StrictModel):
    schema_version:Literal['native-storyboard-media-resolution-v1']
    resolution_id:str=Field(pattern=IDENTITY)
    workspace_id:str
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    media_plan_id:str=Field(pattern=PLAN)
    plan_version:int=Field(ge=1,strict=True)
    plan_sha256:str=Field(pattern=HASH)
    plan_fingerprint:str=Field(pattern=HASH)
    input_sha256:str=Field(pattern=HASH)
    shot_id:str=Field(pattern=SHOT)
    revision:int=Field(ge=1,strict=True)
    document_sha256:str=Field(pattern=HASH)
    request_fingerprint:str=Field(pattern=HASH)
    request:dict
    child_kind:Literal['generation','stock_search','stock_download']
    child_id:str
    child_fingerprint:str=Field(pattern=HASH)
    child_request_sha256:str=Field(pattern=HASH)
    parent_resolution_id:str|None=Field(default=None,pattern=IDENTITY)
    created_at:str
    actor_ref:str=Field(min_length=1,max_length=100)
    automatic_attachment:Literal[False]=False
    automatic_timeline_apply:Literal[False]=False
    provider_calls_at_creation:Literal[0]=0
    paid_operations_at_creation:Literal[0]=0

class NativeStudioMediaResolution:
    def __init__(self,planner,generation,stock):
        self.planner,self.generation,self.stock=planner,generation,stock;self.store,self.workspace=planner.store,planner.workspace
        if generation.queue.store is not self.store or stock.store is not self.store or generation.queue.workspace!=self.workspace or stock.workspace!=self.workspace:
            raise WorkflowError('STUDIO_MEDIA_RESOLUTION_CONFIGURATION_INVALID',400)
        with self.store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_media_resolution_bindings(name TEXT PRIMARY KEY,workspace_id TEXT NOT NULL)')
            con.execute('''CREATE TABLE IF NOT EXISTS native_media_resolutions(resolution_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                media_plan_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,binding_json TEXT NOT NULL,binding_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256))''')
            old=con.execute("SELECT workspace_id FROM native_media_resolution_bindings WHERE name='workspace'").fetchone()
            if old and old[0]!=self.workspace or con.execute('SELECT 1 FROM native_media_resolutions WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('STUDIO_MEDIA_RESOLUTION_WORKSPACE_CHANGED')
            con.execute("INSERT OR IGNORE INTO native_media_resolution_bindings VALUES('workspace',?)",(self.workspace,))

    def record(self,row):
        try:
            raw=json.loads(row['binding_json']);value=Binding.model_validate(raw)
            if (digest(raw)!=row['binding_sha256'] or value.workspace_id!=self.workspace or value.resolution_id!=row['resolution_id'] or value.project_id!=row['project_id']
                or value.media_plan_id!=row['media_plan_id'] or value.request_fingerprint!=row['request_fingerprint'] or value.request_fingerprint!=digest(value.request)
                or value.created_at!=row['created_at'] or not re.fullmatch(r'^[a-f0-9]{32}$' if value.child_kind=='generation' else r'^nstk_[a-f0-9]{32}$',value.child_id)):raise ValueError()
            return copy.deepcopy(raw)
        except (ValueError,KeyError,TypeError):raise WorkflowError('STUDIO_MEDIA_RESOLUTION_BINDING_INVALID') from None

    def raw(self,project,identity):
        with self.store.transaction() as con:
            row=con.execute('SELECT * FROM native_media_resolutions WHERE resolution_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
            if row is None:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_NOT_FOUND',404)
            return self.record(row)

    def replay(self,con,project,key,fingerprint):
        row=con.execute('SELECT * FROM native_media_resolutions WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
        if row:
            value=self.record(row)
            if value['request_fingerprint']!=fingerprint:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_IDEMPOTENCY_CONFLICT')
            return value
        return None

    def get(self,project,identity):
        binding=self.raw(project,identity);child=self.generation.get(project,binding['child_id']) if binding['child_kind']=='generation' else self.stock.get(project,binding['child_id'])
        request=child['snapshot']['request']
        if (child['workspace_id']!=self.workspace or child['project_id']!=project or child['request_fingerprint']!=binding['child_fingerprint']
            or digest(request)!=binding['child_request_sha256'] or child['snapshot']['document_sha256']!=binding['document_sha256'] or request['revision']!=binding['revision']):
            raise WorkflowError('STUDIO_MEDIA_RESOLUTION_CHILD_CHANGED')
        return {'binding':binding,'binding_sha256':digest(binding),'child':child,'automatic_attachment':False,'automatic_timeline_apply':False,'real_provider_acceptance_complete':False}

    def page(self,project):
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            values=[self.record(row) for row in con.execute('SELECT * FROM native_media_resolutions WHERE workspace_id=? AND project_id=? ORDER BY created_at,resolution_id',(self.workspace,project))]
        return {'schema_version':'native-storyboard-media-resolutions-page-v1','workspace_id':self.workspace,'project_id':project,
            'items':[self.get(project,value['resolution_id']) for value in values],'automatic_attachment':False,'automatic_timeline_apply':False}

    def create(self,project,plan_id,payload,*,actor):
        if type(payload) not in (Generate,Search,Download) or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_FIELDS_INVALID',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest()
        request.update(media_plan_id=plan_id,operation='generate' if type(payload) is Generate else 'search' if type(payload) is Search else 'download');fingerprint=digest(request)
        with self.store.transaction() as con:
            old=self.replay(con,project,key,fingerprint)
            if old is None:
                current=self.store.editable(con,project,payload.revision);plan,_,_=self.planner.bound(con,current,plan_id,payload)
        if old is not None:return self.get(project,old['resolution_id']),True
        parent=None
        if type(payload) is Download:
            parent=self.raw(project,payload.parent_resolution_id)
            if (parent['media_plan_id']!=plan_id or parent['child_kind']!='stock_search' or parent['input_sha256']!=plan.input_sha256
                or parent['plan_version']!=plan.version or parent['plan_sha256']!=payload.expected_plan_sha256):raise WorkflowError('STUDIO_MEDIA_RESOLUTION_PARENT_CHANGED')
            shot_id=parent['shot_id']
        else:shot_id=payload.shot_id
        item=next((value for value in plan.items if value.shot_id==shot_id),None)
        if item is None:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_SHOT_NOT_FOUND',404)
        if item.status=='selected':raise WorkflowError('STUDIO_MEDIA_RESOLUTION_EXISTING_ASSET_AVAILABLE')
        identity='nmr_'+uuid.uuid4().hex;native_key='studio-media-'+identity
        common={'revision':payload.revision,'external_acknowledged':payload.external_acknowledged,'fixture_acknowledged':payload.fixture_acknowledged,'request_key':native_key}
        if type(payload) is Generate:
            if item.strategy not in {'ai_image','ai_video'}:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_STRATEGY_CHANGED')
            if item.strategy in item.new_generation_budget_blocked:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_BUDGET_APPROVAL_REQUIRED')
            if item.strategy=='ai_image':parameters=NativeImageParameters(prompt=item.generation_prompt,aspect_ratio=item.target_aspect_ratio,seed=payload.seed)
            else:
                if item.duration_seconds>30:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_VIDEO_DURATION_UNSUPPORTED',400)
                parameters=NativeVideoParameters(prompt=item.generation_prompt,aspect_ratio=item.target_aspect_ratio,seed=payload.seed,duration_seconds=float(item.duration_seconds))
            native=GenerationCreate(**common,parameters=parameters);kind='generation'
        elif type(payload) is Search:
            if item.strategy not in {'stock_image','stock_video'}:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_STRATEGY_CHANGED')
            native=StockSearch(**common,provider=payload.provider,query=' '.join(item.query.split())[:200],media_type='image' if item.strategy=='stock_image' else 'video',
                orientation='landscape' if item.target_aspect_ratio=='16:9' else 'square' if item.target_aspect_ratio=='1:1' else 'portrait');kind='stock_search'
        else:
            if item.strategy not in {'stock_image','stock_video'}:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_STRATEGY_CHANGED')
            native=StockDownload(**common,search_id=parent['child_id'],expected_result_sha256=payload.expected_result_sha256,candidate_id=payload.candidate_id,expected_candidate_sha256=payload.expected_candidate_sha256);kind='stock_download'
        def admitted(con,current,child):
            old=self.replay(con,project,key,fingerprint)
            if old:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_REPLAY_AVAILABLE')
            current_plan,_,_=self.planner.bound(con,current,plan_id,payload)
            if current_plan.input_sha256!=plan.input_sha256:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_PLAN_CHANGED')
            if (con.execute('SELECT count(*) FROM native_media_resolutions WHERE workspace_id=? AND project_id=?',(self.workspace,project)).fetchone()[0]>=200
                or con.execute('SELECT count(*) FROM native_media_resolutions').fetchone()[0]>=5000):raise WorkflowError('STUDIO_MEDIA_RESOLUTION_HISTORY_LIMIT')
            stamp=now();binding=Binding(schema_version='native-storyboard-media-resolution-v1',resolution_id=identity,workspace_id=self.workspace,project_id=project,media_plan_id=plan_id,
                plan_version=plan.version,plan_sha256=payload.expected_plan_sha256,plan_fingerprint=plan.fingerprint,input_sha256=plan.input_sha256,shot_id=shot_id,revision=payload.revision,
                document_sha256=digest(current['document']),request_fingerprint=fingerprint,request=request,child_kind=kind,child_id=child['generation_id'] if kind=='generation' else child['stock_id'],
                child_fingerprint=child['request_fingerprint'],child_request_sha256=digest(child['snapshot']['request']),parent_resolution_id=parent['resolution_id'] if parent else None,created_at=stamp,actor_ref=actor).model_dump(mode='json')
            con.execute('INSERT INTO native_media_resolutions VALUES(?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,plan_id,key,fingerprint,json.dumps(binding),digest(binding),stamp))
            self.store.event(con,project,'studio_media_resolution_created',{'resolution_id':identity,'media_plan_id':plan_id,'plan_sha256':payload.expected_plan_sha256,
                'child_kind':kind,'child_id':binding['child_id'],'provider_calls':0,'paid_operations':0,'automatic_attachment':False,'automatic_timeline_apply':False})
        try:
            if kind=='generation':self.generation.queue.create(project,native,actor=actor,on_admitted=admitted);self.generation.wake.set()
            else:self.stock.create(project,native,actor=actor,on_admitted=admitted)
        except WorkflowError as error:
            if error.code!='STUDIO_MEDIA_RESOLUTION_REPLAY_AVAILABLE':raise
            with self.store.transaction() as con:old=self.replay(con,project,key,fingerprint)
            if old is None:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_REPLAY_MISSING')
            return self.get(project,old['resolution_id']),True
        return self.get(project,identity),False

    def attach(self,project,identity,payload,*,actor):
        if type(payload) is not Import:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_FIELDS_INVALID',400)
        value=self.get(project,identity);binding=value['binding']
        if payload.expected_binding_sha256!=value['binding_sha256']:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_BINDING_CHANGED')
        if binding['child_kind']=='stock_search':raise WorkflowError('STUDIO_MEDIA_RESOLUTION_IMPORT_REQUIRES_ASSET',400)
        body=payload.model_dump(mode='json');body.pop('expected_binding_sha256')
        # Provider cost/result observations legitimately stale the original plan.
        # Existing imports enforce current project CAS, exact result and frozen replay.
        service=self.generation if binding['child_kind']=='generation' else self.stock
        typed=(GenerationImport if binding['child_kind']=='generation' else StockImport).model_validate(body)
        receipt=service.attach(project,binding['child_id'],typed,actor=actor)
        return {**self.get(project,identity),'import_receipt':receipt,'replan_required':True}
