from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from pydantic import ValidationError

from app.publishing_models import PublicationMetadata
from app.publishing_wire import OfficialHTTPClient, OfficialRequest, OfficialResponse, PublishingWireError
from app.tiktok_upload import (ChunkPlan, CreatorInfo, PostChoices, UploadSession, chunk_ack,
    chunk_request, creator_info, creator_request, post_observation, start_request,
    started_pull, started_session, status_request, upload_uri, verified_pull_url, pull_request)

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
TOKEN = 'EXPLICIT_FIXTURE_ACCESS_TOKEN_123456'
URI = 'https://open-upload.tiktokapis.com/video/?upload_id=67890&upload_token=EXPLICIT_FIXTURE_UPLOAD_TOKEN'
CREATOR = CreatorInfo('fixture_creator', ('SELF_ONLY', 'PUBLIC_TO_EVERYONE'), False, False, True, 300)
CHOICES = dict(privacy_level='SELF_ONLY', disable_comment=False, disable_duet=False,
    disable_stitch=True, brand_content_toggle=False, brand_organic_toggle=False, is_aigc=True,
    music_usage_confirmed=True)


def response(data, status=200, error='ok'):
    return OfficialResponse(status, {}, json.dumps({'data': data,
        'error': {'code': error, 'message': 'DO_NOT_EXPOSE_PRIVATE_PROVIDER_MESSAGE'}}).encode())


def init(metadata=None, plan=None, creator=CREATOR, **overrides):
    choices = {**CHOICES, **overrides.pop('choices', {})}
    return start_request(metadata or PublicationMetadata(title='Học AI 😀', caption='Cần Giờ', hashtags=['ViệtNam']),
        plan or ChunkPlan(4_256_257), TOKEN, creator=creator, choices=PostChoices(**choices),
        duration_sec=overrides.pop('duration_sec', 3), client_audited=overrides.pop('client_audited', False),
        media_location=overrides.pop('media_location', 'user_device'), **overrides)


def test_explicit_choices_and_utf16_caption_round_trip_preserve_vietnamese():
    request = init(); body = json.loads(request.body)
    assert body['post_info'] == {**{key: value for key, value in CHOICES.items() if key != 'music_usage_confirmed'},
        'title': 'Học AI 😀\n\nCần Giờ\n\n#ViệtNam'}
    assert body['source_info'] == {'source': 'FILE_UPLOAD', 'video_size': 4_256_257,
        'chunk_size': 4_256_257, 'total_chunk_count': 1}
    assert request.url.endswith('/v2/post/publish/video/init/')
    assert 'Idempotency-Key' not in request.headers
    assert TOKEN not in repr(request) and 'Học' not in repr(request)
    with pytest.raises(ValidationError): PostChoices(privacy_level='SELF_ONLY')
    with pytest.raises(ValidationError): PostChoices(**{**CHOICES, 'disable_duet': 1})
    with pytest.raises(ValidationError): PostChoices(**CHOICES, secret=TOKEN)
    with pytest.raises(ValidationError): PostChoices(**{**CHOICES, 'music_usage_confirmed': 1})


