"""Inert official publishing factory; no startup OAuth, provider call or shared ORM."""
from pathlib import Path
import json
from typing import Literal
from pydantic import Field,StrictInt,model_validator
from .contracts import WorkflowError,digest,file_sha
import hashlib,re
from .official_publication_models import Profile,Gates
from .official_account_tokens import protected_path,unique_pairs
from .official_publication_tokens import load as token_load
from app.models import StrictModel
from app.publishing_wire import OfficialHTTPClient
from app.publishing_credentials import resolve_youtube_credential,target_digest

class Binding(StrictModel):
    profile:Profile
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    token_file:str=Field(min_length=1,max_length=1000,repr=False)
    gates:Gates=Field(default_factory=Gates)

class Registry(StrictModel):
    schema_version:Literal['native-official-publishing-registry-v1']='native-official-publishing-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    bindings:list[Binding]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if any(b.profile.target.workspace_id!=self.workspace_id for b in self.bindings) or len({b.profile.target.profile_id for b in self.bindings})!=len(self.bindings):raise ValueError('Unique scoped publishing profiles required')
        return self

class PublishingFactory:
    def __init__(self,profile,root,workspace,*,gates=None,client=None,resolver=None,binding=None,registry_file=None,registry_sha256=None):
        if type(profile) is not Profile or profile.target.workspace_id!=workspace:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        gates=gates or Gates();client=client or OfficialHTTPClient('youtube')
        if type(gates) is not Gates or type(client) is not OfficialHTTPClient or client.platform!='youtube' or resolver is not None and not callable(resolver):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        if binding is not None and (type(binding) is not Binding or binding.profile!=profile):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        if (registry_file is None)!=(registry_sha256 is None) or registry_sha256 is not None and (not isinstance(registry_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',registry_sha256)):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        self.profile=profile.model_copy(deep=True);self.gates=gates.model_copy(deep=True);self.root=Path(root);self.workspace=workspace;self.client=client
        self.binding=binding.model_copy(deep=True) if binding is not None else None;self.path=protected_path(binding.token_file,self.root) if binding is not None else None
        self.external_resolver=resolver is not None;self.frozen_external_resolver=self.external_resolver
        self.resolver=resolver
        if binding is not None and resolver is None:self.resolver=lambda target:token_load(self.path,self.root,target,self.binding.credential_alias)
        self.frozen={'profile':self.profile.model_dump(mode='json'),'gates':self.gates.model_dump(mode='json')}
        if self.binding is not None:self.frozen['binding']=self.binding.model_dump(mode='json')
        self.registry_file=protected_path(registry_file,self.root) if registry_file is not None else None;self.registry_sha256=registry_sha256;self.frozen_registry_file=self.registry_file
        if registry_sha256 is not None:self.frozen['registry_sha256']=registry_sha256
        self.sha256=digest(self.frozen)
        self.frozen_client=client;self.frozen_transport=client.transport;self.frozen_network=client.network_enabled;self.frozen_resolver=self.resolver;self.frozen_root=self.root.absolute();self.frozen_path=self.path
    def check(self):
        try:
            profile=Profile.model_validate(self.profile.model_dump(mode='json'));gates=Gates.model_validate(self.gates.model_dump(mode='json'));current={'profile':profile.model_dump(mode='json'),'gates':gates.model_dump(mode='json')}
            if self.binding is not None:
                binding=Binding.model_validate(self.binding.model_dump(mode='json'));current['binding']=binding.model_dump(mode='json')
                if binding.profile!=profile or protected_path(binding.token_file,self.root)!=self.path:raise ValueError()
            if self.registry_sha256 is not None:current['registry_sha256']=self.registry_sha256
            if self.registry_file!=self.frozen_registry_file or (self.registry_file is None)!=(self.registry_sha256 is None):raise ValueError()
            if self.registry_file is not None and (protected_path(self.registry_file,self.root)!=self.registry_file or not self.registry_file.is_file() or self.registry_file.stat().st_size>262144 or file_sha(self.registry_file)!=self.registry_sha256):raise ValueError()
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED') from None
        if (type(self.client) is not OfficialHTTPClient or self.client is not self.frozen_client or self.client.platform!='youtube'
            or self.client.transport is not self.frozen_transport or self.client.network_enabled is not self.frozen_network
            or self.resolver is not self.frozen_resolver or self.root.absolute()!=self.frozen_root or profile.target.workspace_id!=self.workspace
            or current!=self.frozen or self.path!=self.frozen_path or self.external_resolver is not self.frozen_external_resolver
            or digest(self.frozen)!=self.sha256):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED')
        return profile,gates
    def public(self):
        profile,gates=self.check();mounted=self.external_resolver or self.path is not None and self.path.is_file() and 0<self.path.stat().st_size<=32768
        configured=all(gates.model_dump().values()) and self.resolver is not None and mounted and (self.client.transport is not None or self.client.network_enabled is True)
        return {'schema_version':'native-official-publishing-factory-v1','target':profile.target.model_dump(mode='json'),'target_binding_sha256':target_digest(profile.target),
            'configuration_sha256':self.sha256,'status':'CONFIGURED' if configured else 'NOT_CONFIGURED','gates':gates.model_dump(mode='json'),
            'disclosures':{key:getattr(profile,key) for key in ('category_id','made_for_kids','contains_synthetic_media')},'chunk_size':profile.chunk_size,
            'mock':self.client.transport is not None,'external_actions_enabled':configured and self.client.transport is None,
            'credential_alias':self.binding.credential_alias if self.binding is not None else None,'credential_present':mounted,
            'credential_verified':False,'real_provider_tested':False,'token_returned':False,'automatic_publishing':False}
    def credential(self,*,now=None):
        profile,_=self.check()
        if self.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_CONFIGURED')
        return resolve_youtube_credential(self.resolver,profile.target,now=now)

def load(path,root,workspace,*,owner_enabled=False):
    if type(owner_enabled) is not bool:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
    path=protected_path(path,root)
    if not path.is_file() or not 1<=path.stat().st_size<=262144:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_REGISTRY_INVALID',400)
    try:
        raw=path.read_bytes();registry=Registry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));checksum=hashlib.sha256(raw).hexdigest()
        if file_sha(path)!=checksum:raise ValueError()
    except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_REGISTRY_INVALID',400) from None
    if registry.workspace_id!=workspace:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_WORKSPACE_MISMATCH',400)
    factories={}
    for binding in registry.bindings:
        gates=Gates(**{key:owner_enabled and value for key,value in binding.gates.model_dump().items()})
        client=OfficialHTTPClient('youtube',network_enabled=all(gates.model_dump().values()))
        factory=PublishingFactory(binding.profile,root,workspace,gates=gates,client=client,binding=binding,registry_file=path,registry_sha256=checksum);factories[binding.profile.target.profile_id]=factory
    return factories
