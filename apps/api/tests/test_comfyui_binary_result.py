"""Binary adapter wire contracts use explicit fixtures, not decode acceptance."""
import copy
import hashlib
import json
import pytest
import httpx
from app.comfyui_binary_result import checksum
from app.media_generation_scope import media_generation_scope
from app.media_intelligence_models import ImageGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
from app.media_generation_routes import generation_envelope, workflow_routes

CONTENT = b'\x89PNG\r\n\x1a\nexplicit-MockTransport-only-not-decodable'
TOKEN = 'explicit-binary-api-fixture-token-32-characters'


def fixture():
    payload = ImageGenerationInput(prompt='Explicit wire fixture', seed=17)
    _, _, inputs = generation_envelope('image', payload, workflow_routes('image', 'npd-text-to-image-v1'))
    content_sha = hashlib.sha256(CONTENT).hexdigest()
    artifact_id = checksum(['workspace-A', 'cui_binary_fixture', content_sha])
    result = {'artifact_reference': 'vf-artifact://' + artifact_id, 'checksum_sha256': content_sha,
        'workflow_id': 'npd-text-to-image-v1', 'workflow_version': '1.0.0', 'fixture': True}
    job = {'job_id': 'cui_binary_fixture', 'workspace_id': 'workspace-A', 'workflow_id': result['workflow_id'],
        'workflow_version': result['workflow_version'], 'status': 'succeeded', 'result': result,
        'result_metadata_sha256': checksum(result)}
    metadata = {'workspace_id': 'workspace-A', 'job_id': job['job_id'], 'artifact_id': artifact_id,
        'checksum_sha256': content_sha, 'mime_type': 'image/png', 'size_bytes': len(CONTENT), 'fixture': True,
        'rights_status': 'unknown', 'production_eligible': False,
        'media': {'width': 128, 'height': 72, 'duration_seconds': None, 'fps': None, 'full_decode_passed': True, 'qc_passed': False,
            'decoded_video_frames': 1, 'audio_streams': 0, 'video_codec': 'png'},
        'provenance': {'workflow_id': result['workflow_id'], 'workflow_version': result['workflow_version'], 'inputs_sha256': checksum(inputs),
            'prompt_sha256': hashlib.sha256(payload.prompt.encode()).hexdigest(), 'seed': 17, 'estimated_cost_vnd': None, 'actual_cost_vnd': None}}
    return job, metadata


async def generate(handler):
    adapter = ComfyUIBridgeGenerationProvider(bridge_url='http://explicit-fixture-bridge', modality='image',
        workflow_id='npd-text-to-image-v1', enabled=True, service_token=TOKEN, transport=httpx.MockTransport(handler))
    with media_generation_scope(workspace_id='workspace-A', project_id='project-A', job_id='resolution-A'):
        return await adapter.generate(ImageGenerationInput(prompt='Explicit wire fixture', seed=17))


@pytest.mark.asyncio
async def test_registered_binary_is_exact_bytes_still_unknown_rights_cost_and_non_production():
    job, metadata = fixture(); calls = []
    def handler(request):
        calls.append(request.url.path)
        assert request.headers['Authorization'] == 'Bearer ' + TOKEN and request.headers['X-VF-Workspace-Id'] == 'workspace-A'
        if request.method == 'POST': return httpx.Response(202, json=job)
        if request.url.path.endswith('/metadata'): return httpx.Response(200, json=metadata)
        return httpx.Response(200, content=CONTENT, headers={'Content-Type': 'image/png', 'X-VF-Content-SHA256': metadata['checksum_sha256']})
    result = await generate(handler)
    assert result.payload == CONTENT and result.content_type == 'image/png' and result.filename.endswith('.png')
    assert result.width == 128 and result.height == 72 and result.duration_seconds is None
    assert result.rights_status == 'unknown' and not result.production_eligible and result.actual_cost_vnd is None and result.estimated_cost_vnd is None
    assert result.generation_provenance['binary_artifact_registered'] and result.generation_provenance['fixture']
    assert result.generation_provenance['registered_artifact'] == metadata and len(calls) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize('field,value', [('workspace_id', 'foreign'), ('job_id', 'cui_foreign'),
    ('artifact_id', 'f' * 64), ('checksum_sha256', 'f' * 64), ('rights_status', 'licensed'),
    ('production_eligible', True), ('mime_type', 'video/mp4'), ('size_bytes', 300 * 1024 * 1024), ('fixture', False)])
async def test_forged_or_foreign_metadata_rejects_before_binary_fetch(field, value):
    job, metadata = fixture(); metadata[field] = value; calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.method == 'POST': return httpx.Response(202, json=job)
        assert request.url.path.endswith('/metadata')
        return httpx.Response(200, json=metadata)
    with pytest.raises(ValueError, match='ARTIFACT_'): await generate(handler)
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_missing_decode_or_result_checksum_cannot_pass_as_registered_binary():
    for invalid_result in [False, True]:
        job, metadata = fixture()
        if invalid_result: job['result_metadata_sha256'] = 'f' * 64
        else: metadata['media']['full_decode_passed'] = False
        def handler(request):
            if request.method == 'POST': return httpx.Response(202, json=job)
            return httpx.Response(200, json=metadata)
        with pytest.raises(ValueError, match='ARTIFACT_'): await generate(handler)


@pytest.mark.asyncio
@pytest.mark.parametrize('kind', ['bytes', 'header', 'mime', 'length', 'large'])
async def test_wrong_binary_bytes_headers_mime_or_bounds_reject(kind):
    job, metadata = fixture()
    def handler(request):
        if request.method == 'POST': return httpx.Response(202, json=job)
        if request.url.path.endswith('/metadata'): return httpx.Response(200, json=metadata)
        content = CONTENT + b'corrupt' if kind in {'bytes', 'length'} else CONTENT
        headers = {'Content-Type': 'text/html' if kind == 'mime' else 'image/png',
            'X-VF-Content-SHA256': 'f' * 64 if kind == 'header' else metadata['checksum_sha256']}
        if kind == 'large': headers['Content-Length'] = str(33 * 1024 * 1024)
        return httpx.Response(200, content=content, headers=headers)
    with pytest.raises(ValueError, match='ARTIFACT_'): await generate(handler)