@pytest.mark.parametrize('metadata,options,code', [
    (PublicationMetadata(title='a', privacy='public'), {}, 'TIKTOK_METADATA_PRIVACY_MISMATCH'),
    (PublicationMetadata(title='a', privacy='unlisted'), {}, 'TIKTOK_METADATA_PRIVACY_MISMATCH'),
    (PublicationMetadata(title='a', privacy='public'), {'choices': {'privacy_level': 'PUBLIC_TO_EVERYONE'}}, 'TIKTOK_CLIENT_AUDIT_REQUIRED'),
    (PublicationMetadata(title='a'), {'choices': {'privacy_level': 'FOLLOWER_OF_CREATOR'}}, 'TIKTOK_PRIVACY_CHOICE_INVALID'),
    (PublicationMetadata(title='a'), {'choices': {'disable_stitch': False}}, 'TIKTOK_CREATOR_INTERACTION_DISABLED'),
    (PublicationMetadata(title='a'), {'duration_sec': 301}, 'TIKTOK_CREATOR_DURATION_EXCEEDED'),
    (PublicationMetadata(title='a'), {'duration_sec': float('nan')}, 'TIKTOK_CREATOR_DURATION_EXCEEDED'),
    (PublicationMetadata(title='a'), {'duration_sec': True}, 'TIKTOK_CREATOR_DURATION_EXCEEDED'),
    (PublicationMetadata(title='a'), {'choices': {'video_cover_timestamp_ms': 3000}}, 'TIKTOK_COVER_FRAME_INVALID'),
    (PublicationMetadata(title='a', scheduled_at=NOW + timedelta(days=1)), {}, 'TIKTOK_LOCAL_SCHEDULER_REQUIRED'),
    (PublicationMetadata(title='a', thumbnail_asset_id='ast_cover'), {}, 'TIKTOK_COVER_FRAME_REQUIRED'),
    (PublicationMetadata(title='a', caption='😀' * 1100), {}, 'TIKTOK_CAPTION_INVALID'),
], ids=['privacy', 'unlisted', 'audit', 'not-offered', 'creator-limit', 'duration', 'nan', 'bool', 'cover', 'schedule', 'thumbnail', 'utf16'])
def test_metadata_or_choices_not_silently_rewritten(metadata, options, code):
    with pytest.raises(PublishingWireError, match=code): init(metadata, **options)


def test_audited_public_and_exact_utf16_boundary():
    # One ASCII title + two newlines + 1098 emoji + one ASCII = 2200 UTF16 units.
    request = init(PublicationMetadata(title='a', caption='😀' * 1098 + 'b', privacy='public'),
        client_audited=True, choices={'privacy_level': 'PUBLIC_TO_EVERYONE'})
    assert len(json.loads(request.body)['post_info']['title'].encode('utf-16-le')) == 4400


@pytest.mark.parametrize('size,chunk,count,last', [
    (1, 8_388_608, 1, 1), (4_194_304, 8_388_608, 1, 4_194_304),
    (8_388_609, 8_388_608, 1, 8_388_609), (20_000_123, 5_000_000, 4, 5_000_123),
    (50_000_123, 8_388_608, 5, 16_445_691), (536_870_912, 8_388_608, 64, 8_388_608),
], ids=['tiny', 'whole', 'merged-whole', 'decimal', 'merged-tail', 'internal-max'])
def test_chunk_floor_count_and_trailing_bytes(size, chunk, count, last):
    plan = ChunkPlan(size, chunk)
    assert plan.count == count and plan.length((count - 1) * chunk) == last
    assert sum(plan.length(i * chunk) for i in range(count)) == size
    assert max(plan.length(i * chunk) for i in range(count)) <= 16 * 1024 * 1024
    with pytest.raises(PublishingWireError): plan.length(size)
    with pytest.raises(PublishingWireError): plan.length(True)
    with pytest.raises(PublishingWireError): plan.length(-1)


@pytest.mark.parametrize('size,chunk', [(0, 8_388_608), (True, 8_388_608), (536_870_913, 8_388_608),
    (4, 4_999_999), (4, 8_388_609)], ids=['zero', 'bool', 'too-large', 'too-small-chunk', 'body-cap'])
def test_invalid_chunk_plan(size, chunk):
    with pytest.raises(PublishingWireError): ChunkPlan(size, chunk)


