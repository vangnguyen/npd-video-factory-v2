from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.production_service import PRODUCTION_RENDER_PROCESSING_KEY, PRODUCTION_RENDER_QUEUE_KEY
from npd_worker.main import recover_production_render_jobs, run_production_render_queue


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
            PRODUCTION_RENDER_QUEUE_KEY: ["rnd_pending"],
            PRODUCTION_RENDER_PROCESSING_KEY: ["rnd_inflight", "rnd_duplicate"],
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
    async def list_incomplete_render_ids(self):
        return ["rnd_duplicate", "rnd_pending"]


class FakeRenderService:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, render_id):
        self.processed.append(render_id)
        return SimpleNamespace(status="awaiting_review")


@pytest.mark.asyncio
async def test_production_render_recovery_deduplicates_database_and_processing_state() -> None:
    redis = FakeRedis()
    count = await recover_production_render_jobs(redis, FakeRepository())
    assert count == 3
    assert redis.lists[PRODUCTION_RENDER_PROCESSING_KEY] == []
    assert redis.lists[PRODUCTION_RENDER_QUEUE_KEY] == [
        "rnd_inflight",
        "rnd_duplicate",
        "rnd_pending",
    ]


@pytest.mark.asyncio
async def test_production_render_worker_claims_processes_and_acknowledges() -> None:
    redis = FakeRedis()
    redis.lists[PRODUCTION_RENDER_PROCESSING_KEY] = []
    service = FakeRenderService()
    task = asyncio.create_task(run_production_render_queue(redis, service))
    await asyncio.wait_for(redis.removed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert service.processed == ["rnd_pending"]
    assert redis.lists[PRODUCTION_RENDER_PROCESSING_KEY] == []
