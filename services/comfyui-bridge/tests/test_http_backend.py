"""HTTP wires are explicit fixtures; actual media decoding is local FFmpeg."""
import asyncio
import hashlib
import json
import time
from pathlib import Path

import httpx
import pytest

from npd_comfyui_bridge.backend import DisabledComfyUIBackend
from npd_comfyui_bridge.binary_artifacts import BinaryArtifactStore, digest
from npd_comfyui_bridge.execution_context import ExecutionContext
from npd_comfyui_bridge.http_backend import ReviewedHTTPComfyUIBackend
from npd_comfyui_bridge.http_transport import ComfyHTTPTransport
from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
from npd_comfyui_bridge.models import BridgeJobCreate
from npd_comfyui_bridge.runtime import select_backend
from npd_comfyui_bridge.service import ComfyUIBridgeService
from npd_comfyui_bridge.workflows import WorkflowRegistry
from test_binary_artifacts import tools, media
from test_graph_compiler import registry_fixture, inputs
from test_bridge import MANIFEST


async def terminal(service, job_id):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = await service.get(job_id)
        if job.status in {'succeeded', 'failed', 'cancelled', 'timed_out'}:
            return job
        await asyncio.sleep(.01)
    raise AssertionError('HTTP fixture did not reach a terminal state')


class WireFixture:
    def __init__(self, content, *, suffix='png', fault=None):
        self.content, self.suffix, self.fault = content, suffix, fault
        self.calls, self.prompts = [], {}
        self.accepted, self.release = asyncio.Event(), asyncio.Event()
        self.hold, self.after_cancel = False, 'cancelled'
        self.cancel_status = 200
        self.reservation_check = None

    async def handle(self, request):
        self.calls.append((request.method, request.url.path))
        assert request.headers['Authorization'] == 'Bearer explicit-fixture-gpu-token'
        path = request.url.path
        if request.method == 'POST' and path == '/prompt':
            body = json.loads(request.content); prompt_id = body['prompt_id']
            if self.reservation_check:
                self.reservation_check(prompt_id, body['prompt'])
            if self.fault == 'reject_once' and len(self.prompts) == 0:
                self.fault = None
                return httpx.Response(400, json={'private': 'provider-secret prompt content'})
            self.prompts[prompt_id] = body['prompt']; self.accepted.set()
            if self.fault == 'lost_reply':
                self.fault = None
                return httpx.Response(502, json={'private': 'provider-secret prompt content'})
            if self.fault == 'interrupted_reply':
                await self.release.wait()
            return httpx.Response(200, json={'prompt_id': prompt_id, 'node_errors': {}})
        prompt_id = path.split('/')[3] if path.startswith('/api/jobs/') else None
        if request.method == 'POST' and path.endswith('/cancel'):
            assert prompt_id in self.prompts
            self.hold = False
            return httpx.Response(self.cancel_status, json={'cancelled': True} if self.cancel_status == 200 else {'secret': 'never expose'})
        if path.startswith('/api/jobs/'):
            if self.fault == 'missing_job':
                return httpx.Response(404, json={})
            status = 'in_progress' if self.hold else (self.after_cancel if any(p == f'/api/jobs/{prompt_id}/cancel' for _, p in self.calls) else 'completed')
            if self.fault == 'remote_failed_once':
                status = 'failed'; self.fault = None
            return httpx.Response(200, json={'id': 'foreign-id' if self.fault == 'foreign_job' else prompt_id, 'status': status})
        if path.startswith('/history/'):
            identity = path.rsplit('/', 1)[1]
            graph = self.prompts[identity]
            if self.fault == 'foreign_graph':
                graph = {**graph, 'foreign': {'class_type': 'Unauthorized', 'inputs': {}}}
            item = {'filename': '../outside.png' if self.fault == 'unsafe_filename' else 'explicit-local-fixture.' + self.suffix,
                    'type': 'output', 'subfolder': ''}
            items = [item, item] if self.fault == 'multiple_outputs' else [item]
            history = {'prompt': [1, 'foreign-id' if self.fault == 'foreign_history' else identity, graph, {}, ['3']],
                'status': {'status_str': 'success', 'completed': True},
                'outputs': {'foreign' if self.fault == 'foreign_node' else '3': {'images' if self.suffix != 'mp4' else 'video': items}}}
            return httpx.Response(200, json={identity: history})
        if path == '/view':
            assert request.url.params['type'] == 'output'
            content = b'\x89PNG\r\n\x1a\nheader-only' if self.fault == 'header_only' else self.content
            mime = {'png': 'image/png', 'jpg': 'image/jpeg', 'mp4': 'video/mp4'}[self.suffix]
            return httpx.Response(200, content=content, headers={'Content-Type': mime})
        raise AssertionError('Unexpected HTTP fixture operation')


