"""Protected public account bindings; calls and token reads are explicit only."""
import hashlib,json,re
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from . import ingestion
from .contracts import WorkflowError,digest,file_sha
from .official_account_tokens import protected_path,unique_pairs,load as token_load
from app.models import StrictModel
from app.publishing_models import PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.analytics_official import AnalyticsHTTPClient,resolve_credential,SCOPES
from app.publishing_wire import OfficialHTTPClient

class Account(StrictModel):
    account_ref:str=Field(pattern=r'^npac_[a-f0-9]{32}$')
    target:PublishingTargetBinding
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    token_file:str=Field(min_length=1,max_length=1000,repr=False)
    read_enabled:StrictBool=False
    publishing_enabled:Literal[False]=False

    @field_validator('publishing_enabled',mode='before')
    @classmethod
    def disabled(cls,value):
        if value is not False:raise ValueError('Publishing must remain explicitly disabled')
        return value

    @model_validator(mode='after')
    def bounded(self):
        expected={'youtube':'youtube-data-api-publishing','tiktok':'tiktok-content-posting-api'}
        if self.target.platform not in SCOPES or self.target.provider_key!=expected[self.target.platform]:raise ValueError('Supported official account contract required')
        if self.publishing_enabled is not False:raise ValueError('Publishing remains disabled')
        return self

class OAuthAccount(StrictModel):
    account_ref:str=Field(pattern=r'^npac_[a-f0-9]{32}$')
    target:PublishingTargetBinding
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    credential_source:Literal['google_oauth_selection']
    google_oauth_slot_id:str=Field(pattern=r'^ngos_[a-f0-9]{32}$')
    read_enabled:StrictBool=False
    publishing_enabled:Literal[False]=False
    @field_validator('publishing_enabled',mode='before')
    @classmethod
    def disabled(cls,value):
        if value is not False:raise ValueError('Publishing must remain explicitly disabled')
        return value
    @model_validator(mode='after')
    def bounded(self):
        if self.target.platform!='youtube' or self.target.provider_key!='youtube-data-api-publishing':raise ValueError('Dedicated Google analytics account required')
        return self

class Registry(StrictModel):
    schema_version:Literal['native-official-account-registry-v1']='native-official-account-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    accounts:list[Account|OAuthAccount]=Field(default_factory=list,max_length=50)

    @model_validator(mode='after')
    def unique(self):
        if (any(a.target.workspace_id!=self.workspace_id for a in self.accounts)
            or len({a.account_ref for a in self.accounts})!=len(self.accounts)
            or len({(a.target.profile_id,a.target.profile_version) for a in self.accounts})!=len(self.accounts)):
            raise ValueError('Unique scoped account bindings required')
        return self

