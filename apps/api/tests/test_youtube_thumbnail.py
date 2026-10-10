"""Official PNG protocol fixtures; no live transport, credential or legal review."""
import hashlib,json,struct,zlib
from dataclasses import asdict,replace
from urllib.parse import parse_qs,urlsplit
import httpx,pytest
from app.publishing_models import PublicationMetadata
from app.publishing_wire import OfficialHTTPClient,OfficialResponse,PublishingWireError
from app.youtube_thumbnail import MAX_PNG_BYTES,MAX_EDGE,png_image,thumbnail_set_request,thumbnail_set_observation
from app.youtube_upload import start_request

TOKEN='explicit-thumbnail-fixture-token-'+'x'*48
VIDEO='AbcD_12-345'
def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
def png(width=3,height=4,channels=3,*,scanlines=None,interlace=0):
    raw=scanlines if scanlines is not None else (b'\x00'+b'\x19\x8b\xd7'*(width) if channels==3 else b'\x00'+b'\x19\x8b\xd7\xff'*width)*height
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2 if channels==3 else 6,0,0,interlace))+chunk(b'IDAT',zlib.compress(raw))+chunk(b'IEND',b'')
def request(content=None):
    content=png() if content is None else content
    return thumbnail_set_request(VIDEO,content,TOKEN,expected_sha256=hashlib.sha256(content).hexdigest())
