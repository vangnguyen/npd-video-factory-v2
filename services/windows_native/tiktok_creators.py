"""Explicit same-grant TikTok account/creator reads and immutable post drafts.

No upload, publication, token refresh or automatic retry is performed here.
"""
import json,math,re,uuid
from dataclasses import asdict
from datetime import datetime,timedelta,timezone
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding,PublicationMetadata
from app.publishing_credentials import target_digest,PublishingCredentialError
from app.publishing_wire import PublishingWireError
from app.analytics_official import response_digest
from app.tiktok_credentials import account_request,confirm_account
from app.tiktok_upload import creator_request,creator_info,CreatorInfo,PostChoices,ChunkPlan,start_request
from .contracts import WorkflowError,digest
from .costs import CostLedger
from .official_publications import NativeOfficialPublications,utc
from .tiktok_connection import NativeTikTokFactory,Profile
from .publication_qc import project as project_qc

TABLE='native_tiktok_creator_checks'
RESPONSES='native_tiktok_creator_responses'
DRAFTS='native_tiktok_post_drafts'

class Check(StrictModel):
    revision:StrictInt=Field(ge=1)
    profile_id:str=Field(pattern=r'^ppf_[A-Za-z0-9_-]{4,60}$')
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_creator_read:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    valid_for_seconds:StrictInt=Field(default=600,ge=60,le=900)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_creator_read',mode='before')
    @classmethod
    def ack(cls,value):
        if value is not True:raise ValueError('Separate raw creator-read consent required')
        return value

