"""Explicit timestamp fixtures and owned MockTransport reads; no provider acceptance."""
from datetime import datetime, timedelta, timezone
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select

from app.analytics_db import AnalyticsFeatureSnapshotORM
from app.analytics_models import AnalyticsSyncRequest
from app.analytics_official import AnalyticsHTTPClient, AnalyticsOAuthCredential
from app.analytics_publication_time import PublicationTimeEvidence, provider_time, bound_time, posting_window
from app.analytics_repository import AnalyticsRepository
from app.db import ProviderRegistryORM, utc_now
from app.learning_models import LearningPolicy, aggregate
from app.publishing_credentials import target_digest
from app.publishing_db import PublicationORM
from app.publishing_models import PublishingTargetBinding
from app.publishing_profiles import PROVIDER_KEYS
from test_analytics_runtime import runtime_stack, reserve
from test_channel_learning import observation

OBSERVED = datetime(2026, 10, 7, 12, tzinfo=timezone.utc)
POSTED = datetime(2026, 10, 6, 18, 30, tzinfo=timezone.utc)


def stamp(platform='tiktok', raw=int(POSTED.timestamp())):
    return provider_time(platform=platform, video={'create_time': raw} if platform == 'tiktok' else {'snippet': {'publishedAt': raw}},
        observed_at=OBSERVED, publication_id='pub_time_fixture', remote_id='1234567890', target_sha256='a' * 64,
        response_sha256='b' * 64, mock=True, external_call=False)


def evidence(value):
    return {'account_match': True, 'target_binding_sha256': value.target_binding_sha256,
        'publication_time': value.model_dump(mode='json'), 'request_observations': [{'operation': value.operation,
            'status': 200, 'response_sha256': value.response_sha256, 'mock': True, 'external_call': False}]}


def bound(payload):
    return bound_time(payload, platform='tiktok', provider_key='tiktok-video-insights-api', publication_id='pub_time_fixture',
        remote_id='1234567890', target_sha256='a' * 64, collected_at=OBSERVED, mock=True, external_call=False, source_kind='official_api')


def test_exact_epoch_posts_have_explicit_utc_semantics_without_public_exposure_claim():
    value = stamp()
    assert value.verified_posted_at == POSTED and value.reported_at == POSTED
    assert value.state == 'verified_provider_posted_time' and value.basis == 'provider_posted_time'
    assert not value.public_exposure_time_verified and value.mock and not value.external_call
    assert bound(evidence(value)) == value


@pytest.mark.parametrize('raw', [None, True, False, '1791311400', 0, -1, 1.5, float('nan'), [], {}, 2**63, int(OBSERVED.timestamp()) + 1])
def test_missing_coerced_invalid_or_future_post_times_remain_unavailable(raw):
    value = stamp(raw=raw)
    assert value.verified_posted_at is None and value.reported_at is None and value.state == 'unavailable'


@pytest.mark.parametrize('raw', ['2026-10-06T18:30:00Z', '2026-10-07T01:30:00+07:00', None,
    '2026-10-06', '2026-10-06T18:30:00', '2026-10-08T18:30:00Z', 'bad', 1791311400])
def test_youtube_provider_timestamp_is_never_promoted_to_exact_publication_time(raw):
    value = stamp('youtube', raw)
    assert value.verified_posted_at is None and value.state == 'unavailable'
    if raw in ('2026-10-06T18:30:00Z', '2026-10-07T01:30:00+07:00'):
        assert value.reported_at == POSTED and value.reason == 'youtube_upload_or_publication_semantics_ambiguous'


@pytest.mark.parametrize('mutation', ['account', 'target', 'platform', 'provider', 'publication', 'remote', 'clock',
    'transport', 'response', 'operation', 'status', 'missing_observation', 'duplicate_observation', 'numeric_time', 'schema'])
