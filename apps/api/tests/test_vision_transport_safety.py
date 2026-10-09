"""Bounded private Vision wire contracts; synthetic keys and HTTP mocks only."""
import asyncio, hashlib, json, logging
import httpx
import pytest
from tests import test_openai_vision_provider as fixture
from app import openai_vision_provider as module
from app.openai_vision_provider import OpenAIVisionProvider, OpenAIVisionResponseError, _MAX_RESPONSE_BYTES
from app.publishing_wire import _sensitive
from app.vision_providers import VisionProviderNotConfigured


class Chunks(httpx.AsyncByteStream):
    def __init__(self, chunks, *, close_error=False):
        self.chunks = chunks; self.read_count = 0; self.closed = False; self.close_error = close_error

    async def __aiter__(self):
        for chunk in self.chunks:
            self.read_count += 1
            yield chunk

    async def aclose(self):
        self.closed = True
        if self.close_error:
            logging.getLogger('httpcore.connection').debug('SYNTHETIC PRIVATE CLOSE BODY')
            raise RuntimeError('sk-' + 'q' * 40)


@pytest.mark.parametrize('value', [0, 1, None, 'false'])
def test_contract_test_gate_is_raw_bool(value):
    with pytest.raises(ValueError, match='contract-test flag'):
        OpenAIVisionProvider(credential_alias='explicit', credential_resolver=lambda _: 'contract-test-key',
            frame_extractor=fixture.StaticFrameExtractor(), transport=httpx.MockTransport(lambda _: None), allow_zero_cost_contract_test=value)


@pytest.mark.asyncio
async def test_zero_cost_bypass_refuses_default_or_builtin_network_transport_before_secret_or_frames():
    resolver = fixture.SecretResolver(); extractor = fixture.StaticFrameExtractor()
    with pytest.raises(ValueError, match='injected test transport'):
        OpenAIVisionProvider(credential_alias='explicit', credential_resolver=resolver, frame_extractor=extractor, allow_zero_cost_contract_test=True)
    wire = httpx.AsyncHTTPTransport(trust_env=False)
    try:
        with pytest.raises(ValueError, match='injected test transport'):
            OpenAIVisionProvider(credential_alias='explicit', credential_resolver=resolver, frame_extractor=extractor,
                transport=wire, allow_zero_cost_contract_test=True)
    finally:
        await wire.aclose()
    assert resolver.calls == extractor.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize('key', [None, b'contract-key', '', 'short', 'sk-test\r\nHEADER', 'sk-非ASCII-synthetic', 'x' * 4097])
async def test_malformed_credentials_refuse_without_frames_dispatch_or_secret_in_errors(tmp_path, key):
    extractor = fixture.StaticFrameExtractor(); calls = []
    adapter = OpenAIVisionProvider(credential_alias='explicit', credential_resolver=lambda _: key, frame_extractor=extractor,
        transport=httpx.MockTransport(lambda request: calls.append(request)), allow_zero_cost_contract_test=True)
    with pytest.raises(VisionProviderNotConfigured, match='cannot be resolved') as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert extractor.calls == 0 and calls == []
    assert str(key) not in str(error.value) if key else True


@pytest.mark.asyncio
async def test_client_explicit_no_env_proxy_redirect_keepalive_and_identity_encoding(tmp_path, monkeypatch):
    calls = []; clients = []; original = httpx.AsyncClient
    monkeypatch.setenv('HTTPS_PROXY', 'http://explicit-unused-fixture-proxy.invalid:9999')
    def client(**kwargs):
        clients.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(module.httpx, 'AsyncClient', client)
    def handler(request):
        calls.append(request)
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['Accept-Encoding'] == 'identity'
        return httpx.Response(200, json=fixture.response_payload())
    adapter, _, _ = fixture.provider(handler)
    result = await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert len(calls) == len(clients) == 1 and result.provenance['mock_tested'] is True
    assert clients[0]['trust_env'] is False and clients[0]['follow_redirects'] is False
    assert clients[0]['limits'].max_connections == 1 and clients[0]['limits'].max_keepalive_connections == 0


@pytest.mark.asyncio
async def test_redirect_with_valid_looking_json_is_not_followed_or_accepted(tmp_path):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={'Location': 'https://explicit-untrusted.invalid/private'}, json=fixture.response_payload())
    adapter, _, _ = fixture.provider(handler)
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert len(calls) == 1 and error.value.code == 'OPENAI_VISION_HTTP_ERROR'
    assert error.value.error_evidence.http_status == 302 and error.value.error_evidence.retryable is False
    assert 'untrusted' not in str(error.value.error_evidence)


