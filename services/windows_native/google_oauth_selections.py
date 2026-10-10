"""Explicit grant -> verified YouTube channel -> runtime credential selection.

No token refresh, upload, startup decryption or implicit publishing approval.
"""
import json,re,uuid,sqlite3
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator
from app.models import StrictModel
from app.google_oauth_protocol import instant,GoogleOAuthError
from app.publishing_credentials import youtube_account_request,confirm_youtube_account,target_digest,PublishingCredentialError
from app.publishing_wire import OfficialHTTPClient,PublishingWireError
from app.analytics_official import response_digest
from .contracts import WorkflowError,digest,file_sha
from .costs import CostLedger
from .google_oauth_operations import NativeGoogleOAuthOperations,Slot

TABLE='native_google_oauth_selections'

class Select(StrictModel):
    revision:StrictInt=Field(ge=1)
    source_operation_id:str=Field(pattern=r'^ngop_[a-f0-9]{32}$')
    expected_result_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_account_access:Literal[True]
    acknowledged_credential_selection:Literal[True]
    acknowledged_protocol_mock:StrictBool=False
    valid_for_seconds:StrictInt=Field(default=600,ge=60,le=900)
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_account_access','acknowledged_credential_selection',mode='before')
    @classmethod
    def acknowledged(cls,value):
        if value is not True:raise ValueError('Separate explicit selection/account consent required')
        return value

