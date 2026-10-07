"""Official wire contracts with explicit MockTransport; no live GPU/network."""
import hashlib
import json
import logging
import pytest
import httpx
from npd_comfyui_bridge.http_transport import ComfyHTTPTransport, ComfyTransportError, RemoteArtifact, retry_after

PROMPT_ID = '024458d5-8e06-4450-b6a0-a944e8b76760'
SECRET = 'explicit-fixture-private-token'
PNG_MAGIC = b'\x89PNG\r\n\x1a\nfixture-not-a-decodable-image'


def client(handler, **kwargs):
    return ComfyHTTPTransport(origin='http://127.0.0.1:8188', server_source_sha256='a' * 64,
        transport=httpx.MockTransport(handler), **kwargs)


@pytest.mark.asyncio
async def test_constructor_and_disabled_methods_never_make_http_calls():
    calls = []
    transport = client(lambda request: calls.append(request))
    assert transport._client is None and not transport.configured
    with pytest.raises(ComfyTransportError, match='NOT_CONFIGURED'):
        await transport.get_job(PROMPT_ID)
    assert calls == [] and transport._client is None
    await transport.close()


@pytest.mark.parametrize('origin', ['http://unapproved.invalid', 'https://user:secret@host.invalid',
    'https://host.invalid/other', 'https://host.invalid?token=secret', 'https://host.invalid#token',
    'https://host.invalid\\evil', 'https://host.invalid/%2f', 'https://host.invalid:99999', ' https://host.invalid'])
def test_origins_reject_userinfo_paths_secrets_and_unapproved_plaintext(origin):
    with pytest.raises(ValueError, match='ORIGIN_INVALID'):
        ComfyHTTPTransport(origin=origin, server_source_sha256='a' * 64)


@pytest.mark.asyncio
async def test_official_submit_poll_history_targeted_cancel_and_secret_free_outer_logs(caplog):
    calls = []
    def respond(request):
        calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer ' + SECRET
        if request.url.path == '/prompt':
            body = json.loads(request.content)
            assert body == {'prompt_id': PROMPT_ID, 'prompt': {'1': {'class_type': 'ExplicitFixture', 'inputs': {'text': 'private fixture'}}}}
            return httpx.Response(200, json={'prompt_id': PROMPT_ID, 'number': 4, 'node_errors': {}})
        if request.url.path == '/api/jobs/' + PROMPT_ID:
            return httpx.Response(200, json={'id': PROMPT_ID, 'status': 'in_progress'})
        if request.url.path == '/history/' + PROMPT_ID:
            return httpx.Response(200, json={PROMPT_ID: {'outputs': {}}})
        assert request.url.path == '/api/jobs/' + PROMPT_ID + '/cancel' and json.loads(request.content) == {}
        return httpx.Response(200, json={'cancelled': True})
    transport = client(respond, enabled=True, bearer_token=SECRET)
    try:
        with caplog.at_level(logging.INFO, logger='httpx'):
            assert await transport.submit_prompt(prompt_id=PROMPT_ID, graph={'1': {'class_type': 'ExplicitFixture', 'inputs': {'text': 'private fixture'}}}) == PROMPT_ID
            assert (await transport.get_job(PROMPT_ID))['status'] == 'in_progress'
            assert await transport.history(PROMPT_ID) == {'outputs': {}}
            assert await transport.cancel_job(PROMPT_ID)
        assert SECRET not in caplog.text and 'private fixture' not in caplog.text
        assert calls == [('POST', '/prompt'), ('GET', '/api/jobs/' + PROMPT_ID),
            ('GET', '/history/' + PROMPT_ID), ('POST', '/api/jobs/' + PROMPT_ID + '/cancel')]
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('status,uncertain', [(302, True), (502, True), (400, False), (401, False), (429, False)])
async def test_submit_never_retries_on_error_and_preserves_uncertainty_without_body_leak(status, uncertain):
    calls = []
    def respond(request):
        calls.append(request)
        return httpx.Response(status, text='private GPU error ' + SECRET, headers={'Location': 'https://untrusted.invalid', 'Retry-After': '120'})
    transport = client(respond, enabled=True)
    try:
        with pytest.raises(ComfyTransportError) as caught:
            await transport.submit_prompt(prompt_id=PROMPT_ID, graph={'fixture': {}})
        assert caught.value.uncertain_dispatch == uncertain and caught.value.retry_after_seconds == 120
        assert SECRET not in str(caught.value) and len(calls) == 1
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_lost_submit_response_is_ambiguous_and_does_not_repost():
    calls = []
    def fail(request):
        calls.append(request)
        raise httpx.ReadTimeout('private prompt ' + SECRET)
    transport = client(fail, enabled=True)
    try:
        with pytest.raises(ComfyTransportError) as caught:
            await transport.submit_prompt(prompt_id=PROMPT_ID, graph={'fixture': {}})
        assert caught.value.uncertain_dispatch and len(calls) == 1 and SECRET not in str(caught.value)
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_bound_json_limit_and_malformed_submit_are_ambiguous():
    transport = client(lambda _: httpx.Response(200, content=b'{}', headers={'Content-Length': str(3 * 1024 * 1024)}), enabled=True)
    try:
        with pytest.raises(ComfyTransportError, match='TOO_LARGE') as caught:
            await transport.submit_prompt(prompt_id=PROMPT_ID, graph={'fixture': {}})
        assert caught.value.uncertain_dispatch
    finally:
        await transport.close()
    transport = client(lambda _: httpx.Response(200, json={'prompt_id': 'different-job', 'node_errors': {}}), enabled=True)
    try:
        with pytest.raises(ComfyTransportError, match='BINDING_INVALID') as caught:
            await transport.submit_prompt(prompt_id=PROMPT_ID, graph={'fixture': {}})
        assert caught.value.uncertain_dispatch
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_read_missing_job_and_history_are_honest_and_foreign_bindings_reject():
    transport = client(lambda _: httpx.Response(404, json={'error': 'not found'}), enabled=True)
    try:
        assert await transport.get_job(PROMPT_ID) is None
    finally:
        await transport.close()
    transport = client(lambda _: httpx.Response(200, json={}), enabled=True)
    try:
        assert await transport.history(PROMPT_ID) is None
        with pytest.raises(ComfyTransportError, match='JOB_BINDING_INVALID'): await transport.get_job(PROMPT_ID)
    finally:
        await transport.close()
    transport = client(lambda _: httpx.Response(200, json={'foreign': {'outputs': {}}}), enabled=True)
    try:
        with pytest.raises(ComfyTransportError, match='HISTORY_BINDING_INVALID'): await transport.history(PROMPT_ID)
    finally:
        await transport.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('invalid', ['../queue', PROMPT_ID.upper(), 'not-a-job', '024458d58e064450b6a0a944e8b76760'])