@pytest.mark.asyncio
async def test_stream_overrun_stops_before_remaining_bytes_and_has_no_complete_response_hash(tmp_path):
    stream = Chunks([b'x' * (1024 * 1024), b'x' * (1024 * 1024), b'x', b'NEVER READ REMAINDER'])
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, stream=stream))
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert error.value.code == 'OPENAI_VISION_RESPONSE_BOUND_EXCEEDED'
    assert error.value.error_evidence.response_sha256 is None and error.value.error_evidence.retryable is False
    assert stream.read_count == 3 and stream.closed and _sensitive.get() is False


@pytest.mark.asyncio
async def test_exact_byte_limit_complete_json_retains_receipt_and_original_hash(tmp_path):
    value = fixture.response_payload(); value['bounded_contract_padding'] = ''
    raw = json.dumps(value).encode(); value['bounded_contract_padding'] = 'x' * (_MAX_RESPONSE_BYTES - len(raw))
    raw = json.dumps(value).encode(); assert len(raw) == _MAX_RESPONSE_BYTES
    stream = Chunks([raw[:1024], raw[1024:]])
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, headers={'content-length': str(len(raw))}, stream=stream))
    result = await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert result.provenance['response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert result.provenance['cost_receipt']['status'] == 'contract_test_zero' and stream.closed


@pytest.mark.asyncio
@pytest.mark.parametrize('headers,code', [
    ({'content-length': str(_MAX_RESPONSE_BYTES + 1)}, 'OPENAI_VISION_RESPONSE_BOUND_EXCEEDED'),
    ({'content-length': '-1'}, 'OPENAI_VISION_RESPONSE_TRANSPORT_INVALID'),
    ({'content-length': '1'}, 'OPENAI_VISION_RESPONSE_TRANSPORT_INVALID'),
    ([('content-length', '20'), ('content-length', '20')], 'OPENAI_VISION_RESPONSE_TRANSPORT_INVALID'),
    ({'content-encoding': 'gzip'}, 'OPENAI_VISION_RESPONSE_TRANSPORT_INVALID'),
    ([('content-encoding', 'identity'), ('content-encoding', 'identity')], 'OPENAI_VISION_RESPONSE_TRANSPORT_INVALID'),
])
async def test_untrusted_response_lengths_and_encoding_fail_closed(tmp_path, headers, code):
    stream = Chunks([json.dumps(fixture.response_payload()).encode()])
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, headers=headers, stream=stream))
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert error.value.code == code and error.value.error_evidence.response_sha256 is None
    assert error.value.error_evidence.retryable is False and stream.closed and _sensitive.get() is False


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['outer_duplicate', 'outer_nan', 'utf16', 'structured_duplicate', 'structured_nan'])
async def test_duplicate_nonfinite_and_nonutf8_json_refuse_without_reinterpreting_usage_or_frames(tmp_path, kind):
    value = fixture.response_payload()
    if kind == 'outer_duplicate': raw = json.dumps(value)[:-1] + ',"usage":' + json.dumps(value['usage']) + '}'
    elif kind == 'outer_nan': raw = json.dumps(value)[:-1] + ',"extra":NaN}'
    elif kind == 'utf16': raw = json.dumps(value).encode('utf-16')
    else:
        text = value['output'][0]['content'][0]['text']
        if kind == 'structured_duplicate': text = text.replace('"frame_index": 0', '"frame_index": 0, "frame_index": 0', 1)
        else: text = text.replace('"confidence": 0.94', '"confidence": NaN', 1)
        value['output'][0]['content'][0]['text'] = text; raw = json.dumps(value)
    payload = raw.encode() if isinstance(raw, str) else raw
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, content=payload))
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert error.value.code == ('OPENAI_VISION_STRUCTURED_OUTPUT_PARSE_FAILED' if kind.startswith('structured') else 'OPENAI_VISION_RESPONSE_PARSE_FAILED')
    assert error.value.error_evidence.response_sha256 == hashlib.sha256(payload).hexdigest()
    assert error.value.error_evidence.retryable is False


@pytest.mark.asyncio
async def test_wire_logging_is_context_local_and_restores_after_success_or_failure(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger='httpx'); caplog.set_level(logging.DEBUG, logger='httpcore.connection')
    logger = logging.getLogger('httpcore.connection'); logger.debug('NORMAL BEFORE ISOLATED VISION')
    def handler(_request):
        logger.debug('SYNTHETIC PRIVATE VISION BODY sk-' + 'q' * 40)
        return httpx.Response(200, json=fixture.response_payload())
    adapter, _, _ = fixture.provider(handler)
    await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert _sensitive.get() is False
    logger.debug('NORMAL AFTER ISOLATED VISION')
    assert 'NORMAL BEFORE' in caplog.text and 'NORMAL AFTER' in caplog.text and 'PRIVATE VISION BODY' not in caplog.text
    assert 'HTTP Request:' not in caplog.text