def body(**changes):return {'kind':'youtube#thumbnailSetResponse','etag':'EXPLICIT-SYNTHETIC-ETAG','items':[{'default':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg'}}],**changes}
def response(value=None,status=200):return OfficialResponse(status,{},json.dumps(body() if value is None else value).encode())


def test_exact_png_video_official_origin_body_headers_and_sha_without_invented_idempotency():
    r=request();assert r.method=='POST';assert urlsplit(r.url).path=='/upload/youtube/v3/thumbnails/set'
    assert parse_qs(urlsplit(r.url).query)=={'uploadType':['media'],'videoId':[VIDEO]}
    assert r.headers['Content-Type']=='image/png' and r.headers['Content-Length']==str(len(r.body))
    assert set(r.headers)=={'Authorization','Content-Type','Content-Length'}
    assert TOKEN not in repr(r) and '\\x89PNG' not in repr(r)
    for color in (3,4):
        b=png(channels=color);image=png_image(b,hashlib.sha256(b).hexdigest());assert (image.width,image.height,image.bytes)==(3,4,len(b))


@pytest.mark.parametrize('content',[b'not PNG',png()[:-1],png()+b'PRIVATE_TRAILER',png(interlace=1),png(width=MAX_EDGE+1),png(scanlines=b'\x00short'),png(scanlines=b'\x05'+b'\x00'*9+b'\x00'+b'\x00'*9+b'\x00'+b'\x00'*9+b'\x00'+b'\x00'*9),
    b'\x89PNG\r\n\x1a\n'+b'\0'*(MAX_PNG_BYTES)], ids=['magic','truncated','trailing','interlaced','edge','short-scanlines','filter','oversized'])
def test_bad_magic_truncation_trailing_bytes_interlace_dimensions_decompression_and_filters_reject(content):
    with pytest.raises(PublishingWireError,match='PNG_PROFILE_INVALID'):request(content)


def test_crc_changed_sha_bombs_incomplete_or_concatenated_streams_fail_before_any_transport():
    valid=png();bad=bytearray(valid);bad[-1]^=1
    bodies=[bytes(bad),png(scanlines=b'\x00'*(MAX_EDGE*MAX_EDGE*4+1))]
    ihdr=chunk(b'IHDR',struct.pack('>IIBBBBB',3,4,8,2,0,0,0));scanlines=(b'\0'+b'\x00'*9)*4
    for data in (zlib.compress(scanlines)[:-2],zlib.compress(scanlines)+zlib.compress(scanlines)):
        bodies.append(b'\x89PNG\r\n\x1a\n'+ihdr+chunk(b'IDAT',data)+chunk(b'IEND',b''))
    for content in bodies:
        with pytest.raises(PublishingWireError):request(content)
    with pytest.raises(PublishingWireError):thumbnail_set_request(VIDEO,valid,TOKEN,expected_sha256='a'*64)


def test_duplicate_palette_reserved_chunk_bit_noncontiguous_data_and_unknown_critical_are_rejected():
    content=png();header_end=33;idat_end=len(content)-12;palette=chunk(b'PLTE',b'\0\0\0')
    bodies=[content[:header_end]+palette*2+content[header_end:],
        content[:header_end]+chunk(b'tExt',b'fixture')+content[header_end:],
        content[:idat_end]+chunk(b'tEXt',b'fixture')+chunk(b'IDAT',b'')+content[idat_end:],
        content[:header_end]+chunk(b'ABCD',b'fixture')+content[header_end:]]
    for value in bodies:
        with pytest.raises(PublishingWireError):request(value)


def test_acknowledgement_retains_null_dimensions_hashes_private_references_and_cannot_claim_remote_pixels_or_rights():
    observed=thumbnail_set_observation(response(),request());assert observed.remote_video_id==VIDEO
    assert observed.original_image.sha256==hashlib.sha256(png()).hexdigest()
    assert observed.variants[0].width is None and observed.variants[0].height is None
    assert observed.provider_response_acknowledged is True
    assert not observed.remote_image_bytes_verified and not observed.rights_independently_verified and not observed.publishing_authorized
    raw=json.dumps(asdict(observed));assert 'https://' not in raw and 'EXPLICIT-SYNTHETIC-ETAG' not in raw and TOKEN not in raw
    assert thumbnail_set_observation(response(body(etag=None)),request()).etag_sha256 is None


@pytest.mark.parametrize('item',[{}, {'default':{'url':'http://i.ytimg.com/vi/'+VIDEO+'/default.jpg'}}, {'default':{'url':'https://evil.invalid/vi/'+VIDEO+'/default.jpg'}},
    {'default':{'url':'https://i.ytimg.com/vi/OTHERID0001/default.jpg'}}, {'default':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg?access_token=PRIVATE'}},
    {'default':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg','width':True}}, {'default':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg','height':0}},
    {'default':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg','api_key':'PRIVATE'}}, {'unknown':{'url':f'https://i.ytimg.com/vi/{VIDEO}/default.jpg'}}])
def test_unsafe_foreign_unknown_or_ambiguous_variant_evidence_is_uncertain_and_never_replayed(item):
    with pytest.raises(PublishingWireError) as error:thumbnail_set_observation(response(body(items=[item])),request())
    assert error.value.uncertain and 'PRIVATE' not in str(error.value)


def test_non_success_empty_duplicate_or_changed_request_binding_never_assumes_completion():
    for status in (400,403,404,429,500):
        with pytest.raises(PublishingWireError) as error:thumbnail_set_observation(response(status=status),request())
        assert error.value.uncertain
    for value in (body(items=[]),body(items=body()['items']*2),body(kind='WRONG'),body(api_key='PRIVATE')):
        with pytest.raises(PublishingWireError):thumbnail_set_observation(response(value),request())
    duplicate=OfficialResponse(200,{},b'{"kind":"youtube#thumbnailSetResponse","kind":"wrong","items":[]}')
    with pytest.raises(PublishingWireError):thumbnail_set_observation(duplicate,request())
    for changed in (replace(request(),headers=dict(request().headers),method='GET'),replace(request(),headers=dict(request().headers),url=request().url+'&videoId=OTHERID0001'),replace(request(),headers=dict(request().headers),url=request().url.replace('/thumbnails/set','/videos'))):
        with pytest.raises(PublishingWireError,match='REQUEST_BINDING_INVALID'):thumbnail_set_observation(response(),changed)


@pytest.mark.asyncio
async def test_one_official_mock_post_preserves_original_png_and_disabled_transport_cannot_dispatch():
    calls=[]
    def handler(r):
        calls.append(r);assert r.method=='POST' and r.content==png();return httpx.Response(200,json=body())
    client=OfficialHTTPClient('youtube',transport=httpx.MockTransport(handler));r=request()
    assert thumbnail_set_observation(await client.request(r),r).remote_video_id==VIDEO;assert len(calls)==1
    with pytest.raises(PublishingWireError,match='EXTERNAL_PUBLISHING_NOT_ACTIVATED'):await OfficialHTTPClient('youtube').request(r)
    assert len(calls)==1


def test_new_protocol_does_not_remove_video_upload_guard_or_silently_drop_requested_thumbnail():
    metadata=PublicationMetadata(title='Explicit fixture',thumbnail_asset_id='ast_explicit_thumbnail')
    with pytest.raises(PublishingWireError,match='YOUTUBE_THUMBNAIL_STAGE_REQUIRED'):
        start_request(metadata,100,TOKEN,category_id='27',made_for_kids=False,contains_synthetic_media=True)
