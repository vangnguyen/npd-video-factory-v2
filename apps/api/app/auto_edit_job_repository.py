"""SQL owns analysis claims and immutable requests; Redis is delivery only."""
import copy
from datetime import timedelta, timezone
from uuid import uuid4
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .auto_edit_db import AutoEditAnalysisORM
from .auto_edit_job_db import AutoEditJobORM, AutoEditJobRequestORM
from .auto_edit_job_models import AutoEditJobRead
from .auto_edit_source_custody import trusted_video_in_session
from .db import JobORM, utc_now
from .models import AutoEditAnalysisJobInput, JobRecord
from .repositories import PostgresJobStore
from .uploaded_audio_repository import digest, actor


class AnalysisJobConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def identity(prefix):
    return prefix+'_'+uuid4().hex[:24]


def live_lease(row):
    deadline = row.lease_expires_at
    if deadline is not None and deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=timezone.utc)
    return row.claim_id is not None and deadline is not None and deadline > utc_now()


def immutable(row):
    return copy.deepcopy({name:getattr(row,name) for name in ('relation_id','analysis_id','job_id',
        'workspace_id','project_id','source_json','configuration_json','provider_json','actor_ref','request_json')})


def check(row, job, expected=None):
    if job is None:raise AnalysisJobConflict('VIDEO_JOB_CUSTODY_CHANGED')
    value = immutable(row)
    if (digest(value) != row.custody_sha256 or expected is not None and value != expected
        or job.job_id != row.job_id or job.workspace_id != row.workspace_id or job.project_id != row.project_id
        or job.request_json != row.request_json or row.request_json['actor_ref'] != row.actor_ref
        or row.request_json['analysis_id'] != row.analysis_id
        or row.request_json['source_sha256'] != row.source_json['source_sha256']
        or row.request_json['provider_binding_sha256'] != digest(row.provider_json)):
        raise AnalysisJobConflict('VIDEO_JOB_CUSTODY_CHANGED')
    return value


def transition(session, job, status, stage, event_type, actor_ref, payload=None):
    current = PostgresJobStore._record(job)
    job.status, job.stage, job.updated_at = status, stage, utc_now()
    job.progress = 100 if status == 'awaiting_review' else 10 if status == 'running' else job.progress
    session.add(PostgresJobStore._event(row=job, current=current, updated=PostgresJobStore._record(job),
        event_type=event_type, actor_ref=actor_ref, payload=payload))


