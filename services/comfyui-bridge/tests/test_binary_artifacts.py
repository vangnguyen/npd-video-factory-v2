"""Actual synthetic local decode and immutable registration; no AI provider."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest
from pydantic import ValidationError
from npd_comfyui_bridge.binary_artifacts import ArtifactError, ArtifactProvenance, BinaryArtifactStore, FFmpegMediaValidator, digest


def provenance(**changes):
    return ArtifactProvenance(model='explicit-local-fixture-model', workflow_id='explicit-local-fixture-v1',
        workflow_version='1.0', graph_sha256='a' * 64, server_source_sha256='b' * 64,
        inputs_sha256='c' * 64, prompt_sha256='d' * 64, seed=17,
        remote_prompt_id='024458d5-8e06-4450-b6a0-a944e8b76760', adapter_elapsed_seconds=0,
        **changes)


@pytest.fixture
def tools():
    ffmpeg, ffprobe = os.getenv('VFNS_MEDIA_FFMPEG'), os.getenv('VFNS_MEDIA_FFPROBE')
    if not ffmpeg or not ffprobe:
        pytest.skip('Explicit isolated FFmpeg tools not configured; media acceptance unverified')
    validator = FFmpegMediaValidator(ffmpeg=ffmpeg, ffprobe=ffprobe)
    assert validator.configured
    return validator


@pytest.fixture
def media(tmp_path, tools):
    results = {}
    for suffix in ['png', 'jpg', 'mp4']:
        path = tmp_path / ('explicit-synthetic.' + suffix)
        arguments = [str(tools.ffmpeg), '-hide_banner', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=128x72:rate=10:duration=0.6']
        if suffix == 'mp4':
            arguments += ['-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=0.6',
                '-map', '0:v', '-map', '1:a', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-movflags', '+faststart']
        else:
            arguments += ['-frames:v', '1']
        subprocess.run(arguments + [str(path)], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=20)
        results[suffix] = path.read_bytes()
    return results


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix,mime', [('png', 'image/png'), ('jpg', 'image/jpeg'), ('mp4', 'video/mp4')])
async def test_actual_synthetic_decode_register_restart_replay_and_workspace_isolation(tmp_path, media, tools, suffix, mime):
    root = tmp_path / 'store'
    store = BinaryArtifactStore(root, validator=tools)
    job = 'cui_local_fixture'
    artifact = await store.register(workspace_id='workspace-A', job_id=job, content=media[suffix], mime_type=mime, provenance=provenance(), fixture=True)
    original = artifact.path.read_bytes()
    document = artifact.document
    assert original == media[suffix] and document['checksum_sha256'] == hashlib.sha256(original).hexdigest()
    assert document['media']['full_decode_passed'] and not document['media']['qc_passed']
    assert document['media']['width'] == 128 and document['media']['height'] == 72
    assert document['rights_status'] == 'unknown' and not document['production_eligible'] and document['fixture']
    assert document['provenance']['actual_cost_vnd'] is None and document['provenance']['estimated_cost_vnd'] is None
    if suffix == 'mp4':
        assert document['media']['decoded_video_frames'] == 6 and document['media']['audio_streams'] == 1
        assert document['media']['fps'] == 10 and 0.59 <= document['media']['duration_seconds'] <= 0.7
    else:
        assert document['media']['decoded_video_frames'] == 1 and document['media']['duration_seconds'] is None
    restarted = BinaryArtifactStore(root, validator=tools)
    assert restarted.read(workspace_id='workspace-A', job_id=job, artifact_id=document['artifact_id']).document == document
    replay = await restarted.register(workspace_id='workspace-A', job_id=job, content=original, mime_type=mime, provenance=provenance(), fixture=True)
    assert replay.document == document and replay.path.read_bytes() == original
    with pytest.raises(ArtifactError, match='NOT_FOUND'):
        restarted.read(workspace_id='workspace-B', job_id=job, artifact_id=document['artifact_id'])
    second = await restarted.register(workspace_id='workspace-B', job_id=job, content=original, mime_type=mime, provenance=provenance(), fixture=True)
    assert second.path != artifact.path and second.document['artifact_id'] != document['artifact_id']


@pytest.mark.asyncio
async def test_full_decode_rejects_header_only_and_mislabeled_media_and_cleans_owned_temporary_files(tmp_path, tools, media):
    root = tmp_path / 'store'
    store = BinaryArtifactStore(root, validator=tools)
    for content, mime in [(b'\x89PNG\r\n\x1a\nheader-only', 'image/png'), (media['mp4'], 'image/png')]:
        with pytest.raises(ArtifactError):
            await store.register(workspace_id='workspace-A', job_id='cui_bad_fixture', content=content, mime_type=mime, provenance=provenance(), fixture=True)
    assert not list(root.rglob('media.*')) and not list(root.rglob('.partial-*'))


@pytest.mark.asyncio
async def test_media_and_manifest_tampering_reject_and_existing_objects_are_not_replaced(tmp_path, tools, media):
    store = BinaryArtifactStore(tmp_path / 'store', validator=tools)
    kwargs = dict(workspace_id='workspace-A', job_id='cui_integrity_fixture', content=media['png'], mime_type='image/png', provenance=provenance(), fixture=True)
    artifact = await store.register(**kwargs)
    with pytest.raises(ArtifactError, match='REPLAY_CONFLICT'):
        await store.register(**{**kwargs, 'fixture': False})
    assert artifact.path.read_bytes() == media['png']
    artifact.path.write_bytes(b'corrupt-owned-test-fixture')
    with pytest.raises(ArtifactError, match='INTEGRITY_INVALID'):
        store.read(workspace_id=kwargs['workspace_id'], job_id=kwargs['job_id'], artifact_id=artifact.document['artifact_id'])
    with pytest.raises(ArtifactError, match='INTEGRITY_INVALID'):
        await store.register(**kwargs)
    assert artifact.path.read_bytes() == b'corrupt-owned-test-fixture'


@pytest.mark.asyncio
async def test_unconfigured_decoder_never_certifies_header_bytes(tmp_path):
    store = BinaryArtifactStore(tmp_path / 'store', validator=FFmpegMediaValidator())
    with pytest.raises(ArtifactError, match='NOT_CONFIGURED'):
        await store.register(workspace_id='workspace-A', job_id='cui_fixture', content=b'\x89PNG\r\n\x1a\nfixture',
            mime_type='image/png', provenance=provenance(), fixture=True)
    assert not list((tmp_path / 'store').rglob('media.*'))


@pytest.mark.asyncio
async def test_scope_and_provenance_reject_paths_or_untyped_private_payloads(tmp_path):
    store = BinaryArtifactStore(tmp_path / 'store', validator=FFmpegMediaValidator())
    with pytest.raises(ArtifactError, match='SCOPE_INVALID'):
        store._job_root('workspace-A', '../foreign')
    with pytest.raises(ArtifactError, match='PROVENANCE_INVALID'):
        await store.register(workspace_id='workspace-A', job_id='cui_fixture', content=b'private', mime_type='image/png',
            provenance={'prompt': 'private content', 'api_key': 'private secret'}, fixture=True)
    with pytest.raises(ValidationError):
        ArtifactProvenance(**{**provenance().model_dump(), 'api_key': 'forbidden'})


def test_linked_artifact_root_rejects_without_reading_outside_files(tmp_path):
    outside = tmp_path / 'outside'; outside.mkdir()
    linked = tmp_path / 'linked'
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError:
        if sys.platform != 'win32':
            raise
        environment = {**os.environ, 'VFNS_JUNCTION_TEST_PATH': str(linked), 'VFNS_JUNCTION_TEST_TARGET': str(outside)}
        subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
            'New-Item -ItemType Junction -Path $env:VFNS_JUNCTION_TEST_PATH -Target $env:VFNS_JUNCTION_TEST_TARGET | Out-Null'],
            env=environment, check=True, timeout=20, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    with pytest.raises(ArtifactError, match='PATH_INVALID'): BinaryArtifactStore(linked, validator=FFmpegMediaValidator())


@pytest.mark.asyncio
async def test_actual_binary_http_requires_auth_workspace_saved_result_and_workflow_binding(monkeypatch, tmp_path, media, tools):
    from httpx import ASGITransport, AsyncClient
    from test_bridge import load_bridge_app, text_to_image_request, wait_terminal
    from npd_comfyui_bridge.job_store import checksum
    app = load_bridge_app(monkeypatch, execution_enabled=True, tmp_path=tmp_path)
    store = BinaryArtifactStore(tmp_path / 'http-artifacts', validator=tools)
    app.state.binary_artifact_store = store
    service = app.state.bridge_service
    request = text_to_image_request('explicit-binary-http-fixture')
    try:
        queued = await service.submit(request)
        job = await wait_terminal(service, queued.job_id)
        details = provenance().model_copy(update={'workflow_id': job.workflow_id, 'workflow_version': job.workflow_version})
        registered = await store.register(workspace_id=job.workspace_id, job_id=job.job_id,
            content=media['png'], mime_type='image/png', provenance=details, fixture=True)
        artifact_id = registered.document['artifact_id']
        reference = 'vf-artifact://' + artifact_id
        # Explicit fixture replaces only its own synthetic job result; no GPU.
        result = {'artifact_reference': reference, 'checksum_sha256': registered.document['checksum_sha256'],
            'workflow_id': job.workflow_id, 'workflow_version': job.workflow_version, 'fixture': True}
        service._set_job(job.model_copy(update={'result': result, 'result_metadata_sha256': checksum(result)}))
        auth = {'Authorization': 'Bearer explicit-fixture-service-token-32-characters', 'X-VF-Workspace-Id': job.workspace_id}
        route = f'/v1/jobs/{job.job_id}/artifacts/{artifact_id}'
        async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
            assert (await client.get(route)).status_code == 401
            assert (await client.get(route, headers={**auth, 'X-VF-Workspace-Id': 'foreign-workspace'})).status_code == 404
            assert (await client.get(route[:-64] + 'f' * 64, headers=auth)).status_code == 404
            metadata = await client.get(route + '/metadata', headers=auth)
            assert metadata.status_code == 200 and metadata.json() == registered.document
            response = await client.get(route, headers=auth)
            assert response.status_code == 200 and response.content == media['png']
            assert response.headers['X-Content-Type-Options'] == 'nosniff' and 'no-store' in response.headers['Cache-Control']
            assert response.headers['X-VF-Content-SHA256'] == hashlib.sha256(response.content).hexdigest()
            # Scope-bound artifacts cannot be served merely by knowing their ID.
            broken = {**result, 'checksum_sha256': '0' * 64}
            service._set_job(job.model_copy(update={'result': broken, 'result_metadata_sha256': checksum(broken)}))
            assert (await client.get(route, headers=auth)).status_code == 404
    finally:
        await service.close()
