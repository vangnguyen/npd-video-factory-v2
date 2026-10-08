"""Explicit Owner OAuth operations; durable one-use claims, no background renewal.

Secrets stay in the immutable private vault. No runtime or credential resolver is
activated here; a successful grant is not account, read or publish approval.
"""
import asyncio,base64,hashlib,json,re,uuid
from datetime import datetime,timedelta
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,ValidationError,field_validator,model_validator
from .contracts import WorkflowError,digest
from .costs import CostLedger
from .google_oauth_vault import NativeGoogleOAuthVault,SecretReceipt
from .official_publications import NativeOfficialPublications,utc
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.google_oauth_protocol import (GoogleDesktopClient,GoogleOAuthTokenClient,GoogleOAuthError,
    authorization,exchange_request,refresh_request,parse_tokens,loopback)

TABLES=('native_google_oauth_authorizations','native_google_oauth_operations','native_google_oauth_events')
STATUSES={'claimed','succeeded','failed','outcome_unknown','review_required'}

def at(value):return utc(datetime.fromisoformat(value))
def typed(value,kind):
    try:
        if type(value) is not kind or set(value.__dict__)-set(kind.model_fields):raise ValueError()
        return kind.model_validate(value.model_dump(mode='python',warnings=False))
    except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_FIELDS_INVALID',400) from None

class Slot(StrictModel):
    slot_id:str=Field(pattern=r'^ngos_[a-f0-9]{32}$')
    target:PublishingTargetBinding
    client:SecretReceipt
    client_id:str=Field(min_length=1,max_length=256)
    scopes:list[str]=Field(min_length=2,max_length=3)
    @model_validator(mode='after')
    def bound(self):
        if self.client.kind!='client' or self.client.workspace_id!=self.target.workspace_id or self.client.target_binding_sha256!=target_digest(self.target) or len(set(self.scopes))!=len(self.scopes):raise ValueError('Dedicated client receipt required')
        GoogleDesktopClient(self.target,self.client.purpose,self.client_id,frozenset(self.scopes));return self

class Consent(StrictModel):
    revision:StrictInt=Field(ge=1)
    slot_id:str=Field(pattern=r'^ngos_[a-f0-9]{32}$')
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_credential_operation:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    valid_for_seconds:StrictInt=Field(default=600,ge=60,le=900)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_credential_operation',mode='before')
    @classmethod
    def acknowledge(cls,value):
        if value is not True:raise ValueError('Separate explicit credential consent required')
        return value

class Start(Consent):
    schema_version:Literal['native-google-oauth-start-v1']='native-google-oauth-start-v1'
    redirect_uri:str=Field(min_length=1,max_length=256)
    @field_validator('redirect_uri')
    @classmethod
    def redirect(cls,value):return loopback(value)

