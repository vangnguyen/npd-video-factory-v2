from __future__ import annotations

import asyncio
import logging
import os

from redis.asyncio import Redis

from app.config import settings
from app.db import create_engine, create_session_factory, verify_database
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


async def main() -> None:
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    redis = Redis.from_url(redis_url, decode_responses=True)
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    await verify_database(session_factory)
    object_storage = create_object_storage(settings)
    await object_storage.ensure_ready()
    platform = PlatformRepository(session_factory)
    store = PostgresJobStore(
        session_factory,
        redis,
        platform=platform,
        object_storage=object_storage,
    )
    config = WorkerConfig.from_env()
    await recover_inflight(redis)
    logger.info("worker_booted queue=%s processing=%s", QUEUE_KEY, PROCESSING_KEY)
    try:
        while True:
            job_id = await redis.brpoplpush(QUEUE_KEY, PROCESSING_KEY, timeout=5)
            if job_id is None:
                continue
            logger.info("job_claimed job_id=%s", job_id)
            try:
                await run_job(store, job_id, config=config)
            finally:
                await redis.lrem(PROCESSING_KEY, 1, job_id)
    finally:
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
