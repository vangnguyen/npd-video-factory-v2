"""Inert protected Meta Page account bindings; no startup decrypt or publish."""
import hashlib, json, os, re, uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from app.models import StrictModel
from app.meta_publishing_protocol import GraphTarget, numeric_id, api_version
from app.meta_publishing_credentials import MetaOAuthCredential, resolve_meta_credential, PROVIDERS
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.publishing_wire import OfficialHTTPClient, OfficialRequest
from .contracts import WorkflowError, digest, file_sha
from .official_account_tokens import protected_path, unique_pairs

PREFIX = b'VF-NATIVE-META-PUBLISHING-PAGE-ACCESS-1\n'
ENTROPY = b'NPD-Video-Factory/native-meta-page-publishing-access/v1'


class Profile(StrictModel):
    schema_version: Literal['native-meta-publishing-profile-v1'] = 'native-meta-publishing-profile-v1'
    target: PublishingTargetBinding
    page_id: str
    api_version: str
    login_type: Literal['facebook_login'] = 'facebook_login'

    @model_validator(mode='after')
    def scope(self):
        if self.target.platform not in PROVIDERS or self.target.provider_key != PROVIDERS[self.target.platform]:
            raise ValueError('Scoped Meta target required')
        numeric_id(self.page_id); api_version(self.api_version)
        GraphTarget(self.target.platform, self.target.target_account_id, self.api_version, self.login_type)
        if self.target.platform == 'facebook' and self.page_id != self.target.target_account_id:
            raise ValueError('Exact Page target required')
        return self

    def graph(self):
        return GraphTarget(self.target.platform, self.target.target_account_id, self.api_version, self.login_type)


class AccessToken(StrictModel):
    schema_version: Literal['native-meta-page-access-token-v1'] = 'native-meta-page-access-token-v1'
    profile: Profile
    credential_alias: str = Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    expires_at: datetime
    scopes: list[str] = Field(min_length=2, max_length=7)
    token: str = Field(min_length=16, max_length=4096, repr=False)

    @field_validator('expires_at', mode='before')
    @classmethod
    def aware(cls, value):
        if not isinstance(value, (str, datetime)): raise ValueError('Explicit aware expiry required')
        value = datetime.fromisoformat(value) if isinstance(value, str) else value
        if value.tzinfo is None: raise ValueError('Explicit aware expiry required')
        return value

    @model_validator(mode='after')
    def scope(self):
        if len(set(self.scopes)) != len(self.scopes): raise ValueError('Unique declared permissions required')
        self.credential()
        return self

    def credential(self):
        return MetaOAuthCredential(self.profile.target, self.profile.graph(), self.profile.page_id,
            self.expires_at, frozenset(self.scopes), self.token)


def save_token(path, root, value):
    from .assemblyai_connection import _dpapi, _restrict_file
    path = protected_path(path, root)
    try: parsed = AccessToken.model_validate(value)
    except Exception: raise WorkflowError('NATIVE_META_TOKEN_INVALID', 400) from None
    encrypted = PREFIX + _dpapi(parsed.model_dump_json().encode(), entropy=ENTROPY, description='Video Factory scoped Meta Page publishing access')
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / ('.native-meta-access-' + uuid.uuid4().hex + '.part')
    try:
        with temporary.open('xb') as handle:
            _restrict_file(temporary); handle.write(encrypted); handle.flush(); os.fsync(handle.fileno())
        if os.name != 'nt': raise WorkflowError('NATIVE_META_WINDOWS_CUSTODY_REQUIRED', 503)
        os.rename(temporary, path)
    except FileExistsError: raise WorkflowError('NATIVE_META_TOKEN_ALREADY_SAVED', 409) from None
    finally: temporary.unlink(missing_ok=True)
    return {'schema_version': 'native-meta-private-receipt-v1', 'profile': parsed.profile.model_dump(mode='json'),
        'credential_alias': parsed.credential_alias, 'cipher_sha256': file_sha(path), 'bytes': path.stat().st_size,
        'token_returned': False, 'publishing_enabled': False, 'external_calls': 0}


