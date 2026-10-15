from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
import tempfile
from contextlib import nullcontext
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
from .provider_safety import (
    ProviderCallContext,
    ProviderSafetyBlocked,
    ProviderSafetyController,
    verify_provider_artifact,
    verify_provider_artifact_storage,
)
from .vision_repository import VisionRepository
from .stock_media_providers import PexelsStockMediaProvider,PixabayStockMediaProvider,stock_request_scope
from .media_generation_scope import media_generation_scope
from .stock_wire_context import CURRENT_OPERATION,stock_wire_operation
from .stock_wire_quota import StockWireDeferred,digest as stock_digest
from .stock_media_providers import OfficialStockProvider,StockProviderFailure
from . import stock_resolution_deferral as stock_wait
from . import stock_planner_retry as stock_planner
from .auto_edit_models import AutoEditAnalysisRead
from .vision_models import VisionAnalysisRead
from .object_storage import sha256_file
from .frozen_storage_read import frozen_asset_read, completed_read, MAX_SOURCE_BYTES
from .bounded_storage_download import StorageDownloadError


MEDIA_RESOLUTION_QUEUE_KEY = "npd:video-factory:v2:media-resolution:queued"
MEDIA_RESOLUTION_PROCESSING_KEY = "npd:video-factory:v2:media-resolution:processing"


class QueueClient(Protocol):
    async def rpush(self, key: str, value: str) -> object: ...


@dataclass(frozen=True)
class MediaProviderBundle:
    stock: StockMediaProvider
    image: ImageGenerationProvider
    video: VideoGenerationProvider


