from __future__ import annotations

import json
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from redis.asyncio import Redis

from .bridge_auth import ServiceAuthVerifier, SigningKeyring
from .bridge_repository import BridgeRepository
from .bridge_routes import router as bridge_router
from .bridge_service import AgentHubBridgeService
from .analytics_providers import AnalyticsProviderRegistry
from .analytics_repository import AnalyticsRepository
from .analytics_routes import router as analytics_router
from .analytics_service import AnalyticsService
from .auto_edit_providers import (
    ContractOnlyTranscriptionProvider,
    DeterministicMediaSignalProvider,
    DeterministicTranscriptionProvider,
    FFmpegMediaSignalProvider,
    FFprobeMediaProbe,
)
from .auto_edit_repository import AutoEditRepository
from .auto_edit_routes import router as auto_edit_router
from .auto_edit_service import AutoEditAnalysisService, UploadService
from .artifacts import (
    ArtifactAccessError,
    recorded_artifact,
    recorded_artifact_path,
    resolve_recorded_artifact,
)
from .config import settings
from .db import create_engine, create_session_factory, verify_database
from .media_intelligence_repository import MediaIntelligenceRepository
from .media_intelligence_routes import router as media_intelligence_router
from .media_intelligence_service import (
    MediaPlanningService,
    MediaResolutionService,
    create_media_provider_bundle,
)
from .media_security import create_media_malware_scanner
from .human_auth import (
    HumanAuthVerifier,
    HumanRateLimiter,
    authorize_human_request,
    authorize_project,
    authorize_workspace,
    principal_from,
)
from .models import JobCreateResponse, JobRecord, VideoJobCreate
from .object_storage import create_object_storage, sha256_file
from .operations_observability import OperationsObservabilityService
from .operations_routes import router as operations_router
from .platform_models import WorkspaceCreate
from .platform_routes import router as platform_router
from .publishing_logic import PublishingCapabilityRegistry
from .publishing_providers import PublishingProviderRegistry
from .publishing_repository import PublishingRepository
from .publishing_routes import router as publishing_router
from .publishing_service import PublishingService
from .production_repository import ProductionRepository
from .production_routes import router as production_router
from .production_service import ProductionPackageService
from .provider_safety import (
    normalize_provider_definitions,
    provider_safety_policy_from_settings,
)
from .provider_safety_durable import DurableProviderSafetyController
from .provider_safety_repository import ProviderSafetyRepository
from .provider_safety_routes import router as provider_safety_router
from .repositories import PlatformRepository, PostgresJobStore
from .trend_providers import create_trend_provider_registry
from .trend_repository import TrendRepository
from .trend_routes import router as trend_router
from .trend_service import TrendIntelligenceService
from .timeline_repository import TimelineRepository
from .timeline_routes import router as timeline_router
from .timeline_service import (
    FFmpegProxyRenderer,
    PreviewService,
    TimelineContractValidator,
    TimelineService,
)
from .vision_providers import ContractOnlyVisionProvider, DeterministicVisionProvider
from .vision_repository import VisionRepository
from .vision_routes import router as vision_router
from .vision_service import VisionAnalysisService


logger = logging.getLogger("uvicorn.error")


