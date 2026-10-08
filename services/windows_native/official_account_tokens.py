"""Domain-bound Windows OAuth access tokens outside Native state and backups.

No OAuth acquisition, refresh, API request or startup token read is performed.
The resolver can also be injected by an approved non-Windows secret service.
"""
import json,os,uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import Field,field_validator,model_validator
from . import ingestion
from .backup import guard
from .contracts import WorkflowError
from app.models import StrictModel
from app.publishing_wire import bearer_headers
from app.analytics_official import AnalyticsOAuthCredential,SCOPES

PREFIX=b'VF-NATIVE-OAUTH-ACCESS-1\n'
ENTROPY=b'NPD-Video-Factory/native-scoped-oauth-access-token/v1'

def unique_pairs(items):
    value={}
    for key,item in items:
        if key in value:raise ValueError('Duplicate protected key')
        value[key]=item
    return value

class AccessToken(StrictModel):
    schema_version:Literal['native-oauth-access-token-v1']='native-oauth-access-token-v1'
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    credential_binding_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    platform:Literal['youtube','tiktok']
    expires_at:datetime
    scopes:list[str]=Field(min_length=1,max_length=16)
    token:str=Field(min_length=16,max_length=4096,repr=False)

    @field_validator('expires_at',mode='before')
    @classmethod
    def time(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Explicit expiry required')
        parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
        if parsed.tzinfo is None:raise ValueError('Timezone required')
        return parsed

    @model_validator(mode='after')
    def valid(self):
        bearer_headers(self.token)
        if len(set(self.scopes))!=len(self.scopes) or not set(self.scopes)<=SCOPES[self.platform]:raise ValueError('Read scopes required')
        return self

def protected_path(path,root):
    if not Path(path).is_absolute():raise WorkflowError('NATIVE_OAUTH_ABSOLUTE_SECRET_PATH_REQUIRED',400)
    path=guard(Path(path))
    # Secret state cannot enter owned state backups or the source checkout.
    repository=Path(__file__).resolve().parents[2];state=Path(root).absolute()
    if path in (repository,state) or any(p in path.parents for p in (repository,state)):
        raise WorkflowError('NATIVE_OAUTH_SECRET_MUST_BE_OUTSIDE_SOURCE_STATE',400)
    return path

def save(path,root,value):
    """Explicit local operator primitive; refuses replacing an existing token."""
    from .assemblyai_connection import _dpapi,_restrict_file
    path=protected_path(path,root)
    try:parsed=AccessToken.model_validate(value)
    except Exception:raise WorkflowError('NATIVE_OAUTH_TOKEN_INVALID',400) from None
    raw=parsed.model_dump_json().encode();encrypted=PREFIX+_dpapi(raw,entropy=ENTROPY,description='Video Factory scoped OAuth access')
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.parent/('.native-oauth-'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('xb') as handle:
            _restrict_file(temporary);handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
        # Windows refuses replacing an existing destination atomically.
        if os.name!='nt':raise WorkflowError('NATIVE_OAUTH_WINDOWS_SECRET_STORAGE_REQUIRED',503)
        os.rename(temporary,path)
    except FileExistsError:raise WorkflowError('NATIVE_OAUTH_TOKEN_ALREADY_SAVED',409) from None
    finally:temporary.unlink(missing_ok=True)
    return {'schema_version':'native-oauth-secret-receipt-v1','workspace_id':parsed.workspace_id,
        'credential_alias':parsed.credential_alias,'credential_binding_sha256':parsed.credential_binding_sha256,
        'token_saved':True,'token_returned':False,'external_calls':0,'publishing_enabled':False}

def load(path,root,target,alias):
    from .assemblyai_connection import _dpapi
    try:
        path=protected_path(path,root)
        if not path.is_file() or path.stat().st_size>32768:raise ValueError()
        raw=path.read_bytes()
        if not raw.startswith(PREFIX):raise ValueError()
        decoded=_dpapi(raw[len(PREFIX):],decrypt=True,entropy=ENTROPY)
        parsed=AccessToken.model_validate(json.loads(decoded,object_pairs_hook=unique_pairs))
        if (parsed.workspace_id!=target.workspace_id or parsed.credential_alias!=alias or parsed.platform!=target.platform
            or parsed.credential_binding_sha256!=target.credential_binding_sha256):raise ValueError()
        return AnalyticsOAuthCredential(target,parsed.expires_at,frozenset(parsed.scopes),parsed.token)
    except Exception:raise WorkflowError('NATIVE_OAUTH_TOKEN_UNAVAILABLE',503) from None