def test_rebound_or_unverified_timestamp_cannot_enter_features_or_learning(mutation):
    payload = evidence(stamp()); value = payload['publication_time']
    if mutation == 'account': payload['account_match'] = False
    if mutation == 'target': payload['target_binding_sha256'] = 'c' * 64
    if mutation == 'platform': value['platform'] = 'youtube'
    if mutation == 'provider': value['provider_key'] = 'fixture'
    if mutation == 'publication': value['publication_id'] = 'pub_other_fixture'
    if mutation == 'remote': value['remote_post_sha256'] = 'd' * 64
    if mutation == 'clock': value['observed_at'] = (OBSERVED + timedelta(seconds=1)).isoformat()
    if mutation == 'transport': value['mock'] = False; value['external_call'] = True
    if mutation == 'response': value['response_sha256'] = 'e' * 64
    if mutation == 'operation': payload['request_observations'][0]['operation'] = 'account_lookup'
    if mutation == 'status': payload['request_observations'][0]['status'] = 202
    if mutation == 'missing_observation': payload['request_observations'] = []
    if mutation == 'duplicate_observation': payload['request_observations'] *= 2
    if mutation == 'numeric_time': value['verified_posted_at'] = int(POSTED.timestamp())
    if mutation == 'schema': value['schema_version'] = 'unknown'
    assert bound(payload) is None


def test_posting_window_requires_identical_feature_and_metric_evidence_and_independent_controls():
    value = stamp(); payload = evidence(value)
    feature = SimpleNamespace(publishing_time=POSTED.replace(tzinfo=None), evidence_json={'publication_time': value.model_dump(mode='json'),
        'publishing_time_source': 'create_time', 'exact_publishing_time_available': True})
    def window():
        return posting_window(payload, feature, platform='tiktok', provider_key=value.provider_key, publication_id=value.publication_id,
            remote_id='1234567890', target_sha256='a' * 64, collected_at=OBSERVED, mock=True, external_call=False, source_kind='official_api')
    assert window() == 'UTC:Tue:16-20:provider-posted'
    rows = [observation(i).model_copy(update={'features': {**observation(i).features,
        'publishing_window': window() if i < 3 else 'UTC:Wed:08-12:provider-posted'}, 'score': 85 if i < 3 else 40}) for i in range(6)]
    result = next(item for item in aggregate(rows, LearningPolicy()) if item.dimension == 'publishing_window')
    assert result.state == 'recommendations_available' and result.groups[0].sample_count == result.groups[0].control_count == 3
    feature.publishing_time = POSTED + timedelta(seconds=1); assert window() is None
    feature.publishing_time = POSTED; feature.evidence_json['publication_time'] = {}; assert window() is None
    feature.evidence_json = None; assert window() is None


async def posted_runtime(stack, runtime, *, raw=int(POSTED.timestamp())):
    parent = stack.publication
    target = PublishingTargetBinding(workspace_id=parent.workspace_id, profile_id='ppf_posted_fixture', profile_version=1,
        platform='tiktok', provider_key=PROVIDER_KEYS['tiktok'], target_account_id='EXPLICIT_POSTED_ACCOUNT_FIXTURE', credential_binding_sha256='c' * 64)
    async with stack.repository.session_factory() as session:
        row = await session.get(PublicationORM, parent.publication_id)
        row.platform = 'tiktok'; row.provider_key = target.provider_key
        row.provider_validation_json = {**row.provider_validation_json, 'provider_key': target.provider_key, 'target_binding': target.model_dump(mode='json')}
        row.receipt_json = {**row.receipt_json, 'platform': 'tiktok', 'provider_key': target.provider_key, 'remote_post_id': '1234567890'}
        session.add(ProviderRegistryORM(provider_id='pvd_posted_fixture', workspace_id=parent.workspace_id,
            provider_key='tiktok-video-insights-api', display_name='EXPLICIT POSTED MOCK FIXTURE', capability='analytics',
            adapter='explicit.fixture', routing_mode='disabled', status='fixture', enabled=False, supports_dry_run=True,
            config_ref=None, metadata_json={'fixture_only': True}))
        await session.commit()
    stack.publication = await stack.service.publishing_repository.get(parent.project_id, parent.publication_id)
    calls = []; timestamp = [raw]
    def receive(request):
        calls.append({'method': request.method, 'path': request.url.path, 'mock': True, 'external_call': False})
        if request.method == 'GET': value = {'data': {'user': {'open_id': target.target_account_id}}}
        else:
            assert 'create_time' in request.url.params['fields'].split(',')
            value = {'data': {'videos': [{'id': '1234567890', 'create_time': timestamp[0], 'view_count': 1000,
                'like_count': 10, 'comment_count': 2, 'share_count': 5}]}}
        return httpx.Response(200, json=value)
    runtime.clock = lambda: OBSERVED; runtime.target_provider = lambda *_: target
    runtime.credential_resolver = lambda selected: AnalyticsOAuthCredential(selected, utc_now() + timedelta(hours=1),
        frozenset({'user.info.basic', 'video.list'}), 'EXPLICIT_POSTED_MOCK_TOKEN')
    runtime.clients['tiktok'] = AnalyticsHTTPClient('tiktok', transport=httpx.MockTransport(receive)); runtime.install(stack.providers)
    return calls, timestamp, target


