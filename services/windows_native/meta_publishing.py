"""Versioned Meta job evidence in the existing Owner/dispatch/cost journals.

Legacy v1 reviews remain inert. This module never contacts a provider.
"""
import hashlib,json,re,uuid
from dataclasses import dataclass
from datetime import datetime,timedelta
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator
from app.models import StrictModel
from app.publishing_models import PublicationReceipt
from app.meta_publishing_protocol import numeric_id
from .contracts import WorkflowError,digest
from .official_publications import utc,CONSENT_REVOKED
from .official_publication_models import Renew
from .store import now
from .publishing_media_delivery import NativePublishingMediaDelivery

PHASES={'prepared','meta_init_intent','meta_init_unconfirmed','meta_created','meta_transfer_intent','meta_transfer_unconfirmed',
    'meta_processing','meta_finish_ready','meta_finish_intent','meta_finish_unconfirmed','meta_status_intent','uploaded','review_required'}
OPS={'meta_init','meta_transfer','meta_finish','meta_status'}

class MediaBind(StrictModel):
    expected_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_dispatch_version:StrictInt=Field(ge=1)
    media_delivery_id:str=Field(pattern=r'^nmd_[a-f0-9]{32}$')
    expected_media_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    acknowledged_exact_media_selection:Literal[True]
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_exact_media_selection',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Exact media selection required')
        return value

class Outcome(StrictModel):
    schema_version:Literal['native-official-meta-operation-outcome-v1']='native-official-meta-operation-outcome-v1'
    operation:Literal['meta_init','meta_transfer','meta_finish','meta_status']
    provider_job_id:str|None=Field(default=None,pattern=r'^[1-9][0-9]{0,31}$')
    remote_post_id:str|None=Field(default=None,pattern=r'^[1-9][0-9]{0,31}$')
    operation_confirmed:StrictBool=False
    provider_status:str|None=Field(default=None,pattern=r'^[A-Za-z_]{1,32}$')
    uploading_phase:str|None=Field(default=None,pattern=r'^[a-z_]{1,32}$')
    processing_phase:str|None=Field(default=None,pattern=r'^[a-z_]{1,32}$')
    publishing_phase:str|None=Field(default=None,pattern=r'^[a-z_]{1,32}$')
    processing_progress:StrictInt|None=Field(default=None,ge=0,le=100)
    error_code:str|None=Field(default=None,pattern=r'^[A-Z0-9_]{1,120}$')
    mock:StrictBool

@dataclass(frozen=True)
class Ticket:
    publication_id:str
    workspace_id:str
    project_id:str
    snapshot_sha256:str
    approval_id:str
    version:int
    intent_id:str
    operation:str

