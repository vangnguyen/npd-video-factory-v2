"""Immutable workspace-bound Vision key custody; no provider or startup decrypt."""
import hashlib, json, os, re, uuid
from pathlib import Path
from typing import Literal
from pydantic import Field, StrictInt, field_validator
from app.models import StrictModel
from .contracts import WorkflowError, digest, file_sha
from .backup import guard
from .official_account_tokens import protected_path, unique_pairs

PREFIX = b'VF-NATIVE-VISION-KEY-1\n'
ENTROPY = b'NPD-Video-Factory/native-vision-key/v1/'
MAX_FILE = 65536


class PrivateVisionKey(StrictModel):
    schema_version: Literal['native-vision-key-private-v1'] = 'native-vision-key-private-v1'
    workspace_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    credential_alias: str = Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    api_key: str = Field(min_length=8, max_length=4096, repr=False)

    @field_validator('api_key')
    @classmethod
    def opaque(cls, value):
        if not value.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError('Bounded private Vision key required')
        return value

    def fingerprint(self):
        return digest({'schema_version': self.schema_version, 'workspace_id': self.workspace_id,
            'credential_alias': self.credential_alias, 'key_sha256': hashlib.sha256(self.api_key.encode()).hexdigest()})


class VisionKeyReceipt(StrictModel):
    schema_version: Literal['native-vision-key-receipt-v1'] = 'native-vision-key-receipt-v1'
    reference: str = Field(pattern=r'^nviv_[a-f0-9]{32}$')
    workspace_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    credential_alias: str = Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    key_binding_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    cipher_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    bytes: StrictInt = Field(ge=1, le=MAX_FILE)
    key_returned: Literal[False] = False
    provider_authorized: Literal[False] = False
    publishing_enabled: Literal[False] = False

    @field_validator('key_returned', 'provider_authorized', 'publishing_enabled', mode='before')
    @classmethod
    def disabled(cls, value):
        if value is not False: raise ValueError('Raw disabled marker required')
        return value


class NativeVisionKeyVault:
    def __init__(self, directory, state_root, workspace):
        if not isinstance(workspace, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', workspace) or not Path(state_root).is_absolute():
            raise WorkflowError('NATIVE_VISION_KEY_CONFIGURATION_INVALID', 400)
        self.root = guard(Path(state_root)); self.directory = protected_path(directory, self.root); self.workspace = workspace
        if self.directory.exists() and not self.directory.is_dir():
            raise WorkflowError('NATIVE_VISION_KEY_CONFIGURATION_INVALID', 400)
        self._frozen = (self.root, self.directory, workspace)

    def check(self):
        if ((self.root, self.directory, self.workspace) != self._frozen or guard(self.root) != self.root
            or protected_path(self.directory, self.root) != self.directory):
            raise WorkflowError('NATIVE_VISION_KEY_CONFIGURATION_CHANGED')

    def receipt(self, value):
        self.check()
        try:
            parsed = VisionKeyReceipt.model_validate(value.model_dump(mode='json', warnings=False) if type(value) is VisionKeyReceipt else value)
            if parsed.workspace_id != self.workspace: raise ValueError()
            return parsed
        except Exception: raise WorkflowError('NATIVE_VISION_KEY_RECEIPT_INVALID', 400) from None

    def path(self, reference):
        self.check()
        if not isinstance(reference, str) or not re.fullmatch(r'nviv_[a-f0-9]{32}', reference):
            raise WorkflowError('NATIVE_VISION_KEY_REFERENCE_INVALID', 400)
        return protected_path(self.directory / (reference + '.dpapi'), self.root)

    def states(self):
        self.check()
        return {'schema_version': 'native-vision-key-vault-v1', 'workspace_id': self.workspace,
            'mounted': self.directory.is_dir(), 'startup_decryption': False, 'key_returned': False,
            'provider_authorized': False, 'publishing_enabled': False, 'real_provider_tested': False}

    def present(self, receipt):
        parsed = self.receipt(receipt); path = self.path(parsed.reference)
        try: return path.is_file() and path.stat().st_size == parsed.bytes and file_sha(path) == parsed.cipher_sha256
        except OSError: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_UNAVAILABLE', 503) from None

    def save(self, value):
        from .assemblyai_connection import _dpapi, _restrict_file
        self.check()
        try:
            parsed = PrivateVisionKey.model_validate(value.model_dump(mode='json', warnings=False) if type(value) is PrivateVisionKey else value)
            if parsed.workspace_id != self.workspace: raise ValueError()
        except Exception: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_INVALID', 400) from None
        reference = 'nviv_' + uuid.uuid4().hex; path = self.path(reference)
        envelope = {'schema_version': 'native-vision-key-envelope-v1', 'reference': reference,
            'workspace_id': self.workspace, 'credential_alias': parsed.credential_alias,
            'key_binding_sha256': parsed.fingerprint(), 'value': parsed.model_dump(mode='json')}
        raw = json.dumps(envelope, separators=(',', ':')).encode('utf-8')
        encrypted = PREFIX + _dpapi(raw, entropy=ENTROPY + self.workspace.encode('ascii'), description='Video Factory dedicated Vision key')
        if not 1 <= len(encrypted) <= MAX_FILE: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_SIZE_INVALID', 400)
        self.directory.mkdir(parents=True, exist_ok=True); self.check(); temporary = self.directory / ('.nviv-' + uuid.uuid4().hex + '.part')
        try:
            with temporary.open('xb') as handle:
                _restrict_file(temporary); handle.write(encrypted); handle.flush(); os.fsync(handle.fileno())
            self.check()
            if os.name != 'nt': raise WorkflowError('NATIVE_VISION_WINDOWS_KEY_STORAGE_REQUIRED', 503)
            os.rename(temporary, path)
        except FileExistsError: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_ALREADY_SAVED') from None
        except WorkflowError: raise
        except Exception: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_SAVE_FAILED', 503) from None
        finally: temporary.unlink(missing_ok=True)
        return VisionKeyReceipt(reference=reference, workspace_id=self.workspace, credential_alias=parsed.credential_alias,
            key_binding_sha256=parsed.fingerprint(), cipher_sha256=file_sha(path), bytes=path.stat().st_size).model_dump(mode='json')

    def key(self, receipt):
        from .assemblyai_connection import _dpapi
        parsed = self.receipt(receipt); path = self.path(parsed.reference)
        try:
            if not self.present(parsed): raise ValueError()
            raw = path.read_bytes()
            if not raw.startswith(PREFIX): raise ValueError()
            value = json.loads(_dpapi(raw[len(PREFIX):], decrypt=True, entropy=ENTROPY + self.workspace.encode('ascii')), object_pairs_hook=unique_pairs)
            if (set(value) != {'schema_version', 'reference', 'workspace_id', 'credential_alias', 'key_binding_sha256', 'value'}
                or value['schema_version'] != 'native-vision-key-envelope-v1'
                or any(value[name] != getattr(parsed, name) for name in ('reference', 'workspace_id', 'credential_alias', 'key_binding_sha256'))):
                raise ValueError()
            private = PrivateVisionKey.model_validate(value['value'])
            if private.workspace_id != self.workspace or private.credential_alias != parsed.credential_alias or private.fingerprint() != parsed.key_binding_sha256:
                raise ValueError()
            if not self.present(parsed): raise ValueError()
            self.check(); return private.api_key
        except Exception: raise WorkflowError('NATIVE_VISION_PRIVATE_KEY_UNAVAILABLE', 503) from None
