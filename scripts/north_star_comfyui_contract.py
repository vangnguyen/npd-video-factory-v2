"""Retain CPU/mock bridge restart evidence in fresh isolated directories.

No GPU, external HTTP, production credential or media-generation claim.
"""
from __future__ import annotations
import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'services' / 'comfyui-bridge'))


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(data_root, output_root):
    from httpx import ASGITransport, AsyncClient
    for path in (data_root, output_root):
        if path.exists() or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in [path, *path.parents]):
            raise ValueError('FRESH_ISOLATED_EVIDENCE_DIRECTORY_REQUIRED')
    data_root.mkdir(parents=True); output_root.mkdir(parents=True)
    store_path = data_root / 'bridge.sqlite3'
    os.environ.update({'APP_ENV': 'development', 'COMFYUI_BACKEND': 'mock', 'COMFYUI_EXECUTION_ENABLED': 'true',
        'COMFYUI_WORKFLOW_MANIFEST': str(ROOT / 'workflows' / 'comfyui' / 'manifest.json'),
        'COMFYUI_BRIDGE_TOKEN': 'explicit-north-star-mock-service-token-32-characters', 'COMFYUI_JOB_STORE_PATH': str(store_path)})
    from npd_comfyui_bridge.main import app
    from npd_comfyui_bridge.backend import DisabledComfyUIBackend, DeterministicMockComfyUIBackend
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore, checksum
    from npd_comfyui_bridge.models import BridgeJobCreate, BridgeJobRead
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    from npd_comfyui_bridge.workflows import WorkflowRegistry
    registry = WorkflowRegistry(ROOT / 'workflows' / 'comfyui' / 'manifest.json')
    request = BridgeJobCreate(workspace_id='explicit-mock-workspace-A', workflow_id='npd-text-to-image-v1',
        workflow_version='1.0.0', client_request_id='north-star-comfyui-contract-001',
        inputs={'prompt': 'Explicit CPU contract fixture; no generated media', 'aspect_ratio': '9:16', 'seed': 7})
    exports = {}
    def export(name, value):
        path = output_root / name
        with path.open('x', encoding='utf-8') as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')
        exports[name] = sha(path)
    export('request.json', request.model_dump(mode='json'))
    headers = {'Authorization': 'Bearer explicit-north-star-mock-service-token-32-characters',
        'X-VF-Workspace-Id': request.workspace_id}
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://explicit-asgi-mock') as client:
            unauthorized = await client.get('/v1/jobs')
            response = await client.post('/v1/jobs', headers=headers, json=request.model_dump(mode='json'))
            assert unauthorized.status_code == 401 and response.status_code == 202
            job_id = response.json()['job_id']
            replay = await client.post('/v1/jobs', headers=headers, json=request.model_dump(mode='json'))
            assert replay.json()['job_id'] == job_id
            for _ in range(200):
                result = await client.get('/v1/jobs/' + job_id, headers=headers)
                if result.json()['status'] == 'succeeded': break
                await asyncio.sleep(0.01)
            else: raise RuntimeError('MOCK_CONTRACT_DID_NOT_COMPLETE')
            job = result.json()
            assert job['result']['fixture'] and job['result_metadata_sha256'] == checksum(job['result'])
            foreign = await client.get('/v1/jobs/' + job_id, headers={**headers, 'X-VF-Workspace-Id': 'explicit-mock-workspace-B'})
            assert foreign.status_code == 404
            audit = (await client.get('/v1/jobs/' + job_id + '/events', headers=headers)).json()
            assert 'prompt' not in json.dumps(audit) and 'service-token' not in json.dumps(audit)
            export('job.json', job); export('job-events.json', audit)
            export('http-security.json', {'unauthorized_status': unauthorized.status_code, 'foreign_workspace_status': foreign.status_code,
                'idempotent_replay_same_job': True, 'transport': 'in-process ASGI; no external network'})
    finally:
        await app.state.bridge_service.close()
    offline = ComfyUIBridgeService(registry, DisabledComfyUIBackend(), job_store=SQLiteBridgeJobStore(store_path))
    try:
        prior = await offline.submit(request)
        assert prior.model_dump(mode='json') == job
        assert await offline.events(job_id) == audit
        export('offline-replay.json', prior.model_dump(mode='json'))
        interrupted_request = request.model_copy(update={'client_request_id': 'north-star-explicit-interruption-fixture'})
        now = datetime.now(timezone.utc)
        interrupted = BridgeJobRead(workspace_id=request.workspace_id, job_id='cui_' + uuid.uuid4().hex[:24],
            workflow_id=request.workflow_id, workflow_version='1.0.0', client_request_id=interrupted_request.client_request_id,
            status='running', progress=45, retry_count=0, result=None, error_code=None, failure_reason=None,
            created_at=now, updated_at=now, definition_sha256=registry.fingerprint(registry.get(request.workflow_id)))
        # Explicit interrupted-state fixture; not a claim of a remote dispatch.
        offline.job_store.save(interrupted, interrupted_request)
    finally:
        await offline.close()
    class CountingMock(DeterministicMockComfyUIBackend):
        def __init__(self): super().__init__(delay_seconds=0); self.calls = 0
        async def execute(self, **kwargs): self.calls += 1; return await super().execute(**kwargs)
    mock = CountingMock()
    recovered = ComfyUIBridgeService(registry, mock, job_store=SQLiteBridgeJobStore(store_path))
    try:
        current = await recovered.get(interrupted.job_id)
        assert current.recovery_required and current.error_code == 'RECOVERY_REQUIRED' and mock.calls == 0
        export('interruption-recovery.json', current.model_dump(mode='json'))
        await recovered.retry(interrupted.job_id)
        for _ in range(200):
            retried = await recovered.get(interrupted.job_id)
            if retried.status == 'succeeded': break
            await asyncio.sleep(0.01)
        else: raise RuntimeError('EXPLICIT_MOCK_RETRY_DID_NOT_COMPLETE')
        assert mock.calls == 1 and retried.retry_count == 1 and not retried.recovery_required
        export('retried-job.json', retried.model_dump(mode='json'))
        export('retried-events.json', await recovered.events(interrupted.job_id))
    finally:
        await recovered.close()
    receipt = {'schema': 'north-star-comfyui-durable-evidence-v1', 'explicit_fixture': True,
        'http_transport': 'in-process ASGI', 'backend': 'deterministic mock', 'real_provider_tested': False,
        'external_provider_calls': 0, 'gpu_dispatches': 0, 'binary_media_created': False, 'binary_artifact_registered': False,
        'production_eligible': False, 'owner_uat_accepted': False, 'production_deployed': False,
        'store_path': str(store_path), 'store_sha256': sha(store_path), 'output_root': str(output_root),
        'terminal_result_replayed_offline': True, 'interruption_required_explicit_retry': True,
        'workspaces_isolated': True, 'audit_omits_private_inputs': True, 'exports': exports}
    export('contract-receipt.json', receipt)
    print(json.dumps({'status': 'CPU_MOCK_CONTRACT_PASS', 'exports': len(exports), 'output_root': str(output_root),
        'real_provider_tested': False, 'gpu_dispatches': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.data_root, args.output_root))
