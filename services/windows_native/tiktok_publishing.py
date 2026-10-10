"""Owned TikTok async job, current creator proof and publication observations.

Public journals contain no upload URI or token. They are never send authority.
"""
import hashlib,json,re,uuid
from datetime import datetime,timedelta,timezone
from pydantic import Field,StrictBool,StrictInt,model_validator,field_validator
from typing import Literal
from app.models import StrictModel
from app.publishing_models import PublicationMetadata
from app.tiktok_upload import ChunkPlan,PostChoices,PostObservation,identifier,start_request
from .contracts import WorkflowError,digest
from .store import now
from .tiktok_creators import creator_dict,parsed_creator
PREFLIGHT='native_official_tiktok_preflights';JOBS='native_official_tiktok_jobs';OBSERVATIONS='native_official_tiktok_observations'
HASH=r'^[a-f0-9]{64}$'
class Preflight(StrictModel):
    schema_version:Literal['native-tiktok-publish-preflight-v1']='native-tiktok-publish-preflight-v1'
    check_id:str=Field(pattern=r'^ntpc_[a-f0-9]{32}$')
    publication_id:str=Field(pattern=r'^nopu_[a-f0-9]{32}$')
    workspace_id:str
    project_id:str=Field(pattern=r'^[a-f0-9]{32}$')
    snapshot_sha256:str=Field(pattern=HASH)
    approval_id:str=Field(pattern=r'^nopa_[a-f0-9]{32}$')
    dispatch_version:StrictInt=Field(ge=1)
    account_target_id:str=Field(min_length=1,max_length=256)
    account_target_binding_sha256:str=Field(pattern=HASH)
    account_match:Literal[True]=True
    account_cost_operation_id:str=Field(min_length=1,max_length=128)
    account_response_sha256:str=Field(pattern=HASH)
    creator_cost_operation_id:str=Field(min_length=1,max_length=128)
    creator_response_sha256:str=Field(pattern=HASH)
    creator:dict
    observed_at:datetime
    @field_validator('account_match',mode='before')
    @classmethod
    def exact_account(cls,value):
        if value is not True:raise ValueError('Actual account match required')
        return value
    @model_validator(mode='after')
    def structured(self):
        parsed_creator(self.creator)
        if self.observed_at.tzinfo is None:raise ValueError('Aware observation required')
        return self
class Receipt(StrictModel):
    schema_version:Literal['native-tiktok-publication-receipt-v1']='native-tiktok-publication-receipt-v1'
    receipt_id:str=Field(pattern=r'^rcpt_[a-f0-9]{32}$')
    provider_key:Literal['tiktok-content-posting-api']='tiktok-content-posting-api'
    platform:Literal['tiktok']='tiktok'
    mode:Literal['live']='live'
    request_fingerprint:str=Field(pattern=HASH)
    provider_job_id:str
    remote_post_id:str|None=None
    public_post_ids:list[str]=Field(max_length=50)
    remote_url:None=None
    privacy_level:str
    mock:StrictBool
    external_action:StrictBool
    publish_complete_confirmed:Literal[True]=True
    public_visibility_confirmed:StrictBool
    observation_id:str=Field(pattern=r'^ntpo_[a-f0-9]{32}$')
    observation_sha256:str=Field(pattern=HASH)
    created_at:datetime
    @field_validator('publish_complete_confirmed',mode='before')
    @classmethod
    def exact_completion(cls,value):
        if value is not True:raise ValueError('Actual completion required')
        return value
    @model_validator(mode='after')
    def qualify(self):
        identifier(self.provider_job_id);validate_ids(self.public_post_ids)
        if (self.remote_post_id!=(self.public_post_ids[0] if len(self.public_post_ids)==1 else None) or self.external_action is not (not self.mock)
            or self.public_visibility_confirmed is not bool(self.public_post_ids) or self.created_at.tzinfo is None
            or self.privacy_level not in {'SELF_ONLY','PUBLIC_TO_EVERYONE','MUTUAL_FOLLOW_FRIENDS','FOLLOWER_OF_CREATOR'}
            or self.public_post_ids and self.privacy_level!='PUBLIC_TO_EVERYONE'):raise ValueError('Qualified provider result required')
        return self
def validate_ids(values):
    if type(values) is not list or len(values)>50 or len(set(values))!=len(values) or any(type(x) is not str or not re.fullmatch('[1-9][0-9]{0,18}',x) or int(x)>9223372036854775807 for x in values):raise ValueError('Actual post IDs required')