def build(tmp_path, tools, wire, *, registry=None, path=None, origin='http://127.0.0.1:8188'):
    if registry is None:
        registry, definition, _, _ = registry_fixture(tmp_path)
    else:
        definition = registry.manifest.workflows[0]
    store = SQLiteBridgeJobStore(path or tmp_path / 'jobs.sqlite3')
    artifacts = BinaryArtifactStore(tmp_path / 'artifacts', validator=tools)
    transport = ComfyHTTPTransport(origin=origin, server_source_sha256='a' * 64, enabled=True,
        bearer_token='explicit-fixture-gpu-token', transport=httpx.MockTransport(wire.handle))
    backend = ReviewedHTTPComfyUIBackend(registry=registry, transport=transport, job_store=store,
        artifacts=artifacts, poll_seconds=.01)
    service = ComfyUIBridgeService(registry, backend, job_store=store)
    payload = BridgeJobCreate(workspace_id='workspace-A', client_request_id='explicit-http-fixture-request',
        workflow_id=definition.workflow_id, workflow_version=definition.version, inputs=inputs())
    return service, store, artifacts, payload


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['png', 'jpg', 'mp4'])
async def test_http_execution_registers_actual_decoded_bytes_and_scoped_offline_replay(tmp_path, tools, media, suffix):
    registry, definition, _, _ = registry_fixture(tmp_path)
    if suffix == 'mp4':
        definition.capability = 'video_generation'
    wire = WireFixture(media[suffix], suffix=suffix)
    service, store, artifacts, payload = build(tmp_path, tools, wire, registry=registry)
    try:
        job = await service.submit(payload)
        def check(identity, graph):
            saved = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 0))
            assert saved.state == 'dispatching' and saved.prompt_id == identity and saved.graph_sha256 == digest(graph)
        wire.reservation_check = check
        done = await terminal(service, job.job_id)
        assert done.status == 'succeeded' and done.progress == 100
        artifact_id = done.result['artifact_reference'].removeprefix('vf-artifact://')
        registered = artifacts.read(workspace_id='workspace-A', job_id=job.job_id, artifact_id=artifact_id)
        assert registered.path.read_bytes() == media[suffix]
        assert registered.document['media']['full_decode_passed'] and registered.document['fixture']
        assert registered.document['rights_status'] == 'unknown' and registered.document['production_eligible'] is False
        assert registered.document['provenance']['actual_cost_vnd'] is None
        assert registered.document['provenance']['prompt_sha256'] == hashlib.sha256(payload.inputs['prompt'].encode()).hexdigest()
        assert len(wire.prompts) == 1
        audit = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 0)).model_dump_json()
        assert payload.inputs['prompt'] not in audit and 'gpu-token' not in audit
    finally:
        await service.close()
    reopened_store = SQLiteBridgeJobStore(tmp_path / 'jobs.sqlite3')
    offline = ComfyUIBridgeService(registry, DisabledComfyUIBackend(), job_store=reopened_store)
    try:
        replay = await offline.submit(payload)
        assert replay == done
        assert artifacts.read(workspace_id='workspace-A', job_id=job.job_id, artifact_id=artifact_id).document == registered.document
        with pytest.raises(RuntimeError, match='JOURNAL_INVALID'):
            reopened_store.latest_dispatch(ExecutionContext('workspace-B', job.job_id, 0))
    finally:
        await offline.close()


