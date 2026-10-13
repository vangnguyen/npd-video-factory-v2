"""Actual SQL/Local/ASGI family boundary; explicit evidence fixtures, no AI calls."""
import asyncio
import copy
import hashlib
import json
import os
import subprocess
import shutil
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import select, func

from app.db import AssetORM, VideoProjectORM, ProviderUsageORM
from app.platform_models import WorkspaceCreate, ProjectCreate
from app.sql_variant_db import SqlVariantArtifactReceiptORM, SqlVariantEventORM
from app.sql_variant_models import MasterBinding
from app.sql_variant_api_service import configure_sql_variant_api, register_sql_variant_routes
from app.sql_variant_repository import SqlVariantFamilyRepository, SqlVariantError
from app.sql_variant_derivation_models import DeriveStoryboardRequest
from app.sql_variant_uploaded_models import DeriveUploadedRequest
from app.sql_variant_storyboard_copy import LocalStoryboardCopier
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_sql_variant_family import env, ready, counts
from test_sql_variant_storyboard_derivation import master_rows
from test_sql_variant_uploaded_derivation import uploaded, request as uploaded_request, saved_audio, ingest
from test_mvp1_multi_input import author, timeline


def app_for(env, *, role='editor', uploaded_enabled=False, storage=True):
    app = FastAPI()
    service = configure_sql_variant_api(app, session_factory=env.factory,
        object_storage=env.storage if storage else None, uploaded_enabled=uploaded_enabled)
    install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
                            workspace_roles={env.workspace.workspace_id: role})
    return app, service


def client_for(app):
    return httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://owned-fixture',
                             headers=TEST_HUMAN_HEADERS)


def base(env):
    return f'/api/v1/projects/{env.project.project_id}/variant-families'


def derive_body(family, *, uploaded=False, key='explicit-api-derived-child-01', member=None):
    contract = DeriveUploadedRequest if uploaded else DeriveStoryboardRequest
    return contract(expected_version=family['version'], expected_snapshot_sha256=family['snapshot_sha256'],
        request_key=key, member_id=(member or family['members'][0])['member_id'],
        acknowledge_unapproved_child=True).model_dump(mode='json')


async def api_family(env, client):
    _, payload, _, _, _ = await ready(env)
    response = await client.post(base(env), json=payload.model_dump(mode='json'))
    assert response.status_code == 201, response.text
    return response.json()['family'], payload


class CountBody:
    """Observe actual receive calls, without swallowing/discarding client bytes."""
    def __init__(self, app):
        self.app, self.calls = app, 0
    async def __call__(self, scope, receive, send):
        async def counted():
            self.calls += 1
            return await receive()
        return await self.app(scope, counted, send)


def test_configuration_and_repeated_registration_are_zero_io_and_not_duplicate(monkeypatch):
    from app import sql_variant_api_service as module
    def denied(*args, **kwargs):
        raise AssertionError('No SQL, byte custody or copier construction during configuration')
    monkeypatch.setattr(module, 'LocalStoryboardCopier', denied)
    monkeypatch.setattr(module, 'LocalEvidenceCopier', denied)
    app = FastAPI()
    one = configure_sql_variant_api(app, session_factory=denied)
    route_count = len(app.routes)
    two = configure_sql_variant_api(app, session_factory=denied, register_routes=False)
    register_sql_variant_routes(app)
    assert one is not two and app.state.sql_variant_api_service is two
    assert len(app.routes) == route_count
    # This FastAPI version stores included routers as lazy route containers.
    assert sum(len(value) for value in app.openapi()['paths'].values()) == 7
    schema=app.openapi()['paths']['/api/v1/projects/{project_id}/variant-families/{family_id}/derive']['post']['requestBody']['content']['application/json']['schema']
    assert schema['discriminator']['propertyName']=='schema_version'
    assert {option['properties']['schema_version']['const'] for option in schema['oneOf']}=={
        'sql-variant-storyboard-derive.v1','sql-variant-uploaded-derive.v1'}
    assert all(option['additionalProperties'] is False for option in schema['oneOf'])
    assert '#/$defs/' not in json.dumps(schema)
    assert two.uploaded_enabled is False