class AutoEditJobRepository:
    def __init__(self, session_factory, analysis_repository):
        self.session_factory, self.analysis_repository = session_factory, analysis_repository

    async def relation(self, session, project_id, job_id, *, lock=False):
        query = select(AutoEditJobORM).where(AutoEditJobORM.project_id==project_id, AutoEditJobORM.job_id==job_id)
        if lock: query=query.with_for_update()
        row=await session.scalar(query.execution_options(populate_existing=True))
        if row is None: raise KeyError(job_id)
        return row

    async def get(self, project_id, job_id):
        async with self.session_factory() as session:
            row=await self.relation(session,project_id,job_id)
            job=await session.get(JobORM,job_id)
            if job is None: raise AnalysisJobConflict('VIDEO_JOB_CUSTODY_CHANGED')
            check(row,job)
            current=await trusted_video_in_session(session,project_id,row.source_json['asset_id'],
                row.source_json['storage_provider'],row.provider_json['max_source_bytes'])
            if current!=row.source_json:raise AnalysisJobConflict('VIDEO_SOURCE_CHANGED')
            snapshot=copy.deepcopy(row.source_json)
            checksum=row.custody_sha256
            analysis_id=row.analysis_id
            record=PostgresJobStore._record(job)
        analysis=await self.analysis_repository.get_analysis(analysis_id)
        if (analysis is None or analysis.project_id!=project_id or analysis.workspace_id!=record.workspace_id
            or analysis.asset_id!=snapshot['asset_id'] or analysis.provenance.get('source_asset_checksum')!=snapshot['source_sha256']):
            raise AnalysisJobConflict('VIDEO_ANALYSIS_CHANGED')
        return AutoEditJobRead(job=record,analysis=analysis,source_sha256=snapshot['source_sha256'],custody_sha256=checksum)

    async def list(self, project_id):
        async with self.session_factory() as session:
            ids=(await session.scalars(select(AutoEditJobORM.job_id).where(AutoEditJobORM.project_id==project_id)
                .order_by(AutoEditJobORM.created_at))).all()
        return [await self.get(project_id,job_id) for job_id in ids]

    async def create(self, project_id, payload, actor_ref, prepared, source, provider):
        actor(actor_ref)
        key=digest([project_id,payload.idempotency_key])
        request_sha=digest([payload.model_dump(mode='json'),provider,source,actor_ref])
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    current=await trusted_video_in_session(session,project_id,source['asset_id'],source['storage_provider'],source['source_size_bytes'])
                    if current!=source or payload.source_sha256!=source['source_sha256']:
                        raise AnalysisJobConflict('VIDEO_SOURCE_CHANGED')
                    old=await session.get(AutoEditJobRequestORM,key)
                    if old is not None:
                        if old.request_sha256!=request_sha or old.actor_ref!=actor_ref:
                            raise AnalysisJobConflict('VIDEO_IDEMPOTENCY_CONFLICT')
                        return old.job_id
                    analysis=await session.scalar(select(AutoEditAnalysisORM).where(AutoEditAnalysisORM.project_id==project_id,
                        AutoEditAnalysisORM.fingerprint==prepared['fingerprint']))
                    relation=None
                    if analysis is not None:
                        relation=await session.scalar(select(AutoEditJobORM).where(AutoEditJobORM.analysis_id==analysis.analysis_id))
                        if relation is None and analysis.status in {'pending','analyzing'}:
                            raise AnalysisJobConflict('VIDEO_LEGACY_ANALYSIS_IN_PROGRESS')
                    else:
                        asset=prepared['asset']
                        analysis=AutoEditAnalysisORM(analysis_id=identity('ana'),workspace_id=asset.workspace_id,
                            project_id=project_id,project_version_id=asset.project_version_id,asset_id=asset.asset_id,
                            status='pending',fingerprint=prepared['fingerprint'],configuration_json=payload.configuration.model_dump(mode='json'),
                            source_media_json=prepared['source_media'].model_dump(mode='json'),
                            provenance_json={**prepared['provenance'],'local_video_execution':'durable_async',
                                'human_review_required':True,'automatic_model_replay':False})
                        session.add(analysis);await session.flush()
                    if relation is not None:
                        relation=await self.relation(session,project_id,relation.job_id,lock=True)
                        job=await session.get(JobORM,relation.job_id,with_for_update=True)
                        analysis=await session.get(AutoEditAnalysisORM,relation.analysis_id,with_for_update=True)
                        check(relation,job)
                        if relation.source_json!=source or relation.configuration_json!=payload.configuration.model_dump(mode='json') or relation.provider_json!=provider:
                            raise AnalysisJobConflict('VIDEO_ANALYSIS_BINDING_CHANGED')
                    else:
                        job_id='job_analysis_'+digest([project_id,prepared['fingerprint']])[:24]
                        request=AutoEditAnalysisJobInput(analysis_id=analysis.analysis_id,source_sha256=source['source_sha256'],
                            provider_binding_sha256=digest(provider),actor_ref=actor_ref)
                        record=JobRecord.new(job_id=job_id,workspace_id=source['workspace_id'],project_id=project_id,
                            project_version_id=analysis.project_version_id,request=request)
                        cached=analysis.status in {'succeeded','failed'}
                        status=('awaiting_review' if analysis.status=='succeeded' else
                            'needs_attention' if analysis.error_code and 'UNKNOWN' in analysis.error_code else 'failed') if cached else 'queued'
                        job=JobORM(job_id=job_id,workspace_id=record.workspace_id,project_id=project_id,
                            project_version_id=record.project_version_id,status=status,
                            stage='awaiting_review' if status=='awaiting_review' else 'failed' if cached else 'queued',
                            progress=100 if cached else 0,request_json=request.model_dump(mode='json'),artifacts_json=[],
                            error_json={'code':analysis.error_code or 'VIDEO_ANALYSIS_FAILED','message':'Source preserved; review required',
                                'failed_stage':'analyzing_video','retryable':False} if status in {'failed','needs_attention'} else None)
                        session.add(job);await session.flush()
                        relation=AutoEditJobORM(relation_id=identity('ajob'),analysis_id=analysis.analysis_id,job_id=job_id,
                            workspace_id=record.workspace_id,project_id=project_id,source_json=source,
                            configuration_json=payload.configuration.model_dump(mode='json'),provider_json=provider,
                            actor_ref=actor_ref,request_json=request.model_dump(mode='json'))
                        relation.custody_sha256=digest(immutable(relation));session.add(relation)
                        session.add(PostgresJobStore._event(row=job,event_type='video_analysis.cached' if cached else 'video_analysis.queued',
                            actor_ref=actor_ref,payload={'analysis_id':analysis.analysis_id,'human_review_required':True}))
                    session.add(AutoEditJobRequestORM(receipt_id=key,project_id=project_id,job_id=relation.job_id,
                        request_key_sha256=key,request_sha256=request_sha,actor_ref=actor_ref))
                    return relation.job_id
        except IntegrityError:
            async with self.session_factory() as session:
                old=await session.get(AutoEditJobRequestORM,key)
                if old and old.request_sha256==request_sha and old.actor_ref==actor_ref:return old.job_id
            # A different key can race on the same canonical fingerprint. Retry
            # SQL reservation once, never provider execution, outside the failed transaction.
            return await self._recover_reservation(project_id,payload,actor_ref,prepared,source,provider,key,request_sha)

    async def _recover_reservation(self, project_id,payload,actor_ref,prepared,source,provider,key,request_sha):
        async with self.session_factory() as session:
            async with session.begin():
                old=await session.get(AutoEditJobRequestORM,key)
                if old:
                    if old.request_sha256!=request_sha or old.actor_ref!=actor_ref:raise AnalysisJobConflict('VIDEO_IDEMPOTENCY_CONFLICT')
                    return old.job_id
                relation=await session.scalar(select(AutoEditJobORM).join(AutoEditAnalysisORM,
                    AutoEditJobORM.analysis_id==AutoEditAnalysisORM.analysis_id).where(AutoEditJobORM.project_id==project_id,
                    AutoEditAnalysisORM.fingerprint==prepared['fingerprint']))
                if relation is None or relation.source_json!=source or relation.provider_json!=provider:
                    raise AnalysisJobConflict('VIDEO_RESERVATION_CONFLICT')
                check(relation,await session.get(JobORM,relation.job_id))
                session.add(AutoEditJobRequestORM(receipt_id=key,project_id=project_id,job_id=relation.job_id,
                    request_key_sha256=key,request_sha256=request_sha,actor_ref=actor_ref))
                return relation.job_id

    async def claim(self, job_id):
        async with self.session_factory() as session:
            async with session.begin():
                observed=await session.get(JobORM,job_id)
                if observed is None or observed.status!='queued' or observed.request_json.get('kind')!='auto_edit_analysis':return None
                row=await self.relation(session,observed.project_id,job_id,lock=True)
                try:
                    check(row,observed)
                    current=await trusted_video_in_session(session,row.project_id,row.source_json['asset_id'],
                        row.source_json['storage_provider'],row.provider_json['max_source_bytes'])
                    if current!=row.source_json:raise AnalysisJobConflict('VIDEO_SOURCE_CHANGED')
                except (ValueError,KeyError):
                    # Poisoned queued custody is a durable review state, never a
                    # hot recovery loop and never permission to dispatch.
                    blocked=await session.scalar(update(JobORM).where(JobORM.job_id==job_id,JobORM.status=='queued').values(
                        status='needs_attention',stage='failed',updated_at=utc_now(),
                        error_json={'code':'VIDEO_SOURCE_OR_CUSTODY_CHANGED','message':'Stored request/source requires review',
                            'failed_stage':'analyzing_video','retryable':False}).returning(JobORM))
                    if blocked is not None:
                        analysis=await session.get(AutoEditAnalysisORM,row.analysis_id,with_for_update=True)
                        if analysis is not None and analysis.status=='pending' and analysis.project_id==blocked.project_id and analysis.workspace_id==blocked.workspace_id:
                            analysis.status='failed';analysis.error_code='VIDEO_SOURCE_OR_CUSTODY_CHANGED';analysis.updated_at=utc_now()
                        session.add(PostgresJobStore._event(row=blocked,event_type='video_analysis.blocked',actor_ref='worker',
                            payload={'automatic_model_replay':False}))
                    return None
                job=await session.scalar(update(JobORM).where(JobORM.job_id==job_id,JobORM.status=='queued').values(
                    status='running',stage='analyzing_video',progress=10,updated_at=utc_now()).returning(JobORM))
                if job is None:return None
                value=check(row,job)
                analysis=await session.get(AutoEditAnalysisORM,row.analysis_id,with_for_update=True)
                if analysis.status!='pending':raise AnalysisJobConflict('VIDEO_ANALYSIS_STATE_CHANGED')
                analysis.status='analyzing';analysis.updated_at=utc_now()
                row.claim_id=identity('vclaim');row.lease_expires_at=utc_now()+timedelta(seconds=row.provider_json['lease_seconds'])
                session.add(PostgresJobStore._event(row=job,event_type='video_analysis.claimed',actor_ref=row.actor_ref))
                return value,row.claim_id,analysis.fingerprint

    async def cancel(self, project_id,job_id,actor_ref):
        actor(actor_ref)
        async with self.session_factory() as session:
            async with session.begin():
                row=await self.relation(session,project_id,job_id,lock=True)
                job=await session.get(JobORM,job_id,with_for_update=True)
                check(row,job)
                if job.status in {'queued','running','needs_attention'}:
                    analysis=await session.get(AutoEditAnalysisORM,row.analysis_id,with_for_update=True)
                    analysis.status='failed';analysis.error_code='VIDEO_ANALYSIS_CANCELLED';analysis.updated_at=utc_now()
                    job.error_json={'code':'VIDEO_ANALYSIS_CANCELLED','message':'Cancelled; source preserved',
                        'failed_stage':'analyzing_video','retryable':False}
                    transition(session,job,'cancelled','failed','video_analysis.cancelled',actor_ref)
                    row.claim_id=None;row.lease_expires_at=None
        return await self.get(project_id,job_id)
