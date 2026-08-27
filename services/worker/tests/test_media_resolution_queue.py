from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.media_intelligence_service import (
    MEDIA_RESOLUTION_PROCESSING_KEY,
    MEDIA_RESOLUTION_QUEUE_KEY,
)
from npd_worker.main import recover_media_resolution_jobs, run_media_resolution_queue


class FakePipeline:
    def __init__(self, redis) -> None:
        self.redis = redis

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def delete(self, key):
        self.redis.lists[key] = []
        return self

    def lrem(self, key, _count, value):
        self.redis.lists[key] = [item for item in self.redis.lists.get(key, []) if item != value]
        return self

    def rpush(self, key, *values):
        self.redis.lists.setdefault(key, []).extend(values)
        return self

    async def execute(self):
        return []


class FakeRedis:
    def __init__(self) -> None:
        self.lists = {
            MEDIA_RESOLUTION_QUEUE_KEY: ["mrj_pending"],
            MEDIA_RESOLUTION_PROCESSING_KEY: ["mrj_inflight", "mrj_duplicate"],
        }
        self.claimed = False
        self.removed = asyncio.Event()

    async def lrange(self, key, _start, _end):
        return list(self.lists.get(key, []))

    def pipeline(self, *, transaction):
        assert transaction is True
        return FakePipeline(self)

    async def brpoplpush(self, source, destination, *, timeout):
        assert timeout == 5
        if not self.claimed:
            self.claimed = True
            value = self.lists[source].pop()
            self.lists.setdefault(destination, []).insert(0, value)
            return value
        await asyncio.sleep(60)

    async def lrem(self, key, _count, value):
        self.lists[key] = [item for item in self.lists.get(key, []) if item != value]
        self.removed.set()


class FakeRepository:
    async def list_incomplete_resolution_job_ids(self):
        return ["mrj_duplicate", "mrj_pending"]


class FakeResolutionService:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, job_id):
        self.processed.append(job_id)
        return SimpleNamespace(status="succeeded")


@pytest.mark.asyncio
async def test_recovery_deduplicates_inflight_and_persistent_jobs() -> None:
    redis = FakeRedis()
    count = await recover_media_resolution_jobs(redis, FakeRepository())
    assert count == 3
    assert redis.lists[MEDIA_RESOLUTION_PROCESSING_KEY] == []
    assert redis.lists[MEDIA_RESOLUTION_QUEUE_KEY] == [
        "mrj_inflight",
        "mrj_duplicate",
        "mrj_pending",
    ]


@pytest.mark.asyncio
async def test_worker_claims_processes_and_acknowledges_resolution_job() -> None:
    redis = FakeRedis()
    redis.lists[MEDIA_RESOLUTION_QUEUE_KEY] = ["mrj_one"]
    redis.lists[MEDIA_RESOLUTION_PROCESSING_KEY] = []
    service = FakeResolutionService()
    task = asyncio.create_task(run_media_resolution_queue(redis, service))
    await asyncio.wait_for(redis.removed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.processed == ["mrj_one"]
    assert redis.lists[MEDIA_RESOLUTION_PROCESSING_KEY] == []
