"""Explicit TikTok steps through the common Owner/ticket/cost/queue fences."""
import hashlib
from contextlib import suppress
from app.publishing_models import PublicationMetadata
from app.publishing_wire import PublishingWireError
from app.analytics_official import response_digest
from app.tiktok_credentials import account_request,confirm_account
from app.tiktok_upload import ChunkPlan,PostChoices,creator_request,creator_info,start_request,started_session,chunk_request,chunk_ack,status_request,post_observation
from .contracts import WorkflowError,file_sha
from . import tiktok_publishing as records
def backed_off(worker,project,identity,version,response,operation):
    if response.status==429 or response.status>=500:
        from .official_publication_worker import retry_delay
        delay=retry_delay(response);worker.journal.read_backoff(project,identity,version,operation,delay,response_digest(response))
        raise PublishingWireError('NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF',retry_after=delay)
def account(worker,project,identity,version,factory,credential,*,guard=None):
    response,cost=worker.send(project,identity,version,factory,credential,account_request(credential),'publish_account_lookup',guard=guard,with_cost=True)
    backed_off(worker,project,identity,version,response,'publish_account_lookup');proof=confirm_account(response,credential.target);worker.context(project,identity,version,guard=guard)
    return proof,cost,response_digest(response)
def step(worker,project,identity,version,*,guard=None):
    from .official_publication_worker import code
    value,factory,path,dispatch=worker.context(project,identity,version,guard=guard);phase=dispatch['phase'];ticket=None
    if phase not in {'prepared','uploading','reconciliation_required'}:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_STEP_REVIEW_REQUIRED')
    upload=worker.vault.load(project,identity) if phase=='uploading' else None
    credential=factory.credential(now=worker.journal.clock());account_proof,account_cost,account_sha=account(worker,project,identity,version,factory,credential,guard=guard)
    try:
        if phase=='prepared':
            response,creator_cost=worker.send(project,identity,version,factory,credential,creator_request(credential.token),'publish_creator_lookup',guard=guard,with_cost=True)
            backed_off(worker,project,identity,version,response,'publish_creator_lookup');info=creator_info(response);worker.context(project,identity,version,guard=guard)
            proof=records.record_preflight(worker.journal,project,identity,version,info,account_proof,account_cost,account_sha,creator_cost,response_digest(response))
            s=value['snapshot'];plan=ChunkPlan(dispatch['total_bytes'],s['chunk_size']);issued=worker.journal.clock()
            request=start_request(PublicationMetadata.model_validate(s['metadata']),plan,credential.token,creator=info,choices=PostChoices.model_validate(s['choices']),duration_sec=s['duration_seconds'],
                client_audited=s['disclosures']['api_client_audited'],media_location=s['disclosures']['media_location'])
            ticket=worker.journal.begin_intent(project,identity,version,'init',creator_preflight_id=proof['proof']['check_id'])
            response,cost=worker.send(project,identity,ticket.version,factory,credential,request,'upload_initialize',ticket=ticket,guard=guard,with_cost=True)
            worker.vault.save(ticket,started_session(response,plan,now=issued),cost_operation_id=cost,response_sha256=response_digest(response))
        else:
            if phase=='uploading':
                offset=dispatch['acknowledged_bytes'];length=upload.plan.length(offset)
                with path.open('rb') as source:source.seek(offset);content=source.read(length)
                if len(content)!=length or file_sha(path)!=value['snapshot']['final_sha256']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_ARTIFACT_CHANGED')
                request=chunk_request(upload,offset,content,now=worker.journal.clock());ticket=worker.journal.begin_intent(project,identity,version,'chunk',range_start=offset,range_end=offset+length,body_sha256=hashlib.sha256(content).hexdigest())
            else:
                with worker.journal.store.transaction() as con:provider=records.job(con,value)
                request=status_request(provider['provider_job_id'],credential.token);ticket=worker.journal.begin_intent(project,identity,version,'reconcile')
            response,cost=worker.send(project,identity,ticket.version,factory,credential,request,'upload_'+ticket.operation,ticket=ticket,guard=guard,with_cost=True)
            if ticket.operation=='chunk':records.finish_upload(worker.journal,ticket,chunk_ack(response,upload.plan,offset),response_digest(response),cost)
            elif response.status==429 or response.status>=500:
                from .official_publication_worker import retry_delay
                delay=retry_delay(response);records.reconcile_backoff(worker.journal,ticket,response_digest(response),cost,delay)
                raise PublishingWireError('NATIVE_OFFICIAL_PUBLISH_READ_BACKOFF',retry_after=delay)
            else:records.finish_upload(worker.journal,ticket,None,response_digest(response),cost,obs=post_observation(response,total_bytes=dispatch['total_bytes']))
    except Exception as error:
        if ticket is not None:
            with suppress(WorkflowError):worker.journal.uncertain(ticket,code(error))
        raise WorkflowError(code(error)) from None
    return worker.journal.state(project,identity)
def poll(worker,project,identity,version,*,guard=None):
    value,factory,_,dispatch=worker.context(project,identity,version,guard=guard)
    if dispatch['phase']!='uploaded' or dispatch['acknowledged_bytes']!=dispatch['total_bytes']:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PROCESSING_UPLOAD_REQUIRED')
    with worker.journal.store.transaction() as con:provider=records.job(con,value)
    credential=factory.credential(now=worker.journal.clock());account(worker,project,identity,version,factory,credential,guard=guard)
    requested_at=worker.journal.clock();response,cost=worker.send(project,identity,version,factory,credential,status_request(provider['provider_job_id'],credential.token),'publish_processing_status',guard=guard,with_cost=True)
    backed_off(worker,project,identity,version,response,'publish_processing_status')
    return records.processing(worker.journal,project,identity,version,value['approval_id'],post_observation(response,total_bytes=dispatch['total_bytes']),response_digest(response),cost,requested_at)
