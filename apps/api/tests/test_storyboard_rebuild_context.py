"""Owned SQL/canonical rebuilds; synthetic source fixtures, no production renderer/TTS."""
import asyncio
import copy
import json
import shutil
import subprocess
from pathlib import Path

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select, func

from app.content_models import ContentDocument, ContentSaveRequest
from app.content_routes import router as content_router
from app.db import AssetORM, ProviderUsageORM, VideoProjectORM
from app.human_auth import authorize_human_request
from app.production_models import VoiceConfig
from app.production_logic import validate_reframe_render_profile, ProductionContractError
from app.sql_variant_db import SqlVariantMemberORM
from app.sql_variant_models import canonical
from app.sql_variant_narration_projection import narration_projection, child_cues
from app.sql_variant_narration_proposal import read_narration_proposal
from app.sql_variant_repository import SqlVariantError
from app.timeline_db import TimelineVersionORM
from app.timeline_models import TimelineCreateRequest
from app.timeline_repository import TimelineConflictError
from app.timeline_routes import router as timeline_router
from app.timeline_logic import TimelineEditError
from app.uploaded_audio_repository import UploadedAudioRepository
from app.uploaded_audio_db import UploadedAudioORM
from auth_test_support import install_test_human_auth, TEST_HUMAN_HEADERS
from test_sql_variant_family import env
from test_sql_variant_storyboard_derivation import setup, request, run, master_rows
from test_mvp1_multi_input import author, timeline
from test_sql_variant_narration_reuse import narration_env


def app_for(env):
    app = FastAPI()
    app.state.timeline_service, app.state.content_service = env.service, env.content
    for router in (content_router, timeline_router):
        app.include_router(router, dependencies=[Depends(authorize_human_request)])
    install_test_human_auth(app, platform_repository=env.platform, platform_role=None,
        workspace_roles={env.workspace.workspace_id: 'editor'})
    return app


async def approve(env, child, *, changed_text=None):
    """Explicit fixture-owned image/video rights; never transfers master rights."""
    async with env.factory() as session, session.begin():
        assets = (await session.scalars(select(AssetORM).where(AssetORM.project_id == child))).all()
        for asset in assets:
            if asset.content_type.startswith(('image/', 'video/')):
                asset.provenance = {**asset.provenance, 'rights_status': 'owned', 'explicit_first_party_fixture_decision': True}
                asset.version += 1
    current = await env.content.latest(child)
    document = ContentDocument.model_validate(current.snapshot['content'])
    if changed_text is not None:
        scene = document.scenes[0].model_copy(update={'narration': changed_text})
        document = document.model_copy(update={'scenes': [scene, *document.scenes[1:]]})
    document = document.model_copy(update={'approved': True})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app_for(env)), base_url='http://owned-rebuild',
                                headers=TEST_HUMAN_HEADERS) as client:
        response = await client.put(f'/api/v1/projects/{child}/content', json=ContentSaveRequest(
            expected_content_version_id=current.project_version_id, document=document).model_dump(mode='json'))
    assert response.status_code == 200, response.text
    return await env.platform.get_version(response.json()['project_version_id'])


async def rebuild(env, child, version, expected, kind='storyboard_media'):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app_for(env)), base_url='http://owned-rebuild',
                                headers=TEST_HUMAN_HEADERS) as client:
        response = await client.post(f'/api/v1/projects/{child}/timeline', json=TimelineCreateRequest(
            source_kind=kind, content_version_id=version.project_version_id,
            expected_timeline_version=expected).model_dump(mode='json'))
    assert response.status_code == 201, response.text
    return await env.timeline.get_timeline(child)


async def derived(env):
    families, family, repository, service = await setup(env)
    receipt, _ = await run(env, service, family, request(family))
    child = receipt.result['child_project_id']
    version = await approve(env, child)
    return child, version, receipt


async def versions(env, child):
    return canonical([v.model_dump(mode='json') for v in await env.timeline.list_versions(child)])


