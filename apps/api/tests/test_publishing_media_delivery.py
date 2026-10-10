"""Provider contracts with actual local byte streams and explicit S3 protocol/SDK mocks."""
import hashlib,io,logging
from datetime import datetime,timezone
from pathlib import Path
import pytest
from app.publishing_media_delivery import (DeliveryScope,StorageProfile,StorageCredential,S3PublishingMediaDelivery,S3SDKDeliveryWire,MediaDeliveryError,private_sdk_logging,MAX_SINGLE_UPLOAD_BYTES)
from services.windows_native.tests.media_delivery_fixture import FixtureStore

@pytest.fixture
def fixture(tmp_path):
    clock=lambda:datetime.now(timezone.utc);profile=StorageProfile('https://fixture-storage.invalid','vf-media-fixture','us-east-1','media-fixture-credential')
    storage=FixtureStore(profile,clock);events=[]
    def observer(action,proof,ticket):events.append((action,proof));return len(events)
    data=b'EXPLICIT NONPLAYABLE MEDIA DELIVERY BYTE FIXTURE'*100;path=tmp_path/'final.mp4';path.write_bytes(data)
    scope=DeliveryScope('wsp_fixture','a'*32,'b'*32,'nopu_'+'c'*32,'d'*64,hashlib.sha256(data).hexdigest(),len(data))
    adapter=S3PublishingMediaDelivery(profile,storage.wire,observer,clock=clock)
    return adapter,storage,events,scope,path,data

def test_conditional_upload_exact_stream_readback_and_private_authorized_lease(fixture):
    adapter,storage,events,scope,path,data=fixture;obj=adapter.stage(scope,path,allow_create=True);lease=adapter.lease(obj,ttl_seconds=120)
    assert storage.puts==1 and obj.scope==scope and obj.mock is True and storage.objects[scope.object_key]['data']==data
    assert lease.url.startswith(adapter.profile.public_prefix+scope.object_key) and 'X-Amz-' not in repr(lease)
    assert all(body.closed for body in storage.bodies) and len([e for e in events if e[0]=='before'])==6
    assert adapter.stage(scope,path,allow_create=True)==obj and storage.puts==1

def test_unknown_write_read_only_recovery_never_repeats_upload(fixture):
    adapter,storage,events,scope,path,data=fixture;storage.lose_reply=True
    with pytest.raises(MediaDeliveryError,match='UNCONFIRMED') as error:adapter.stage(scope,path,allow_create=True)
    assert error.value.uncertain and storage.puts==1
    storage.lose_reply=False;obj=adapter.stage(scope,path,allow_create=False);assert obj.scope==scope and storage.puts==1

def test_read_only_missing_object_never_opens_source_or_creates(fixture):
    adapter,storage,events,scope,path,data=fixture;path.unlink()
    with pytest.raises(MediaDeliveryError,match='READ_ONLY'):adapter.stage(scope,path)
    assert storage.puts==0 and len(storage.calls)==1

def test_source_and_delivered_byte_tampering_are_rejected_not_overwritten(fixture):
    adapter,storage,events,scope,path,data=fixture;path.write_bytes(b'changed')
    with pytest.raises(MediaDeliveryError,match='SOURCE_CHANGED'):adapter.stage(scope,path,allow_create=True)
    assert storage.puts==0;path.write_bytes(data);adapter.stage(scope,path,allow_create=True)
    storage.objects[scope.object_key]['data']=b'X'*len(data)
    with pytest.raises(MediaDeliveryError,match='OBJECT_CHANGED'):adapter.verify(scope)
    assert storage.puts==1 and all(body.closed for body in storage.bodies)

@pytest.mark.parametrize('change',[{'workspace_id':'../other'},{'size_bytes':True},{'final_sha256':'invalid'},{'publication_id':'foreign'},{'content_type':'text/plain'}])
def test_scopes_are_typed_and_workspace_bound(fixture,change):
    adapter,storage,events,scope,path,data=fixture
    with pytest.raises(MediaDeliveryError):DeliveryScope(**{**scope.public(),**change})

@pytest.mark.parametrize('url',['https://foreign.invalid/final.mp4','http://fixture-storage.invalid/vf-media-fixture/final.mp4','https://fixture-storage.invalid/vf-media-fixture/../foreign.mp4'])
def test_signer_cannot_supply_arbitrary_or_foreign_url(fixture,url):
    adapter,storage,events,scope,path,data=fixture;obj=adapter.stage(scope,path,allow_create=True);storage.url_override=url
    with pytest.raises(MediaDeliveryError,match='AUTHORIZED_URL'):adapter.lease(obj)

def test_sdk_default_is_inert_and_credentials_never_enter_repr(fixture):
    adapter,storage,events,scope,path,data=fixture;calls=[]
    sdk=S3SDKDeliveryWire(adapter.profile,lambda alias:calls.append(alias))
    with pytest.raises(MediaDeliveryError,match='NOT_CONFIGURED'):sdk.call('head_object',{'Bucket':adapter.profile.bucket,'Key':scope.object_key})
    assert calls==[] and sdk.clients is None
    secret=StorageCredential('EXPLICIT-FIXTURE-ACCESS','EXPLICIT-FIXTURE-SECRET');assert 'EXPLICIT' not in repr(secret)
    with pytest.raises(MediaDeliveryError):StorageCredential('EXPLICIT-FIXTURE-ACCESS','EXPLICIT-FIXTURE-SECRET','invalid\nheader')