def new_job_id() -> str:
    millis = int(time.time() * 1000)
    return f"vid_{millis:013d}_{uuid.uuid4().hex[:10]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.job_storage_root.mkdir(parents=True, exist_ok=True)
    settings.asset_storage_root.mkdir(parents=True, exist_ok=True)
    settings.upload_staging_root.mkdir(parents=True, exist_ok=True)
    settings.analysis_staging_root.mkdir(parents=True, exist_ok=True)
    settings.vision_staging_root.mkdir(parents=True, exist_ok=True)
    settings.media_staging_root.mkdir(parents=True, exist_ok=True)
    settings.preview_staging_root.mkdir(parents=True, exist_ok=True)
    settings.preview_download_root.mkdir(parents=True, exist_ok=True)
    settings.production_render_staging_root.mkdir(parents=True, exist_ok=True)
    settings.production_render_download_root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    human_auth_verifier = HumanAuthVerifier.from_file(
        settings.human_auth_keys_file,
        max_token_ttl_seconds=settings.human_auth_max_token_ttl_seconds,
    )
    object_storage = create_object_storage(settings)
    platform = PlatformRepository(session_factory)
    trend_repository = TrendRepository(session_factory)
    auto_edit_repository = AutoEditRepository(session_factory)
    vision_repository = VisionRepository(session_factory)
    media_intelligence_repository = MediaIntelligenceRepository(session_factory)
    timeline_repository = TimelineRepository(session_factory)
    production_repository = ProductionRepository(session_factory)
    publishing_repository = PublishingRepository(session_factory)
    analytics_repository = AnalyticsRepository(session_factory)
    provider_safety_repository = ProviderSafetyRepository(session_factory)
    trend_providers = create_trend_provider_registry(
        settings.trend_fixture_path,
        fixture_enabled=settings.trend_fixture_enabled,
    )
    await verify_database(session_factory)
    await provider_safety_repository.ensure_state()
    await object_storage.ensure_ready()
    default_workspace = await platform.ensure_workspace(
        WorkspaceCreate(
            slug=settings.default_workspace_slug,
            name=settings.default_workspace_name,
            owner_ref=settings.default_workspace_owner_ref,
            provenance={"source": "bootstrap-config"},
        )
    )
    provider_definitions = normalize_provider_definitions(_provider_definitions())
    await platform.seed_providers(provider_definitions)
    await trend_repository.seed_sources(trend_providers.definitions())
    app.state.database_engine = engine
    app.state.database_session_factory = session_factory
    app.state.redis = redis
    app.state.human_api_enabled = settings.human_api_enabled
    app.state.human_write_enabled = settings.human_write_enabled
    app.state.human_auth_verifier = human_auth_verifier
    app.state.human_rate_limiter = HumanRateLimiter(
        redis,
        requests_per_minute=settings.human_rate_limit_per_minute,
    )
    app.state.object_storage = object_storage
    app.state.platform_repository = platform
    app.state.provider_safety_controller = DurableProviderSafetyController(
        provider_safety_policy_from_settings(settings),
        repository=provider_safety_repository,
        provider_definitions=provider_definitions,
        operation_lease_seconds=settings.provider_operation_lease_seconds,
        operation_retention_days=settings.provider_operation_retention_days,
    )
    app.state.provider_safety_recovered_operations = len(
        await app.state.provider_safety_controller.recover_stale_operations()
    )
    app.state.operations_observability = OperationsObservabilityService(
        session_factory=session_factory,
        redis=redis,
        object_storage=object_storage,
        provider_safety=app.state.provider_safety_controller,
        job_storage_root=settings.job_storage_root,
        object_storage_provider=settings.object_storage_provider,
        queue_backlog_warning=settings.operations_queue_backlog_warning,
        failed_jobs_warning=settings.operations_failed_jobs_warning,
        disk_warning_percent=settings.operations_disk_warning_percent,
        disk_critical_percent=settings.operations_disk_critical_percent,
        provider_ledger_retention_days=settings.provider_operation_retention_days,
        evidence_retention_days=settings.operations_evidence_retention_days,
        operations_log_retention_days=settings.operations_log_retention_days,
        retention_cleanup_enabled=settings.provider_retention_cleanup_enabled,
    )
    app.state.trend_repository = trend_repository
    app.state.auto_edit_repository = auto_edit_repository
    app.state.vision_repository = vision_repository
    app.state.media_intelligence_repository = media_intelligence_repository
    app.state.timeline_repository = timeline_repository
    app.state.production_repository = production_repository
    app.state.publishing_repository = publishing_repository
    app.state.analytics_repository = analytics_repository
    app.state.default_workspace_id = default_workspace.workspace_id
    app.state.trend_provider_registry = trend_providers
    app.state.trend_intelligence_service = TrendIntelligenceService(
        trend_repository,
        trend_providers,
        platform,
    )
    app.state.job_store = PostgresJobStore(
        session_factory,
        redis,
        platform=platform,
        object_storage=object_storage,
    )
    media_probe = FFprobeMediaProbe(settings.ffprobe_path)
    transcription_provider = (
        DeterministicTranscriptionProvider()
        if settings.transcription_provider == "fixture"
        else ContractOnlyTranscriptionProvider()
    )
    signal_provider = (
        DeterministicMediaSignalProvider()
        if settings.auto_edit_signal_provider == "fixture"
        else FFmpegMediaSignalProvider(settings.ffmpeg_path)
    )
    app.state.upload_service = UploadService(
        repository=auto_edit_repository,
        platform=platform,
        object_storage=object_storage,
        media_probe=media_probe,
        malware_scanner=create_media_malware_scanner(settings),
        staging_root=settings.upload_staging_root,
        default_part_size_bytes=settings.upload_default_part_size_bytes,
        max_part_size_bytes=settings.upload_max_part_size_bytes,
        max_upload_size_bytes=settings.upload_max_size_bytes,
    )
    app.state.auto_edit_analysis_service = AutoEditAnalysisService(
        repository=auto_edit_repository,
        platform=platform,
        object_storage=object_storage,
        transcription_provider=transcription_provider,
        signal_provider=signal_provider,
        staging_root=settings.analysis_staging_root,
        provider_safety=app.state.provider_safety_controller,
    )
    vision_provider = (
        DeterministicVisionProvider()
        if settings.vision_provider == "fixture"
        else ContractOnlyVisionProvider()
    )
    app.state.vision_analysis_service = VisionAnalysisService(
        repository=vision_repository,
        auto_edit_repository=auto_edit_repository,
        platform=platform,
        object_storage=object_storage,
        provider=vision_provider,
        staging_root=settings.vision_staging_root,
        provider_safety=app.state.provider_safety_controller,
    )
    media_providers = create_media_provider_bundle(settings)
    app.state.media_provider_bundle = media_providers
    app.state.media_planning_service = MediaPlanningService(
        repository=media_intelligence_repository,
        auto_edit_repository=auto_edit_repository,
        vision_repository=vision_repository,
        platform=platform,
        providers=media_providers,
        allow_external_execution=settings.media_external_execution_enabled,
        allow_paid_execution=settings.media_paid_execution_enabled,
    )
    app.state.media_resolution_service = MediaResolutionService(
        repository=media_intelligence_repository,
        platform=platform,
        auto_edit_repository=auto_edit_repository,
        object_storage=object_storage,
        providers=media_providers,
        queue=redis,
        staging_root=settings.media_staging_root,
        allow_external_execution=settings.media_external_execution_enabled,
        allow_paid_execution=settings.media_paid_execution_enabled,
        provider_safety=app.state.provider_safety_controller,
    )
    app.state.timeline_service = TimelineService(
        repository=timeline_repository,
        platform=platform,
        auto_edit_repository=auto_edit_repository,
        media_repository=media_intelligence_repository,
        validator=TimelineContractValidator(settings.contracts_root / "timeline.schema.json"),
    )
    app.state.preview_service = PreviewService(
        repository=timeline_repository,
        platform=platform,
        auto_edit_repository=auto_edit_repository,
        object_storage=object_storage,
        queue=redis,
        renderer=FFmpegProxyRenderer(settings.ffmpeg_path),
        staging_root=settings.preview_staging_root,
    )
    app.state.preview_download_root = settings.preview_download_root
    app.state.production_package_service = ProductionPackageService(
        repository=production_repository,
        timeline_repository=timeline_repository,
        asset_repository=auto_edit_repository,
        queue=redis,
        settings=settings,
    )
    publishing_capabilities = PublishingCapabilityRegistry(
        settings.contracts_root / "publishing-capabilities.json"
    )
    publishing_providers = PublishingProviderRegistry(settings)
    app.state.publishing_service = PublishingService(
        repository=publishing_repository,
        production_repository=production_repository,
        asset_repository=auto_edit_repository,
        capabilities=publishing_capabilities,
        providers=publishing_providers,
        settings=settings,
    )
    analytics_providers = AnalyticsProviderRegistry(settings)
    app.state.analytics_provider_registry = analytics_providers
    app.state.analytics_service = AnalyticsService(
        repository=analytics_repository,
        publishing_repository=publishing_repository,
        platform_repository=platform,
        providers=analytics_providers,
        queue=redis,
        settings=settings,
    )
    app.state.bridge_auth_verifier = None
    app.state.agent_hub_bridge_service = None
    if settings.agent_hub_bridge_enabled:
        app.state.bridge_auth_verifier = ServiceAuthVerifier.from_file(
            settings.agent_hub_service_keys_file,
            redis,
            max_clock_skew_seconds=settings.service_auth_max_clock_skew_seconds,
            replay_ttl_seconds=settings.service_auth_replay_ttl_seconds,
        )
        app.state.agent_hub_bridge_service = AgentHubBridgeService(
            repository=BridgeRepository(session_factory),
            platform_repository=platform,
            publishing_repository=publishing_repository,
            analytics_repository=analytics_repository,
            queue=redis,
            default_workspace_id=default_workspace.workspace_id,
            webhook_destination_ref=settings.agent_hub_webhook_destination_ref,
            webhook_provider_mode=settings.agent_hub_webhook_mode,
            webhook_max_attempts=settings.agent_hub_webhook_max_attempts,
            production_deployed=settings.app_env.lower() == "production",
        )
        if settings.agent_hub_webhook_mode != "disabled":
            SigningKeyring.from_file(settings.agent_hub_webhook_signing_keys_file)
    app.state.production_render_download_root = settings.production_render_download_root
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


