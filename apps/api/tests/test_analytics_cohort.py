"""Synthetic observations only; no external acceptance or fabricated real metrics."""
from datetime import timedelta
import hashlib
import json
from types import SimpleNamespace

import pytest
import httpx
from pydantic import ValidationError
from sqlalchemy import select

from app.analytics_cohort import VERSION, WinnerChannelPolicy, assess_channel, counter_growth, values
from app.analytics_logic import assess_winner
from app.analytics_models import AnalyticsSyncRequest, NormalizedMetrics
from app.analytics_providers import AnalyticsCollection
from app.analytics_service import AnalyticsSyncProcessor
from app.analytics_db import AnalyticsFeatureSnapshotORM
from app.db import utc_now
from app.db import ProviderRegistryORM
from app.analytics_official import AnalyticsHTTPClient, AnalyticsOAuthCredential
from app.publishing_models import PublishingTargetBinding
from app.publishing_profiles import PROVIDER_KEYS
from app.publishing_credentials import target_digest
from app.publishing_db import PublicationORM
from test_analytics_runtime import runtime_stack, reserve


@pytest.mark.parametrize('intent', [
    {'minimum_peer_posts': True}, {'minimum_peer_posts': 6, 'maximum_peer_posts': 5},
    {'winner_threshold': 20, 'underperforming_threshold': 30}, {'minimum_weight_coverage': True},
    {'weights': {'view_velocity': .5}}, {'weights': {**WinnerChannelPolicy().weights, 'ctr': float('nan')}},
    {'weights': {**WinnerChannelPolicy().weights, 'ctr': True}},
])
def test_policy_rejects_ambiguous_or_incomplete_config(intent):
    with pytest.raises(ValidationError): WinnerChannelPolicy.model_validate(intent)


def test_invalid_operator_policy_fails_before_reads_without_echoing_raw_configuration():
    with pytest.raises(ValueError, match='^WINNER_CHANNEL_POLICY_INVALID$') as error:
        AnalyticsSyncProcessor(repository=None, publishing_repository=None, platform_repository=None,
            trend_repository=None, timeline_repository=None, production_repository=None, providers=None,
            settings=SimpleNamespace(analytics_winner_policy_json='{"PRIVATE_FIXTURE_FIELD":"DO_NOT_LOG"}'))
    assert 'PRIVATE_FIXTURE_FIELD' not in str(error.value) and 'DO_NOT_LOG' not in str(error.value)


def peers(metrics, duration=10, count=5):
    return {'peers': [{'snapshot_id': 'ams_explicit_fixture_' + str(i), 'values': values(metrics, duration)} for i in range(count)],
        'candidate_rows_truncated': False, 'counter_growth': None, 'scope_verified': True}


def test_relative_assessment_preserves_nulls_and_is_explainable_without_global_thresholds():
    policy = WinnerChannelPolicy()
    baseline = NormalizedMetrics(views=1000, average_view_duration=3, likes=25, comments=2, shares=5, followers_gained=5, ctr=.02, revenue=500)
    current = NormalizedMetrics(views=1000, average_view_duration=6, likes=50, comments=5, shares=10, followers_gained=10, ctr=.05, revenue=1000)
    draft = assess_channel(current, duration=10, production_cost=None, context=peers(baseline), policy=policy)
    assert draft.state == 'winner_candidate' and draft.algorithm_version == VERSION
    assert draft.score == 100 and draft.data_coverage == .56
    by_name = {factor.factor: factor for factor in draft.factors}
    assert by_name['completion'].score is by_name['saves'].score is by_name['view_velocity'].score is None
    assert by_name['retention'].evidence['peer_median'] == .3
    assert by_name['retention'].evidence['peer_count'] == 5
    assert all(factor.evidence['policy_sha256'] == policy.digest() for factor in draft.factors)
    assert current.observation_window_hours is None and current.completion_rate is None
    assert 'do not delete' in draft.recommendations[1]


@pytest.mark.parametrize('restriction', ['too_few_peers', 'low_views', 'missing_retention', 'unverified_scope', 'unsupported_baseline'])
def test_insufficient_evidence_does_not_classify_or_invent_missing_data(restriction):
    policy = WinnerChannelPolicy()
    metrics = NormalizedMetrics(views=1000, average_view_duration=3, likes=25, shares=5, ctr=.02)
    context = peers(metrics)
    if restriction == 'too_few_peers': context['peers'] = context['peers'][:4]
    if restriction == 'low_views': metrics = metrics.model_copy(update={'views': 499})
    if restriction == 'missing_retention': metrics = metrics.model_copy(update={'average_view_duration': None})
    if restriction == 'unverified_scope': context['scope_verified'] = False
    if restriction == 'unsupported_baseline': context = peers(NormalizedMetrics(views=1000))
    result = assess_channel(metrics, duration=10, production_cost=None, context=context, policy=policy)
    assert result.state == 'insufficient_data' and result.score is None


