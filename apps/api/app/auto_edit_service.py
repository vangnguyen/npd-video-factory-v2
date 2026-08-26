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
from .auto_edit_providers import MediaProbe, MediaSignalProvider, ProviderNotConfigured, TranscriptionProvider
from .auto_edit_repository import AutoEditRepository
from .media_validation import MediaValidationError, safe_upload_filename, sniff_media
from .object_storage import ObjectStorageProvider, validate_object_key
from .platform_models import AssetRegister
from .repositories import PlatformRepository


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
        staging_root: Path,
        default_part_size_bytes: int,
        max_part_size_bytes: int,
        max_upload_size_bytes: int,
    ):
        self.repository = repository
        self.platform = platform
        self.object_storage = object_storage
        self.media_probe = media_probe
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
    ):
        self.repository = repository
        self.platform = platform
        self.object_storage = object_storage
        self.transcription_provider = transcription_provider
        self.signal_provider = signal_provider
        self.staging_root = staging_root.resolve()

    async def analyze(
        self, project_id: str, payload: AutoEditAnalysisRequest
    ) -> AutoEditAnalysisRead:
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
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "asset_checksum": asset.checksum_sha256,
                    "configuration": payload.model_dump(mode="json"),
                    "transcription_provider": self.transcription_provider.key,
                    "signal_provider": self.signal_provider.key,
                    "algorithm_version": self.algorithm_version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        analysis_id, created = await self.repository.create_analysis(
            project_id=project_id,
            asset=asset,
            fingerprint=fingerprint,
            configuration=payload,
            source_media=source_media,
            provenance={
                "algorithm_version": self.algorithm_version,
                "source_asset_checksum": asset.checksum_sha256,
                "source_media_mutated": False,
                "publish_requested": False,
                "paid_external_call": False,
                "vision_analysis": "deferred-to-v2-05",
            },
        )
        if not created:
            existing = await self.repository.get_analysis(analysis_id)
            if existing is None:
                raise RuntimeError("analysis fingerprint exists without readable state")
            return existing
        await self.repository.mark_analysis_running(analysis_id)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        local_path = self.staging_root / f"{analysis_id}-{asset.filename}"
        try:
            await self.object_storage.download_file(object_key=asset.object_key, destination=local_path)
            transcript, signals = await asyncio.gather(
                self.transcription_provider.transcribe(
                    local_path,
                    metadata=source_media,
                    checksum_sha256=asset.checksum_sha256,
                ),
                self.signal_provider.analyze(
                    local_path,
                    metadata=source_media,
                    silence_threshold_db=payload.silence_threshold_db,
                    minimum_silence_duration=payload.minimum_silence_duration,
                ),
            )
            scenes = build_scenes(
                duration=float(source_media.duration_seconds),
                signals=signals,
                transcript=transcript,
            )
            silence = build_silence_decisions(signals=signals, transcript=transcript, config=payload)
            highlights = build_highlights(scenes=scenes, top_k=payload.top_highlights)
            await self.platform.record_provider_operation(
                workspace_id=asset.workspace_id,
                project_id=asset.project_id,
                job_id=None,
                provider_key=self.transcription_provider.key,
                capability="transcription",
                operation=f"auto-edit-transcript:{analysis_id}",
                estimated_cost=Decimal("0"),
                actual_cost=Decimal("0"),
                metadata={"fixture": transcript.provenance.get("fixture", False)},
            )
            await self.platform.record_provider_operation(
                workspace_id=asset.workspace_id,
                project_id=asset.project_id,
                job_id=None,
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
                provider_key=self.transcription_provider.key,
                transcript=transcript,
                scenes=scenes,
                silence_decisions=silence,
                highlights=highlights,
            )
        except ProviderNotConfigured:
            await self.repository.mark_analysis_failed(analysis_id, "PROVIDER_NOT_CONFIGURED")
            raise
        except Exception:
            await self.repository.mark_analysis_failed(analysis_id, "AUTO_EDIT_ANALYSIS_FAILED")
            raise
        finally:
            local_path.unlink(missing_ok=True)
        result = await self.repository.get_analysis(analysis_id)
        if result is None:
            raise RuntimeError("analysis result was not persisted")
        return result

    async def get(self, analysis_id: str) -> AutoEditAnalysisRead | None:
        return await self.repository.get_analysis(analysis_id)

    async def list(self, project_id: str) -> list[AutoEditAnalysisRead]:
        if await self.platform.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_analyses(project_id)
