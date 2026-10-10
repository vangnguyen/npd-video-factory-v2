"""Shared Meta admission: legacy v1 remains inert; v2 needs explicit execution."""
import hashlib, json, re
from datetime import datetime
from types import SimpleNamespace
from typing import Literal
from pydantic import Field, StrictBool, StrictInt, model_validator
from app.models import StrictModel
from app.meta_publishing_protocol import caption, fb_finish_request
from app.publishing_models import PublicationMetadata, PublishingTargetBinding, PlatformValidationRead
from app.publishing_credentials import target_digest
from app.publishing_logic import validate_platform
from app.publishing_wire import MAX_BODY, OfficialHTTPClient, PublishingWireError
from .contracts import WorkflowError, digest, file_sha
from .meta_connection import NativeMetaAccountFactory, Profile
from .meta_account_evidence import validate as validate_account_source
from .official_account_tokens import protected_path, unique_pairs
from .official_publication_models import MetaCreate, MetaExecutionCreate, Gates
from .publication_qc import project as project_qc


class Options(StrictModel):
    share_to_feed: StrictBool = False

class ExecutionCapability(StrictModel):
    schema_version:Literal['native-meta-s3-pull-execution-capability-v1']='native-meta-s3-pull-execution-capability-v1'
    media_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class Binding(StrictModel):
    account_ref: str = Field(pattern=r'^npac_[a-f0-9]{32}$')
    expected_account_configuration_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    gates: Gates = Field(default_factory=Gates)
    options: Options = Field(default_factory=Options)


class Registry(StrictModel):
    schema_version: Literal['native-meta-distribution-registry-v1'] = 'native-meta-distribution-registry-v1'
    version: StrictInt = Field(ge=1, le=1)
    workspace_id: str = Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    bindings: list[Binding] = Field(default_factory=list, max_length=50)

    @model_validator(mode='after')
    def unique(self):
        if len({b.account_ref for b in self.bindings}) != len(self.bindings): raise ValueError('Unique Meta account references required')
        return self

class ExecutionBinding(Binding):
    execution:ExecutionCapability

class ExecutionRegistry(Registry):
    schema_version:Literal['native-meta-distribution-registry-v2']='native-meta-distribution-registry-v2'
    version:StrictInt=Field(ge=2,le=2)
    bindings:list[ExecutionBinding]=Field(default_factory=list,max_length=50)


