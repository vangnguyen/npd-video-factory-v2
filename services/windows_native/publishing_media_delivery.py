"""Owned durable media disclosure/storage intents; never grants publishing authority."""
import hashlib, json, os, re, uuid
from datetime import datetime, timedelta, timezone
from typing import Literal
from pathlib import Path
from pydantic import Field, StrictInt, field_validator
from app.models import StrictModel
from app.publishing_media_delivery import (DeliveryScope, StorageProfile, StorageCredential, S3SDKDeliveryWire, ProtocolFixtureDeliveryWire,
    S3PublishingMediaDelivery, MediaDeliveryError, VerifiedMediaObject, MAX_SINGLE_UPLOAD_BYTES, checksum)
from .contracts import WorkflowError, digest, file_sha
from .official_account_tokens import protected_path, unique_pairs
from .official_publications import NativeOfficialPublications, utc
from .costs import CostLedger
from .store import now

PREFIX=b'VF-NATIVE-PUBLISHING-S3-CREDENTIAL-1\n'
ENTROPY=b'NPD-Video-Factory/native-publishing-s3-credential/v1'
LEASE_PREFIX=b'VF-NATIVE-PUBLISHING-MEDIA-LEASE-1\n'
LEASE_ENTROPY=b'NPD-Video-Factory/native-publishing-media-lease/v1'


class Credential(StrictModel):
    schema_version:Literal['native-publishing-s3-credential-v1']='native-publishing-s3-credential-v1'
    workspace_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    storage_profile_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    credential_alias:str=Field(pattern=r'^[a-z][a-z0-9-]{3,79}$')
    expires_at:datetime
    access_key:str=Field(min_length=8,max_length=4096,repr=False)
    secret_key:str=Field(min_length=8,max_length=4096,repr=False)
    session_token:str|None=Field(default=None,max_length=16384,repr=False)
    @field_validator('expires_at',mode='before')
    @classmethod
    def aware(cls,value):
        if not isinstance(value,(str,datetime)):raise ValueError('Aware expiry required')
        parsed=datetime.fromisoformat(value) if isinstance(value,str) else value
        if parsed.tzinfo is None:raise ValueError('Aware expiry required')
        return parsed
    def resolved(self):return StorageCredential(self.access_key,self.secret_key,self.session_token)


def save_private(path,root,value,*,prefix,entropy):
    from .assemblyai_connection import _dpapi,_restrict_file
    path=protected_path(path,root);raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
    encrypted=prefix+_dpapi(raw,entropy=entropy,description='Video Factory scoped publishing media')
    path.parent.mkdir(parents=True,exist_ok=True);temporary=path.parent/('.native-media-'+uuid.uuid4().hex+'.part')
    try:
        with temporary.open('xb') as handle:_restrict_file(temporary);handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
        if os.name!='nt':raise WorkflowError('NATIVE_MEDIA_WINDOWS_PRIVATE_STORAGE_REQUIRED',503)
        os.rename(temporary,path)
    except FileExistsError:raise WorkflowError('NATIVE_MEDIA_PRIVATE_ALREADY_SAVED') from None
    finally:temporary.unlink(missing_ok=True)
    return file_sha(path)


def save_credential(path,root,value):
    try:parsed=Credential.model_validate(value);parsed.resolved()
    except Exception:raise WorkflowError('NATIVE_MEDIA_STORAGE_CREDENTIAL_INVALID',400) from None
    sha=save_private(path,root,parsed.model_dump(mode='json'),prefix=PREFIX,entropy=ENTROPY)
    return {'schema_version':'native-publishing-s3-credential-receipt-v1','workspace_id':parsed.workspace_id,
        'storage_profile_sha256':parsed.storage_profile_sha256,'cipher_sha256':sha,'credential_saved':True,'credential_returned':False,'external_calls':0}