def create_media_provider_bundle(settings, *, stock_wire_guard=None) -> MediaProviderBundle:
    stock: StockMediaProvider = (
        DeterministicStockMediaProvider()
        if settings.stock_media_provider == "fixture"
        else ContractOnlyStockMediaProvider()
    )
    if settings.stock_media_provider in {'pexels','pixabay'}:
        adapter=PexelsStockMediaProvider if settings.stock_media_provider=='pexels' else PixabayStockMediaProvider
        secret=settings.pexels_api_key if settings.stock_media_provider=='pexels' else settings.pixabay_api_key
        stock=adapter(api_key=secret.get_secret_value(),enabled=settings.media_external_execution_enabled,
            cache_root=settings.stock_cache_root,wire_guard=stock_wire_guard,require_wire_guard=True)
    if settings.image_generation_provider == "fixture":
        image: ImageGenerationProvider = DeterministicImageGenerationProvider()
    elif settings.image_generation_provider == "comfyui":
        image = ComfyUIBridgeGenerationProvider(
            bridge_url=settings.comfyui_bridge_url,
            modality="image",
            workflow_id=settings.comfyui_image_workflow_id,
            enabled=settings.comfyui_execution_enabled,
            timeout_seconds=settings.comfyui_bridge_timeout_seconds,
            service_token=settings.comfyui_bridge_token.get_secret_value(),
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
            service_token=settings.comfyui_bridge_token.get_secret_value(),
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
        learning=None,
        object_storage=None,
    ) -> None:
        self.repository = repository
        self.auto_edit_repository = auto_edit_repository
        self.vision_repository = vision_repository
        self.platform = platform
        self.providers = providers
        self.allow_external_execution = allow_external_execution
        self.allow_paid_execution = allow_paid_execution
        self.learning = learning
        self.object_storage = object_storage

    async def create(self, *, project_id: str, payload: MediaPlanRequest,
                     defer_stock_execution: bool = False) -> MediaPlanRead:
        project = await self.platform.get_project(project_id)
        analysis = await self.auto_edit_repository.get_analysis(payload.analysis_id,transcript_id=payload.transcript_id)
        if project is None or analysis is None or analysis.project_id != project_id:
            raise KeyError(project_id)
        learning_feedback = None
        if payload.learning_snapshot_id:
            if self.learning is None: raise ValueError('LEARNING_SERVICE_NOT_CONFIGURED')
            learning_feedback = await self.learning.feedback(project.workspace_id, payload.learning_snapshot_id, niche=project.niche)
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
        if source_asset is None or source_asset.project_id != project_id:
            raise KeyError(analysis.asset_id)
        if analysis.provenance.get('source_asset_checksum') != source_asset.checksum_sha256:
            raise ValueError('source analysis checksum is stale')
        if vision and vision.provenance.get('source_asset_checksum') != source_asset.checksum_sha256:
            raise ValueError('saved Vision checksum differs from the source asset')
        provider_status = self._provider_status()
        if self._managed_stock():
            provider_status = {**provider_status, 'stock_binding': self._stock_identity()}
        supporting_assets = await self.platform.list_assets(project_id) if payload.purpose == 'supporting_broll' else []
        fingerprint = hashlib.sha256(
            json.dumps(
                {
                    "project_id": project_id,
                    "analysis_fingerprint": analysis.fingerprint,
                    "transcript_id":analysis.transcript.transcript_id if analysis.transcript else None,
                    "transcript_version":analysis.transcript.version if analysis.transcript else None,
                    "vision_fingerprint": vision.fingerprint if vision else None,
                    "configuration": payload.model_dump(mode="json", exclude={'learning_snapshot_id'} if payload.learning_snapshot_id is None else set()),
                    "providers": provider_status,
                    "algorithm": "priority-media-planner-v1",
                    **({'execution_mode': 'reviewed-preparation-only-v1'} if defer_stock_execution else {}),
                    **({'supporting_assets':[(asset.asset_id,asset.checksum_sha256,asset.provenance,asset.filename)
                        for asset in supporting_assets]} if payload.purpose=='supporting_broll' else {}),
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
                "algorithm": "priority-media-planner-v1",
                "selection_policy":payload.selection_policy,
                "transcript_id":analysis.transcript.transcript_id if analysis.transcript else None,
                "source_asset_sha256":source_asset.checksum_sha256,
                "mock_tested": True,
                "real_provider_tested": False,
                "source_analysis_id": analysis.analysis_id,
                "vision_analysis_id": vision.vision_analysis_id if vision else None,
                "rights_gate": "unknown-or-non-production-media-blocks-publishing",
                "source_media_mutated": False,
                "publish_requested": False,
                "paid_external_call": False,
                **({'learning_feedback': learning_feedback} if learning_feedback else {}),
            },
        )
        if not created:
            existing = await self.repository.get_plan(media_plan_id)
            if existing is None:
                raise RuntimeError("media plan fingerprint exists without readable state")
            return existing
        if self._managed_stock():
            binding = await self._freeze_stock_plan(project, analysis, vision, source_asset, supporting_assets,
                payload, provider_status, defer_stock_execution=defer_stock_execution)
            if binding['searches']:
                binding.update(media_plan_id=media_plan_id, fingerprint=fingerprint,
                    project_version_id=analysis.project_version_id)
                await stock_planner.initialize(self.repository, media_plan_id, binding, self._stock_clock(),
                    require_review=defer_stock_execution)
                if defer_stock_execution:
                    return await self.repository.get_plan(media_plan_id)
                return await self.process_stock_plan(media_plan_id)
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
                await self.providers.image.estimate_cost(image_input)
                if image_available and (not defer_stock_execution or payload.allow_ai_image) else None
            )
            video_cost = (
                await self.providers.video.estimate_cost(video_input)
                if video_available and (not defer_stock_execution or payload.allow_ai_video) else None
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
                if payload.purpose == 'supporting_broll':
                    from .broll_planner import supporting_candidates,choose_supporting_strategy
                    strategy,_ = choose_supporting_strategy(payload,supporting_candidates(supporting_assets,analysis,broll.search_query),
                        stock=stock_available,image=image_available,video=video_available,preferred_type=broll.preferred_media_type)
                if strategy not in {"stock_image", "stock_video"}:
                    continue
                if defer_stock_execution:
                    raise ValueError('REVIEWED_STOCK_SCHEDULER_REQUIRED')
                with stock_request_scope(project.workspace_id), stock_wire_operation(workspace_id=project.workspace_id,
                    project_id=project_id,source_ref='media-plan:'+media_plan_id+':'+scene.scene_id,
                    budget_sha256=stock_digest({'max_ai_cost_vnd':str(payload.max_ai_cost_vnd),'paid':False})):
                    if strategy == "stock_video":
                        found = await self.providers.stock.search_videos(broll.search_query,orientation=orientation,limit=3)
                    else:
                        found = await self.providers.stock.search_images(broll.search_query,orientation=orientation,limit=3)
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
                supporting_assets=supporting_assets,
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
                    actual_cost=None if self.providers.stock.external else Decimal("0"),
                    metadata={
                        "fixture": not self.providers.stock.external,
                        "external_call": self.providers.stock.external,
                        "paid": self.providers.stock.paid,
                        "real_provider_tested":self.providers.stock.real_provider_tested,
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

    def _managed_stock(self):
        stock = self.providers.stock
        return isinstance(stock, OfficialStockProvider) and stock.wire_guard is not None \
            and self._provider_available(stock) and not stock.paid

    def _stock_identity(self):
        stock = self.providers.stock
        return {'provider': stock.key, 'mode': stock.cache_mode,
            'configuration_sha256': stock.cache_binding_sha256, 'paid': stock.paid}

    def _stock_clock(self):
        return stock_planner.clock(self.providers.stock.wire_guard.clock())

    async def _freeze_stock_plan(self, project, analysis, vision, source, supporting, payload, provider_status,
                                 *, defer_stock_execution=False):
        available = {'stock': self._provider_available(self.providers.stock),
            'image': self._provider_available(self.providers.image), 'video': self._provider_available(self.providers.video)}
        aspect = platform_aspect_ratio(payload.platform)
        image_cost = await self.providers.image.estimate_cost(ImageGenerationInput(prompt='media-plan-estimate',
            aspect_ratio=aspect)) if available['image'] and (not defer_stock_execution or payload.allow_ai_image) else None
        video_cost = await self.providers.video.estimate_cost(VideoGenerationInput(prompt='media-plan-estimate',
            aspect_ratio=aspect)) if available['video'] and (not defer_stock_execution or payload.allow_ai_video) else None
        searches = []
        for scene in analysis.scenes:
            broll = build_broll_decision(analysis=analysis, scene=scene, vision=vision, brand_context=payload.brand_context)
            strategy = select_strategy(ordinal=scene.ordinal, payload=payload, preferred_media_type=broll.preferred_media_type,
                stock_available=available['stock'], image_available=available['image'], video_available=available['video'],
                has_source_asset=True)
            if payload.purpose == 'supporting_broll':
                from .broll_planner import supporting_candidates, choose_supporting_strategy
                strategy, _ = choose_supporting_strategy(payload, supporting_candidates(supporting, analysis, broll.search_query),
                    stock=available['stock'], image=available['image'], video=available['video'],
                    preferred_type=broll.preferred_media_type)
            if strategy in {'stock_image', 'stock_video'}:
                searches.append({'scene_id': scene.scene_id, 'strategy': strategy, 'query': broll.search_query,
                    'orientation': platform_orientation(payload.platform), 'limit': 3})
        inputs = {'project': project.model_dump(mode='json'), 'analysis': analysis.model_dump(mode='json'),
            'vision': vision.model_dump(mode='json') if vision else None, 'source_asset': source.model_dump(mode='json'),
            'supporting_assets': [asset.model_dump(mode='json') for asset in supporting],
            'configuration': payload.model_dump(mode='json'), 'provider_status': provider_status}
        return {'schema_version': 'sql-stock-planner-binding.v1', 'paid': False, 'provider': self._stock_identity(),
            'inputs': inputs, 'inputs_sha256': stock_digest(inputs), 'availability': available,
            'image_cost_vnd': str(image_cost) if image_cost is not None else None,
            'video_cost_vnd': str(video_cost) if video_cost is not None else None,
            'budget_sha256': stock_digest({'max_ai_cost_vnd': str(payload.max_ai_cost_vnd), 'paid': False}),
            'searches': searches, 'source_file_sha256': source.checksum_sha256}

    async def _verify_stock_plan_inputs(self, plan, binding, *, verify_bytes=True):
        if not self._managed_stock():
            raise ValueError('STOCK_PLANNER_NOT_CONFIGURED')
        if binding['provider'] != self._stock_identity():
            raise ValueError('STOCK_PLANNER_PROVIDER_CHANGED')
        inputs = binding['inputs']
        if plan.media_plan_id != binding['media_plan_id'] or plan.fingerprint != binding['fingerprint'] \
                or plan.workspace_id != inputs['project']['workspace_id'] or plan.project_id != inputs['project']['project_id'] \
                or plan.project_version_id != binding['project_version_id'] or plan.analysis_id != inputs['analysis']['analysis_id'] \
                or plan.vision_analysis_id != (inputs['vision']['vision_analysis_id'] if inputs['vision'] else None) \
                or plan.max_ai_cost_vnd != Decimal(inputs['configuration']['max_ai_cost_vnd']):
            raise ValueError('STOCK_PLANNER_PLAN_SCOPE_CHANGED')
        if stock_digest(inputs) != binding['inputs_sha256'] or inputs['configuration'] != plan.configuration.model_dump(mode='json') \
                or inputs['provider_status'] != plan.provider_status:
            raise ValueError('STOCK_PLANNER_BINDING_CHANGED')
        project = await self.platform.get_project(plan.project_id)
        analysis = await self.auto_edit_repository.get_analysis(plan.analysis_id, transcript_id=plan.configuration.transcript_id)
        source = await self.auto_edit_repository.get_asset(inputs['source_asset']['asset_id'])
        vision = await self.vision_repository.get_analysis(plan.vision_analysis_id) if plan.vision_analysis_id else None
        supporting = await self.platform.list_assets(plan.project_id) if plan.configuration.purpose == 'supporting_broll' else []
        current = {'project': project.model_dump(mode='json') if project else None,
            'analysis': analysis.model_dump(mode='json') if analysis else None,
            'vision': vision.model_dump(mode='json') if vision else None,
            'source_asset': source.model_dump(mode='json') if source else None,
            'supporting_assets': [asset.model_dump(mode='json') for asset in supporting],
            'configuration': plan.configuration.model_dump(mode='json'), 'provider_status': plan.provider_status}
        if stock_digest(current) != binding['inputs_sha256']:
            raise ValueError('STOCK_PLANNER_SOURCE_CHANGED')
        if not verify_bytes:
            return
        if self.object_storage is None:
            raise ValueError('STOCK_PLANNER_SOURCE_STORAGE_NOT_CONFIGURED')
        with tempfile.TemporaryDirectory(prefix='vf-sp-') as owned:
            path = Path(owned) / 'source'
            try:
                proof=frozen_asset_read(AssetRead.model_validate(inputs['source_asset']),
                    workspace_id=plan.workspace_id,project_id=plan.project_id,storage=self.object_storage,
                    maximum=MAX_SOURCE_BYTES)
                await proof.download(self.object_storage,path)
                checksum=await completed_read(asyncio.to_thread(sha256_file,path))
            except StorageDownloadError as error:
                if error.code in {'STORAGE_DOWNLOAD_HASH_MISMATCH','STORAGE_DOWNLOAD_SIZE_MISMATCH','STORAGE_DOWNLOAD_SIZE_LIMIT'}:
                    raise ValueError('STOCK_PLANNER_SOURCE_FILE_CHANGED') from None
                raise ValueError('STOCK_PLANNER_SOURCE_DOWNLOAD_FAILED') from None
            except Exception:
                raise ValueError('STOCK_PLANNER_SOURCE_DOWNLOAD_FAILED') from None
            if checksum != binding['source_file_sha256']:
                raise ValueError('STOCK_PLANNER_SOURCE_FILE_CHANGED')
        # The object download is awaited. Recheck current database versions
        # after it completes so an edit during that wait cannot start a wire.
        latest = await self.repository.get_plan(plan.media_plan_id)
        await self._verify_stock_plan_inputs(latest, binding, verify_bytes=False)

    async def process_stock_plan(self, media_plan_id: str, *, expected_version=None,
                                 binding_sha256=None) -> MediaPlanRead:
        plan = await self.repository.get_plan(media_plan_id)
        if plan is None:
            raise KeyError(media_plan_id)
        value = stock_planner.state(plan.provenance)
        reviewed = expected_version is not None or binding_sha256 is not None
        configured = isinstance(self.providers.stock, OfficialStockProvider) and self.providers.stock.wire_guard is not None
        if not reviewed and (value is None or value['status'] in stock_planner.TERMINAL or not configured):
            return plan
        stamp = self._stock_clock() if configured else time.time()
        claim_id = await stock_planner.claim(self.repository, media_plan_id, stamp,
            expected_version=expected_version, binding_sha256=binding_sha256, allow_claim=configured)
        if claim_id is None:
            return await self.repository.get_plan(media_plan_id)
        try:
            await self._verify_stock_plan_inputs(plan, value['binding'])
            for request in value['binding']['searches']:
                current = await self.repository.get_plan(media_plan_id)
                execution = stock_planner.state(current.provenance)
                if not stock_planner.owned(execution, claim_id) or execution['lease_until'] <= self._stock_clock():
                    return current
                if request['scene_id'] in execution['results']:
                    continue
                # A queued plan can outlive edits made while a previous search
                # was in flight. Validate again before starting the next wire.
                await self._verify_stock_plan_inputs(current, value['binding'])
                current = await self.repository.get_plan(media_plan_id)
                execution = stock_planner.state(current.provenance)
                if not stock_planner.owned(execution, claim_id, self._stock_clock()):
                    return current
                calls = 0
                try:
                    with stock_request_scope(plan.workspace_id), stock_wire_operation(workspace_id=plan.workspace_id,
                        project_id=plan.project_id, source_ref='media-plan:'+media_plan_id+':'+request['scene_id'],
                        budget_sha256=value['binding']['budget_sha256']) as operation:
                        method = self.providers.stock.search_videos if request['strategy'] == 'stock_video' else self.providers.stock.search_images
                        try:
                            found = await method(request['query'], orientation=request['orientation'], limit=request['limit'])
                        finally:
                            calls = operation.wire_attempts
                    self._validate_stock_evidence(found)
                    if calls:
                        await self._meter_stock_search(plan, request, claim_id, value['binding_sha256'], calls, 'succeeded')
                    if not await stock_planner.checkpoint(self.repository, media_plan_id, claim_id, request['scene_id'],
                        [candidate.model_dump(mode='json') for candidate in found], calls, stamp=self._stock_clock()):
                        return await self.repository.get_plan(media_plan_id)
                except StockWireDeferred as deferred:
                    await stock_planner.wait(self.repository, media_plan_id, claim_id, scene_id=request['scene_id'],
                        code=deferred.code, next_at=deferred.next_at, calls=calls, stamp=self._stock_clock())
                    return await self.repository.get_plan(media_plan_id)
                except StockProviderFailure as error:
                    if calls:
                        await self._meter_stock_search(plan, request, claim_id, value['binding_sha256'], calls, 'failed', error.code)
                    if not error.retryable:
                        await stock_planner.fail(self.repository, media_plan_id, claim_id, error.code, calls=calls,
                            stamp=self._stock_clock())
                        return await self.repository.get_plan(media_plan_id)
                    now = self._stock_clock()
                    await stock_planner.wait(self.repository, media_plan_id, claim_id, scene_id=request['scene_id'],
                        code=error.code, next_at=now+max(5, error.retry_after_seconds or 0), calls=calls, stamp=now)
                    return await self.repository.get_plan(media_plan_id)
            current = await self.repository.get_plan(media_plan_id)
            execution = stock_planner.state(current.provenance)
            if not stock_planner.owned(execution, claim_id):
                return current
            await self._verify_stock_plan_inputs(current, value['binding'])
            binding = value['binding'];inputs = binding['inputs'];available = binding['availability']
            items = build_plan_items(media_plan_id=media_plan_id, fingerprint=plan.fingerprint,
                analysis=AutoEditAnalysisRead.model_validate(inputs['analysis']),
                vision=VisionAnalysisRead.model_validate(inputs['vision']) if inputs['vision'] else None,
                payload=plan.configuration, source_asset=AssetRead.model_validate(inputs['source_asset']),
                stock_candidates={scene: [StockMediaCandidateRead.model_validate(candidate) for candidate in result['candidates']]
                    for scene, result in execution['results'].items()},
                stock_available=available['stock'], image_available=available['image'], video_available=available['video'],
                image_cost_vnd=Decimal(binding['image_cost_vnd']) if binding['image_cost_vnd'] is not None else None,
                video_cost_vnd=Decimal(binding['video_cost_vnd']) if binding['video_cost_vnd'] is not None else None,
                supporting_assets=[AssetRead.model_validate(asset) for asset in inputs['supporting_assets']])
            projected = sum((item.estimated_cost_vnd for item in items if item.strategy in {'ai_image', 'ai_video'}), Decimal('0'))
            await self.repository.save_plan_items(media_plan_id=media_plan_id, items=items,
                projected_ai_cost_vnd=projected, needs_approval=any(item.needs_approval for item in items)
                or projected > plan.max_ai_cost_vnd, expected_stock_claim_id=claim_id, stock_observed_at=self._stock_clock())
        except Exception as error:
            code = str(error) if isinstance(error, ValueError) and str(error).startswith('STOCK_PLANNER_') else \
                error.code if isinstance(error, StockProviderFailure) else 'STOCK_PLANNER_FAILED'
            await stock_planner.fail(self.repository, media_plan_id, claim_id, code, stamp=self._stock_clock())
        return await self.repository.get_plan(media_plan_id)

    async def _meter_stock_search(self, plan, request, claim_id, binding_sha256, calls, status, code=None):
        await self.platform.record_provider_operation(workspace_id=plan.workspace_id,
            project_id=plan.project_id, job_id=None, provider_key=self.providers.stock.key, capability='stock_media',
            operation='stock-planner:'+plan.media_plan_id+':'+request['scene_id']+':'+claim_id,
            model=self.providers.stock.cache_binding_sha256, units=Decimal(calls), unit_name='wire_search',
            estimated_cost=Decimal('0'), actual_cost=None, max_cost_vnd=plan.max_ai_cost_vnd, status=status,
            metadata={'fixture': self.providers.stock.cache_mode == 'fixture', 'external_call': True,
                'paid': False, 'real_provider_tested': False, 'binding_sha256': binding_sha256, 'error_code': code})

    async def recover_due_stock_plans(self, *, limit=25):
        if not isinstance(self.providers.stock, OfficialStockProvider) or self.providers.stock.wire_guard is None:
            return 0
        identifiers = await stock_planner.due(self.repository, self._stock_clock(), limit)
        for identity in identifiers:
            await self.process_stock_plan(identity)
        return len(identifiers)

    async def stock_search_history(self, media_plan_id):
        return await stock_planner.history(self.repository, media_plan_id)

    async def retry_stock_search(self, media_plan_id, payload):
        plan = await self.repository.get_plan(media_plan_id)
        if plan is None:
            raise KeyError(media_plan_id)
        value = stock_planner.state(plan.provenance)
        if value is None or plan.version != payload.expected_version or value['binding_sha256'] != payload.binding_sha256:
            raise stock_planner.StockPlannerConflict('STOCK_PLANNER_REVIEW_STALE')
        return await self.process_stock_plan(media_plan_id, expected_version=payload.expected_version,
            binding_sha256=payload.binding_sha256)

    async def cancel_stock_search(self, media_plan_id, payload):
        await stock_planner.cancel(self.repository, media_plan_id, payload.expected_version, payload.binding_sha256)
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
        provider_safety: ProviderSafetyController | None = None,
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
        self.provider_safety = provider_safety or ProviderSafetyController.fail_closed()

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
        if capability == 'stock_media':
            if not selected_candidate_id and item.candidates:
                selected_candidate_id = item.candidates[0].candidate_id
            if not selected_candidate_id or selected_candidate_id not in {
                candidate.candidate_id for candidate in item.candidates
            }:
                raise ValueError("selected stock candidate is not part of the media plan item")
        stock_selected=next((candidate.model_dump(mode='json') for candidate in item.candidates
            if candidate.candidate_id==selected_candidate_id),None) if capability=='stock_media' else None
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
                "fixture": not external and capability != 'internal_media',
                "provider_configured": (self.providers.stock.configured if capability == 'stock_media' else
                    self.providers.image.configured if capability == 'image_generation' else
                    self.providers.video.configured if capability == 'video_generation' else True),
                "request": request_payload,
                "source_media_mutated": False,
                "publish_requested": False,
                **({'stock_selected_candidate':stock_selected,'stock_selected_candidate_sha256':stock_digest(stock_selected)}
                    if stock_selected is not None else {}),
            },
        )
        if created and job.status == "queued":
            await self.queue.rpush(MEDIA_RESOLUTION_QUEUE_KEY, job.resolution_job_id)
        return job

    async def process(self, resolution_job_id: str) -> MediaResolutionJobRead:
        job,plan,item=await self.repository.get_resolution_context(resolution_job_id)
        from .broll_internal_resolution_core import has_marker
        if has_marker(job):
            from .broll_internal_resolution_worker import process
            return await process(self, resolution_job_id)
        adapter=self.providers.stock
        managed=job.capability=='stock_media' and not job.paid and isinstance(adapter,OfficialStockProvider) and adapter.wire_guard is not None
        if not managed or job.status in {'succeeded','failed','cancelled','needs_approval'}:
            return await self._process_once(resolution_job_id)
        guard=adapter.wire_guard;stamp=float(guard.clock())
        claim=await stock_wait.claim(self.repository,resolution_job_id,stamp)
        if not claim.allowed:return await self.repository.get_resolution_job(resolution_job_id)
        with stock_request_scope(plan.workspace_id),stock_wire_operation(workspace_id=plan.workspace_id,
                project_id=plan.project_id,source_ref='media-resolution:'+resolution_job_id+':stock:'+str(claim.cycle),
                budget_sha256=stock_digest({'max_ai_cost_vnd':str(plan.max_ai_cost_vnd),'paid':False})) as operation:
            try:
                selected=self._stock_candidate(job,item)
                metadata=await adapter.cached_metadata(selected.provider_asset_id)
                async with guard.prepare_download(adapter,plan.workspace_id,metadata):
                    await self._process_once(resolution_job_id,stock_cycle=claim.cycle,stock_claim_id=claim.claim_id)
            except StockWireDeferred as deferred:
                await stock_wait.defer(self.repository,resolution_job_id,claim.claim_id,code=deferred.code,
                    next_at=deferred.next_at,wire_attempts=operation.wire_attempts,stamp=float(guard.clock()))
            except StockProviderFailure as error:
                if error.retryable:
                    now=float(guard.clock())
                    await stock_wait.defer(self.repository,resolution_job_id,claim.claim_id,code=error.code,
                        next_at=now+max(5,error.retry_after_seconds or 0),wire_attempts=operation.wire_attempts,stamp=now)
                else:
                    await self.repository.mark_resolution_failed(resolution_job_id,error_code=error.code,reason=error.code,
                        expected_stock_claim_id=claim.claim_id)
            except Exception:
                await self.repository.mark_resolution_failed(resolution_job_id,error_code='STOCK_PRE_DISPATCH_FAILED',
                    reason='Stock source/configuration could not be verified; no inferred approval.',
                    expected_stock_claim_id=claim.claim_id)
            finally:
                await stock_wait.release_claim(self.repository,resolution_job_id,claim.claim_id)
        return await self.repository.get_resolution_job(resolution_job_id)

    def _stock_candidate(self,job,item):
        evidence=getattr(job,'provenance',{}).get('stock_selected_candidate')
        if evidence is not None:
            if stock_digest(evidence)!=job.provenance.get('stock_selected_candidate_sha256'):
                raise ValueError('STOCK_SELECTED_CANDIDATE_CHANGED')
            selected=StockMediaCandidateRead.model_validate(evidence)
        else:
            selected=next((value for value in item.candidates if value.candidate_id==job.selected_candidate_id),None)
        if selected is None or selected.candidate_id!=job.selected_candidate_id or selected.provider!=self.providers.stock.key:
            raise ValueError('STOCK_SELECTED_CANDIDATE_CHANGED')
        binding=selected.provenance.get('cache_binding_sha256')
        if binding is not None and binding!=getattr(self.providers.stock,'cache_binding_sha256',binding):
            raise ValueError('STOCK_SELECTED_PROVIDER_CONFIGURATION_CHANGED')
        return selected

    async def _process_once(self, resolution_job_id: str, *, stock_cycle=None,stock_claim_id=None,
                            reviewed_internal_claim_id=None) -> MediaResolutionJobRead:
        job, plan, item = await self.repository.get_resolution_context(resolution_job_id)
        if job.status in {"succeeded", "failed", "cancelled", "needs_approval"}:
            return job
        if not await self.repository.mark_resolution_running(resolution_job_id, expected_stock_claim_id=stock_claim_id,
                expected_reviewed_internal_claim_id=reviewed_internal_claim_id):
            return await self.repository.get_resolution_job(resolution_job_id)
        staging_path: Path | None = None
        artifact_evidence = None
        try:
            if job.capability != 'internal_media':
                self._ensure_provider_configured(item)
            provider_context = ProviderCallContext(
                operation_key=f"media-resolution:{resolution_job_id}"+(f':stock:{stock_cycle}' if stock_cycle is not None else ''),
                workspace_id=plan.workspace_id,
                project_id=plan.project_id,
                job_id=resolution_job_id,
                provider_key=job.provider_key,
                capability=job.capability,
                operation=job.operation,
                external_call=job.external_call,
                paid=job.paid,
                estimated_cost_vnd=job.estimated_cost_vnd,
                # G-01 and G-03 are pending. No credential alias or full RightsRecord is inferred
                # from environment variables, provider configuration or a downloadable asset.
                credential_alias=None,
                rights_required=job.external_call,
            )
            execution = await self.provider_safety.execute(
                provider_context,
                lambda: self._materialize(job, plan, item, expected_stock_claim_id=stock_claim_id),
            )
            materialized, existing_asset = execution.value
            if materialized.external_call and not self.allow_external_execution:
                raise RuntimeError("external media execution is disabled in V2-06")
            if materialized.paid and not self.allow_paid_execution:
                raise RuntimeError("paid media execution is disabled in V2-06")
            if (materialized.estimated_cost_vnd is None or materialized.estimated_cost_vnd > plan.max_ai_cost_vnd) and item.strategy in {
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
                artifact_evidence = verify_provider_artifact(
                    operation_key=provider_context.operation_key,
                    provider_key=job.provider_key,
                    capability=job.capability,
                    request_payload=job.provenance.get("request", {}),
                    payload=materialized.payload,
                    content_type=materialized.content_type,
                    provider_job_id=materialized.provider_job_id,
                    source_reference=materialized.source_reference,
                    real_provider_tested=materialized.real_provider_tested,
                )
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
                artifact_evidence = verify_provider_artifact_storage(
                    artifact_evidence,
                    checksum_sha256=stored.checksum_sha256,
                    size_bytes=stored.size_bytes,
                    content_type=stored.content_type,
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
                            "fixture": not materialized.external_call or materialized.generation_provenance.get('fixture') is True,
                            "provider_artifact_evidence": artifact_evidence.model_dump(mode="json"),
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
                    "fixture": not materialized.external_call or materialized.generation_provenance.get('fixture') is True,
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
                    "provider_safety_receipt": execution.receipt.model_dump(mode="json"),
                    "provider_artifact_evidence_id": (
                        artifact_evidence.evidence_id if artifact_evidence else None
                    ),
                    "provider_artifact_storage_verified": bool(
                        artifact_evidence and artifact_evidence.storage_receipt_verified
                    ),
                    "asset_checksum_sha256":asset.checksum_sha256,
                    "full_rights_record_required_for_production": True,
                },
                expected_stock_claim_id=stock_claim_id,
                expected_reviewed_internal_claim_id=reviewed_internal_claim_id,
            )
        except MediaProviderNotConfigured as exc:
            await self.repository.mark_resolution_failed(
                resolution_job_id,
                error_code="PROVIDER_NOT_CONFIGURED",
                reason=str(exc),
                expected_stock_claim_id=stock_claim_id,
                expected_reviewed_internal_claim_id=reviewed_internal_claim_id,
            )
        except ProviderSafetyBlocked as exc:
            if stock_cycle is not None and isinstance(exc.__cause__,StockProviderFailure) and exc.__cause__.retryable:
                raise exc.__cause__
            if stock_cycle is not None and isinstance(exc.__cause__,StockWireDeferred):raise exc.__cause__
            await self.repository.mark_resolution_failed(
                resolution_job_id,
                error_code=exc.code,
                reason=str(exc),
                expected_stock_claim_id=stock_claim_id,
                expected_reviewed_internal_claim_id=reviewed_internal_claim_id,
            )
        except Exception as exc:
            if stock_cycle is not None and isinstance(exc,(StockWireDeferred,StockProviderFailure)):raise
            await self.repository.mark_resolution_failed(
                resolution_job_id,
                error_code="MEDIA_RESOLUTION_FAILED",
                reason=str(exc),
                expected_stock_claim_id=stock_claim_id,
                expected_reviewed_internal_claim_id=reviewed_internal_claim_id,
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
        adapter=self.providers.stock
        now=float(adapter.wire_guard.clock()) if isinstance(adapter,OfficialStockProvider) and adapter.wire_guard is not None else time.time()
        identifiers = await self.repository.list_incomplete_resolution_job_ids(now=now)
        count = 0
        for identifier in identifiers:
            from .broll_internal_resolution_core import has_marker
            if has_marker(await self.repository.get_resolution_job(identifier)):
                # Reviewed handoff is explicit authorized POST-only. Neither
                # startup recovery nor a read can resume a private attempt.
                continue
            await self.queue.rpush(MEDIA_RESOLUTION_QUEUE_KEY, identifier)
            count += 1
        return count

    async def recover_due_stock(self) -> int:
        """Requeue elapsed read-only stock waits without touching processing jobs."""
        adapter = self.providers.stock
        if not isinstance(adapter, OfficialStockProvider) or adapter.wire_guard is None:
            return 0
        identifiers = await self.repository.list_due_stock_resolution_job_ids(
            now=float(adapter.wire_guard.clock()))
        # The script makes pending-list de-duplication atomic. SQL claim fencing
        # remains the authority if a worker already popped this identifier.
        script = "redis.call('LREM', KEYS[1], 0, ARGV[1]); return redis.call('RPUSH', KEYS[1], ARGV[1])"
        evaluate = getattr(self.queue, 'eval', None)
        if not callable(evaluate):
            if identifiers:
                raise RuntimeError('STOCK_RECOVERY_ATOMIC_QUEUE_REQUIRED')
            return 0
        for identifier in identifiers:
            await evaluate(script, 1, MEDIA_RESOLUTION_QUEUE_KEY, identifier)
        return len(identifiers)

    async def _resolution_contract(self, plan, item, payload):
        aspect = platform_aspect_ratio(plan.configuration.platform)
        seed = int(hashlib.sha256(item.media_plan_item_id.encode()).hexdigest()[:8], 16) % 2_147_483_648
        if item.strategy == "user_asset" or payload.asset_id:
            if payload.candidate_id:
                raise ValueError('registered asset reuse does not accept a stock candidate')
            selected_asset_id = payload.asset_id or item.source_asset_id
            if plan.configuration.purpose == 'supporting_broll':
                selected = next((candidate for candidate in item.provenance.get('supporting_candidates',[])
                    if candidate['asset_id']==selected_asset_id),None)
                if selected is None:
                    raise ValueError('select a registered supporting asset from this plan')
                source = await self.auto_edit_repository.get_asset(selected_asset_id)
                if source is None or source.project_id != plan.project_id or source.workspace_id != plan.workspace_id:
                    raise KeyError(selected_asset_id)
                if source.checksum_sha256 != selected['checksum_sha256']:
                    raise ValueError('selected supporting asset checksum is stale')
            elif payload.asset_id:
                raise ValueError('asset picker requires a supporting B-roll plan')
            return (
                "internal-media",
                "internal_media",
                "reuse-user-asset",
                {"source_asset_id": selected_asset_id,
                    **({'checksum_sha256':selected['checksum_sha256']} if plan.configuration.purpose=='supporting_broll' else {})},
                Decimal("0"),
                False,
                False,
                False,
            )
        if item.strategy in {"stock_image", "stock_video"}:
            if payload.asset_id:
                raise ValueError('select a stock candidate for the stock strategy')
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
            if payload.asset_id or payload.candidate_id:
                raise ValueError('generation does not accept an asset/candidate override')
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
        if payload.asset_id or payload.candidate_id:
            raise ValueError('generation does not accept an asset/candidate override')
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

    async def _materialize(self, job, plan, item, *, expected_stock_claim_id=None) -> tuple[ProviderMaterializedMedia, AssetRead | None]:
        if expected_stock_claim_id is not None:
            current = await self.repository.get_resolution_job(job.resolution_job_id)
            if current is None or current.status != 'running' or current.provenance.get(stock_wait.KEY, {}).get('claim_id') != expected_stock_claim_id:
                raise RuntimeError('STOCK_RESOLUTION_CLAIM_LOST_BEFORE_WIRE')
        if job.capability != 'internal_media':
            self._ensure_provider_configured(item)
        if job.external_call and not self.allow_external_execution:
            raise RuntimeError("external media execution is disabled in V2-06")
        if job.paid and not self.allow_paid_execution:
            raise RuntimeError("paid media execution is disabled in V2-06")
        if job.capability == 'internal_media':
            selected_id = job.provenance.get('request',{}).get('source_asset_id') or item.source_asset_id
            if not selected_id:
                raise RuntimeError("user-asset plan item is missing its source asset")
            asset = await self.auto_edit_repository.get_asset(selected_id)
            if asset is None or asset.project_id != plan.project_id or asset.workspace_id != plan.workspace_id:
                raise KeyError(selected_id)
            expected = job.provenance.get('request',{}).get('checksum_sha256')
            if expected and expected != asset.checksum_sha256:
                raise ValueError('selected supporting asset checksum changed before resolution')
            rights = str(asset.provenance.get("rights_status", "unknown"))
            license_name = str(asset.provenance.get("license", "unknown"))
            if rights == 'restricted':
                raise ValueError('restricted supporting media cannot be reused')
            measured = asset.provenance.get('media_metadata') or {}
            return (
                ProviderMaterializedMedia(
                    filename=asset.filename,
                    content_type=asset.content_type,
                    payload=b"",
                    provider_job_id=None,
                    source_type="internal_library" if asset.provenance.get('source_type')=='internal_library' else "user_upload",
                    rights_status=rights,
                    license=license_name,
                    license_url=asset.provenance.get("license_url"),
                    provider_asset_id=asset.asset_id,
                    creator=None,
                    source_reference=f"asset://{asset.asset_id}",
                    attribution_requirement=None,
                    width=measured.get("width"),
                    height=measured.get("height"),
                    duration_seconds=measured.get("duration_seconds"),
                    orientation="unknown",
                    production_eligible=rights in {"owned", "licensed", "verified"} and not asset.provenance.get('fixture'),
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
            selected = self._stock_candidate(job,item)
            if selected is None:
                raise ValueError("selected stock candidate is missing")
            if selected.provider != self.providers.stock.key:
                raise ValueError("selected stock candidate belongs to a different provider")
            # Non-external fixtures are fully materializable from the candidate
            # contract persisted with the media plan.  Do not depend on an
            # in-process search cache: API planning and worker resolution run in
            # separate containers and both must survive restarts.  External
            # adapters may still refresh provider metadata or signed URLs.
            with stock_request_scope(plan.workspace_id), (nullcontext() if CURRENT_OPERATION.get() is not None else stock_wire_operation(workspace_id=plan.workspace_id,
                project_id=plan.project_id,source_ref='media-resolution:'+getattr(job,'resolution_job_id','direct-materialization'),
                budget_sha256=stock_digest({'max_ai_cost_vnd':str(plan.max_ai_cost_vnd),'paid':False}))):
                candidate = (
                    await self.providers.stock.get_asset(selected.provider_asset_id)
                    if self.providers.stock.external
                    else selected
                )
                return await self.providers.stock.download_asset(candidate), None
        if item.strategy in {"ai_image", "motion_graphic"}:
            request = ImageGenerationInput.model_validate(job.provenance.get("request") or {})
            with media_generation_scope(workspace_id=plan.workspace_id, project_id=plan.project_id, job_id=job.resolution_job_id):
                return await self.providers.image.generate(request), None
        request = VideoGenerationInput.model_validate(job.provenance.get("request") or {})
        with media_generation_scope(workspace_id=plan.workspace_id, project_id=plan.project_id, job_id=job.resolution_job_id):
            return await self.providers.video.generate(request), None

    def _ensure_provider_configured(self, item) -> None:
        if item.strategy in {"stock_image", "stock_video"} and not self.providers.stock.configured:
            raise MediaProviderNotConfigured("Stock media provider is not configured")
        if item.strategy in {"ai_image", "motion_graphic"} and not self.providers.image.configured:
            raise MediaProviderNotConfigured("Image generation provider is not configured")
        if item.strategy == "ai_video" and not self.providers.video.configured:
            raise MediaProviderNotConfigured("Video generation provider is not configured")


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
    if "fixture" in content_type or content_type.endswith("+json"):
        return "media_contract_fixture"
    if content_type.startswith("image/"):
        return "stock_image" if strategy == "stock_image" else "generated_image"
    return "stock_video" if strategy == "stock_video" else "generated_video"
