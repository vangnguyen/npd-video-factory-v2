from __future__ import annotations

import copy
import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol

import httpx

from .object_storage import ObjectStorageProvider, validate_object_key
from .platform_models import AssetRegister
from .production_audio import AudioMixEngine, audio_provider_status
from .production_logic import (
    PROFILE_DIMENSIONS,
    ProductionContractError,
    TimelineRenderContractValidator,
    build_timeline_render_manifest,
    derive_subtitle_cues,
    validate_music_rights,
    validate_subtitles,
    validate_timeline_renderability,
)
from .production_models import (
    ApprovalDecisionRequest,
    ApprovalRead,
    ApprovalRequest,
    AudioMixReplaceRequest,
    FinalRenderCreateRequest,
    MixConfig,
    ProductionEventRead,
    ProductionPackageCreateRequest,
    ProductionPackageRead,
    RenderCreateRequest,
    RenderJobRead,
    SubtitleReplaceRequest,
    SubtitleStyle,
)
from .production_qc import ProductionQCError
from .production_repository import ProductionRepository
from .providers import TTSNotConfiguredError
from .timeline_models import TimelineSnapshot


PRODUCTION_RENDER_QUEUE_KEY = "npd:video-factory:v2:production-render:queued"
PRODUCTION_RENDER_PROCESSING_KEY = "npd:video-factory:v2:production-render:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> Any: ...


class TimelineRenderEngine(Protocol):
    async def render(
        self,
        *,
        render_id: str,
        manifest_path: Path,
        output_path: Path,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any]: ...


class ProductionQC(Protocol):
    async def inspect(
        self,
        path: Path,
        *,
        expected_duration: float,
        expected_width: int,
        expected_height: int,
        expected_fps: float,
        subtitle_qc: dict[str, Any],
        timeline_qc: dict[str, Any],
    ) -> dict[str, Any]: ...


class RenderCancelledError(RuntimeError):
    pass


class RemotionTimelineRenderEngine:
    def __init__(self, *, renderer_url: str, timeout_seconds: float):
        self.renderer_url = renderer_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    async def render(
        self,
        *,
        render_id: str,
        manifest_path: Path,
        output_path: Path,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any]:
        if await is_cancelled():
            raise RenderCancelledError("render was cancelled before Remotion started")
        timeout = httpx.Timeout(connect=10, read=self.timeout_seconds, write=30, pool=10)
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(
                    f"{self.renderer_url}/render",
                    json={
                        "job_id": render_id,
                        "manifest_path": str(manifest_path),
                        "output_path": str(output_path),
                    },
                )
            except httpx.RequestError as exc:
                raise RuntimeError("Remotion renderer is unavailable") from exc
        if response.status_code >= 400:
            try:
                body = response.json()
            except ValueError:
                body = {}
            message = str(body.get("message") or body.get("error", {}).get("message") or f"HTTP {response.status_code}")
            raise RuntimeError(f"Remotion timeline render failed: {message}")
        result = response.json()
        if result.get("status") != "success" or result.get("output_path") != str(output_path):
            raise RuntimeError("Remotion renderer returned an invalid success response")
        if await is_cancelled():
            output_path.unlink(missing_ok=True)
            raise RenderCancelledError("render was cancelled after Remotion completed")
        return dict(result)


class DeterministicTimelineRenderEngine:
    async def render(
        self,
        *,
        render_id: str,
        manifest_path: Path,
        output_path: Path,
        is_cancelled: Callable[[], Awaitable[bool]],
    ) -> dict[str, Any]:
        if await is_cancelled():
            raise RenderCancelledError("deterministic render was cancelled")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes((json.dumps(manifest, sort_keys=True) + render_id).encode("utf-8"))
        return {"status": "success", "output_path": str(output_path), "renderer": "deterministic"}


