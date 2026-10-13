"""Durable asynchronous analysis; ambiguous work is never dispatched again."""
import asyncio
import copy
import json
from datetime import timedelta
from decimal import Decimal
from sqlalchemy import select, update
from .auto_edit_db import AutoEditAnalysisORM, TranscriptORM
from .auto_edit_job_db import AutoEditJobORM
from .auto_edit_job_repository import AutoEditJobRepository, AnalysisJobConflict, check, immutable, live_lease, transition
from .auto_edit_models import AutoEditAnalysisRequest
from .auto_edit_local_evidence import frozen_video_binding
from .auto_edit_source_custody import staged_trusted_video, trusted_video_snapshot, trusted_video_in_session, verify_file
from .local_video_transcription_provider import completed_io
from .db import JobORM, utc_now
from .auto_edit_providers import ProviderNotConfigured
from .provider_safety import ProviderSafetyBlocked, ProviderTransientError
from .uploaded_audio_repository import digest

ANALYSIS_QUEUE = 'npd:video-factory:v3:analysis:queued'


def provider_snapshot(provider):
    value={name:getattr(provider,name,None) for name in ('key','model','capability','external_call','paid','credential_alias',
        'language','response_format','timestamp_granularities','max_file_bytes','max_duration_seconds','algorithm_version')}
    value['adapter']=type(provider).__module__+'.'+type(provider).__qualname__
    value['estimated_cost_vnd']=str(provider.estimated_cost_vnd)
    value['immutable_binding']=copy.deepcopy(getattr(provider,'immutable_binding',None))
    profile=getattr(provider,'asr_prompt_profile',None)
    value['asr_prompt_profile']=profile.model_dump(mode='json') if hasattr(profile,'model_dump') else profile
    return json.loads(json.dumps(value,allow_nan=False))


