"""Independent, default-inactive Native generation execution and explicit import.

Submission uncertainty requires explicit read-only reconciliation. Actual media
staging and terminal receipts never authorize rights, approval or publication.
"""
import asyncio,hashlib,json,threading,time
from copy import deepcopy
from .backup import guard
from .contracts import WorkflowError,digest
from .generation_models import GenerationImport
from .generation_media import NativeGenerationMedia
from .store import now
from app.media_intelligence_models import ImageGenerationInput,VideoGenerationInput
from app.media_generation_scope import media_generation_scope


class NativeGenerationWorker:
    def __init__(self,queue,config):
        self.queue,self.store,self.config=queue,queue.store,config;self.media=NativeGenerationMedia(queue,config)
        self.stop,self.wake,self.worker=threading.Event(),threading.Event(),None
        with self.store.transaction() as con:
            con.execute('CREATE TABLE IF NOT EXISTS native_generation_results (generation_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,created_at TEXT NOT NULL)')
            con.execute('CREATE TABLE IF NOT EXISTS native_generation_imports (generation_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,request_sha256 TEXT NOT NULL,key_sha256 TEXT NOT NULL,receipt_json TEXT NOT NULL,receipt_sha256 TEXT NOT NULL,created_at TEXT NOT NULL)')

    def result(self,con,project,identity,*,physical=True):
        job=self.queue.read(self.queue.row(con,project,identity))
        row=con.execute('SELECT * FROM native_generation_results WHERE generation_id=? AND workspace_id=? AND project_id=?',(identity,self.queue.workspace,project)).fetchone()
        if row is None:raise WorkflowError('NATIVE_GENERATION_RESULT_NOT_READY',404)
        stage=self.media.read(con,project,identity,physical=physical)
        try:
            value=json.loads(row['result_json']);original=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(job['cost_operation_id'],)).fetchone()
            if (digest(value)!=row['result_sha256'] or job['status']!='succeeded' or value.get('schema_version')!='native-generation-result-v1'
                or value.get('generation_id')!=identity or value.get('workspace_id')!=self.queue.workspace or value.get('project_id')!=project
                or value.get('request_fingerprint')!=job['request_fingerprint'] or value.get('provider_job_id')!=job['provider_job_id']
                or value.get('stage_receipt_sha256')!=digest(stage) or value.get('asset_id')!=stage['asset']['id'] or value.get('asset_sha256')!=stage['asset']['sha256']
                or value.get('provider_payload_sha256')!=stage['provider_payload_sha256'] or value.get('original_cost_operation_id')!=job['cost_operation_id']
                or value.get('mode') not in {'create','reconcile','local_stage_recovery'} or value.get('actual_cost_vnd') is not None or value.get('rights_status')!='unknown'
                or value.get('production_eligible') is not False or value.get('rights_independently_verified') is not False or value.get('real_provider_tested') is not False
                or value.get('automatic_attachment') is not False or value.get('canonical_timeline_mutated') is not False or value.get('fixture')!=(job['snapshot']['selection']['mode']=='fixture')
                or original is None or original['project_id']!=project or original['request_sha256']!=job['request_fingerprint']
                or original['operation']!='generation.'+identity+'.submit' or original['provider']!=job['snapshot']['selection']['provider']
                or original['model']!='workflow:'+job['snapshot']['selection']['workflow_id'] or original['status'] not in {'response_received','outcome_unknown'}
                or bool(original['paid'])!=(job['snapshot']['selection']['mode']=='official') or not original['external_call']
                or type(value.get('recovery_count')) is not int or value['recovery_count']!=job['recovery_count'] or original['actual_cost'] is not None):raise ValueError()
            operation=value.get('result_cost_operation_id')
            if value['mode']=='create':
                if (operation!=job['cost_operation_id'] or original['status']!='response_received' or value['recovery_count']!=0
                    or json.loads(original['receipt'])['provider_response_sha256']!=digest(stage)):raise ValueError()
            elif value['mode']=='local_stage_recovery':
                if operation is not None or value['recovery_count']<1:raise ValueError()
            else:
                read=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(operation,)).fetchone()
                if (read is None or read['project_id']!=project or read['provider']!=job['snapshot']['selection']['provider']
                    or read['request_sha256']!=job['request_fingerprint'] or read['operation']!='generation.'+identity+'.reconcile.'+str(value['recovery_count'])
                    or read['model']!='workflow:'+job['snapshot']['selection']['workflow_id'] or read['paid'] or not read['external_call'] or read['status']!='response_received'
                    or read['actual_cost'] is not None or value['recovery_count']<1 or json.loads(read['receipt'])['provider_response_sha256']!=digest(stage)):raise ValueError()
        except (ValueError,KeyError,TypeError):raise WorkflowError('NATIVE_GENERATION_RESULT_INVALID') from None
        return value,stage

    def get(self,project,identity,*,physical=True):
        with self.store.transaction() as con:
            job=self.queue.read(self.queue.row(con,project,identity));result=None
            if job['status']=='succeeded':result,stage=self.result(con,project,identity,physical=physical);result={**result,'asset':stage['asset']}
            return {**job,'worker_wired':True,'result':result}

    def page(self,project,*,limit=25):
        page=self.queue.page(project,limit=limit)
        return {**page,'items':[self.get(project,j['generation_id'],physical=False) for j in page['items']]}

    def finish(self,claim,operation,*,mode):
        with self.store.transaction() as con:
            row=self.queue.fenced(con,claim);job=self.queue.read(row);stage=self.media.read(con,row['project_id'],row['generation_id'])
            if mode!=claim['mode'] and not (mode=='local_stage_recovery' and claim['mode']=='reconcile'):raise WorkflowError('NATIVE_GENERATION_FINISH_MODE_INVALID')
            receipt={'schema_version':'native-generation-result-v1','generation_id':row['generation_id'],'workspace_id':self.queue.workspace,'project_id':row['project_id'],
                'request_fingerprint':row['request_fingerprint'],'provider_job_id':row['provider_job_id'],'stage_receipt_sha256':digest(stage),
                'asset_id':stage['asset']['id'],'asset_sha256':stage['asset']['sha256'],'provider_payload_sha256':stage['provider_payload_sha256'],
                'original_cost_operation_id':row['cost_operation_id'],'result_cost_operation_id':operation,'mode':mode,'recovery_count':row['recovery_count'],
                'actual_cost_vnd':None,'rights_status':'unknown','production_eligible':False,'rights_independently_verified':False,'real_provider_tested':False,
                'fixture':job['snapshot']['selection']['mode']=='fixture','automatic_attachment':False,'canonical_timeline_mutated':False,'created_at':now()}
            con.execute('INSERT INTO native_generation_results VALUES(?,?,?,?,?,?)',(row['generation_id'],self.queue.workspace,row['project_id'],json.dumps(receipt),digest(receipt),now()))
            con.execute("UPDATE native_generation_jobs SET status='succeeded',phase='media_ready',claim_id=NULL,lease_until=NULL,failure_code=NULL,updated_at=? WHERE generation_id=? AND claim_id=?",
                (now(),row['generation_id'],claim['claim_id']))
            self.result(con,row['project_id'],row['generation_id']);self.queue.event(con,row,'generation.result.ready','native-generation-worker',
                asset_id=stage['asset']['id'],asset_sha256=stage['asset']['sha256'],mode=mode,rights_status='unknown',production_eligible=False)

    def cancel_requested(self,claim):
        if self.stop.is_set():raise WorkflowError('NATIVE_GENERATION_WORKER_INTERRUPTED')
        with self.store.transaction() as con:return bool(self.queue.fenced(con,claim)['cancel_requested'])

    async def execute(self,claim,payload):
        async def observe(value):self.queue.observe(claim,value)
        adapter=self.queue.factory.create(claim['job']['snapshot']['request']['parameters']['modality'],payload,
            on_job=observe,cancel_requested=lambda:self.cancel_requested(claim))
        with media_generation_scope(workspace_id=self.queue.workspace,project_id=claim['project_id'],job_id=claim['generation_id']):
            call=adapter.generate(payload) if claim['mode']=='create' else adapter.reconcile(payload,provider_job_id=claim['job']['provider_job_id'])
            return await asyncio.wait_for(call,timeout=660)

    def process(self):
        claim=self.queue.claim()
        if claim is None:return None
        operation=None;attempted=False;reference_operation=None;reference_attempted=False;job=claim['job'];identity=claim['generation_id'];failure=None
        try:
            if claim['mode']=='reconcile':
                with self.store.transaction() as con:
                    staged=con.execute('SELECT 1 FROM native_generation_media WHERE generation_id=?',(identity,)).fetchone()
                if staged:
                    self.finish(claim,None,mode='local_stage_recovery');return identity
                modality=job['snapshot']['request']['parameters']['modality'];payload=(ImageGenerationInput if modality=='image' else VideoGenerationInput).model_validate(job['provider_input'])
            else:
                if self.cancel_requested(claim):raise WorkflowError('NATIVE_GENERATION_CANCELLED_BEFORE_DISPATCH')
                if job['snapshot']['references']['sources']:
                    reference_operation=self.queue.costs.begin(project_id=claim['project_id'],provider=job['snapshot']['selection']['provider'],model='scoped-reference-intake.v1',
                        operation='generation.'+identity+'.reference-intake',request_sha256=job['request_fingerprint'],estimated_cost=None,external_call=True,paid=False)
                    reference_attempted=True
                payload=asyncio.run(asyncio.wait_for(self.queue.references.stage(identity,job['snapshot']['references'],self.queue.factory),timeout=420))
                if reference_operation:self.queue.costs.settle(reference_operation,status='response_received',actual_cost=None,response_sha256=digest(payload.model_dump(mode='json')))
                self.queue.bind_input(claim,payload)
            if self.cancel_requested(claim) and claim['mode']=='create':raise WorkflowError('NATIVE_GENERATION_CANCELLED_BEFORE_DISPATCH')
            self.queue.renew(claim)
            operation=self.queue.costs.begin(project_id=claim['project_id'],provider=job['snapshot']['selection']['provider'],model='workflow:'+job['snapshot']['selection']['workflow_id'],
                operation='generation.'+identity+('.submit' if claim['mode']=='create' else '.reconcile.'+str(job['recovery_count'])),
                request_sha256=job['request_fingerprint'],estimated_cost=None,external_call=True,paid=claim['mode']=='create' and job['snapshot']['selection']['mode']=='official')
            if claim['mode']=='create':self.queue.mark_dispatch(claim,operation)
            attempted=True;output=asyncio.run(self.execute(claim,payload));stage=self.media.register(claim,output)
            self.queue.costs.settle(operation,status='response_received',actual_cost=None,response_sha256=digest(stage));self.finish(claim,operation,mode=claim['mode'])
        except WorkflowError as error:failure=error.code
        except TimeoutError:failure='NATIVE_GENERATION_PROVIDER_TIMEOUT'
        except Exception:failure='NATIVE_GENERATION_PROVIDER_OUTCOME_UNKNOWN'
        if failure:
            for cost,touched in [(reference_operation,reference_attempted),(operation,attempted)]:
                if cost:
                    try:self.queue.costs.settle(cost,status='outcome_unknown' if touched else 'rejected',error_code=failure)
                    except WorkflowError:pass # Never rewrite an immutable receipt.
            try:self.queue.fail(claim,failure,needs_approval=failure=='AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH')
            except WorkflowError:pass # Expired claims cannot mutate newer state.
        return identity

    def asset_file(self,project,identity):
        with self.store.transaction() as con:
            _,stage=self.result(con,project,identity);asset=stage['asset'];return guard(self.store.root/'assets'/asset['id'],exists=True),asset

    def attach(self,project,identity,payload,*,actor):
        if type(payload) is not GenerationImport or not payload.acknowledged:raise WorkflowError('NATIVE_GENERATION_IMPORT_ACK_REQUIRED',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fingerprint=digest(request)
        with self.store.transaction() as con:
            row=self.queue.row(con,project,identity);result,stage=self.result(con,project,identity);asset=stage['asset']
            if payload.expected_fingerprint!=row['request_fingerprint'] or payload.expected_asset_sha256!=asset['sha256']:raise WorkflowError('NATIVE_GENERATION_IMPORT_BINDING_CHANGED')
            old=con.execute('SELECT * FROM native_generation_imports WHERE generation_id=?',(identity,)).fetchone()
            if old:
                receipt=json.loads(old['receipt_json']);version=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project,receipt.get('revision'))).fetchone()
                if (old['workspace_id']!=self.queue.workspace or old['project_id']!=project or old['key_sha256']!=key or old['request_sha256']!=fingerprint
                    or digest(receipt)!=old['receipt_sha256'] or receipt.get('schema_version')!='native-generation-import-v1' or receipt.get('workspace_id')!=self.queue.workspace
                    or receipt.get('project_id')!=project or receipt.get('generation_id')!=identity or receipt.get('asset_id')!=asset['id'] or receipt.get('asset_sha256')!=asset['sha256']
                    or receipt.get('revision')!=payload.revision+1 or receipt.get('approval_invalidated') is not True or receipt.get('rights_independently_verified') is not False
                    or receipt.get('canonical_timeline_auto_edited') is not False or receipt.get('external_calls')!=0 or version is None
                    or digest(json.loads(version[0]))!=receipt.get('document_sha256') or asset not in json.loads(version[0]).get('assets',[])):
                    raise WorkflowError('NATIVE_GENERATION_IMPORT_RECEIPT_INVALID')
                return {**receipt,'idempotent_replay':True}
            self.store.append_media_in_transaction(con,project,payload.revision,deepcopy(asset));current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            receipt={'schema_version':'native-generation-import-v1','generation_id':identity,'workspace_id':self.queue.workspace,'project_id':project,
                'revision':current['revision'],'asset_id':asset['id'],'asset_sha256':asset['sha256'],'document_sha256':digest(current['document']),
                'approval_invalidated':True,'rights_independently_verified':False,'canonical_timeline_auto_edited':False,'external_calls':0,'actor_ref':actor,'idempotent_replay':False}
            con.execute('INSERT INTO native_generation_imports VALUES(?,?,?,?,?,?,?,?)',(identity,self.queue.workspace,project,fingerprint,key,json.dumps(receipt),digest(receipt),now()))
            self.queue.event(con,row,'generation.asset.attached',actor,asset_id=asset['id'],revision=current['revision'],rights_status='unknown',rights_verified=False);return receipt

    def start(self,observer):
        if self.worker is not None:raise WorkflowError('NATIVE_GENERATION_WORKER_ALREADY_STARTED')
        def work():
            while not self.stop.is_set():
                started=time.monotonic()
                try:
                    identity=self.process()
                    if identity is not None:
                        observer.emit('worker_step',stage='generation',provider='comfyui',duration=time.monotonic()-started,job_id=identity);continue
                except Exception:observer.emit('worker_failed',stage='generation',provider='comfyui',duration=time.monotonic()-started)
                self.wake.wait(1);self.wake.clear()
        self.worker=threading.Thread(target=work,daemon=True,name='native-independent-generation-worker');self.worker.start()

    def close(self):
        self.stop.set();self.wake.set()
        if self.worker is not None:self.worker.join(timeout=2)
