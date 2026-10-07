from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.analytics_service import ANALYTICS_SYNC_PROCESSING_KEY, ANALYTICS_SYNC_QUEUE_KEY
from npd_worker.main import recover_analytics_sync_jobs, run_analytics_sync_queue, run_analytics_due_scheduler
from app.analytics_service import enqueue_analytics_sync


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
            ANALYTICS_SYNC_QUEUE_KEY: ["ans_pending"],
            ANALYTICS_SYNC_PROCESSING_KEY: ["ans_inflight", "ans_duplicate"],
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

    async def eval(self, _script, key_count, queued, processing, identifier):
        assert key_count == 2
        if identifier in self.lists[queued] or identifier in self.lists[processing]: return 0
        self.lists[queued].append(identifier); return 1


class FakeRepository:
    async def recover_incomplete_sync_ids(self):
        return ["ans_duplicate", "ans_pending"]


class FakeProcessor:
    def __init__(self) -> None:
        self.processed: list[str] = []

    async def process(self, sync_id):
        self.processed.append(sync_id)
        return SimpleNamespace(status="succeeded")


@pytest.mark.asyncio
async def test_analytics_recovery_deduplicates_database_and_processing_state() -> None:
    redis = FakeRedis()
    count = await recover_analytics_sync_jobs(redis, FakeRepository())
    assert count == 3
    assert redis.lists[ANALYTICS_SYNC_PROCESSING_KEY] == []
    assert redis.lists[ANALYTICS_SYNC_QUEUE_KEY] == [
        "ans_inflight",
        "ans_duplicate",
        "ans_pending",
    ]


@pytest.mark.asyncio
async def test_queue_admission_deduplicates_pending_and_processing_syncs():
    redis = FakeRedis()
    assert await enqueue_analytics_sync(redis, 'ans_pending') is False
    assert await enqueue_analytics_sync(redis, 'ans_inflight') is False
    assert await enqueue_analytics_sync(redis, 'ans_new_sync') is True
    assert await enqueue_analytics_sync(redis, 'ans_new_sync') is False
    with pytest.raises(ValueError): await enqueue_analytics_sync(redis, 'private content')
    assert redis.lists[ANALYTICS_SYNC_QUEUE_KEY] == ['ans_pending', 'ans_new_sync']


@pytest.mark.asyncio
async def test_due_tick_survives_queue_outage_and_recovers_without_private_logging(monkeypatch, caplog):
    redis = FakeRedis(); redis.lists[ANALYTICS_SYNC_QUEUE_KEY] = []
    original = redis.eval; ticks = 0
    class Repository:
        async def activate_due_sync_ids(self): return ['ans_due_fixture'] if ticks == 0 else []
        async def queued_sync_ids(self): return ['ans_due_fixture']
    async def eval_once(*args):
        if ticks == 0: raise ConnectionError('PRIVATE TOKEN / PRIVATE ENDPOINT')
        return await original(*args)
    redis.eval = eval_once
    async def sleep(seconds):
        nonlocal ticks
        assert seconds == 5; ticks += 1
        if ticks == 2: raise asyncio.CancelledError()
    monkeypatch.setattr('npd_worker.main.asyncio.sleep', sleep)
    with pytest.raises(asyncio.CancelledError): await run_analytics_due_scheduler(redis, Repository())
    assert redis.lists[ANALYTICS_SYNC_QUEUE_KEY] == ['ans_due_fixture']
    assert 'analytics_due_tick_failed' in caplog.text and 'PRIVATE' not in caplog.text


@pytest.mark.asyncio
async def test_analytics_worker_claims_processes_and_acknowledges() -> None:
    redis = FakeRedis()
    redis.lists[ANALYTICS_SYNC_PROCESSING_KEY] = []
    processor = FakeProcessor()
    task = asyncio.create_task(run_analytics_sync_queue(redis, processor))
    await asyncio.wait_for(redis.removed.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert processor.processed == ["ans_pending"]
    assert redis.lists[ANALYTICS_SYNC_PROCESSING_KEY] == []
