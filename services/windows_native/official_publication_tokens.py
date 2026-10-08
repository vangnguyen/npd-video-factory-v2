"""Separate scoped publishing OAuth secrets; no acquisition/refresh/wire calls."""
import json,os,uuid
from datetime import datetime
from pydantic import Field,field_validator,model_validator
from typing import Literal
from .official_account_tokens import protected_path,unique_pairs
from .contracts import WorkflowError
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import PublishingOAuthCredential,ALLOWED_SCOPES,UPLOAD,READ,FULL,SSL

PREFIX=b'VF-NATIVE-PUBLISHING-OAUTH-ACCESS-1\n'
ENTROPY=b'NPD-Video-Factory/native-scoped-publishing-oauth-access-token/v1'

class AccessToken(StrictModel):
    schema_version:Literal['native-publishing-oauth-access-token-v1']='native-publishing-oauth-access-token-v1'
    target:PublishingTargetBinding
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    expires_at:datetime
    scopes:list[str]=Field(min_length=1,max_length=4)
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
        if self.target.platform!='youtube' or self.target.provider_key!='youtube-data-api-publishing' or len(set(self.scopes))!=len(self.scopes) or not set(self.scopes)<=ALLOWED_SCOPES:raise ValueError('Scoped publishing credential required')
        if not set(self.scopes)&{UPLOAD,FULL,SSL} or not set(self.scopes)&{READ,FULL,SSL}:raise ValueError('Explicit upload and account read permissions required')
        PublishingOAuthCredential(self.target,self.expires_at,frozenset(self.scopes),self.token)
        return self

def save(path,root,value):
    """Explicit local operator primitive; never overwrites a protected token."""
    from .assemblyai_connection import _dpapi,_restrict_file
    path=protected_path(path,root)
    try:parsed=AccessToken.model_validate(value)
    except Exception:raise WorkflowError('NATIVE_PUBLISH_OAUTH_TOKEN_INVALID',400) from None
    encrypted=PREFIX+_dpapi(parsed.model_dump_json().encode(),entropy=ENTROPY,description='Video Factory scoped publishing OAuth access')
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.parent/('.native-publish-oauth-'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('xb') as handle:_restrict_file(temporary);handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
        if os.name!='nt':raise WorkflowError('NATIVE_PUBLISH_OAUTH_WINDOWS_STORAGE_REQUIRED',503)
        os.rename(temporary,path)
    except FileExistsError:raise WorkflowError('NATIVE_PUBLISH_OAUTH_TOKEN_ALREADY_SAVED',409) from None
    finally:temporary.unlink(missing_ok=True)
    return {'schema_version':'native-publishing-oauth-secret-receipt-v1','target':parsed.target.model_dump(mode='json'),'credential_alias':parsed.credential_alias,
        'token_saved':True,'token_returned':False,'external_calls':0,'publishing_enabled':False}

def load(path,root,target,alias):
    from .assemblyai_connection import _dpapi
    try:
        path=protected_path(path,root)
        if not path.is_file() or not 1<=path.stat().st_size<=32768:raise ValueError()
        raw=path.read_bytes()
        if not raw.startswith(PREFIX):raise ValueError()
        parsed=AccessToken.model_validate(json.loads(_dpapi(raw[len(PREFIX):],decrypt=True,entropy=ENTROPY),object_pairs_hook=unique_pairs))
        if parsed.target!=target or parsed.credential_alias!=alias:raise ValueError()
        return PublishingOAuthCredential(parsed.target,parsed.expires_at,frozenset(parsed.scopes),parsed.token)
    except Exception:raise WorkflowError('NATIVE_PUBLISH_OAUTH_TOKEN_UNAVAILABLE',503) from None
