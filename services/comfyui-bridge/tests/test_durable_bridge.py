"""CPU-only persistence/security/lifecycle acceptance, with explicit mock GPU."""
import asyncio
from datetime import datetime, timezone
import json
import pytest
from httpx import ASGITransport, AsyncClient
from npd_comfyui_bridge.backend import DeterministicMockComfyUIBackend, DisabledComfyUIBackend
from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore, checksum
from npd_comfyui_bridge.models import BridgeJobRead
from npd_comfyui_bridge.service import ComfyUIBridgeService
from npd_comfyui_bridge.workflows import WorkflowRegistry
from test_bridge import MANIFEST, text_to_image_request, wait_terminal, load_bridge_app


@pytest.mark.asyncio
async def test_durable_terminal_replay_result_hash_and_workspace_isolation_survive_restart(tmp_path):
    path = tmp_path / 'bridge.sqlite3'
    service = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend(delay_seconds=0),
        job_store=SQLiteBridgeJobStore(path))
    original = text_to_image_request('same-client-request')
    first = await service.submit(original)
    second = await service.submit(original.model_copy(update={'workspace_id': 'fixture-workspace-B'}))
    assert first.job_id != second.job_id
    finished = await wait_terminal(service, first.job_id)
    await wait_terminal(service, second.job_id)
    assert finished.result_metadata_sha256 == checksum(finished.result)
    audit = await service.events(first.job_id)
    assert audit[-1]['status'] == 'succeeded' and 'prompt' not in json.dumps(audit)
    finished.result['fixture'] = False
    assert (await service.get(first.job_id)).result['fixture']
    await service.close()
    offline = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), DisabledComfyUIBackend(), job_store=SQLiteBridgeJobStore(path))
    try:
        replay = await offline.submit(original)
        assert replay.job_id == first.job_id and replay.status == 'succeeded'
        assert replay.result['fixture'] and replay.result_metadata_sha256 == checksum(replay.result)
        assert len(await offline.list_jobs(workspace_id=original.workspace_id)) == 1
        assert (await offline.events(first.job_id)) == audit
    finally:
        await offline.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('status', ['queued', 'running'])
async def test_interrupted_durable_jobs_require_explicit_retry_and_do_not_replay(status, tmp_path):
    registry = WorkflowRegistry(MANIFEST)
    path = tmp_path / 'bridge.sqlite3'
    store = SQLiteBridgeJobStore(path)
    request = text_to_image_request('fixture-interrupted')
    now = datetime.now(timezone.utc)
    job = BridgeJobRead(workspace_id=request.workspace_id, job_id='cui_interrupted', workflow_id=request.workflow_id,
        workflow_version='1.0.0', client_request_id=request.client_request_id, status=status, progress=45 if status == 'running' else 0,
        retry_count=0, result=None, error_code=None, failure_reason=None, created_at=now, updated_at=now,
        definition_sha256=registry.fingerprint(registry.get(request.workflow_id)))
    store.save(job, request); store.close()
    class CountingBackend(DeterministicMockComfyUIBackend):
        def __init__(self): super().__init__(delay_seconds=0); self.calls = 0
        async def execute(self, **kwargs): self.calls += 1; return await super().execute(**kwargs)
    backend = CountingBackend()
    recovered = ComfyUIBridgeService(registry, backend, job_store=SQLiteBridgeJobStore(path))
    try:
        current = await recovered.get(job.job_id)
        assert current.status == 'failed' and current.error_code == 'RECOVERY_REQUIRED' and current.recovery_required
        await asyncio.sleep(0)
        assert backend.calls == 0
        assert (await recovered.submit(request)).job_id == job.job_id and backend.calls == 0
        await recovered.retry(job.job_id)
        result = await wait_terminal(recovered, job.job_id)
        assert result.status == 'succeeded' and backend.calls == 1 and result.retry_count == 1
        assert not result.recovery_required
        assert any(e['error_code'] == 'RECOVERY_REQUIRED' for e in await recovered.events(job.job_id))
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_bounded_queue_cancel_pending_and_owned_shutdown_retain_recovery(tmp_path):
    class GateBackend(DeterministicMockComfyUIBackend):
        def __init__(self): super().__init__(delay_seconds=0); self.calls = []; self.started = asyncio.Event(); self.release = asyncio.Event()
        async def execute(self, **kwargs):
            self.calls.append(kwargs['inputs']['seed']); self.started.set()
            await self.release.wait()
            return await super().execute(**kwargs)
    backend = GateBackend(); path = tmp_path / 'bridge.sqlite3'
    service = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), backend, job_store=SQLiteBridgeJobStore(path), max_concurrent_jobs=1, max_queued_jobs=1)
    first = await service.submit(text_to_image_request('first-in-queue'))
    await asyncio.wait_for(backend.started.wait(), 1)
    pending = await service.submit(text_to_image_request('second-in-queue'))
    with pytest.raises(RuntimeError, match='BRIDGE_QUEUE_FULL'):
        await service.submit(text_to_image_request('third-in-queue'))
    assert (await service.get(pending.job_id)).status == 'queued' and len(backend.calls) == 1
    await service.cancel(pending.job_id)
    await service.close()
    recovered = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), DisabledComfyUIBackend(), job_store=SQLiteBridgeJobStore(path))
    try:
        assert (await recovered.get(first.job_id)).recovery_required
        assert (await recovered.get(pending.job_id)).status == 'cancelled'
        assert len(backend.calls) == 1
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_retry_limit_and_exact_approved_definition_drift_reject_before_dispatch():
    registry = WorkflowRegistry(MANIFEST)
    backend = DeterministicMockComfyUIBackend(delay_seconds=0, fail=True)
    service = ComfyUIBridgeService(registry, backend, max_retries=1)
    try:
        job = await service.submit(text_to_image_request('retry-limit-job'))
        assert (await wait_terminal(service, job.job_id)).status == 'failed'
        registry.get(job.workflow_id).timeout_seconds += 1
        with pytest.raises(ValueError, match='APPROVED_WORKFLOW_CHANGED'): await service.retry(job.job_id)
        assert (await service.get(job.job_id)).retry_count == 0
        registry.get(job.workflow_id).timeout_seconds -= 1
        await service.retry(job.job_id)
        assert (await wait_terminal(service, job.job_id)).status == 'failed'
        with pytest.raises(ValueError, match='BRIDGE_RETRY_LIMIT_REACHED'): await service.retry(job.job_id)
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_untrusted_backend_error_cannot_leak_provider_secret_or_private_prompt():
    class UnsafeErrorBackend(DeterministicMockComfyUIBackend):
        async def execute(self, **kwargs): raise RuntimeError('Bearer provider-secret private prompt body')
    service = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), UnsafeErrorBackend())
    try:
        job = await service.submit(text_to_image_request('safe-error-job'))
        result = await wait_terminal(service, job.job_id)
        assert result.status == 'failed'
        assert 'provider-secret' not in result.model_dump_json() and 'private prompt body' not in result.model_dump_json()
    finally:
        await service.close()


