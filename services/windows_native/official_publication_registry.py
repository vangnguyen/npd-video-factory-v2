"""Inert official publishing factory; no startup OAuth, provider call or shared ORM."""
from pathlib import Path
from .contracts import WorkflowError,digest
from .official_publication_models import Profile,Gates
from app.publishing_wire import OfficialHTTPClient
from app.publishing_credentials import resolve_youtube_credential,target_digest

class PublishingFactory:
    def __init__(self,profile,root,workspace,*,gates=None,client=None,resolver=None):
        if type(profile) is not Profile or profile.target.workspace_id!=workspace:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        gates=gates or Gates();client=client or OfficialHTTPClient('youtube')
        if type(gates) is not Gates or type(client) is not OfficialHTTPClient or client.platform!='youtube' or resolver is not None and not callable(resolver):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_INVALID',400)
        self.profile=profile.model_copy(deep=True);self.gates=gates.model_copy(deep=True);self.root=Path(root);self.workspace=workspace;self.client=client;self.resolver=resolver
        self.frozen={'profile':self.profile.model_dump(mode='json'),'gates':self.gates.model_dump(mode='json')};self.sha256=digest(self.frozen)
        self.frozen_client=client;self.frozen_transport=client.transport;self.frozen_network=client.network_enabled;self.frozen_resolver=resolver;self.frozen_root=self.root.absolute()
    def check(self):
        try:profile=Profile.model_validate(self.profile.model_dump(mode='json'));gates=Gates.model_validate(self.gates.model_dump(mode='json'))
        except Exception:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED') from None
        if (type(self.client) is not OfficialHTTPClient or self.client is not self.frozen_client or self.client.platform!='youtube'
            or self.client.transport is not self.frozen_transport or self.client.network_enabled is not self.frozen_network
            or self.resolver is not self.frozen_resolver or self.root.absolute()!=self.frozen_root or profile.target.workspace_id!=self.workspace
            or {'profile':profile.model_dump(mode='json'),'gates':gates.model_dump(mode='json')}!=self.frozen
            or digest(self.frozen)!=self.sha256):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED')
        return profile,gates
    def public(self):
        profile,gates=self.check();configured=all(gates.model_dump().values()) and self.resolver is not None and (self.client.transport is not None or self.client.network_enabled is True)
        return {'schema_version':'native-official-publishing-factory-v1','target':profile.target.model_dump(mode='json'),'target_binding_sha256':target_digest(profile.target),
            'configuration_sha256':self.sha256,'status':'CONFIGURED' if configured else 'NOT_CONFIGURED','gates':gates.model_dump(mode='json'),
            'disclosures':{key:getattr(profile,key) for key in ('category_id','made_for_kids','contains_synthetic_media')},'chunk_size':profile.chunk_size,
            'mock':self.client.transport is not None,'external_actions_enabled':configured and self.client.transport is None,
            'credential_verified':False,'real_provider_tested':False,'token_returned':False,'automatic_publishing':False}
    def credential(self,*,now=None):
        profile,_=self.check()
        if self.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_NOT_CONFIGURED')
        return resolve_youtube_credential(self.resolver,profile.target,now=now)
