"""Inert TikTok publisher credentials and creator-read bindings.

This connection never grants publication authority or sends at startup.
"""
import hashlib,json,os,re,uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.publishing_wire import OfficialHTTPClient
from app.tiktok_credentials import TikTokOAuthCredential,resolve_tiktok_credential,SCOPES
from app.tiktok_upload import MIN_CHUNK,DEFAULT_CHUNK
from .contracts import WorkflowError,digest,file_sha
from .official_account_tokens import protected_path,unique_pairs

PREFIX=b'VF-NATIVE-TIKTOK-PUBLISHING-ACCESS-1\n'
ENTROPY=b'NPD-Video-Factory/native-tiktok-publishing-access-token/v1'

class AccessToken(StrictModel):
    schema_version:Literal['native-tiktok-publishing-access-token-v1']='native-tiktok-publishing-access-token-v1'
    target:PublishingTargetBinding
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    expires_at:datetime
    scopes:list[str]=Field(min_length=2,max_length=2)
    token:str=Field(min_length=16,max_length=4096,repr=False)
    @field_validator('expires_at',mode='before')
    @classmethod
    def aware(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Explicit aware expiry required')
        parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
        if parsed.tzinfo is None:raise ValueError('Explicit aware expiry required')
        return parsed
    @model_validator(mode='after')
    def scoped(self):
        if len(set(self.scopes))!=2 or frozenset(self.scopes)!=SCOPES:raise ValueError('Dedicated publish/account scopes required')
        try:TikTokOAuthCredential(self.target,self.expires_at,frozenset(self.scopes),self.token)
        except Exception:raise ValueError('Dedicated TikTok credential required') from None
        return self

def save_token(path,root,value):
    from .assemblyai_connection import _dpapi,_restrict_file
    path=protected_path(path,root)
    try:parsed=AccessToken.model_validate(value)
    except Exception:raise WorkflowError('NATIVE_TIKTOK_TOKEN_INVALID',400) from None
    encrypted=PREFIX+_dpapi(parsed.model_dump_json().encode(),entropy=ENTROPY,description='Video Factory scoped TikTok publishing access')
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.parent/('.native-tiktok-access-'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('xb') as handle:_restrict_file(temporary);handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
        if os.name!='nt':raise WorkflowError('NATIVE_TIKTOK_WINDOWS_CUSTODY_REQUIRED',503)
        os.rename(temporary,path)
    except FileExistsError:raise WorkflowError('NATIVE_TIKTOK_TOKEN_ALREADY_SAVED',409) from None
    finally:temporary.unlink(missing_ok=True)
    return {'schema_version':'native-tiktok-private-receipt-v1','target':parsed.target.model_dump(mode='json'),'credential_alias':parsed.credential_alias,
        'cipher_sha256':file_sha(path),'bytes':path.stat().st_size,'token_returned':False,'publishing_enabled':False,'external_calls':0}

def load_token(path,root,target,alias):
    from .assemblyai_connection import _dpapi
    try:
        path=protected_path(path,root)
        if not path.is_file() or not 1<=path.stat().st_size<=32768:raise ValueError()
        raw=path.read_bytes()
        if not raw.startswith(PREFIX):raise ValueError()
        parsed=AccessToken.model_validate(json.loads(_dpapi(raw[len(PREFIX):],decrypt=True,entropy=ENTROPY),object_pairs_hook=unique_pairs))
        if parsed.target!=target or parsed.credential_alias!=alias or path.read_bytes()!=raw:raise ValueError()
        return TikTokOAuthCredential(parsed.target,parsed.expires_at,frozenset(parsed.scopes),parsed.token)
    except Exception:raise WorkflowError('NATIVE_TIKTOK_TOKEN_UNAVAILABLE',503) from None

class Profile(StrictModel):
    schema_version:Literal['native-tiktok-publishing-profile-v1']='native-tiktok-publishing-profile-v1'
    target:PublishingTargetBinding
    api_client_audited:StrictBool=False
    media_location:Literal['user_device']='user_device'
    chunk_size:StrictInt=Field(default=DEFAULT_CHUNK,ge=MIN_CHUNK,le=32*1024*1024)
    @model_validator(mode='after')
    def platform(self):
        if self.target.platform!='tiktok' or self.target.provider_key!='tiktok-content-posting-api':raise ValueError('Dedicated TikTok target required')
        return self

class Binding(StrictModel):
    profile:Profile
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    token_file:str=Field(min_length=1,max_length=1000,repr=False)
    creator_reads_enabled:StrictBool=False

class Registry(StrictModel):
    schema_version:Literal['native-tiktok-publishing-registry-v1']='native-tiktok-publishing-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    bindings:list[Binding]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if any(b.profile.target.workspace_id!=self.workspace_id for b in self.bindings) or len({b.profile.target.profile_id for b in self.bindings})!=len(self.bindings):raise ValueError('Unique scoped profiles required')
        return self

class NativeTikTokFactory:
    def __init__(self,binding,root,workspace,*,owner_read_enabled=False,transport=None,registry_file=None,registry_sha256=None):
        if type(binding) is not Binding or type(owner_read_enabled) is not bool or binding.profile.target.workspace_id!=workspace:raise WorkflowError('NATIVE_TIKTOK_CONFIGURATION_INVALID',400)
        if (registry_file is None)!=(registry_sha256 is None) or registry_sha256 is not None and (type(registry_sha256) is not str or not re.fullmatch('[a-f0-9]{64}',registry_sha256)):raise WorkflowError('NATIVE_TIKTOK_CONFIGURATION_INVALID',400)
        self.binding=binding.model_copy(deep=True);self.root=Path(root).absolute();self.workspace=workspace;self.profile=self.binding.profile
        self.path=protected_path(binding.token_file,self.root);self.registry_file=protected_path(registry_file,self.root) if registry_file is not None else None;self.registry_sha256=registry_sha256
        self.read_enabled=owner_read_enabled and binding.creator_reads_enabled
        self.client=OfficialHTTPClient('tiktok',network_enabled=self.read_enabled and transport is None,transport=transport)
        self.configuration={'binding':self.binding.model_dump(mode='json'),**({'registry_sha256':registry_sha256} if registry_sha256 is not None else {})};self.sha256=digest(self.configuration)
        self.frozen=(self.root,workspace,self.path,self.registry_file,registry_sha256,self.read_enabled,self.client,self.client.transport,self.client.network_enabled,self.sha256,digest(self.configuration))
    def check(self):
        try:
            parsed=Binding.model_validate(self.binding.model_dump(mode='json'))
            if (type(self.binding) is not Binding or self.profile!=parsed.profile or self.profile is not self.binding.profile or type(self.client) is not OfficialHTTPClient or self.client.platform!='tiktok'
                or (self.root,self.workspace,self.path,self.registry_file,self.registry_sha256,self.read_enabled,self.client,self.client.transport,self.client.network_enabled,self.sha256,digest(self.configuration))!=self.frozen
                or type(self.read_enabled) is not bool or parsed.profile.target.workspace_id!=self.workspace or protected_path(parsed.token_file,self.root)!=self.path
                or self.configuration!={'binding':parsed.model_dump(mode='json'),**({'registry_sha256':self.registry_sha256} if self.registry_sha256 is not None else {})}):raise ValueError()
            if self.registry_file is not None and (protected_path(self.registry_file,self.root)!=self.registry_file or not self.registry_file.is_file() or not 1<=self.registry_file.stat().st_size<=262144 or file_sha(self.registry_file)!=self.registry_sha256):raise ValueError()
        except Exception:raise WorkflowError('NATIVE_TIKTOK_CONFIGURATION_CHANGED') from None
        return parsed
    def public(self):
        binding=self.check();mounted=self.path.is_file() and 0<self.path.stat().st_size<=32768
        configured=self.read_enabled and mounted and (self.client.transport is not None or self.client.network_enabled is True)
        return {'schema_version':'native-tiktok-publishing-factory-v1','target':binding.profile.target.model_dump(mode='json'),'configuration_sha256':self.sha256,
            'target_binding_sha256':digest(binding.profile.target.model_dump(mode='json')),'credential_alias':binding.credential_alias,'credential_present':mounted,'credential_verified':False,
            'status':'READ_CONFIGURED' if configured else 'NOT_CONFIGURED','mock':self.client.transport is not None,'creator_reads_enabled':configured,
            'profile':binding.profile.model_dump(mode='json'),'token_returned':False,'publishing_enabled':False,'publication_dispatch_supported':False,'real_provider_tested':False}
    def cipher(self):
        self.check()
        if not self.path.is_file() or not 1<=self.path.stat().st_size<=32768:raise WorkflowError('NATIVE_TIKTOK_TOKEN_UNAVAILABLE',503)
        return file_sha(self.path)
    def credential(self,*,now,expected_cipher_sha256):
        self.check()
        if self.public()['status']!='READ_CONFIGURED':raise WorkflowError('NATIVE_TIKTOK_CREATOR_READ_DISABLED')
        if type(expected_cipher_sha256) is not str or not re.fullmatch('[a-f0-9]{64}',expected_cipher_sha256) or self.cipher()!=expected_cipher_sha256:raise WorkflowError('NATIVE_TIKTOK_CIPHER_CHANGED')
        credential=resolve_tiktok_credential(lambda target:load_token(self.path,self.root,target,self.binding.credential_alias),self.profile.target,now=now)
        self.check()
        if self.cipher()!=expected_cipher_sha256:raise WorkflowError('NATIVE_TIKTOK_CIPHER_CHANGED')
        return credential

def load(path,root,workspace,*,owner_read_enabled=False):
    if type(owner_read_enabled) is not bool:raise WorkflowError('NATIVE_TIKTOK_CONFIGURATION_INVALID',400)
    path=protected_path(path,root)
    try:
        if not path.is_file() or not 1<=path.stat().st_size<=262144:raise ValueError()
        raw=path.read_bytes();registry=Registry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));sha=hashlib.sha256(raw).hexdigest()
        if file_sha(path)!=sha:raise ValueError()
    except Exception:raise WorkflowError('NATIVE_TIKTOK_REGISTRY_INVALID',400) from None
    if registry.workspace_id!=workspace:raise WorkflowError('NATIVE_TIKTOK_WORKSPACE_MISMATCH',400)
    return {b.profile.target.profile_id:NativeTikTokFactory(b,root,workspace,owner_read_enabled=owner_read_enabled,registry_file=path,registry_sha256=sha) for b in registry.bindings}
