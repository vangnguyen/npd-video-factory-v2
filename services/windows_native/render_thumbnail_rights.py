"""Finite current-Owner thumbnail exceptions; never license or publish authority."""
import base64,copy,json,re,uuid
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
from typing import Literal
from urllib.parse import parse_qsl,urlsplit
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.human_identity import HumanAuthVerifier,HumanPrincipal
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .official_publications import utc
from .render_thumbnails import NativeRenderThumbnails,PATTERN

SCHEMA='native-render-thumbnail-rights-review-v1'
PURPOSE='render_thumbnail_rights_exception'
FALSE_FLAGS=('rights_independently_verified','publishing_authorized','source_asset_rights_granted','provider_authorized',
    'canonical_timeline_mutated','project_revision_changed','final_video_approved','owner_uat_accepted','real_provider_tested')
TABLE='native_render_thumbnail_rights'

class Review(StrictModel):
    revision:StrictInt=Field(ge=1)
    thumbnail_asset_id:str=Field(pattern='^'+PATTERN+'$')
    expected_thumbnail_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_rights_input_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    action:Literal['grant','revoke']
    reason:str=Field(min_length=10,max_length=2000)
    evidence_reference:str=Field(min_length=5,max_length=1000)
    valid_days:StrictInt=Field(default=7,ge=1,le=30)
    allow_publishing_review:StrictBool=False
    acknowledged_thumbnail_rights_exception:Literal[True]
    acknowledged_not_independent_license_verification:Literal[True]
    override_id:str|None=Field(default=None,pattern=r'^nrto_[a-f0-9]{32}$')
    expected_override_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')

    @field_validator('acknowledged_thumbnail_rights_exception','acknowledged_not_independent_license_verification',mode='before')
    @classmethod
    def ack(cls,value):
        if value is not True:raise ValueError('Separate explicit Owner thumbnail exception review required')
        return value

    @field_validator('evidence_reference')
    @classmethod
    def reference(cls,value):
        try:
            parsed=urlsplit(value);parsed.port
            if (parsed.scheme not in ('http','https','document','library','upload') or parsed.username or parsed.password or parsed.fragment
                or parsed.scheme in ('http','https') and not parsed.hostname or any(ord(c)<32 for c in value)
                or any(re.search(r'(token|password|secret|api.?key|signature|credential|authorization)',k,re.I) for k,_ in parse_qsl(parsed.query))):raise ValueError()
        except Exception:raise ValueError('Only bounded human evidence references without credentials are permitted') from None
        return value

    @model_validator(mode='after')
    def action_fields(self):
        if (self.action=='grant' and (self.override_id is not None or self.expected_override_sha256 is not None)
            or self.action=='revoke' and (self.override_id is None or self.expected_override_sha256 is None or self.allow_publishing_review)):
            raise ValueError('Grant and revoke require separate original bindings')
        return self

class Create(Review):
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')

def stamp(value):
    if not isinstance(value,str):raise ValueError()
    parsed=datetime.fromisoformat(value)
    if parsed.utcoffset()!=timedelta(0):raise ValueError()
    return parsed.astimezone(timezone.utc)

