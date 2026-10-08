"""Protected public Desktop client-slot registry; never decrypts at startup."""
import hashlib,json
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,model_validator
from app.models import StrictModel
from .google_oauth_operations import Slot
from .official_account_tokens import protected_path,unique_pairs
from .contracts import WorkflowError,file_sha

class Registry(StrictModel):
    schema_version:Literal['native-google-oauth-registry-v1']='native-google-oauth-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    token_exchange_enabled:StrictBool=False
    slots:list[Slot]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if any(s.target.workspace_id!=self.workspace_id for s in self.slots) or len({s.slot_id for s in self.slots})!=len(self.slots) or len({(s.target.profile_id,s.target.profile_version,s.client.purpose) for s in self.slots})!=len(self.slots):raise ValueError('Unique workspace/purpose client slots required')
        return self

def load(path,root,workspace):
    path=protected_path(path,root)
    if not path.is_file() or not 1<=path.stat().st_size<=262144:raise WorkflowError('NATIVE_GOOGLE_OAUTH_REGISTRY_INVALID',400)
    try:
        raw=path.read_bytes();registry=Registry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));checksum=hashlib.sha256(raw).hexdigest()
        if protected_path(path,root)!=path or file_sha(path)!=checksum:raise ValueError()
    except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_REGISTRY_INVALID',400) from None
    if registry.workspace_id!=workspace:raise WorkflowError('NATIVE_GOOGLE_OAUTH_WORKSPACE_MISMATCH',400)
    return registry,path,checksum
