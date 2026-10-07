"""Actual HTTP request/stream composition with official origins and no network."""
import json
import gzip
import logging
from unittest.mock import patch

import httpx
import pytest

from app.publishing_wire import MAX_BODY, MAX_RESPONSE, OfficialHTTPClient, OfficialRequest, OfficialResponse, PublishingWireError, official_url


TOKEN = 'explicit-fixture-token-' + 'x' * 48
URI = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=PRIVATE_UPLOAD_TOKEN'


@pytest.mark.asyncio
async def test_disabled_transport_cannot_allocate_client_or_network():
    with patch('app.publishing_wire.httpx.AsyncHTTPTransport', side_effect=AssertionError('Must not allocate a live transport')):
        with pytest.raises(PublishingWireError, match='EXTERNAL_PUBLISHING_NOT_ACTIVATED'):
            await OfficialHTTPClient('youtube').request(OfficialRequest('POST', URI))


@pytest.mark.parametrize('uri', ['http://www.googleapis.com/upload', 'https://www.googleapis.com.evil.test/',
    'https://127.0.0.1/', 'https://www.googleapis.com@evil.test/', 'https://www.googleapis.com:444/',
    'https://www.googleapis.com/a/../b', 'https://www.googleapis.com/a/%2e%2e/b',
    'https://www.googleapis.com/#fragment', 'https://www.googleapis.com/\n',
    'https://www.googleapis.com/?access_token=private', 'https://www.googleapis.com/?key=private',
    'https://open.tiktokapis.com/v2/post/publish/video/init/'])
def test_origins_cross_platform_tokens_traversal_and_unsafe_transport_urls_are_rejected(uri):
    with pytest.raises(PublishingWireError, match='PUBLISHING_OFFICIAL_ORIGIN_REQUIRED'):
        official_url(uri, 'youtube')


def test_request_body_headers_are_bounded_immutable_and_hidden_in_repr():
    source = {'Authorization': 'Bearer ' + TOKEN, 'Content-Length': '3'}
    request = OfficialRequest('PUT', URI, source, b'raw')
    source['Authorization'] = 'changed'; assert request.headers['Authorization'] == 'Bearer ' + TOKEN
    assert TOKEN not in repr(request) and 'PRIVATE_UPLOAD_TOKEN' not in repr(request) and 'raw' not in repr(request)
    with pytest.raises(TypeError): request.headers['other'] = 'no mutation'
    for headers, body in [({'Authorization': 'Bearer x\nprivate'}, b''), ({'X-Unknown': 'x'}, b''),
        ({'Authorization': 'Bearer x', 'authorization': 'Bearer y'}, b''), ({'Content-Length': '1'}, b'xx'), ({}, b'x' * (MAX_BODY + 1))]:
        with pytest.raises(PublishingWireError): OfficialRequest('POST', URI, headers, body)


@pytest.mark.asyncio
async def test_official_request_preserves_binary_and_oauth_header_without_cookies_or_proxy_state():
    seen = []
    def handler(request):
        seen.append(request); return httpx.Response(308, headers={'Range': 'bytes=0-2', 'Set-Cookie': 'PRIVATE=not_used'}, content=b'')
    client = OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler))
    response = await client.request(OfficialRequest('PUT', URI, {'Authorization': 'Bearer ' + TOKEN,
        'Content-Length': '3', 'Content-Type': 'video/mp4'}, b'abc'))
    assert response.status == 308 and response.headers == {'range': 'bytes=0-2'}
    assert seen[0].content == b'abc' and seen[0].headers['authorization'] == 'Bearer ' + TOKEN
    assert 'cookie' not in seen[0].headers and seen[0].extensions['timeout']['write'] == 30.0


