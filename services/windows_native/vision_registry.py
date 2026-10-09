"""Frozen protected public Vision configuration; paid admission belongs to caller."""
import hashlib, json, re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal
import httpx
from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator
from app.models import StrictModel
from app.openai_vision_provider import OpenAIVisionProvider
from .contracts import WorkflowError, digest, file_sha
from .official_account_tokens import protected_path, unique_pairs
from .vision_credentials import NativeVisionKeyVault, VisionKeyReceipt
from .vision_frame_bridge import NativeEvidenceFrameExtractor


class VisionProfile(StrictModel):
    schema_version: Literal['native-vision-profile-v1'] = 'native-vision-profile-v1'
    profile_id: str = Field(pattern=r'^nvip_[a-f0-9]{32}$')
    enabled: StrictBool = False
    provider: Literal['openai-vision'] = 'openai-vision'
    model: Literal['gpt-5-mini'] = 'gpt-5-mini'
    key_receipt: VisionKeyReceipt
    estimated_cost_vnd: Decimal = Field(ge=0, le=1000000000000)
    input_vnd_per_million_tokens: Decimal = Field(ge=0, le=1000000000000)
    cached_input_vnd_per_million_tokens: Decimal = Field(ge=0, le=1000000000000)
    output_vnd_per_million_tokens: Decimal = Field(ge=0, le=1000000000000)

    @field_validator('estimated_cost_vnd', 'input_vnd_per_million_tokens', 'cached_input_vnd_per_million_tokens', 'output_vnd_per_million_tokens', mode='before')
    @classmethod
    def money(cls, value):
        if type(value) not in (str, int, Decimal): raise ValueError('Explicit finite VND amount required')
        try: amount = Decimal(value)
        except (InvalidOperation, ValueError): raise ValueError('Explicit finite VND amount required') from None
        if not amount.is_finite() or amount.as_tuple().exponent < -6: raise ValueError('Bounded finite VND amount required')
        return amount


class VisionRegistry(StrictModel):
    schema_version: Literal['native-vision-registry-v1'] = 'native-vision-registry-v1'
    version: StrictInt = Field(ge=1, le=1)
    workspace_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    profiles: list[VisionProfile] = Field(default_factory=list, max_length=8)

    @model_validator(mode='after')
    def bound(self):
        if (len({p.profile_id for p in self.profiles}) != len(self.profiles)
            or len({p.key_receipt.credential_alias for p in self.profiles}) != len(self.profiles)
            or any(p.key_receipt.workspace_id != self.workspace_id for p in self.profiles)):
            raise ValueError('Unique scoped Vision profiles required')
        return self


