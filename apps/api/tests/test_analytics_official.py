"""Official request/normalization contracts using explicit synthetic responses only."""
from dataclasses import replace
from datetime import date, timedelta
import json

import httpx
import pytest
from pydantic import ValidationError

from app.analytics_official import (AnalyticsHTTPClient, AnalyticsQuery, AnalyticsOAuthCredential, AnalyticsOfficialError,
    YT_READ, YT_ANALYTICS, YT_MONEY, YT_METRICS, number, resolve_credential, account_request, confirm_account,
    youtube_report_request, youtube_metrics, youtube_video_request, confirm_youtube_video,
    tiktok_video_request, tiktok_metrics, response_object)
from app.analytics_models import AnalyticsSyncRequest, NormalizedMetrics
from app.analytics_providers import AnalyticsRateLimited
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialRequest, OfficialResponse, OfficialHTTPClient, PublishingWireError, official_url
from app.db import utc_now


def target(platform='youtube'):
    return PublishingTargetBinding(workspace_id='wsp_analytics_fixture', profile_id='ppf_analytics_fixture', profile_version=1,
        platform=platform, provider_key='youtube-data-api' if platform == 'youtube' else 'tiktok-content-posting-api',
        target_account_id='UC_analytics_fixture' if platform == 'youtube' else 'analytics_open_id_fixture', credential_binding_sha256='a' * 64)


def credential(platform='youtube', **changes):
    return AnalyticsOAuthCredential(**{'target': target(platform), 'expires_at': utc_now() + timedelta(hours=1),
        'scopes': frozenset({YT_READ, YT_ANALYTICS}) if platform == 'youtube' else frozenset({'user.info.basic', 'video.list'}),
        'token': 'EXPLICIT-ANALYTICS-FIXTURE-TOKEN', **changes})


def query(**changes):
    return AnalyticsQuery(**{'start_date': date(2026, 10, 1), 'end_date': date(2026, 10, 6), **changes})


def response(value, status=200, headers=None):
    return OfficialResponse(status, headers or {}, json.dumps(value).encode())


def yt_table(values=None, revenue=False):
    names = (*YT_METRICS, 'estimatedRevenue') if revenue else YT_METRICS
    return {'columnHeaders': [{'name': name, 'columnType': 'METRIC', 'dataType': 'FLOAT' if name in
        ('estimatedMinutesWatched', 'averageViewDuration', 'estimatedRevenue') else 'INTEGER'} for name in names],
        'rows': [[1000, 120.5, 7.23, 50, 2, 9, 4, *([100000] if revenue else [])] if values is None else values]}


def test_youtube_exact_owner_video_dates_and_vnd_without_mismatched_semantics():
    current = credential(scopes=frozenset({YT_READ, YT_ANALYTICS, YT_MONEY})); requested = query(include_revenue=True)
    assert resolve_credential(lambda _: current, target(), requested) == current
    request = youtube_report_request(current, 'abcDEfgHI_1', requested)
    params = dict(httpx.URL(request.url).params)
    assert params['ids'] == 'channel==' + target().target_account_id and params['filters'] == 'video==abcDEfgHI_1'
    assert params['currency'] == 'VND' and params['startDate'] == '2026-10-01' and params['endDate'] == '2026-10-06'
    assert 'access_token' not in params and request.headers['Authorization'].endswith(current.token)
    metrics, evidence = youtube_metrics(response(yt_table(revenue=True)), requested)
    assert metrics.watch_time == 7230 and metrics.average_view_duration == 7.23 and metrics.revenue == 100000
    assert metrics.completion_rate is None and metrics.rpm is None and metrics.observation_window_hours is None
    assert metrics.impressions is None and metrics.saves is None and metrics.ctr is None
    assert evidence['coverage_end_date'] is None and evidence['revenue_basis'] == 'provider_estimate'
    assert current.token not in repr(current) + repr(request)


@pytest.mark.parametrize('raw', [True, False, '3', -1, float('nan'), float('inf'), {}, [], 2**53])
def test_metrics_reject_coercion_nonfinite_negative_and_unrepresentable_values(raw):
    with pytest.raises(AnalyticsOfficialError, match='ANALYTICS_METRIC_INVALID'): number(raw)


def test_missing_rows_and_missing_metrics_are_null_not_zero():
    table = yt_table(); table.pop('rows')
    metrics, evidence = youtube_metrics(response(table), query())
    assert all(value is None for value in metrics.model_dump().values()) and evidence['row_count'] == 0
    metrics, evidence = tiktok_metrics(response({'data': {'videos': []}, 'error': {'code': 'ok'}}), '1234567890')
    assert metrics.views is None and evidence['row_count'] == 0
    metrics, _ = tiktok_metrics(response({'data': {'videos': [{'id': '1234567890', 'view_count': 0}]}, 'error': {'code': 'ok'}}), '1234567890')
    assert metrics.views == 0 and metrics.likes is None


@pytest.mark.parametrize('mutation', ['header_name', 'header_type', 'duplicate_header', 'extra_rows', 'short_row', 'bad_count'])
def test_youtube_rejects_incorrect_shapes_and_metrics(mutation):
    table = yt_table()
    if mutation == 'header_name': table['columnHeaders'][0]['name'] = 'impressions'
    if mutation == 'header_type': table['columnHeaders'][0]['columnType'] = 'DIMENSION'
    if mutation == 'duplicate_header': table['columnHeaders'][1] = table['columnHeaders'][0]
    if mutation == 'extra_rows': table['rows'] *= 2
    if mutation == 'short_row': table['rows'][0].pop()
    if mutation == 'bad_count': table['rows'][0][0] = 1.25
    with pytest.raises(AnalyticsOfficialError): youtube_metrics(response(table), query())


