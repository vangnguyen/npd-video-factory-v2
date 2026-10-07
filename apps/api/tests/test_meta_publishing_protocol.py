import json
from datetime import datetime, timezone
from urllib.parse import parse_qs

import httpx
import pytest

from app.meta_publishing_protocol import (GraphTarget, FacebookUploadSession, caption,
    confirmed_success, created_id, fb_create_request, fb_created_session, fb_finish_request,
    fb_observation, fb_status_request, fb_upload_request, ig_container_observation,
    ig_container_request, ig_create_request, ig_publish_request)
from app.publishing_models import PublicationMetadata
from app.publishing_wire import MAX_BODY, OfficialHTTPClient, OfficialResponse, PublishingWireError

TOKEN = 'EXPLICIT_META_PROTOCOL_FIXTURE_TOKEN_123456'
IG = GraphTarget('instagram_reels', '17841400000001', 'v26.0', 'facebook_login')
FB = GraphTarget('facebook', '123456789', 'v26.0', 'facebook_login')
VIDEO = '724627979033843'
CONTAINER = '18270815569115548'
PREFIX = 'https://media.fixture.example/owned/'
URL = PREFIX + 'final.mp4?signature=EXPLICIT_FIXTURE_SIGNATURE'


def response(data, status=200): return OfficialResponse(status, {}, json.dumps(data).encode())


def session(**overrides):
    return FacebookUploadSession(**{'target': FB, 'video_id': VIDEO,
        'uri': f'https://rupload.facebook.com/video-upload/v26.0/{VIDEO}', **overrides})


def ig_create(metadata=None, **options):
    return ig_create_request(IG, metadata or PublicationMetadata(title='Cần Giờ', caption='Học AI 😀', privacy='public'),
        TOKEN, video_url=options.pop('video_url', URL), authorized_prefix=PREFIX,
        share_to_feed=options.pop('share_to_feed', False), **options)


def test_instagram_create_status_and_publish_are_distinct_scoped_requests():
    request = ig_create(); body = parse_qs(request.body.decode())
    assert body['media_type'] == ['REELS'] and body['video_url'] == [URL]
    assert body['caption'] == ['Cần Giờ\n\nHọc AI 😀'] and body['share_to_feed'] == ['false']
    assert 'access_token' not in request.url and TOKEN not in repr(request) and 'SIGNATURE' not in repr(request)
    assert request.headers['Authorization'] == 'Bearer ' + TOKEN
    identifier = created_id(response({'id': CONTAINER}))
    status = ig_container_request(IG, identifier, TOKEN)
    assert status.method == 'GET' and parse_qs(status.url.split('?')[1]) == {'fields': ['id,status_code']}
    observed = ig_container_observation(response({'id': CONTAINER, 'status_code': 'FINISHED', 'status': TOKEN}), IG, CONTAINER)
    assert observed.ready and TOKEN not in repr(observed)
    publish = ig_publish_request(IG, observed, TOKEN)
    assert parse_qs(publish.body.decode()) == {'creation_id': [CONTAINER]}
    assert publish.url.endswith(IG.account_id + '/media_publish')


@pytest.mark.parametrize('updates', [{'account_id': '../private'}, {'account_id': '0'}, {'api_version': 'latest'},
    {'api_version': 'v26.0/../../'}, {'login_type': 'instagram_login'}, {'platform': 'youtube'}],
    ids=['path-id', 'zero', 'no-version', 'version-traversal', 'different-login-contract', 'platform'])
def test_explicit_format_binding_rejects_invalid_configuration(updates):
    with pytest.raises(PublishingWireError): GraphTarget(**{**IG.__dict__, **updates})


@pytest.mark.parametrize('state', [None, 'IN_PROGRESS', 'ERROR', 'EXPIRED', 'UNKNOWN_NEW_STATE'])
def test_only_observed_finished_container_can_be_published(state):
    observed = ig_container_observation(response({'id': CONTAINER, 'status_code': state}), IG, CONTAINER)
    assert observed.provider_status == state and not observed.ready
    with pytest.raises(PublishingWireError, match='NOT_READY'): ig_publish_request(IG, observed, TOKEN)