@pytest.mark.asyncio
async def test_uncertain_submission_reconciles_exact_prompt_without_a_second_write(tmp_path, tools, media):
    wire = WireFixture(media['png'], fault='lost_reply')
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); failed = await terminal(service, job.job_id)
        assert failed.recovery_required and failed.error_code == 'REMOTE_RECOVERY_REQUIRED'
        assert 'provider-secret' not in failed.model_dump_json()
        saved = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 0))
        assert saved.state == 'uncertain'
        await service.retry(job.job_id); done = await terminal(service, job.job_id)
        assert done.status == 'succeeded' and done.retry_count == 1
        assert len(wire.prompts) == 1 and sum(p == '/prompt' for _, p in wire.calls) == 1
        assert store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 1)).prompt_id == saved.prompt_id
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_restart_interrupted_dispatch_requires_explicit_reconciliation_no_auto_replay(tmp_path, tools, media):
    wire = WireFixture(media['png'], fault='interrupted_reply')
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    registry = service.registry
    job = await service.submit(payload)
    await asyncio.wait_for(wire.accepted.wait(), 1)
    await service.close()
    wire.fault = None
    recovered, store, artifacts, _ = build(tmp_path, tools, wire, registry=registry)
    try:
        state = await recovered.get(job.job_id)
        assert state.recovery_required and state.status == 'failed'
        assert len(wire.calls) == 1
        await recovered.retry(job.job_id); done = await terminal(recovered, job.job_id)
        assert done.status == 'succeeded' and len(wire.prompts) == 1
        assert sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await recovered.close()


@pytest.mark.asyncio
async def test_absent_job_after_uncertain_submission_never_authorizes_resubmission(tmp_path, tools, media):
    wire = WireFixture(media['png'], fault='lost_reply')
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); await terminal(service, job.job_id)
        wire.fault = 'missing_job'
        for _ in range(2):
            await service.retry(job.job_id); failed = await terminal(service, job.job_id)
            assert failed.recovery_required and failed.status == 'failed'
        assert sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['reject_once', 'remote_failed_once'])
async def test_explicit_retry_only_after_definitive_rejection_or_remote_terminal_failure(tmp_path, tools, media, fault):
    wire = WireFixture(media['png'], fault=fault)
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); failed = await terminal(service, job.job_id)
        assert failed.status == 'failed' and failed.recovery_required is False
        first = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 0))
        await service.retry(job.job_id); done = await terminal(service, job.job_id)
        assert done.status == 'succeeded' and sum(p == '/prompt' for _, p in wire.calls) == 2
        second = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 1))
        assert first.prompt_id != second.prompt_id
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('cancel_status,terminal_status', [(200, 'cancelled'), (502, 'cancelled'), (200, 'completed')])
async def test_targeted_cancel_remains_pending_until_bound_remote_terminal_and_preserves_success_race(tmp_path, tools, media, cancel_status, terminal_status):
    wire = WireFixture(media['png']); wire.hold = True; wire.cancel_status = cancel_status; wire.after_cancel = terminal_status
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); await asyncio.wait_for(wire.accepted.wait(), 1)
        pending = await service.cancel(job.job_id)
        assert pending.status in {'queued', 'running'} and pending.cancellation_requested and pending.error_code is None
        done = await terminal(service, job.job_id)
        assert done.status == ('succeeded' if terminal_status == 'completed' else 'cancelled')
        assert sum(p.endswith('/cancel') for _, p in wire.calls) == 1
        assert not any(p in {'/interrupt', '/queue'} for _, p in wire.calls)
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize('fault', ['foreign_job', 'foreign_history', 'foreign_graph', 'foreign_node', 'multiple_outputs', 'unsafe_filename', 'header_only'])
async def test_foreign_or_ambiguous_result_and_fake_media_fail_closed_without_replacement(tmp_path, tools, media, fault):
    wire = WireFixture(media['png'], fault=fault)
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); failed = await terminal(service, job.job_id)
        assert failed.status == 'failed' and failed.recovery_required
        assert not list(artifacts.root.rglob('artifact.json'))
        assert len(wire.prompts) == 1
        await service.retry(job.job_id); failed = await terminal(service, job.job_id)
        assert failed.status == 'failed' and sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_retargeted_origin_and_corrupt_dispatch_journal_block_before_network(tmp_path, tools, media):
    wire = WireFixture(media['png'], fault='lost_reply')
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    registry = service.registry
    job = await service.submit(payload); await terminal(service, job.job_id); await service.close()
    recovered, store, artifacts, _ = build(tmp_path, tools, wire, registry=registry, origin='http://127.0.0.1:8288')
    try:
        count = len(wire.calls)
        await recovered.retry(job.job_id); failed = await terminal(recovered, job.job_id)
        assert failed.error_code == 'REMOTE_RECOVERY_REQUIRED' and len(wire.calls) == count
        with store.connection:
            store.connection.execute('UPDATE bridge_prompt_dispatches SET document=?', (b'{}',))
        await recovered.retry(job.job_id); failed = await terminal(recovered, job.job_id)
        assert failed.status == 'failed' and failed.recovery_required and len(wire.calls) == count
    finally:
        await recovered.close()