def load_token(path, root, profile, alias):
    from .assemblyai_connection import _dpapi
    try:
        path = protected_path(path, root)
        if not path.is_file() or not 1 <= path.stat().st_size <= 32768: raise ValueError()
        raw = path.read_bytes()
        if not raw.startswith(PREFIX): raise ValueError()
        parsed = AccessToken.model_validate(json.loads(_dpapi(raw[len(PREFIX):], decrypt=True, entropy=ENTROPY), object_pairs_hook=unique_pairs))
        if parsed.profile != profile or parsed.credential_alias != alias or path.read_bytes() != raw: raise ValueError()
        return parsed.credential()
    except Exception: raise WorkflowError('NATIVE_META_TOKEN_UNAVAILABLE', 503) from None


class Binding(StrictModel):
    account_ref: str = Field(pattern=r'^npac_[a-f0-9]{32}$')
    profile: Profile
    credential_alias: str = Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    token_file: str = Field(min_length=1, max_length=1000, repr=False)
    read_enabled: StrictBool = False
    publishing_enabled: Literal[False] = False

    @property
    def target(self): return self.profile.target

    @field_validator('publishing_enabled', mode='before')
    @classmethod
    def disabled(cls, value):
        if value is not False: raise ValueError('Separate publication authority required')
        return value


class Registry(StrictModel):
    schema_version: Literal['native-meta-account-registry-v1'] = 'native-meta-account-registry-v1'
    version: StrictInt = Field(ge=1, le=1)
    workspace_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    accounts: list[Binding] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def unique(self):
        if (any(a.target.workspace_id != self.workspace_id for a in self.accounts)
            or len({a.account_ref for a in self.accounts}) != len(self.accounts)
            or len({a.target.profile_id for a in self.accounts}) != len(self.accounts)):
            raise ValueError('Unique scoped Meta bindings required')
        return self


class MetaReadClient:
    def __init__(self, profile, *, enabled=False, transport=None):
        self.profile = profile
        self.wire = OfficialHTTPClient(profile.target.platform, network_enabled=enabled and transport is None, transport=transport)

    @property
    def mock(self): return self.wire.transport is not None

    @property
    def enabled(self): return self.mock or self.wire.network_enabled

    async def request(self, request):
        from urllib.parse import urlsplit, parse_qs
        if type(request) is not OfficialRequest: raise WorkflowError('NATIVE_META_READONLY_REQUEST_REQUIRED')
        parsed = urlsplit(request.url)
        paths = {f'/{self.profile.api_version}/me': 'id,instagram_business_account' if self.profile.target.platform == 'instagram_reels' else 'id'}
        if self.profile.target.platform == 'instagram_reels': paths[f'/{self.profile.api_version}/{self.profile.target.target_account_id}'] = 'id'
        if (type(request) is not OfficialRequest or request.method != 'GET' or request.body or parsed.hostname != 'graph.facebook.com'
            or parsed.path not in paths or parse_qs(parsed.query) != {'fields': [paths[parsed.path]]}):
            raise WorkflowError('NATIVE_META_READONLY_REQUEST_REQUIRED')
        return await self.wire.request(request)


