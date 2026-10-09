"""Current pre-send admission, synchronous and private; protocol mocks only."""
import hashlib, traceback
import httpx
import pytest
from tests import test_openai_vision_provider as fixture
from app.openai_vision_provider import OpenAIVisionProvider, OpenAIVisionResponseError
from app.publishing_wire import _sensitive


def provider(handler, guard, observer=None):
    return OpenAIVisionProvider(credential_alias='explicit-guard',credential_resolver=lambda _:'contract-test-key',
        frame_extractor=fixture.StaticFrameExtractor(),transport=httpx.MockTransport(handler),allow_zero_cost_contract_test=True,
        dispatch_guard=guard,response_observer=observer)


@pytest.mark.asyncio
async def test_guard_runs_after_input_before_one_send_and_complete_response_observation(tmp_path):
    order = []
    def guard(): order.append('admission')
    def handler(request):
        assert order == ['admission']; order.append('wire'); return httpx.Response(200,json=fixture.response_payload())
    def observe(_): order.append('complete-response')
    adapter = provider(handler,guard,observe); assert order == []
    await fixture.analyze(adapter,tmp_path/'owned-source'); assert order == ['admission','wire','complete-response']
    assert not _sensitive.get()


@pytest.mark.asyncio
async def test_private_admission_failure_has_no_wire_response_retry_or_raw_exception_cause(tmp_path):
    calls = []
    def guard(): raise RuntimeError('sk-private-admission-diagnostic')
    with pytest.raises(OpenAIVisionResponseError) as caught:
        await fixture.analyze(provider(lambda _:calls.append(True),guard),tmp_path/'owned-source')
    assert calls == [] and caught.value.code == 'OPENAI_VISION_DISPATCH_ADMISSION_FAILED'
    assert caught.value.error_evidence.response_sha256 is None and caught.value.error_evidence.retryable is False
    assert 'sk-private-admission' not in ''.join(traceback.format_exception(caught.value)) and not _sensitive.get()


@pytest.mark.parametrize('kind',['async-function','non-callable','nonempty-return','coroutine-return'])
@pytest.mark.asyncio
async def test_admission_cannot_be_async_ignored_or_boolean_result(tmp_path,kind):
    async def pending(): return None
    if kind in ('async-function','non-callable'):
        with pytest.raises(ValueError): provider(lambda _:None,pending if kind=='async-function' else 1)
    else:
        with pytest.raises(OpenAIVisionResponseError) as caught:
            await fixture.analyze(provider(lambda _:pytest.fail('NO WIRE'),lambda:True if kind=='nonempty-return' else pending()),tmp_path/'owned-source')
        assert caught.value.code == 'OPENAI_VISION_DISPATCH_ADMISSION_FAILED'
    assert not _sensitive.get()