@pytest.mark.asyncio
async def test_viewer_gets_actual_availability_saved_family_and_receipt_without_copy_or_mutation(env, monkeypatch):
    app, service = app_for(env)
    async with client_for(app) as client:
        family, _ = await api_family(env, client)
        created = await client.post(base(env) + f"/{family['family_id']}/derive", json=derive_body(family))
        assert created.status_code == 201, created.text
        receipt = created.json()['receipt']
    original = await master_rows(env)
    prior = await counts(env)
    from app import sql_variant_api_service as module
    def no_copier(*args, **kwargs):
        raise AssertionError('GET must not construct a copier or read provider/media bytes')
    monkeypatch.setattr(module, 'LocalStoryboardCopier', no_copier)
    monkeypatch.setattr(module, 'LocalEvidenceCopier', no_copier)
    async def no_download(*args, **kwargs):
        raise AssertionError('GET must never stage bytes')
    monkeypatch.setattr(env.storage, 'download_file', no_download)
    install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
                            workspace_roles={env.workspace.workspace_id: 'viewer'})
    async with client_for(app) as client:
        available = await client.get(base(env) + '/availability')
        assert available.status_code == 200 and available.json()['derivation']['engine'] == 'storyboard'
        listing = await client.get(base(env) + '?limit=1')
        assert listing.status_code == 200 and len(listing.json()['items']) == 1
        current = await client.get(base(env) + f"/{family['family_id']}")
        assert current.status_code == 200 and current.json()['safety']['child_projects_created'] == 1
        read = await client.get(base(env) + f"/{family['family_id']}/receipts/{receipt['receipt_id']}")
        assert read.status_code == 200 and read.json() == receipt
        assert all(r.headers['cache-control'] == 'no-store' for r in (available, listing, current, read))
    assert await counts(env) == prior and await master_rows(env) == original
    assert not env.queue.values and not await env.platform.list_cost_records(env.project.project_id)


@pytest.mark.asyncio
@pytest.mark.parametrize('denial,expected', [('viewer',403), ('no_token',401), ('foreign',404),
    ('api_disabled',503), ('write_disabled',503)])
async def test_write_admission_before_body_and_no_sql_mutation(env, denial, expected):
    await ready(env)
    app, _ = app_for(env, role='viewer' if denial == 'viewer' else 'editor')
    if denial == 'foreign':
        install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
                                workspace_roles={'wsp_unrelated': 'owner'})
    if denial == 'api_disabled':app.state.human_api_enabled = False
    if denial == 'write_disabled':app.state.human_write_enabled = False
    observed = CountBody(app)
    before = await counts(env)
    headers = {} if denial == 'no_token' else TEST_HUMAN_HEADERS
    async with httpx.AsyncClient(transport=httpx.ASGITransport(observed),base_url='http://owned-fixture') as client:
        result = await client.post(base(env), content=b'{private malformed input', headers=headers)
    assert result.status_code == expected and result.headers['cache-control'] == 'no-store'
    assert observed.calls == 0 and await counts(env) == before
    assert 'private' not in result.text


@pytest.mark.asyncio
async def test_foreign_project_family_receipt_and_workspace_are_hidden_before_copy(env):
    app, _ = app_for(env)
    async with client_for(app) as client:
        family, _ = await api_family(env, client)
        result = await client.post(base(env) + f"/{family['family_id']}/derive", json=derive_body(family))
        assert result.status_code == 201
        receipt = result.json()['receipt']
        other = await env.platform.create_project(env.workspace.workspace_id, ProjectCreate(slug='other-api-master',name='Fixture'))
        foreign = await env.platform.create_workspace(WorkspaceCreate(slug='foreign-api',name='Fixture',owner_ref='fixture'))
        outsider = await env.platform.create_project(foreign.workspace_id,ProjectCreate(slug='foreign-master',name='Fixture'))
        prior = await counts(env)
        for project in (other, outsider):
            prefix = f'/api/v1/projects/{project.project_id}/variant-families'
            for suffix in (f"/{family['family_id']}", f"/{family['family_id']}/receipts/{receipt['receipt_id']}"):
                read = await client.get(prefix + suffix)
                assert read.status_code == 404 and read.headers['cache-control'] == 'no-store'
            denied = await client.post(prefix + f"/{family['family_id']}/derive",json=derive_body(family))
            assert denied.status_code == 404
        assert await counts(env) == prior


