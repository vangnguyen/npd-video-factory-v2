"""Bridge authentication and request identity contracts; no GPU is dispatched."""
import json
import pytest
import httpx
from app.config import Settings
from app.media_generation_scope import current_generation_scope, media_generation_scope
from app.media_intelligence_models import ImageGenerationInput
from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider, MediaProviderNotConfigured

TOKEN = 'explicit-comfyui-scope-fixture-token-32-characters'


def provider(transport, *, token=TOKEN):
    return ComfyUIBridgeGenerationProvider(bridge_url='http://bridge.test', modality='image',
        workflow_id='npd-text-to-image-v1', enabled=True, timeout_seconds=1, service_token=token, transport=transport)


@pytest.mark.asyncio
async def test_missing_key_or_scope_blocks_before_dispatch_and_scope_resets():
    def forbidden(_request): raise AssertionError('GPU dispatch is forbidden')
    transport = httpx.MockTransport(forbidden)
    with pytest.raises(MediaProviderNotConfigured):
        await provider(transport, token='').generate(ImageGenerationInput(prompt='fixture'))
    with pytest.raises(ValueError, match='MEDIA_GENERATION_SCOPE_REQUIRED'):
        await provider(transport).generate(ImageGenerationInput(prompt='fixture'))
    with media_generation_scope(workspace_id='workspace-A', project_id='project-A', job_id='job-A'):
        assert current_generation_scope() == ('workspace-A', 'project-A', 'job-A')
    with pytest.raises(ValueError, match='MEDIA_GENERATION_SCOPE_REQUIRED'): current_generation_scope()
    settings = Settings(_env_file=None, comfyui_bridge_token=TOKEN)
    assert TOKEN not in repr(settings) and TOKEN not in settings.model_dump_json()


@pytest.mark.asyncio
async def test_identical_prompt_in_different_workspace_or_job_gets_separate_bridge_identity():
    sent = []
    def handler(request):
        body = json.loads(request.content); sent.append(body)
        assert request.headers['Authorization'] == 'Bearer ' + TOKEN
        assert request.headers['X-VF-Workspace-Id'] == body['workspace_id']
        return httpx.Response(202, json={'job_id': 'cui_explicit_mock', 'workflow_id': body['workflow_id'],
            'workspace_id': body['workspace_id'], 'status': 'succeeded', 'result': {
                'artifact_reference': 'fixture://comfyui/mock', 'checksum_sha256': 'a' * 64, 'fixture': True}})
    adapter = provider(httpx.MockTransport(handler))
    payload = ImageGenerationInput(prompt='same explicit fixture')
    for workspace, job in [('workspace-A', 'job-A'), ('workspace-B', 'job-A'), ('workspace-A', 'job-B'), ('workspace-A', 'job-A')]:
        with media_generation_scope(workspace_id=workspace, project_id='project-A', job_id=job):
            result = await adapter.generate(payload)
        assert not result.production_eligible and result.generation_provenance['fixture']
        assert not result.generation_provenance['binary_artifact_registered']
        assert result.actual_cost_vnd is None and result.estimated_cost_vnd is None
    assert len({body['client_request_id'] for body in sent}) == 3
    assert sent[0]['client_request_id'] == sent[3]['client_request_id']
    assert all('graph' not in body for body in sent)


@pytest.mark.asyncio
@pytest.mark.parametrize('job_id,workspace,workflow', [
    ('cui_../../private', 'workspace-A', 'npd-text-to-image-v1'),
    ('cui_mock', 'workspace-B', 'npd-text-to-image-v1'),
    ('cui_mock', 'workspace-A', 'unknown-workflow')])
async def test_untrusted_response_binding_or_job_path_rejected_before_poll(job_id, workspace, workflow):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(202, json={'job_id': job_id, 'workspace_id': workspace, 'workflow_id': workflow, 'status': 'queued'})
    with media_generation_scope(workspace_id='workspace-A', project_id='project-A', job_id='job-A'):
        with pytest.raises(ValueError, match='COMFYUI_JOB_BINDING_INVALID'):
            await provider(httpx.MockTransport(handler)).generate(ImageGenerationInput(prompt='fixture'))
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_unpriced_gpu_generation_needs_approval_before_queue_or_dispatch(tmp_path):
    from test_media_intelligence import setup_media_stack, plan_request
    from app.media_intelligence_service import MediaProviderBundle
    from app.media_intelligence_models import MediaResolutionRequest
    from app.media_intelligence_providers import DeterministicStockMediaProvider, DeterministicVideoGenerationProvider
    def forbidden(_request): raise AssertionError('Unpriced GPU dispatch is forbidden')
    adapter = provider(httpx.MockTransport(forbidden))
    stack = await setup_media_stack(tmp_path, MediaProviderBundle(stock=DeterministicStockMediaProvider(),
        image=adapter, video=DeterministicVideoGenerationProvider()))
    try:
        stack['planner'].allow_external_execution = True # Mechanical mock test only, not environment enablement.
        payload = plan_request(stack).model_copy(update={'selection_policy': 'priority', 'resolver_priority': ['ai_image'], 'allow_stock': False})
        plan = await stack['planner'].create(project_id=stack['project'].project_id, payload=payload)
        assert plan.needs_approval and all(item.needs_approval for item in plan.items)
        assert all(item.provenance['estimated_cost_unknown'] for item in plan.items)
        for item in plan.items:
            job = await stack['resolver'].enqueue(project_id=plan.project_id, media_plan_id=plan.media_plan_id,
                media_plan_item_id=item.media_plan_item_id, payload=MediaResolutionRequest())
            assert job.status == 'needs_approval' and job.estimated_cost_vnd is None and job.actual_cost_vnd is None
        assert stack['queue'].values == []
    finally:
        await stack['engine'].dispose()