class Action(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class Draft(StrictModel):
    revision:StrictInt=Field(ge=1)
    creator_check_id:str=Field(pattern=r'^ntcr_[a-f0-9]{32}$')
    expected_creator_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    final_job_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    expected_final_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    metadata:PublicationMetadata
    choices:PostChoices
    acknowledged_video_selection:Literal[True]
    acknowledged_ai_disclosure:Literal[True]
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_video_selection','acknowledged_ai_disclosure',mode='before')
    @classmethod
    def ack(cls,value):
        if value is not True:raise ValueError('Separate raw video/disclosure acknowledgment required')
        return value

def creator_dict(info):return asdict(info)|{'privacy_options':list(info.privacy_options)}
def parsed_creator(value):
    if type(value) is not dict or set(value)!={'username','nickname','privacy_options','comment_disabled','duet_disabled','stitch_disabled','max_duration_sec'}:raise ValueError()
    return CreatorInfo(**(value|{'privacy_options':tuple(value['privacy_options'])}))
def safe_code(error):
    value=getattr(error,'code','NATIVE_TIKTOK_CREATOR_READ_FAILED')
    return value if type(value) is str and re.fullmatch('[A-Z0-9_]{1,120}',value) else 'NATIVE_TIKTOK_CREATOR_READ_FAILED'

FACTORY_FIELDS={'schema_version','target','configuration_sha256','target_binding_sha256','credential_alias','credential_present','credential_verified','status','mock','creator_reads_enabled','profile','token_returned','publishing_enabled','publication_dispatch_supported','real_provider_tested'}

class NativeTikTokCreators:
    def __init__(self,publications,*,factories=None,enabled=False):
        if type(publications) is not NativeOfficialPublications or type(enabled) is not bool:raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONFIGURATION_INVALID',400)
        self.publications=publications;self.store=publications.store;self.workspace=publications.workspace;self.clock=publications.clock;self.enabled=enabled
        self.factories=dict(factories or {});self.costs=CostLedger(self.store)
        if len(self.factories)>50 or any(type(f) is not NativeTikTokFactory or k!=f.profile.target.profile_id or f.root!=self.store.root.absolute() or f.workspace!=self.workspace for k,f in self.factories.items()):raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONFIGURATION_INVALID',400)
        self.frozen=(publications,self.store,self.workspace,self.clock,self.enabled,self.costs,self.store.root.absolute(),self.store.db.absolute(),tuple(sorted(self.factories.items())))
        self.check()
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_tiktok_creator_checks (
            check_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,status TEXT NOT NULL,
            result_sha256 TEXT,result_json TEXT,failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_tiktok_creator_responses (
            check_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,operation TEXT NOT NULL,
            response_sha256 TEXT NOT NULL,cost_operation_id TEXT NOT NULL,summary_sha256 TEXT NOT NULL,summary_json TEXT NOT NULL,
            PRIMARY KEY(check_id,operation));
            CREATE TABLE IF NOT EXISTS native_tiktok_post_drafts (
            draft_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            con.execute('CREATE UNIQUE INDEX IF NOT EXISTS native_tiktok_draft_key ON '+DRAFTS+'(workspace_id,project_id,key_sha256)')
            if con.execute('SELECT 1 FROM '+TABLE+' WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone() or con.execute('SELECT 1 FROM '+DRAFTS+' WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_TIKTOK_CREATOR_WORKSPACE_CHANGED')
    def check(self):
        if ((self.publications,self.store,self.workspace,self.clock,self.enabled,self.costs,self.store.root.absolute(),self.store.db.absolute(),tuple(sorted(self.factories.items())))!=self.frozen
            or type(self.enabled) is not bool or type(self.costs) is not CostLedger or self.costs.store is not self.store):raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONFIGURATION_CHANGED')
        for factory in self.factories.values():factory.check()
    def identity(self,principal=None,*,authority=None):
        self.check()
        try:
            current=self.publications.identity(principal,**({'token_id':authority['token_id'],'subject':authority['subject']} if authority else {}))
            if authority is not None and current!=authority:raise ValueError()
            return current
        except Exception:raise WorkflowError('NATIVE_TIKTOK_CURRENT_OWNER_REQUIRED',403) from None
    def states(self):
        self.check();return {'schema_version':'native-tiktok-creator-runtime-v1','workspace_id':self.workspace,'enabled':self.enabled,'default_enabled':False,
            'factories':[f.public() for _,f in sorted(self.factories.items())],'token_returned':False,'publishing_enabled':False,
            'publication_dispatch_supported':False,'automatic_retry':False,'real_provider_tested':False}
    def event(self,con,project,ref,action,actor,**evidence):
        # Reuse the owned workflow event ledger; no metadata/content or secret.
        self.store.event(con,project,'tiktok.creator.'+action,{'reference':ref,'actor_ref':actor,**evidence})
    def row(self,con,project,identity,table=TABLE):
        row=con.execute('SELECT * FROM '+table+' WHERE '+('check_id' if table==TABLE else 'draft_id')+'=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_TIKTOK_CREATOR_NOT_FOUND',404)
        return row
    def read(self,row):
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));request=Check.model_validate({**snapshot['request'],'request_key':'internal-tiktok-creator-key'});profile=Profile.model_validate(snapshot['factory']['profile'])
            if (set(snapshot)!={'schema_version','workspace_id','project_id','request','factory','authority','document_sha256','cipher_sha256','consented_at','deadline','mock','token_returned','publishing_enabled'}
                or snapshot['schema_version']!='native-tiktok-creator-snapshot-v1' or digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_sha256']
                or not re.fullmatch('ntcr_[a-f0-9]{32}',value['check_id']) or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace or snapshot['project_id']!=value['project_id']
                or set(snapshot['factory'])!=FACTORY_FIELDS or snapshot['factory']['schema_version']!='native-tiktok-publishing-factory-v1'
                or profile.target.workspace_id!=self.workspace or profile.target.profile_id!=request.profile_id or snapshot['factory']['target']!=profile.target.model_dump(mode='json')
                or snapshot['factory']['configuration_sha256']!=request.expected_configuration_sha256 or snapshot['factory']['target_binding_sha256']!=target_digest(profile.target)
                or not re.fullmatch('[a-z][a-z0-9-]{3,79}',snapshot['factory']['credential_alias'])
                or type(snapshot['factory']['credential_present']) is not bool or snapshot['factory']['credential_verified'] is not False
                or type(snapshot['factory']['creator_reads_enabled']) is not bool or snapshot['factory']['status'] not in ('READ_CONFIGURED','NOT_CONFIGURED')
                or snapshot['factory']['creator_reads_enabled'] is not (snapshot['factory']['status']=='READ_CONFIGURED')
                or snapshot['factory']['status']=='READ_CONFIGURED' and snapshot['factory']['credential_present'] is not True
                or type(snapshot['mock']) is not bool or snapshot['mock'] is not request.acknowledged_protocol_mock or snapshot['factory']['mock'] is not snapshot['mock']
                or any(snapshot[k] is not False for k in ('token_returned','publishing_enabled')) or any(snapshot['factory'][k] is not False for k in ('token_returned','publishing_enabled','publication_dispatch_supported','real_provider_tested'))
                or set(snapshot['authority'])!={'token_id','subject','identity_revision_sha256','expires_at'}
                or any(type(snapshot['authority'][k]) is not str or not snapshot['authority'][k] for k in ('token_id','subject'))
                or not re.fullmatch('[a-f0-9]{64}',snapshot['authority']['identity_revision_sha256']) or not re.fullmatch('[a-f0-9]{64}',snapshot['document_sha256'])
                or snapshot['cipher_sha256'] is not None and not re.fullmatch('[a-f0-9]{64}',snapshot['cipher_sha256'])
                or (utc(datetime.fromisoformat(snapshot['deadline']))-utc(datetime.fromisoformat(snapshot['consented_at']))).total_seconds()!=request.valid_for_seconds
                or utc(datetime.fromisoformat(snapshot['deadline']))>utc(datetime.fromisoformat(snapshot['authority']['expires_at']))
                or value['status'] not in ('not_configured','pending','claimed','succeeded','failed','review_required','outcome_unknown','cancelled')):raise ValueError()
            result_raw=value.pop('result_json');result=json.loads(result_raw) if result_raw is not None else None
            if (result is not None)!=bool(value['result_sha256']) or result is not None and digest(result)!=value['result_sha256'] or value['status']=='succeeded' and result is None:raise ValueError()
            if result is not None:
                if set(result)!={'schema_version','target_binding_sha256','account','creator','account_response_sha256','creator_response_sha256','mock','token_returned','publishing_enabled','real_provider_tested'}:raise ValueError()
                parsed_creator(result['creator'])
                if (result['schema_version']!='native-tiktok-creator-result-v1' or result['target_binding_sha256']!=target_digest(profile.target) or result['account']!={'target_account_id':profile.target.target_account_id,'target_binding_sha256':target_digest(profile.target),'source':'tiktok.user.info.open_id','account_match':True}
                    or result['mock'] is not snapshot['mock'] or any(result[k] is not False for k in ('token_returned','publishing_enabled','real_provider_tested'))
                    or any(not re.fullmatch('[a-f0-9]{64}',result[k]) for k in ('account_response_sha256','creator_response_sha256'))):raise ValueError()
            value.pop('key_sha256');return {**value,'snapshot':snapshot,'result':result,'token_returned':False,'publishing_enabled':False}
        except Exception:raise WorkflowError('NATIVE_TIKTOK_CREATOR_EVIDENCE_CHANGED') from None
    def links(self,con,value):
        for row in con.execute('SELECT * FROM '+RESPONSES+' WHERE check_id=?',(value['check_id'],)).fetchall():
            try:
                summary=json.loads(row['summary_json']);cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(row['cost_operation_id'],)).fetchone();operation='tiktok_creator.'+row['operation']+'.'+value['check_id']
                if (row['workspace_id']!=self.workspace or row['project_id']!=value['project_id'] or row['operation'] not in ('account','creator') or digest(summary)!=row['summary_sha256']
                    or cost is None or cost['id']!=digest({'project':value['project_id'],'job':None,'provider':'official-tiktok','operation':operation})
                    or cost['operation']!=operation or cost['provider']!='official-tiktok' or cost['project_id']!=value['project_id'] or cost['job_id'] is not None or cost['model'] is not None
                    or cost['paid']!=0 or cost['external_call']!=int(not value['snapshot']['mock']) or cost['estimated_cost'] is not None or cost['actual_cost'] is not None
                    or cost['request_sha256']!=digest({'check_id':value['check_id'],'snapshot_sha256':value['snapshot_sha256'],'operation':row['operation']})
                    or cost['status']!='response_received' or json.loads(cost['receipt'])['provider_response_sha256']!=row['response_sha256']):raise ValueError()
                if value['result'] is not None and (row['response_sha256']!=value['result'][row['operation']+'_response_sha256'] or summary!=value['result'][row['operation']]):raise ValueError()
            except Exception:raise WorkflowError('NATIVE_TIKTOK_CREATOR_RESPONSE_CHANGED') from None
        if value['result'] is not None and con.execute('SELECT count(*) FROM '+RESPONSES+' WHERE check_id=?',(value['check_id'],)).fetchone()[0]!=2:raise WorkflowError('NATIVE_TIKTOK_CREATOR_RESPONSE_CHANGED')
    def get(self,project,identity):
        self.check()
        with self.store.transaction() as con:value=self.read(self.row(con,project,identity));self.links(con,value);return value
    def fence(self,con,value,*,claimed=False):
        self.check();snapshot=value['snapshot'];self.identity(authority=snapshot['authority']);request=Check.model_validate({**snapshot['request'],'request_key':'internal-tiktok-creator-key'})
        project=self.store.editable(con,value['project_id'],request.revision)
        if digest(project['document'])!=snapshot['document_sha256'] or not utc(datetime.fromisoformat(snapshot['consented_at']))<=utc(self.clock())<utc(datetime.fromisoformat(snapshot['deadline'])):raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONSENT_CHANGED')
        factory=self.factories.get(request.profile_id)
        if not self.enabled or factory is None or factory.public()!=snapshot['factory'] or factory.public()['status']!='READ_CONFIGURED' or factory.cipher()!=snapshot['cipher_sha256']:raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONFIGURATION_CHANGED')
        if claimed and value['status']!='claimed':raise WorkflowError('NATIVE_TIKTOK_CREATOR_CLAIM_CHANGED')
        self.links(con,value);return factory
    def create(self,project,payload,*,principal):
        self.check();payload=Check.model_validate(payload.model_dump(mode='json') if type(payload) is Check else payload);authority=self.identity(principal);request=payload.model_dump(mode='json',exclude={'request_key'})
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM '+TABLE+' WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,digest(payload.request_key))).fetchone()
            if prior:
                if prior['request_sha256']!=digest(request):raise WorkflowError('NATIVE_TIKTOK_CREATOR_IDEMPOTENCY_CONFLICT')
                value=self.read(prior);self.links(con,value);return value,True
            current=self.store.editable(con,project,payload.revision);factory=self.factories.get(payload.profile_id)
            if factory is None:raise WorkflowError('NATIVE_TIKTOK_CREATOR_NOT_CONFIGURED',503)
            public=factory.public()
            if public['configuration_sha256']!=payload.expected_configuration_sha256 or public['mock'] is not payload.acknowledged_protocol_mock:raise WorkflowError('NATIVE_TIKTOK_CREATOR_BINDING_CHANGED')
            stamp=utc(self.clock());deadline=stamp+timedelta(seconds=payload.valid_for_seconds)
            if deadline>utc(datetime.fromisoformat(authority['expires_at'])):raise WorkflowError('NATIVE_TIKTOK_CREATOR_OWNER_WINDOW_REQUIRED',403)
            snapshot={'schema_version':'native-tiktok-creator-snapshot-v1','workspace_id':self.workspace,'project_id':project,'request':request,'factory':public,'authority':authority,
                'document_sha256':digest(current['document']),'cipher_sha256':factory.cipher() if public['credential_present'] else None,'consented_at':stamp.isoformat(),'deadline':deadline.isoformat(),
                'mock':public['mock'],'token_returned':False,'publishing_enabled':False}
            identity='ntcr_'+uuid.uuid4().hex;status='pending' if self.enabled and public['status']=='READ_CONFIGURED' else 'not_configured'
            con.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,digest(payload.request_key),digest(request),digest(snapshot),json.dumps(snapshot),status,None,None,None,stamp.isoformat(),stamp.isoformat()))
            self.identity(authority=authority);self.event(con,project,identity,'prepared',authority['token_id'],status=status,mock=public['mock'])
        return self.get(project,identity),False
    async def fetch(self,project,identity,*,principal,expected_snapshot_sha256):
        self.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity));self.links(con,value)
            if value['snapshot_sha256']!=expected_snapshot_sha256:raise WorkflowError('NATIVE_TIKTOK_CREATOR_SNAPSHOT_CHANGED')
            if value['status']=='succeeded':return value
            if value['status']!='pending':raise WorkflowError('NATIVE_TIKTOK_CREATOR_NOT_PENDING')
            factory=self.fence(con,value);con.execute('UPDATE '+TABLE+" SET status='claimed',updated_at=? WHERE check_id=?",(utc(self.clock()).isoformat(),identity))
        cost=None;sent=False;response_seen=False;outputs={};hashes={}
        try:
            credential=factory.credential(now=self.clock(),expected_cipher_sha256=value['snapshot']['cipher_sha256'])
            for operation,builder,parser in (('account',lambda:account_request(credential),lambda response:confirm_account(response,credential.target)),('creator',lambda:creator_request(credential.token),lambda response:creator_dict(creator_info(response)))):
                cost=self.costs.begin(project_id=project,provider='official-tiktok',model=None,operation='tiktok_creator.'+operation+'.'+identity,
                    request_sha256=digest({'check_id':identity,'snapshot_sha256':value['snapshot_sha256'],'operation':operation}),estimated_cost=None,paid=False,external_call=not value['snapshot']['mock'])
                with self.store.transaction() as con:self.fence(con,self.read(self.row(con,project,identity)),claimed=True)
                fresh=factory.credential(now=self.clock(),expected_cipher_sha256=value['snapshot']['cipher_sha256'])
                if fresh!=credential:raise WorkflowError('NATIVE_TIKTOK_CREATOR_CREDENTIAL_CHANGED')
                with self.store.transaction() as con:self.fence(con,self.read(self.row(con,project,identity)),claimed=True)
                sent=True;response_seen=False;response=await factory.client.request(builder());response_seen=True;sha=response_digest(response)
                self.costs.settle(cost,status='response_received',response_sha256=sha);summary=parser(response)
                with self.store.transaction() as con:
                    self.fence(con,self.read(self.row(con,project,identity)),claimed=True)
                    con.execute('INSERT INTO '+RESPONSES+' VALUES(?,?,?,?,?,?,?,?)',(identity,self.workspace,project,operation,sha,cost,digest(summary),json.dumps(summary)))
                outputs[operation]=summary;hashes[operation+'_response_sha256']=sha;sent=False;cost=None
            result={'schema_version':'native-tiktok-creator-result-v1','target_binding_sha256':target_digest(credential.target),**outputs,**hashes,'mock':value['snapshot']['mock'],'token_returned':False,'publishing_enabled':False,'real_provider_tested':False}
            with self.store.transaction() as con:
                self.fence(con,self.read(self.row(con,project,identity)),claimed=True)
                con.execute('UPDATE '+TABLE+" SET status='succeeded',result_sha256=?,result_json=?,updated_at=? WHERE check_id=?",(digest(result),json.dumps(result),utc(self.clock()).isoformat(),identity))
                self.event(con,project,identity,'read_completed',value['snapshot']['authority']['token_id'],mock=value['snapshot']['mock'],publishing_enabled=False)
        except Exception as error:
            failure=safe_code(error);status='outcome_unknown' if sent and not response_seen else 'review_required' if response_seen else 'failed'
            if cost is not None and self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown' if sent else 'rejected',error_code=failure)
            with self.store.transaction() as con:
                con.execute('UPDATE '+TABLE+' SET status=?,failure_code=?,updated_at=? WHERE check_id=? AND status=\'claimed\'',(status,failure,utc(self.clock()).isoformat(),identity))
                self.event(con,project,identity,'stopped','system:creator-read',status=status,failure_code=failure)
        return self.get(project,identity)
    def cancel(self,project,identity,payload,*,principal):
        self.identity(principal);payload=Action.model_validate(payload.model_dump(mode='json') if type(payload) is Action else payload)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity))
            if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_TIKTOK_CREATOR_SNAPSHOT_CHANGED')
            if value['status']=='claimed':raise WorkflowError('NATIVE_TIKTOK_CREATOR_BUSY')
            con.execute('UPDATE '+TABLE+" SET status='cancelled',updated_at=? WHERE check_id=?",(utc(self.clock()).isoformat(),identity))
            self.event(con,project,identity,'cancelled',principal.token_id,publishing_enabled=False)
        return self.get(project,identity)
    def recover(self):
        self.check();costs=[]
        with self.store.transaction() as con:
            rows=con.execute('SELECT * FROM '+TABLE+" WHERE workspace_id=? AND status='claimed'",(self.workspace,)).fetchall()
            for row in rows:
                self.read(row)
                for operation in ('account','creator'):
                    costs.append(digest({'project':row['project_id'],'job':None,'provider':'official-tiktok','operation':'tiktok_creator.'+operation+'.'+row['check_id']}))
                con.execute('UPDATE '+TABLE+" SET status='outcome_unknown',failure_code='NATIVE_TIKTOK_CREATOR_RECOVERY_NO_REPLAY',updated_at=? WHERE check_id=?",(utc(self.clock()).isoformat(),row['check_id']))
                self.event(con,row['project_id'],row['check_id'],'recovery_unknown','system:recovery',publishing_enabled=False)
        for cost in costs:
            with self.store.transaction() as con:exists=con.execute('SELECT 1 FROM native_cost_operations WHERE id=?',(cost,)).fetchone()
            if exists and self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown',error_code='NATIVE_TIKTOK_CREATOR_RECOVERY_NO_REPLAY')
        return len(rows)
    def read_draft(self,row):
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));payload=Draft.model_validate({**snapshot['request'],'request_key':'internal-tiktok-draft-key'});source=snapshot['creator_check']
            public_fields={'check_id','workspace_id','project_id','request_sha256','snapshot_sha256','status','result_sha256','failure_code','created_at','updated_at','snapshot','result','token_returned','publishing_enabled'}
            if set(source)!=public_fields:raise ValueError()
            source_row={k:v for k,v in source.items() if k not in ('snapshot','result','token_returned','publishing_enabled')}
            source_row.update(snapshot_json=json.dumps(source['snapshot']),result_json=json.dumps(source['result']) if source['result'] is not None else None,key_sha256='internal-reconstruction')
            if self.read(source_row)!=source:raise ValueError()
            media=snapshot['source'];authority=snapshot['authority'];prepared=utc(datetime.fromisoformat(snapshot['prepared_at']))
            if (set(media)!={'final_job_id','final_sha256','final_bytes','job_snapshot_sha256','job_result_sha256','document_sha256','final_review','duration_sec'}
                or type(media['final_bytes']) is not int or not 1<=media['final_bytes']<=512*1024*1024
                or any(type(media[k]) is not str or not re.fullmatch('[a-f0-9]{64}',media[k]) for k in ('final_sha256','job_snapshot_sha256','job_result_sha256','document_sha256'))
                or type(media['duration_sec']) not in (int,float) or not math.isfinite(media['duration_sec']) or media['duration_sec']<=0
                or media['document_sha256']!=source['snapshot']['document_sha256'] or payload.revision!=source['snapshot']['request']['revision']
                or type(media['final_review']) is not dict or media['final_review'].get('decision')!='approve' or media['final_review'].get('artifact_sha256')!=media['final_sha256']
                or media['final_review'].get('snapshot_sha256')!=media['job_snapshot_sha256']
                or set(authority)!={'token_id','subject','identity_revision_sha256','expires_at'}
                or any(type(authority[k]) is not str or not authority[k] for k in ('token_id','subject'))
                or not re.fullmatch('[a-f0-9]{64}',authority['identity_revision_sha256'])
                or not utc(datetime.fromisoformat(source['snapshot']['consented_at']))<=prepared<utc(datetime.fromisoformat(source['snapshot']['deadline']))
                or prepared>=utc(datetime.fromisoformat(authority['expires_at']))):raise ValueError()
            profile=Profile.model_validate(source['snapshot']['factory']['profile'])
            start_request(payload.metadata,ChunkPlan(media['final_bytes'],profile.chunk_size),'EXPLICIT-UNSENT-TIKTOK-DRAFT-TOKEN',creator=parsed_creator(source['result']['creator']),choices=payload.choices,
                duration_sec=media['duration_sec'],client_audited=profile.api_client_audited,media_location=profile.media_location)
            if (set(snapshot)!={'schema_version','workspace_id','project_id','request','creator_check','source','prepared_at','authority','token_returned','publishing_enabled','publish_approval_required'}
                or snapshot['schema_version']!='native-tiktok-post-draft-v1' or not re.fullmatch('ntpd_[a-f0-9]{32}',value['draft_id']) or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace or snapshot['project_id']!=value['project_id']
                or digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_sha256'] or source['status']!='succeeded' or source['check_id']!=payload.creator_check_id
                or source['result_sha256']!=payload.expected_creator_result_sha256 or snapshot['source']['final_job_id']!=payload.final_job_id or snapshot['source']['final_sha256']!=payload.expected_final_sha256
                or any(snapshot[k] is not False for k in ('token_returned','publishing_enabled')) or snapshot['publish_approval_required'] is not True):raise ValueError()
            value.pop('key_sha256');return {**value,'snapshot':snapshot,'token_returned':False,'publishing_enabled':False,'publish_approval_required':True}
        except Exception:raise WorkflowError('NATIVE_TIKTOK_DRAFT_EVIDENCE_CHANGED') from None
    def draft_links(self,con,value):
        source=self.read(self.row(con,value['project_id'],value['snapshot']['request']['creator_check_id']))
        if any(source[k]!=value['snapshot']['creator_check'][k] for k in ('snapshot','result','snapshot_sha256','result_sha256')):raise WorkflowError('NATIVE_TIKTOK_DRAFT_CREATOR_CHANGED')
        self.links(con,source)
        media=value['snapshot']['source'];job=self.store.job(con.execute('SELECT * FROM jobs WHERE id=? AND project_id=?',(media['final_job_id'],value['project_id'])).fetchone(),con)
        if (job['kind']!='render' or job['status']!='succeeded' or digest(job['snapshot'])!=media['job_snapshot_sha256'] or digest(job['result'])!=media['job_result_sha256']
            or job['final_review']!=media['final_review'] or project_qc(job).get('duration_seconds')!=media['duration_sec'] or job['result']['qc']['final_sha256']!=media['final_sha256']):
            raise WorkflowError('NATIVE_TIKTOK_DRAFT_FINAL_CHANGED')
    def get_draft(self,project,identity):
        self.check()
        with self.store.transaction() as con:
            value=self.read_draft(self.row(con,project,identity,DRAFTS));self.draft_links(con,value);return value
    def draft(self,project,payload,*,principal):
        self.check();payload=Draft.model_validate(payload.model_dump(mode='python') if type(payload) is Draft else payload);authority=self.identity(principal);request=payload.model_dump(mode='json',exclude={'request_key'})
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM '+DRAFTS+' WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,digest(payload.request_key))).fetchone()
            if prior:
                if prior['request_sha256']!=digest(request):raise WorkflowError('NATIVE_TIKTOK_DRAFT_IDEMPOTENCY_CONFLICT')
                value=self.read_draft(prior);self.draft_links(con,value);return value,True
            current=self.store.editable(con,project,payload.revision);value=self.read(self.row(con,project,payload.creator_check_id));self.links(con,value);factory=self.fence(con,value)
            if value['status']!='succeeded' or value['result_sha256']!=payload.expected_creator_result_sha256:raise WorkflowError('NATIVE_TIKTOK_DRAFT_CREATOR_CHANGED')
            job,sha,path=self.publications.publications.render(con,project,payload.final_job_id);qc=project_qc(job)
            if sha!=payload.expected_final_sha256 or job['revision']!=payload.revision or digest(job['snapshot']['document'])!=digest(current['document']):raise WorkflowError('NATIVE_TIKTOK_DRAFT_FINAL_CHANGED')
            info=parsed_creator(value['result']['creator'])
            start_request(payload.metadata,ChunkPlan(path.stat().st_size,factory.profile.chunk_size),'EXPLICIT-UNSENT-TIKTOK-DRAFT-TOKEN',creator=info,choices=payload.choices,
                duration_sec=qc.get('duration_seconds'),client_audited=factory.profile.api_client_audited,media_location=factory.profile.media_location)
            source={'final_job_id':job['id'],'final_sha256':sha,'final_bytes':path.stat().st_size,'job_snapshot_sha256':digest(job['snapshot']),'job_result_sha256':digest(job['result']),
                'document_sha256':digest(current['document']),'final_review':job['final_review'],'duration_sec':qc.get('duration_seconds')}
            snapshot={'schema_version':'native-tiktok-post-draft-v1','workspace_id':self.workspace,'project_id':project,'request':request,'creator_check':value,'source':source,
                'prepared_at':utc(self.clock()).isoformat(),'authority':authority,'token_returned':False,'publishing_enabled':False,'publish_approval_required':True}
            identity='ntpd_'+uuid.uuid4().hex;self.identity(authority=authority);self.fence(con,value)
            con.execute('INSERT INTO '+DRAFTS+' VALUES(?,?,?,?,?,?,?,?)',(identity,self.workspace,project,digest(payload.request_key),digest(request),digest(snapshot),json.dumps(snapshot),utc(self.clock()).isoformat()))
            self.event(con,project,identity,'draft_prepared',authority['token_id'],publishing_enabled=False)
        return self.get_draft(project,identity),False
    def page(self,project,*,kind='check',limit=25,cursor=None):
        self.check();table,prefix,field=(TABLE,'ntcr_','check_id') if kind=='check' else (DRAFTS,'ntpd_','draft_id')
        if kind not in ('check','draft') or type(limit) is not int or not 1<=limit<=100 or cursor is not None and (type(cursor) is not str or not re.fullmatch(prefix+'[a-f0-9]{32}',cursor)):raise WorkflowError('NATIVE_TIKTOK_CREATOR_PAGE_INVALID',400)
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());params=[self.workspace,project];clause=''
            if cursor:
                anchor=self.row(con,project,cursor,table);clause=' AND (created_at<? OR (created_at=? AND '+field+'<?))';params.extend([anchor['created_at'],anchor['created_at'],cursor])
            rows=con.execute('SELECT * FROM '+table+' WHERE workspace_id=? AND project_id=?'+clause+' ORDER BY created_at DESC,'+field+' DESC LIMIT ?',(*params,limit+1)).fetchall()
        items=[self.get(project,row['check_id']) if kind=='check' else self.get_draft(project,row['draft_id']) for row in rows[:limit]]
        return {'schema_version':'native-tiktok-creator-page-v1','kind':kind,'workspace_id':self.workspace,'project_id':project,'items':items,
            'next_cursor':items[-1][field] if len(rows)>limit else None,'truncated':len(rows)>limit,'token_returned':False,'publishing_enabled':False}