@pytest.mark.asyncio
async def test_redirect_never_dispatches_a_second_request_and_mutating_outcome_remains_uncertain():
    seen = []
    def handler(request):
        seen.append(request); return httpx.Response(307, headers={'Location': 'https://evil.test/PRIVATE'}, content=b'PRIVATE PROVIDER ERROR')
    with pytest.raises(PublishingWireError) as caught:
        await OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler)).request(OfficialRequest('POST', URI))
    assert len(seen) == 1 and caught.value.code == 'PUBLISHING_REDIRECT_REJECTED' and caught.value.uncertain
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.asyncio
async def test_timeout_after_post_is_not_retried_or_returned_with_private_url_exception():
    seen = []
    def handler(request):
        seen.append(request); raise httpx.ReadTimeout('PRIVATE SECRET ' + TOKEN + str(request.url), request=request)
    with pytest.raises(PublishingWireError) as caught:
        await OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler)).request(OfficialRequest('POST', URI))
    assert len(seen) == 1 and caught.value.code == 'PUBLISHING_NETWORK_OUTCOME_UNKNOWN' and caught.value.uncertain
    assert TOKEN not in repr(caught.value) and 'PRIVATE' not in str(caught.value)


@pytest.mark.asyncio
async def test_response_size_and_provider_shape_fail_with_fixed_nonprivate_error():
    with pytest.raises(PublishingWireError, match='PUBLISHING_RESPONSE_SIZE_LIMIT'):
        await OfficialHTTPClient('youtube', transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b'x' * (MAX_RESPONSE + 1)))).request(OfficialRequest('GET', URI))
    for body in (b'[]', b'PRIVATE_PROVIDER_ERROR', b'null'):
        with pytest.raises(PublishingWireError, match='PUBLISHING_PROVIDER_RESPONSE_INVALID'):
            OfficialResponse(200, {}, body).json_object()


@pytest.mark.asyncio
async def test_compressed_provider_body_is_rejected_before_decompression():
    raw = gzip.compress(b'x' * (MAX_RESPONSE + 1))
    response = httpx.Response(200, headers={'Content-Encoding': 'gzip'}, stream=httpx.ByteStream(raw))
    with patch.object(response, 'aiter_bytes', side_effect=AssertionError('Must reject before decoding')) as decode:
        with pytest.raises(PublishingWireError, match='PUBLISHING_COMPRESSED_RESPONSE_REJECTED'):
            await OfficialHTTPClient('youtube', transport=httpx.MockTransport(lambda request: response)).request(OfficialRequest('GET', URI))
        decode.assert_not_called()


@pytest.mark.asyncio
async def test_upload_and_oauth_tokens_are_excluded_from_debug_wire_logs_without_changing_unrelated_logs(caplog):
    caplog.set_level(logging.DEBUG)
    def handler(request):
        logging.getLogger('httpx').info('PRIVATE %s %s', request.url, request.headers)
        logging.getLogger('httpcore.http11').debug('PRIVATE %s', request.url)
        return httpx.Response(200, json={'ok': True})
    await OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler)).request(OfficialRequest('POST', URI, {'Authorization': 'Bearer ' + TOKEN}))
    assert 'PRIVATE' not in caplog.text and TOKEN not in caplog.text
    logging.getLogger('httpx').info('Unrelated safe request still visible')
    assert 'Unrelated safe request still visible' in caplog.text


@pytest.mark.asyncio
async def test_tiktok_signed_upload_uri_is_allowed_but_oauth_bearer_cannot_cross_into_upload_host():
    seen = []
    def handler(request): seen.append(request); return httpx.Response(201, content=b'')
    client = OfficialHTTPClient('tiktok', transport=httpx.MockTransport(handler))
    uri = 'https://open-upload.tiktokapis.com/video/?upload_token=PRIVATE_UPLOAD_TOKEN'
    with pytest.raises(PublishingWireError, match='PUBLISHING_UPLOAD_BEARER_FORBIDDEN'):
        await client.request(OfficialRequest('PUT', uri, {'Authorization': 'Bearer ' + TOKEN}))
    assert seen == []
    assert (await client.request(OfficialRequest('PUT', uri, {'Content-Length': '3'}, b'raw'))).status == 201
    assert 'authorization' not in seen[0].headers


def test_arbitrary_injected_transport_and_nonboolean_activation_are_refused():
    for options in ({'transport': object()}, {'network_enabled': 1}):
        with pytest.raises(PublishingWireError, match='PUBLISHING_TRANSPORT_CONFIGURATION_INVALID'):
            OfficialHTTPClient('youtube', **options)
