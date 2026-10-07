"""Fresh-root HTTP backend rehearsal; mock GPU wires, real local media decoding.

No result is manually injected into a bridge job. The backend compiles explicit
fixture graphs, reserves writes, polls history, downloads and registers bytes.
The second process opens with an offline backend and verifies exact replay.
"""
from __future__ import annotations
import argparse
import asyncio
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'services/comfyui-bridge'), str(ROOT / 'apps/api')]
WORKSPACE = 'http-backend-explicit-fixture-workspace'
TOKEN = 'explicit-north-star-http-bridge-token-32-characters'
GPU_TOKEN = 'explicit-north-star-http-gpu-fixture-token'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path, value):
    with path.open('xb') as handle:
        handle.write(value if isinstance(value, bytes) else (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n').encode())


def fresh(path):
    from npd_comfyui_bridge.job_store import linked
    if not path.is_absolute() or path.exists() or linked(path): raise ValueError('FRESH_ABSOLUTE_UNLINKED_ROOT_REQUIRED')
    path.mkdir(parents=True, exist_ok=False)


def fixture_manifest(data):
    original = json.loads((ROOT / 'workflows/comfyui/manifest.json').read_text(encoding='utf-8'))
    folder = data / 'explicit-fixture-workflows'; folder.mkdir()
    definitions = []
    for workflow_id in ['npd-text-to-image-v1', 'npd-video-generation-v1']:
        definition = next(row for row in original['workflows'] if row['workflow_id'] == workflow_id)
        graph = {'1': {'class_type': 'ExplicitFixtureText', 'inputs': {'text': 'fixed', 'seed': 0}},
            '2': {'class_type': 'ExplicitFixtureCanvas', 'inputs': {'width': 128, 'height': 72}},
            '3': {'class_type': 'ExplicitFixtureSave', 'inputs': {'source': ['2', 0], 'duration': 0.6}}}
        graph_path = folder / definition['graph_file']; write(graph_path, {'prompt': graph})
        bindings = [{'parameter': 'prompt', 'node_id': '1', 'input_name': 'text'},
            {'parameter': 'seed', 'node_id': '1', 'input_name': 'seed'},
            {'parameter': 'aspect_ratio', 'node_id': '2', 'input_name': 'width', 'transform': 'aspect_width'},
            {'parameter': 'aspect_ratio', 'node_id': '2', 'input_name': 'height', 'transform': 'aspect_height'}]
        if workflow_id == 'npd-video-generation-v1':
            bindings.append({'parameter': 'duration_seconds', 'node_id': '3', 'input_name': 'duration'})
        definition['required_model_identifiers'] = ['explicit-fixture-no-ai-model']
        definition['execution'] = {'graph_sha256': sha(graph_path), 'approval_kind': 'explicit_fixture',
            'approval_reference': 'EXPLICIT SYNTHETIC TEST ONLY; no Owner approval',
            'allowed_node_classes': ['ExplicitFixtureText', 'ExplicitFixtureCanvas', 'ExplicitFixtureSave'],
            'bindings': bindings, 'output_nodes': ['3'], 'aspect_dimensions': {'16:9': [128, 72]}}
        definitions.append(definition)
    manifest = folder / 'manifest.json'
    write(manifest, {'manifest_version': 'explicit-http-fixture-v1', 'workflows': definitions})
    return manifest


class GPUWireFixture:
    def __init__(self, binaries): self.binaries, self.prompts, self.calls, self.lost = binaries, {}, [], False
    async def handle(self, request):
        import httpx
        assert request.headers['Authorization'] == 'Bearer ' + GPU_TOKEN
        self.calls.append({'method': request.method, 'path': request.url.path})
        if request.url.path == '/prompt':
            body = json.loads(request.content); identity, graph = body['prompt_id'], body['prompt']
            assert identity not in self.prompts
            self.prompts[identity] = graph
            if graph['1']['inputs']['seed'] == 23 and not self.lost:
                self.lost = True
                return httpx.Response(502, json={'error': 'explicit lost submission reply fixture'})
            return httpx.Response(200, json={'prompt_id': identity, 'node_errors': {}})
        if request.url.path.startswith('/api/jobs/'):
            identity = request.url.path.rsplit('/', 1)[1]
            assert identity in self.prompts
            return httpx.Response(200, json={'id': identity, 'status': 'completed'})
        if request.url.path.startswith('/history/'):
            identity = request.url.path.rsplit('/', 1)[1]; graph = self.prompts[identity]
            suffix = 'mp4' if graph['1']['inputs']['seed'] == 19 else 'png'
            return httpx.Response(200, json={identity: {'prompt': [1, identity, graph, {}, ['3']],
                'status': {'status_str': 'success', 'completed': True},
                'outputs': {'3': {'video' if suffix == 'mp4' else 'images': [{'filename': 'synthetic.' + suffix, 'type': 'output', 'subfolder': ''}]}}}})
        if request.url.path == '/view':
            suffix = request.url.params['filename'].rsplit('.', 1)[1]
            return httpx.Response(200, content=self.binaries[suffix], headers={'Content-Type': 'video/mp4' if suffix == 'mp4' else 'image/png'})
        raise AssertionError('Unexpected fixture HTTP operation')


async def snapshot(data, ffmpeg, ffprobe):
    from npd_comfyui_bridge.backend import DisabledComfyUIBackend
    from npd_comfyui_bridge.binary_artifacts import BinaryArtifactStore, FFmpegMediaValidator
    from npd_comfyui_bridge.execution_context import ExecutionContext
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    from npd_comfyui_bridge.workflows import WorkflowRegistry
    registry = WorkflowRegistry(data / 'explicit-fixture-workflows/manifest.json')
    store = SQLiteBridgeJobStore(data / 'jobs.sqlite3'); service = ComfyUIBridgeService(registry, DisabledComfyUIBackend(), job_store=store)
    artifacts = BinaryArtifactStore(data / 'artifacts', validator=FFmpegMediaValidator(ffmpeg=ffmpeg, ffprobe=ffprobe))
    try:
        result = {'jobs': [], 'backend_configured': service.backend.configured}
        for job, request in store.load():
            replay = await service.submit(request); assert replay == job and job.status == 'succeeded'
            record = store.latest_dispatch(ExecutionContext(job.workspace_id, job.job_id, job.retry_count))
            artifact = artifacts.read(workspace_id=job.workspace_id, job_id=job.job_id, artifact_id=record.artifact_id)
            assert sha(artifact.path) == record.artifact_sha256
            result['jobs'].append({'job': job.model_dump(mode='json'), 'dispatch': record.model_dump(mode='json'),
                'artifact': artifact.document, 'events': await service.events(job.job_id)})
        result['jobs'].sort(key=lambda row: row['job']['job_id'])
        return result
    finally: await service.close()


async def run(args):
    import httpx
    if args.reopen:
        expected = json.loads((args.output_root / 'offline-snapshot.json').read_bytes())
        actual = await snapshot(args.data_root, args.ffmpeg, args.ffprobe)
        assert actual == expected
        write(args.output_root / 'new-process-replay.json', {'exact_replay': True, 'backend_configured': False,
            'actual_artifacts_verified': len(actual['jobs']), 'jobs': actual['jobs']})
        print(json.dumps({'status': 'NEW_PROCESS_OFFLINE_REPLAY_PASS', 'artifacts': len(actual['jobs'])})); return
    fresh(args.data_root); fresh(args.output_root)
    manifest = fixture_manifest(args.data_root); binaries = {}
    for suffix in ['png', 'mp4']:
        path = args.data_root / ('synthetic.' + suffix)
        command = [str(args.ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=10:duration=0.6']
        command += ['-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-movflags', '+faststart'] if suffix == 'mp4' else ['-frames:v', '1']
        subprocess.run([*command, str(path)], check=True, timeout=20, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        binaries[suffix] = path.read_bytes()
    os.environ.update({'COMFYUI_BACKEND': 'disabled', 'COMFYUI_EXECUTION_ENABLED': 'false', 'APP_ENV': 'development',
        'COMFYUI_BRIDGE_TOKEN': TOKEN, 'COMFYUI_WORKFLOW_MANIFEST': str(manifest),
        'COMFYUI_JOB_STORE_PATH': str(args.data_root / 'jobs.sqlite3'), 'COMFYUI_ARTIFACT_ROOT': str(args.data_root / 'artifacts'),
        'COMFYUI_FFMPEG_PATH': str(args.ffmpeg), 'COMFYUI_FFPROBE_PATH': str(args.ffprobe)})
    from npd_comfyui_bridge.http_backend import ReviewedHTTPComfyUIBackend
    from npd_comfyui_bridge.http_transport import ComfyHTTPTransport
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    from app.media_generation_scope import media_generation_scope
    from app.media_intelligence_models import ImageGenerationInput, VideoGenerationInput
    from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider
    bridge = importlib.import_module('npd_comfyui_bridge.main')
    await bridge.service.close()
    wire = GPUWireFixture(binaries)
    store = SQLiteBridgeJobStore(args.data_root / 'jobs.sqlite3')
    transport = ComfyHTTPTransport(origin='http://127.0.0.1:8188', server_source_sha256='0' * 64,
        enabled=True, bearer_token=GPU_TOKEN, transport=httpx.MockTransport(wire.handle))
    backend = ReviewedHTTPComfyUIBackend(registry=bridge.registry, transport=transport, job_store=store,
        artifacts=bridge.app.state.binary_artifact_store, poll_seconds=.01)
    bridge.backend = backend; bridge.service = ComfyUIBridgeService(bridge.registry, backend, job_store=store)
    bridge.app.state.bridge_service = bridge.service
    observations = []
    async def observed(value): observations.append(value)
    try:
        for modality, seed in [('image', 17), ('video', 19), ('image', 23)]:
            adapter = ComfyUIBridgeGenerationProvider(bridge_url='http://explicit-asgi-fixture', modality=modality,
                workflow_id='npd-text-to-image-v1' if modality == 'image' else 'npd-video-generation-v1', enabled=True,
                service_token=TOKEN, transport=httpx.ASGITransport(app=bridge.app), timeout_seconds=10, on_job=observed)
            values = {'prompt': 'Explicit synthetic HTTP fixture; no AI generation', 'seed': seed, 'aspect_ratio': '16:9'}
            payload = ImageGenerationInput(**values) if modality == 'image' else VideoGenerationInput(**values, duration_seconds=.6)
            with media_generation_scope(workspace_id=WORKSPACE, project_id='explicit-fixture-project', job_id=f'fixture-resolution-{seed}'):
                if seed == 23:
                    try: await adapter.generate(payload)
                    except RuntimeError: pass
                    else: raise AssertionError('Lost-reply fixture unexpectedly succeeded')
                    job = next(job for job, req in store.load() if req.inputs['seed'] == seed)
                    assert job.recovery_required and len(wire.prompts) == 3
                    write(args.output_root / 'uncertain-before-retry.json', job.model_dump(mode='json'))
                    await bridge.service.retry(job.job_id)
                result = await adapter.generate(payload)
            suffix = 'mp4' if modality == 'video' else 'png'
            assert result.payload == binaries[suffix] and result.rights_status == 'unknown' and not result.production_eligible
            assert result.actual_cost_vnd is None and result.generation_provenance['binary_artifact_registered']
            write(args.output_root / f'{seed}-media.{suffix}', result.payload)
            write(args.output_root / f'{seed}-provider-provenance.json', result.generation_provenance)
            route = f'/v1/jobs/{result.provider_job_id}/artifacts/{result.source_reference.removeprefix("vf-artifact://")}'
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=bridge.app), base_url='http://test') as client:
                assert (await client.get(route)).status_code == 401
                assert (await client.get(route, headers={'Authorization': 'Bearer ' + TOKEN, 'X-VF-Workspace-Id': 'foreign'})).status_code == 404
        assert len(wire.prompts) == 3 and sum(row['path'] == '/prompt' for row in wire.calls) == 3
        assert TOKEN not in json.dumps(observations) and values['prompt'] not in json.dumps(observations)
        write(args.output_root / 'lifecycle.json', observations); write(args.output_root / 'gpu-fixture-wires.json', wire.calls)
    finally: await bridge.service.close()
    write(args.output_root / 'offline-snapshot.json', await snapshot(args.data_root, args.ffmpeg, args.ffprobe))
    sources = ['scripts/north_star_comfyui_http_backend.py', 'services/comfyui-bridge/npd_comfyui_bridge/http_backend.py',
        'services/comfyui-bridge/npd_comfyui_bridge/job_store.py', 'services/comfyui-bridge/npd_comfyui_bridge/main.py',
        'services/comfyui-bridge/npd_comfyui_bridge/service.py', 'services/comfyui-bridge/npd_comfyui_bridge/binary_artifacts.py']
    exports = {p.name: {'sha256': sha(p), 'size_bytes': p.stat().st_size} for p in args.output_root.iterdir() if p.is_file()}
    write(args.output_root / 'receipt.json', {'schema': 'north-star-comfyui-http-backend-v1', 'explicit_fixture': True,
        'source_sha256': {name: sha(ROOT / name) for name in sources}, 'exports': exports, 'real_provider_tested': False,
        'real_gpu_dispatches': 0, 'mock_gpu_prompt_writes': 3, 'actual_decoded_artifacts': 3, 'manual_result_injection': False,
        'lost_reply_reconciled_without_duplicate': True, 'rights_status': 'unknown', 'actual_cost_vnd': None,
        'owner_uat_accepted': False, 'production_deployed': False, 'data_root': str(args.data_root)})
    print(json.dumps({'status': 'HTTP_FIXTURE_LOCAL_DECODE_PASS', 'mock_writes': 3, 'actual_artifacts': 3, 'exports': len(exports)+1}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True); parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True); parser.add_argument('--ffprobe', type=Path, required=True)
    parser.add_argument('--reopen', action='store_true')
    asyncio.run(run(parser.parse_args()))