class NativeMetaPublishingFactory:
    def __init__(self, connection, *, gates=None, options=None, owner_enabled=False, registry_file=None, registry_sha256=None, execution=None):
        if (type(connection) is not NativeMetaAccountFactory or type(owner_enabled) is not bool
            or gates is not None and type(gates) is not Gates or options is not None and type(options) is not Options
            or execution is not None and type(execution) is not ExecutionCapability):
            raise WorkflowError('NATIVE_META_DISTRIBUTION_CONFIGURATION_INVALID', 400)
        connection.check(); self.connection = connection; self.profile = connection.profile; self.root = connection.root; self.workspace = connection.workspace
        self.gates = Gates(**{k: owner_enabled and v for k,v in (gates or Gates()).model_dump().items()})
        self.options = (options or Options()).model_copy(deep=True)
        if self.profile.target.platform == 'facebook' and self.options.share_to_feed: raise WorkflowError('NATIVE_META_DISTRIBUTION_OPTIONS_INVALID', 400)
        self.registry_file = protected_path(registry_file, self.root) if registry_file is not None else None; self.registry_sha256 = registry_sha256
        if (registry_file is None) != (registry_sha256 is None) or registry_sha256 is not None and (type(registry_sha256) is not str or not re.fullmatch('[a-f0-9]{64}',registry_sha256)):
            raise WorkflowError('NATIVE_META_DISTRIBUTION_CONFIGURATION_INVALID', 400)
        self.execution=execution.model_copy(deep=True) if execution is not None else None
        self.execution_supported = execution is not None
        self.client = OfficialHTTPClient(self.profile.target.platform, network_enabled=self.execution_supported and all(self.gates.model_dump().values()) and connection.client.wire.transport is None, transport=connection.client.wire.transport)
        self.configuration = {'account_ref': connection.account.account_ref, 'account_configuration_sha256': connection.sha256,
            'cipher_sha256': connection.cipher_sha256, 'gates': self.gates.model_dump(mode='json'), 'options': self.options.model_dump(mode='json'), 'execution_supported': self.execution_supported,
            **({'execution':self.execution.model_dump(mode='json')} if self.execution is not None else {}),
            **({'registry_sha256':registry_sha256} if registry_sha256 is not None else {})}
        self.sha256 = digest(self.configuration)
        self.frozen = (connection, self.profile, self.root, self.workspace, self.client, self.client.transport, self.client.network_enabled,
            self.registry_file, registry_sha256, self.sha256, digest(self.configuration))

    def check(self):
        try:
            self.connection.check(); gates=Gates.model_validate(self.gates.model_dump(mode='json')); options=Options.model_validate(self.options.model_dump(mode='json'))
            config={'account_ref':self.connection.account.account_ref,'account_configuration_sha256':self.connection.sha256,'cipher_sha256':self.connection.cipher_sha256,
                'gates':gates.model_dump(mode='json'),'options':options.model_dump(mode='json'),'execution_supported':self.execution is not None,
                **({'execution':ExecutionCapability.model_validate(self.execution.model_dump(mode='json')).model_dump(mode='json')} if self.execution is not None else {}),
                **({'registry_sha256':self.registry_sha256} if self.registry_sha256 is not None else {})}
            if (type(self.execution_supported) is not bool or self.execution_supported is not (self.execution is not None) or type(self.client) is not OfficialHTTPClient or self.client.platform != self.profile.target.platform
                or self.profile is not self.connection.profile or config != self.configuration
                or (self.connection,self.profile,self.root,self.workspace,self.client,self.client.transport,self.client.network_enabled,
                    self.registry_file,self.registry_sha256,self.sha256,digest(self.configuration)) != self.frozen): raise ValueError()
            if self.registry_file is not None and (protected_path(self.registry_file,self.root) != self.registry_file
                or not self.registry_file.is_file() or not 1 <= self.registry_file.stat().st_size <= 262144 or file_sha(self.registry_file) != self.registry_sha256): raise ValueError()
        except Exception: raise WorkflowError('NATIVE_META_DISTRIBUTION_CONFIGURATION_CHANGED') from None
        return self.profile, gates

    def public(self):
        profile,gates=self.check(); account=self.connection.public()
        configured=all(gates.model_dump().values()) and account['status']=='CONFIGURED'
        return {'schema_version':'native-official-meta-publishing-factory-v2' if self.execution_supported else 'native-official-meta-publishing-factory-v1','target':profile.target.model_dump(mode='json'),
            'target_binding_sha256':target_digest(profile.target),'configuration_sha256':self.sha256,'status':'CONFIGURED' if configured else 'NOT_CONFIGURED',
            'gates':gates.model_dump(mode='json'),'profile':profile.model_dump(mode='json'),'options':self.options.model_dump(mode='json'),
            'account_ref':self.connection.account.account_ref,'account_configuration_sha256':self.connection.sha256,'cipher_sha256':self.connection.cipher_sha256,
            'disclosures':disclosures(profile,self.options),'chunk_size':MAX_BODY,'mock':self.client.transport is not None,
            'external_actions_enabled':configured and self.execution_supported and self.client.transport is None,'execution_supported':self.execution_supported,
            **({'media_configuration_sha256':self.execution.media_configuration_sha256} if self.execution is not None else {}),'credential_alias':self.connection.account.credential_alias,
            'credential_present':account['credential_present'],'credential_verified':False,'provider_permissions_verified':False,'app_eligibility_verified':False,
            'real_provider_tested':False,'token_returned':False,'automatic_publishing':False}

    def credential(self, *, now=None):
        self.check()
        if not self.execution_supported:raise WorkflowError('NATIVE_META_PUBLISH_EXECUTION_NOT_IMPLEMENTED')
        if self.public()['status']!='CONFIGURED':raise WorkflowError('NATIVE_META_PUBLISH_EXECUTION_NOT_CONFIGURED')
        return self.connection.credential(now=now)


