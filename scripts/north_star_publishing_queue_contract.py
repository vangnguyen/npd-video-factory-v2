"""Owned consent queue/HTTP contract; all live account/media/provider inputs are fixtures."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from httpx import ASGITransport, AsyncClient

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from app.publishing_dispatch import DispatchError
from test_publishing import request_for
from test_publishing_dispatch import fixture_stack
from test_publishing_queue import configured_service, consent_payload, headers, http_app


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def restarted(fixture, row):
    source = '''import asyncio,json,sys
from app.db import create_engine,create_session_factory
from app.publishing_dispatch import DispatchError,PublishingDispatchJournal
from app.publishing_repository import PublishingRepository
p=json.load(sys.stdin); engine=create_engine(p['database']); factory=create_session_factory(engine)
async def run():
    row=await PublishingRepository(factory).get(p['project'],p['publication'])
    value={'publication_status':row.status,'external_action':row.external_action,'has_receipt':row.receipt is not None}
    try:
        value['dispatch']=await PublishingDispatchJournal(factory).get(p['workspace'],p['publication'])
    except DispatchError as error:
        value['dispatch_code']=error.code
    print(json.dumps(value)); await engine.dispose()
asyncio.run(run())
'''
    payload = {'database': 'sqlite+aiosqlite:///' + str(fixture['db']), 'workspace': row.workspace_id,
        'project': row.project_id, 'publication': row.publication_id}
    return json.loads(subprocess.check_output([sys.executable, '-c', source], input=json.dumps(payload).encode(),
        cwd=ROOT / 'apps/api', timeout=30))


async def run(root, output):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    generator = fixture_stack.__wrapped__(root / 'owned-database'); fixture = await anext(generator)
    http = []
    try:
        configured = configured_service(fixture); project = fixture['publication'].project_id
        async with AsyncClient(transport=ASGITransport(app=http_app(fixture, configured)), base_url='http://explicit-contract') as client:
            async def request(method, path, role='owner', body=None, key=None):
                authorization = headers(role)
                if key: authorization['Idempotency-Key'] = key
                response = await client.request(method, path, headers=authorization, json=body)
                http.append({'method': method, 'path': path, 'fixture_role': role, 'status': response.status_code,
                    'response_sha256': hashlib.sha256(response.content).hexdigest()})
                return response
            platforms = await request('GET', '/api/v1/publishing-platforms'); assert platforms.status_code == 200
            assert not any(value['live_execution_enabled'] for value in platforms.json())
            create_path = f'/api/v1/projects/{project}/publish'
            payload = request_for(fixture['publication'].final_render_id, mode='live').model_dump(mode='json')
            created = await request('POST', create_path, body=payload, key='explicit-queue-http-reservation')
            assert created.status_code == 201 and created.json()['status'] == 'awaiting_publish_approval'
            replay = await request('POST', create_path, body=payload, key='explicit-queue-http-reservation')
            assert replay.status_code == 201 and replay.headers['X-Idempotent-Replay'] == 'true' and replay.json() == created.json()
            row = await configured.service.get(project, created.json()['publication_id'])
            path = f'/api/v1/projects/{project}/publications/{row.publication_id}'
            for read_path in (f'/api/v1/projects/{project}/publications', path, f'/api/v1/projects/{project}/publication-history'):
                assert (await request('GET', read_path, role='viewer')).status_code == 200
            for role in ('editor', 'reviewer', 'viewer'):
                assert (await request('POST', path + '/publish-approval', role, {})).status_code == 403
            foreign = await request('GET', '/api/v1/projects/prj_foreign_fixture/publications/' + row.publication_id + '/dispatch')
            assert foreign.status_code == 404
            consent = consent_payload(fixture, row, configured)
            approved = await request('POST', path + '/publish-approval', body=consent, key='explicit-queue-http-consent')
            assert approved.status_code == 200 and approved.headers['Cache-Control'] == 'no-store'
            replay = await request('POST', path + '/publish-approval', body=consent, key='explicit-queue-http-consent')
            assert replay.json() == approved.json(); grant = approved.json()
            after_consent = await request('GET', path)
            assert after_consent.json()['status'] == 'awaiting_publish_approval'
            before = restarted(fixture, row)
            assert before['publication_status'] == 'awaiting_publish_approval' and before['dispatch_code'] == 'PUBLISH_DISPATCH_NOT_FOUND'
            state = await configured.journal.prepare(row.workspace_id, row.publication_id, grant['publish_approval_id'])
            assert state['phase'] == 'init_ready'
            read = await request('GET', path + '/dispatch', role='viewer'); assert read.status_code == 200
            assert 'intent_id' not in read.text and 'private_session_ref' not in read.text
            body = {'publish_approval_id': grant['publish_approval_id']}
            assert (await request('POST', path + '/publish-approval/revoke', 'editor', body)).status_code == 403
            revoked = await request('POST', path + '/publish-approval/revoke', body=body)
            assert revoked.status_code == 200 and revoked.json()['revoked'] is True
        try:
            await configured.journal.intent(row.workspace_id, row.publication_id, state['version'], 'init')
        except DispatchError as error:
            assert error.code == 'PUBLISH_APPROVAL_REQUIRED_OR_EXPIRED'
        else:
            raise AssertionError('Revoked consent admitted an upload')
        after = restarted(fixture, row)
        assert after['publication_status'] == 'publishing' and after['dispatch']['phase'] == 'init_ready'
        assert not after['external_action'] and not after['has_receipt'] and configured.provider.publish_calls == 0
        write(output / 'queued-publication.json', created.json())
        write(output / 'explicit-owner-consent.json', {'grant': grant, 'revoked': revoked.json()})
        write(output / 'http-evidence.json', {'requests': http, 'request_count': len(http), 'provider_publish_calls': 0})
        write(output / 'restart-evidence.json', {'before_worker_admission': before, 'after_admission_and_revocation': after, 'separate_processes': 2})
        events = await configured.service.history(project)
        write(output / 'events.json', [event.model_dump(mode='json') for event in events])
    finally:
        await generator.aclose()
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert 'Bearer ' not in serialized and 'intent_id' not in serialized and 'private_session_ref' not in serialized
    write(output / 'receipt.json', {'schema': 'north-star-publishing-queue-contract-v1', 'status': 'PASS',
        'actual_asgi_http_requests': len(http), 'actual_sqlite_transactions': True, 'separate_process_reads': 2,
        'fixtures_only': ['account', 'profile', 'credential configuration', 'identity', 'production approval', 'render/QC', 'publish consent'],
        'actual_provider_calls': 0, 'real_credentials_read': 0, 'paid_operations': 0,
        'default_adapter_activated': False, 'official_account_verified': False, 'owner_uat_accepted': False,
        'publishing_ready': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 6, 'http_requests': len(http), 'separate_process_reads': 2, 'provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve()))
