from __future__ import annotations

import asyncio
import hashlib
import json
import math
import shutil
import uuid
from collections.abc import AsyncIterable
from decimal import Decimal
from pathlib import Path

from .asr_prompt_profile import prompt_profile_sha256, validate_prompt_profile
from .asr_derived_timing import derive_positive_duration_transcript
from .auto_edit_logic import build_highlights, build_scenes, build_silence_decisions
from .auto_edit_models import (
    AutoEditAnalysisRead,
    AutoEditAnalysisRequest,
    MediaMetadata,
    UploadCompleteRead,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadPartRead,
    UploadRead,
)
from .auto_edit_providers import (
    MediaProbe,
    MediaSignalProvider,
    ProviderNotConfigured,
    TranscriptionProvider,
    require_positive_duration_transcript,
)
from .auto_edit_repository import AutoEditRepository
from .media_security import (
    ArchiveContainerRejected,
    MediaMalwareScanner,
    MediaScanResult,
    MediaScanUnavailable,
    MediaSecurityError,
    UnsafeMediaRejected,
    reject_archive_container,
    utc_now as media_security_utc_now,
)
from .media_validation import MediaValidationError, safe_upload_filename, sniff_media
from .object_storage import ObjectStorageProvider, validate_object_key, sha256_file
from .frozen_storage_read import frozen_asset_read, asset_custody, completed_read, MAX_SOURCE_BYTES
from .bounded_storage_download import StorageDownloadError
from .platform_models import AssetRegister
from .provider_safety import (
    ProviderCallContext,
    ProviderExecutionTrace,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    ProviderTransientError,
)
from .repositories import PlatformRepository
from .auto_edit_local_evidence import frozen_video_binding, validated_evidence, rejected_evidence
from .auto_edit_source_custody import staged_trusted_video, verify_file, gather_drained


class UploadConflictError(RuntimeError):
    pass


class UploadSizeError(ValueError):
    pass


def _new_upload_id() -> str:
    return f"upl_{uuid.uuid4().hex[:24]}"


def _upload_object_key(upload: UploadRead, checksum_sha256: str) -> str:
    return validate_object_key(
        f"workspaces/{upload.workspace_id}/projects/{upload.project_id}/"
        f"uploads/{checksum_sha256[:24]}/{upload.safe_filename}"
    )


def _assemble(parts: list[Path], destination: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with destination.open("wb") as output:
        for part in parts:
            with part.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)
    return digest.hexdigest(), size