class ProductionPackageService:
    def __init__(
        self,
        *,
        repository: ProductionRepository,
        timeline_repository: Any,
        asset_repository: Any,
        queue: QueueClient,
        settings: Any,
    ):
        self.repository = repository
        self.timeline_repository = timeline_repository
        self.asset_repository = asset_repository
        self.queue = queue
        self.settings = settings

    async def create_or_refresh(
        self, project_id: str, payload: ProductionPackageCreateRequest
    ) -> ProductionPackageRead:
        timeline = await self.timeline_repository.get_timeline(project_id)
        if timeline is None:
            raise KeyError("timeline")
        if payload.expected_timeline_version is not None and payload.expected_timeline_version != timeline.current_version:
            from .production_repository import ProductionConflictError

            raise ProductionConflictError(
                entity="timeline",
                expected=payload.expected_timeline_version,
                actual=timeline.current_version,
            )
        cues = derive_subtitle_cues(timeline.snapshot)
        package, _created = await self.repository.create_or_refresh_package(
            timeline=timeline,
            cues=cues,
            style=SubtitleStyle(),
            mix_config=MixConfig(),
            provider_status=audio_provider_status(self.settings),
            actor_ref=payload.actor_ref,
        )
        return package

    async def get(self, project_id: str) -> ProductionPackageRead | None:
        return await self.repository.get_package(project_id)

    async def replace_subtitles(
        self, project_id: str, payload: SubtitleReplaceRequest
    ) -> ProductionPackageRead:
        package = await self.repository.get_package(project_id)
        if package is None:
            raise KeyError("production-package")
        timeline = await self.timeline_repository.get_timeline(project_id)
        if timeline is None:
            raise KeyError("timeline")
        validate_subtitles(payload.cues, payload.style, timeline.snapshot.duration_seconds)
        return await self.repository.replace_subtitles(
            project_id=project_id,
            expected_timeline_version=payload.expected_timeline_version,
            expected_subtitle_version=payload.expected_subtitle_version,
            cues=payload.cues,
            style=payload.style,
            actor_ref=payload.actor_ref,
            reason=payload.reason,
        )

    async def replace_audio_mix(
        self, project_id: str, payload: AudioMixReplaceRequest
    ) -> ProductionPackageRead:
        if payload.config.music.asset_id:
            asset = await self.asset_repository.get_asset(payload.config.music.asset_id)
            if asset is None or asset.project_id != project_id:
                raise ProductionContractError("configured music asset was not found in this project")
            validate_music_rights(asset)
        if not payload.config.voice.enabled and payload.config.music.asset_id is None:
            raise ProductionContractError("audio mix must enable narration or configure a licensed music asset")
        return await self.repository.replace_audio_mix(
            project_id=project_id,
            expected_timeline_version=payload.expected_timeline_version,
            expected_audio_version=payload.expected_audio_version,
            config=payload.config,
            provider_status=audio_provider_status(self.settings),
            actor_ref=payload.actor_ref,
            reason=payload.reason,
        )

    async def enqueue_review(self, project_id: str, payload: RenderCreateRequest) -> RenderJobRead:
        if payload.profile != "review-540x960":
            raise ProductionContractError("review render must use the review-540x960 profile")
        render = await self.repository.create_render(
            project_id=project_id,
            expected_timeline_version=payload.expected_timeline_version,
            expected_subtitle_version=payload.expected_subtitle_version,
            expected_audio_version=payload.expected_audio_version,
            render_kind="review",
            profile=payload.profile,
            actor_ref=payload.actor_ref,
        )
        await self.queue.rpush(PRODUCTION_RENDER_QUEUE_KEY, render.render_id)
        return render

    async def enqueue_final(
        self, project_id: str, payload: FinalRenderCreateRequest
    ) -> RenderJobRead:
        render = await self.repository.create_render(
            project_id=project_id,
            expected_timeline_version=payload.expected_timeline_version,
            expected_subtitle_version=payload.expected_subtitle_version,
            expected_audio_version=payload.expected_audio_version,
            render_kind="final",
            profile=payload.profile,
            actor_ref=payload.actor_ref,
            approval_id=payload.approval_id,
        )
        await self.queue.rpush(PRODUCTION_RENDER_QUEUE_KEY, render.render_id)
        return render

    async def get_render(self, project_id: str, render_id: str) -> RenderJobRead | None:
        render = await self.repository.get_render(render_id)
        return render if render and render.project_id == project_id else None

    async def cancel_render(self, project_id: str, render_id: str, actor_ref: str) -> RenderJobRead | None:
        return await self.repository.cancel_render(project_id, render_id, actor_ref)

    async def request_approval(self, project_id: str, payload: ApprovalRequest) -> ApprovalRead:
        return await self.repository.request_approval(
            project_id=project_id,
            review_render_id=payload.review_render_id,
            requester_ref=payload.requester_ref,
            note=payload.note,
        )

    async def decide_approval(
        self, project_id: str, approval_id: str, payload: ApprovalDecisionRequest
    ) -> ApprovalRead:
        return await self.repository.decide_approval(
            project_id=project_id,
            approval_id=approval_id,
            decision=payload.decision,
            reviewer_ref=payload.reviewer_ref,
            comment=payload.comment,
        )

    async def history(self, project_id: str) -> list[ProductionEventRead]:
        return await self.repository.list_events(project_id)


