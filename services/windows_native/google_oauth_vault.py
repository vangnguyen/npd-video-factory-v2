"""Immutable domain-bound private OAuth custody; no callback claim or provider call.

Every decrypt is explicit. Current human authority, one-use operation claims,
credential selection, cost audit and production approval belong to the caller.
"""
import json,os,re,uuid
from datetime import datetime
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from . import ingestion
from .contracts import WorkflowError,file_sha,digest
from .official_account_tokens import protected_path,unique_pairs
from .backup import guard
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.google_oauth_protocol import GoogleDesktopClient,GoogleAuthorization,GoogleOAuthGrant,instant,opaque,loopback

PREFIX=b'VF-NATIVE-GOOGLE-OAUTH-PRIVATE-1\n'
MAX_FILE=65536
ENTROPY=b'NPD-Video-Factory/native-google-oauth-private/v1/'

class Aware(StrictModel):
    @field_validator('*',mode='before',check_fields=False)
    @classmethod
    def aware_fields(cls,value,info):
        if info.field_name in ('created_at','expires_at','obtained_at','refresh_expires_at') and value is not None:
            if not isinstance(value,(str,datetime)):raise ValueError('Explicit aware time required')
            instant(datetime.fromisoformat(value) if isinstance(value,str) else value)
        return value

class PrivateClient(StrictModel):
    schema_version:Literal['native-google-oauth-client-private-v1']='native-google-oauth-client-private-v1'
    target:PublishingTargetBinding
    purpose:Literal['analytics','publishing']
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    client_id:str=Field(min_length=1,max_length=256)
    scopes:list[str]=Field(min_length=2,max_length=3)
    client_secret:str|None=Field(default=None,repr=False)
    @model_validator(mode='after')
    def valid(self):
        if len(self.scopes)!=len(set(self.scopes)):raise ValueError('Distinct scopes required')
        self.client();return self
    def client(self):return GoogleDesktopClient(self.target,self.purpose,self.client_id,frozenset(self.scopes),self.client_secret)

class SecretReceipt(StrictModel):
    schema_version:Literal['native-google-oauth-private-receipt-v1']='native-google-oauth-private-receipt-v1'
    reference:str=Field(pattern=r'^nogv_[a-f0-9]{32}$')
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    kind:Literal['client','authorization','grant']
    purpose:Literal['analytics','publishing']
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    target_binding_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    cipher_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    bytes:StrictInt=Field(ge=1,le=MAX_FILE)
    token_returned:Literal[False]=False
    publishing_enabled:Literal[False]=False
    @field_validator('token_returned','publishing_enabled',mode='before')
    @classmethod
    def disabled(cls,v):
        if v is not False:raise ValueError('Raw disabled marker required')
        return v

class PrivateAuthorization(Aware):
    schema_version:Literal['native-google-oauth-authorization-private-v1']='native-google-oauth-authorization-private-v1'
    client:SecretReceipt
    redirect_uri:str=Field(min_length=1,max_length=256)
    created_at:datetime
    expires_at:datetime
    state:str=Field(repr=False)
    verifier:str=Field(repr=False)
    @model_validator(mode='after')
    def valid(self):
        if self.client.kind!='client' or not opaque(self.state,43,128) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',self.verifier):raise ValueError('Bound private authorization required')
        loopback(self.redirect_uri)
        if not 0<(self.expires_at-self.created_at).total_seconds()<=900:raise ValueError('Bounded authorization window required')
        return self

class PrivateGrant(Aware):
    schema_version:Literal['native-google-oauth-grant-private-v1']='native-google-oauth-grant-private-v1'
    client:SecretReceipt
    target:PublishingTargetBinding
    purpose:Literal['analytics','publishing']
    scopes:list[str]=Field(min_length=2,max_length=3)
    obtained_at:datetime
    expires_at:datetime
    refresh_expires_at:datetime|None
    mock:StrictBool
    access_token:str=Field(repr=False)
    refresh_token:str=Field(repr=False)
    previous:SecretReceipt|None=None
    @model_validator(mode='after')
    def valid(self):
        if (self.client.kind!='client' or self.client.purpose!=self.purpose or self.client.workspace_id!=self.target.workspace_id
            or self.client.target_binding_sha256!=target_digest(self.target) or len(self.scopes)!=len(set(self.scopes))
            or not 0<(self.expires_at-self.obtained_at).total_seconds()<=86400 or self.refresh_expires_at is not None and self.refresh_expires_at<=self.obtained_at
            or not opaque(self.access_token) or not opaque(self.refresh_token)):raise ValueError('Bound private grant required')
        if self.previous is not None and (self.previous.kind!='grant' or any(getattr(self.previous,k)!=getattr(self.client,k) for k in ('workspace_id','purpose','credential_alias','configuration_sha256','target_binding_sha256'))):raise ValueError('Same-purpose prior grant required')
        return self