async def test_actual_six_child_rebuilds_keep_four_canvases_profiles_and_semantic_clock(env):
    families, family, repository, service = await setup(env)
    master = await master_rows(env)
    ratios = set()
    for index, member in enumerate(family.members):
        current = await families.get(env.workspace.workspace_id, env.project.project_id, family.family_id)
        receipt, _ = await run(env, service, current, request(current, member, f'canvas-child-fixture-{index:02}'))
        child = receipt.result['child_project_id']
        before = await env.timeline.get_timeline(child)
        first = await env.timeline.get_version(before.timeline_id, 1)
        semantic = narration_projection(before.snapshot, child_cues(before.snapshot), VoiceConfig(enabled=True))
        approved = await approve(env, child)
        after = await rebuild(env, child, approved, 1)
        assert (after.snapshot.width, after.snapshot.height, after.snapshot.aspect_ratio, after.snapshot.fps) == (
            member.profile.width, member.profile.height, member.profile.aspect_ratio, before.snapshot.fps)
        assert after.snapshot.metadata['reframe'] == {'aspect_ratio': member.profile.aspect_ratio,
            'fallback': 'center_crop', 'needs_attention': True, 'confidence': None}
        origin = after.snapshot.metadata['sql_variant_derivative']
        assert origin == {'schema_version': 'sql-variant-storyboard-lineage.v1', 'source_type': 'storyboard_variant_derivative',
            'master_project_id': env.project.project_id, 'family_id': family.family_id, 'member_id': member.member_id,
            'approval_inherited': False, 'publishing_enabled': False}
        assert narration_projection(after.snapshot, child_cues(after.snapshot), VoiceConfig(enabled=True)) == semantic
        assert after.approval_status == 'draft' and after.approved_timeline_version is None and after.latest_preview_id is None
        assert (await env.timeline.get_version(before.timeline_id, 1)) == first
        for profile in (member.profile.review_profile, member.profile.final_profile):
            validate_reframe_render_profile(after.snapshot, profile)
        wrong = 'vertical-1080x1920' if member.profile.aspect_ratio != '9:16' else 'landscape-1920x1080'
        with pytest.raises(ProductionContractError):
            validate_reframe_render_profile(after.snapshot, wrong)
        for track in after.snapshot.tracks:
            for clip in track.clips:
                assert 'reframe' not in clip.metadata and 'measured_source_words' not in clip.metadata
        assert after.current_version == 2 and after.source_content_version_id == approved.project_version_id
        ratios.add(after.snapshot.aspect_ratio)
    assert ratios == {'16:9', '9:16', '1:1', '4:5'}
    assert await master_rows(env) == master and env.queue.values == []
    async with env.factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProviderUsageORM)) == 0


async def test_ordinary_default_rebuild_is_idempotent_and_carries_no_new_origin_or_attention(env):
    version = await author(env)
    await timeline(env, version)
    original = await env.timeline.get_timeline(env.project.project_id)
    same = await timeline(env, version)
    assert same == original and same.current_version == 1
    assert 'sql_variant_derivative' not in same.snapshot.metadata and 'reframe' not in same.snapshot.metadata
    assert (same.snapshot.width, same.snapshot.height, same.snapshot.aspect_ratio) == (1080, 1920, '9:16')


async def test_own_modified_canvas_survives_but_clip_crop_tracking_and_approval_metadata_do_not(env):
    child, version, receipt = await derived(env)
    before = await env.timeline.get_timeline(child)
    modified = before.snapshot.model_copy(deep=True)
    modified.width, modified.height, modified.aspect_ratio, modified.fps = 1080, 1350, '4:5', 24.
    modified.metadata.update(reframe={'aspect_ratio': '4:5', 'plan_id': 'old_plan', 'affected_clip_ids': ['old_clip']},
        approval={'owner_accepted': True}, uploaded_audio_bindings_v1={'old': {'claimed_word_timings': [1, 2]}})
    modified.tracks[0].clips[0].metadata['reframe'] = {'keyframes': [{'time': 99, 'x': .1}], 'plan_id': 'stale'}
    await env.timeline.commit_mutation(project_id=child, expected_version=1, snapshot=modified,
        mutation={'type': 'explicit-fixture-canvas-edit'}, actor_ref='fixture-editor')
    after = await rebuild(env, child, version, 2)
    assert (after.snapshot.width, after.snapshot.height, after.snapshot.aspect_ratio, after.snapshot.fps) == (1080, 1350, '4:5', 24.)
    assert set(after.snapshot.metadata['reframe']) == {'aspect_ratio', 'fallback', 'needs_attention', 'confidence'}
    for key in ('approval', 'uploaded_audio_bindings_v1', 'narration_reflow'):
        assert key not in after.snapshot.metadata
    assert all('reframe' not in clip.metadata for track in after.snapshot.tracks for clip in track.clips)


