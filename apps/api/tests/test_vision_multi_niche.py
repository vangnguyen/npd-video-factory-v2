"""Provider contract accepts generic niches without changing engine code."""
import json
import httpx
import pytest
from tests import test_openai_vision_provider as fixture


@pytest.mark.asyncio
@pytest.mark.parametrize('label', ['technology_ai_education', 'cooking_instruction', 'real_estate_overview'])
async def test_same_structured_adapter_handles_configured_niches_and_sample_limits(tmp_path, label):
    captured = []
    def handler(request):
        body = json.loads(request.content); captured.append(body)
        prompt = body['input'][0]['content'][0]['text']
        assert 'real-estate media' not in prompt and 'any content niche' in prompt
        assert 'Vietnamese diacritics' in prompt
        assert 'continuous tracking' in prompt and 'decoded presentation timestamps' in prompt
        assert 'independently calibrated confidence' in prompt and body['store'] is False
        value = fixture.response_payload()
        frames = json.loads(value['output'][0]['content'][0]['text'])
        for frame in frames['frames']:
            frame.update(semantic_label=label, environment='explicit_niche_contract_mock', action='explicit_mock')
        value['output'][0]['content'][0]['text'] = json.dumps(frames, ensure_ascii=False)
        return httpx.Response(200, json=value)
    adapter, _, extractor = fixture.provider(handler)
    result = await fixture.analyze(adapter, tmp_path / 'explicit-synthetic-source')
    assert len(captured) == 1 and extractor.calls == 1
    assert all(frame.semantic_label == label for frame in result.frames)
    assert result.provenance['mock_tested'] is True and result.provenance['real_provider_tested'] is False