def test_container_scope_and_malformed_observation_fail_closed():
    for data in [{'id': '9999', 'status_code': 'FINISHED'}, {'id': CONTAINER, 'status_code': True},
        {'id': CONTAINER, 'status_code': TOKEN + '<private>'}]:
        with pytest.raises(PublishingWireError): ig_container_observation(response(data), IG, CONTAINER)
    observed = ig_container_observation(response({'id': CONTAINER, 'status_code': 'FINISHED'}), IG, CONTAINER)
    foreign = GraphTarget('instagram_reels', '9999', 'v26.0', 'facebook_login')
    with pytest.raises(PublishingWireError): ig_publish_request(foreign, observed, TOKEN)


@pytest.mark.parametrize('metadata', [PublicationMetadata(title='a'), PublicationMetadata(title='a', privacy='unlisted'),
    PublicationMetadata(title='a', privacy='public', scheduled_at=datetime(2099, 1, 1, tzinfo=timezone.utc)),
    PublicationMetadata(title='a', privacy='public', thumbnail_asset_id='ast_fixture'),
    PublicationMetadata(title='a', privacy='public', caption='x' * 2200)],
    ids=['private', 'unlisted', 'schedule', 'thumbnail', 'internal-caption-cap'])
def test_metadata_not_silently_rewritten(metadata):
    with pytest.raises(PublishingWireError): ig_create(metadata)
    with pytest.raises(PublishingWireError): ig_create(share_to_feed=1)


@pytest.mark.parametrize('url', [URL.replace('https:', 'http:'), URL.replace('media.fixture.example', 'evil.example'),
    URL.replace('/owned/', '/else/'), URL.replace('/owned/', '/owned/../'), URL + '#private'],
    ids=['scheme', 'foreign', 'path', 'traversal', 'fragment'])
def test_authorized_server_media_bound_to_exact_https_prefix(url):
    with pytest.raises(PublishingWireError, match='AUTHORIZED_MEDIA_PREFIX_REQUIRED'): ig_create(video_url=url)


def test_facebook_local_and_hosted_upload_confirmation_are_not_publication():
    created = fb_create_request(FB, TOKEN)
    assert parse_qs(created.body.decode()) == {'upload_phase': ['start']}
    value = fb_created_session(response({'video_id': VIDEO, 'upload_url': session().uri}), FB)
    local = fb_upload_request(value, TOKEN, content=b'EXPLICIT_NONPLAYABLE_FIXTURE')
    assert local.headers['Authorization'] == 'OAuth ' + TOKEN and local.headers['offset'] == '0'
    assert local.headers['file_size'] == str(len(local.body))
    assert TOKEN not in repr(local) and local.url == value.uri
    hosted = fb_upload_request(value, TOKEN, video_url=URL, authorized_prefix=PREFIX)
    assert hosted.headers['file_url'] == URL and hosted.body == b''
    assert confirmed_success(response({'success': True})) is True
    for success in (False, 1, 'true', None):
        with pytest.raises(PublishingWireError): confirmed_success(response({'success': success}))
    status = fb_status_request(FB, VIDEO, TOKEN)
    assert parse_qs(status.url.split('?')[1]) == {'fields': ['id,status']}
    observed = fb_observation(response({'id': VIDEO, 'status': {'video_status': 'processing',
        'uploading_phase': {'status': 'complete'}, 'processing_phase': {'status': 'not_started'}}}), VIDEO)
    assert observed.processing_progress is None and observed.publishing_phase is None
    assert observed.uploading_phase == 'complete'  # Never invent a published receipt.


@pytest.mark.parametrize('uri', [f'https://evil.example/video-upload/v26.0/{VIDEO}',
    f'https://rupload.facebook.com/video-upload/v25.0/{VIDEO}', f'https://rupload.facebook.com/video-upload/v26.0/9999',
    f'https://rupload.facebook.com/video-upload/v26.0/{VIDEO}?access_token={TOKEN}'],
    ids=['host', 'version', 'video-id', 'oauth-query'])
def test_returned_upload_origin_version_and_object_are_exact(uri):
    with pytest.raises(PublishingWireError): session(uri=uri)
    with pytest.raises(PublishingWireError) as caught: fb_created_session(response({'video_id': VIDEO, 'upload_url': uri}), FB)
    assert caught.value.uncertain and TOKEN not in str(caught.value)


def test_upload_body_is_bounded_and_exclusive():
    for kwargs in ({'content': b''}, {'content': b'x' * (MAX_BODY + 1)}, {'content': b'fixture', 'video_url': URL}, {}):
        with pytest.raises(PublishingWireError): fb_upload_request(session(), TOKEN, **kwargs)