def test_store_single_owner_lease_is_released_on_close(tmp_path):
    path = tmp_path / 'bridge.sqlite3'; store = SQLiteBridgeJobStore(path)
    try:
        with pytest.raises(RuntimeError, match='BRIDGE_STORE_IN_USE'): SQLiteBridgeJobStore(path)
    finally:
        store.close()
    next_owner = SQLiteBridgeJobStore(path); assert next_owner.load() == []; next_owner.close()


@pytest.mark.asyncio
async def test_corrupt_private_request_fails_integrity_before_any_backend_execution(tmp_path):
    path = tmp_path / 'bridge.sqlite3'
    service = ComfyUIBridgeService(WorkflowRegistry(MANIFEST), DeterministicMockComfyUIBackend(delay_seconds=0), job_store=SQLiteBridgeJobStore(path))
    job = await service.submit(text_to_image_request('corrupt-job')); await wait_terminal(service, job.job_id)
    await service.close()
    store = SQLiteBridgeJobStore(path)
    try:
        with store.connection:
            store.connection.execute('UPDATE bridge_jobs SET document=? WHERE job_id=?', (b'{}', job.job_id))
        with pytest.raises(RuntimeError, match='BRIDGE_STORE_INVALID'): store.load()
    finally:
        store.close()


@pytest.mark.asyncio
async def test_http_service_auth_and_scope_guard_every_job_route(monkeypatch, tmp_path):
    app = load_bridge_app(monkeypatch, execution_enabled=True, tmp_path=tmp_path)
    auth = {'Authorization': 'Bearer explicit-fixture-service-token-32-characters', 'X-VF-Workspace-Id': 'fixture-workspace-A'}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get('/healthz')).status_code == 200
            assert (await client.get('/v1/jobs')).status_code == 401
            assert (await client.post('/v1/jobs', json=text_to_image_request().model_dump(mode='json'))).status_code == 401
            assert (await client.get('/v1/jobs', headers={'Authorization': auth['Authorization']})).status_code == 422
            sent = await client.post('/v1/jobs', headers=auth, json=text_to_image_request('authorized-http').model_dump(mode='json'))
            assert sent.status_code == 202
            job_id = sent.json()['job_id']
            other = {**auth, 'X-VF-Workspace-Id': 'fixture-workspace-B'}
            assert (await client.get('/v1/jobs', headers=other)).json() == []
            for suffix, method in [('', 'GET'), ('/events', 'GET'), ('/cancel', 'POST'), ('/retry', 'POST')]:
                assert (await client.request(method, '/v1/jobs/' + job_id + suffix, headers=other)).status_code == 404
                assert (await client.request(method, '/v1/jobs/' + job_id + suffix)).status_code == 401
            mismatched = await client.post('/v1/jobs', headers=other, json=text_to_image_request().model_dump(mode='json'))
            assert mismatched.status_code == 422
            assert (await client.get('/v1/jobs/' + job_id + '/events', headers=auth)).status_code == 200
            assert len(await app.state.bridge_service.list_jobs()) == 1
    finally:
        await app.state.bridge_service.close()


def test_reference_workflow_rejects_arbitrary_client_graph_even_with_permissive_old_schema():
    registry = WorkflowRegistry(MANIFEST)
    definition = registry.get('npd-image-to-image-v1')
    inputs = {'prompt': 'explicit fixture', 'reference_images': ['asset://fixture-A'], 'aspect_ratio': '9:16', 'seed': 1,
        'unrecognized': {'graph': {'1': {'class_type': 'UntrustedNode'}}}}
    with pytest.raises(ValueError, match='ARBITRARY_CLIENT_GRAPH_FORBIDDEN'):
        registry.validate_inputs(definition, inputs)
