"""Official PNG thumbnail protocol; no transport, activation, retry or consent.

The bounded RGB/RGBA profile matches original Native rendered-QC PNGs. Provider
response acknowledgement does not verify remote pixels, rights or publishing.
"""
from dataclasses import dataclass
import hashlib,json,re,struct,zlib
from urllib.parse import parse_qsl,urlencode,urlsplit
from .publishing_wire import OfficialRequest,OfficialResponse,PublishingWireError,bearer_headers,official_url,MAX_RESPONSE
from .youtube_upload import video_id

MAX_PNG_BYTES=4*1024*1024  # Internal original-render profile, not vendor maximum.
MAX_EDGE=960
ENDPOINT='https://www.googleapis.com/upload/youtube/v3/thumbnails/set'
VARIANTS=frozenset({'default','medium','high','standard','maxres'})


@dataclass(frozen=True)
class ThumbnailImage:
    sha256:str
    bytes:int
    width:int
    height:int


def png_image(content,expected_sha256):
    """Validate bytes, CRCs and bounded complete noninterlaced 8-bit scanlines."""
    try:
        if (type(content) is not bytes or not 45<=len(content)<=MAX_PNG_BYTES or content[:8]!=b'\x89PNG\r\n\x1a\n'
            or not isinstance(expected_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',expected_sha256)
            or hashlib.sha256(content).hexdigest()!=expected_sha256):raise ValueError()
        offset=8;count=0;header=None;parts=[];idat_closed=False;palette_seen=False;ended=False
        while offset<len(content):
            count+=1
            if count>256 or len(content)-offset<12:raise ValueError()
            length=struct.unpack('>I',content[offset:offset+4])[0];kind=content[offset+4:offset+8];end=offset+12+length
            if end>len(content) or not re.fullmatch(rb'[A-Za-z]{4}',kind) or kind[2]&32:raise ValueError()
            data=content[offset+8:offset+8+length];crc=struct.unpack('>I',content[offset+8+length:end])[0]
            if zlib.crc32(kind+data)&0xffffffff!=crc:raise ValueError()
            if count==1 and kind!=b'IHDR':raise ValueError()
            if kind==b'IHDR':
                if header is not None or length!=13:raise ValueError()
                width,height,depth,color,compression,filtering,interlace=struct.unpack('>IIBBBBB',data)
                if not 3<=width<=MAX_EDGE or not 3<=height<=MAX_EDGE or depth!=8 or color not in (2,6) or (compression,filtering,interlace)!=(0,0,0):raise ValueError()
                header=(width,height,3 if color==2 else 4)
            elif kind==b'IDAT':
                if header is None or idat_closed:raise ValueError()
                parts.append(data)
            elif kind==b'IEND':
                if length or not parts or end!=len(content):raise ValueError()
                ended=True
            elif kind==b'PLTE':
                if palette_seen or parts or not length or length%3 or length>768:raise ValueError()
                palette_seen=True
            elif kind[0]&32==0:raise ValueError()  # Unsupported critical chunk.
            if parts and kind!=b'IDAT':idat_closed=True
            offset=end
        if not ended or header is None:raise ValueError()
        width,height,channels=header;stride=1+width*channels;expected=height*stride;decoder=zlib.decompressobj()
        scanlines=decoder.decompress(b''.join(parts),expected+1)
        if (len(scanlines)!=expected or not decoder.eof or decoder.unconsumed_tail or decoder.unused_data
            or any(scanlines[i]>4 for i in range(0,expected,stride))):raise ValueError()
        return ThumbnailImage(expected_sha256,len(content),width,height)
    except (ValueError,TypeError,struct.error,zlib.error,OverflowError):
        raise PublishingWireError('YOUTUBE_THUMBNAIL_PNG_PROFILE_INVALID') from None


def thumbnail_set_request(remote_video_id,content,token,*,expected_sha256):
    video_id(remote_video_id);png_image(content,expected_sha256)
    return OfficialRequest('POST',ENDPOINT+'?'+urlencode({'uploadType':'media','videoId':remote_video_id}),
        {**bearer_headers(token),'Content-Type':'image/png','Content-Length':str(len(content))},content)


@dataclass(frozen=True)
class ThumbnailVariant:
    name:str
    url_sha256:str
    width:int|None
    height:int|None


@dataclass(frozen=True)
class ThumbnailSetObservation:
    remote_video_id:str
    original_image:ThumbnailImage
    variants:tuple[ThumbnailVariant,...]
    etag_sha256:str|None
    provider_response_acknowledged:bool=True
    remote_image_bytes_verified:bool=False
    rights_independently_verified:bool=False
    publishing_authorized:bool=False


def request_binding(request):
    try:
        if type(request) is not OfficialRequest or request.method!='POST':raise ValueError()
        official_url(request.url,'youtube');parsed=urlsplit(request.url);pairs=parse_qsl(parsed.query,strict_parsing=True)
        if parsed.scheme+'://'+parsed.netloc+parsed.path!=ENDPOINT or len(pairs)!=2 or len(dict(pairs))!=2:raise ValueError()
        params=dict(pairs)
        if set(params)!={'uploadType','videoId'} or params['uploadType']!='media':raise ValueError()
        remote=video_id(params['videoId'])
        headers={k.lower():v for k,v in request.headers.items()}
        if set(headers)!={'authorization','content-type','content-length'} or headers['content-type']!='image/png' or headers['content-length']!=str(len(request.body)):raise ValueError()
        if not headers['authorization'].startswith('Bearer '):raise ValueError()
        bearer_headers(headers['authorization'][7:])
        return remote,png_image(request.body,hashlib.sha256(request.body).hexdigest())
    except (ValueError,TypeError,KeyError,PublishingWireError):raise PublishingWireError('YOUTUBE_THUMBNAIL_REQUEST_BINDING_INVALID') from None


def thumbnail_set_observation(response,request):
    """Associate a bounded acknowledgement with the exact outgoing body/video.

    Only URL/etag digests enter the observation. URLs are never fetched; images
    returned by the API may be resized and are not claimed byte-exact originals.
    """
    remote,image=request_binding(request)
    if type(response) is not OfficialResponse or type(response.status) is not int or response.status!=200:
        raise PublishingWireError('YOUTUBE_THUMBNAIL_NOT_CONFIRMED',status=getattr(response,'status',None),uncertain=True)
    try:
        if type(response.body) is not bytes or len(response.body)>MAX_RESPONSE:raise ValueError()
        def unique(pairs):
            result={}
            for key,value in pairs:
                if key in result:raise ValueError()
                result[key]=value
            return result
        value=json.loads(response.body,object_pairs_hook=unique)
        if (type(value) is not dict or set(value)-{'kind','etag','items'} or value.get('kind')!='youtube#thumbnailSetResponse'
            or type(value.get('items')) is not list or len(value['items'])!=1):raise ValueError()
        item=value['items'][0]
        if type(item) is not dict or not item or set(item)-VARIANTS:raise ValueError()
        variants=[]
        for name in sorted(item):
            v=item[name]
            if type(v) is not dict or set(v)-{'url','width','height'}:raise ValueError()
            url=v.get('url')
            if not isinstance(url,str) or not url.isascii() or not 1<=len(url)<=4096 or any(ord(c)<33 for c in url):raise ValueError()
            parsed=urlsplit(url);parsed.port
            # Internal video-thumbnail CDN profile; never use these URLs as a fetch instruction.
            if (parsed.scheme!='https' or parsed.hostname!='i.ytimg.com' or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443)
                or not re.fullmatch(r'/vi(?:_webp)?/'+re.escape(remote)+r'/[A-Za-z0-9_-]+\.(?:jpg|png|webp)',parsed.path)
                or any(re.search(r'(token|password|secret|api.?key|authorization|credential)',k,re.I) for k,_ in parse_qsl(parsed.query))):raise ValueError()
            dimensions=[v.get(k) for k in ('width','height')]
            if any(d is not None and (type(d) is not int or not 1<=d<=16384) for d in dimensions):raise ValueError()
            variants.append(ThumbnailVariant(name,hashlib.sha256(url.encode()).hexdigest(),*dimensions))
        etag=value.get('etag')
        if etag is not None and (not isinstance(etag,str) or not 1<=len(etag)<=512 or any(ord(c)<32 for c in etag)):raise ValueError()
        return ThumbnailSetObservation(remote,image,tuple(variants),hashlib.sha256(etag.encode()).hexdigest() if etag is not None else None)
    except (ValueError,TypeError,KeyError,RecursionError,OverflowError):
        raise PublishingWireError('YOUTUBE_THUMBNAIL_RESPONSE_UNCONFIRMED',status=response.status,uncertain=True) from None
