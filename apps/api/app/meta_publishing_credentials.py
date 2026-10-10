"""Scoped Facebook-Login Page custody and readonly identity proofs.

Declared permissions and a successful lookup never establish app eligibility,
publication approval, rights or permission to publish.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json

from .meta_publishing_protocol import GraphTarget, graph_request, numeric_id
from .publishing_models import PublishingTargetBinding
from .publishing_wire import OfficialResponse, PublishingWireError, bearer_headers

PROVIDERS = {'facebook': 'facebook-graph-api-publishing',
    'instagram_reels': 'instagram-graph-api-publishing'}
REQUIRED = {'facebook': frozenset({'pages_read_engagement', 'pages_manage_posts'}),
    'instagram_reels': frozenset({'pages_read_engagement', 'instagram_basic', 'instagram_content_publish'})}
ALLOWED = frozenset({'pages_read_engagement', 'pages_manage_posts', 'pages_show_list',
    'instagram_basic', 'instagram_content_publish', 'ads_read', 'ads_management'})


@dataclass(frozen=True)
class MetaOAuthCredential:
    target: PublishingTargetBinding
    graph: GraphTarget
    page_id: str
    expires_at: datetime
    scopes: frozenset[str]
    token: str = field(repr=False)

    def __post_init__(self):
        try:
            if type(self.target) is not PublishingTargetBinding or type(self.graph) is not GraphTarget:
                raise ValueError()
            target = PublishingTargetBinding.model_validate(self.target.model_dump())
            graph = GraphTarget(self.graph.platform, self.graph.account_id, self.graph.api_version, self.graph.login_type)
            numeric_id(self.page_id); bearer_headers(self.token)
            if (target.platform not in PROVIDERS or target.provider_key != PROVIDERS[target.platform]
                or graph.platform != target.platform or graph.account_id != target.target_account_id
                or target.platform == 'facebook' and self.page_id != graph.account_id
                or type(self.scopes) is not frozenset or not REQUIRED[target.platform] <= self.scopes <= ALLOWED
                or type(self.expires_at) is not datetime or self.expires_at.tzinfo is None):
                raise ValueError()
        except Exception:
            raise PublishingWireError('META_SCOPED_CREDENTIAL_INVALID') from None


def resolve_meta_credential(resolver, target, graph, page_id, *, now=None):
    try:
        value = resolver(target) if callable(resolver) else None
        if type(value) is not MetaOAuthCredential: raise ValueError()
        value = MetaOAuthCredential(value.target, value.graph, value.page_id, value.expires_at, value.scopes, value.token)
        if value.target != target or value.graph != graph or value.page_id != page_id: raise ValueError()
    except Exception:
        raise PublishingWireError('META_SCOPED_CREDENTIAL_UNAVAILABLE') from None
    instant = now or datetime.now(timezone.utc)
    if type(instant) is not datetime or instant.tzinfo is None or value.expires_at <= instant + timedelta(seconds=90):
        raise PublishingWireError('META_SCOPED_CREDENTIAL_REFRESH_REQUIRED')
    return value


def page_identity_request(credential):
    if type(credential) is not MetaOAuthCredential: raise PublishingWireError('META_SCOPED_CREDENTIAL_INVALID')
    fields = 'id,instagram_business_account' if credential.target.platform == 'instagram_reels' else 'id'
    return graph_request(credential.graph, 'GET', 'me', credential.token, {'fields': fields})


def instagram_identity_request(credential):
    if type(credential) is not MetaOAuthCredential or credential.target.platform != 'instagram_reels':
        raise PublishingWireError('META_INSTAGRAM_TARGET_REQUIRED')
    return graph_request(credential.graph, 'GET', credential.graph.account_id, credential.token, {'fields': 'id'})


def identity_object(response):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError()
            result[key] = value
        return result
    if type(response) is not OfficialResponse: raise PublishingWireError('META_ACCOUNT_RESPONSE_INVALID')
    if response.status == 429 or response.status >= 500:
        delay = response.headers.get('retry-after')
        delay = min(3600, int(delay)) if type(delay) is str and delay.isascii() and delay.isdigit() and len(delay) <= 6 else None
        raise PublishingWireError('META_ACCOUNT_RATE_LIMIT' if response.status == 429 else 'META_ACCOUNT_PROVIDER_UNAVAILABLE', retry_after=delay)
    try:
        value = json.loads(response.body, object_pairs_hook=pairs)
        if response.status != 200 or type(value) is not dict or 'error' in value: raise ValueError()
        return value
    except Exception:
        raise PublishingWireError('META_ACCOUNT_RESPONSE_INVALID') from None


def confirm_page_identity(response, credential):
    value = identity_object(response)
    if value.get('id') != credential.page_id or type(value.get('id')) is not str:
        raise PublishingWireError('META_TOKEN_PAGE_NOT_CONFIRMED')
    if credential.target.platform == 'instagram_reels':
        linked = value.get('instagram_business_account')
        if type(linked) is not dict or type(linked.get('id')) is not str or linked['id'] != credential.target.target_account_id:
            raise PublishingWireError('META_LINKED_INSTAGRAM_NOT_CONFIRMED')
    return True


def confirm_instagram_identity(response, credential):
    value = identity_object(response)
    if credential.target.platform != 'instagram_reels' or type(value.get('id')) is not str or value['id'] != credential.target.target_account_id:
        raise PublishingWireError('META_INSTAGRAM_ACCOUNT_NOT_CONFIRMED')
    return True
