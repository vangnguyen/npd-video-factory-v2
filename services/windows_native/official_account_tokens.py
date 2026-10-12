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
from app import analytics_meta

PREFIX=b'VF-NATIVE-OAUTH-ACCESS-1\n'
ENTROPY=b'NPD-Video-Factory/native-scoped-oauth-access-token/v1'
META_PREFIX=b'VF-NATIVE-META-ANALYTICS-ACCESS-1\n'
META_ENTROPY=b'NPD-Video-Factory/native-scoped-meta-analytics-access-token/v1'

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
        allowed=analytics_meta.SCOPES[self.platform]|{'pages_show_list'} if self.platform in analytics_meta.PLATFORMS else SCOPES[self.platform]
        if len(set(self.scopes))!=len(self.scopes) or not set(self.scopes)<=allowed:raise ValueError('Read scopes required')
        return self


class MetaAccessToken(AccessToken):
    schema_version:Literal['native-meta-analytics-access-token-v1']='native-meta-analytics-access-token-v1'
    platform:Literal['instagram_reels','facebook']
    api_version:str=Field(pattern=r'^v[1-9][0-9]{0,2}\.0$')
    page_id:str=Field(pattern=r'^[1-9][0-9]{0,31}$')


def parse_token(value):
    if isinstance(value,StrictModel):value=value.model_dump(mode='python')
    if not isinstance(value,dict):raise ValueError('Explicit scoped token required')
    tag=value.get('schema_version','native-oauth-access-token-v1')
    if tag=='native-oauth-access-token-v1':return AccessToken.model_validate(value)
    if tag=='native-meta-analytics-access-token-v1':return MetaAccessToken.model_validate(value)
    raise ValueError('Unknown scoped token version')

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
    try:parsed=parse_token(value)
    except Exception:raise WorkflowError('NATIVE_OAUTH_TOKEN_INVALID',400) from None
    meta=type(parsed) is MetaAccessToken
    raw=parsed.model_dump_json().encode();encrypted=(META_PREFIX if meta else PREFIX)+_dpapi(raw,
        entropy=META_ENTROPY if meta else ENTROPY,description='Video Factory scoped Meta analytics access' if meta else 'Video Factory scoped OAuth access')
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

def load(path,root,target,alias,*,api_version=None,page_id=None):
    from .assemblyai_connection import _dpapi
    try:
        path=protected_path(path,root)
        if not path.is_file() or path.stat().st_size>32768:raise ValueError()
        raw=path.read_bytes()
        meta=target.platform in analytics_meta.PLATFORMS
        prefix=META_PREFIX if meta else PREFIX
        if not raw.startswith(prefix):raise ValueError()
        decoded=_dpapi(raw[len(prefix):],decrypt=True,entropy=META_ENTROPY if meta else ENTROPY)
        parsed=parse_token(json.loads(decoded,object_pairs_hook=unique_pairs))
        if (type(parsed) is MetaAccessToken) is not meta or path.read_bytes()!=raw:raise ValueError()
        if (parsed.workspace_id!=target.workspace_id or parsed.credential_alias!=alias or parsed.platform!=target.platform
            or parsed.credential_binding_sha256!=target.credential_binding_sha256):raise ValueError()
        if meta:
            if parsed.api_version!=api_version or parsed.page_id!=page_id:raise ValueError()
            return analytics_meta.MetaAnalyticsCredential(target,parsed.api_version,parsed.page_id,
                parsed.expires_at,frozenset(parsed.scopes),parsed.token)
        return AnalyticsOAuthCredential(target,parsed.expires_at,frozenset(parsed.scopes),parsed.token)
    except Exception:raise WorkflowError('NATIVE_OAUTH_TOKEN_UNAVAILABLE',503) from None