class Revoke(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class NativeGoogleOAuthSelections:
    def __init__(self,oauth,*,enabled=False,client=None):
        if type(oauth) is not NativeGoogleOAuthOperations or type(enabled) is not bool:raise WorkflowError('NATIVE_GOOGLE_SELECTION_CONFIGURATION_INVALID',400)
        self.oauth=oauth;self.store=oauth.store;self.workspace=oauth.workspace;self.clock=oauth.clock
        self.enabled=enabled;self.client=client or OfficialHTTPClient('youtube',network_enabled=enabled)
        if type(self.client) is not OfficialHTTPClient or self.client.platform!='youtube':raise WorkflowError('NATIVE_GOOGLE_SELECTION_CONFIGURATION_INVALID',400)
        self.costs=CostLedger(self.store)
        self.frozen=(oauth,self.store,self.workspace,self.clock,self.store.root.absolute(),self.store.db.absolute(),enabled,self.client,self.client.transport,self.client.network_enabled,self.costs)
        self.check()
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_google_oauth_selections (
            selection_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
            slot_id TEXT NOT NULL,target_sha256 TEXT NOT NULL,status TEXT NOT NULL,cost_operation_id TEXT,
            result_sha256 TEXT,result_json TEXT,failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            UNIQUE(workspace_id,project_id,key_sha256));
            CREATE UNIQUE INDEX IF NOT EXISTS native_google_selection_active_target
            ON native_google_oauth_selections(workspace_id,target_sha256) WHERE status='active';''')
            if con.execute('SELECT 1 FROM '+TABLE+' WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_GOOGLE_SELECTION_WORKSPACE_CHANGED')
    def check(self):
        if ((self.oauth,self.store,self.workspace,self.clock,self.store.root.absolute(),self.store.db.absolute(),self.enabled,self.client,self.client.transport,self.client.network_enabled,self.costs)!=self.frozen
            or type(self.enabled) is not bool or self.costs.store is not self.store):raise WorkflowError('NATIVE_GOOGLE_SELECTION_CONFIGURATION_CHANGED')
        self.oauth.check()
    def configured(self):
        self.check();return self.enabled and self.oauth.configured() and (self.client.transport is not None or self.client.network_enabled is True)
    def states(self):
        return {'schema_version':'native-google-selection-runtime-v1','workspace_id':self.workspace,'enabled':self.configured(),'default_enabled':False,
            'slots':[s.model_dump(mode='json') for _,s in sorted(self.oauth.slots.items()) if s.client.purpose=='publishing'],
            'mock':self.client.transport is not None,'token_returned':False,'publishing_enabled':False,'automatic_refresh':False,
            'startup_decryption':False,'account_verified':False,'real_provider_tested':False}
    def row(self,con,project,identity):
        row=con.execute('SELECT * FROM '+TABLE+' WHERE selection_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_GOOGLE_SELECTION_NOT_FOUND',404)
        return row
    def read(self,row):
        try:
            value=dict(row);snapshot=json.loads(value.pop('snapshot_json'));value.pop('key_sha256')
            request=Select.model_validate({**snapshot['request'],'request_key':'internal-google-selection-key'});slot=Slot.model_validate(snapshot['slot'])
            if (set(snapshot)!={'schema_version','workspace_id','project_id','request','authority','slot','source_operation_snapshot_sha256','source_result_sha256','grant_receipt',
                'grant_proof','document_sha256','approved_at','deadline','mock','token_returned','publishing_enabled','automatic_refresh'}
                or snapshot['schema_version']!='native-google-selection-snapshot-v1' or digest(snapshot)!=value['snapshot_sha256']
                or digest(snapshot['request'])!=value['request_sha256'] or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace
                or snapshot['project_id']!=value['project_id'] or slot.slot_id!=value['slot_id'] or target_digest(slot.target)!=value['target_sha256']
                or slot.client.purpose!='publishing' or request.expected_result_sha256!=snapshot['source_result_sha256']
                or snapshot['mock'] is not request.acknowledged_protocol_mock
                or set(snapshot['authority'])!={'token_id','subject','identity_revision_sha256','expires_at'}
                or any(type(snapshot['authority'][k]) is not str or not snapshot['authority'][k] for k in ('token_id','subject'))
                or not re.fullmatch('[a-f0-9]{64}',snapshot['authority']['identity_revision_sha256'])
                or any(snapshot[k] is not False for k in ('token_returned','publishing_enabled','automatic_refresh'))
                or (instant_from(snapshot['deadline'])-instant_from(snapshot['approved_at'])).total_seconds()!=request.valid_for_seconds
                or instant_from(snapshot['deadline'])>instant_from(snapshot['authority']['expires_at'])
                or value['status'] not in {'pending_verification','not_configured','claimed','active','revoked','failed','outcome_unknown','review_required'}):raise ValueError()
            result=json.loads(value.pop('result_json')) if value['result_json'] is not None else None
            if (result is not None)!=bool(value['result_sha256']) or result is not None and digest(result)!=value['result_sha256']:raise ValueError()
            if value['status']=='active' and result is None:raise ValueError()
            if result is not None and (set(result)!={'schema_version','channel_id','target_binding_sha256','grant_receipt_sha256','response_sha256','account_verified','mock',
                'credential_selected','token_returned','publishing_enabled','real_provider_tested','cost_operation_id'}
                or result['schema_version']!='native-google-selection-result-v1' or result['channel_id']!=slot.target.target_account_id
                or result['target_binding_sha256']!=value['target_sha256'] or result['grant_receipt_sha256']!=digest(snapshot['grant_receipt'])
                or result['mock'] is not snapshot['mock'] or result['account_verified'] is not True or result['credential_selected'] is not True
                or any(result[k] is not False for k in ('token_returned','publishing_enabled','real_provider_tested'))
                or result['cost_operation_id']!=value['cost_operation_id'] or not re.fullmatch('[a-f0-9]{64}',result['response_sha256'])):raise ValueError()
            return {**value,'snapshot':snapshot,'result':result,'token_returned':False,'publishing_enabled':False,'automatic_refresh':False}
        except Exception:raise WorkflowError('NATIVE_GOOGLE_SELECTION_EVIDENCE_CHANGED') from None
    def get(self,project,identity):
        self.check()
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity));self.source(con,value);return value
    def source(self,con,value,*,current=False):
        snapshot=value['snapshot'];request=Select.model_validate({**snapshot['request'],'request_key':'internal-google-selection-key'})
        row=self.oauth.row(con,value['project_id'],request.source_operation_id,'operation');source=self.oauth.read(row,'operation')
        self.oauth.links(con,value['project_id'],source,'operation')
        slot=Slot.model_validate(snapshot['slot']);result=source['result']
        if (source['status']!='succeeded' or source['snapshot_sha256']!=snapshot['source_operation_snapshot_sha256'] or source['result_sha256']!=snapshot['source_result_sha256']
            or source['snapshot']['slot']!=snapshot['slot'] or result['grant_receipt']!=snapshot['grant_receipt'] or result['grant_proof']!=snapshot['grant_proof']):raise WorkflowError('NATIVE_GOOGLE_SELECTION_SOURCE_CHANGED')
        self.cost_links(con,value)
        if current:
            self.check();live=self.oauth.slots.get(slot.slot_id)
            if live is None or live.model_dump(mode='json')!=snapshot['slot']:raise WorkflowError('NATIVE_GOOGLE_SELECTION_SLOT_CHANGED')
            self.oauth.identity(authority=snapshot['authority'])
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(value['project_id'],)).fetchone())
            state=con.execute('SELECT archived FROM project_dashboard WHERE project_id=?',(value['project_id'],)).fetchone()
            if state is not None and state['archived']:raise WorkflowError('NATIVE_GOOGLE_SELECTION_PROJECT_ARCHIVED')
            proof=snapshot['grant_proof']
            if instant_from(proof['expires_at'])<=instant(self.clock())+timedelta(seconds=90):raise WorkflowError('NATIVE_GOOGLE_SELECTION_REFRESH_REQUIRED')
            rotated=con.execute("SELECT 1 FROM native_google_oauth_operations WHERE workspace_id=? AND source_ref=? AND status NOT IN ('failed','not_configured') LIMIT 1",
                (self.workspace,snapshot['grant_receipt']['reference'])).fetchone()
            if rotated:raise WorkflowError('NATIVE_GOOGLE_SELECTION_GRANT_SUPERSEDED')
            # Availability validates immutable encrypted files without decrypting.
            for receipt in (slot.client,snapshot['grant_receipt']):
                receipt=self.oauth.vault.receipt(receipt)
                path=self.oauth.vault.path(receipt.reference)
                if not path.is_file() or path.stat().st_size!=receipt.bytes or file_sha(path)!=receipt.cipher_sha256:raise WorkflowError('NATIVE_GOOGLE_SELECTION_PRIVATE_FILE_CHANGED')
        return slot
    def cost_links(self,con,value):
        try:
            identity=value['selection_id'];cost_id=value['cost_operation_id']
            if cost_id is None:
                if value['result'] is not None:raise ValueError()
                return
            operation='oauth_selection_account.'+identity
            cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(cost_id,)).fetchone()
            if (cost is None or cost_id!=digest({'project':value['project_id'],'job':None,'provider':'official-youtube','operation':operation})
                or cost['project_id']!=value['project_id'] or cost['job_id'] is not None or cost['provider']!='official-youtube' or cost['operation']!=operation
                or cost['model'] is not None or cost['paid']!=0 or cost['external_call']!=int(not value['snapshot']['mock'])
                or cost['estimated_cost'] is not None or cost['actual_cost'] is not None
                or cost['request_sha256']!=digest({'selection_id':identity,'snapshot_sha256':value['snapshot_sha256']})):raise ValueError()
            if value['result'] is not None and (cost['status']!='response_received' or json.loads(cost['receipt'])['provider_response_sha256']!=value['result']['response_sha256']):raise ValueError()
        except Exception:raise WorkflowError('NATIVE_GOOGLE_SELECTION_COST_EVIDENCE_CHANGED') from None
    def fence(self,con,value,*,verify=False):
        slot=self.source(con,value,current=True)
        if not self.configured() or value['snapshot']['mock'] is not (self.client.transport is not None):raise WorkflowError('NATIVE_GOOGLE_SELECTION_DISABLED')
        if verify:
            snapshot=value['snapshot'];request=Select.model_validate({**snapshot['request'],'request_key':'internal-google-selection-key'})
            project=self.store.editable(con,value['project_id'],request.revision)
            if digest(project['document'])!=snapshot['document_sha256'] or not instant_from(snapshot['approved_at'])<=instant(self.clock())<instant_from(snapshot['deadline']):raise WorkflowError('NATIVE_GOOGLE_SELECTION_CONSENT_CHANGED')
        return slot
    def create(self,project,payload,*,principal):
        payload=Select.model_validate(payload.model_dump(mode='json') if type(payload) is Select else payload)
        authority=self.oauth.identity(principal);key=digest(payload.request_key);request=payload.model_dump(mode='json',exclude={'request_key'})
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM '+TABLE+' WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_sha256']!=digest(request):raise WorkflowError('NATIVE_GOOGLE_SELECTION_IDEMPOTENCY_CONFLICT')
                value=self.read(prior);self.source(con,value);return value,True
            current=self.store.editable(con,project,payload.revision)
            source=self.oauth.read(self.oauth.row(con,project,payload.source_operation_id,'operation'),'operation');self.oauth.links(con,project,source,'operation')
            if source['status']!='succeeded' or source['result_sha256']!=payload.expected_result_sha256:raise WorkflowError('NATIVE_GOOGLE_SELECTION_SOURCE_CHANGED')
            slot=Slot.model_validate(source['snapshot']['slot']);result=source['result']
            if slot.client.purpose!='publishing' or result['grant_proof']['mock'] is not payload.acknowledged_protocol_mock:raise WorkflowError('NATIVE_GOOGLE_SELECTION_PURPOSE_OR_MOCK_CHANGED')
            stamp=instant(self.clock());deadline=stamp+timedelta(seconds=payload.valid_for_seconds)
            if deadline>instant_from(authority['expires_at']):raise WorkflowError('NATIVE_GOOGLE_SELECTION_OWNER_WINDOW_REQUIRED',403)
            snapshot={'schema_version':'native-google-selection-snapshot-v1','workspace_id':self.workspace,'project_id':project,'request':request,'authority':authority,
                'slot':slot.model_dump(mode='json'),'source_operation_snapshot_sha256':source['snapshot_sha256'],'source_result_sha256':source['result_sha256'],
                'grant_receipt':result['grant_receipt'],'grant_proof':result['grant_proof'],'document_sha256':digest(current['document']),
                'approved_at':stamp.isoformat(),'deadline':deadline.isoformat(),'mock':payload.acknowledged_protocol_mock,'token_returned':False,'publishing_enabled':False,'automatic_refresh':False}
            identity='ngosel_'+uuid.uuid4().hex;status='pending_verification' if self.configured() else 'not_configured'
            con.execute('INSERT INTO '+TABLE+' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,key,digest(request),digest(snapshot),json.dumps(snapshot),slot.slot_id,target_digest(slot.target),status,None,None,None,None,stamp.isoformat(),stamp.isoformat()))
            self.source(con,self.read(self.row(con,project,identity)),current=True)
            # FULL transaction commit precedes any private decrypt or provider request.
            self.oauth.event(con,project,identity,'oauth.credential.selection.created',authority['token_id'],snapshot_sha256=digest(snapshot),status=status)
        return self.get(project,identity),False
    async def verify(self,project,identity,*,principal,expected_snapshot_sha256):
        self.oauth.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity))
            if value['snapshot_sha256']!=expected_snapshot_sha256:raise WorkflowError('NATIVE_GOOGLE_SELECTION_SNAPSHOT_CHANGED')
            if value['status']=='active':self.fence(con,value);return value
            if value['status']!='pending_verification':raise WorkflowError('NATIVE_GOOGLE_SELECTION_NOT_PENDING')
            self.fence(con,value,verify=True)
            con.execute("UPDATE "+TABLE+" SET status='claimed',updated_at=? WHERE selection_id=?",(instant(self.clock()).isoformat(),identity))
        cost=None;sent=False;response_seen=False
        try:
            slot=Slot.model_validate(value['snapshot']['slot']);client=self.oauth.private_client(slot)
            grant=self.oauth.vault.grant(value['snapshot']['grant_receipt']);credential=grant.credential(client,now=self.clock())
            if grant.mock is not value['snapshot']['mock']:raise WorkflowError('NATIVE_GOOGLE_SELECTION_PURPOSE_OR_MOCK_CHANGED')
            cost=self.costs.begin(project_id=project,provider='official-youtube',model=None,operation='oauth_selection_account.'+identity,
                request_sha256=digest({'selection_id':identity,'snapshot_sha256':value['snapshot_sha256']}),external_call=not grant.mock,paid=False,estimated_cost=None)
            with self.store.transaction() as con:
                current=self.read(self.row(con,project,identity));self.fence(con,current,verify=True)
                if current['status']!='claimed':raise WorkflowError('NATIVE_GOOGLE_SELECTION_CLAIM_CHANGED')
                con.execute('UPDATE '+TABLE+' SET cost_operation_id=? WHERE selection_id=?',(cost,identity))
            # Re-read after the last private key load; authority can change there.
            with self.store.transaction() as con:self.fence(con,self.read(self.row(con,project,identity)),verify=True)
            request=youtube_account_request(credential);sent=True;response=await self.client.request(request);response_seen=True
            sha=response_digest(response);self.costs.settle(cost,status='response_received',response_sha256=sha)
            confirm_youtube_account(response,slot.target)
            with self.store.transaction() as con:
                current=self.read(self.row(con,project,identity));self.fence(con,current,verify=True)
                if current['status']!='claimed' or current['cost_operation_id']!=cost:raise WorkflowError('NATIVE_GOOGLE_SELECTION_CLAIM_CHANGED')
                fresh=self.oauth.vault.grant(value['snapshot']['grant_receipt']);self.fence(con,current,verify=True)
                if fresh!=grant:raise WorkflowError('NATIVE_GOOGLE_SELECTION_GRANT_CHANGED')
                result={'schema_version':'native-google-selection-result-v1','channel_id':slot.target.target_account_id,'target_binding_sha256':target_digest(slot.target),
                    'grant_receipt_sha256':digest(value['snapshot']['grant_receipt']),'response_sha256':sha,'account_verified':True,'mock':grant.mock,
                    'credential_selected':True,'token_returned':False,'publishing_enabled':False,'real_provider_tested':False,'cost_operation_id':cost}
                con.execute("UPDATE "+TABLE+" SET status='revoked',updated_at=? WHERE workspace_id=? AND target_sha256=? AND status='active'",
                    (instant(self.clock()).isoformat(),self.workspace,target_digest(slot.target)))
                con.execute("UPDATE "+TABLE+" SET status='active',result_sha256=?,result_json=?,updated_at=? WHERE selection_id=?",
                    (digest(result),json.dumps(result),instant(self.clock()).isoformat(),identity))
                self.oauth.event(con,project,identity,'oauth.credential.selection.verified',value['snapshot']['authority']['token_id'],result_sha256=digest(result),cost_operation_id=cost,read_only=True)
            return self.get(project,identity)
        except BaseException as error:
            code=error.code if isinstance(error,(WorkflowError,GoogleOAuthError,PublishingWireError,PublishingCredentialError)) else 'NATIVE_GOOGLE_SELECTION_INTERRUPTED'
            status='outcome_unknown' if sent and not response_seen else 'review_required' if response_seen and isinstance(error,WorkflowError) else 'failed'
            if cost and self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown' if status=='outcome_unknown' else 'rejected',error_code=code)
            with self.store.transaction() as con:
                con.execute("UPDATE "+TABLE+" SET status=?,failure_code=?,updated_at=? WHERE selection_id=? AND status='claimed'",(status,code,instant(self.clock()).isoformat(),identity))
                self.oauth.event(con,project,identity,'oauth.credential.selection.'+status,'system:local',failure_code=code,cost_operation_id=cost)
            if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
            return self.get(project,identity)
    def active(self,slot_id,target):
        self.check()
        # Factories are read inside the publication journal's writer transaction.
        # A separate read-only WAL snapshot avoids a nested BEGIN IMMEDIATE.
        with self.reading() as con:
            row=con.execute("SELECT * FROM "+TABLE+" WHERE workspace_id=? AND slot_id=? AND target_sha256=? AND status='active'",(self.workspace,slot_id,target_digest(target))).fetchone()
            if row is None:raise WorkflowError('NATIVE_GOOGLE_SELECTION_REQUIRED')
            value=self.read(row);slot=self.fence(con,value)
            if slot.target!=target:raise WorkflowError('NATIVE_GOOGLE_SELECTION_TARGET_CHANGED')
            return value,slot
    @contextmanager
    def reading(self):
        con=sqlite3.connect(self.store.db.absolute().as_uri()+'?mode=ro',uri=True,timeout=5)
        con.row_factory=sqlite3.Row
        try:
            con.execute('PRAGMA query_only=ON');con.execute('BEGIN')
            yield con
        finally:con.close()
    def credential(self,slot_id,target):
        value,slot=self.active(slot_id,target);client=self.oauth.private_client(slot);grant=self.oauth.vault.grant(value['snapshot']['grant_receipt'])
        credential=grant.credential(client,now=self.clock());current,_=self.active(slot_id,target)
        if current!=value or grant.mock is not value['snapshot']['mock']:raise WorkflowError('NATIVE_GOOGLE_SELECTION_GRANT_CHANGED')
        return credential
    def revoke(self,project,identity,payload,*,principal):
        self.oauth.identity(principal);payload=Revoke.model_validate(payload.model_dump(mode='json') if type(payload) is Revoke else payload)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity))
            if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_GOOGLE_SELECTION_SNAPSHOT_CHANGED')
            if value['status']=='claimed':raise WorkflowError('NATIVE_GOOGLE_SELECTION_OPERATION_BUSY')
            con.execute("UPDATE "+TABLE+" SET status='revoked',updated_at=? WHERE selection_id=?",(instant(self.clock()).isoformat(),identity))
            self.oauth.event(con,project,identity,'oauth.credential.selection.revoked',principal.token_id,external_action=False)
        return self.get(project,identity)
    def recover(self):
        self.check();costs=[]
        with self.store.transaction() as con:
            rows=con.execute("SELECT * FROM "+TABLE+" WHERE workspace_id=? AND status='claimed'",(self.workspace,)).fetchall()
            for row in rows:
                self.read(row)
                cost=row['cost_operation_id'] or digest({'project':row['project_id'],'job':None,'provider':'official-youtube','operation':'oauth_selection_account.'+row['selection_id']})
                if con.execute('SELECT 1 FROM native_cost_operations WHERE id=?',(cost,)).fetchone():costs.append(cost)
                else:cost=None
                con.execute("UPDATE "+TABLE+" SET status='outcome_unknown',cost_operation_id=?,failure_code='NATIVE_GOOGLE_SELECTION_RECOVERY_NO_REPLAY',updated_at=? WHERE selection_id=?",(cost,instant(self.clock()).isoformat(),row['selection_id']))
                self.oauth.event(con,row['project_id'],row['selection_id'],'oauth.credential.selection.outcome_unknown','system:recovery',failure_code='NATIVE_GOOGLE_SELECTION_RECOVERY_NO_REPLAY')
        for cost in costs:
            if self.costs.pending(cost):self.costs.settle(cost,status='outcome_unknown',error_code='NATIVE_GOOGLE_SELECTION_RECOVERY_NO_REPLAY')
        return len(rows)

    def page(self,project,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_GOOGLE_SELECTION_PAGE_INVALID',400)
        if cursor is not None and (type(cursor) is not str or not re.fullmatch('ngosel_[a-f0-9]{32}',cursor)):raise WorkflowError('NATIVE_GOOGLE_SELECTION_PAGE_INVALID',400)
        self.check()
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            clause='';params=[self.workspace,project]
            if cursor:
                anchor=self.row(con,project,cursor);clause=' AND (created_at<? OR (created_at=? AND selection_id<?))'
                params.extend([anchor['created_at'],anchor['created_at'],cursor])
            rows=con.execute('SELECT * FROM '+TABLE+' WHERE workspace_id=? AND project_id=?'+clause+' ORDER BY created_at DESC,selection_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            items=[]
            for row in rows[:limit]:
                value=self.read(row);self.source(con,value);items.append(value)
            return {'schema_version':'native-google-selection-page-v1','workspace_id':self.workspace,'project_id':project,'items':items,
                'next_cursor':items[-1]['selection_id'] if len(rows)>limit else None,'truncated':len(rows)>limit,
                'token_returned':False,'publishing_enabled':False,'automatic_refresh':False}

def instant_from(value):
    from datetime import datetime
    return instant(datetime.fromisoformat(value))

class PublishingSelectionResolver:
    """One-time startup attachment; availability never decrypts private grants."""
    def __init__(self,binding,root,workspace):
        self.binding=binding.model_copy(deep=True);self.root=Path(root).absolute();self.workspace=workspace
        self.frozen=(digest(binding.model_dump(mode='json')),self.root,workspace);self.service=None;self.frozen_service=None
    def check(self):
        if (digest(self.binding.model_dump(mode='json')),self.root,self.workspace)!=self.frozen or self.service is not self.frozen_service:raise WorkflowError('NATIVE_GOOGLE_SELECTION_RESOLVER_CHANGED')
        if self.service is not None:
            if type(self.service) is not NativeGoogleOAuthSelections or self.service.store.root.absolute()!=self.root or self.service.workspace!=self.workspace:raise WorkflowError('NATIVE_GOOGLE_SELECTION_RESOLVER_CHANGED')
            self.service.check()
    def attach(self,service):
        self.check()
        if self.service is not None:raise WorkflowError('NATIVE_GOOGLE_SELECTION_RESOLVER_ALREADY_ATTACHED')
        if type(service) is not NativeGoogleOAuthSelections or service.store.root.absolute()!=self.root or service.workspace!=self.workspace:raise WorkflowError('NATIVE_GOOGLE_SELECTION_RESOLVER_CHANGED')
        service.check()
        slot=service.oauth.slots.get(self.binding.google_oauth_slot_id)
        if slot is None or slot.client.purpose!='publishing' or slot.target!=self.binding.profile.target or slot.client.credential_alias!=self.binding.credential_alias:raise WorkflowError('NATIVE_GOOGLE_SELECTION_SLOT_CHANGED')
        self.service=self.frozen_service=service;self.check()
    def available(self,*,mock):
        self.check()
        if self.service is None:return False
        try:
            value,_=self.service.active(self.binding.google_oauth_slot_id,self.binding.profile.target)
            return value['snapshot']['mock'] is mock
        except WorkflowError:return False
    def __call__(self,target):
        self.check()
        if self.service is None or target!=self.binding.profile.target:raise WorkflowError('NATIVE_GOOGLE_SELECTION_REQUIRED')
        return self.service.credential(self.binding.google_oauth_slot_id,target)
