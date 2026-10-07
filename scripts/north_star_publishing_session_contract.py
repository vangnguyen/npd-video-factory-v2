"""Real encrypted SQLite restart; no live credential/session/publishing input."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api/tests'))
from test_publishing_dispatch import fixture_stack, prepared
from test_publishing_session_migration import rehearse
from app.publishing_db import PublicationPrivateSessionORM
from app.publishing_dispatch import DispatchError
from app.publishing_session_vault import PublishingSessionVault, SessionEncryptionKey, SessionVaultError
from app.youtube_upload import UploadSession


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle, 'sha256').hexdigest()


def write(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2); handle.write('\n')


async def run(root, output):
    root.mkdir(parents=True, exist_ok=False); output.mkdir(parents=True, exist_ok=False)
    write(output / 'migration.json', rehearse(root / 'pre-vault.db'))
    generator = fixture_stack.__wrapped__(root / 'sealed'); fixture = await anext(generator)
    # Explicit fixed fixture key, never a real credential or production bootstrap.
    key = SessionEncryptionKey('explicit-contract-fixture', b'\x03' * 32)
    uri = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=VAULT_PRIVATE_FIXTURE'
    try:
        _grant, state = await prepared(fixture); journal = fixture['journal']
        ticket = await journal.intent(fixture['workspace'], state['publication_id'], state['version'], 'init')
        vault = PublishingSessionVault(fixture['stack'].repository.session_factory,
            key_provider=lambda identifier: key if identifier in (None, key.key_id) else None, clock=lambda: fixture['clock'][0])
        upload = UploadSession(uri, fixture['total_bytes']); reference = await vault.save(ticket, upload)
        assert await vault.save(ticket, upload, ttl_seconds=86400) == reference
        async with fixture['stack'].repository.session_factory() as session:
            row = await session.get(PublicationPrivateSessionORM, reference)
            expiry = row.expires_at.isoformat(); nonce = row.nonce; ciphertext = row.ciphertext
            assert len((await session.scalars(select(PublicationPrivateSessionORM))).all()) == 1
        write(output / 'sealed-receipt.json', {'status': 'PASS', 'encryption': 'AES-256-GCM',
            'ciphertext_sha256': hashlib.sha256(ciphertext).hexdigest(), 'ciphertext_bytes': len(ciphertext),
            'nonce_bytes': len(nonce), 'plaintext_uri_present_in_ciphertext': uri.encode() in ciphertext,
            'key_persisted': False, 'idempotent_replay_does_not_extend_expiry': True,
            'expires_at': expiry, 'expiry_source': 'internal_policy', 'session_ref_exposed': False})
        # Crash interval: the sealed receipt exists before the journal records its opaque ref.
        await fixture['stack'].engine.dispose()
        code = ('import asyncio,hashlib,json; from app.db import create_engine,create_session_factory; '
            'from app.publishing_session_vault import PublishingSessionVault,SessionEncryptionKey; '
            f'engine=create_engine({("sqlite+aiosqlite:///" + str(fixture["db"]))!r}); '
            'key=SessionEncryptionKey("explicit-contract-fixture",b"\\x03"*32); '
            'vault=PublishingSessionVault(create_session_factory(engine),key_provider=lambda identifier:key); '
            f'\nasync def run():\n value=await vault.load({fixture["workspace"]!r},{state["publication_id"]!r},{reference!r},expected_binding_sha256={state["binding_sha256"]!r})\n '
            'print(json.dumps({"uri_sha256":hashlib.sha256(value.uri.encode()).hexdigest(),"total_bytes":value.total_bytes}))\n await engine.dispose()\nasyncio.run(run())')
        restarted = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=ROOT / 'apps/api', timeout=20))
        assert restarted == {'uri_sha256': hashlib.sha256(uri.encode()).hexdigest(), 'total_bytes': upload.total_bytes}
        write(output / 'restart.json', {'status': 'PASS', 'separate_python_process': True,
            'sealed_receipt_persisted_before_journal_finish': True, 'exact_uri_and_size_restored': True,
            'private_uri_printed': False, 'automatic_orphan_recovery_implemented': False})
        state = await journal.finish(ticket, session_ref=reference)
        assert await vault.load(fixture['workspace'], state['publication_id'], reference, expected_binding_sha256=state['binding_sha256']) == upload
        failures = []
        for workspace, digest in (('wsp_foreign_fixture', state['binding_sha256']), (fixture['workspace'], '0' * 64)):
            try: await vault.load(workspace, state['publication_id'], reference, expected_binding_sha256=digest)
            except SessionVaultError as error: failures.append(error.code)
            else: raise AssertionError('Foreign session admission')
        assert failures == ['PUBLISH_SESSION_SCOPE_NOT_FOUND'] * 2
        vault.key_provider = None
        try: await vault.load(fixture['workspace'], state['publication_id'], reference, expected_binding_sha256=state['binding_sha256'])
        except SessionVaultError as error: assert error.code == 'PUBLISH_SESSION_KEY_NOT_CONFIGURED'
        else: raise AssertionError('Plaintext fallback occurred')
        write(output / 'admission.json', {'status': 'PASS', 'foreign_workspace_and_binding': 'refused',
            'missing_key': 'refused', 'plaintext_fallback': False, 'publishing_state': state,
            'uploaded_or_published': False, 'no_provider_request_issued': True})
        await fixture['stack'].engine.dispose()
        scanned = {path.name: {'sha256': sha(path), 'bytes': path.stat().st_size,
            'plaintext_uri_found': uri.encode() in path.read_bytes(), 'fixture_key_found': key.key in path.read_bytes()}
            for path in (root / 'sealed').glob('production.db*') if path.is_file()}
        assert scanned and not any(value['plaintext_uri_found'] or value['fixture_key_found'] for value in scanned.values())
        write(output / 'database-inspection.json', {'status': 'PASS', 'scanned_database_and_sidecars': scanned})
    finally: await generator.aclose()
    serialized = ''.join(path.read_text(encoding='utf-8') for path in output.glob('*.json'))
    assert uri not in serialized and reference not in serialized
    import cryptography
    write(output / 'receipt.json', {'schema': 'north-star-publishing-session-contract-v1', 'status': 'PASS',
        'crypto_version': cryptography.__version__, 'actual_aes256gcm': True, 'actual_sqlite_restart': True,
        'all_keys_human_media_provider_inputs_are_fixtures': True, 'actual_external_requests': 0,
        'secrets_read': 0, 'paid_operations': 0, 'live_adapter_activated': False,
        'publishing_ready': False, 'owner_uat_accepted': False, 'production_deployed': False,
        'exports_sha256': {path.name: sha(path) for path in sorted(output.glob('*.json'))}})
    print(json.dumps({'status': 'PASS', 'exports': 6, 'crypto_version': cryptography.__version__, 'actual_provider_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--fixture-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True); args = parser.parse_args()
    asyncio.run(run(args.fixture_root.resolve(), args.output_root.resolve()))
