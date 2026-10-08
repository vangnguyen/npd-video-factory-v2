"""Native durable official publish review/consent and dispatch fences.

Pure provider protocols are reused; this journal never sends a provider request.
Dry-run receipts and account checks cannot themselves grant publishing authority.
"""
from contextlib import nullcontext
from datetime import datetime,timedelta,timezone
import json,re,uuid
from .contracts import WorkflowError,digest
from .official_publication_models import Create,Approve,Action
from .official_publication_registry import PublishingFactory
from .publications import PROFILES
from .publication_qc import project as project_qc
from .store import now
from app.human_identity import HumanAuthVerifier,HumanPrincipal
from app.publishing_logic import validate_platform
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.youtube_upload import start_request,size_bytes
from app.publishing_wire import PublishingWireError
from types import SimpleNamespace

def utc(value):
    if not isinstance(value,datetime) or value.tzinfo is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_TIME_INVALID',400)
    return value.astimezone(timezone.utc)

class NativeOfficialPublications:
    def __init__(self,store,publications,accounts,*,factories=None,identity_provider=None,clock=lambda:datetime.now(timezone.utc)):
        self.store,self.publications,self.accounts=store,publications,accounts;self.workspace=publications.workspace_id;self.factories=dict(factories or {})
        self.identity_provider,self.clock=identity_provider,clock;accounts.check_workspace()
        if accounts.store is not store or accounts.workspace!=self.workspace or publications.store is not store:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_SCOPE_INVALID',400)
        if identity_provider is not None and not callable(identity_provider):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_IDENTITY_INVALID',400)
        if any(type(f) is not PublishingFactory or key!=f.profile.target.profile_id or f.workspace!=self.workspace or f.root.absolute()!=store.root.absolute() for key,f in self.factories.items()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        with store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_official_publications (
                publication_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_fingerprint TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,
                dedupe_sha256 TEXT NOT NULL,status TEXT NOT NULL,approval_id TEXT,failure_code TEXT,actor_ref TEXT NOT NULL,
                created_at TEXT NOT NULL,updated_at TEXT NOT NULL,UNIQUE(workspace_id,project_id,key_sha256));
                CREATE UNIQUE INDEX IF NOT EXISTS native_official_publish_duplicate_guard ON native_official_publications(workspace_id,dedupe_sha256)
                WHERE status NOT IN ('not_configured','cancelled');
                CREATE TABLE IF NOT EXISTS native_official_publish_approvals (
                approval_id TEXT PRIMARY KEY,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                grant_sha256 TEXT NOT NULL,grant_json TEXT NOT NULL,status TEXT NOT NULL,created_at TEXT NOT NULL,revoked_at TEXT);
                CREATE TABLE IF NOT EXISTS native_official_publish_events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,publication_id TEXT NOT NULL,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,
                action TEXT NOT NULL,actor_ref TEXT NOT NULL,evidence_json TEXT NOT NULL,created_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS native_official_publish_dispatches (
                publication_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,approval_id TEXT NOT NULL,
                phase TEXT NOT NULL,version INTEGER NOT NULL,total_bytes INTEGER NOT NULL,acknowledged_bytes INTEGER NOT NULL,
                private_session_ref TEXT,remote_post_id TEXT,intent_id TEXT,failure_code TEXT,updated_at TEXT NOT NULL);''')
            if con.execute('SELECT 1 FROM native_official_publications WHERE workspace_id!=? LIMIT 1',(self.workspace,)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKSPACE_CHANGED')
    def event(self,con,row,action,actor,**evidence):
        con.execute('INSERT INTO native_official_publish_events(publication_id,workspace_id,project_id,action,actor_ref,evidence_json,created_at) VALUES(?,?,?,?,?,?,?)',
            (row['publication_id'],self.workspace,row['project_id'],action,actor,json.dumps(evidence),now()))
    def row(self,con,project,identity):
        self.accounts.check_workspace();self.store.project(con.execute('SELECT * FROM projects WHERE id=?',(project,)).fetchone())
        row=con.execute('SELECT * FROM native_official_publications WHERE publication_id=? AND project_id=? AND workspace_id=?',(identity,project,self.workspace)).fetchone()
        if row is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLICATION_NOT_FOUND',404)
        return row
    def read(self,row):
        value=dict(row)
        try:
            snapshot=json.loads(value.pop('snapshot_json'));request=Create.model_validate({**snapshot['request'],'request_key':'internal-official-publish-key'});target=PublishingTargetBinding.model_validate(snapshot['target'])
            if (digest(snapshot)!=value['snapshot_sha256'] or snapshot['schema_version']!='native-official-publication-snapshot-v1'
                or value['workspace_id']!=self.workspace or snapshot['workspace_id']!=self.workspace or snapshot['project_id']!=value['project_id']
                or digest(snapshot['request'])!=value['request_fingerprint'] or target.workspace_id!=self.workspace or target.profile_id!=request.profile_id
                or target.platform!='youtube' or target.provider_key!='youtube-data-api-publishing' or snapshot['target_binding_sha256']!=target_digest(target)
                or snapshot['configuration_sha256']!=request.expected_configuration_sha256 or snapshot['dry_run_snapshot_sha256']!=request.expected_dry_run_snapshot_sha256
                or snapshot['project_revision']!=request.revision or type(snapshot['project_revision']) is not int or type(snapshot['mock']) is not bool
                or snapshot['dry_run_receipt_is_publish_authority'] is not False or snapshot['account_check_is_publish_authority'] is not False
                or snapshot['separate_owner_publish_approval_required'] is not True or snapshot['token_returned'] is not False
                or not re.fullmatch(r'[a-f0-9]{64}',snapshot['final_sha256']) or not re.fullmatch(r'[a-f0-9]{64}',snapshot['document_sha256'])
                or value['dedupe_sha256']!=digest({'workspace':self.workspace,'platform':target.platform,'account':target.target_account_id,'final':snapshot['final_sha256'],'mock':snapshot['mock']})
                or value['status'] not in {'not_configured','awaiting_publish_approval','queued','running','cancelled','review_required','completed'}):raise ValueError()
            size_bytes(snapshot['final_bytes']);value.pop('key_sha256')
            return {**value,'snapshot':snapshot,'schema_version':'native-official-publication-v1','mock':snapshot['mock'],'token_returned':False,'real_provider_tested':False}
        except (ValueError,TypeError,KeyError,PublishingWireError):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_EVIDENCE_CHANGED') from None
    def get(self,project,identity):
        with self.store.transaction() as con:return self.read(self.row(con,project,identity))
    def states(self):
        self.accounts.check_workspace()
        return {'schema_version':'native-official-publishing-factories-v1','workspace_id':self.workspace,'profiles':[f.public() for _,f in sorted(self.factories.items())],
            'automatic_publishing':False,'separate_owner_publish_approval_required':True,'token_returned':False,'real_provider_tested':False}
    def identity(self,principal=None,*,token_id=None,subject=None):
        try:
            verifier=self.identity_provider() if self.identity_provider else None
            if type(verifier) is not HumanAuthVerifier:raise ValueError()
            if principal is not None:
                if type(principal) is not HumanPrincipal or principal.role_for(self.workspace)!='owner':raise ValueError()
                token_id,subject=principal.token_id,principal.subject
            record=verifier.registry.tokens.get(token_id);instant=utc(self.clock())
            if record is None or not record.enabled or record.subject!=subject or utc(record.issued_at)>instant or utc(record.expires_at)<=instant or record.not_before is not None and utc(record.not_before)>instant:raise ValueError()
            current=HumanPrincipal(token_id=record.token_id,subject=record.subject,display_name=record.display_name,platform_role=record.platform_role,workspace_roles=record.workspace_roles,expires_at=record.expires_at)
            if current.role_for(self.workspace)!='owner' or principal is not None and current!=principal:raise ValueError()
            return {'token_id':record.token_id,'subject':record.subject,'identity_revision_sha256':digest(record.model_dump(mode='json')),'expires_at':utc(record.expires_at).isoformat()}
        except Exception:raise WorkflowError('NATIVE_HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED',403) from None
    def source(self,con,project,payload,factory):
        current=self.store.editable(con,project,payload.revision);parent=self.publications.get_row(con,project,payload.dry_run_publication_id)
        review,_=self.publications.revalidate(con,parent)
        if review['status']!='dry_run_succeeded' or review['snapshot_sha256']!=payload.expected_dry_run_snapshot_sha256 or review['snapshot']['request']['platform']!='youtube':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_VALIDATED_DRY_RUN_REQUIRED')
        check=self.accounts.read(self.accounts.row(con,project,payload.account_check_id));proof=check['result'];state=factory.public()
        if (check['status']!='succeeded' or proof is None or check['snapshot']['target']!=state['target'] or check['snapshot']['project_revision']!=current['revision']
            or check['snapshot']['document_sha256']!=digest(current['document']) or check['snapshot']['mock'] is not state['mock']):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CURRENT_ACCOUNT_PROOF_REQUIRED')
        account_factory=self.accounts.factories.get(check['account_ref'])
        if account_factory is None or account_factory.public()['status']!='CONFIGURED' or account_factory.sha256!=check['snapshot']['configuration_sha256']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CURRENT_ACCOUNT_PROOF_REQUIRED')
        if state['configuration_sha256']!=payload.expected_configuration_sha256:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED')
        job,actual,path=self.publications.render(con,project,review['snapshot']['request']['final_job_id']);qc=project_qc(job)
        from app.publishing_models import PublicationMetadata
        metadata=PublicationMetadata.model_validate(review['snapshot']['request']['metadata'])
        platform=validate_platform(capability=self.publications.capabilities.get('youtube'),metadata=metadata,render=SimpleNamespace(profile=PROFILES.get((qc.get('width'),qc.get('height')),'native-unmapped-profile'),qc_report=qc),output_asset=SimpleNamespace(size_bytes=path.stat().st_size),mode='live')
        if platform.status!='passed':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PLATFORM_VALIDATION_FAILED')
        # Pure metadata/disclosure admission only; this request is never dispatched here.
        start_request(metadata,path.stat().st_size,'EXPLICIT-UNSENT-PREFLIGHT-TOKEN',category_id=factory.profile.category_id,made_for_kids=factory.profile.made_for_kids,contains_synthetic_media=factory.profile.contains_synthetic_media,now=utc(self.clock()))
        return current,review,check,state,job,actual,path,platform.model_dump(mode='json')
    def create(self,project,payload,*,principal):
        authority=self.identity(principal);request=payload.model_dump(mode='json',exclude={'request_key'});key=digest(payload.request_key);fingerprint=digest(request)
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_official_publications WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior:
                if prior['request_fingerprint']!=fingerprint:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_IDEMPOTENCY_CONFLICT')
                return self.read(prior),True
            factory=self.factories.get(payload.profile_id)
            if factory is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_CONFIGURED')
            current,review,check,state,job,actual,path,platform=self.source(con,project,payload,factory)
            snapshot={'schema_version':'native-official-publication-snapshot-v1','workspace_id':self.workspace,'project_id':project,'project_revision':current['revision'],
                'document_sha256':digest(current['document']),'request':request,'dry_run_snapshot_sha256':review['snapshot_sha256'],'account_check_snapshot_sha256':check['snapshot_sha256'],
                'account_result_sha256':check['result_sha256'],'configuration_sha256':state['configuration_sha256'],'target':state['target'],'target_binding_sha256':state['target_binding_sha256'],
                'final_job_id':job['id'],'final_sha256':actual,'final_bytes':path.stat().st_size,'final_job_snapshot_sha256':digest(job['snapshot']),
                'final_review':job['final_review'],'validation':{'dry_run':review['snapshot']['validation'],'official_platform':platform},'metadata':review['snapshot']['request']['metadata'],
                'disclosures':state['disclosures'],'chunk_size':state['chunk_size'],'mock':state['mock'],'dry_run_receipt_is_publish_authority':False,'account_check_is_publish_authority':False,
                'separate_owner_publish_approval_required':True,'token_returned':False}
            dedupe=digest({'workspace':self.workspace,'platform':'youtube','account':state['target']['target_account_id'],'final':actual,'mock':state['mock']})
            if con.execute("SELECT 1 FROM native_official_publications WHERE workspace_id=? AND dedupe_sha256=? AND status NOT IN ('not_configured','cancelled')",(self.workspace,dedupe)).fetchone():raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_DUPLICATE_REVIEW_REQUIRED')
            stamp=now();identity='nopu_'+uuid.uuid4().hex;status='awaiting_publish_approval' if state['status']=='CONFIGURED' else 'not_configured'
            con.execute('INSERT INTO native_official_publications VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,fingerprint,digest(snapshot),json.dumps(snapshot),dedupe,status,None,None,authority['token_id'],stamp,stamp))
            row=self.row(con,project,identity);self.event(con,row,'official.publication.review.created',authority['token_id'],status=status,mock=state['mock'],external_action=False)
            return self.read(row),False
    def revalidate(self,con,row):
        value=self.read(row);snapshot=value['snapshot'];payload=Create.model_validate({**snapshot['request'],'request_key':'internal-official-publish-key'});factory=self.factories.get(payload.profile_id)
        if factory is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED')
        current,review,check,state,job,actual,path,platform=self.source(con,row['project_id'],payload,factory)
        expected={'document_sha256':digest(current['document']),'account_check_snapshot_sha256':check['snapshot_sha256'],'account_result_sha256':check['result_sha256'],
            'final_job_id':job['id'],'final_sha256':actual,'final_bytes':path.stat().st_size,'final_job_snapshot_sha256':digest(job['snapshot']),'final_review':job['final_review'],
            'validation':{'dry_run':review['snapshot']['validation'],'official_platform':platform},'target':state['target'],'target_binding_sha256':state['target_binding_sha256'],
            'metadata':review['snapshot']['request']['metadata'],'disclosures':state['disclosures'],'chunk_size':state['chunk_size'],'mock':state['mock']}
        if state['status']!='CONFIGURED' or any(snapshot[k]!=v for k,v in expected.items()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_REVIEW_BINDING_CHANGED')
        return value,factory,path
    def approve(self,project,identity,payload,*,principal):
        authority=self.identity(principal)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value,_,_=self.revalidate(con,row)
            if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_REVIEW_BINDING_CHANGED')
            if row['status']=='queued' and row['approval_id']:
                self.valid_grant(con,row);return self.read(row)
            if row['status']!='awaiting_publish_approval':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_REVIEWABLE')
            instant=utc(self.clock());expires=min(instant+timedelta(seconds=payload.valid_for_seconds),datetime.fromisoformat(authority['expires_at']))
            if (expires-instant).total_seconds()<60:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_OWNER_TOKEN_EXPIRING')
            grant={'schema_version':'native-official-publish-approval-v1','publication_id':identity,'workspace_id':self.workspace,'project_id':project,
                'snapshot_sha256':row['snapshot_sha256'],'authority':authority,'issued_at':instant.isoformat(),'expires_at':expires.isoformat(),
                'acknowledged_official_publication':True,'dry_run_approval_reused':False,'mock':value['snapshot']['mock']}
            approval='nopa_'+uuid.uuid4().hex;stamp=now()
            con.execute('INSERT INTO native_official_publish_approvals VALUES(?,?,?,?,?,?,?,?,?)',(approval,identity,self.workspace,project,digest(grant),json.dumps(grant),'active',stamp,None))
            con.execute("UPDATE native_official_publications SET status='queued',approval_id=?,updated_at=? WHERE publication_id=?",(approval,stamp,identity))
            con.execute('INSERT INTO native_official_publish_dispatches VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,row['snapshot_sha256'],approval,'prepared',1,value['snapshot']['final_bytes'],0,None,None,None,None,stamp))
            self.event(con,row,'official.publication.approved',authority['token_id'],approval_id=approval,mock=grant['mock'],external_action=False)
            return self.read(self.row(con,project,identity))
    def valid_grant(self,con,row):
        grant_row=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=? AND workspace_id=? AND project_id=?',(row['approval_id'],row['publication_id'],self.workspace,row['project_id'])).fetchone()
        try:
            if grant_row is None or grant_row['status']!='active' or grant_row['revoked_at'] is not None:raise ValueError()
            grant=json.loads(grant_row['grant_json']);issued=utc(datetime.fromisoformat(grant['issued_at']));expires=utc(datetime.fromisoformat(grant['expires_at']));instant=utc(self.clock())
            if (digest(grant)!=grant_row['grant_sha256'] or grant['schema_version']!='native-official-publish-approval-v1'
                or any(grant[k]!=row[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256'))
                or grant['acknowledged_official_publication'] is not True or grant['dry_run_approval_reused'] is not False
                or grant['mock'] is not self.read(row)['snapshot']['mock'] or not issued<=instant<expires or not 60<=(expires-issued).total_seconds()<=3600):raise ValueError()
            authority=self.identity(token_id=grant['authority']['token_id'],subject=grant['authority']['subject'])
            if authority!=grant['authority']:raise ValueError()
            return grant
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CURRENT_OWNER_GRANT_REQUIRED') from None
    def admission(self,project,identity,*,con=None):
        with (self.store.transaction() if con is None else nullcontext(con)) as con:
            row=self.row(con,project,identity)
            if row['status'] not in ('queued','running'):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_DISPATCHABLE')
            self.valid_grant(con,row);value,factory,path=self.revalidate(con,row)
            dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(identity,)).fetchone()
            if (dispatch is None or any(dispatch[k]!=row[k] for k in ('workspace_id','project_id','snapshot_sha256','approval_id'))
                or dispatch['total_bytes']!=value['snapshot']['final_bytes'] or type(dispatch['version']) is not int or dispatch['version']<1
                or not 0<=dispatch['acknowledged_bytes']<=dispatch['total_bytes']):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_DISPATCH_BINDING_CHANGED')
            return value,factory,path,dict(dispatch)
    def cancel(self,project,identity,payload,*,principal):
        authority=self.identity(principal)
        with self.store.transaction() as con:
            row=self.row(con,project,identity);value=self.read(row)
            if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_REVIEW_BINDING_CHANGED')
            dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(identity,)).fetchone()
            if row['status']=='completed' or dispatch is not None and dispatch['phase']!='prepared':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_EXTERNAL_RECONCILIATION_REQUIRED')
            if row['status']!='cancelled':
                con.execute("UPDATE native_official_publications SET status='cancelled',updated_at=? WHERE publication_id=?",(now(),identity))
                con.execute("UPDATE native_official_publish_approvals SET status='revoked',revoked_at=? WHERE publication_id=? AND status='active'",(now(),identity))
                self.event(con,row,'official.publication.cancelled',authority['token_id'],external_action=False)
            return self.read(self.row(con,project,identity))