def disclosures(profile, options):
    return {'page_id':profile.page_id,'api_version':profile.api_version,'login_type':profile.login_type,'share_to_feed':options.share_to_feed,
        'provider_permissions_verified':False,'app_eligibility_verified':False}


def load(path, accounts, *, owner_enabled=False):
    from .official_accounts import NativeOfficialAccounts
    if type(accounts) is not NativeOfficialAccounts or type(owner_enabled) is not bool: raise WorkflowError('NATIVE_META_DISTRIBUTION_CONFIGURATION_INVALID',400)
    accounts.check_workspace()
    return load_runtime(path,accounts.store.root,accounts.workspace,accounts.factories,owner_enabled=owner_enabled)


def load_runtime(path,root,workspace,accounts,*,owner_enabled=False):
    """Pure protected config load before socket allocation; no account DB/key read."""
    from pathlib import Path
    if (type(owner_enabled) is not bool or type(accounts) is not dict or len(accounts)>50 or type(workspace) is not str
        or not re.fullmatch('[A-Za-z0-9_-]{1,80}',workspace)):raise WorkflowError('NATIVE_META_DISTRIBUTION_CONFIGURATION_INVALID',400)
    path=protected_path(path,root)
    try:
        if not path.is_file() or not 1 <= path.stat().st_size <= 262144: raise ValueError()
        raw=path.read_bytes(); data=json.loads(raw,object_pairs_hook=unique_pairs)
        registry=(ExecutionRegistry if data.get('schema_version')=='native-meta-distribution-registry-v2' else Registry).model_validate(data);sha=hashlib.sha256(raw).hexdigest()
        if file_sha(path) != sha or registry.workspace_id != workspace: raise ValueError()
    except Exception: raise WorkflowError('NATIVE_META_DISTRIBUTION_REGISTRY_INVALID',400) from None
    values={}
    for binding in registry.bindings:
        connection=accounts.get(binding.account_ref)
        if (type(connection) is not NativeMetaAccountFactory or connection.sha256 != binding.expected_account_configuration_sha256
            or connection.root!=Path(root).absolute() or connection.workspace!=workspace or connection.account.account_ref!=binding.account_ref):
            raise WorkflowError('NATIVE_META_DISTRIBUTION_ACCOUNT_BINDING_CHANGED')
        factory=NativeMetaPublishingFactory(connection,gates=binding.gates,options=binding.options,owner_enabled=owner_enabled,registry_file=path,registry_sha256=sha,execution=getattr(binding,'execution',None))
        if factory.profile.target.profile_id in values: raise WorkflowError('NATIVE_META_DISTRIBUTION_PROFILE_CONFLICT')
        values[factory.profile.target.profile_id]=factory
    return values


def preflight(snapshot, profile, instant=None):
    try:
        metadata=PublicationMetadata.model_validate(snapshot['metadata']); options=Options.model_validate(snapshot['meta_options']); text=caption(metadata)
        if snapshot['metadata_source'] != 'completed_dry_run' or metadata.scheduled_at is not None or metadata.thumbnail_asset_id is not None: raise ValueError()
        if profile.target.platform=='instagram_reels':
            if metadata.privacy != 'public' or len(text)>2200: raise ValueError()
        else:
            if options.share_to_feed: raise ValueError()
            fb_finish_request(profile.graph(), '1', metadata, 'EXPLICIT-UNSENT-META-PREFLIGHT-TOKEN',
                video_state='DRAFT' if metadata.privacy=='private' else 'PUBLISHED')
    except (ValueError,KeyError,TypeError,PublishingWireError): raise WorkflowError('NATIVE_META_DISTRIBUTION_METADATA_INVALID',400) from None


