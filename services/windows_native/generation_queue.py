"""Owned durable admission, claims and provider observations for Native generation.

No worker/HTTP/UI is started here. Private worker methods require fenced claims;
recovery queues only reconciliation and never reauthorizes a generation POST.
"""
import hashlib,json,re,time,uuid
from copy import deepcopy
from .contracts import WorkflowError,digest
from .generation_models import GenerationCreate,GenerationAction,GenerationRecovery
from .generation_registry import GenerationFactory,approved_catalog,MANIFEST
from .generation_references import NativeGenerationReferences,parameters,selected_references,api_parameters
from .store import now
from .costs import CostLedger
from app.media_generation_routes import workflow_routes,generation_envelope
from app.comfyui_generation_lifecycle import GenerationObservation

STATES={'not_configured','queued','running','succeeded','failed','cancelled','recovery_required','needs_approval'}
ID=re.compile(r'^[a-f0-9]{32}$')


class NativeGenerationQueue:
    def __init__(self,store,*,workspace_id='wsp_native_local',factory=None,clock=time.time,references=None):
        if factory is not None and type(factory) is not GenerationFactory:raise WorkflowError('NATIVE_GENERATION_CONFIGURATION_INVALID',400)
        self.store,self.workspace,self.factory,self.clock=store,workspace_id,factory,clock
        self.costs=CostLedger(store)
        self.references=references or NativeGenerationReferences(store,workspace_id=workspace_id)
        if self.references.store is not store or self.references.workspace!=workspace_id:raise WorkflowError('NATIVE_GENERATION_WORKSPACE_MISMATCH',400)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_generation_bindings (name TEXT PRIMARY KEY,workspace_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_generation_jobs (generation_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,key_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,phase TEXT NOT NULL,claim_id TEXT,lease_until REAL,dispatch_started INTEGER NOT NULL,
                provider_input_json TEXT,provider_input_sha256 TEXT,provider_job_id TEXT,observation_json TEXT,observation_sha256 TEXT,
                cost_operation_id TEXT,cancel_requested INTEGER NOT NULL,recovery_count INTEGER NOT NULL,failure_code TEXT,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_generation_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,generation_id TEXT NOT NULL,
                project_id TEXT NOT NULL,action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_generation_recovery_requests (generation_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,PRIMARY KEY(generation_id,key_sha256));''')
            bound=con.execute("SELECT workspace_id FROM native_generation_bindings WHERE name='workspace'").fetchone()
            if (bound and bound[0]!=workspace_id or con.execute('SELECT 1 FROM native_generation_jobs WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone()
                or con.execute('SELECT 1 FROM native_generation_reference_admissions WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone()):
                raise WorkflowError('NATIVE_GENERATION_WORKSPACE_MISMATCH',400)
            con.execute("INSERT OR IGNORE INTO native_generation_bindings VALUES('workspace',?)",(workspace_id,))

    def selection(self,value):
        inputs=api_parameters(value,{ref.asset_id:'native-owned-selection://'+ref.asset_id for ref in selected_references(value)})
        primary='npd-text-to-image-v1' if value.modality=='image' else 'npd-video-generation-v1'
        key,operation,_=generation_envelope(value.modality,inputs,workflow_routes(value.modality,primary))
        if self.factory:
            try:return self.factory.selection(value.modality,inputs)
            except WorkflowError as error:
                if error.code!='NATIVE_GENERATION_WORKFLOW_NOT_APPROVED':raise
                return {'provider':'comfyui-'+value.modality,'workflow_id':key,'workflow_version':None,'operation':operation,'workflow_sha256':None,
                    'manifest_sha256':self.factory.catalog['manifest_sha256'],'provider_configuration_sha256':self.factory.sha256,'mode':self.factory.mode,
                    'status':'NOT_CONFIGURED','executable_workflow_reviewed':False,'real_provider_tested':False}
        catalog=approved_catalog(MANIFEST);definition=catalog['definitions'][key]
        return {'provider':'comfyui-'+value.modality,'workflow_id':key,'workflow_version':definition.version,'operation':operation,
            'workflow_sha256':catalog['workflow_sha256'][key],'manifest_sha256':catalog['manifest_sha256'],'provider_configuration_sha256':None,
            'mode':'official','status':'NOT_CONFIGURED','executable_workflow_reviewed':catalog['reviewed'][key],'real_provider_tested':False}

    def row(self,con,project,identity):
        row=con.execute('SELECT * FROM native_generation_jobs WHERE generation_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_GENERATION_JOB_NOT_FOUND',404)
        return row

    def read(self,row):
        try:
            snapshot=json.loads(row['snapshot_json']);request=GenerationCreate.model_validate({**snapshot['request'],'request_key':'private-generation-read-key'})
            value=parameters(snapshot['request']['parameters']);selection=snapshot['selection']
            provider_input=json.loads(row['provider_input_json']) if row['provider_input_json'] else None
            observation=GenerationObservation.model_validate_json(row['observation_json']) if row['observation_json'] else None
            if (not ID.fullmatch(row['generation_id']) or row['workspace_id']!=self.workspace or row['status'] not in STATES
                or snapshot.get('schema_version')!='native-generation-job-snapshot-v1' or snapshot.get('workspace_id')!=self.workspace
                or snapshot.get('project_id')!=row['project_id'] or snapshot.get('generation_id')!=row['generation_id']
                or digest(snapshot)!=row['snapshot_sha256'] or digest(snapshot['request'])!=row['request_fingerprint']
                or snapshot.get('request_fingerprint')!=row['request_fingerprint'] or row['dispatch_started'] not in (0,1) or row['cancel_requested'] not in (0,1)
                or not 0<=row['recovery_count']<=3 or selection['mode'] not in {'fixture','official'}
                or selection['status'] not in {'CONFIGURED','NOT_CONFIGURED'} or selection['provider']!='comfyui-'+value.modality
                or selection['real_provider_tested'] is not False or selection['status']=='NOT_CONFIGURED' and row['status'] not in {'not_configured','cancelled'}
                or request.external_acknowledged!=(selection['mode']=='official') or request.fixture_acknowledged!=(selection['mode']=='fixture')
                or selection['workflow_id']!=generation_envelope(value.modality,api_parameters(value,{ref.asset_id:'native-owned-selection://'+ref.asset_id for ref in selected_references(value)}),
                    workflow_routes(value.modality,'npd-text-to-image-v1' if value.modality=='image' else 'npd-video-generation-v1'))[0]):raise ValueError()
            source=snapshot.get('references')
            if source is not None:
                from .generation_references import ReferenceSnapshot
                typed=ReferenceSnapshot.model_validate(source)
                if (typed.sha256!=digest({k:v for k,v in source.items() if k!='sha256'}) or typed.project_id!=row['project_id'] or typed.workspace_id!=self.workspace
                    or typed.revision!=request.revision or typed.parameters!=snapshot['request']['parameters'] or typed.document_sha256!=snapshot['document_sha256']
                    or typed.provider_configuration_sha256!=selection['provider_configuration_sha256'] or typed.provider_mode!=selection['mode']):raise ValueError()
            elif selection['status']=='CONFIGURED':raise ValueError()
            if provider_input is not None:
                refs={ref.asset_id:'vf-reference://'+('0'*64) for ref in selected_references(value)}
                expected=api_parameters(value,refs);cls=type(expected);typed=cls.model_validate(provider_input)
                if digest(provider_input)!=row['provider_input_sha256'] or row['dispatch_started'] and row['cost_operation_id'] is None:raise ValueError()
                supplied=[*typed.reference_images,*([typed.mask_reference] if hasattr(typed,'mask_reference') and typed.mask_reference else [])]
                if any(not re.fullmatch(r'vf-reference://[a-f0-9]{64}',uri) for uri in supplied):raise ValueError()
                unbound=typed.model_dump(mode='json');unbound.pop('reference_images');unbound.pop('mask_reference',None)
                scalars=expected.model_dump(mode='json');scalars.pop('reference_images');scalars.pop('mask_reference',None)
                if unbound!=scalars or len(typed.reference_images)!=len(value.references):raise ValueError()
            elif row['dispatch_started'] or row['provider_input_sha256'] is not None:raise ValueError()
            if observation:
                if (digest(observation.model_dump(mode='json'))!=row['observation_sha256'] or observation.provider_job_id!=row['provider_job_id']
                    or observation.workspace_id!=self.workspace or observation.workflow_id!=selection['workflow_id']
                    or observation.workflow_version!=selection['workflow_version'] or not row['dispatch_started']):raise ValueError()
            elif row['provider_job_id'] is not None or row['observation_sha256'] is not None:raise ValueError()
            if (row['status']=='running')!=(row['claim_id'] is not None and row['lease_until'] is not None):raise ValueError()
            if row['status']=='succeeded' and (not observation or observation.status!='succeeded' or not row['dispatch_started'] or row['failure_code'] is not None):raise ValueError()
        except (ValueError,TypeError,KeyError):raise WorkflowError('NATIVE_GENERATION_JOURNAL_INVALID') from None
        public={k:row[k] for k in ('generation_id','workspace_id','project_id','request_fingerprint','status','phase','provider_job_id','cost_operation_id',
            'recovery_count','failure_code','created_at','updated_at')}
        return {'schema_version':'native-generation-job-v1',**public,'cancel_requested':bool(row['cancel_requested']),'dispatch_started':bool(row['dispatch_started']),
            'snapshot':snapshot,'provider_input':provider_input,'observation':observation.model_dump(mode='json') if observation else None,
            'worker_wired':False,'publish_enabled':False,'automatic_attachment':False,'real_provider_tested':False}

    def event(self,con,row,action,actor,**evidence):
        if not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_GENERATION_ACTOR_INVALID',400)
        con.execute('INSERT INTO native_generation_events(generation_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (row['generation_id'],row['project_id'],action,actor,json.dumps(evidence,allow_nan=False),now()))

    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(self.row(con,project,identity))

    def page(self,project,*,limit=25):
        if type(limit) is not int or not 1<=limit<=200:raise WorkflowError('NATIVE_GENERATION_PAGE_INVALID',400)
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            return {'schema_version':'native-generation-page-v1','workspace_id':self.workspace,'project_id':project,
                'items':[self.read(row) for row in con.execute('SELECT * FROM native_generation_jobs WHERE workspace_id=? AND project_id=? ORDER BY created_at DESC,generation_id DESC LIMIT ?',
                    (self.workspace,project,limit))],'worker_wired':False,'publish_enabled':False}

    def create(self,project,payload,*,actor,on_admitted=None):
        if type(payload) is not GenerationCreate or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_GENERATION_REQUEST_INVALID',400)
        if on_admitted is not None and not callable(on_admitted):raise WorkflowError('NATIVE_GENERATION_ADMISSION_HOOK_INVALID',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fingerprint=digest(request)
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_generation_jobs WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if old:
                if old['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_GENERATION_IDEMPOTENCY_CONFLICT')
                return self.read(old),True
        selection=self.selection(payload.parameters)
        if payload.external_acknowledged!=(selection['mode']=='official') or payload.fixture_acknowledged!=(selection['mode']=='fixture'):
            raise WorkflowError('NATIVE_GENERATION_SOURCE_ACK_REQUIRED',400)
        references=self.references.freeze(project,payload.revision,payload.parameters,self.factory,fixture_acknowledged=payload.fixture_acknowledged) if selection['status']=='CONFIGURED' else None
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_generation_jobs WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if old:
                if old['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_GENERATION_IDEMPOTENCY_CONFLICT')
                return self.read(old),True
            current=self.store.editable(con,project,payload.revision)
            if references and references['document_sha256']!=digest(current['document']):raise WorkflowError('NATIVE_GENERATION_PROJECT_CHANGED')
            if (con.execute('SELECT count(*) FROM native_generation_jobs WHERE workspace_id=? AND project_id=?',(self.workspace,project)).fetchone()[0]>=200
                or con.execute('SELECT count(*) FROM native_generation_jobs').fetchone()[0]>=5000):
                raise WorkflowError('NATIVE_GENERATION_HISTORY_LIMIT')
            identity=uuid.uuid4().hex;stamp=now();snapshot={'schema_version':'native-generation-job-snapshot-v1','generation_id':identity,'workspace_id':self.workspace,
                'project_id':project,'request':request,'request_fingerprint':fingerprint,'selection':selection,'document_sha256':digest(current['document']),'references':references}
            status='queued' if references is not None else 'not_configured'
            con.execute('INSERT INTO native_generation_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,fingerprint,key,json.dumps(snapshot),digest(snapshot),status,status,None,None,0,None,None,None,None,None,None,0,0,None,stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'generation.request.created',actor,status=status,external_call=False)
            value=self.read(row)
            # Internal consumers may bind their journal in this same FULL transaction.
            # Raising rolls back the job/event; no worker can observe an unbound job.
            if on_admitted is not None:on_admitted(con,current,value)
            return value,False

    def claim(self):
        with self.store.transaction() as con:
            for row in con.execute("SELECT * FROM native_generation_jobs WHERE workspace_id=? AND status='running' AND lease_until<=?",(self.workspace,self.clock())).fetchall():
                self.read(row);con.execute("UPDATE native_generation_jobs SET status='recovery_required',phase='interrupted',claim_id=NULL,lease_until=NULL,failure_code='NATIVE_GENERATION_WORKER_INTERRUPTED',updated_at=? WHERE generation_id=?",(now(),row['generation_id']))
                self.event(con,row,'generation.worker.interrupted','native-generation-worker',dispatch_started=bool(row['dispatch_started']),external_outcome_unknown=bool(row['dispatch_started']))
            if con.execute("SELECT 1 FROM native_generation_jobs WHERE workspace_id=? AND status='running'",(self.workspace,)).fetchone():return None
            if self.factory is None or not self.factory.enabled:return None
            row=con.execute("SELECT * FROM native_generation_jobs WHERE workspace_id=? AND status='queued' ORDER BY created_at,generation_id LIMIT 1",(self.workspace,)).fetchone()
            if row is None:return None
            value=self.read(row)
            try:selected=self.selection(parameters(value['snapshot']['request']['parameters']))
            except WorkflowError:selected=None
            if (selected is None or selected['status']!='CONFIGURED' or selected['provider_configuration_sha256']!=value['snapshot']['selection']['provider_configuration_sha256']
                or selected['workflow_sha256']!=value['snapshot']['selection']['workflow_sha256']):
                status='recovery_required' if row['dispatch_started'] else 'failed'
                con.execute('UPDATE native_generation_jobs SET status=?,phase=?,failure_code=?,updated_at=? WHERE generation_id=?',
                    (status,status,'NATIVE_GENERATION_PROVIDER_CONFIGURATION_CHANGED',now(),row['generation_id']))
                self.event(con,row,'generation.configuration.changed','native-generation-worker',status=status,external_call=False);return None
            claim=uuid.uuid4().hex;mode='reconcile' if row['dispatch_started'] else 'create'
            con.execute("UPDATE native_generation_jobs SET status='running',phase=?,claim_id=?,lease_until=?,updated_at=? WHERE generation_id=?",('reconciling' if mode=='reconcile' else 'admitted',claim,self.clock()+900,now(),row['generation_id']))
            self.event(con,row,'generation.worker.claimed','native-generation-worker',mode=mode)
            return {'generation_id':row['generation_id'],'project_id':row['project_id'],'claim_id':claim,'mode':mode,'job':self.read(self.row(con,row['project_id'],row['generation_id']))}

    def fenced(self,con,claim):
        row=self.row(con,claim['project_id'],claim['generation_id']);self.read(row)
        if row['status']!='running' or row['claim_id']!=claim['claim_id'] or row['lease_until']<=self.clock():raise WorkflowError('NATIVE_GENERATION_WORKER_FENCED')
        return row

    def bind_input(self,claim,payload):
        with self.store.transaction() as con:
            row=self.fenced(con,claim);value=self.read(row);snapshot=value['snapshot']
            if row['dispatch_started']:raise WorkflowError('NATIVE_GENERATION_NO_RESUBMISSION')
            expected_payload=self.bound_input(con,row);expected=expected_payload.model_dump(mode='json')
            if type(payload) is not type(expected_payload) or payload.model_dump(mode='json')!=expected:raise WorkflowError('NATIVE_GENERATION_PROVIDER_INPUT_CHANGED')
            if value['provider_input'] is not None and value['provider_input']!=expected:raise WorkflowError('NATIVE_GENERATION_PROVIDER_INPUT_CHANGED')
            con.execute("UPDATE native_generation_jobs SET provider_input_json=?,provider_input_sha256=?,phase='input_bound',updated_at=? WHERE generation_id=?",(json.dumps(expected),digest(expected),now(),row['generation_id']))
            self.event(con,row,'generation.input.bound','native-generation-worker',input_sha256=digest(expected),external_call=False)

    def renew(self,claim):
        with self.store.transaction() as con:
            row=self.fenced(con,claim)
            con.execute('UPDATE native_generation_jobs SET lease_until=?,updated_at=? WHERE generation_id=? AND claim_id=?',(self.clock()+900,now(),row['generation_id'],claim['claim_id']))

    def bound_input(self,con,row):
        snapshot=self.read(row)['snapshot'];typed,params,_=self.references.check(snapshot['references'],self.factory,con);uris={}
        for source in typed.sources:
            saved=con.execute('SELECT * FROM native_generation_reference_admissions WHERE workspace_id=? AND project_id=? AND generation_id=? AND asset_id=?',
                (self.workspace,row['project_id'],row['generation_id'],source.asset_id)).fetchone()
            if saved is None or saved['state']!='confirmed':raise WorkflowError('NATIVE_GENERATION_REFERENCE_NOT_CONFIRMED')
            bound=self.references.read(saved,snapshot['references']);uris[source.asset_id]='vf-reference://'+bound['reference_id']
        return api_parameters(params,uris)

    def mark_dispatch(self,claim,cost_operation_id):
        with self.store.transaction() as con:
            row=self.fenced(con,claim);value=self.read(row)
            if row['dispatch_started'] or value['provider_input'] is None:raise WorkflowError('NATIVE_GENERATION_NO_RESUBMISSION')
            if row['cancel_requested']:raise WorkflowError('NATIVE_GENERATION_CANCELLED_BEFORE_DISPATCH')
            if self.bound_input(con,row).model_dump(mode='json')!=value['provider_input']:raise WorkflowError('NATIVE_GENERATION_PROVIDER_INPUT_CHANGED')
            cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(cost_operation_id,)).fetchone()
            if (cost is None or cost['project_id']!=row['project_id'] or cost['job_id'] is not None or cost['provider']!=value['snapshot']['selection']['provider']
                or cost['request_sha256']!=row['request_fingerprint'] or cost['status']!='dispatch_intent'
                or cost['operation']!='generation.'+row['generation_id']+'.submit' or cost['model']!='workflow:'+value['snapshot']['selection']['workflow_id']
                or not cost['external_call']
                or bool(cost['paid'])!=(value['snapshot']['selection']['mode']=='official')):raise WorkflowError('NATIVE_GENERATION_COST_ADMISSION_INVALID')
            con.execute("UPDATE native_generation_jobs SET dispatch_started=1,cost_operation_id=?,phase='submitting',updated_at=? WHERE generation_id=?",(cost_operation_id,now(),row['generation_id']))
            self.event(con,row,'generation.dispatch.intent','native-generation-worker',cost_operation_id=cost_operation_id,input_sha256=row['provider_input_sha256'])

    def observe(self,claim,body):
        try:observation=GenerationObservation.model_validate(body).model_dump(mode='json')
        except (ValueError,TypeError):raise WorkflowError('NATIVE_GENERATION_OBSERVATION_INVALID') from None
        with self.store.transaction() as con:
            row=self.fenced(con,claim);value=self.read(row);selected=value['snapshot']['selection']
            if (not row['dispatch_started'] or observation['workspace_id']!=self.workspace or observation['workflow_id']!=selected['workflow_id']
                or observation['workflow_version']!=selected['workflow_version'] or row['provider_job_id'] is not None and row['provider_job_id']!=observation['provider_job_id']):
                raise WorkflowError('NATIVE_GENERATION_OBSERVATION_BINDING_INVALID')
            if value['observation']==observation:return False
            con.execute("UPDATE native_generation_jobs SET provider_job_id=?,observation_json=?,observation_sha256=?,phase='observed',updated_at=? WHERE generation_id=?",
                (observation['provider_job_id'],json.dumps(observation),digest(observation),now(),row['generation_id']))
            self.event(con,row,'generation.provider.observed','native-generation-worker',**observation);return True

    def fail(self,claim,code,*,needs_approval=False):
        if not isinstance(code,str) or not re.fullmatch(r'[A-Z0-9_]{1,120}',code) or type(needs_approval) is not bool:raise WorkflowError('NATIVE_GENERATION_FAILURE_INVALID',400)
        with self.store.transaction() as con:
            row=self.fenced(con,claim);value=self.read(row)
            confirmed=value['observation'] and value['observation']['status']=='cancelled'
            status='cancelled' if confirmed else 'recovery_required' if row['dispatch_started'] else 'needs_approval' if needs_approval else 'cancelled' if row['cancel_requested'] else 'failed'
            con.execute('UPDATE native_generation_jobs SET status=?,phase=?,claim_id=NULL,lease_until=NULL,failure_code=?,updated_at=? WHERE generation_id=?',(status,status,code,now(),row['generation_id']))
            self.event(con,row,'generation.worker.stopped','native-generation-worker',status=status,failure_code=code,remote_outcome_unknown=bool(row['dispatch_started'] and not confirmed))
            return self.read(self.row(con,row['project_id'],row['generation_id']))

    def cancel(self,project,identity,payload,*,actor):
        if type(payload) is not GenerationAction:raise WorkflowError('NATIVE_GENERATION_CANCEL_INVALID',400)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);self.read(row)
            if payload.expected_fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_GENERATION_BINDING_CHANGED')
            if row['status']=='cancelled':return self.read(row)
            if row['status'] not in {'queued','running','not_configured','needs_approval','recovery_required'}:raise WorkflowError('NATIVE_GENERATION_CANCEL_STATE_INVALID')
            local=not row['dispatch_started'] and row['status']!='running'
            con.execute('UPDATE native_generation_jobs SET cancel_requested=1,status=?,phase=?,updated_at=? WHERE generation_id=?',
                ('cancelled' if local else row['status'],'cancelled' if local else row['phase'],now(),identity))
            self.event(con,row,'generation.cancel.requested',actor,local_confirmed=local,remote_cancel_confirmed=False);return self.read(self.row(con,project,identity))

    def recover(self,project,identity,payload,*,actor):
        if type(payload) is not GenerationRecovery or not payload.acknowledged:raise WorkflowError('NATIVE_GENERATION_RECOVERY_ACK_REQUIRED',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fingerprint=digest(request)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row)
            if payload.expected_fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_GENERATION_BINDING_CHANGED')
            prior=con.execute('SELECT * FROM native_generation_recovery_requests WHERE generation_id=? AND key_sha256=?',(identity,key)).fetchone()
            if prior:
                receipt=json.loads(prior['receipt_json'])
                if (prior['request_sha256']!=fingerprint or digest(receipt)!=prior['receipt_sha256'] or receipt.get('generation_id')!=identity or receipt.get('project_id')!=project or receipt.get('workspace_id')!=self.workspace
                    or receipt.get('mode')!='reconcile' or receipt.get('generation_submission_authorized') is not False or receipt.get('external_calls')!=0
                    or receipt.get('request_fingerprint')!=row['request_fingerprint'] or type(receipt.get('recovery_count')) is not int or not 1<=receipt['recovery_count']<=row['recovery_count']):
                    raise WorkflowError('NATIVE_GENERATION_RECOVERY_RECEIPT_INVALID')
                return {**receipt,'idempotent_replay':True}
            if row['status']!='recovery_required' or not row['dispatch_started'] or value['provider_input'] is None or row['recovery_count']>=3:
                raise WorkflowError('NATIVE_GENERATION_RECONCILIATION_STATE_INVALID')
            count=row['recovery_count']+1
            con.execute("UPDATE native_generation_jobs SET status='queued',phase='reconcile_queued',recovery_count=?,updated_at=? WHERE generation_id=?",(count,now(),identity))
            receipt={'schema_version':'native-generation-reconciliation-request-v1','generation_id':identity,'workspace_id':self.workspace,'project_id':project,
                'request_fingerprint':row['request_fingerprint'],'mode':'reconcile','recovery_count':count,'generation_submission_authorized':False,'external_calls':0,'actor_ref':actor,'idempotent_replay':False}
            con.execute('INSERT INTO native_generation_recovery_requests VALUES(?,?,?,?,?)',(identity,key,fingerprint,json.dumps(receipt),digest(receipt)))
            self.event(con,row,'generation.reconciliation.queued',actor,recovery_count=count,generation_submission_authorized=False);return receipt
