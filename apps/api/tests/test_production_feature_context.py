"""Owned render/analytics state: subsequent metadata edits cannot relabel media."""
import json

import pytest
from sqlalchemy import select

from app.db import VideoProjectORM
from app.platform_models import ProjectVersionCreate
from app.production_db import ProductionRenderJobORM
from app.production_features import read, retain
from app.production_models import ProductionPackageCreateRequest, RenderCreateRequest
from app.timeline_db import TimelineVersionORM
from test_audio_subtitle_render_qc import setup_stack
from test_analytics_runtime import runtime_stack, reserve


async def queued(stack, snapshot=None):
    version = await stack.platform.create_version(stack.project.project_id, ProjectVersionCreate(snapshot=snapshot or {
        'topic': 'Original education topic', 'source_idea': {'hook_concept': 'Original hook',
            'cta_concept': 'Original CTA', 'visual_concept': 'Original visual'}}))
    package = await stack.service.create_or_refresh(stack.project.project_id,
        ProductionPackageCreateRequest(expected_timeline_version=1))
    render = await stack.service.enqueue_review(stack.project.project_id, RenderCreateRequest(
        expected_timeline_version=1, expected_subtitle_version=package.subtitle.version,
        expected_audio_version=package.audio_mix.version))
    return version, render


@pytest.mark.asyncio
async def test_queued_context_survives_completion_later_edit_and_physical_evidence(tmp_path):
    stack = await setup_stack(tmp_path)
    try:
        version, render = await queued(stack)
        original = render.manifest['feature_context']
        await stack.platform.create_version(stack.project.project_id,
            ProjectVersionCreate(snapshot={'topic': 'Later unrelated topic'}))
        async with stack.repository.session_factory() as session:
            project = await session.get(VideoProjectORM, stack.project.project_id)
            project.niche = 'technology'; await session.commit()
        completed = await stack.processor.process(render.render_id)
        assert completed.status == 'awaiting_review'
        context = read(completed.manifest, workspace=stack.project.workspace_id,
            project=stack.project.project_id, timeline_version=render.timeline_version_id)
        assert context.project_version_id == version.project_version_id and context.niche == 'real_estate'
        assert context.topic == 'Original education topic' and context.cta == 'Original CTA'
        assert context.hook_type == 'Original hook' and completed.manifest['feature_context'] == original
        asset = await stack.asset_repository.get_asset(completed.manifest['supporting_asset_ids']['render-evidence'])
        exported_path = tmp_path / 'owned-render-evidence-copy.json'
        await stack.storage.download_file(object_key=asset.object_key, destination=exported_path)
        exported = json.loads(exported_path.read_text(encoding='utf-8'))
        assert asset.project_version_id == version.project_version_id
        assert exported['feature_context'] == original
        restarted = type(stack.repository)(stack.repository.session_factory)
        assert (await restarted.get_render(render.render_id)).manifest['feature_context'] == original
    finally: await stack.engine.dispose()


@pytest.mark.asyncio
async def test_bound_content_version_overrides_later_project_version(tmp_path):
    stack = await setup_stack(tmp_path)
    try:
        old = await stack.platform.create_version(stack.project.project_id, ProjectVersionCreate(snapshot={'topic': 'Bound old content'}))
        async with stack.repository.session_factory() as session:
            timeline = await session.get(TimelineVersionORM, stack.timeline.current_version_id)
            timeline.snapshot_json = {**timeline.snapshot_json, 'metadata': {
                **timeline.snapshot_json.get('metadata', {}), 'content_version_id': old.project_version_id}}
            await session.commit()
        later, render = await queued(stack, {'topic': 'New unrelated content'})
        context = read(render.manifest, workspace=stack.project.workspace_id, project=stack.project.project_id,
            timeline_version=render.timeline_version_id)
        assert context.source_content_version_id == context.project_version_id == old.project_version_id
        assert context.project_version_id != later.project_version_id and context.topic == 'Bound old content'
    finally: await stack.engine.dispose()


@pytest.mark.asyncio
async def test_completion_cannot_replace_context_or_commit_partial_render(tmp_path):
    stack = await setup_stack(tmp_path)
    try:
        _, render = await queued(stack)
        wrong = {**render.manifest, 'feature_context': {**render.manifest['feature_context'], 'topic': 'replacement'}}
        with pytest.raises(ValueError, match='REPLACEMENT_REFUSED'):
            await stack.repository.complete_render(render.render_id, output_asset_id=stack.asset.asset_id,
                qc_report={'status': 'passed', 'fixture_only': True}, manifest=wrong)
        saved = await stack.repository.get_render(render.render_id)
        assert saved.status == 'queued' and saved.output_asset_id is None and saved.manifest == render.manifest
        assert retain({'renderer': 'finished'}, render.manifest)['feature_context'] == render.manifest['feature_context']
        for arguments in ({'workspace': 'wsp_foreign', 'project': render.project_id, 'timeline_version': render.timeline_version_id},
            {'workspace': render.workspace_id, 'project': 'prj_foreign', 'timeline_version': render.timeline_version_id},
            {'workspace': render.workspace_id, 'project': render.project_id, 'timeline_version': 'tlv_foreign'}):
            with pytest.raises(ValueError, match='SCOPE_OR_HASH_MISMATCH'): read(render.manifest, **arguments)
        with pytest.raises(ValueError, match='SCOPE_OR_HASH_MISMATCH'):
            read(wrong, workspace=render.workspace_id, project=render.project_id, timeline_version=render.timeline_version_id)
    finally: await stack.engine.dispose()


@pytest.mark.asyncio
async def test_official_collection_uses_original_niche_without_current_topic_fallback(runtime_stack):
    stack, _, _, calls, _, _ = runtime_stack
    original = await stack.production.repository.get_render(stack.publication.final_render_id)
    await stack.production.platform.create_version(stack.publication.project_id,
        ProjectVersionCreate(snapshot={'topic': 'Later unrelated learning label', 'source_idea': {'hook_concept': 'Later hook'}}))
    async with stack.repository.session_factory() as session:
        project = await session.get(VideoProjectORM, stack.publication.project_id)
        project.niche = 'technology'; await session.commit()
    sync = await reserve(stack, 'frozen-project-metadata'); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'succeeded' and len(calls) == 3
    features = (await stack.repository.report(sync.project_id)).video_features
    assert features.niche == original.manifest['feature_context']['niche'] == 'real_estate'
    assert features.topic is None and features.hook_type is None
    assert features.evidence['project_metadata_source'] == 'published_render_request_context'
    assert features.evidence['feature_context_sha256'] == original.manifest['feature_context_sha256']
    assert features.publishing_time is None


@pytest.mark.asyncio
async def test_legacy_render_keeps_missing_metadata_null_after_new_project_edits(runtime_stack):
    stack, _, _, _, _, _ = runtime_stack
    async with stack.repository.session_factory() as session:
        row = await session.get(ProductionRenderJobORM, stack.publication.final_render_id)
        row.manifest_json = {key: value for key, value in row.manifest_json.items() if key not in ('feature_context', 'feature_context_sha256')}
        await session.commit()
    await stack.production.platform.create_version(stack.publication.project_id,
        ProjectVersionCreate(snapshot={'topic': 'New tag must not backfill old media'}))
    sync = await reserve(stack, 'legacy-project-metadata'); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'succeeded'
    features = (await stack.repository.report(sync.project_id)).video_features
    assert features.topic is features.niche is features.cta is features.hook_type is None
    assert features.evidence['project_metadata_source'] == 'unavailable_legacy_render'
    assert features.duration_seconds is not None and features.publishing_time is None