@pytest.mark.asyncio
async def test_reserve_derive_cancel_replay_cas_verified_actor_and_independent_child(env):
    app, _ = app_for(env)
    async with client_for(app) as client:
        family, payload = await api_family(env, client)
        original = await master_rows(env)
        replay = await client.post(base(env), json=payload.model_dump(mode='json'))
        assert replay.status_code == 201 and replay.json()['replayed'] and replay.json()['family'] == family
        assert family['actor_ref'] == 'usr:test-owner'
        body = derive_body(family)
        created = await client.post(base(env) + f"/{family['family_id']}/derive", json=body)
        assert created.status_code == 201, created.text
        receipt = created.json()['receipt']
        assert receipt['actor_ref'] == 'usr:test-owner' and receipt['state'] == 'ready'
        prior = await counts(env)
        replay = await client.post(base(env) + f"/{family['family_id']}/derive", json=body)
        assert replay.status_code == 201 and replay.json()['receipt'] == receipt and replay.json()['replayed']
        changed = {**body, 'member_id': family['members'][1]['member_id']}
        denied = await client.post(base(env) + f"/{family['family_id']}/derive", json=changed)
        assert denied.status_code == 409 and denied.json()['detail']['error']['code'] == 'SQL_VARIANT_IDEMPOTENCY_CONFLICT'
        current = (await client.get(base(env) + f"/{family['family_id']}")).json()
        stale = await client.post(base(env) + f"/{family['family_id']}/cancel", json=dict(
            expected_version=1, expected_snapshot_sha256=current['snapshot_sha256'], request_key='explicit-api-cancel-stale'))
        assert stale.status_code == 409 and await counts(env) == prior
        cancel_body = dict(expected_version=current['version'], expected_snapshot_sha256=current['snapshot_sha256'],
                           request_key='explicit-api-cancel-ready')
        cancelled = await client.post(base(env) + f"/{family['family_id']}/cancel", json=cancel_body)
        assert cancelled.status_code == 200 and cancelled.json()['family']['state'] == 'cancelled'
        repeated = await client.post(base(env) + f"/{family['family_id']}/cancel", json=cancel_body)
        assert repeated.status_code == 200 and repeated.json()['replayed']
        child = await env.timeline.get_timeline(receipt['result']['child_project_id'])
        assert child.approval_status == 'draft' and child.latest_preview_id is None and child.approved_timeline_version is None
        version = await env.platform.get_version(receipt['result']['content_version_id'])
        assert version.snapshot['content']['approved'] is False
        for old,new in receipt['result']['asset_map'].items():
            source = await env.assets.get_asset(old); copied = await env.assets.get_asset(new)
            assert source.object_key != copied.object_key and copied.provenance['rights_status'] == 'unknown'
            assert env.storage._path(source.object_key).read_bytes() == env.storage._path(copied.object_key).read_bytes()
        assert await master_rows(env) == original and not env.queue.values


@pytest.mark.asyncio
@pytest.mark.parametrize('mutation', ['actor', 'schema', 'false_ack', 'numeric_ack', 'extra', 'duplicate', 'nonfinite', 'query', 'oversize'])
async def test_strict_bodies_never_echo_private_payload_or_claim(env, mutation):
    app, _ = app_for(env)
    async with client_for(app) as client:
        family, _ = await api_family(env, client)
        prior = await counts(env)
        body = derive_body(family)
        url = base(env) + f"/{family['family_id']}/derive"
        expected = 422
        if mutation == 'actor':body['actor_ref'] = 'private-unverified-owner'
        elif mutation == 'schema':body['schema_version'] = 'sql-variant-uploaded-derive.v1'
        elif mutation == 'false_ack':body['acknowledge_unapproved_child'] = False
        elif mutation == 'numeric_ack':body['acknowledge_unapproved_child'] = 1
        elif mutation == 'extra':body['private_path'] = 'private-source'
        if mutation == 'schema':expected = 409
        if mutation == 'query':url += '?actor=private-unverified-owner'
        if mutation == 'oversize':
            response = await client.post(url,content=b' ' * (65536 + 1),headers={'Content-Type':'application/json'});expected = 413
        elif mutation == 'duplicate':
            response = await client.post(url,content=b'{"schema_version":"private","schema_version":"other"}',headers={'Content-Type':'application/json'})
        elif mutation == 'nonfinite':
            response = await client.post(url,content=b'{"private":NaN}',headers={'Content-Type':'application/json'})
        else:response = await client.post(url,json=body)
        assert response.status_code == expected, response.text
        assert 'private' not in response.text and response.headers['cache-control'] == 'no-store'
        assert await counts(env) == prior


