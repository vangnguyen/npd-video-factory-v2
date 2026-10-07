"""Actual local synthetic MP4 bytes; mocked official upload, no real publication."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess

import httpx

from app.config import Settings
from app.publishing_models import PublicationMetadata
from app.publishing_providers import ExternalPublishingNotActivated, PublishingContext, PublishingProviderRegistry
from app.publishing_wire import OfficialHTTPClient, PublishingWireError
from app.youtube_upload import UNIT, chunk_request, start_request, started_session, status_request, upload_progress


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


async def run(root, output, ffmpeg):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    source = root / 'explicit-synthetic-source.mp4'
    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=size=432x768:rate=30:duration=2',
        '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000:duration=2', '-c:v', 'libx264', '-preset', 'ultrafast',
        '-crf', '28', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-shortest', '-movflags', '+faststart', str(source)],
        check=True, timeout=60, capture_output=True)
    probe = json.loads(subprocess.check_output([str(ffmpeg.with_name('ffprobe.exe')), '-v', 'error',
        '-show_format', '-show_streams', '-of', 'json', str(source)], timeout=20))
    subprocess.run([str(ffmpeg), '-nostdin', '-v', 'error', '-xerror', '-i', str(source), '-f', 'null', '-'],
        check=True, timeout=30, capture_output=True)
    raw = source.read_bytes(); total = len(raw)
    token = 'explicit-wire-fixture-' + 'x' * 48
    uri = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=PRIVATE_FIXTURE_SESSION'
    metadata = PublicationMetadata(title='Ví dụ wire · không đăng thật', description='Nguồn MP4 tổng hợp do FFmpeg tạo; chưa phải video được Owner duyệt.', privacy='private')
    requests, received = [], bytearray()
    initialized, completed, lost_final_response = False, False, False
    def handler(request):
        nonlocal initialized, completed, lost_final_response
        requests.append({'method': request.method, 'path': request.url.path,
            'query_keys': sorted(set(request.url.params.keys())), 'body_bytes': len(request.content),
            'body_sha256': hashlib.sha256(request.content).hexdigest(),
            'content_range': request.headers.get('content-range'),
            'bearer_header_present': 'authorization' in request.headers})
        if request.method == 'POST':
            assert not initialized; initialized = True
            assert json.loads(request.content)['status']['privacyStatus'] == 'private'
            return httpx.Response(200, headers={'Location': uri})
        assert initialized and str(request.url) == uri and request.method == 'PUT'
        if request.headers['content-range'] == f'bytes */{total}':
            assert completed and lost_final_response
            return httpx.Response(201, json={'id': 'AbcD_12-345'})
        assert not completed
        start = len(received); end = start + len(request.content) - 1
        assert request.headers['content-range'] == f'bytes {start}-{end}/{total}'
        received.extend(request.content)
        if len(received) == total:
            completed = True; lost_final_response = True
            raise httpx.ReadTimeout('PRIVATE PROVIDER DETAIL ' + token + uri, request=request)
        return httpx.Response(308, headers={'Range': f'bytes=0-{len(received)-1}'})
    client = OfficialHTTPClient('youtube', transport=httpx.MockTransport(handler))
    session = started_session(await client.request(start_request(metadata, total, token, category_id='27',
        made_for_kids=False, contains_synthetic_media=True)), total)
    offset = 0
    while offset < total:
        content = raw[offset:offset + UNIT]
        try:
            progress = upload_progress(await client.request(chunk_request(session, offset, content, token, chunk_size=UNIT)), session)
            assert progress.status == 'uploading'; offset = progress.acknowledged_bytes
        except PublishingWireError as error:
            assert error.code == 'PUBLISHING_NETWORK_OUTCOME_UNKNOWN' and error.uncertain and completed
            break
    progress = upload_progress(await client.request(status_request(session, token)), session)
    assert progress.status == 'uploaded' and progress.remote_video_id == 'AbcD_12-345'
    assert bytes(received) == raw and sum(r['method'] == 'POST' for r in requests) == 1
    assert requests[-1]['content_range'] == f'bytes */{total}' and requests[-1]['body_bytes'] == 0
    settings = Settings(); registry = PublishingProviderRegistry(settings)
    assert not settings.publish_enabled and not registry.for_live('youtube').validate().supports_live_publish
    try:
        await registry.for_live('youtube').publish(PublishingContext(platform='youtube', project_id='prj_fixture',
            final_render_id='rnd_fixture', output_asset_id='ast_fixture', request_fingerprint='a' * 64, metadata=metadata))
    except ExternalPublishingNotActivated:
        pass
    else:
        raise AssertionError('Application publishing factory must remain disabled')
    write(output / 'source.json', {'path': str(source), 'sha256': sha(source), 'bytes': total,
        'source_type': 'explicit_synthetic_local_fixture', 'full_av_decode_passed': True, 'owner_approved': False,
        'streams': [{k: stream[k] for k in ('codec_type', 'codec_name', 'width', 'height', 'sample_rate', 'duration') if k in stream} for stream in probe['streams']]})
    write(output / 'mock-wire-requests.json', requests)
    write(output / 'reconciliation.json', {'mock': True, 'lost_final_response': True, 'one_init_post': True,
        'source_bytes_equal_received': True, 'query_existing_session_after_uncertain_upload': True,
        'remote_video_id_is_fixture': True, 'actual_external_requests': 0, 'real_post_created': False})
    write(output / 'disabled-application.json', {'publish_enabled': settings.publish_enabled,
        'external_execution_enabled': settings.publish_external_execution_enabled, 'owner_gate_enabled': settings.publish_owner_gate_enabled,
        'official_provider_state': registry.official_status('youtube').model_dump(mode='json'),
        'default_transport_live_calls': False, 'network_secrets_read': 0})
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert token not in serialized and uri not in serialized and 'PRIVATE_FIXTURE_SESSION' not in serialized
    write(output / 'receipt.json', {'schema': 'north-star-publishing-wire-contract-v1', 'status': 'PASS',
        'local_real_media_decode': True, 'mock_transport_provider_only': True, 'real_provider_acceptance': False,
        'durable_dispatch_integration_verified': False, 'native_publishing_ui_complete': False,
        'owner_uat_accepted': False, 'production_deployed': False, 'requests': len(requests),
        'source_sha256': sha(source), 'exports_sha256': {path.name: sha(path) for path in output.glob('*.json')}})
    print(json.dumps({'status': 'PASS', 'exports': 5, 'mock_wire_requests': len(requests), 'source_bytes': total, 'actual_provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); parser.add_argument('--ffmpeg', type=Path, required=True)
    args = parser.parse_args(); asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve(), args.ffmpeg.resolve()))