_production_mode = settings.app_env.lower() == "production"
app = FastAPI(
    title="NPD Video Factory V2 API",
    version="0.12.0",
    lifespan=lifespan,
    docs_url=None if _production_mode else "/docs",
    redoc_url=None if _production_mode else "/redoc",
    openapi_url=None if _production_mode else "/openapi.json",
)
_human_route_dependencies = [Depends(authorize_human_request)]
app.include_router(platform_router, dependencies=_human_route_dependencies)
app.include_router(trend_router, dependencies=_human_route_dependencies)
app.include_router(auto_edit_router, dependencies=_human_route_dependencies)
app.include_router(vision_router, dependencies=_human_route_dependencies)
app.include_router(media_intelligence_router, dependencies=_human_route_dependencies)
app.include_router(timeline_router, dependencies=_human_route_dependencies)
app.include_router(production_router, dependencies=_human_route_dependencies)
app.include_router(publishing_router, dependencies=_human_route_dependencies)
app.include_router(analytics_router, dependencies=_human_route_dependencies)
app.include_router(provider_safety_router, dependencies=_human_route_dependencies)
app.include_router(operations_router, dependencies=_human_route_dependencies)
app.include_router(bridge_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    supplied_request_id = request.headers.get("X-Request-ID", "")
    request_id = (
        supplied_request_id
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied_request_id)
        else uuid.uuid4().hex
    )
    supplied_correlation_id = request.headers.get("X-Correlation-ID", "")
    correlation_id = (
        supplied_correlation_id
        if re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", supplied_correlation_id)
        else request_id
    )
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    started = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Correlation-ID"] = correlation_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else response.headers.get("Cache-Control", "no-cache")
    path_ids = {
        key: value
        for key, value in request.path_params.items()
        if key in {"workspace_id", "project_id", "job_id"}
        and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", str(value))
    }
    logger.info(
        json.dumps(
            {
                "event": "http_request_completed",
                "request_id": request_id,
                "correlation_id": correlation_id,
                "method": request.method,
                "route": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 3),
                **path_ids,
                "secret_free": True,
            },
            sort_keys=True,
        )
    )
    return response


