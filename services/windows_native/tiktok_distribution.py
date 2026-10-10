"""Typed TikTok distribution factory and admission on the existing Native journal."""
import json,re
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Literal
from pydantic import Field,StrictInt,model_validator
from app.models import StrictModel
from app.publishing_models import PublicationMetadata,PublishingTargetBinding
from app.publishing_credentials import target_digest
from app.publishing_logic import validate_platform
from app.publishing_wire import OfficialHTTPClient,PublishingWireError
from app.tiktok_upload import ChunkPlan,PostChoices,start_request
from .contracts import WorkflowError,digest,file_sha
from .official_publication_models import Gates,TikTokCreate
from .official_account_tokens import protected_path,unique_pairs
from .tiktok_connection import NativeTikTokFactory,Profile
from .publication_qc import project as project_qc

class DistributionBinding(StrictModel):
    profile_id:str=Field(pattern=r'^ppf_[A-Za-z0-9_-]{4,60}$')
    expected_creator_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    gates:Gates=Field(default_factory=Gates)

class DistributionRegistry(StrictModel):
    schema_version:Literal['native-tiktok-distribution-registry-v1']='native-tiktok-distribution-registry-v1'
    version:StrictInt=Field(ge=1,le=1)
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    bindings:list[DistributionBinding]=Field(default_factory=list,max_length=50)
    @model_validator(mode='after')
    def unique(self):
        if len({b.profile_id for b in self.bindings})!=len(self.bindings):raise ValueError('Unique publishing profiles required')
        return self

class NativeTikTokPublishingFactory:
    def __init__(self,connection,*,gates=None,owner_enabled=False,registry_file=None,registry_sha256=None):
        if type(connection) is not NativeTikTokFactory or type(owner_enabled) is not bool or gates is not None and type(gates) is not Gates:
            raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CONFIGURATION_INVALID',400)
        connection.check();gates=gates or Gates();self.connection=connection;self.profile=connection.profile;self.root=connection.root;self.workspace=connection.workspace
        self.gates=Gates(**{key:owner_enabled and value for key,value in gates.model_dump().items()})
        self.registry_file=protected_path(registry_file,self.root) if registry_file is not None else None;self.registry_sha256=registry_sha256
        if (registry_file is None)!=(registry_sha256 is None) or registry_sha256 is not None and (type(registry_sha256) is not str or not re.fullmatch('[a-f0-9]{64}',registry_sha256)):raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CONFIGURATION_INVALID',400)
        self.cipher_sha256=connection.cipher() if connection.public()['credential_present'] else None
        # Native transfer/status/session execution is a separate increment. Real
        # networking stays disabled until that worker path is implemented.
        self.client=OfficialHTTPClient('tiktok',network_enabled=False,transport=connection.client.transport)
        self.configuration={'creator_configuration_sha256':connection.sha256,'gates':self.gates.model_dump(mode='json'),'cipher_sha256':self.cipher_sha256}
        if registry_sha256 is not None:self.configuration['registry_sha256']=registry_sha256
        self.sha256=digest(self.configuration);self.frozen=(connection,self.profile,self.root,self.workspace,self.client,self.client.transport,self.client.network_enabled,self.registry_file,registry_sha256,self.cipher_sha256,self.sha256,digest(self.configuration))
    def check(self):
        try:
            self.connection.check();gates=Gates.model_validate(self.gates.model_dump(mode='json'))
            configuration={'creator_configuration_sha256':self.connection.sha256,'gates':gates.model_dump(mode='json'),'cipher_sha256':self.cipher_sha256}
            if self.registry_sha256 is not None:configuration['registry_sha256']=self.registry_sha256
            if ((self.connection,self.profile,self.root,self.workspace,self.client,self.client.transport,self.client.network_enabled,self.registry_file,self.registry_sha256,self.cipher_sha256,self.sha256,digest(self.configuration))!=self.frozen
                or type(self.client) is not OfficialHTTPClient or self.client.platform!='tiktok' or self.profile is not self.connection.profile or self.configuration!=configuration
                or self.registry_file is not None and (not self.registry_file.is_file() or not 1<=self.registry_file.stat().st_size<=262144 or file_sha(self.registry_file)!=self.registry_sha256)):raise ValueError()
        except Exception:raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CONFIGURATION_CHANGED') from None
        return self.profile,gates
    def public(self):
        profile,gates=self.check();read=self.connection.public();mounted=read['credential_present'] and self.cipher_sha256 is not None and self.connection.cipher()==self.cipher_sha256
        configured=all(gates.model_dump().values()) and mounted and read['status']=='READ_CONFIGURED' and (self.client.transport is not None or self.client.network_enabled is True)
        return {'schema_version':'native-official-tiktok-publishing-factory-v1','target':profile.target.model_dump(mode='json'),'target_binding_sha256':target_digest(profile.target),'configuration_sha256':self.sha256,
            'status':'CONFIGURED' if configured else 'NOT_CONFIGURED','gates':gates.model_dump(mode='json'),'disclosures':{'api_client_audited':profile.api_client_audited,'media_location':profile.media_location},'chunk_size':profile.chunk_size,
            'creator_configuration_sha256':self.connection.sha256,'cipher_sha256':self.cipher_sha256,'mock':self.client.transport is not None,'external_actions_enabled':False,'execution_supported':False,
            'credential_alias':self.connection.binding.credential_alias,'credential_present':mounted,'credential_verified':False,'real_provider_tested':False,'token_returned':False,'automatic_publishing':False}
    def credential(self,*,now=None):
        self.check()
        if self.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_NOT_CONFIGURED')
        if now is None:raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_TIME_REQUIRED')
        return self.connection.credential(now=now,expected_cipher_sha256=self.cipher_sha256)