def ensure(journal):
    with journal.store.transaction() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS native_official_meta_media_bindings (
            binding_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,key_sha256 TEXT NOT NULL,request_sha256 TEXT NOT NULL,binding_json TEXT NOT NULL,binding_sha256 TEXT NOT NULL,
            created_at TEXT NOT NULL,UNIQUE(publication_id,key_sha256));
            CREATE TABLE IF NOT EXISTS native_official_meta_preflights (
            proof_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
            snapshot_sha256 TEXT NOT NULL,proof_json TEXT NOT NULL,proof_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS native_official_meta_responses (
            intent_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
            response_sha256 TEXT,result_json TEXT NOT NULL,result_sha256 TEXT NOT NULL,created_at TEXT NOT NULL,retry_not_before TEXT);
            CREATE UNIQUE INDEX IF NOT EXISTS native_official_meta_one_init ON native_official_publish_intents(publication_id) WHERE operation='meta_init';
            CREATE UNIQUE INDEX IF NOT EXISTS native_official_meta_one_transfer ON native_official_publish_intents(publication_id) WHERE operation='meta_transfer';
            CREATE UNIQUE INDEX IF NOT EXISTS native_official_meta_one_finish ON native_official_publish_intents(publication_id) WHERE operation='meta_finish';''')

def scoped(row,value):
    if row is None or any(row[k]!=value[k] for k in ('publication_id','workspace_id','project_id')) or 'snapshot_sha256' in row.keys() and row['snapshot_sha256']!=value['snapshot_sha256']:
        raise WorkflowError('NATIVE_META_PUBLISH_EVIDENCE_SCOPE_CHANGED')

def original_grant(con,value,approval,instant):
    row=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=?',(approval,value['publication_id'])).fetchone();scoped(row,value)
    try:
        grant=json.loads(row['grant_json'])
        if (digest(grant)!=row['grant_sha256'] or any(grant[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256'))
            or grant['mock'] is not value['mock'] or grant['acknowledged_official_publication'] is not True or grant['dry_run_approval_reused'] is not False
            or not utc(datetime.fromisoformat(grant['issued_at']))<=utc(datetime.fromisoformat(instant))<utc(datetime.fromisoformat(grant['expires_at']))):raise ValueError()
    except Exception:raise WorkflowError('NATIVE_META_PUBLISH_ORIGINAL_GRANT_CHANGED') from None
    return grant

def read_binding(journal,con,value,row):
    scoped(row,value)
    try:
        b=json.loads(row['binding_json']);request=MediaBind.model_validate({**b['request'],'request_key':'internal-exact-meta-media-key'})
        if (set(b)!={'schema_version','binding_id','publication_id','workspace_id','project_id','snapshot_sha256','request','approval_id','media_result_sha256','mock','bound_at'}
            or b['schema_version']!='native-official-meta-media-binding-v1' or digest(b)!=row['binding_sha256']
            or b['binding_id']!=row['binding_id'] or any(b[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256'))
            or b['request']!=request.model_dump(mode='json',exclude={'request_key'}) or digest(b['request'])!=row['request_sha256']
            or request.expected_snapshot_sha256!=value['snapshot_sha256'] or b['mock'] is not value['mock'] or b['bound_at']!=row['created_at']):raise ValueError()
        original_grant(con,value,b['approval_id'],b['bound_at'])
        media=NativePublishingMediaDelivery.history(journal,value['project_id'],request.media_delivery_id,con=con)
        s=media['snapshot'];scope=s['scope'];final=value['snapshot']
        if (media['status']!='succeeded' or media['snapshot_sha256']!=request.expected_media_snapshot_sha256 or media['result_sha256']!=b['media_result_sha256']
            or s['mock'] is not value['mock'] or s['configuration_sha256']!=final['media_configuration_sha256']
            or scope['publication_id']!=value['publication_id'] or scope['publication_snapshot_sha256']!=value['snapshot_sha256']
            or any(scope[k]!=final[k] for k in ('final_job_id','final_sha256')) or scope['size_bytes']!=final['final_bytes']):raise ValueError()
        return {'binding':b,'sha256':row['binding_sha256'],'media':media}
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_META_MEDIA_BINDING_CHANGED') from None

def binding(journal,con,value):
    row=con.execute('SELECT * FROM native_official_meta_media_bindings WHERE publication_id=? ORDER BY rowid DESC LIMIT 1',(value['publication_id'],)).fetchone()
    return read_binding(journal,con,value,row) if row is not None else None

def bind_media(journal,media,project,identity,payload,*,principal):
    if type(payload) is not MediaBind or type(media) is not NativePublishingMediaDelivery or media.journal is not journal:raise WorkflowError('NATIVE_META_MEDIA_BINDING_INVALID',400)
    journal.identity(principal);payload=MediaBind.model_validate(payload.model_dump(mode='json'));request=payload.model_dump(mode='json',exclude={'request_key'})
    with journal.store.transaction() as con:
        value=journal.get(project,identity,con=con)
        prior=con.execute('SELECT * FROM native_official_meta_media_bindings WHERE publication_id=? AND key_sha256=?',(identity,digest(payload.request_key))).fetchone()
        if prior is not None:
            if prior['request_sha256']!=digest(request):raise WorkflowError('NATIVE_META_MEDIA_IDEMPOTENCY_CONFLICT')
            return read_binding(journal,con,value,prior),True
        value,_,_,dispatch=admission(journal,project,identity,con=con)
        if (value['snapshot_sha256']!=payload.expected_snapshot_sha256 or dispatch['version']!=payload.expected_dispatch_version
            or dispatch['phase'] not in {'prepared','meta_created'} or con.execute("SELECT 1 FROM native_official_publish_intents WHERE publication_id=? AND operation='meta_transfer'",(identity,)).fetchone()):raise WorkflowError('NATIVE_META_MEDIA_BINDING_STALE')
        delivery=media.get(project,payload.media_delivery_id,con=con);instant=utc(journal.clock()).isoformat();reference='nmb_'+uuid.uuid4().hex
        b={'schema_version':'native-official-meta-media-binding-v1','binding_id':reference,'publication_id':identity,'workspace_id':journal.workspace,'project_id':project,
            'snapshot_sha256':value['snapshot_sha256'],'request':request,'approval_id':value['approval_id'],'media_result_sha256':delivery['result_sha256'],'mock':value['mock'],'bound_at':instant}
        con.execute('INSERT INTO native_official_meta_media_bindings VALUES(?,?,?,?,?,?,?,?,?,?)',(reference,identity,journal.workspace,project,value['snapshot_sha256'],digest(payload.request_key),digest(request),json.dumps(b),digest(b),instant))
        result=read_binding(journal,con,value,con.execute('SELECT * FROM native_official_meta_media_bindings WHERE binding_id=?',(reference,)).fetchone())
        journal.event(con,journal.row(con,project,identity),'official.meta.media.selected',principal.token_id,binding_id=reference,media_snapshot_sha256=payload.expected_media_snapshot_sha256,url_returned=False)
        return result,False

def cost(con,value,identity,version,operation,body_sha,response_sha,*,intent_id=None):
    row=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(identity,)).fetchone()
    try:
        receipt=json.loads(row['receipt']);proof={'publication_id':value['publication_id'],'snapshot_sha256':value['snapshot_sha256'],'version':version,'operation':operation,'body_sha256':body_sha}
        if (row['project_id']!=value['project_id'] or row['provider']!='official-'+value['snapshot']['target']['platform'] or row['paid']!=0
            or row['job_id']!=value['snapshot']['final_job_id']
            or bool(row['external_call'])==value['mock'] or row['request_sha256']!=digest(proof) or row['status']!='response_received'
            or receipt['provider_response_sha256']!=response_sha or not re.fullmatch(re.escape(operation)+r'\.[a-f0-9]{32}',row['operation'])
            or intent_id is not None and row['operation']!=operation+'.'+intent_id
            or row['id']!=digest({'project':value['project_id'],'job':value['snapshot']['final_job_id'],'provider':row['provider'],'operation':row['operation']})):raise ValueError()
    except Exception:raise WorkflowError('NATIVE_META_PUBLISH_COST_EVIDENCE_CHANGED') from None

def record_preflight(journal,project,identity,version,reads):
    with journal.store.transaction() as con:
        value,_,_,dispatch=admission(journal,project,identity,con=con)
        if dispatch['version']!=version:raise WorkflowError('NATIVE_META_PUBLISH_WORKER_STALE')
        p={'schema_version':'native-official-meta-preflight-v1','proof_id':'nmpp_'+uuid.uuid4().hex,'publication_id':identity,'workspace_id':journal.workspace,'project_id':project,
            'snapshot_sha256':value['snapshot_sha256'],'approval_id':value['approval_id'],'dispatch_version':version,'target':value['snapshot']['target'],
            'account_match':True,'reads':reads,'mock':value['mock'],'observed_at':utc(journal.clock()).isoformat(),'publishing_authority':False}
        con.execute('INSERT INTO native_official_meta_preflights VALUES(?,?,?,?,?,?,?,?)',(p['proof_id'],identity,journal.workspace,project,value['snapshot_sha256'],json.dumps(p),digest(p),p['observed_at']))
        return read_preflight(con,value,p['proof_id'])

def read_preflight(con,value,identity):
    row=con.execute('SELECT * FROM native_official_meta_preflights WHERE proof_id=?',(identity,)).fetchone();scoped(row,value)
    try:
        p=json.loads(row['proof_json'])
        if (set(p)!={'schema_version','proof_id','publication_id','workspace_id','project_id','snapshot_sha256','approval_id','dispatch_version','target','account_match','reads','mock','observed_at','publishing_authority'}
            or p['schema_version']!='native-official-meta-preflight-v1' or digest(p)!=row['proof_sha256'] or p['proof_id']!=identity or p['target']!=value['snapshot']['target']
            or any(p[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256')) or p['mock'] is not value['mock'] or p['account_match'] is not True
            or p['publishing_authority'] is not False or type(p['dispatch_version']) is not int or p['observed_at']!=row['created_at']):raise ValueError()
        original_grant(con,value,p['approval_id'],p['observed_at'])
        expected=['meta_page_lookup']+(['meta_instagram_lookup'] if value['snapshot']['target']['platform']=='instagram_reels' else [])
        if [r['operation'] for r in p['reads']]!=expected:raise ValueError()
        for r in p['reads']:
            if set(r)!={'operation','cost_operation_id','response_sha256'}:raise ValueError()
            cost(con,value,r['cost_operation_id'],p['dispatch_version'],r['operation'],hashlib.sha256(b'').hexdigest(),r['response_sha256'])
        return {'proof':p,'sha256':row['proof_sha256']}
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_META_PUBLISH_PREFLIGHT_CHANGED') from None

def results(journal,con,value):
    output=[]
    for row in con.execute('SELECT r.* FROM native_official_meta_responses r JOIN native_official_publish_intents i ON i.intent_id=r.intent_id WHERE r.publication_id=? ORDER BY i.version',(value['publication_id'],)):
        scoped(row,value)
        try:
            data=json.loads(row['result_json']);out=Outcome.model_validate(data['outcome']);intent=con.execute('SELECT * FROM native_official_publish_intents WHERE intent_id=?',(row['intent_id'],)).fetchone();scoped(intent,value)
            if (set(data)!={'schema_version','outcome','cost_operation_id','approval_id','dispatch_version','body_sha256','binding_id','preflight_id','observed_at','mock'}
                or data['schema_version']!='native-official-meta-response-v1' or data['mock'] is not value['mock'] or out.mock is not value['mock']
                or out.model_dump(mode='json')!=data['outcome'] or digest(data)!=row['result_sha256'] or data['observed_at']!=row['created_at']
                or intent['operation']!=out.operation or intent['version']!=data['dispatch_version'] or intent['approval_id']!=data['approval_id']
                or intent['body_sha256']!=data['body_sha256'] or row['retry_not_before'] is not None
                or intent['status']!=('response_received' if row['response_sha256'] is not None else 'outcome_unknown')):raise ValueError()
            original_grant(con,value,data['approval_id'],intent['created_at'])
            if data['preflight_id'] is not None:
                preflight=read_preflight(con,value,data['preflight_id'])
                if preflight['proof']['dispatch_version']!=intent['version']-1 or preflight['proof']['approval_id']!=data['approval_id']:raise ValueError()
            elif out.operation!='meta_status':raise ValueError()
            if data['binding_id'] is not None:
                read_binding(journal,con,value,con.execute('SELECT * FROM native_official_meta_media_bindings WHERE binding_id=?',(data['binding_id'],)).fetchone())
            if row['response_sha256'] is not None:cost(con,value,data['cost_operation_id'],intent['version'],out.operation,data['body_sha256'],row['response_sha256'],intent_id=row['intent_id'])
            else:
                if out.operation_confirmed or out.remote_post_id is not None or out.error_code is None:raise ValueError()
                if data['cost_operation_id'] is not None:
                    record=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(data['cost_operation_id'],)).fetchone()
                    expected={'publication_id':value['publication_id'],'snapshot_sha256':value['snapshot_sha256'],'version':intent['version'],'operation':out.operation,'body_sha256':intent['body_sha256']}
                    if (record is None or record['project_id']!=value['project_id'] or record['job_id']!=value['snapshot']['final_job_id'] or record['provider']!='official-'+value['snapshot']['target']['platform']
                        or record['operation']!=out.operation+'.'+row['intent_id'] or record['request_sha256']!=digest(expected)
                        or record['id']!=digest({'project':value['project_id'],'job':value['snapshot']['final_job_id'],'provider':record['provider'],'operation':record['operation']})
                        or record['status'] not in {'rejected','outcome_unknown'} or record['paid']!=0 or bool(record['external_call'])==value['mock']):raise ValueError()
            if out.operation_confirmed and (out.error_code is not None or row['response_sha256'] is None):raise ValueError()
            output.append({'intent_id':row['intent_id'],'response_sha256':row['response_sha256'],'result_sha256':row['result_sha256'],'data':data})
        except WorkflowError:raise
        except Exception:raise WorkflowError('NATIVE_META_PUBLISH_RESPONSE_CHANGED') from None
    return output

def job(journal,con,value):
    rows=[r for r in results(journal,con,value) if r['data']['outcome']['operation']=='meta_init' and r['data']['outcome']['provider_job_id'] is not None]
    if not rows:return None
    if len(rows)!=1:raise WorkflowError('NATIVE_META_PUBLISH_JOB_CHANGED')
    row=rows[0];out=row['data']['outcome']
    if out['operation_confirmed'] is not True:raise WorkflowError('NATIVE_META_PUBLISH_JOB_CHANGED')
    return {'schema_version':'native-official-meta-job-v1','publication_id':value['publication_id'],'snapshot_sha256':value['snapshot_sha256'],
        'platform':value['snapshot']['target']['platform'],'provider_job_id':out['provider_job_id'],'init_intent_id':row['intent_id'],
        'init_response_sha256':row['response_sha256'],'init_result_sha256':row['result_sha256'],'mock':value['mock'],'upload_url_returned':False}

def observations(journal,con,value):
    return [r for r in results(journal,con,value) if r['data']['outcome']['operation']=='meta_status']

def links(journal,con,value,dispatch):
    if value['snapshot']['execution_supported'] is not True:raise WorkflowError('NATIVE_META_PUBLISH_EXECUTION_REQUIRED')
    if dispatch is None:return
    if (any(dispatch[k]!=value[k] for k in ('workspace_id','project_id','snapshot_sha256','approval_id')) or dispatch['phase'] not in PHASES
        or type(dispatch['version']) is not int or dispatch['version']<1 or dispatch['total_bytes']!=value['snapshot']['final_bytes']
        or type(dispatch['acknowledged_bytes']) is not int or not 0<=dispatch['acknowledged_bytes']<=dispatch['total_bytes'] or dispatch['private_session_ref'] is not None):
        raise WorkflowError('NATIVE_META_PUBLISH_DISPATCH_CHANGED')
    records=results(journal,con,value);original=job(journal,con,value)
    pending=list(con.execute("SELECT * FROM native_official_publish_intents WHERE publication_id=? AND status='dispatch_intent'",(value['publication_id'],)))
    if (len(pending)!=(1 if dispatch['intent_id'] is not None else 0)
        or dispatch['intent_id'] is None and dispatch['phase'].endswith('_intent')
        or dispatch['intent_id'] is not None and (pending[0]['intent_id']!=dispatch['intent_id'] or pending[0]['version']!=dispatch['version']
            or pending[0]['operation']+'_intent'!=dispatch['phase'] or pending[0]['approval_id']!=dispatch['approval_id'])):
        raise WorkflowError('NATIVE_META_PUBLISH_DISPATCH_CHANGED')
    if dispatch['phase']!='uploaded' and (dispatch['acknowledged_bytes']!=0 or dispatch['remote_post_id'] is not None):raise WorkflowError('NATIVE_META_PUBLISH_COMPLETION_CHANGED')
    if dispatch['phase'] not in {'prepared','meta_init_intent','meta_init_unconfirmed','review_required'} and original is None:raise WorkflowError('NATIVE_META_PUBLISH_JOB_CHANGED')
    if records and binding(journal,con,value) is None:raise WorkflowError('NATIVE_META_MEDIA_BINDING_CHANGED')
    for r in records:
        out=r['data']['outcome']
        if out['operation']!='meta_init' and original is not None and out['provider_job_id']!=original['provider_job_id']:raise WorkflowError('NATIVE_META_PUBLISH_JOB_CHANGED')
    if dispatch['phase']=='uploaded':
        if dispatch['acknowledged_bytes']!=dispatch['total_bytes'] or dispatch['remote_post_id'] is None:raise WorkflowError('NATIVE_META_PUBLISH_COMPLETION_CHANGED')
        numeric_id(dispatch['remote_post_id'])

def admission(journal,project,identity,*,con,validate_grant=True):
    from .meta_distribution import NativeMetaPublishingFactory
    value=journal.get(project,identity,con=con);s=value['snapshot']
    if s.get('execution_supported') is not True:raise WorkflowError('NATIVE_META_PUBLISH_EXECUTION_REQUIRED')
    dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(identity,)).fetchone()
    if dispatch is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_DISPATCHABLE')
    if validate_grant:
        if value['status'] not in {'queued','running'}:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_DISPATCHABLE')
        journal.valid_grant(con,journal.row(con,project,identity))
    factory=journal.factories.get(s['request']['profile_id'])
    if type(factory) is not NativeMetaPublishingFactory or not factory.execution_supported:raise WorkflowError('NATIVE_META_PUBLISH_CONFIGURATION_CHANGED')
    state=factory.public()
    if (state['status']!='CONFIGURED' or state['configuration_sha256']!=s['configuration_sha256'] or state['target']!=s['target']
        or state['mock'] is not s['mock'] or state['cipher_sha256']!=s['credential_cipher_sha256'] or state['media_configuration_sha256']!=s['media_configuration_sha256']):raise WorkflowError('NATIVE_META_PUBLISH_CONFIGURATION_CHANGED')
    path=None
    if dispatch['phase'] in {'prepared','meta_init_intent','meta_created','meta_transfer_intent'}:_,_,path=journal.revalidate(con,journal.row(con,project,identity))
    if validate_grant:journal.valid_grant(con,journal.row(con,project,identity))
    return value,factory,path,dict(dispatch)

def begin(journal,project,identity,version,operation,body_sha,*,binding_id=None,preflight_id=None):
    if operation not in OPS or type(version) is not int or not re.fullmatch('[a-f0-9]{64}',body_sha):raise WorkflowError('NATIVE_META_PUBLISH_INTENT_INVALID')
    with journal.store.transaction() as con:
        value,_,_,dispatch=admission(journal,project,identity,con=con);phase=dispatch['phase']
        allowed={'meta_init':{'prepared'},'meta_transfer':{'meta_created'},'meta_finish':{'meta_finish_ready'},
            'meta_status':{'meta_processing','meta_transfer_unconfirmed','meta_finish_unconfirmed','meta_finish_ready'}}
        if dispatch['version']!=version or phase not in allowed[operation] or dispatch['intent_id'] is not None:raise WorkflowError('NATIVE_META_PUBLISH_WORKER_STALE')
        if operation=='meta_transfer' and value['snapshot']['target']['platform']!='facebook':raise WorkflowError('NATIVE_META_PUBLISH_OPERATION_INVALID')
        if operation!='meta_status':
            p=read_preflight(con,value,preflight_id)
            if p['proof']['dispatch_version']!=version or p['proof']['approval_id']!=value['approval_id']:raise WorkflowError('NATIVE_META_PUBLISH_PREFLIGHT_STALE')
        if operation in {'meta_init','meta_transfer'}:
            b=read_binding(journal,con,value,con.execute('SELECT * FROM native_official_meta_media_bindings WHERE binding_id=?',(binding_id,)).fetchone())
            if binding(journal,con,value)['binding']['binding_id']!=binding_id:raise WorkflowError('NATIVE_META_MEDIA_SELECTION_CHANGED')
            if b['media']['snapshot']['approval_id']!=value['approval_id']:raise WorkflowError('NATIVE_META_MEDIA_CURRENT_CONSENT_REQUIRED')
        identity_intent=uuid.uuid4().hex;instant=utc(journal.clock()).isoformat()
        con.execute('INSERT INTO native_official_publish_intents VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity_intent,identity,journal.workspace,project,value['snapshot_sha256'],value['approval_id'],version+1,operation,None,None,body_sha,'dispatch_intent',instant))
        con.execute("UPDATE native_official_publish_dispatches SET phase=?,version=?,intent_id=?,updated_at=? WHERE publication_id=?",(operation+'_intent',version+1,identity_intent,now(),identity))
        con.execute("UPDATE native_official_publications SET status='running',updated_at=? WHERE publication_id=?",(now(),identity))
        return Ticket(identity,journal.workspace,project,value['snapshot_sha256'],value['approval_id'],version+1,identity_intent,operation)

def fence(journal,con,ticket,*,require_grant=False):
    if type(ticket) is not Ticket or ticket.workspace_id!=journal.workspace or ticket.operation not in OPS:raise WorkflowError('NATIVE_META_PUBLISH_TICKET_INVALID')
    value=journal.read(journal.row(con,ticket.project_id,ticket.publication_id));dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(ticket.publication_id,)).fetchone()
    intent=con.execute('SELECT * FROM native_official_publish_intents WHERE intent_id=?',(ticket.intent_id,)).fetchone();scoped(dispatch,value);scoped(intent,value)
    if (any(dispatch[k]!=getattr(ticket,k) for k in ('approval_id','version','intent_id','snapshot_sha256')) or dispatch['phase']!=ticket.operation+'_intent'
        or any(intent[k]!=getattr(ticket,k) for k in ('publication_id','workspace_id','project_id','snapshot_sha256','approval_id','version','operation')) or intent['status']!='dispatch_intent'):
        raise WorkflowError('NATIVE_META_PUBLISH_TICKET_STALE')
    if require_grant:admission(journal,ticket.project_id,ticket.publication_id,con=con)
    return value,dict(dispatch),dict(intent)

def finish(journal,ticket,outcome,cost_id,response_sha,*,binding_id=None,preflight_id=None):
    out=Outcome.model_validate(outcome.model_dump(mode='json'))
    with journal.store.transaction() as con:
        value,dispatch,intent=fence(journal,con,ticket);s=value['snapshot'];platform=s['target']['platform']
        if out.operation!=ticket.operation or out.mock is not value['mock']:raise WorkflowError('NATIVE_META_PUBLISH_RESPONSE_SCOPE_CHANGED')
        prior=job(journal,con,value)
        if ticket.operation!='meta_init' and (prior is None or prior['provider_job_id']!=out.provider_job_id):raise WorkflowError('NATIVE_META_PUBLISH_JOB_CHANGED')
        instant=utc(journal.clock()).isoformat()
        data={'schema_version':'native-official-meta-response-v1','outcome':out.model_dump(mode='json'),'cost_operation_id':cost_id,'approval_id':ticket.approval_id,
            'dispatch_version':ticket.version,'body_sha256':intent['body_sha256'],'binding_id':binding_id,'preflight_id':preflight_id,'observed_at':instant,'mock':value['mock']}
        con.execute('INSERT INTO native_official_meta_responses VALUES(?,?,?,?,?,?,?,?,?)',(ticket.intent_id,ticket.publication_id,journal.workspace,ticket.project_id,response_sha,json.dumps(data),digest(data),instant,None))
        confirmed=out.operation_confirmed;phase=dispatch['phase'];remote=None;completed=False
        if ticket.operation=='meta_init':phase=('meta_created' if platform=='facebook' else 'meta_processing') if confirmed else 'meta_init_unconfirmed'
        elif ticket.operation=='meta_transfer':phase='meta_processing' if confirmed else 'meta_transfer_unconfirmed'
        elif ticket.operation=='meta_finish':
            phase='meta_processing' if confirmed and platform=='facebook' else 'meta_finish_unconfirmed'
            if confirmed and platform=='instagram_reels' and out.remote_post_id is not None:phase='uploaded';remote=out.remote_post_id;completed=True
        else:
            if platform=='instagram_reels':
                finish_attempted=con.execute("SELECT 1 FROM native_official_publish_intents WHERE publication_id=? AND operation='meta_finish'",(ticket.publication_id,)).fetchone()
                phase='meta_finish_unconfirmed' if finish_attempted else 'meta_finish_ready' if out.provider_status=='FINISHED' else 'meta_processing'
            else:
                finish_attempted=con.execute("SELECT 1 FROM native_official_publish_intents WHERE publication_id=? AND operation='meta_finish'",(ticket.publication_id,)).fetchone()
                phase='meta_processing' if finish_attempted else 'meta_finish_ready' if out.uploading_phase=='complete' else 'meta_transfer_unconfirmed'
                if finish_attempted and out.provider_status=='ready' and out.uploading_phase==out.processing_phase==out.publishing_phase=='complete':
                    phase='uploaded';remote=out.provider_job_id;completed=True
        try:journal.valid_grant(con,journal.row(con,ticket.project_id,ticket.publication_id));current_grant=True
        except WorkflowError:current_grant=False
        failed=out.provider_status in {'ERROR','EXPIRED','error','failed'} or any(p in {'error','failed'} for p in (out.uploading_phase,out.processing_phase,out.publishing_phase))
        status='completed' if completed else 'review_required' if not current_grant or failed or phase=='meta_init_unconfirmed' else 'queued'
        failure=CONSENT_REVOKED if value['failure_code']==CONSENT_REVOKED else out.error_code or ('NATIVE_META_PROCESSING_FAILED_REVIEW_REQUIRED' if failed else None)
        con.execute('UPDATE native_official_publish_intents SET status=? WHERE intent_id=?',('response_received' if response_sha is not None else 'outcome_unknown',ticket.intent_id))
        con.execute('UPDATE native_official_publish_dispatches SET phase=?,version=version+1,acknowledged_bytes=?,remote_post_id=?,intent_id=NULL,failure_code=?,updated_at=? WHERE publication_id=?',
            (phase,dispatch['total_bytes'] if completed else 0,remote,failure,now(),ticket.publication_id))
        con.execute('UPDATE native_official_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',(status,failure,now(),ticket.publication_id))
        if completed:
            receipt=PublicationReceipt(receipt_id='rcpt_'+uuid.uuid4().hex,provider_key=s['target']['provider_key'],platform=platform,mode='live',request_fingerprint=value['request_fingerprint'],
                remote_post_id=remote,remote_url=None,mock=value['mock'],external_action=not value['mock'],created_at=journal.clock()).model_dump(mode='json')
            con.execute('INSERT INTO native_official_publish_receipts VALUES(?,?,?,?,?,?,?)',(ticket.publication_id,journal.workspace,ticket.project_id,value['snapshot_sha256'],json.dumps(receipt),digest(receipt),instant))
        journal.event(con,journal.row(con,ticket.project_id,ticket.publication_id),'official.meta.operation.observed','worker',operation=ticket.operation,response_sha256=response_sha,
            provider_job_id=out.provider_job_id,operation_confirmed=confirmed,post_confirmed=completed,mock=value['mock'],private_url_returned=False)
    return journal.state(ticket.project_id,ticket.publication_id)

def read_receipt(journal,con,value,row):
    scoped(row,value)
    try:
        receipt=json.loads(row['receipt_json']);parsed=PublicationReceipt.model_validate(receipt);records=results(journal,con,value)
        if (parsed.model_dump(mode='json')!=receipt or digest(receipt)!=row['receipt_sha256'] or parsed.platform!=value['snapshot']['target']['platform']
            or parsed.provider_key!=value['snapshot']['target']['provider_key'] or parsed.request_fingerprint!=value['request_fingerprint'] or parsed.mode!='live'
            or parsed.mock is not value['mock'] or parsed.external_action is not (not value['mock']) or parsed.remote_url is not None or value['status']!='completed'):raise ValueError()
        dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone()
        if dispatch['phase']!='uploaded' or dispatch['remote_post_id']!=parsed.remote_post_id or dispatch['acknowledged_bytes']!=dispatch['total_bytes']:raise ValueError()
        if not records:raise ValueError()
        out=records[-1]['data']['outcome'];numeric_id(parsed.remote_post_id)
        if parsed.platform=='instagram_reels':
            if out['operation']!='meta_finish' or out['operation_confirmed'] is not True or out['remote_post_id']!=parsed.remote_post_id:raise ValueError()
        else:
            if out['operation']!='meta_status' or out['provider_job_id']!=parsed.remote_post_id or out['provider_status']!='ready' or not all(out[k]=='complete' for k in ('uploading_phase','processing_phase','publishing_phase')):raise ValueError()
            if not any(r['data']['outcome']['operation']=='meta_finish' for r in records):raise ValueError()
        return receipt
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_META_PUBLISH_RECEIPT_CHANGED') from None

def recover(journal,costs):
    """No replay/key load: retain known cost hashes and unknown remote outcomes."""
    with journal.store.transaction() as con:
        rows=list(con.execute("SELECT * FROM native_official_publish_dispatches WHERE workspace_id=? AND phase IN ('meta_init_intent','meta_transfer_intent','meta_finish_intent','meta_status_intent')",(journal.workspace,)))
    for row in rows:
        ticket=Ticket(row['publication_id'],journal.workspace,row['project_id'],row['snapshot_sha256'],row['approval_id'],row['version'],row['intent_id'],row['phase'].removesuffix('_intent'))
        with journal.store.transaction() as con:
            value,_,_=fence(journal,con,ticket);original=job(journal,con,value)
            found=con.execute('SELECT * FROM native_cost_operations WHERE project_id=? AND provider=? AND operation=?',
                (ticket.project_id,'official-'+value['snapshot']['target']['platform'],ticket.operation+'.'+ticket.intent_id)).fetchone()
            proof=con.execute('SELECT proof_id,proof_json FROM native_official_meta_preflights WHERE publication_id=? ORDER BY created_at DESC,proof_id DESC',(ticket.publication_id,)).fetchall()
            preflight_id=next((r['proof_id'] for r in proof if json.loads(r['proof_json'])['dispatch_version']==ticket.version-1),None) if ticket.operation!='meta_status' else None
            selected=binding(journal,con,value) if ticket.operation in {'meta_init','meta_transfer'} else None
        response_sha=None
        if found is not None:
            if found['status']=='dispatch_intent':costs.settle(found['id'],status='outcome_unknown',error_code='NATIVE_META_PUBLISH_INTERRUPTED_NO_REPLAY')
            elif found['status']=='response_received':response_sha=json.loads(found['receipt'])['provider_response_sha256']
        outcome=Outcome(operation=ticket.operation,provider_job_id=original['provider_job_id'] if original else None,error_code='NATIVE_META_PUBLISH_INTERRUPTED_NO_REPLAY',mock=value['mock'])
        finish(journal,ticket,outcome,found['id'] if found else None,response_sha,
            binding_id=selected['binding']['binding_id'] if selected else None,preflight_id=preflight_id)
    return len(rows)

def renew(journal,project,identity,payload,*,principal):
    """Same job/immutable metadata, finite new Owner grant; no init restart."""
    if type(payload) is not Renew:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_RENEWAL_INVALID',400)
    authority=journal.identity(principal);payload=Renew.model_validate(payload.model_dump(mode='json'));key=digest(payload.request_key)
    fingerprint=digest({'publication_id':identity,'request':payload.model_dump(mode='json',exclude={'request_key'})})
    with journal.store.transaction() as con:
        value,factory,_,dispatch=admission(journal,project,identity,con=con,validate_grant=False);row=journal.row(con,project,identity)
        prior=con.execute('SELECT * FROM native_official_publish_renewals WHERE workspace_id=? AND project_id=? AND key_sha256=?',(journal.workspace,project,key)).fetchone()
        if prior is not None:
            if prior['publication_id']!=identity or prior['request_sha256']!=fingerprint:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_RENEWAL_IDEMPOTENCY_CONFLICT')
            return {**dict(prior),'replayed':True,'external_calls':0,'automatic_renewal':False}
        if (value['snapshot_sha256']!=payload.expected_snapshot_sha256 or dispatch['version']!=payload.expected_dispatch_version or dispatch['intent_id'] is not None
            or value['status'] not in {'queued','running','review_required'} or dispatch['phase']=='uploaded'):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_RENEWAL_BINDING_CHANGED')
        instant=utc(journal.clock());expires=min(instant+timedelta(seconds=payload.valid_for_seconds),utc(datetime.fromisoformat(authority['expires_at'])))
        if (expires-instant).total_seconds()<60:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_OWNER_TOKEN_EXPIRING')
        approval='nopa_'+uuid.uuid4().hex;renewal='nopr_'+uuid.uuid4().hex;version=dispatch['version']+1;stamp=now()
        grant={'schema_version':'native-official-publish-approval-v1','publication_id':identity,'workspace_id':journal.workspace,'project_id':project,'snapshot_sha256':value['snapshot_sha256'],
            'authority':authority,'issued_at':instant.isoformat(),'expires_at':expires.isoformat(),'acknowledged_official_publication':True,'dry_run_approval_reused':False,'mock':value['mock'],
            'renewal_id':renewal,'prior_approval_id':row['approval_id'],'restart_initialization_authorized':False}
        con.execute("UPDATE native_official_publish_approvals SET status='revoked',revoked_at=? WHERE publication_id=? AND status='active'",(stamp,identity))
        con.execute('INSERT INTO native_official_publish_approvals VALUES(?,?,?,?,?,?,?,?,?)',(approval,identity,journal.workspace,project,digest(grant),json.dumps(grant),'active',stamp,None))
        con.execute('INSERT INTO native_official_publish_renewals VALUES(?,?,?,?,?,?,?,?,?,?,?)',(renewal,identity,journal.workspace,project,key,fingerprint,row['approval_id'],approval,version,value['snapshot_sha256'],stamp))
        con.execute("UPDATE native_official_publications SET status='queued',approval_id=?,failure_code=NULL,updated_at=? WHERE publication_id=?",(approval,stamp,identity))
        con.execute('UPDATE native_official_publish_dispatches SET approval_id=?,version=?,failure_code=NULL,updated_at=? WHERE publication_id=?',(approval,version,stamp,identity))
        journal.event(con,row,'official.meta.consent.renewed',authority['token_id'],renewal_id=renewal,approval_id=approval,original_job_preserved=True,restart_initialization_authorized=False)
        return {'renewal_id':renewal,'publication_id':identity,'workspace_id':journal.workspace,'project_id':project,'approval_id':approval,'prior_approval_id':row['approval_id'],
            'dispatch_version':version,'snapshot_sha256':value['snapshot_sha256'],'created_at':stamp,'replayed':False,'external_calls':0,'automatic_renewal':False}