async def test_invalid_remote_id_rejects_before_http(invalid):
    calls = []
    transport = client(lambda request: calls.append(request), enabled=True)
    try:
        with pytest.raises(ComfyTransportError, match='JOB_ID_INVALID'): await transport.cancel_job(invalid)
        assert calls == []
    finally:
        await transport.close()


@pytest.mark.parametrize('filename,subfolder,type_', [('..private.png', '', 'output'), ('/private.png', '', 'output'),
    ('good.png', '../escape', 'output'), ('good.png', 'folder\\escape', 'output'), ('good.png', '', 'input')])
def test_remote_output_descriptors_are_bounded_output_only(filename, subfolder, type_):
    with pytest.raises(ComfyTransportError, match='DESCRIPTOR_INVALID'): RemoteArtifact(filename, subfolder, type_)


@pytest.mark.asyncio
async def test_image_upload_has_no_overwrite_and_requires_exact_server_readback():
    calls = []
    def respond(request):
        calls.append(request.url.path)
        if request.method == 'POST':
            assert b'name="overwrite"\r\n\r\nfalse' in request.content and b'name="type"\r\n\r\ninput' in request.content
            return httpx.Response(200, json={'name': 'owned.png', 'subfolder': '', 'type': 'input'})
        assert dict(request.url.params) == {'filename': 'owned.png', 'subfolder': '', 'type': 'input'}
        return httpx.Response(200, content=PNG_MAGIC, headers={'Content-Type': 'image/png'})
    transport = client(respond, enabled=True)
    try:
        assert await transport.upload_image(filename='owned.png', content=PNG_MAGIC,
            expected_sha256=hashlib.sha256(PNG_MAGIC).hexdigest(), mime_type='image/png') == 'owned.png'
        assert calls == ['/upload/image', '/view']
        with pytest.raises(ComfyTransportError, match='UPLOAD_INVALID'):
            await transport.upload_image(filename='owned.png', content=PNG_MAGIC, expected_sha256='0' * 64, mime_type='image/png')
        assert len(calls) == 2
    finally:
        await transport.close()


@pytest.mark.asyncio
async def test_output_download_magic_is_explicitly_not_full_decoding():
    transport = client(lambda request: httpx.Response(200, content=PNG_MAGIC, headers={'Content-Type': 'image/png'}), enabled=True)
    try:
        assert await transport.download_artifact(RemoteArtifact('fixture.png', 'owned')) == (PNG_MAGIC, 'image/png')
        with pytest.raises(ComfyTransportError, match='UNSUPPORTED'): await transport.download_artifact(RemoteArtifact('private.json'))
    finally:
        await transport.close()
    transport = client(lambda request: httpx.Response(200, content=b'<html>private</html>', headers={'Content-Type': 'image/png'}), enabled=True)
    try:
        with pytest.raises(ComfyTransportError, match='CONTENT_INVALID'): await transport.download_artifact(RemoteArtifact('fixture.png'))
    finally:
        await transport.close()


def test_retry_after_seconds_http_date_and_invalid_values():
    assert retry_after('120') == 120 and retry_after('99999999') == 86400
    assert retry_after('Thu, 01 Jan 1970 00:00:00 GMT') == 0
    assert retry_after('private error') is None