def load(path,creators,*,owner_enabled=False):
    from .tiktok_creators import NativeTikTokCreators
    if type(owner_enabled) is not bool or type(creators) is not NativeTikTokCreators:raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CONFIGURATION_INVALID',400)
    creators.check()
    path=protected_path(path,creators.store.root)
    try:
        if not path.is_file() or not 1<=path.stat().st_size<=262144:raise ValueError()
        raw=path.read_bytes();registry=DistributionRegistry.model_validate(json.loads(raw,object_pairs_hook=unique_pairs));sha=digest_bytes(raw)
        if file_sha(path)!=sha or registry.workspace_id!=creators.workspace:raise ValueError()
    except Exception:raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_REGISTRY_INVALID',400) from None
    values={}
    for binding in registry.bindings:
        connection=creators.factories.get(binding.profile_id)
        if connection is None or connection.sha256!=binding.expected_creator_configuration_sha256:raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CREATOR_BINDING_CHANGED')
        values[binding.profile_id]=NativeTikTokPublishingFactory(connection,gates=binding.gates,owner_enabled=owner_enabled,registry_file=path,registry_sha256=sha)
    return values

def digest_bytes(raw):
    import hashlib
    return hashlib.sha256(raw).hexdigest()

def preflight(snapshot,profile,*,creator=None):
    from .tiktok_creators import parsed_creator
    try:
        info=creator or parsed_creator(snapshot['creator_draft']['snapshot']['creator_check']['result']['creator'])
        start_request(PublicationMetadata.model_validate(snapshot['metadata']),ChunkPlan(snapshot['final_bytes'],profile.chunk_size),'EXPLICIT-UNSENT-TIKTOK-PREFLIGHT-TOKEN',creator=info,
            choices=PostChoices.model_validate(snapshot['choices']),duration_sec=snapshot['duration_seconds'],client_audited=profile.api_client_audited,media_location=profile.media_location)
    except PublishingWireError as error:raise WorkflowError(error.code,400) from None

