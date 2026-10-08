"""Finite separately approved official reads over the existing collector; default off."""
import base64,json,re,uuid
from contextlib import nullcontext
from datetime import datetime,timedelta
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,ValidationError,field_validator,model_validator
from .contracts import WorkflowError,digest
from .official_analytics import NativeOfficialAnalytics
from .official_analytics_models import Collect,Cancel
from .official_account_registry import AccountFactory
from .official_publications import utc
from app.models import StrictModel
from app.bridge_auth import canonical_json_bytes
from app.publishing_credentials import target_digest

TABLES=('native_official_analytics_refresh_plans','native_official_analytics_refresh_occurrences','native_official_analytics_refresh_events')
STATUSES={'active','not_configured','completed','cancelled','needs_attention','expired'}
PENDING={'queued','running','retry_scheduled'}

def same(a,b):return canonical_json_bytes(a)==canonical_json_bytes(b)
def at(value):return utc(datetime.fromisoformat(value))

class RefreshCreate(Collect):
    schema_version:Literal['native-official-analytics-refresh-request-v1']='native-official-analytics-refresh-request-v1'
    acknowledged_background_reads:Literal[True]
    max_runs:StrictInt=Field(ge=1,le=100)
    interval_seconds:StrictInt=Field(ge=60,le=86400)
    start_at:datetime
    deadline:datetime
    @field_validator('acknowledged_background_reads',mode='before')
    @classmethod
    def background(cls,value):
        if value is not True:raise ValueError('Separate explicit background read consent required')
        return value
    @field_validator('start_at','deadline',mode='before')
    @classmethod
    def instant(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Explicit aware time required')
        return value
    @model_validator(mode='after')
    def window(self):
        if self.start_at.tzinfo is None or self.deadline.tzinfo is None or not self.start_at+timedelta(seconds=60)<=self.deadline<=self.start_at+timedelta(days=7):
            raise ValueError('Aware bounded read window required')
        self.start_at,self.deadline=utc(self.start_at),utc(self.deadline)
        return self

class RefreshCancel(StrictModel):
    expected_policy_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_version:StrictInt=Field(ge=1)
    cancel_pending_read:StrictBool

def typed(value,kind):
    try:
        if type(value) is not kind:raise ValueError()
        return kind.model_validate(value.model_dump(mode='python',warnings=False))
    except (ValueError,TypeError,ValidationError):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_FIELDS_INVALID',400) from None

def collector_payload(payload,key,*,seconds=None):
    value=payload.model_dump(mode='json')
    value={name:value[name] for name in Collect.model_fields}
    value.update(schema_version='native-official-analytics-request-v1',request_key=key)
    if seconds is not None:value['valid_for_seconds']=seconds
    return Collect.model_validate(value)

class NativeOfficialAnalyticsRefresh:
    def __init__(self,analytics,*,enabled=False):
        if type(analytics) is not NativeOfficialAnalytics or type(enabled) is not bool or enabled and not analytics.enabled:
            raise WorkflowError('NATIVE_OFFICIAL_REFRESH_CONFIGURATION_INVALID',400)
        self.analytics,self.store,self.workspace,self.clock=analytics,analytics.store,analytics.workspace,analytics.clock
        self.enabled=self.frozen_enabled=enabled
        self.frozen=(analytics,self.store,self.workspace,self.clock,self.store.root.absolute())
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_analytics_refresh_plans (
            plan_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,publication_id TEXT NOT NULL,
            key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,policy_sha256 TEXT NOT NULL,policy_json TEXT NOT NULL,
            status TEXT NOT NULL,version INTEGER NOT NULL,run_count INTEGER NOT NULL,next_due_at TEXT NOT NULL,pending_sync_id TEXT,
            failure_code TEXT,actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
            UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_official_analytics_refresh_occurrences (
            occurrence_id TEXT PRIMARY KEY,plan_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
            publication_id TEXT NOT NULL,ordinal INTEGER NOT NULL,policy_sha256 TEXT NOT NULL,sync_id TEXT UNIQUE NOT NULL,
            consent_sha256 TEXT NOT NULL,occurrence_sha256 TEXT NOT NULL,occurrence_json TEXT NOT NULL,UNIQUE(plan_id,ordinal));
            CREATE TABLE IF NOT EXISTS native_official_analytics_refresh_events (
            sequence INTEGER PRIMARY KEY AUTOINCREMENT,plan_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
            action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_analytics_refresh_plans WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():
                raise WorkflowError('NATIVE_OFFICIAL_REFRESH_WORKSPACE_CHANGED')
    def check(self):
        if (self.enabled is not self.frozen_enabled or type(self.enabled) is not bool
            or (self.analytics,self.store,self.workspace,self.clock,self.store.root.absolute())!=self.frozen
            or self.analytics.store is not self.store or self.analytics.workspace!=self.workspace or self.analytics.clock is not self.clock):
            raise WorkflowError('NATIVE_OFFICIAL_REFRESH_CONFIGURATION_CHANGED')
        self.analytics.check()
    def configured(self):self.check();return self.enabled and self.analytics.enabled
    def states(self):
        return {'schema_version':'native-official-analytics-refresh-runtime-v1','workspace_id':self.workspace,'enabled':self.configured(),
            'default_enabled':False,'separate_owner_background_read_consent_required':True,'fixed_report_query':True,
            'automatic_consent_renewal':False,'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
    def row(self,con,project,identity):
        self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_official_analytics_refresh_plans WHERE plan_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_NOT_FOUND',404)
        return row
    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_official_analytics_refresh_events(plan_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['plan_id'],self.workspace,row['project_id'],action,actor,json.dumps(evidence),utc(self.clock()).isoformat()))
    @staticmethod
    def credential_proof(credential):
        return {'expires_at':utc(credential.expires_at).isoformat(),'scopes_sha256':digest(sorted(credential.scopes)),
            'target_binding_sha256':target_digest(credential.target)}
    def read(self,con,row):
        try:
            value=dict(row);policy=json.loads(value.pop('policy_json'))
            request=RefreshCreate.model_validate({**policy['request'],'request_key':'internal-finite-official-refresh-key'})
            if (set(policy)!={'schema_version','plan_id','workspace_id','project_id','publication_id','request','authority','mock','source','target_binding_sha256','credential_proof','approved_at','automatic_consent_renewal','publishing_enabled','fixed_report_query'}
                or not same(policy['request'],request.model_dump(mode='json',exclude={'request_key'}))
                or digest(policy)!=row['policy_sha256'] or policy['schema_version']!='native-official-analytics-refresh-policy-v1'
                or any(policy[k]!=row[k] for k in ('plan_id','workspace_id','project_id','publication_id')) or row['workspace_id']!=self.workspace
                or not re.fullmatch(r'noap_[a-f0-9]{32}',row['plan_id']) or request.publication_id!=row['publication_id']
                or digest(policy['request'])!=row['request_fingerprint'] or type(policy['mock']) is not bool or request.acknowledged_protocol_mock is not policy['mock']
                or policy['automatic_consent_renewal'] is not False or policy['publishing_enabled'] is not False or policy['fixed_report_query'] is not True
                or row['status'] not in STATUSES or type(row['version']) is not int or row['version']<1
                or type(row['run_count']) is not int or not 0<=row['run_count']<=request.max_runs
                or row['pending_sync_id'] is not None and not re.fullmatch(r'noas_[a-f0-9]{32}',row['pending_sync_id'])
                or row['failure_code'] is not None and not re.fullmatch(r'[A-Z0-9_]{1,120}',row['failure_code'])
                or at(policy['approved_at'])>request.start_at or request.deadline>at(policy['authority']['expires_at'])
                or at(row['next_due_at'])<request.start_at or row['created_at']!=policy['approved_at']
                or row['status']=='completed' and (row['run_count']!=request.max_runs or row['pending_sync_id'] is not None)
                or row['status']=='active' and row['run_count']==request.max_runs and row['pending_sync_id'] is None):raise ValueError()
            publication,source=self.analytics.source(row['project_id'],collector_payload(request,'internal-plan-source-proof-key'),policy['approved_at'],con=con)
            if (not same(source,policy['source']) or policy['mock'] is not publication['mock']
                or policy['target_binding_sha256']!=publication['snapshot']['target_binding_sha256']):raise ValueError()
            proof=policy['credential_proof']
            if proof is not None:
                if (set(proof)!={'expires_at','scopes_sha256','target_binding_sha256'} or request.deadline>at(proof['expires_at'])
                    or proof['target_binding_sha256']!=policy['target_binding_sha256'] or not re.fullmatch(r'[a-f0-9]{64}',proof['scopes_sha256'])):raise ValueError()
            elif row['status'] not in {'not_configured','cancelled'} or row['run_count']!=0:raise ValueError()
            value.pop('key_sha256');value.update(schema_version='native-official-analytics-refresh-plan-v1',policy=policy,mock=policy['mock'],
                token_returned=False,publishing_enabled=False,automatic_consent_renewal=False,real_provider_tested=False)
            return value
        except (KeyError,TypeError,ValueError,ValidationError):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_EVIDENCE_CHANGED') from None
    def occurrences(self,con,row,value):
        items=[];request=RefreshCreate.model_validate({**value['policy']['request'],'request_key':'internal-occurrence-proof-key'})
        for record in con.execute('SELECT * FROM native_official_analytics_refresh_occurrences WHERE plan_id=? ORDER BY ordinal',(row['plan_id'],)):
            try:
                item=json.loads(record['occurrence_json']);ordinal=len(items)+1
                if (set(item)!={'schema_version','occurrence_id','plan_id','workspace_id','project_id','publication_id','ordinal','policy_sha256','sync_id','consent_sha256','read_request_sha256','due_at','admitted_at'}
                    or digest(item)!=record['occurrence_sha256'] or item['schema_version']!='native-official-analytics-refresh-occurrence-v1'
                    or any(record[k]!=row[k] or item[k]!=row[k] for k in ('plan_id','workspace_id','project_id','publication_id','policy_sha256'))
                    or item['occurrence_id']!=record['occurrence_id'] or not re.fullmatch(r'noao_[a-f0-9]{32}',item['occurrence_id'])
                    or type(item['ordinal']) is not int or item['ordinal']!=record['ordinal'] or item['ordinal']!=ordinal or ordinal>row['run_count']
                    or item['sync_id']!=record['sync_id'] or item['consent_sha256']!=record['consent_sha256']
                    or not request.start_at<=at(item['due_at'])<=at(item['admitted_at'])<request.deadline):raise ValueError()
                expected_due=request.start_at if not items else at(items[-1]['admitted_at'])+timedelta(seconds=request.interval_seconds)
                if at(item['due_at'])!=expected_due:raise ValueError()
                sync=self.analytics.get(row['project_id'],item['sync_id'],con=con)
                seconds=min(request.valid_for_seconds,int((request.deadline-at(item['admitted_at'])).total_seconds()))
                read_request=collector_payload(request,self.key(row,ordinal),seconds=seconds).model_dump(mode='json',exclude={'request_key'})
                if (sync['publication_id']!=row['publication_id'] or sync['snapshot_sha256']!=item['consent_sha256']
                    or item['read_request_sha256']!=digest(read_request) or not same(sync['snapshot']['request'],read_request)
                    or not same(sync['snapshot']['authority'],value['policy']['authority']) or sync['mock'] is not value['mock']
                    or sync['snapshot']['consented_at']!=item['admitted_at'] or at(sync['snapshot']['deadline'])>request.deadline):raise ValueError()
                _,source=self.analytics.source(row['project_id'],Collect.model_validate({**read_request,'request_key':'internal-occurrence-source-key'}),item['admitted_at'],con=con)
                if not same(source,sync['snapshot']['source']):raise ValueError()
                items.append({**item,'occurrence_sha256':record['occurrence_sha256'],'sync':sync})
            except (ValueError,KeyError,TypeError,ValidationError):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_OCCURRENCE_CHANGED') from None
        if (len(items)!=row['run_count'] or row['pending_sync_id'] is not None and (not items or row['pending_sync_id']!=items[-1]['sync_id'])
            or items and at(row['next_due_at'])!=at(items[-1]['admitted_at'])+timedelta(seconds=request.interval_seconds)
            or not items and at(row['next_due_at'])!=request.start_at):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_OCCURRENCE_CHANGED')
        return items
    @staticmethod
    def key(row,ordinal):return 'refresh_'+digest([row['workspace_id'],row['project_id'],row['plan_id'],row['policy_sha256'],ordinal])
    def get(self,project,identity,*,con=None):
        with (self.store.transaction() if con is None else nullcontext(con)) as source:
            row=self.row(source,project,identity);value=self.read(source,row)
            return {**value,'occurrences':self.occurrences(source,row,value)}
    def create(self,project,payload,*,principal):
        self.check();payload=typed(payload,RefreshCreate);authority=self.analytics.identity(principal)
        request=payload.model_dump(mode='json',exclude={'request_key'});key,fp=digest(payload.request_key),digest(request)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_analytics_refresh_plans WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fp:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_IDEMPOTENCY_CONFLICT')
                return self.get(project,prior['plan_id'],con=con),True
            instant=utc(self.clock())
            if not instant<=payload.start_at<payload.deadline<=at(authority['expires_at']):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_WINDOW_OUTSIDE_CONSENT')
            publication,source=self.analytics.source(project,collector_payload(payload,'internal-refresh-source-key'),instant.isoformat(),con=con)
            factory=self.analytics.accounts.factories.get(payload.account_ref)
            if (type(factory) is not AccountFactory or factory.sha256!=payload.expected_configuration_sha256
                or factory.public()['target']!=publication['snapshot']['target'] or factory.client.mock is not publication['mock']
                or payload.acknowledged_protocol_mock is not publication['mock']):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_ACCOUNT_BINDING_CHANGED')
            configured=self.configured() and factory.public()['status']=='CONFIGURED'
            proof=self.credential_proof(factory.credential(payload.query,now=instant)) if configured else None
            if proof is not None and payload.deadline>at(proof['expires_at']):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_WINDOW_OUTSIDE_CREDENTIAL')
            if con.execute("SELECT 1 FROM native_official_analytics_refresh_plans WHERE workspace_id=? AND publication_id=? AND status='active'",(self.workspace,payload.publication_id)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_REFRESH_ALREADY_ACTIVE')
            self.analytics.identity(authority=authority)
            identity,stamp='noap_'+uuid.uuid4().hex,instant.isoformat()
            policy={'schema_version':'native-official-analytics-refresh-policy-v1','plan_id':identity,'workspace_id':self.workspace,'project_id':project,'publication_id':payload.publication_id,
                'request':request,'authority':authority,'mock':publication['mock'],'source':source,'target_binding_sha256':publication['snapshot']['target_binding_sha256'],
                'credential_proof':proof,'approved_at':stamp,'automatic_consent_renewal':False,'publishing_enabled':False,'fixed_report_query':True}
            con.execute('INSERT INTO native_official_analytics_refresh_plans VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,payload.publication_id,key,fp,digest(policy),json.dumps(policy),'active' if configured else 'not_configured',1,0,utc(payload.start_at).isoformat(),None,None,authority['token_id'],stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'analytics.official.refresh.approved',authority['token_id'],configured=configured,external_call=False)
            self.analytics.identity(authority=authority)
            return self.get(project,identity,con=con),False
    def admission(self,con,row,value):
        if not self.configured():raise WorkflowError('NATIVE_OFFICIAL_REFRESH_NOT_ENABLED')
        policy=value['policy'];request=RefreshCreate.model_validate({**policy['request'],'request_key':'internal-refresh-admission-key'})
        self.analytics.identity(authority=policy['authority']);instant=utc(self.clock())
        if instant>=request.deadline:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_DEADLINE_EXPIRED')
        if instant<request.start_at:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_NOT_DUE')
        if row['run_count']>=request.max_runs:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_RUN_LIMIT')
        seconds=min(request.valid_for_seconds,int((request.deadline-instant).total_seconds()))
        if seconds<60:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_DEADLINE_NEAR')
        factory=self.analytics.accounts.factories.get(request.account_ref)
        if (type(factory) is not AccountFactory or factory.sha256!=request.expected_configuration_sha256 or factory.public()['status']!='CONFIGURED'
            or factory.client.mock is not value['mock'] or factory.public()['target_binding_sha256']!=policy['target_binding_sha256']):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_ACCOUNT_BINDING_CHANGED')
        if not same(self.credential_proof(factory.credential(request.query,now=instant)),policy['credential_proof']):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_CREDENTIAL_CHANGED')
        self.analytics.identity(authority=policy['authority'])
        return request,seconds
    def stop(self,con,row,status,code,*,clear=False):
        con.execute('UPDATE native_official_analytics_refresh_plans SET status=?,failure_code=?,version=version+1,pending_sync_id=?,updated_at=? WHERE plan_id=?',
            (status,code,None if clear else row['pending_sync_id'],utc(self.clock()).isoformat(),row['plan_id']))
        self.event(con,row,'analytics.official.refresh.stopped','worker',status=status,failure_code=code,external_call=False,automatic_retry=False)
    def tick(self):
        if not self.configured():return None
        with self.store.transaction() as con:
            rows=con.execute("SELECT * FROM native_official_analytics_refresh_plans WHERE workspace_id=? AND status='active' ORDER BY next_due_at,plan_id LIMIT 100",(self.workspace,)).fetchall()
            for row in rows:
                value=self.read(con,row);occurrences=self.occurrences(con,row,value)
                if row['pending_sync_id']:
                    sync=occurrences[-1]['sync']
                    if sync['status'] in PENDING:continue
                    if sync['status']!='succeeded':
                        self.stop(con,row,'needs_attention','NATIVE_OFFICIAL_REFRESH_SOURCE_'+sync['status'].upper(),clear=True)
                        return self.get(row['project_id'],row['plan_id'],con=con)
                    finished=row['run_count']==value['policy']['request']['max_runs']
                    con.execute('UPDATE native_official_analytics_refresh_plans SET pending_sync_id=NULL,status=?,version=version+1,updated_at=? WHERE plan_id=?',
                        ('completed' if finished else 'active',utc(self.clock()).isoformat(),row['plan_id']))
                    self.event(con,row,'analytics.official.refresh.observed','worker',sync_id=sync['sync_id'],external_call=False)
                    row=self.row(con,row['project_id'],row['plan_id']);value=self.read(con,row)
                    if finished:return self.get(row['project_id'],row['plan_id'],con=con)
                if utc(self.clock())<at(row['next_due_at']):continue
                if con.execute("SELECT 1 FROM native_official_analytics_syncs WHERE workspace_id=? AND publication_id=? AND status IN ('queued','running','retry_scheduled')",(self.workspace,row['publication_id'])).fetchone():continue
                try:request,seconds=self.admission(con,row,value)
                except WorkflowError as error:
                    self.stop(con,row,'expired' if error.code in {'NATIVE_OFFICIAL_REFRESH_DEADLINE_EXPIRED','NATIVE_OFFICIAL_REFRESH_DEADLINE_NEAR'} else 'needs_attention',error.code)
                    return self.get(row['project_id'],row['plan_id'],con=con)
                ordinal=row['run_count']+1;due=row['next_due_at'];read_payload=collector_payload(request,self.key(row,ordinal))
                sync,replay=self.analytics._create_authorized(row['project_id'],read_payload,authority=value['policy']['authority'],con=con,deadline_cap=request.deadline)
                if replay:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_UNEXPECTED_EXISTING_OCCURRENCE')
                self.analytics.identity(authority=value['policy']['authority'])
                admitted=sync['snapshot']['consented_at'];identity='noao_'+uuid.uuid4().hex
                occurrence={'schema_version':'native-official-analytics-refresh-occurrence-v1','occurrence_id':identity,'plan_id':row['plan_id'],'workspace_id':self.workspace,'project_id':row['project_id'],'publication_id':row['publication_id'],
                    'ordinal':ordinal,'policy_sha256':row['policy_sha256'],'sync_id':sync['sync_id'],'consent_sha256':sync['snapshot_sha256'],
                    'read_request_sha256':digest(sync['snapshot']['request']),'due_at':due,'admitted_at':admitted}
                con.execute('INSERT INTO native_official_analytics_refresh_occurrences VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (identity,row['plan_id'],self.workspace,row['project_id'],row['publication_id'],ordinal,row['policy_sha256'],sync['sync_id'],sync['snapshot_sha256'],digest(occurrence),json.dumps(occurrence)))
                con.execute('UPDATE native_official_analytics_refresh_plans SET run_count=?,pending_sync_id=?,next_due_at=?,version=version+1,updated_at=? WHERE plan_id=?',
                    (ordinal,sync['sync_id'],(at(admitted)+timedelta(seconds=request.interval_seconds)).isoformat(),admitted,row['plan_id']))
                self.event(con,row,'analytics.official.refresh.admitted','worker',occurrence_id=identity,sync_id=sync['sync_id'],ordinal=ordinal,external_call=False)
                self.analytics.identity(authority=value['policy']['authority'])
                return self.get(row['project_id'],row['plan_id'],con=con)
        return None
    def cancel(self,project,identity,payload,*,principal):
        payload=typed(payload,RefreshCancel);authority=self.analytics.identity(principal)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.get(project,identity,con=con)
            if payload.expected_policy_sha256!=row['policy_sha256'] or payload.expected_version!=row['version']:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_REVIEW_BINDING_CHANGED')
            if row['status'] not in {'cancelled','completed'}:
                if payload.cancel_pending_read and row['pending_sync_id']:
                    sync=value['occurrences'][-1]['sync']
                    self.analytics._cancel_authorized(project,sync['sync_id'],Cancel(expected_snapshot_sha256=sync['snapshot_sha256']),authority=authority,con=con)
                con.execute("UPDATE native_official_analytics_refresh_plans SET status='cancelled',version=version+1,updated_at=? WHERE plan_id=?",(utc(self.clock()).isoformat(),identity))
                self.event(con,row,'analytics.official.refresh.cancelled',authority['token_id'],cancel_pending_read=payload.cancel_pending_read,external_call=False,remote_deletion=False)
                self.analytics.identity(authority=authority)
            return self.get(project,identity,con=con)
    def recover(self):
        self.check();count=0
        with self.store.transaction() as con:
            for row in con.execute("SELECT * FROM native_official_analytics_refresh_plans WHERE workspace_id=? AND status='active' AND pending_sync_id IS NOT NULL",(self.workspace,)).fetchall():
                value=self.get(row['project_id'],row['plan_id'],con=con);sync=value['occurrences'][-1]['sync']
                if sync['status'] not in PENDING|{'succeeded'}:
                    self.stop(con,row,'needs_attention','NATIVE_OFFICIAL_REFRESH_RECOVERY_REVIEW_REQUIRED',clear=True);count+=1
        return {'plans_needing_attention':count,'external_calls':0,'automatic_unknown_retry':False,'token_returned':False}
    def page(self,project,*,publication=None,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100 or publication is not None and (not isinstance(publication,str) or not re.fullmatch(r'nopu_[a-f0-9]{32}',publication)):
            raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if (not isinstance(after,list) or len(after)!=5 or after[:3]!=[self.workspace,project,publication]
                    or not isinstance(after[3],str) or len(after[3])>40 or not isinstance(after[4],str) or not re.fullmatch(r'noap_[a-f0-9]{32}',after[4])):raise ValueError()
                at(after[3])
            except (ValueError,TypeError,IndexError):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400) from None
        with self.store.transaction() as con:
            self.check();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            if publication:self.analytics.publications.get(project,publication,con=con)
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if publication:where+=' AND publication_id=?';params.append(publication)
            if after:where+=' AND (created_at<? OR (created_at=? AND plan_id<?))';params.extend([after[3],after[3],after[4]])
            rows=con.execute('SELECT * FROM native_official_analytics_refresh_plans WHERE '+where+' ORDER BY created_at DESC,plan_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            values=[self.get(project,row['plan_id'],con=con) for row in rows[:limit]]
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,publication,rows[limit-1]['created_at'],rows[limit-1]['plan_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
        return {'schema_version':'native-official-analytics-refresh-page-v1','workspace_id':self.workspace,'project_id':project,'publication_id':publication,
            'items':values,'next_cursor':next_cursor,'truncated':len(rows)>limit,'publishing_enabled':False,'token_returned':False}