def test_start_upload_chunk_status_are_separate_observations():
    plan = ChunkPlan(10_000_123, 5_000_000)
    session = started_session(response({'publish_id': 'v_pub_file~v2-1.123456789', 'upload_url': URI}), plan, now=NOW)
    assert session.expires_at == NOW + timedelta(hours=1)
    assert 'UPLOAD_TOKEN' not in repr(session) and 'v_pub' not in repr(session)
    request = chunk_request(session, 0, b'x' * 5_000_000, now=NOW)
    assert 'Authorization' not in request.headers and request.headers['Content-Range'] == 'bytes 0-4999999/10000123'
    assert chunk_ack(OfficialResponse(206, {}, b''), plan, 0) == 5_000_000
    assert chunk_ack(OfficialResponse(201, {}, b''), plan, 5_000_000) == plan.total_bytes
    with pytest.raises(PublishingWireError) as caught: chunk_ack(OfficialResponse(201, {}, b''), plan, 0)
    assert caught.value.uncertain is True
    with pytest.raises(PublishingWireError): chunk_request(session, 0, b'too short', now=NOW)
    with pytest.raises(PublishingWireError, match='EXPIRED'): chunk_request(session, 0, b'', now=session.expires_at)
    status = status_request(session.publish_id, TOKEN)
    assert json.loads(status.body) == {'publish_id': session.publish_id}
    observation = post_observation(response({'status': 'PUBLISH_COMPLETE'}), total_bytes=plan.total_bytes)
    assert observation.uploaded_bytes is None and observation.public_post_ids == ()
    assert observation.failure_code is None  # No invented public URL or ID for a private post.


@pytest.mark.parametrize('uri', [
    URI.replace('open-upload', 'evil'), URI.replace('https:', 'http:'), URI.replace('/video/', '/other/'),
    URI + '&upload_token=duplicate', URI + '&access_token=' + TOKEN,
    URI.replace('upload_token=', 'missing='), URI + '#private', URI.replace('/video/', '/%2e%2e/video/'),
], ids=['host', 'scheme', 'path', 'duplicate', 'oauth-query', 'missing', 'fragment', 'traversal'])
def test_signed_upload_uri_strict_and_errors_private(uri):
    with pytest.raises(PublishingWireError) as caught: upload_uri(uri)
    assert TOKEN not in str(caught.value) and 'UPLOAD_TOKEN' not in str(caught.value)


def test_latest_creator_permissions_normalized_without_avatar_or_provider_error():
    data = dict(creator_username='fixture_creator', privacy_level_options=['SELF_ONLY'],
        comment_disabled=True, duet_disabled=True, stitch_disabled=True, max_video_post_duration_sec=60,
        creator_avatar_url='https://PRIVATE_AVATAR', creator_nickname='Private nickname')
    result = creator_info(response(data))
    assert result.privacy_options == ('SELF_ONLY',) and result.max_duration_sec == 60
    assert result.nickname == 'Private nickname' and 'Private nickname' not in repr(result)
    assert not hasattr(result, 'creator_avatar_url')
    assert creator_request(TOKEN).url.endswith('/creator_info/query/')
    for key, invalid in [('privacy_level_options', ['UNKNOWN']), ('comment_disabled', 1), ('max_video_post_duration_sec', True)]:
        with pytest.raises(PublishingWireError): creator_info(response({**data, key: invalid}))
    with pytest.raises(PublishingWireError) as caught: creator_info(response(data, error='spam_risk_user_banned_from_posting'))
    assert 'DO_NOT_EXPOSE' not in str(caught.value)


@pytest.mark.parametrize('data', [
    {'status': 'UNKNOWN'}, {'status': 'PROCESSING_UPLOAD', 'uploaded_bytes': True},
    {'status': 'PROCESSING_UPLOAD', 'uploaded_bytes': 101},
    {'status': 'PUBLISH_COMPLETE', 'publicaly_available_post_id': [True]},
    {'status': 'PUBLISH_COMPLETE', 'publicaly_available_post_id': ['9223372036854775808']},
    {'status': 'PUBLISH_COMPLETE', 'publicaly_available_post_id': [123, '123']},
    {'status': 'PROCESSING_UPLOAD', 'publicaly_available_post_id': [123]},
], ids=['unknown', 'bool', 'past-total', 'bool-id', 'int64', 'duplicate', 'premature-id'])
def test_impossible_status_rejected(data):
    with pytest.raises(PublishingWireError): post_observation(response(data), total_bytes=100)


