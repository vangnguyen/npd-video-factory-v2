"""Dedicated in-memory TikTok OAuth and stable open-ID account admission."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .publishing_credentials import PublishingCredentialError, target_digest
from .publishing_models import PublishingTargetBinding
from .publishing_wire import OfficialRequest, OfficialResponse, bearer_headers

PUBLISH = 'video.publish'
READ_ACCOUNT = 'user.info.basic'
SCOPES = frozenset({PUBLISH, READ_ACCOUNT})


@dataclass(frozen=True)
class TikTokOAuthCredential:
    target: PublishingTargetBinding
    expires_at: datetime
    scopes: frozenset[str]
    token: str = field(repr=False)

    def __post_init__(self):
        try:
            if type(self.target) is not PublishingTargetBinding: raise ValueError()
            checked = PublishingTargetBinding.model_validate(self.target.model_dump())
            if (checked.platform != 'tiktok' or checked.provider_key != 'tiktok-content-posting-api'
                or type(self.expires_at) is not datetime or self.expires_at.tzinfo is None
                or type(self.scopes) is not frozenset or not self.scopes or not self.scopes <= SCOPES):
                raise ValueError()
            bearer_headers(self.token)
        except Exception:
            raise PublishingCredentialError('TIKTOK_OAUTH_CREDENTIAL_INVALID') from None


def resolve_tiktok_credential(resolver, target, *, now=None):
    try:
        target = PublishingTargetBinding.model_validate(target.model_dump())
        credential = resolver(target) if callable(resolver) else None
        if type(credential) is not TikTokOAuthCredential: raise ValueError()
        credential = TikTokOAuthCredential(credential.target, credential.expires_at, credential.scopes, credential.token)
    except Exception:
        raise PublishingCredentialError('TIKTOK_OAUTH_NOT_CONFIGURED') from None
    if target.platform != 'tiktok' or credential.target != target:
        raise PublishingCredentialError('TIKTOK_OAUTH_TARGET_MISMATCH')
    current = now or datetime.now(timezone.utc)
    if type(current) is not datetime or current.tzinfo is None or credential.expires_at <= current + timedelta(seconds=90):
        raise PublishingCredentialError('TIKTOK_OAUTH_REFRESH_REQUIRED')
    if credential.scopes != SCOPES: raise PublishingCredentialError('TIKTOK_OAUTH_SCOPES_REQUIRED')
    return credential


def account_request(credential):
    if type(credential) is not TikTokOAuthCredential: raise PublishingCredentialError('TIKTOK_OAUTH_CREDENTIAL_INVALID')
    # A mutable username/nickname is not the stable application-specific account ID.
    return OfficialRequest('GET', 'https://open.tiktokapis.com/v2/user/info/?fields=open_id',
        bearer_headers(credential.token))


def confirm_account(response, target):
    try:
        if type(response) is not OfficialResponse or response.status != 200 or type(target) is not PublishingTargetBinding:
            raise ValueError()
        checked = PublishingTargetBinding.model_validate(target.model_dump())
        if checked.platform != 'tiktok' or checked.provider_key != 'tiktok-content-posting-api': raise ValueError()
        value = response.json_object()
        if value.get('error', {}).get('code') != 'ok': raise ValueError()
        user = value['data']['user']
        if type(user) is not dict or type(user.get('open_id')) is not str or user['open_id'] != checked.target_account_id:
            raise ValueError()
    except Exception:
        raise PublishingCredentialError('TIKTOK_OAUTH_ACCOUNT_NOT_CONFIRMED') from None
    return {'target_account_id': checked.target_account_id, 'target_binding_sha256': target_digest(checked),
        'source': 'tiktok.user.info.open_id', 'account_match': True}
