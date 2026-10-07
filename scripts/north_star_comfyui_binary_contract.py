"""Local synthetic media -> scoped bridge storage/HTTP -> API adapter evidence.

GPU execution is explicit mock. Synthetic FFmpeg media is registered by this
fixture, not a live generative backend. Rights/Owner UAT/provider acceptance
remain incomplete. Both roots must be fresh; no old evidence is overwritten.
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def run(data_root, output_root, ffmpeg, ffprobe):
    for path in (data_root, output_root):
        if path.exists() or any(p.is_symlink() or getattr(p, 'is_junction', lambda: False)() for p in [path, *path.parents]):
            raise ValueError('FRESH_UNLINKED_ROOT_REQUIRED')
    data_root.mkdir(parents=True, exist_ok=False); output_root.mkdir(parents=True, exist_ok=False)
    manifest = ROOT / 'workflows/comfyui/manifest.json'
    token = 'explicit-north-star-binary-fixture-token-32-characters'
    os.environ.update({'COMFYUI_BACKEND': 'mock', 'COMFYUI_EXECUTION_ENABLED': 'true', 'APP_ENV': 'development',
        'COMFYUI_BRIDGE_TOKEN': token, 'COMFYUI_WORKFLOW_MANIFEST': str(manifest),
        'COMFYUI_JOB_STORE_PATH': str(data_root / 'bridge.sqlite3'), 'COMFYUI_ARTIFACT_ROOT': str(data_root / 'artifacts'),
        'COMFYUI_FFMPEG_PATH': str(ffmpeg), 'COMFYUI_FFPROBE_PATH': str(ffprobe)})
    sys.path[:0] = [str(ROOT / 'services/comfyui-bridge'), str(ROOT / 'apps/api')]
    from httpx import ASGITransport, AsyncClient
    from npd_comfyui_bridge.binary_artifacts import ArtifactProvenance, BinaryArtifactStore, FFmpegMediaValidator
    from npd_comfyui_bridge.backend import DisabledComfyUIBackend
    from npd_comfyui_bridge.job_store import SQLiteBridgeJobStore, checksum
    from npd_comfyui_bridge.models import BridgeJobCreate
    from npd_comfyui_bridge.service import ComfyUIBridgeService
    from app.media_generation_scope import media_generation_scope
    from app.media_generation_routes import generation_envelope
    from app.media_intelligence_models import ImageGenerationInput, VideoGenerationInput
    from app.media_intelligence_providers import ComfyUIBridgeGenerationProvider, _stable_token
    bridge = importlib.import_module('npd_comfyui_bridge.main')
    service, registry, store = bridge.service, bridge.registry, bridge.app.state.binary_artifact_store
    exports, requests, saved, binaries = {}, [], [], []
    def export(name, value):
        path = output_root / name
        if isinstance(value, bytes): path.write_bytes(value)
        else: path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + '\n', encoding='utf-8')
        exports[name] = {'path': str(path), 'sha256': sha(path), 'size_bytes': path.stat().st_size}
    try:
        for modality, suffix in [('image', 'png'), ('video', 'mp4')]:
            path = data_root / ('explicit-local-synthetic.' + suffix)
            arguments = [str(ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=10:duration=0.6']
            if modality == 'video':
                arguments += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=0.6',
                    '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
            else: arguments += ['-frames:v', '1']
            subprocess.run(arguments + [str(path)], check=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
            payload = (ImageGenerationInput(prompt='Explicit synthetic binary fixture; no AI generation', seed=17, aspect_ratio='16:9') if modality == 'image' else
                VideoGenerationInput(prompt='Explicit synthetic binary fixture; no AI generation', seed=17, aspect_ratio='16:9', duration_seconds=0.6))
            workspace_id, project_id, resolution_id = 'binary-fixture-workspace', 'binary-fixture-project', 'binary-resolution-' + modality
            adapter = ComfyUIBridgeGenerationProvider(bridge_url='http://explicit-asgi-fixture', modality=modality,
                workflow_id='npd-text-to-image-v1' if modality == 'image' else 'npd-video-generation-v1', enabled=True,
                service_token=token, transport=ASGITransport(app=bridge.app))
            workflow_id, _, inputs = generation_envelope(modality, payload, adapter.workflow_routes)
            request = BridgeJobCreate(workspace_id=workspace_id, workflow_id=workflow_id, inputs=inputs,
                client_request_id=_stable_token(workspace_id, project_id, resolution_id, payload.model_dump_json(), workflow_id))
            requests.append(request)
            queued = await service.submit(request)
            for _ in range(200):
                job = await service.get(queued.job_id)
                if job.status == 'succeeded': break
                await asyncio.sleep(0.01)
            else: raise RuntimeError('MOCK_JOB_DID_NOT_COMPLETE')
            definition = registry.get(workflow_id)
            started = time.monotonic()
            provenance = ArtifactProvenance(model='explicit-local-synthetic-no-gpu', workflow_id=workflow_id,
                workflow_version=job.workflow_version, graph_sha256=sha(manifest.parent / definition.graph_file),
                server_source_sha256='0' * 64, inputs_sha256=checksum(inputs), prompt_sha256=hashlib.sha256(payload.prompt.encode()).hexdigest(),
                seed=17, remote_prompt_id='024458d5-8e06-4450-b6a0-a944e8b76760', adapter_elapsed_seconds=time.monotonic() - started)
            registered = await store.register(workspace_id=workspace_id, job_id=job.job_id, content=path.read_bytes(),
                mime_type='image/png' if modality == 'image' else 'video/mp4', provenance=provenance, fixture=True)
            result = {'artifact_reference': 'vf-artifact://' + registered.document['artifact_id'],
                'checksum_sha256': registered.document['checksum_sha256'], 'workflow_id': workflow_id,
                'workflow_version': job.workflow_version, 'fixture': True}
            registry.validate_output(definition, result)
            # Only this isolated fixture job binds its actual synthetic media.
            service._set_job(job.model_copy(update={'result': result, 'result_metadata_sha256': checksum(result)}))
            with media_generation_scope(workspace_id=workspace_id, project_id=project_id, job_id=resolution_id):
                materialized = await adapter.generate(payload)
            assert materialized.payload == path.read_bytes() and materialized.generation_provenance['binary_artifact_registered']
            assert materialized.rights_status == 'unknown' and not materialized.production_eligible and materialized.actual_cost_vnd is None
            route = f'/v1/jobs/{job.job_id}/artifacts/{registered.document["artifact_id"]}'
            async with AsyncClient(transport=ASGITransport(app=bridge.app), base_url='http://explicit-asgi-fixture') as client:
                assert (await client.get(route)).status_code == 401
                assert (await client.get(route, headers={'Authorization': 'Bearer ' + token, 'X-VF-Workspace-Id': 'foreign'})).status_code == 404
            current = await service.get(job.job_id)
            saved.append(current.model_dump(mode='json')); binaries.append(registered.document)
            export(modality + '.' + suffix, materialized.payload)
            export(modality + '-artifact.json', registered.document)
            export(modality + '-api-provenance.json', materialized.generation_provenance)
            export(modality + '-job.json', current.model_dump(mode='json'))
            audit = await service.events(job.job_id)
            assert token not in json.dumps(audit) and payload.prompt not in json.dumps(audit)
            export(modality + '-events.json', audit)
            export(modality + '-decode-timing.json', {'measured_registration_adapter_seconds': time.monotonic() - started,
                'gpu_execution_time_seconds': None, 'not_ai_generation': True})
    finally:
        await service.close()
    offline = ComfyUIBridgeService(registry, DisabledComfyUIBackend(), job_store=SQLiteBridgeJobStore(data_root / 'bridge.sqlite3'))
    restarted_store = BinaryArtifactStore(data_root / 'artifacts', validator=FFmpegMediaValidator(ffmpeg=ffmpeg, ffprobe=ffprobe))
    try:
        for request, prior, document in zip(requests, saved, binaries):
            replay = await offline.submit(request)
            assert replay.model_dump(mode='json') == prior
            registered = restarted_store.read(workspace_id=document['workspace_id'], job_id=document['job_id'], artifact_id=document['artifact_id'])
            assert registered.document == document and sha(registered.path) == document['checksum_sha256']
        export('offline-replay.json', {'exact_terminal_jobs_and_binary_documents_replayed': True,
            'backend_configured': False, 'jobs': saved, 'actual_binary_count': len(binaries)})
    finally:
        await offline.close()
    source = ['scripts/north_star_comfyui_binary_contract.py', 'services/comfyui-bridge/npd_comfyui_bridge/binary_artifacts.py',
        'services/comfyui-bridge/npd_comfyui_bridge/main.py', 'apps/api/app/comfyui_binary_result.py', 'apps/api/app/media_intelligence_providers.py']
    export('contract-receipt.json', {'schema': 'north-star-comfyui-binary-contract-v1', 'explicit_fixture': True,
        'executed_source_sha256': {p: sha(ROOT / p) for p in source}, 'media_creator': 'FFmpeg synthetic fixture; no AI provider',
        'bridge_backend': 'deterministic mock plus explicit isolated fixture registration', 'transport': 'in-process ASGI',
        'real_provider_tested': False, 'external_provider_calls': 0, 'gpu_dispatches': 0, 'actual_binary_artifacts': len(binaries),
        'full_decode_passed': True, 'qc_passed': False, 'rights_status': 'unknown', 'production_eligible': False,
        'owner_uat_accepted': False, 'production_deployed': False, 'store_sha256': sha(data_root / 'bridge.sqlite3'),
        'http_auth_and_workspace_guards_passed': True, 'exact_offline_replay_passed': True, 'exports': exports})
    print(json.dumps({'status': 'LOCAL_SYNTHETIC_BINARY_CONTRACT_PASS', 'exports': len(exports), 'output_root': str(output_root),
        'gpu_dispatches': 0, 'real_provider_tested': False, 'qc_passed': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    parser.add_argument('--ffmpeg', type=Path, required=True)
    parser.add_argument('--ffprobe', type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.data_root, args.output_root, args.ffmpeg, args.ffprobe))
