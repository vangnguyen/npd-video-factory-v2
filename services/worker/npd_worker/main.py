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
from app.repositories import PlatformRepository, PostgresJobStore
from app.state import QUEUE_KEY

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
    await recover_media_resolution_jobs(redis, media_repository)
    logger.info("worker_booted queue=%s processing=%s", QUEUE_KEY, PROCESSING_KEY)
    try:
        await asyncio.gather(
            run_video_queue(redis, store, config=config),
            run_media_resolution_queue(redis, media_resolution_service),
        )
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