class NativeMediaDeliveryFactory:
    def __init__(self,profile,root,workspace,*,enabled=False,directory=None,credential_file=None,credential_expires_at=None,
                 estimated_operation_cost_vnd=None,wire=None,clock=lambda:datetime.now(timezone.utc)):
        if (type(profile) is not StorageProfile or type(enabled) is not bool or type(workspace) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,80}',workspace) or not callable(clock)
            or estimated_operation_cost_vnd is not None and (type(estimated_operation_cost_vnd) is not int or not 1<=estimated_operation_cost_vnd<=10**9)):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONFIGURATION_INVALID',400)
        self.profile,self.root,self.workspace,self.enabled,self.clock=profile,Path(root).absolute(),workspace,enabled,clock
        self.directory=protected_path(directory,self.root) if directory is not None else None
        self.credential_file=protected_path(credential_file,self.root) if credential_file is not None else None
        self.expires_at=utc(credential_expires_at) if credential_expires_at is not None else None
        if (self.credential_file is None)!=(self.expires_at is None):raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONFIGURATION_INVALID',400)
        self.cipher_sha256=file_sha(self.credential_file) if self.credential_file is not None and self.credential_file.is_file() else None
        self.estimate=estimated_operation_cost_vnd
        if wire is not None and (type(wire) is not ProtocolFixtureDeliveryWire or wire.profile!=profile or wire.mock is not True or wire.network_enabled is not False):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_FIXTURE_INVALID',400)
        self.wire=wire or S3SDKDeliveryWire(profile,self.credential,network_enabled=enabled)
        self.configuration={'storage_profile':dict(profile.__dict__),'workspace_id':workspace,'state_root_sha256':digest(str(self.root)),'enabled':enabled,'mock':self.wire.mock,
            'credential_cipher_sha256':self.cipher_sha256,'credential_expires_at':self.expires_at.isoformat() if self.expires_at is not None else None,
            'estimated_operation_cost_vnd':self.estimate,'lease_directory_sha256':digest(str(self.directory)) if self.directory is not None else None}
        self.sha256=digest(self.configuration)
        self.frozen=(profile,profile.sha256,self.root,workspace,enabled,self.directory,self.credential_file,self.cipher_sha256,self.expires_at,self.estimate,self.wire,self.wire.mock,clock,self.sha256,digest(self.configuration))
    def check(self):
        if (self.profile,self.profile.sha256,self.root,self.workspace,self.enabled,self.directory,self.credential_file,self.cipher_sha256,self.expires_at,self.estimate,self.wire,self.wire.mock,self.clock,self.sha256,digest(self.configuration))!=self.frozen:
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONFIGURATION_CHANGED')
        if self.directory is not None and protected_path(self.directory,self.root)!=self.directory:raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONFIGURATION_CHANGED')
        if self.credential_file is not None and (protected_path(self.credential_file,self.root)!=self.credential_file
            or (file_sha(self.credential_file) if self.credential_file.is_file() else None)!=self.cipher_sha256):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_CREDENTIAL_CHANGED')
        if type(self.wire) is ProtocolFixtureDeliveryWire:self.wire.check()
    def public(self):
        self.check();configured=self.enabled and self.directory is not None and (self.wire.mock or self.cipher_sha256 is not None and self.expires_at>utc(self.clock())+timedelta(seconds=90) and self.estimate is not None)
        return {'schema_version':'native-publishing-media-delivery-factory-v1','workspace_id':self.workspace,'configuration_sha256':self.sha256,
            'status':'CONFIGURED' if configured else 'NOT_CONFIGURED','mock':self.wire.mock,'provider':'s3-publishing-media',
            'credential_returned':False,'url_returned':False,'publishing_authority':False,'automatic_delivery':False,'real_provider_tested':False}
    def credential(self,alias):
        from .assemblyai_connection import _dpapi
        try:
            self.check()
            if self.public()['status']!='CONFIGURED' or alias!=self.profile.credential_alias or self.wire.mock:raise ValueError()
            raw=self.credential_file.read_bytes()
            if not raw.startswith(PREFIX) or len(raw)>32768:raise ValueError()
            parsed=Credential.model_validate(json.loads(_dpapi(raw[len(PREFIX):],decrypt=True,entropy=ENTROPY),object_pairs_hook=unique_pairs))
            if (parsed.workspace_id!=self.workspace or parsed.storage_profile_sha256!=self.profile.sha256 or parsed.credential_alias!=alias
                or parsed.expires_at!=self.expires_at or parsed.expires_at<=utc(self.clock())+timedelta(seconds=90)):raise ValueError()
            return parsed.resolved()
        except Exception:raise MediaDeliveryError('MEDIA_DELIVERY_CREDENTIAL_UNAVAILABLE') from None


class Create(StrictModel):
    schema_version:Literal['native-publishing-media-delivery-request-v1']='native-publishing-media-delivery-request-v1'
    publication_id:str=Field(pattern=r'^nopu_[a-f0-9]{32}$')
    expected_publication_snapshot_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    expected_configuration_sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    ttl_seconds:StrictInt=Field(default=3600,ge=60,le=86400)
    valid_for_seconds:StrictInt=Field(default=900,ge=60,le=3600)
    max_external_cost_vnd:StrictInt=Field(default=0,ge=0,le=10**12)
    acknowledged_external_media_delivery:Literal[True]
    reconcile_delivery_id:str|None=Field(default=None,pattern=r'^nmd_[a-f0-9]{32}$')
    request_key:str=Field(min_length=16,max_length=200,pattern=r'^[A-Za-z0-9_-]+$')
    @field_validator('acknowledged_external_media_delivery',mode='before')
    @classmethod
    def explicit(cls,value):
        if value is not True:raise ValueError('Separate explicit media disclosure consent required')
        return value