@pytest.mark.asyncio
async def test_lost_response_replay_proves_same_receipt_without_a_second_child(env):
    app, _ = app_for(env)
    async with client_for(app) as client:
        family, _ = await api_family(env, client)
    class LoseReply(httpx.AsyncBaseTransport):
        def __init__(self):self.inner=httpx.ASGITransport(app);self.lost=False
        async def handle_async_request(self, request):
            response = await self.inner.handle_async_request(request)
            if not self.lost:
                self.lost=True
                await response.aclose()
                raise httpx.ReadError('explicit fixture lost reply',request=request)
            return response
    async with httpx.AsyncClient(transport=LoseReply(),base_url='http://owned-fixture',headers=TEST_HUMAN_HEADERS) as client:
        body=derive_body(family);url=base(env)+f"/{family['family_id']}/derive"
        with pytest.raises(httpx.ReadError):await client.post(url,json=body)
        before=await counts(env)
        replay=await client.post(url,json=body)
        assert replay.status_code==201 and replay.json()['replayed']
        receipt=replay.json()['receipt'];assert receipt['state']=='ready'
        read=await client.get(base(env)+f"/{family['family_id']}/receipts/{receipt['receipt_id']}")
        assert read.status_code==200 and read.json()==receipt and await counts(env)==before


@pytest.mark.asyncio
async def test_unknown_copy_receipt_is_observed_without_automatic_recopy(env,monkeypatch):
    from app import sql_variant_api_service as module
    class UncertainCopier(LocalStoryboardCopier):
        calls=0
        async def copy(self,items):
            type(self).calls+=1
            await super().copy(items)
            raise SqlVariantError('SQL_VARIANT_COPY_TIMEOUT')
    app,_=app_for(env)
    async with client_for(app) as client:
        family,_=await api_family(env,client);body=derive_body(family)
        monkeypatch.setattr(module,'LocalStoryboardCopier',UncertainCopier)
        failed=await client.post(base(env)+f"/{family['family_id']}/derive",json=body)
        assert failed.status_code==409 and UncertainCopier.calls==1
        before=await counts(env);files={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.storage.root.rglob('*') if p.is_file()}
        replay=await client.post(base(env)+f"/{family['family_id']}/derive",json=body)
        assert replay.status_code==201 and replay.json()['replayed'] and replay.json()['receipt']['state']=='unknown'
        assert UncertainCopier.calls==1 and await counts(env)==before
        assert files=={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in env.storage.root.rglob('*') if p.is_file()}
        assert replay.json()['receipt']['result'] is None


