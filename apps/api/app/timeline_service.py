from __future__ import annotations

import asyncio
import copy
import json
import math
import re
import shutil
from pathlib import Path
from typing import Protocol

from jsonschema import Draft202012Validator

from .auto_edit_repository import AutoEditRepository
from .media_intelligence_repository import MediaIntelligenceRepository
from .object_storage import ObjectStorageProvider, LocalObjectStorageProvider, validate_object_key, sha256_file
from .frozen_storage_read import frozen_asset_read, asset_custody, completed_read, MAX_SOURCE_BYTES
from .bounded_storage_download import StorageDownloadError
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
from .timeline_repository import TimelineRepository, TimelineConflictError
from .timeline_proxy import (
    ProxyRenderResult, ProxyRenderer, DeterministicProxyRenderer,
    FFmpegProxyRenderer, PreviewCancelledError,
)


PREVIEW_QUEUE_KEY = "npd:video-factory:v2:preview:queued"
PREVIEW_PROCESSING_KEY = "npd:video-factory:v2:preview:processing"


class LegacyLocalPreviewRead:
    """Read registered project-scoped Local assets without rewriting their keys."""

    def __init__(self, asset, *, preview, storage):
        if (type(storage) is not LocalObjectStorageProvider or asset.storage_provider != 'local'
                or asset.workspace_id != preview.workspace_id or asset.project_id != preview.project_id
                or type(asset.size_bytes) is not int or not 0 < asset.size_bytes <= MAX_SOURCE_BYTES
                or not isinstance(asset.checksum_sha256, str)
                or re.fullmatch('[a-f0-9]{64}', asset.checksum_sha256) is None):
            raise ValueError('PREVIEW_LEGACY_LOCAL_PROOF_INVALID')
        self.prefix = f'projects/{preview.project_id}/'
        self.object_key = validate_object_key(asset.object_key)
        if self.object_key != asset.object_key or not self.object_key.startswith(self.prefix):
            raise ValueError('PREVIEW_LEGACY_LOCAL_SCOPE_CHANGED')
        self.size_bytes = asset.size_bytes
        self.checksum_sha256 = asset.checksum_sha256

    async def download(self, storage, destination):
        if type(storage) is not LocalObjectStorageProvider:
            raise ValueError('PREVIEW_LEGACY_LOCAL_PROVIDER_CHANGED')
        await completed_read(storage.download_file(object_key=self.object_key, destination=destination,
            max_bytes=MAX_SOURCE_BYTES, expected_size_bytes=self.size_bytes,
            expected_sha256=self.checksum_sha256, expected_prefix=self.prefix), cancel_operation=True)


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
            existing = await self.repository.get_timeline(project_id)
            if existing and payload.expected_timeline_version is not None and existing.current_version != payload.expected_timeline_version:
                raise TimelineConflictError(expected=payload.expected_timeline_version, actual=existing.current_version)
            context = await self._storyboard_rebuild_context(project, existing)
            snapshot = await build_storyboard(self, project, payload)
            if context is not None:
                snapshot.width, snapshot.height, snapshot.fps, snapshot.aspect_ratio = context['canvas']
                if context['reframe']:
                    snapshot.metadata['reframe'] = {'aspect_ratio': snapshot.aspect_ratio,
                        'fallback': 'center_crop', 'needs_attention': True, 'confidence': None}
                if context['origin'] is not None:
                    snapshot.metadata['sql_variant_derivative'] = copy.deepcopy(context['origin'])
            self.validator.validate(snapshot)
            if existing:
                current = await self.repository.get_timeline(project_id)
                if current is None or current.current_version_id != existing.current_version_id or current.current_version != existing.current_version:
                    raise TimelineConflictError(expected=existing.current_version, actual=current.current_version if current else 0)
                if existing.snapshot == snapshot:
                    return current
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

    async def _storyboard_rebuild_context(self, project, existing):
        """Keep this child's canvas and historic allocator references only.

        A rebuild has fresh clips and source windows. Historic origin references
        locate an immutable import receipt; they attest no current master source,
        approval, rights, crop path or measured speech alignment.
        """
        if existing is None:
            return None
        if existing.project_id != project.project_id or existing.workspace_id != project.workspace_id:
            raise TimelineEditError('STORYBOARD_REBUILD_SCOPE_CHANGED')
        snapshot = existing.snapshot.model_copy(deep=True)
        ratios = {'9:16': 9 / 16, '16:9': 16 / 9, '1:1': 1., '4:5': 4 / 5}
        if (snapshot.aspect_ratio not in ratios or not math.isfinite(snapshot.fps)
                or not 0 < snapshot.fps <= 120 or abs(snapshot.width / snapshot.height - ratios[snapshot.aspect_ratio]) > 1e-6):
            raise TimelineEditError('STORYBOARD_REBUILD_CANVAS_INVALID')
        reframed = snapshot.metadata.get('reframe')
        if reframed is not None and (not isinstance(reframed, dict) or reframed.get('aspect_ratio') != snapshot.aspect_ratio):
            raise TimelineEditError('STORYBOARD_REBUILD_CANVAS_INVALID')
        original = snapshot.metadata.get('sql_variant_derivative')
        provenance = project.provenance
        story = provenance.get('source_type') == 'storyboard_variant_derivative'
        if not story and original is None:
            return {'canvas': (snapshot.width, snapshot.height, snapshot.fps, snapshot.aspect_ratio),
                'reframe': reframed is not None or (snapshot.width, snapshot.height, snapshot.aspect_ratio) != (1080, 1920, '9:16'),
                'origin': None}
        try:
            candidate = provenance if story else original
            master, family, member = candidate['master_project_id'], candidate['family_id'], candidate['member_id']
            if (not isinstance(master, str) or re.fullmatch(r'prj_[A-Za-z0-9_-]{4,60}', master) is None
                    or master == project.project_id or re.fullmatch(r'vfa_[a-f0-9]{32}', family) is None
                    or re.fullmatch(r'vfm_[a-f0-9]{32}', member) is None or candidate.get('approval_inherited') is not False
                    or candidate.get('publishing_enabled', False) is not False):
                raise ValueError()
            if original is not None:
                if (not isinstance(original, dict) or any(original.get(k) != value for k, value in
                        [('master_project_id', master), ('family_id', family), ('member_id', member)])
                        or original.get('approval_inherited') is not False
                        or original.get('rights_override_inherited', False) is not False
                        or original.get('publishing_enabled', False) is not False
                        or original.get('new_inference_calls', 0) != 0):
                    raise ValueError()
            if story:
                if original is not None and original.get('schema_version') != 'sql-variant-storyboard-lineage.v1':
                    raise ValueError()
                receipt_id = provenance['receipt_id']
                kind = 'storyboard_derivation'
            else:
                if (not isinstance(original, dict) or original.get('schema_version') != 'sql-variant-evidence-lineage.v1'
                        or provenance.get('source_type') != 'uploaded_variant_derivative'
                        or provenance.get('parent_project_id') != master or provenance.get('approval_inherited') is not False
                        or provenance.get('rights_override_inherited') is not False or provenance.get('publishing_enabled') is not False):
                    raise ValueError()
                receipt_id = provenance['derivation_receipt_id']
                kind = 'uploaded_evidence_derivation'
            if not isinstance(receipt_id, str) or re.fullmatch(r'vfr_[a-f0-9]{32}', receipt_id) is None:
                raise ValueError()
            from sqlalchemy import select
            from .sql_variant_db import SqlVariantFamilyORM, SqlVariantMemberORM, SqlVariantArtifactReceiptORM
            from .sql_variant_models import digest
            # One SQL view binds the allocator relationship. No writer lock,
            # source-current calculation, byte read or provider call occurs.
            async with self.repository.session_factory() as session:
                joined = (await session.execute(select(SqlVariantFamilyORM, SqlVariantMemberORM, SqlVariantArtifactReceiptORM)
                    .join(SqlVariantMemberORM, SqlVariantMemberORM.family_id == SqlVariantFamilyORM.family_id)
                    .join(SqlVariantArtifactReceiptORM, SqlVariantArtifactReceiptORM.member_id == SqlVariantMemberORM.member_id)
                    .where(SqlVariantFamilyORM.family_id == family, SqlVariantFamilyORM.workspace_id == project.workspace_id,
                        SqlVariantFamilyORM.master_project_id == master, SqlVariantMemberORM.member_id == member,
                        SqlVariantMemberORM.workspace_id == project.workspace_id, SqlVariantMemberORM.child_project_id == project.project_id,
                        SqlVariantArtifactReceiptORM.receipt_id == receipt_id, SqlVariantArtifactReceiptORM.family_id == family,
                        SqlVariantArtifactReceiptORM.workspace_id == project.workspace_id,
                        SqlVariantArtifactReceiptORM.kind == kind, SqlVariantArtifactReceiptORM.state == 'ready'))).one_or_none()
                if joined is None:
                    raise ValueError()
                family_row, _member, receipt = joined
                if (digest(receipt.input_json) != receipt.input_sha256 or digest(receipt.result_json) != receipt.result_sha256
                        or provenance.get('input_sha256') != receipt.input_sha256
                        or receipt.result_json.get('child_project_id') != project.project_id):
                    raise ValueError()
                if not story and (original.get('family_snapshot_sha256') != family_row.snapshot_sha256
                        or original.get('source_timeline_sha256') != digest(receipt.input_json['source_timeline'])):
                    raise ValueError()
        except (KeyError, TypeError, ValueError, AttributeError):
            raise TimelineEditError('STORYBOARD_REBUILD_ORIGIN_INVALID') from None
        origin = {'schema_version': 'sql-variant-storyboard-lineage.v1', 'source_type': 'storyboard_variant_derivative',
            'master_project_id': master, 'family_id': family, 'member_id': member,
            'approval_inherited': False, 'publishing_enabled': False} if story else copy.deepcopy(original)
        return {'canvas': (snapshot.width, snapshot.height, snapshot.fps, snapshot.aspect_ratio), 'reframe': True, 'origin': origin}

    async def get(self, project_id: str) -> TimelineRead | None:
        return await self.repository.get_timeline(project_id)

    async def list_versions(self, project_id: str) -> list[TimelineVersionRead]:
        return await self.repository.list_versions(project_id)

    async def mutate(self, project_id: str, payload: TimelineMutationRequest) -> TimelineRead:
        timeline = await self.repository.get_timeline(project_id)
        if timeline is None:
            raise KeyError(project_id)
        snapshot = apply_operations(timeline.snapshot, payload.operations)
        from .uploaded_audio_timeline import refresh_after_edit
        from .uploaded_audio_repository import AudioConflict
        try:
            snapshot = refresh_after_edit(timeline.snapshot, snapshot, payload.operations)
        except AudioConflict as exc:
            raise TimelineEditError(exc.code) from exc
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
            source_custodies = {}
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
                source_custodies[asset.asset_id] = asset_custody(asset)
                await self._download_preview_asset(preview,asset,destination)
                assets[asset.asset_id] = (asset, destination)
            await self.repository.set_preview_progress(preview_id, 35)
            await self._assert_preview_sources_current(preview, assets, expected_custodies=source_custodies)
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

    async def _download_preview_asset(self,preview,asset,path):
        asset=asset.model_copy(deep=True)
        custody=asset_custody(asset)
        try:
            if asset.object_key.startswith(f'projects/{preview.project_id}/'):
                proof=LegacyLocalPreviewRead(asset,preview=preview,storage=self.object_storage)
            else:
                proof=frozen_asset_read(asset,workspace_id=preview.workspace_id,project_id=preview.project_id,
                    storage=self.object_storage,maximum=MAX_SOURCE_BYTES)
            await proof.download(self.object_storage,path)
            if await completed_read(asyncio.to_thread(sha256_file,path))!=asset.checksum_sha256:
                raise RuntimeError('PREVIEW_SOURCE_CHECKSUM_MISMATCH')
        except StorageDownloadError as error:
            if error.code in {'STORAGE_DOWNLOAD_HASH_MISMATCH','STORAGE_DOWNLOAD_SIZE_MISMATCH','STORAGE_DOWNLOAD_SIZE_LIMIT'}:
                raise RuntimeError('PREVIEW_SOURCE_CHECKSUM_MISMATCH') from None
            raise RuntimeError('PREVIEW_SOURCE_DOWNLOAD_FAILED') from None
        except Exception:
            raise RuntimeError('PREVIEW_SOURCE_DOWNLOAD_FAILED') from None
        snapshot=await self.auto_edit_repository.read_source_snapshot(project_id=preview.project_id,
            asset_ids=(asset.asset_id,),preview_id=preview.preview_id)
        self._check_preview_source_snapshot(preview,{asset.asset_id:(asset,path)},snapshot,
            expected_custodies={asset.asset_id:custody})

    async def _assert_preview_sources_current(self, preview, assets, *, expected_custodies=None):
        """Recheck after the final progress await, before invoking any renderer."""
        custodies=expected_custodies if expected_custodies is not None else {
            asset.asset_id:asset_custody(asset) for asset,_ in assets.values()}
        for asset, path in assets.values():
            try:
                checksum = await completed_read(asyncio.to_thread(sha256_file, path))
            except (OSError, ValueError):
                raise RuntimeError('PREVIEW_SOURCE_DOWNLOAD_FAILED') from None
            if checksum != asset.checksum_sha256:
                raise RuntimeError('PREVIEW_SOURCE_CHECKSUM_MISMATCH')
        snapshot=await self.auto_edit_repository.read_source_snapshot(project_id=preview.project_id,
            asset_ids=tuple(assets),preview_id=preview.preview_id)
        self._check_preview_source_snapshot(preview,assets,snapshot,expected_custodies=custodies)

    @staticmethod
    def _check_preview_source_snapshot(preview,assets,snapshot,*,expected_custodies):
        project=snapshot['project'];timeline=snapshot['timeline'];current_preview=snapshot['preview']
        if project is None or project['workspace_id']!=preview.workspace_id or project['project_id']!=preview.project_id:
            raise RuntimeError('PREVIEW_SOURCE_SCOPE_CHANGED')
        for asset, _ in assets.values():
            current=snapshot['assets'].get(asset.asset_id)
            if current is None or asset_custody(current)!=expected_custodies[asset.asset_id]:
                raise RuntimeError('PREVIEW_SOURCE_CUSTODY_CHANGED')
        if (timeline is None or timeline['workspace_id']!=preview.workspace_id
                or timeline['project_id']!=preview.project_id or timeline['timeline_id']!=preview.timeline_id
                or timeline['current_version_id']!=preview.timeline_version_id
                or timeline['current_version']!=preview.timeline_version):
            raise PreviewCancelledError('PREVIEW_TIMELINE_CHANGED')
        if (current_preview is None or current_preview['workspace_id']!=preview.workspace_id
                or current_preview['project_id']!=preview.project_id or current_preview['preview_id']!=preview.preview_id
                or current_preview['timeline_id']!=preview.timeline_id
                or current_preview['timeline_version_id']!=preview.timeline_version_id
                or current_preview['timeline_version']!=preview.timeline_version
                or current_preview['status']!='running' or current_preview['cancellation_requested']
                or current_preview['invalidated_at'] is not None):
            raise PreviewCancelledError('PREVIEW_CANCELLED')
