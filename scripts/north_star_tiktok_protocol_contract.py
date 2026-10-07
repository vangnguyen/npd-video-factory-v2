"""Physical synthetic media through official MockTransport; no publish authority."""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))
from app.publishing_models import PublicationMetadata, PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient
from app.tiktok_credentials import (TikTokOAuthCredential, account_request, confirm_account, resolve_tiktok_credential)
from app.tiktok_upload import (ChunkPlan, PostChoices, chunk_ack, chunk_request, creator_info, creator_request,
    post_observation, start_request, started_session, status_request)


async def run(args):
    source = Path(args.source).resolve(strict=True); output = Path(args.output).resolve()
    assert not output.exists(), 'Fresh evidence directory required'
    source_bytes = source.read_bytes()
    digest = hashlib.sha256(source_bytes).hexdigest()
    assert digest == '80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d'
    result = subprocess.run([args.ffprobe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)],
        capture_output=True, timeout=30, check=True)
    raw = json.loads(result.stdout)
    video = next(s for s in raw['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in raw['streams'] if s['codec_type'] == 'audio')
    assert (video['width'], video['height'], video['codec_name'], audio['codec_name']) == (1080, 1920, 'h264', 'aac')
    duration = float(raw['format']['duration'])
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    token = 'EXPLICIT_PROTOCOL_FIXTURE_TOKEN_NOT_REAL_123456'
    uri = 'https://open-upload.tiktokapis.com/video/?upload_id=67890&upload_token=EXPLICIT_PRIVATE_FIXTURE'
    target = PublishingTargetBinding(workspace_id='wsp_protocol_fixture', profile_id='ppf_protocol_fixture',
        profile_version=1, platform='tiktok', provider_key='tiktok-content-posting-api',
        target_account_id='EXPLICIT_OPEN_ID', credential_binding_sha256='a' * 64)
    credential = resolve_tiktok_credential(lambda _: TikTokOAuthCredential(target, now + timedelta(hours=1),
        frozenset({'video.publish', 'user.info.basic'}), token), target, now=now)
    requests, received = [], []
    polls = 0
    def handler(request):
        nonlocal polls
        path = request.url.path
        if request.url.host == 'open-upload.tiktokapis.com':
            assert 'authorization' not in request.headers and request.content == source_bytes
            received.append(hashlib.sha256(request.content).hexdigest())
            requests.append({'method': request.method, 'operation': 'upload', 'bytes': len(request.content), 'mock': True})
            return httpx.Response(201)
        assert request.headers['authorization'] == 'Bearer ' + token
        operation = 'account' if path == '/v2/user/info/' else 'creator' if path.endswith('/creator_info/query/') else 'init' if path.endswith('/video/init/') else 'status'
        requests.append({'method': request.method, 'operation': operation, 'mock': True})
        if operation == 'account': data = {'user': {'open_id': 'EXPLICIT_OPEN_ID'}}
        elif operation == 'creator':
            data = {'creator_username': 'fixture_creator', 'creator_nickname': 'Explicit Fixture Channel',
                'privacy_level_options': ['SELF_ONLY'], 'comment_disabled': True,
                'duet_disabled': True, 'stitch_disabled': True, 'max_video_post_duration_sec': 60}
        elif operation == 'init':
            body = json.loads(request.content)
            assert body['post_info']['privacy_level'] == 'SELF_ONLY'
            assert body['source_info'] == {'source': 'FILE_UPLOAD', 'video_size': len(source_bytes),
                'chunk_size': len(source_bytes), 'total_chunk_count': 1}
            data = {'publish_id': 'v_pub_explicit_fixture', 'upload_url': uri}
        else:
            assert path.endswith('/status/fetch/')
            polls += 1
            data = {'status': 'PROCESSING_UPLOAD' if polls == 1 else 'PUBLISH_COMPLETE'}
        return httpx.Response(200, json={'data': data, 'error': {'code': 'ok'}})
    client = OfficialHTTPClient('tiktok', transport=httpx.MockTransport(handler))
    account = confirm_account(await client.request(account_request(credential)), target)
    creator = creator_info(await client.request(creator_request(token)))
    choices = PostChoices(privacy_level='SELF_ONLY', disable_comment=True, disable_duet=True,
        disable_stitch=True, brand_content_toggle=False, brand_organic_toggle=False,
        is_aigc=False, music_usage_confirmed=True)
    plan = ChunkPlan(len(source_bytes))
    init = start_request(PublicationMetadata(title='Cần Giờ — kiểm tra giao thức', caption='Video thử nghiệm tổng hợp'),
        plan, token, creator=creator, choices=choices, duration_sec=duration,
        client_audited=False, media_location='user_device')
    session = started_session(await client.request(init), plan, now=now)
    assert chunk_ack(await client.request(chunk_request(session, 0, source_bytes, now=now)), plan, 0) == len(source_bytes)
    observations = [post_observation(await client.request(status_request(session.publish_id, token)),
        total_bytes=len(source_bytes)) for _ in range(2)]
    assert [o.status for o in observations] == ['PROCESSING_UPLOAD', 'PUBLISH_COMPLETE']
    assert all(o.public_post_ids == () and o.uploaded_bytes is None for o in observations)
    assert received == [digest] and sum(r['operation'] == 'init' for r in requests) == 1
    assert hashlib.sha256(source.read_bytes()).hexdigest() == digest
    exports = {
        'source.json': {'sha256': digest, 'bytes': len(source_bytes), 'synthetic_media': True, 'unchanged': True},
        'media.json': {'width': video['width'], 'height': video['height'], 'codec': video['codec_name'],
            'fps': video['r_frame_rate'], 'audio_codec': audio['codec_name'], 'duration': duration, 'ffprobe_real': True,
            'full_qc_run_in_this_contract': False},
        'request-audit.json': requests,
        'observations.json': [{'status': o.status, 'uploaded_bytes': o.uploaded_bytes,
            'public_post_ids': list(o.public_post_ids), 'mock': True} for o in observations],
        'contract.json': {'status': 'PASS', 'mock_requests': len(requests), 'initializations': 1,
            'received_sha256': received[0], 'account_match_fixture': account['account_match'],
            'actual_cost': None, 'cost_records_created': 0, 'actual_provider_requests': 0, 'paid_operations': 0,
            'real_credentials_read': 0, 'published': False, 'external_action': False,
            'durable_runtime_accepted': False, 'owner_uat_accepted': False,
            'identity_account_credentials_disclosures_and_confirmations_are_fixtures': True},
    }
    public = json.dumps(exports, ensure_ascii=False)
    assert token not in public and uri not in public and 'upload_token' not in public
    output.mkdir(parents=True)
    for name, value in exports.items():
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'status': 'PASS', 'exports': len(exports), 'mock_requests': len(requests),
        'received_bytes': len(source_bytes), 'initializations': 1, 'actual_provider_requests': 0, 'published': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--ffprobe', required=True)
    asyncio.run(run(parser.parse_args()))
