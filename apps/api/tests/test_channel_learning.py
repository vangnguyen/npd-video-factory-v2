"""Owned synthetic histories; neither metrics nor feature labels are real-provider evidence."""
import hashlib
from datetime import timedelta
from types import SimpleNamespace

import httpx
import pytest
from fastapi import Depends
from pydantic import ValidationError
from sqlalchemy import select

from app.analytics_cohort import WinnerChannelPolicy, assess_channel, values
from app.analytics_db import AnalyticsFeatureSnapshotORM, WinnerAssessmentORM
from app.analytics_models import AnalyticsSyncRequest, NormalizedMetrics
from app.analytics_providers import AnalyticsCollection
from app.db import utc_now
from app.human_auth import authorize_human_request
from app.learning_db import ChannelLearningSnapshotORM
from app.learning_models import DIMENSIONS, LearningCreate, LearningObservation, LearningPolicy, aggregate
from app.learning_routes import router
from app.learning_service import ChannelLearningService, LearningError
from app.production_db import ProductionRenderJobORM
from app.production_features import RenderFeatureContext, digest as feature_digest
from app.publishing_credentials import target_digest
from app.publishing_db import PublicationORM
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_publication_api import application
from test_analytics_runtime import runtime_stack, reserve


def observation(index, feature='question', score=85):
    return LearningObservation(snapshot_id=f'ams_learning_fixture_{index}', publication_id=f'pub_learning_fixture_{index}',
        assessment_id=f'awa_learning_fixture_{index}', render_id=f'ren_learning_fixture_{index}', timeline_version_id='tlv_learning_fixture',
        feature_context_sha256='a' * 64, remote_post_sha256=hashlib.sha256(str(index).encode()).hexdigest(),
        collected_at=utc_now(), score=score, winner_policy_sha256='b' * 64, assessment_basis_sha256='c' * 64,
        features={name: feature if name == 'hook' else None for name in DIMENSIONS})


@pytest.mark.parametrize('invalid', [dict(minimum_group_posts=True), dict(minimum_group_posts=2),
    dict(minimum_group_posts=50, minimum_control_posts=50, maximum_posts=6),
    dict(minimum_score_difference=True), dict(minimum_score_difference=float('nan'))])
def test_policy_rejects_ambiguous_or_insufficient_sample_limits(invalid):
    with pytest.raises(ValidationError): LearningPolicy.model_validate(invalid)


def test_group_requires_distinct_comparison_posts_and_reports_only_descriptive_association():
    rows = [observation(i) for i in range(3)] + [observation(i, 'statement', 40) for i in range(3, 6)]
    result = aggregate(rows, LearningPolicy())
    hook = next(item for item in result if item.dimension == 'hook')
    assert hook.state == 'recommendations_available'
    a, b = hook.groups
    assert a.state == 'recommendation_candidate' and a.score_difference == 45
    assert a.sample_count == a.control_count == 3 and set(a.snapshot_ids).isdisjoint(a.control_snapshot_ids)
    assert b.state == 'no_positive_association' and 'causal' in a.recommendation
    assert all(item.state == 'insufficient_data' and item.missing_feature_posts == 6 for item in result if item.dimension != 'hook')


@pytest.mark.parametrize('case', ['few_group', 'few_control', 'null_control', 'no_difference', 'below_threshold'])
def test_missing_and_weak_samples_do_not_become_winning_strategies(case):
    rows = [observation(i) for i in range(3)] + [observation(i, 'statement', 40) for i in range(3, 6)]
    if case == 'few_group': rows = rows[1:]
    if case == 'few_control': rows = rows[:-1]
    if case == 'null_control': rows = rows[:3] + [observation(i, None) for i in range(3, 6)]
    if case == 'no_difference': rows = [observation(i, 'question' if i < 3 else 'statement', 85) for i in range(6)]
    if case == 'below_threshold': rows = [observation(i, 'question' if i < 3 else 'statement', 85 if i < 3 else 80) for i in range(6)]
    result = next(item for item in aggregate(rows, LearningPolicy()) if item.dimension == 'hook')
    assert result.state != 'recommendations_available'
    if case in ('few_group', 'few_control', 'null_control'):
        assert all(row.score_difference is None and row.state == 'insufficient_data' for row in result.groups)


