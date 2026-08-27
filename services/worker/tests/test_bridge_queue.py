from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.bridge_service import WEBHOOK_PROCESSING_KEY, WEBHOOK_QUEUE_KEY
from npd_worker.main import recover_webhook_deliveries, run_webhook_queue


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
            WEBHOOK_QUEUE_KEY: ["wdl_pending"],
            WEBHOOK_PROCESSING_KEY: ["wdl_inflight", "wdl_duplicate"],
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
    async def recover_incomplete_delivery_ids(self):
        return ["wdl_duplicate", "wdl_pending"]


class FakeProcessor:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, delivery_id):
        self.processed.append(delivery_id)
        return SimpleNamespace(status="succeeded")


@pytest.mark.asyncio
async def test_webhook_recovery_deduplicates_database_and_processing_state() -> None:
    redis = FakeRedis()
    count = await recover_webhook_deliveries(redis, FakeRepository())
    assert count == 3
    assert redis.lists[WEBHOOK_PROCESSING_KEY] == []
    assert redis.lists[WEBHOOK_QUEUE_KEY] == ["wdl_inflight", "wdl_duplicate", "wdl_pending"]


@pytest.mark.asyncio
async def test_webhook_worker_claims_processes_and_acknowledges() -> None:
    redis = FakeRedis()
    redis.lists[WEBHOOK_PROCESSING_KEY] = []
    processor = FakeProcessor()
    task = asyncio.create_task(run_webhook_queue(redis, processor))
    await asyncio.wait_for(redis.removed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processor.processed == ["wdl_pending"]
    assert redis.lists[WEBHOOK_PROCESSING_KEY] == []