class Refresh(Consent):
    schema_version:Literal['native-google-oauth-refresh-v1']='native-google-oauth-refresh-v1'
    source_operation_id:str=Field(pattern=r'^ngop_[a-f0-9]{32}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class Cancel(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class NativeGoogleOAuthOperations:
    def __init__(self,publications,vault,*,slots=None,client=None,enabled=False):
        if type(publications) is not NativeOfficialPublications or type(vault) is not NativeGoogleOAuthVault or type(enabled) is not bool:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        self.publications,self.store,self.workspace,self.clock=publications,publications.store,publications.workspace,publications.clock
        self.vault,self.client,self.enabled=vault,GoogleOAuthTokenClient() if client is None else client,enabled
        if type(self.client) is not GoogleOAuthTokenClient or vault.root!=self.store.root.absolute() or vault.workspace!=self.workspace:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        self.slots={key:typed(value,Slot) for key,value in dict(slots or {}).items()}
        if len(self.slots)>50 or any(key!=s.slot_id or s.target.workspace_id!=self.workspace for key,s in self.slots.items()):raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_INVALID',400)
        self.slot_sha=digest({k:v.model_dump(mode='json') for k,v in self.slots.items()})
        self.costs=CostLedger(self.store)
        self.frozen=(publications,self.store,self.workspace,self.clock,self.store.root.absolute(),vault,self.client,enabled,self.costs,self.slot_sha)
        self.frozen_identity_provider=publications.identity_provider;self.frozen_accounts=publications.accounts
        self.check()
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_google_oauth_authorizations (
            authorization_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,status TEXT NOT NULL,
            operation_id TEXT UNIQUE,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_google_oauth_operations (
            operation_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,source_ref TEXT NOT NULL,
            status TEXT NOT NULL,cost_operation_id TEXT,result_sha256 TEXT,result_json TEXT,failure_code TEXT,
            created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256),UNIQUE(workspace_id,source_ref));
            CREATE TABLE IF NOT EXISTS native_google_oauth_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,reference TEXT NOT NULL,
            action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            for table in TABLES:
                if con.execute('SELECT 1 FROM '+table+' WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_GOOGLE_OAUTH_WORKSPACE_CHANGED')
    def check(self):
        try:
            if type(self.enabled) is not bool or (self.publications,self.store,self.workspace,self.clock,self.store.root.absolute(),self.vault,self.client,self.enabled,self.costs,self.slot_sha)!=self.frozen:raise ValueError()
            if self.publications.store is not self.store or self.publications.workspace!=self.workspace or self.publications.clock is not self.clock or self.costs.store is not self.store:raise ValueError()
            if self.publications.identity_provider is not self.frozen_identity_provider or self.publications.accounts is not self.frozen_accounts or self.frozen_accounts.store is not self.store or self.frozen_accounts.workspace!=self.workspace:raise ValueError()
            if digest({k:typed(v,Slot).model_dump(mode='json') for k,v in self.slots.items()})!=self.slot_sha:raise ValueError()
            self.publications.accounts.check_workspace();self.vault.check();self.client.check()
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONFIGURATION_CHANGED') from None
    def configured(self):self.check();return self.enabled and (self.client.mock or self.client.network_enabled)
    def states(self):
        return {'schema_version':'native-google-oauth-runtime-v1','workspace_id':self.workspace,'enabled':self.configured(),'default_enabled':False,
            'slots':[s.model_dump(mode='json') for _,s in sorted(self.slots.items())],'automatic_refresh':False,'startup_decryption':False,
            'account_verified':False,'token_returned':False,'publishing_enabled':False,'production_consent_renewed':False,'real_provider_tested':False}
    def identity(self,principal=None,authority=None):
        try:
            self.check();current=self.publications.identity(principal,**({'token_id':authority['token_id'],'subject':authority['subject']} if authority else {}))
            if authority is not None and current!=authority:raise ValueError()
            return current
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CURRENT_OWNER_REQUIRED',403) from None
    def event(self,con,project,ref,action,actor,**evidence):
        con.execute('INSERT INTO native_google_oauth_events(workspace_id,project_id,reference,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (self.workspace,project,ref,action,actor,json.dumps(evidence),utc(self.clock()).isoformat()))
    def slot(self,payload):
        self.check();slot=self.slots.get(payload.slot_id)
        if slot is None or slot.client.configuration_sha256!=payload.expected_configuration_sha256 or payload.acknowledged_protocol_mock is not self.client.mock:raise WorkflowError('NATIVE_GOOGLE_OAUTH_SLOT_BINDING_CHANGED')
        return slot
    def private_client(self,slot):
        self.check();client=self.vault.client(slot.client)
        if client.target!=slot.target or client.client_id!=slot.client_id or client.scopes!=frozenset(slot.scopes) or client.purpose!=slot.client.purpose or client.fingerprint()!=slot.client.configuration_sha256:raise WorkflowError('NATIVE_GOOGLE_OAUTH_SLOT_BINDING_CHANGED')
        return client
    def source(self,con,project,payload):return self.store.editable(con,project,payload.revision)
    def row(self,con,project,identity,kind):
        self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        table=TABLES[0] if kind=='authorization' else TABLES[1];column='authorization_id' if kind=='authorization' else 'operation_id'
        row=con.execute('SELECT * FROM '+table+' WHERE '+column+'=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_NOT_FOUND',404)
        return row
    def read(self,row,kind):
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));value.pop('key_sha256');cls=Start if kind=='authorization' or snapshot['operation']=='authorization_code' else Refresh
            request=cls.model_validate({**snapshot['request'],'request_key':'internal-google-oauth-key'});slot=Slot.model_validate(snapshot['slot'])
            common={'schema_version','workspace_id','project_id','request','authority','slot','document_sha256','mock','approved_at','deadline',
                'token_returned','publishing_enabled','production_consent_renewed','account_verified','automatic_refresh'}
            extra=({'authorization_receipt'} if kind=='authorization' else {'operation','source_ref','source_snapshot_sha256','authorization_receipt'} if snapshot['operation']=='authorization_code' else {'operation','source_ref','source_result_sha256','previous_grant_receipt'})
            if (digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_sha256'] or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace
                or set(snapshot)!=common|extra
                or snapshot['project_id']!=value['project_id'] or slot.slot_id!=request.slot_id or slot.client.configuration_sha256!=request.expected_configuration_sha256
                or slot.target.workspace_id!=self.workspace or type(snapshot['mock']) is not bool or snapshot['mock'] is not request.acknowledged_protocol_mock
                or not re.fullmatch(r'[a-f0-9]{64}',snapshot['document_sha256']) or at(snapshot['deadline'])<=at(snapshot['approved_at'])
                or (at(snapshot['deadline'])-at(snapshot['approved_at'])).total_seconds()!=request.valid_for_seconds or at(snapshot['deadline'])>at(snapshot['authority']['expires_at'])
                or set(snapshot['authority'])!={'token_id','subject','identity_revision_sha256','expires_at'} or not re.fullmatch(r'[a-f0-9]{64}',snapshot['authority']['identity_revision_sha256'])
                or any(snapshot[k] is not False for k in ('token_returned','publishing_enabled','production_consent_renewed','account_verified','automatic_refresh'))):raise ValueError()
            if kind=='authorization':
                if snapshot['schema_version']!='native-google-oauth-authorization-snapshot-v1' or value['status'] not in {'not_configured','awaiting_callback','consumed','cancelled','expired'}:raise ValueError()
                receipt=snapshot['authorization_receipt']
                if receipt is not None:
                    r=SecretReceipt.model_validate(receipt)
                    if r.kind!='authorization' or any(getattr(r,k)!=getattr(slot.client,k) for k in ('workspace_id','purpose','credential_alias','configuration_sha256','target_binding_sha256')):raise ValueError()
                elif value['status']!='not_configured':raise ValueError()
                if (value['status']=='consumed')!=(value['operation_id'] is not None):raise ValueError()
            else:
                if snapshot['schema_version']!='native-google-oauth-operation-snapshot-v1' or value['status'] not in STATUSES or snapshot['operation'] not in {'authorization_code','refresh_token'} or snapshot['source_ref']!=value['source_ref']:raise ValueError()
                result=json.loads(value.pop('result_json')) if value['result_json'] is not None else None
                if (result is not None)!=bool(value['result_sha256']) or result is not None and digest(result)!=value['result_sha256'] or (value['status']=='succeeded')!=(result is not None):raise ValueError()
                if result is not None:
                    r=SecretReceipt.model_validate(result['grant_receipt']);proof=result['grant_proof']
                    if (r.kind!='grant' or any(getattr(r,k)!=getattr(slot.client,k) for k in ('workspace_id','purpose','credential_alias','configuration_sha256','target_binding_sha256'))
                        or set(result)!={'schema_version','grant_receipt','grant_proof','response_sha256','http_status','cost_operation_id','credential_selected'}
                        or result['schema_version']!='native-google-oauth-result-v1' or result['credential_selected'] is not False or type(result['http_status']) is not int or result['http_status']!=200
                        or result['cost_operation_id']!=value['cost_operation_id'] or not re.fullmatch(r'[a-f0-9]{64}',result['response_sha256'])
                        or set(proof)!={'schema_version','target_binding_sha256','configuration_sha256','purpose','scopes','obtained_at','expires_at','refresh_expires_at','mock','token_returned','account_verified','publishing_enabled','production_consent_renewed','real_provider_tested'}
                        or proof['schema_version']!='google-oauth-grant-proof-v1'
                        or proof['configuration_sha256']!=r.configuration_sha256 or proof['target_binding_sha256']!=r.target_binding_sha256 or proof['purpose']!=r.purpose
                        or proof['scopes']!=sorted(slot.scopes) or proof['mock'] is not snapshot['mock'] or at(proof['expires_at'])<=at(proof['obtained_at'])
                        or not at(snapshot['approved_at'])<=at(proof['obtained_at'])<at(snapshot['deadline']) or at(proof['expires_at'])>at(proof['obtained_at'])+timedelta(days=1)
                        or proof['refresh_expires_at'] is not None and at(proof['refresh_expires_at'])<=at(proof['obtained_at'])
                        or any(proof[k] is not False for k in ('token_returned','account_verified','publishing_enabled','production_consent_renewed','real_provider_tested'))):raise ValueError()
                value['result']=result
            return {**value,'snapshot':snapshot,'schema_version':'native-google-oauth-'+kind+'-v1','token_returned':False,'publishing_enabled':False,'automatic_refresh':False,'real_provider_tested':False}
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_EVIDENCE_CHANGED') from None
    def get(self,project,identity,*,kind='operation'):
        if kind not in ('operation','authorization'):raise WorkflowError('NATIVE_GOOGLE_OAUTH_FIELDS_INVALID',400)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity,kind),kind);self.links(con,project,value,kind);return value
    def links(self,con,project,value,kind):
        """Historical provenance checks need neither current consent nor secrets."""
        try:
            snapshot=value['snapshot']
            if kind=='authorization':
                if value['operation_id']:
                    operation=self.read(self.row(con,project,value['operation_id'],'operation'),'operation')
                    if operation['snapshot']['source_ref']!=value['authorization_id'] or operation['snapshot']['source_snapshot_sha256']!=value['snapshot_sha256']:raise ValueError()
                return
            if snapshot['operation']=='authorization_code':
                source=self.read(self.row(con,project,snapshot['source_ref'],'authorization'),'authorization')
                expected={**source['snapshot'],'schema_version':'native-google-oauth-operation-snapshot-v1','operation':'authorization_code','source_ref':source['authorization_id'],'source_snapshot_sha256':source['snapshot_sha256']}
                if source['operation_id']!=value['operation_id'] or source['status']!='consumed' or snapshot!=expected:raise ValueError()
            else:
                source=self.read(self.row(con,project,snapshot['request']['source_operation_id'],'operation'),'operation')
                if source['operation_id']==value['operation_id'] or source['status']!='succeeded' or source['result_sha256']!=snapshot['source_result_sha256'] or source['result_sha256']!=snapshot['request']['expected_result_sha256'] or source['result']['grant_receipt']!=snapshot['previous_grant_receipt'] or source['result']['grant_receipt']['reference']!=snapshot['source_ref'] or source['snapshot']['slot']!=snapshot['slot']:raise ValueError()
            if value['cost_operation_id']:
                cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(value['cost_operation_id'],)).fetchone()
                if (cost is None or cost['id']!=digest({'project':project,'job':None,'provider':'official-google-oauth','operation':'token:'+value['operation_id']})
                    or cost['project_id']!=project or cost['job_id'] is not None or cost['provider']!='official-google-oauth' or cost['operation']!='token:'+value['operation_id']
                    or cost['model'] is not None or cost['paid']!=0 or cost['external_call']!=int(not snapshot['mock']) or cost['estimated_cost'] is not None or cost['actual_cost'] is not None
                    or cost['request_sha256']!=digest({'operation':snapshot['operation'],'snapshot_sha256':value['snapshot_sha256']})):raise ValueError()
                if value['result'] is not None and (cost['status']!='response_received' or json.loads(cost['receipt'])['provider_response_sha256']!=value['result']['response_sha256']):raise ValueError()
            elif value['result'] is not None:raise ValueError()
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_SOURCE_EVIDENCE_CHANGED') from None
    def page(self,project,*,kind='operation',limit=25,cursor=None):
        if kind not in ('operation','authorization') or type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400)
        after=None;column='operation_id' if kind=='operation' else 'authorization_id';table=TABLES[1] if kind=='operation' else TABLES[0]
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or not 1<=len(cursor)<=2048 or not re.fullmatch(r'[A-Za-z0-9_-]+',cursor):raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if type(after) is not list or len(after)!=5 or after[:3]!=[self.workspace,project,kind] or not re.fullmatch(r'ngo'+('p' if kind=='operation' else 'a')+r'_[a-f0-9]{32}',after[4]):raise ValueError()
                at(after[3])
            except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400) from None
        with self.store.transaction() as con:
            self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND '+column+'<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM '+table+' WHERE '+where+' ORDER BY created_at DESC,'+column+' DESC LIMIT ?',(*params,limit+1)).fetchall();items=[]
            for row in rows[:limit]:
                value=self.read(row,kind);self.links(con,project,value,kind);items.append(value)
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,kind,rows[limit-1]['created_at'],rows[limit-1][column]]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-google-oauth-page-v1','workspace_id':self.workspace,'project_id':project,'kind':kind,'items':items,'truncated':len(rows)>limit,'next_cursor':next_cursor,'token_returned':False,'automatic_refresh':False,'publishing_enabled':False}
    def private_authorization(self,snapshot,slot):
        flow=self.vault.authorization(snapshot['authorization_receipt'])
        if flow.configuration_sha256!=slot.client.configuration_sha256 or flow.redirect_uri!=snapshot['request']['redirect_uri'] or flow.created_at!=at(snapshot['approved_at']) or flow.expires_at!=at(snapshot['deadline']):raise WorkflowError('NATIVE_GOOGLE_OAUTH_AUTHORIZATION_BINDING_CHANGED')
        return flow
    def private_request(self,snapshot,slot,client,request,previous):
        current=self.private_client(slot)
        if current!=client or request.operation!=snapshot['operation'] or not at(snapshot['approved_at'])<=utc(request.issued_at)<at(snapshot['deadline']):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_REQUEST_CHANGED')
        fields=request.check(current)
        if request.operation=='authorization_code':
            flow=self.private_authorization(snapshot,slot)
            if fields['code_verifier']!=flow.verifier or fields['redirect_uri']!=flow.redirect_uri or previous is not None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_REQUEST_CHANGED')
        else:
            original=self.vault.grant(snapshot['previous_grant_receipt'])
            if original!=previous or fields['refresh_token']!=original.refresh_token:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_REQUEST_CHANGED')
    def snapshot(self,project,payload,authority,slot,document,**extra):
        stamp=utc(self.clock());deadline=stamp+timedelta(seconds=payload.valid_for_seconds)
        if deadline>at(authority['expires_at']):raise WorkflowError('NATIVE_GOOGLE_OAUTH_OWNER_WINDOW_REQUIRED',403)
        return {'workspace_id':self.workspace,'project_id':project,'request':payload.model_dump(mode='json',exclude={'request_key'}),'authority':authority,
            'slot':slot.model_dump(mode='json'),'document_sha256':digest(document),'mock':self.client.mock,'approved_at':stamp.isoformat(),'deadline':deadline.isoformat(),
            'token_returned':False,'publishing_enabled':False,'production_consent_renewed':False,'account_verified':False,'automatic_refresh':False,**extra}
    def fence(self,con,project,snapshot):
        self.identity(authority=snapshot['authority']);cls=Start if snapshot.get('operation')!='refresh_token' else Refresh
        payload=cls.model_validate({**snapshot['request'],'request_key':'internal-google-oauth-key'});slot=self.slot(payload);current=self.source(con,project,payload)
        if slot.model_dump(mode='json')!=snapshot['slot'] or digest(current['document'])!=snapshot['document_sha256'] or not at(snapshot['approved_at'])<=utc(self.clock())<at(snapshot['deadline']):raise WorkflowError('NATIVE_GOOGLE_OAUTH_CONSENT_CHANGED')
        if not self.configured():raise WorkflowError('NATIVE_GOOGLE_OAUTH_DISABLED')
        return slot
    def start(self,project,payload,*,principal):
        payload=typed(payload,Start);authority=self.identity(principal);key=digest(payload.request_key);request=digest(payload.model_dump(mode='json',exclude={'request_key'}))
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_google_oauth_authorizations WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_sha256']!=request:raise WorkflowError('NATIVE_GOOGLE_OAUTH_IDEMPOTENCY_CONFLICT')
                return self.read(prior,'authorization'),True
            slot=self.slot(payload);current=self.source(con,project,payload);snapshot=self.snapshot(project,payload,authority,slot,current['document'],schema_version='native-google-oauth-authorization-snapshot-v1',authorization_receipt=None)
            status='not_configured';identity='ngoa_'+uuid.uuid4().hex
            if self.configured():
                flow=authorization(self.private_client(slot),payload.redirect_uri,now=at(snapshot['approved_at']),valid_for_seconds=payload.valid_for_seconds)
                snapshot['authorization_receipt']=self.vault.save_authorization(flow,slot.client);self.fence(con,project,snapshot);status='awaiting_callback'
            self.identity(authority=authority);stamp=utc(self.clock()).isoformat()
            con.execute('INSERT INTO native_google_oauth_authorizations VALUES(?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,request,digest(snapshot),json.dumps(snapshot),status,None,stamp,stamp))
            self.event(con,project,identity,'oauth.authorization.prepared',authority['token_id'],status=status)
            return self.read(self.row(con,project,identity,'authorization'),'authorization'),False
    def authorization_url(self,project,identity,*,principal,expected_snapshot_sha256):
        self.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity,'authorization'),'authorization')
            if value['snapshot_sha256']!=expected_snapshot_sha256 or value['status']!='awaiting_callback':raise WorkflowError('NATIVE_GOOGLE_OAUTH_AUTHORIZATION_NOT_PENDING')
            slot=self.fence(con,project,value['snapshot']);flow=self.private_authorization(value['snapshot'],slot);self.private_client(slot)
            url=flow.url(utc(self.clock()));self.fence(con,project,value['snapshot']);return url
    def cancel(self,project,identity,payload,*,principal):
        payload=typed(payload,Cancel);authority=self.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity,'authorization'),'authorization')
            if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_GOOGLE_OAUTH_REVIEW_BINDING_CHANGED')
            if value['status'] not in {'awaiting_callback','not_configured','cancelled'}:raise WorkflowError('NATIVE_GOOGLE_OAUTH_ALREADY_CONSUMED')
            # Not-configured history has no private intent and is already inert.
            if value['status']=='awaiting_callback':
                con.execute("UPDATE native_google_oauth_authorizations SET status='cancelled',updated_at=? WHERE authorization_id=?",(utc(self.clock()).isoformat(),identity))
                self.event(con,project,identity,'oauth.authorization.cancelled',authority['token_id'])
            self.identity(authority=authority);return self.read(self.row(con,project,identity,'authorization'),'authorization')
    def claim(self,con,project,key,snapshot):
        self.fence(con,project,snapshot);identity='ngop_'+uuid.uuid4().hex;stamp=utc(self.clock()).isoformat()
        if con.execute('SELECT 1 FROM native_google_oauth_operations WHERE workspace_id=? AND source_ref=?',(self.workspace,snapshot['source_ref'])).fetchone():raise WorkflowError('NATIVE_GOOGLE_OAUTH_SOURCE_ALREADY_CONSUMED')
        con.execute('INSERT INTO native_google_oauth_operations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,digest(snapshot['request']),digest(snapshot),json.dumps(snapshot),snapshot['source_ref'],'claimed',None,None,None,None,stamp,stamp))
        self.event(con,project,identity,'oauth.operation.claimed',snapshot['authority']['token_id'],operation=snapshot['operation']);self.fence(con,project,snapshot);return identity
    async def exchange(self,project,identity,callback_query,*,principal,expected_snapshot_sha256):
        self.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity,'authorization'),'authorization');snapshot=value['snapshot']
            if value['snapshot_sha256']!=expected_snapshot_sha256 or value['status']!='awaiting_callback':raise WorkflowError('NATIVE_GOOGLE_OAUTH_AUTHORIZATION_NOT_PENDING')
            slot=self.fence(con,project,snapshot);client=self.private_client(slot);flow=self.private_authorization(snapshot,slot)
            try:request=exchange_request(flow,callback_query,now=utc(self.clock()))
            except GoogleOAuthError as error:
                if error.code!='GOOGLE_OAUTH_CONSENT_DENIED':raise WorkflowError(error.code,400) from None
                request=None
            operation={**snapshot,'schema_version':'native-google-oauth-operation-snapshot-v1','operation':'authorization_code','source_ref':identity,'source_snapshot_sha256':value['snapshot_sha256']}
            op=self.claim(con,project,digest(identity),operation)
            con.execute("UPDATE native_google_oauth_authorizations SET status='consumed',operation_id=?,updated_at=? WHERE authorization_id=?",(op,utc(self.clock()).isoformat(),identity))
            if request is None:
                con.execute("UPDATE native_google_oauth_operations SET status='failed',failure_code='GOOGLE_OAUTH_CONSENT_DENIED' WHERE operation_id=?",(op,))
                self.event(con,project,op,'oauth.operation.failed',snapshot['authority']['token_id'],failure_code='GOOGLE_OAUTH_CONSENT_DENIED')
        if request is None:return self.get(project,op)
        return await self.execute(project,op,slot,client,request)
    async def refresh(self,project,payload,*,principal):
        payload=typed(payload,Refresh);authority=self.identity(principal);key=digest(payload.request_key);fingerprint=digest(payload.model_dump(mode='json',exclude={'request_key'}))
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_google_oauth_operations WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_GOOGLE_OAUTH_IDEMPOTENCY_CONFLICT')
                return self.read(prior,'operation')
            slot=self.slot(payload);current=self.source(con,project,payload);source=self.read(self.row(con,project,payload.source_operation_id,'operation'),'operation')
            if source['status']!='succeeded' or source['result_sha256']!=payload.expected_result_sha256 or source['snapshot']['slot']!=slot.model_dump(mode='json'):raise WorkflowError('NATIVE_GOOGLE_OAUTH_GRANT_SOURCE_CHANGED')
            previous_receipt=source['result']['grant_receipt']
            snapshot=self.snapshot(project,payload,authority,slot,current['document'],schema_version='native-google-oauth-operation-snapshot-v1',operation='refresh_token',
                source_ref=previous_receipt['reference'],source_result_sha256=source['result_sha256'],previous_grant_receipt=previous_receipt)
            self.fence(con,project,snapshot);client=self.private_client(slot);previous=self.vault.grant(previous_receipt)
            if previous.mock is not self.client.mock:raise WorkflowError('NATIVE_GOOGLE_OAUTH_GRANT_SOURCE_CHANGED')
            try:request=refresh_request(client,previous,now=utc(self.clock()))
            except GoogleOAuthError as error:raise WorkflowError(error.code,400) from None
            op=self.claim(con,project,key,snapshot)
        return await self.execute(project,op,slot,client,request,previous=previous,previous_receipt=previous_receipt)
    async def execute(self,project,identity,slot,client,request,*,previous=None,previous_receipt=None):
        cost=None;observed=False;wire_started=False;response=None
        try:
            value=self.get(project,identity);snapshot=value['snapshot']
            cost=self.costs.begin(project_id=project,provider='official-google-oauth',model=None,operation='token:'+identity,
                request_sha256=digest({'operation':request.operation,'snapshot_sha256':value['snapshot_sha256']}),estimated_cost=None,external_call=not snapshot['mock'],paid=False)
            with self.store.transaction() as con:
                row=self.row(con,project,identity,'operation')
                if row['status']!='claimed':raise WorkflowError('NATIVE_GOOGLE_OAUTH_CLAIM_CHANGED')
                self.fence(con,project,snapshot);self.private_request(snapshot,slot,client,request,previous)
                con.execute('UPDATE native_google_oauth_operations SET cost_operation_id=? WHERE operation_id=?',(cost,identity))
            with self.store.transaction() as con:
                row=self.row(con,project,identity,'operation')
                if row['status']!='claimed' or row['cost_operation_id']!=cost:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CLAIM_CHANGED')
                self.fence(con,project,snapshot);self.private_request(snapshot,slot,client,request,previous)
            wire_started=True
            response=await self.client.send(client,request,now=utc(self.clock()));observed=True
            response_sha=hashlib.sha256(response.body).hexdigest()
            self.costs.settle(cost,status='response_received',response_sha256=response_sha)
            if response.mock is not snapshot['mock']:raise WorkflowError('NATIVE_GOOGLE_OAUTH_MOCK_BINDING_CHANGED')
            grant=parse_tokens(client,request,response,now=utc(self.clock()),previous=previous)
            with self.store.transaction() as con:
                row=self.row(con,project,identity,'operation');self.read(row,'operation')
                if row['status']!='claimed' or row['cost_operation_id']!=cost:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CLAIM_CHANGED')
                self.fence(con,project,snapshot);self.private_request(snapshot,slot,client,request,previous)
                if request.operation=='authorization_code':self.private_authorization(snapshot,slot)
                else:
                    source=self.read(self.row(con,project,snapshot['request']['source_operation_id'],'operation'),'operation')
                    if source['result_sha256']!=snapshot['source_result_sha256'] or source['result']['grant_receipt']!=previous_receipt:raise WorkflowError('NATIVE_GOOGLE_OAUTH_GRANT_SOURCE_CHANGED')
                    self.vault.grant(previous_receipt)
                receipt=self.vault.save_grant(grant,slot.client,previous=previous_receipt)
                self.fence(con,project,snapshot);self.private_client(slot)
                result={'schema_version':'native-google-oauth-result-v1','grant_receipt':receipt,'grant_proof':grant.public(client),
                    'response_sha256':response_sha,'http_status':response.status,'cost_operation_id':cost,'credential_selected':False}
                con.execute("UPDATE native_google_oauth_operations SET status='succeeded',result_sha256=?,result_json=?,updated_at=? WHERE operation_id=?",(digest(result),json.dumps(result),utc(self.clock()).isoformat(),identity))
                self.event(con,project,identity,'oauth.operation.succeeded',snapshot['authority']['token_id'],result_sha256=digest(result),cost_operation_id=cost)
            return self.get(project,identity)
        except BaseException as error:
            code=error.code if isinstance(error,(GoogleOAuthError,WorkflowError)) else 'NATIVE_GOOGLE_OAUTH_OPERATION_INTERRUPTED'
            uncertain=bool(wire_started and not observed or isinstance(error,GoogleOAuthError) and error.uncertain)
            status='outcome_unknown' if uncertain else 'review_required' if observed and isinstance(error,WorkflowError) else 'failed'
            if cost is not None and self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown' if uncertain else 'rejected',error_code=code)
            with self.store.transaction() as con:
                row=self.row(con,project,identity,'operation')
                if row['status']=='claimed':
                    con.execute('UPDATE native_google_oauth_operations SET status=?,failure_code=?,cost_operation_id=?,updated_at=? WHERE operation_id=?',(status,code,cost,utc(self.clock()).isoformat(),identity))
                    self.event(con,project,identity,'oauth.operation.'+status,'system:local',failure_code=code,cost_operation_id=cost)
            if isinstance(error,(KeyboardInterrupt,SystemExit,asyncio.CancelledError)):raise
            return self.get(project,identity)
    def recover(self):
        """Startup never decrypts or resends a possibly consumed code/refresh token."""
        costs=[];self.check()
        with self.store.transaction() as con:
            for row in con.execute("SELECT * FROM native_google_oauth_operations WHERE workspace_id=? AND status='claimed'",(self.workspace,)).fetchall():
                self.read(row,'operation');con.execute("UPDATE native_google_oauth_operations SET status='outcome_unknown',failure_code='NATIVE_GOOGLE_OAUTH_RESTART_NO_REPLAY',updated_at=? WHERE operation_id=?",(utc(self.clock()).isoformat(),row['operation_id']))
                self.event(con,row['project_id'],row['operation_id'],'oauth.operation.outcome_unknown','system:recovery',failure_code='NATIVE_GOOGLE_OAUTH_RESTART_NO_REPLAY')
                # The ledger commits separately before its public reference is
                # attached. Recover that narrow crash window deterministically.
                cost=row['cost_operation_id'] or digest({'project':row['project_id'],'job':None,'provider':'official-google-oauth','operation':'token:'+row['operation_id']})
                if con.execute('SELECT 1 FROM native_cost_operations WHERE id=?',(cost,)).fetchone():
                    con.execute('UPDATE native_google_oauth_operations SET cost_operation_id=? WHERE operation_id=?',(cost,row['operation_id']));costs.append(cost)
            for row in con.execute("SELECT * FROM native_google_oauth_authorizations WHERE workspace_id=? AND status='awaiting_callback'",(self.workspace,)).fetchall():
                value=self.read(row,'authorization')
                if utc(self.clock())>=at(value['snapshot']['deadline']):
                    con.execute("UPDATE native_google_oauth_authorizations SET status='expired',updated_at=? WHERE authorization_id=?",(utc(self.clock()).isoformat(),row['authorization_id']))
                    self.event(con,row['project_id'],row['authorization_id'],'oauth.authorization.expired','system:recovery')
        for cost in costs:
            if self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown',error_code='NATIVE_GOOGLE_OAUTH_RESTART_NO_REPLAY')
        return {'schema_version':'native-google-oauth-recovery-v1','provider_calls':0,'automatic_retries':0,'token_returned':False}