async def test_current_version_change_while_builder_waits_is_rejected_even_for_same_rebuild(env, monkeypatch):
    child, version, _ = await derived(env)
    import app.storyboard_timeline as builder
    original = builder.build_storyboard
    entered, release = asyncio.Event(), asyncio.Event()
    async def pause(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        return result
    monkeypatch.setattr(builder, 'build_storyboard', pause)
    running = asyncio.create_task(env.service.create(child, TimelineCreateRequest(source_kind='storyboard_media',
        content_version_id=version.project_version_id, expected_timeline_version=1)))
    await asyncio.wait_for(entered.wait(), 10)
    current = await env.timeline.get_timeline(child)
    changed = current.snapshot.model_copy(deep=True)
    changed.width, changed.height, changed.aspect_ratio = 1080, 1080, '1:1'
    changed.metadata['reframe'] = {'aspect_ratio': '1:1'}
    committed = await env.timeline.commit_mutation(project_id=child, expected_version=1, snapshot=changed,
        mutation={'type': 'explicit-concurrent-fixture-canvas'}, actor_ref='fixture-editor')
    committed = await env.timeline.get_timeline(child)
    history = await versions(env, child)
    release.set()
    with pytest.raises(TimelineConflictError):
        await running
    assert await env.timeline.get_timeline(child) == committed and await versions(env, child) == history


@pytest.mark.parametrize('field', ['ratio', 'reframe', 'canonical_origin', 'project_origin', 'relationship'])
async def test_malformed_canvas_or_origin_does_not_build_or_overwrite_history(env, monkeypatch, field):
    child, version, receipt = await derived(env)
    current = await env.timeline.get_timeline(child)
    async with env.factory() as session, session.begin():
        row = await session.get(TimelineVersionORM, current.current_version_id)
        snapshot = copy.deepcopy(row.snapshot_json)
        if field == 'ratio':
            snapshot['width'] = 1080
        if field == 'reframe':
            snapshot['metadata']['reframe']['aspect_ratio'] = '4:5'
        if field == 'canonical_origin':
            snapshot['metadata']['sql_variant_derivative']['master_project_id'] = 'prj_foreign_fixture'
        if field == 'project_origin':
            project = await session.get(VideoProjectORM, child)
            project.provenance = {**project.provenance, 'family_id': 'vfa_' + 'a' * 32}
        if field == 'relationship':
            member = await session.get(SqlVariantMemberORM, receipt.member_id)
            member.child_project_id = None
        row.snapshot_json = snapshot
    import app.storyboard_timeline as builder
    async def deny(*args, **kwargs):
        pytest.fail('Invalid source context must reject before builder IO')
    monkeypatch.setattr(builder, 'build_storyboard', deny)
    history = await versions(env, child)
    with pytest.raises(TimelineEditError, match='STORYBOARD_REBUILD_(CANVAS|ORIGIN)_INVALID'):
        await env.service.create(child, TimelineCreateRequest(source_kind='storyboard_media',
            content_version_id=version.project_version_id, expected_timeline_version=1))
    assert await versions(env, child) == history


async def test_changed_child_script_keeps_canvas_but_old_narration_receipt_and_new_proposal_cannot_authorize_it(narration_env):
    f = narration_env
    receipt, _ = await f.service.reuse(f.env.workspace.workspace_id, f.env.project.project_id,
        f.family.family_id, f.request, actor_ref='fixture-editor')
    assert receipt.state == 'ready'
    immutable = receipt.model_dump(mode='json')
    before = await f.env.timeline.get_timeline(f.child.project_id)
    version = await approve(f.env, f.child.project_id, changed_text='Lời đọc mới cần duyệt nguồn riêng.')
    after = await rebuild(f.env, f.child.project_id, version, 1)
    assert (after.snapshot.width, after.snapshot.height, after.snapshot.aspect_ratio) == (
        before.snapshot.width, before.snapshot.height, before.snapshot.aspect_ratio)
    assert child_cues(after.snapshot)[0].text != child_cues(before.snapshot)[0].text
    async with f.env.factory() as session:
        with pytest.raises(SqlVariantError, match='CHILD_NOT_CURRENT'):
            await f.repo._capture(session, f.env.workspace.workspace_id, f.env.project.project_id,
                f.family.family_id, f.request, lock=False, actor_ref='fixture-editor')
    with pytest.raises(SqlVariantError, match='SEMANTICS_CHANGED'):
        await read_narration_proposal(f.repo, f.env.workspace.workspace_id, f.env.project.project_id,
            f.family.family_id, f.child.project_id, actor_ref='fixture-editor')
    assert (await f.repo.get(f.env.workspace.workspace_id, f.env.project.project_id, f.family.family_id, receipt.receipt_id)).model_dump(mode='json') == immutable


async def test_mixed_import_keeps_exact_historic_origin_and_old_audio_receipt_verification(env, tmp_path):
    """Existing fixture encodes owned color/sine media, never invokes the production renderer."""
    from test_sql_variant_uploaded_derivation import uploaded, request as uploaded_request
    families, family, repository, service, analysis = await uploaded(env, audio=True, mixed=True, reviewed_audio=True)
    receipt, _ = await service.derive(env.workspace.workspace_id, env.project.project_id, family.family_id,
        uploaded_request(family), actor_ref='fixture-editor')
    child = receipt.result['child_project_id']
    version = await approve(env, child)
    before = await env.timeline.get_timeline(child)
    async with env.factory() as session:
        audio = await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id == child))
    audio_before = (await UploadedAudioRepository(env.factory).get(child, audio.audio_id)).model_dump(mode='json')
    asset = await env.assets.get_asset(audio.asset_id)
    origin = canonical(before.snapshot.metadata['sql_variant_derivative'])
    after = await rebuild(env, child, version, before.current_version, 'mixed')
    assert canonical(after.snapshot.metadata['sql_variant_derivative']) == origin
    assert (after.snapshot.width, after.snapshot.height, after.snapshot.aspect_ratio) == (before.snapshot.width, before.snapshot.height, before.snapshot.aspect_ratio)
    assert 'uploaded_audio_bindings_v1' not in after.snapshot.metadata
    audio_after = (await UploadedAudioRepository(env.factory).get(child, audio.audio_id)).model_dump(mode='json')
    assert audio_after['original'] == audio_before['original'] and audio_after['current'] == audio_before['current']
    node = shutil.which('node')
    assert node, 'The existing Studio receipt verification requires local Node, no external wire'
    root = Path(__file__).resolve().parents[3]
    payload = tmp_path / 'historic-source-receipt.json'
    payload.write_text(json.dumps({'before': before.model_dump(mode='json'), 'after': after.model_dump(mode='json'),
        'asset': asset.model_dump(mode='json'), 'receipt': receipt.model_dump(mode='json')}, ensure_ascii=False), encoding='utf8')
    script = tmp_path / 'verify-historic-source-receipt.mjs'
    script.write_text("import {readFileSync} from 'node:fs';import assert from 'node:assert/strict';import {webcrypto} from 'node:crypto';\n"
        + "const {verifyVariantReceipt,verifiedVariantReceipt,variantReceiptPath}=await import(process.argv[3]);\n"
        + "const v=JSON.parse(readFileSync(process.argv[2],'utf8'));const s=t=>({workspaceId:t.workspace_id,projectId:t.project_id,timeline:t,assets:[v.asset]});\n"
        + "const before=s(v.before),after=s(v.after);assert.equal(variantReceiptPath(before,v.asset),variantReceiptPath(after,v.asset));\n"
        + "const proof=await verifyVariantReceipt(v.receipt,before,v.asset,webcrypto);after.verifiedVariantReceipts=[proof];\n"
        + "assert.equal(verifiedVariantReceipt(after,v.asset).receipt_id,v.receipt.receipt_id);console.log('HISTORIC_RECEIPT_REVERIFIED_NO_AUTHORITY_TRANSFER');\n", encoding='utf8')
    result = subprocess.run([node, str(script), str(payload), (root / 'apps/studio-web/verified-variant-source.mjs').as_uri()],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert 'HISTORIC_RECEIPT_REVERIFIED' in result.stdout
