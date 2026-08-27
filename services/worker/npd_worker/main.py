from __future__ import annotations

import asyncio
import logging
import os

from redis.asyncio import Redis

from app.config import settings
from app.db import create_engine, create_session_factory, verify_database
from app.auto_edit_repository import AutoEditRepository
from app.media_intelligence_repository import MediaIntelligenceRepository
from app.media_intelligence_service import (
    MEDIA_RESOLUTION_PROCESSING_KEY,
    MEDIA_RESOLUTION_QUEUE_KEY,
    MediaResolutionService,
    create_media_provider_bundle,
)
from app.object_storage import create_object_storage
from app.production_audio import AudioMixEngine, create_audio_tts_provider
from app.production_logic import TimelineRenderContractValidator
from app.production_qc import FullProductionQC
from app.production_repository import ProductionRepository
from app.production_service import (
    PRODUCTION_RENDER_PROCESSING_KEY,
    PRODUCTION_RENDER_QUEUE_KEY,
    ProductionRenderProcessor,
    RemotionTimelineRenderEngine,
)
from app.repositories import PlatformRepository, PostgresJobStore
from app.state import QUEUE_KEY
from app.timeline_repository import TimelineRepository
from app.timeline_service import (
    PREVIEW_PROCESSING_KEY,
    PREVIEW_QUEUE_KEY,
    FFmpegProxyRenderer,
    PreviewService,
)

from .pipeline import WorkerConfig, run_job


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("npd-video-worker")
PROCESSING_KEY = "npd:video-jobs:processing"


async def recover_inflight(redis: Redis) -> int:
    inflight = await redis.lrange(PROCESSING_KEY, 0, -1)
    if not inflight:
        return 0
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(PROCESSING_KEY)
        pipe.rpush(QUEUE_KEY, *inflight)
        await pipe.execute()
    logger.warning("recovered_inflight count=%d", len(inflight))
    return len(inflight)


async def recover_media_resolution_jobs(
    redis: Redis,
    repository: MediaIntelligenceRepository,
) -> int:
    inflight = await redis.lrange(MEDIA_RESOLUTION_PROCESSING_KEY, 0, -1)
    pending = await repository.list_incomplete_resolution_job_ids()
    identifiers = list(dict.fromkeys([*inflight, *pending]))
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(MEDIA_RESOLUTION_PROCESSING_KEY)
        for identifier in identifiers:
            pipe.lrem(MEDIA_RESOLUTION_QUEUE_KEY, 0, identifier)
            pipe.rpush(MEDIA_RESOLUTION_QUEUE_KEY, identifier)
        await pipe.execute()
    if identifiers:
        logger.warning("recovered_media_resolution count=%d", len(identifiers))
    return len(identifiers)


async def recover_preview_jobs(redis: Redis, repository: TimelineRepository) -> int:
    inflight = await redis.lrange(PREVIEW_PROCESSING_KEY, 0, -1)
    pending = await repository.list_incomplete_preview_ids()
    identifiers = list(dict.fromkeys([*inflight, *pending]))
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(PREVIEW_PROCESSING_KEY)
        for identifier in identifiers:
            pipe.lrem(PREVIEW_QUEUE_KEY, 0, identifier)
            pipe.rpush(PREVIEW_QUEUE_KEY, identifier)
        await pipe.execute()
    if identifiers:
        logger.warning("recovered_preview count=%d", len(identifiers))
    return len(identifiers)


async def recover_production_render_jobs(
    redis: Redis,
    repository: ProductionRepository,
) -> int:
    inflight = await redis.lrange(PRODUCTION_RENDER_PROCESSING_KEY, 0, -1)
    pending = await repository.list_incomplete_render_ids()
    identifiers = list(dict.fromkeys([*inflight, *pending]))
    async with redis.pipeline(transaction=True) as pipe:
        pipe.delete(PRODUCTION_RENDER_PROCESSING_KEY)
        for identifier in identifiers:
            pipe.lrem(PRODUCTION_RENDER_QUEUE_KEY, 0, identifier)
            pipe.rpush(PRODUCTION_RENDER_QUEUE_KEY, identifier)
        await pipe.execute()
    if identifiers:
        logger.warning("recovered_production_render count=%d", len(identifiers))
    return len(identifiers)


async def run_video_queue(
    redis: Redis,
    store: PostgresJobStore,
    *,
    config: WorkerConfig,
) -> None:
    while True:
        job_id = await redis.brpoplpush(QUEUE_KEY, PROCESSING_KEY, timeout=5)
        if job_id is None:
            continue
        logger.info("job_claimed job_id=%s", job_id)
        try:
            await run_job(store, job_id, config=config)
        finally:
            await redis.lrem(PROCESSING_KEY, 1, job_id)


