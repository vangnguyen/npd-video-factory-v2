"""Pure credential/account protocol fixtures; no secret read or request is executed."""
from datetime import datetime, timedelta, timezone
import json

import httpx

import pytest

from app.publishing_credentials import (FULL, READ, SSL, UPLOAD, PublishingCredentialError, PublishingOAuthCredential,
    confirm_youtube_account, resolve_youtube_credential, target_digest, youtube_account_request)
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient, OfficialResponse

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
TOKEN = 'EXPLICIT_OAUTH_FIXTURE_NOT_A_REAL_TOKEN_1234'


def target(**updates):
    return PublishingTargetBinding.model_validate({'workspace_id': 'wsp_oauth_fixture', 'profile_id': 'ppf_oauth_fixture',
        'profile_version': 1, 'platform': 'youtube', 'provider_key': 'explicit-oauth-fixture',
        'target_account_id': 'EXPLICIT-ACCOUNT', 'credential_binding_sha256': 'a' * 64, **updates})


def credential(**updates):
    return PublishingOAuthCredential(**{'target': target(), 'expires_at': NOW + timedelta(hours=1),
        'scopes': frozenset({UPLOAD, READ}), 'token': TOKEN, **updates})


def test_in_memory_credential_has_hidden_token_exact_target_and_official_account_request():
    value = resolve_youtube_credential(lambda _: credential(), target(), now=NOW)
    assert TOKEN not in repr(value)
    request = youtube_account_request(value)
    assert request.method == 'GET' and request.url.endswith('?part=id&mine=true&maxResults=2') and not request.body
    assert request.headers['Authorization'] == 'Bearer ' + TOKEN and TOKEN not in repr(request)
    response = OfficialResponse(200, {}, json.dumps({'items': [{'id': 'EXPLICIT-ACCOUNT'}]}).encode())
    confirmed = confirm_youtube_account(response, target())
    assert confirmed['account_match'] and confirmed['target_binding_sha256'] == target_digest(target())


@pytest.mark.parametrize('scopes', [frozenset({FULL}), frozenset({SSL}), frozenset({UPLOAD, READ})])
def test_required_upload_and_account_read_scopes_are_admitted(scopes):
    assert resolve_youtube_credential(lambda _: credential(scopes=scopes), target(), now=NOW)


@pytest.mark.parametrize('scopes', [frozenset({UPLOAD}), frozenset({READ})])
def test_missing_operation_scopes_fail_before_account_request(scopes):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_SCOPES_REQUIRED'):
        resolve_youtube_credential(lambda _: credential(scopes=scopes), target(), now=NOW)


@pytest.mark.parametrize('updates', [{'profile_version': 2}, {'target_account_id': 'OTHER-ACCOUNT'},
    {'credential_binding_sha256': 'b' * 64}, {'workspace_id': 'wsp_foreign'}, {'platform': 'facebook'}])
def test_changed_oauth_binding_cannot_be_substituted_for_reviewed_destination(updates):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_TARGET_MISMATCH'):
        resolve_youtube_credential(lambda _: credential(target=target(**updates)), target(), now=NOW)


@pytest.mark.parametrize('expiry', [NOW - timedelta(seconds=1), NOW, NOW + timedelta(seconds=90)])
def test_expired_or_too_short_lived_tokens_need_refresh(expiry):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_REFRESH_REQUIRED'):
        resolve_youtube_credential(lambda _: credential(expires_at=expiry), target(), now=NOW)


def test_missing_or_private_error_resolver_does_not_expose_credential_details():
    def bad(_target): raise RuntimeError(TOKEN)
    for resolver in (None, bad, lambda _: 'RAW-TOKEN', lambda _: credential(target=target().model_copy(update={'profile_version': True}))):
        with pytest.raises(PublishingCredentialError) as raised:
            resolve_youtube_credential(resolver, target(), now=NOW)
        assert TOKEN not in str(raised.value)


@pytest.mark.parametrize('value', [
    {}, {'items': []}, {'items': [{'id': 'OTHER-ACCOUNT'}]}, {'items': [{'id': 'EXPLICIT-ACCOUNT'}, {'id': 'OTHER-ACCOUNT'}]},
    {'items': [{'id': 'EXPLICIT-ACCOUNT'}], 'nextPageToken': 'PRIVATE-FIXTURE'}, {'items': [{'id': True}]},
])
def test_empty_wrong_ambiguous_or_paginated_accounts_are_never_guessed(value):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_ACCOUNT_NOT_CONFIRMED'):
        confirm_youtube_account(OfficialResponse(200, {}, json.dumps(value).encode()), target())


@pytest.mark.parametrize('updates', [{'expires_at': NOW.replace(tzinfo=None)}, {'scopes': [UPLOAD, READ]},
    {'token': True}, {'target': target().model_copy(update={'profile_version': True})},
    {'scopes': frozenset({UPLOAD, READ, 'PRIVATE-FIXTURE-UNSUPPORTED-SCOPE'})}])
def test_malformed_credential_metadata_is_rejected_without_raw_error(updates):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_CREDENTIAL_INVALID') as raised:
        credential(**updates)
    assert 'PRIVATE' not in str(raised.value)


@pytest.mark.parametrize('status', [401, 403, 429, 500])
def test_account_error_does_not_become_an_identity_or_expose_provider_body(status):
    with pytest.raises(PublishingCredentialError, match='PUBLISH_OAUTH_ACCOUNT_NOT_CONFIRMED') as raised:
        confirm_youtube_account(OfficialResponse(status, {}, b'PRIVATE-PROVIDER-FIXTURE'), target())
    assert 'PRIVATE' not in str(raised.value)


@pytest.mark.asyncio
async def test_scoped_official_account_lookup_runs_only_through_explicit_mock_transport():
    received = []
    async def handle(request):
        received.append((request.method, str(request.url)))
        assert request.headers['authorization'] == 'Bearer ' + TOKEN and not request.content
        return httpx.Response(200, json={'items': [{'id': 'EXPLICIT-ACCOUNT'}]})
    client = OfficialHTTPClient('youtube', transport=httpx.MockTransport(handle))
    value = resolve_youtube_credential(lambda _: credential(), target(), now=NOW)
    confirmed = confirm_youtube_account(await client.request(youtube_account_request(value)), target())
    assert confirmed['account_match'] and len(received) == 1 and client.network_enabled is False
