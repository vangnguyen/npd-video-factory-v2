"""Immutable, workspace-scoped S3 media delivery for official pull-URL publishing.

No startup credential discovery, bucket creation, public ACL or automatic retry.
An owned caller must authorize and journal every operation through the observer.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs, unquote
from contextlib import contextmanager
from contextvars import ContextVar
import base64, hashlib, json, logging, re

_private=ContextVar('vf_media_delivery_private',default=False)
MAX_SINGLE_UPLOAD_BYTES=5*1024**3
class _PrivateFilter(logging.Filter):
    def filter(self,record):return not _private.get()

@contextmanager
def private_sdk_logging():
    names={'botocore.auth','botocore.endpoint','botocore.credentials','botocore.httpsession','botocore.parsers','botocore.hooks','boto3.resources.action'}
    names.update(n for n in logging.Logger.manager.loggerDict if n.startswith(('botocore.','boto3.')))
    for name in names:
        logger=logging.getLogger(name)
        if not any(type(f) is _PrivateFilter for f in logger.filters):logger.addFilter(_PrivateFilter())
    token=_private.set(True)
    try:yield
    finally:_private.reset(token)


class MediaDeliveryError(RuntimeError):
    def __init__(self, code, *, uncertain=False):
        self.code,self.uncertain=code,uncertain;super().__init__(code)


def checksum(value):
    if type(value) is not str or not re.fullmatch('[a-f0-9]{64}',value):raise MediaDeliveryError('MEDIA_DELIVERY_SHA256_REQUIRED')
    return value


def sha(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def endpoint(value):
    try:
        p=urlsplit(value)
        if (type(value) is not str or not value.isascii() or not 1<=len(value)<=2048 or p.scheme!='https' or not p.hostname
            or p.username is not None or p.password is not None or p.port not in (None,443) or p.path not in ('','/') or p.query or p.fragment
            or any(ord(c)<33 or ord(c)==127 for c in value) or '\\' in value):raise ValueError()
        return value.rstrip('/')
    except (TypeError,ValueError):raise MediaDeliveryError('MEDIA_DELIVERY_HTTPS_ENDPOINT_REQUIRED') from None


@dataclass(frozen=True)
class DeliveryScope:
    workspace_id:str
    project_id:str
    final_job_id:str
    publication_id:str
    publication_snapshot_sha256:str
    final_sha256:str
    size_bytes:int
    content_type:str='video/mp4'

    def __post_init__(self):
        if (type(self.workspace_id) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,80}',self.workspace_id)
            or any(type(v) is not str or not re.fullmatch('[a-f0-9]{32}',v) for v in (self.project_id,self.final_job_id))
            or type(self.publication_id) is not str or not re.fullmatch('nopu_[a-f0-9]{32}',self.publication_id)
            or type(self.size_bytes) is not int or not 1<=self.size_bytes<=512*1024**3 or self.content_type!='video/mp4'):
            raise MediaDeliveryError('MEDIA_DELIVERY_SCOPE_REQUIRED')
        checksum(self.publication_snapshot_sha256);checksum(self.final_sha256)

    @property
    def object_key(self):
        return f'workspaces/{self.workspace_id}/projects/{self.project_id}/jobs/{self.final_job_id}/{self.final_sha256}/final.mp4'

    def public(self):return dict(self.__dict__)


@dataclass(frozen=True)
class StorageProfile:
    endpoint_url:str
    bucket:str
    region:str
    credential_alias:str
    public_endpoint_url:str|None=None

    def __post_init__(self):
        endpoint(self.endpoint_url)
        if self.public_endpoint_url is not None:endpoint(self.public_endpoint_url)
        if (type(self.bucket) is not str or not re.fullmatch('[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]',self.bucket)
            or '..' in self.bucket or re.fullmatch('[0-9.]+',self.bucket)
            or type(self.region) is not str or not re.fullmatch('[a-z0-9-]{1,64}',self.region)
            or type(self.credential_alias) is not str or not re.fullmatch('[a-z][a-z0-9-]{3,79}',self.credential_alias)):
            raise MediaDeliveryError('MEDIA_DELIVERY_STORAGE_PROFILE_INVALID')

    @property
    def sha256(self):return sha(self.__dict__)

    @property
    def public_prefix(self):return endpoint(self.public_endpoint_url or self.endpoint_url)+'/'+self.bucket+'/'


@dataclass(frozen=True)
class StorageCredential:
    access_key:str=field(repr=False)
    secret_key:str=field(repr=False)
    session_token:str|None=field(default=None,repr=False)

    def __post_init__(self):
        if any(type(v) is not str or not 8<=len(v)<=4096 or not v.isascii() or any(ord(c)<33 or ord(c)==127 for c in v)
            for v in (self.access_key,self.secret_key)) or self.session_token is not None and (type(self.session_token) is not str or not 8<=len(self.session_token)<=16384
                or not self.session_token.isascii() or any(ord(c)<33 or ord(c)==127 for c in self.session_token)):
            raise MediaDeliveryError('MEDIA_DELIVERY_CREDENTIAL_INVALID')


class S3SDKDeliveryWire:
    """Lazily resolved, bounded SDK with explicit credentials and zero SDK retries."""
    mock=False
    def __init__(self,profile,resolver,*,network_enabled=False):
        if type(profile) is not StorageProfile or not callable(resolver) or type(network_enabled) is not bool:raise MediaDeliveryError('MEDIA_DELIVERY_WIRE_INVALID')
        self.profile,self.resolver,self.network_enabled=profile,resolver,network_enabled
        self.frozen=(profile,resolver,network_enabled);self.clients=None

    def check(self):
        if (self.profile,self.resolver,self.network_enabled)!=self.frozen:raise MediaDeliveryError('MEDIA_DELIVERY_WIRE_CHANGED')
        if self.network_enabled is not True:raise MediaDeliveryError('MEDIA_DELIVERY_NOT_CONFIGURED')

    def client(self,*,signing=False):
        self.check()
        if self.clients is None:
            credential=self.resolver(self.profile.credential_alias)
            if type(credential) is not StorageCredential:raise MediaDeliveryError('MEDIA_DELIVERY_CREDENTIAL_INVALID')
            # Lazy dependency; importing the Native core does not initialize an SDK.
            import boto3
            from botocore.config import Config
            options={'region_name':self.profile.region,'aws_access_key_id':credential.access_key,'aws_secret_access_key':credential.secret_key,
                'aws_session_token':credential.session_token,'config':Config(signature_version='s3v4',connect_timeout=10,read_timeout=60,
                    retries={'total_max_attempts':1},s3={'addressing_style':'path'})}
            # Imports create additional SDK loggers. Fence construction after
            # those imports as well as the actual requests/signing operations.
            with private_sdk_logging():
                self.clients=(boto3.client('s3',endpoint_url=endpoint(self.profile.endpoint_url),**options),
                    boto3.client('s3',endpoint_url=endpoint(self.profile.public_endpoint_url or self.profile.endpoint_url),**options))
        return self.clients[1 if signing else 0]

    def call(self,operation,arguments):
        if operation not in {'head_object','get_object','put_object'}:raise MediaDeliveryError('MEDIA_DELIVERY_OPERATION_INVALID')
        try:
            with private_sdk_logging():return getattr(self.client(),operation)(**arguments)
        except MediaDeliveryError:raise
        except Exception as error:
            # SDK errors can contain credentials, signed URLs or private paths.
            code=(getattr(error,'response',{}) or {}).get('Error',{}).get('Code')
            if code in ('404','NoSuchKey','NotFound'):raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_ABSENT') from None
            if code in ('412','PreconditionFailed'):raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_ALREADY_EXISTS') from None
            raise MediaDeliveryError('MEDIA_DELIVERY_OPERATION_UNCONFIRMED',uncertain=operation=='put_object') from None

    def sign(self,key,ttl,version_id):
        if type(version_id) is not str or not 1<=len(version_id)<=1024 or version_id=='null' or any(ord(c)<33 or ord(c)==127 for c in version_id):
            raise MediaDeliveryError('MEDIA_DELIVERY_VERSIONED_OBJECT_REQUIRED')
        try:
            with private_sdk_logging():return self.client(signing=True).generate_presigned_url('get_object',Params={'Bucket':self.profile.bucket,'Key':key,'VersionId':version_id},ExpiresIn=ttl,HttpMethod='GET')
        except MediaDeliveryError:raise
        except Exception:raise MediaDeliveryError('MEDIA_DELIVERY_SIGNING_FAILED') from None


class ProtocolFixtureDeliveryWire:
    """Explicit injected fixture only; its objects cannot authorize a live consumer."""
    mock=True
    network_enabled=False
    def __init__(self,profile,handler,signer):
        if type(profile) is not StorageProfile or not callable(handler) or not callable(signer):raise MediaDeliveryError('MEDIA_DELIVERY_FIXTURE_INVALID')
        self.profile,self.handler,self.signer=profile,handler,signer;self.frozen=(profile,profile.sha256,handler,signer)
    def check(self):
        if self.mock is not True or self.network_enabled is not False or (self.profile,self.profile.sha256,self.handler,self.signer)!=self.frozen:
            raise MediaDeliveryError('MEDIA_DELIVERY_FIXTURE_CHANGED')
    def call(self,operation,arguments):
        self.check()
        if operation not in {'head_object','get_object','put_object'}:raise MediaDeliveryError('MEDIA_DELIVERY_OPERATION_INVALID')
        return self.handler(operation,arguments)
    def sign(self,key,ttl,version_id):self.check();return self.signer(key,ttl,version_id)


@dataclass(frozen=True)
class VerifiedMediaObject:
    scope:DeliveryScope
    configuration_sha256:str
    object_key:str
    etag:str
    version_id:str|None
    mock:bool

    def public(self):return {'scope':self.scope.public(),'configuration_sha256':self.configuration_sha256,'object_key':self.object_key,
        'etag':self.etag,'version_id':self.version_id,'mock':self.mock,'verified_bytes':True}


@dataclass(frozen=True)
class PublishingMediaLease:
    object:VerifiedMediaObject
    issued_at:datetime
    expires_at:datetime
    url:str=field(repr=False)


class S3PublishingMediaDelivery:
    """Observer is mandatory: commit intent/consent/cost before each SDK call."""
    def __init__(self,profile,wire,observer,*,clock=lambda:datetime.now(timezone.utc)):
        if type(profile) is not StorageProfile or not callable(observer) or not callable(clock) or getattr(wire,'mock',None) not in (True,False):
            raise MediaDeliveryError('MEDIA_DELIVERY_CONFIGURATION_INVALID')
        if type(wire.mock) is not bool or wire.profile!=profile:raise MediaDeliveryError('MEDIA_DELIVERY_CONFIGURATION_INVALID')
        self.profile,self.wire,self.observer,self.clock=profile,wire,observer,clock
        self.frozen=(profile,profile.sha256,wire,wire.mock,observer,clock)

    def check(self):
        if (self.profile,self.profile.sha256,self.wire,self.wire.mock,self.observer,self.clock)!=self.frozen:raise MediaDeliveryError('MEDIA_DELIVERY_CONFIGURATION_CHANGED')
        self.wire.check()

    def call(self,scope,operation,arguments,*,consume=None):
        self.check();proof={'scope':scope.public(),'configuration_sha256':self.profile.sha256,'operation':operation,'object_key':scope.object_key,'mock':self.wire.mock}
        ticket=self.observer('before',proof,None)
        try:
            value=self.wire.call(operation,arguments)
            result=consume(value) if consume is not None else value
            # Whitelisted receipt fields; never Body, headers, signed query or SDK exception text.
            response={'etag':value.get('ETag'),'version_id':value.get('VersionId'),'size_bytes':value.get('ContentLength'),
                'checksum_sha256':value.get('ChecksumSHA256'),'object_found':True}
        except MediaDeliveryError as error:
            self.observer('after',{'request':proof,'status':'outcome_unknown' if error.uncertain else 'rejected','error_code':error.code},ticket);raise
        except Exception:
            self.observer('after',{'request':proof,'status':'outcome_unknown' if operation=='put_object' else 'rejected','error_code':'MEDIA_DELIVERY_OPERATION_UNCONFIRMED'},ticket)
            raise MediaDeliveryError('MEDIA_DELIVERY_OPERATION_UNCONFIRMED',uncertain=operation=='put_object') from None
        # A receipt persistence error cannot transform a known response into a
        # second observer call or authorize repeating the provider mutation.
        try:self.observer('after',{'request':proof,'response':response,'status':'response_received'},ticket)
        except Exception:raise MediaDeliveryError('MEDIA_DELIVERY_EVIDENCE_NOT_SAVED',uncertain=operation=='put_object') from None
        return result

    def verify(self,scope):
        if type(scope) is not DeliveryScope:raise MediaDeliveryError('MEDIA_DELIVERY_SCOPE_REQUIRED')
        base={'Bucket':self.profile.bucket,'Key':scope.object_key}
        head=self.call(scope,'head_object',base)
        if (type(head.get('ContentLength')) is not int or head['ContentLength']!=scope.size_bytes or head.get('ContentType')!=scope.content_type
            or head.get('Metadata',{}).get('sha256')!=scope.final_sha256 or type(head.get('ETag')) is not str or not 1<=len(head['ETag'])<=256
            or any(ord(c)<32 for c in head['ETag'])):raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
        version=head.get('VersionId')
        if version is not None and (type(version) is not str or not 1<=len(version)<=1024 or any(ord(c)<33 for c in version)):
            raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
        def consume(response):
            body=response.get('Body');h=hashlib.sha256();total=0
            try:
                if body is None or not hasattr(body,'read'):raise MediaDeliveryError('MEDIA_DELIVERY_BYTES_REQUIRED')
                while True:
                    block=body.read(min(1024*1024,scope.size_bytes-total+1))
                    if type(block) is not bytes:raise MediaDeliveryError('MEDIA_DELIVERY_BYTES_REQUIRED')
                    if not block:break
                    total+=len(block)
                    if total>scope.size_bytes:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
                    h.update(block)
                if total!=scope.size_bytes or h.hexdigest()!=scope.final_sha256:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
                if response.get('ETag')!=head['ETag'] or response.get('VersionId')!=version:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
            finally:
                if body is not None and hasattr(body,'close'):body.close()
            return True
        self.call(scope,'get_object',{**base,**({'VersionId':version} if version is not None else {'IfMatch':head['ETag']})},consume=consume)
        return VerifiedMediaObject(scope,self.profile.sha256,scope.object_key,head['ETag'],version,self.wire.mock)

    def stage(self,scope,path,*,allow_create=False):
        if type(scope) is not DeliveryScope or type(allow_create) is not bool:raise MediaDeliveryError('MEDIA_DELIVERY_SCOPE_REQUIRED')
        # This durable adapter uses single conditional PUT, not unjournaled
        # automatic multipart retries. Larger delivery needs its own protocol.
        if scope.size_bytes>MAX_SINGLE_UPLOAD_BYTES:raise MediaDeliveryError('MEDIA_DELIVERY_MULTIPART_NOT_IMPLEMENTED')
        self.check()
        try:return self.verify(scope)
        except MediaDeliveryError as error:
            if error.code!='MEDIA_DELIVERY_OBJECT_ABSENT':raise
            if not allow_create:raise MediaDeliveryError('MEDIA_DELIVERY_READ_ONLY_RECOVERY_OBJECT_ABSENT') from None
        path=Path(path)
        with path.open('rb') as body:
            h=hashlib.sha256();total=0
            for block in iter(lambda:body.read(1024*1024),b''):total+=len(block);h.update(block)
            if total!=scope.size_bytes or h.hexdigest()!=scope.final_sha256:raise MediaDeliveryError('MEDIA_DELIVERY_SOURCE_CHANGED')
            body.seek(0)
            try:
                self.call(scope,'put_object',{'Bucket':self.profile.bucket,'Key':scope.object_key,'Body':body,'ContentLength':scope.size_bytes,
                    'ContentType':scope.content_type,'IfNoneMatch':'*','ChecksumSHA256':base64.b64encode(bytes.fromhex(scope.final_sha256)).decode(),
                    'Metadata':{'sha256':scope.final_sha256}})
            except MediaDeliveryError as error:
                if error.code!='MEDIA_DELIVERY_OBJECT_ALREADY_EXISTS':raise
        return self.verify(scope)  # Metadata/ETag alone never proves the delivered bytes.

    def lease(self,object,*,ttl_seconds=3600):
        if (type(object) is not VerifiedMediaObject or type(ttl_seconds) is not int or not 60<=ttl_seconds<=86400
            or object.configuration_sha256!=self.profile.sha256 or object.object_key!=object.scope.object_key or object.mock is not self.wire.mock):
            raise MediaDeliveryError('MEDIA_DELIVERY_LEASE_BINDING_CHANGED')
        if object.version_id in (None,'null'):raise MediaDeliveryError('MEDIA_DELIVERY_VERSIONED_OBJECT_REQUIRED')
        verified=self.verify(object.scope)
        if verified!=object:raise MediaDeliveryError('MEDIA_DELIVERY_OBJECT_CHANGED')
        self.check();instant=self.clock()
        if not isinstance(instant,datetime) or instant.tzinfo is None:raise MediaDeliveryError('MEDIA_DELIVERY_TIME_INVALID')
        # Authorize/sign locally too; it does not create an external object or billed response.
        self.observer('sign',{'scope':object.scope.public(),'configuration_sha256':self.profile.sha256,'mock':self.wire.mock},None)
        url=self.wire.sign(object.object_key,ttl_seconds,object.version_id)
        instant=self.clock()
        if not isinstance(instant,datetime) or instant.tzinfo is None:raise MediaDeliveryError('MEDIA_DELIVERY_TIME_INVALID')
        return self.validate_lease(object,url,instant,ttl_seconds)

    def validate_lease(self,object,url,issued_at,ttl_seconds,*,expires_at=None):
        """Local validation for issuance and sealed private consumer retrieval."""
        self.check()
        try:
            if (type(object) is not VerifiedMediaObject or type(object.scope) is not DeliveryScope or object.configuration_sha256!=self.profile.sha256
                or object.object_key!=object.scope.object_key or object.mock is not self.wire.mock or object.version_id in (None,'null')
                or type(ttl_seconds) is not int or not 60<=ttl_seconds<=86400 or not isinstance(issued_at,datetime) or issued_at.tzinfo is None):raise ValueError()
            parsed=urlsplit(url);query=parse_qs(parsed.query,keep_blank_values=True)
            allowed={'versionId','X-Amz-Algorithm','X-Amz-Credential','X-Amz-Date','X-Amz-Expires','X-Amz-SignedHeaders','X-Amz-Signature','X-Amz-Security-Token','X-Amz-Content-Sha256'}
            if (type(url) is not str or not url.isascii() or len(url)>8192 or not url.startswith(self.profile.public_prefix)
                or unquote(parsed.path)!=urlsplit(self.profile.public_prefix).path+object.object_key or parsed.fragment or parsed.username or parsed.password
                or set(query)-allowed or any(len(v)!=1 for v in query.values())
                or query.get('versionId')!=[object.version_id] or query.get('X-Amz-SignedHeaders')!=['host']
                or query.get('X-Amz-Expires')!=[str(ttl_seconds)] or query.get('X-Amz-Algorithm')!=['AWS4-HMAC-SHA256']
                or len(query.get('X-Amz-Signature',[]))!=1 or len(query.get('X-Amz-Credential',[]))!=1 or len(query.get('X-Amz-Date',[]))!=1
                or not re.fullmatch('[a-f0-9]{64}',query['X-Amz-Signature'][0]) or any(ord(c)<33 or ord(c)==127 for c in url)):
                raise ValueError()
            signed_at=datetime.strptime(query['X-Amz-Date'][0],'%Y%m%dT%H%M%SZ').replace(tzinfo=timezone.utc)
            credential=query['X-Amz-Credential'][0].split('/')
            if len(credential)!=5 or not credential[0] or credential[1:]!=[signed_at.strftime('%Y%m%d'),self.profile.region,'s3','aws4_request']:
                raise ValueError()
            deadline=signed_at+timedelta(seconds=ttl_seconds)
            if not 0<=(issued_at-signed_at).total_seconds()<=60 or deadline<=issued_at or expires_at is not None and deadline!=expires_at:raise ValueError()
            return PublishingMediaLease(object,issued_at,deadline,url)
        except (ValueError,TypeError,KeyError,AttributeError):raise MediaDeliveryError('MEDIA_DELIVERY_AUTHORIZED_URL_REQUIRED') from None
