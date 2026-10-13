"""Durable, provider-neutral audio jobs and explicit immutable human revisions."""
import copy
import json
import math
import re
import asyncio
from contextlib import suppress
from dataclasses import asdict
from decimal import Decimal
from datetime import timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unicodedata
from sqlalchemy import select, update
from .auto_edit_models import TranscriptRead
from .auto_edit_providers import (ProviderTranscript, ProviderSegment, ProviderWord,
    ProviderNotConfigured, require_positive_duration_transcript)
from .db import JobORM, utc_now
from .models import UploadedAudioJobInput
from .object_storage import sha256_file
from .provider_safety import ProviderCallContext, ProviderSafetyController, ProviderSafetyBlocked, ProviderExecutionTrace
from .repositories import PostgresJobStore
from .transcript_word_review import revised
from .uploaded_audio_db import UploadedAudioORM
from .uploaded_audio_repository import UploadedAudioRepository, AudioConflict, source, digest, identity, actor
from .frozen_storage_read import frozen_asset_read, asset_custody, completed_read, MAX_SOURCE_BYTES, FrozenReadRejected
from .bounded_storage_download import StorageDownloadError

AUDIO_QUEUE = 'npd:video-factory:v2:uploaded-audio:queued'


def live_lease(parent):
    deadline=parent.lease_expires_at
    if deadline is not None and deadline.tzinfo is None:
        deadline=deadline.replace(tzinfo=timezone.utc)
    return parent.claim_id is not None and deadline is not None and deadline>utc_now()


def provider_binding(provider):
    profile = getattr(provider, 'asr_prompt_profile', getattr(provider, 'profile', None))
    if hasattr(profile, 'model_dump'):
        profile = profile.model_dump(mode='json')
    binding = {'provider_key':provider.key,'model':provider.model,'external_call':provider.external_call,
        'paid':provider.paid,'language':getattr(provider,'language',None),
        'response_format':getattr(provider,'response_format',None),
        'timestamp_granularities':list(getattr(provider,'timestamp_granularities',())),
        'profile':profile,'word_timing_policy':'strict_provider_intervals',
        'credential_alias':provider.credential_alias,'estimated_cost_vnd':str(provider.estimated_cost_vnd),
        'max_file_bytes':getattr(provider,'max_file_bytes',None),
        'max_duration_seconds':getattr(provider,'max_duration_seconds',None),
        'provider_http_timeout_seconds':getattr(provider,'provider_http_timeout_seconds',None),
        'controller_hard_timeout_seconds':getattr(provider,'controller_hard_timeout_seconds',None)}
    immutable = getattr(provider, 'immutable_binding', None)
    if immutable is not None:
        if not isinstance(immutable, dict):
            raise AudioConflict('AUDIO_PROVIDER_BINDING_INVALID')
        try:
            digest(immutable)
        except (ValueError, TypeError):
            raise AudioConflict('AUDIO_PROVIDER_BINDING_INVALID') from None
        binding['immutable_binding'] = copy.deepcopy(immutable)
    return binding


def snapshot_evidence(value, receipt):
    return {'language':value.language,'confidence':value.confidence,
        'segments':[asdict(s) for s in value.segments],
        'provenance':{**copy.deepcopy(value.provenance),'provider_safety_receipt':receipt.model_dump(mode='json')},
        'actual_cost_vnd':str(value.actual_cost_vnd) if value.actual_cost_vnd is not None else None}


