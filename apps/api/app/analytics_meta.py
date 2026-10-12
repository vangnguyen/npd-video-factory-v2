"""Closed Meta Facebook-Login analytics reads; no OAuth acquisition or startup.

Instagram media insights and Facebook video counters retain distinct bases.
No account total, reporting window, timestamp, watch-time unit or revenue is
inferred. The shared runtime supplies receipt, workspace, consent and cost gates.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

from .analytics_models import NormalizedMetrics
from .analytics_official import AnalyticsOfficialError, number
from .analytics_providers import AnalyticsRateLimited
from .meta_publishing_protocol import api_version, numeric_id
from .publishing_credentials import target_digest
from .publishing_models import PublishingTargetBinding
from .publishing_profiles import PROVIDER_KEYS
from .publishing_wire import (OfficialHTTPClient, OfficialRequest, OfficialResponse,
    PublishingWireError, bearer_headers, official_url)

PLATFORMS = frozenset({'instagram_reels', 'facebook'})
SCOPES = {
    'instagram_reels': frozenset({'instagram_basic', 'instagram_manage_insights', 'pages_read_engagement'}),
    'facebook': frozenset({'pages_read_engagement', 'read_insights'}),
}
REQUIRED_SCOPES = {**SCOPES, 'facebook': frozenset({'pages_read_engagement'})}
IG_MAPPING = {'views': 'views', 'reach': 'reach', 'likes': 'likes', 'comments': 'comments',
    'shares': 'shares', 'saved': 'saves'}
FB_MAPPING = {'views': 'views', 'likes.summary.total_count': 'likes', 'comments.summary.total_count': 'comments'}
FB_FIELDS = 'id,from,views,likes.limit(0).summary(true),comments.limit(0).summary(true)'


def fail(code):
    raise AnalyticsOfficialError(code)


def object_id(platform, value):
    if platform not in PLATFORMS: fail('ANALYTICS_PLATFORM_NOT_CONFIGURED')
    try: return numeric_id(value)
    except PublishingWireError: fail('ANALYTICS_VIDEO_ID_INVALID')


@dataclass(frozen=True)
class MetaAnalyticsCredential:
    target: PublishingTargetBinding
    api_version: str
    page_id: str
    expires_at: datetime
    scopes: frozenset[str]
    token: str = field(repr=False)

    def __post_init__(self):
        try:
            target = PublishingTargetBinding.model_validate(self.target.model_dump())
            if (target.platform not in PLATFORMS or target.provider_key != PROVIDER_KEYS[target.platform]
                or type(self.scopes) is not frozenset or not self.scopes
                or not self.scopes <= SCOPES[target.platform] | {'pages_show_list'}
                or not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None):
                raise ValueError()
            api_version(self.api_version); numeric_id(self.page_id); numeric_id(target.target_account_id)
            if target.platform == 'facebook' and self.page_id != target.target_account_id: raise ValueError()
            bearer_headers(self.token)
            object.__setattr__(self, 'target', target)
        except Exception:
            raise AnalyticsOfficialError('ANALYTICS_META_OAUTH_INVALID') from None


def resolve_credential(resolver, target, *, now=None):
    try:
        value = resolver(target) if callable(resolver) else None
        if type(value) is not MetaAnalyticsCredential: raise ValueError()
        credential = MetaAnalyticsCredential(value.target, value.api_version, value.page_id,
            value.expires_at, value.scopes, value.token)
    except Exception:
        raise AnalyticsOfficialError('ANALYTICS_META_OAUTH_NOT_CONFIGURED') from None
    current = now or datetime.now(timezone.utc)
    if credential.target != target: fail('ANALYTICS_OAUTH_TARGET_MISMATCH')
    if current.tzinfo is None or credential.expires_at <= current + timedelta(seconds=90):
        fail('ANALYTICS_OAUTH_REFRESH_REQUIRED')
    if not REQUIRED_SCOPES[target.platform] <= credential.scopes: fail('ANALYTICS_OAUTH_SCOPES_REQUIRED')
    return credential


class MetaAnalyticsHTTPClient:
    """Explicit version, one official origin and closed GET query shapes only."""
    def __init__(self, platform, *, api_version, network_enabled=False, transport=None):
        if platform not in PLATFORMS: fail('ANALYTICS_PLATFORM_NOT_CONFIGURED')
        try:
            from .meta_publishing_protocol import api_version as validate_version
            validate_version(api_version)
        except PublishingWireError: fail('ANALYTICS_META_VERSION_REQUIRED')
        self.platform, self.api_version = platform, api_version
        self.wire = OfficialHTTPClient('analytics_' + platform, network_enabled=network_enabled, transport=transport)

    @property
    def mock(self): return self.wire.transport is not None

    @property
    def enabled(self): return self.mock or self.wire.network_enabled is True

    async def request(self, request):
        try:
            if type(request) is not OfficialRequest: raise ValueError()
            parsed = urlsplit(official_url(request.url, 'analytics_' + self.platform))
            pairs = parse_qsl(parsed.query, keep_blank_values=True)
            params = dict(pairs)
            if request.method != 'GET' or request.body or len(params) != len(pairs): raise ValueError()
            prefix = '/' + self.api_version + '/'
            if not parsed.path.startswith(prefix): raise ValueError()
            suffix = parsed.path[len(prefix):]
            if suffix == 'me':
                fields = 'id,instagram_business_account' if self.platform == 'instagram_reels' else 'id'
                valid = params == {'fields': fields}
            elif re.fullmatch(r'[1-9][0-9]{0,31}', suffix):
                fields = 'id,owner,media_product_type' if self.platform == 'instagram_reels' else 'id,from'
                valid = params == {'fields': fields} or self.platform == 'facebook' and params == {'fields': FB_FIELDS}
            elif self.platform == 'instagram_reels' and re.fullmatch(r'[1-9][0-9]{0,31}/insights', suffix):
                valid = params == {'metric': ','.join(IG_MAPPING), 'period': 'lifetime'}
            else: valid = False
            if not valid: raise ValueError()
        except (ValueError, PublishingWireError, AttributeError):
            raise AnalyticsOfficialError('ANALYTICS_READ_ONLY_ENDPOINT_REQUIRED') from None
        return await self.wire.request(request)


def _request(credential, suffix, params):
    if type(credential) is not MetaAnalyticsCredential: fail('ANALYTICS_META_OAUTH_INVALID')
    return OfficialRequest('GET', f'https://graph.facebook.com/{credential.api_version}/{suffix}?' + urlencode(params),
        bearer_headers(credential.token))


def account_request(credential):
    fields = 'id,instagram_business_account' if credential.target.platform == 'instagram_reels' else 'id'
    return _request(credential, 'me', {'fields': fields})


def response_object(response):
    if type(response) is not OfficialResponse: fail('ANALYTICS_RESPONSE_INVALID')
    if response.status == 429 or response.status >= 500:
        delay = response.headers.get('retry-after', '')
        delay = min(3600, int(delay)) if isinstance(delay, str) and re.fullmatch(r'[0-9]{1,9}', delay) else 30
        raise AnalyticsRateLimited(max(1, delay), 'ANALYTICS_PROVIDER_BACKOFF')
    try: value = response.json_object()
    except PublishingWireError: fail('ANALYTICS_RESPONSE_INVALID')
    error = value.get('error')
    if isinstance(error, dict) and type(error.get('code')) is int and error['code'] in (4, 17, 32, 613):
        raise AnalyticsRateLimited(30, 'ANALYTICS_PROVIDER_BACKOFF')
    if response.status in (401, 403) or isinstance(error, dict) and error.get('code') in (10, 190, 200):
        fail('ANALYTICS_AUTHORIZATION_REQUIRED')
    if response.status != 200 or error is not None: fail('ANALYTICS_PROVIDER_REJECTED')
    return value


def confirm_account(response, target, *, page_id):
    value = response_object(response)
    if value.get('id') != page_id: fail('ANALYTICS_ACCOUNT_NOT_CONFIRMED')
    if target.platform == 'instagram_reels':
        account = value.get('instagram_business_account')
        if not isinstance(account, dict) or account.get('id') != target.target_account_id:
            fail('ANALYTICS_ACCOUNT_NOT_CONFIRMED')
    elif target.platform != 'facebook' or value['id'] != target.target_account_id:
        fail('ANALYTICS_ACCOUNT_NOT_CONFIRMED')
    return {'account_match': True, 'target_binding_sha256': target_digest(target),
        'login_type': 'facebook_login', 'authenticated_page_match': True}


def ownership_request(credential, remote):
    remote = object_id(credential.target.platform, remote)
    fields = 'id,owner,media_product_type' if credential.target.platform == 'instagram_reels' else 'id,from'
    return _request(credential, remote, {'fields': fields})


def confirm_ownership(response, target, remote):
    value = response_object(response)
    owner = value.get('owner' if target.platform == 'instagram_reels' else 'from')
    if (value.get('id') != object_id(target.platform, remote) or not isinstance(owner, dict)
        or owner.get('id') != target.target_account_id
        or target.platform == 'instagram_reels' and value.get('media_product_type') != 'REELS'):
        fail('ANALYTICS_VIDEO_OWNERSHIP_NOT_CONFIRMED')
    return value


def metrics_request(credential, remote):
    remote = object_id(credential.target.platform, remote)
    if credential.target.platform == 'instagram_reels':
        return _request(credential, remote + '/insights', {'metric': ','.join(IG_MAPPING), 'period': 'lifetime'})
    return _request(credential, remote, {'fields': FB_FIELDS})


def metrics(response, target, remote, *, api_version):
    remote = object_id(target.platform, remote)
    value = response_object(response); result = {}; returned = []
    if target.platform == 'instagram_reels':
        rows = value.get('data')
        paging = value.get('paging', {})
        if (not isinstance(rows, list) or len(rows) > len(IG_MAPPING)
            or not isinstance(paging, dict) or paging.get('next')):
            fail('ANALYTICS_REPORT_SHAPE_INVALID')
        for row in rows:
            if not isinstance(row, dict): fail('ANALYTICS_REPORT_SHAPE_INVALID')
            name = row.get('name'); values = row.get('values')
            if (type(name) is not str or name not in IG_MAPPING or name in returned or row.get('period') != 'lifetime'
                or row.get('id') != f'{remote}/insights/{name}/lifetime'
                or not isinstance(values, list) or len(values) > 1):
                fail('ANALYTICS_REPORT_SHAPE_INVALID')
            returned.append(name)
            if values:
                if not isinstance(values[0], dict): fail('ANALYTICS_REPORT_SHAPE_INVALID')
                result[IG_MAPPING[name]] = number(values[0].get('value'), count=True)
        mapping, scope = IG_MAPPING, 'lifetime_media_insights'
    else:
        confirm_ownership(response, target, remote)
        if 'views' in value:
            result['views'] = number(value['views'], count=True); returned.append('views')
        for name in ('likes', 'comments'):
            if name not in value: continue
            edge = value[name]
            if edge is None: continue
            if not isinstance(edge, dict) or edge.get('data') != []:
                fail('ANALYTICS_REPORT_SHAPE_INVALID')
            summary = edge.get('summary')
            if summary is None: continue
            if not isinstance(summary, dict): fail('ANALYTICS_REPORT_SHAPE_INVALID')
            if 'total_count' in summary:
                result[name] = number(summary['total_count'], count=True)
                returned.append(name + '.summary.total_count')
        mapping, scope = FB_MAPPING, 'cumulative_video_node_counters'
    normalized = NormalizedMetrics(**result)
    return normalized, {'schema_version': 'meta-analytics-counts-v1', 'api_version': api_version,
        'metric_mapping': mapping, 'returned_metrics': returned, 'metric_scope': scope,
        'query': None, 'coverage_end_date': None, 'observed_window_hours': None,
        'normalized_units': {key: 'count' for key, value in result.items() if value is not None},
        'unavailable_metrics': [key for key, value in normalized.model_dump().items() if value is None],
        'watch_time_unit_verified': False, 'completion_rate_supported': False, 'revenue_supported': False,
        'provider_metric_semantics_real_verified': False}