def source(journal, con, project, payload, factory, *, validation_time=None):
    from .publications import PROFILES
    from .official_publications import utc
    if (type(payload) not in {MetaCreate,MetaExecutionCreate} or type(factory) is not NativeMetaPublishingFactory
        or factory.execution_supported is not (type(payload) is MetaExecutionCreate)
        or factory.connection is not journal.accounts.factories.get(factory.connection.account.account_ref)):
        raise WorkflowError('NATIVE_META_DISTRIBUTION_BINDING_CHANGED')
    current=journal.store.editable(con,project,payload.revision); review,_=journal.publications.revalidate(con,journal.publications.get_row(con,project,payload.dry_run_publication_id))
    state=factory.public(); profile=factory.profile
    if review['status']!='dry_run_succeeded' or review['snapshot_sha256']!=payload.expected_dry_run_snapshot_sha256 or review['snapshot']['request']['platform']!=profile.target.platform:
        raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_VALIDATED_DRY_RUN_REQUIRED')
    check=journal.accounts.linked(con,journal.accounts.row(con,project,payload.account_check_id)); metadata=validate_account_source(check['snapshot'],check['result'])
    instant=utc(validation_time if validation_time is not None else journal.clock())
    if (check['status']!='succeeded' or check['result'] is None or check['account_ref']!=state['account_ref']
        or check['snapshot_sha256']!=payload.expected_account_check_snapshot_sha256 or check['result_sha256']!=payload.expected_account_result_sha256
        or check['snapshot']['configuration_sha256']!=state['account_configuration_sha256'] or metadata.profile!=profile or metadata.cipher_sha256!=state['cipher_sha256']
        or check['snapshot']['target']!=state['target'] or check['snapshot']['project_revision']!=current['revision']
        or check['snapshot']['document_sha256']!=digest(current['document']) or check['snapshot']['mock'] is not state['mock']
        or not metadata.consented_at <= instant < metadata.deadline or factory.connection.public()['status']!='CONFIGURED'):
        raise WorkflowError('NATIVE_META_DISTRIBUTION_CURRENT_ACCOUNT_PROOF_REQUIRED')
    if state['configuration_sha256']!=payload.expected_configuration_sha256: raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_CONFIGURATION_CHANGED')
    if type(payload) is MetaExecutionCreate and state['media_configuration_sha256']!=payload.expected_media_configuration_sha256:raise WorkflowError('NATIVE_META_MEDIA_CONFIGURATION_CHANGED')
    job,actual,path=journal.publications.render(con,project,review['snapshot']['request']['final_job_id']); qc=project_qc(job)
    content=PublicationMetadata.model_validate(review['snapshot']['request']['metadata'])
    platform=validate_platform(capability=journal.publications.capabilities.get(profile.target.platform),metadata=content,
        render=SimpleNamespace(profile=PROFILES.get((qc.get('width'),qc.get('height')),'native-unmapped-profile'),qc_report=qc),
        output_asset=SimpleNamespace(size_bytes=path.stat().st_size),mode='live')
    if platform.status!='passed': raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PLATFORM_VALIDATION_FAILED')
    preflight({'metadata':content.model_dump(mode='json'),'metadata_source':'completed_dry_run','meta_options':factory.options.model_dump(mode='json')},profile,instant)
    return current,review,check,state,job,actual,path,platform.model_dump(mode='json'),None


BASE_FIELDS={'schema_version','workspace_id','project_id','project_revision','document_sha256','request','dry_run_snapshot_sha256','account_check_snapshot_sha256','account_result_sha256','configuration_sha256','target','target_binding_sha256',
    'final_job_id','final_sha256','final_bytes','final_job_snapshot_sha256','final_review','validation','metadata','reviewed_at','metadata_source','disclosures','chunk_size','mock','dry_run_receipt_is_publish_authority','account_check_is_publish_authority','separate_owner_publish_approval_required','token_returned'}