def store_from(request: Request) -> PostgresJobStore:
    return request.app.state.job_store


def _provider_definitions() -> list[dict[str, object]]:
    # The durable provider registry describes the original video-job pipeline,
    # whose worker is still selected with TTS_PROVIDER. V2-08 has a separate,
    # fail-closed AUDIO_TTS_PROVIDER contract exposed by the production package.
    selected_tts = settings.tts_provider.lower()
    return [
        {
            "provider_key": "deterministic-content",
            "display_name": "Deterministic Content Fixture",
            "capability": "content",
            "adapter": "app.providers.DeterministicContentProvider",
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
            "metadata": {"paid": False, "ci_safe": True},
        },
        {
            "provider_key": "espeak",
            "display_name": "eSpeak Vietnamese Test Voice",
            "capability": "tts",
            "adapter": "app.providers.EspeakVietnameseTTSProvider",
            "routing_mode": "primary" if selected_tts == "espeak" else "disabled",
            "status": "healthy",
            "enabled": selected_tts == "espeak",
            "supports_dry_run": True,
            "metadata": {"paid": False, "ci_safe": True, "human_voice_accepted": False},
        },
        {
            "provider_key": "openai-tts",
            "display_name": "OpenAI Vietnamese TTS",
            "capability": "tts",
            "adapter": "app.providers.OpenAIVietnameseTTSProvider",
            "routing_mode": "primary" if selected_tts == "openai" else "disabled",
            "status": "degraded" if settings.openai_api_key else "not_configured",
            "enabled": selected_tts == "openai" and bool(settings.openai_api_key),
            "supports_dry_run": False,
            "config_ref": "env:OPENAI_API_KEY",
            "metadata": {"paid": True, "manual_acceptance_only": True},
        },
        {
            "provider_key": "remotion",
            "display_name": "Remotion Renderer",
            "capability": "rendering",
            "adapter": "renderer.service",
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
            "metadata": {"paid": False, "ci_safe": True},
        },
        {
            "provider_key": settings.object_storage_provider,
            "display_name": "S3-compatible Object Storage" if settings.object_storage_provider == "s3" else "Local Object Storage",
            "capability": "object_storage",
            "adapter": (
                "app.object_storage.S3ObjectStorageProvider"
                if settings.object_storage_provider == "s3"
                else "app.object_storage.LocalObjectStorageProvider"
            ),
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
            "config_ref": "env:OBJECT_STORAGE_*" if settings.object_storage_provider == "s3" else None,
            "metadata": {"production_supported": settings.object_storage_provider == "s3"},
        },
        {
            "provider_key": "fixture-transcription",
            "display_name": "Deterministic Vietnamese Transcript Fixture",
            "capability": "transcription",
            "adapter": "app.auto_edit_providers.DeterministicTranscriptionProvider",
            "routing_mode": "primary" if settings.transcription_provider == "fixture" else "disabled",
            "status": "healthy" if settings.transcription_provider == "fixture" else "not_configured",
            "enabled": settings.transcription_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:synthetic-transcript",
            "metadata": {"paid": False, "ci_safe": True, "fixture": True},
        },
        {
            "provider_key": "transcription-not-configured",
            "display_name": "Live Transcription Provider Contract",
            "capability": "transcription",
            "adapter": "app.auto_edit_providers.ContractOnlyTranscriptionProvider",
            "routing_mode": "disabled",
            "status": "not_configured",
            "enabled": False,
            "supports_dry_run": True,
            "config_ref": "env:TRANSCRIPTION_PROVIDER_*",
            "metadata": {"contract_only": True, "paid": None},
        },
        {
            "provider_key": "fixture-media-signals",
            "display_name": "Deterministic Media Signal Fixture",
            "capability": "media_analysis",
            "adapter": "app.auto_edit_providers.DeterministicMediaSignalProvider",
            "routing_mode": "primary" if settings.auto_edit_signal_provider == "fixture" else "disabled",
            "status": "healthy" if settings.auto_edit_signal_provider == "fixture" else "not_configured",
            "enabled": settings.auto_edit_signal_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:synthetic-media-signals",
            "metadata": {"paid": False, "ci_safe": True, "fixture": True},
        },
        {
            "provider_key": "ffmpeg-media-signals",
            "display_name": "FFmpeg Scene and Silence Signals",
            "capability": "media_analysis",
            "adapter": "app.auto_edit_providers.FFmpegMediaSignalProvider",
            "routing_mode": "primary" if settings.auto_edit_signal_provider == "ffmpeg" else "disabled",
            "status": "healthy" if settings.auto_edit_signal_provider == "ffmpeg" else "not_configured",
            "enabled": settings.auto_edit_signal_provider == "ffmpeg",
            "supports_dry_run": True,
            "config_ref": "env:FFMPEG_PATH",
            "metadata": {"paid": False, "production_supported": True, "fixture": False},
        },
        {
            "provider_key": "fixture-vision",
            "display_name": "Deterministic Structured Vision Fixture",
            "capability": "vision",
            "adapter": "app.vision_providers.DeterministicVisionProvider",
            "routing_mode": "primary" if settings.vision_provider == "fixture" else "disabled",
            "status": "healthy" if settings.vision_provider == "fixture" else "not_configured",
            "enabled": settings.vision_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:structured-vision-fixture",
            "metadata": {
                "paid": False,
                "ci_safe": True,
                "fixture": True,
                "real_provider_tested": False,
            },
        },
        {
            "provider_key": "vision-not-configured",
            "display_name": "Live Vision Provider Contract",
            "capability": "vision",
            "adapter": "app.vision_providers.ContractOnlyVisionProvider",
            "routing_mode": "disabled",
            "status": "not_configured",
            "enabled": False,
            "supports_dry_run": True,
            "config_ref": "env:VISION_PROVIDER_*",
            "metadata": {"contract_only": True, "paid": None, "real_provider_tested": False},
        },
        {
            "provider_key": "internal-media",
            "display_name": "Immutable User and Internal Media Resolver",
            "capability": "internal_media",
            "adapter": "app.media_intelligence_service.MediaResolutionService",
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
            "metadata": {
                "paid": False,
                "ci_safe": True,
                "source_media_mutation": False,
                "rights_evidence_required": True,
            },
        },
        {
            "provider_key": "fixture-stock",
            "display_name": "Deterministic Licensed Stock Fixture",
            "capability": "stock_media",
            "adapter": "app.media_intelligence_providers.DeterministicStockMediaProvider",
            "routing_mode": "primary" if settings.stock_media_provider == "fixture" else "disabled",
            "status": "healthy" if settings.stock_media_provider == "fixture" else "not_configured",
            "enabled": settings.stock_media_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:synthetic-stock-fixtures",
            "metadata": {
                "paid": False,
                "fixture": True,
                "ci_safe": True,
                "real_provider_tested": False,
                "social_media_downloaded": False,
                "production_eligible": False,
            },
        },
        {
            "provider_key": "stock-not-configured",
            "display_name": "Licensed Stock Provider Contract",
            "capability": "stock_media",
            "adapter": "app.media_intelligence_providers.ContractOnlyStockMediaProvider",
            "routing_mode": "disabled",
            "status": "not_configured",
            "enabled": False,
            "supports_dry_run": True,
            "config_ref": "env:STOCK_MEDIA_PROVIDER_*",
            "metadata": {"contract_only": True, "real_provider_tested": False},
        },
        {
            "provider_key": "fixture-image-generation",
            "display_name": "Deterministic Image Generation Fixture",
            "capability": "image_generation",
            "adapter": "app.media_intelligence_providers.DeterministicImageGenerationProvider",
            "routing_mode": "primary" if settings.image_generation_provider == "fixture" else "disabled",
            "status": "healthy" if settings.image_generation_provider == "fixture" else "not_configured",
            "enabled": settings.image_generation_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:synthetic-svg-generator",
            "metadata": {
                "paid": False,
                "fixture": True,
                "ci_safe": True,
                "real_provider_tested": False,
                "production_eligible": False,
            },
        },
        {
            "provider_key": "image-generation-not-configured",
            "display_name": "Remote Image Generation Provider Contract",
            "capability": "image_generation",
            "adapter": "app.media_intelligence_providers.ContractOnlyImageGenerationProvider",
            "routing_mode": "disabled",
            "status": "not_configured",
            "enabled": False,
            "supports_dry_run": True,
            "config_ref": "env:IMAGE_GENERATION_PROVIDER_*",
            "metadata": {"contract_only": True, "paid": True, "real_provider_tested": False},
        },
        {
            "provider_key": "fixture-video-generation",
            "display_name": "Deterministic Video Generation Contract Fixture",
            "capability": "video_generation",
            "adapter": "app.media_intelligence_providers.DeterministicVideoGenerationProvider",
            "routing_mode": "primary" if settings.video_generation_provider == "fixture" else "disabled",
            "status": "healthy" if settings.video_generation_provider == "fixture" else "not_configured",
            "enabled": settings.video_generation_provider == "fixture",
            "supports_dry_run": True,
            "config_ref": "built-in:synthetic-video-contract",
            "metadata": {
                "paid": False,
                "fixture": True,
                "ci_safe": True,
                "playable_video": False,
                "real_provider_tested": False,
                "production_eligible": False,
            },
        },
        {
            "provider_key": "video-generation-not-configured",
            "display_name": "Remote Video Generation Provider Contract",
            "capability": "video_generation",
            "adapter": "app.media_intelligence_providers.ContractOnlyVideoGenerationProvider",
            "routing_mode": "disabled",
            "status": "not_configured",
            "enabled": False,
            "supports_dry_run": True,
            "config_ref": "env:VIDEO_GENERATION_PROVIDER_*",
            "metadata": {"contract_only": True, "paid": True, "real_provider_tested": False},
        },
        *[
            {
                "provider_key": f"comfyui-{modality}",
                "display_name": f"ComfyUI {modality.title()} Generation Bridge",
                "capability": f"{modality}_generation",
                "adapter": "app.media_intelligence_providers.ComfyUIBridgeGenerationProvider",
                "routing_mode": "primary" if selected == "comfyui" else "disabled",
                "status": "degraded" if selected == "comfyui" else "not_configured",
                "enabled": selected == "comfyui" and settings.comfyui_execution_enabled,
                "supports_dry_run": True,
                "config_ref": "env:COMFYUI_BRIDGE_URL",
                "metadata": {
                    "paid": False,
                    "gpu": True,
                    "approved_workflows_only": True,
                    "real_provider_tested": False,
                },
            }
            for modality, selected in (
                ("image", settings.image_generation_provider),
                ("video", settings.video_generation_provider),
            )
        ],
        {
            "provider_key": "fixture-trends",
            "display_name": "Deterministic Trend Fixtures",
            "capability": "trend_source",
            "adapter": "app.trend_providers.FixtureTrendSourceProvider",
            "routing_mode": "primary" if settings.trend_fixture_enabled else "disabled",
            "status": "healthy" if settings.trend_fixture_enabled else "not_configured",
            "enabled": settings.trend_fixture_enabled,
            "supports_dry_run": True,
            "config_ref": "bundled:app/fixtures/trend-signals.json",
            "metadata": {
                "paid": False,
                "ci_safe": True,
                "fixture": True,
                "authorized_access": settings.trend_fixture_enabled,
                "creator_media_downloaded": False,
            },
        },
        *[
            {
                "provider_key": provider_key,
                "display_name": display_name,
                "capability": "trend_source",
                "adapter": "app.trend_providers.ContractOnlyTrendSourceProvider",
                "routing_mode": "disabled",
                "status": "not_configured",
                "enabled": False,
                "supports_dry_run": True,
                "config_ref": config_ref,
                "metadata": {
                    "contract_only": True,
                    "authorized_access": False,
                    "creator_media_downloaded": False,
                },
            }
            for provider_key, display_name, config_ref in (
                ("youtube-data-api", "YouTube Data API", "env:YOUTUBE_DATA_API_*"),
                ("tiktok-authorized-api", "TikTok Authorized Research API", "env:TIKTOK_RESEARCH_API_*"),
                ("google-trends-authorized", "Google Trends Authorized Provider", "env:GOOGLE_TRENDS_PROVIDER_*"),
                ("meta-content-library", "Meta Content Library API", "env:META_CONTENT_LIBRARY_*"),
                ("public-rss", "Public RSS/News Feeds", "file:TREND_RSS_ALLOWLIST_FILE"),
            )
        ],
        *_publishing_provider_definitions(),
        *_analytics_provider_definitions(),
    ]