class AccountFactory:
    def __init__(self,account,root,workspace,*,owner_read_enabled=False,transport=None,resolver=None,registry_file=None,registry_sha256=None):
        if type(owner_read_enabled) is not bool or type(account) not in (Account,OAuthAccount) or account.target.workspace_id!=workspace:
            raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
        if type(account) is OAuthAccount:
            from .google_analytics_selection_resolver import AnalyticsSelectionResolver
            if resolver is not None:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_RESOLVER_INVALID',400)
            resolver=AnalyticsSelectionResolver(account,root,workspace)
        self.account=account.model_copy(deep=True);self.root=Path(root);self.workspace=workspace
        if (registry_file is None)!=(registry_sha256 is None) or registry_sha256 is not None and (not isinstance(registry_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',registry_sha256)):
            raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
        self.registry_file=protected_path(registry_file,self.root) if registry_file is not None else None
        self.registry_sha256=registry_sha256;self.frozen_registry_file=self.registry_file;self.frozen_registry_sha256=registry_sha256
        self.path=protected_path(account.token_file,root) if type(account) is Account else None
        self.frozen_path=self.path
        self.client=AnalyticsHTTPClient(account.target.platform,network_enabled=owner_read_enabled and account.read_enabled,transport=transport)
        if resolver is not None and not callable(resolver):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_RESOLVER_INVALID',400)
        self.resolver=resolver;self.read_enabled=owner_read_enabled and account.read_enabled
        self.frozen=self.account.model_dump(mode='json');self.sha256=digest({**self.frozen,**({'registry_sha256':registry_sha256} if registry_sha256 is not None else {})})
        self.frozen_root=self.root.absolute();self.frozen_resolver=resolver;self.frozen_enabled=self.read_enabled
        self.frozen_transport=transport;self.frozen_network=self.client.wire.network_enabled
        self.frozen_client=self.client;self.frozen_wire=self.client.wire

    def check(self):
        try:
            if type(self.account) not in (Account,OAuthAccount):raise ValueError()
            parsed=type(self.account).model_validate(self.account.model_dump(mode='json'))
            if type(parsed) is OAuthAccount:
                from .google_analytics_selection_resolver import AnalyticsSelectionResolver
                if type(self.resolver) is not AnalyticsSelectionResolver or self.resolver.binding!=parsed or self.path is not None:raise ValueError()
                self.resolver.check()
            if (self.registry_file!=self.frozen_registry_file or self.registry_sha256!=self.frozen_registry_sha256
                or (self.registry_file is None)!=(self.registry_sha256 is None)):raise ValueError()
            if self.registry_file is not None and (protected_path(self.registry_file,self.root)!=self.registry_file
                or not self.registry_file.is_file() or not 1<=self.registry_file.stat().st_size<=262144
                or file_sha(self.registry_file)!=self.registry_sha256):raise ValueError()
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED') from None
        if (type(self.client) is not AnalyticsHTTPClient or self.client is not self.frozen_client
            or type(self.client.wire) is not OfficialHTTPClient or self.client.wire is not self.frozen_wire
            or self.client.wire.platform!='analytics_'+parsed.target.platform or self.root.absolute()!=self.frozen_root
            or self.resolver is not self.frozen_resolver or self.read_enabled is not self.frozen_enabled
            or self.client.wire.transport is not self.frozen_transport or self.client.wire.network_enabled is not self.frozen_network
            or parsed.model_dump(mode='json')!=self.frozen
            or digest({**parsed.model_dump(mode='json'),**({'registry_sha256':self.registry_sha256} if self.registry_sha256 is not None else {})})!=self.sha256
            or parsed.target.workspace_id!=self.workspace or self.path!=self.frozen_path
            or type(parsed) is Account and protected_path(parsed.token_file,self.root)!=self.path
            or self.client.platform!=parsed.target.platform):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED')
        return parsed

    def public(self):
        value=self.check();mounted=self.resolver is not None or self.path is not None and self.path.is_file() and 0<self.path.stat().st_size<=32768
        if type(value) is OAuthAccount:mounted=self.resolver.available(mock=self.client.mock)
        enabled=self.read_enabled and self.client.enabled and mounted
        return {'account_ref':value.account_ref,'target':value.target.model_dump(mode='json'),'target_binding_sha256':target_digest(value.target),
            'configuration_sha256':self.sha256,'credential_alias':value.credential_alias,
            'status':'CONFIGURED' if enabled else 'NOT_CONFIGURED','credential_verified':False,
            'credential_present':mounted,
            'mode':'fixture' if self.client.mock else 'official','external_reads_enabled':enabled and not self.client.mock,
            'publishing_enabled':False,'token_returned':False,'account_verified':False,'real_provider_tested':False}

    def credential(self,query=None,*,now=None):
        value=self.check()
        if not self.read_enabled or not self.client.enabled:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_READ_DISABLED')
        if type(value) is OAuthAccount and not self.resolver.available(mock=self.client.mock):raise WorkflowError('NATIVE_GOOGLE_ANALYTICS_SELECTION_REQUIRED')
        resolver=self.resolver or (lambda target:token_load(self.path,self.root,target,value.credential_alias))
        credential=resolve_credential(resolver,value.target,query,now=now)
        self.check()
        return credential

def load(path,root,workspace,*,owner_read_enabled=False):
    if type(owner_read_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
    path=protected_path(path,root)
    if not path.is_file() or not 1<=path.stat().st_size<=262144:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_REGISTRY_INVALID',400)
    try:
        raw=path.read_bytes();registry=Registry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));checksum=hashlib.sha256(raw).hexdigest()
        if file_sha(path)!=checksum:raise ValueError()
    except Exception:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_REGISTRY_INVALID',400) from None
    if registry.workspace_id!=workspace:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_WORKSPACE_MISMATCH',400)
    return {a.account_ref:AccountFactory(a,root,workspace,owner_read_enabled=owner_read_enabled,registry_file=path,registry_sha256=checksum) for a in registry.accounts}
