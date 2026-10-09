"""Complete response accounting before semantic failure; no raw body or paid wire."""
import hashlib, json, traceback
from decimal import Decimal
import httpx
import pytest
from pydantic import ValidationError
from tests import test_openai_vision_provider as fixture
from tests.test_vision_transport_safety import Chunks
from app import openai_vision_provider as module
from app.openai_vision_provider import OpenAIVisionProvider, OpenAIVisionResponseError, VisionResponseObservation, _MAX_RESPONSE_BYTES
from app.provider_safety import ProviderTimeoutError
from app.publishing_wire import _sensitive


def provider(handler, observer):
    return OpenAIVisionProvider(credential_alias='explicit-vision-response', credential_resolver=lambda _: 'contract-test-key',
        frame_extractor=fixture.StaticFrameExtractor(), estimated_cost_vnd=Decimal('300'),
        input_vnd_per_million_tokens=Decimal('1000000'), cached_input_vnd_per_million_tokens=Decimal('500000'),
        output_vnd_per_million_tokens=Decimal('2000000'), transport=httpx.MockTransport(handler),
        allow_zero_cost_contract_test=True, response_observer=observer)


@pytest.mark.asyncio
async def test_single_complete_observation_precedes_semantic_mapping_and_matches_final_usage_hash(tmp_path, monkeypatch):
    observations = []; raw = json.dumps(fixture.response_payload()).encode(); requests = []
    def handler(request):
        requests.append(request.content); return httpx.Response(200, content=raw, headers={'x-request-id': 'req_retained'})
    adapter = provider(handler, observations.append); original = adapter._map_frame
    def mapped(*args):
        assert len(observations) == 1; return original(*args)
    monkeypatch.setattr(adapter, '_map_frame', mapped)
    assert observations == []
    result = await fixture.analyze(adapter, tmp_path / 'owned-source')
    observation = observations[0]
    assert observation.response_sha256 == result.provenance['response_sha256'] == hashlib.sha256(raw).hexdigest()
    assert observation.request_sha256 == result.provenance['request_sha256'] == hashlib.sha256(requests[0]).hexdigest()
    assert observation.input_tokens == 120 and observation.cached_input_tokens == 20 and observation.output_tokens == 80
    assert Decimal(observation.calculated_usage_cost_vnd) == result.actual_cost_vnd == Decimal('270.000000')
    assert observation.mock_transport is True and observation.billing_invoice_verified is False
    public = observation.model_dump_json()
    assert 'contract-test-key' not in public and 'data:image/' not in public and 'caption' not in public and 'frames' not in public
    assert not _sensitive.get()


@pytest.mark.parametrize('kind', ['invalid-structured-json', 'invalid-structured-fields', 'missing-frames', 'wrong-model', 'incomplete-output'])
@pytest.mark.asyncio
async def test_complete_hash_and_valid_usage_are_retained_even_when_semantics_or_envelope_reject(tmp_path, kind):
    payload = fixture.response_payload()
    if kind == 'invalid-structured-json': payload['output'][0]['content'][0]['text'] = 'not JSON'
    elif kind == 'invalid-structured-fields': payload['output'][0]['content'][0]['text'] = json.dumps({'frames': [{'unsafe-extra': True}]})
    elif kind == 'missing-frames': payload['output'][0]['content'][0]['text'] = json.dumps({'frames': []})
    elif kind == 'wrong-model': payload['model'] = 'unapproved-model'
    else: payload['status'] = 'incomplete'
    raw = json.dumps(payload).encode(); observations = []
    adapter = provider(lambda _: httpx.Response(200, content=raw), observations.append)
    with pytest.raises(OpenAIVisionResponseError): await fixture.analyze(adapter, tmp_path / 'owned-source')
    assert len(observations) == 1 and observations[0].response_sha256 == hashlib.sha256(raw).hexdigest()
    assert observations[0].calculated_usage_cost_vnd == '270.000000'
    assert not _sensitive.get()


@pytest.mark.parametrize('usage', [None, {}, {'input_tokens': 120, 'output_tokens': 80},
    {'input_tokens': True, 'output_tokens': 80, 'input_tokens_details': {'cached_tokens': 20}},
    {'input_tokens': '120', 'output_tokens': 80, 'input_tokens_details': {'cached_tokens': 20}},
    {'input_tokens': 120, 'output_tokens': 80.0, 'input_tokens_details': {'cached_tokens': 20}},
    {'input_tokens': -1, 'output_tokens': 80, 'input_tokens_details': {'cached_tokens': 0}},
    {'input_tokens': 120, 'output_tokens': 80, 'input_tokens_details': {'cached_tokens': 121}},
    {'input_tokens': 16385, 'output_tokens': 80, 'input_tokens_details': {'cached_tokens': 20}},
    {'input_tokens': 120, 'output_tokens': 8001, 'input_tokens_details': {'cached_tokens': 20}}])
@pytest.mark.asyncio
async def test_missing_noninteger_negative_or_unbounded_usage_never_coerces_defaults_or_clamps(tmp_path, usage):
    payload = fixture.response_payload(); payload['usage'] = usage; observations = []; raw = json.dumps(payload).encode()
    adapter = provider(lambda _: httpx.Response(200, content=raw), observations.append)
    with pytest.raises(OpenAIVisionResponseError): await fixture.analyze(adapter, tmp_path / 'owned-source')
    assert len(observations) == 1 and observations[0].response_sha256 == hashlib.sha256(raw).hexdigest()
    assert observations[0].input_tokens is observations[0].cached_input_tokens is observations[0].output_tokens is observations[0].calculated_usage_cost_vnd is None


