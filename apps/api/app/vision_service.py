from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path

from .auto_edit_repository import AutoEditRepository
from .object_storage import ObjectStorageProvider, sha256_file
from .repositories import PlatformRepository
from .vision_logic import (
    build_reframe_plans,
    build_subject_tracks,
    build_vision_scenes,
    normalize_frames,
    rank_best_frames,
)
from .vision_models import VisionAnalysisRead, VisionAnalysisRequest
from .vision_providers import VisionProvider, VisionProviderNotConfigured
from .vision_repository import VisionRepository


class VisionAnalysisService:
    algorithm_version = "v2-05.1"

    def __init__(
        self,
        *,
        repository: VisionRepository,
        auto_edit_repository: AutoEditRepository,
        platform: PlatformRepository,
        object_storage: ObjectStorageProvider,
        provider: VisionProvider,
        staging_root: Path,
    ):
        self.repository = repository
        self.auto_edit_repository = auto_edit_repository
        self.platform = platform
        self.object_storage = object_storage
        self.provider = provider
        self.staging_root = staging_root.resolve()

    async def analyze(
        self,
        *,
        project_id: str,
        analysis_id: str,
        payload: VisionAnalysisRequest,
    ) -> VisionAnalysisRead:
        base = await self.auto_edit_repository.get_analysis(analysis_id)
        if base is None or base.project_id != project_id:
            raise KeyError(analysis_id)
        if base.status != "succeeded":
            raise ValueError("Vision analysis requires a succeeded V2-04 Auto Edit analysis")
        asset = await self.auto_edit_repository.get_asset(base.asset_id)
        if asset is None or asset.project_id != project_id or asset.kind != "video":
            raise KeyError(base.asset_id)
        duration = float(base.source_media.duration_seconds or 0)
        if duration <= 0:
            raise ValueError("source video duration is unavailable")
        for override in payload.manual_overrides:
            if override.time >= duration:
                raise ValueError("manual override time must be inside source duration")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "auto_edit_fingerprint": base.fingerprint,
                    "asset_checksum": asset.checksum_sha256,
                    "configuration": payload.model_dump(mode="json"),
                    "provider": self.provider.key,
                    "model": self.provider.model,
                    "algorithm_version": self.algorithm_version,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        vision_analysis_id, created = await self.repository.create_analysis(
            base_analysis=base,
            asset=asset,
            fingerprint=fingerprint,
            configuration=payload,
            provider_key=self.provider.key,
            model=self.provider.model,
            provenance={
                "algorithm_version": self.algorithm_version,
                "source_asset_checksum": asset.checksum_sha256,
                "base_auto_edit_analysis_id": analysis_id,
                "structured_json": True,
                "source_media_mutated": False,
                "publish_requested": False,
                "paid_external_call": False,
                "manual_override_supported": True,
            },
        )
        if not created:
            existing = await self.repository.get_analysis(vision_analysis_id)
            if existing is None:
                raise RuntimeError("vision fingerprint exists without readable state")
            return existing
        await self.repository.mark_running(vision_analysis_id)
        self.staging_root.mkdir(parents=True, exist_ok=True)
        local_path = self.staging_root / f"{vision_analysis_id}-{asset.filename}"
        try:
            await self.object_storage.download_file(object_key=asset.object_key, destination=local_path)
            if sha256_file(local_path) != asset.checksum_sha256:
                raise ValueError("downloaded Vision source checksum does not match the asset record")
            provider_result = await self.provider.analyze(
                local_path,
                metadata=base.source_media,
                scenes=base.scenes,
                asset_id=asset.asset_id,
                checksum_sha256=asset.checksum_sha256,
                sample_interval_seconds=payload.sample_interval_seconds,
            )
            if provider_result.provenance.get("external_call") or provider_result.provenance.get(
                "paid"
            ):
                raise RuntimeError("external or paid Vision execution is disabled in V2-05")
            frames = normalize_frames(
                provider_result.frames,
                provider_key=self.provider.key,
                model=self.provider.model,
                fingerprint=fingerprint,
            )
            if any(frame.timestamp_seconds >= duration for frame in frames):
                raise ValueError("vision provider evidence timestamp is outside source duration")
            scenes = build_vision_scenes(
                scenes=base.scenes,
                frames=frames,
                fingerprint=fingerprint,
            )
            tracks = build_subject_tracks(
                frames=frames,
                fingerprint=fingerprint,
                minimum_confidence=payload.minimum_tracking_confidence,
            )
            reframe_plans = build_reframe_plans(
                frames=frames,
                tracks=tracks,
                metadata=base.source_media,
                aspect_ratios=payload.aspect_ratios,
                manual_overrides=payload.manual_overrides,
                minimum_tracking_confidence=payload.minimum_tracking_confidence,
                subtitle_safe_area_bottom=payload.subtitle_safe_area_bottom,
                maximum_jump=payload.maximum_crop_jump,
                fingerprint=fingerprint,
            )
            best_frame_ids, thumbnail_candidate_ids = rank_best_frames(frames)
            await self.platform.record_provider_operation(
                workspace_id=asset.workspace_id,
                project_id=asset.project_id,
                job_id=None,
                provider_key=self.provider.key,
                capability="vision",
                operation=f"vision-analysis:{vision_analysis_id}",
                model=self.provider.model,
                units=Decimal(len(frames)),
                unit_name="sampled_frame",
                estimated_cost=Decimal("0"),
                actual_cost=Decimal("0"),
                metadata={
                    "fixture": provider_result.provenance.get("fixture", False),
                    "external_call": provider_result.provenance.get("external_call", False),
                },
            )
            await self.repository.save_results(
                vision_analysis_id=vision_analysis_id,
                frames=frames,
                scenes=scenes,
                tracks=tracks,
                reframe_plans=reframe_plans,
                best_frame_ids=best_frame_ids,
                thumbnail_candidate_ids=thumbnail_candidate_ids,
                provider_provenance=provider_result.provenance,
            )
        except VisionProviderNotConfigured:
            await self.repository.mark_failed(vision_analysis_id, "PROVIDER_NOT_CONFIGURED")
            raise
        except Exception:
            await self.repository.mark_failed(vision_analysis_id, "VISION_ANALYSIS_FAILED")
            raise
        finally:
            local_path.unlink(missing_ok=True)
        result = await self.repository.get_analysis(vision_analysis_id)
        if result is None:
            raise RuntimeError("vision analysis result was not persisted")
        return result

    async def get(self, vision_analysis_id: str) -> VisionAnalysisRead | None:
        return await self.repository.get_analysis(vision_analysis_id)

    async def list(self, project_id: str) -> list[VisionAnalysisRead]:
        if await self.platform.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_analyses(project_id)