def observation(value,total):
    if type(value) is not PostObservation or value.status not in {'PROCESSING_UPLOAD','PROCESSING_DOWNLOAD','SEND_TO_USER_INBOX','PUBLISH_COMPLETE','FAILED'} or type(value.public_post_ids) is not tuple:raise ValueError('Typed observation required')
    validate_ids(list(value.public_post_ids))
    if (value.uploaded_bytes is not None and (type(value.uploaded_bytes) is not int or not 0<=value.uploaded_bytes<=total) or value.public_post_ids and value.status!='PUBLISH_COMPLETE'
        or value.failure_code!=('TIKTOK_POST_FAILED' if value.status=='FAILED' else None)):raise ValueError('Provider observation invalid')
    return {'status':value.status,'uploaded_bytes':value.uploaded_bytes,'public_post_ids':list(value.public_post_ids),'failure_code':value.failure_code}
def ensure(journal):
    with journal.store.transaction() as con:
        con.executescript('''CREATE TABLE IF NOT EXISTS native_official_tiktok_preflights (
        check_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,proof_json TEXT NOT NULL,proof_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_official_tiktok_jobs (
        publication_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,
        job_json TEXT NOT NULL,job_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS native_official_tiktok_observations (
        observation_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
        snapshot_sha256 TEXT NOT NULL,observation_json TEXT NOT NULL,observation_sha256 TEXT NOT NULL,created_at TEXT NOT NULL);''')
        for table in (PREFLIGHT,JOBS,OBSERVATIONS):
            if con.execute('SELECT 1 FROM '+table+' WHERE workspace_id!=? LIMIT 1',(journal.workspace,)).fetchone():raise WorkflowError('NATIVE_TIKTOK_PUBLISH_WORKSPACE_CHANGED')
def exists(con,table):return con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone() is not None
def request_sha(value,version,operation,body_sha):
    return digest({'publication_id':value['publication_id'],'snapshot_sha256':value['snapshot_sha256'],'version':version,'operation':operation,'body_sha256':body_sha})
def cost(con,value,identity,version,operation,body_sha,response_sha,*,intent_id=None):
    row=con.execute('SELECT * FROM native_cost_operations WHERE id=? AND project_id=?',(identity,value['project_id'])).fetchone()
    try:
        if (row is None or row['provider']!='official-tiktok' or row['model'] is not None or row['job_id'] is not None or row['paid']!=0 or row['needs_approval']!=0
            or row['external_call']!=int(not value['mock']) or row['status']!='response_received' or row['request_sha256']!=request_sha(value,version,operation,body_sha)
            or not re.fullmatch(re.escape(operation)+r'\.[a-f0-9]{32}',row['operation']) or intent_id is not None and row['operation']!=operation+'.'+intent_id
            or json.loads(row['receipt'])['provider_response_sha256']!=response_sha):raise ValueError()
    except Exception:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_COST_PROOF_CHANGED') from None
    return dict(row)
def metadata_request(value,info):
    s=value['snapshot'];return start_request(PublicationMetadata.model_validate(s['metadata']),ChunkPlan(s['final_bytes'],s['chunk_size']),'UNSENT-NATIVE-TIKTOK-BODY-PROOF',
        creator=info,choices=PostChoices.model_validate(s['choices']),duration_sec=s['duration_seconds'],client_audited=s['disclosures']['api_client_audited'],media_location=s['disclosures']['media_location'])