def _publishing_provider_definitions() -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = [
        {
            "provider_key": "mock-publishing",
            "display_name": "Deterministic Publishing Dry Run",
            "capability": "publishing",
            "adapter": "app.publishing_providers.MockPublishingProvider",
            "routing_mode": "primary",
            "status": "healthy",
            "enabled": True,
            "supports_dry_run": True,
            "config_ref": "built-in:v2-09-dry-run",
            "metadata": {
                "official_api_only": True,
                "mock": True,
                "external_action": False,
                "ci_safe": True,
            },
        }
    ]
    credential_refs = {
        "youtube": settings.youtube_publishing_credential_ref,
        "tiktok": settings.tiktok_publishing_credential_ref,
        "instagram_reels": settings.instagram_publishing_credential_ref,
        "facebook": settings.facebook_publishing_credential_ref,
    }
    display_names = {
        "youtube": "YouTube Data API Publishing",
        "tiktok": "TikTok Content Posting API",
        "instagram_reels": "Instagram Graph API Reels Publishing",
        "facebook": "Facebook Graph API Publishing",
    }
    for platform, provider_key in PublishingProviderRegistry.PROVIDER_KEYS.items():
        configured = bool(credential_refs[platform])
        definitions.append(
            {
                "provider_key": provider_key,
                "display_name": display_names[platform],
                "capability": "publishing",
                "adapter": "app.publishing_providers.OfficialPublishingProvider",
                "routing_mode": "disabled",
                "status": "degraded" if configured else "not_configured",
                "enabled": False,
                "supports_dry_run": False,
                "config_ref": f"external-secret-ref:{platform}",
                "metadata": {
                    "platform": platform,
                    "official_api_only": True,
                    "contract_only": True,
                    "external_action": False,
                    "credential_reference_configured": configured,
                },
            }
        )
    return definitions


