"""Inert Meta Facebook-Login publishing contracts; no account/authority claim."""
from dataclasses import dataclass, field
import re
from urllib.parse import urlencode, urlsplit

from .publishing_models import PublicationMetadata
from .publishing_wire import (MAX_BODY, OfficialRequest, OfficialResponse, PublishingWireError,
    bearer_headers, official_url)
from .tiktok_upload import verified_pull_url

GRAPH = 'https://graph.facebook.com'
RUPLOAD = 'https://rupload.facebook.com'


def fail(code, **context):
    raise PublishingWireError(code, **context)


def numeric_id(value):
    if type(value) is not str or not re.fullmatch(r'[1-9][0-9]{0,31}', value): fail('META_OBJECT_ID_INVALID')
    return value


def api_version(value):
    if type(value) is not str or not re.fullmatch(r'v[1-9][0-9]{0,2}\.0', value): fail('META_EXPLICIT_API_VERSION_REQUIRED')
    return value  # Format only; configured version/provider acceptance is separate.


@dataclass(frozen=True)
class GraphTarget:
    platform: str
    account_id: str
    api_version: str
    login_type: str

    def __post_init__(self):
        numeric_id(self.account_id); api_version(self.api_version)
        if self.platform not in ('instagram_reels', 'facebook') or self.login_type != 'facebook_login':
            fail('META_FACEBOOK_LOGIN_TARGET_REQUIRED')


def graph_request(target, method, suffix, token, fields):
    if type(target) is not GraphTarget: fail('META_TARGET_REQUIRED')
    url = f'{GRAPH}/{target.api_version}/{suffix}'
    if method == 'GET': return OfficialRequest(method, url + '?' + urlencode(fields), bearer_headers(token))
    body = urlencode(fields).encode('utf-8')
    return OfficialRequest('POST', url, {**bearer_headers(token), 'Content-Type': 'application/x-www-form-urlencoded',
        'Content-Length': str(len(body))}, body)


def response_object(response, *, mutating=False):
    if type(response) is not OfficialResponse: fail('META_RESPONSE_INVALID', uncertain=mutating)
    if response.status == 429 or response.status >= 500:
        delay = response.headers.get('retry-after')
        delay = min(3600, int(delay)) if type(delay) is str and re.fullmatch(r'[0-9]{1,6}', delay) else None
        fail('META_RATE_LIMIT' if response.status == 429 else 'META_PROVIDER_UNAVAILABLE',
            status=response.status, uncertain=mutating, retry_after=delay)
    try: value = response.json_object()
    except PublishingWireError: fail('META_RESPONSE_INVALID', status=response.status, uncertain=mutating)
    if response.status not in (200, 201) or 'error' in value:
        fail('META_OPERATION_NOT_CONFIRMED', status=response.status, uncertain=mutating)
    return value


def caption(metadata):
    try: metadata = PublicationMetadata.model_validate(metadata.model_dump())
    except Exception: fail('META_METADATA_INVALID')
    if metadata.scheduled_at is not None: fail('META_LOCAL_SCHEDULER_REQUIRED')
    if metadata.thumbnail_asset_id: fail('META_THUMBNAIL_STAGE_REQUIRED')
    return '\n\n'.join(dict.fromkeys(part for part in (metadata.title, metadata.description, metadata.caption,
        ' '.join('#' + tag for tag in metadata.hashtags)) if part))


def media_pull_url(value, prefix):
    try: return verified_pull_url(value, prefix)
    except PublishingWireError:
        raise PublishingWireError('META_AUTHORIZED_MEDIA_PREFIX_REQUIRED') from None


def ig_create_request(target, metadata, token, *, video_url, authorized_prefix, share_to_feed):
    if type(target) is not GraphTarget or target.platform != 'instagram_reels': fail('META_INSTAGRAM_TARGET_REQUIRED')
    text = caption(metadata)
    if type(share_to_feed) is not bool or metadata.privacy != 'public' or len(text) > 2200:
        fail('META_INSTAGRAM_EXPLICIT_PUBLIC_OPTIONS_REQUIRED')
    return graph_request(target, 'POST', target.account_id + '/media', token,
        {'media_type': 'REELS', 'video_url': media_pull_url(video_url, authorized_prefix),
            'caption': text, 'share_to_feed': 'true' if share_to_feed else 'false'})


def created_id(response):
    try: return numeric_id(response_object(response, mutating=True)['id'])
    except (KeyError, PublishingWireError):
        raise PublishingWireError('META_CREATE_OUTCOME_UNCONFIRMED', uncertain=True) from None


def ig_container_request(target, container_id, token):
    if type(target) is not GraphTarget or target.platform != 'instagram_reels': fail('META_INSTAGRAM_TARGET_REQUIRED')
    return graph_request(target, 'GET', numeric_id(container_id), token, {'fields': 'id,status_code'})


@dataclass(frozen=True)
class ContainerObservation:
    target: GraphTarget
    container_id: str
    provider_status: str | None

    @property
    def ready(self): return self.provider_status == 'FINISHED'