class NativeMetaAccountFactory:
    def __init__(self, binding, root, workspace, *, owner_read_enabled=False, transport=None, registry_file=None, registry_sha256=None):
        if type(binding) is not Binding or type(owner_read_enabled) is not bool or binding.target.workspace_id != workspace:
            raise WorkflowError('NATIVE_META_CONFIGURATION_INVALID', 400)
        if (registry_file is None) != (registry_sha256 is None) or registry_sha256 is not None and (type(registry_sha256) is not str or not re.fullmatch('[a-f0-9]{64}', registry_sha256)):
            raise WorkflowError('NATIVE_META_CONFIGURATION_INVALID', 400)
        self.account = binding.model_copy(deep=True); self.profile = self.account.profile
        self.root = Path(root).absolute(); self.workspace = workspace; self.path = protected_path(binding.token_file, self.root)
        self.registry_file = protected_path(registry_file, self.root) if registry_file is not None else None; self.registry_sha256 = registry_sha256
        self.read_enabled = owner_read_enabled and binding.read_enabled
        self.client = MetaReadClient(self.profile, enabled=self.read_enabled, transport=transport)
        self.cipher_sha256 = file_sha(self.path) if self.path.is_file() and 0 < self.path.stat().st_size <= 32768 else None
        self.configuration = {'binding': self.account.model_dump(mode='json'), 'read_enabled': self.read_enabled, 'cipher_sha256': self.cipher_sha256,
            **({'registry_sha256': registry_sha256} if registry_sha256 is not None else {})}
        self.sha256 = digest(self.configuration)
        self.frozen = (self.root, workspace, self.path, self.registry_file, registry_sha256, self.read_enabled, self.client,
            self.client.wire, self.client.wire.transport, self.client.wire.network_enabled, self.cipher_sha256, self.sha256, digest(self.configuration))

    def check(self):
        try:
            parsed = Binding.model_validate(self.account.model_dump(mode='json'))
            config = {'binding': parsed.model_dump(mode='json'), 'read_enabled': self.read_enabled, 'cipher_sha256': self.cipher_sha256,
                **({'registry_sha256': self.registry_sha256} if self.registry_sha256 is not None else {})}
            if (type(self.account) is not Binding or self.profile is not self.account.profile or self.profile != parsed.profile
                or type(self.client) is not MetaReadClient or self.client.profile is not self.profile or type(self.client.wire) is not OfficialHTTPClient
                or self.client.wire.platform != parsed.target.platform or parsed.target.workspace_id != self.workspace or config != self.configuration
                or protected_path(parsed.token_file, self.root) != self.path
                or (self.root, self.workspace, self.path, self.registry_file, self.registry_sha256, self.read_enabled, self.client,
                    self.client.wire, self.client.wire.transport, self.client.wire.network_enabled, self.cipher_sha256, self.sha256, digest(self.configuration)) != self.frozen):
                raise ValueError()
            if self.registry_file is not None and (protected_path(self.registry_file, self.root) != self.registry_file
                or not self.registry_file.is_file() or not 1 <= self.registry_file.stat().st_size <= 262144 or file_sha(self.registry_file) != self.registry_sha256): raise ValueError()
        except Exception: raise WorkflowError('NATIVE_META_CONFIGURATION_CHANGED') from None
        return parsed

    def public(self):
        binding = self.check()
        mounted = self.cipher_sha256 is not None and self.path.is_file() and 0 < self.path.stat().st_size <= 32768 and file_sha(self.path) == self.cipher_sha256
        enabled = self.read_enabled and self.client.enabled and mounted
        return {'schema_version': 'native-meta-account-factory-v1', 'account_ref': binding.account_ref,
            'target': binding.target.model_dump(mode='json'), 'target_binding_sha256': target_digest(binding.target), 'configuration_sha256': self.sha256,
            'profile': self.profile.model_dump(mode='json'), 'cipher_sha256': self.cipher_sha256, 'credential_alias': binding.credential_alias,
            'status': 'CONFIGURED' if enabled else 'NOT_CONFIGURED', 'credential_present': mounted,
            'mode': 'fixture' if self.client.mock else 'official', 'external_reads_enabled': enabled and not self.client.mock,
            'credential_verified': False, 'account_verified': False, 'provider_permissions_verified': False,
            'app_eligibility_verified': False, 'publishing_enabled': False, 'token_returned': False, 'real_provider_tested': False}

    def credential(self, *, now=None):
        self.check()
        if self.public()['status'] != 'CONFIGURED': raise WorkflowError('NATIVE_META_ACCOUNT_READ_DISABLED')
        value = resolve_meta_credential(lambda _: load_token(self.path, self.root, self.profile, self.account.credential_alias),
            self.profile.target, self.profile.graph(), self.profile.page_id, now=now)
        if self.public()['status'] != 'CONFIGURED': raise WorkflowError('NATIVE_META_CONFIGURATION_CHANGED')
        return value


def load(path, root, workspace, *, owner_read_enabled=False):
    if type(owner_read_enabled) is not bool: raise WorkflowError('NATIVE_META_CONFIGURATION_INVALID', 400)
    path = protected_path(path, root)
    try:
        if not path.is_file() or not 1 <= path.stat().st_size <= 262144: raise ValueError()
        raw = path.read_bytes(); registry = Registry.model_validate(json.loads(raw, object_pairs_hook=unique_pairs)); checksum = hashlib.sha256(raw).hexdigest()
        if file_sha(path) != checksum or registry.workspace_id != workspace: raise ValueError()
    except Exception: raise WorkflowError('NATIVE_META_ACCOUNT_REGISTRY_INVALID', 400) from None
    return {a.account_ref: NativeMetaAccountFactory(a, root, workspace, owner_read_enabled=owner_read_enabled,
        registry_file=path, registry_sha256=checksum) for a in registry.accounts}
