from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest

from app.publishing_credentials import PublishingCredentialError
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient, OfficialResponse
from app.tiktok_credentials import (PUBLISH, READ_ACCOUNT, TikTokOAuthCredential,
    account_request, confirm_account, resolve_tiktok_credential)

NOW = datetime(2026, 10, 7, tzinfo=timezone.utc)
TOKEN = 'EXPLICIT_TIKTOK_CREDENTIAL_FIXTURE_123456789'


def target(**overrides):
    return PublishingTargetBinding(workspace_id='wsp_tiktok_fixture', profile_id='ppf_tiktok_fixture',
        profile_version=overrides.pop('profile_version', 1), platform=overrides.pop('platform', 'tiktok'),
        provider_key=overrides.pop('provider_key', 'tiktok-content-posting-api'),
        target_account_id=overrides.pop('target_account_id', 'EXPLICIT_OPEN_ID'),
        credential_binding_sha256=overrides.pop('credential_binding_sha256', 'a' * 64), **overrides)


def credential(**overrides):
    return TikTokOAuthCredential(**{'target': target(), 'expires_at': NOW + timedelta(hours=1),
        'scopes': frozenset({PUBLISH, READ_ACCOUNT}), 'token': TOKEN, **overrides})


def response(user, **overrides):
    return OfficialResponse(200, {}, json.dumps({'data': {'user': user}, 'error': {'code': 'ok'}, **overrides}).encode())


def test_dedicated_hidden_inmemory_credential_and_exact_account():
    value = resolve_tiktok_credential(lambda _: credential(), target(), now=NOW)
    request = account_request(value)
    assert TOKEN not in repr(value) and TOKEN not in repr(request)
    assert request.url.endswith('/v2/user/info/?fields=open_id') and not request.body
    assert request.headers['Authorization'] == 'Bearer ' + TOKEN
    result = confirm_account(response({'open_id': 'EXPLICIT_OPEN_ID', 'display_name': 'PRIVATE'}), target())
    assert result['account_match'] and result['source'] == 'tiktok.user.info.open_id'
    assert 'PRIVATE' not in str(result)


@pytest.mark.parametrize('scopes', [frozenset({PUBLISH}), frozenset({READ_ACCOUNT})], ids=['publish-only', 'read-only'])
def test_both_direct_publish_and_stable_account_scopes_required(scopes):
    with pytest.raises(PublishingCredentialError, match='SCOPES_REQUIRED'):
        resolve_tiktok_credential(lambda _: credential(scopes=scopes), target(), now=NOW)


@pytest.mark.parametrize('updates', [{'profile_version': 2}, {'target_account_id': 'OTHER'},
    {'credential_binding_sha256': 'b' * 64}], ids=['revision', 'account', 'credential-revision'])
def test_reviewed_credential_target_cannot_be_substituted(updates):
    with pytest.raises(PublishingCredentialError, match='TARGET_MISMATCH'):
        resolve_tiktok_credential(lambda _: credential(target=target(**updates)), target(), now=NOW)


@pytest.mark.parametrize('offset', [-1, 0, 90], ids=['expired', 'now', 'wire-window'])
def test_expiry_rejects_before_wire(offset):
    with pytest.raises(PublishingCredentialError, match='REFRESH_REQUIRED'):
        resolve_tiktok_credential(lambda _: credential(expires_at=NOW + timedelta(seconds=offset)), target(), now=NOW)


@pytest.mark.parametrize('updates', [{'scopes': frozenset({'video.upload', PUBLISH, READ_ACCOUNT})},
    {'token': 'SHORT'}, {'expires_at': NOW.replace(tzinfo=None)}, {'scopes': [PUBLISH, READ_ACCOUNT]},
    {'target': target(platform='youtube')}, {'target': target(provider_key='foreign-provider')},
    {'target': target().model_copy(update={'profile_version': True})}],
    ids=['unrelated-scope', 'token', 'naive-time', 'mutable-scopes', 'platform', 'provider', 'unchecked-target'])
def test_malformed_credential_rejected_without_private_details(updates):
    with pytest.raises(PublishingCredentialError, match='CREDENTIAL_INVALID') as caught: credential(**updates)
    assert TOKEN not in str(caught.value)


def test_private_resolver_errors_fixed():
    def bad(_): raise RuntimeError(TOKEN)
    for resolver in (bad, None, lambda _: TOKEN):
        with pytest.raises(PublishingCredentialError, match='NOT_CONFIGURED') as caught:
            resolve_tiktok_credential(resolver, target(), now=NOW)
        assert TOKEN not in str(caught.value)


@pytest.mark.parametrize('user', [{}, {'open_id': True}, {'open_id': 'OTHER'},
    {'username': 'EXPLICIT_OPEN_ID'}, [{'open_id': 'EXPLICIT_OPEN_ID'}]],
    ids=['missing', 'bool', 'foreign', 'username-is-not-open-id', 'collection'])
def test_account_identity_never_guessed(user):
    with pytest.raises(PublishingCredentialError, match='ACCOUNT_NOT_CONFIRMED'): confirm_account(response(user), target())


def test_error_envelope_is_not_account_verification():
    for result in (response({'open_id': 'EXPLICIT_OPEN_ID'}, error={'code': 'access_token_invalid', 'message': TOKEN}),
        OfficialResponse(401, {}, TOKEN.encode()), OfficialResponse(200, {}, b'not-json')):
        with pytest.raises(PublishingCredentialError, match='ACCOUNT_NOT_CONFIRMED') as caught: confirm_account(result, target())
        assert TOKEN not in str(caught.value)


@pytest.mark.asyncio
async def test_official_account_lookup_only_explicit_mock_and_no_username_guess():
    seen = []
    def handler(request):
        seen.append(request)
        assert request.url.host == 'open.tiktokapis.com' and request.url.params['fields'] == 'open_id'
        assert request.headers['authorization'] == 'Bearer ' + TOKEN
        return httpx.Response(200, json={'data': {'user': {'open_id': 'EXPLICIT_OPEN_ID'}}, 'error': {'code': 'ok'}})
    client = OfficialHTTPClient('tiktok', transport=httpx.MockTransport(handler))
    result = confirm_account(await client.request(account_request(credential())), target())
    assert result['account_match'] and len(seen) == 1