def _analytics_provider_definitions() -> list[dict[str, object]]:
    definitions: list[dict[str, object]] = [
        {
            "provider_key": "fixture-analytics-v1",
            "display_name": "Deterministic Analytics Fixture",
            "capability": "analytics",
            "adapter": "app.analytics_providers.DeterministicAnalyticsProvider",
            "routing_mode": "primary" if settings.analytics_fixture_enabled else "disabled",
            "status": "healthy" if settings.analytics_fixture_enabled else "not_configured",
            "enabled": settings.analytics_fixture_enabled,
            "supports_dry_run": True,
            "config_ref": "built-in:v2-10-analytics-fixture",
            "metadata": {
                "mock": True,
                "external_call": False,
                "historical_snapshots": True,
                "real_provider_tested": False,
                "production_deployed": False,
            },
        }
    ]
    credential_refs = {
        "youtube": settings.youtube_analytics_credential_ref,
        "tiktok": settings.tiktok_analytics_credential_ref,
        "instagram_reels": settings.instagram_analytics_credential_ref,
        "facebook": settings.facebook_analytics_credential_ref,
    }
    for platform, provider_key in AnalyticsProviderRegistry.OFFICIAL_KEYS.items():
        configured = bool(credential_refs[platform])
        definitions.append(
            {
                "provider_key": provider_key,
                "display_name": f"{platform.replace('_', ' ').title()} Analytics API",
                "capability": "analytics",
                "adapter": "app.analytics_providers.OfficialAnalyticsProvider",
                "routing_mode": "disabled",
                "status": "degraded" if configured else "not_configured",
                "enabled": False,
                "supports_dry_run": False,
                "config_ref": f"external-secret-ref:{platform}:analytics",
                "metadata": {
                    "platform": platform,
                    "contract_only": True,
                    "external_call": False,
                    "credential_reference_configured": configured,
                    "real_provider_tested": False,
                    "production_deployed": False,
                },
            }
        )
    return definitions