def source(journal,con,project,payload,factory,*,validation_time=None):
    from .tiktok_creators import NativeTikTokCreators,TABLE,DRAFTS
    from .official_publications import utc
    from .publications import PROFILES
    if type(payload) is not TikTokCreate or type(factory) is not NativeTikTokPublishingFactory or type(journal.tiktok_creators) is not NativeTikTokCreators or factory.connection is not journal.tiktok_creators.factories.get(payload.profile_id):
        raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_BINDING_CHANGED')
    current=journal.store.editable(con,project,payload.revision);parent=journal.publications.get_row(con,project,payload.dry_run_publication_id);review,_=journal.publications.revalidate(con,parent)
    if review['status']!='dry_run_succeeded' or review['snapshot_sha256']!=payload.expected_dry_run_snapshot_sha256 or review['snapshot']['request']['platform']!='tiktok':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_VALIDATED_DRY_RUN_REQUIRED')
    creators=journal.tiktok_creators;draft=creators.read_draft(creators.row(con,project,payload.creator_draft_id,DRAFTS));creators.draft_links(con,draft)
    check=creators.read(creators.row(con,project,draft['snapshot']['request']['creator_check_id']));creators.links(con,check);state=factory.public()
    instant=utc(validation_time if validation_time is not None else journal.clock());check_snapshot=check['snapshot'];request=draft['snapshot']['request']
    if (draft['snapshot_sha256']!=payload.expected_creator_draft_snapshot_sha256 or draft['snapshot']['workspace_id']!=journal.workspace or request['revision']!=current['revision'] or check['status']!='succeeded'
        or check_snapshot['factory']!=factory.connection.public() or check_snapshot['cipher_sha256']!=factory.cipher_sha256 or check_snapshot['document_sha256']!=digest(current['document'])
        or not utc(datetime.fromisoformat(check_snapshot['consented_at']))<=instant<utc(datetime.fromisoformat(check_snapshot['deadline']))
        or state['mock'] is not check_snapshot['mock'] or state['configuration_sha256']!=payload.expected_configuration_sha256):raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_CURRENT_CREATOR_REQUIRED')
    # A completed read window is not publication authority. The engine separately
    # checks a current Owner publish grant before every external step.
    creators.identity(authority=check_snapshot['authority'])
    job,actual,path=journal.publications.render(con,project,review['snapshot']['request']['final_job_id']);qc=project_qc(job);metadata=PublicationMetadata.model_validate(request['metadata'])
    if request['final_job_id']!=job['id'] or request['expected_final_sha256']!=actual or review['snapshot']['request']['metadata']!=metadata.model_dump(mode='json'):
        raise WorkflowError('NATIVE_TIKTOK_DISTRIBUTION_FINAL_OR_METADATA_CHANGED')
    platform=validate_platform(capability=journal.publications.capabilities.get('tiktok'),metadata=metadata,render=SimpleNamespace(profile=PROFILES.get((qc.get('width'),qc.get('height')),'native-unmapped-profile'),qc_report=qc),output_asset=SimpleNamespace(size_bytes=path.stat().st_size),mode='live')
    if platform.status!='passed':raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PLATFORM_VALIDATION_FAILED')
    preflight({'metadata':metadata.model_dump(mode='json'),'final_bytes':path.stat().st_size,'duration_seconds':qc.get('duration_seconds'),'choices':request['choices'],'creator_draft':draft},factory.profile)
    return current,review,check,state,job,actual,path,platform.model_dump(mode='json'),None,draft

def evidence_reader(journal):
    from .tiktok_creators import NativeTikTokCreators
    # Public evidence has no authority-bearing service constructor, mutable
    # registry, provider or private-load methods; all relational reads use con.
    class Reader:
        read=NativeTikTokCreators.read
        read_draft=NativeTikTokCreators.read_draft
        row=NativeTikTokCreators.row
        links=NativeTikTokCreators.links
        draft_links=NativeTikTokCreators.draft_links
    reader=Reader();reader.store=journal.store;reader.workspace=journal.workspace;return reader

