from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.publishing_models import PublicationMetadata
from app.publishing_wire import OfficialHTTPClient, OfficialResponse, PublishingWireError
from app.youtube_upload import UNIT, UploadSession, chunk_request, delete_request, start_request, started_session, status_request, upload_progress, video_status, video_status_request


TOKEN = 'explicit-fixture-token-' + 'x' * 48
URI = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=PRIVATE_SESSION'
VID = 'AbcD_12-345'
NOW = datetime(2026, 10, 7, 9, 0, tzinfo=timezone.utc)


def start(metadata=None, **changes):
    return start_request(metadata or PublicationMetadata(title='Tiếng Việt · AI dễ hiểu', description='Nguồn được kiểm chứng.', caption='Ví dụ minh họa.', hashtags=['AI']),
        UNIT + 3, TOKEN, **{'category_id': '27', 'made_for_kids': False, 'contains_synthetic_media': True, **changes})


def test_metadata_preserves_vietnamese_caption_privacy_and_explicit_disclosures():
    request = start(); payload = json.loads(request.body)
    assert request.method == 'POST' and 'notifySubscribers=false' in request.url
    assert payload['snippet']['title'] == 'Tiếng Việt · AI dễ hiểu'
    assert payload['snippet']['description'] == 'Nguồn được kiểm chứng.\n\nVí dụ minh họa.\n\n#AI'
    assert payload['status'] == {'privacyStatus': 'private', 'selfDeclaredMadeForKids': False, 'containsSyntheticMedia': True}
    assert request.headers['Content-Length'] == str(len(request.body)) and request.headers['X-Upload-Content-Type'] == 'video/mp4'
    assert not any(key.lower() == 'idempotency-key' for key in request.headers)


@pytest.mark.parametrize('changes', [{'title': 'x' * 101}, {'title': '<invalid>'}, {'description': 'ế' * 2000},
    {'description': '<private>'}, {'hashtags': ['a' * 79 + str(i) for i in range(7)]}, {'thumbnail_asset_id': 'ast_explicit_fixture'}])
def test_unsupported_metadata_is_not_silently_published(changes):
    with pytest.raises(PublishingWireError): start(PublicationMetadata(title='Fixture', **{k:v for k,v in changes.items() if k!='title'}) if 'title' not in changes else PublicationMetadata(**changes))


def test_disclosures_category_and_future_private_schedule_are_required():
    for changes in ({'made_for_kids': None}, {'contains_synthetic_media': 'true'}, {'category_id': ''}):
        with pytest.raises(PublishingWireError): start(**changes)
    for metadata in (PublicationMetadata(title='Fixture', scheduled_at=NOW - timedelta(seconds=1)),
        PublicationMetadata(title='Fixture', privacy='public', scheduled_at=NOW + timedelta(hours=1))):
        with pytest.raises(PublishingWireError, match='YOUTUBE_FUTURE_PRIVATE_SCHEDULE_REQUIRED'): start(metadata, now=NOW)
    assert json.loads(start(PublicationMetadata(title='Fixture', scheduled_at=NOW + timedelta(hours=1)), now=NOW).body)['status']['publishAt'] == '2026-10-07T10:00:00Z'


def test_session_initialization_requires_confirmed_official_location_and_hides_it_in_repr():
    session = started_session(OfficialResponse(200, {'location': URI}, b''), UNIT + 3)
    assert 'PRIVATE_SESSION' not in repr(session)
    for response in (OfficialResponse(500, {}, b'PRIVATE'), OfficialResponse(200, {}, b''),
        OfficialResponse(200, {'location': 'https://evil.test/PRIVATE'}, b''),
        OfficialResponse(200, {'location': 'https://www.googleapis.com/wrong?x=y'}, b'')):
        with pytest.raises(PublishingWireError) as caught: started_session(response, UNIT)
        assert caught.value.uncertain and 'PRIVATE' not in str(caught.value)