def test_provider_failures_and_mutating_unknown_response_never_become_success():
    for status in [429, 500]:
        with pytest.raises(PublishingWireError) as caught:
            started_session(OfficialResponse(status, {'retry-after': '120'}, b'{}'), ChunkPlan(10), now=NOW)
        assert caught.value.uncertain and caught.value.retry_after == 120
    with pytest.raises(PublishingWireError) as caught:
        started_session(OfficialResponse(200, {}, b'not json'), ChunkPlan(10), now=NOW)
    assert caught.value.uncertain
    result = post_observation(response({'status': 'FAILED', 'fail_reason': TOKEN}), total_bytes=10)
    assert result.failure_code == 'TIKTOK_POST_FAILED' and TOKEN not in repr(result)
    complete = post_observation(response({'status': 'PUBLISH_COMPLETE', 'publicaly_available_post_id': [123]}), total_bytes=10)
    assert complete.public_post_ids == ('123',)


@pytest.mark.asyncio
async def test_official_mock_transport_flow_and_regional_upload_oauth_fence():
    requests = []
    def handler(request):
        requests.append(request)
        if request.url.host in ('open-upload.tiktokapis.com', 'upload.us.tiktokapis.com'):
            assert 'authorization' not in request.headers
            return httpx.Response(201)
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        return httpx.Response(200, json={'data': {}, 'error': {'code': 'ok'}})
    client = OfficialHTTPClient('tiktok', transport=httpx.MockTransport(handler))
    for uri in [URI, URI.replace('open-upload', 'upload.us')]:
        session = UploadSession('v_pub_fixture', uri, ChunkPlan(4), NOW + timedelta(hours=1))
        assert (await client.request(chunk_request(session, 0, b'ftyp', now=NOW))).status == 201
        with pytest.raises(PublishingWireError, match='UPLOAD_BEARER_FORBIDDEN'):
            await client.request(OfficialRequest('PUT', uri, {'Authorization': 'Bearer ' + TOKEN}))
    await client.request(creator_request(TOKEN))
    assert len(requests) == 3
    with pytest.raises(PublishingWireError, match='NOT_ACTIVATED'):
        await OfficialHTTPClient('tiktok').request(creator_request(TOKEN))


def test_explicit_music_branded_content_and_user_device_provenance():
    with pytest.raises(PublishingWireError, match='VERIFIED_PULL_REQUIRED'):
        init(media_location='server_storage')
    with pytest.raises(PublishingWireError, match='BRANDED_PRIVATE_UNSUPPORTED'):
        init(choices={'brand_content_toggle': True})
    with pytest.raises(PublishingWireError, match='BRANDED_CONTENT_CONFIRMATION_REQUIRED'):
        init(PublicationMetadata(title='a', privacy='public'), client_audited=True,
            choices={'privacy_level': 'PUBLIC_TO_EVERYONE', 'brand_content_toggle': True})
    request = init(PublicationMetadata(title='a', privacy='public'), client_audited=True,
        choices={'privacy_level': 'PUBLIC_TO_EVERYONE', 'brand_content_toggle': True, 'branded_content_policy_confirmed': True})
    payload = json.loads(request.body)['post_info']
    assert payload['brand_content_toggle'] is True
    assert 'music_usage_confirmed' not in payload and 'branded_content_policy_confirmed' not in payload


def test_server_media_pull_uses_explicit_preverified_prefix_not_upload_bytes():
    prefix = 'https://media.fixture.example/owned/'
    url = prefix + 'final.mp4?signature=EXPLICIT_FIXTURE_SIGNATURE'
    request = pull_request(PublicationMetadata(title='AI'), TOKEN, video_url=url, verified_prefix=prefix,
        creator=CREATOR, choices=PostChoices(**CHOICES), duration_sec=3, client_audited=False)
    assert json.loads(request.body)['source_info'] == {'source': 'PULL_FROM_URL', 'video_url': url}
    assert 'SIGNATURE' not in repr(request)
    assert started_pull(response({'publish_id': 'v_pub_url~fixture'})) == 'v_pub_url~fixture'
    observation = post_observation(response({'status': 'PROCESSING_DOWNLOAD'}), total_bytes=10)
    assert observation.uploaded_bytes is None and observation.public_post_ids == ()


