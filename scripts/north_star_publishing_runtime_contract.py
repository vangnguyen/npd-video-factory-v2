"""Authenticated API/config/runtime/actual media integration; all provider traffic is mock."""
import argparse
import asyncio
from datetime import timedelta
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
from sqlalchemy import select

from north_star_publishing_worker_contract import sha, write
from app.db import CostRecordORM
from app.production_qc import FullProductionQC
from app.publishing_db import PublicationEventORM
from app.publishing_dispatch import checksum
from app.publishing_models import PublicationRead
from app.publishing_profiles import PublishingProfileCatalog
from test_publishing_dispatch import fixture_stack
from test_publishing_queue import http_app, headers
from test_publishing_runtime import runtime_fixture
from test_publishing_worker import ExplicitReceiver


def restarted(fixture, root, work, received, mode):
    code = '''import asyncio,json,sys,hashlib
from datetime import datetime,timedelta
from pathlib import Path
from types import SimpleNamespace
import httpx
from app.db import create_engine,create_session_factory
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.object_storage import LocalObjectStorageProvider
from app.publishing_credentials import PublishingOAuthCredential,UPLOAD,READ
from app.publishing_profiles import PublishingProfileRegistry
from app.publishing_repository import PublishingRepository
from app.publishing_runtime import YouTubePublishingRuntime
from app.publishing_session_vault import SessionEncryptionKey
from app.publishing_wire import OfficialHTTPClient
p=json.load(sys.stdin); now=datetime.fromisoformat(p['now']); root=Path(p['root'])
profiles=PublishingProfileRegistry.from_json((root/'public-profile-fixtures.json').read_bytes())
target=profiles.select(p['workspace'],'youtube').target
engine=create_engine(p['database']); factory=create_session_factory(engine)
verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(p['registry']),max_token_ttl_seconds=86400)
calls=[]
def handle(request):
    calls.append(request.method)
    if request.method=='GET' and request.url.path.endswith('/channels'):
        return httpx.Response(200,json={'items':[{'id':target.target_account_id}]})
    if p['mode']=='query':
        assert request.method=='PUT' and not request.content and request.headers['content-range'].startswith('bytes */')
        assert hashlib.sha256(Path(p['received']).read_bytes()).hexdigest()==p['source_sha256']
        return httpx.Response(200,json={'id':'AbcD_12-345'})
    assert request.method=='GET' and request.url.params['id']=='AbcD_12-345'
    return httpx.Response(200,json={'items':[{'id':'AbcD_12-345','status':{'privacyStatus':'private'},
        'processingDetails':{'processingStatus':'succeeded'}}]})
credential=PublishingOAuthCredential(target,now+timedelta(hours=1),frozenset({UPLOAD,READ}),'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234')
service=SimpleNamespace(repository=PublishingRepository(factory),settings=SimpleNamespace(
    publish_enabled=True,publish_external_execution_enabled=True,publish_owner_gate_enabled=True))
runtime=YouTubePublishingRuntime(service=service,profiles=profiles,storage=LocalObjectStorageProvider(root/'objects'),
    private_root=root/'private-work',identity_provider=lambda:verifier,credential_resolver=lambda _:credential,
    key_provider=lambda _:SessionEncryptionKey('explicit_fixture',bytes(range(32))),
    client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(handle)),clock=lambda:now)
async def run():
    try:
        result=await runtime.run_one(p['workspace'],p['work_id'],p['version'])
        assert result['status']==('waiting' if p['mode']=='query' else 'completed')
        assert calls==(['GET','PUT'] if p['mode']=='query' else ['GET','GET'])
        print(json.dumps({'work':result,'mock_requests':calls,'separate_process':True,'new_initializations':0}))
    finally: await engine.dispose()
asyncio.run(run())
'''
    payload = {'database': 'sqlite+aiosqlite:///' + str(fixture['db']), 'now': fixture['clock'][0].isoformat(),
        'registry': fixture['verifier'].registry.model_dump(mode='json'), 'root': str(root), 'workspace': fixture['workspace'],
        'work_id': work['work_id'], 'version': work['version'], 'received': str(received), 'source_sha256': sha(received), 'mode': mode}
    result = subprocess.run([sys.executable, '-c', code], input=json.dumps(payload), text=True,
        capture_output=True, timeout=60, check=True)
    return json.loads(result.stdout)