def test_draft_and_published_are_explicit_and_never_reinterpreted_privacy():
    draft = fb_finish_request(FB, VIDEO, PublicationMetadata(title='Draft'), TOKEN, video_state='DRAFT')
    assert parse_qs(draft.body.decode())['video_state'] == ['DRAFT']
    public = fb_finish_request(FB, VIDEO, PublicationMetadata(title='Public', privacy='public'), TOKEN, video_state='PUBLISHED')
    assert parse_qs(public.body.decode())['video_state'] == ['PUBLISHED']
    for state in ('PUBLISHED', 'SCHEDULED', 'UNKNOWN'):
        with pytest.raises(PublishingWireError): fb_finish_request(FB, VIDEO, PublicationMetadata(title='a'), TOKEN, video_state=state)


@pytest.mark.parametrize('status', [{'processing_progress': True}, {'processing_progress': 101},
    {'video_status': TOKEN + '<private>'}, {'uploading_phase': True}],
    ids=['bool-progress', 'past100', 'raw-private-status', 'bad-phase'])
def test_impossible_video_observations_rejected(status):
    with pytest.raises(PublishingWireError): fb_observation(response({'id': VIDEO, 'status': status}), VIDEO)


def test_error_messages_and_uncertain_mutations_never_become_success():
    for result in [response({'error': {'message': TOKEN}}, 400), OfficialResponse(200, {}, TOKEN.encode()),
        response({'success': False})]:
        with pytest.raises(PublishingWireError) as caught: confirmed_success(result)
        assert caught.value.uncertain and TOKEN not in str(caught.value)
    with pytest.raises(PublishingWireError) as caught:
        confirmed_success(OfficialResponse(429, {'retry-after': '120'}, b'{}'))
    assert caught.value.retry_after == 120


@pytest.mark.asyncio
async def test_official_instagram_mock_container_then_ready_then_publish():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == 'graph.facebook.com' and request.headers['authorization'] == 'Bearer ' + TOKEN
        assert 'access_token' not in request.url.params
        if request.url.path.endswith('/media'): return httpx.Response(200, json={'id': CONTAINER})
        if request.method == 'GET': return httpx.Response(200, json={'id': CONTAINER, 'status_code': 'FINISHED'})
        return httpx.Response(200, json={'id': '90011803596441'})
    client = OfficialHTTPClient('instagram_reels', transport=httpx.MockTransport(handler))
    container = created_id(await client.request(ig_create()))
    observed = ig_container_observation(await client.request(ig_container_request(IG, container, TOKEN)), IG, container)
    media_id = created_id(await client.request(ig_publish_request(IG, observed, TOKEN)))
    assert media_id == '90011803596441' and len(seen) == 3
    with pytest.raises(PublishingWireError, match='NOT_ACTIVATED'): await OfficialHTTPClient('instagram_reels').request(ig_create())


@pytest.mark.asyncio
async def test_official_facebook_mock_start_body_finish_and_null_status():
    seen = []
    def handler(request):
        seen.append(request)
        if request.url.host == 'rupload.facebook.com':
            assert request.headers['authorization'] == 'OAuth ' + TOKEN and request.content == b'ftyp'
            return httpx.Response(200, json={'success': True})
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        if request.method == 'GET': return httpx.Response(200, json={'id': VIDEO, 'status': {}})
        if parse_qs(request.content.decode())['upload_phase'] == ['start']:
            return httpx.Response(200, json={'video_id': VIDEO, 'upload_url': session().uri})
        return httpx.Response(200, json={'success': True})
    client = OfficialHTTPClient('facebook', transport=httpx.MockTransport(handler))
    upload = fb_created_session(await client.request(fb_create_request(FB, TOKEN)), FB)
    assert confirmed_success(await client.request(fb_upload_request(upload, TOKEN, content=b'ftyp')))
    assert confirmed_success(await client.request(fb_finish_request(FB, VIDEO,
        PublicationMetadata(title='Fixture draft'), TOKEN, video_state='DRAFT')))
    observation = fb_observation(await client.request(fb_status_request(FB, VIDEO, TOKEN)), VIDEO)
    assert observation.video_status is None and observation.publishing_phase is None and len(seen) == 4
    with pytest.raises(PublishingWireError, match='NOT_ACTIVATED'): await OfficialHTTPClient('facebook').request(fb_create_request(FB, TOKEN))