def rejected_local_evidence(exc, request, configuration, source_size_bytes):
    """Validate the captured exception, never a mutable provider singleton."""
    from .local_uploaded_audio_provider import LocalAudioEvidenceRejected
    if not isinstance(exc, LocalAudioEvidenceRejected) or configuration is None:
        return None
    try:
        value = copy.deepcopy(exc.evidence)
        binding = configuration['provider']
        encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        valid = (len(encoded) <= 32*1024*1024 and digest(value) == exc.evidence_sha256
            and value['schema_version'] == 'sql-local-audio-evidence.v1'
            and binding['provider_key'] == 'local-faster-whisper'
            and binding['external_call'] is False and binding['paid'] is False
            and value['source_sha256'] == request.source_sha256
            and type(value['source_size_bytes']) is int and value['source_size_bytes'] == source_size_bytes
            and value['immutable_binding'] == binding['immutable_binding']
            and isinstance(value['model_result'], dict) and digest(value['model_result']) == value['model_result_sha256']
            and isinstance(value['decoded_audio_clock'], dict) and digest(value['decoded_audio_clock']) == value['decoded_audio_clock_sha256']
            and isinstance(value['pcm_sha256'], str) and re.fullmatch('[a-f0-9]{64}', value['pcm_sha256']) is not None
            and type(value['provider_result_normalized']) is bool and value['source_projection_validated'] is False
            and value['source_checksum_verified_before_inference'] is True
            and (value['source_checksum_verified_after_result'] is None or value['source_checksum_verified_after_result'] is True)
            and (value.get('original_source_unchanged') is not True or value['source_checksum_verified_after_result'] is True)
            and type(value['provider_billed_cost_vnd']) is int and value['provider_billed_cost_vnd'] == 0
            and value['operating_electricity_hardware_cost_vnd'] is None
            and value['human_accepted'] is False and value['publishing_enabled'] is False
            and value['rejection_code'] == exc.code
            and isinstance(exc.code, str) and re.fullmatch('LOCAL_AUDIO_[A-Z0-9_]{1,100}', exc.code) is not None)
    except (ValueError, TypeError, KeyError, OverflowError, AttributeError, RecursionError):
        return None
    return value if valid else None


def normalize_evidence(evidence, parent, *, created_at):
    segments = tuple(ProviderSegment(**{**s,'words':tuple(ProviderWord(**w) for w in s['words'])})
        for s in evidence['segments'])
    provider = ProviderTranscript(language=evidence['language'], confidence=evidence['confidence'],
        segments=segments, provenance=evidence['provenance'])
    require_positive_duration_transcript(provider)
    if not 1 <= len(segments) <= 1000:
        raise AudioConflict('AUDIO_TRANSCRIPT_SEGMENT_LIMIT')
    previous = 0.; ordinal = 0; normalized = []
    duration = parent.media_metadata_json['duration_seconds']
    for index, segment in enumerate(segments):
        if (not segment.text.strip() or len(segment.text)>4000
            or not math.isfinite(segment.start_seconds) or not math.isfinite(segment.end_seconds) or segment.start_seconds<previous
            or segment.end_seconds>duration or len(segment.words)>2000):
            raise AudioConflict('AUDIO_TRANSCRIPT_SOURCE_BOUNDS')
        previous = segment.end_seconds
        words = []
        word_end = segment.start_seconds
        for word in segment.words:
            if (not word.text.strip() or not math.isfinite(word.start_seconds) or not math.isfinite(word.end_seconds)
                or word.start_seconds < word_end or word.end_seconds > segment.end_seconds):
                raise AudioConflict('AUDIO_TRANSCRIPT_INVALID')
            word_end = word.end_seconds
            words.append({'word_id':'wrd_'+digest([parent.audio_id,'word',ordinal])[:24],
                'ordinal':ordinal,'text':word.text,'start_seconds':word.start_seconds,
                'end_seconds':word.end_seconds,'confidence':word.confidence})
            ordinal += 1
        normalized.append({'segment_id':'seg_'+digest([parent.audio_id,'segment',index])[:24],
            'ordinal':index,'text':segment.text,'start_seconds':segment.start_seconds,
            'end_seconds':segment.end_seconds,'speaker':segment.speaker,'confidence':segment.confidence,'words':words})
    if ordinal>10000:
        raise AudioConflict('AUDIO_TRANSCRIPT_WORD_LIMIT')
    return TranscriptRead(transcript_id='trn_'+digest([parent.audio_id,'original'])[:24],
        analysis_id=parent.audio_id,asset_id=parent.asset_id,version=1,is_original_evidence=True,
        provider_key=parent.configuration_json['provider']['provider_key'],language=provider.language,
        confidence=provider.confidence,segments=normalized,created_at=created_at,
        provenance={**copy.deepcopy(provider.provenance),'source_asset_sha256':parent.source_sha256,
            'source_media_mutated':False,'recognition_review_required':True})