def test_duplicate_post_or_overflow_refused_before_group_counting():
    item = observation(1)
    with pytest.raises(ValueError, match='DISTINCT_POST'): aggregate([item, item], LearningPolicy())
    with pytest.raises(ValueError, match='DISTINCT_POST'): aggregate([observation(i) for i in range(7)], LearningPolicy(maximum_posts=6))
    with pytest.raises(ValueError, match='BASIS_MISMATCH'):
        aggregate([observation(1), observation(2).model_copy(update={'assessment_basis_sha256': 'd' * 64})], LearningPolicy())


async def seed_learning_history(stack, target, *, count=6):
    """Six explicit manual metric seeds and cloned fixture render annotations, zero wire reads."""
    factory = stack.repository.session_factory
    policy = WinnerChannelPolicy()
    for index in range(count):
        parent_id = f'pub_learning_seed_fixture_{index}'
        async with factory() as session:
            original = await session.get(PublicationORM, stack.publication.publication_id)
            render = await session.get(ProductionRenderJobORM, original.final_render_id)
            context = RenderFeatureContext.model_validate(render.manifest_json['feature_context']).model_copy(update={
                'hook_type': 'fixture-question' if index < 3 else 'fixture-statement',
                'visual_strategy': 'fixture-source' if index < 3 else 'fixture-slides'})
            fields = {column.name: getattr(render, column.name) for column in ProductionRenderJobORM.__table__.columns}
            identity = f'ren_learning_seed_fixture_{index}'
            fields.update(render_id=identity, version=1000 + index,
                manifest_json={**render.manifest_json, 'feature_context': context.model_dump(mode='json'), 'feature_context_sha256': feature_digest(context)})
            session.add(ProductionRenderJobORM(**fields))
            fields = {column.name: getattr(original, column.name) for column in PublicationORM.__table__.columns}
            fields.update(publication_id=parent_id, final_render_id=identity, idempotency_key_hash=hashlib.sha256(parent_id.encode()).hexdigest(),
                receipt_json={**original.receipt_json, 'remote_post_id': f'LearningFixture{index:04d}'})
            session.add(PublicationORM(**fields)); await session.commit()
        sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id,
            payload=AnalyticsSyncRequest(publication_id=parent_id, provider_mode='official', query={'start_date': '2026-10-01', 'end_date': '2026-10-06'}),
            idempotency_key='learning-explicit-synthetic-seed-' + str(index))
        claimed = await stack.repository.claim(sync.sync_id)
        parent = await stack.service.publishing_repository.get(sync.project_id, parent_id)
        features = await stack.processor._capture_features(claimed, parent)
        duration = features.duration_seconds
        metric = NormalizedMetrics(views=1000, average_view_duration=duration * (.8 if index < 3 else .3),
            likes=100, comments=10, shares=10, followers_gained=10)
        baseline = NormalizedMetrics(views=1000, average_view_duration=duration * .5, likes=100, comments=10, shares=10, followers_gained=10)
        context = {'peers': [{'snapshot_id': f'ams_explicit_baseline_fixture_{i}', 'values': values(baseline, duration)} for i in range(5)],
            'candidate_rows_truncated': False, 'counter_growth': None, 'scope_verified': True}
        assessment = assess_channel(metric, duration=duration, production_cost=None, context=context, policy=policy)
        assert assessment.score is not None
        await stack.repository.complete(sync.sync_id, collection=AnalyticsCollection(provider_key='youtube-analytics-api',
            source='explicit-learning-metadata-fixture', source_kind='official_api', collected_at=utc_now() - timedelta(minutes=count - index),
            metrics=metric, mock=True, external_call=False, evidence={'query': sync.query, 'account_match': True,
                'target_binding_sha256': target_digest(target), 'explicit_synthetic_metric_seed': True, 'actual_provider_calls': 0}),
            features=features, assessment=assessment, insights=[], expected_attempt=claimed.attempt_count)
    current = await reserve(stack, 'learning-current-anchor'); await stack.processor.process(current.sync_id)
    return current


def learning_app(stack, role='owner'):
    app = application(stack, role=role)
    app.state.channel_learning_service = ChannelLearningService(stack.repository.session_factory)
    app.include_router(router, dependencies=[Depends(authorize_human_request)])
    return app


