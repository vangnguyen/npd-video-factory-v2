"""Scoped SQL custody and CAS for independent uploaded audio evidence."""
import hashlib
import json
import math
import uuid
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from .auto_edit_db import UploadSessionORM
from .auto_edit_models import MediaMetadata, TranscriptRead
from .db import AssetORM, JobORM, VideoProjectORM, utc_now
from .models import JobRecord, UploadedAudioJobInput
from .repositories import PostgresJobStore
from .timeline_db import TimelineORM, TimelineVersionORM
from .uploaded_audio_db import UploadedAudioORM, UploadedAudioVersionORM
from .uploaded_audio_models import AudioTranscriptionRead


class AudioConflict(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def identity(prefix):
    return prefix + '_' + uuid.uuid4().hex[:24]


def actor(value):
    if not isinstance(value, str) or not value or len(value) > 160 or any(ord(c) < 32 for c in value):
        raise AudioConflict('AUDIO_ACTOR_INVALID')
    return value


async def source(session, project_id, asset_id, *, parent=None):
    project = await session.get(VideoProjectORM, project_id)
    asset = await session.get(AssetORM, asset_id)
    if (project is None or asset is None or asset.project_id != project_id
        or asset.workspace_id != project.workspace_id):
        raise KeyError(asset_id)
    if asset.asset_class != 'source' or asset.kind != 'audio' or not asset.content_type.startswith('audio/'):
        raise AudioConflict('AUDIO_SOURCE_REQUIRED')
    upload = await session.get(UploadSessionORM, asset.provenance.get('source_reference', ''))
    if (asset.provenance.get('source_type') != 'user_upload' or upload is None
        or upload.asset_id != asset_id or upload.project_id != project_id
        or upload.workspace_id != project.workspace_id
        or upload.status not in {'completed', 'completed_duplicate'}
        or upload.quarantine_state != 'trusted' or upload.trusted_at is None
        or upload.scan_checksum_sha256 != asset.checksum_sha256):
        raise AudioConflict('AUDIO_TRUSTED_UPLOAD_REQUIRED')
    try:
        media = MediaMetadata.model_validate(asset.provenance.get('media_metadata'))
    except ValueError:
        raise AudioConflict('AUDIO_METADATA_INVALID') from None
    duration = media.duration_seconds
    if (media.media_kind != 'audio' or media.audio_codec is None or media.video_codec is not None
        or duration is None or not math.isfinite(duration) or not 0 < duration <= 3600):
        raise AudioConflict('AUDIO_METADATA_INVALID')
    if upload.media_metadata_json != media.model_dump(mode='json') or media.detected_content_type != asset.content_type:
        raise AudioConflict('AUDIO_METADATA_CHANGED')
    if parent is not None and (parent.workspace_id != project.workspace_id
        or parent.asset_id != asset_id or parent.source_sha256 != asset.checksum_sha256
        or parent.source_size_bytes != asset.size_bytes
        or parent.media_metadata_json != media.model_dump(mode='json')):
        raise AudioConflict('AUDIO_SOURCE_CHANGED')
    return project, asset, media


class UploadedAudioRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def parent(self, session, project_id, audio_id, *, lock=False):
        query = select(UploadedAudioORM).where(UploadedAudioORM.audio_id == audio_id,
            UploadedAudioORM.project_id == project_id)
        if lock:
            query = query.with_for_update()
        parent = await session.scalar(query)
        if parent is None:
            raise KeyError(audio_id)
        await source(session, project_id, parent.asset_id, parent=parent)
        return parent

    async def versions(self, session, parent):
        if parent.current_version > 51:
            raise AudioConflict('AUDIO_HISTORY_CHANGED')
        rows = (await session.scalars(select(UploadedAudioVersionORM).where(
            UploadedAudioVersionORM.audio_id == parent.audio_id).order_by(UploadedAudioVersionORM.version))).all()
        values = []
        for index, row in enumerate(rows, 1):
            try:
                unchanged=digest(row.transcript_json)==row.transcript_sha256
                value = TranscriptRead.model_validate(row.transcript_json)
            except (ValueError,TypeError):
                raise AudioConflict('AUDIO_HISTORY_CHANGED') from None
            if not unchanged:
                raise AudioConflict('AUDIO_HISTORY_CHANGED')
            if (value.transcript_id != row.transcript_id or value.version != index or row.version != index
                or value.asset_id != parent.asset_id or value.analysis_id != parent.audio_id
                or value.is_original_evidence != (index == 1)
                or index > 1 and value.provenance.get('derived_from_transcript_id') not in {v.transcript_id for v in values}):
                raise AudioConflict('AUDIO_HISTORY_CHANGED')
            values.append(value)
        if len(values) != parent.current_version:
            raise AudioConflict('AUDIO_HISTORY_CHANGED')
        if parent.original_evidence_json is not None:
            try:
                unchanged=digest(parent.original_evidence_json)==parent.original_evidence_sha256
            except (ValueError,TypeError):
                raise AudioConflict('AUDIO_ORIGINAL_EVIDENCE_CHANGED') from None
            if not unchanged:
                raise AudioConflict('AUDIO_ORIGINAL_EVIDENCE_CHANGED')
            if values:
                # Reconstruct the first normalized snapshot from immutable returned
                # provider evidence. Hashes alone do not prove normalized lineage.
                from .uploaded_audio_service import normalize_evidence
                try:
                    expected = normalize_evidence(parent.original_evidence_json, parent,
                        created_at=values[0].created_at)
                except (ValueError,TypeError,KeyError):
                    raise AudioConflict('AUDIO_ORIGINAL_EVIDENCE_CHANGED') from None
                if expected != values[0]:
                    raise AudioConflict('AUDIO_ORIGINAL_EVIDENCE_CHANGED')
        elif values:
            raise AudioConflict('AUDIO_ORIGINAL_EVIDENCE_CHANGED')
        return values

    async def get(self, project_id, audio_id):
        async with self.session_factory() as session:
            parent = await self.parent(session, project_id, audio_id)
            versions = await self.versions(session, parent)
            job = await session.get(JobORM, parent.job_id)
            if (job is None or job.project_id != project_id or job.workspace_id != parent.workspace_id
                or job.request_json.get('audio_id') != audio_id):
                raise AudioConflict('AUDIO_JOB_CHANGED')
            timeline = await session.scalar(select(TimelineORM).where(TimelineORM.project_id == project_id))
            return AudioTranscriptionRead(audio_id=audio_id, workspace_id=parent.workspace_id,
                project_id=project_id, asset_id=parent.asset_id, source_sha256=parent.source_sha256,
                job=PostgresJobStore._record(job).model_dump(mode='json'),
                original=versions[0] if versions else None, current=versions[-1] if versions else None,
                versions=versions, timeline_version=timeline.current_version if timeline else None)

    async def list(self, project_id):
        async with self.session_factory() as session:
            if await session.get(VideoProjectORM, project_id) is None:
                raise KeyError(project_id)
            ids = (await session.scalars(select(UploadedAudioORM.audio_id).where(
                UploadedAudioORM.project_id == project_id).order_by(UploadedAudioORM.created_at))).all()
        return [await self.get(project_id, audio_id) for audio_id in ids]

    async def create(self, project_id, payload, provider_binding, actor_ref):
        actor(actor_ref)
        key = digest([project_id, payload.idempotency_key])
        request_sha = digest([payload.model_dump(mode='json'), provider_binding])
        audio_id = 'aud_' + key[:24]
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    project, asset, media = await source(session, project_id, payload.asset_id)
                    if asset.checksum_sha256 != payload.source_sha256:
                        raise AudioConflict('AUDIO_SOURCE_CHANGED')
                    old = await session.get(UploadedAudioORM, audio_id)
                    if old is not None:
                        if old.project_id != project_id or old.request_sha256 != request_sha:
                            raise AudioConflict('AUDIO_IDEMPOTENCY_CONFLICT')
                        return audio_id
                    job_id = 'job_audio_' + key[:24]
                    record = JobRecord.new(job_id=job_id, workspace_id=project.workspace_id,
                        project_id=project_id, project_version_id=project.current_version_id,
                        request=UploadedAudioJobInput(audio_id=audio_id, source_sha256=asset.checksum_sha256,
                            provider_binding_sha256=digest(provider_binding), actor_ref=actor_ref))
                    job = JobORM(job_id=job_id, workspace_id=project.workspace_id, project_id=project_id,
                        project_version_id=project.current_version_id, status='queued', stage='queued', progress=0,
                        request_json=record.request.model_dump(mode='json'), artifacts_json=[], created_at=record.created_at,
                        updated_at=record.updated_at)
                    session.add(job)
                    await session.flush()
                    session.add(PostgresJobStore._event(row=job, event_type='uploaded_audio.queued', actor_ref=actor_ref))
                    session.add(UploadedAudioORM(audio_id=audio_id, workspace_id=project.workspace_id,
                        project_id=project_id, asset_id=asset.asset_id, job_id=job_id, source_sha256=asset.checksum_sha256,
                        source_size_bytes=asset.size_bytes, request_key_sha256=key, request_sha256=request_sha,
                        configuration_json={'request':payload.model_dump(mode='json'), 'provider':provider_binding},
                        media_metadata_json=media.model_dump(mode='json'), current_version=0))
            return audio_id
        except IntegrityError:
            async with self.session_factory() as session:
                row = await session.get(UploadedAudioORM, audio_id)
                if row and row.project_id == project_id and row.request_sha256 == request_sha:
                    return audio_id
            raise AudioConflict('AUDIO_IDEMPOTENCY_CONFLICT') from None

    async def append(self, project_id, audio_id, *, expected_version, expected_id,
                     source_sha256, expected_timeline_version, actor_ref, revise):
        actor(actor_ref)
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    parent = await self.parent(session, project_id, audio_id, lock=True)
                    versions = await self.versions(session, parent)
                    if (not versions or parent.current_version != expected_version
                        or versions[-1].transcript_id != expected_id):
                        raise AudioConflict('AUDIO_TRANSCRIPT_VERSION_CHANGED')
                    if parent.source_sha256 != source_sha256:
                        raise AudioConflict('AUDIO_SOURCE_CHANGED')
                    if parent.current_version >= 51:
                        raise AudioConflict('AUDIO_TRANSCRIPT_HISTORY_LIMIT')
                    timeline = await session.scalar(select(TimelineORM).where(
                        TimelineORM.project_id == project_id).with_for_update())
                    if expected_timeline_version != (timeline.current_version if timeline else None):
                        raise AudioConflict('AUDIO_TIMELINE_VERSION_CHANGED')
                    if timeline:
                        version = await session.get(TimelineVersionORM, timeline.current_version_id)
                        if version is None or timeline.workspace_id != parent.workspace_id:
                            raise AudioConflict('AUDIO_TIMELINE_CHANGED')
                        prior_ids = {v.transcript_id for v in versions}
                        for track in version.snapshot_json['tracks']:
                            for clip in track['clips']:
                                meta = clip.get('metadata', {})
                                if (meta.get('transcript_id') in prior_ids
                                    or meta.get('audio_transcription_id') == audio_id):
                                    # Audio source mappings differ from video source mappings.
                                    # Keep approved captions untouched until explicitly reviewed.
                                    raise AudioConflict('AUDIO_CANONICAL_CAPTION_REVIEW_REQUIRED')
                    value = revise(versions, parent)
                    if value is None:
                        return await self.get(project_id, audio_id)
                    count = await session.execute(update(UploadedAudioORM).where(
                        UploadedAudioORM.audio_id == audio_id,
                        UploadedAudioORM.current_version == expected_version).values(current_version=expected_version+1))
                    if count.rowcount != 1:
                        raise AudioConflict('AUDIO_TRANSCRIPT_VERSION_CHANGED')
                    session.add(self.version_row(value, actor_ref))
                    job = await session.get(JobORM, parent.job_id)
                    session.add(PostgresJobStore._event(row=job, event_type='uploaded_audio.transcript_version_saved',
                        actor_ref=actor_ref, payload={'transcript_id':value.transcript_id,'version':value.version,
                            'source_media_mutated':False,'timeline_mutated':False,'provider_calls':0}))
            return await self.get(project_id, audio_id)
        except (IntegrityError, OperationalError) as exc:
            if isinstance(exc, OperationalError) and 'locked' not in str(exc).lower():
                raise
            raise AudioConflict('AUDIO_TRANSCRIPT_VERSION_CHANGED') from exc

    @staticmethod
    def version_row(value, actor_ref):
        body = value.model_dump(mode='json')
        return UploadedAudioVersionORM(transcript_id=value.transcript_id, audio_id=value.analysis_id,
            version=value.version, transcript_json=body, transcript_sha256=digest(body),
            actor_ref=actor_ref, created_at=value.created_at)