def read_snapshot(journal, value, snapshot):
    try:
        execution=snapshot['schema_version']=='native-official-meta-publication-snapshot-v2'
        request=(MetaExecutionCreate if execution else MetaCreate).model_validate({**snapshot['request'],'request_key':'internal-meta-publication-key'}); target=PublishingTargetBinding.model_validate(snapshot['target'])
        profile=Profile.model_validate(snapshot['meta_profile']); options=Options.model_validate(snapshot['meta_options']); check=snapshot['meta_account_proof']
        account_fields={'check_id','workspace_id','project_id','account_ref','request_fingerprint','snapshot_sha256','status','attempts','result_sha256','failure_code','actor_ref','created_at','updated_at',
            'schema_version','snapshot','result','publishing_enabled','token_returned'}
        if set(check)!=account_fields:raise ValueError()
        account_row={k:v for k,v in check.items() if k not in {'schema_version','snapshot','result','publishing_enabled','token_returned'}}
        account_row.update(snapshot_json=json.dumps(check['snapshot']),result_json=json.dumps(check['result']),key_sha256='internal-meta-proof-key',claim_id=None)
        if journal.accounts.read(account_row)!=check:raise ValueError()
        metadata=validate_account_source(check['snapshot'],check['result'])
        platform=PlatformValidationRead.model_validate(snapshot['validation']['official_platform'])
        if (set(snapshot)!=(BASE_FIELDS|{'meta_profile','meta_options','meta_account_proof','credential_cipher_sha256','execution_supported'}|({'media_configuration_sha256'} if execution else set()))
            or digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_fingerprint'] or value['workspace_id']!=journal.workspace
            or snapshot['workspace_id']!=journal.workspace or snapshot['project_id']!=value['project_id'] or target.workspace_id!=journal.workspace
            or profile.target!=target or target.profile_id!=request.profile_id or target_digest(target)!=snapshot['target_binding_sha256']
            or snapshot['configuration_sha256']!=request.expected_configuration_sha256 or snapshot['dry_run_snapshot_sha256']!=request.expected_dry_run_snapshot_sha256
            or type(snapshot['project_revision']) is not int or snapshot['project_revision']!=request.revision or type(snapshot['mock']) is not bool
            or snapshot['dry_run_receipt_is_publish_authority'] is not False or snapshot['account_check_is_publish_authority'] is not False
            or snapshot['separate_owner_publish_approval_required'] is not True or snapshot['token_returned'] is not False or snapshot['execution_supported'] is not execution
            or execution and snapshot['media_configuration_sha256']!=request.expected_media_configuration_sha256
            or snapshot['metadata_source']!='completed_dry_run' or datetime.fromisoformat(snapshot['reviewed_at']).tzinfo is None
            or not metadata.consented_at <= datetime.fromisoformat(snapshot['reviewed_at']) < metadata.deadline
            or platform.status!='passed' or platform.capability.platform!=target.platform or platform.capability.verification_state!='owner_verified_for_live'
            or any(c['passed'] is not True for c in snapshot['validation']['official_platform']['checks'])
            or value['status'] not in ({'not_configured','awaiting_publish_approval','queued','running','cancelled','review_required','completed'} if execution else {'not_configured','awaiting_publish_approval','queued','running','cancelled','review_required'})
            or not re.fullmatch('nopu_[a-f0-9]{32}',value['publication_id']) or not re.fullmatch('[a-f0-9]{32}',snapshot['final_job_id'])
            or any(type(snapshot[k]) is not str or not re.fullmatch('[a-f0-9]{64}',snapshot[k]) for k in ('document_sha256','final_sha256','final_job_snapshot_sha256','credential_cipher_sha256'))
            or type(snapshot['final_bytes']) is not int or not 1<=snapshot['final_bytes']<=512*1024*1024*1024 or type(snapshot['chunk_size']) is not int or snapshot['chunk_size']!=MAX_BODY
            or snapshot['disclosures']!=disclosures(profile,options) or check['status']!='succeeded'
            or check['workspace_id']!=journal.workspace or check['project_id']!=value['project_id'] or check['check_id']!=request.account_check_id
            or check['snapshot_sha256']!=request.expected_account_check_snapshot_sha256 or check['result_sha256']!=request.expected_account_result_sha256
            or snapshot['account_check_snapshot_sha256']!=check['snapshot_sha256'] or snapshot['account_result_sha256']!=check['result_sha256']
            or check['snapshot']['target']!=snapshot['target'] or check['snapshot']['mock'] is not snapshot['mock']
            or check['snapshot']['project_revision']!=snapshot['project_revision'] or check['snapshot']['document_sha256']!=snapshot['document_sha256']
            or check['snapshot']['meta']['profile']!=snapshot['meta_profile'] or check['snapshot']['meta']['cipher_sha256']!=snapshot['credential_cipher_sha256']
            or value['dedupe_sha256']!=digest({'workspace':journal.workspace,'platform':target.platform,'account':target.target_account_id,'final':snapshot['final_sha256'],'mock':snapshot['mock']})):
            raise ValueError()
        preflight(snapshot,profile)
    except Exception: raise WorkflowError('NATIVE_META_DISTRIBUTION_EVIDENCE_CHANGED') from None
    value.pop('key_sha256')
    return {**value,'snapshot':snapshot,'schema_version':'native-official-publication-v1','mock':snapshot['mock'],
        'token_returned':False,'real_provider_tested':False,'receipt':None,'published':False,'mock_publication_complete':False}


