"""In-memory scoped OAuth admission and official account check; no secret acquisition."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from .publishing_models import PublishingTargetBinding
from .publishing_wire import OfficialRequest, OfficialResponse, bearer_headers

UPLOAD = 'https://www.googleapis.com/auth/youtube.upload'
READ = 'https://www.googleapis.com/auth/youtube.readonly'
FULL = 'https://www.googleapis.com/auth/youtube'
SSL = 'https://www.googleapis.com/auth/youtube.force-ssl'
ALLOWED_SCOPES = frozenset({UPLOAD, READ, FULL, SSL})


class PublishingCredentialError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def target_digest(target):
    return hashlib.sha256(json.dumps(target.model_dump(mode='json'), ensure_ascii=False,
        sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@dataclass(frozen=True)
class PublishingOAuthCredential:
    target: PublishingTargetBinding
    expires_at: datetime
    scopes: frozenset[str]
    token: str = field(repr=False)

    def __post_init__(self):
        try:
            if not isinstance(self.target, PublishingTargetBinding):
                raise ValueError()
            PublishingTargetBinding.model_validate(self.target.model_dump())
            if (not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None
                or type(self.scopes) is not frozenset or not self.scopes or not self.scopes <= ALLOWED_SCOPES):
                raise ValueError()
            bearer_headers(self.token)
        except Exception:
            raise PublishingCredentialError('PUBLISH_OAUTH_CREDENTIAL_INVALID') from None


def resolve_youtube_credential(resolver, target, *, now=None):
    """The resolver returns an already refreshed token; it is never written to a file/DB."""
    try:
        target = PublishingTargetBinding.model_validate(target.model_dump())
        credential = resolver(target) if callable(resolver) else None
        if not isinstance(credential, PublishingOAuthCredential):
            raise ValueError()
        # Reconstruct to reject unchecked mutation by trusted integration code.
        credential = PublishingOAuthCredential(credential.target, credential.expires_at, credential.scopes, credential.token)
    except Exception:
        raise PublishingCredentialError('PUBLISH_OAUTH_NOT_CONFIGURED') from None
    if target.platform != 'youtube' or credential.target != target:
        raise PublishingCredentialError('PUBLISH_OAUTH_TARGET_MISMATCH')
    current = now or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None or credential.expires_at <= current + timedelta(seconds=90):
        raise PublishingCredentialError('PUBLISH_OAUTH_REFRESH_REQUIRED')
    if not (credential.scopes & {UPLOAD, FULL, SSL}) or not (credential.scopes & {READ, FULL, SSL}):
        raise PublishingCredentialError('PUBLISH_OAUTH_SCOPES_REQUIRED')
    return credential


def youtube_account_request(credential):
    if not isinstance(credential, PublishingOAuthCredential) or credential.target.platform != 'youtube':
        raise PublishingCredentialError('PUBLISH_OAUTH_CREDENTIAL_INVALID')
    return OfficialRequest('GET', 'https://www.googleapis.com/youtube/v3/channels?part=id&mine=true&maxResults=2',
        bearer_headers(credential.token))


def confirm_youtube_account(response, target):
    """Exactly one authenticated channel must match. No guessed account or pagination fallback."""
    try:
        if not isinstance(response, OfficialResponse) or response.status != 200 or target.platform != 'youtube':
            raise ValueError()
        value = response.json_object(); items = value.get('items')
        if (not isinstance(items, list) or len(items) != 1 or not isinstance(items[0], dict)
            or not isinstance(items[0].get('id'), str) or not re.fullmatch('[A-Za-z0-9._~-]{1,128}', items[0]['id'])
            or items[0]['id'] != target.target_account_id or value.get('nextPageToken')):
            raise ValueError()
    except Exception:
        raise PublishingCredentialError('PUBLISH_OAUTH_ACCOUNT_NOT_CONFIRMED') from None
    return {'target_account_id': target.target_account_id, 'target_binding_sha256': target_digest(target),
        'source': 'youtube.channels.mine', 'account_match': True}
