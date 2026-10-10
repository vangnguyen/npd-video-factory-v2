"""Explicit asynchronous Meta steps using scoped official protocol, never a browser."""
import hashlib
from app.analytics_official import response_digest
from app.publishing_models import PublicationMetadata
from app.publishing_wire import PublishingWireError
from app.meta_publishing_credentials import page_identity_request,instagram_identity_request,confirm_page_identity,confirm_instagram_identity
from app import meta_publishing_protocol as protocol
from .contracts import WorkflowError
from .publishing_media_delivery import NativePublishingMediaDelivery
from . import meta_publishing as journal


class NativeMetaExecutor:
    def __init__(self,worker,media):
        if type(media) is not NativePublishingMediaDelivery or media.journal is not worker.journal:
            raise WorkflowError('NATIVE_META_PUBLISH_MEDIA_BINDING_INVALID',400)
        self.worker,self.media=worker,media;self.frozen=(worker,media,worker.journal,worker.costs,media.store,media.workspace,media.factory)
    def check(self,value,phase):
        if (self.worker,self.media,self.worker.journal,self.worker.costs,self.media.store,self.media.workspace,self.media.factory)!=self.frozen:
            raise WorkflowError('NATIVE_META_PUBLISH_MEDIA_BINDING_CHANGED')
        if self.media.factory is None or self.media.factory.sha256!=value['snapshot']['media_configuration_sha256']:
            raise WorkflowError('NATIVE_META_PUBLISH_MEDIA_NOT_CONFIGURED')
        self.media.factory.check_configuration()
        if phase in {'prepared','meta_init_intent','meta_created','meta_transfer_intent'}:self.media.factory.check()
        if self.media.factory.wire.mock is not value['mock']:raise WorkflowError('NATIVE_META_PUBLISH_MEDIA_MODE_CHANGED')
    def selected(self,value,*,resolve=False):
        with self.media.store.transaction() as con:b=journal.binding(self.worker.journal,con,value)
        if b is None:raise WorkflowError('NATIVE_META_PUBLISH_MEDIA_SELECTION_REQUIRED')
        lease=None
        if resolve:
            lease=self.media.resolve_for_consumer(value['project_id'],b['binding']['request']['media_delivery_id'],
                publication_snapshot_sha256=value['snapshot_sha256'],consumer_mock=value['mock'])
        return b,lease
    def preflight(self,project,identity,version,factory,credential,*,guard=None):
        from .official_publication_worker import retry_delay
        proofs=[]
        operations=[('meta_page_lookup',page_identity_request(credential),confirm_page_identity)]
        if factory.profile.target.platform=='instagram_reels':operations.append(('meta_instagram_lookup',instagram_identity_request(credential),confirm_instagram_identity))
        for name,request,confirm in operations:
            response,cost=self.worker.send(project,identity,version,factory,credential,request,name,guard=guard,with_cost=True)
            if response.status==429 or response.status>=500:
                self.worker.journal.read_backoff(project,identity,version,name,retry_delay(response),response_digest(response))
                raise WorkflowError('NATIVE_META_PUBLISH_READ_BACKOFF')
            confirm(response,credential);proofs.append({'operation':name,'cost_operation_id':cost,'response_sha256':response_digest(response)})
        return journal.record_preflight(self.worker.journal,project,identity,version,proofs)
    def step(self,project,identity,version,*,guard=None,read_only=False):
        from .official_publication_worker import code,retry_delay
        value,factory,_,dispatch=self.worker.context(project,identity,version,guard=guard);phase=dispatch['phase'];platform=factory.profile.target.platform
        if phase in {'meta_init_unconfirmed','review_required','uploaded'}:raise WorkflowError('NATIVE_META_PUBLISH_RECONCILIATION_REVIEW_REQUIRED')
        original=None
        with self.media.store.transaction() as con:original=journal.job(self.worker.journal,con,value)
        credential=factory.credential(now=self.worker.journal.clock());target=factory.profile.graph();content=PublicationMetadata.model_validate(value['snapshot']['metadata'])
        binding=None;proof=None
        if phase=='prepared':
            if read_only:raise WorkflowError('NATIVE_META_PUBLISH_ORIGINAL_JOB_REQUIRED')
            binding,lease=self.selected(value,resolve=True)
            request=(protocol.fb_create_request(target,credential.token) if platform=='facebook' else protocol.ig_create_request(target,content,credential.token,
                video_url=lease.url,authorized_prefix=self.media.factory.profile.public_prefix,share_to_feed=factory.options.share_to_feed));operation='meta_init'
        elif phase=='meta_created':
            if read_only:raise WorkflowError('NATIVE_META_PUBLISH_UPLOAD_NOT_SUBMITTED')
            binding,lease=self.selected(value,resolve=True);job_id=original['provider_job_id']
            session=protocol.FacebookUploadSession(target,job_id,f'https://rupload.facebook.com/video-upload/{target.api_version}/{job_id}')
            request=protocol.fb_upload_request(session,credential.token,video_url=lease.url,authorized_prefix=self.media.factory.profile.public_prefix);operation='meta_transfer'
        elif phase=='meta_finish_ready' and not read_only:
            job_id=original['provider_job_id']
            if platform=='facebook':request=protocol.fb_finish_request(target,job_id,content,credential.token,video_state='DRAFT' if content.privacy=='private' else 'PUBLISHED')
            else:request=protocol.ig_publish_request(target,protocol.ContainerObservation(target,job_id,'FINISHED'),credential.token)
            operation='meta_finish'
        else:
            if original is None:raise WorkflowError('NATIVE_META_PUBLISH_ORIGINAL_JOB_REQUIRED')
            if phase not in {'meta_processing','meta_transfer_unconfirmed','meta_finish_unconfirmed','meta_finish_ready'}:raise WorkflowError('NATIVE_META_PUBLISH_STEP_INVALID')
            job_id=original['provider_job_id'];request=protocol.fb_status_request(target,job_id,credential.token) if platform=='facebook' else protocol.ig_container_request(target,job_id,credential.token);operation='meta_status'
        if operation!='meta_status':proof=self.preflight(project,identity,version,factory,credential,guard=guard)
        # Resolve again after preflight: no URL dispatch can outlive its consent
        # or private lease merely because identity reads took time.
        if binding is not None:
            current,current_lease=self.selected(value,resolve=True)
            if current['binding']['binding_id']!=binding['binding']['binding_id'] or current['sha256']!=binding['sha256'] or current_lease!=lease:
                raise WorkflowError('NATIVE_META_MEDIA_SELECTION_CHANGED')
        ticket=journal.begin(self.worker.journal,project,identity,version,operation,hashlib.sha256(request.body).hexdigest(),
            binding_id=binding['binding']['binding_id'] if binding is not None else None,preflight_id=proof['proof']['proof_id'] if proof is not None else None)
        response=None;cost=None
        try:
            response,cost=self.worker.send(project,identity,ticket.version,factory,credential,request,operation,ticket=ticket,guard=guard,with_cost=True)
            if operation=='meta_init':
                job_id=protocol.fb_created_session(response,target).video_id if platform=='facebook' else protocol.created_id(response)
                outcome=journal.Outcome(operation=operation,provider_job_id=job_id,operation_confirmed=True,mock=value['mock'])
            elif operation=='meta_transfer':
                outcome=journal.Outcome(operation=operation,provider_job_id=original['provider_job_id'],operation_confirmed=protocol.confirmed_success(response),mock=value['mock'])
            elif operation=='meta_finish':
                remote=protocol.created_id(response) if platform=='instagram_reels' else None
                confirmed=True if remote is not None else protocol.confirmed_success(response)
                outcome=journal.Outcome(operation=operation,provider_job_id=original['provider_job_id'],remote_post_id=remote,operation_confirmed=confirmed,mock=value['mock'])
            elif platform=='instagram_reels':
                observation=protocol.ig_container_observation(response,target,original['provider_job_id'])
                outcome=journal.Outcome(operation=operation,provider_job_id=observation.container_id,provider_status=observation.provider_status,mock=value['mock'])
            else:
                observation=protocol.fb_observation(response,original['provider_job_id'])
                outcome=journal.Outcome(operation=operation,provider_job_id=observation.video_id,provider_status=observation.video_status,
                    uploading_phase=observation.uploading_phase,processing_phase=observation.processing_phase,publishing_phase=observation.publishing_phase,
                    processing_progress=observation.processing_progress,mock=value['mock'])
        except Exception as error:
            if cost is None:
                with self.media.store.transaction() as con:
                    row=con.execute('SELECT id FROM native_cost_operations WHERE project_id=? AND provider=? AND operation=?',
                        (project,'official-'+platform,operation+'.'+ticket.intent_id)).fetchone()
                    cost=row['id'] if row is not None else None
            outcome=journal.Outcome(operation=operation,provider_job_id=original['provider_job_id'] if original is not None else None,error_code=code(error),mock=value['mock'])
        result=journal.finish(self.worker.journal,ticket,outcome,cost,response_digest(response) if response is not None else None,
            binding_id=binding['binding']['binding_id'] if binding is not None else None,preflight_id=proof['proof']['proof_id'] if proof is not None else None)
        if operation=='meta_status' and response is not None and (response.status==429 or response.status>=500):
            self.worker.journal.read_backoff(project,identity,result['dispatch']['version'],operation,retry_delay(response),response_digest(response));result=self.worker.journal.state(project,identity)
        return result