def test_zero_median_does_not_produce_infinity_and_engagement_support_sets_must_match():
    baseline = NormalizedMetrics(views=1000, average_view_duration=0, likes=0, shares=0, ctr=0)
    current = NormalizedMetrics(views=1000, average_view_duration=0, likes=0, comments=1, shares=0, ctr=.02)
    result = assess_channel(current, duration=10, production_cost=float('nan'), context=peers(baseline), policy=WinnerChannelPolicy())
    by_name = {factor.factor: factor for factor in result.factors}
    assert by_name['retention'].score == 50 and by_name['shares'].score == 50 and by_name['ctr'].score == 100
    assert by_name['engagement'].score is None and by_name['engagement'].evidence['peer_count'] == 0
    assert by_name['production_cost_efficiency'].evidence['raw_value'] is None


@pytest.mark.parametrize('case', ['valid', 'reset', 'short_interval', 'period_report'])
def test_counter_growth_uses_two_cumulative_observations_without_publishing_age(case):
    now = utc_now(); previous = {'snapshot_id': 'ams_counter_fixture', 'collected_at': now - timedelta(hours=6),
        'metrics': NormalizedMetrics(views=1000), 'evidence': {'metric_scope': 'cumulative_video_counters'}}
    current = SimpleNamespace(collected_at=now, metrics=NormalizedMetrics(views=2000), evidence={'metric_scope': 'cumulative_video_counters'})
    if case == 'reset': current.metrics = NormalizedMetrics(views=900)
    if case == 'short_interval': previous['collected_at'] = now - timedelta(hours=1)
    if case == 'period_report': current.evidence = {'metric_scope': 'requested_report_interval'}
    result = counter_growth(current, previous, WinnerChannelPolicy())
    if case != 'valid': assert result is None
    else:
        assert result['reported_counter_growth_per_hour'] == pytest.approx(1000 / 6)
        assert result['actual_publishing_age_hours'] is None and result['provider_update_lag_unknown']
        assert current.metrics.observation_window_hours is None


async def seed_peer(stack, current, index, *, query=None, remote=None, target=None, mock=True):
    publication_id = 'pub_cohort_explicit_fixture_' + str(index)
    target = target or current
    async with stack.repository.session_factory() as session:
        original = await session.get(PublicationORM, stack.publication.publication_id)
        fields = {column.name: getattr(original, column.name) for column in PublicationORM.__table__.columns}
        fields.update(publication_id=publication_id, idempotency_key_hash=hashlib.sha256(publication_id.encode()).hexdigest(),
            receipt_json={**original.receipt_json, 'remote_post_id': remote or f'PeerVid{index:04d}'},
            provider_validation_json={**original.provider_validation_json, 'target_binding': target.model_dump(mode='json')})
        session.add(PublicationORM(**fields)); await session.commit()
    body = AnalyticsSyncRequest(publication_id=publication_id, provider_mode='official', query=query or {'start_date': '2026-10-01', 'end_date': '2026-10-06'})
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id, payload=body,
        idempotency_key='cohort-explicit-seed-' + str(index))
    claimed = await stack.repository.claim(sync.sync_id)
    parent = await stack.service.publishing_repository.get(sync.project_id, publication_id)
    features = await stack.processor._capture_features(claimed, parent)
    metrics = NormalizedMetrics(views=1000, average_view_duration=1.5, likes=20, comments=2, shares=5, followers_gained=5)
    await stack.repository.complete(sync.sync_id, collection=AnalyticsCollection(provider_key='youtube-analytics-api',
        source='explicit-cohort-metadata-fixture', source_kind='official_api', collected_at=utc_now() - timedelta(hours=index + 1),
        metrics=metrics, mock=mock, external_call=False, evidence={'query': sync.query, 'account_match': True,
            'target_binding_sha256': target_digest(target), 'fixture_metric_seed_only': True, 'actual_provider_calls': 0}),
        features=features, assessment=assess_winner(metrics, video_duration_seconds=features.duration_seconds, production_cost_vnd=None),
        insights=[], expected_attempt=claimed.attempt_count)