class NativePublishingMediaDelivery:
    def __init__(self,journal,*,factory=None):
        if type(journal) is not NativeOfficialPublications or factory is not None and (type(factory) is not NativeMediaDeliveryFactory or factory.root!=journal.store.root.absolute() or factory.workspace!=journal.workspace):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_BINDING_INVALID',400)
        self.journal,self.store,self.workspace,self.factory=journal,journal.store,journal.workspace,factory;self.costs=CostLedger(self.store)
        with self.store.transaction() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS native_publishing_media_deliveries (
                delivery_id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL,project_id TEXT NOT NULL,key_sha256 TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,snapshot_sha256 TEXT NOT NULL,snapshot_json TEXT NOT NULL,status TEXT NOT NULL,
                lease_ref TEXT,lease_cipher_sha256 TEXT,result_json TEXT,result_sha256 TEXT,failure_code TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                UNIQUE(workspace_id,project_id,key_sha256));
                CREATE TABLE IF NOT EXISTS native_publishing_media_operations (
                operation_id TEXT PRIMARY KEY,delivery_id TEXT NOT NULL,ordinal INTEGER NOT NULL,operation TEXT NOT NULL,
                request_sha256 TEXT NOT NULL,cost_operation_id TEXT NOT NULL,status TEXT NOT NULL,response_json TEXT,response_sha256 TEXT,
                created_at TEXT NOT NULL,UNIQUE(delivery_id,ordinal));''')
    def row(self,con,project,identity):
        row=con.execute('SELECT * FROM native_publishing_media_deliveries WHERE workspace_id=? AND project_id=? AND delivery_id=?',(self.workspace,project,identity)).fetchone()
        if row is None:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_FOUND',404)
        return row
    def read(self,row):
        value=dict(row)
        try:
            snapshot=json.loads(value.pop('snapshot_json'));request=Create.model_validate({**snapshot['request'],'request_key':'internal-media-delivery-key'});scope=DeliveryScope(**snapshot['scope'])
            raw=value.pop('result_json');result=json.loads(raw) if raw else None
            checksum(snapshot['storage_profile_sha256']);checksum(snapshot['configuration_sha256']);checksum(snapshot['authority']['identity_revision_sha256'])
            consented=utc(datetime.fromisoformat(snapshot['consented_at']));expires=utc(datetime.fromisoformat(snapshot['expires_at']))
            if (set(snapshot)!={'schema_version','workspace_id','project_id','request','scope','configuration_sha256','storage_profile_sha256','approval_id','authority','consented_at','expires_at','mock','url_returned','publishing_authority'}
                or snapshot['request']!=request.model_dump(mode='json',exclude={'request_key'}) or snapshot['scope']!=scope.public()
                or not re.fullmatch('nmd_[a-f0-9]{32}',value['delivery_id']) or not re.fullmatch('nopa_[a-f0-9]{32}',snapshot['approval_id'])
                or set(snapshot['authority'])!={'token_id','subject','identity_revision_sha256','expires_at'}
                or not isinstance(snapshot['authority']['token_id'],str) or not isinstance(snapshot['authority']['subject'],str)
                or expires>utc(datetime.fromisoformat(snapshot['authority']['expires_at']))
                or digest(snapshot)!=value['snapshot_sha256'] or digest(snapshot['request'])!=value['request_sha256'] or snapshot['schema_version']!='native-publishing-media-delivery-snapshot-v1'
                or snapshot['workspace_id']!=self.workspace or value['workspace_id']!=self.workspace or snapshot['project_id']!=value['project_id']
                or scope.workspace_id!=self.workspace or scope.project_id!=value['project_id'] or scope.publication_id!=request.publication_id
                or scope.publication_snapshot_sha256!=request.expected_publication_snapshot_sha256 or snapshot['configuration_sha256']!=request.expected_configuration_sha256
                or type(snapshot['mock']) is not bool or snapshot['url_returned'] is not False or snapshot['publishing_authority'] is not False
                or not 60<=(expires-consented).total_seconds()<=request.valid_for_seconds
                or value['status'] not in {'queued','running','succeeded','not_configured','outcome_unknown','failed','cancelled','needs_approval'}
                or (value['status']=='succeeded')!=(result is not None)):raise ValueError()
            if result is None and any(value[k] is not None for k in ('result_sha256','lease_ref','lease_cipher_sha256')):raise ValueError()
            if result is not None and (set(result)!={'schema_version','delivery_id','snapshot_sha256','scope','verified_object','lease_issued_at','lease_expires_at','mock','url_returned','publishing_authority'}
                or result['schema_version']!='native-publishing-media-delivery-result-v1' or digest(result)!=value['result_sha256'] or result['delivery_id']!=value['delivery_id'] or result['snapshot_sha256']!=value['snapshot_sha256']
                or result['scope']!=snapshot['scope'] or result['mock'] is not snapshot['mock'] or result['url_returned'] is not False or result['publishing_authority'] is not False
                or result['verified_object']['scope']!=scope.public() or result['verified_object']['configuration_sha256']!=snapshot['storage_profile_sha256']
                or result['verified_object']['object_key']!=scope.object_key or result['verified_object']['mock'] is not snapshot['mock'] or result['verified_object']['verified_bytes'] is not True
                or not re.fullmatch('nml_[a-f0-9]{32}',value['lease_ref']) or not re.fullmatch('[a-f0-9]{64}',value['lease_cipher_sha256'])):raise ValueError()
            if result is not None:
                object=result['verified_object'];issued=utc(datetime.fromisoformat(result['lease_issued_at']));deadline=utc(datetime.fromisoformat(result['lease_expires_at']))
                if (set(object)!={'scope','configuration_sha256','object_key','etag','version_id','mock','verified_bytes'}
                    or type(object['etag']) is not str or not 1<=len(object['etag'])<=256 or any(ord(c)<33 or ord(c)==127 for c in object['etag'])
                    or type(object['version_id']) is not str or not 1<=len(object['version_id'])<=1024 or object['version_id']=='null' or any(ord(c)<33 or ord(c)==127 for c in object['version_id'])
                    or not consented<=issued<expires or not request.ttl_seconds-60<=(deadline-issued).total_seconds()<=request.ttl_seconds or deadline<=issued):raise ValueError()
            value.pop('key_sha256');return {**value,'schema_version':'native-publishing-media-delivery-v1','snapshot':snapshot,'result':result,'url_returned':False,'publishing_authority':False,'real_provider_tested':False}
        except Exception:raise WorkflowError('NATIVE_MEDIA_DELIVERY_EVIDENCE_CHANGED') from None
    def get(self,project,identity,*,con=None):
        from contextlib import nullcontext
        with (self.store.transaction() if con is None else nullcontext(con)) as con:
            value=self.read(self.row(con,project,identity));operations=[]
            parent=self.journal.get(project,value['snapshot']['scope']['publication_id'],con=con)
            scope=value['snapshot']['scope'];source=parent['snapshot']
            grant_row=con.execute('SELECT * FROM native_official_publish_approvals WHERE approval_id=? AND publication_id=? AND workspace_id=? AND project_id=?',
                (value['snapshot']['approval_id'],parent['publication_id'],self.workspace,project)).fetchone()
            try:
                grant=json.loads(grant_row['grant_json'])
                if (parent['snapshot_sha256']!=scope['publication_snapshot_sha256'] or parent['mock'] is not value['snapshot']['mock']
                    or any(source[k]!=scope[k] for k in ('final_job_id','final_sha256')) or source['final_bytes']!=scope['size_bytes']
                    or digest(grant)!=grant_row['grant_sha256'] or any(grant[k]!=parent[k] for k in ('publication_id','workspace_id','project_id','snapshot_sha256'))
                    or grant['mock'] is not value['snapshot']['mock'] or grant['acknowledged_official_publication'] is not True or grant['dry_run_approval_reused'] is not False
                    or not utc(datetime.fromisoformat(grant['issued_at']))<=utc(datetime.fromisoformat(value['snapshot']['consented_at']))<utc(datetime.fromisoformat(grant['expires_at']))
                    or utc(datetime.fromisoformat(value['snapshot']['expires_at']))>utc(datetime.fromisoformat(grant['expires_at']))):raise ValueError()
            except Exception:raise WorkflowError('NATIVE_MEDIA_DELIVERY_ORIGINAL_SOURCE_CHANGED') from None
            for row in con.execute('SELECT * FROM native_publishing_media_operations WHERE delivery_id=? ORDER BY ordinal',(identity,)):
                operation=dict(row);receipt=json.loads(operation.pop('response_json')) if row['response_json'] else None
                cost=con.execute('SELECT * FROM native_cost_operations WHERE id=?',(row['cost_operation_id'],)).fetchone()
                proof={'scope':value['snapshot']['scope'],'configuration_sha256':value['snapshot']['storage_profile_sha256'],'operation':row['operation'],
                    'object_key':DeliveryScope(**value['snapshot']['scope']).object_key,'mock':value['snapshot']['mock']}
                expected_operation='media_'+identity+'_'+str(row['ordinal'])+'_'+row['operation']
                if (cost is None or cost['project_id']!=project or cost['job_id']!=value['snapshot']['scope']['final_job_id']
                    or cost['provider']!='s3-publishing-media' or cost['request_sha256']!=row['request_sha256']
                    or row['operation'] not in {'head_object','get_object','put_object'} or type(row['ordinal']) is not int or row['ordinal']!=len(operations)+1
                    or row['request_sha256']!=digest(proof) or cost['operation']!=expected_operation
                    or cost['id']!=digest({'project':project,'job':cost['job_id'],'provider':'s3-publishing-media','operation':expected_operation})
                    or value['snapshot']['request']['reconcile_delivery_id'] is not None and row['operation']=='put_object'
                    or bool(cost['external_call'])==value['snapshot']['mock'] or bool(cost['paid'])==value['snapshot']['mock']
                    or cost['status']!=row['status'] or row['status'] not in {'dispatch_intent','response_received','rejected','outcome_unknown'}
                    or receipt is None and (row['response_sha256'] is not None or row['status'] not in {'dispatch_intent','outcome_unknown'})
                    or receipt is not None and (digest(receipt)!=row['response_sha256'] or receipt['status']!=row['status'] or cost['status']!=row['status']
                        or set(receipt)!={'status','response','error_code'}
                        or json.loads(cost['receipt'] or 'null')['provider_response_sha256']!=row['response_sha256'])):raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_EVIDENCE_CHANGED')
                if receipt is not None and receipt['response'] is not None and set(receipt['response'])!={'etag','version_id','size_bytes','checksum_sha256','object_found'}:
                    raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_EVIDENCE_CHANGED')
                operations.append({**operation,'response':receipt})
            if value['status']=='succeeded':
                names=tuple(r['operation'] for r in operations)
                if (names not in {('head_object','get_object','head_object','get_object'),('head_object','put_object','head_object','get_object','head_object','get_object')}
                    or any(r['status']!='response_received' for r in operations[-4:])):raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_EVIDENCE_CHANGED')
                object=value['result']['verified_object']
                for operation in operations[-4:]:
                    response=operation['response']['response']
                    if (response is None or response['object_found'] is not True or response['etag']!=object['etag'] or response['version_id']!=object['version_id']
                        or response['size_bytes']!=scope['size_bytes']):raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_EVIDENCE_CHANGED')
            return {**value,'operations':operations}
    def create(self,project,payload,*,principal):
        if type(payload) is not Create:raise WorkflowError('NATIVE_MEDIA_DELIVERY_FIELDS_INVALID',400)
        try:payload=Create.model_validate(payload.model_dump(mode='json'))
        except Exception:raise WorkflowError('NATIVE_MEDIA_DELIVERY_FIELDS_INVALID',400) from None
        authority=self.journal.identity(principal);request=payload.model_dump(mode='json',exclude={'request_key'});key=digest(payload.request_key)
        if self.factory is None:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_CONFIGURED')
        state=self.factory.public()
        with self.store.transaction() as con:
            prior=con.execute('SELECT * FROM native_publishing_media_deliveries WHERE workspace_id=? AND project_id=? AND key_sha256=?',(self.workspace,project,key)).fetchone()
            if prior is not None:
                if prior['request_sha256']!=digest(request):raise WorkflowError('NATIVE_MEDIA_DELIVERY_IDEMPOTENCY_CONFLICT')
                return self.get(project,prior['delivery_id'],con=con),True
            parent=self.journal.row(con,project,payload.publication_id);grant=self.journal.valid_grant(con,parent);public,_,_=self.journal.revalidate(con,parent)
            if public['snapshot_sha256']!=payload.expected_publication_snapshot_sha256 or state['configuration_sha256']!=payload.expected_configuration_sha256 or public['mock'] is not state['mock']:
                raise WorkflowError('NATIVE_MEDIA_DELIVERY_SOURCE_CHANGED')
            scope=DeliveryScope(self.workspace,project,public['snapshot']['final_job_id'],public['publication_id'],public['snapshot_sha256'],public['snapshot']['final_sha256'],public['snapshot']['final_bytes'])
            if scope.size_bytes>MAX_SINGLE_UPLOAD_BYTES:raise WorkflowError('NATIVE_MEDIA_DELIVERY_MULTIPART_NOT_IMPLEMENTED')
            previous=None
            if payload.reconcile_delivery_id is not None:
                previous=self.read(self.row(con,project,payload.reconcile_delivery_id))
                if previous['status'] not in {'outcome_unknown','succeeded','cancelled'} or previous['snapshot']['scope']!=scope.public() or previous['snapshot']['configuration_sha256']!=state['configuration_sha256']:
                    raise WorkflowError('NATIVE_MEDIA_DELIVERY_RECONCILIATION_BINDING_CHANGED')
            else:
                for row in con.execute("SELECT * FROM native_publishing_media_deliveries WHERE workspace_id=? AND project_id=? AND status NOT IN ('failed','not_configured','needs_approval')",(self.workspace,project)):
                    prior=self.read(row)
                    if prior['status']=='cancelled' and not con.execute("SELECT 1 FROM native_publishing_media_operations WHERE delivery_id=? AND operation='put_object'",(prior['delivery_id'],)).fetchone():continue
                    if prior['snapshot']['scope']==scope.public() and prior['snapshot']['configuration_sha256']==state['configuration_sha256']:
                        raise WorkflowError('NATIVE_MEDIA_DELIVERY_EXISTING_REVIEW_REQUIRED')
            instant=utc(self.journal.clock());expires=min(instant+timedelta(seconds=payload.valid_for_seconds),utc(datetime.fromisoformat(grant['expires_at'])),utc(datetime.fromisoformat(authority['expires_at'])))
            if (expires-instant).total_seconds()<60:raise WorkflowError('NATIVE_MEDIA_DELIVERY_OWNER_GRANT_EXPIRING')
            snapshot={'schema_version':'native-publishing-media-delivery-snapshot-v1','workspace_id':self.workspace,'project_id':project,'request':request,'scope':scope.public(),
                'configuration_sha256':state['configuration_sha256'],'storage_profile_sha256':self.factory.profile.sha256,'approval_id':parent['approval_id'],'authority':authority,'consented_at':instant.isoformat(),'expires_at':expires.isoformat(),
                'mock':state['mock'],'url_returned':False,'publishing_authority':False}
            identity='nmd_'+uuid.uuid4().hex;stamp=now();status='queued' if state['status']=='CONFIGURED' else 'not_configured'
            con.execute('INSERT INTO native_publishing_media_deliveries VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(identity,self.workspace,project,key,digest(request),digest(snapshot),json.dumps(snapshot),status,None,None,None,None,None,stamp,stamp))
            self.store.event(con,project,'publishing.media.delivery.requested',{'delivery_id':identity,'snapshot_sha256':digest(snapshot),'mock':state['mock'],'publishing_authority':False})
            return self.read(self.row(con,project,identity)),False
    def admit(self,con,value,*,expected_status='running'):
        if self.factory is None or self.factory.public()['status']!='CONFIGURED' or self.factory.sha256!=value['snapshot']['configuration_sha256']:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_CONFIGURED')
        snapshot=value['snapshot'];instant=utc(self.journal.clock())
        if not utc(datetime.fromisoformat(snapshot['consented_at']))<=instant<utc(datetime.fromisoformat(snapshot['expires_at'])):raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONSENT_EXPIRED')
        if not snapshot['mock'] and self.factory.expires_at<=instant+timedelta(seconds=snapshot['request']['ttl_seconds']+60):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_CREDENTIAL_LIFETIME_TOO_SHORT')
        authority=self.journal.identity(token_id=snapshot['authority']['token_id'],subject=snapshot['authority']['subject'])
        if authority!=snapshot['authority']:raise WorkflowError('NATIVE_MEDIA_DELIVERY_OWNER_CHANGED')
        parent=self.journal.row(con,value['project_id'],snapshot['scope']['publication_id']);self.journal.valid_grant(con,parent)
        if parent['approval_id']!=snapshot['approval_id'] or parent['snapshot_sha256']!=snapshot['scope']['publication_snapshot_sha256']:raise WorkflowError('NATIVE_MEDIA_DELIVERY_OWNER_CHANGED')
        _,_,path=self.journal.revalidate(con,parent)
        if value['status']!=expected_status:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_RUNNING')
        return path
    def process(self,project,identity):
        with self.store.transaction() as con:
            row=self.row(con,project,identity)
            if row['status']!='queued':raise WorkflowError('NATIVE_MEDIA_DELIVERY_NO_AUTOMATIC_REPLAY')
            con.execute("UPDATE native_publishing_media_deliveries SET status='running',updated_at=? WHERE delivery_id=?",(now(),identity))
        ordinal=[0];put_started=[False]
        def observer(action,proof,ticket):
            if action in {'before','sign'}:
                with self.store.transaction() as con:
                    current=self.read(self.row(con,project,identity));self.admit(con,current)
                    if action=='sign':return None
                    request_hash=digest(proof);paid=not current['snapshot']['mock'];estimate=self.factory.estimate if paid else None
                    spent=sum(int(r[0] or 0) for r in con.execute("SELECT estimated_cost FROM native_cost_operations WHERE project_id=? AND provider='s3-publishing-media' AND operation LIKE ?",(project,'media_'+identity+'_%')))
                    if paid and (estimate is None or spent+estimate>current['snapshot']['request']['max_external_cost_vnd']):raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_APPROVAL_REQUIRED')
                ordinal[0]+=1;operation='media_'+identity+'_'+str(ordinal[0])+'_'+proof['operation']
                cost=self.costs.begin(project_id=project,job_id=current['snapshot']['scope']['final_job_id'],provider='s3-publishing-media',model=None,operation=operation,
                    request_sha256=request_hash,estimated_cost=estimate,external_call=paid,paid=paid)
                op=uuid.uuid4().hex
                try:
                    with self.store.transaction() as con:
                        self.admit(con,self.read(self.row(con,project,identity)))
                        con.execute('INSERT INTO native_publishing_media_operations VALUES(?,?,?,?,?,?,?,?,?,?)',(op,identity,ordinal[0],proof['operation'],request_hash,cost,'dispatch_intent',None,None,now()))
                except Exception:
                    self.costs.settle(cost,status='rejected',error_code='NATIVE_MEDIA_DELIVERY_NOT_SENT');raise
                if proof['operation']=='put_object':put_started[0]=True
                return {'operation_id':op,'cost_operation_id':cost}
            receipt={'status':proof['status'],'response':proof.get('response'),'error_code':proof.get('error_code')};response_sha=digest(receipt)
            # Preserve the normalized known response first. If interrupted
            # before cost settlement, recovery can finish the same receipt
            # locally without replaying or guessing the provider result.
            with self.store.transaction() as con:
                con.execute('UPDATE native_publishing_media_operations SET status=?,response_json=?,response_sha256=? WHERE operation_id=? AND status=?',(proof['status'],json.dumps(receipt),response_sha,ticket['operation_id'],'dispatch_intent'))
            self.costs.settle(ticket['cost_operation_id'],status=proof['status'],response_sha256=response_sha,error_code=proof.get('error_code'))
        try:
            with self.store.transaction() as con:
                value=self.read(self.row(con,project,identity));path=self.admit(con,value)
            adapter=S3PublishingMediaDelivery(self.factory.profile,self.factory.wire,observer,clock=self.journal.clock);scope=DeliveryScope(**value['snapshot']['scope'])
            object=adapter.stage(scope,path,allow_create=value['snapshot']['request']['reconcile_delivery_id'] is None)
            lease=adapter.lease(object,ttl_seconds=value['snapshot']['request']['ttl_seconds']);reference='nml_'+uuid.uuid4().hex
            private={'schema_version':'native-publishing-media-lease-v1','delivery_id':identity,'snapshot_sha256':value['snapshot_sha256'],'object':object.public(),
                'issued_at':lease.issued_at.isoformat(),'expires_at':lease.expires_at.isoformat(),'url':lease.url}
            cipher=save_private(self.factory.directory/(reference+'.dpapi'),self.store.root,private,prefix=LEASE_PREFIX,entropy=LEASE_ENTROPY)
            result={'schema_version':'native-publishing-media-delivery-result-v1','delivery_id':identity,'snapshot_sha256':value['snapshot_sha256'],'scope':scope.public(),
                'verified_object':object.public(),'lease_issued_at':lease.issued_at.isoformat(),'lease_expires_at':lease.expires_at.isoformat(),'mock':value['snapshot']['mock'],'url_returned':False,'publishing_authority':False}
            with self.store.transaction() as con:
                self.admit(con,self.read(self.row(con,project,identity)))
                con.execute("UPDATE native_publishing_media_deliveries SET status='succeeded',lease_ref=?,lease_cipher_sha256=?,result_json=?,result_sha256=?,updated_at=? WHERE delivery_id=?",(reference,cipher,json.dumps(result),digest(result),now(),identity))
        except Exception as error:
            code=error.code if isinstance(error,(WorkflowError,MediaDeliveryError)) else 'NATIVE_MEDIA_DELIVERY_OPERATION_FAILED'
            if not re.fullmatch('[A-Z0-9_]{1,120}',code):code='NATIVE_MEDIA_DELIVERY_OPERATION_FAILED'
            status='needs_approval' if code in {'NATIVE_MEDIA_DELIVERY_COST_APPROVAL_REQUIRED','AI_COST_APPROVAL_REQUIRED_BEFORE_DISPATCH'} else 'outcome_unknown' if put_started[0] else 'failed'
            with self.store.transaction() as con:con.execute('UPDATE native_publishing_media_deliveries SET status=?,failure_code=?,updated_at=? WHERE delivery_id=? AND status=?',(status,code,now(),identity,'running'))
        return self.get(project,identity)
    def resolve_for_consumer(self,project,identity,*,publication_snapshot_sha256,consumer_mock,minimum_valid_seconds=120):
        """Private worker-only value. Public history/backup never reads this file.

        This resolves media disclosure consent only. A Meta worker must separately
        obtain its own execution-capable publication intent before sending a URL.
        """
        from .assemblyai_connection import _dpapi
        value=self.get(project,identity)
        if (type(consumer_mock) is not bool or consumer_mock is not value['snapshot']['mock'] or type(minimum_valid_seconds) is not int
            or not 1<=minimum_valid_seconds<=3600 or publication_snapshot_sha256!=value['snapshot']['scope']['publication_snapshot_sha256']):
            raise WorkflowError('NATIVE_MEDIA_DELIVERY_CONSUMER_BINDING_CHANGED')
        with self.store.transaction() as con:self.admit(con,value,expected_status='succeeded')
        try:
            path=protected_path(self.factory.directory/(value['lease_ref']+'.dpapi'),self.store.root)
            if not path.is_file() or file_sha(path)!=value['lease_cipher_sha256']:raise ValueError()
            raw=path.read_bytes()
            if not raw.startswith(LEASE_PREFIX) or len(raw)>32768:raise ValueError()
            private=json.loads(_dpapi(raw[len(LEASE_PREFIX):],decrypt=True,entropy=LEASE_ENTROPY),object_pairs_hook=unique_pairs)
            result=value['result'];scope=DeliveryScope(**result['scope']);object=result['verified_object']
            if (set(private)!={'schema_version','delivery_id','snapshot_sha256','object','issued_at','expires_at','url'}
                or private['schema_version']!='native-publishing-media-lease-v1' or private['delivery_id']!=identity or private['snapshot_sha256']!=value['snapshot_sha256']
                or private['object']!=object or private['issued_at']!=result['lease_issued_at'] or private['expires_at']!=result['lease_expires_at']):raise ValueError()
            verified=VerifiedMediaObject(scope,object['configuration_sha256'],object['object_key'],object['etag'],object['version_id'],object['mock'])
            adapter=S3PublishingMediaDelivery(self.factory.profile,self.factory.wire,lambda *args:None,clock=self.journal.clock)
            lease=adapter.validate_lease(verified,private['url'],utc(datetime.fromisoformat(private['issued_at'])),value['snapshot']['request']['ttl_seconds'],
                expires_at=utc(datetime.fromisoformat(private['expires_at'])))
            if utc(self.journal.clock())+timedelta(seconds=minimum_valid_seconds)>=lease.expires_at:raise ValueError()
            self.factory.check()
            if file_sha(path)!=value['lease_cipher_sha256']:raise ValueError()
        except Exception:raise WorkflowError('NATIVE_MEDIA_DELIVERY_PRIVATE_LEASE_UNAVAILABLE') from None
        with self.store.transaction() as con:self.admit(con,self.read(self.row(con,project,identity)),expected_status='succeeded')
        return lease
    def recover(self):
        with self.store.transaction() as con:
            identities=[r[0] for r in con.execute("SELECT delivery_id FROM native_publishing_media_deliveries WHERE workspace_id=?",(self.workspace,))]
            count=con.execute("UPDATE native_publishing_media_deliveries SET status='outcome_unknown',failure_code='NATIVE_MEDIA_DELIVERY_INTERRUPTED_NO_REPLAY',updated_at=? WHERE workspace_id=? AND status='running'",(now(),self.workspace)).rowcount
        for identity in identities:
            with self.store.transaction() as con:
                value=self.read(con.execute('SELECT * FROM native_publishing_media_deliveries WHERE delivery_id=?',(identity,)).fetchone())
                pending=list(con.execute("SELECT * FROM native_cost_operations WHERE provider='s3-publishing-media' AND operation LIKE ? AND status='dispatch_intent'",('media_'+identity+'_%',)))
                operations={r['cost_operation_id']:dict(r) for r in con.execute('SELECT * FROM native_publishing_media_operations WHERE delivery_id=?',(identity,))}
            for cost in pending:
                operation=operations.get(cost['id'])
                if operation is not None and operation['response_json'] is not None:
                    try:
                        receipt=json.loads(operation['response_json'])
                        if (digest(receipt)!=operation['response_sha256'] or receipt['status']!=operation['status'] or cost['request_sha256']!=operation['request_sha256']
                            or cost['project_id']!=value['project_id'] or cost['job_id']!=value['snapshot']['scope']['final_job_id']):raise ValueError()
                    except Exception:raise WorkflowError('NATIVE_MEDIA_DELIVERY_COST_EVIDENCE_CHANGED') from None
                    self.costs.settle(cost['id'],status=receipt['status'],response_sha256=operation['response_sha256'],error_code=receipt['error_code'])
                else:self.costs.settle(cost['id'],status='outcome_unknown',error_code='NATIVE_MEDIA_DELIVERY_INTERRUPTED_NO_REPLAY')
            with self.store.transaction() as con:
                con.execute("UPDATE native_publishing_media_operations SET status='outcome_unknown' WHERE delivery_id=? AND status='dispatch_intent'",(identity,))
        return count
    def cancel(self,project,identity,*,principal):
        self.journal.identity(principal)
        with self.store.transaction() as con:
            value=self.read(self.row(con,project,identity))
            if value['status'] not in {'queued','running','not_configured','needs_approval'}:raise WorkflowError('NATIVE_MEDIA_DELIVERY_RECONCILIATION_REQUIRED')
            con.execute("UPDATE native_publishing_media_deliveries SET status='cancelled',updated_at=? WHERE delivery_id=?",(now(),identity))
        return self.get(project,identity)
