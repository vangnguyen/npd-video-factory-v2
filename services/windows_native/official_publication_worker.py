"""One explicit fenced YouTube step; no automatic/live factory activation.

Uses existing official protocol and cost primitives with owned Native journals.
No shared ORM, browser publishing, OAuth acquisition or remote deletion.
"""
import asyncio,hashlib,re,uuid
from dataclasses import replace
from contextlib import suppress
from .contracts import WorkflowError,digest,file_sha
from .costs import CostLedger
from .official_publications import NativeOfficialPublications,preflight
from .official_publication_sessions import SessionVault
from app.publishing_credentials import PublishingCredentialError,youtube_account_request,confirm_youtube_account
from app.publishing_models import PublicationMetadata
from app.publishing_wire import PublishingWireError
from app.analytics_official import response_digest
from app.youtube_upload import start_request,started_session,status_request,chunk_request,upload_progress,video_status_request,video_observation

def code(error):
    value=error.code if isinstance(error,(WorkflowError,PublishingCredentialError,PublishingWireError)) else 'NATIVE_OFFICIAL_PUBLISH_WORKER_FAILED'
    return value if isinstance(value,str) and re.fullmatch(r'[A-Z0-9_]{1,120}',value) else 'NATIVE_OFFICIAL_PUBLISH_WORKER_FAILED'

def retry_delay(response):
    value=response.headers.get('retry-after','')
    return int(value) if isinstance(value,str) and re.fullmatch(r'[0-9]{1,4}',value) and 1<=int(value)<=3600 else 30