async def run_media_resolution_queue(
    redis: Redis,
    service: MediaResolutionService,
) -> None:
    while True:
        resolution_job_id = await redis.brpoplpush(
            MEDIA_RESOLUTION_QUEUE_KEY,
            MEDIA_RESOLUTION_PROCESSING_KEY,
            timeout=5,
        )
        if resolution_job_id is None:
            continue
        logger.info("media_resolution_claimed resolution_job_id=%s", resolution_job_id)
        try:
            result = await service.process(resolution_job_id)
            logger.info(
                "media_resolution_completed resolution_job_id=%s status=%s",
                resolution_job_id,
                result.status,
            )
        except Exception:
            logger.exception("media_resolution_worker_error resolution_job_id=%s", resolution_job_id)
        finally:
            await redis.lrem(MEDIA_RESOLUTION_PROCESSING_KEY, 1, resolution_job_id)


async def run_preview_queue(redis: Redis, service: PreviewService) -> None:
    while True:
        preview_id = await redis.brpoplpush(
            PREVIEW_QUEUE_KEY,
            PREVIEW_PROCESSING_KEY,
            timeout=5,
        )
        if preview_id is None:
            continue
        logger.info("preview_claimed preview_id=%s", preview_id)
        try:
            result = await service.process(preview_id)
            logger.info("preview_completed preview_id=%s status=%s", preview_id, result.status)
        except Exception:
            logger.exception("preview_worker_error preview_id=%s", preview_id)
        finally:
            await redis.lrem(PREVIEW_PROCESSING_KEY, 1, preview_id)


async def run_production_render_queue(
    redis: Redis,
    service: ProductionRenderProcessor,
) -> None:
    while True:
        render_id = await redis.brpoplpush(
            PRODUCTION_RENDER_QUEUE_KEY,
            PRODUCTION_RENDER_PROCESSING_KEY,
            timeout=5,
        )
        if render_id is None:
            continue
        logger.info("production_render_claimed render_id=%s", render_id)
        try:
            result = await service.process(render_id)
            logger.info("production_render_completed render_id=%s status=%s", render_id, result.status)
        except Exception:
            logger.exception("production_render_worker_error render_id=%s", render_id)
        finally:
            await redis.lrem(PRODUCTION_RENDER_PROCESSING_KEY, 1, render_id)


async def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis = Redis.from_url(redis_url, decode_responses=True)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    await verify_database(session_factory)
    object_storage = create_object_storage(settings)
    await object_storage.ensure_ready()
    platform = PlatformRepository(session_factory)
    auto_edit_repository = AutoEditRepository(session_factory)
    media_repository = MediaIntelligenceRepository(session_factory)
    timeline_repository = TimelineRepository(session_factory)
    production_repository = ProductionRepository(session_factory)
    store = PostgresJobStore(
        session_factory,
        redis,
        platform=platform,
        object_storage=object_storage,
    )
    config = WorkerConfig.from_env()
    await recover_inflight(redis)
    providers = create_media_provider_bundle(settings)
    media_resolution_service = MediaResolutionService(
        repository=media_repository,
        platform=platform,
        auto_edit_repository=auto_edit_repository,
        object_storage=object_storage,
        providers=providers,
        queue=redis,
        staging_root=settings.media_staging_root,
        allow_external_execution=settings.media_external_execution_enabled,
        allow_paid_execution=settings.media_paid_execution_enabled,
    )
    preview_service = PreviewService(
        repository=timeline_repository,
        platform=platform,
        auto_edit_repository=auto_edit_repository,
        object_storage=object_storage,
        queue=redis,
        renderer=FFmpegProxyRenderer(settings.ffmpeg_path),
        staging_root=settings.preview_staging_root,
    )
    production_render_service = ProductionRenderProcessor(
        repository=production_repository,
        platform=platform,
        asset_repository=auto_edit_repository,
        object_storage=object_storage,
        renderer=RemotionTimelineRenderEngine(
            renderer_url=settings.renderer_url,
            timeout_seconds=settings.renderer_timeout_seconds,
        ),
        qc=FullProductionQC(
            ffprobe_path=settings.ffprobe_path,
            ffmpeg_path=settings.ffmpeg_path,
        ),
        tts_provider=create_audio_tts_provider(settings),
        audio_engine=AudioMixEngine(ffmpeg_path=settings.ffmpeg_path),
        manifest_validator=TimelineRenderContractValidator(
            settings.contracts_root / "timeline-render.schema.json"
        ),
        staging_root=settings.production_render_staging_root,
        brand_name=settings.video_factory_brand_name,
    )
    await recover_media_resolution_jobs(redis, media_repository)
    await recover_preview_jobs(redis, timeline_repository)
    await recover_production_render_jobs(redis, production_repository)
    logger.info("worker_booted queue=%s processing=%s", QUEUE_KEY, PROCESSING_KEY)
    try:
        await asyncio.gather(
            run_video_queue(redis, store, config=config),
            run_media_resolution_queue(redis, media_resolution_service),
            run_preview_queue(redis, preview_service),
            run_production_render_queue(redis, production_render_service),
        )
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
