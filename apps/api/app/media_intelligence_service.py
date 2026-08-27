from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from .auto_edit_repository import AutoEditRepository
from .media_intelligence_logic import (
    build_broll_decision,
    build_plan_items,
    platform_aspect_ratio,
    platform_orientation,
    select_strategy,
    stable_id,
)
from .media_intelligence_models import (
    ImageGenerationInput,
    MediaAssetProvenanceRead,
    MediaPlanRead,
    MediaPlanRequest,
    MediaResolutionJobRead,
    MediaResolutionRequest,
    StockMediaCandidateRead,
    VideoGenerationInput,
)
from .media_intelligence_providers import (
    ComfyUIBridgeGenerationProvider,
    ContractOnlyImageGenerationProvider,
    ContractOnlyStockMediaProvider,
    ContractOnlyVideoGenerationProvider,
    DeterministicImageGenerationProvider,
    DeterministicStockMediaProvider,
    DeterministicVideoGenerationProvider,
    ImageGenerationProvider,
    MediaProviderNotConfigured,
    ProviderMaterializedMedia,
    StockMediaProvider,
    VideoGenerationProvider,
)
from .media_intelligence_repository import MediaIntelligenceRepository
from .object_storage import ObjectStorageProvider, validate_object_key
from .platform_models import AssetRead, AssetRegister
from .repositories import PlatformRepository
from .vision_repository import VisionRepository


MEDIA_RESOLUTION_QUEUE_KEY = "npd:video-factory:v2:media-resolution:queued"
MEDIA_RESOLUTION_PROCESSING_KEY = "npd:video-factory:v2:media-resolution:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


@dataclass(frozen=True)
class MediaProviderBundle:
    stock: StockMediaProvider
    image: ImageGenerationProvider
    video: VideoGenerationProvider


def create_media_provider_bundle(settings) -> MediaProviderBundle:
    stock: StockMediaProvider = (
        DeterministicStockMediaProvider()
        if settings.stock_media_provider == "fixture"
        else ContractOnlyStockMediaProvider()
    )
    if settings.image_generation_provider == "fixture":
        image: ImageGenerationProvider = DeterministicImageGenerationProvider()
    elif settings.image_generation_provider == "comfyui":
        image = ComfyUIBridgeGenerationProvider(
            bridge_url=settings.comfyui_bridge_url,
            modality="image",
            workflow_id=settings.comfyui_image_workflow_id,
            enabled=settings.comfyui_execution_enabled,
            timeout_seconds=settings.comfyui_bridge_timeout_seconds,
        )
    else:
        image = ContractOnlyImageGenerationProvider()
    if settings.video_generation_provider == "fixture":
        video: VideoGenerationProvider = DeterministicVideoGenerationProvider()
    elif settings.video_generation_provider == "comfyui":
        video = ComfyUIBridgeGenerationProvider(
            bridge_url=settings.comfyui_bridge_url,
            modality="video",
            workflow_id=settings.comfyui_video_workflow_id,
            enabled=settings.comfyui_execution_enabled,
            timeout_seconds=settings.comfyui_bridge_timeout_seconds,
        )
    else:
        video = ContractOnlyVideoGenerationProvider()
    return MediaProviderBundle(stock=stock, image=image, video=video)


