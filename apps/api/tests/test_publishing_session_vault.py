"""Actual optional AEAD with fixture-only keys, identities, sessions and media."""
from dataclasses import replace
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import select

from app.publishing_db import PublicationPrivateSessionORM
from app.publishing_dispatch import DispatchError
from app.publishing_session_vault import PublishingSessionVault, SessionEncryptionKey, SessionVaultError
from app.youtube_upload import UploadSession
from test_publishing_dispatch import fixture_stack, prepared


crypto = pytest.mark.skipif(importlib.util.find_spec('cryptography') is None, reason='optional publishing crypto dependency not installed')
URI = 'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&upload_id=EXPLICIT_PRIVATE_FIXTURE'
KEY = SessionEncryptionKey('fixture-one', b'\x01' * 32)


async def ready(fixture):
    grant, value = await prepared(fixture)
    ticket = await fixture['journal'].intent(fixture['workspace'], value['publication_id'], value['version'], 'init')
    vault = PublishingSessionVault(fixture['stack'].repository.session_factory,
        key_provider=lambda identifier: KEY if identifier in (None, KEY.key_id) else None, clock=lambda: fixture['clock'][0])
    upload = UploadSession(URI, fixture['total_bytes'])
    return grant, value, ticket, vault, upload


@pytest.mark.asyncio
async def test_no_key_or_key_resolver_failure_cannot_fall_back_to_plaintext(fixture_stack):
    fixture = fixture_stack; _grant, _value, ticket, _vault, upload = await ready(fixture)
    def failure(_identifier): raise RuntimeError(URI)
    for provider, code in ((None, 'KEY_NOT_CONFIGURED'), (failure, 'KEY_UNAVAILABLE'), (lambda _id: 'invalid', 'KEY_UNAVAILABLE')):
        vault = PublishingSessionVault(fixture['stack'].repository.session_factory, key_provider=provider)
        with pytest.raises(SessionVaultError, match=code) as caught: await vault.save(ticket, upload)
        assert URI not in str(caught.value)
    async with fixture['stack'].repository.session_factory() as session:
        assert (await session.scalars(select(PublicationPrivateSessionORM))).all() == []


def test_key_and_request_values_are_strict_and_repr_has_no_key():
    for key in (b'1' * 16, b'1' * 31, b'1' * 33, 'plaintext'):
        with pytest.raises(SessionVaultError, match='KEY_INVALID'): SessionEncryptionKey('fixture', key)
    with pytest.raises(SessionVaultError, match='KEY_INVALID'): SessionEncryptionKey('../bad', b'1' * 32)
    assert repr(KEY) == "SessionEncryptionKey(key_id='fixture-one')"
    calls = []
    vault = PublishingSessionVault(None, key_provider=lambda identifier: calls.append(identifier))
    for identifier in ('../unapproved', 'a' * 65, 'private\nvalue', 7):
        with pytest.raises(SessionVaultError, match='KEY_UNAVAILABLE'): vault.cipher(identifier)
    assert calls == []


@pytest.mark.asyncio
async def test_missing_optional_crypto_cannot_store_a_plaintext_receipt(fixture_stack, monkeypatch):
    import builtins
    fixture = fixture_stack; _grant, _value, ticket, vault, upload = await ready(fixture)
    original = builtins.__import__
    def blocked(name, *args, **kwargs):
        if name == 'cryptography.hazmat.primitives.ciphers.aead': raise ImportError('Explicit unavailable dependency fixture')
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, '__import__', blocked)
    with pytest.raises(SessionVaultError, match='CRYPTO_NOT_CONFIGURED'): await vault.save(ticket, upload)
    async with fixture['stack'].repository.session_factory() as session:
        assert (await session.scalars(select(PublicationPrivateSessionORM))).all() == []