def ig_container_observation(response, target, container_id):
    if type(target) is not GraphTarget or target.platform != 'instagram_reels': fail('META_INSTAGRAM_TARGET_REQUIRED')
    value = response_object(response)
    if value.get('id') != numeric_id(container_id): fail('META_CONTAINER_SCOPE_MISMATCH')
    status = value.get('status_code')
    if status is not None and (type(status) is not str or not re.fullmatch(r'[A-Z_]{1,32}', status)):
        fail('META_CONTAINER_STATUS_INVALID')
    return ContainerObservation(target, container_id, status)  # Unknown status is retained, never ready.


def ig_publish_request(target, observation, token):
    if type(target) is not GraphTarget or target.platform != 'instagram_reels': fail('META_INSTAGRAM_TARGET_REQUIRED')
    if type(observation) is not ContainerObservation or observation.target != target or observation.ready is not True:
        fail('META_CONTAINER_NOT_READY')
    return graph_request(target, 'POST', target.account_id + '/media_publish', token, {'creation_id': numeric_id(observation.container_id)})


@dataclass(frozen=True)
class FacebookUploadSession:
    target: GraphTarget
    video_id: str
    uri: str = field(repr=False)

    def __post_init__(self):
        if type(self.target) is not GraphTarget or self.target.platform != 'facebook': fail('META_FACEBOOK_TARGET_REQUIRED')
        numeric_id(self.video_id); official_url(self.uri, 'facebook')
        parsed = urlsplit(self.uri)
        if (parsed.hostname != 'rupload.facebook.com' or parsed.query
            or parsed.path != f'/video-upload/{self.target.api_version}/{self.video_id}'):
            fail('META_UPLOAD_SESSION_SCOPE_MISMATCH')


def fb_create_request(target, token):
    if type(target) is not GraphTarget or target.platform != 'facebook': fail('META_FACEBOOK_TARGET_REQUIRED')
    return graph_request(target, 'POST', target.account_id + '/video_reels', token, {'upload_phase': 'start'})


def fb_created_session(response, target):
    value = response_object(response, mutating=True)
    try: return FacebookUploadSession(target, value['video_id'], value['upload_url'])
    except (KeyError, PublishingWireError):
        raise PublishingWireError('META_UPLOAD_INIT_NOT_CONFIRMED', uncertain=True) from None


def fb_upload_request(session, token, *, content=None, video_url=None, authorized_prefix=None):
    if type(session) is not FacebookUploadSession: fail('META_UPLOAD_SESSION_REQUIRED')
    headers = {'Authorization': bearer_headers(token)['Authorization'].replace('Bearer ', 'OAuth ', 1)}
    if content is not None:
        if type(content) is not bytes or not 1 <= len(content) <= MAX_BODY or video_url is not None:
            fail('META_BOUNDED_UPLOAD_BODY_REQUIRED')
        headers.update({'offset': '0', 'file_size': str(len(content)), 'Content-Length': str(len(content)),
            'Content-Type': 'application/octet-stream'})
        body = content
    else:
        headers['file_url'] = media_pull_url(video_url, authorized_prefix); body = b''
    return OfficialRequest('POST', session.uri, headers, body)


def confirmed_success(response):
    if response_object(response, mutating=True).get('success') is not True:
        fail('META_MUTATION_OUTCOME_UNCONFIRMED', uncertain=True)
    return True  # Operation success, not a completed public post.


def fb_status_request(target, video_id, token):
    if type(target) is not GraphTarget or target.platform != 'facebook': fail('META_FACEBOOK_TARGET_REQUIRED')
    return graph_request(target, 'GET', numeric_id(video_id), token, {'fields': 'id,status'})


@dataclass(frozen=True)
class FacebookObservation:
    video_id: str
    video_status: str | None
    uploading_phase: str | None
    processing_phase: str | None
    publishing_phase: str | None
    processing_progress: int | None


def fb_observation(response, video_id):
    value = response_object(response)
    if value.get('id') != numeric_id(video_id) or type(value.get('status')) is not dict: fail('META_VIDEO_SCOPE_MISMATCH')
    status = value['status']; phases = []
    for name in ('uploading_phase', 'processing_phase', 'publishing_phase'):
        row = status.get(name)
        if row is not None and type(row) is not dict: fail('META_VIDEO_STATUS_INVALID')
        phases.append(row.get('status') if row else None)
    video = status.get('video_status'); progress = status.get('processing_progress')
    if (any(item is not None and (type(item) is not str or not re.fullmatch(r'[a-z_]{1,32}', item)) for item in [video, *phases])
        or progress is not None and (type(progress) is not int or not 0 <= progress <= 100)):
        fail('META_VIDEO_STATUS_INVALID')
    return FacebookObservation(video_id, video, *phases, progress)  # Missing observations remain null.


def fb_finish_request(target, video_id, metadata, token, *, video_state):
    if type(target) is not GraphTarget or target.platform != 'facebook': fail('META_FACEBOOK_TARGET_REQUIRED')
    text = caption(metadata)
    if (video_state not in ('DRAFT', 'PUBLISHED') or metadata.privacy not in ('private', 'public')
        or (video_state == 'DRAFT') != (metadata.privacy == 'private')):
        fail('META_FACEBOOK_EXPLICIT_STATE_REQUIRED')
    return graph_request(target, 'POST', target.account_id + '/video_reels', token,
        {'upload_phase': 'finish', 'video_id': numeric_id(video_id), 'video_state': video_state,
            'title': metadata.title, 'description': text})