class MediaPlanningService:
    def __init__(
        self,
        *,
        repository: MediaIntelligenceRepository,
        auto_edit_repository: AutoEditRepository,
        vision_repository: VisionRepository,
        platform: PlatformRepository,
        providers: MediaProviderBundle,
        allow_external_execution: bool,
        allow_paid_execution: bool,
    ) -> None:
        self.repository = repository
        self.auto_edit_repository = auto_edit_repository
        self.vision_repository = vision_repository
        self.platform = platform
        self.providers = providers
        self.allow_external_execution = allow_external_execution
        self.allow_paid_execution = allow_paid_execution

    async def create(self, *, project_id: str, payload: MediaPlanRequest) -> MediaPlanRead:
        project = await self.platform.get_project(project_id)
        analysis = await self.auto_edit_repository.get_analysis(payload.analysis_id)
        if project is None or analysis is None or analysis.project_id != project_id:
            raise KeyError(project_id)
        if analysis.status != "succeeded":
            raise ValueError("Auto Edit analysis must be succeeded before media planning")
        vision = None
        if payload.vision_analysis_id:
            vision = await self.vision_repository.get_analysis(payload.vision_analysis_id)
            if (
                vision is None
                or vision.project_id != project_id
                or vision.analysis_id != analysis.analysis_id
                or vision.status != "succeeded"
            ):
                raise KeyError(payload.vision_analysis_id)
        source_asset = await self.auto_edit_repository.get_asset(analysis.asset_id)
        if source_asset is None:
            raise KeyError(analysis.asset_id)
        provider_status = self._provider_status()
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "project_id": project_id,
                    "analysis_fingerprint": analysis.fingerprint,
                    "vision_fingerprint": vision.fingerprint if vision else None,
                    "configuration": payload.model_dump(mode="json"),
                    "providers": provider_status,
                    "algorithm": "media-planner-v2-06.1",
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode("utf-8")
        ).hexdigest()
        media_plan_id, created = await self.repository.create_plan(
            analysis=analysis,
            vision=vision,
            fingerprint=fingerprint,
            configuration=payload,
            provider_status=provider_status,
            provenance={
                "algorithm": "media-planner-v2-06.1",
                "mock_tested": True,
                "real_provider_tested": False,
                "source_analysis_id": analysis.analysis_id,
                "vision_analysis_id": vision.vision_analysis_id if vision else None,
                "rights_gate": "unknown-or-non-production-media-blocks-publishing",
                "source_media_mutated": False,
                "publish_requested": False,
                "paid_external_call": False,
            },
        )
        if not created:
            existing = await self.repository.get_plan(media_plan_id)
            if existing is None:
                raise RuntimeError("media plan fingerprint exists without readable state")
            return existing
        try:
            stock_available = self._provider_available(self.providers.stock)
            image_available = self._provider_available(self.providers.image)
            video_available = self._provider_available(self.providers.video)
            image_input = ImageGenerationInput(
                prompt="media-plan-estimate",
                aspect_ratio=platform_aspect_ratio(payload.platform),
            )
            video_input = VideoGenerationInput(
                prompt="media-plan-estimate",
                aspect_ratio=platform_aspect_ratio(payload.platform),
            )
            image_cost = (
                await self.providers.image.estimate_cost(image_input) if image_available else None
            )
            video_cost = (
                await self.providers.video.estimate_cost(video_input) if video_available else None
            )
            stock_candidates: dict[str, list[StockMediaCandidateRead]] = {}
            total_stock_candidates = 0
            orientation = platform_orientation(payload.platform)
            for scene in analysis.scenes:
                broll = build_broll_decision(
                    analysis=analysis,
                    scene=scene,
                    vision=vision,
                    brand_context=payload.brand_context,
                )
                strategy = select_strategy(
                    ordinal=scene.ordinal,
                    payload=payload,
                    preferred_media_type=broll.preferred_media_type,
                    stock_available=stock_available,
                    image_available=image_available,
                    video_available=video_available,
                    has_source_asset=True,
                )
                if strategy not in {"stock_image", "stock_video"}:
                    continue
                if strategy == "stock_video":
                    found = await self.providers.stock.search_videos(
                        broll.search_query,
                        orientation=orientation,
                        limit=3,
                    )
                else:
                    found = await self.providers.stock.search_images(
                        broll.search_query,
                        orientation=orientation,
                        limit=3,
                    )
                self._validate_stock_evidence(found)
                stock_candidates[scene.scene_id] = found
                total_stock_candidates += len(found)
            items = build_plan_items(
                media_plan_id=media_plan_id,
                fingerprint=fingerprint,
                analysis=analysis,
                vision=vision,
                payload=payload,
                source_asset=source_asset,
                stock_candidates=stock_candidates,
                stock_available=stock_available,
                image_available=image_available,
                video_available=video_available,
                image_cost_vnd=image_cost,
                video_cost_vnd=video_cost,
            )
            projected = sum(
                (item.estimated_cost_vnd for item in items if item.strategy in {"ai_image", "ai_video"}),
                start=Decimal("0"),
            )
            needs_approval = any(item.needs_approval for item in items) or projected > payload.max_ai_cost_vnd
            await self.repository.save_plan_items(
                media_plan_id=media_plan_id,
                items=items,
                projected_ai_cost_vnd=projected,
                needs_approval=needs_approval,
            )
            if total_stock_candidates:
                await self.platform.record_provider_operation(
                    workspace_id=analysis.workspace_id,
                    project_id=project_id,
                    job_id=None,
                    provider_key=self.providers.stock.key,
                    capability="stock_media",
                    operation=f"media-plan-stock-search:{media_plan_id}",
                    units=Decimal(total_stock_candidates),
                    unit_name="candidate",
                    estimated_cost=Decimal("0"),
                    actual_cost=Decimal("0"),
                    metadata={
                        "fixture": True,
                        "external_call": False,
                        "paid": False,
                        "social_media_downloaded": False,
                    },
                )
        except Exception:
            await self.repository.mark_plan_failed(media_plan_id, "MEDIA_PLANNING_FAILED")
            raise
        result = await self.repository.get_plan(media_plan_id)
        if result is None:
            raise RuntimeError("media plan result was not persisted")
        return result

    async def get(self, media_plan_id: str) -> MediaPlanRead | None:
        return await self.repository.get_plan(media_plan_id)

    async def list(self, project_id: str) -> list[MediaPlanRead]:
        if await self.platform.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_plans(project_id)

    async def list_media_assets(self, project_id: str) -> list[MediaAssetProvenanceRead]:
        if await self.platform.get_project(project_id) is None:
            raise KeyError(project_id)
        return await self.repository.list_media_assets(project_id)

    def _provider_available(self, provider) -> bool:
        return bool(
            provider.configured
            and (not provider.external or self.allow_external_execution)
            and (not provider.paid or self.allow_paid_execution)
        )

    def _provider_status(self) -> dict[str, object]:
        return {
            "stock": _provider_state(self.providers.stock, self._provider_available(self.providers.stock)),
            "image_generation": _provider_state(
                self.providers.image, self._provider_available(self.providers.image)
            ),
            "video_generation": _provider_state(
                self.providers.video, self._provider_available(self.providers.video)
            ),
            "external_execution_enabled": self.allow_external_execution,
            "paid_execution_enabled": self.allow_paid_execution,
        }

    def _validate_stock_evidence(self, candidates: list[StockMediaCandidateRead]) -> None:
        for candidate in candidates:
            external = bool(candidate.provenance.get("external_call"))
            paid = bool(candidate.provenance.get("paid"))
            if external and not self.allow_external_execution:
                raise RuntimeError("external stock execution is disabled in V2-06")
            if paid and not self.allow_paid_execution:
                raise RuntimeError("paid stock execution is disabled in V2-06")
            if candidate.provenance.get("social_media_downloaded"):
                raise RuntimeError("social-platform media download is prohibited")