class AnalysisClaim:
    def __init__(self,service,value,token,fingerprint):
        self.service,self.value,self.token,self.fingerprint=service,value,token,fingerprint
        self.job_id=value['job_id']

    async def lock(self,session):
        row=await self.service.repository.relation(session,self.value['project_id'],self.job_id,lock=True)
        job=await session.scalar(select(JobORM).where(JobORM.job_id==self.job_id).with_for_update()
            .execution_options(populate_existing=True))
        check(row,job,self.value)
        if job.status!='running' or row.claim_id!=self.token or not live_lease(row):
            raise AnalysisJobConflict('VIDEO_JOB_CLAIM_REVOKED')
        self.row,self.job=row,job

    async def validate(self,session,analysis):
        source=self.value['source_json']
        if (analysis.analysis_id!=self.value['analysis_id'] or analysis.workspace_id!=self.value['workspace_id']
            or analysis.project_id!=self.value['project_id'] or analysis.asset_id!=source['asset_id']
            or analysis.fingerprint!=self.fingerprint or analysis.status!='analyzing'
            or analysis.configuration_json!=self.value['configuration_json']
            or analysis.source_media_json!=source['media_metadata']
            or analysis.provenance_json.get('source_asset_checksum')!=source['source_sha256']
            or await session.scalar(select(TranscriptORM.transcript_id).where(TranscriptORM.analysis_id==analysis.analysis_id))):
            raise AnalysisJobConflict('VIDEO_ANALYSIS_CHANGED')
        current=await trusted_video_in_session(session,self.value['project_id'],source['asset_id'],
            source['storage_provider'],self.value['provider_json']['max_source_bytes'])
        if current!=source:raise AnalysisJobConflict('VIDEO_SOURCE_CHANGED')
        await self.service.verify_runtime(self.value['provider_json'])
        # Runtime verification can take time; the lease must still authorize commit.
        if not live_lease(self.row):raise AnalysisJobConflict('VIDEO_JOB_CLAIM_REVOKED')

    async def before_execute(self,prepared):
        if prepared['fingerprint']!=self.fingerprint:
            raise AnalysisJobConflict('VIDEO_ANALYSIS_BINDING_CHANGED')
        async with self.service.session_factory() as session:
            async with session.begin():
                await self.lock(session)
                analysis=await session.get(AutoEditAnalysisORM,self.value['analysis_id'],with_for_update=True)
                await self.validate(session,analysis)

    async def verify_original_file(self,path):
        source=self.value['source_json']
        await verify_file(path,source)
        async with staged_trusted_video(self.service.analysis_service.repository,self.service.analysis_service.object_storage,
            self.value['project_id'],source['asset_id'],self.service.analysis_service.staging_root,
            self.value['provider_json']['max_source_bytes'],expected=source):
            await self.service.verify_runtime(self.value['provider_json'])

    async def record_result(self,result):
        """Keep actual provider billing independent of downstream/job acceptance."""
        provider=self.value['provider_json']['transcription']
        receipt=result.receipt.model_dump(mode='json')
        capability=provider.get('capability') or 'transcription'
        if (receipt['provider_key']!=provider['key'] or receipt['capability']!=capability
            or receipt['external_call']!=provider['external_call'] or receipt['paid']!=provider['paid']):
            raise AnalysisJobConflict('VIDEO_PROVIDER_RECEIPT_CHANGED')
        estimate=provider['estimated_cost_vnd']
        # Keep the existing frozen 'None' representation and binding hash;
        # nullable provider estimates remain SQL NULL, never an invented zero.
        estimate=None if estimate is None or estimate=='None' else Decimal(estimate)
        media=self.value['source_json']['media_metadata']
        await self.service.analysis_service.platform.record_provider_operation(
            workspace_id=self.value['workspace_id'],project_id=self.value['project_id'],job_id=self.job_id,
            provider_key=provider['key'],capability=capability,
            operation='auto-edit-transcript:'+self.value['analysis_id'],model=provider['model'],
            units=Decimal(str(media['duration_seconds']))/Decimal('60'),unit_name='audio_minute',
            estimated_cost=estimate,actual_cost=result.value.actual_cost_vnd,
            metadata={'fixture':bool(result.value.provenance.get('fixture',False)),
                'external_call':provider['external_call'],'consumer_acceptance_pending':True,'human_accepted':False,
                'actual_cost_known':result.value.actual_cost_vnd is not None,'budget_reservation_is_billed_cost':False,
                'receipt':receipt})

    async def is_cancelled(self):
        async with self.service.session_factory() as session:
            row=await session.get(AutoEditJobORM,self.value['relation_id'])
            job=await session.get(JobORM,self.job_id)
            if row is None or job is None:return True
            try:check(row,job,self.value)
            except AnalysisJobConflict:return True
            return job.status!='running' or row.claim_id!=self.token or not live_lease(row)

    async def complete(self,session,analysis):
        # Called inside the real transcript/scenes transaction; no separate terminal write.
        # A slow awaited result flush can consume the lease after validate().
        # These locked durable objects must still fence the terminal transition.
        check(self.row,self.job,self.value)
        if self.job.status!='running' or self.row.claim_id!=self.token or not live_lease(self.row):
            raise AnalysisJobConflict('VIDEO_PROVIDER_OUTCOME_UNKNOWN')
        self.row.claim_id=None;self.row.lease_expires_at=None
        self.job.error_json=None
        self.job.artifacts_json=[{'kind':'metadata','name':'video-analysis.json',
            'url':f'/api/v1/projects/{analysis.project_id}/analyses/{analysis.analysis_id}',
            'checksum_sha256':None}]
        transition(session,self.job,'awaiting_review','awaiting_review','video_analysis.ready',self.value['actor_ref'],
            {'analysis_id':analysis.analysis_id,'human_review_required':True,'source_media_mutated':False,'timeline_mutated':False})

    async def fail(self,code,*,evidence=None,attention=False,only_expired=False):
        unknown=attention or 'UNKNOWN' in code or code=='AUTO_EDIT_ANALYSIS_CANCELLED'
        async with self.service.session_factory() as session:
            async with session.begin():
                row=await self.service.repository.relation(session,self.value['project_id'],self.job_id,lock=True)
                job=await session.scalar(select(JobORM).where(JobORM.job_id==self.job_id).with_for_update()
                    .execution_options(populate_existing=True))
                if job is None or job.status!='running' or row.claim_id!=self.token:return False
                if only_expired and live_lease(row):return False
                try:check(row,job,self.value)
                except AnalysisJobConflict:
                    code='VIDEO_JOB_CUSTODY_CHANGED';unknown=True;evidence=None
                if not live_lease(row):
                    unknown=True
                    if code!='VIDEO_JOB_CUSTODY_CHANGED':code='VIDEO_PROVIDER_OUTCOME_UNKNOWN'
                    # Matching, unrecovered claim evidence is rejected diagnostics,
                    # never an authoritative transcript or permission to replay.
                analysis=await session.get(AutoEditAnalysisORM,self.value['analysis_id'],with_for_update=True)
                if (analysis is None or analysis.project_id!=self.value['project_id']
                    or analysis.workspace_id!=self.value['workspace_id']):return False
                if analysis.status=='succeeded':return False
                if evidence is not None:
                    if evidence.get('source_sha256')!=self.value['source_json']['source_sha256']:
                        evidence=None
                    else:
                        saved={'evidence':copy.deepcopy(evidence),'sha256':digest(evidence)}
                        previous=analysis.provenance_json.get('local_video_rejected_evidence')
                        if previous is not None and previous!=saved:
                            raise AnalysisJobConflict('VIDEO_EVIDENCE_IMMUTABLE')
                        analysis.provenance_json={**analysis.provenance_json,'local_video_rejected_evidence':saved,
                            'human_review_required':True,'automatic_model_replay':False}
                analysis.status='failed';analysis.error_code=code;analysis.updated_at=utc_now()
                job.error_json={'code':code,'message':'Source preserved; recognition requires review',
                    'failed_stage':'analyzing_video','retryable':False}
                transition(session,job,'needs_attention' if unknown else 'failed','failed','video_analysis.failed',
                    self.value['actor_ref'],{'code':code,'automatic_model_replay':False})
                row.claim_id=None;row.lease_expires_at=None
                return True


