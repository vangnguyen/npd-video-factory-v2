from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Protocol

from jsonschema import Draft202012Validator

from .auto_edit_repository import AutoEditRepository
from .media_intelligence_repository import MediaIntelligenceRepository
from .object_storage import ObjectStorageProvider, validate_object_key, sha256_file
from .platform_models import AssetRead, AssetRegister
from .repositories import PlatformRepository
from .timeline_logic import TimelineEditError, apply_operations, build_initial_timeline
from .timeline_models import (
    PreviewCreateRequest,
    PreviewRead,
    TimelineCreateRequest,
    TimelineMutationRequest,
    TimelineRead,
    TimelineRestoreRequest,
    TimelineSnapshot,
    TimelineVersionRead,
)
from .timeline_repository import TimelineRepository
from .timeline_proxy import (
    ProxyRenderResult, ProxyRenderer, DeterministicProxyRenderer,
    FFmpegProxyRenderer, PreviewCancelledError,
)


PREVIEW_QUEUE_KEY = "npd:video-factory:v2:preview:queued"
PREVIEW_PROCESSING_KEY = "npd:video-factory:v2:preview:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


class TimelineContractValidator:
    def __init__(self, schema_path: Path):
        self.schema_path = schema_path
        self._validator: Draft202012Validator | None = None

    def validate(self, snapshot: TimelineSnapshot) -> None:
        if self._validator is None:
            schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema)
            self._validator = Draft202012Validator(schema)
        self._validator.validate(snapshot.model_dump(mode="json"))