def links(journal, con, value, *, include_execution=True):
    snapshot=value['snapshot']; request=snapshot['request']
    check=journal.accounts.linked(con,journal.accounts.row(con,value['project_id'],request['account_check_id']))
    if check!=snapshot['meta_account_proof']: raise WorkflowError('NATIVE_META_DISTRIBUTION_ACCOUNT_PROOF_CHANGED')
    review=journal.publications.read(journal.publications.get_row(con,value['project_id'],request['dry_run_publication_id']))
    if (review['status']!='dry_run_succeeded' or review['snapshot_sha256']!=snapshot['dry_run_snapshot_sha256']
        or review['snapshot']['request']['platform']!=snapshot['target']['platform'] or review['snapshot']['request']['metadata']!=snapshot['metadata']
        or review['snapshot']['request']['revision']!=snapshot['project_revision']
        or review['snapshot']['request']['final_job_id']!=snapshot['final_job_id'] or review['snapshot']['final_sha256']!=snapshot['final_sha256']
        or review['snapshot']['final_bytes']!=snapshot['final_bytes'] or review['snapshot']['job_snapshot_sha256']!=snapshot['final_job_snapshot_sha256']
        or review['snapshot']['final_review']!=snapshot['final_review'] or review['snapshot']['validation']!=snapshot['validation']['dry_run']):
        raise WorkflowError('NATIVE_META_DISTRIBUTION_DRY_RUN_CHANGED')
    dispatch=con.execute('SELECT * FROM native_official_publish_dispatches WHERE publication_id=?',(value['publication_id'],)).fetchone()
    if snapshot['execution_supported'] is True:
        if not include_execution:return
        from .meta_publishing import links as execution_links
        return execution_links(journal,con,value,dispatch)
    if (dispatch is not None and (any(dispatch[k]!=value[k] for k in ('workspace_id','project_id','snapshot_sha256','approval_id'))
        or dispatch['phase']!='prepared' or dispatch['acknowledged_bytes']!=0 or dispatch['total_bytes']!=snapshot['final_bytes']
        or type(dispatch['version']) is not int or dispatch['version']<1
        or any(dispatch[k] is not None for k in ('private_session_ref','remote_post_id','intent_id')))
        or any(con.execute('SELECT 1 FROM '+table+' WHERE publication_id=? LIMIT 1',(value['publication_id'],)).fetchone()
            for table in ('native_official_publish_intents','native_official_publish_processing','native_official_publish_receipts'))):
        raise WorkflowError('NATIVE_META_DISTRIBUTION_EXECUTION_EVIDENCE_UNSUPPORTED')