def read_snapshot(journal,value,snapshot):
    request=TikTokCreate.model_validate({**snapshot['request'],'request_key':'internal-tiktok-publication-key'});target=PublishingTargetBinding.model_validate(snapshot['target'])
    fields={'schema_version','workspace_id','project_id','project_revision','document_sha256','request','dry_run_snapshot_sha256','account_check_snapshot_sha256','account_result_sha256','configuration_sha256','target','target_binding_sha256',
        'final_job_id','final_sha256','final_bytes','final_job_snapshot_sha256','final_review','validation','metadata','reviewed_at','metadata_source','disclosures','chunk_size','mock','dry_run_receipt_is_publish_authority','account_check_is_publish_authority','separate_owner_publish_approval_required','token_returned','creator_draft','choices','duration_seconds','credential_cipher_sha256'}
    if (set(snapshot)!=fields or digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_fingerprint'] or value['workspace_id']!=journal.workspace or snapshot['workspace_id']!=journal.workspace or snapshot['project_id']!=value['project_id']
        or target.workspace_id!=journal.workspace or target.profile_id!=request.profile_id or target.platform!='tiktok' or target.provider_key!='tiktok-content-posting-api' or target_digest(target)!=snapshot['target_binding_sha256']
        or request.expected_configuration_sha256!=snapshot['configuration_sha256'] or request.expected_dry_run_snapshot_sha256!=snapshot['dry_run_snapshot_sha256'] or type(snapshot['project_revision']) is not int or request.revision!=snapshot['project_revision']
        or type(snapshot['mock']) is not bool or snapshot['dry_run_receipt_is_publish_authority'] is not False or snapshot['account_check_is_publish_authority'] is not False or snapshot['separate_owner_publish_approval_required'] is not True or snapshot['token_returned'] is not False
        or value['dedupe_sha256']!=digest({'workspace':journal.workspace,'platform':'tiktok','account':target.target_account_id,'final':snapshot['final_sha256'],'mock':snapshot['mock']})
        or value['status'] not in {'not_configured','awaiting_publish_approval','queued','running','cancelled','review_required','completed'} or snapshot['metadata_source']!='completed_dry_run'
        or datetime.fromisoformat(snapshot['reviewed_at']).tzinfo is None or not re.fullmatch('nopu_[a-f0-9]{32}',value['publication_id'])
        or any(type(snapshot[k]) is not str or not re.fullmatch('[a-f0-9]{64}',snapshot[k]) for k in ('document_sha256','final_sha256','final_job_snapshot_sha256','credential_cipher_sha256'))):
        raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_EVIDENCE_CHANGED')
    # Pure public replay uses the original owned draft/cost/job links. No current
    # registry, token, network or identity is needed to read historical evidence.
    reader=evidence_reader(journal);embedded=snapshot['creator_draft'];draft_row={k:v for k,v in embedded.items() if k not in ('snapshot','token_returned','publishing_enabled','publish_approval_required')}
    draft_row.update(snapshot_json=json.dumps(embedded['snapshot']),key_sha256='internal-reconstruction');draft=reader.read_draft(draft_row)
    check=draft['snapshot']['creator_check'];profile=Profile.model_validate(check['snapshot']['factory']['profile']);media=draft['snapshot']['source']
    if (snapshot['creator_draft']!=draft or draft['draft_id']!=request.creator_draft_id or draft['workspace_id']!=journal.workspace or draft['project_id']!=value['project_id'] or draft['snapshot']['request']['revision']!=snapshot['project_revision']
        or draft['snapshot_sha256']!=request.expected_creator_draft_snapshot_sha256 or check['snapshot_sha256']!=snapshot['account_check_snapshot_sha256'] or check['result_sha256']!=snapshot['account_result_sha256']
        or profile.target!=target or check['snapshot']['mock'] is not snapshot['mock'] or check['snapshot']['cipher_sha256']!=snapshot['credential_cipher_sha256']
        or media['final_job_id']!=snapshot['final_job_id'] or media['final_sha256']!=snapshot['final_sha256'] or media['final_bytes']!=snapshot['final_bytes'] or media['job_snapshot_sha256']!=snapshot['final_job_snapshot_sha256']
        or media['document_sha256']!=snapshot['document_sha256'] or media['final_review']!=snapshot['final_review'] or media['duration_sec']!=snapshot['duration_seconds'] or snapshot['chunk_size']!=profile.chunk_size
        or snapshot['disclosures']!={'api_client_audited':profile.api_client_audited,'media_location':profile.media_location} or snapshot['choices']!=draft['snapshot']['request']['choices'] or snapshot['metadata']!=draft['snapshot']['request']['metadata']):
        raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_EVIDENCE_CHANGED')
    preflight(snapshot,profile);value.pop('key_sha256')
    return {**value,'snapshot':snapshot,'schema_version':'native-official-publication-v1','mock':snapshot['mock'],'token_returned':False,'real_provider_tested':False,'receipt':None,'published':False,'mock_publication_complete':False}