async def collect_posted(stack, suffix):
    sync, _ = await stack.service.create_sync(project_id=stack.publication.project_id,
        payload=AnalyticsSyncRequest(publication_id=stack.publication.publication_id, provider_mode='official'),
        idempotency_key='posted-time-owned-fixture-' + suffix)
    result = await stack.processor.process(sync.sync_id)
    assert result.status == 'succeeded' and result.mock and not result.external_call
    return await stack.repository.report(sync.project_id)


@pytest.mark.asyncio
async def test_runtime_persists_verified_posted_time_and_missing_refresh_preserves_old_history(runtime_stack):
    stack, runtime, _, _, _, _ = runtime_stack
    calls, timestamp, target = await posted_runtime(stack, runtime)
    first = await collect_posted(stack, 'first'); old = first.latest_snapshot.model_dump(mode='json')
    assert first.video_features.publishing_time == POSTED and first.video_features.evidence['exact_publishing_time_available']
    assert first.video_features.evidence['publishing_time_source'] == 'create_time'
    assert first.latest_snapshot.metrics.average_view_duration is None and first.latest_assessment.state == 'insufficient_data'
    async with stack.repository.session_factory() as session:
        feature = await session.scalar(select(AnalyticsFeatureSnapshotORM).where(AnalyticsFeatureSnapshotORM.snapshot_id == first.latest_snapshot.snapshot_id))
        assert posting_window(first.latest_snapshot.evidence, feature, platform='tiktok', provider_key=first.latest_snapshot.provider_key,
            publication_id=stack.publication.publication_id, remote_id='1234567890', target_sha256=target_digest(target),
            collected_at=first.latest_snapshot.collected_at, mock=True, external_call=False, source_kind='official_api') == 'UTC:Tue:16-20:provider-posted'
    timestamp[0] = None
    later = await collect_posted(stack, 'missing-refresh')
    assert later.video_features.publishing_time is None and not later.video_features.evidence['exact_publishing_time_available']
    restored = await AnalyticsRepository(stack.repository.session_factory).list_snapshots(stack.publication.project_id)
    assert any(item.model_dump(mode='json') == old for item in restored) and len(calls) == 4
    assert 'EXPLICIT_POSTED_MOCK_TOKEN' not in json.dumps([item.model_dump(mode='json') for item in restored])


@pytest.mark.asyncio
async def test_youtube_runtime_retains_reported_time_without_receipt_backfill(runtime_stack):
    stack, runtime, target, calls, _, _ = runtime_stack
    runtime.clock = lambda: OBSERVED
    def receive(request):
        calls.append({'method': request.method, 'path': request.url.path})
        if request.url.path.endswith('/channels'): value = {'items': [{'id': target[0].target_account_id}]}
        elif request.url.path.endswith('/videos'): value = {'items': [{'id': 'abcDEfgHI_1', 'snippet': {
            'channelId': target[0].target_account_id, 'publishedAt': POSTED.isoformat()}}]}
        else:
            from test_analytics_official import yt_table
            value = yt_table()
        return httpx.Response(200, json=value)
    runtime.clients['youtube'] = AnalyticsHTTPClient('youtube', transport=httpx.MockTransport(receive))
    sync = await reserve(stack, 'reported-youtube'); await stack.processor.process(sync.sync_id)
    report = await stack.repository.report(sync.project_id)
    assert report.video_features.publishing_time is None
    assert PublicationTimeEvidence.model_validate(report.latest_snapshot.evidence['publication_time']).reported_at == POSTED
    assert report.latest_snapshot.evidence['publication_time']['verified_posted_at'] is None
    assert not report.video_features.evidence['exact_publishing_time_available'] and len(calls) == 3
