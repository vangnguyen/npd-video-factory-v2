"""Durable official stock selection/download; explicit attachment, default disabled.

Separate worker and owned SQLite state, no Agent Hub database or media queue
dependency. Metadata remains provider evidence, not independent legal clearance.
"""
import asyncio,base64,copy,hashlib,json,re,threading,time,uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit
from .backup import guard
from .contracts import WorkflowError,digest,file_sha
from .costs import CostLedger
from .media import ingest_media,discard_media
from .store import now
from .stock_models import StockSearch,StockDownload,StockImport
from .stock_registry import StockFactory
from app.media_intelligence_models import StockMediaCandidateRead
from app.media_intelligence_providers import MediaProviderNotConfigured,ProviderMaterializedMedia
from app.stock_media_providers import StockProviderFailure,stock_request_scope,PexelsStockMediaProvider,PixabayStockMediaProvider

VERSION='native-stock-job-v1';ID=re.compile(r'^nstk_[a-f0-9]{32}$')
STATUSES={'queued','running','retry_scheduled','succeeded','failed','not_configured','cancelled'}
PROVIDERS={'pexels':PexelsStockMediaProvider,'pixabay':PixabayStockMediaProvider}


class NativeStock:
    def __init__(self,store,config,*,workspace_id='wsp_native_local',factories=None,clock=time.time):
        self.store,self.config,self.workspace,self.clock=store,config,workspace_id,clock
        self.factories=dict(factories or {});self.stop=threading.Event();self.wake=threading.Event();self.worker=None
        if any(key not in PROVIDERS or type(value) is not StockFactory or value.key!=key for key,value in self.factories.items()):raise WorkflowError('NATIVE_STOCK_PROVIDER_CONFIGURATION_INVALID',400)
        self.cache_scope=digest({'workspace':workspace_id,'root':str(store.root.resolve())});self.costs=CostLedger(store)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_stock_bindings (name TEXT PRIMARY KEY,workspace_id TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_stock_jobs (stock_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                kind TEXT NOT NULL,request_fingerprint TEXT NOT NULL,key_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
                status TEXT NOT NULL,attempts INTEGER NOT NULL,claim_id TEXT,lease_until REAL,next_at REAL,result_json TEXT,result_sha256 TEXT,
                failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_stock_imports (stock_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,key_sha256 TEXT NOT NULL,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_stock_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT,stock_id TEXT NOT NULL,
                project_id TEXT NOT NULL,action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);''')
            binding=con.execute("SELECT workspace_id FROM native_stock_bindings WHERE name='workspace'").fetchone()
            if ((binding and binding[0]!=workspace_id) or con.execute('SELECT 1 FROM native_stock_jobs WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone()
                or con.execute('SELECT 1 FROM native_stock_imports WHERE workspace_id!=? LIMIT 1',(workspace_id,)).fetchone()):raise WorkflowError('NATIVE_STOCK_WORKSPACE_MISMATCH',400)
            con.execute("INSERT OR IGNORE INTO native_stock_bindings VALUES('workspace',?)",(workspace_id,))

    def providers(self):
        return {'schema_version':'native-stock-providers-v1','workspace_id':self.workspace,'ui_enablement_supported':False,'automatic_attachment':False,
            'items':[{'provider':key,'status':'CONFIGURED' if (factory:=self.factories.get(key)) and factory.enabled else 'NOT_CONFIGURED',
                'mode':factory.mode if factory else 'official','configuration_sha256':factory.sha256 if factory else None,
                'license':adapter.license,'license_url':adapter.license_url,'independent_rights_verification':False} for key,adapter in PROVIDERS.items()]}

    def row(self,con,project,identity):
        value=con.execute('SELECT * FROM native_stock_jobs WHERE stock_id=? AND workspace_id=? AND project_id=?',(identity,self.workspace,project)).fetchone()
        if value is None:raise WorkflowError('NATIVE_STOCK_JOB_NOT_FOUND',404)
        return value

    def read(self,row):
        value=dict(row)
        try:snapshot=json.loads(value.pop('snapshot_json'));raw=value.pop('result_json');result=json.loads(raw) if raw else None
        except (ValueError,TypeError):raise WorkflowError('NATIVE_STOCK_SNAPSHOT_INVALID') from None
        if not isinstance(snapshot,dict) or (result is not None and not isinstance(result,dict)):raise WorkflowError('NATIVE_STOCK_RESULT_INVALID')
        if (not ID.fullmatch(value['stock_id']) or value['workspace_id']!=self.workspace or value['status'] not in STATUSES
            or digest(snapshot)!=value['snapshot_sha256'] or snapshot.get('schema_version')!='native-stock-snapshot-v1'
            or snapshot.get('workspace_id')!=self.workspace or snapshot.get('project_id')!=value['project_id']
            or snapshot.get('request_fingerprint')!=value['request_fingerprint'] or value['request_fingerprint']!=digest({'kind':value['kind'],**snapshot.get('request',{})})):
            raise WorkflowError('NATIVE_STOCK_SNAPSHOT_INVALID')
        try:({'search':StockSearch,'download':StockDownload}[value['kind']]).model_validate({**snapshot['request'],'request_key':'internal-stock-read-key'})
        except (KeyError,ValueError,TypeError):raise WorkflowError('NATIVE_STOCK_SNAPSHOT_INVALID') from None
        if (value['status']=='succeeded')!=(result is not None) or (result is not None and digest(result)!=value['result_sha256']):raise WorkflowError('NATIVE_STOCK_RESULT_INVALID')
        if result is not None:
            if (result.get('schema_version')!='native-stock-result-v1' or result.get('stock_id')!=value['stock_id']
                or result.get('workspace_id')!=self.workspace or result.get('project_id')!=value['project_id'] or result.get('kind')!=value['kind']
                or result.get('provider')!=snapshot['provider'] or result.get('mock')!=(snapshot['provider_mode']=='fixture')
                or result.get('canonical_timeline_mutated') is not False or result.get('automatic_attachment') is not False
                or result.get('paid_operations')!=0 or result.get('real_provider_acceptance_complete') is not False
                or type(result.get('actual_provider_calls')) is not int or result['actual_provider_calls']<0
                or (result['mock'] and result['actual_provider_calls']!=0)):raise WorkflowError('NATIVE_STOCK_RESULT_INVALID')
            if value['kind']=='search':
                candidates=result.get('candidates');seen=set()
                if not isinstance(candidates,list) or len(candidates)>snapshot['request']['limit'] or result.get('candidates_sha256')!=digest(candidates):raise WorkflowError('NATIVE_STOCK_CANDIDATES_INVALID')
                if result.get('candidate_sha256')!={item.get('candidate_id'):digest(item) for item in candidates if isinstance(item,dict)}:raise WorkflowError('NATIVE_STOCK_CANDIDATES_INVALID')
                for candidate in candidates:
                    try:item=StockMediaCandidateRead.model_validate(candidate)
                    except ValueError:raise WorkflowError('NATIVE_STOCK_CANDIDATES_INVALID') from None
                    adapter=PROVIDERS[snapshot['provider']];page=urlsplit(item.source_reference)
                    if (item.provider!=snapshot['provider'] or not re.fullmatch(r'smc_[a-f0-9]{24}',item.candidate_id) or item.candidate_id in seen
                        or item.media_type!=snapshot['request']['media_type'] or not re.fullmatch(item.media_type+r':[1-9][0-9]{0,11}',item.provider_asset_id)
                        or item.license!=adapter.license or item.license_url!=adapter.license_url or item.rights_status!='licensed' or item.production_eligible
                        or item.semantic_score is not None or item.vision_rerank_score is not None
                        or item.provenance.get('fixture')!=result['mock'] or item.provenance.get('real_provider_tested') is not False
                        or page.scheme!='https' or page.hostname not in {adapter.source_host,'www.'+adapter.source_host} or page.username or page.password):
                        raise WorkflowError('NATIVE_STOCK_CANDIDATES_INVALID')
                    seen.add(item.candidate_id)
            else:
                asset=result.get('asset',{});expected='unknown' if result['mock'] else 'licensed'
                if (not re.fullmatch(r'[a-f0-9]{32}\.(jpg|mp4)',asset.get('id','')) or not re.fullmatch(r'[a-f0-9]{64}',asset.get('sha256',''))
                    or asset.get('source_type')!='stock' or asset.get('provider')!=snapshot['provider'] or asset.get('rights_status')!=expected
                    or asset.get('production_eligible') is not False or asset.get('generation_provenance',{}).get('fixture')!=result['mock']
                    or asset.get('needs_attention') is not True or asset.get('source_sha256')!=result.get('download_payload_sha256')):raise WorkflowError('NATIVE_STOCK_ASSET_INVALID')
        value.pop('key_sha256');value.pop('claim_id');value.pop('lease_until')
        return {'schema_version':VERSION,**value,'snapshot':snapshot,'result':result,'attachment':None,'publish_enabled':False,'automatic_attachment':False}

    def projection(self,con,row):
        value=self.read(row);attached=con.execute('SELECT * FROM native_stock_imports WHERE stock_id=?',(row['stock_id'],)).fetchone()
        if attached:
            receipt=json.loads(attached['result_json']);asset=(value.get('result') or {}).get('asset',{})
            frozen=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(row['project_id'],receipt.get('revision'))).fetchone()
            if (digest(receipt)!=attached['result_sha256'] or attached['workspace_id']!=self.workspace or attached['project_id']!=row['project_id']
                or receipt.get('stock_id')!=row['stock_id'] or receipt.get('project_id')!=row['project_id'] or receipt.get('workspace_id')!=self.workspace
                or receipt.get('asset_id')!=asset.get('id') or receipt.get('asset_sha256')!=asset.get('sha256') or receipt.get('rights_independently_verified') is not False
                or receipt.get('approval_invalidated') is not True or receipt.get('external_calls')!=0
                or frozen is None or receipt.get('document_sha256')!=digest(json.loads(frozen[0]))):raise WorkflowError('NATIVE_STOCK_IMPORT_RECEIPT_INVALID')
            value['attachment']=receipt
        return value

    def get(self,project,identity):
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            return self.projection(con,self.row(con,project,identity))

    def page(self,project,*,limit=25,cursor=None):
        if type(limit) is not int or not 1<=limit<=100:raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400)
        after=None
        if cursor:
            try:
                if len(cursor)>512:raise ValueError()
                after=json.loads(base64.urlsafe_b64decode(cursor));assert len(after)==4 and after[:2]==[self.workspace,project] and ID.fullmatch(after[3]);datetime.fromisoformat(after[2])
            except (ValueError,TypeError,AssertionError):raise WorkflowError('NATIVE_STOCK_CURSOR_INVALID',400) from None
        with self.store.transaction() as con:
            self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            where='workspace_id=? AND project_id=?';params=[self.workspace,project]
            if after:where+=' AND (created_at<? OR (created_at=? AND stock_id<?))';params.extend([after[2],after[2],after[3]])
            rows=con.execute('SELECT * FROM native_stock_jobs WHERE '+where+' ORDER BY created_at DESC,stock_id DESC LIMIT ?',(*params,limit+1)).fetchall()
            following=base64.urlsafe_b64encode(json.dumps([self.workspace,project,rows[limit-1]['created_at'],rows[limit-1]['stock_id']]).encode()).decode() if len(rows)>limit else None
            return {'schema_version':'native-stock-page-v1','workspace_id':self.workspace,'project_id':project,'items':[self.projection(con,row) for row in rows[:limit]],'next_cursor':following,'automatic_attachment':False}

    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_stock_events(stock_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?)',
            (row['stock_id'],row['project_id'],action,actor,json.dumps(evidence),now()))

    def source(self,con,project,request):
        parent=self.read(self.row(con,project,request['search_id']))
        if parent['kind']!='search' or parent['status']!='succeeded' or parent['result_sha256']!=request['expected_result_sha256']:raise WorkflowError('NATIVE_STOCK_SELECTION_CHANGED')
        candidate=next((item for item in parent['result']['candidates'] if item['candidate_id']==request['candidate_id']),None)
        if candidate is None or digest(candidate)!=request['expected_candidate_sha256']:raise WorkflowError('NATIVE_STOCK_SELECTION_CHANGED')
        return parent,candidate

    def create(self,project,payload,*,actor):
        kind='search' if type(payload) is StockSearch else 'download' if type(payload) is StockDownload else None
        if kind is None or not isinstance(actor,str) or not 1<=len(actor)<=100:raise WorkflowError('NATIVE_STOCK_REQUEST_INVALID',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest()
        if kind=='search':
            request['query']=' '.join(request['query'].split())
            if not request['query']:raise WorkflowError('NATIVE_STOCK_REQUEST_INVALID',400)
        fingerprint=digest({'kind':kind,**request})
        with self.store.transaction() as con:
            old=con.execute('SELECT * FROM native_stock_jobs WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if old:
                if old['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_STOCK_IDEMPOTENCY_CONFLICT')
                return self.read(old),True
            current=self.store.editable(con,project,payload.revision);candidate=None;parent=None
            if kind=='download':parent,candidate=self.source(con,project,request);provider=parent['snapshot']['provider']
            else:provider=request['provider']
            factory=self.factories.get(provider);mode=factory.mode if factory else 'official'
            if request['external_acknowledged']!=(mode=='official') or request['fixture_acknowledged']!=(mode=='fixture'):raise WorkflowError('NATIVE_STOCK_SOURCE_ACK_REQUIRED',400)
            if parent and factory and parent['snapshot']['provider_configuration_sha256']!=factory.sha256:raise WorkflowError('NATIVE_STOCK_PROVIDER_CONFIGURATION_CHANGED')
            if con.execute('SELECT count(*) FROM native_stock_jobs WHERE workspace_id=? AND project_id=?',(self.workspace,project)).fetchone()[0]>=200:raise WorkflowError('NATIVE_STOCK_HISTORY_LIMIT')
            identity='nstk_'+uuid.uuid4().hex;stamp=now();snapshot={'schema_version':'native-stock-snapshot-v1','workspace_id':self.workspace,'project_id':project,
                'document_sha256':digest(current['document']),'request':request,'request_fingerprint':fingerprint,'provider':provider,'provider_mode':mode,
                'provider_configuration_sha256':factory.sha256 if factory else None,'cache_scope_sha256':self.cache_scope,'source_candidate':candidate}
            status='queued' if factory and factory.enabled else 'not_configured'
            con.execute('INSERT INTO native_stock_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (identity,self.workspace,project,kind,fingerprint,key,json.dumps(snapshot,ensure_ascii=False),digest(snapshot),status,0,None,None,None,None,None,None,stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'stock.request.created',actor,status=status,kind=kind,provider=provider,mode=mode,external_call=False)
            value=self.read(row)
        self.wake.set();return value,False

    def cancel(self,project,identity,*,fingerprint,actor):
        with self.store.transaction() as con:
            row=self.row(con,project,identity);self.read(row)
            if row['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_STOCK_BINDING_CHANGED')
            if row['status']=='cancelled':return self.read(row)
            if row['status'] not in ('queued','retry_scheduled'):raise WorkflowError('NATIVE_STOCK_CANCEL_STATE_INVALID')
            con.execute("UPDATE native_stock_jobs SET status='cancelled',next_at=NULL,updated_at=? WHERE stock_id=?",(now(),identity))
            self.event(con,row,'stock.request.cancelled',actor,external_call=False);return self.read(self.row(con,project,identity))

    async def call(self,adapter,kind,request,candidate,counter):
        async def count(_request):counter['wire_attempts']+=1
        adapter._http().event_hooks['request'].append(count)
        try:
            with stock_request_scope(self.cache_scope):
                async with asyncio.timeout(35):
                    if kind=='search':return await (adapter.search_images if request['media_type']=='image' else adapter.search_videos)(request['query'],orientation=request['orientation'],limit=request['limit'])
                    return await adapter.download_asset(StockMediaCandidateRead.model_validate(candidate))
        finally:await adapter.aclose()

    def process(self):
        if self.stop.is_set():return None
        with self.store.transaction() as con:
            for old in con.execute("SELECT * FROM native_stock_jobs WHERE workspace_id=? AND status='running' AND lease_until<=?",(self.workspace,self.clock())).fetchall():
                self.read(old);con.execute('UPDATE native_stock_jobs SET status=?,claim_id=NULL,lease_until=NULL,next_at=?,failure_code=?,updated_at=? WHERE stock_id=?',
                    ('retry_scheduled' if old['attempts']<3 else 'failed',self.clock()+5 if old['attempts']<3 else None,'NATIVE_STOCK_WORKER_INTERRUPTED',now(),old['stock_id']))
                self.event(con,old,'stock.request.interrupted','native-stock-worker',attempt=old['attempts'],external_outcome_unknown=True)
            row=con.execute("SELECT * FROM native_stock_jobs WHERE workspace_id=? AND (status='queued' OR (status='retry_scheduled' AND next_at<=?)) ORDER BY created_at,stock_id LIMIT 1",(self.workspace,self.clock())).fetchone()
            if row is None:return None
            value=self.read(row);snapshot=value['snapshot'];claim=uuid.uuid4().hex;attempt=row['attempts']+1
            con.execute("UPDATE native_stock_jobs SET status='running',attempts=?,claim_id=?,lease_until=?,next_at=NULL,updated_at=? WHERE stock_id=?",(attempt,claim,self.clock()+600,now(),row['stock_id']))
            self.event(con,row,'stock.request.claimed','native-stock-worker',attempt=attempt)
        result=None;asset=None;operation=None;failure=None;retryable=False;delay=5*2**(attempt-1);counter={'wire_attempts':0}
        try:
            factory=self.factories.get(snapshot['provider'])
            if factory is None or not factory.enabled:raise MediaProviderNotConfigured()
            if factory.sha256!=snapshot['provider_configuration_sha256'] or snapshot['cache_scope_sha256']!=self.cache_scope:raise WorkflowError('NATIVE_STOCK_PROVIDER_CONFIGURATION_CHANGED')
            with self.store.transaction() as con:
                current=self.store.editable(con,row['project_id'],snapshot['request']['revision'])
                if digest(current['document'])!=snapshot['document_sha256']:raise WorkflowError('NATIVE_STOCK_PROJECT_CHANGED')
                if row['kind']=='download':
                    _,source=self.source(con,row['project_id'],snapshot['request'])
                    if source!=snapshot['source_candidate']:raise WorkflowError('NATIVE_STOCK_SELECTION_CHANGED')
            operation=self.costs.begin(project_id=row['project_id'],provider=snapshot['provider'],model='stock-api.v1',
                operation='stock.'+row['kind']+'.'+row['stock_id']+'.'+str(attempt),request_sha256=row['request_fingerprint'],estimated_cost=0,external_call=True,paid=False)
            adapter=factory.create(self.store.root,self.cache_scope)
            output=asyncio.run(self.call(adapter,row['kind'],snapshot['request'],snapshot['source_candidate'],counter))
            mock=snapshot['provider_mode']=='fixture'
            result={'schema_version':'native-stock-result-v1','stock_id':row['stock_id'],'workspace_id':self.workspace,'project_id':row['project_id'],
                'kind':row['kind'],'provider':snapshot['provider'],'mock':mock,'actual_provider_calls':0 if mock else counter['wire_attempts'],
                'fixture_wire_attempts':counter['wire_attempts'] if mock else 0,'paid_operations':0,'real_provider_acceptance_complete':False,
                'canonical_timeline_mutated':False,'automatic_attachment':False,'cost_operation_id':operation,'actual_billed_cost_vnd':None}
            if row['kind']=='search':
                candidates=[candidate.model_dump(mode='json') for candidate in output];result.update(candidates=candidates,candidates_sha256=digest(candidates),
                    candidate_sha256={candidate['candidate_id']:digest(candidate) for candidate in candidates})
            else:
                if type(output) is not ProviderMaterializedMedia or output.source_type!='stock' or output.production_eligible or output.paid:raise WorkflowError('NATIVE_STOCK_PROVIDER_RESULT_INVALID')
                folder=guard(self.store.root/'stock-work'/row['stock_id']);folder.mkdir(parents=True,exist_ok=True)
                path=guard(folder/(claim+'.media'));path.write_bytes(output.payload)
                try:
                    for directory in ['assets','originals']:guard(self.store.root/directory)
                    asset=ingest_media(self.config,path,output.content_type,output.filename,rights_confirmed=True,illustration=False)
                finally:path.unlink(missing_ok=True)
                asset.update(source_type='stock',source='official-stock-api' if not mock else 'explicit-stock-api-fixture',
                    rights_status='unknown' if mock else 'licensed',license=output.license,license_url=output.license_url,provider=snapshot['provider'],
                    provider_asset_id=output.provider_asset_id,source_reference=output.source_reference,creator=output.creator,
                    attribution_requirement=output.attribution_requirement,generation_provenance=output.generation_provenance,
                    production_eligible=False,needs_attention=True,independent_rights_verification=False)
                result.update(asset=asset,download_payload_sha256=hashlib.sha256(output.payload).hexdigest(),
                    provider_metadata={'width':output.width,'height':output.height,'duration_seconds':output.duration_seconds,'orientation':output.orientation},
                    full_native_media_validation_passed=True)
            self.costs.settle(operation,status='response_received',actual_cost=None,response_sha256=digest(result))
        except MediaProviderNotConfigured:failure='NATIVE_STOCK_NOT_CONFIGURED'
        except StockProviderFailure as error:failure=error.code;retryable=error.retryable;delay=max(delay,error.retry_after_seconds or 0)
        except WorkflowError as error:failure=error.code
        except TimeoutError:failure='NATIVE_STOCK_TIMEOUT';retryable=True
        except Exception:failure='NATIVE_STOCK_PROVIDER_FAILED'
        if failure and operation:
            try:self.costs.settle(operation,status='outcome_unknown' if counter['wire_attempts'] else 'rejected',error_code=failure)
            except WorkflowError:pass
        committed=False
        try:
            with self.store.transaction() as con:
                current=self.row(con,row['project_id'],row['stock_id'])
                if current['claim_id']!=claim or current['status']!='running':return row['stock_id']
                if self.stop.is_set():failure='NATIVE_STOCK_WORKER_INTERRUPTED';retryable=True
                status='not_configured' if failure=='NATIVE_STOCK_NOT_CONFIGURED' else 'retry_scheduled' if failure and retryable and attempt<3 else 'failed' if failure else 'succeeded'
                next_at=self.clock()+min(3600,delay) if status=='retry_scheduled' else None
                result=None if failure else result
                con.execute('UPDATE native_stock_jobs SET status=?,claim_id=NULL,lease_until=NULL,next_at=?,result_json=?,result_sha256=?,failure_code=?,updated_at=? WHERE stock_id=? AND claim_id=?',
                    (status,next_at,json.dumps(result,ensure_ascii=False) if result is not None else None,digest(result) if result is not None else None,failure,now(),row['stock_id'],claim))
                checked=self.read(self.row(con,row['project_id'],row['stock_id']))
                self.event(con,current,'stock.request.'+status,'native-stock-worker',attempt=attempt,failure_code=failure,
                    actual_provider_calls=0 if snapshot['provider_mode']=='fixture' else counter['wire_attempts'],fixture=snapshot['provider_mode']=='fixture')
                committed=checked['status']=='succeeded'
        finally:
            if asset is not None and not committed:discard_media(self.config,asset)
        return row['stock_id']

    def asset_file(self,project,identity):
        value=self.get(project,identity)
        if value['kind']!='download' or value['status']!='succeeded':raise WorkflowError('NATIVE_STOCK_ASSET_NOT_READY')
        asset=value['result']['asset'];path=guard(self.store.root/'assets'/asset['id'],exists=True)
        original=guard(self.store.root/'originals'/asset['original_id'],exists=True)
        if file_sha(path)!=asset['sha256'] or file_sha(original)!=asset['source_sha256']:raise WorkflowError('NATIVE_STOCK_ASSET_CHANGED')
        return path,asset

    def attach(self,project,identity,payload,*,actor):
        if type(payload) is not StockImport or not payload.acknowledged:raise WorkflowError('NATIVE_STOCK_IMPORT_ACK_REQUIRED',400)
        request=payload.model_dump(mode='json');key=hashlib.sha256(request.pop('request_key').encode()).hexdigest();fingerprint=digest(request)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row)
            old=con.execute('SELECT * FROM native_stock_imports WHERE stock_id=?',(identity,)).fetchone()
            if old:
                receipt=json.loads(old['result_json'])
                if old['workspace_id']!=self.workspace or old['project_id']!=project or old['key_sha256']!=key or old['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_STOCK_IMPORT_CONFLICT')
                frozen=con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?',(project,receipt.get('revision'))).fetchone()
                asset=value.get('result',{}).get('asset',{})
                if (digest(receipt)!=old['result_sha256'] or frozen is None or digest(json.loads(frozen[0]))!=receipt.get('document_sha256')
                    or receipt.get('schema_version')!='native-stock-import-v1' or receipt.get('workspace_id')!=self.workspace or receipt.get('project_id')!=project
                    or receipt.get('stock_id')!=identity or receipt.get('asset_id')!=asset.get('id') or receipt.get('asset_sha256')!=payload.expected_asset_sha256
                    or receipt.get('revision')!=payload.revision+1 or receipt.get('approval_invalidated') is not True or receipt.get('external_calls')!=0
                    or receipt.get('rights_independently_verified') is not False or receipt.get('canonical_timeline_auto_edited') is not False):raise WorkflowError('NATIVE_STOCK_IMPORT_RECEIPT_INVALID')
                return {**receipt,'idempotent_replay':True}
            if value['kind']!='download' or value['status']!='succeeded' or payload.expected_fingerprint!=row['request_fingerprint']:raise WorkflowError('NATIVE_STOCK_IMPORT_BINDING_CHANGED')
            # Validate the physical source/normalized bytes before any project
            # mutation. No URL, license or provider field comes from this DTO.
            asset=value['result']['asset'];path=guard(self.store.root/'assets'/asset['id'],exists=True);original=guard(self.store.root/'originals'/asset['original_id'],exists=True)
            if asset['sha256']!=payload.expected_asset_sha256 or file_sha(path)!=asset['sha256'] or file_sha(original)!=asset['source_sha256']:raise WorkflowError('NATIVE_STOCK_ASSET_CHANGED')
            self.store.append_media_in_transaction(con,project,payload.revision,copy.deepcopy(asset))
            current=self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
            receipt={'schema_version':'native-stock-import-v1','stock_id':identity,'workspace_id':self.workspace,'project_id':project,'revision':current['revision'],
                'asset_id':asset['id'],'asset_sha256':asset['sha256'],'document_sha256':digest(current['document']),'approval_invalidated':True,
                'canonical_timeline_auto_edited':False,'rights_independently_verified':False,'external_calls':0,'actor_ref':actor,'idempotent_replay':False}
            con.execute('INSERT INTO native_stock_imports VALUES(?,?,?,?,?,?,?,?)',(identity,self.workspace,project,fingerprint,key,json.dumps(receipt),digest(receipt),now()))
            self.event(con,row,'stock.asset.attached',actor,asset_id=asset['id'],revision=current['revision'],rights_verified=False)
            return receipt

    def start(self,observer):
        def work():
            while not self.stop.is_set():
                try:
                    if self.process() is not None:continue
                except Exception:observer.emit('worker_failed',stage='stock',duration=0)
                self.wake.wait(1);self.wake.clear()
        self.worker=threading.Thread(target=work,daemon=True,name='native-independent-stock-worker');self.worker.start()

    def close(self):
        self.stop.set();self.wake.set()
        if self.worker is not None:self.worker.join(timeout=2)