def scope(row,value):
    if row is None or any(row[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256')):raise WorkflowError('NATIVE_TIKTOK_PUBLISH_EVIDENCE_SCOPE_CHANGED')
def read_admission(journal,project,identity,*,con,validate_grant=True):
    """Read an already initialized remote job, never authorize uploaded bytes.

    Original immutable render/creator/cost links still validate. Later timeline
    edits and local media expiry do not erase the remote publication's identity.
    """
    from .tiktok_distribution import NativeTikTokPublishingFactory
    value=journal.get(project,identity,con=con);s=value['snapshot'];dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(identity,)).fetchone();scope(dispatch,value)
    if s['target']['platform']!='tiktok' or dispatch['phase'] not in {'uploaded','reconciliation_required','reconcile_intent'} or dispatch['approval_id']!=value['approval_id'] or type(dispatch['version']) is not int:
        raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_BINDING_CHANGED')
    if validate_grant:
        if value['status'] not in {'queued','running'}:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_DISPATCHABLE')
        journal.valid_grant(con,journal.row(con,project,identity))
    factory=journal.factories.get(s['request']['profile_id'])
    if type(factory) is not NativeTikTokPublishingFactory or factory.root!=journal.store.root.absolute() or factory.workspace!=journal.workspace:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_CONFIGURATION_CHANGED')
    state=factory.public()
    if (state['status']!='CONFIGURED' or state['configuration_sha256']!=s['configuration_sha256'] or state['target']!=s['target'] or state['target_binding_sha256']!=s['target_binding_sha256']
        or state['mock'] is not s['mock'] or state['cipher_sha256']!=s['credential_cipher_sha256'] or type(dispatch['acknowledged_bytes']) is not int or not 0<=dispatch['acknowledged_bytes']<=dispatch['total_bytes']
        or dispatch['total_bytes']!=s['final_bytes'] or dispatch['phase']=='uploaded' and dispatch['acknowledged_bytes']!=dispatch['total_bytes']):raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_CONFIGURATION_CHANGED')
    if job(con,value) is None:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_BINDING_CHANGED')
    if validate_grant:journal.valid_grant(con,journal.row(con,project,identity))
    return value,factory,None,dict(dispatch)
def read_preflight(con,value,identity):
    row=con.execute('SELECT * FROM '+PREFLIGHT+' WHERE check_id=?',(identity,)).fetchone();scope(row,value)
    try:
        data=json.loads(row['proof_json']);proof=Preflight.model_validate(data)
        if (proof.model_dump(mode='json')!=data or digest(data)!=row['proof_sha256'] or data['check_id']!=row['check_id'] or data['observed_at']!=row['created_at']
            or any(data[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256'))
            or proof.account_target_id!=value['snapshot']['target']['target_account_id'] or proof.account_target_binding_sha256!=value['snapshot']['target_binding_sha256']):raise ValueError()
        grant=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=? AND workspace_id=? AND project_id=?',(proof.approval_id,value['publication_id'],value['workspace_id'],value['project_id'])).fetchone()
        if grant is None:raise ValueError()
        original=json.loads(grant['grant_json'])
        if (digest(original)!=grant['grant_sha256'] or original['snapshot_sha256']!=value['snapshot_sha256'] or original['mock'] is not value['mock']
            or not datetime.fromisoformat(original['issued_at'])<=proof.observed_at<datetime.fromisoformat(original['expires_at'])):raise ValueError()
        cost(con,value,proof.account_cost_operation_id,proof.dispatch_version,'publish_account_lookup',hashlib.sha256(b'').hexdigest(),proof.account_response_sha256)
        cost(con,value,proof.creator_cost_operation_id,proof.dispatch_version,'publish_creator_lookup',hashlib.sha256(b'{}').hexdigest(),proof.creator_response_sha256)
        metadata_request(value,parsed_creator(proof.creator))
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_PREFLIGHT_CHANGED') from None
    return {'proof':data,'sha256':row['proof_sha256']}
def record_preflight(journal,project,identity,version,info,account,account_cost,account_response,creator_cost,creator_response):
    with journal.store.transaction() as con:
        value,_,_,dispatch=journal.admission(project,identity,con=con)
        if dispatch['phase']!='prepared' or dispatch['version']!=version or value['snapshot']['target']['platform']!='tiktok':raise WorkflowError('NATIVE_TIKTOK_PUBLISH_PREFLIGHT_STALE')
        proof=Preflight(check_id='ntpc_'+uuid.uuid4().hex,publication_id=identity,workspace_id=journal.workspace,project_id=project,snapshot_sha256=value['snapshot_sha256'],approval_id=value['approval_id'],dispatch_version=version,
            account_target_id=account['target_account_id'],account_target_binding_sha256=account['target_binding_sha256'],account_match=account['account_match'],account_cost_operation_id=account_cost,account_response_sha256=account_response,
            creator_cost_operation_id=creator_cost,creator_response_sha256=creator_response,creator=creator_dict(info),observed_at=journal.clock()).model_dump(mode='json')
        metadata_request(value,info);con.execute('INSERT INTO '+PREFLIGHT+' VALUES(?,?,?,?,?,?,?,?)',(proof['check_id'],identity,journal.workspace,project,value['snapshot_sha256'],json.dumps(proof),digest(proof),proof['observed_at']))
        result=read_preflight(con,value,proof['check_id']);journal.event(con,journal.row(con,project,identity),'official.tiktok.creator.preflight.observed','worker',check_id=proof['check_id'],proof_sha256=result['sha256'],external_action=False)
        return result
def init_fingerprint(con,value,total,preflight_id,version,approval_id):
    proof=read_preflight(con,value,preflight_id)
    if proof['proof']['dispatch_version']!=version or proof['proof']['approval_id']!=approval_id:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_PREFLIGHT_STALE')
    return digest({'metadata':value['snapshot']['metadata'],'disclosures':value['snapshot']['disclosures'],'choices':value['snapshot']['choices'],'total_bytes':total,
        'creator_preflight_id':preflight_id,'creator_preflight_sha256':proof['sha256'],'credential_cipher_sha256':value['snapshot']['credential_cipher_sha256']})
def init_proof(con,value,intent):
    rows=con.execute('SELECT check_id FROM '+PREFLIGHT+' WHERE publication_id=? AND workspace_id=? AND project_id=? AND snapshot_sha256=?',(value['publication_id'],value['workspace_id'],value['project_id'],value['snapshot_sha256'])).fetchall()
    matches=[]
    for row in rows:
        proof=read_preflight(con,value,row['check_id'])
        if proof['proof']['dispatch_version']+1==intent['version'] and proof['proof']['approval_id']==intent['approval_id'] and init_fingerprint(con,value,intent['total_bytes'] if 'total_bytes' in intent else value['snapshot']['final_bytes'],row['check_id'],intent['version']-1,intent['approval_id'])==intent['body_sha256']:matches.append(proof)
    if len(matches)!=1:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_INIT_PROOF_CHANGED')
    return matches[0]
def job(con,value):
    if not exists(con,JOBS):return None
    row=con.execute('SELECT * FROM '+JOBS+' WHERE publication_id=?',(value['publication_id'],)).fetchone()
    if row is None:return None
    scope(row,value)
    try:
        data=json.loads(row['job_json']);s=value['snapshot']
        fields={'schema_version','provider_job_id','session_ref','total_bytes','init_intent_id','init_response_sha256','init_cost_operation_id','creator_preflight_id','creator_preflight_sha256','target_binding_sha256','configuration_sha256','created_at','expires_at','mock','token_returned','upload_url_returned'}
        if (set(data)!=fields or data['schema_version']!='native-tiktok-provider-job-v1' or digest(data)!=row['job_sha256'] or data['created_at']!=row['created_at'] or data['mock'] is not value['mock']
            or data['token_returned'] is not False or data['upload_url_returned'] is not False or data['target_binding_sha256']!=s['target_binding_sha256'] or data['configuration_sha256']!=s['configuration_sha256']
            or type(data['total_bytes']) is not int or data['total_bytes']!=s['final_bytes'] or not re.fullmatch(r'nups_[a-f0-9]{32}',data['session_ref'])):raise ValueError()
        identifier(data['provider_job_id']);created=datetime.fromisoformat(data['created_at']);expires=datetime.fromisoformat(data['expires_at'])
        if created.tzinfo is None or expires.tzinfo is None or (expires-created).total_seconds()!=3600:raise ValueError()
        intent=con.execute("SELECT * FROM native_official_publish_intents WHERE intent_id=? AND operation='init'",(data['init_intent_id'],)).fetchone();scope(intent,value)
        if intent['status']!='response_received':raise ValueError()
        proof=init_proof(con,value,dict(intent))
        if proof['proof']['check_id']!=data['creator_preflight_id'] or proof['sha256']!=data['creator_preflight_sha256'] or datetime.fromisoformat(proof['proof']['observed_at'])>created:raise ValueError()
        request=metadata_request(value,parsed_creator(proof['proof']['creator']))
        cost(con,value,data['init_cost_operation_id'],intent['version'],'upload_initialize',hashlib.sha256(request.body).hexdigest(),data['init_response_sha256'],intent_id=intent['intent_id'])
        session=con.execute('SELECT * FROM native_official_publish_sessions WHERE session_ref=?',(data['session_ref'],)).fetchone();scope(session,value)
        if any(session[k]!=data[k] for k in ('target_binding_sha256','configuration_sha256','total_bytes','created_at','expires_at')) or session['mock']!=int(value['mock']):raise ValueError()
        dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone();scope(dispatch,value)
        if dispatch['private_session_ref']!=data['session_ref'] or dispatch['total_bytes']!=data['total_bytes']:raise ValueError()
        events=con.execute("SELECT evidence_json FROM native_official_publish_events WHERE publication_id=? AND workspace_id=? AND project_id=? AND action='official.tiktok.session.registered'",(value['publication_id'],value['workspace_id'],value['project_id'])).fetchall()
        if not any(json.loads(e['evidence_json']).get('provider_job_sha256')==row['job_sha256'] and json.loads(e['evidence_json']).get('provider_job_id')==data['provider_job_id'] and json.loads(e['evidence_json']).get('init_response_sha256')==data['init_response_sha256'] for e in events):raise ValueError()
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_JOB_CHANGED') from None
    return {**data,'publication_id':value['publication_id'],'workspace_id':value['workspace_id'],'project_id':value['project_id'],'snapshot_sha256':value['snapshot_sha256'],'job_sha256':row['job_sha256']}
def read_observation(con,value,row):
    scope(row,value)
    try:
        data=json.loads(row['observation_json']);fields={'schema_version','observation_id','publication_id','workspace_id','project_id','snapshot_sha256','approval_id','dispatch_version','provider_job_id',
            'status','uploaded_bytes','public_post_ids','failure_code','response_sha256','cost_operation_id','requested_at','observed_at','mock','external_call','publish_complete_confirmed','public_visibility_confirmed'}
        if (set(data)!=fields or data['schema_version']!='native-tiktok-processing-observation-v1' or data['observation_id']!=row['observation_id'] or digest(data)!=row['observation_sha256']
            or any(data[k]!=value[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256')) or data['observed_at']!=row['created_at'] or data['mock'] is not value['mock'] or data['external_call'] is not (not value['mock'])
            or type(data['dispatch_version']) is not int or data['dispatch_version']<1 or not re.fullmatch(r'nopa_[a-f0-9]{32}',data['approval_id']) or datetime.fromisoformat(data['observed_at']).tzinfo is None):raise ValueError()
        provider=job(con,value)
        if provider is None or provider['provider_job_id']!=data['provider_job_id']:raise ValueError()
        obs=PostObservation(data['status'],data['uploaded_bytes'],tuple(data['public_post_ids']),data['failure_code']);observation(obs,value['snapshot']['final_bytes'])
        if data['publish_complete_confirmed'] is not (obs.status=='PUBLISH_COMPLETE') or data['public_visibility_confirmed'] is not bool(obs.public_post_ids):raise ValueError()
        from app.tiktok_upload import status_request
        request=status_request(provider['provider_job_id'],'UNSENT-NATIVE-TIKTOK-STATUS-PROOF')
        cost(con,value,data['cost_operation_id'],data['dispatch_version'],'publish_processing_status',hashlib.sha256(request.body).hexdigest(),data['response_sha256'])
        grant=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=? AND workspace_id=? AND project_id=?',(data['approval_id'],value['publication_id'],value['workspace_id'],value['project_id'])).fetchone()
        if grant is None:raise ValueError()
        original=json.loads(grant['grant_json']);requested=datetime.fromisoformat(data['requested_at'])
        if digest(original)!=grant['grant_sha256'] or original['snapshot_sha256']!=value['snapshot_sha256'] or requested.tzinfo is None or not datetime.fromisoformat(original['issued_at'])<=requested<datetime.fromisoformat(original['expires_at']) or requested>datetime.fromisoformat(data['observed_at']):raise ValueError()
    except WorkflowError:raise
    except Exception:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_OBSERVATION_CHANGED') from None
    return data
def observations(con,value):
    if not exists(con,OBSERVATIONS):return []
    rows=con.execute('SELECT * FROM '+OBSERVATIONS+' WHERE publication_id=? AND workspace_id=? AND project_id=? ORDER BY rowid DESC LIMIT 50',(value['publication_id'],value['workspace_id'],value['project_id'])).fetchall()
    return [read_observation(con,value,row) for row in reversed(rows)]
def processing(journal,project,identity,version,approval_id,obs,response_sha,cost_id,requested_at):
    with journal.store.transaction() as con:
        value=journal.read(journal.row(con,project,identity));dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(identity,)).fetchone();scope(dispatch,value)
        if value['snapshot']['target']['platform']!='tiktok' or dispatch['version']!=version or dispatch['approval_id']!=approval_id or dispatch['phase']!='uploaded' or dispatch['acknowledged_bytes']!=dispatch['total_bytes']:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_PROCESSING_STALE')
        provider=job(con,value);body=observation(obs,dispatch['total_bytes'])
        from app.tiktok_upload import status_request
        request=status_request(provider['provider_job_id'],'UNSENT-NATIVE-TIKTOK-STATUS-PROOF');cost(con,value,cost_id,version,'publish_processing_status',hashlib.sha256(request.body).hexdigest(),response_sha)
        instant=journal.clock().astimezone(timezone.utc);oid='ntpo_'+uuid.uuid4().hex
        evidence={'schema_version':'native-tiktok-processing-observation-v1','observation_id':oid,'publication_id':identity,'workspace_id':journal.workspace,'project_id':project,'snapshot_sha256':value['snapshot_sha256'],
            'approval_id':approval_id,'dispatch_version':version,'provider_job_id':provider['provider_job_id'],**body,'response_sha256':response_sha,'cost_operation_id':cost_id,'requested_at':requested_at.astimezone(timezone.utc).isoformat(),'observed_at':instant.isoformat(),'mock':value['mock'],
            'external_call':not value['mock'],'publish_complete_confirmed':obs.status=='PUBLISH_COMPLETE','public_visibility_confirmed':bool(obs.public_post_ids)}
        con.execute('INSERT INTO '+OBSERVATIONS+' VALUES(?,?,?,?,?,?,?,?)',(oid,identity,journal.workspace,project,value['snapshot_sha256'],json.dumps(evidence),digest(evidence),instant.isoformat()))
        read_observation(con,value,con.execute('SELECT * FROM '+OBSERVATIONS+' WHERE observation_id=?',(oid,)).fetchone())
        privacy=value['snapshot']['choices']['privacy_level'];failure=obs.failure_code
        if obs.status in {'PROCESSING_DOWNLOAD','SEND_TO_USER_INBOX'}:failure='TIKTOK_POST_MODE_UNEXPECTED_REVIEW_REQUIRED'
        if obs.public_post_ids and privacy!='PUBLIC_TO_EVERYONE':failure='TIKTOK_VISIBILITY_UNCONFIRMED_REVIEW_REQUIRED'
        confirmed=obs.status=='PUBLISH_COMPLETE' and failure is None and (privacy!='PUBLIC_TO_EVERYONE' or bool(obs.public_post_ids))
        remote=obs.public_post_ids[0] if confirmed and len(obs.public_post_ids)==1 else None
        if confirmed:
            receipt=Receipt(receipt_id='rcpt_'+uuid.uuid4().hex,request_fingerprint=value['request_fingerprint'],provider_job_id=provider['provider_job_id'],remote_post_id=remote,public_post_ids=list(obs.public_post_ids),privacy_level=privacy,
                mock=value['mock'],external_action=not value['mock'],public_visibility_confirmed=bool(obs.public_post_ids),observation_id=oid,observation_sha256=digest(evidence),created_at=instant).model_dump(mode='json')
            con.execute('INSERT INTO native_official_publish_receipts VALUES(?,?,?,?,?,?,?)',(identity,journal.workspace,project,value['snapshot_sha256'],json.dumps(receipt),digest(receipt),instant.isoformat()))
        # A received status is evidence, even if approval was revoked during its
        # wire. It authorizes no later request. A confirmed completed post is kept.
        try:read_admission(journal,project,identity,con=con);live=True
        except WorkflowError:live=False
        con.execute('UPDATE native_official_publish_dispatches SET version=version+1,remote_post_id=?,failure_code=?,updated_at=? WHERE publication_id=?',(remote,failure,now(),identity))
        con.execute('UPDATE native_official_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',('completed' if confirmed else 'review_required' if failure or not live else 'queued',failure if failure else value['failure_code'] if not live else None,now(),identity))
        journal.event(con,journal.row(con,project,identity),'official.tiktok.processing.observed','worker',observation_id=oid,observation_sha256=digest(evidence),response_sha256=response_sha,confirmed=confirmed,public_post_ids=list(obs.public_post_ids),provider_job_id=provider['provider_job_id'],external_action=False)
    return journal.get(project,identity)
def read_receipt(con,value,row):
    scope(row,value)
    try:
        data=json.loads(row['receipt_json']);receipt=Receipt.model_validate(data);provider=job(con,value)
        dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone();scope(dispatch,value)
        observation_row=con.execute('SELECT * FROM '+OBSERVATIONS+' WHERE observation_id=?',(receipt.observation_id,)).fetchone();evidence=read_observation(con,value,observation_row)
        if (data!=receipt.model_dump(mode='json') or digest(data)!=row['receipt_sha256'] or receipt.request_fingerprint!=value['request_fingerprint'] or receipt.mock is not value['mock']
            or receipt.provider_job_id!=provider['provider_job_id'] or receipt.privacy_level!=value['snapshot']['choices']['privacy_level'] or evidence['status']!='PUBLISH_COMPLETE' or digest(evidence)!=receipt.observation_sha256
            or data['public_post_ids']!=evidence['public_post_ids'] or datetime.fromisoformat(evidence['observed_at'])!=receipt.created_at or dispatch['remote_post_id']!=receipt.remote_post_id
            or dispatch['phase']!='uploaded' or dispatch['acknowledged_bytes']!=dispatch['total_bytes'] or value['status']!='completed'
            or receipt.privacy_level=='PUBLIC_TO_EVERYONE' and not receipt.public_post_ids):raise ValueError()
    except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_RECEIPT_CHANGED') from None
    return data
def finish_upload(journal,ticket,offset,response_sha,cost_id,*,obs=None):
    with journal.store.transaction() as con:
        value,dispatch,intent=journal.fence(con,ticket);provider=job(con,value)
        if value['snapshot']['target']['platform']!='tiktok' or ticket.operation not in {'chunk','reconcile'} or provider is None:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_PROGRESS_INVALID')
        if ticket.operation=='chunk':body_sha=intent['body_sha256'];ceiling=intent['range_end']
        else:
            from app.tiktok_upload import status_request
            body_sha=hashlib.sha256(status_request(provider['provider_job_id'],'UNSENT-NATIVE-TIKTOK-STATUS-PROOF').body).hexdigest()
            ceiling=con.execute("SELECT max(range_end) FROM native_official_publish_intents WHERE publication_id=? AND workspace_id=? AND project_id=? AND snapshot_sha256=? AND operation='chunk'",(ticket.publication_id,ticket.workspace_id,ticket.project_id,ticket.snapshot_sha256)).fetchone()[0] or 0
        cost(con,value,cost_id,ticket.version,'upload_'+ticket.operation,body_sha,response_sha,intent_id=ticket.intent_id)
        details=observation(obs,dispatch['total_bytes']) if obs is not None else None
        failure=None;delay=None;phase='uploading'
        if ticket.operation=='chunk':
            if obs is not None or type(offset) is not int or offset!=ceiling:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_ACK_INVALID')
        else:
            if obs is None:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_ACK_INVALID')
            offset=obs.uploaded_bytes
            if offset is None:
                offset=dispatch['total_bytes'] if obs.status=='PUBLISH_COMPLETE' and ceiling==dispatch['total_bytes'] else dispatch['acknowledged_bytes'];phase='reconciliation_required';delay=30
            if obs.status in {'FAILED','PROCESSING_DOWNLOAD','SEND_TO_USER_INBOX'}:phase='review_required';failure='TIKTOK_RECONCILIATION_REVIEW_REQUIRED';offset=dispatch['acknowledged_bytes']
        if type(offset) is not int or not dispatch['acknowledged_bytes']<=offset<=ceiling:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_ACK_INVALID')
        if phase!='review_required' and offset==dispatch['total_bytes']:phase='uploaded';delay=None
        elif phase!='review_required' and offset%value['snapshot']['chunk_size']:phase='review_required';failure='TIKTOK_PARTIAL_CHUNK_REVIEW_REQUIRED'
        elif phase=='uploading' and offset==dispatch['acknowledged_bytes']:phase='reconciliation_required';delay=30
        if phase=='uploading' and journal.clock()>=datetime.fromisoformat(provider['expires_at']):phase='review_required';failure='TIKTOK_UPLOAD_SESSION_EXPIRED_REVIEW_REQUIRED'
        try:
            (read_admission(journal,ticket.project_id,ticket.publication_id,con=con) if ticket.operation=='reconcile' else journal.admission(ticket.project_id,ticket.publication_id,con=con));live=True
        except WorkflowError:live=False
        instant=journal.clock().astimezone(timezone.utc);result={'schema_version':'native-tiktok-upload-observation-v1','phase':phase,'acknowledged_bytes':offset,'provider_job_id':provider['provider_job_id'],
            'remote_post_id':None,'observation':details,'cost_operation_id':cost_id,'mock':value['mock'],'external_call':not value['mock'],'observed_at':instant.isoformat(),'retry_after':delay,'failure_code':failure}
        retry=(instant+timedelta(seconds=delay)).isoformat() if delay else None
        con.execute('INSERT INTO native_official_publish_responses VALUES(?,?,?,?,?,?,?,?,?)',(ticket.intent_id,ticket.publication_id,journal.workspace,ticket.project_id,response_sha,json.dumps(result),digest(result),instant.isoformat(),retry))
        con.execute("UPDATE native_official_publish_intents SET status='response_received' WHERE intent_id=?",(ticket.intent_id,))
        con.execute('UPDATE native_official_publish_dispatches SET phase=?,version=version+1,acknowledged_bytes=?,remote_post_id=NULL,intent_id=NULL,failure_code=?,updated_at=? WHERE publication_id=?',(phase,offset,failure,now(),ticket.publication_id))
        con.execute('UPDATE native_official_publications SET status=?,failure_code=?,updated_at=? WHERE publication_id=?',('review_required' if phase=='review_required' or not live else 'queued',failure if failure else value['failure_code'] if not live else None,now(),ticket.publication_id))
        journal.event(con,journal.row(con,ticket.project_id,ticket.publication_id),'official.tiktok.upload.observed','worker',response_sha256=response_sha,**result)
    return journal.state(ticket.project_id,ticket.publication_id)

def reconcile_backoff(journal,ticket,response_sha,cost_id,delay):
    """Record an actual throttled status response without inventing progress."""
    if type(delay) is not int or not 1<=delay<=3600 or ticket.operation!='reconcile':raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_BACKOFF_INVALID')
    with journal.store.transaction() as con:
        value,dispatch,_=journal.fence(con,ticket);provider=job(con,value)
        from app.tiktok_upload import status_request
        if value['snapshot']['target']['platform']!='tiktok' or provider is None:raise WorkflowError('NATIVE_TIKTOK_PUBLISH_READ_BACKOFF_INVALID')
        body_sha=hashlib.sha256(status_request(provider['provider_job_id'],'UNSENT-NATIVE-TIKTOK-STATUS-PROOF').body).hexdigest()
        cost(con,value,cost_id,ticket.version,'upload_reconcile',body_sha,response_sha,intent_id=ticket.intent_id)
        instant=journal.clock().astimezone(timezone.utc);retry=(instant+timedelta(seconds=delay)).isoformat()
        result={'schema_version':'native-tiktok-upload-read-backoff-v1','phase':'reconciliation_required','acknowledged_bytes':dispatch['acknowledged_bytes'],
            'provider_job_id':provider['provider_job_id'],'remote_post_id':None,'observation':None,'cost_operation_id':cost_id,'mock':value['mock'],
            'external_call':not value['mock'],'observed_at':instant.isoformat(),'retry_after':delay,'failure_code':'NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF'}
        try:read_admission(journal,ticket.project_id,ticket.publication_id,con=con);live=True
        except WorkflowError:live=False
        con.execute('INSERT INTO native_official_publish_responses VALUES(?,?,?,?,?,?,?,?,?)',(ticket.intent_id,ticket.publication_id,journal.workspace,ticket.project_id,response_sha,json.dumps(result),digest(result),instant.isoformat(),retry))
        con.execute("UPDATE native_official_publish_intents SET status='response_received' WHERE intent_id=?",(ticket.intent_id,))
        con.execute("UPDATE native_official_publish_dispatches SET phase='reconciliation_required',version=version+1,intent_id=NULL,failure_code=NULL,updated_at=? WHERE publication_id=?",(now(),ticket.publication_id))
        con.execute('UPDATE native_official_publications SET status=?,updated_at=? WHERE publication_id=?',('queued' if live else 'review_required',now(),ticket.publication_id))
        journal.event(con,journal.row(con,ticket.project_id,ticket.publication_id),'official.tiktok.reconciliation.backoff','worker',response_sha256=response_sha,**result)
    return retry
