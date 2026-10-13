"""Official stock APIs; scoped 24h caching, attributed licenses, bounded bytes.

No protected-platform scraper, arbitrary host, automatic paid call or fabricated
semantic score. Constructors are inert unless explicitly enabled with a key.
"""
from __future__ import annotations
import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime,timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import uuid
import httpx
from .media_intelligence_models import StockMediaCandidateRead
from .media_intelligence_providers import MediaProviderNotConfigured,ProviderMaterializedMedia
from .stock_retry_policy import retry_delay
from .stock_wire_context import CURRENT_OPERATION
from .stock_cache_policy import StockCachePolicy,StockResponseCache,StockCacheError,linked as cache_linked
from dataclasses import asdict

CACHE_SECONDS=86400
JSON_LIMIT=2*1024*1024
SCOPE=ContextVar('video_factory_stock_workspace',default=None)


@contextmanager
def stock_request_scope(workspace_id):
    if not isinstance(workspace_id,str) or not 1<=len(workspace_id)<=200:raise ValueError('STOCK_WORKSPACE_SCOPE_REQUIRED')
    token=SCOPE.set(workspace_id)
    try:yield
    finally:SCOPE.reset(token)


class StockProviderFailure(RuntimeError):
    def __init__(self,code,*,retryable=False,retry_after_seconds=None):
        super().__init__(code);self.code=code;self.retryable=retryable;self.retry_after_seconds=retry_after_seconds


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def cache_io_path(path):
    """Windows long-path IO only; callers validate ordinary path containment first."""
    path=Path(path).absolute();value=str(path)
    if os.name=='nt' and len(value)>=240 and not value.startswith('\\\\?\\'):
        return Path('\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value)
    return path


def linked(path):
    return cache_linked(path)


class CredentialTransport(httpx.AsyncBaseTransport):
    """Inject only at the wire boundary; HTTPX's logged request stays secret-free."""
    def __init__(self,inner,key,provider):self.inner,self.key,self.provider=inner,key,provider
    async def handle_async_request(self,request):
        url=request.url;headers=httpx.Headers(request.headers)
        if self.provider=='pexels' and url.host=='api.pexels.com':headers['Authorization']=self.key
        elif self.provider=='pixabay' and url.host=='pixabay.com' and url.path.startswith('/api/'):
            url=url.copy_merge_params({'key':self.key})
        forwarded=httpx.Request(request.method,url,headers=headers,stream=request.stream,extensions=request.extensions)
        return await self.inner.handle_async_request(forwarded)
    async def aclose(self):await self.inner.aclose()


class OfficialStockProvider:
    external=True
    paid=False
    real_provider_tested=False
    api_host=''
    cdn_hosts=frozenset()
    license=''
    license_url=''
    source_host=''

    def __init__(self,*,api_key='',enabled=False,cache_root:Path,cache_scope=None,transport=None,
                 timeout_seconds=20,max_download_bytes=250*1024*1024,cache_configuration_sha256=None,
                 wire_guard=None,require_wire_guard=False,cache_policy=None):
        if not 1<=timeout_seconds<=60 or not 1<=max_download_bytes<=250*1024*1024:
            raise ValueError('STOCK_BOUNDS_INVALID')
        if not isinstance(api_key,str) or len(api_key)>8192 or any(c in api_key for c in '\r\n'):
            raise ValueError('STOCK_CREDENTIAL_INVALID')
        if cache_configuration_sha256 is not None and (not isinstance(cache_configuration_sha256,str)
                or not re.fullmatch(r'[a-f0-9]{64}',cache_configuration_sha256)):
            raise ValueError('STOCK_CACHE_CONFIGURATION_INVALID')
        self.configured=bool(enabled and api_key);self._api_key=api_key
        self.cache_root=Path(cache_root);self.cache_scope=cache_scope
        self.timeout_seconds=timeout_seconds;self.max_download_bytes=max_download_bytes
        self._transport=transport;self._client=None;self._cache_lock=asyncio.Lock()
        self.mock_transport_used=isinstance(transport,httpx.MockTransport)
        self.cache_configuration_sha256=cache_configuration_sha256
        self.cache_policy=cache_policy or StockCachePolicy()
        if type(self.cache_policy) is not StockCachePolicy:raise ValueError('STOCK_CACHE_POLICY_INVALID')
        self._frozen_cache_policy=digest(asdict(self.cache_policy))
        self._cache_write_skips=0;self._cache_write_last_code=None
        self.cache_mode='fixture' if self.mock_transport_used else 'official'
        self.cache_binding_sha256=digest(self._cache_binding())
        self._frozen_cache_identity=(self.cache_binding_sha256,self.cache_mode,self.cache_configuration_sha256)
        if type(require_wire_guard) is not bool:raise ValueError('STOCK_WIRE_GUARD_CONFIGURATION_INVALID')
        self.wire_guard,self.require_wire_guard=wire_guard,require_wire_guard

    def _cache_binding(self):
        """Hash execution identity; neither the secret nor filesystem path is cached."""
        return {'schema_version':'stock-response-cache-binding.v2','provider':self.key,
            'credential_sha256':hashlib.sha256(self._api_key.encode()).hexdigest(),
            'configured':self.configured,'execution_mode':'fixture' if isinstance(self._transport,httpx.MockTransport) else 'official',
            'root_sha256':digest(str(self.cache_root.resolve())),
            'timeout_seconds':self.timeout_seconds,'max_download_bytes':self.max_download_bytes,
            'configuration_sha256':self.cache_configuration_sha256}

    async def aclose(self):
        if self._client:await self._client.aclose();self._client=None

    def _require(self):
        if not self.configured:raise MediaProviderNotConfigured('STOCK_PROVIDER_NOT_CONFIGURED')
        if ((self.cache_binding_sha256,self.cache_mode,self.cache_configuration_sha256)!=self._frozen_cache_identity
                or digest(self._cache_binding())!=self.cache_binding_sha256
                or self.mock_transport_used!=(self.cache_mode=='fixture')):
            raise StockProviderFailure('STOCK_CACHE_CONFIGURATION_CHANGED')
        if type(self.cache_policy) is not StockCachePolicy or digest(asdict(self.cache_policy))!=self._frozen_cache_policy:
            raise StockProviderFailure('STOCK_CACHE_POLICY_CHANGED')
        scope=self.cache_scope or SCOPE.get()
        if not isinstance(scope,str) or not 1<=len(scope)<=200:raise ValueError('STOCK_WORKSPACE_SCOPE_REQUIRED')
        return scope

    def _http(self):
        if self._client is None:
            inner=self._transport or httpx.AsyncHTTPTransport(retries=0,trust_env=False)
            self._client=httpx.AsyncClient(transport=CredentialTransport(inner,self._api_key,self.key),
                timeout=self.timeout_seconds,follow_redirects=False,trust_env=False)
        return self._client

    def _url(self,value,hosts):
        if not isinstance(value,str) or len(value)>2000:raise StockProviderFailure('STOCK_URL_INVALID')
        parsed=urlsplit(value)
        try:port=parsed.port
        except ValueError:raise StockProviderFailure('STOCK_URL_INVALID') from None
        if (parsed.scheme!='https' or parsed.hostname not in hosts or port not in (None,443) or parsed.username
                or parsed.password or parsed.fragment or '\\' in value or any(ord(c)<33 for c in value)
                or re.search(r'(?:^|[&?])(?:key|api_key|access_token|token)=',parsed.query,re.I)):
            raise StockProviderFailure('STOCK_URL_INVALID')
        return value

    async def _response(self,url,params=None,*,limit):
        workspace=self._require();lease=None;status=None;headers=None
        if self.require_wire_guard and self.wire_guard is None:
            raise StockProviderFailure('STOCK_WIRE_GUARD_NOT_CONFIGURED')
        host=urlsplit(url).hostname
        request_class='api' if host==self.api_host else 'cdn' if host in self.cdn_hosts else None
        if request_class is None:raise StockProviderFailure('STOCK_WIRE_HOST_INVALID')
        if self.wire_guard is not None:
            lease=await self.wire_guard.admit(self,workspace,request_class)
        try:
            async with asyncio.timeout(self.timeout_seconds):
                async with self._http().stream('GET',url,params=params) as response:
                    status=response.status_code;headers=response.headers
                    if response.status_code!=200:
                        retryable=response.status_code in {429,500,502,503,504}
                        clock=getattr(self.wire_guard,'clock',time.time)
                        seconds=retry_delay(response.headers,float(clock())) if retryable else None
                        raise StockProviderFailure('STOCK_RATE_LIMITED' if response.status_code==429 else 'STOCK_HTTP_FAILED',
                            retryable=retryable,retry_after_seconds=seconds)
                    declared=response.headers.get('Content-Length')
                    if declared and (not declared.isdigit() or int(declared)>limit):raise StockProviderFailure('STOCK_RESPONSE_TOO_LARGE')
                    chunks=[];size=0
                    async for chunk in response.aiter_bytes():
                        size+=len(chunk)
                        if size>limit:raise StockProviderFailure('STOCK_RESPONSE_TOO_LARGE')
                        chunks.append(chunk)
                    return b''.join(chunks),response.headers.get('Content-Type','').split(';')[0].lower()
        except (httpx.HTTPError,TimeoutError):raise StockProviderFailure('STOCK_NETWORK_FAILED',retryable=True) from None
        finally:
            if lease is not None:await self.wire_guard.release(lease,status=status,headers=headers)

    def _cache_path(self,scope,key):
        path=self.cache_root/digest(scope)/self.key/(key+'.json')
        if linked(path) or self.cache_root.resolve() not in path.resolve().parents:raise StockProviderFailure('STOCK_CACHE_PATH_INVALID')
        return path

    def _cache_request(self,path,params):
        scope=self._require();key=digest({'provider':self.key,'path':path,'params':params,'schema':2,
            'binding_sha256':self.cache_binding_sha256})
        return scope,key,self._cache_path(scope,key)

    def _read_cache(self,scope,key,file):
        if Path(file).absolute()!=self._cache_path(scope,key).absolute():raise StockProviderFailure('STOCK_CACHE_PATH_INVALID')
        try:return self._response_cache(scope).read(key)
        except StockCacheError as error:raise StockProviderFailure(str(error),retryable=str(error)=='STOCK_CACHE_BUSY',retry_after_seconds=1 if str(error)=='STOCK_CACHE_BUSY' else None) from None

    def _response_cache(self,scope):
        return StockResponseCache(self.cache_root,scope_sha256=digest(scope),provider=self.key,binding_sha256=self.cache_binding_sha256,
            execution_mode=self.cache_mode,configuration_sha256=self.cache_configuration_sha256,policy=self.cache_policy,clock=lambda:time.time())

    async def cache_maintenance(self):
        scope=self._require()
        try:return await asyncio.to_thread(self._response_cache(scope).maintain)
        except StockCacheError as error:raise StockProviderFailure(str(error)) from None

    def _cache_write_skipped(self,code):
        if code not in {'STOCK_CACHE_SCAN_LIMIT','STOCK_CACHE_BUSY','STOCK_CACHE_IO_FAILED','STOCK_CACHE_WRITE_UNAVAILABLE',
            'STOCK_CACHE_GROWTH_BLOCKED','STOCK_CACHE_ENTRY_NOT_STORED'}:raise ValueError('STOCK_CACHE_DIAGNOSTIC_INVALID')
        self._cache_write_skips=min(100000,self._cache_write_skips+1);self._cache_write_last_code=code

    def cache_write_diagnostics(self):
        """Process-local opaque counts; never infer provider health from cache IO."""
        return {'schema_version':'stock-response-cache-write-diagnostic.v1','skipped_writes':self._cache_write_skips,
            'last_code':self._cache_write_last_code,'cache_limits_bypassed':False,'provider_health_inferred':False}

    async def cached_metadata(self,provider_asset_id):
        path,params=self._metadata_request(provider_asset_id)
        scope,key,file=self._cache_request(path,params)
        body=await asyncio.to_thread(self._read_cache,scope,key,file)
        return (digest(scope)+':'+key,body) if body is not None else None

    async def _json(self,path,params):
        scope,key,file=self._cache_request(path,params);memo_key=digest(scope)+':'+key
        operation=CURRENT_OPERATION.get()
        if operation is not None and memo_key in operation.cached_inputs:
            return operation.cached_inputs[memo_key]
        cached_body=await asyncio.to_thread(self._read_cache,scope,key,file)
        if cached_body is not None:return cached_body
        # Neither the filesystem lock nor an asyncio cache lock spans wire/quota.
        raw,mime=await self._response('https://'+self.api_host+path,params,limit=JSON_LIMIT)
        if mime!='application/json' or self._api_key.encode() in raw:raise StockProviderFailure('STOCK_RESPONSE_INVALID')
        try:body=json.loads(raw)
        except ValueError:raise StockProviderFailure('STOCK_RESPONSE_INVALID') from None
        if not isinstance(body,dict):raise StockProviderFailure('STOCK_RESPONSE_INVALID')
        cached={'schema':2,'scope':digest(scope),'key':key,'provider':self.key,
            'binding_sha256':self.cache_binding_sha256,'execution_mode':self.cache_mode,
            'configuration_sha256':self.cache_configuration_sha256,
            'created_at':time.time(),'response':body,'sha256':digest(body)}
        try:
            result=await asyncio.to_thread(self._response_cache(scope).write,key,cached)
            if not result['stored']:self._cache_write_skipped(result['code'])
        except StockCacheError as error:
            if str(error) not in {'STOCK_CACHE_SCAN_LIMIT','STOCK_CACHE_BUSY','STOCK_CACHE_IO_FAILED'}:
                raise StockProviderFailure(str(error)) from None
            self._cache_write_skipped(str(error))
        except OSError:
            # Optional local cache IO cannot discard a validated provider 200.
            # Read corruption/path/binding checks above retain their fail-closed
            # boundary; no quota state is cleared and no limit is bypassed.
            self._cache_write_skipped('STOCK_CACHE_WRITE_UNAVAILABLE')
        return body

    @staticmethod
    def _orientation(value):
        # Native journals preserve their original "any" DTO/fingerprint. The
        # neutral provider contract uses "unknown" to omit an orientation filter.
        if value not in {'portrait','landscape','square','unknown','any'}:
            raise ValueError('STOCK_SEARCH_INVALID')
        return 'unknown' if value=='any' else value

    def _query(self,query,orientation,limit):
        if (not isinstance(query,str) or not query.strip() or len(query)>500 or orientation not in {'portrait','landscape','square','unknown'}
                or type(limit) is not int or not 1<=limit<=80):raise ValueError('STOCK_SEARCH_INVALID')
        return ' '.join(query.split())

    def _candidate(self,item,media_type,*,url,width,height,rank=None,query=None):
        identifier=str(item['id'])
        if not re.fullmatch(r'[1-9][0-9]{0,11}',identifier):raise StockProviderFailure('STOCK_ASSET_ID_INVALID')
        page=self._url(item['url'] if self.key=='pexels' else item['pageURL'],{self.source_host,'www.'+self.source_host})
        download=self._url(url,self.cdn_hosts)
        creator=(item.get('photographer') if media_type=='image' else (item.get('user') or {}).get('name')) if self.key=='pexels' else item.get('user')
        duration=item.get('duration') if media_type=='video' else None
        if not creator:raise StockProviderFailure('STOCK_CREATOR_MISSING')
        return StockMediaCandidateRead(candidate_id='smc_'+digest([self.key,media_type,identifier])[:24],provider=self.key,
            provider_asset_id=media_type+':'+identifier,creator=str(creator),source_reference=page,
            license=self.license,license_url=self.license_url,
            attribution_requirement='Display provider/source link and credit creator where possible; retain license restrictions',
            width=width,height=height,duration_seconds=duration,
            orientation='unknown' if not width or not height else 'square' if width==height else 'portrait' if height>width else 'landscape',
            media_type=media_type,semantic_score=None,rights_status='licensed',production_eligible=False,
            estimated_cost_vnd=Decimal(0),provenance={'provider':self.key,'authorized_source':True,'external_call':True,
                'paid':False,'fixture':self.mock_transport_used,'mock_transport_used':self.mock_transport_used,
                'cache_binding_sha256':self.cache_binding_sha256,'cache_execution_mode':self.cache_mode,
                'cache_configuration_sha256':self.cache_configuration_sha256,
                'real_provider_tested':False,'download_url':download,'provider_result_rank':rank,
                'query':query,'description':item.get('alt') if self.key=='pexels' else item.get('tags'),
                'licensing_basis':'provider content license; third-party/personality/trademark rights not independently verified',
                'license_url':self.license_url,'metadata_normalized_at':datetime.now(timezone.utc).isoformat(),
                'rights_independently_verified':False,'social_media_downloaded':False,'needs_attention':True,
                'source_metadata_dimensions_only':True,'production_acceptance_required':True})

    async def download_asset(self,candidate):
        self._require()
        if candidate.provider!=self.key or candidate.rights_status!='licensed':raise ValueError('STOCK_CANDIDATE_INVALID')
        # Re-fetch by canonical provider ID; client-supplied URLs/rights are ignored.
        trusted=await self.get_asset(candidate.provider_asset_id)
        url=self._url(trusted.provenance['download_url'],self.cdn_hosts)
        limit=min(self.max_download_bytes,32*1024*1024) if trusted.media_type=='image' else self.max_download_bytes
        raw,mime=await self._response(url,limit=limit)
        valid=(trusted.media_type=='image' and ((mime=='image/jpeg' and raw.startswith(b'\xff\xd8\xff')) or
            (mime=='image/png' and raw.startswith(b'\x89PNG\r\n\x1a\n')))) or (trusted.media_type=='video' and
            mime=='video/mp4' and len(raw)>=12 and raw[4:8]==b'ftyp')
        if not valid:raise StockProviderFailure('STOCK_MIME_MAGIC_MISMATCH')
        suffix={'image/jpeg':'.jpg','image/png':'.png','video/mp4':'.mp4'}[mime]
        return ProviderMaterializedMedia(filename=self.key+'-'+trusted.provider_asset_id.replace(':','-')+suffix,
            content_type=mime,payload=raw,provider_job_id=None,source_type='stock',rights_status='licensed',
            license=trusted.license,license_url=trusted.license_url,provider_asset_id=trusted.provider_asset_id,
            creator=trusted.creator,source_reference=trusted.source_reference,attribution_requirement=trusted.attribution_requirement,
            width=trusted.width,height=trusted.height,duration_seconds=trusted.duration_seconds,orientation=trusted.orientation,
            production_eligible=False,estimated_cost_vnd=Decimal(0),actual_cost_vnd=None,external_call=True,
            paid=False,real_provider_tested=False,generation_provenance={'provider':self.key,'licensed_stock':True,
                'real_provider_tested':False,'mock_transport_used':self.mock_transport_used,
                'fixture':self.mock_transport_used,'production_eligible':False,'complete_decode_required':True,
                'source_metadata_dimensions_only':True,'payload_sha256':hashlib.sha256(raw).hexdigest(),
                'licensing':trusted.provenance,'provider_pricing_basis':'official free stock API; local compute cost unknown',
                'actual_local_compute_cost':None})


class PexelsStockMediaProvider(OfficialStockProvider):
    key='pexels';api_host='api.pexels.com';source_host='pexels.com'
    cdn_hosts=frozenset({'images.pexels.com','videos.pexels.com'})
    license='Pexels License';license_url='https://www.pexels.com/license/'

    def _parse(self,item,kind,rank=None,query=None):
        try:
            if kind=='image':url=item['src']['original'];width=item['width'];height=item['height']
            else:
                files=[f for f in item['video_files'] if f.get('file_type')=='video/mp4' and f.get('width') and f.get('height')
                    and urlsplit(f.get('link','')).hostname in self.cdn_hosts]
                if not files:raise StockProviderFailure('STOCK_RENDITION_UNAVAILABLE')
                feasible=[f for f in files if max(f['width'],f['height'])<=1920]
                selected=max(feasible,key=lambda f:f['width']*f['height']) if feasible else min(files,key=lambda f:f['width']*f['height'])
                url=selected['link'];width=selected['width'];height=selected['height']
            return self._candidate(item,kind,url=url,width=width,height=height,rank=rank,query=query)
        except (KeyError,TypeError,ValueError,AttributeError):raise StockProviderFailure('STOCK_METADATA_INVALID') from None

    async def _search(self,kind,query,orientation,limit):
        orientation=self._orientation(orientation)
        query=self._query(query,orientation,limit);params={'query':query,'per_page':limit}
        if orientation!='unknown':params['orientation']=orientation
        body=await self._json('/v1/search' if kind=='image' else '/v1/videos/search',params)
        items=body.get('photos' if kind=='image' else 'videos')
        if not isinstance(items,list):raise StockProviderFailure('STOCK_RESPONSE_INVALID')
        return [self._parse(item,kind,index+1,query) for index,item in enumerate(items[:limit])]

    async def search_images(self,query,*,orientation,limit):return await self._search('image',query,orientation,limit)
    async def search_videos(self,query,*,orientation,limit):return await self._search('video',query,orientation,limit)
    def _metadata_request(self,provider_asset_id):
        match=re.fullmatch(r'(image|video):([1-9][0-9]{0,11})',provider_asset_id)
        if not match:raise ValueError('STOCK_ASSET_ID_INVALID')
        kind,identifier=match.groups()
        return ('/v1/photos/' if kind=='image' else '/v1/videos/videos/')+identifier,{}

    async def get_asset(self,provider_asset_id):
        path,params=self._metadata_request(provider_asset_id)
        body=await self._json(path,params)
        kind,identifier=provider_asset_id.split(':')
        if str(body.get('id'))!=identifier:raise StockProviderFailure('STOCK_ASSET_BINDING_MISMATCH')
        return self._parse(body,kind)


class PixabayStockMediaProvider(OfficialStockProvider):
    key='pixabay';api_host='pixabay.com';source_host='pixabay.com'
    cdn_hosts=frozenset({'cdn.pixabay.com'})
    license='Pixabay Content License';license_url='https://pixabay.com/service/license-summary/'

    def _parse(self,item,kind,rank=None,query=None):
        try:
            if kind=='image':url=item['webformatURL'];width=item['webformatWidth'];height=item['webformatHeight']
            else:
                selected=item['videos']['medium'];url=selected['url'];width=selected['width'];height=selected['height']
            return self._candidate(item,kind,url=url,width=width,height=height,rank=rank,query=query)
        except (KeyError,TypeError,ValueError,AttributeError):raise StockProviderFailure('STOCK_METADATA_INVALID') from None

    async def _search(self,kind,query,orientation,limit):
        orientation=self._orientation(orientation)
        query=self._query(query,orientation,limit)
        if len(query)>100:raise ValueError('PIXABAY_QUERY_MAX_100_CHARACTERS')
        params={'q':query,'per_page':max(3,limit),'safesearch':'true'}
        if kind=='image':params['image_type']='photo'
        # Pixabay's square selection is a local filter; do not send an unsupported value.
        if kind=='image' and orientation in {'portrait','landscape'}:params['orientation']='vertical' if orientation=='portrait' else 'horizontal'
        body=await self._json('/api/' if kind=='image' else '/api/videos/',params)
        items=body.get('hits')
        if not isinstance(items,list):raise StockProviderFailure('STOCK_RESPONSE_INVALID')
        parsed=[self._parse(item,kind,index+1,query) for index,item in enumerate(items)]
        return [item for item in parsed if (orientation=='unknown' or
            kind=='image' and orientation!='square' or item.orientation==orientation)][:limit]

    async def search_images(self,query,*,orientation,limit):return await self._search('image',query,orientation,limit)
    async def search_videos(self,query,*,orientation,limit):return await self._search('video',query,orientation,limit)
    def _metadata_request(self,provider_asset_id):
        match=re.fullmatch(r'(image|video):([1-9][0-9]{0,11})',provider_asset_id)
        if not match:raise ValueError('STOCK_ASSET_ID_INVALID')
        kind,identifier=match.groups()
        return ('/api/' if kind=='image' else '/api/videos/'),{'id':identifier}

    async def get_asset(self,provider_asset_id):
        path,params=self._metadata_request(provider_asset_id)
        body=await self._json(path,params)
        kind,identifier=provider_asset_id.split(':')
        items=body.get('hits',[])
        if len(items)!=1 or str(items[0].get('id'))!=identifier:raise StockProviderFailure('STOCK_ASSET_BINDING_MISMATCH')
        return self._parse(items[0],kind)