@pytest.mark.asyncio
async def test_close_error_is_fixed_nonretryable_and_restores_privacy_without_private_exception(tmp_path, caplog):
    caplog.set_level(logging.DEBUG, logger='httpcore.connection')
    stream = Chunks([json.dumps(fixture.response_payload()).encode()], close_error=True)
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, stream=stream))
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert error.value.code == 'OPENAI_VISION_TRANSPORT_UNCLASSIFIED'
    assert error.value.error_evidence.retryable is False and _sensitive.get() is False
    assert 'sk-' not in str(error.value) + str(error.value.error_evidence) and 'PRIVATE CLOSE' not in caplog.text


@pytest.mark.asyncio
async def test_client_cleanup_failure_has_complete_body_hash_fixed_error_and_no_retry(tmp_path):
    raw = json.dumps(fixture.response_payload()).encode()
    class ClosingTransport(httpx.MockTransport):
        async def aclose(self):
            raise RuntimeError('sk-' + 'q' * 40)
    wire = ClosingTransport(lambda _: httpx.Response(200, content=raw))
    adapter, _, _ = fixture.provider(transport=wire)
    with pytest.raises(OpenAIVisionResponseError) as error:
        await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert error.value.code == 'OPENAI_VISION_TRANSPORT_CLOSE_FAILED' and _sensitive.get() is False
    assert error.value.error_evidence.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert error.value.error_evidence.retryable is False and 'sk-' not in str(error.value.error_evidence)


@pytest.mark.asyncio
async def test_cancellation_restores_privacy_and_never_retries(tmp_path):
    calls = []
    async def handler(request):
        calls.append(request); raise asyncio.CancelledError()
    adapter, _, _ = fixture.provider(handler)
    with pytest.raises(asyncio.CancelledError): await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert len(calls) == 1 and _sensitive.get() is False


@pytest.mark.asyncio
async def test_provider_error_inline_image_is_redacted_in_public_diagnostics(tmp_path):
    image = 'data:image/png;base64,' + base64_bytes()
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(400, json={'error': {'message': 'Invalid supplied image ' + image}}))
    with pytest.raises(OpenAIVisionResponseError) as error: await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert image not in str(error.value.error_evidence) and '<redacted>' in error.value.error_evidence.provider_error_message


def base64_bytes():
    import base64
    return base64.b64encode(b'EXPLICIT PRIVATE IMAGE CONTRACT BYTES').decode()


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['transport', 'validation'])
async def test_private_exception_context_is_suppressed_in_tracebacks_but_safe_evidence_retained(tmp_path, kind):
    import traceback
    private = 'sk-' + 'q' * 40
    def handler(request):
        if kind == 'transport': raise httpx.ReadError(private, request=request)
        value = fixture.response_payload(); frames = json.loads(value['output'][0]['content'][0]['text'])
        frames['frames'][0]['caption'] = private + ('x' * 1001)
        value['output'][0]['content'][0]['text'] = json.dumps(frames)
        return httpx.Response(200, json=value)
    adapter, _, _ = fixture.provider(handler)
    with pytest.raises(Exception) as error: await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    shown = ''.join(traceback.format_exception(error.value))
    assert private not in shown and error.value.__suppress_context__ is True
    assert error.value.error_evidence.secret_recorded is False
    assert error.value.error_evidence.code == ('OPENAI_VISION_NETWORK_ERROR' if kind == 'transport' else 'OPENAI_VISION_STRUCTURED_OUTPUT_INVALID')


@pytest.mark.asyncio
async def test_secret_shaped_request_header_is_hashed_without_changing_actual_response_digest(tmp_path):
    private = 'sk-' + 'q' * 40
    raw = json.dumps(fixture.response_payload()).encode()
    adapter, _, _ = fixture.provider(lambda _: httpx.Response(200, headers={'x-request-id': private}, content=raw))
    result = await fixture.analyze(adapter, tmp_path / 'explicit-owned-source')
    assert result.provenance['provider_request_id'] == 'sha256:' + hashlib.sha256(private.encode()).hexdigest()
    assert result.provenance['response_sha256'] == hashlib.sha256(raw).hexdigest() and private not in str(result.provenance)