class UploadService:
    def __init__(
        self,
        *,
        repository: AutoEditRepository,
        platform: PlatformRepository,
        object_storage: ObjectStorageProvider,
        media_probe: MediaProbe,
        malware_scanner: MediaMalwareScanner,
        staging_root: Path,
        default_part_size_bytes: int,
        max_part_size_bytes: int,
        max_upload_size_bytes: int,
    ):
        self.repository = repository
        self.platform = platform
        self.object_storage = object_storage
        self.media_probe = media_probe
        self.malware_scanner = malware_scanner
        self.staging_root = staging_root.resolve()
        self.default_part_size_bytes = default_part_size_bytes
        self.max_part_size_bytes = max_part_size_bytes
        self.max_upload_size_bytes = max_upload_size_bytes

    def _upload_folder(self, upload_id: str) -> Path:
        if not upload_id.startswith("upl_") or not upload_id[4:].isalnum():
            raise ValueError("invalid upload id")
        candidate = (self.staging_root / upload_id).resolve()
        if self.staging_root not in candidate.parents:
            raise ValueError("upload staging path escaped root")
        return candidate

    async def initialize(self, payload: UploadInitRequest) -> UploadRead:
        if payload.size_bytes > self.max_upload_size_bytes:
            raise UploadSizeError("upload exceeds configured maximum size")
        safe_name = safe_upload_filename(payload.filename)
        part_size = payload.part_size_bytes or self.default_part_size_bytes
        if part_size > self.max_part_size_bytes:
            raise UploadSizeError("part size exceeds configured maximum")
        total_parts = math.ceil(payload.size_bytes / part_size)
        upload_id = _new_upload_id()
        folder = self._upload_folder(upload_id)
        folder.mkdir(parents=True, exist_ok=False)
        try:
            return await self.repository.create_upload(
                upload_id=upload_id,
                payload=payload,
                safe_filename=safe_name,
                part_size_bytes=part_size,
                total_parts=total_parts,
            )
        except Exception:
            await asyncio.to_thread(shutil.rmtree, folder, True)
            raise

    async def get(self, upload_id: str) -> UploadRead | None:
        return await self.repository.get_upload(upload_id)

    async def store_part(
        self,
        upload_id: str,
        part_number: int,
        chunks: AsyncIterable[bytes],
        *,
        expected_part_sha256: str | None,
    ) -> UploadRead:
        upload = await self.repository.get_upload(upload_id)
        if upload is None:
            raise KeyError(upload_id)
        if upload.status not in {"initialized", "uploading"}:
            raise UploadConflictError("upload is not accepting parts")
        if part_number < 1 or part_number > upload.total_parts:
            raise UploadSizeError("part number is outside the upload range")
        expected_size = (
            upload.part_size_bytes
            if part_number < upload.total_parts
            else upload.size_bytes - upload.part_size_bytes * (upload.total_parts - 1)
        )
        folder = self._upload_folder(upload_id)
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / f"part-{part_number:06d}.bin"
        temporary = destination.with_suffix(".tmp")
        digest = hashlib.sha256()
        size = 0
        try:
            with temporary.open("wb") as handle:
                async for chunk in chunks:
                    if not chunk:
                        continue
                    size += len(chunk)
                    if size > expected_size or size > self.max_part_size_bytes:
                        raise UploadSizeError("part body exceeds expected size")
                    handle.write(chunk)
                    digest.update(chunk)
            if size != expected_size:
                raise UploadSizeError("part body does not match expected size")
            checksum = digest.hexdigest()
            if expected_part_sha256 and checksum != expected_part_sha256:
                raise UploadConflictError("part checksum mismatch")
            temporary.replace(destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise
        return await self.repository.record_part(
            upload_id,
            UploadPartRead(part_number=part_number, size_bytes=size, checksum_sha256=checksum),
        )

    async def complete(
        self, upload_id: str, payload: UploadCompleteRequest
    ) -> UploadCompleteRead:
        upload = await self.repository.get_upload(upload_id)
        if upload is None:
            raise KeyError(upload_id)
        if upload.status in {"completed", "completed_duplicate"}:
            if not upload.asset_id or not upload.media_metadata:
                raise RuntimeError("completed upload is missing persisted evidence")
            asset = await self.repository.get_asset(upload.asset_id)
            if asset is None:
                raise RuntimeError("completed upload asset is missing")
            return UploadCompleteRead(
                upload=upload,
                asset_id=asset.asset_id,
                duplicate=upload.status == "completed_duplicate",
                checksum_sha256=asset.checksum_sha256,
                media_metadata=upload.media_metadata,
            )
        if upload.status not in {"initialized", "uploading"}:
            raise UploadConflictError("upload cannot be completed")
        parts_by_number = {part.part_number: part for part in upload.received_parts}
        if set(parts_by_number) != set(range(1, upload.total_parts + 1)):
            raise UploadConflictError("not all upload parts have been received")
        folder = self._upload_folder(upload_id)
        part_paths = [folder / f"part-{number:06d}.bin" for number in range(1, upload.total_parts + 1)]
        if not all(path.is_file() for path in part_paths):
            raise UploadConflictError("staged upload part is missing")
        assembled = folder / "assembled.bin"
        checksum, size = await asyncio.to_thread(_assemble, part_paths, assembled)
        expected_checksum = payload.checksum_sha256 or upload.expected_checksum_sha256
        if size != upload.size_bytes:
            await self.repository.mark_upload_failed(upload_id, "UPLOAD_SIZE_MISMATCH")
            raise UploadConflictError("assembled upload size mismatch")
        if expected_checksum and checksum != expected_checksum:
            await self.repository.mark_upload_failed(upload_id, "UPLOAD_CHECKSUM_MISMATCH")
            raise UploadConflictError("assembled upload checksum mismatch")
        await self.repository.mark_upload_quarantined(upload_id)
        try:
            reject_archive_container(assembled)
        except ArchiveContainerRejected as exc:
            now = media_security_utc_now()
            await self.repository.record_upload_scan(
                upload_id,
                MediaScanResult(
                    verdict="rejected",
                    provider="archive-deny-policy",
                    signature_version="no-archive-v1",
                    result_code="ARCHIVE_CONTAINER_REJECTED",
                    checksum_sha256=checksum,
                    started_at=now,
                    completed_at=now,
                ),
            )
            raise UnsafeMediaRejected("archive containers are rejected before media parsing") from exc
        try:
            scan = await self.malware_scanner.scan(
                assembled,
                expected_checksum_sha256=checksum,
            )
        except MediaSecurityError as exc:
            now = media_security_utc_now()
            scan = MediaScanResult(
                verdict="error",
                provider=type(self.malware_scanner).__name__,
                signature_version="runtime-unavailable",
                result_code="MALWARE_SCANNER_ERROR",
                checksum_sha256=checksum,
                started_at=now,
                completed_at=now,
            )
            await self.repository.record_upload_scan(upload_id, scan)
            raise MediaScanUnavailable("media remains quarantined because scanning failed") from exc
        await self.repository.record_upload_scan(upload_id, scan)
        if scan.verdict == "infected":
            raise UnsafeMediaRejected("unsafe media was rejected and retained in quarantine")
        if scan.verdict != "clean":
            raise MediaScanUnavailable("media remains quarantined without a clean scan verdict")
        try:
            detected_kind, detected_content_type = sniff_media(assembled, upload.declared_content_type)
            compatible = (
                upload.media_kind == detected_kind
                or (upload.media_kind == "logo" and detected_kind == "image")
                or (upload.media_kind == "music" and detected_kind == "audio")
            )
            if not compatible:
                raise MediaValidationError("declared media kind does not match media signature")
            media_metadata = await self.media_probe.probe(
                assembled,
                detected_content_type=detected_content_type,
                media_kind=upload.media_kind,
            )
        except Exception:
            await self.repository.mark_upload_failed(upload_id, "MEDIA_VALIDATION_FAILED")
            raise
        duplicate = await self.repository.find_duplicate_asset(
            project_id=upload.project_id,
            checksum_sha256=checksum,
            size_bytes=size,
        )
        if duplicate:
            finished = await self.repository.finish_upload(
                upload_id,
                asset_id=duplicate.asset_id,
                duplicate_of_asset_id=duplicate.asset_id,
                media_metadata=media_metadata,
            )
            await asyncio.to_thread(shutil.rmtree, folder, True)
            return UploadCompleteRead(
                upload=finished,
                asset_id=duplicate.asset_id,
                duplicate=True,
                checksum_sha256=checksum,
                media_metadata=media_metadata,
            )
        object_key = _upload_object_key(upload, checksum)
        try:
            stored = await self.object_storage.put_file(
                object_key=object_key,
                path=assembled,
                content_type=detected_content_type,
            )
            asset = await self.platform.register_asset(
                upload.project_id,
                AssetRegister(
                    project_version_id=upload.project_version_id,
                    asset_class="source",
                    kind=upload.media_kind,
                    filename=upload.safe_filename,
                    object_key=stored.object_key,
                    content_type=stored.content_type,
                    size_bytes=stored.size_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    storage_provider=stored.storage_provider,
                    provenance={
                        "source_type": "user_upload",
                        "rights_status": upload.rights_status,
                        "license": upload.license,
                        "source_reference": upload_id,
                        "generation_provenance": None,
                        "media_metadata": media_metadata.model_dump(mode="json"),
                        "client_filename_retained_as_evidence": upload.original_filename,
                    },
                ),
            )
        except Exception:
            await self.repository.mark_upload_failed(upload_id, "STORAGE_PERSISTENCE_FAILED")
            raise
        finished = await self.repository.finish_upload(
            upload_id,
            asset_id=asset.asset_id,
            duplicate_of_asset_id=None,
            media_metadata=media_metadata,
        )
        await asyncio.to_thread(shutil.rmtree, folder, True)
        return UploadCompleteRead(
            upload=finished,
            asset_id=asset.asset_id,
            duplicate=False,
            checksum_sha256=checksum,
            media_metadata=media_metadata,
        )


class AutoEditAnalysisService:
    algorithm_version = "v2-04.1"

    def __init__(
        self,
        *,
        repository: AutoEditRepository,
        platform: PlatformRepository,
        object_storage: ObjectStorageProvider,
        transcription_provider: TranscriptionProvider,
        signal_provider: MediaSignalProvider,
        staging_root: Path,
        provider_safety: ProviderSafetyController | None = None,
        derived_timing_enabled: bool = False,
    ):
        self.repository = repository
        self.platform = platform
        self.object_storage = object_storage
        self.transcription_provider = transcription_provider
        self.signal_provider = signal_provider
        self.staging_root = staging_root.resolve()
        self.provider_safety = provider_safety or ProviderSafetyController.fail_closed()
        self.derived_timing_enabled = derived_timing_enabled

    async def analyze(
        self, project_id: str, payload: AutoEditAnalysisRequest
    ) -> AutoEditAnalysisRead:
        binding = frozen_video_binding(self.transcription_provider)
        if binding is None:
            return await self._analyze(project_id, payload)
        if payload.word_timing_policy != 'strict_provider_intervals':
            # Local CPU evidence never authorizes invented word intervals.
            raise ValueError('LOCAL_VIDEO_STRICT_PROVIDER_TIMING_REQUIRED')
        await asyncio.to_thread(self.transcription_provider.verify)
        async with staged_trusted_video(self.repository, self.object_storage, project_id, payload.asset_id,
                self.staging_root, self.transcription_provider.max_file_bytes) as (path, snapshot):
            return await self._analyze(project_id, payload, local_path_override=path,
                local_source_snapshot=snapshot, local_binding=binding)

    async def prepare(self, project_id, payload, *, local_binding=None):
        if (
            payload.word_timing_policy != "strict_provider_intervals"
            and not self.derived_timing_enabled
        ):
            raise ValueError("DERIVED_TIMING_POLICY_NOT_ENABLED")
        asset = await self.repository.get_asset(payload.asset_id)
        if asset is None or asset.project_id != project_id:
            raise KeyError(payload.asset_id)
        if asset.asset_class != "source" or asset.kind != "video":
            raise ValueError("V2-04 analysis requires a source video asset")
        metadata_payload = asset.provenance.get("media_metadata")
        if not isinstance(metadata_payload, dict):
            raise ValueError("source asset is missing validated media metadata")
        source_media = MediaMetadata.model_validate(metadata_payload)
        if not source_media.duration_seconds or source_media.duration_seconds <= 0:
            raise ValueError("source video duration is unavailable")
        # Freeze before cache lookup as well as execution: W1 cannot reuse an
        # otherwise-identical W0 analysis, nor drift between context and dispatch.
        transcription_provider = self.transcription_provider
        asr_prompt_profile = validate_prompt_profile(
            getattr(transcription_provider, "asr_prompt_profile", None)
        )
        profile_binding = (
            {"asr_prompt_profile_sha256": prompt_profile_sha256(asr_prompt_profile)}
            if asr_prompt_profile is not None
            else {}
        )
        if local_binding is not None:
            profile_binding = {**profile_binding, 'local_video_binding_sha256': local_binding['sha256']}
        profile_kwargs = (
            {"expected_asr_prompt_profile": asr_prompt_profile}
            if hasattr(transcription_provider, "asr_prompt_profile")
            else {}
        )
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "asset_checksum": asset.checksum_sha256,
                    "configuration": payload.model_dump(mode="json"),
                    "transcription_provider": transcription_provider.key,
                    "signal_provider": self.signal_provider.key,
                    **({"signal_algorithm": self.signal_provider.algorithm_version}
                       if getattr(self.signal_provider, "algorithm_version", None) else {}),
                    "algorithm_version": self.algorithm_version,
                    **profile_binding,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        provenance = {
            'algorithm_version': self.algorithm_version, 'source_asset_checksum': asset.checksum_sha256,
            'source_media_mutated': False, 'publish_requested': False, 'paid_external_call': False,
            'vision_analysis': 'deferred-to-v2-05',
            **({'local_video_execution': 'synchronous_partial', 'human_review_required': True,
                'production_acceptance_verified': False, 'automatic_model_replay': False} if local_binding else {}),
            **profile_binding,
        }
        return {'asset': asset, 'source_media': source_media, 'fingerprint': fingerprint,
            'profile_binding': profile_binding, 'profile_kwargs': profile_kwargs,
            'asr_prompt_profile': asr_prompt_profile, 'provenance': provenance}

    async def _analyze(self, project_id, payload, *, local_path_override=None,
                       local_source_snapshot=None, local_binding=None, analysis_id_override=None, job_guard=None):
        prepared = await self.prepare(project_id, payload, local_binding=local_binding)
        asset, source_media, fingerprint = prepared['asset'], prepared['source_media'], prepared['fingerprint']
        profile_binding, profile_kwargs = prepared['profile_binding'], prepared['profile_kwargs']
        asr_prompt_profile = prepared['asr_prompt_profile']
        transcription_provider = self.transcription_provider
        source_provider_identity = self._source_provider_identity()
        if job_guard is not None:
            await job_guard.before_execute(prepared)
        if analysis_id_override is None:
            analysis_id, created = await self.repository.create_analysis(
                project_id=project_id, asset=asset, fingerprint=fingerprint, configuration=payload,
                source_media=source_media, provenance=prepared['provenance'])
        else:
            analysis_id, created = analysis_id_override, True
        if not created:
            existing = await self.repository.get_analysis(analysis_id)
            if existing is None:
                raise RuntimeError("analysis fingerprint exists without readable state")
            return existing
        if job_guard is None:
            await self.repository.mark_analysis_running(analysis_id)
        elif getattr(transcription_provider, 'supports_durable_cancellation', False):
            profile_kwargs = {**profile_kwargs, 'is_cancelled': job_guard.is_cancelled}
        self.staging_root.mkdir(parents=True, exist_ok=True)
        local_path = local_path_override or self.staging_root / f"{analysis_id}-{safe_upload_filename(asset.filename)}"
        local_result_evidence = None
        try:
            if local_source_snapshot is None:
                await self._download_analysis_source(prepared,project_id,payload,local_path,job_guard=job_guard,
                    expected_provider_identity=source_provider_identity)
            else:
                await verify_file(local_path, local_source_snapshot)
                if local_binding is not None:
                    await asyncio.to_thread(transcription_provider.verify)
                    if frozen_video_binding(transcription_provider) != local_binding:
                        raise ValueError('AUTO_EDIT_LOCAL_VIDEO_BINDING_CHANGED')
            if source_media.audio_codec is None:
                # A validated video with NO audio stream needs visual analysis, not fabricated ASR.
                signals = await self.signal_provider.analyze(local_path, metadata=source_media,
                    silence_threshold_db=payload.silence_threshold_db,
                    minimum_silence_duration=payload.minimum_silence_duration)
                scenes = build_scenes(duration=float(source_media.duration_seconds),
                    signals=signals, transcript=None)
                if job_guard is not None:
                    await job_guard.verify_original_file(local_path)
                await self.repository.save_analysis_results(analysis_id=analysis_id,
                    asset_id=asset.asset_id, provider_key=self.signal_provider.key, transcript=None,
                    scenes=scenes, silence_decisions=[],
                    highlights=build_highlights(scenes=scenes, top_k=payload.top_highlights),
                    signal_evidence={**signals.provenance,"waveform":signals.waveform,"visual":signals.visual},
                    local_source_snapshot=local_source_snapshot, job_guard=job_guard)
                result = await self.repository.get_analysis(analysis_id)
                if result is None:
                    raise RuntimeError("visual analysis was not persisted")
                return result
            execution_trace = ProviderExecutionTrace()
            dispatched = False
            async def dispatch_transcription():
                nonlocal dispatched
                if job_guard is not None:
                    if dispatched:
                        raise TimeoutError('AUTO_EDIT_PROVIDER_OUTCOME_UNKNOWN')
                    if await job_guard.is_cancelled():
                        raise asyncio.CancelledError()
                dispatched = True
                return await transcription_provider.transcribe(local_path, metadata=source_media,
                    checksum_sha256=asset.checksum_sha256, execution_trace=execution_trace, **profile_kwargs)
            operation_key = (
                payload.acceptance_operation_id
                if transcription_provider.external_call
                and payload.acceptance_operation_id is not None
                else f"{analysis_id}:transcription"
            )
            transcription_capability = getattr(
                transcription_provider,
                "capability",
                "transcription",
            )
            execution_gate = getattr(
                getattr(self.provider_safety, "policy", None),
                "execution_gate",
                None,
            )
            transcription = self.provider_safety.execute(
                ProviderCallContext(
                    operation_key=operation_key,
                    acceptance_lineage_id=(
                        execution_gate.acceptance_lineage_id
                        if transcription_provider.external_call
                        and execution_gate is not None
                        else None
                    ),
                    workspace_id=asset.workspace_id,
                    project_id=asset.project_id,
                    job_id=job_guard.job_id if job_guard else None,
                    provider_key=transcription_provider.key,
                    model=transcription_provider.model,
                    capability=transcription_capability,
                    operation=(
                        "flow_a_asr"
                        if transcription_provider.external_call
                        else "auto_edit_transcription"
                    ),
                    external_call=transcription_provider.external_call,
                    paid=transcription_provider.paid,
                    estimated_cost_vnd=transcription_provider.estimated_cost_vnd,
                    credential_alias=transcription_provider.credential_alias,
                    asset_id=asset.asset_id,
                    asset_hash=asset.checksum_sha256,
                    input_media_kind=(
                        source_media.media_kind
                        if transcription_provider.external_call
                        and source_media.media_kind in {"audio", "video"}
                        else None
                    ),
                    input_file_bytes=(
                        local_path.stat().st_size
                        if transcription_provider.external_call
                        else None
                    ),
                    input_duration_seconds=(
                        source_media.duration_seconds
                        if transcription_provider.external_call
                        else None
                    ),
                    requested_language=(
                        getattr(transcription_provider, "language", None)
                        if transcription_provider.external_call
                        else None
                    ),
                    response_format=(
                        getattr(transcription_provider, "response_format", None)
                        if transcription_provider.external_call
                        else None
                    ),
                    timestamp_granularities=(
                        getattr(transcription_provider, "timestamp_granularities", ())
                        if transcription_provider.external_call
                        else ()
                    ),
                    asr_prompt_profile=asr_prompt_profile,
                    # A real Flow A run must supply the separate G-03 rights record. Basic upload
                    # labels are not silently promoted into approved provider-rights evidence.
                    rights_required=transcription_provider.external_call,
                    rights=[],
                ),
                dispatch_transcription,
                actual_cost=lambda result: result.actual_cost_vnd,
                timeout_evidence_factory=lambda timeout_envelope, error: (
                    execution_trace.timeout_evidence(
                        code="CONTROLLER_ENVELOPE_TIMEOUT",
                        timeout_kind="controller_envelope",
                        timeout_envelope=timeout_envelope,
                        error=error,
                        retryable=True,
                        provider_error_message=(
                            "Transcription provider operation exceeded the controller deadline"
                        ),
                    )
                ),
            )
            async def capture_transcription():
                nonlocal local_result_evidence
                result = await transcription
                if local_binding is not None:
                    local_result_evidence = validated_evidence(result.value.provenance.get('local_video_evidence'),
                        local_binding, local_source_snapshot)
                    if local_result_evidence is None:
                        raise ValueError('AUTO_EDIT_LOCAL_VIDEO_RESULT_EVIDENCE_INVALID')
                if job_guard is not None:
                    await job_guard.record_result(result)
                return result
            transcription_result, signals = await gather_drained(
                capture_transcription(),
                self.signal_provider.analyze(
                    local_path,
                    metadata=source_media,
                    silence_threshold_db=payload.silence_threshold_db,
                    minimum_silence_duration=payload.minimum_silence_duration,
                ),
            )
            if local_binding is not None:
                await asyncio.to_thread(transcription_provider.verify)
                if frozen_video_binding(transcription_provider) != local_binding:
                    raise ValueError('AUTO_EDIT_LOCAL_VIDEO_BINDING_CHANGED')
                await verify_file(local_path, local_source_snapshot)
                async with staged_trusted_video(self.repository, self.object_storage, project_id, payload.asset_id,
                        self.staging_root, transcription_provider.max_file_bytes, expected=local_source_snapshot):
                    pass
            elif job_guard is not None:
                await job_guard.verify_original_file(local_path)
            transcript = type(transcription_result.value)(
                language=transcription_result.value.language,
                confidence=transcription_result.value.confidence,
                segments=transcription_result.value.segments,
                provenance={
                    **transcription_result.value.provenance,
                    "provider_safety_receipt": transcription_result.receipt.model_dump(mode="json"),
                },
                actual_cost_vnd=transcription_result.value.actual_cost_vnd,
            )
            downstream_transcript = (
                require_positive_duration_transcript(transcript)
                if payload.word_timing_policy == "strict_provider_intervals"
                else derive_positive_duration_transcript(
                    transcript,
                    algorithm=payload.word_timing_policy,
                )
            )
            scenes = build_scenes(
                duration=float(source_media.duration_seconds),
                signals=signals,
                transcript=downstream_transcript,
            )
            silence = build_silence_decisions(
                signals=signals,
                transcript=downstream_transcript,
                config=payload,
            )
            highlights = build_highlights(scenes=scenes, top_k=payload.top_highlights)
            await self.platform.record_provider_operation(
                workspace_id=asset.workspace_id,
                project_id=asset.project_id,
                job_id=job_guard.job_id if job_guard else None,
                provider_key=transcription_provider.key,
                capability=transcription_capability,
                operation=f"auto-edit-transcript:{analysis_id}",
                model=transcription_provider.model,
                units=Decimal(str(source_media.duration_seconds)) / Decimal("60"),
                unit_name="audio_minute",
                estimated_cost=transcription_provider.estimated_cost_vnd,
                actual_cost=transcription_result.value.actual_cost_vnd,
                metadata={
                    "budget_reserved_vnd": str(transcription_result.receipt.charged_cost_vnd),
                    "budget_reservation_is_billed_cost": False,
                    "estimated_cost_basis": "provider_admission_estimate",
                    "actual_cost_known": transcription_result.value.actual_cost_vnd is not None,
                    "fixture": transcript.provenance.get("fixture", False),
                    "external_call": transcript.provenance.get("external_call", False),
                    "currency": "VND",
                    "cost_receipt_recorded": bool(
                        transcript.provenance.get("cost_receipt")
                    ),
                    **profile_binding,
                },
            )
            await self.platform.record_provider_operation(
                workspace_id=asset.workspace_id,
                project_id=asset.project_id,
                job_id=job_guard.job_id if job_guard else None,
                provider_key=self.signal_provider.key,
                capability="media_analysis",
                operation=f"auto-edit-signals:{analysis_id}",
                estimated_cost=Decimal("0"),
                actual_cost=Decimal("0"),
                metadata=signals.provenance,
            )
            await self.repository.save_analysis_results(
                analysis_id=analysis_id,
                asset_id=asset.asset_id,
                provider_key=transcription_provider.key,
                transcript=downstream_transcript,
                scenes=scenes,
                silence_decisions=silence,
                highlights=highlights,
                signal_evidence={**signals.provenance,"waveform":signals.waveform,"visual":signals.visual},
                local_source_snapshot=local_source_snapshot,
                job_guard=job_guard,
            )
        except asyncio.CancelledError:
            await self.repository.mark_analysis_failed(analysis_id, 'AUTO_EDIT_LOCAL_OUTCOME_UNKNOWN' if local_binding else 'AUTO_EDIT_ANALYSIS_CANCELLED',
                local_evidence=local_result_evidence, expected_source_sha256=asset.checksum_sha256, job_guard=job_guard)
            raise
        except ProviderNotConfigured:
            await self.repository.mark_analysis_failed(analysis_id, "PROVIDER_NOT_CONFIGURED",
                local_evidence=local_result_evidence, expected_source_sha256=asset.checksum_sha256, job_guard=job_guard)
            raise
        except ProviderSafetyBlocked:
            await self.repository.mark_analysis_failed(analysis_id, "PROVIDER_SAFETY_BLOCKED",
                local_evidence=local_result_evidence, expected_source_sha256=asset.checksum_sha256, job_guard=job_guard)
            raise
        except Exception as exc:
            evidence = local_result_evidence or rejected_evidence(exc, local_binding, local_source_snapshot)
            code = ('AUTO_EDIT_LOCAL_OUTCOME_UNKNOWN' if (local_binding or job_guard) and isinstance(exc, (TimeoutError,ProviderTransientError))
                    else 'AUTO_EDIT_ANALYSIS_FAILED')
            await self.repository.mark_analysis_failed(analysis_id, code,
                local_evidence=evidence, expected_source_sha256=asset.checksum_sha256, job_guard=job_guard)
            raise
        finally:
            if local_path_override is None:
                local_path.unlink(missing_ok=True)
        result = await self.repository.get_analysis(analysis_id)
        if result is None:
            raise RuntimeError("analysis result was not persisted")
        return result

    async def get(self, analysis_id: str) -> AutoEditAnalysisRead | None:
        return await self.repository.get_analysis(analysis_id)

    def _source_provider_identity(self):
        return tuple(tuple(getattr(provider,name,None) for name in (
            'key','model','external_call','paid','credential_alias','estimated_cost_vnd','algorithm_version',
            'max_file_bytes','max_duration_seconds'))
            for provider in (self.transcription_provider,self.signal_provider))

    async def _download_analysis_source(self,prepared,project_id,payload,path,*,job_guard=None,expected_provider_identity=None):
        """Admit registered source bytes, then recheck inputs before analysis."""
        asset=prepared['asset'];identity=expected_provider_identity or self._source_provider_identity();custody=asset_custody(asset)
        project=await self.platform.get_project(project_id)
        if project is None or project.project_id!=project_id:
            raise ValueError('AUTO_EDIT_SOURCE_SCOPE_CHANGED')
        if self._source_provider_identity()!=identity:
            raise ValueError('AUTO_EDIT_SOURCE_PROVIDER_CHANGED')
        try:
            proof=frozen_asset_read(asset,workspace_id=project.workspace_id,project_id=project_id,
                storage=self.object_storage,maximum=MAX_SOURCE_BYTES)
            await proof.download(self.object_storage,path)
            if await completed_read(asyncio.to_thread(sha256_file,path))!=asset.checksum_sha256:
                raise ValueError('AUTO_EDIT_SOURCE_BYTES_CHANGED')
        except StorageDownloadError as error:
            if error.code in {'STORAGE_DOWNLOAD_HASH_MISMATCH','STORAGE_DOWNLOAD_SIZE_MISMATCH','STORAGE_DOWNLOAD_SIZE_LIMIT'}:
                raise ValueError('source checksum changed') from None
            raise ValueError('AUTO_EDIT_SOURCE_DOWNLOAD_FAILED') from None
        except Exception:
            raise ValueError('AUTO_EDIT_SOURCE_DOWNLOAD_FAILED') from None
        current=await self.prepare(project_id,payload)
        if asset_custody(current['asset'])!=custody or current['fingerprint']!=prepared['fingerprint'] \
                or current['source_media']!=prepared['source_media'] or self._source_provider_identity()!=identity:
            raise ValueError('AUTO_EDIT_SOURCE_CUSTODY_CHANGED')
        if job_guard is not None:
            await job_guard.before_execute(current)
            if await job_guard.is_cancelled():
                raise asyncio.CancelledError()

    async def list(self, project_id: str) -> list[AutoEditAnalysisRead]:
        if await self.platform.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_analyses(project_id)