@pytest.mark.parametrize('url,prefix', [
    ('http://media.fixture.example/owned/f.mp4', 'https://media.fixture.example/owned/'),
    ('https://evil.example/owned/f.mp4', 'https://media.fixture.example/owned/'),
    ('https://media.fixture.example/owned-else/f.mp4', 'https://media.fixture.example/owned/'),
    ('https://media.fixture.example/owned/../f.mp4', 'https://media.fixture.example/owned/'),
    ('https://media.fixture.example/owned/%2e%2e/f.mp4', 'https://media.fixture.example/owned/'),
    ('https://media.fixture.example/owned/%2Felse/f.mp4', 'https://media.fixture.example/owned/'),
    ('https://media.fixture.example/owned/f.mp4', 'https://media.fixture.example/owned/?proof=true'),
    ('https://media.fixture.example/owned/', 'https://media.fixture.example/owned/'),
    ('https://127.0.0.1/owned/f.mp4', 'https://127.0.0.1/owned/'),
    ('https://localhost/owned/f.mp4', 'https://localhost/owned/'),
], ids=['http', 'foreign', 'prefix-boundary', 'traversal', 'encoded-traversal', 'encoded-slash', 'query-proof', 'folder', 'ip', 'localhost'])
def test_verified_prefix_boundary_is_not_a_user_asserted_url_verification(url, prefix):
    with pytest.raises(PublishingWireError, match='VERIFIED_PULL_PREFIX_REQUIRED'):
        verified_pull_url(url, prefix)


@pytest.mark.asyncio
async def test_full_explicit_mock_file_transfer_then_processing_never_invents_real_post():
    seen = []
    plan = ChunkPlan(4)
    def handler(request):
        seen.append(request)
        path = request.url.path
        if path.endswith('/creator_info/query/'):
            data = {'creator_username': 'fixture_creator', 'creator_nickname': 'Fixture channel',
                'privacy_level_options': ['SELF_ONLY'], 'comment_disabled': True,
                'duet_disabled': True, 'stitch_disabled': True, 'max_video_post_duration_sec': 60}
        elif path.endswith('/video/init/'):
            data = {'publish_id': 'v_pub_fixture', 'upload_url': URI}
        elif path == '/video/':
            assert request.content == b'ftyp' and 'authorization' not in request.headers
            return httpx.Response(201)
        else:
            assert path.endswith('/status/fetch/')
            data = {'status': 'PUBLISH_COMPLETE'}
        return httpx.Response(200, json={'data': data, 'error': {'code': 'ok'}})
    client = OfficialHTTPClient('tiktok', transport=httpx.MockTransport(handler))
    creator = creator_info(await client.request(creator_request(TOKEN)))
    choices = PostChoices(**{**CHOICES, 'disable_comment': True, 'disable_duet': True})
    session = started_session(await client.request(start_request(PublicationMetadata(title='Fixture only'),
        plan, TOKEN, creator=creator, choices=choices, duration_sec=3,
        client_audited=False, media_location='user_device')), plan, now=NOW)
    assert chunk_ack(await client.request(chunk_request(session, 0, b'ftyp', now=NOW)), plan, 0) == 4
    observed = post_observation(await client.request(status_request(session.publish_id, TOKEN)), total_bytes=4)
    assert observed.status == 'PUBLISH_COMPLETE' and observed.public_post_ids == ()
    assert sum(request.url.path.endswith('/video/init/') for request in seen) == 1 and len(seen) == 4
    # Explicit MockTransport and non-playable fixture bytes: no real provider acceptance.
