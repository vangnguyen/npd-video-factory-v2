from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.timeline_service import PREVIEW_PROCESSING_KEY, PREVIEW_QUEUE_KEY
from npd_worker.main import recover_preview_jobs, run_preview_queue


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
            PREVIEW_QUEUE_KEY: ["prv_pending"],
            PREVIEW_PROCESSING_KEY: ["prv_inflight", "prv_duplicate"],
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
    async def list_incomplete_preview_ids(self):
        return ["prv_duplicate", "prv_pending"]


class FakePreviewService:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, preview_id):
        self.processed.append(preview_id)
        return SimpleNamespace(status="ready")


@pytest.mark.asyncio
async def test_preview_recovery_deduplicates_persisted_and_inflight_jobs() -> None:
    redis = FakeRedis()
    count = await recover_preview_jobs(redis, FakeRepository())
    assert count == 3
    assert redis.lists[PREVIEW_PROCESSING_KEY] == []
    assert redis.lists[PREVIEW_QUEUE_KEY] == ["prv_inflight", "prv_duplicate", "prv_pending"]


@pytest.mark.asyncio
async def test_worker_claims_processes_and_acknowledges_preview() -> None:
    redis = FakeRedis()
    redis.lists[PREVIEW_QUEUE_KEY] = ["prv_one"]
    redis.lists[PREVIEW_PROCESSING_KEY] = []
    service = FakePreviewService()
    task = asyncio.create_task(run_preview_queue(redis, service))
    await asyncio.wait_for(redis.removed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.processed == ["prv_one"]
    assert redis.lists[PREVIEW_PROCESSING_KEY] == []
