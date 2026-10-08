"""Finite separately authorized official publication steps; default off.

This kernel owns only Native SQLite scheduling. It reuses the exact publication
worker and never creates credentials, refreshes grants or clears upload guards.
"""
from dataclasses import dataclass
from datetime import datetime,timedelta
import json,re,uuid
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.models import StrictModel
from .contracts import WorkflowError,digest
from .official_publication_models import Step
from .official_publications import utc
from .official_publication_worker import NativeOfficialPublicationWorker,code

TABLES=('native_official_publish_queue_plans','native_official_publish_queue_steps','native_official_publish_queue_events')
STATUSES={'queued','running','completed','cancelled','needs_attention','exhausted','expired'}

class QueueCreate(Step):
    acknowledged_background_steps:Literal[True]
    max_steps:StrictInt=Field(ge=1,le=100)
    interval_seconds:StrictInt=Field(ge=30,le=3600)
    start_at:datetime
    deadline:datetime
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_background_steps',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Explicit separate background consent required')
        return value
    @field_validator('start_at','deadline',mode='before')
    @classmethod
    def instant(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Explicit aware time required')
        return value
    @model_validator(mode='after')
    def bounds(self):
        if self.start_at.tzinfo is None or self.deadline.tzinfo is None or not self.start_at<self.deadline:raise ValueError('Aware finite scheduling window required')
        return self

class QueueCancel(StrictModel):
    expected_policy_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')

class DispatchResult(StrictModel):
    phase:Literal['prepared','init_intent','init_unconfirmed','uploading','chunk_intent','reconcile_intent','reconciliation_required','uploaded','review_required']
    version:StrictInt=Field(ge=1)
    total_bytes:StrictInt=Field(ge=1)
    acknowledged_bytes:StrictInt=Field(ge=0)
    @model_validator(mode='after')
    def bounds(self):
        if self.acknowledged_bytes>self.total_bytes:raise ValueError('Invalid acknowledgement')
        return self

class Outcome(StrictModel):
    schema_version:Literal['native-official-publish-queue-outcome-v1']='native-official-publish-queue-outcome-v1'
    mock:StrictBool
    dispatch:DispatchResult|None=None
    published:StrictBool=False
    mock_publication_complete:StrictBool=False
    receipt_sha256:str|None=Field(default=None,pattern=r'^[a-f0-9]{64}$')
    failure_code:str|None=Field(default=None,pattern=r'^[A-Z0-9_]{1,120}$')
    @model_validator(mode='after')
    def receipt(self):
        if self.published and self.mock or self.mock_publication_complete and not self.mock or self.published and self.mock_publication_complete:raise ValueError('Qualified receipt required')
        if bool(self.receipt_sha256)!=(self.published or self.mock_publication_complete):raise ValueError('Receipt binding required')
        if self.receipt_sha256 and (self.dispatch is None or self.dispatch.phase!='uploaded' or self.dispatch.acknowledged_bytes!=self.dispatch.total_bytes):raise ValueError('Completed upload required')
        return self

@dataclass(frozen=True)
class QueueTicket:
    plan_id:str
    publication_id:str
    workspace_id:str
    project_id:str
    policy_sha256:str
    version:int
    ordinal:int
    dispatch_version:int
    claim_id:str
    def __post_init__(self):
        patterns={'plan_id':r'nopq_[a-f0-9]{32}','publication_id':r'nopu_[a-f0-9]{32}','workspace_id':r'[A-Za-z0-9_-]{1,80}',
            'project_id':r'[a-f0-9]{32}','policy_sha256':r'[a-f0-9]{64}','claim_id':r'[a-f0-9]{32}'}
        if any(not isinstance(getattr(self,k),str) or not re.fullmatch(v,getattr(self,k)) for k,v in patterns.items()) or any(type(v) is not int or v<1 for v in (self.version,self.ordinal,self.dispatch_version)):
            raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_TICKET_INVALID',400)

class NativeOfficialPublicationQueue:
    def __init__(self,worker,*,enabled=False):
        if type(worker) is not NativeOfficialPublicationWorker or type(enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_CONFIGURATION_INVALID',400)
        self.worker,self.enabled=worker,enabled;self.frozen_worker,self.frozen_enabled=worker,enabled
        self.journal=worker.journal;self.store,self.workspace=self.journal.store,self.journal.workspace
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_publish_queue_plans (
                plan_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,policy_sha256 TEXT NOT NULL,policy_json TEXT NOT NULL,
                status TEXT NOT NULL,version INTEGER NOT NULL,step_count INTEGER NOT NULL,next_due_at TEXT NOT NULL,
                claim_id TEXT,failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE UNIQUE INDEX IF NOT EXISTS native_official_publish_one_active_plan ON native_official_publish_queue_plans(workspace_id,publication_id) WHERE status IN ('queued','running');
                CREATE TABLE IF NOT EXISTS native_official_publish_queue_steps (
                claim_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                ordinal INTEGER NOT NULL,plan_version INTEGER NOT NULL,dispatch_version INTEGER NOT NULL,operation TEXT NOT NULL,status TEXT NOT NULL,
                result_json TEXT,result_sha256 TEXT,created_at TEXT NOT NULL,finished_at TEXT,UNIQUE(plan_id,ordinal));
                CREATE TABLE IF NOT EXISTS native_official_publish_queue_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,plan_id TEXT NOT NULL,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,
                project_id TEXT NOT NULL,action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_publish_queue_plans WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_SCOPE_CHANGED')
    def clock(self):return utc(self.journal.clock())
    def configured(self):
        if self.worker is not self.frozen_worker or self.enabled is not self.frozen_enabled or self.worker.journal is not self.journal or self.journal.store is not self.store or self.workspace!=self.journal.workspace:
            raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_CONFIGURATION_CHANGED')
        self.journal.accounts.check_workspace();return self.enabled
    def row(self,con,project,identity):
        self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone());self.journal.accounts.check_workspace()
        row=con.execute('SELECT * FROM native_official_publish_queue_plans WHERE plan_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_FOUND',404)
        return row
    def read(self,con,row):
        try:
            value=dict(row);policy=json.loads(value.pop('policy_json'));request=QueueCreate.model_validate({**policy['request'],'request_key':'internal-queue-review-key'})
            publication=self.journal.read(self.journal.row(con,row['project_id'],row['publication_id']))
            if (digest(policy)!=row['policy_sha256'] or policy['schema_version']!='native-official-publish-queue-policy-v1'
                or any(policy[k]!=row[k] for k in ('plan_id','publication_id','workspace_id','project_id')) or row['workspace_id']!=self.workspace
                or not re.fullmatch(r'nopq_[a-f0-9]{32}',row['plan_id']) or type(policy['mock']) is not bool or policy['mock'] is not publication['mock']
                or request.expected_snapshot_sha256!=publication['snapshot_sha256'] or policy['approval_id'] is None
                or not re.fullmatch(r'nopa_[a-f0-9]{32}',policy['approval_id']) or policy['automatic_consent_renewal'] is not False
                or policy['remote_deletion_enabled'] is not False or digest({'publication_id':row['publication_id'],'request':policy['request']})!=row['request_sha256']
                or row['status'] not in STATUSES or type(row['version']) is not int or row['version']<1 or type(row['step_count']) is not int or not 0<=row['step_count']<=request.max_steps
                or row['status']=='running' and row['claim_id'] is None or row['claim_id'] is not None and not re.fullmatch(r'[a-f0-9]{32}',row['claim_id'])
                or row['failure_code'] is not None and not re.fullmatch(r'[A-Z0-9_]{1,120}',row['failure_code'])):raise ValueError()
            if utc(datetime.fromisoformat(row['next_due_at']))<utc(request.start_at):raise ValueError()
            value.pop('key_sha256')
            return {**value,'schema_version':'native-official-publish-queue-plan-v1','policy':policy,'mock':policy['mock'],
                'token_returned':False,'session_uri_returned':False,'real_provider_tested':False}
        except (ValueError,TypeError,KeyError):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_EVIDENCE_CHANGED') from None
    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_official_publish_queue_events(plan_id,publication_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?,?)',
            (row['plan_id'],row['publication_id'],self.workspace,row['project_id'],action,actor,json.dumps(evidence),self.clock().isoformat()))
    def get(self,project,identity):
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(con,row)
            return {**value,'steps':self.steps(con,row,value)}
    def steps(self,con,row,value):
        steps=[]
        for step in con.execute('SELECT * FROM native_official_publish_queue_steps WHERE plan_id=? ORDER BY ordinal',(row['plan_id'],)):
            if (any(step[k]!=row[k] for k in ('plan_id','publication_id','workspace_id','project_id')) or step['status'] not in ('dispatch_intent','completed','failed','outcome_unknown')
                or step['operation'] not in ('step','poll') or type(step['ordinal']) is not int or step['ordinal']!=len(steps)+1 or not step['ordinal']<=row['step_count']
                or not re.fullmatch(r'[a-f0-9]{32}',step['claim_id']) or type(step['plan_version']) is not int or not 2<=step['plan_version']<=row['version']
                or type(step['dispatch_version']) is not int or step['dispatch_version']<1):
                raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEP_CHANGED')
            result=None
            if step['result_json'] is not None:
                try:
                    result=json.loads(step['result_json']);parsed=Outcome.model_validate(result)
                    if digest(result)!=step['result_sha256'] or parsed.mock is not value['mock']:raise ValueError()
                except (ValueError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEP_CHANGED') from None
            if (step['status']=='dispatch_intent')!=(result is None) or (step['finished_at'] is None)!=(result is None):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEP_CHANGED')
            steps.append({**dict(step),'result':result});steps[-1].pop('result_json')
        if len(steps)!=row['step_count']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEP_CHANGED')
        return steps
    def create(self,project,publication,payload,*,principal):
        authority=self.journal.identity(principal)
        if type(payload) is not QueueCreate:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_FIELDS_INVALID',400)
        try:payload=QueueCreate.model_validate(payload.model_dump(mode='python',warnings=False))
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_FIELDS_INVALID',400) from None
        request=payload.model_dump(mode='json',exclude={'request_key'});fingerprint=digest({'publication_id':publication,'request':request});key=digest(payload.request_key)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_publish_queue_plans WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior is not None:
                if prior['publication_id']!=publication or prior['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_IDEMPOTENCY_CONFLICT')
                value=self.read(con,prior);return {**value,'idempotent_replay':True}
            if not self.configured():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_ENABLED')
            self.worker.check();value,_,_,dispatch=self.journal.admission(project,publication,con=con);grant=self.journal.valid_grant(con,self.journal.row(con,project,publication));instant=self.clock()
            if payload.expected_snapshot_sha256!=value['snapshot_sha256'] or payload.expected_dispatch_version!=dispatch['version'] or dispatch['intent_id'] is not None or dispatch['phase'] not in ('prepared','uploading','reconciliation_required','uploaded'):
                raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_REVIEW_BINDING_CHANGED')
            if not instant<=utc(payload.start_at)<utc(payload.deadline)<=utc(datetime.fromisoformat(grant['expires_at'])) or utc(payload.deadline)>utc(datetime.fromisoformat(authority['expires_at'])):
                raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_WINDOW_OUTSIDE_CONSENT')
            if con.execute("SELECT 1 FROM native_official_publish_queue_plans WHERE workspace_id=? AND publication_id=? AND status IN ('queued','running')",(self.workspace,publication)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_ALREADY_ACTIVE')
            identity='nopq_'+uuid.uuid4().hex;stamp=instant.isoformat()
            policy={'schema_version':'native-official-publish-queue-policy-v1','plan_id':identity,'publication_id':publication,'workspace_id':self.workspace,'project_id':project,
                'approval_id':value['approval_id'],'authority':authority,'mock':value['mock'],'request':request,'automatic_consent_renewal':False,'remote_deletion_enabled':False}
            con.execute('INSERT INTO native_official_publish_queue_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,publication,self.workspace,project,key,fingerprint,digest(policy),json.dumps(policy),'queued',1,0,utc(payload.start_at).isoformat(),None,None,stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'official.publication.queue.approved',authority['token_id'],max_steps=payload.max_steps,deadline=utc(payload.deadline).isoformat(),external_action=False)
            return {**self.read(con,row),'idempotent_replay':False}
    def cancel(self,project,identity,payload,*,principal):
        authority=self.journal.identity(principal)
        try:
            if type(payload) is not QueueCancel:raise ValueError()
            payload=QueueCancel.model_validate(payload.model_dump(mode='python',warnings=False))
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_FIELDS_INVALID',400) from None
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(con,row)
            if payload.expected_policy_sha256!=row['policy_sha256']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_REVIEW_BINDING_CHANGED')
            if row['status'] not in ('completed','cancelled'):
                con.execute("UPDATE native_official_publish_queue_plans SET status='cancelled',version=version+1,updated_at=? WHERE plan_id=?",(self.clock().isoformat(),identity))
                self.event(con,row,'official.publication.queue.cancelled',authority['token_id'],external_action=False,publication_grant_revoked=False,remote_delete_requested=False)
            return self.read(con,self.row(con,project,identity))
    def admission(self,con,row):
        if not self.configured():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_ENABLED')
        value=self.read(con,row);policy=value['policy'];request=QueueCreate.model_validate({**policy['request'],'request_key':'internal-queue-review-key'})
        self.steps(con,row,value)
        authority=self.journal.identity(token_id=policy['authority']['token_id'],subject=policy['authority']['subject'])
        if authority!=policy['authority']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_OWNER_CHANGED')
        if self.clock()<utc(request.start_at):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_DUE')
        if self.clock()>=utc(request.deadline):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_DEADLINE_EXPIRED')
        publication,_,_,dispatch=self.journal.admission(row['project_id'],row['publication_id'],con=con)
        if publication['approval_id']!=policy['approval_id']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_GRANT_CHANGED')
        return value,request,publication,dispatch
    def claim(self):
        if not self.configured():return None
        with self.store.transaction() as con:
            row=con.execute("SELECT * FROM native_official_publish_queue_plans WHERE workspace_id=? AND status='queued' AND next_due_at<=? ORDER BY next_due_at,plan_id LIMIT 1",(self.workspace,self.clock().isoformat())).fetchone()
            if row is None:return None
            try:
                value,request,publication,dispatch=self.admission(con,row)
                if row['step_count']>=request.max_steps:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEPS_EXHAUSTED')
                if dispatch['intent_id'] is not None or dispatch['phase'] not in ('prepared','uploading','reconciliation_required','uploaded'):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_DISPATCH_REVIEW_REQUIRED')
                retry=self.journal.backoff_until(con,row['project_id'],row['publication_id'],publication)
                if retry is not None and utc(datetime.fromisoformat(retry))>self.clock():
                    con.execute('UPDATE native_official_publish_queue_plans SET next_due_at=?,updated_at=? WHERE plan_id=?',(retry,self.clock().isoformat(),row['plan_id']));return None
            except WorkflowError as error:
                status='expired' if error.code=='NATIVE_OFFICIAL_PUBLISH_QUEUE_DEADLINE_EXPIRED' else 'exhausted' if error.code=='NATIVE_OFFICIAL_PUBLISH_QUEUE_STEPS_EXHAUSTED' else 'needs_attention'
                con.execute('UPDATE native_official_publish_queue_plans SET status=?,failure_code=?,version=version+1,updated_at=? WHERE plan_id=?',(status,error.code,self.clock().isoformat(),row['plan_id']))
                self.event(con,row,'official.publication.queue.stopped','worker',failure_code=error.code,external_action=False);return self.read(con,self.row(con,row['project_id'],row['plan_id']))
            claim=uuid.uuid4().hex;version=row['version']+1;ordinal=row['step_count']+1;operation='poll' if dispatch['phase']=='uploaded' else 'step';stamp=self.clock().isoformat()
            con.execute('INSERT INTO native_official_publish_queue_steps VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(claim,row['plan_id'],row['publication_id'],self.workspace,row['project_id'],ordinal,version,dispatch['version'],operation,'dispatch_intent',None,None,stamp,None))
            con.execute("UPDATE native_official_publish_queue_plans SET status='running',version=?,step_count=?,claim_id=?,updated_at=? WHERE plan_id=?",(version,ordinal,claim,stamp,row['plan_id']))
            self.event(con,row,'official.publication.queue.step.claimed','worker',ordinal=ordinal,operation=operation,dispatch_version=dispatch['version'],external_action=False)
            return QueueTicket(row['plan_id'],row['publication_id'],self.workspace,row['project_id'],row['policy_sha256'],version,ordinal,dispatch['version'],claim),operation
    def fence(self,con,ticket):
        if type(ticket) is not QueueTicket:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_TICKET_INVALID',400)
        QueueTicket(**ticket.__dict__);row=self.row(con,ticket.project_id,ticket.plan_id);value=self.read(con,row)
        step=con.execute('SELECT * FROM native_official_publish_queue_steps WHERE claim_id=?',(ticket.claim_id,)).fetchone()
        if (ticket.workspace_id!=self.workspace or any(row[k]!=getattr(ticket,k) for k in ('plan_id','publication_id','workspace_id','project_id','policy_sha256'))
            or row['claim_id']!=ticket.claim_id or step is None or step['status']!='dispatch_intent'
            or any(step[k]!=getattr(ticket,k) for k in ('plan_id','publication_id','workspace_id','project_id','ordinal','dispatch_version')) or step['plan_version']!=ticket.version):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_TICKET_STALE')
        return row,value,step
    def guard(self,ticket):
        with self.store.transaction() as con:
            row,_,_=self.fence(con,ticket)
            if row['status']!='running' or row['version']!=ticket.version:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_CANCELLED_OR_CHANGED')
            self.admission(con,row)
    def finish(self,ticket,outcome):
        try:
            if type(outcome) is not Outcome:raise ValueError()
            outcome=Outcome.model_validate(outcome.model_dump(mode='python',warnings=False))
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_OUTCOME_INVALID',400) from None
        with self.store.transaction() as con:
            row,value,_=self.fence(con,ticket)
            if outcome.mock is not value['mock']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_OUTCOME_INVALID')
            request=QueueCreate.model_validate({**value['policy']['request'],'request_key':'internal-queue-review-key'});instant=self.clock();due=instant+timedelta(seconds=request.interval_seconds)
            status='needs_attention' if outcome.failure_code else 'completed' if outcome.receipt_sha256 else 'queued'
            if outcome.failure_code in ('NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF','NATIVE_OFFICIAL_PUBLISH_BACKOFF_ACTIVE'):
                publication=self.journal.read(self.journal.row(con,ticket.project_id,ticket.publication_id));retry=self.journal.backoff_until(con,ticket.project_id,ticket.publication_id,publication)
                if retry is not None and publication['status']=='queued':status='queued';due=max(due,utc(datetime.fromisoformat(retry)))
            if status=='queued' and row['step_count']>=request.max_steps:status='exhausted'
            if status=='queued' and due>=utc(request.deadline):status='expired'
            if row['status']=='cancelled':status='cancelled'
            result=outcome.model_dump(mode='json');stamp=instant.isoformat()
            con.execute('UPDATE native_official_publish_queue_steps SET status=?,result_json=?,result_sha256=?,finished_at=? WHERE claim_id=?',('failed' if outcome.failure_code else 'completed',json.dumps(result),digest(result),stamp,ticket.claim_id))
            con.execute('UPDATE native_official_publish_queue_plans SET status=?,version=version+1,claim_id=NULL,next_due_at=?,failure_code=?,updated_at=? WHERE plan_id=?',(status,due.isoformat(),outcome.failure_code,stamp,ticket.plan_id))
            self.event(con,row,'official.publication.queue.step.finished','worker',ordinal=ticket.ordinal,status=status,result_sha256=digest(result),external_action=False)
        return self.get(ticket.project_id,ticket.plan_id)
    def process(self):
        claim=self.claim()
        if claim is None or not isinstance(claim,tuple):return claim
        ticket,operation=claim;failure=None
        try:
            method=self.worker.poll_processing if operation=='poll' else self.worker.step
            method(ticket.project_id,ticket.publication_id,ticket.dispatch_version,guard=lambda:self.guard(ticket))
        except Exception as error:failure=code(error)
        try:
            state=self.journal.state(ticket.project_id,ticket.publication_id);dispatch=state['dispatch'];receipt=state['receipt']
            outcome=Outcome(mock=state['mock'],dispatch=None if dispatch is None else {k:dispatch[k] for k in ('phase','version','total_bytes','acknowledged_bytes')},
                published=state['published'],mock_publication_complete=state['mock_publication_complete'],receipt_sha256=digest(receipt) if receipt is not None else None,failure_code=failure)
        except WorkflowError as error:
            with self.store.transaction() as con:_,value,_=self.fence(con,ticket)
            outcome=Outcome(mock=value['mock'],failure_code=code(error))
        return self.finish(ticket,outcome)
    def recover(self):
        """Owned startup only, after publication-worker recovery; no provider calls."""
        recovered=0
        with self.store.transaction() as con:
            for row in con.execute('SELECT * FROM native_official_publish_queue_plans WHERE workspace_id=? AND claim_id IS NOT NULL',(self.workspace,)).fetchall():
                value=self.read(con,row);step=con.execute('SELECT * FROM native_official_publish_queue_steps WHERE claim_id=?',(row['claim_id'],)).fetchone()
                if step is None or step['status']!='dispatch_intent' or any(step[k]!=row[k] for k in ('plan_id','publication_id','workspace_id','project_id')):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_STEP_CHANGED')
                result=Outcome(mock=value['mock'],failure_code='NATIVE_OFFICIAL_PUBLISH_QUEUE_RESTART_REVIEW_REQUIRED').model_dump(mode='json');stamp=self.clock().isoformat()
                con.execute("UPDATE native_official_publish_queue_steps SET status='outcome_unknown',result_json=?,result_sha256=?,finished_at=? WHERE claim_id=?",(json.dumps(result),digest(result),stamp,row['claim_id']))
                con.execute('UPDATE native_official_publish_queue_plans SET status=?,version=version+1,claim_id=NULL,failure_code=?,updated_at=? WHERE plan_id=?',('cancelled' if row['status']=='cancelled' else 'needs_attention',result['failure_code'],stamp,row['plan_id']))
                self.event(con,row,'official.publication.queue.recovered','worker',automatic_retry=False,external_action=False);recovered+=1
        return {'recovered_steps':recovered,'external_calls':0,'automatic_upload_retry':False}