class ProductionRenderProcessor:
    def __init__(
        self,
        *,
        repository: ProductionRepository,
        platform: Any,
        asset_repository: Any,
        object_storage: ObjectStorageProvider,
        renderer: TimelineRenderEngine,
        qc: ProductionQC,
        tts_provider: Any,
        audio_engine: AudioMixEngine,
        manifest_validator: TimelineRenderContractValidator,
        staging_root: Path,
        brand_name: str,
    ):
        self.repository = repository
        self.platform = platform
        self.asset_repository = asset_repository
        self.object_storage = object_storage
        self.renderer = renderer
        self.qc = qc
        self.tts_provider = tts_provider
        self.audio_engine = audio_engine
        self.manifest_validator = manifest_validator
        self.staging_root = staging_root
        self.brand_name = brand_name

    async def process(self, render_id: str) -> RenderJobRead:
        context = await self.repository.get_render_context(render_id)
        if context is None:
            raise KeyError(render_id)
        render, subtitles, audio_mix, snapshot_json = context
        if render.status not in {"queued", "running"}:
            return render
        started = await self.repository.start_render(render_id)
        if started is None:
            raise KeyError(render_id)
        if started.status in {"cancelled", "stale"}:
            return started

        workdir = (self.staging_root.resolve() / render_id).resolve()
        if self.staging_root.resolve() not in workdir.parents:
            raise RuntimeError("render staging path escaped its configured root")
        try:
            workdir.mkdir(parents=True, exist_ok=True)
            snapshot = TimelineSnapshot.model_validate(snapshot_json)
            project = await self.platform.get_project(render.project_id)
            if project is None:
                raise RuntimeError("render project disappeared")
            await self.repository.set_render_progress(render_id, 10)
            asset_ids = {
                clip.asset_id
                for track in snapshot.tracks
                if track.type == "video" and not track.disabled
                for clip in track.clips
                if not clip.disabled and clip.asset_id
            }
            if audio_mix.config.music.asset_id:
                asset_ids.add(audio_mix.config.music.asset_id)
            asset_paths: dict[str, tuple[Any, Path]] = {}
            for asset_id in sorted(asset_ids):
                await self._check_cancelled(render_id)
                asset = await self.asset_repository.get_asset(asset_id)
                if asset is None or asset.project_id != render.project_id:
                    raise ProductionContractError(f"render asset is unavailable: {asset_id}")
                suffix = Path(asset.filename).suffix[:12] or ".bin"
                path = workdir / f"{asset.asset_id}{suffix}"
                await self.object_storage.download_file(object_key=asset.object_key, destination=path)
                asset_paths[asset.asset_id] = (asset, path)
            timeline_qc = validate_timeline_renderability(
                snapshot, available_asset_ids=set(asset_paths)
            )
            subtitle_qc = validate_subtitles(
                subtitles.cues, subtitles.style, snapshot.duration_seconds
            )
            music_path: Path | None = None
            if audio_mix.config.music.asset_id:
                music_asset, music_path = asset_paths[audio_mix.config.music.asset_id]
                validate_music_rights(music_asset)

            await self.repository.set_render_progress(render_id, 25)
            narration_path = workdir / "narration.wav"
            narration_manifest = await self.audio_engine.synthesize_narration(
                self.tts_provider,
                cues=subtitles.cues,
                config=audio_mix.config,
                duration_seconds=snapshot.duration_seconds,
                output_path=narration_path,
                workdir=workdir,
            )
            await self._check_cancelled(render_id)
            mixed_audio_path = workdir / "audio-mix.wav"
            mix_manifest = await self.audio_engine.mix(
                narration_path=narration_path,
                music_path=music_path,
                cues=subtitles.cues,
                config=audio_mix.config,
                duration_seconds=snapshot.duration_seconds,
                output_path=mixed_audio_path,
            )
            subtitle_path = workdir / "subtitles.srt"
            _write_srt(subtitle_path, subtitles.cues)

            await self.repository.set_render_progress(render_id, 45)
            manifest = build_timeline_render_manifest(
                snapshot=snapshot,
                subtitles=subtitles,
                mix_config=audio_mix.config,
                mixed_audio_path=mixed_audio_path,
                asset_paths={key: value for key, value in asset_paths.items() if key != audio_mix.config.music.asset_id},
                profile=render.profile,
                project_name=project.name,
                project_slug=project.slug,
                niche=project.niche,
                brand_name=self.brand_name,
            )
            self.manifest_validator.validate(manifest)
            manifest_path = workdir / "timeline-render-manifest.json"
            manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            await self.repository.set_render_progress(render_id, 55)
            output_path = workdir / ("review.mp4" if render.render_kind == "review" else "final.mp4")
            renderer_result = await self.renderer.render(
                render_id=render_id,
                manifest_path=manifest_path,
                output_path=output_path,
                is_cancelled=lambda: self.repository.render_cancel_requested(render_id),
            )
            await self.repository.set_render_progress(render_id, 88)
            width, height = PROFILE_DIMENSIONS[render.profile]
            qc_report = await self.qc.inspect(
                output_path,
                expected_duration=snapshot.duration_seconds,
                expected_width=width,
                expected_height=height,
                expected_fps=snapshot.fps,
                subtitle_qc=subtitle_qc,
                timeline_qc=timeline_qc,
            )
            qc_path = workdir / "qc.json"
            qc_path.write_text(json.dumps(qc_report, ensure_ascii=False, indent=2), encoding="utf-8")
            evidence_manifest = _evidence_manifest(
                manifest,
                narration=narration_manifest,
                mix=mix_manifest,
                renderer=renderer_result,
                qc=qc_report,
            )
            evidence_path = workdir / "render-evidence.json"
            evidence_path.write_text(json.dumps(evidence_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            await self.repository.set_render_progress(render_id, 94)
            supporting_assets: dict[str, str] = {}
            for path, asset_class, kind, content_type in (
                (mixed_audio_path, "render", "audio-mix", "audio/wav"),
                (subtitle_path, "metadata", "subtitle-srt", "application/x-subrip"),
                (qc_path, "metadata", "full-qc-report", "application/json"),
                (evidence_path, "metadata", "render-evidence", "application/json"),
            ):
                registered = await self._persist_asset(
                    render,
                    project_version_id=project.current_version_id,
                    path=path,
                    asset_class=asset_class,
                    kind=kind,
                    content_type=content_type,
                )
                supporting_assets[kind] = registered.asset_id
            output_asset = await self._persist_asset(
                render,
                project_version_id=project.current_version_id,
                path=output_path,
                asset_class="render",
                kind="av-review" if render.render_kind == "review" else "final-render",
                content_type="video/mp4",
            )
            evidence_manifest["supporting_asset_ids"] = supporting_assets
            evidence_manifest["output_asset_id"] = output_asset.asset_id
            evidence_manifest["output_checksum_sha256"] = output_asset.checksum_sha256
            completed = await self.repository.complete_render(
                render_id,
                output_asset_id=output_asset.asset_id,
                qc_report=qc_report,
                manifest=evidence_manifest,
            )
            if completed is None:
                raise RuntimeError("render completion record disappeared")
            await self._record_costs(render)
            return completed
        except RenderCancelledError as exc:
            failed = await self.repository.fail_render(render_id, code="RENDER_CANCELLED", reason=str(exc))
            if failed is None:
                raise
            return failed
        except ProductionQCError as exc:
            failed = await self.repository.fail_render(
                render_id,
                code="QC_FAILED",
                reason=str(exc),
                qc_report=exc.report,
            )
            if failed is None:
                raise
            return failed
        except TTSNotConfiguredError as exc:
            failed = await self.repository.fail_render(render_id, code="TTS_NOT_CONFIGURED", reason=str(exc))
            if failed is None:
                raise
            return failed
        except Exception as exc:
            failed = await self.repository.fail_render(
                render_id,
                code="PRODUCTION_RENDER_FAILED",
                reason=f"{type(exc).__name__}: {exc}",
            )
            if failed is None:
                raise
            return failed
        finally:
            shutil.rmtree(workdir, ignore_errors=True)

    async def recover_incomplete(self, queue: QueueClient) -> int:
        identifiers = await self.repository.list_incomplete_render_ids()
        for identifier in identifiers:
            await queue.rpush(PRODUCTION_RENDER_QUEUE_KEY, identifier)
        return len(identifiers)

    async def _check_cancelled(self, render_id: str) -> None:
        if await self.repository.render_cancel_requested(render_id):
            raise RenderCancelledError("render was cancelled")

    async def _persist_asset(
        self,
        render: RenderJobRead,
        *,
        project_version_id: str | None,
        path: Path,
        asset_class: str,
        kind: str,
        content_type: str,
    ):
        object_key = validate_object_key(
            f"workspaces/{render.workspace_id}/projects/{render.project_id}/production-renders/{render.render_id}/{path.name}"
        )
        stored = await self.object_storage.put_file(
            object_key=object_key,
            path=path,
            content_type=content_type,
        )
        return await self.platform.register_asset(
            render.project_id,
            AssetRegister(
                project_version_id=project_version_id,
                asset_class=asset_class,
                kind=kind,
                filename=path.name,
                object_key=stored.object_key,
                content_type=content_type,
                size_bytes=stored.size_bytes,
                checksum_sha256=stored.checksum_sha256,
                storage_provider=stored.storage_provider,
                provenance={
                    "source": "v2-08-production-render",
                    "render_id": render.render_id,
                    "render_kind": render.render_kind,
                    "timeline_version": render.timeline_version,
                    "subtitle_version": render.subtitle_version,
                    "audio_version": render.audio_version,
                    "approval_id": render.approval_id,
                    "publishing_allowed": False,
                },
            ),
            job_id=None,
        )

    async def _record_costs(self, render: RenderJobRead) -> None:
        tts_key = "openai-tts" if self.tts_provider.__class__.__name__.startswith("OpenAI") else "espeak"
        zero = Decimal("0") if tts_key == "espeak" else None
        await self.platform.record_provider_operation(
            workspace_id=render.workspace_id,
            project_id=render.project_id,
            job_id=None,
            provider_key=tts_key,
            capability="tts",
            operation=f"tts.v2-08.{render.render_id}",
            estimated_cost=zero,
            actual_cost=zero,
            metadata={"render_id": render.render_id, "scene_aligned": True, "currency": "VND"},
        )
        await self.platform.record_provider_operation(
            workspace_id=render.workspace_id,
            project_id=render.project_id,
            job_id=None,
            provider_key="remotion",
            capability="rendering",
            operation=f"render.timeline-v2-08.{render.render_id}",
            estimated_cost=Decimal("0"),
            actual_cost=Decimal("0"),
            metadata={"render_id": render.render_id, "profile": render.profile, "currency": "VND"},
        )


def _write_srt(path: Path, cues: list[Any]) -> None:
    blocks: list[str] = []
    for index, cue in enumerate(cues, start=1):
        blocks.append(
            f"{index}\n{_srt_time(cue.start_seconds)} --> {_srt_time(cue.end_seconds)}\n{cue.text}"
        )
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def _srt_time(seconds: float) -> str:
    milliseconds = int(round(max(0, seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _evidence_manifest(
    manifest: dict[str, Any],
    *,
    narration: dict[str, Any],
    mix: dict[str, Any],
    renderer: dict[str, Any],
    qc: dict[str, Any],
) -> dict[str, Any]:
    evidence = copy.deepcopy(manifest)
    for clip in evidence["visual_clips"]:
        clip["uri"] = f"asset://{clip['clip_id']}"
    evidence["audio"]["mix_uri"] = "artifact://audio-mix"
    evidence["narration"] = narration
    evidence["mix"] = mix
    evidence["renderer_result"] = {
        key: value for key, value in renderer.items() if key not in {"output_path"}
    }
    evidence["qc_status"] = qc.get("status")
    return evidence
