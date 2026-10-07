"""Scoped read-only official analytics contracts; no startup or credential acquisition."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
from urllib.parse import urlencode, urlsplit

from pydantic import ConfigDict, StrictBool, model_validator

from .models import StrictModel
from .analytics_models import NormalizedMetrics
from .analytics_providers import AnalyticsRateLimited
from .publishing_credentials import target_digest
from .publishing_models import PublishingTargetBinding
from .publishing_wire import OfficialHTTPClient, OfficialRequest, OfficialResponse, bearer_headers

YT_READ = 'https://www.googleapis.com/auth/youtube.readonly'
YT_ANALYTICS = 'https://www.googleapis.com/auth/yt-analytics.readonly'
YT_MONEY = 'https://www.googleapis.com/auth/yt-analytics-monetary.readonly'
SCOPES = {'youtube': frozenset({YT_READ, YT_ANALYTICS, YT_MONEY}),
          'tiktok': frozenset({'user.info.basic', 'video.list'})}
YT_METRICS = ('views', 'estimatedMinutesWatched', 'averageViewDuration', 'likes', 'comments', 'shares', 'subscribersGained')
YT_MAPPING = dict(zip(YT_METRICS, ('views', 'watch_time', 'average_view_duration', 'likes', 'comments', 'shares', 'followers_gained')))
TT_FIELDS = ('id', 'view_count', 'like_count', 'comment_count', 'share_count')
TT_MAPPING = {'view_count': 'views', 'like_count': 'likes', 'comment_count': 'comments', 'share_count': 'shares'}


class AnalyticsOfficialError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def fail(code):
    raise AnalyticsOfficialError(code)


class AnalyticsQuery(StrictModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    start_date: date
    end_date: date
    include_revenue: StrictBool = False

    @model_validator(mode='after')
    def ordered(self):
        if type(self.include_revenue) is not bool or self.end_date < self.start_date or (self.end_date - self.start_date).days > 365:
            raise ValueError('Analytics requires an ordered date interval of at most 366 days')
        return self


@dataclass(frozen=True)
class AnalyticsOAuthCredential:
    target: PublishingTargetBinding
    expires_at: datetime
    scopes: frozenset[str]
    token: str = field(repr=False)

    def __post_init__(self):
        try:
            PublishingTargetBinding.model_validate(self.target.model_dump())
            if (self.target.platform not in SCOPES or type(self.scopes) is not frozenset or not self.scopes
                or not self.scopes <= SCOPES[self.target.platform] or self.expires_at.tzinfo is None):
                raise ValueError()
            bearer_headers(self.token)
        except Exception:
            raise AnalyticsOfficialError('ANALYTICS_OAUTH_INVALID') from None


def resolve_credential(resolver, target, query, *, now=None):
    try:
        credential = resolver(target) if callable(resolver) else None
        if type(credential) is not AnalyticsOAuthCredential:
            raise ValueError()
        credential = AnalyticsOAuthCredential(credential.target, credential.expires_at, credential.scopes, credential.token)
    except Exception:
        raise AnalyticsOfficialError('ANALYTICS_OAUTH_NOT_CONFIGURED') from None
    current = now or datetime.now(timezone.utc)
    if credential.target != target:
        fail('ANALYTICS_OAUTH_TARGET_MISMATCH')
    if current.tzinfo is None or credential.expires_at <= current + timedelta(seconds=90):
        fail('ANALYTICS_OAUTH_REFRESH_REQUIRED')
    required = {YT_READ, YT_ANALYTICS} if target.platform == 'youtube' else {'user.info.basic', 'video.list'}
    if query and query.include_revenue:
        if target.platform != 'youtube': fail('ANALYTICS_REVENUE_UNSUPPORTED')
        required.add(YT_MONEY)
    if not required <= credential.scopes: fail('ANALYTICS_OAUTH_SCOPES_REQUIRED')
    return credential


def video_id(platform, value):
    pattern = r'[A-Za-z0-9_-]{11}' if platform == 'youtube' else r'[1-9][0-9]{0,18}' if platform == 'tiktok' else None
    if pattern is None or not isinstance(value, str) or not re.fullmatch(pattern, value):
        fail('ANALYTICS_VIDEO_ID_INVALID')
    if platform == 'tiktok' and int(value) > 2**63 - 1: fail('ANALYTICS_VIDEO_ID_INVALID')
    return value


def number(value, *, count=False):
    if value is None: return None
    if type(value) not in (int, float) or value < 0 or value > 2**53 - 1 or not math.isfinite(value) or (count and value != int(value)):
        fail('ANALYTICS_METRIC_INVALID')
    return float(value)


def response_object(response):
    if type(response) is not OfficialResponse: fail('ANALYTICS_RESPONSE_INVALID')
    if response.status == 429 or response.status >= 500:
        delay = response.headers.get('retry-after', '')
        delay = min(3600, int(delay)) if isinstance(delay, str) and re.fullmatch(r'[0-9]{1,9}', delay) else 30
        raise AnalyticsRateLimited(max(1, delay), 'ANALYTICS_PROVIDER_BACKOFF')
    if response.status in (401, 403): fail('ANALYTICS_AUTHORIZATION_REQUIRED')
    if response.status != 200: fail('ANALYTICS_PROVIDER_REJECTED')
    try:
        value = response.json_object()
        if isinstance(value.get('error'), dict) and value['error'].get('code') == 'rate_limit_exceeded':
            raise AnalyticsRateLimited(30, 'ANALYTICS_PROVIDER_BACKOFF')
        if 'error' in value and (not isinstance(value['error'], dict) or value['error'].get('code') != 'ok'):
            fail('ANALYTICS_PROVIDER_REJECTED')
        return value
    except (AnalyticsOfficialError, AnalyticsRateLimited): raise
    except Exception: raise AnalyticsOfficialError('ANALYTICS_RESPONSE_INVALID') from None


class AnalyticsHTTPClient:
    """Fixed read endpoints only; upload, publish, deletion and arbitrary graphs are forbidden."""
    def __init__(self, platform, *, network_enabled=False, transport=None):
        if platform not in SCOPES: fail('ANALYTICS_PLATFORM_NOT_CONFIGURED')
        self.platform = platform
        self.wire = OfficialHTTPClient('analytics_' + platform, network_enabled=network_enabled, transport=transport)

    @property
    def mock(self): return self.wire.transport is not None

    @property
    def enabled(self): return self.mock or self.wire.network_enabled is True

    async def request(self, request):
        parsed = urlsplit(request.url)
        allowed = ({('GET', 'www.googleapis.com', '/youtube/v3/channels'),
                    ('GET', 'www.googleapis.com', '/youtube/v3/videos'),
                    ('GET', 'youtubeanalytics.googleapis.com', '/v2/reports')}
                   if self.platform == 'youtube' else
                   {('GET', 'open.tiktokapis.com', '/v2/user/info/'), ('POST', 'open.tiktokapis.com', '/v2/video/query/')})
        if (request.method, parsed.hostname, parsed.path) not in allowed: fail('ANALYTICS_READ_ONLY_ENDPOINT_REQUIRED')
        if request.method == 'GET' and request.body: fail('ANALYTICS_READ_ONLY_ENDPOINT_REQUIRED')
        return await self.wire.request(request)


def account_request(credential):
    url = ('https://www.googleapis.com/youtube/v3/channels?part=id&mine=true&maxResults=2'
           if credential.target.platform == 'youtube' else 'https://open.tiktokapis.com/v2/user/info/?fields=open_id')
    return OfficialRequest('GET', url, bearer_headers(credential.token))


def confirm_account(response, target):
    value = response_object(response)
    if target.platform == 'youtube':
        items = value.get('items')
        if not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict) or value.get('nextPageToken'):
            fail('ANALYTICS_ACCOUNT_NOT_CONFIRMED')
        account = items[0].get('id')
    else:
        user = (value.get('data') or {}).get('user') if isinstance(value.get('data'), dict) else None
        account = user.get('open_id') if isinstance(user, dict) else None
    if account != target.target_account_id: fail('ANALYTICS_ACCOUNT_NOT_CONFIRMED')
    return {'account_match': True, 'target_binding_sha256': target_digest(target)}


def youtube_video_request(credential, remote_id):
    remote_id = video_id('youtube', remote_id)
    return OfficialRequest('GET', 'https://www.googleapis.com/youtube/v3/videos?' + urlencode({'part': 'snippet', 'id': remote_id}), bearer_headers(credential.token))


def confirm_youtube_video(response, target, remote_id):
    items = response_object(response).get('items')
    if (not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict)
        or items[0].get('id') != remote_id or not isinstance(items[0].get('snippet'), dict)
        or items[0]['snippet'].get('channelId') != target.target_account_id):
        fail('ANALYTICS_VIDEO_OWNERSHIP_NOT_CONFIRMED')


def youtube_report_request(credential, remote_id, query):
    remote_id = video_id('youtube', remote_id)
    query = AnalyticsQuery.model_validate(query.model_dump())
    metrics = (*YT_METRICS, 'estimatedRevenue') if query.include_revenue else YT_METRICS
    params = {'ids': 'channel==' + credential.target.target_account_id, 'startDate': query.start_date.isoformat(),
              'endDate': query.end_date.isoformat(), 'filters': 'video==' + remote_id,
              'metrics': ','.join(metrics), 'maxResults': '2', 'currency': 'VND'}
    return OfficialRequest('GET', 'https://youtubeanalytics.googleapis.com/v2/reports?' + urlencode(params), bearer_headers(credential.token))


def youtube_metrics(response, query):
    value = response_object(response)
    expected = (*YT_METRICS, 'estimatedRevenue') if query.include_revenue else YT_METRICS
    headers = value.get('columnHeaders'); rows = value.get('rows', [])
    if (not isinstance(headers, list) or len(headers) != len(expected)
        or any(not isinstance(header, dict) or header.get('name') != name or header.get('columnType') != 'METRIC'
               or header.get('dataType') not in ('INTEGER', 'FLOAT') for header, name in zip(headers, expected))
        or not isinstance(rows, list) or len(rows) > 1): fail('ANALYTICS_REPORT_SHAPE_INVALID')
    result = {}
    if rows:
        if not isinstance(rows[0], list) or len(rows[0]) != len(expected): fail('ANALYTICS_REPORT_SHAPE_INVALID')
        for name, raw in zip(expected, rows[0]):
            normalized = 'revenue' if name == 'estimatedRevenue' else YT_MAPPING[name]
            scalar = number(raw, count=name in ('views', 'likes', 'comments', 'shares', 'subscribersGained'))
            result[normalized] = scalar * 60 if name == 'estimatedMinutesWatched' and scalar is not None else scalar
    # Requested dates are not proof of complete coverage or an observed window.
    return NormalizedMetrics(**result), {'query': query.model_dump(mode='json'), 'row_count': len(rows),
        'currency': 'VND' if query.include_revenue else None, 'revenue_basis': 'provider_estimate' if query.include_revenue else None,
        'metric_mapping': {**YT_MAPPING, **({'estimatedRevenue': 'revenue'} if query.include_revenue else {})},
        'watch_time_conversion': 'minutes * 60', 'observed_window_hours': None, 'coverage_end_date': None,
        'completion_rate_supported': False, 'rpm_derived': False}


def tiktok_video_request(credential, remote_id):
    remote_id = video_id('tiktok', remote_id)
    body = json.dumps({'filters': {'video_ids': [remote_id]}}, separators=(',', ':')).encode()
    return OfficialRequest('POST', 'https://open.tiktokapis.com/v2/video/query/?' + urlencode({'fields': ','.join(TT_FIELDS)}),
                           {**bearer_headers(credential.token), 'Content-Type': 'application/json'}, body)


def tiktok_metrics(response, remote_id):
    value = response_object(response); data = value.get('data')
    videos = data.get('videos') if isinstance(data, dict) else None
    if not isinstance(videos, list) or len(videos) > 1: fail('ANALYTICS_REPORT_SHAPE_INVALID')
    result = {}
    if videos:
        if not isinstance(videos[0], dict) or videos[0].get('id') != remote_id: fail('ANALYTICS_VIDEO_OWNERSHIP_NOT_CONFIRMED')
        result = {normalized: number(videos[0].get(name), count=True) for name, normalized in TT_MAPPING.items()}
    return NormalizedMetrics(**result), {'metric_mapping': TT_MAPPING, 'row_count': len(videos),
        'metric_scope': 'cumulative_video_counters', 'observed_window_hours': None,
        'watch_time_supported': False, 'completion_rate_supported': False, 'revenue_supported': False}


def response_digest(response):
    return hashlib.sha256(response.body).hexdigest()