class AutoEditJobService:
    def __init__(self,*,analysis_service,queue,max_source_bytes=2_000_000_000,lease_seconds=300,timeout_seconds=1800):
        if (type(max_source_bytes) is not int or not 0<max_source_bytes<=2*1024**3
            or type(lease_seconds) is not int or not 30<=lease_seconds<=3600
            or type(timeout_seconds) is not int or not 30<=timeout_seconds<=3600):
            raise ValueError('VIDEO_JOB_BOUNDS_INVALID')
        self.analysis_service,self.queue=analysis_service,queue
        self.session_factory=analysis_service.repository.session_factory
        self.repository=AutoEditJobRepository(self.session_factory,analysis_service.repository)
        self.max_source_bytes,self.lease_seconds,self.timeout_seconds=max_source_bytes,lease_seconds,timeout_seconds

    def binding(self):
        provider=self.analysis_service.transcription_provider
        return {'transcription':provider_snapshot(provider),
            'signals':{'key':self.analysis_service.signal_provider.key,
                'algorithm_version':getattr(self.analysis_service.signal_provider,'algorithm_version',None),
                'executable':str(getattr(self.analysis_service.signal_provider,'executable','')),
                'timeout_seconds':getattr(self.analysis_service.signal_provider,'timeout_seconds',None),
                'adapter':type(self.analysis_service.signal_provider).__module__+'.'+type(self.analysis_service.signal_provider).__qualname__},
            'analysis_algorithm':self.analysis_service.algorithm_version,
            'derived_timing_enabled':self.analysis_service.derived_timing_enabled,
            'max_source_bytes':min(self.max_source_bytes,getattr(provider,'max_file_bytes',self.max_source_bytes)),
            'lease_seconds':self.lease_seconds,'timeout_seconds':self.timeout_seconds}

    async def verify_runtime(self,expected):
        provider=self.analysis_service.transcription_provider
        if provider.key=='transcription-not-configured':raise ProviderNotConfigured('VIDEO_PROVIDER_NOT_CONFIGURED')
        if callable(getattr(provider,'verify',None)):
            await completed_io(asyncio.to_thread(provider.verify))
        if self.binding()!=expected:raise AnalysisJobConflict('VIDEO_PROVIDER_OR_CONFIGURATION_CHANGED')

    async def create(self,project_id,payload,actor_ref):
        bound=self.binding()
        await self.verify_runtime(bound)
        local=frozen_video_binding(self.analysis_service.transcription_provider)
        if local is not None and payload.configuration.word_timing_policy!='strict_provider_intervals':
            raise AnalysisJobConflict('LOCAL_VIDEO_STRICT_PROVIDER_TIMING_REQUIRED')
        source=await trusted_video_snapshot(self.analysis_service.repository,project_id,payload.configuration.asset_id,
            self.analysis_service.object_storage.name,bound['max_source_bytes'])
        if source['source_sha256']!=payload.source_sha256:raise AnalysisJobConflict('VIDEO_SOURCE_CHANGED')
        prepared=await self.analysis_service.prepare(project_id,payload.configuration,local_binding=local)
        # A cache reply still verifies the original physical source before adopting stored evidence.
        async with self.session_factory() as session:
            old=await session.scalar(select(AutoEditAnalysisORM).where(AutoEditAnalysisORM.project_id==project_id,
                AutoEditAnalysisORM.fingerprint==prepared['fingerprint']))
            cached=old is not None and old.status in {'succeeded','failed'}
        if cached:
            async with staged_trusted_video(self.analysis_service.repository,self.analysis_service.object_storage,
                project_id,source['asset_id'],self.analysis_service.staging_root,bound['max_source_bytes'],expected=source):
                await self.verify_runtime(bound)
        job_id=await self.repository.create(project_id,payload,actor_ref,prepared,source,bound)
        result=await self.repository.get(project_id,job_id)
        if result.job.status=='queued':await self.queue.rpush(ANALYSIS_QUEUE,job_id)
        return result

    async def process(self,job_id):
        claimed=await self.repository.claim(job_id)
        if claimed is None:return
        value,token,fingerprint=claimed
        guard=AnalysisClaim(self,value,token,fingerprint)
        heartbeat=asyncio.create_task(self.heartbeat(guard))
        try:
            async with asyncio.timeout(value['provider_json']['timeout_seconds']):
                await self.verify_runtime(value['provider_json'])
                source=value['source_json']
                async with staged_trusted_video(self.analysis_service.repository,self.analysis_service.object_storage,
                    value['project_id'],source['asset_id'],self.analysis_service.staging_root,
                    value['provider_json']['max_source_bytes'],expected=source) as (path,snapshot):
                    await self.analysis_service._analyze(value['project_id'],AutoEditAnalysisRequest.model_validate(value['configuration_json']),
                        local_path_override=path,local_source_snapshot=snapshot,
                        local_binding=frozen_video_binding(self.analysis_service.transcription_provider),
                        analysis_id_override=value['analysis_id'],job_guard=guard)
        except asyncio.CancelledError:
            await completed_io(guard.fail('VIDEO_PROVIDER_OUTCOME_UNKNOWN',attention=True))
            raise
        except Exception as exc:
            unknown=isinstance(exc,(TimeoutError,ProviderTransientError))
            code=('VIDEO_PROVIDER_OUTCOME_UNKNOWN' if unknown else 'VIDEO_PROVIDER_NOT_CONFIGURED' if isinstance(exc,ProviderNotConfigured)
                else 'VIDEO_PROVIDER_SAFETY_BLOCKED' if isinstance(exc,ProviderSafetyBlocked)
                else exc.code if isinstance(exc,AnalysisJobConflict) else 'VIDEO_ANALYSIS_FAILED')
            await guard.fail(code,attention=unknown)
        finally:
            heartbeat.cancel()
            async def drain():return await asyncio.gather(heartbeat,return_exceptions=True)
            await completed_io(drain())

    async def heartbeat(self,guard):
        lease=guard.value['provider_json']['lease_seconds']
        while True:
            await asyncio.sleep(min(30,max(5,lease/3)))
            try:
                async with self.session_factory() as session:
                    async with session.begin():
                        running=select(JobORM.job_id).where(JobORM.job_id==guard.job_id,JobORM.status=='running').exists()
                        row=await session.get(AutoEditJobORM,guard.value['relation_id'])
                        if row is None or immutable(row)!=guard.value or not live_lease(row):return
                        result=await session.execute(update(AutoEditJobORM).where(AutoEditJobORM.relation_id==row.relation_id,
                            AutoEditJobORM.claim_id==guard.token,AutoEditJobORM.lease_expires_at>utc_now(),running).values(lease_expires_at=utc_now()+timedelta(seconds=lease)))
                        if result.rowcount!=1:return
            except Exception:return  # Lost durable renewal must expire; no in-memory lease extension.

    async def recover(self,*,include_queued=True):
        async with self.session_factory() as session:
            rows=(await session.execute(select(AutoEditJobORM,JobORM,AutoEditAnalysisORM.fingerprint)
                .join(JobORM,AutoEditJobORM.job_id==JobORM.job_id)
                .join(AutoEditAnalysisORM,AutoEditJobORM.analysis_id==AutoEditAnalysisORM.analysis_id)
                .where(JobORM.status.in_(['queued','running'])))).all()
            queued=[job.job_id for row,job,fp in rows if job.status=='queued' and include_queued]
            expired=[(immutable(row),row.claim_id,fp) for row,job,fp in rows if job.status=='running' and not live_lease(row)]
        for value,token,fp in expired:
            await AnalysisClaim(self,value,token,fp).fail('VIDEO_PROVIDER_OUTCOME_UNKNOWN',attention=True,only_expired=True)
        for job_id in queued:await self.queue.rpush(ANALYSIS_QUEUE,job_id)
        return len(queued)

    async def cancel(self,project_id,job_id,actor_ref):
        return await self.repository.cancel(project_id,job_id,actor_ref)