@pytest.mark.asyncio
async def test_concurrent_same_request_observes_pending_and_explicit_cancel_prevents_child_commit(env,monkeypatch):
    from app import sql_variant_api_service as module
    entered,release=asyncio.Event(),asyncio.Event()
    class PausedCopier(LocalStoryboardCopier):
        calls=0
        async def copy(self,items):
            type(self).calls+=1;entered.set()
            await release.wait()
            return await super().copy(items)
    app,_=app_for(env)
    async with client_for(app) as client:
        family,_=await api_family(env,client);body=derive_body(family);url=base(env)+f"/{family['family_id']}/derive"
        monkeypatch.setattr(module,'LocalStoryboardCopier',PausedCopier)
        active=asyncio.create_task(client.post(url,json=body))
        try:
            await asyncio.wait_for(entered.wait(),10)
            observed=await client.post(url,json=body)
            assert observed.status_code==201 and observed.json()['replayed']
            pending=observed.json()['receipt'];assert pending['state']=='pending' and pending['result'] is None
            current=(await client.get(base(env)+f"/{family['family_id']}")).json()
            before=await counts(env)
            cancelled=await client.post(base(env)+f"/{family['family_id']}/cancel",json=dict(
                expected_version=current['version'],expected_snapshot_sha256=current['snapshot_sha256'],
                request_key='explicit-api-cancel-pending'))
            assert cancelled.status_code==200
            release.set();result=await active
            assert result.status_code==409 and PausedCopier.calls==1
            read=await client.get(base(env)+f"/{family['family_id']}/receipts/{pending['receipt_id']}")
            assert read.status_code==200 and read.json()['state']=='cancelled' and read.json()['result'] is None
            assert (await counts(env))['video_projects']==before['video_projects']
            replay=await client.post(url,json=body)
            assert replay.status_code==201 and replay.json()['replayed'] and replay.json()['receipt']['state']=='cancelled'
            assert PausedCopier.calls==1 and not env.queue.values
        finally:
            release.set();await asyncio.gather(active,return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize('change',['source','storage_configuration'])
async def test_changed_source_or_configuration_blocks_before_new_claim(env,change):
    app,service=app_for(env)
    async with client_for(app) as client:
        family,_=await api_family(env,client);before=await counts(env)
        if change=='source':
            current=await env.timeline.get_timeline(env.project.project_id)
            snapshot=current.snapshot.model_copy(deep=True);snapshot.metadata['explicit_change']=True
            await env.timeline.commit_mutation(project_id=env.project.project_id,expected_version=current.current_version,
                snapshot=snapshot,mutation={'type':'explicit-fixture'},actor_ref='fixture-editor')
        else:service.object_storage=None
        denied=await client.post(base(env)+f"/{family['family_id']}/derive",json=derive_body(family))
        assert denied.status_code==409 and await counts(env)==before
        read=await client.get(base(env)+f"/{family['family_id']}")
        assert read.status_code==200 and read.json()['source_current'] is (change!='source')


@pytest.mark.asyncio
async def test_uploaded_disabled_is_configuration_gap_and_saved_read_has_no_copy(env):
    _,family,_,_,_=await uploaded(env)
    app,_=app_for(env)
    before=await counts(env)
    async with client_for(app) as client:
        available=await client.get(base(env)+'/availability')
        assert available.json()['derivation']==dict(schema_version='sql-variant-api-dispatch.v1',engine='uploaded_evidence',
            state='NOT_CONFIGURED',reason_code='SQL_VARIANT_UPLOADED_NOT_CONFIGURED',provider_calls=0,automatic_execution=False)
        denied=await client.post(base(env)+f'/{family.family_id}/derive',json=uploaded_request(family).model_dump(mode='json'))
        assert denied.status_code==503 and await counts(env)==before


@pytest.mark.asyncio
async def test_missing_storage_is_not_configured_and_never_claims_a_copy(env):
    app,_=app_for(env,storage=False)
    async with client_for(app) as client:
        family,_=await api_family(env,client);before=await counts(env)
        available=await client.get(base(env)+'/availability')
        assert available.status_code==200 and available.json()['derivation']['state']=='NOT_CONFIGURED'
        assert available.json()['derivation']['reason_code']=='SQL_VARIANT_STORAGE_NOT_CONFIGURED'
        denied=await client.post(base(env)+f"/{family['family_id']}/derive",json=derive_body(family))
        assert denied.status_code==503 and await counts(env)==before


@pytest.mark.asyncio
@pytest.mark.parametrize('lane',['video','mixed','storyboard_audio'])
async def test_current_bound_graph_dispatch_imports_actual_child_without_new_provider_calls(env,lane):
    if lane=='storyboard_audio':
        families,payload,_,_,built=await ready(env)
        await saved_audio(env,built)
        available=await families.availability(env.workspace.workspace_id,env.project.project_id)
        payload=payload.model_copy(update={'expected_binding_sha256':available.binding_sha256})
        family,_=await families.reserve(env.workspace.workspace_id,env.project.project_id,payload,actor_ref='fixture-editor')
    else:
        families,family,_,_,_=await uploaded(env,mixed=lane=='mixed')
    app,service=app_for(env,uploaded_enabled=True)
    async with client_for(app) as client:
        available=await client.get(base(env)+'/availability')
        assert available.status_code==200 and available.json()['derivation']['engine']=='uploaded_evidence'
        if lane=='storyboard_audio':assert available.json()['availability']['binding']['source_mode']=='storyboard_media'
        denied=await client.post(base(env)+f'/{family.family_id}/derive',json=derive_body(family.model_dump(mode='json')))
        assert denied.status_code==409
        result=await client.post(base(env)+f'/{family.family_id}/derive',json=uploaded_request(family).model_dump(mode='json'))
        assert result.status_code==201,result.text
        receipt=result.json()['receipt'];assert receipt['schema_version']=='sql-variant-uploaded-receipt.v1'
        assert receipt['safety']['provider_calls']==0 and not receipt['safety']['approval_inherited']
        child=await env.timeline.get_timeline(receipt['result']['child_project_id'])
        assert child.approval_status=='draft' and child.latest_preview_id is None
        service.uploaded_enabled=False  # Disabled copying does not conceal historical receipts.
        read=await client.get(base(env)+f'/{family.family_id}/receipts/{receipt["receipt_id"]}')
        assert read.status_code==200 and read.json()==receipt
    assert not env.queue.values
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProviderUsageORM))==0