class NativeVisionFactory:
    def __init__(self, profile, vault, *, operator_enabled=False, transport=None, registry_file=None, registry_sha256=None):
        if (type(profile) is not VisionProfile or type(vault) is not NativeVisionKeyVault or type(operator_enabled) is not bool
            or transport is not None and type(transport) is not httpx.MockTransport
            or profile.key_receipt.workspace_id != vault.workspace
            or (registry_file is None) != (registry_sha256 is None)
            or registry_sha256 is not None and (not isinstance(registry_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', registry_sha256))):
            raise WorkflowError('NATIVE_VISION_FACTORY_CONFIGURATION_INVALID', 400)
        self.profile = profile.model_copy(deep=True); self.vault = vault; self.workspace = vault.workspace; self.root = vault.root
        self.operator_enabled = operator_enabled; self.transport = transport; self.mock = transport is not None
        self.registry_file = protected_path(registry_file, self.root) if registry_file is not None else None
        self.registry_sha256 = registry_sha256
        self._frozen = (vault, self.root, self.workspace, operator_enabled, transport, self.mock, self.registry_file, registry_sha256)
        self._profile = self.profile.model_dump(mode='json', warnings=False)
        self.sha256 = digest({'schema_version': 'native-vision-provider-configuration-v1', 'profile': self._profile,
            'operator_enabled': operator_enabled, 'mock': self.mock, 'registry_sha256': registry_sha256})
        self._sha256 = self.sha256
        self.check()

    def check(self):
        try:
            parsed = VisionProfile.model_validate(self.profile.model_dump(mode='json', warnings=False))
            if ((self.vault, self.root, self.workspace, self.operator_enabled, self.transport, self.mock, self.registry_file, self.registry_sha256) != self._frozen
                or parsed.model_dump(mode='json') != self._profile or self.sha256 != self._sha256
                or self.workspace != self.vault.workspace or self.root != self.vault.root
                or type(self.operator_enabled) is not bool or type(self.mock) is not bool or self.mock != (self.transport is not None)
                or self.transport is not None and type(self.transport) is not httpx.MockTransport):
                raise ValueError()
            self.vault.check()
            if self.registry_file is not None:
                if (protected_path(self.registry_file, self.root) != self.registry_file or not self.registry_file.is_file()
                    or not 1 <= self.registry_file.stat().st_size <= 262144 or file_sha(self.registry_file) != self.registry_sha256):
                    raise ValueError()
            return parsed
        except Exception: raise WorkflowError('NATIVE_VISION_FACTORY_CONFIGURATION_CHANGED') from None

    def public(self):
        p = self.check(); mounted = self.vault.present(p.key_receipt)
        costs = self.mock or p.estimated_cost_vnd > 0 and p.input_vnd_per_million_tokens > 0 and p.output_vnd_per_million_tokens > 0
        enabled = self.operator_enabled and p.enabled and mounted and costs
        return {'schema_version': 'native-vision-provider-configuration-v1', 'workspace_id': self.workspace,
            'profile': p.model_dump(mode='json'), 'configuration_sha256': self.sha256,
            'status': 'CONFIGURED' if enabled else 'NOT_CONFIGURED', 'mock': self.mock,
            'credential_present': mounted, 'credential_verified': False, 'startup_decryption': False,
            'source_frame_limit': 8, 'input_dimension_limit': 2048, 'provider_http_timeout_seconds': 90,
            'controller_hard_timeout_seconds': 120, 'max_output_tokens': 8000,
            'provider_authorized': False, 'automatic_dispatch': False, 'publishing_enabled': False, 'real_provider_tested': False}

    def provider(self, extractor):
        p = self.check()
        if self.public()['status'] != 'CONFIGURED': raise WorkflowError('NATIVE_VISION_PROVIDER_NOT_CONFIGURED')
        if (type(extractor) is not NativeEvidenceFrameExtractor or extractor.root != self.root
            or extractor.max_frames not in (1, 8)):
            raise WorkflowError('NATIVE_VISION_PROVIDER_INPUT_INVALID', 400)
        extractor.binding()
        def resolve(alias):
            current = self.check()
            if current.key_receipt.credential_alias != alias or self.public()['status'] != 'CONFIGURED':
                raise WorkflowError('NATIVE_VISION_PROVIDER_NOT_CONFIGURED')
            key = self.vault.key(current.key_receipt); self.check(); return key
        return OpenAIVisionProvider(credential_alias=p.key_receipt.credential_alias, credential_resolver=resolve,
            frame_extractor=extractor, estimated_cost_vnd=p.estimated_cost_vnd,
            input_vnd_per_million_tokens=p.input_vnd_per_million_tokens,
            cached_input_vnd_per_million_tokens=p.cached_input_vnd_per_million_tokens,
            output_vnd_per_million_tokens=p.output_vnd_per_million_tokens,
            transport=self.transport, allow_zero_cost_contract_test=self.mock)


def load(path, vault, *, operator_enabled=False):
    if type(vault) is not NativeVisionKeyVault or type(operator_enabled) is not bool:
        raise WorkflowError('NATIVE_VISION_REGISTRY_CONFIGURATION_INVALID', 400)
    path = protected_path(path, vault.root)
    try:
        if not path.is_file() or not 1 <= path.stat().st_size <= 262144: raise ValueError()
        raw = path.read_bytes(); value = VisionRegistry.model_validate(json.loads(raw, object_pairs_hook=unique_pairs))
        checksum = hashlib.sha256(raw).hexdigest()
        if value.workspace_id != vault.workspace or file_sha(path) != checksum: raise ValueError()
    except Exception: raise WorkflowError('NATIVE_VISION_REGISTRY_INVALID', 400) from None
    return {p.profile_id: NativeVisionFactory(p, vault, operator_enabled=operator_enabled,
        registry_file=path, registry_sha256=checksum) for p in value.profiles}
