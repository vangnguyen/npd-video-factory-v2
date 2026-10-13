"""Local ASR configuration truth without decoding/model inference/network."""
import copy
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.auto_edit_providers import ContractOnlyTranscriptionProvider
from app.config import Settings
from app.db import Base, ProviderRegistryORM, create_engine
from app.human_auth import authorize_human_request
from app.human_identity import HumanAuthRegistry
from app.provider_safety import ProviderSafetyController, normalize_provider_definitions
from app.provider_safety_routes import router
from app.uploaded_audio_runtime import provider_from_settings
import app.main as main_module
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS


def settings_for(root):
    fields=('job_storage_root','asset_storage_root','object_storage_local_root','upload_staging_root',
        'analysis_staging_root','vision_staging_root','media_staging_root','preview_staging_root',
        'preview_download_root','production_render_staging_root','production_render_download_root','stock_cache_root')
    auth=root/'empty-human-keys.json'
    auth.write_text(HumanAuthRegistry(version=1).model_dump_json(),encoding='utf-8')
    return Settings(_env_file=None,transcription_provider='local_cpu',local_asr_enabled=True,
        local_asr_runtime_manifest=root/'missing-runtime.json',local_asr_runtime_manifest_sha256='a'*64,
        ffmpeg_path=str(root/'missing-decoder.exe'),local_asr_decoder_sha256='b'*64,
        database_url='sqlite+aiosqlite:///'+str(root/'registry.sqlite').replace('\\','/'),
        contracts_root=Path(__file__).resolve().parents[3]/'packages/contracts',
        human_auth_keys_file=auth,
        **{name:root/name for name in fields})


def row(definitions):
    return next(value for value in definitions if value['provider_key']=='local-faster-whisper')


@pytest.mark.asyncio
async def test_invalid_owned_runtime_and_unsupplied_instance_remain_not_configured(tmp_path,monkeypatch):
    settings=settings_for(tmp_path);monkeypatch.setattr(main_module,'settings',settings)
    actual=provider_from_settings(settings)
    assert actual.key=='transcription-not-configured'
    for provider in (None,actual,SimpleNamespace(key='local-faster-whisper',external_call=True,paid=False)):
        definitions=normalize_provider_definitions(main_module._provider_definitions(provider))
        selected=row(definitions)
        assert not selected['enabled'] and selected['status']=='not_configured' and selected['routing_mode']=='disabled'
        assert selected['metadata']['runtime_configured'] is False
        snapshot=await ProviderSafetyController.fail_closed(definitions).snapshot()
        state=next(value for value in snapshot.providers if value.provider_key=='local-faster-whisper')
        assert not state.enabled and not state.production_eligible


@pytest.mark.asyncio
async def test_configured_stub_is_unverified_and_definition_reads_never_reinstantiate(tmp_path,monkeypatch):
    monkeypatch.setattr(main_module,'settings',settings_for(tmp_path))
    calls=[]
    def forbidden_factory(_settings):calls.append('unexpected_runtime_hash');raise AssertionError('SECOND_FACTORY_NOT_ALLOWED')
    monkeypatch.setattr(main_module,'uploaded_audio_provider',forbidden_factory)
    configured=SimpleNamespace(key='local-faster-whisper',external_call=False,paid=False)
    for _ in range(3):
        definitions=normalize_provider_definitions(main_module._provider_definitions(configured));selected=row(definitions)
        assert selected['enabled'] and selected['status']=='degraded' and selected['routing_mode']=='primary'
        assert selected['metadata']['runtime_configured'] is True
        assert selected['metadata']['provider_health_verified'] is False and selected['metadata']['semantic_quality_verified'] is False
        assert selected['metadata']['production_acceptance_required'] is True and selected['metadata']['production_acceptance_verified'] is False
        assert not next(value for value in (await ProviderSafetyController.fail_closed(definitions).snapshot()).providers
            if value.provider_key=='local-faster-whisper').production_eligible
    assert not calls


@pytest.mark.asyncio
@pytest.mark.parametrize('configured',[False,True])
async def test_actual_isolated_lifespan_seeds_same_selected_instance_once_and_get_does_not_hash(tmp_path,monkeypatch,configured):
    settings=settings_for(tmp_path);monkeypatch.setattr(main_module,'settings',settings)
    engine=create_engine(settings.database_url)
    async with engine.begin() as connection:await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(main_module,'create_engine',lambda _url:engine)
    class RedisFixture:
        closed=False
        async def aclose(self):self.closed=True
    redis=RedisFixture();monkeypatch.setattr(main_module.Redis,'from_url',lambda *_args,**_kwargs:redis)
    selected=SimpleNamespace(key='local-faster-whisper',external_call=False,paid=False,estimated_cost_vnd=Decimal('0')) \
        if configured else ContractOnlyTranscriptionProvider()
    calls=[];seeds=[]
    def factory(actual_settings):
        assert actual_settings is settings;calls.append('one_explicit_fixture_runtime_selection');return selected
    monkeypatch.setattr(main_module,'uploaded_audio_provider',factory)
    original_seed=main_module.PlatformRepository.seed_providers
    async def tracked_seed(repository,definitions):
        assert calls==['one_explicit_fixture_runtime_selection']
        seeds.append(copy.deepcopy(row(definitions)))
        await original_seed(repository,definitions)
    monkeypatch.setattr(main_module.PlatformRepository,'seed_providers',tracked_seed)
    fixture_app=FastAPI();fixture_app.include_router(router,dependencies=[Depends(authorize_human_request)])
    fixture_app.add_api_route('/api/v1/capabilities',main_module.capabilities,dependencies=[Depends(authorize_human_request)])
    monkeypatch.setattr(main_module,'app',fixture_app)
    try:
        async with main_module.lifespan(fixture_app):
            assert fixture_app.state.uploaded_audio_service.provider is selected
            assert len(seeds)==1 and seeds[0]['enabled']==configured
            async with fixture_app.state.database_session_factory() as session:
                saved=await session.scalar(select(ProviderRegistryORM).where(ProviderRegistryORM.provider_key=='local-faster-whisper'))
                assert saved.enabled==configured and saved.status==('degraded' if configured else 'not_configured')
                assert saved.metadata_json['runtime_configured']==configured
            install_test_human_auth(fixture_app)
            async with AsyncClient(transport=ASGITransport(fixture_app),base_url='http://owned-local-registry') as client:
                for _ in range(2):
                    snapshot=await client.get('/api/v1/provider-safety',headers=TEST_HUMAN_HEADERS)
                    capabilities=await client.get('/api/v1/capabilities',headers=TEST_HUMAN_HEADERS)
                    assert snapshot.status_code==capabilities.status_code==200
                    observed=next(value for value in snapshot.json()['providers'] if value['provider_key']=='local-faster-whisper')
                    assert observed['enabled']==configured and not observed['production_eligible']
            assert calls==['one_explicit_fixture_runtime_selection']
        assert redis.closed
    finally:await engine.dispose()
