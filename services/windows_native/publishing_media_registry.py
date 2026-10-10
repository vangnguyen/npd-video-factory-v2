"""Protected, default-off publishing object delivery; no startup SDK/key decode."""
import hashlib,json
from datetime import datetime
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.models import StrictModel
from app.publishing_media_delivery import StorageProfile
from .contracts import WorkflowError,file_sha
from .official_account_tokens import protected_path,unique_pairs
from .publishing_media_delivery import NativeMediaDeliveryFactory


class Profile(StrictModel):
    endpoint_url:str=Field(min_length=1,max_length=2048)
    bucket:str=Field(min_length=3,max_length=63)
    region:str=Field(min_length=1,max_length=64)
    credential_alias:str=Field(min_length=4,max_length=80)
    public_endpoint_url:str|None=Field(default=None,max_length=2048)
    def resolved(self):return StorageProfile(**self.model_dump(mode='python'))
    @model_validator(mode='after')
    def valid(self):self.resolved();return self


class Registry(StrictModel):
    schema_version:Literal['native-publishing-media-registry-v1']='native-publishing-media-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    enabled:StrictBool=False
    storage_profile:Profile
    lease_directory:str=Field(min_length=1,max_length=4096)
    credential_file:str|None=Field(default=None,max_length=4096)
    credential_expires_at:datetime|None=None
    estimated_operation_cost_vnd:StrictInt|None=Field(default=None,ge=1,le=10**9)
    @field_validator('credential_expires_at',mode='before')
    @classmethod
    def time(cls,value):
        if value is None:return value
        if not isinstance(value,(str,datetime)):raise ValueError('Explicit aware credential expiry required')
        parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
        if parsed.tzinfo is None:raise ValueError('Explicit aware credential expiry required')
        return parsed
    @model_validator(mode='after')
    def pair(self):
        if (self.credential_file is None)!=(self.credential_expires_at is None):raise ValueError('Bound credential path/expiry required')
        return self


def load(path,root,workspace,*,owner_enabled=False):
    if type(owner_enabled) is not bool:raise WorkflowError('NATIVE_MEDIA_RUNTIME_CONFIGURATION_INVALID',400)
    path=protected_path(path,root)
    try:
        if not path.is_file() or not 1<=path.stat().st_size<=262144:raise ValueError()
        raw=path.read_bytes();registry=Registry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));sha=hashlib.sha256(raw).hexdigest()
        if file_sha(path)!=sha or registry.workspace_id!=workspace:raise ValueError()
        factory=NativeMediaDeliveryFactory(registry.storage_profile.resolved(),root,workspace,enabled=owner_enabled and registry.enabled,
            directory=registry.lease_directory,credential_file=registry.credential_file,credential_expires_at=registry.credential_expires_at,
            estimated_operation_cost_vnd=registry.estimated_operation_cost_vnd,registry_file=path,registry_sha256=sha)
        factory.check();return factory
    except Exception:raise WorkflowError('NATIVE_MEDIA_RUNTIME_REGISTRY_INVALID',400) from None