@pytest.mark.asyncio
async def test_persisted_channel_assessment_deduplicates_posts_and_excludes_incompatible_reports(runtime_stack):
    stack, _, current, calls, _, _ = runtime_stack
    for index in range(5): await seed_peer(stack, current[0], index)
    await seed_peer(stack, current[0], 5, remote='PeerVid0000')
    await seed_peer(stack, current[0], 6, query={'start_date': '2026-09-01', 'end_date': '2026-09-02'})
    await seed_peer(stack, current[0], 7, target=current[0].model_copy(update={'profile_version': 2}))
    await seed_peer(stack, current[0], 8, mock=False)  # Deliberate transport metadata simulation; no real call.
    assert calls == []
    before = [row.model_dump(mode='json') for row in await stack.repository.list_snapshots(stack.publication.project_id)]
    sync = await reserve(stack, 'channel-cohort'); result = await stack.processor.process(sync.sync_id)
    assert result.status == 'succeeded' and result.mock and not result.external_call and len(calls) == 3
    report = await stack.repository.report(sync.project_id); assessment = report.latest_assessment
    assert assessment.algorithm_version == VERSION and assessment.state == 'winner_candidate'
    retention = next(factor for factor in assessment.factors if factor.factor == 'retention')
    assert retention.evidence['peer_count'] == 5 and len(set(retention.evidence['peer_snapshot_ids'])) == 5
    assert next(factor for factor in assessment.factors if factor.factor == 'view_velocity').score is None
    assert report.latest_snapshot.metrics.observation_window_hours is None
    assert not assessment.automatic_action and not assessment.paid_media_mutation and not assessment.content_deletion
    after = {row.snapshot_id: row.model_dump(mode='json') for row in await stack.repository.list_snapshots(sync.project_id)}
    assert all(after[row['snapshot_id']] == row for row in before)
    assert all(VERSION in insight.evidence_refs for insight in report.learning_insights)
    # Deliberate corruption simulation in the owned test DB: the next assessment
    # must exclude the peer rather than trusting a metadata-source label alone.
    async with stack.repository.session_factory() as session:
        feature = await session.scalar(select(AnalyticsFeatureSnapshotORM).where(
            AnalyticsFeatureSnapshotORM.snapshot_id == retention.evidence['peer_snapshot_ids'][0]))
        feature.evidence_json = {**feature.evidence_json, 'feature_context_sha256': 'f' * 64}
        await session.commit()
    later = await reserve(stack, 'channel-cohort-corrupt-peer'); await stack.processor.process(later.sync_id)
    limited = (await stack.repository.report(later.project_id)).latest_assessment
    assert limited.state == 'winner_candidate'
    replacement = next(factor for factor in limited.factors if factor.factor == 'retention')
    assert replacement.evidence['peer_count'] == 5
    assert retention.evidence['peer_snapshot_ids'][0] not in replacement.evidence['peer_snapshot_ids']
    async with stack.repository.session_factory() as session:
        alias = await session.scalar(select(AnalyticsFeatureSnapshotORM).where(
            AnalyticsFeatureSnapshotORM.publication_id == 'pub_cohort_explicit_fixture_5'))
        alias.evidence_json = {**alias.evidence_json, 'feature_context_sha256': 'f' * 64}
        await session.commit()
    final = await reserve(stack, 'channel-cohort-all-aliases-corrupt'); await stack.processor.process(final.sync_id)
    limited = (await stack.repository.report(final.project_id)).latest_assessment
    assert limited.state == 'insufficient_data' and limited.score is None
    assert next(factor for factor in limited.factors if factor.factor == 'retention').evidence['peer_count'] == 4


