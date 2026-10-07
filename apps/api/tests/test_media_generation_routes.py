"""Approved manifest wire acceptance for every generation mode; explicit mocks."""
import json
from pathlib import Path
import httpx
import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError
from app.media_generation_scope import media_generation_scope
from app.media_generation_routes import workflow_routes
from app.media_intelligence_models import ImageGenerationInput, VideoGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider

MANIFEST = json.loads((Path(__file__).parents[3] / 'workflows/comfyui/manifest.json').read_text(encoding='utf-8'))
DEFINITIONS = {item['workflow_id']: item for item in MANIFEST['workflows']}
IMAGE = 'asset://explicit-owned-image-fixture'
MASK = 'asset://explicit-owned-mask-fixture'


CASES = [
    ('image', {'operation': 'generate'}, 'npd-text-to-image-v1', 'generate'),
    ('image', {'operation': 'generate', 'reference_images': [IMAGE]}, 'npd-image-to-image-v1', 'image_to_image'),
    ('image', {'operation': 'image_to_image', 'reference_images': [IMAGE]}, 'npd-image-to-image-v1', 'image_to_image'),
    ('image', {'operation': 'variation', 'reference_images': [IMAGE]}, 'npd-image-to-image-v1', 'variation'),
    ('image', {'operation': 'inpaint', 'reference_images': [IMAGE], 'mask_reference': MASK}, 'npd-inpaint-v1', 'inpaint'),
    ('image', {'operation': 'upscale', 'reference_images': [IMAGE], 'upscale_factor': 4}, 'npd-upscale-v1', 'upscale'),
    ('video', {'mode': 'text_to_video'}, 'npd-video-generation-v1', 'text_to_video'),
    ('video', {'mode': 'image_to_video', 'reference_images': [IMAGE]}, 'npd-image-to-video-v1', 'image_to_video'),
    ('video', {'mode': 'reference_assisted', 'reference_images': [IMAGE, 'asset://second-owned-fixture']}, 'npd-image-to-video-v1', 'reference_assisted'),
]


@pytest.mark.asyncio
@pytest.mark.parametrize('modality,options,expected_workflow,expected_operation', CASES)
async def test_each_mode_matches_separate_approved_manifest_and_retains_evidence(modality, options, expected_workflow, expected_operation):
    requests = []
    def handler(request):
        sent = json.loads(request.content); requests.append(sent)
        assert set(sent) == {'workflow_id', 'workspace_id', 'inputs', 'client_request_id'}
        assert sent['workflow_id'] == expected_workflow
        Draft202012Validator(DEFINITIONS[sent['workflow_id']]['input_schema']).validate(sent['inputs'])
        assert 'graph' not in sent['inputs'] and 'model_weights' not in sent['inputs']
        return httpx.Response(202, json={'job_id': 'cui_explicit_modes_fixture', 'workspace_id': sent['workspace_id'],
            'workflow_id': expected_workflow, 'workflow_version': '1.0.0', 'status': 'succeeded', 'result': {
                'artifact_reference': 'fixture://comfyui/mode-result', 'checksum_sha256': 'a' * 64, 'fixture': True}})
    primary = 'npd-text-to-image-v1' if modality == 'image' else 'npd-video-generation-v1'
    provider = ComfyUIBridgeGenerationProvider(bridge_url='http://bridge.test', modality=modality, workflow_id=primary,
        enabled=True, service_token='explicit-generation-mode-contract-token-32-characters', transport=httpx.MockTransport(handler))
    payload = (ImageGenerationInput if modality == 'image' else VideoGenerationInput)(prompt='Explicit mode fixture', seed=27, **options)
    with media_generation_scope(workspace_id='workspace-A', project_id='project-A', job_id='job-A'):
        result = await provider.generate(payload)
    evidence = result.generation_provenance
    assert evidence['workflow'] == expected_workflow and evidence['operation'] == expected_operation
    assert evidence['model'] == 'workflow:' + expected_workflow and evidence['workflow_version'] == '1.0.0'
    assert evidence['seed'] == 27 and evidence['prompt'] == payload.prompt
    assert evidence['reference_images'] == payload.reference_images
    assert evidence['generation_time_seconds'] >= 0 and evidence['mock_transport_used'] and evidence['fixture']
    assert not evidence['binary_artifact_registered'] and result.actual_cost_vnd is None and result.estimated_cost_vnd is None
    assert not result.production_eligible and result.rights_status == 'unknown' and not result.real_provider_tested
    if expected_operation == 'inpaint':
        assert requests[0]['inputs']['mask_reference'] == MASK and evidence['mask_reference'] == MASK
    if expected_operation == 'upscale':
        assert requests[0]['inputs']['scale'] == 4 and evidence['upscale_factor'] == 4