class TimelineService:
    def __init__(
        self,
        *,
        repository: TimelineRepository,
        platform: PlatformRepository,
        auto_edit_repository: AutoEditRepository,
        media_repository: MediaIntelligenceRepository,
        validator: TimelineContractValidator,
        object_storage: ObjectStorageProvider | None = None,
    ):
        self.repository = repository
        self.platform = platform
        self.auto_edit_repository = auto_edit_repository
        self.media_repository = media_repository
        self.validator = validator
        self.object_storage = object_storage

    async def create(self, project_id: str, payload: TimelineCreateRequest) -> TimelineRead:
        project = await self.platform.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        if payload.source_kind != "video_analysis":
            from .storyboard_timeline import build_storyboard
            snapshot = await build_storyboard(self, project, payload)
            self.validator.validate(snapshot)
            existing = await self.repository.get_timeline(project_id)
            if existing:
                if existing.snapshot == snapshot:
                    return existing
                if payload.expected_timeline_version is None:
                    raise TimelineEditError("expected_timeline_version required to rebuild existing timeline")
                return await self.repository.commit_mutation(project_id=project_id,
                    expected_version=payload.expected_timeline_version, snapshot=snapshot,
                    mutation={"type": "storyboard-rebuild", "content_version_id": payload.content_version_id},
                    actor_ref=payload.actor_ref)
            timeline, _ = await self.repository.create_timeline(project_id=project_id,
                source_analysis_id=None, source_media_plan_id=None, source_content_version_id=payload.content_version_id,
                snapshot=snapshot, actor_ref=payload.actor_ref)
            return timeline
        existing = await self.repository.get_timeline(project_id)
        transcript_id = None
        if existing and payload.silence_decision_ids is not None:
            if payload.expected_timeline_version is None:
                raise TimelineEditError("expected_timeline_version is required to rebuild silence cuts")
            if existing.source_analysis_id != payload.analysis_id:
                raise TimelineEditError("active timeline uses another source")
            if any(track.locked and track.type != "metadata" for track in existing.snapshot.tracks):
                raise TimelineEditError("unlock timeline tracks before rebuilding silence cuts")
            transcript_id = (existing.snapshot.metadata.get("transcript_revision") or {}).get("transcript_id")
        analysis = (await self.auto_edit_repository.get_analysis(payload.analysis_id, transcript_id=transcript_id)
                    if transcript_id else await self.auto_edit_repository.get_analysis(payload.analysis_id))
        if analysis is None or analysis.project_id != project_id:
            raise KeyError(payload.analysis_id)
        if analysis.status != "succeeded":
            raise TimelineEditError("Auto Edit analysis is not ready")
        if analysis.source_media.audio_codec and (analysis.transcript is None or not analysis.transcript.segments):
            raise TimelineEditError("SPOKEN_VIDEO_ASR_REQUIRED")
        source_asset = await self.auto_edit_repository.get_asset(analysis.asset_id)
        if source_asset is None or source_asset.project_id != project_id:
            raise KeyError(analysis.asset_id)

        media_plan = None
        assets: dict[str, AssetRead] = {}
        if payload.media_plan_id:
            media_plan = await self.media_repository.get_plan(payload.media_plan_id)
            if media_plan is None or media_plan.project_id != project_id:
                raise KeyError(payload.media_plan_id)
            if media_plan.analysis_id != analysis.analysis_id:
                raise TimelineEditError("media plan and Auto Edit analysis do not share the same source")
            for evidence in media_plan.media_assets:
                asset = await self.auto_edit_repository.get_asset(evidence.asset_id)
                if asset is not None and asset.project_id == project_id:
                    assets[asset.asset_id] = asset

        snapshot = build_initial_timeline(
            analysis=analysis,
            source_asset=source_asset,
            media_plan=media_plan,
            media_assets=assets,
            silence_decision_ids=payload.silence_decision_ids,
        )
        self.validator.validate(snapshot)
        existing=await self.repository.get_timeline(project_id)
        if existing and payload.silence_decision_ids is not None:
            if payload.expected_timeline_version is None:raise TimelineEditError('expected_timeline_version is required to rebuild silence cuts')
            if existing.source_analysis_id!=analysis.analysis_id:raise TimelineEditError('active timeline uses another source')
            return await self.repository.commit_mutation(project_id=project_id,expected_version=payload.expected_timeline_version,
                snapshot=snapshot,mutation={'type':'silence-review-rebuild','source_analysis_id':analysis.analysis_id,
                                           'selected_decision_ids':payload.silence_decision_ids,'source_media_mutated':False},actor_ref=payload.actor_ref)
        timeline, _ = await self.repository.create_timeline(
            project_id=project_id,
            source_analysis_id=analysis.analysis_id,
            source_media_plan_id=media_plan.media_plan_id if media_plan else None,
            snapshot=snapshot,
            actor_ref=payload.actor_ref,
        )
        return timeline

    async def get(self, project_id: str) -> TimelineRead | None:
        return await self.repository.get_timeline(project_id)

    async def list_versions(self, project_id: str) -> list[TimelineVersionRead]:
        return await self.repository.list_versions(project_id)

    async def mutate(self, project_id: str, payload: TimelineMutationRequest) -> TimelineRead:
        timeline = await self.repository.get_timeline(project_id)
        if timeline is None:
            raise KeyError(project_id)
        snapshot = apply_operations(timeline.snapshot, payload.operations)
        self.validator.validate(snapshot)
        return await self.repository.commit_mutation(
            project_id=project_id,
            expected_version=payload.expected_version,
            snapshot=snapshot,
            mutation={
                "type": "edit",
                "reason": payload.reason,
                "operations": [item.model_dump(mode="json", exclude_none=True) for item in payload.operations],
                "source_media_mutated": False,
                "publish_requested": False,
            },
            actor_ref=payload.actor_ref,
        )

    async def restore(self, project_id: str, payload: TimelineRestoreRequest) -> TimelineRead:
        timeline = await self.repository.get_timeline(project_id)
        if timeline is None:
            raise KeyError(project_id)
        version = await self.repository.get_version(timeline.timeline_id, payload.restore_version)
        if version is None:
            raise KeyError(f"timeline-version:{payload.restore_version}")
        self.validator.validate(version.snapshot)
        return await self.repository.commit_mutation(
            project_id=project_id,
            expected_version=payload.expected_version,
            snapshot=version.snapshot,
            mutation={
                "type": "restore",
                "restored_from_version": payload.restore_version,
                "source_media_mutated": False,
                "publish_requested": False,
            },
            actor_ref=payload.actor_ref,
        )


