"""Actual isolated SQLite interleaving; no real provider/audio/render execution."""
import asyncio
from sqlalchemy import select, update
import pytest
from app.db import CostRecordORM, ProviderUsageORM
from app.production_db import ProductionRenderJobORM, ProductionEventORM
from test_sql_tts_artifact_reuse import env, ready

async def rows(environment):
    async with environment.factory() as session:
        result = {}
        for model in (ProductionRenderJobORM, ProductionEventORM, ProviderUsageORM, CostRecordORM):
            saved = (await session.scalars(select(model))).all()
            result[model.__tablename__] = [
                {column.name:getattr(row,column.name) for column in model.__table__.columns}
                for row in saved]
        return result

@pytest.mark.asyncio
@pytest.mark.parametrize('terminal',['failed','awaiting_review','ready'])
async def test_legacy_terminal_commit_during_start_is_observed_without_io(env,monkeypatch,terminal):
    state,worker,_,queued = await ready(env)
    assert queued.manifest.get('variant_narration_request') is None
    entered,resume = asyncio.Event(),asyncio.Event()
    original = worker.repository.start_render
    async def paused(identity):
        entered.set();await resume.wait()
        return await original(identity)
    monkeypatch.setattr(worker.repository,'start_render',paused)
    attempts=[]
    async def forbidden(**kwargs):
        attempts.append('io');raise AssertionError('TERMINAL_RENDER_MUST_NOT_DISPATCH')
    monkeypatch.setattr(worker.object_storage,'download_file',forbidden)
    monkeypatch.setattr(worker.audio_engine,'mix',forbidden)
    monkeypatch.setattr(worker.renderer,'render',forbidden)
    task=asyncio.create_task(worker.process(queued.render_id))
    try:
        await asyncio.wait_for(entered.wait(),10)
        if terminal=='failed':
            await worker.repository.fail_render(queued.render_id,code='FIRST_WORKER_FIXTURE_FAILURE',
                reason='First worker fixture terminal decision; no real processing.')
        else:
            # Explicit terminal-state fixture for the observation boundary, not QC acceptance.
            async with env.factory() as session,session.begin():
                await session.execute(update(ProductionRenderJobORM).where(
                    ProductionRenderJobORM.render_id==queued.render_id).values(status=terminal))
        before=await rows(env)
        authoritative=await worker.repository.get_render(queued.render_id)
        resume.set();result=await asyncio.wait_for(task,15)
        assert result.model_dump(mode='json')==authoritative.model_dump(mode='json')
        assert await rows(env)==before
        assert attempts==[] and state['calls']==[]
        assert not worker.staging_root.exists()
    finally:
        resume.set()
        if not task.done():
            task.cancel();await asyncio.gather(task,return_exceptions=True)