def not_found(message: str = "Job not found.") -> HTTPException:
    return HTTPException(status_code=404, detail={"error": {"code": "ARTIFACT_NOT_FOUND", "message": message}})


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz(request: Request) -> dict[str, str]:
    try:
        await request.app.state.redis.ping()
        await verify_database(request.app.state.database_session_factory)
        await request.app.state.object_storage.ensure_ready()
        storage = settings.job_storage_root.resolve()
        storage.mkdir(parents=True, exist_ok=True)
        probe = storage / ".readyz"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "INTERNAL_ERROR", "message": "Readiness dependency unavailable."}},
        ) from exc
    return {"status": "ready"}


@app.get("/api/v1/auth/session", dependencies=_human_route_dependencies)
async def human_session(request: Request) -> dict[str, object]:
    principal = principal_from(request)
    return {
        "subject": principal.subject,
        "display_name": principal.display_name,
        "platform_role": principal.platform_role,
        "workspace_roles": dict(principal.workspace_roles),
        "expires_at": principal.expires_at.isoformat(),
        "human_write_enabled": bool(request.app.state.human_write_enabled),
    }


@app.get("/api/v1/capabilities", dependencies=_human_route_dependencies)
async def capabilities() -> dict[str, object]:
    return {
        "video_jobs": True,
        "deterministic_content": True,
        "publishing_implemented": True,
        "publishing_mode": "dry_run_only",
        "publish_enabled": settings.publish_enabled,
        "publish_external_execution_enabled": settings.publish_external_execution_enabled,
        "publish_owner_gate_enabled": settings.publish_owner_gate_enabled,
        "human_approval_required": settings.human_approval_required,
        "human_authentication": "short_lived_external_bearer",
        "human_rbac_roles": ["viewer", "editor", "reviewer", "owner"],
        "workspace_isolation": "deny_by_default",
        "human_write_enabled": settings.human_write_enabled,
        "human_rate_limit_per_minute": settings.human_rate_limit_per_minute,
        "analytics_implemented": True,
        "analytics_mode": "deterministic_fixture" if settings.analytics_fixture_enabled else "not_configured",
        "analytics_external_execution_enabled": False,
        "analytics_historical_snapshots": True,
        "winner_detection": "explainable_recommendation_only",
        "learning_feedback_auto_applied": False,
        "agent_hub_runtime_dependency": False,
        "agent_hub_bridge_implemented": True,
        "agent_hub_bridge_enabled": settings.agent_hub_bridge_enabled,
        "agent_hub_bridge_contract": "agent-hub-bridge.v1",
        "agent_hub_webhook_mode": settings.agent_hub_webhook_mode,
        "agent_hub_webhook_external_delivery_enabled": settings.agent_hub_webhook_external_delivery_enabled,
        "service_auth": "hmac-sha256-anti-replay",
        "shared_agent_hub_database": False,
        "shared_agent_hub_redis": False,
        "metadata_database": "postgresql",
        "queue": "redis-transient",
        "object_storage": settings.object_storage_provider,
        "durable_job_state": True,
        "cost_currency": "VND",
        "provider_safety_plane": "enforced",
        "provider_safety_state_backend": "postgresql",
        "provider_external_execution_enabled": settings.provider_external_execution_enabled,
        "provider_paid_execution_enabled": settings.provider_paid_execution_enabled,
        "provider_global_kill_switch_engaged": settings.provider_global_kill_switch_engaged,
        "provider_budget_currency": settings.provider_budget_currency,
        "provider_ledger_retention_days": settings.provider_operation_retention_days,
        "provider_ledger_cleanup_enabled": settings.provider_retention_cleanup_enabled,
        "operations_snapshot": "authenticated_read_only",
        "operations_external_notifications_enabled": settings.operations_external_notifications_enabled,
        "request_correlation_headers": ["X-Request-ID", "X-Correlation-ID"],
        "operations_evidence_retention_days": settings.operations_evidence_retention_days,
        "operations_log_retention_days": settings.operations_log_retention_days,
        "trend_radar": True,
        "idea_intelligence": True,
        "content_opportunity_queue": True,
        "trend_provider_mode": "deterministic_fixture" if settings.trend_fixture_enabled else "not_configured",
        "live_trend_providers_configured": False,
        "creator_media_download": False,
        "idea_to_project_state": "draft_only",
        "resumable_upload": True,
        "upload_quarantine_required": True,
        "upload_malware_scanner_mode": settings.media_malware_scanner_mode,
        "archive_ingestion_enabled": False,
        "public_ingress_approved": False,
        "auto_edit_analysis": True,
        "auto_edit_timeline": True,
        "timeline_versioning": True,
        "timeline_optimistic_concurrency": True,
        "proxy_preview": "asynchronous_540p",
        "preview_audio": "version_bound_av_review",
        "preview_publish": False,
        "subtitle_editor": True,
        "dynamic_subtitles": True,
        "audio_mixer": True,
        "music_ducking": True,
        "audio_tts_provider": settings.audio_tts_provider,
        "audio_external_execution_enabled": settings.audio_external_execution_enabled,
        "review_render": "asynchronous_540x960",
        "final_render_profiles": [
            "vertical-1080x1920",
            "landscape-1920x1080",
            "square-1080x1080",
        ],
        "final_render_requires_version_bound_approval": True,
        "full_video_qc": True,
        "final_render_publish": "dry_run_validation_only",
        "source_media_mutation": False,
        "transcription_provider": settings.transcription_provider,
        "media_signal_provider": settings.auto_edit_signal_provider,
        "vision_analysis": True,
        "vision_provider": settings.vision_provider,
        "live_vision_provider_configured": False,
        "ocr": True,
        "subject_tracking": True,
        "smart_reframe": True,
        "smart_reframe_aspect_ratios": ["9:16", "16:9", "1:1", "4:5"],
        "smart_reframe_preview_only": True,
        "media_intelligence": True,
        "media_planner": True,
        "broll_planner": True,
        "stock_media_provider": settings.stock_media_provider,
        "image_generation_provider": settings.image_generation_provider,
        "video_generation_provider": settings.video_generation_provider,
        "comfyui_bridge_contract": True,
        "comfyui_execution_enabled": settings.comfyui_execution_enabled,
        "media_external_execution_enabled": settings.media_external_execution_enabled,
        "media_paid_execution_enabled": settings.media_paid_execution_enabled,
        "media_rights_gate": "fail_closed",
        "media_resolution": "asynchronous",
        "media_fixture_production_eligible": False,
    }