class NativeGoogleOAuthVault:
    def __init__(self,directory,state_root,workspace):
        if not isinstance(workspace,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',workspace):raise WorkflowError('NATIVE_GOOGLE_OAUTH_VAULT_CONFIGURATION_INVALID',400)
        if not Path(state_root).is_absolute():raise WorkflowError('NATIVE_GOOGLE_OAUTH_VAULT_CONFIGURATION_INVALID',400)
        self.root=guard(Path(state_root));self.directory=protected_path(directory,self.root);self.workspace=workspace
        self.frozen=(self.root,self.directory,workspace)
    def check(self):
        if (self.root,self.directory,self.workspace)!=self.frozen or guard(self.root)!=self.root or protected_path(self.directory,self.root)!=self.directory:raise WorkflowError('NATIVE_GOOGLE_OAUTH_VAULT_CONFIGURATION_CHANGED')
    def states(self):
        self.check()
        return {'schema_version':'native-google-oauth-vault-v1','workspace_id':self.workspace,'mounted':self.directory.is_dir(),
            'startup_decryption':False,'token_returned':False,'publishing_enabled':False,'automatic_refresh':False,'account_verified':False,'real_provider_tested':False}
    def receipt(self,value,kind=None):
        try:parsed=SecretReceipt.model_validate(value.model_dump(mode='json',warnings=False) if type(value) is SecretReceipt else value)
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_RECEIPT_INVALID',400) from None
        self.check()
        if parsed.workspace_id!=self.workspace or kind is not None and parsed.kind!=kind:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_BINDING_CHANGED')
        return parsed
    def path(self,reference):
        self.check()
        if not isinstance(reference,str) or not re.fullmatch(r'nogv_[a-f0-9]{32}',reference):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_REFERENCE_INVALID',400)
        return protected_path(self.directory/(reference+'.dpapi'),self.root)
    def entropy(self,kind,purpose):return ENTROPY+(kind+'/'+purpose+'/'+self.workspace).encode('ascii')
    def _save(self,kind,value,client):
        from .assemblyai_connection import _dpapi,_restrict_file
        self.check()
        try:
            cls={'client':PrivateClient,'authorization':PrivateAuthorization,'grant':PrivateGrant}[kind]
            if type(value) is not cls or type(client) is not PrivateClient:raise ValueError()
            value=cls.model_validate(value.model_dump(mode='json',warnings=False));client=PrivateClient.model_validate(client.model_dump(mode='json',warnings=False))
            if client.target.workspace_id!=self.workspace:raise ValueError()
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_FIELDS_INVALID',400) from None
        public=client.client();reference='nogv_'+uuid.uuid4().hex;path=self.path(reference)
        envelope={'schema_version':'native-google-oauth-private-envelope-v1','reference':reference,'workspace_id':self.workspace,'kind':kind,'purpose':client.purpose,
            'configuration_sha256':public.fingerprint(),'target_binding_sha256':target_digest(client.target),'credential_alias':client.credential_alias,'value':value.model_dump(mode='json',warnings=False)}
        raw=json.dumps(envelope,separators=(',',':')).encode('utf-8')
        if len(raw)>32768:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_SIZE_LIMIT',400)
        encrypted=PREFIX+_dpapi(raw,entropy=self.entropy(kind,client.purpose),description='Video Factory dedicated Google OAuth')
        if not 1<=len(encrypted)<=MAX_FILE:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_SIZE_LIMIT',400)
        self.directory.mkdir(parents=True,exist_ok=True);self.check();temporary=self.directory/('.nogv-'+uuid.uuid4().hex+'.part')
        try:
            with temporary.open('xb') as h:_restrict_file(temporary);h.write(encrypted);h.flush();os.fsync(h.fileno())
            self.check()
            if os.name!='nt':raise WorkflowError('NATIVE_GOOGLE_OAUTH_WINDOWS_STORAGE_REQUIRED',503)
            os.rename(temporary,path)
        except FileExistsError:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_ALREADY_SAVED',409) from None
        except WorkflowError:raise
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_SAVE_FAILED',503) from None
        finally:temporary.unlink(missing_ok=True)
        return SecretReceipt(reference=reference,workspace_id=self.workspace,kind=kind,purpose=client.purpose,credential_alias=client.credential_alias,
            configuration_sha256=public.fingerprint(),target_binding_sha256=target_digest(client.target),cipher_sha256=file_sha(path),bytes=path.stat().st_size).model_dump(mode='json')
    def _load(self,receipt,kind):
        from .assemblyai_connection import _dpapi
        receipt=self.receipt(receipt,kind);path=self.path(receipt.reference)
        try:
            if not path.is_file() or path.stat().st_size!=receipt.bytes or file_sha(path)!=receipt.cipher_sha256:raise ValueError()
            encrypted=path.read_bytes()
            if not encrypted.startswith(PREFIX):raise ValueError()
            decoded=_dpapi(encrypted[len(PREFIX):],decrypt=True,entropy=self.entropy(kind,receipt.purpose))
            envelope=json.loads(decoded,object_pairs_hook=unique_pairs)
            if set(envelope)!={'schema_version','reference','workspace_id','kind','purpose','configuration_sha256','target_binding_sha256','credential_alias','value'} or envelope['schema_version']!='native-google-oauth-private-envelope-v1' or any(envelope[k]!=getattr(receipt,k) for k in ('reference','workspace_id','kind','purpose','configuration_sha256','target_binding_sha256','credential_alias')):raise ValueError()
            parsed={'client':PrivateClient,'authorization':PrivateAuthorization,'grant':PrivateGrant}[kind].model_validate(envelope['value'])
            if kind=='client':
                if parsed.target.workspace_id!=receipt.workspace_id or parsed.purpose!=receipt.purpose or parsed.credential_alias!=receipt.credential_alias or parsed.client().fingerprint()!=receipt.configuration_sha256 or target_digest(parsed.target)!=receipt.target_binding_sha256:raise ValueError()
            elif any(getattr(parsed.client,k)!=getattr(receipt,k) for k in ('workspace_id','purpose','credential_alias','configuration_sha256','target_binding_sha256')):raise ValueError()
            if path.stat().st_size!=receipt.bytes or file_sha(path)!=receipt.cipher_sha256:raise ValueError()
            self.check();return parsed
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_UNAVAILABLE',503) from None
    def save_client(self,value):
        try:
            parsed=PrivateClient.model_validate(value.model_dump(mode='json',warnings=False) if type(value) is PrivateClient else value)
            if parsed.target.workspace_id!=self.workspace:raise ValueError()
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CLIENT_INVALID',400) from None
        return self._save('client',parsed,parsed)
    def client(self,receipt):
        value=self._load(receipt,'client');r=self.receipt(receipt,'client')
        if value.target.workspace_id!=self.workspace or value.purpose!=r.purpose or value.credential_alias!=r.credential_alias or value.client().fingerprint()!=r.configuration_sha256 or target_digest(value.target)!=r.target_binding_sha256:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_BINDING_CHANGED')
        return value.client()
    def save_authorization(self,flow,client_receipt):
        try:
            r=self.receipt(client_receipt,'client');client=self._load(r,'client');expected=self.client(r)
            if type(flow) is not GoogleAuthorization or flow.configuration_sha256!=expected.fingerprint() or flow.client.fingerprint()!=expected.fingerprint():raise ValueError()
            # Preserve the finite intent even after expiry; admission belongs to the caller.
            value=PrivateAuthorization(client=r,redirect_uri=flow.redirect_uri,created_at=flow.created_at,expires_at=flow.expires_at,state=flow.state,verifier=flow.verifier)
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_AUTHORIZATION_BINDING_INVALID',400) from None
        return self._save('authorization',value,client)
    def authorization(self,receipt):
        value=self._load(receipt,'authorization');r=self.receipt(receipt,'authorization');c=self.client(value.client)
        if c.fingerprint()!=r.configuration_sha256 or target_digest(c.target)!=r.target_binding_sha256 or c.purpose!=r.purpose:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_BINDING_CHANGED')
        return GoogleAuthorization(c,r.configuration_sha256,value.redirect_uri,value.created_at,value.expires_at,value.state,value.verifier)
    def save_grant(self,grant,client_receipt,*,previous=None):
        try:
            r=self.receipt(client_receipt,'client');private=self._load(r,'client');c=self.client(r)
            if type(grant) is not GoogleOAuthGrant:raise ValueError()
            grant.check(c);old=self.receipt(previous,'grant') if previous is not None else None
            if old is not None:
                original=self.grant(old)
                if original.configuration_sha256!=grant.configuration_sha256 or original.mock is not grant.mock or grant.obtained_at<original.obtained_at or original.refresh_expires_at is not None and (grant.refresh_expires_at is None or grant.refresh_expires_at>original.refresh_expires_at):raise ValueError()
            value=PrivateGrant(client=r,target=grant.target,purpose=grant.purpose,scopes=sorted(grant.scopes),obtained_at=grant.obtained_at,expires_at=grant.expires_at,
                refresh_expires_at=grant.refresh_expires_at,mock=grant.mock,access_token=grant.access_token,refresh_token=grant.refresh_token,previous=old)
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_GRANT_BINDING_INVALID',400) from None
        return self._save('grant',value,private)
    def grant(self,receipt):
        value=self._load(receipt,'grant');r=self.receipt(receipt,'grant');c=self.client(value.client)
        grant=GoogleOAuthGrant(value.target,value.purpose,r.configuration_sha256,frozenset(value.scopes),value.obtained_at,value.expires_at,value.refresh_expires_at,value.mock,value.access_token,value.refresh_token)
        try:grant.check(c)
        except Exception:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PRIVATE_BINDING_CHANGED') from None
        return grant
