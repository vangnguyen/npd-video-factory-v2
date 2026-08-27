from __future__ import annotations

import asyncio
import json
import math
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from jsonschema import Draft202012Validator

from .auto_edit_repository import AutoEditRepository
from .media_intelligence_repository import MediaIntelligenceRepository
from .object_storage import ObjectStorageProvider, validate_object_key
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


PREVIEW_QUEUE_KEY = "npd:video-factory:v2:preview:queued"
PREVIEW_PROCESSING_KEY = "npd:video-factory:v2:preview:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


class PreviewCancelledError(RuntimeError):
    pass


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
    ):
        self.repository = repository
        self.platform = platform
        self.auto_edit_repository = auto_edit_repository
        self.media_repository = media_repository
        self.validator = validator

    async def create(self, project_id: str, payload: TimelineCreateRequest) -> TimelineRead:
        project = await self.platform.get_project(project_id)
        if project is None:
            raise KeyError(project_id)
        analysis = await self.auto_edit_repository.get_analysis(payload.analysis_id)
        if analysis is None or analysis.project_id != project_id:
            raise KeyError(payload.analysis_id)
        if analysis.status != "succeeded":
            raise TimelineEditError("Auto Edit analysis is not ready")
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
        )
        self.validator.validate(snapshot)
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


@dataclass(frozen=True)
class ProxyRenderResult:
    path: Path
    manifest: dict[str, object]


class ProxyRenderer(Protocol):
    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult: ...


class DeterministicProxyRenderer:
    """Test-only renderer; its output is evidence, never represented as playable video."""

    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult:
        if await is_cancelled():
            raise PreviewCancelledError("preview was cancelled")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(
            json.dumps(
                {
                    "fixture": True,
                    "duration_seconds": snapshot.duration_seconds,
                    "assets": sorted(assets),
                },
                sort_keys=True,
            ).encode("utf-8")
        )
        return ProxyRenderResult(
            path=output_path,
            manifest={
                "renderer": "deterministic-contract-fixture",
                "playable": False,
                "fixture": True,
                "audio_included": False,
            },
        )


class FFmpegProxyRenderer:
    def __init__(self, ffmpeg_path: str = "ffmpeg"):
        self.ffmpeg_path = ffmpeg_path

    async def render(
        self,
        *,
        snapshot: TimelineSnapshot,
        assets: dict[str, tuple[AssetRead, Path]],
        output_path: Path,
        width: int,
        height: int,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> ProxyRenderResult:
        if await is_cancelled():
            raise PreviewCancelledError("preview was cancelled")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        duration = max(0.1, snapshot.duration_seconds)
        command = [
            self.ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"color=c=0x0b132b:s={width}x{height}:r=30:d={duration:.6f}",
        ]
        renderable: list[tuple[object, AssetRead, int]] = []
        ignored: list[str] = []
        for track in sorted(snapshot.tracks, key=lambda item: item.order):
            if track.type != "video" or track.disabled:
                continue
            for clip in track.clips:
                if clip.disabled or not clip.asset_id or clip.asset_id not in assets:
                    ignored.append(clip.clip_id)
                    continue
                asset, path = assets[clip.asset_id]
                content_type = asset.content_type.lower()
                supported_raster_types = {"image/jpeg", "image/png", "image/webp"}
                if not (content_type.startswith("video/") or content_type in supported_raster_types):
                    ignored.append(clip.clip_id)
                    continue
                if content_type.startswith("image/"):
                    command.extend(["-loop", "1", "-t", f"{clip.duration:.6f}", "-i", str(path)])
                else:
                    command.extend(
                        [
                            "-ss",
                            f"{clip.source_start:.6f}",
                            "-t",
                            f"{clip.source_end - clip.source_start:.6f}",
                            "-i",
                            str(path),
                        ]
                    )
                renderable.append((clip, asset, len(renderable) + 1))

        filters = ["[0:v]setpts=PTS-STARTPTS[base]"]
        previous = "base"
        rendered_ids: list[str] = []
        for ordinal, (clip, _asset, input_index) in enumerate(renderable):
            crop = clip.crop
            target_width = max(2, int(width * clip.transform.scale))
            target_height = max(2, int(height * clip.transform.scale))
            alpha = clip.opacity
            rotation_radians = clip.transform.rotation_degrees * math.pi / 180
            filters.append(
                f"[{input_index}:v]"
                f"crop=iw*{crop.width:.6f}:ih*{crop.height:.6f}:iw*{crop.x:.6f}:ih*{crop.y:.6f},"
                f"format=rgba,rotate={rotation_radians:.9f}:ow=rotw(iw):oh=roth(ih):c=black@0,"
                f"scale={target_width}:{target_height}:force_original_aspect_ratio=decrease,"
                f"pad={target_width}:{target_height}:(ow-iw)/2:(oh-ih)/2:color=black,"
                f"fps=30,setpts=(PTS-STARTPTS)/{clip.speed:.6f}+{clip.timeline_start:.6f}/TB,"
                f"format=rgba,colorchannelmixer=aa={alpha:.6f}[clip{ordinal}]"
            )
            output = f"layer{ordinal}"
            x = f"(W-w)/2+{clip.transform.x:.6f}*W/2"
            y = f"(H-h)/2+{clip.transform.y:.6f}*H/2"
            start = clip.timeline_start
            end = clip.timeline_start + clip.duration
            filters.append(
                f"[{previous}][clip{ordinal}]overlay=x={x}:y={y}:eof_action=pass:shortest=0:"
                f"enable='between(t,{start:.6f},{end:.6f})'[{output}]"
            )
            previous = output
            rendered_ids.append(clip.clip_id)
        filters.append(f"[{previous}]format=yuv420p[outv]")
        command.extend(
            [
                "-filter_complex",
                ";".join(filters),
                "-map",
                "[outv]",
                "-an",
                "-t",
                f"{duration:.6f}",
                "-c:v",
                "libx264",
                "-preset",
                "ultrafast",
                "-crf",
                "30",
                "-movflags",
                "+faststart",
                str(output_path),
            ]
        )
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        while True:
            try:
                await asyncio.wait_for(process.wait(), timeout=0.25)
                break
            except TimeoutError:
                if await is_cancelled():
                    process.terminate()
                    await process.wait()
                    output_path.unlink(missing_ok=True)
                    raise PreviewCancelledError("preview was cancelled")
        stderr = (await process.stderr.read()).decode("utf-8", errors="replace") if process.stderr else ""
        if process.returncode != 0 or not output_path.is_file():
            raise RuntimeError(f"ffmpeg proxy render failed: {stderr[-700:]}")
        return ProxyRenderResult(
            path=output_path,
            manifest={
                "renderer": "ffmpeg-proxy-v1",
                "playable": True,
                "fixture": False,
                "audio_included": False,
                "rendered_clip_ids": rendered_ids,
                "ignored_clip_ids": sorted(set(ignored)),
            },
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
                if track.type == "video" and not track.disabled and not clip.disabled and clip.asset_id
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
                    "audio_mixing": "deferred_to_v2_08",
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