@app.post(
    "/api/v1/video-jobs",
    response_model=JobCreateResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=_human_route_dependencies,
)
async def create_video_job(
    payload: VideoJobCreate,
    request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key", max_length=200),
) -> JobCreateResponse:
    store = store_from(request)
    platform = getattr(request.app.state, "platform_repository", None)
    context = None
    if platform is not None:
        try:
            if payload.project_id:
                await authorize_project(request, payload.project_id, "editor")
            elif payload.workspace_id:
                await authorize_workspace(request, payload.workspace_id, "editor")
            else:
                await authorize_workspace(request, request.app.state.default_workspace_id, "editor")
            context = await platform.resolve_job_context(
                payload.model_dump(mode="json"),
                default_workspace=WorkspaceCreate(
                    slug=settings.default_workspace_slug,
                    name=settings.default_workspace_name,
                    owner_ref=settings.default_workspace_owner_ref,
                    provenance={"source": "bootstrap-config"},
                ),
            )
        except KeyError as exc:
            raise HTTPException(
                status_code=404,
                detail={"error": {"code": "NOT_FOUND", "message": "Workspace, project or version not found."}},
            ) from exc
    candidate = JobRecord.new(
        job_id=new_job_id(),
        request=payload,
        workspace_id=context.workspace_id if context else payload.workspace_id,
        project_id=context.project_id if context else payload.project_id,
        project_version_id=context.project_version_id if context else payload.project_version_id,
    )
    record = await store.create(candidate, idempotency_key=idempotency_key)
    if record.job_id == candidate.job_id:
        await store.enqueue(record.job_id)
    return JobCreateResponse(
        job_id=record.job_id,
        workspace_id=record.workspace_id,
        project_id=record.project_id,
        project_version_id=record.project_version_id,
        status=record.status,
        stage=record.stage,
        progress=record.progress,
        status_url=f"/api/v1/video-jobs/{record.job_id}",
    )


@app.get(
    "/api/v1/video-jobs/{job_id}",
    response_model=JobRecord,
    dependencies=_human_route_dependencies,
)
async def get_video_job(job_id: str, request: Request) -> JobRecord:
    if not job_id.startswith("vid_") or len(job_id) > 80:
        raise not_found()
    record = await store_from(request).get(job_id)
    if record is None:
        raise not_found()
    return record


@app.get(
    "/api/v1/video-jobs/{job_id}/artifacts/{artifact_name}",
    dependencies=_human_route_dependencies,
)
async def get_video_artifact(job_id: str, artifact_name: str, request: Request) -> FileResponse:
    record = await store_from(request).get(job_id)
    if record is None:
        raise not_found()
    try:
        path = resolve_recorded_artifact(settings.job_storage_root, record, artifact_name)
    except ArtifactAccessError as exc:
        try:
            artifact = recorded_artifact(record, artifact_name)
            if not artifact.object_key:
                raise exc
            path = recorded_artifact_path(settings.job_storage_root, record, artifact_name)
            await request.app.state.object_storage.download_file(
                object_key=artifact.object_key,
                destination=path,
            )
            if artifact.checksum_sha256 and sha256_file(path) != artifact.checksum_sha256:
                path.unlink(missing_ok=True)
                raise ArtifactAccessError("artifact checksum mismatch")
        except Exception as recovery_exc:
            raise not_found("Artifact not found.") from recovery_exc
    return FileResponse(path=path, filename=artifact_name)
