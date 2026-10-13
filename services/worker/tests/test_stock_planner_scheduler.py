"""Dedicated scheduler delegates only fenced read-only planning work."""
import asyncio
import pytest
from npd_worker import main as worker


@pytest.mark.asyncio
@pytest.mark.parametrize('failed',[False,True])
async def test_planner_scheduler_waits_and_recovers_after_one_failure(monkeypatch,caplog,failed):
    calls=[]
    class Service:
        async def recover_due_stock_plans(self,*,limit):
            calls.append(limit)
            if len(calls)==1 and failed:
                raise RuntimeError('PRIVATE fixture detail must never be logged')
            return 1
    async def pause(seconds):
        assert seconds==30
        if len(calls)==2:raise asyncio.CancelledError()
    monkeypatch.setattr(worker.asyncio,'sleep',pause)
    with pytest.raises(asyncio.CancelledError):await worker.recover_due_stock_plans(Service())
    assert calls==[25,25] and 'PRIVATE' not in caplog.text
    if failed:assert 'stock_due_plan_recovery_failed' in caplog.text
