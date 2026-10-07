"""Actual synthetic bytes via official Meta MockTransport; no provider acceptance."""
import argparse, asyncio, hashlib, json
from pathlib import Path
import sys
from urllib.parse import parse_qs

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.meta_publishing_protocol import (GraphTarget, confirmed_success, created_id, fb_create_request,
    fb_created_session, fb_finish_request, fb_observation, fb_status_request, fb_upload_request,
    ig_container_request, ig_container_observation, ig_create_request, ig_publish_request)
from app.publishing_models import PublicationMetadata
from app.publishing_wire import OfficialHTTPClient


async def run(args):
    source = Path(args.source).resolve(strict=True); output = Path(args.output).resolve()
    assert not output.exists(), 'Fresh evidence directory required'
    content = source.read_bytes(); digest = hashlib.sha256(content).hexdigest()
    assert digest == '80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d'
    token = 'EXPLICIT_META_PROTOCOL_FIXTURE_TOKEN_NOT_REAL'
    fb = GraphTarget('facebook', '123456789', 'v26.0', 'facebook_login')
    ig = GraphTarget('instagram_reels', '17841400000001', 'v26.0', 'facebook_login')
    video, container = '724627979033843', '18270815569115548'
    url = f'https://rupload.facebook.com/video-upload/v26.0/{video}'
    prefix = 'https://media.fixture.example/owned/'
    requests = []; received_sha = None
    def facebook(request):
        nonlocal received_sha
        if request.url.host == 'rupload.facebook.com':
            assert request.headers['authorization'] == 'OAuth ' + token and request.content == content
            received_sha = hashlib.sha256(request.content).hexdigest()
            requests.append({'platform': 'facebook', 'operation': 'binary-upload', 'bytes': len(request.content), 'mock': True})
            return httpx.Response(200, json={'success': True})
        assert request.headers['authorization'] == 'Bearer ' + token
        if request.method == 'GET':
            requests.append({'platform': 'facebook', 'operation': 'status', 'mock': True})
            return httpx.Response(200, json={'id': video, 'status': {'uploading_phase': {'status': 'complete'}}})
        params = parse_qs(request.content.decode())
        operation = params['upload_phase'][0]
        requests.append({'platform': 'facebook', 'operation': operation, 'mock': True})
        if operation == 'start': return httpx.Response(200, json={'video_id': video, 'upload_url': url})
        assert params['video_state'] == ['DRAFT']
        return httpx.Response(200, json={'success': True})
    fb_client = OfficialHTTPClient('facebook', transport=httpx.MockTransport(facebook))
    session = fb_created_session(await fb_client.request(fb_create_request(fb, token)), fb)
    assert confirmed_success(await fb_client.request(fb_upload_request(session, token, content=content)))
    assert confirmed_success(await fb_client.request(fb_finish_request(fb, video,
        PublicationMetadata(title='Cần Giờ — thử nghiệm tổng hợp'), token, video_state='DRAFT')))
    observed = fb_observation(await fb_client.request(fb_status_request(fb, video, token)), video)
    assert observed.processing_progress is None and observed.publishing_phase is None and received_sha == digest
    def instagram(request):
        assert request.url.host == 'graph.facebook.com' and request.headers['authorization'] == 'Bearer ' + token
        if request.method == 'GET':
            operation, data = 'container-status', {'id': container, 'status_code': 'FINISHED'}
        elif request.url.path.endswith('/media'):
            operation, data = 'container-create', {'id': container}
            params = parse_qs(request.content.decode()); assert params['media_type'] == ['REELS']
        else:
            operation, data = 'publish', {'id': '90011803596441'}
            assert request.url.path.endswith('/media_publish')
        requests.append({'platform': 'instagram_reels', 'operation': operation, 'mock': True})
        return httpx.Response(200, json=data)
    ig_client = OfficialHTTPClient('instagram_reels', transport=httpx.MockTransport(instagram))
    container_id = created_id(await ig_client.request(ig_create_request(ig,
        PublicationMetadata(title='Video fixture', privacy='public'), token,
        video_url=prefix + 'fixture.mp4', authorized_prefix=prefix, share_to_feed=False)))
    ready = ig_container_observation(await ig_client.request(ig_container_request(ig, container_id, token)), ig, container_id)
    fixture_media = created_id(await ig_client.request(ig_publish_request(ig, ready, token)))
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    exports = {
        'source.json': {'sha256': digest, 'bytes': len(content), 'synthetic_media': True, 'unchanged': True,
            'received_sha256': received_sha},
        'request-audit.json': requests,
        'observations.json': {'facebook': {'uploading_phase': observed.uploading_phase,
            'processing_progress': observed.processing_progress, 'publishing_phase': observed.publishing_phase,
            'draft_request_is_not_publication': True}, 'instagram': {'ready_fixture': ready.ready,
            'returned_media_id_is_fixture': True, 'media_id': fixture_media, 'mock': True}},
        'contract.json': {'status': 'PASS', 'mock_requests': len(requests), 'facebook_actual_byte_transfer': True,
            'instagram_hosted_download_actual_tested': False, 'account_or_permissions_verified': False,
            'version_is_explicit_fixture_not_actual_provider_verification': True,
            'cost_records_created': 0, 'actual_cost': None, 'actual_provider_requests': 0,
            'paid_operations': 0, 'real_credentials_read': 0, 'published': False, 'external_action': False,
            'durable_runtime_accepted': False, 'owner_uat_accepted': False, 'full_qc_in_this_contract': False},
    }
    public = json.dumps(exports, ensure_ascii=False)
    assert token not in public and url not in public and 'signature=' not in public
    output.mkdir(parents=True)
    for name, value in exports.items():
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'exports': len(exports), 'mock_requests': len(requests),
        'actual_source_bytes': len(content), 'actual_provider_requests': 0, 'published': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--source', required=True); parser.add_argument('--output', required=True)
    asyncio.run(run(parser.parse_args()))