@pytest.mark.parametrize('model,options', [
    (ImageGenerationInput, {'operation': 'variation'}), (ImageGenerationInput, {'operation': 'image_to_image'}),
    (ImageGenerationInput, {'operation': 'inpaint', 'reference_images': [IMAGE]}),
    (ImageGenerationInput, {'operation': 'generate', 'mask_reference': MASK}),
    (ImageGenerationInput, {'operation': 'generate', 'upscale_factor': 4}),
    (ImageGenerationInput, {'reference_images': ['  ']}),
    (VideoGenerationInput, {'mode': 'image_to_video'}), (VideoGenerationInput, {'mode': 'reference_assisted'}),
])
def test_missing_or_incompatible_reference_mask_scale_rejected_before_dispatch(model, options):
    with pytest.raises(ValidationError): model(prompt='explicit fixture', **options)


def test_text_generation_serialization_preserves_legacy_fingerprint_and_upscale_defaults_are_explicit():
    assert ImageGenerationInput(prompt='legacy fixture').model_dump(mode='json') == {
        'prompt': 'legacy fixture', 'negative_prompt': '', 'aspect_ratio': '9:16', 'reference_images': [],
        'style': 'cinematic', 'seed': 1, 'quality': 'draft', 'operation': 'generate'}
    upscale = ImageGenerationInput(prompt='upscale fixture', operation='upscale', reference_images=[IMAGE])
    assert upscale.upscale_factor == 2 and upscale.model_dump(mode='json')['upscale_factor'] == 2


def test_configured_routes_are_copied_validated_and_preserve_primary_workflow_override():
    override = {'variation': 'owner-reviewed-variation-v1'}
    routes = workflow_routes('image', 'owner-reviewed-primary-v1', override)
    override['variation'] = 'changed-without-review'
    assert routes['variation'] == 'owner-reviewed-variation-v1' and routes['generate'] == 'owner-reviewed-primary-v1'
    with pytest.raises(TypeError): routes['generate'] = 'mutate'
    with pytest.raises(ValueError): workflow_routes('image', 'approved-v1', {'unrecognized': 'unsafe-v1'})
    with pytest.raises(ValueError): workflow_routes('image', '../unsafe')


@pytest.mark.asyncio
async def test_untrusted_bridge_failure_body_is_not_exposed_in_adapter_errors():
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(202, json={'job_id': 'cui_fixture_error', 'workflow_id': body['workflow_id'],
            'workspace_id': body['workspace_id'], 'status': 'failed', 'error_code': 'provider-secret private provider body'})
    adapter = ComfyUIBridgeGenerationProvider(bridge_url='http://bridge.test', modality='image',
        workflow_id='npd-text-to-image-v1', enabled=True, service_token='explicit-error-contract-token-32-characters',
        transport=httpx.MockTransport(handler))
    with media_generation_scope(workspace_id='workspace-A', project_id='project-A', job_id='job-A'):
        with pytest.raises(RuntimeError, match='BRIDGE_FAILURE') as failed:
            await adapter.generate(ImageGenerationInput(prompt='explicit fixture'))
    assert 'provider-secret' not in str(failed.value) and 'private provider body' not in str(failed.value)
