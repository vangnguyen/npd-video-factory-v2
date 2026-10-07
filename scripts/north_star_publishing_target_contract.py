"""Owned destination-consent/restart contract; every account/credential is a fixture."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from app.publishing_dispatch import DispatchError
from test_publishing_dispatch import fixture_stack
from test_publishing_target import bind_target, target_for


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def restarted(fixture, grant, target):
    source = '''import asyncio,json,sys
from app.db import create_engine,create_session_factory
from app.human_identity import HumanAuthRegistry,HumanAuthVerifier
from app.publishing_dispatch import DispatchError,PublishingDispatchJournal
from app.publishing_models import PublishingTargetBinding
from datetime import datetime
p=json.load(sys.stdin)
engine=create_engine(p['database'])
verifier=HumanAuthVerifier(HumanAuthRegistry.model_validate(p['registry']),max_token_ttl_seconds=86400)
target=PublishingTargetBinding.model_validate(p['target'])
journal=PublishingDispatchJournal(create_session_factory(engine),identity_provider=lambda:verifier,
    target_provider=lambda workspace,profile:target,require_target_binding=True,clock=lambda:datetime.fromisoformat(p['now']))
async def run():
    try:
        value=await journal.prepare(p['workspace'],p['publication'],p['grant'])
        print(json.dumps({'status':'PASS','state':value}))
    except DispatchError as error:
        print(json.dumps({'status':'REFUSED','code':error.code}))
    finally:
        await engine.dispose()
asyncio.run(run())
'''
    payload = {'database': 'sqlite+aiosqlite:///' + str(fixture['db']), 'registry': fixture['verifier'].registry.model_dump(mode='json'),
        'target': target.model_dump(mode='json'), 'now': fixture['clock'][0].isoformat(), 'workspace': fixture['workspace'],
        'publication': fixture['publication'].publication_id, 'grant': grant['publish_approval_id']}
    return json.loads(subprocess.check_output([sys.executable, '-c', source], input=json.dumps(payload).encode(),
        cwd=ROOT / 'apps/api', timeout=30))


async def run(root, output):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    generator = fixture_stack.__wrapped__(root / 'owned-database')
    fixture = await anext(generator)
    try:
        journal, current, _calls, approve = await bind_target(fixture)
        try:
            await approve(expected_target_sha256=None)
        except DispatchError as error:
            assert error.code == 'PUBLISH_APPROVAL_TARGET_STALE_RELOAD'
        else:
            raise AssertionError('Consent accepted an unreviewed destination')
        grant = await approve(); assert await approve() == grant
        write(output / 'explicit-fixture-consent.json', grant)
        await fixture['stack'].engine.dispose()
        first = restarted(fixture, grant, current[0]); assert first['status'] == 'PASS'
        restarts = [first]
        for updates in ({'target_account_id': 'OTHER-EXPLICIT-ACCOUNT'}, {'profile_version': 2}, {'credential_binding_sha256': 'd' * 64}):
            value = restarted(fixture, grant, target_for(fixture, **updates))
            assert value == {'status': 'REFUSED', 'code': 'PUBLISH_TARGET_CHANGED_REVALIDATE'}
            restarts.append(value)
        state = await journal.get(fixture['workspace'], fixture['publication'].publication_id)
        assert state['phase'] == 'init_ready' and state['version'] == 1
        write(output / 'restart-revalidation.json', {'separate_processes': 4, 'results': restarts})
        write(output / 'unchanged-dispatch.json', {'state': state, 'wire_calls': 0, 'initialization_claims': 0,
            'account_changes_refused': True, 'profile_changes_refused': True, 'credential_binding_changes_refused': True})
    finally:
        await generator.aclose()
    write(output / 'receipt.json', {'schema': 'north-star-publishing-target-contract-v1', 'status': 'PASS',
        'actual_sqlite_transactions': True, 'separate_process_revalidations': 4, 'unreviewed_destination_consent': 'refused',
        'fixtures_only': ['account', 'profile', 'credential fingerprint', 'identity', 'production approval', 'QC', 'publish consent'],
        'actual_provider_requests': 0, 'actual_oauth_secrets_read': 0, 'paid_operations': 0,
        'official_account_verification': False, 'default_adapter_activated': False, 'owner_uat_accepted': False,
        'publishing_ready': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 4, 'separate_process_revalidations': 4, 'wire_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', required=True, type=Path)
    parser.add_argument('--output-root', required=True, type=Path); args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve()))