class MediaResolutionService:
    def __init__(
        self,
        *,
        repository: MediaIntelligenceRepository,
        platform: PlatformRepository,
        auto_edit_repository: AutoEditRepository,
        object_storage: ObjectStorageProvider,
        providers: MediaProviderBundle,
        queue: QueueClient,
        staging_root: Path,
        allow_external_execution: bool,
        allow_paid_execution: bool,
    ) -> None:
        self.repository = repository
        self.platform = platform
        self.auto_edit_repository = auto_edit_repository
        self.object_storage = object_storage
        self.providers = providers
        self.queue = queue
        self.staging_root = staging_root
        self.allow_external_execution = allow_external_execution
        self.allow_paid_execution = allow_paid_execution

    async def enqueue(
        self,
        *,
        project_id: str,
        media_plan_id: str,
        media_plan_item_id: str,
        payload: MediaResolutionRequest,
    ) -> MediaResolutionJobRead:
        plan = await self.repository.get_plan(media_plan_id)
        if plan is None or plan.project_id != project_id:
            raise KeyError(media_plan_id)
        item = next(
            (value for value in plan.items if value.media_plan_item_id == media_plan_item_id),
            None,
        )
        if item is None:
            raise KeyError(media_plan_item_id)
        provider_key, capability, operation, request_payload, estimate, external, paid, tested = (
            await self._resolution_contract(plan, item, payload)
        )
        selected_candidate_id = payload.candidate_id
        if item.strategy in {"stock_image", "stock_video"}:
            if not selected_candidate_id and item.candidates:
                selected_candidate_id = item.candidates[0].candidate_id
            if not selected_candidate_id or selected_candidate_id not in {
                candidate.candidate_id for candidate in item.candidates
            }:
                raise ValueError("selected stock candidate is not part of the media plan item")
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "media_plan_fingerprint": plan.fingerprint,
                    "item_id": media_plan_item_id,
                    "strategy": item.strategy,
                    "candidate_id": selected_candidate_id,
                    "provider": provider_key,
                    "request": request_payload,
                    "algorithm": "media-resolution-v2-06.1",
                },
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        job, created = await self.repository.create_resolution_job(
            media_plan_id=media_plan_id,
            media_plan_item_id=media_plan_item_id,
            fingerprint=fingerprint,
            provider_key=provider_key,
            capability=capability,
            operation=operation,
            selected_candidate_id=selected_candidate_id,
            request_payload=request_payload,
            estimated_cost_vnd=estimate,
            external_call=external,
            paid=paid,
            real_provider_tested=tested,
            provenance={
                "algorithm": "media-resolution-v2-06.1",
                "asynchronous": True,
                "fixture": not external,
                "request": request_payload,
                "source_media_mutated": False,
                "publish_requested": False,
            },
        )
        if created and job.status == "queued":
            await self.queue.rpush(MEDIA_RESOLUTION_QUEUE_KEY, job.resolution_job_id)
        return job

    async def process(self, resolution_job_id: str) -> MediaResolutionJobRead:
        job, plan, item = await self.repository.get_resolution_context(resolution_job_id)
        if job.status in {"succeeded", "failed", "cancelled", "needs_approval"}:
            return job
        await self.repository.mark_resolution_running(resolution_job_id)
        staging_path: Path | None = None
        try:
            materialized, existing_asset = await self._materialize(job, plan, item)
            if materialized.external_call and not self.allow_external_execution:
                raise RuntimeError("external media execution is disabled in V2-06")
            if materialized.paid and not self.allow_paid_execution:
                raise RuntimeError("paid media execution is disabled in V2-06")
            if materialized.estimated_cost_vnd > plan.max_ai_cost_vnd and item.strategy in {
                "ai_image",
                "ai_video",
                "motion_graphic",
            }:
                await self.repository.mark_resolution_needs_approval(
                    resolution_job_id,
                    reason="Projected AI media cost exceeds max_ai_cost_vnd.",
                )
                result = await self.repository.get_resolution_job(resolution_job_id)
                if result is None:
                    raise RuntimeError("resolution approval state was not persisted")
                return result
            asset = existing_asset
            if asset is None:
                safe_name = _safe_filename(materialized.filename)
                self.staging_root.mkdir(parents=True, exist_ok=True)
                staging_path = self.staging_root / f"{resolution_job_id}-{safe_name}"
                staging_path.write_bytes(materialized.payload)
                object_key = validate_object_key(
                    f"workspaces/{plan.workspace_id}/projects/{plan.project_id}/media/"
                    f"{resolution_job_id}/{safe_name}"
                )
                stored = await self.object_storage.put_file(
                    object_key=object_key,
                    path=staging_path,
                    content_type=materialized.content_type,
                )
                asset_class = "stock" if materialized.source_type == "stock" else "generated"
                asset = await self.platform.register_asset(
                    plan.project_id,
                    AssetRegister(
                        project_version_id=plan.project_version_id,
                        asset_class=asset_class,
                        kind=_asset_kind(item.strategy, materialized.content_type),
                        filename=safe_name,
                        object_key=stored.object_key,
                        content_type=stored.content_type,
                        size_bytes=stored.size_bytes,
                        checksum_sha256=stored.checksum_sha256,
                        storage_provider=stored.storage_provider,
                        provenance={
                            "source_type": materialized.source_type,
                            "rights_status": materialized.rights_status,
                            "license": materialized.license,
                            "license_url": materialized.license_url,
                            "provider": job.provider_key,
                            "provider_asset_id": materialized.provider_asset_id,
                            "source_reference": materialized.source_reference,
                            "generation_provenance": materialized.generation_provenance,
                            "production_eligible": materialized.production_eligible,
                            "fixture": not materialized.external_call,
                        },
                    ),
                )
            await self.platform.record_provider_operation(
                workspace_id=plan.workspace_id,
                project_id=plan.project_id,
                job_id=None,
                provider_key=job.provider_key,
                capability=job.capability,
                operation=f"media-resolution:{resolution_job_id}",
                model=str(materialized.generation_provenance.get("model") or "v2-06"),
                units=Decimal("1"),
                unit_name="asset",
                estimated_cost=materialized.estimated_cost_vnd,
                actual_cost=materialized.actual_cost_vnd,
                max_cost_vnd=plan.max_ai_cost_vnd,
                metadata={
                    "fixture": not materialized.external_call,
                    "external_call": materialized.external_call,
                    "paid": materialized.paid,
                    "real_provider_tested": materialized.real_provider_tested,
                },
            )
            media_asset_id = stable_id("mas", resolution_job_id, asset.asset_id)
            await self.repository.complete_resolution(
                resolution_job_id=resolution_job_id,
                asset=asset,
                media_asset_id=media_asset_id,
                source_type=materialized.source_type,
                rights_status=materialized.rights_status,
                license_name=materialized.license,
                license_url=materialized.license_url,
                provider=job.provider_key,
                provider_asset_id=materialized.provider_asset_id,
                creator=materialized.creator,
                source_reference=materialized.source_reference,
                attribution_requirement=materialized.attribution_requirement,
                generation_provenance=materialized.generation_provenance,
                width=materialized.width,
                height=materialized.height,
                duration_seconds=materialized.duration_seconds,
                orientation=materialized.orientation,
                production_eligible=materialized.production_eligible,
                provider_job_id=materialized.provider_job_id,
                actual_cost_vnd=materialized.actual_cost_vnd,
                downloaded_at=datetime.now(timezone.utc) if existing_asset is None else None,
                provenance={
                    "resolution_job_id": resolution_job_id,
                    "rights_evidence_preserved": True,
                    "owner_override_recorded": False,
                    "source_media_mutated": False,
                    "publish_requested": False,
                },
            )
        except MediaProviderNotConfigured as exc:
            await self.repository.mark_resolution_failed(
                resolution_job_id,
                error_code="PROVIDER_NOT_CONFIGURED",
                reason=str(exc),
            )
        except Exception as exc:
            await self.repository.mark_resolution_failed(
                resolution_job_id,
                error_code="MEDIA_RESOLUTION_FAILED",
                reason=str(exc),
            )
        finally:
            if staging_path:
                staging_path.unlink(missing_ok=True)
        result = await self.repository.get_resolution_job(resolution_job_id)
        if result is None:
            raise RuntimeError("resolution result was not persisted")
        return result

    async def get(self, resolution_job_id: str) -> MediaResolutionJobRead | None:
        return await self.repository.get_resolution_job(resolution_job_id)

    async def recover_pending(self) -> int:
        identifiers = await self.repository.list_incomplete_resolution_job_ids()
        for identifier in identifiers:
            await self.queue.rpush(MEDIA_RESOLUTION_QUEUE_KEY, identifier)
        return len(identifiers)

    async def _resolution_contract(self, plan, item, payload):
        aspect = platform_aspect_ratio(plan.configuration.platform)
        seed = int(hashlib.sha256(item.media_plan_item_id.encode()).hexdigest()[:8], 16) % 2_147_483_648
        if item.strategy == "user_asset":
            return (
                "internal-media",
                "internal_media",
                "reuse-user-asset",
                {"source_asset_id": item.source_asset_id},
                Decimal("0"),
                False,
                False,
                False,
            )
        if item.strategy in {"stock_image", "stock_video"}:
            return (
                self.providers.stock.key,
                "stock_media",
                f"resolve-{item.strategy}",
                {"candidate_id": payload.candidate_id},
                Decimal("0"),
                self.providers.stock.external,
                self.providers.stock.paid,
                self.providers.stock.real_provider_tested,
            )
        if item.strategy in {"ai_image", "motion_graphic"}:
            request = ImageGenerationInput(
                prompt=item.broll.generation_prompt,
                negative_prompt="logos, watermarks, copied creator composition",
                aspect_ratio=aspect,
                style="motion graphic" if item.strategy == "motion_graphic" else "cinematic",
                seed=seed,
                quality="draft",
            )
            estimate = await self.providers.image.estimate_cost(request) if self.providers.image.configured else None
            return (
                self.providers.image.key,
                "image_generation",
                f"generate-{item.strategy}",
                request.model_dump(mode="json"),
                estimate,
                self.providers.image.external,
                self.providers.image.paid,
                self.providers.image.real_provider_tested,
            )
        request = VideoGenerationInput(
            prompt=item.broll.generation_prompt,
            negative_prompt="logos, watermarks, copied creator composition",
            aspect_ratio=aspect,
            duration_seconds=min(10, item.broll.duration_seconds),
            seed=seed,
        )
        estimate = await self.providers.video.estimate_cost(request) if self.providers.video.configured else None
        return (
            self.providers.video.key,
            "video_generation",
            "generate-ai-video",
            request.model_dump(mode="json"),
            estimate,
            self.providers.video.external,
            self.providers.video.paid,
            self.providers.video.real_provider_tested,
        )

    async def _materialize(self, job, plan, item) -> tuple[ProviderMaterializedMedia, AssetRead | None]:
        if item.strategy in {"stock_image", "stock_video"} and not self.providers.stock.configured:
            raise MediaProviderNotConfigured("Stock media provider is not configured")
        if item.strategy in {"ai_image", "motion_graphic"} and not self.providers.image.configured:
            raise MediaProviderNotConfigured("Image generation provider is not configured")
        if item.strategy == "ai_video" and not self.providers.video.configured:
            raise MediaProviderNotConfigured("Video generation provider is not configured")
        if job.external_call and not self.allow_external_execution:
            raise RuntimeError("external media execution is disabled in V2-06")
        if job.paid and not self.allow_paid_execution:
            raise RuntimeError("paid media execution is disabled in V2-06")
        if item.strategy == "user_asset":
            if not item.source_asset_id:
                raise RuntimeError("user-asset plan item is missing its source asset")
            asset = await self.auto_edit_repository.get_asset(item.source_asset_id)
            if asset is None or asset.project_id != plan.project_id:
                raise KeyError(item.source_asset_id)
            rights = str(asset.provenance.get("rights_status", "unknown"))
            license_name = str(asset.provenance.get("license", "unknown"))
            return (
                ProviderMaterializedMedia(
                    filename=asset.filename,
                    content_type=asset.content_type,
                    payload=b"",
                    provider_job_id=None,
                    source_type="user_upload",
                    rights_status=rights,
                    license=license_name,
                    license_url=asset.provenance.get("license_url"),
                    provider_asset_id=asset.asset_id,
                    creator=None,
                    source_reference=f"asset://{asset.asset_id}",
                    attribution_requirement=None,
                    width=job.provenance.get("width"),
                    height=job.provenance.get("height"),
                    duration_seconds=job.provenance.get("duration_seconds"),
                    orientation="unknown",
                    production_eligible=rights in {"owned", "licensed"},
                    estimated_cost_vnd=Decimal("0"),
                    actual_cost_vnd=Decimal("0"),
                    external_call=False,
                    paid=False,
                    real_provider_tested=False,
                    generation_provenance={
                        "source": "immutable-user-upload",
                        "checksum_sha256": asset.checksum_sha256,
                        "source_media_mutated": False,
                    },
                ),
                asset,
            )
        if item.strategy in {"stock_image", "stock_video"}:
            selected = next(
                (
                    candidate
                    for candidate in item.candidates
                    if candidate.candidate_id == job.selected_candidate_id
                ),
                None,
            )
            if selected is None:
                raise ValueError("selected stock candidate is missing")
            if selected.provider != self.providers.stock.key:
                raise ValueError("selected stock candidate belongs to a different provider")
            # Non-external fixtures are fully materializable from the candidate
            # contract persisted with the media plan.  Do not depend on an
            # in-process search cache: API planning and worker resolution run in
            # separate containers and both must survive restarts.  External
            # adapters may still refresh provider metadata or signed URLs.
            candidate = (
                await self.providers.stock.get_asset(selected.provider_asset_id)
                if self.providers.stock.external
                else selected
            )
            return await self.providers.stock.download_asset(candidate), None
        if item.strategy in {"ai_image", "motion_graphic"}:
            request = ImageGenerationInput.model_validate(job.provenance.get("request") or {})
            return await self.providers.image.generate(request), None
        request = VideoGenerationInput.model_validate(job.provenance.get("request") or {})
        return await self.providers.video.generate(request), None


def _provider_state(provider, available: bool) -> dict[str, object]:
    if not provider.configured:
        status = "not_configured"
    elif available:
        status = "healthy"
    else:
        status = "disabled"
    return {
        "provider_key": provider.key,
        "status": status,
        "configured": provider.configured,
        "external": provider.external,
        "paid": provider.paid,
        "real_provider_tested": provider.real_provider_tested,
    }


def _safe_filename(value: str) -> str:
    name = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(value).name).strip(".-")
    if not name:
        raise ValueError("provider returned an unsafe filename")
    return name[:128]


def _asset_kind(strategy: str, content_type: str) -> str:
    if content_type == "image/svg+xml":
        return "stock_image" if strategy == "stock_image" else "generated_image"
    if "fixture" in content_type or content_type.endswith("+json"):
        return "media_contract_fixture"
    return "stock_video" if strategy == "stock_video" else "generated_video"
