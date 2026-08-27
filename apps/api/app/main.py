from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import FileResponse
from redis.asyncio import Redis

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
from .models import JobCreateResponse, JobRecord, VideoJobCreate
from .object_storage import create_object_storage, sha256_file
from .platform_models import WorkspaceCreate
from .platform_routes import router as platform_router
from .repositories import PlatformRepository, PostgresJobStore
from .trend_providers import create_trend_provider_registry
from .trend_repository import TrendRepository
from .trend_routes import router as trend_router
from .trend_service import TrendIntelligenceService


def new_job_id() -> str:
    millis = int(time.time() * 1000)
    return f"vid_{millis:013d}_{uuid.uuid4().hex[:10]}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.job_storage_root.mkdir(parents=True, exist_ok=True)
    settings.asset_storage_root.mkdir(parents=True, exist_ok=True)
    settings.upload_staging_root.mkdir(parents=True, exist_ok=True)
    settings.analysis_staging_root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    redis = Redis.from_url(settings.redis_url, decode_responses=False)
    object_storage = create_object_storage(settings)
    platform = PlatformRepository(session_factory)
    trend_repository = TrendRepository(session_factory)
    auto_edit_repository = AutoEditRepository(session_factory)
    trend_providers = create_trend_provider_registry(
        settings.trend_fixture_path,
        fixture_enabled=settings.trend_fixture_enabled,
    )
    await verify_database(session_factory)
    await object_storage.ensure_ready()
    await platform.ensure_workspace(
        WorkspaceCreate(
            slug=settings.default_workspace_slug,
            name=settings.default_workspace_name,
            owner_ref=settings.default_workspace_owner_ref,
            provenance={"source": "bootstrap-config"},
        )
    )
    await platform.seed_providers(_provider_definitions())
    await trend_repository.seed_sources(trend_providers.definitions())
    app.state.database_engine = engine
    app.state.database_session_factory = session_factory
    app.state.redis = redis
    app.state.object_storage = object_storage
    app.state.platform_repository = platform
    app.state.trend_repository = trend_repository
    app.state.auto_edit_repository = auto_edit_repository
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
    )
    try:
        yield
    finally:
        await redis.aclose()
        await engine.dispose()


app = FastAPI(title="NPD Video Factory V2 API", version="0.5.0", lifespan=lifespan)
app.include_router(platform_router)
app.include_router(trend_router)
app.include_router(auto_edit_router)


def store_from(request: Request) -> PostgresJobStore:
    return request.app.state.job_store


def _provider_definitions() -> list[dict[str, object]]:
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
    ]


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


@app.get("/api/v1/capabilities")
async def capabilities() -> dict[str, object]:
    return {
        "video_jobs": True,
        "deterministic_content": True,
        "publishing_implemented": False,
        "publish_enabled": settings.publish_enabled,
        "human_approval_required": settings.human_approval_required,
        "agent_hub_runtime_dependency": False,
        "metadata_database": "postgresql",
        "queue": "redis-transient",
        "object_storage": settings.object_storage_provider,
        "durable_job_state": True,
        "cost_currency": "VND",
        "trend_radar": True,
        "idea_intelligence": True,
        "content_opportunity_queue": True,
        "trend_provider_mode": "deterministic_fixture" if settings.trend_fixture_enabled else "not_configured",
        "live_trend_providers_configured": False,
        "creator_media_download": False,
        "idea_to_project_state": "draft_only",
        "resumable_upload": True,
        "auto_edit_analysis": True,
        "auto_edit_timeline": False,
        "source_media_mutation": False,
        "transcription_provider": settings.transcription_provider,
        "media_signal_provider": settings.auto_edit_signal_provider,
    }


@app.post("/api/v1/video-jobs", response_model=JobCreateResponse, status_code=status.HTTP_202_ACCEPTED)
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


@app.get("/api/v1/video-jobs/{job_id}", response_model=JobRecord)
async def get_video_job(job_id: str, request: Request) -> JobRecord:
    if not job_id.startswith("vid_") or len(job_id) > 80:
        raise not_found()
    record = await store_from(request).get(job_id)
    if record is None:
        raise not_found()
    return record


@app.get("/api/v1/video-jobs/{job_id}/artifacts/{artifact_name}")
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