@pytest.mark.parametrize('raw', [b'{"usage":{},"usage":{}}', b'{"usage":NaN}', b'null', b'not UTF8 \xff'])
@pytest.mark.asyncio
async def test_complete_malformed_json_retains_digest_and_unknown_usage_without_raw_private_body(tmp_path, raw):
    observations = []; adapter = provider(lambda _: httpx.Response(200, content=raw), observations.append)
    with pytest.raises(OpenAIVisionResponseError): await fixture.analyze(adapter, tmp_path / 'owned-source')
    assert len(observations) == 1 and observations[0].response_sha256 == hashlib.sha256(raw).hexdigest()
    assert observations[0].calculated_usage_cost_vnd is None


@pytest.mark.parametrize('kind', ['oversize', 'timeout', 'wrong-length'])
@pytest.mark.asyncio
async def test_incomplete_or_ambiguous_body_never_calls_complete_response_observer(tmp_path, kind):
    observations = []
    def handler(request):
        if kind == 'timeout': raise httpx.ReadTimeout('sk-private-test-value', request=request)
        if kind == 'oversize': return httpx.Response(200, stream=Chunks([b'x' * _MAX_RESPONSE_BYTES, b'x']))
        return httpx.Response(200, content=b'{}', headers={'Content-Length': '3'})
    with pytest.raises((OpenAIVisionResponseError, ProviderTimeoutError)):
        await fixture.analyze(provider(handler, observations.append), tmp_path / 'owned-source')
    assert observations == [] and not _sensitive.get()


@pytest.mark.asyncio
async def test_observer_failure_is_private_fixed_nonretryable_with_original_complete_digest(tmp_path):
    raw = json.dumps(fixture.response_payload()).encode(); calls = []
    def observer(value):
        calls.append(value); raise RuntimeError('sk-private-observer-diagnostic-value')
    with pytest.raises(OpenAIVisionResponseError) as caught:
        await fixture.analyze(provider(lambda _: httpx.Response(200, content=raw), observer), tmp_path / 'owned-source')
    assert len(calls) == 1 and caught.value.code == 'OPENAI_VISION_RESPONSE_OBSERVATION_FAILED'
    assert caught.value.error_evidence.response_sha256 == hashlib.sha256(raw).hexdigest()
    assert caught.value.error_evidence.retryable is False
    assert 'sk-private-observer' not in ''.join(traceback.format_exception(caught.value)) and not _sensitive.get()


@pytest.mark.asyncio
async def test_complete_observation_survives_later_client_cleanup_failure(tmp_path, monkeypatch):
    observations = []; raw = json.dumps(fixture.response_payload()).encode(); original = httpx.AsyncClient.aclose
    async def close(client):
        await original(client); raise RuntimeError('sk-private-cleanup-value')
    monkeypatch.setattr(httpx.AsyncClient, 'aclose', close)
    with pytest.raises(OpenAIVisionResponseError) as caught:
        await fixture.analyze(provider(lambda _: httpx.Response(200, content=raw), observations.append), tmp_path / 'owned-source')
    assert caught.value.code == 'OPENAI_VISION_TRANSPORT_CLOSE_FAILED' and len(observations) == 1
    assert observations[0].response_sha256 == hashlib.sha256(raw).hexdigest() and not _sensitive.get()


@pytest.mark.asyncio
async def test_private_request_id_redacts_before_observer_and_explicit_zero_usage_stays_zero(tmp_path):
    observations = []; payload = fixture.response_payload(); payload['usage'] = {'input_tokens': 0, 'output_tokens': 0, 'input_tokens_details': {'cached_tokens': 0}}
    result = await fixture.analyze(provider(lambda _: httpx.Response(200, json=payload, headers={'x-request-id': 'sk-private-provider-request-id'}), observations.append), tmp_path / 'owned-source')
    assert observations[0].provider_request_id.startswith('sha256:') and observations[0].input_tokens == 0
    assert observations[0].calculated_usage_cost_vnd == '0.000000' and result.actual_cost_vnd == 0


def test_observer_is_explicit_synchronous_callback_and_invoice_marker_is_raw_false():
    async def async_observer(_): pass
    for observer in (async_observer, 1, object()):
        with pytest.raises(ValueError, match='Synchronous'): provider(lambda _: None, observer)
    value = {'request_sha256': 'a' * 64, 'response_sha256': 'b' * 64, 'http_status': 200, 'client_request_id': 'explicit', 'mock_transport': True}
    for changes in ({'billing_invoice_verified': 0}, {'input_tokens': 0}, {'mock_transport': 1}, {'raw_body': 'private'}):
        with pytest.raises(ValidationError): VisionResponseObservation.model_validate({**value, **changes})


@pytest.mark.asyncio
async def test_unawaited_callback_return_is_closed_and_refused(tmp_path):
    async def pending(): return None
    with pytest.raises(OpenAIVisionResponseError) as caught:
        await fixture.analyze(provider(lambda _: httpx.Response(200, json=fixture.response_payload()), lambda _: pending()), tmp_path / 'owned-source')
    assert caught.value.code == 'OPENAI_VISION_RESPONSE_OBSERVATION_FAILED' and not _sensitive.get()