class NativeRenderThumbnailRights:
    def __init__(self,thumbnails,*,enabled=False,identity_provider=None,clock=lambda:datetime.now(timezone.utc)):
        if (type(thumbnails) is not NativeRenderThumbnails or type(enabled) is not bool or not callable(clock)
            or identity_provider is not None and not callable(identity_provider)):raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_CONFIGURATION_INVALID',400)
        self.thumbnails,self.enabled,self.identity_provider,self.clock=thumbnails,enabled,identity_provider,clock
        self.store,self.config,self.workspace=thumbnails.store,thumbnails.config,thumbnails.workspace
        self._frozen=(thumbnails,enabled,identity_provider,clock,self.store,self.config,self.workspace,self.store.root.absolute())
        self.check()
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_render_thumbnail_rights (
                sequence INTEGER PRIMARY KEY,override_id TEXT UNIQUE NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                thumbnail_asset_id TEXT NOT NULL,action TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,
                snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,created_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256));
                CREATE INDEX IF NOT EXISTS native_render_thumbnail_rights_history ON native_render_thumbnail_rights(workspace_id,project_id,sequence);''')
            if con.execute('SELECT 1 FROM native_render_thumbnail_rights WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():
                raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_SCOPE_INVALID')

    def check(self):
        if self._frozen!=(self.thumbnails,self.enabled,self.identity_provider,self.clock,self.store,self.config,self.workspace,self.store.root.absolute()):
            raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_CONFIGURATION_CHANGED')
        self.thumbnails.check()

    def states(self):
        self.check()
        return {'schema_version':'native-render-thumbnail-rights-runtime-v1','workspace_id':self.workspace,'enabled':self.enabled,'purpose':PURPOSE,
            'current_owner_required':True,'separate_thumbnail_ack_required':True,'finite_expiry_required':True,'rights_status':'unknown',
            'license':None,'external_calls':0,'paid_operations':0,**{k:False for k in FALSE_FLAGS}}

    def identity(self,principal=None,authority=None):
        try:
            self.check();verifier=self.identity_provider() if self.identity_provider else None
            if type(verifier) is not HumanAuthVerifier:raise ValueError()
            if principal is not None and (type(principal) is not HumanPrincipal or principal.role_for(self.workspace)!='owner'):raise ValueError()
            token=principal.token_id if principal is not None else authority['token_id'];subject=principal.subject if principal is not None else authority['subject']
            record=verifier.registry.tokens.get(token);instant=utc(self.clock())
            if (record is None or not record.enabled or record.subject!=subject or utc(record.issued_at)>instant or instant>=utc(record.expires_at)
                or record.not_before is not None and utc(record.not_before)>instant):raise ValueError()
            current=HumanPrincipal(token_id=record.token_id,subject=record.subject,display_name=record.display_name,
                platform_role=record.platform_role,workspace_roles=record.workspace_roles,expires_at=record.expires_at)
            if current.role_for(self.workspace)!='owner' or principal is not None and principal!=current:raise ValueError()
            proof={'token_id':token,'subject':subject,'identity_revision_sha256':digest(record.model_dump(mode='json')),'expires_at':utc(record.expires_at).isoformat()}
            if authority is not None and authority!=proof:raise ValueError()
            return proof
        except Exception:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_CURRENT_OWNER_REQUIRED',403) from None

    def input(self,project,identity,*,con=None):
        self.check()
        with self.store.transaction() if con is None else nullcontext(con) as owned:
            self.thumbnails.connection(owned);row=self.thumbnails.get(project,identity,con=owned);s=row['snapshot'];b=s['input_binding']
            binding={'schema_version':'native-render-thumbnail-rights-input-v1','purpose':PURPOSE,'workspace_id':self.workspace,'project_id':project,
                'thumbnail_asset_id':identity,'thumbnail_snapshot_sha256':row['snapshot_sha256'],'thumbnail_request_sha256':row['request_sha256'],
                'render_job_id':s['request']['render_job_id'],'original_document_sha256':b['original_document_sha256'],
                'original_render_snapshot_sha256':b['original_snapshot_sha256'],'final_sha256':b['record']['observation']['rendered_video_sha256'],
                'image':copy.deepcopy(s['image']),'original_source_rights_review_still_required':True,**{k:False for k in FALSE_FLAGS}}
            return {'schema_version':'native-render-thumbnail-rights-input-view-v1','workspace_id':self.workspace,'project_id':project,
                'thumbnail_asset_id':identity,'rights_input_sha256':digest(binding),'binding':binding,'publishing_authorized':False}

    @staticmethod
    def ref(row):
        return None if row is None else {'override_id':row['override_id'],'sequence':row['sequence'],'snapshot_sha256':row['snapshot_sha256']}

    def row(self,con,project,identity):
        self.thumbnails.connection(con)
        if not isinstance(identity,str) or not re.fullmatch(r'nrto_[a-f0-9]{32}',identity):raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_NOT_FOUND',404)
        return con.execute('SELECT * FROM native_render_thumbnail_rights WHERE workspace_id=? AND project_id=? AND override_id=?',(self.workspace,project,identity)).fetchone()

    def latest(self,con,project,thumbnail,before=None):
        self.thumbnails.connection(con);sql='SELECT * FROM native_render_thumbnail_rights WHERE workspace_id=? AND project_id=? AND thumbnail_asset_id=?';params=[self.workspace,project,thumbnail]
        if before is not None:sql+=' AND sequence<?';params.append(before)
        return con.execute(sql+' ORDER BY sequence DESC LIMIT 1',params).fetchone()

    def read(self,con,row):
        self.check();self.thumbnails.connection(con)
        if row is None:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_NOT_FOUND',404)
        try:
            v=dict(row);s=json.loads(v['snapshot_json']);req=Review.model_validate(s['request']);authority=s['owner_identity'];created=stamp(v['created_at'])
            fields={'schema_version','purpose','override_id','sequence','workspace_id','project_id','thumbnail_asset_id','request','rights_input',
                'rights_input_sha256','previous_record','owner_identity','created_at','expires_at','actor_ref','external_calls','paid_operations',*FALSE_FLAGS}
            if (set(s)!=fields or s['schema_version']!=SCHEMA or s['purpose']!=PURPOSE or s['override_id']!=v['override_id']
                or not re.fullmatch(r'nrto_[a-f0-9]{32}',v['override_id']) or type(s['sequence']) is not int or s['sequence']!=v['sequence'] or s['sequence']<1
                or s['workspace_id']!=self.workspace or v['workspace_id']!=self.workspace or s['project_id']!=v['project_id']
                or s['thumbnail_asset_id']!=v['thumbnail_asset_id'] or req.thumbnail_asset_id!=v['thumbnail_asset_id'] or req.action!=v['action']
                or req.model_dump(mode='json')!=s['request'] or digest(s)!=v['snapshot_sha256'] or digest(s['request'])!=v['request_sha256']
                or any(s[k] is not False for k in FALSE_FLAGS) or any(type(s[k]) is not int or s[k]!=0 for k in ('external_calls','paid_operations'))
                or s['created_at']!=v['created_at'] or s['actor_ref']!=authority['token_id']
                or set(authority)!={'token_id','subject','identity_revision_sha256','expires_at'}
                or not all(isinstance(authority[k],str) and 1<=len(authority[k])<=200 for k in ('token_id','subject'))
                or not re.fullmatch(r'[a-f0-9]{64}',authority['identity_revision_sha256']) or created>=stamp(authority['expires_at'])):raise ValueError()
            view=self.input(v['project_id'],v['thumbnail_asset_id'],con=con)
            if (view['binding']!=s['rights_input'] or view['rights_input_sha256']!=s['rights_input_sha256']
                or req.expected_rights_input_sha256!=s['rights_input_sha256'] or req.expected_thumbnail_snapshot_sha256!=view['binding']['thumbnail_snapshot_sha256']):raise ValueError()
            previous=self.latest(con,v['project_id'],v['thumbnail_asset_id'],before=v['sequence'])
            if self.ref(previous)!=s['previous_record']:raise ValueError()
            if s['previous_record'] is not None and (type(s['previous_record']['sequence']) is not int or s['previous_record']['sequence']>=s['sequence']):raise ValueError()
            if previous is not None and digest(json.loads(previous['snapshot_json']))!=previous['snapshot_sha256']:raise ValueError()
            original=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(v['project_id'],req.revision)).fetchone()
            if original is None or previous is not None and created<stamp(previous['created_at']):raise ValueError()
            if req.action=='grant':
                selected=self.thumbnails.get(v['project_id'],v['thumbnail_asset_id'],con=con)
                if (s['expires_at'] is None or stamp(s['expires_at'])!=created+timedelta(days=req.valid_days) or original is None
                    or req.revision!=selected['snapshot']['request']['revision'] or digest(json.loads(original[0]))!=view['binding']['original_document_sha256']):raise ValueError()
            else:
                if previous is None or previous['action']!='grant' or previous['override_id']!=req.override_id or previous['snapshot_sha256']!=req.expected_override_sha256 or s['expires_at'] is not None:raise ValueError()
                self.read(con,previous)
            v.pop('key_sha256');v.pop('snapshot_json')
            return {**v,'schema_version':SCHEMA,'snapshot':s,'rights_status':'unknown','license':None,'rights_independently_verified':False,'publishing_authorized':False,'owner_uat_accepted':False}
        except WorkflowError:raise
        except Exception:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_EVIDENCE_INVALID') from None

    def current(self,con,project,request,*,physical):
        view=self.input(project,request.thumbnail_asset_id,con=con);selected=self.thumbnails.get(project,request.thumbnail_asset_id,con=con)
        if view['rights_input_sha256']!=request.expected_rights_input_sha256 or selected['snapshot_sha256']!=request.expected_thumbnail_snapshot_sha256:
            raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_INPUT_CHANGED')
        if physical:
            actual=self.store.editable(con,project,request.revision)
            if actual['revision']!=selected['snapshot']['request']['revision'] or digest(actual['document'])!=view['binding']['original_document_sha256']:
                raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_INPUT_CHANGED')
            self.thumbnails.image(project,request.thumbnail_asset_id,con=con)
        return view

    def record(self,project,payload,*,principal):
        self.check()
        try:
            if type(payload) is not Create or set(payload.__dict__)-set(Create.model_fields):raise ValueError()
            payload=Create.model_validate(payload.model_dump(mode='python'))
        except Exception:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_FIELDS_INVALID',400) from None
        authority=self.identity(principal)
        if payload.action=='grant' and not self.enabled:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_NOT_ENABLED',403)
        request=payload.model_dump(mode='json',exclude={'request_key'});fp=digest(request);key=digest(payload.request_key)
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_render_thumbnail_rights WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if old:
                if old['request_sha256']!=fp:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_IDEMPOTENCY_CONFLICT')
                return self.read(con,old),True
            self.store.editable(con,project,payload.revision);view=self.current(con,project,payload,physical=payload.action=='grant')
            prior=self.latest(con,project,payload.thumbnail_asset_id)
            if prior is not None:self.read(con,prior)
            if payload.action=='revoke' and (prior is None or prior['action']!='grant' or prior['override_id']!=payload.override_id or prior['snapshot_sha256']!=payload.expected_override_sha256):
                raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_ORIGINAL_GRANT_REQUIRED')
            created=utc(self.clock());sequence=con.execute('SELECT coalesce(max(sequence),0)+1 FROM native_render_thumbnail_rights').fetchone()[0];identity='nrto_'+uuid.uuid4().hex
            s={'schema_version':SCHEMA,'purpose':PURPOSE,'override_id':identity,'sequence':sequence,'workspace_id':self.workspace,'project_id':project,
                'thumbnail_asset_id':payload.thumbnail_asset_id,'request':request,'rights_input':view['binding'],'rights_input_sha256':view['rights_input_sha256'],
                'previous_record':self.ref(prior),'owner_identity':authority,'actor_ref':authority['token_id'],'created_at':created.isoformat(),
                'expires_at':(created+timedelta(days=payload.valid_days)).isoformat() if payload.action=='grant' else None,'external_calls':0,'paid_operations':0,**{k:False for k in FALSE_FLAGS}}
            if self.identity(principal,authority)!=authority or self.current(con,project,payload,physical=payload.action=='grant')!=view:
                raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_INPUT_CHANGED')
            con.execute('INSERT INTO native_render_thumbnail_rights VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                (sequence,identity,self.workspace,project,payload.thumbnail_asset_id,payload.action,key,fp,digest(s),json.dumps(s,ensure_ascii=False),s['created_at']))
            return self.read(con,self.row(con,project,identity)),False

    def get(self,project,identity,*,con=None):
        self.check()
        with self.store.transaction() if con is None else nullcontext(con) as owned:return self.read(owned,self.row(owned,project,identity))

    def active(self,project,thumbnail,*,publishing=True,con=None):
        self.check()
        if type(publishing) is not bool:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_FIELDS_INVALID',400)
        with self.store.transaction() if con is None else nullcontext(con) as owned:
            self.input(project,thumbnail,con=owned);row=self.latest(owned,project,thumbnail)
            if row is None:return None
            value=self.read(owned,row);s=value['snapshot'];request=Review.model_validate(s['request']);instant=utc(self.clock())
            if (not self.enabled or request.action!='grant' or publishing and not request.allow_publishing_review
                or not stamp(s['created_at'])<=instant<stamp(s['expires_at'])):return None
            try:self.identity(authority=s['owner_identity'])
            except WorkflowError:return None
            self.current(owned,project,request,physical=True)
            return {'schema_version':'native-render-thumbnail-current-owner-exception-v1','purpose':PURPOSE,'workspace_id':self.workspace,'project_id':project,
                'thumbnail_asset_id':thumbnail,'thumbnail_snapshot_sha256':request.expected_thumbnail_snapshot_sha256,'rights_input_sha256':s['rights_input_sha256'],
                'override_id':row['override_id'],'override_snapshot_sha256':row['snapshot_sha256'],'owner_identity_sha256':digest(s['owner_identity']),
                'created_at':s['created_at'],'expires_at':s['expires_at'],'allow_publishing_review':request.allow_publishing_review,
                'rights_status':'unknown','license':None,'original_source_rights_review_still_required':True,**{k:False for k in FALSE_FLAGS}}

    def page(self,project,*,limit=25,cursor=None):
        self.check();after=None
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_PAGE_INVALID',400)
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,1000}',cursor):raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if type(after) is not list or len(after)!=3 or after[:2]!=[self.workspace,project] or type(after[2]) is not int or after[2]<1:raise ValueError()
            except Exception:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND sequence<?';params.append(after[2])
            rows=con.execute('SELECT * FROM native_render_thumbnail_rights WHERE '+where+' ORDER BY sequence DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['sequence']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-render-thumbnail-rights-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.read(con,r) for r in rows[:limit]],
                'limit':limit,'next_cursor':next_cursor,'rights_status':'unknown','rights_independently_verified':False,'publishing_authorized':False,'owner_uat_accepted':False}