@pytest.mark.asyncio
async def test_unanalysed_video_core_gate_and_empty_graph_contract_never_fall_back(env):
    from app.content_models import StoryboardScene
    from app.timeline_logic import TimelineEditError
    path=env.tmp/'owned-unanalysed.mp4'
    subprocess.run([shutil.which('ffmpeg'),'-v','error','-f','lavfi','-i','color=s=320x240:r=24:d=1',
        '-c:v','libx264','-threads','1','-pix_fmt','yuv420p',str(path)],check=True,timeout=30)
    asset,_=await ingest(env,path,'video','video/mp4')
    content=await author(env,[StoryboardScene(scene_id='scene_unanalysed_fixture',narration='Explicit supplied footage.',
        media_strategy='user_asset',asset_id=asset.asset_id,source_start=0.,duration_seconds=1.)])
    with pytest.raises(TimelineEditError,match='VIDEO_ANALYSIS_REQUIRED'):
        await timeline(env,content,kind='mixed')
    assert await env.timeline.get_timeline(env.project.project_id) is None
    # The current canonical builder already requires video analysis. Exercise
    # the defensive future/unsupported dispatcher contract as metadata ONLY,
    # without inserting a fabricated mixed timeline, analysis or upload/job.
    env.project=await env.platform.create_project(env.workspace.workspace_id,
        ProjectCreate(slug='dispatcher-contract-master',name='Explicit pure metadata contract fixture'))
    _,_,available,_,_=await ready(env)
    metadata=available.binding.model_dump(mode='json');metadata['source_mode']='mixed'
    hypothetical=MasterBinding.model_validate(metadata)
    app,service=app_for(env,uploaded_enabled=True)
    before=await counts(env)
    status=service.dispatch(hypothetical)
    assert status.state=='UNSUPPORTED' and status.engine=='unsupported'
    assert status.reason_code=='SQL_VARIANT_SOURCE_GRAPH_REQUIRED'
    assert await counts(env)==before


@pytest.mark.asyncio
async def test_capture_actual_asgi_contracts_for_independent_studio_fixture(env):
    app,_=app_for(env)
    _,payload,_,_,_=await ready(env)
    prior=await master_rows(env)
    async with client_for(app) as client:
        availability=await client.get(base(env)+'/availability');assert availability.status_code==200
        reserved=await client.post(base(env),json=payload.model_dump(mode='json'));assert reserved.status_code==201
        family=reserved.json()['family']
        derived=await client.post(base(env)+f"/{family['family_id']}/derive",json=derive_body(family));assert derived.status_code==201,derived.text
        current=await client.get(base(env)+f"/{family['family_id']}");assert current.status_code==200
        page=await client.get(base(env));assert page.status_code==200
    assert await master_rows(env)==prior and not env.queue.values
    target=os.getenv('SQL_VARIANT_API_CAPTURE_PATH')
    if target:
        root=Path(__file__).resolve().parents[3]
        paths=['apps/api/app/sql_variant_api_service.py','apps/api/app/sql_variant_routes.py','apps/api/tests/test_sql_variant_api.py']
        source_sha={name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in paths}
        record=dict(schema_version='sql-variant-family-actual-asgi-fixtures.v1',
            fixture_scope='owned actual SQLite + Local + ASGI; supplied manual script and first-party PNG; no ASR/model/provider/renderer',
            model_results_used=False,provider_calls=0,renderer_calls=0,owner_uat=False,
            workspace_id=env.workspace.workspace_id,master_project_id=env.project.project_id,
            repository_root=str(root),head=subprocess.run(['git','rev-parse','HEAD'],cwd=root,capture_output=True,text=True,check=True).stdout.strip(),
            source_sha256=source_sha,
            dto=dict(availability=availability.json(),reserved_family_mutation=reserved.json(),
                derived_receipt_mutation=derived.json(),current_family=current.json(),page=page.json()))
        with Path(target).open('x',encoding='utf-8',newline='\n') as stream:
            stream.write(json.dumps(record,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        print('ACTUAL_ASGI_DTO_CAPTURE_SHA256='+hashlib.sha256(Path(target).read_bytes()).hexdigest())
