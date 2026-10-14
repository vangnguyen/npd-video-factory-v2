"""Actual SQL persistence; audio/provider/renderer execution is outside this test."""
from types import SimpleNamespace
import pytest
from sqlalchemy import select
from app.db import CostRecordORM, ProviderUsageORM
from app.production_service import ProductionRenderProcessor
from test_mvp1_multi_input import env

def processor(environment):
    # Isolated accounting boundary; no render, audio, queue, storage or provider method is invoked.
    value = object.__new__(ProductionRenderProcessor)
    value.platform = environment.platform
    return value

def render(environment, identity):
    return SimpleNamespace(workspace_id=environment.workspace.workspace_id,
                           project_id=environment.project.project_id,
                           render_id=identity, profile='youtube-landscape')

async def rows(environment):
    async with environment.factory() as session:
        result = {}
        for model in (ProviderUsageORM, CostRecordORM):
            values = (await session.scalars(select(model))).all()
            result[model.__tablename__] = [
                {column.name: getattr(value, column.name) for column in model.__table__.columns}
                for value in values]
        return result

@pytest.mark.asyncio
async def test_disabled_voice_records_render_without_inventing_espeak_usage(env):
    await processor(env)._record_costs(render(env, 'rnd_disabled_voice_regression'),
        narration={'provider':'disabled','timing':[],'cue_count':0})
    saved = await rows(env)
    usage = saved['provider_usage']
    assert len(usage) == 1
    assert usage[0]['provider_key'] == 'remotion' and usage[0]['capability'] == 'rendering'
    assert len(saved['cost_records']) == 1

@pytest.mark.asyncio
async def test_disabled_voice_new_render_preserves_original_historical_ledger(env):
    await env.platform.record_provider_operation(workspace_id=env.workspace.workspace_id,
        project_id=env.project.project_id,job_id=None,provider_key='espeak',capability='tts',
        operation='tts.v2-08.rnd_historical_disabled', metadata={
            'native_provider':'disabled','provider_call_performed':None,
            'fixture':True,'historical_bookkeeping_known_limitation':True})
    before = await rows(env)
    await processor(env)._record_costs(render(env, 'rnd_new_disabled'),
        narration={'provider':'disabled','timing':[],'cue_count':0})
    after = await rows(env)
    for table, saved in before.items():
        assert all(row in after[table] for row in saved)
        assert len(after[table]) == len(saved) + 1
    assert [row['provider_key'] for row in after['provider_usage'] if row['capability']=='tts'] == ['espeak']

@pytest.mark.asyncio
async def test_explicit_local_fixture_voice_accounting_is_retained(env):
    await processor(env)._record_costs(render(env, 'rnd_existing_fixture'),
        narration={'provider':'deterministic-wave','timing':[],'cue_count':0})
    saved = await rows(env)
    usage = saved['provider_usage']
    assert len(usage) == 2
    tts = next(row for row in usage if row['capability']=='tts')
    assert tts['provider_key']=='espeak'
    assert tts['metadata_json']['native_provider']=='deterministic-wave'