class NativeOfficialPublicationWorker:
    def __init__(self,journal,vault):
        if type(journal) is not NativeOfficialPublications or type(vault) is not SessionVault or vault.journal is not journal:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKER_CONFIGURATION_INVALID',400)
        self.journal,self.vault=journal,vault;self.frozen_journal,self.frozen_vault=journal,vault;self.costs=CostLedger(journal.store)
    def check(self):
        if self.journal is not self.frozen_journal or self.vault is not self.frozen_vault or self.vault.journal is not self.journal or self.costs.store is not self.journal.store:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKER_CONFIGURATION_CHANGED')
        if not self.vault.configured():raise WorkflowError('NATIVE_OFFICIAL_SESSION_NOT_CONFIGURED')
    def context(self,project,identity,version,ticket=None,*,guard=None):
        if guard is not None:guard()
        self.check()
        with self.journal.store.transaction() as con:
            value,factory,path,dispatch=self.journal.admission(project,identity,con=con)
            if dispatch['version']!=version:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKER_STALE')
            if ticket is not None:self.journal.ticket(con,ticket)
            self.journal.eligible(con,project,identity,value)
            if dispatch['phase'] in ('prepared','init_intent'):
                preflight(PublicationMetadata.model_validate(value['snapshot']['metadata']),dispatch['total_bytes'],factory.profile,self.journal.clock())
        if guard is not None:guard()
        return value,factory,path,dispatch
    def send(self,project,identity,version,factory,credential,request,operation,*,ticket=None,guard=None):
        value,current,_,_=self.context(project,identity,version,ticket,guard=guard)
        if current is not factory or factory.credential(now=self.journal.clock())!=credential:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CREDENTIAL_CHANGED')
        # No private URL, bearer or raw response enters SQLite/audit/cost rows.
        cost=self.costs.begin(project_id=project,provider='official-youtube',model=None,operation=operation+'.'+(ticket.intent_id if ticket is not None else uuid.uuid4().hex),
            request_sha256=digest({'publication_id':identity,'snapshot_sha256':value['snapshot_sha256'],'version':version,'operation':operation,'body_sha256':hashlib.sha256(request.body).hexdigest()}),
            external_call=not value['mock'],paid=False,estimated_cost=None)
        sent=False
        try:
            self.context(project,identity,version,ticket,guard=guard)
            if factory.credential(now=self.journal.clock())!=credential:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CREDENTIAL_CHANGED')
            if guard is not None:guard()
            sent=True;response=asyncio.run(factory.client.request(request))
            self.costs.settle(cost,status='response_received',response_sha256=response_digest(response))
            return response
        except Exception as error:
            self.costs.settle(cost,status='outcome_unknown' if sent else 'rejected',error_code=code(error));raise
    def account(self,project,identity,version,factory,credential,*,guard=None):
        response=self.send(project,identity,version,factory,credential,youtube_account_request(credential),'publish_account_lookup',guard=guard)
        if response.status==429 or response.status>=500:
            self.journal.read_backoff(project,identity,version,'publish_account_lookup',retry_delay(response),response_digest(response))
            raise PublishingWireError('NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF',retry_after=retry_delay(response))
        confirm_youtube_account(response,credential.target);self.context(project,identity,version,guard=guard)
    def step(self,project,identity,expected_version,*,guard=None):
        if type(expected_version) is not int:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKER_VERSION_INVALID',400)
        value,factory,path,dispatch=self.context(project,identity,expected_version,guard=guard);phase=dispatch['phase'];ticket=None
        if phase not in ('prepared','uploading','reconciliation_required'):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_STEP_REVIEW_REQUIRED')
        upload=None if phase=='prepared' else self.vault.load(project,identity)
        credential=factory.credential(now=self.journal.clock());self.account(project,identity,expected_version,factory,credential,guard=guard)
        try:
            if phase=='prepared':
                profile=factory.profile;request=start_request(PublicationMetadata.model_validate(value['snapshot']['metadata']),dispatch['total_bytes'],credential.token,
                    category_id=profile.category_id,made_for_kids=profile.made_for_kids,contains_synthetic_media=profile.contains_synthetic_media,now=self.journal.clock())
                ticket=self.journal.begin_intent(project,identity,expected_version,'init')
                response=self.send(project,identity,ticket.version,factory,credential,request,'upload_initialize',ticket=ticket,guard=guard)
                self.vault.save(ticket,started_session(response,dispatch['total_bytes']))
            else:
                if phase=='reconciliation_required':
                    request=status_request(upload,credential.token);ticket=self.journal.begin_intent(project,identity,expected_version,'reconcile')
                else:
                    start=dispatch['acknowledged_bytes'];length=min(factory.profile.chunk_size,dispatch['total_bytes']-start)
                    if not length:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_COMPLETION_RECONCILIATION_REQUIRED')
                    with path.open('rb') as source:source.seek(start);content=source.read(length)
                    if len(content)!=length or file_sha(path)!=value['snapshot']['final_sha256']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_ARTIFACT_CHANGED')
                    request=chunk_request(upload,start,content,credential.token,chunk_size=factory.profile.chunk_size)
                    ticket=self.journal.begin_intent(project,identity,expected_version,'chunk',range_start=start,range_end=start+length,body_sha256=hashlib.sha256(content).hexdigest())
                response=self.send(project,identity,ticket.version,factory,credential,request,'upload_'+ticket.operation,ticket=ticket,guard=guard)
                progress=upload_progress(response,upload)
                if progress.status=='reconciliation_required':progress=replace(progress,retry_after=retry_delay(response))
                self.journal.finish_progress(ticket,progress,response_digest(response))
        except Exception as error:
            if ticket is not None:
                with suppress(WorkflowError):self.journal.uncertain(ticket,code(error))
            raise WorkflowError(code(error)) from None
        return self.journal.state(project,identity)
    def poll_processing(self,project,identity,expected_version,*,guard=None):
        value,factory,_,dispatch=self.context(project,identity,expected_version,guard=guard)
        if dispatch['phase']!='uploaded' or dispatch['remote_post_id'] is None:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PROCESSING_UPLOAD_REQUIRED')
        credential=factory.credential(now=self.journal.clock());self.account(project,identity,expected_version,factory,credential,guard=guard)
        response=self.send(project,identity,expected_version,factory,credential,video_status_request(dispatch['remote_post_id'],credential.token),'publish_processing_status',guard=guard)
        if response.status==429 or response.status>=500:
            self.journal.read_backoff(project,identity,expected_version,'publish_processing_status',retry_delay(response),response_digest(response))
            raise PublishingWireError('NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF',retry_after=retry_delay(response))
        observation=video_observation(response,dispatch['remote_post_id'])
        return self.journal.record_processing(project,identity,expected_version,observation,response_digest(response))
    def recover(self):
        """Owned startup only. Finalize unfinished costs without credential reads."""
        if self.journal is not self.frozen_journal or self.vault is not self.frozen_vault or self.costs.store is not self.journal.store:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKER_CONFIGURATION_CHANGED')
        self.journal.accounts.check_workspace();result=self.journal.recover();settled=0
        with self.journal.store.transaction() as con:
            rows=con.execute("SELECT c.* FROM native_cost_operations c WHERE c.provider='official-youtube' AND c.paid=0 AND c.status='dispatch_intent' AND EXISTS(SELECT 1 FROM native_official_publications p WHERE p.project_id=c.project_id AND p.workspace_id=?)",(self.journal.workspace,)).fetchall()
        for row in rows:
            if not re.fullmatch(r'(publish_account_lookup|publish_processing_status|upload_initialize|upload_chunk|upload_reconcile)\.[a-f0-9]{32}',row['operation']):continue
            self.costs.settle(row['id'],status='outcome_unknown',error_code='NATIVE_OFFICIAL_PUBLISH_RESTART_OUTCOME_UNKNOWN');settled+=1
        return {**result,'unfinished_costs_marked_unknown':settled,'automatic_upload_retry':False}