def test_tiktok_queries_one_owned_video_and_preserves_unsupported_metrics():
    request = tiktok_video_request(credential('tiktok'), '1234567890')
    assert json.loads(request.body) == {'filters': {'video_ids': ['1234567890']}}
    value = {'data': {'videos': [{'id': '1234567890', 'view_count': 999, 'like_count': 10, 'comment_count': 0, 'share_count': 4}]}, 'error': {'code': 'ok'}}
    metrics, evidence = tiktok_metrics(response(value), '1234567890')
    assert metrics.views == 999 and metrics.comments == 0 and metrics.shares == 4
    assert metrics.completion_rate is None and metrics.watch_time is None and metrics.revenue is None
    assert evidence['metric_scope'] == 'cumulative_video_counters'
    with pytest.raises(AnalyticsOfficialError): tiktok_metrics(response(value), '999')


@pytest.mark.parametrize('status', [429, 500, 503])
def test_backoff_is_bounded_and_raw_provider_text_never_escapes(status):
    with pytest.raises(AnalyticsRateLimited) as caught:
        response_object(response({'error': 'PRIVATE CONTENT / TOKEN'}, status, {'retry-after': '999999999'}))
    assert caught.value.retry_after_seconds == 3600 and 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('status', [400, 401, 403])
def test_provider_rejections_have_fixed_private_codes(status):
    with pytest.raises(AnalyticsOfficialError) as caught: response_object(response({'error': 'TOKEN CONTENT'}, status))
    assert 'TOKEN CONTENT' not in str(caught.value)


def test_dedicated_read_credential_expiry_scope_and_account_fences():
    current = credential()
    for altered, expected in ((replace(current, expires_at=utc_now() + timedelta(seconds=60)), 'REFRESH_REQUIRED'),
        (replace(current, scopes=frozenset({YT_READ})), 'SCOPES_REQUIRED'),
        (replace(current, target=target().model_copy(update={'profile_version': 2})), 'TARGET_MISMATCH')):
        with pytest.raises(AnalyticsOfficialError, match=expected): resolve_credential(lambda _: altered, target(), query())
    with pytest.raises(AnalyticsOfficialError, match='SCOPES_REQUIRED'): resolve_credential(lambda _: current, target(), query(include_revenue=True))
    with pytest.raises(AnalyticsOfficialError, match='OAUTH_INVALID'):
        replace(current, scopes=frozenset({YT_READ, 'https://www.googleapis.com/auth/youtube.upload'}))
    assert confirm_account(response({'items': [{'id': target().target_account_id}]}), target())['account_match']
    with pytest.raises(AnalyticsOfficialError): confirm_account(response({'items': [{'id': 'foreign-channel'}]}), target())
    assert confirm_account(response({'data': {'user': {'open_id': target('tiktok').target_account_id}}, 'error': {'code': 'ok'}}), target('tiktok'))['account_match']


def test_youtube_video_ownership_must_match_even_with_correct_authenticated_channel():
    current = credential(); request = youtube_video_request(current, 'abcDEfgHI_1')
    assert dict(httpx.URL(request.url).params)['id'] == 'abcDEfgHI_1'
    correct = {'items': [{'id': 'abcDEfgHI_1', 'snippet': {'channelId': current.target.target_account_id}}]}
    confirm_youtube_video(response(correct), current.target, 'abcDEfgHI_1')
    correct['items'][0]['snippet']['channelId'] = 'FOREIGN'
    with pytest.raises(AnalyticsOfficialError, match='OWNERSHIP'): confirm_youtube_video(response(correct), current.target, 'abcDEfgHI_1')


@pytest.mark.parametrize('platform,url,method', [('youtube', 'https://www.googleapis.com/upload/youtube/v3/videos', 'POST'),
    ('youtube', 'https://youtubeanalytics.googleapis.com/v2/groups', 'DELETE'),
    ('tiktok', 'https://open.tiktokapis.com/v2/post/publish/video/init/', 'POST')])
@pytest.mark.asyncio
async def test_read_client_cannot_publish_or_delete(platform, url, method):
    calls = []
    client = AnalyticsHTTPClient(platform, transport=httpx.MockTransport(lambda request: calls.append(request)))
    with pytest.raises(AnalyticsOfficialError, match='READ_ONLY'): await client.request(OfficialRequest(method, url))
    assert calls == []


@pytest.mark.asyncio
async def test_disabled_transport_and_publisher_origin_isolation():
    with pytest.raises(PublishingWireError, match='NOT_ACTIVATED'):
        await AnalyticsHTTPClient('youtube').request(account_request(credential()))
    with pytest.raises(PublishingWireError, match='ORIGIN_REQUIRED'):
        official_url('https://youtubeanalytics.googleapis.com/upload/youtube/v3/videos', 'youtube')


@pytest.mark.parametrize('values', [{'include_revenue': 1}, {'end_date': '2026-09-30'}, {'end_date': '2027-10-02'}])
def test_query_bounds_and_explicit_fixture_separation(values):
    with pytest.raises(ValidationError): query(**values)
    with pytest.raises(ValidationError): AnalyticsSyncRequest(publication_id='pub_fixture', query=query().model_dump(mode='json'))


@pytest.mark.parametrize('value', [True, '12', float('nan'), float('inf')])
def test_public_normalized_metrics_also_reject_coerced_or_nonfinite_values(value):
    with pytest.raises(ValidationError): NormalizedMetrics(views=value)