@crypto
@pytest.mark.asyncio
async def test_encrypted_receipt_commits_before_reference_and_idempotent_replay_does_not_extend(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    async with fixture['stack'].repository.session_factory() as session:
        row = await session.get(PublicationPrivateSessionORM, reference)
        expires = row.expires_at; cipher = row.ciphertext
        assert len(row.nonce) == 12 and URI.encode() not in cipher and KEY.key not in cipher
    fixture['clock'][0] += timedelta(seconds=5)
    assert await vault.save(ticket, upload, ttl_seconds=86400) == reference
    async with fixture['stack'].repository.session_factory() as session:
        row = await session.get(PublicationPrivateSessionORM, reference)
        assert row.expires_at == expires and row.ciphertext == cipher
    loaded = await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256'])
    assert loaded == upload and URI not in repr(loaded)
    state = await fixture['journal'].finish(ticket, session_ref=reference)
    assert state['phase'] == 'upload_ready' and reference not in json.dumps(state)
    await fixture['stack'].engine.dispose()
    assert URI.encode() not in fixture['db'].read_bytes() and KEY.key not in fixture['db'].read_bytes()


@crypto
@pytest.mark.asyncio
async def test_concurrent_receipt_replay_is_single_and_conflicting_uri_cannot_overwrite(fixture_stack):
    import asyncio
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    results = await asyncio.gather(*(vault.save(ticket, upload) for _ in range(2)))
    assert results[0] == results[1]
    with pytest.raises(SessionVaultError, match='RECEIPT_CONFLICT'):
        await vault.save(ticket, UploadSession(URI + '-different', upload.total_bytes))
    async with fixture['stack'].repository.session_factory() as session:
        assert len((await session.scalars(select(PublicationPrivateSessionORM))).all()) == 1
    assert (await vault.load(fixture['workspace'], value['publication_id'], results[0], expected_binding_sha256=value['binding_sha256'])).uri == URI


@crypto
@pytest.mark.asyncio
@pytest.mark.parametrize('tamper', ['ciphertext', 'nonce', 'created_at', 'expires_at', 'key_id'])
async def test_ciphertext_and_authenticated_metadata_tampering_fail_closed(fixture_stack, tamper):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    async with fixture['stack'].repository.session_factory() as session:
        async with session.begin():
            row = await session.get(PublicationPrivateSessionORM, reference)
            if tamper == 'ciphertext': row.ciphertext = bytes([row.ciphertext[0] ^ 1]) + row.ciphertext[1:]
            elif tamper == 'nonce': row.nonce = bytes([row.nonce[0] ^ 1]) + row.nonce[1:]
            elif tamper == 'key_id': row.key_id = 'wrong-key'
            else: setattr(row, tamper, getattr(row, tamper) + timedelta(seconds=10))
    with pytest.raises(SessionVaultError, match='AUTHENTICATION_FAILED|KEY_UNAVAILABLE') as caught:
        await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256'])
    assert URI not in str(caught.value)


@crypto
@pytest.mark.asyncio
async def test_workspace_publication_binding_and_ticket_nonce_cannot_be_substituted(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    with pytest.raises(SessionVaultError, match='STALE_OR_FOREIGN_TICKET'):
        await vault.save(replace(ticket, intent_id='0' * 32), upload)
    reference = await vault.save(ticket, upload)
    for workspace, publication, digest in (('wsp_foreign', value['publication_id'], value['binding_sha256']),
        (fixture['workspace'], 'pub_foreign', value['binding_sha256']), (fixture['workspace'], value['publication_id'], '0' * 64)):
        with pytest.raises(SessionVaultError, match='SCOPE_NOT_FOUND'):
            await vault.load(workspace, publication, reference, expected_binding_sha256=digest)
    await fixture['journal'].finish(ticket, session_ref=reference)
    with pytest.raises(SessionVaultError, match='STALE_OR_FOREIGN_TICKET'): await vault.save(ticket, upload)


@crypto
@pytest.mark.asyncio
async def test_key_rotation_retains_original_key_and_missing_old_key_never_uses_new_key(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    new = SessionEncryptionKey('fixture-two', b'\x02' * 32)
    keys = {KEY.key_id: KEY, new.key_id: new}; vault.key_provider = lambda identifier: keys.get(identifier or new.key_id)
    assert await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256']) == upload
    del keys[KEY.key_id]
    with pytest.raises(SessionVaultError, match='KEY_UNAVAILABLE'):
        await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256'])


@crypto
@pytest.mark.asyncio
async def test_expired_session_never_extends_or_admits_reinitialization(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload, ttl_seconds=60)
    fixture['clock'][0] += timedelta(seconds=61)
    with pytest.raises(SessionVaultError, match='EXPIRED_REVIEW_REQUIRED'): await vault.save(ticket, upload)
    with pytest.raises(SessionVaultError, match='EXPIRED_REVIEW_REQUIRED'):
        await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256'])
    with pytest.raises(DispatchError, match='INITIALIZATION_MUST_NOT_REPEAT'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], ticket.version, 'init')


@crypto
@pytest.mark.asyncio
async def test_separate_process_decrypts_with_fixture_key_without_printing_private_uri(fixture_stack):
    fixture = fixture_stack; _grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload); await fixture['stack'].engine.dispose()
    code = ('import asyncio,hashlib,json; from app.db import create_engine,create_session_factory; '
        'from app.publishing_session_vault import PublishingSessionVault,SessionEncryptionKey; '
        f'engine=create_engine({("sqlite+aiosqlite:///" + str(fixture["db"]))!r}); '
        'key=SessionEncryptionKey("fixture-one",b"\\x01"*32); '
        'vault=PublishingSessionVault(create_session_factory(engine),key_provider=lambda identifier:key); '
        f'\nasync def run():\n result=await vault.load({fixture["workspace"]!r},{value["publication_id"]!r},{reference!r},expected_binding_sha256={value["binding_sha256"]!r})\n '
        'print(json.dumps({"uri_sha256":hashlib.sha256(result.uri.encode()).hexdigest(),"total_bytes":result.total_bytes}))\n await engine.dispose()\nasyncio.run(run())')
    result = json.loads(subprocess.check_output([sys.executable, '-c', code], cwd=Path(__file__).parents[1], timeout=20))
    assert result == {'uri_sha256': hashlib.sha256(URI.encode()).hexdigest(), 'total_bytes': upload.total_bytes}


@crypto
@pytest.mark.asyncio
async def test_decrypt_for_reconciliation_after_revocation_does_not_authorize_another_chunk(fixture_stack):
    fixture = fixture_stack; grant, value, ticket, vault, upload = await ready(fixture)
    reference = await vault.save(ticket, upload)
    state = await fixture['journal'].finish(ticket, session_ref=reference)
    await fixture['journal'].revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    assert await vault.load(fixture['workspace'], value['publication_id'], reference, expected_binding_sha256=value['binding_sha256']) == upload
    with pytest.raises(DispatchError, match='APPROVAL_REQUIRED_OR_EXPIRED'):
        await fixture['journal'].intent(fixture['workspace'], value['publication_id'], state['version'], 'chunk', offset=0, length=1)