def test_runtime_is_inert_default_disabled_and_checked_in_placeholders_are_not_configured(tmp_path, tools):
    registry = WorkflowRegistry(MANIFEST)
    store = SQLiteBridgeJobStore(tmp_path / 'jobs.sqlite3'); artifacts = BinaryArtifactStore(tmp_path / 'artifacts', validator=tools)
    try:
        assert not select_backend(environment={}, registry=registry, job_store=store, artifacts=artifacts).configured
        environment = {'COMFYUI_EXECUTION_ENABLED': 'true', 'COMFYUI_BACKEND': 'http',
            'COMFYUI_API_ORIGIN': 'http://127.0.0.1:8188', 'COMFYUI_SERVER_SOURCE_SHA256': 'a' * 64}
        backend = select_backend(environment=environment, registry=registry, job_store=store, artifacts=artifacts)
        assert isinstance(backend, ReviewedHTTPComfyUIBackend) and not backend.configured and backend.transport._client is None
        with pytest.raises(RuntimeError, match='MOCK_PRODUCTION_FORBIDDEN'):
            select_backend(environment={'COMFYUI_BACKEND': 'mock', 'APP_ENV': 'production'}, registry=registry, job_store=store, artifacts=artifacts)
        with pytest.raises(RuntimeError, match='HTTP_CONFIGURATION_INVALID'):
            select_backend(environment={**environment, 'COMFYUI_API_ORIGIN': 'http://user:secret@remote.invalid'}, registry=registry, job_store=store, artifacts=artifacts)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_remote_timeout_retains_identity_and_retry_reconciles_without_duplicate_generation(tmp_path, tools, media):
    registry, definition, _, _ = registry_fixture(tmp_path); definition.timeout_seconds = .8
    wire = WireFixture(media['png']); wire.hold = True
    service, store, artifacts, payload = build(tmp_path, tools, wire, registry=registry)
    try:
        job = await service.submit(payload); timed_out = await terminal(service, job.job_id)
        assert timed_out.status == 'timed_out' and timed_out.recovery_required and timed_out.error_code == 'TIMEOUT'
        wire.hold = False
        await service.retry(job.job_id); done = await terminal(service, job.job_id)
        assert done.status == 'succeeded' and sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_queued_cancel_never_dispatches_or_claims_remote_interruption(tmp_path, tools, media):
    wire = WireFixture(media['png']); wire.hold = True
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        first = await service.submit(payload); await asyncio.wait_for(wire.accepted.wait(), 1)
        second = await service.submit(payload.model_copy(update={'client_request_id': 'explicit-second-fixture'}))
        pending = await service.cancel(second.job_id)
        assert pending.status == 'queued' and pending.cancellation_requested
        wire.hold = False
        assert (await terminal(service, first.job_id)).status == 'succeeded'
        assert (await terminal(service, second.job_id)).status == 'cancelled'
        assert store.latest_dispatch(ExecutionContext(second.workspace_id, second.job_id, 0)) is None
        assert sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_reference_modes_require_a_trusted_stager_before_job_admission(tmp_path, tools, media):
    registry, definition, _, _ = registry_fixture(tmp_path, reference=True)
    wire = WireFixture(media['png'])
    service, store, artifacts, payload = build(tmp_path, tools, wire, registry=registry)
    try:
        payload.inputs = inputs(reference_images=['https://client.invalid/not-authorized.png'])
        with pytest.raises(ValueError, match='VERIFIED_REFERENCE_NOT_CONFIGURED'):
            await service.submit(payload)
        assert not store.load() and not wire.calls
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_actual_authenticated_bridge_serves_backend_result_to_neutral_binary_consumer(monkeypatch, tmp_path, tools, media):
    import importlib
    from app.media_generation_scope import media_generation_scope
    from app.media_intelligence_models import ImageGenerationInput
    from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
    from test_bridge import load_bridge_app
    bootstrap = tmp_path / 'bootstrap'; bootstrap.mkdir()
    app = load_bridge_app(monkeypatch, execution_enabled=False, tmp_path=bootstrap)
    await app.state.bridge_service.close()
    wire = WireFixture(media['png'])
    root = tmp_path / 'execution'; root.mkdir()
    service, store, artifacts, payload = build(root, tools, wire)
    main = importlib.import_module('npd_comfyui_bridge.main')
    monkeypatch.setattr(main, 'service', service); monkeypatch.setattr(main, 'backend', service.backend)
    monkeypatch.setattr(main, 'registry', service.registry)
    app.state.bridge_service, app.state.binary_artifact_store = service, artifacts
    observations = []
    async def observed(value): observations.append(value)
    adapter = ComfyUIBridgeGenerationProvider(bridge_url='http://test', modality='image', workflow_id=payload.workflow_id,
        enabled=True, service_token='explicit-fixture-service-token-32-characters', transport=httpx.ASGITransport(app=app),
        timeout_seconds=5, on_job=observed)
    try:
        with media_generation_scope(workspace_id='workspace-A', project_id='fixture-project-A', job_id='fixture-resolution-A'):
            result = await adapter.generate(ImageGenerationInput(prompt='Explicit scalar fixture', aspect_ratio='9:16', seed=27))
        assert result.payload == media['png'] and result.content_type == 'image/png'
        assert result.generation_provenance['binary_artifact_registered'] and result.generation_provenance['fixture']
        assert result.rights_status == 'unknown' and result.production_eligible is False and result.actual_cost_vnd is None
        assert observations[0]['phase'] == 'submitted' and observations[-1]['status'] == 'succeeded'
        job_id = result.provider_job_id; artifact_id = result.source_reference.removeprefix('vf-artifact://')
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            route = f'/v1/jobs/{job_id}/artifacts/{artifact_id}'
            assert (await client.get(route)).status_code == 401
            assert (await client.get(route, headers={'Authorization': 'Bearer explicit-fixture-service-token-32-characters',
                'X-VF-Workspace-Id': 'foreign-workspace'})).status_code == 404
        assert sum(p == '/prompt' for _, p in wire.calls) == 1
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_cancel_after_saved_reference_dispatch_reconciles_remote_instead_of_false_local_confirmation(tmp_path, tools, media):
    from npd_comfyui_bridge.execution_models import VerifiedReferenceToken
    registry, definition, _, _ = registry_fixture(tmp_path, reference=True)
    wire = WireFixture(media['png'], fault='lost_reply')
    service, store, artifacts, payload = build(tmp_path, tools, wire, registry=registry)
    token_calls = []
    async def explicitly_fake_verified_token(*, workspace_id, source_reference):
        token_calls.append(source_reference)
        return VerifiedReferenceToken(workspace_id=workspace_id, source_reference=source_reference,
            source_sha256=hashlib.sha256(media['png']).hexdigest(), uploaded_filename='explicit-fixture-token.png',
            upload_sha256=hashlib.sha256(media['png']).hexdigest(), fixture=True)
    service.backend.reference_resolver = explicitly_fake_verified_token
    payload.inputs = inputs(reference_images=['fixture://explicit-owned-reference'])
    try:
        job = await service.submit(payload); failed = await terminal(service, job.job_id)
        assert failed.recovery_required
        wire.hold = True
        await service.retry(job.job_id)
        pending = await service.cancel(job.job_id)
        assert pending.status == 'queued' and pending.cancellation_requested
        done = await terminal(service, job.job_id)
        assert done.status == 'cancelled' and sum(p.endswith('/cancel') for _, p in wire.calls) == 1
        assert sum(p == '/prompt' for _, p in wire.calls) == 1 and len(token_calls) == 2
    finally:
        await service.close()


@pytest.mark.asyncio
async def test_confirmed_remote_cancel_allows_only_an_explicit_new_attempt(tmp_path, tools, media):
    wire = WireFixture(media['png']); wire.hold = True
    service, store, artifacts, payload = build(tmp_path, tools, wire)
    try:
        job = await service.submit(payload); await asyncio.wait_for(wire.accepted.wait(), 1)
        await service.cancel(job.job_id); await service.cancel(job.job_id)
        done = await terminal(service, job.job_id)
        assert done.status == 'cancelled' and sum(p.endswith('/cancel') for _, p in wire.calls) == 1
        prior = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 0))
        await service.retry(job.job_id); done = await terminal(service, job.job_id)
        assert done.status == 'succeeded' and sum(p == '/prompt' for _, p in wire.calls) == 2
        current = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, 1))
        assert current.prompt_id != prior.prompt_id
    finally:
        await service.close()
