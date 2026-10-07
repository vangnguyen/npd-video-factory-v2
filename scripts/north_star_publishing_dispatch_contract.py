"""Owned SQLite restart/dispatch rehearsal. All identities/media/providers are fixtures."""
import argparse
import asyncio
from datetime import timedelta
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from test_publishing_dispatch import fixture_stack, prepared
from test_publishing_dispatch_migration import rehearse
from app.publishing_db import PublicationEventORM
from app.publishing_dispatch import DispatchError


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle, 'sha256').hexdigest()


def restarted(fixture):
    # A different Python process reads only the committed public projection.
    source = ('import asyncio,json; from app.db import create_engine,create_session_factory; '
        'from app.publishing_dispatch import PublishingDispatchJournal; '
        f'engine=create_engine({("sqlite+aiosqlite:///" + str(fixture["db"]))!r}); '
        'journal=PublishingDispatchJournal(create_session_factory(engine)); '
        f'\nasync def run():\n print(json.dumps(await journal.get({fixture["workspace"]!r},{fixture["publication"].publication_id!r})))\n await engine.dispose()\nasyncio.run(run())')
    return json.loads(subprocess.check_output([sys.executable, '-c', source], cwd=ROOT / 'apps/api', timeout=20))


def committed_before_fixture_provider(fixture, ticket):
    with sqlite3.connect(str(fixture['db'])) as connection:
        phase, version = connection.execute('SELECT phase,version FROM publication_dispatches WHERE publication_id=?',
            (ticket.publication_id,)).fetchone()
        assert phase == ticket.phase and version == ticket.version
    return {'fixture_provider_only': True, 'phase': phase, 'version': version, 'committed_before_callback': True}


async def run(root, output):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    write(output / 'migration.json', rehearse(root / 'pre-dispatch.db'))
    fixture_generator = fixture_stack.__wrapped__(root / 'confirmed')
    fixture = await anext(fixture_generator)
    history, restarts, callbacks = [], [], []
    try:
        grant, value = await prepared(fixture); write(output / 'publish-only-fixture-consent.json', grant)
        journal = fixture['journal']; workspace = fixture['workspace']; identifier = value['publication_id']
        history.append(value)
        candidates = await asyncio.gather(*(journal.intent(workspace, identifier, value['version'], 'init') for _ in range(2)), return_exceptions=True)
        tickets = [value for value in candidates if not isinstance(value, Exception)]
        assert len(tickets) == 1 and len([value for value in candidates if isinstance(value, DispatchError)]) == 1
        ticket = tickets[0]; callbacks.append(committed_before_fixture_provider(fixture, ticket))
        restarts.append(restarted(fixture)); assert restarts[-1]['phase'] == 'init_intent'
        value = await journal.finish(ticket, session_ref='pss_' + 'a' * 32); history.append(value)
        ticket = await journal.intent(workspace, identifier, value['version'], 'chunk', offset=0, length=fixture['total_bytes'])
        callbacks.append(committed_before_fixture_provider(fixture, ticket))
        value = await journal.finish(ticket, uncertain=True); history.append(value)
        await fixture['stack'].engine.dispose(); restarts.append(restarted(fixture))
        assert restarts[-1]['phase'] == 'chunk_uncertain' and restarts[-1]['acknowledged_bytes'] == 0
        ticket = await journal.intent(workspace, identifier, value['version'], 'reconcile')
        callbacks.append(committed_before_fixture_provider(fixture, ticket))
        value = await journal.finish(ticket, acknowledged_bytes=fixture['total_bytes'], remote_post_id='AbcD_12-345')
        history.append(value); assert value['phase'] == 'uploaded'
        assert sum(value['phase'] == 'init_intent' for value in callbacks) == 1
        assert value['remote_post_id'] == 'AbcD_12-345'
        async with fixture['stack'].repository.session_factory() as session:
            rows = (await session.scalars(select(PublicationEventORM).order_by(PublicationEventORM.created_at))).all()
            events = [{'event_id': row.event_id, 'event_type': row.event_type, 'actor_ref': row.actor_ref, 'payload': row.payload_json} for row in rows]
        await journal.revoke(workspace, grant['publish_approval_id'], principal=fixture['principals']['owner'])
        write(output / 'dispatch-history.json', {'history': history, 'callbacks': callbacks, 'concurrent_init_claims': 2, 'successful_init_claims': 1})
        write(output / 'events.json', events)
    finally:
        await fixture_generator.aclose()
    ambiguous_generator = fixture_stack.__wrapped__(root / 'ambiguous')
    fixture = await anext(ambiguous_generator)
    try:
        _grant, value = await prepared(fixture); journal = fixture['journal']
        ticket = await journal.intent(fixture['workspace'], value['publication_id'], value['version'], 'init')
        value = await journal.finish(ticket, uncertain=True); assert value['phase'] == 'init_uncertain'
        await fixture['stack'].engine.dispose(); restarts.append(restarted(fixture))
        fixture['clock'][0] += timedelta(minutes=10)
        try:
            await journal.intent(fixture['workspace'], value['publication_id'], value['version'], 'init')
        except DispatchError as error:
            assert error.code == 'PUBLISH_INITIALIZATION_MUST_NOT_REPEAT'
        else: raise AssertionError('Ambiguous initialization was repeated')
        write(output / 'ambiguous-initialization.json', {'status': 'PASS', 'state': value,
            'new_initialization_after_restart_and_lease_expiry': 'refused', 'requires_owner_reconciliation': True})
    finally:
        await ambiguous_generator.aclose()
    write(output / 'restart-projections.json', restarts)
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert 'pss_' not in serialized and 'intent_id' not in serialized and 'Bearer ' not in serialized
    write(output / 'receipt.json', {'schema': 'north-star-publishing-dispatch-contract-v1', 'status': 'PASS',
        'actual_sqlite_transactions': True, 'separate_process_restart_reads': 3,
        'fixtures_only': ['human identity', 'publish consent', 'production approval', 'render', 'QC', 'provider receipt', 'private session reference'],
        'actual_external_requests': 0, 'secrets_read': 0, 'paid_operations': 0, 'default_adapter_activated': False,
        'uploaded_is_not_published': True, 'private_session_encryption_verified': False,
        'real_provider_acceptance': False, 'owner_uat_accepted': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 7, 'separate_process_reads': 3, 'actual_provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve()))
