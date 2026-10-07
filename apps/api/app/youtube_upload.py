"""Official resumable request/response protocol; never initiates or retries itself."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from urllib.parse import urlencode, urlsplit

from .publishing_models import PublicationMetadata
from .publishing_wire import MAX_BODY, OfficialRequest, OfficialResponse, PublishingWireError, bearer_headers, official_url


UNIT = 256 * 1024
DEFAULT_CHUNK = 8 * 1024 * 1024
MAX_UPLOAD = 512 * 1024 * 1024  # Internal safe profile, not the platform maximum.
ORIGIN = 'https://www.googleapis.com'


def size_bytes(value):
    if type(value) is not int or not 1 <= value <= MAX_UPLOAD:
        raise PublishingWireError('YOUTUBE_UPLOAD_SIZE_INVALID')
    return value


def upload_uri(value):
    official_url(value, 'youtube')
    if urlsplit(value).path != '/upload/youtube/v3/videos' or not urlsplit(value).query:
        raise PublishingWireError('YOUTUBE_UPLOAD_SESSION_INVALID')
    return value


def video_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{11}', value):
        raise PublishingWireError('YOUTUBE_VIDEO_ID_INVALID')
    return value


@dataclass(frozen=True)
class UploadProgress:
    status: str
    acknowledged_bytes: int | None
    remote_video_id: str | None = None
    retry_after: int | None = None


@dataclass(frozen=True)
class UploadSession:
    uri: str = field(repr=False)
    total_bytes: int

    def __post_init__(self):
        upload_uri(self.uri); size_bytes(self.total_bytes)


def start_request(metadata, total_bytes, token, *, category_id, made_for_kids, contains_synthetic_media, now=None):
    if not isinstance(metadata, PublicationMetadata) or type(made_for_kids) is not bool or type(contains_synthetic_media) is not bool:
        raise PublishingWireError('YOUTUBE_EXPLICIT_DISCLOSURES_REQUIRED')
    size_bytes(total_bytes)
    description = '\n\n'.join(part for part in (metadata.description,
        metadata.caption if metadata.caption != metadata.description else '',
        ' '.join('#' + tag for tag in metadata.hashtags)) if part)
    if not 1 <= len(metadata.title) <= 100 or '<' in metadata.title or '>' in metadata.title or len(description.encode('utf-8')) > 5000 or '<' in description or '>' in description:
        raise PublishingWireError('YOUTUBE_METADATA_INVALID')
    if not isinstance(category_id, str) or not re.fullmatch(r'[0-9]{1,3}', category_id):
        raise PublishingWireError('YOUTUBE_CATEGORY_REQUIRED')
    if sum(len(tag) for tag in metadata.hashtags) + max(0, len(metadata.hashtags) - 1) > 500:
        raise PublishingWireError('YOUTUBE_METADATA_INVALID')
    if metadata.thumbnail_asset_id:
        raise PublishingWireError('YOUTUBE_THUMBNAIL_STAGE_REQUIRED')
    status = {'privacyStatus': metadata.privacy, 'selfDeclaredMadeForKids': made_for_kids,
        'containsSyntheticMedia': contains_synthetic_media}
    if metadata.scheduled_at is not None:
        current = now or datetime.now(timezone.utc)
        if metadata.privacy != 'private' or current.tzinfo is None or metadata.scheduled_at <= current:
            raise PublishingWireError('YOUTUBE_FUTURE_PRIVATE_SCHEDULE_REQUIRED')
        status['publishAt'] = metadata.scheduled_at.astimezone(timezone.utc).isoformat().replace('+00:00', 'Z')
    body = json.dumps({'snippet': {'title': metadata.title, 'description': description,
        'tags': metadata.hashtags, 'categoryId': category_id}, 'status': status}, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    headers = {**bearer_headers(token), 'Content-Type': 'application/json; charset=UTF-8', 'Content-Length': str(len(body)),
        'X-Upload-Content-Length': str(total_bytes), 'X-Upload-Content-Type': 'video/mp4'}
    # No vendor idempotency header is invented. The application must persist a
    # dispatch intent BEFORE POST and never initiate another session on uncertainty.
    return OfficialRequest('POST', ORIGIN + '/upload/youtube/v3/videos?' + urlencode({
        'uploadType': 'resumable', 'part': 'snippet,status', 'notifySubscribers': 'false'}), headers, body)


def started_session(response, total_bytes):
    if not isinstance(response, OfficialResponse) or response.status not in (200, 201):
        raise PublishingWireError('YOUTUBE_UPLOAD_INIT_NOT_CONFIRMED', status=getattr(response, 'status', None), uncertain=True)
    try:
        return UploadSession(response.headers['location'], total_bytes)
    except (KeyError, PublishingWireError):
        raise PublishingWireError('YOUTUBE_UPLOAD_INIT_NOT_CONFIRMED', status=response.status, uncertain=True) from None


def status_request(session, token):
    if not isinstance(session, UploadSession):
        raise PublishingWireError('YOUTUBE_UPLOAD_SESSION_INVALID')
    return OfficialRequest('PUT', session.uri, {**bearer_headers(token), 'Content-Length': '0',
        'Content-Range': 'bytes */' + str(session.total_bytes)})


def chunk_request(session, offset, content, token, *, chunk_size=DEFAULT_CHUNK):
    if not isinstance(session, UploadSession) or type(offset) is not int or not 0 <= offset < session.total_bytes or not isinstance(content, bytes):
        raise PublishingWireError('YOUTUBE_UPLOAD_CHUNK_INVALID')
    if type(chunk_size) is not int or not UNIT <= chunk_size <= MAX_BODY or chunk_size % UNIT:
        raise PublishingWireError('YOUTUBE_UPLOAD_CHUNK_INVALID')
    remaining = session.total_bytes - offset
    if not 1 <= len(content) <= chunk_size or len(content) != min(chunk_size, remaining):
        raise PublishingWireError('YOUTUBE_UPLOAD_CHUNK_INVALID')
    return OfficialRequest('PUT', session.uri, {**bearer_headers(token), 'Content-Length': str(len(content)),
        'Content-Type': 'video/mp4', 'Content-Range': f'bytes {offset}-{offset + len(content) - 1}/{session.total_bytes}'}, content)


def upload_progress(response, session):
    if not isinstance(response, OfficialResponse) or not isinstance(session, UploadSession):
        raise PublishingWireError('YOUTUBE_UPLOAD_RESPONSE_INVALID')
    if response.status in (200, 201):
        try:
            identifier = video_id(response.json_object().get('id'))
        except PublishingWireError:
            raise PublishingWireError('YOUTUBE_UPLOAD_COMPLETION_UNCONFIRMED', status=response.status, uncertain=True) from None
        return UploadProgress('uploaded', session.total_bytes, identifier)
    if response.status == 308:
        raw_range = response.headers.get('range')
        if raw_range is None:
            acknowledged = 0
        else:
            match = re.fullmatch(r'bytes=0-([0-9]{1,12})', raw_range)
            if not match or int(match[1]) >= session.total_bytes:
                raise PublishingWireError('YOUTUBE_UPLOAD_RANGE_INVALID', uncertain=True)
            acknowledged = int(match[1]) + 1
        retry_after = response.headers.get('retry-after')
        if retry_after is not None and (not re.fullmatch(r'[0-9]{1,4}', retry_after) or not 1 <= int(retry_after) <= 3600):
            raise PublishingWireError('YOUTUBE_RETRY_AFTER_INVALID', uncertain=True)
        return UploadProgress('uploading', acknowledged, retry_after=int(retry_after) if retry_after else None)
    if response.status in (404, 410):
        # Do not follow the vendor's start-over suggestion automatically: a lost
        # final response may already have created a post. Explicit reconciliation.
        return UploadProgress('session_expired_requires_review', None)
    if response.status == 429 or response.status >= 500:
        return UploadProgress('reconciliation_required', None)
    return UploadProgress('failed_requires_review', None)


def video_status_request(identifier, token):
    return OfficialRequest('GET', ORIGIN + '/youtube/v3/videos?' + urlencode({
        'part': 'status,processingDetails', 'id': video_id(identifier)}), bearer_headers(token))


def video_status(response, identifier):
    identifier = video_id(identifier)
    if not isinstance(response, OfficialResponse) or response.status != 200:
        raise PublishingWireError('YOUTUBE_STATUS_UNAVAILABLE', status=getattr(response, 'status', None))
    values = response.json_object().get('items')
    if not isinstance(values, list) or len(values) != 1 or not isinstance(values[0], dict) or values[0].get('id') != identifier:
        raise PublishingWireError('YOUTUBE_STATUS_REFERENCE_MISMATCH')
    status = values[0].get('status', {}); processing = values[0].get('processingDetails', {})
    if not isinstance(status, dict) or not isinstance(processing, dict):
        raise PublishingWireError('YOUTUBE_PROVIDER_STATUS_INVALID')
    upload, state = status.get('uploadStatus'), processing.get('processingStatus')
    if upload in ('deleted', 'failed', 'rejected') or state in ('failed', 'terminated'):
        return 'failed_requires_review'
    if state == 'succeeded' or upload == 'processed':
        return 'processed'
    if state == 'processing' or upload == 'uploaded':
        return 'processing'
    return 'unknown'


def delete_request(identifier, token):
    # A distinct application Owner delete approval is required before dispatch.
    return OfficialRequest('DELETE', ORIGIN + '/youtube/v3/videos?' + urlencode({'id': video_id(identifier)}), bearer_headers(token))