def test_observer_receipt_failure_is_not_reclassified_or_called_twice(fixture):
    adapter,storage,events,scope,path,data=fixture;count=[]
    def observer(action,proof,ticket):
        if action=='after':count.append(action);raise RuntimeError('Explicit evidence persistence outage')
    failing=S3PublishingMediaDelivery(adapter.profile,storage.wire,observer)
    # Existing object makes the first SDK response known; this is not a missing-object error.
    adapter.stage(scope,path,allow_create=True)
    with pytest.raises(MediaDeliveryError,match='EVIDENCE_NOT_SAVED'):failing.verify(scope)
    assert count==['after'] and storage.puts==1

def test_sdk_contract_and_local_signing_use_real_boto_sdk_without_network(fixture):
    from botocore.stub import Stubber,ANY
    from botocore.response import StreamingBody
    adapter,storage,events,scope,path,data=fixture
    credential=StorageCredential('EXPLICITFIXTUREACCESS','EXPLICIT-FIXTURE-SECRET-KEY-0000000000000000')
    wire=S3SDKDeliveryWire(adapter.profile,lambda _:credential,network_enabled=True);client=wire.client()
    response={'ContentLength':len(data),'ContentType':'video/mp4','Metadata':{'sha256':scope.final_sha256},'ETag':'"fixture-etag"','VersionId':'explicit-sdk-fixture-version'}
    base={'Bucket':adapter.profile.bucket,'Key':scope.object_key}
    with Stubber(client) as stub:
        stub.add_client_error('head_object',service_error_code='404',http_status_code=404,expected_params=base)
        stub.add_response('put_object',{'ETag':'"fixture-etag"'},{**base,'Body':ANY,'ContentLength':len(data),'ContentType':'video/mp4','IfNoneMatch':'*',
            'ChecksumSHA256':ANY,'Metadata':{'sha256':scope.final_sha256}})
        stub.add_response('head_object',response,base)
        stub.add_response('get_object',{**response,'Body':StreamingBody(io.BytesIO(data),len(data))},{**base,'VersionId':'explicit-sdk-fixture-version'})
        actual=S3PublishingMediaDelivery(adapter.profile,wire,lambda *args:None);object=actual.stage(scope,path,allow_create=True)
        stub.assert_no_pending_responses()
    # Presigning is local cryptographic work and sends no S3 request.
    url=wire.sign(scope.object_key,120,'explicit-sdk-fixture-version');assert url.startswith(adapter.profile.public_prefix+scope.object_key) and 'X-Amz-Signature=' in url and object.mock is False
    actual.validate_lease(object,url,datetime.now(timezone.utc),120)

@pytest.mark.parametrize('version',[None,'null'])
def test_unversioned_objects_cannot_issue_pull_url_lease(fixture,version):
    adapter,storage,events,scope,path,data=fixture;adapter.stage(scope,path,allow_create=True)
    storage.objects[scope.object_key]['VersionId']=version;object=adapter.verify(scope)
    with pytest.raises(MediaDeliveryError,match='VERSIONED_OBJECT_REQUIRED'):adapter.lease(object)

def test_multipart_limit_is_explicit_before_any_source_open_or_external_operation(fixture):
    adapter,storage,events,scope,path,data=fixture;larger=DeliveryScope(**{**scope.public(),'size_bytes':MAX_SINGLE_UPLOAD_BYTES+1})
    with pytest.raises(MediaDeliveryError,match='MULTIPART_NOT_IMPLEMENTED'):adapter.stage(larger,path,allow_create=True)
    assert storage.calls==[] and events==[]

@pytest.mark.parametrize('change',[{'versionId':'foreign-version'},{'X-Amz-SignedHeaders':'host;authorization'},{'unexpected':'disclosure'},{'X-Amz-Credential':'foreign/region/scope'}])
def test_signed_query_is_exact_version_and_host_only_without_extra_disclosure(fixture,change):
    from urllib.parse import urlsplit,parse_qs,urlencode,urlunsplit
    adapter,storage,events,scope,path,data=fixture;object=adapter.stage(scope,path,allow_create=True)
    parts=urlsplit(storage.sign(scope.object_key,120,object.version_id));query={k:v[0] for k,v in parse_qs(parts.query).items()};query.update(change)
    storage.url_override=urlunsplit((parts.scheme,parts.netloc,parts.path,urlencode(query),parts.fragment))
    with pytest.raises(MediaDeliveryError,match='AUTHORIZED_URL'):adapter.lease(object,ttl_seconds=120)

def test_sdk_logs_hide_private_request_context_and_restore_normal_logging(caplog):
    logger=logging.getLogger('botocore.auth')
    with caplog.at_level(logging.DEBUG):
        with private_sdk_logging():logger.debug('EXPLICIT-PRIVATE-SIGNED-URL-FIXTURE')
        logger.debug('normal-public-message')
    assert 'EXPLICIT-PRIVATE' not in caplog.text and 'normal-public-message' in caplog.text
