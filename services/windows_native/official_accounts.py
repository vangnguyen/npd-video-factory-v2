"""Durable scoped read-only account checks; never a publishing authorization."""
import asyncio,base64,json,re,uuid
from contextlib import nullcontext
from datetime import datetime,timezone
from typing import Literal
from pydantic import Field,StrictInt,field_validator
from .backup import guard
from .contracts import WorkflowError,digest
from .costs import CostLedger
from .store import now
from .official_account_registry import AccountFactory
from .meta_connection import NativeMetaAccountFactory
from app.models import StrictModel
from app.analytics_official import AnalyticsOfficialError,account_request,confirm_account,response_digest
from app.publishing_wire import PublishingWireError
from app.publishing_credentials import target_digest
from app.publishing_models import PublishingTargetBinding

class Verify(StrictModel):
    schema_version:Literal['native-official-account-check-request-v1']='native-official-account-check-request-v1'
    revision:StrictInt=Field(ge=1)
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_read_only:Literal[True]
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_read_only',mode='before')
    @classmethod
    def acknowledge(cls,value):
        if value is not True:raise ValueError('Explicit read-only acknowledgement required')
        return value

class NativeOfficialAccounts:
    def __init__(self,store,*,workspace_id='wsp_native_local',factories=None,clock=lambda:datetime.now(timezone.utc)):
        self.store,self.workspace,self.clock=store,workspace_id,clock;self.factories=dict(factories or {})
        self.check_workspace()
        if len(self.factories)>50 or any(type(f) not in (AccountFactory,NativeMetaAccountFactory) or key!=f.account.account_ref or f.workspace!=workspace_id or f.root.absolute()!=store.root.absolute() for key,f in self.factories.items()):
            raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
        self.costs=CostLedger(store)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_account_checks (
                check_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,account_ref TEXT NOT NULL,
                key_sha256 TEXT NOT NULL,request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                status TEXT NOT NULL,attempts INTEGER NOT NULL,claim_id TEXT,result_json TEXT,result_sha256 TEXT,failure_code TEXT,
                actor_ref TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256));
                CREATE INDEX IF NOT EXISTS native_official_account_history ON native_official_account_checks(workspace_id,project_id,created_at,check_id);
                CREATE TABLE IF NOT EXISTS native_official_account_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,check_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_account_checks WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_WORKSPACE_CHANGED')

    def check_workspace(self):
        path=guard(self.store.root/'.vf-auth-workspace.json')
        try:
            if not path.exists():
                if self.workspace!='wsp_native_local':raise ValueError()
            elif path.stat().st_size>512 or json.loads(path.read_bytes())!={'schema':'vf-native-workspace-binding-v1','workspace_id':self.workspace}:raise ValueError()
        except (ValueError,TypeError,OSError):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_WORKSPACE_CHANGED') from None

    def states(self):
        self.check_workspace()
        return {'schema_version':'native-official-accounts-v1','workspace_id':self.workspace,'accounts':[f.public() for _,f in sorted(self.factories.items())],
            'supported_read_contracts':['youtube','tiktok','facebook','instagram_reels'],'publishing_enabled':False,'automatic_verification':False,'token_returned':False,'real_provider_tested':False}

    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_official_account_events(check_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['check_id'],self.workspace,row['project_id'],action,actor,json.dumps(evidence),now()))

    def row(self,con,project,identity):
        self.check_workspace();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_official_account_checks WHERE check_id=? AND project_id=? AND workspace_id=?',(identity,project,self.workspace)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CHECK_NOT_FOUND',404)
        return row

    def read(self,row):
        value=dict(row)
        try:
            snapshot=json.loads(value.pop('snapshot_json'));raw=value.pop('result_json');result=json.loads(raw) if raw else None
            if (value['workspace_id']!=self.workspace or digest(snapshot)!=value['snapshot_sha256'] or snapshot['workspace_id']!=self.workspace
                or snapshot['project_id']!=value['project_id'] or snapshot['account_ref']!=value['account_ref']
                or digest(snapshot['request'])!=value['request_fingerprint'] or snapshot['schema_version']!='native-official-account-check-snapshot-v1'):raise ValueError()
            Verify.model_validate({**snapshot['request'],'request_key':'internal-account-check-key'})
            if (type(snapshot['mock']) is not bool or type(snapshot['project_revision']) is not int
                or snapshot['project_revision']!=snapshot['request']['revision']
                or snapshot['configuration_sha256']!=snapshot['request']['expected_configuration_sha256']
                or not re.fullmatch(r'[a-f0-9]{64}',snapshot['document_sha256'])):raise ValueError()
            target=PublishingTargetBinding.model_validate(snapshot['target'])
            if target.workspace_id!=self.workspace or snapshot['target_binding_sha256']!=target_digest(target):raise ValueError()
            if target.platform in ('facebook','instagram_reels'):
                from .meta_account_evidence import validate
                validate(snapshot,result)
            elif 'meta' in snapshot or result is not None and 'meta' in result:raise ValueError()
            if value['status'] not in {'queued','running','succeeded','failed','not_configured','cancelled','outcome_unknown'}:raise ValueError()
            if (value['status']=='succeeded')!=(result is not None):raise ValueError()
            if result is not None:
                if (digest(result)!=value['result_sha256'] or result['schema_version']!='native-official-account-check-result-v1'
                    or any(result[n]!=value[n] for n in ('check_id','workspace_id','project_id','account_ref','snapshot_sha256'))
                    or result['target_binding_sha256']!=snapshot['target_binding_sha256'] or result['account_match'] is not True
                    or result['read_only'] is not True or result['publishing_enabled'] is not False
                    or result['token_returned'] is not False or result['real_provider_tested'] is not False
                    or type(result['mock']) is not bool or result['mock'] is not snapshot['mock']
                    or type(result['external_call']) is not bool or result['mock']==result['external_call']
                    or result['operation']!='account_lookup' or type(result['response_status']) is not int or result['response_status']!=200
                    or not re.fullmatch(r'[a-f0-9]{64}',result['response_sha256'])):raise ValueError()
            value.pop('key_sha256');value.pop('claim_id')
            return {**value,'schema_version':'native-official-account-check-v1','snapshot':snapshot,'result':result,'publishing_enabled':False,'token_returned':False}
        except (ValueError,KeyError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_EVIDENCE_CHANGED') from None

    def create(self,project,account_ref,payload,*,actor):
        self.check_workspace();request=payload.model_dump(mode='json',exclude={'request_key'});fp=digest(request);key=digest(payload.request_key)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_account_checks WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fp or prior['account_ref']!=account_ref:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_IDEMPOTENCY_CONFLICT')
                return self.linked(con,prior),True
            current=self.store.editable(con,project,payload.revision);factory=self.factories.get(account_ref)
            if factory is None:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_NOT_FOUND',404)
            public=factory.public()
            if public['configuration_sha256']!=payload.expected_configuration_sha256:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED')
            snapshot={'schema_version':'native-official-account-check-snapshot-v1','workspace_id':self.workspace,'project_id':project,'account_ref':account_ref,
                'project_revision':current['revision'],'document_sha256':digest(current['document']),'request':request,'target':public['target'],
                'target_binding_sha256':public['target_binding_sha256'],'configuration_sha256':public['configuration_sha256'],'mock':factory.client.mock}
            if type(factory) is NativeMetaAccountFactory:
                from .meta_account_evidence import source
                snapshot['meta']=source(factory,self.clock)
            status='queued' if public['status']=='CONFIGURED' else 'not_configured';stamp=now();identity='nack_'+uuid.uuid4().hex
            con.execute('INSERT INTO native_official_account_checks VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,account_ref,key,fp,digest(snapshot),json.dumps(snapshot),status,0,None,None,None,
                 'NATIVE_OFFICIAL_ACCOUNT_READ_NOT_CONFIGURED' if status=='not_configured' else None,actor,stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'account.check.created',actor,status=status,external_call=False)
            return self.read(row),False

    def linked(self,con,row):
        value=self.read(row)
        if value['snapshot']['target']['platform'] in ('facebook','instagram_reels'):
            from .meta_account_evidence import links
            links(self,con,value)
        return value

    def get(self,project,identity):
        with self.store.transaction() as con:return self.linked(con,self.row(con,project,identity))

    def page(self,project,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400)
        after=None
        if cursor is not None:
            try:
                if not isinstance(cursor,str) or len(cursor)>2048:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)))
                if not isinstance(after,list) or len(after)!=4 or after[:2]!=[self.workspace,project] or not isinstance(after[2],str) or len(after[2])>40 or not re.fullmatch(r'nack_[a-f0-9]{32}',after[3]):raise ValueError()
                if datetime.fromisoformat(after[2]).tzinfo is None:raise ValueError()
            except (ValueError,TypeError,IndexError):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400) from None
        with self.store.transaction() as con:
            self.check_workspace();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND check_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_official_account_checks WHERE '+where+' ORDER BY created_at DESC,check_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            next_cursor=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['created_at'],rows[limit-1]['check_id']]).encode()).decode().rstrip('=') if len(rows)>limit else None
            return {'schema_version':'native-official-account-check-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.linked(con,r) for r in rows[:limit]],
                'truncated':len(rows)>limit,'next_cursor':next_cursor,'publishing_enabled':False,'token_returned':False}

    def admission(self,project,identity,claim,*,con=None):
        with (self.store.transaction() if con is None else nullcontext(con)) as con:
            row=self.row(con,project,identity);value=self.read(row);snapshot=value['snapshot'];factory=self.factories.get(row['account_ref'])
            current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            if row['status']!='running' or row['claim_id']!=claim:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CHECK_CANCELLED')
            if current['revision']!=snapshot['project_revision'] or digest(current['document'])!=snapshot['document_sha256']:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PROJECT_CHANGED')
            if factory is None or factory.public()['status']!='CONFIGURED' or factory.sha256!=snapshot['configuration_sha256'] or factory.client.mock is not snapshot['mock']:
                raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED')
            if type(factory) is NativeMetaAccountFactory:
                from .meta_account_evidence import admission
                admission(factory,snapshot,self.clock())
            return factory,value

    def process(self,*,project=None,identity=None,fingerprint=None):
        self.check_workspace()
        with self.store.transaction() as con:
            row=self.row(con,project,identity) if identity else con.execute("SELECT * FROM native_official_account_checks WHERE workspace_id=? AND status='queued' ORDER BY created_at,check_id LIMIT 1",(self.workspace,)).fetchone()
            if row is None:return None
            value=self.read(row)
            if identity and fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_BINDING_CHANGED')
            if row['status']!='queued':return value
            project,identity=row['project_id'],row['check_id'];claim=uuid.uuid4().hex
            con.execute("UPDATE native_official_account_checks SET status='running',claim_id=?,attempts=attempts+1,updated_at=? WHERE check_id=?",(claim,now(),identity))
        operation=None;sent=False
        try:
            factory,value=self.admission(project,identity,claim);snapshot=value['snapshot']
            if type(factory) is NativeMetaAccountFactory:
                from .meta_account_evidence import lookup
                result=lookup(self,factory,value,project,identity,claim)
                with self.store.transaction() as con:
                    self.admission(project,identity,claim,con=con);row=self.row(con,project,identity)
                    if row['status']!='running' or row['claim_id']!=claim:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CHECK_CANCELLED')
                    con.execute("UPDATE native_official_account_checks SET status='succeeded',claim_id=NULL,result_json=?,result_sha256=?,updated_at=? WHERE check_id=?",(json.dumps(result),digest(result),now(),identity))
                    self.event(con,row,'account.check.confirmed','worker',mock=result['mock'],external_call=result['external_call'],response_sha256=result['response_sha256'])
                return self.get(project,identity)
            credential=factory.credential(now=self.clock())
            request=account_request(credential)
            operation=self.costs.begin(project_id=project,provider='official-'+credential.target.platform,model=None,operation='account_lookup.'+identity,
                request_sha256=digest({'check_id':identity,'snapshot_sha256':value['snapshot_sha256'],'operation':'account_lookup'}),estimated_cost=None,
                external_call=not factory.client.mock,paid=False)
            self.admission(project,identity,claim);sent=True
            response=asyncio.run(factory.client.request(request));self.costs.settle(operation,status='response_received',response_sha256=response_digest(response))
            confirmed=confirm_account(response,credential.target);self.admission(project,identity,claim)
            result={'schema_version':'native-official-account-check-result-v1','check_id':identity,'workspace_id':self.workspace,'project_id':project,'account_ref':value['account_ref'],
                'snapshot_sha256':value['snapshot_sha256'],'target_binding_sha256':snapshot['target_binding_sha256'],'account_match':confirmed['account_match'],
                'operation':'account_lookup','response_sha256':response_digest(response),'response_status':response.status,'cost_operation_id':operation,
                'mock':factory.client.mock,'external_call':not factory.client.mock,'read_only':True,'verified_at':self.clock().isoformat(),
                'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
            with self.store.transaction() as con:
                self.admission(project,identity,claim,con=con)
                row=self.row(con,project,identity)
                if row['status']!='running' or row['claim_id']!=claim:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CHECK_CANCELLED')
                con.execute("UPDATE native_official_account_checks SET status='succeeded',claim_id=NULL,result_json=?,result_sha256=?,updated_at=? WHERE check_id=?",(json.dumps(result),digest(result),now(),identity))
                self.event(con,row,'account.check.confirmed','worker',mock=result['mock'],external_call=result['external_call'],response_sha256=result['response_sha256'])
        except Exception as error:
            code=error.code if isinstance(error,(WorkflowError,AnalyticsOfficialError,PublishingWireError)) else 'NATIVE_OFFICIAL_ACCOUNT_CHECK_FAILED'
            if operation is not None:
                with self.store.transaction() as con:cost=con.execute('SELECT status FROM native_cost_operations WHERE id=?',(operation,)).fetchone()
                if cost and cost['status']=='dispatch_intent':self.costs.settle(operation,status='outcome_unknown' if sent else 'rejected',error_code=code)
            with self.store.transaction() as con:
                row=self.row(con,project,identity)
                if row['status']=='running' and row['claim_id']==claim:
                    con.execute("UPDATE native_official_account_checks SET status='failed',claim_id=NULL,failure_code=?,updated_at=? WHERE check_id=?",(code,now(),identity))
                    self.event(con,row,'account.check.failed','worker',failure_code=code)
        return self.get(project,identity)

    def recover(self):
        with self.store.transaction() as con:
            self.check_workspace()
            for row in con.execute("SELECT * FROM native_official_account_checks WHERE workspace_id=? AND status='running'",(self.workspace,)).fetchall():
                con.execute("UPDATE native_official_account_checks SET status='outcome_unknown',claim_id=NULL,failure_code='NATIVE_OFFICIAL_ACCOUNT_RESTART_REVIEW_REQUIRED',updated_at=? WHERE check_id=?",(now(),row['check_id']))
                self.event(con,row,'account.check.interrupted','recovery',automatic_retry=False)
