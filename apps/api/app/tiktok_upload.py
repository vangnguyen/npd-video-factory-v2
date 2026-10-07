"""Official FILE_UPLOAD protocol; request builders never send or auto-retry."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import math
import re
from typing import Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import ConfigDict, Field, field_validator
from .models import StrictModel
from .publishing_models import PublicationMetadata
from .publishing_wire import (MAX_BODY, TIKTOK_UPLOAD_HOSTS, OfficialRequest,
    OfficialResponse, PublishingWireError, bearer_headers, official_url)

ORIGIN = 'https://open.tiktokapis.com'
MAX_UPLOAD = 512 * 1024 * 1024  # Internal supported profile, not platform maximum.
MIN_CHUNK = 5_000_000
DEFAULT_CHUNK = 8 * 1024 * 1024
PRIVACY = frozenset({'PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY'})


def fail(code, **kwargs):
    raise PublishingWireError(code, **kwargs)


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9._~:-]{1,64}', value):
        fail('TIKTOK_PUBLISH_ID_INVALID')
    return value


def upload_uri(value):
    official_url(value, 'tiktok')
    parsed = urlsplit(value)
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    if (len(value) > 256 or parsed.hostname not in TIKTOK_UPLOAD_HOSTS or parsed.path not in ('/video/', '/upload/')
        or len(pairs) != 2 or {key for key, _ in pairs} != {'upload_id', 'upload_token'}
        or any(not re.fullmatch(r'[A-Za-z0-9._~=-]{1,192}', content) for _, content in pairs)):
        fail('TIKTOK_UPLOAD_SESSION_INVALID')
    return value


def api_request(path, token, body):
    data = json.dumps(body, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    return OfficialRequest('POST', ORIGIN + path, {**bearer_headers(token),
        'Content-Type': 'application/json; charset=UTF-8', 'Content-Length': str(len(data))}, data)


def creator_request(token):
    return api_request('/v2/post/publish/creator_info/query/', token, {})


def response_data(response, *, mutating=False):
    if type(response) is not OfficialResponse:
        fail('TIKTOK_RESPONSE_INVALID', uncertain=mutating)
    if response.status == 429 or response.status >= 500:
        delay = response.headers.get('retry-after')
        delay = min(3600, int(delay)) if isinstance(delay, str) and re.fullmatch(r'[0-9]{1,6}', delay) else None
        fail('TIKTOK_RATE_LIMIT' if response.status == 429 else 'TIKTOK_PROVIDER_UNAVAILABLE',
            status=response.status, uncertain=mutating, retry_after=delay)
    try:
        try: value = response.json_object()
        except PublishingWireError:
            fail('TIKTOK_RESPONSE_INVALID', status=response.status, uncertain=mutating)
        if response.status != 200 or type(value.get('error')) is not dict or value['error'].get('code') != 'ok':
            fail('TIKTOK_OPERATION_NOT_CONFIRMED', status=response.status, uncertain=mutating)
        if type(value.get('data')) is not dict: raise ValueError()
        return value['data']
    except (ValueError, TypeError):
        fail('TIKTOK_RESPONSE_INVALID', status=response.status, uncertain=mutating)


@dataclass(frozen=True)
class CreatorInfo:
    username: str = field(repr=False)
    privacy_options: tuple[str, ...]
    comment_disabled: bool
    duet_disabled: bool
    stitch_disabled: bool
    max_duration_sec: int
    nickname: str | None = field(default=None, repr=False)

    def __post_init__(self):
        if (not isinstance(self.username, str) or not re.fullmatch(r'[A-Za-z0-9._]{1,64}', self.username)
            or type(self.privacy_options) is not tuple or not 1 <= len(self.privacy_options) <= 4
            or any(not isinstance(value, str) or value not in PRIVACY for value in self.privacy_options)
            or len(set(self.privacy_options)) != len(self.privacy_options)
            or any(type(value) is not bool for value in (self.comment_disabled, self.duet_disabled, self.stitch_disabled))
            or type(self.max_duration_sec) is not int or not 1 <= self.max_duration_sec <= 3600
            or (self.nickname is not None and (not isinstance(self.nickname, str)
                or not 1 <= len(self.nickname) <= 128 or any(ord(c) < 32 for c in self.nickname)))):
            fail('TIKTOK_CREATOR_INFO_INVALID')


def creator_info(response):
    data = response_data(response)
    try:
        return CreatorInfo(data['creator_username'], tuple(data['privacy_level_options']),
            data['comment_disabled'], data['duet_disabled'], data['stitch_disabled'], data['max_video_post_duration_sec'],
            data['creator_nickname'])
    except (KeyError, TypeError, ValueError):
        fail('TIKTOK_CREATOR_INFO_INVALID')


class PostChoices(StrictModel):
    """Explicit user selections; no privacy or interaction defaults."""
    model_config = ConfigDict(extra='forbid', strict=True, frozen=True)
    privacy_level: Literal['PUBLIC_TO_EVERYONE', 'MUTUAL_FOLLOW_FRIENDS', 'FOLLOWER_OF_CREATOR', 'SELF_ONLY']
    disable_comment: bool
    disable_duet: bool
    disable_stitch: bool
    brand_content_toggle: bool
    brand_organic_toggle: bool
    is_aigc: bool
    music_usage_confirmed: Literal[True]
    branded_content_policy_confirmed: Literal[True] | None = None
    video_cover_timestamp_ms: int | None = Field(default=None, ge=0, le=2_147_483_647)

    @field_validator('music_usage_confirmed', 'branded_content_policy_confirmed', mode='before')
    @classmethod
    def exact_confirmation(cls, value):
        if value is not None and value is not True:
            raise ValueError('confirmation must be the explicit boolean true')
        return value


@dataclass(frozen=True)
class ChunkPlan:
    total_bytes: int
    chunk_bytes: int = DEFAULT_CHUNK

    def __post_init__(self):
        if (type(self.total_bytes) is not int or not 1 <= self.total_bytes <= MAX_UPLOAD
            or type(self.chunk_bytes) is not int or not MIN_CHUNK <= self.chunk_bytes <= MAX_BODY // 2):
            fail('TIKTOK_CHUNK_PLAN_INVALID')

    @property
    def count(self):
        return max(1, self.total_bytes // self.chunk_bytes)

    @property
    def advertised_chunk_bytes(self):
        return min(self.chunk_bytes, self.total_bytes)

    def length(self, offset):
        if type(offset) is not int or offset < 0 or offset % self.chunk_bytes or offset // self.chunk_bytes >= self.count:
            fail('TIKTOK_CHUNK_OFFSET_INVALID')
        return self.total_bytes - offset if offset // self.chunk_bytes == self.count - 1 else self.chunk_bytes


def _post_info(metadata, *, creator, choices, duration_sec, client_audited):
    if type(metadata) is not PublicationMetadata or type(creator) is not CreatorInfo or type(choices) is not PostChoices:
        fail('TIKTOK_EXPLICIT_POST_CHOICES_REQUIRED')
    try:
        choices = PostChoices.model_validate(choices.model_dump())
        metadata = PublicationMetadata.model_validate(metadata.model_dump())
    except ValueError:
        fail('TIKTOK_EXPLICIT_POST_CHOICES_REQUIRED')
    if type(client_audited) is not bool or choices.privacy_level not in creator.privacy_options:
        fail('TIKTOK_PRIVACY_CHOICE_INVALID')
    if not client_audited and choices.privacy_level != 'SELF_ONLY': fail('TIKTOK_CLIENT_AUDIT_REQUIRED')
    if metadata.privacy not in ('private', 'public') or ((metadata.privacy == 'private') != (choices.privacy_level == 'SELF_ONLY')):
        fail('TIKTOK_METADATA_PRIVACY_MISMATCH')
    if metadata.scheduled_at is not None: fail('TIKTOK_LOCAL_SCHEDULER_REQUIRED')
    if metadata.thumbnail_asset_id: fail('TIKTOK_COVER_FRAME_REQUIRED')
    if type(duration_sec) not in (int, float) or not math.isfinite(duration_sec) or not 0 < duration_sec <= creator.max_duration_sec:
        fail('TIKTOK_CREATOR_DURATION_EXCEEDED')
    if choices.video_cover_timestamp_ms is not None and choices.video_cover_timestamp_ms >= duration_sec * 1000:
        fail('TIKTOK_COVER_FRAME_INVALID')
    if any(disabled and not selected for disabled, selected in (
        (creator.comment_disabled, choices.disable_comment), (creator.duet_disabled, choices.disable_duet),
        (creator.stitch_disabled, choices.disable_stitch))):
        fail('TIKTOK_CREATOR_INTERACTION_DISABLED')
    if choices.brand_content_toggle and choices.privacy_level == 'SELF_ONLY': fail('TIKTOK_BRANDED_PRIVATE_UNSUPPORTED')
    if choices.brand_content_toggle and choices.branded_content_policy_confirmed is not True:
        fail('TIKTOK_BRANDED_CONTENT_CONFIRMATION_REQUIRED')
    parts = list(dict.fromkeys(value for value in (metadata.title, metadata.description, metadata.caption,
        ' '.join('#' + tag for tag in metadata.hashtags)) if value))
    caption = '\n\n'.join(parts)
    try: units = len(caption.encode('utf-16-le')) // 2
    except UnicodeError: fail('TIKTOK_CAPTION_INVALID')
    if units > 2200: fail('TIKTOK_CAPTION_INVALID')
    post = {**choices.model_dump(exclude_none=True, exclude={'music_usage_confirmed', 'branded_content_policy_confirmed'}),
        'title': caption}
    return post


def start_request(metadata, plan, token, *, creator, choices, duration_sec, client_audited, media_location):
    if media_location != 'user_device': fail('TIKTOK_SERVER_MEDIA_VERIFIED_PULL_REQUIRED')
    if type(plan) is not ChunkPlan: fail('TIKTOK_CHUNK_PLAN_INVALID')
    post = _post_info(metadata, creator=creator, choices=choices, duration_sec=duration_sec, client_audited=client_audited)
    return api_request('/v2/post/publish/video/init/', token, {'post_info': post, 'source_info': {
        'source': 'FILE_UPLOAD', 'video_size': plan.total_bytes,
        'chunk_size': plan.advertised_chunk_bytes, 'total_chunk_count': plan.count}})


def verified_pull_url(value, prefix):
    """Match an injected, previously verified public prefix; never verify by assertion.

    Trusted configuration must establish TikTok dashboard ownership and URL lifetime.
    This pure builder does not fetch a URL or assert that verification happened.
    """
    try:
        parsed = []
        for raw in (value, prefix):
            if (not isinstance(raw, str) or not 1 <= len(raw) <= 2048 or not raw.isascii()
                or any(ord(c) < 33 for c in raw) or '\\' in raw): raise ValueError()
            item = urlsplit(raw); decoded = unquote(item.path)
            if (item.scheme != 'https' or not item.hostname or item.username or item.password or item.fragment
                or item.port not in (None, 443) or item.hostname in ('localhost', 'localhost.localdomain')
                or not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', item.hostname)
                or re.fullmatch(r'[0-9.]+', item.hostname)
                or any(part in ('.', '..') for part in decoded.split('/'))
                or '\\' in decoded or any(ord(c) < 32 for c in decoded)
                or re.search(r'%(?:2f|5c)', item.path, flags=re.IGNORECASE)):
                raise ValueError()
            parsed.append(item)
        video, owned = parsed
        if (owned.query or not owned.path.endswith('/') or not owned.path.startswith('/')
            or (video.hostname, video.port or 443) != (owned.hostname, owned.port or 443)
            or not video.path.startswith(owned.path) or video.path == owned.path): raise ValueError()
        return value
    except (TypeError, ValueError):
        fail('TIKTOK_VERIFIED_PULL_PREFIX_REQUIRED')


def pull_request(metadata, token, *, video_url, verified_prefix, creator, choices, duration_sec, client_audited):
    video_url = verified_pull_url(video_url, verified_prefix)
    post = _post_info(metadata, creator=creator, choices=choices, duration_sec=duration_sec, client_audited=client_audited)
    return api_request('/v2/post/publish/video/init/', token,
        {'post_info': post, 'source_info': {'source': 'PULL_FROM_URL', 'video_url': video_url}})


def started_pull(response):
    data = response_data(response, mutating=True)
    try: return identifier(data['publish_id'])
    except (KeyError, PublishingWireError): fail('TIKTOK_PULL_INIT_NOT_CONFIRMED', uncertain=True)


@dataclass(frozen=True)
class UploadSession:
    publish_id: str = field(repr=False)
    uri: str = field(repr=False)
    plan: ChunkPlan
    expires_at: datetime

    def __post_init__(self):
        identifier(self.publish_id); upload_uri(self.uri)
        if type(self.plan) is not ChunkPlan or type(self.expires_at) is not datetime or self.expires_at.tzinfo is None:
            fail('TIKTOK_UPLOAD_SESSION_INVALID')


def started_session(response, plan, *, now=None):
    data = response_data(response, mutating=True)
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None: fail('TIKTOK_UPLOAD_SESSION_INVALID')
    try: return UploadSession(data['publish_id'], data['upload_url'], plan, current + timedelta(hours=1))
    except (KeyError, TypeError, PublishingWireError):
        fail('TIKTOK_UPLOAD_INIT_NOT_CONFIRMED', uncertain=True)


def chunk_request(session, offset, content, *, now=None):
    if type(session) is not UploadSession: fail('TIKTOK_UPLOAD_SESSION_INVALID')
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None or current >= session.expires_at: fail('TIKTOK_UPLOAD_SESSION_EXPIRED')
    length = session.plan.length(offset)
    if not isinstance(content, bytes) or len(content) != length: fail('TIKTOK_CHUNK_LENGTH_INVALID')
    return OfficialRequest('PUT', session.uri, {'Content-Type': 'video/mp4', 'Content-Length': str(length),
        'Content-Range': f'bytes {offset}-{offset + length - 1}/{session.plan.total_bytes}'}, content)


def chunk_ack(response, plan, offset):
    end = offset + plan.length(offset)
    expected = 201 if end == plan.total_bytes else 206
    if type(response) is not OfficialResponse or response.status != expected:
        fail('TIKTOK_CHUNK_OUTCOME_UNCONFIRMED', status=getattr(response, 'status', None), uncertain=True)
    return end


def status_request(publish_id, token):
    return api_request('/v2/post/publish/status/fetch/', token, {'publish_id': identifier(publish_id)})


@dataclass(frozen=True)
class PostObservation:
    status: str
    uploaded_bytes: int | None
    public_post_ids: tuple[str, ...]
    failure_code: str | None = None


def post_observation(response, *, total_bytes):
    if type(total_bytes) is not int or not 1 <= total_bytes <= MAX_UPLOAD: fail('TIKTOK_UPLOAD_SIZE_INVALID')
    data = response_data(response)
    status = data.get('status')
    if status not in ('PROCESSING_UPLOAD', 'PROCESSING_DOWNLOAD', 'SEND_TO_USER_INBOX', 'PUBLISH_COMPLETE', 'FAILED'):
        fail('TIKTOK_POST_STATUS_INVALID')
    count = data.get('uploaded_bytes')
    if count is not None and (type(count) is not int or not 0 <= count <= total_bytes): fail('TIKTOK_POST_STATUS_INVALID')
    ids = data.get('publicaly_available_post_id', [])
    if type(ids) is not list or len(ids) > 50: fail('TIKTOK_POST_STATUS_INVALID')
    normalized = []
    for value in ids:
        if type(value) not in (int, str) or not re.fullmatch(r'[1-9][0-9]{0,18}', str(value)) or int(value) > 9_223_372_036_854_775_807:
            fail('TIKTOK_POST_STATUS_INVALID')
        normalized.append(str(value))
    if len(set(normalized)) != len(normalized) or (normalized and status != 'PUBLISH_COMPLETE'): fail('TIKTOK_POST_STATUS_INVALID')
    # Private posts can complete with no public ID; never invent an ID or URL.
    return PostObservation(status, count, tuple(normalized), 'TIKTOK_POST_FAILED' if status == 'FAILED' else None)