async def exercise_counter_history(stack, runtime):
    """Twelve collections via actual read adapter/MockTransport, explicit test clock."""
    original = stack.publication
    target = PublishingTargetBinding(workspace_id=original.workspace_id, profile_id='ppf_counter_fixture',
        profile_version=1, platform='tiktok', provider_key=PROVIDER_KEYS['tiktok'],
        target_account_id='EXPLICIT_COUNTER_ACCOUNT_FIXTURE', credential_binding_sha256='c' * 64)
    clock = [utc_now() - timedelta(hours=12)]; views = {}; calls = []
    async with stack.repository.session_factory() as session:
        row = await session.get(PublicationORM, original.publication_id)
        row.platform = 'tiktok'; row.provider_key = target.provider_key
        row.provider_validation_json = {**row.provider_validation_json, 'provider_key': target.provider_key,
            'target_binding': target.model_dump(mode='json')}
        row.receipt_json = {**row.receipt_json, 'platform': 'tiktok', 'provider_key': target.provider_key, 'remote_post_id': '9999900001'}
        session.add(ProviderRegistryORM(provider_id='pvd_explicit_counter_fixture', workspace_id=original.workspace_id,
            provider_key='tiktok-video-insights-api', display_name='EXPLICIT COUNTER MOCK FIXTURE', capability='analytics',
            adapter='explicit.fixture', routing_mode='disabled', status='fixture', enabled=False,
            supports_dry_run=True, config_ref=None, metadata_json={'fixture_only': True}))
        await session.commit()
    stack.publication = await stack.service.publishing_repository.get(original.project_id, original.publication_id)
    def receive(request):
        calls.append({'method': request.method, 'path': request.url.path, 'mock': True, 'external_call': False})
        if request.method == 'GET': payload = {'data': {'user': {'open_id': target.target_account_id}}}
        else:
            remote = json.loads(request.content)['filters']['video_ids'][0]
            payload = {'data': {'videos': [{'id': remote, 'view_count': views[remote],
                'like_count': 10, 'comment_count': 2, 'share_count': 5}]}}
        return httpx.Response(200, json=payload)
    runtime.clock = lambda: clock[0]
    runtime.target_provider = lambda *_: target
    runtime.credential_resolver = lambda selected: AnalyticsOAuthCredential(selected, utc_now() + timedelta(hours=1),
        frozenset({'user.info.basic', 'video.list'}), 'EXPLICIT_COUNTER_MOCK_TOKEN')
    runtime.clients['tiktok'] = AnalyticsHTTPClient('tiktok', transport=httpx.MockTransport(receive))
    runtime.install(stack.providers)
    parents = []
    async with stack.repository.session_factory() as session:
        row = await session.get(PublicationORM, original.publication_id)
        fields = {column.name: getattr(row, column.name) for column in PublicationORM.__table__.columns}
        for index in range(5):
            identity = 'pub_counter_explicit_fixture_' + str(index); remote = str(9999900100 + index)
            session.add(PublicationORM(**{**fields, 'publication_id': identity,
                'idempotency_key_hash': hashlib.sha256(identity.encode()).hexdigest(),
                'receipt_json': {**fields['receipt_json'], 'remote_post_id': remote}}))
            parents.append((identity, remote))
        await session.commit()
    async def collect(identity, remote, round_id, count):
        views[remote] = count
        sync, _ = await stack.service.create_sync(project_id=original.project_id,
            payload=AnalyticsSyncRequest(publication_id=identity, provider_mode='official'),
            idempotency_key=f'counter-mock-{identity}-{round_id}')
        result = await stack.processor.process(sync.sync_id)
        assert result.status == 'succeeded' and result.mock and not result.external_call
    for identity, remote in parents: await collect(identity, remote, 1, 500)
    clock[0] += timedelta(hours=6)
    for identity, remote in parents: await collect(identity, remote, 2, 1000)
    await collect(original.publication_id, '9999900001', 1, 1000)
    clock[0] += timedelta(hours=6)
    await collect(original.publication_id, '9999900001', 2, 2000)
    report = await stack.repository.report(original.project_id)
    factor = next(item for item in report.latest_assessment.factors if item.factor == 'view_velocity')
    assert factor.score == 100 and factor.evidence['peer_count'] == 5
    assert factor.evidence['raw_value'] == pytest.approx(1000 / 6)
    assert factor.evidence['peer_median'] == pytest.approx(500 / 6)
    assert len(factor.evidence['peer_counter_growth']) == 5 and factor.evidence['counter_growth']['elapsed_collection_hours'] == 6
    assert all(value['previous_snapshot_id'] for value in factor.evidence['peer_counter_growth'].values())
    assert report.latest_assessment.state == 'insufficient_data' and report.latest_assessment.score is None
    assert report.latest_snapshot.metrics.average_view_duration is None and report.latest_snapshot.metrics.completion_rate is None
    assert report.latest_snapshot.metrics.observation_window_hours is None and report.video_features.publishing_time is None
    assert len(calls) == 24
    return report, calls


@pytest.mark.asyncio
async def test_persisted_cumulative_read_history_supports_velocity_without_invented_retention(runtime_stack):
    stack, runtime, _, _, _, _ = runtime_stack
    await exercise_counter_history(stack, runtime)