@pytest.mark.asyncio
async def test_persisted_scoped_snapshot_is_versioned_idempotent_and_does_not_rewrite_history(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    await seed_learning_history(stack, current[0]); assert len(calls) == 3
    before = [row.model_dump(mode='json') for row in await stack.repository.list_snapshots(stack.publication.project_id)]
    service = ChannelLearningService(stack.repository.session_factory)
    payload = LearningCreate(publication_id=stack.publication.publication_id)
    result, replay = await service.create(stack.publication.project_id, payload, actor='usr:fixture', key='learning-fixture-owned-key')
    assert not replay and len(result.observations) == 7 and result.scope['mock'] and not result.scope['external_call']
    hook = next(item for item in result.dimensions if item.dimension == 'hook')
    assert hook.state == 'recommendations_available' and hook.groups[0].value == 'fixture-question'
    assert next(item for item in result.dimensions if item.dimension == 'publishing_window').state == 'insufficient_data'
    again, replay = await service.create(stack.publication.project_id, payload, actor='usr:another-fixture', key='learning-fixture-owned-key')
    assert replay and again == result and again.created_by == 'usr:fixture'
    with pytest.raises(LearningError, match='IDEMPOTENCY'):
        await service.create(stack.publication.project_id, payload.model_copy(update={'policy': LearningPolicy(minimum_group_posts=4)}), actor='usr:fixture', key='learning-fixture-owned-key')
    await stack.processor.process((await reserve(stack, 'learning-later-anchor')).sync_id)
    later, _ = await service.create(stack.publication.project_id, payload, actor='usr:fixture', key='learning-fixture-owned-key-later')
    assert later.anchor_snapshot_id != result.anchor_snapshot_id and later.content_sha256 != result.content_sha256
    assert await ChannelLearningService(stack.repository.session_factory).get(result.workspace_id, result.learning_snapshot_id) == result
    assert await service.get('wsp_other_fixture', result.learning_snapshot_id) is None
    after = {row.snapshot_id: row.model_dump(mode='json') for row in await stack.repository.list_snapshots(stack.publication.project_id)}
    assert all(after[row['snapshot_id']] == row for row in before)
    assert not result.autonomous_execution and result.recommendation_only


@pytest.mark.asyncio
async def test_legacy_features_insufficient_assessment_query_policy_and_duplicate_post_are_excluded(runtime_stack):
    stack, _, current, _, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    async with stack.repository.session_factory() as session:
        features = (await session.scalars(select(AnalyticsFeatureSnapshotORM).where(AnalyticsFeatureSnapshotORM.publication_id.like('pub_learning_seed_fixture_%')).order_by(AnalyticsFeatureSnapshotORM.publication_id))).all()
        features[0].evidence_json = {**features[0].evidence_json, 'feature_context_sha256': 'f' * 64}
        assessments = (await session.scalars(select(WinnerAssessmentORM).where(WinnerAssessmentORM.publication_id.like('pub_learning_seed_fixture_%')).order_by(WinnerAssessmentORM.publication_id))).all()
        assessments[1].state = 'insufficient_data'; assessments[1].score = None
        assessments[2].factors_json = [{**item, 'evidence': {**item['evidence'], 'policy_sha256': 'f' * 64}} for item in assessments[2].factors_json]
        parents = (await session.scalars(select(PublicationORM).where(PublicationORM.publication_id.like('pub_learning_seed_fixture_%')).order_by(PublicationORM.publication_id))).all()
        parents[3].receipt_json = {**parents[3].receipt_json, 'remote_post_id': parents[4].receipt_json['remote_post_id']}
        await session.commit()
    service = ChannelLearningService(stack.repository.session_factory)
    result, _ = await service.create(stack.publication.project_id, LearningCreate(publication_id=stack.publication.publication_id), actor='fixture', key='learning-exclusions-fixture-key')
    assert len(result.observations) == 3
    assert result.excluded_rows['missing_or_invalid_frozen_assessment'] == 2
    assert result.excluded_rows['incompatible_winner_policy'] == result.excluded_rows['duplicate_remote_post'] == 1
    assert all(item.state == 'insufficient_data' for item in result.dimensions)


@pytest.mark.asyncio
@pytest.mark.parametrize('role', ['owner', 'editor', 'reviewer', 'viewer'])
async def test_authenticated_creation_read_scope_and_no_store(runtime_stack, role):
    stack, _, current, calls, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    app = learning_app(stack, role=role); base = f'/api/v1/projects/{stack.publication.project_id}/analytics/learning-snapshots'
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
        reply = await client.post(base, json={'publication_id': stack.publication.publication_id}, headers={'Idempotency-Key': 'learning-api-owned-fixture-key'})
        if role == 'viewer':
            assert reply.status_code == 403
        else:
            assert reply.status_code == 201 and reply.headers['Cache-Control'] == 'no-store'
            value = reply.json(); identity = value['learning_snapshot_id']
            endpoint = f'/api/v1/workspaces/{stack.publication.workspace_id}/learning-snapshots/{identity}'
            assert (await client.get(endpoint)).json() == value
            advice = await client.get(endpoint + '/recommendations')
            assert advice.status_code == 200 and advice.json()['content_sha256'] == value['content_sha256']
            assert (await client.get(endpoint.replace(stack.publication.workspace_id, 'wsp_foreign'))).status_code == 404
            assert (await client.post(base, json={'publication_id': 'pub_missing_fixture'}, headers={'Idempotency-Key': 'missing-publication-fixture-key'})).status_code == 404
        assert (await client.get(base)).status_code == 200
        assert (await client.get(base, params={'limit': 101})).status_code == 422
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_tamper_rejected_and_mock_fixture_not_promoted_to_real_provider_history(runtime_stack):
    stack, _, current, _, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    service = ChannelLearningService(stack.repository.session_factory)
    with pytest.raises(LearningError, match='OFFICIAL_CHANNEL'):
        await service.create(stack.publication.project_id, LearningCreate(publication_id=stack.publication.publication_id, provider_mode='fixture'), actor='fixture', key='fixture-scope-rejected-key')
    result, _ = await service.create(stack.publication.project_id, LearningCreate(publication_id=stack.publication.publication_id), actor='fixture', key='tamper-fixture-owned-key')
    with pytest.raises(LearningError, match='NICHE_MISMATCH'):
        await service.feedback(result.workspace_id, result.learning_snapshot_id, niche='technology')
    async with service.factory() as session:
        row = await session.get(ChannelLearningSnapshotORM, result.learning_snapshot_id)
        row.snapshot_json = {**row.snapshot_json, 'observations': []}; await session.commit()
    with pytest.raises(LearningError, match='SNAPSHOT_INVALID'): await service.get(result.workspace_id, result.learning_snapshot_id)


@pytest.mark.asyncio
async def test_trend_idea_queue_and_draft_project_retain_reviewed_recommendation_lineage(runtime_stack):
    from test_trend_intelligence import FIXTURE_PATH, FIXTURE_AS_OF
    from app.trend_providers import create_trend_provider_registry
    from app.trend_repository import TrendRepository
    from app.trend_service import TrendIntelligenceService
    from app.trend_models import TrendCollectionRequest, TrendClusterRefreshRequest, IdeaGenerateRequest, ContentQueueRefreshRequest
    stack, _, current, calls, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    learning = ChannelLearningService(stack.repository.session_factory)
    saved, _ = await learning.create(stack.publication.project_id, LearningCreate(publication_id=stack.publication.publication_id), actor='fixture', key='learning-trend-integration-fixture')
    providers = create_trend_provider_registry(FIXTURE_PATH); repository = TrendRepository(stack.repository.session_factory)
    await repository.seed_sources(providers.definitions())
    service = TrendIntelligenceService(repository, providers, stack.production.platform, learning=learning)
    await service.collect(saved.workspace_id, TrendCollectionRequest())
    context = dict(niche=saved.scope['niche'], as_of=FIXTURE_AS_OF)
    base = await service.refresh_clusters(saved.workspace_id, TrendClusterRefreshRequest(**context))
    advised = await service.refresh_clusters(saved.workspace_id, TrendClusterRefreshRequest(**context, learning_snapshot_id=saved.learning_snapshot_id))
    assert [item.score.total_score for item in base] == [item.score.total_score for item in advised]
    assert all(item.learning_feedback['global_trend_score_unchanged'] for item in advised)
    ideas = await service.generate_ideas(advised[0].cluster_id, IdeaGenerateRequest(niche=saved.scope['niche'], learning_snapshot_id=saved.learning_snapshot_id))
    assert all(item.brief['learning_feedback']['content_sha256'] == saved.content_sha256 and item.provenance['learning_is_advisory'] for item in ideas)
    replay = await service.generate_ideas(advised[0].cluster_id, IdeaGenerateRequest(niche=saved.scope['niche'], learning_snapshot_id=saved.learning_snapshot_id))
    assert {item.idea_id for item in replay} == {item.idea_id for item in ideas}
    # Non-advised briefs remain available, but an explicitly advised queue cannot mix them in.
    ordinary = await service.generate_ideas(advised[0].cluster_id, IdeaGenerateRequest(niche=saved.scope['niche']))
    assert all('learning_feedback' not in item.brief for item in ordinary)
    queue = await service.refresh_queue(saved.workspace_id, ContentQueueRefreshRequest(niche=saved.scope['niche'], learning_snapshot_id=saved.learning_snapshot_id))
    assert all(item.idea.brief['learning_feedback']['learning_snapshot_id'] == saved.learning_snapshot_id for item in queue)
    project = await service.create_draft_project(ideas[0].idea_id)
    version = await stack.production.platform.get_version(project.project_version_id)
    assert version.snapshot['source_idea']['brief']['learning_feedback']['content_sha256'] == saved.content_sha256
    assert version.snapshot['approval']['approved'] is version.snapshot['approval']['publish_enabled'] is False
    with pytest.raises(LearningError, match='NOT_FOUND'):
        await learning.feedback('wsp_foreign_fixture', saved.learning_snapshot_id)
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_media_planner_persists_advice_without_changing_strategy_or_paid_admission(tmp_path):
    from test_media_intelligence import setup_media_stack, plan_request
    stack = await setup_media_stack(tmp_path)
    try:
        baseline = await stack['planner'].create(project_id=stack['project'].project_id, payload=plan_request(stack))
        calls = []
        class ExplicitLearningStub:
            async def feedback(self, workspace, identity, *, niche):
                calls.append((workspace, identity, niche))
                if identity == 'lsn_unknown_fixture': raise LearningError('LEARNING_SNAPSHOT_NOT_FOUND')
                return {'learning_snapshot_id': identity, 'content_sha256': 'a' * 64, 'recommendation_only': True,
                    'autonomous_execution': False, 'recommendations': [], 'mock_feedback_reader': True}
        stack['planner'].learning = ExplicitLearningStub()
        payload = plan_request(stack).model_copy(update={'learning_snapshot_id': 'lsn_explicit_fixture'})
        advised = await stack['planner'].create(project_id=stack['project'].project_id, payload=payload)
        assert advised.provenance['learning_feedback']['mock_feedback_reader']
        assert advised.provenance['learning_feedback']['autonomous_execution'] is False
        assert [item.strategy for item in baseline.items] == [item.strategy for item in advised.items]
        assert baseline.media_plan_id != advised.media_plan_id
        assert calls == [(stack['project'].workspace_id, payload.learning_snapshot_id, stack['project'].niche)]
        with pytest.raises(LearningError, match='NOT_FOUND'):
            await stack['planner'].create(project_id=stack['project'].project_id, payload=payload.model_copy(update={'learning_snapshot_id': 'lsn_unknown_fixture'}))
    finally: await stack['engine'].dispose()


@pytest.mark.asyncio
async def test_concurrent_same_key_and_bounded_post_selection_are_auditable(runtime_stack):
    import asyncio
    stack, _, current, _, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    service = ChannelLearningService(stack.repository.session_factory)
    payload = LearningCreate(publication_id=stack.publication.publication_id, policy=LearningPolicy(maximum_posts=6))
    results = await asyncio.gather(*(service.create(stack.publication.project_id, payload, actor='fixture', key='learning-concurrent-fixture-key') for _ in range(2)))
    assert results[0][0].learning_snapshot_id == results[1][0].learning_snapshot_id
    assert sorted(replay for _, replay in results) == [False, True]
    assert len(results[0][0].observations) == 6 and results[0][0].selected_posts_truncated
    assert len(await service.list(stack.publication.project_id)) == 1


@pytest.mark.asyncio
async def test_different_supported_factors_are_not_compared_as_equivalent_scores(runtime_stack):
    stack, _, current, _, _, _ = runtime_stack
    await seed_learning_history(stack, current[0])
    async with stack.repository.session_factory() as session:
        row = await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.publication_id == 'pub_learning_seed_fixture_0'))
        row.factors_json = [{**item, 'score': None} if item['factor'] == 'shares' else item for item in row.factors_json]
        await session.commit()
    value, _ = await ChannelLearningService(stack.repository.session_factory).create(stack.publication.project_id,
        LearningCreate(publication_id=stack.publication.publication_id), actor='fixture', key='learning-basis-fixture-key')
    assert value.excluded_rows['incompatible_assessment_basis'] == 1 and len(value.observations) == 6
    assert next(item for item in value.dimensions if item.dimension == 'hook').state == 'insufficient_data'