class PreviewService:
    def __init__(
        self,
        *,
        repository: TimelineRepository,
        platform: PlatformRepository,
        auto_edit_repository: AutoEditRepository,
        object_storage: ObjectStorageProvider,
        queue: QueueClient,
        renderer: ProxyRenderer,
        staging_root: Path,
    ):
        self.repository = repository
        self.platform = platform
        self.auto_edit_repository = auto_edit_repository
        self.object_storage = object_storage
        self.queue = queue
        self.renderer = renderer
        self.staging_root = staging_root

    async def enqueue(self, project_id: str, payload: PreviewCreateRequest) -> PreviewRead:
        preview, created = await self.repository.create_preview(
            project_id=project_id,
            timeline_version=payload.timeline_version,
            width=payload.width,
            height=payload.height,
            actor_ref=payload.actor_ref,
        )
        if created and preview.status == "queued":
            await self.queue.rpush(PREVIEW_QUEUE_KEY, preview.preview_id)
        return preview

    async def get(self, project_id: str, preview_id: str) -> PreviewRead | None:
        preview = await self.repository.get_preview(preview_id)
        return preview if preview and preview.project_id == project_id else None

    async def cancel(self, project_id: str, preview_id: str) -> PreviewRead | None:
        preview = await self.repository.get_preview(preview_id)
        if preview is None or preview.project_id != project_id:
            return None
        return await self.repository.cancel_preview(preview_id)

    async def process(self, preview_id: str) -> PreviewRead:
        context = await self.repository.get_preview_context(preview_id)
        if context is None:
            raise KeyError(preview_id)
        preview, version = context
        if preview.status not in {"queued", "running"}:
            return preview
        started = await self.repository.start_preview(preview_id)
        if started is None:
            raise KeyError(preview_id)
        if started.status in {"cancelled", "stale"}:
            return started

        workdir = (self.staging_root / preview_id).resolve()
        output_path = workdir / "preview.mp4"
        try:
            workdir.mkdir(parents=True, exist_ok=True)
            assets: dict[str, tuple[AssetRead, Path]] = {}
            asset_ids = {
                clip.asset_id
                for track in version.snapshot.tracks
                for clip in track.clips
                if track.type in {"video", "audio"} and not track.disabled and not clip.disabled and clip.asset_id
                and (track.type != "audio" or (not track.muted and clip.volume > 0))
            }
            for asset_id in sorted(asset_ids):
                if await self.repository.preview_cancel_requested(preview_id):
                    raise PreviewCancelledError("preview was cancelled")
                asset = await self.auto_edit_repository.get_asset(asset_id)
                if asset is None or asset.project_id != preview.project_id:
                    raise RuntimeError(f"timeline asset is unavailable: {asset_id}")
                suffix = Path(asset.filename).suffix[:12] or ".bin"
                destination = workdir / f"{asset.asset_id}{suffix}"
                await self.object_storage.download_file(object_key=asset.object_key, destination=destination)
                if sha256_file(destination) != asset.checksum_sha256:
                    raise RuntimeError("PREVIEW_SOURCE_CHECKSUM_MISMATCH")
                assets[asset.asset_id] = (asset, destination)
            await self.repository.set_preview_progress(preview_id, 35)
            result = await self.renderer.render(
                snapshot=version.snapshot,
                assets=assets,
                output_path=output_path,
                width=preview.width,
                height=preview.height,
                is_cancelled=lambda: self.repository.preview_cancel_requested(preview_id),
            )
            await self.repository.set_preview_progress(preview_id, 85)
            object_key = validate_object_key(
                f"workspaces/{preview.workspace_id}/projects/{preview.project_id}/previews/{preview_id}/preview.mp4"
            )
            stored = await self.object_storage.put_file(
                object_key=object_key,
                path=result.path,
                content_type="video/mp4",
            )
            timeline = await self.repository.get_timeline(preview.project_id)
            if timeline is None:
                raise RuntimeError("timeline disappeared during preview rendering")
            asset = await self.platform.register_asset(
                preview.project_id,
                AssetRegister(
                    project_version_id=timeline.project_version_id,
                    asset_class="render",
                    kind="proxy-preview",
                    filename="preview.mp4",
                    object_key=stored.object_key,
                    content_type="video/mp4",
                    size_bytes=stored.size_bytes,
                    checksum_sha256=stored.checksum_sha256,
                    storage_provider=stored.storage_provider,
                    provenance={
                        "source": "timeline-proxy-preview",
                        "timeline_id": preview.timeline_id,
                        "timeline_version": preview.timeline_version,
                        "preview_only": True,
                        "publishing_allowed": False,
                        "source_media_mutated": False,
                    },
                ),
                job_id=None,
            )
            await self.repository.set_preview_progress(preview_id, 95)
            completed = await self.repository.complete_preview(
                preview_id,
                output_asset_id=asset.asset_id,
                manifest={
                    **result.manifest,
                    "timeline_id": preview.timeline_id,
                    "timeline_version": preview.timeline_version,
                    "width": preview.width,
                    "height": preview.height,
                    "duration_seconds": version.snapshot.duration_seconds,
                    "output_checksum_sha256": stored.checksum_sha256,
                    "proxy_only": True,
                    "publishing_allowed": False,
                    "source_media_mutated": False,
                    "audio_mixing": result.manifest.get("audio_mixing", "unavailable"),
                },
            )
            if completed is None:
                raise RuntimeError("preview completion record disappeared")
            return completed
        except PreviewCancelledError as exc:
            cancelled = await self.repository.fail_preview(
                preview_id, code="PREVIEW_CANCELLED", reason=str(exc)
            )
            if cancelled is None:
                raise
            return cancelled
        except Exception as exc:
            failed = await self.repository.fail_preview(
                preview_id, code="PREVIEW_RENDER_FAILED", reason=str(exc)
            )
            if failed is None:
                raise
            return failed
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def recover_incomplete(self) -> int:
        identifiers = await self.repository.list_incomplete_preview_ids()
        for identifier in identifiers:
            await self.queue.rpush(PREVIEW_QUEUE_KEY, identifier)
        return len(identifiers)