async def run(root, output, source, ffmpeg, ffprobe):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    source_sha = sha(source)
    assert source_sha == '80de36cef34e3945a196e32928ee8d77e6a67100810501acfd38c35d99ebca2d'
    generator = fixture_stack.__wrapped__(root / 'project-fixture'); fixture = await anext(generator)
    try:
        runtime, service, payload, receiver, stored, _owned_source, profile = await runtime_fixture(fixture, root, source_bytes=source.read_bytes())
        catalog = PublishingProfileCatalog(profiles=[profile]); write(root / 'public-profile-fixtures.json', catalog.model_dump(mode='json'))
        runtime.guard.qc = FullProductionQC(ffprobe_path=str(ffprobe), ffmpeg_path=str(ffmpeg))
        inspect = runtime.guard.qc.inspect; reports = []
        async def qc(*args, **kwargs):
            report = await inspect(*args, **kwargs); reports.append(report); return report
        runtime.guard.qc.inspect = qc
        application = http_app(fixture, SimpleNamespace(service=service)); requests = []
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application), base_url='http://explicit-test') as client:
            project_path = f'/api/v1/projects/{fixture["publication"].project_id}'
            created = await client.post(project_path + '/publish', headers={**headers('owner'), 'Idempotency-Key': 'explicit-runtime-http-create'},
                json=payload.model_dump(mode='json'))
            assert created.status_code == 201; requests.append({'method': 'POST', 'status': 201, 'action': 'create'})
            row = PublicationRead.model_validate(created.json()); assert row.mock and row.status == 'awaiting_publish_approval'
            receiver.append(ExplicitReceiver({**fixture, 'publication': row}, runtime.journal, profile.target, source.read_bytes(), lose_final=True))
            path = project_path + f'/publications/{row.publication_id}'
            consent = await client.post(path + '/publish-approval', headers={**headers('owner'), 'Idempotency-Key': 'explicit-runtime-http-consent'},
                json={'expected_fingerprint': row.request_fingerprint, 'expected_artifact_sha256': stored.checksum_sha256,
                    'expected_target_sha256': checksum(profile.target.model_dump(mode='json')), 'acknowledged': True})
            assert consent.status_code == 200; requests.append({'method': 'POST', 'status': 200, 'action': 'publish-only-consent'})
            grant = consent.json()
            queued = await client.post(path + '/publishing-work', headers=headers('owner'), json={'publish_approval_id': grant['publish_approval_id']})
            assert queued.status_code == 200 and receiver[0].requests == []; work = queued.json()
            requests.append({'method': 'POST', 'status': 200, 'action': 'enqueue-no-wire'})
            read = await client.get(path + '/publishing-work', headers=headers('viewer')); assert read.json() == work
            requests.append({'method': 'GET', 'status': read.status_code, 'action': 'viewer-work'})
            initialized = await runtime.run_one(row.workspace_id, work['work_id'], work['version'])
            fixture['clock'][0] += timedelta(seconds=2)
            uncertain = await runtime.run_one(row.workspace_id, work['work_id'], initialized['version'])
            assert uncertain['status'] == 'waiting' and uncertain['failures'] == 1
            received = root / 'explicit-mock-receiver.mp4'; received.write_bytes(receiver[0].received)
            assert sha(received) == source_sha and receiver[0].initializations == 1
            revoked = await client.post(path + '/publish-approval/revoke', headers=headers('owner'), json={'publish_approval_id': grant['publish_approval_id']})
            assert revoked.status_code == 200; requests.append({'method': 'POST', 'status': 200, 'action': 'revoke-future-mutation'})
            await fixture['stack'].engine.dispose(); fixture['clock'][0] += timedelta(seconds=30)
            queried = restarted(fixture, root, uncertain, received, 'query')
            fixture['clock'][0] += timedelta(seconds=2)
            completed = restarted(fixture, root, queried['work'], received, 'processing')
            publication = await client.get(path, headers=headers('viewer')); assert publication.status_code == 200
            requests.append({'method': 'GET', 'status': 200, 'action': 'viewer-final-mock-record'})
            done = publication.json(); assert done['mock'] and not done['external_action'] and done['receipt']['remote_url'] is None
        assert len(reports) == 2 and all(value['status'] == 'passed' for value in reports) and sha(source) == source_sha
        async with runtime.session_factory() as session:
            costs = (await session.scalars(select(CostRecordORM).where(CostRecordORM.provenance['source'].as_string() == 'publishing-wire-admission'))).all()
            events = (await session.scalars(select(PublicationEventORM).where(PublicationEventORM.publication_id == row.publication_id))).all()
        assert len(costs) == 8 and all(cost.actual_cost is None for cost in costs)
        write(output / 'api.json', {'requests': requests, 'all_accounts_roles_gates_approvals_are_fixtures': True, 'created': created.json(), 'completed': done})
        write(output / 'work.json', {'queued': work, 'initialized': initialized, 'uncertain': uncertain, 'query': queried, 'processing': completed})
        write(output / 'media-qc.json', {'reports': reports, 'actual_av_quality': True, 'timeline_subtitle_approval_inputs_are_fixtures': True})
        write(output / 'profile.json', catalog.model_dump(mode='json'))
        write(output / 'source.json', {'source': str(source), 'sha256': source_sha, 'receiver_sha256': sha(received),
            'source_unchanged': True, 'bytes': source.stat().st_size, 'synthetic_pattern_and_sine_only': True,
            'not_a_video_factory_final_render': True, 'not_owner_uat': True})
        write(output / 'cost.json', {'request_intents': len(costs), 'actual_costs': None, 'all_mock': True})
        write(output / 'events.json', [{'type': value.event_type, 'payload': value.payload_json} for value in events])
    finally: await generator.aclose()
    exported = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert all(value not in exported for value in ('Bearer ', 'EXPLICIT_PRIVATE_FIXTURE', 'private_session_ref', 'lease_owner'))
    write(output / 'receipt.json', {'schema': 'publishing-runtime-contract-v1', 'status': 'PASS',
        'api_requests': 6, 'actual_full_qc_runs': 2, 'separate_processes': 2, 'mock_requests': 8, 'initializations': 1,
        'actual_provider_requests': 0, 'paid_operations': 0, 'real_credentials_read': 0,
        'mock_publication_complete': True, 'published': False, 'owner_uat_accepted': False,
        'publishing_ready': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 8, 'api_requests': 6, 'mock_requests': 8,
        'separate_processes': 2, 'initializations': 1, 'published': False}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    for name in ('fixture-root', 'output-root', 'source', 'ffmpeg', 'ffprobe'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve(), args.source.resolve(), args.ffmpeg.resolve(), args.ffprobe.resolve()))
