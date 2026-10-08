"""Protected public account bindings; calls and token reads are explicit only."""
import json
from pathlib import Path
from typing import Literal
from pydantic import Field,StrictBool,StrictInt,field_validator,model_validator
from . import ingestion
from .backup import guard
from .contracts import WorkflowError,digest
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

class Registry(StrictModel):
    schema_version:Literal['native-official-account-registry-v1']='native-official-account-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    accounts:list[Account]=Field(default_factory=list,max_length=50)

    @model_validator(mode='after')
    def unique(self):
        if (any(a.target.workspace_id!=self.workspace_id for a in self.accounts)
            or len({a.account_ref for a in self.accounts})!=len(self.accounts)
            or len({(a.target.profile_id,a.target.profile_version) for a in self.accounts})!=len(self.accounts)):
            raise ValueError('Unique scoped account bindings required')
        return self

class AccountFactory:
    def __init__(self,account,root,workspace,*,owner_read_enabled=False,transport=None,resolver=None):
        if type(owner_read_enabled) is not bool or type(account) is not Account or account.target.workspace_id!=workspace:
            raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_INVALID',400)
        self.account=account.model_copy(deep=True);self.root=Path(root);self.workspace=workspace
        self.path=protected_path(account.token_file,root)
        self.client=AnalyticsHTTPClient(account.target.platform,network_enabled=owner_read_enabled and account.read_enabled,transport=transport)
        if resolver is not None and not callable(resolver):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_RESOLVER_INVALID',400)
        self.resolver=resolver;self.read_enabled=owner_read_enabled and account.read_enabled
        self.frozen=self.account.model_dump(mode='json');self.sha256=digest(self.frozen)
        self.frozen_root=self.root.absolute();self.frozen_resolver=resolver;self.frozen_enabled=self.read_enabled
        self.frozen_transport=transport;self.frozen_network=self.client.wire.network_enabled
        self.frozen_client=self.client;self.frozen_wire=self.client.wire

    def check(self):
        try:parsed=Account.model_validate(self.account.model_dump(mode='json'))
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED') from None
        if (type(self.client) is not AnalyticsHTTPClient or self.client is not self.frozen_client
            or type(self.client.wire) is not OfficialHTTPClient or self.client.wire is not self.frozen_wire
            or self.client.wire.platform!='analytics_'+parsed.target.platform or self.root.absolute()!=self.frozen_root
            or self.resolver is not self.frozen_resolver or self.read_enabled is not self.frozen_enabled
            or self.client.wire.transport is not self.frozen_transport or self.client.wire.network_enabled is not self.frozen_network
            or parsed.model_dump(mode='json')!=self.frozen or digest(parsed.model_dump(mode='json'))!=self.sha256
            or parsed.target.workspace_id!=self.workspace or protected_path(parsed.token_file,self.root)!=self.path
            or self.client.platform!=parsed.target.platform):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_CONFIGURATION_CHANGED')
        return parsed

    def public(self):
        value=self.check();mounted=self.resolver is not None or self.path.is_file() and 0<self.path.stat().st_size<=32768
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
        resolver=self.resolver or (lambda target:token_load(self.path,self.root,target,value.credential_alias))
        return resolve_credential(resolver,value.target,query,now=now)

def load(path,root,workspace,*,owner_read_enabled=False):
    path=guard(Path(path),exists=True)
    if Path(root).absolute() in path.parents or path.stat().st_size>262144:raise WorkflowError('NATIVE_OFFICIAL_REGISTRY_MUST_BE_OUTSIDE_STATE',400)
    try:registry=Registry.model_validate(json.loads(path.read_bytes(),object_pairs_hook=unique_pairs))
    except Exception:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_REGISTRY_INVALID',400) from None
    if registry.workspace_id!=workspace:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_WORKSPACE_MISMATCH',400)
    return {a.account_ref:AccountFactory(a,root,workspace,owner_read_enabled=owner_read_enabled) for a in registry.accounts}
