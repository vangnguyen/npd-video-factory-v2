"""Actual isolated bootstrap + synthetic ledger events. No TTS/server/model use."""
from decimal import Decimal

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.config import Settings
from app.db import Base, CostRecordORM, ProviderRegistryORM, ProviderUsageORM, create_engine
from app.human_auth import authorize_human_request
from app.platform_models import ProjectCreate
from app.provider_safety import ProviderSafetyController, normalize_provider_definitions
from app.provider_safety_routes import router
import app.main as main_module
import app.vieneu_contracts as contracts
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_local_asr_registry import settings_for


def row(definitions):
    return next(value for value in definitions if value['provider_key']=='vieneu-tts' and value['capability']=='tts')


@pytest.mark.asyncio
@pytest.mark.parametrize('changes,enabled',[
    ({},False),
    ({'audio_tts_provider':'vieneu'},False),
    ({'audio_tts_provider':'vieneu','vieneu_local_execution_enabled':True,'vieneu_voice_id':'Mai Anh'},False),
    ({'audio_tts_provider':'espeak','vieneu_local_execution_enabled':True},False),
    ({'audio_tts_provider':'vieneu','vieneu_local_execution_enabled':True},True),
])
async def test_public_selection_metadata_always_registers_vieneu_without_runtime_or_secret_access(monkeypatch,changes,enabled):
    # Explicit empty key avoids ambient credential selection; no adapter imports
    # or calls are needed for either configured or disabled registry definitions.
    if changes.get('audio_tts_provider')=='espeak' and changes.get('vieneu_local_execution_enabled') is True:
        with pytest.raises(ValueError,match='VIENEU_LOCAL_AUDITION_ONLY'):
            Settings(_env_file=None,openai_api_key='',**changes)
        # Simulate an unsafe in-process DTO mutation as an additional registry
        # guard, without weakening the actual configuration validator.
        settings=Settings(_env_file=None,openai_api_key='').model_copy(update=changes)
    else:
        settings=Settings(_env_file=None,openai_api_key='',**changes)
    monkeypatch.setattr(main_module,'settings',settings)
    definitions=normalize_provider_definitions(main_module._provider_definitions());selected=row(definitions)
    assert selected['enabled']==enabled and selected['status']==('degraded' if enabled else 'not_configured')
    assert selected['routing_mode']==('primary' if enabled else 'disabled') and selected['supports_dry_run'] is False
    metadata=selected['metadata']
    assert metadata['selection_configured']==enabled and metadata['configuration_only'] is True
    for flag in ('provider_health_verified','runtime_custody_verified','semantic_quality_verified',
        'production_acceptance_verified','human_voice_accepted','production_deployed'):
        assert metadata[flag] is False
    assert metadata['production_acceptance_required'] is True and metadata['rights_status']=='unknown'
    assert metadata['selected_candidate_profile_sha256']==(contracts.SELECTED_PROFILE_SHA if enabled else None)
    observed=next(value for value in (await ProviderSafetyController.fail_closed(definitions).snapshot()).providers
        if value.provider_key=='vieneu-tts')
    assert observed.enabled==enabled and observed.execution_class=='local' and observed.paid is False
    assert not observed.production_eligible


def test_selected_public_profile_drift_disables_row_without_constructing_provider(tmp_path,monkeypatch):
    del tmp_path
    settings=Settings(_env_file=None,openai_api_key='',audio_tts_provider='vieneu',vieneu_local_execution_enabled=True)
    monkeypatch.setattr(main_module,'settings',settings)
    def changed():raise ValueError('EXPLICIT FIXTURE PROFILE CONTRACT DRIFT')
    monkeypatch.setattr(contracts,'selected_vieneu_profile',changed)
    selected=row(main_module._provider_definitions())
    assert not selected['enabled'] and selected['status']=='not_configured'
    assert selected['metadata']['selected_candidate_profile_sha256'] is None


@pytest.mark.asyncio
@pytest.mark.parametrize('configured',[False,True])
async def test_actual_lifespan_seeds_vieneu_and_accepts_synthetic_cost_operation_without_manual_provider_seed(tmp_path,monkeypatch,configured):
    settings=settings_for(tmp_path).model_copy(update={'transcription_provider':'contract','local_asr_enabled':False,
        'audio_tts_provider':'vieneu' if configured else 'espeak','vieneu_local_execution_enabled':configured,
        'openai_api_key':''})
    monkeypatch.setattr(main_module,'settings',settings)
    engine=create_engine(settings.database_url)
    async with engine.begin() as connection:await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(main_module,'create_engine',lambda _url:engine)
    class RedisFixture:
        closed=False
        async def aclose(self):self.closed=True
    redis=RedisFixture();monkeypatch.setattr(main_module.Redis,'from_url',lambda *_args,**_kwargs:redis)
    fixture_app=FastAPI();fixture_app.include_router(router,dependencies=[Depends(authorize_human_request)])
    try:
        async with main_module.lifespan(fixture_app):
            async with fixture_app.state.database_session_factory() as session:
                saved=await session.scalar(select(ProviderRegistryORM).where(
                    ProviderRegistryORM.provider_key=='vieneu-tts',ProviderRegistryORM.capability=='tts'))
                assert saved is not None and saved.enabled==configured
                assert saved.status==('degraded' if configured else 'not_configured')
            install_test_human_auth(fixture_app)
            async with AsyncClient(transport=ASGITransport(fixture_app),base_url='http://owned-vieneu-registry') as client:
                reply=await client.get('/api/v1/provider-safety',headers=TEST_HUMAN_HEADERS)
                assert reply.status_code==200
                observed=next(value for value in reply.json()['providers'] if value['provider_key']=='vieneu-tts')
                assert observed['enabled']==configured and observed['production_eligible'] is False
            platform=fixture_app.state.platform_repository
            project=await platform.create_project(fixture_app.state.default_workspace_id,
                ProjectCreate(slug='synthetic-vieneu-meter',name='EXPLICIT SYNTHETIC REGISTRY LEDGER CONTRACT'))
            arguments={'workspace_id':project.workspace_id,'project_id':project.project_id,'job_id':None,
                'provider_key':'vieneu-tts','capability':'tts','operation':'fixture-only.registry-bootstrap.v1',
                'model':'vieneu-v3-turbo','units':Decimal('0'),'unit_name':'provider_calls',
                'estimated_cost':None,'actual_cost':None,'max_cost_vnd':Decimal('0'),
                'metadata':{'fixture':True,'provider_calls':0,'provider_call_performed':False,'model_inferences':0,
                    'real_provider_tested':False,'synthetic_ledger_contract_only':True,'human_quality_accepted':False}}
            usage,cost=await platform.record_provider_operation(**arguments)
            replay_usage,replay_cost=await platform.record_provider_operation(**arguments)
            assert usage.usage_id==replay_usage.usage_id and cost.cost_id==replay_cost.cost_id
            assert usage.provider_key=='vieneu-tts' and usage.units==0 and usage.metadata['provider_calls']==0
            assert cost.estimated_cost is None and cost.actual_cost is None and cost.needs_approval and not cost.approved
            async with fixture_app.state.database_session_factory() as session:
                assert await session.scalar(select(func.count()).select_from(ProviderUsageORM))==1
                assert await session.scalar(select(func.count()).select_from(CostRecordORM))==1
        assert redis.closed
    finally:await engine.dispose()