def clone_version(base, current, actor_ref, note, *, restored=False):
    value = base.model_dump(mode='json')
    mapping = {}
    for segment in value['segments']:
        old = segment['segment_id']; segment['segment_id'] = identity('seg'); mapping[old] = segment['segment_id']
        for word in segment['words']:
            word['word_id'] = identity('wrd')
    value.update(transcript_id=identity('trn'),version=current.version+1,is_original_evidence=False,
        created_at=utc_now(),provenance={**copy.deepcopy(base.provenance),'human_edit':True,'actor_ref':actor_ref,
            'original_evidence':False,
            'derived_from_transcript_id':base.transcript_id,'derived_from_version':base.version,
            'segment_id_mapping':mapping,'edit_note':note,'remote_calls':0,'source_media_mutated':False,
            **({'restored_from_transcript_id':base.transcript_id} if restored else {})})
    return TranscriptRead.model_validate(value)


class UploadedAudioService:
    def __init__(self, *, session_factory, platform, object_storage, queue, provider,
                 staging_root, provider_safety=None):
        self.repository = UploadedAudioRepository(session_factory)
        self.session_factory, self.platform, self.object_storage = session_factory, platform, object_storage
        self.queue, self.provider, self.staging_root = queue, provider, Path(staging_root)
        self.provider_safety = provider_safety or ProviderSafetyController.fail_closed()

    def binding(self):
        return {**provider_binding(self.provider),
            'execution_policy_sha256':digest(self.provider_safety.policy.model_dump(mode='json')),
            'lease_seconds':int(self.provider_safety.policy.retry.controller_hard_timeout_seconds)+120}

    async def create(self, project_id, payload, actor_ref):
        if self.provider.key == 'transcription-not-configured':
            raise ProviderNotConfigured('AUDIO_PROVIDER_NOT_CONFIGURED')
        binding = self.binding()
        if payload.expected_provider_key is not None and payload.expected_provider_key != self.provider.key:
            raise AudioConflict('AUDIO_PROVIDER_CHANGED')
        audio_id = await self.repository.create(project_id, payload, binding, actor_ref)
        result = await self.repository.get(project_id, audio_id)
        if result.job['status']=='queued':
            await self.queue.rpush(AUDIO_QUEUE, result.job['job_id'])
        return result

    async def source_file(self, project_id, audio_id):
        async with self.session_factory() as session:
            parent = await self.repository.parent(session, project_id, audio_id)
            _, asset, _ = await source(session, project_id, parent.asset_id, parent=parent)
            sha, size, mime = parent.source_sha256, parent.source_size_bytes, asset.content_type
            # Intake validates bytes/MIME, not client extensions. Stage a name
            # matching that verified MIME for adapters that check suffixes.
            suffix = {'audio/wav':'.wav','audio/x-wav':'.wav','audio/mpeg':'.mp3',
                'audio/flac':'.flac'}.get(asset.content_type)
            if suffix is None:
                raise AudioConflict('AUDIO_MIME_UNSUPPORTED')
            if asset.storage_provider != self.object_storage.name:
                raise AudioConflict('AUDIO_STORAGE_CHANGED')
            limit=parent.configuration_json.get('provider',{}).get('max_file_bytes')
            if limit is not None and (type(limit) is not int or limit<=0):
                raise AudioConflict('AUDIO_PROVIDER_BINDING_INVALID')
            try:
                proof=frozen_asset_read(asset,workspace_id=parent.workspace_id,project_id=project_id,
                    storage=self.object_storage,maximum=min(limit,MAX_SOURCE_BYTES) if limit is not None else MAX_SOURCE_BYTES)
                custody=asset_custody(asset)
            except FrozenReadRejected:
                raise AudioConflict('AUDIO_SOURCE_CHANGED') from None
        self.staging_root.mkdir(parents=True, exist_ok=True)
        owner = TemporaryDirectory(prefix='uploaded-audio-',dir=self.staging_root)
        path = Path(owner.name)/('source'+suffix)
        try:
            try:
                await proof.download(self.object_storage,path)
            except StorageDownloadError as error:
                if error.code in {'STORAGE_DOWNLOAD_SIZE_LIMIT','STORAGE_DOWNLOAD_SIZE_MISMATCH',
                    'STORAGE_DOWNLOAD_HASH_MISMATCH','STORAGE_DOWNLOAD_STAGE_HASH_MISMATCH',
                    'STORAGE_DOWNLOAD_PATH_CHANGED'}:
                    raise AudioConflict('AUDIO_SOURCE_CHANGED') from None
                raise AudioConflict('AUDIO_SOURCE_DOWNLOAD_FAILED') from None
            except Exception:
                raise AudioConflict('AUDIO_SOURCE_DOWNLOAD_FAILED') from None
            if path.stat().st_size!=size or await completed_read(asyncio.to_thread(sha256_file,path))!=sha:
                raise AudioConflict('AUDIO_SOURCE_CHANGED')
            # Recheck registered custody after an asynchronous download.
            async with self.session_factory() as session:
                current=await self.repository.parent(session, project_id, audio_id)
                _,current_asset,_=await source(session,project_id,current.asset_id,parent=current)
                if asset_custody(current_asset)!=custody:
                    raise AudioConflict('AUDIO_SOURCE_CHANGED')
            return owner,path,mime,sha
        except BaseException:
            owner.cleanup()
            raise

    async def verify_source_file(self, project_id, audio_id):
        owner,_,_,_ = await self.source_file(project_id,audio_id)
        owner.cleanup()

    async def process(self, job_id):
        async with self.session_factory() as session:
            async with session.begin():
                observed=await session.get(JobORM,job_id)
                if observed is None or observed.status!='queued' or observed.request_json.get('kind')!='uploaded_audio_transcription':
                    return
                request = UploadedAudioJobInput.model_validate(observed.request_json)
                project_id = observed.project_id
                # All custody mutations acquire parent then job. PostgreSQL
                # cancellation/recovery cannot deadlock a completion/claim.
                parent=await session.get(UploadedAudioORM,request.audio_id,with_for_update=True)
                if parent is None or parent.job_id!=job_id or parent.project_id!=project_id:
                    raise AudioConflict('AUDIO_JOB_CHANGED')
                job = await session.scalar(update(JobORM).where(JobORM.job_id==job_id,JobORM.status=='queued',
                    JobORM.request_json['kind'].as_string()=='uploaded_audio_transcription').values(
                    status='running',stage='analyzing_audio',progress=10,updated_at=utc_now()).returning(JobORM))
                if job is None:
                    return
                if job.request_json!=request.model_dump(mode='json') or job.workspace_id!=parent.workspace_id:
                    raise AudioConflict('AUDIO_JOB_CHANGED')
                claim_id=identity('aclaim')
                parent.claim_id=claim_id
                lease_seconds=parent.configuration_json['provider']['lease_seconds']
                parent.lease_expires_at=utc_now()+timedelta(seconds=lease_seconds)
                session.add(PostgresJobStore._event(row=job,event_type='uploaded_audio.claimed',actor_ref=request.actor_ref))
        heartbeat=asyncio.create_task(self.heartbeat(job_id,request.audio_id,claim_id,lease_seconds))
        evidence = None; configuration = None; source_size_bytes = None
        try:
            async with self.session_factory() as session:
                parent = await self.repository.parent(session,project_id,request.audio_id)
                if parent.job_id!=job_id or parent.workspace_id!=job.workspace_id:
                    raise AudioConflict('AUDIO_JOB_CHANGED')
                configuration = copy.deepcopy(parent.configuration_json)
                media_json = copy.deepcopy(parent.media_metadata_json)
                source_size_bytes = parent.source_size_bytes
                if (digest(self.binding())!=request.provider_binding_sha256
                    or configuration['provider']!=self.binding()
                    or request.source_sha256!=parent.source_sha256):
                    raise AudioConflict('AUDIO_PROVIDER_OR_SOURCE_CHANGED')
            owner,path,_,_ = await self.source_file(project_id,request.audio_id)
            try:
                async with self.session_factory() as session:
                    job = await session.get(JobORM,job_id)
                    if job.status!='running':
                        return
                from .auto_edit_models import MediaMetadata
                payload = configuration['request']
                profile = getattr(self.provider,'asr_prompt_profile',getattr(self.provider,'profile',None))
                context = ProviderCallContext(operation_key=payload.get('provider_operation_key') or job_id+':asr',
                    acceptance_lineage_id=getattr(self.provider_safety.policy.execution_gate,'acceptance_lineage_id',None)
                        if self.provider.external_call else None,
                    workspace_id=parent.workspace_id,project_id=project_id,job_id=job_id,provider_key=self.provider.key,
                    model=self.provider.model,capability=getattr(self.provider,'capability','transcription'),
                    operation='uploaded_audio_transcription',external_call=self.provider.external_call,paid=self.provider.paid,
                    estimated_cost_vnd=self.provider.estimated_cost_vnd,credential_alias=self.provider.credential_alias,
                    asset_id=parent.asset_id,asset_hash=request.source_sha256,input_media_kind='audio',
                    input_file_bytes=path.stat().st_size,input_duration_seconds=media_json['duration_seconds'],
                    requested_language=getattr(self.provider,'language',None),response_format=getattr(self.provider,'response_format',None),
                    timestamp_granularities=tuple(getattr(self.provider,'timestamp_granularities',())),
                    asr_prompt_profile=profile,rights_required=self.provider.external_call,rights=payload.get('rights',[]))
                kwargs = {'expected_asr_prompt_profile':profile} if hasattr(self.provider,'asr_prompt_profile') else {}
                if getattr(self.provider, 'supports_durable_cancellation', False) is True:
                    async def is_cancelled():
                        async with self.session_factory() as session:
                            row = await session.get(UploadedAudioORM, request.audio_id)
                            current_job = await session.get(JobORM, job_id)
                            return (row is None or current_job is None or current_job.status != 'running'
                                or row.claim_id != claim_id or not live_lease(row)
                                or row.configuration_json != configuration)
                    kwargs['is_cancelled'] = is_cancelled
                dispatched = False
                async def dispatch_once():
                    nonlocal dispatched
                    if dispatched:
                        raise AudioConflict('AUDIO_PROVIDER_OUTCOME_UNKNOWN')
                    dispatched = True
                    return await self.provider.transcribe(path,metadata=MediaMetadata.model_validate(media_json),
                        checksum_sha256=request.source_sha256,execution_trace=ProviderExecutionTrace(),**kwargs)
                result = await self.provider_safety.execute(context,dispatch_once,actual_cost=lambda v:v.actual_cost_vnd)
                evidence = snapshot_evidence(result.value,result.receipt)
                await self.platform.record_provider_operation(workspace_id=parent.workspace_id,project_id=project_id,
                    job_id=job_id,provider_key=self.provider.key,capability=context.capability,
                    operation='uploaded-audio-transcription',model=self.provider.model,
                    units=Decimal(str(media_json['duration_seconds']))/Decimal('60'),unit_name='audio_minute',
                    estimated_cost=self.provider.estimated_cost_vnd,actual_cost=result.value.actual_cost_vnd,
                    metadata={'fixture':bool(result.value.provenance.get('fixture',False)),
                        'external_call':self.provider.external_call,'human_accepted':False,
                        'actual_cost_known':result.value.actual_cost_vnd is not None,
                        'budget_reservation_is_billed_cost':False,'receipt':result.receipt.model_dump(mode='json')})
                normalized = normalize_evidence(evidence,parent,created_at=utc_now())
                await self.verify_source_file(project_id,request.audio_id)
                async with self.session_factory() as session:
                    async with session.begin():
                        parent = await self.repository.parent(session,project_id,request.audio_id,lock=True)
                        job = await session.get(JobORM,job_id,with_for_update=True)
                        if job.status!='running' or parent.claim_id!=claim_id:
                            return
                        if (not live_lease(parent) or parent.configuration_json!=configuration
                            or job.request_json!=request.model_dump(mode='json')
                            or job.workspace_id!=parent.workspace_id):
                            raise AudioConflict('AUDIO_COMPLETION_CHANGED')
                        if parent.current_version!=0 or parent.original_evidence_json is not None:
                            raise AudioConflict('AUDIO_COMPLETION_CHANGED')
                        parent.original_evidence_json=evidence;parent.original_evidence_sha256=digest(evidence)
                        parent.current_version=1
                        parent.claim_id=None;parent.lease_expires_at=None
                        session.add(self.repository.version_row(normalized,request.actor_ref))
                        await session.flush()
                        job.status='awaiting_review';job.stage='awaiting_review';job.progress=100;job.updated_at=utc_now()
                        job.artifacts_json=[{'kind':'metadata','name':'audio-transcript.json','url':request.audio_id,
                            'checksum_sha256':digest(normalized.model_dump(mode='json'))}]
                        session.add(PostgresJobStore._event(row=job,event_type='uploaded_audio.transcript_ready',
                            actor_ref=request.actor_ref,payload={'transcript_id':normalized.transcript_id,
                                'human_review_required':True,'source_media_mutated':False,'timeline_mutated':False}))
            finally:
                owner.cleanup()
        except Exception as exc:
            if evidence is None:
                evidence = rejected_local_evidence(exc, request, configuration, source_size_bytes)
            code = ('AUDIO_PROVIDER_NOT_CONFIGURED' if isinstance(exc,ProviderNotConfigured) else
                'AUDIO_PROVIDER_SAFETY_BLOCKED' if isinstance(exc,ProviderSafetyBlocked) else
                exc.code if isinstance(exc,AudioConflict) else 'AUDIO_TRANSCRIPTION_FAILED')
            from .provider_safety import ProviderTransientError
            unknown = code=='AUDIO_PROVIDER_OUTCOME_UNKNOWN' or isinstance(exc,(ProviderTransientError,TimeoutError))
            await self.fail(job_id,'AUDIO_PROVIDER_OUTCOME_UNKNOWN' if unknown else code,evidence=evidence,
                attention=unknown,expected_claim_id=claim_id,expected_configuration=configuration,
                expected_request=request.model_dump(mode='json'))
        finally:
            heartbeat.cancel()
            with suppress(asyncio.CancelledError):
                await heartbeat

    async def heartbeat(self, job_id, audio_id, claim_id, lease_seconds):
        """Only this live claim can renew; cancellation/recovery revoke custody."""
        while True:
            await asyncio.sleep(min(30,max(5,lease_seconds/3)))
            try:
                async with self.session_factory() as session:
                    async with session.begin():
                        running=select(JobORM.job_id).where(JobORM.job_id==job_id,JobORM.status=='running').exists()
                        result=await session.execute(update(UploadedAudioORM).where(UploadedAudioORM.audio_id==audio_id,
                            UploadedAudioORM.claim_id==claim_id,running).values(
                                lease_expires_at=utc_now()+timedelta(seconds=lease_seconds)))
                        if result.rowcount!=1:
                            return
            except Exception:
                # Losing durable renewal makes the claim expire safely. Never
                # extend custody in memory while the database is unavailable.
                return

    async def fail(self, job_id, code, *, evidence=None, attention=False, expected_claim_id=None, only_expired=False,
                   expected_configuration=None, expected_request=None):
        if evidence is not None:
            try:
                digest(evidence)
            except (ValueError,TypeError):
                # A non-JSON/NaN provider result is not durable evidence. Its
                # failed job/cost remain recorded without invented snapshots.
                evidence=None
        async with self.session_factory() as session:
            async with session.begin():
                observed=await session.get(JobORM,job_id)
                if observed is None or observed.request_json.get('kind')!='uploaded_audio_transcription':
                    return
                parent=await session.get(UploadedAudioORM,observed.request_json['audio_id'],with_for_update=True)
                job=await session.scalar(select(JobORM).where(JobORM.job_id==job_id).with_for_update()
                    .execution_options(populate_existing=True))
                if job is None or job.status!='running':
                    return
                if parent is None or expected_claim_id is not None and parent.claim_id!=expected_claim_id:
                    return
                if only_expired and live_lease(parent):
                    return
                if evidence is not None and (expected_claim_id is not None and not live_lease(parent)
                    or expected_configuration is not None and parent.configuration_json != expected_configuration
                    or expected_request is not None and job.request_json != expected_request):
                    evidence = None
                job.status='needs_attention' if attention else 'failed';job.stage='failed';job.updated_at=utc_now()
                job.error_json={'code':code,'message':'Audio recognition requires review; source preserved',
                    'failed_stage':'analyzing_audio','retryable':False}
                if evidence is not None:
                    if parent.original_evidence_json is None:
                        parent.original_evidence_json=evidence;parent.original_evidence_sha256=digest(evidence)
                parent.claim_id=None;parent.lease_expires_at=None
                session.add(PostgresJobStore._event(row=job,event_type='uploaded_audio.failed',actor_ref='worker',payload={'code':code}))

    async def recover(self, *, include_queued=True):
        async with self.session_factory() as session:
            rows = (await session.execute(select(JobORM,UploadedAudioORM).join(UploadedAudioORM,
                UploadedAudioORM.job_id==JobORM.job_id).where(JobORM.status.in_(['queued','running']),
                JobORM.request_json['kind'].as_string()=='uploaded_audio_transcription'))).all()
            queued=[job.job_id for job,parent in rows if job.status=='queued' and include_queued]
            running=[(job.job_id,parent.claim_id) for job,parent in rows if job.status=='running' and not live_lease(parent)]
        for job_id,claim_id in running:
            await self.fail(job_id,'AUDIO_PROVIDER_OUTCOME_UNKNOWN',attention=True,
                expected_claim_id=claim_id,only_expired=True)
        for job_id in queued:
            await self.queue.rpush(AUDIO_QUEUE,job_id)
        return len(queued)

    async def cancel(self, project_id, audio_id, actor_ref):
        actor(actor_ref)
        async with self.session_factory() as session:
            async with session.begin():
                parent = await self.repository.parent(session,project_id,audio_id,lock=True)
                job = await session.get(JobORM,parent.job_id,with_for_update=True)
                if job.status in {'queued','running','needs_attention'}:
                    job.status='cancelled';job.stage='failed';job.updated_at=utc_now()
                    parent.claim_id=None;parent.lease_expires_at=None
                    session.add(PostgresJobStore._event(row=job,event_type='uploaded_audio.cancelled',actor_ref=actor_ref))
        return await self.repository.get(project_id,audio_id)

    async def edit_text(self, project_id, audio_id, payload, actor_ref):
        await self.verify_source_file(project_id,audio_id)
        def revise(versions,parent):
            current=versions[-1]
            if payload.edit.base_transcript_id not in (None,current.transcript_id):
                raise AudioConflict('AUDIO_EXPLICIT_RESTORE_REQUIRED')
            edits={s.segment_id:unicodedata.normalize('NFC',s.text) for s in payload.edit.segments}
            if not set(edits)<={s.segment_id for s in current.segments}:
                raise AudioConflict('AUDIO_SEGMENT_FOREIGN')
            changed={s.segment_id for s in current.segments if edits.get(s.segment_id,s.text)!=s.text}
            if not changed:
                return None
            derived=clone_version(current,current,actor_ref,payload.edit.note)
            segments=[]
            for old,new in zip(current.segments,derived.segments,strict=True):
                body=new.model_dump(mode='json')
                if old.segment_id in changed:
                    body.update(text=edits[old.segment_id],words=[],confidence=None)
                segments.append(body)
            return derived.model_copy(update={'confidence':None,'segments':TranscriptRead.model_validate({
                **derived.model_dump(mode='json'),'segments':segments}).segments,'provenance':{
                    **derived.provenance,'changed_segment_ids':sorted(changed),'word_timestamp_policy':'discard_for_changed_text'}})
        return await self.repository.append(project_id,audio_id,expected_version=payload.edit.expected_version,
            expected_id=payload.expected_transcript_id,source_sha256=payload.source_sha256,
            expected_timeline_version=payload.edit.expected_timeline_version,actor_ref=actor_ref,revise=revise)

    async def apply_captions(self, project_id, audio_id, payload, actor_ref):
        await self.verify_source_file(project_id, audio_id)
        return await self.repository.apply_captions(project_id, audio_id, payload, actor_ref)

    async def edit_words(self, project_id, audio_id, payload, actor_ref):
        await self.verify_source_file(project_id,audio_id)
        def revise(versions,parent):
            from .transcript_word_editing import _declared_gaps
            try:
                return revised(versions[-1],payload.edit,duration=parent.media_metadata_json['duration_seconds'],
                    actor_ref=actor_ref,gaps=_declared_gaps(versions[-1],parent.media_metadata_json['duration_seconds']))
            except ValueError as exc:
                raise AudioConflict('AUDIO_WORD_REVIEW_INVALID') from exc
        return await self.repository.append(project_id,audio_id,expected_version=payload.edit.expected_version,
            expected_id=payload.edit.expected_transcript_id,source_sha256=payload.source_sha256,
            expected_timeline_version=payload.edit.expected_timeline_version,actor_ref=actor_ref,revise=revise)

    async def restore(self, project_id, audio_id, payload, actor_ref):
        await self.verify_source_file(project_id,audio_id)
        def revise(versions,parent):
            target=next((v for v in versions if v.transcript_id==payload.target_transcript_id),None)
            if target is None:
                raise AudioConflict('AUDIO_RESTORE_TARGET_FOREIGN')
            return clone_version(target,versions[-1],actor_ref,payload.note,restored=True)
        return await self.repository.append(project_id,audio_id,expected_version=payload.expected_version,
            expected_id=payload.expected_transcript_id,source_sha256=payload.source_sha256,
            expected_timeline_version=payload.expected_timeline_version,actor_ref=actor_ref,revise=revise)