def test_chunks_query_server_before_resume_and_use_exact_continuous_acknowledged_offset():
    session = UploadSession(URI, UNIT + 3)
    assert status_request(session, TOKEN).headers['Content-Range'] == f'bytes */{UNIT + 3}'
    progress = upload_progress(OfficialResponse(308, {'range': f'bytes=0-{UNIT-1}', 'retry-after': '10'}, b''), session)
    assert progress.acknowledged_bytes == UNIT and progress.retry_after == 10
    request = chunk_request(session, progress.acknowledged_bytes, b'end', TOKEN, chunk_size=UNIT)
    assert request.headers['Content-Range'] == f'bytes {UNIT}-{UNIT+2}/{UNIT+3}'
    assert upload_progress(OfficialResponse(201, {}, json.dumps({'id': VID}).encode()), session).remote_video_id == VID
    for offset, content, size in ((0, b'bad', UNIT), (True, b'bad', UNIT), (UNIT, b'end', 123), (UNIT+3, b'end', UNIT), (UNIT, b'toolong', UNIT)):
        with pytest.raises(PublishingWireError): chunk_request(session, offset, content, TOKEN, chunk_size=size)


def test_malformed_ranges_receipts_and_retry_after_do_not_assume_upload_success():
    session = UploadSession(URI, UNIT)
    assert upload_progress(OfficialResponse(308, {}, b''), session).acknowledged_bytes == 0
    for headers in ({'range': 'bytes=1-5'}, {'range': f'bytes=0-{UNIT}'}, {'range': 'PRIVATE'}, {'retry-after': '9999'}):
        with pytest.raises(PublishingWireError) as caught: upload_progress(OfficialResponse(308, headers, b''), session)
        assert caught.value.uncertain and 'PRIVATE' not in str(caught.value)
    with pytest.raises(PublishingWireError, match='YOUTUBE_UPLOAD_COMPLETION_UNCONFIRMED'): upload_progress(OfficialResponse(201, {}, b'{}'), session)
    assert upload_progress(OfficialResponse(404, {}, b''), session).status == 'session_expired_requires_review'
    assert upload_progress(OfficialResponse(503, {}, b''), session).status == 'reconciliation_required'
    assert upload_progress(OfficialResponse(401, {}, b''), session).status == 'failed_requires_review'


@pytest.mark.asyncio
async def test_full_mock_official_http_sequence_keeps_one_init_then_queries_before_resuming():
    calls = []
    def handler(request):
        calls.append(request)
        if request.method == 'POST': return httpx.Response(200, headers={'Location': URI})
        if request.headers['content-range'].startswith('bytes */'): return httpx.Response(308, headers={'Range': f'bytes=0-{UNIT-1}'})
        assert request.content == b'end'; return httpx.Response(201, json={'id': VID})
    client = OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler))
    session = started_session(await client.request(start()), UNIT+3)
    progress = upload_progress(await client.request(status_request(session, TOKEN)), session)
    done = upload_progress(await client.request(chunk_request(session, progress.acknowledged_bytes, b'end', TOKEN, chunk_size=UNIT)), session)
    assert done.remote_video_id == VID and [call.method for call in calls] == ['POST','PUT','PUT']


def test_processing_status_is_scoped_to_the_exact_known_video_and_never_invents_metrics():
    request = video_status_request(VID, TOKEN); assert request.method == 'GET' and 'processingDetails' in request.url
    for state, expected in [('succeeded','processed'),('processing','processing'),('failed','failed_requires_review'),('unknown','unknown')]:
        response = OfficialResponse(200, {}, json.dumps({'items':[{'id':VID,'processingDetails':{'processingStatus':state}}]}).encode())
        assert video_status(response, VID) == expected
    for items in ([], [{'id':'DifferentID'}], [{'id':VID},{'id':VID}]):
        with pytest.raises(PublishingWireError): video_status(OfficialResponse(200, {}, json.dumps({'items':items}).encode()), VID)
    assert delete_request(VID, TOKEN).method == 'DELETE'
