"""Explicit Google Desktop OAuth primitives; no startup secret read or activation.

The caller owns current human authority, durable one-use callback/operation claims,
encrypted custody and account confirmation. Refresh never renews production consent.
"""
from dataclasses import dataclass,field
from datetime import datetime,timedelta,timezone
import base64,hashlib,hmac,json,re,secrets
from urllib.parse import parse_qsl,urlencode,urlsplit
import httpx
from .analytics_official import AnalyticsOAuthCredential,YT_READ,YT_ANALYTICS,YT_MONEY
from .publishing_credentials import PublishingOAuthCredential,UPLOAD,READ,target_digest
from .publishing_models import PublishingTargetBinding
from .publishing_wire import bearer_headers,_install_privacy_filters,_sensitive

AUTHORIZATION_URL='https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URL='https://oauth2.googleapis.com/token'
MAX_RESPONSE=32768

class GoogleOAuthError(RuntimeError):
    def __init__(self,code,*,uncertain=False,needs_reauthorization=False):
        self.code,self.uncertain,self.needs_reauthorization=code,uncertain,needs_reauthorization
        super().__init__(code)

def fail(code,**flags):raise GoogleOAuthError(code,**flags)
def instant(value=None):
    value=datetime.now(timezone.utc) if value is None else value
    if type(value) is not datetime or value.tzinfo is None:fail('GOOGLE_OAUTH_AWARE_CLOCK_REQUIRED')
    return value.astimezone(timezone.utc)
def checksum(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def pairs(raw,*,maximum=12):
    try:
        values=parse_qsl(raw,keep_blank_values=True,strict_parsing=True,max_num_fields=maximum)
        if len({k for k,v in values})!=len(values):raise ValueError()
        return dict(values)
    except Exception:fail('GOOGLE_OAUTH_FIELDS_INVALID')
def opaque(value,minimum=16,maximum=4096):
    return isinstance(value,str) and re.fullmatch(r'[A-Za-z0-9._~+/=-]{'+str(minimum)+','+str(maximum)+'}',value) is not None
def json_pairs(values):
    result={}
    for k,v in values:
        if k in result:raise ValueError()
        result[k]=v
    return result
def loopback(value):
    try:
        if not isinstance(value,str) or not value.isascii() or any(ord(c)<33 for c in value) or '\\' in value:raise ValueError()
        p=urlsplit(value)
        if p.scheme!='http' or p.hostname not in ('127.0.0.1','::1') or p.port is None or not 1<=p.port<=65535 or p.username is not None or p.password is not None or p.query or p.fragment or p.path not in ('','/','/oauth/google/callback'):raise ValueError()
        host='[::1]' if p.hostname=='::1' else '127.0.0.1'
        if value!='http://'+host+':'+str(p.port)+p.path:raise ValueError()
        return value
    except Exception:fail('GOOGLE_OAUTH_DESKTOP_LOOPBACK_REQUIRED')

@dataclass(frozen=True)
class GoogleDesktopClient:
    target:PublishingTargetBinding
    purpose:str
    client_id:str
    scopes:frozenset[str]
    client_secret:str|None=field(default=None,repr=False)
    def __post_init__(self):
        try:
            if type(self.target) is not PublishingTargetBinding:raise ValueError()
            parsed=PublishingTargetBinding.model_validate(self.target.model_dump(mode='python'))
            if parsed.platform!='youtube' or parsed.provider_key!='youtube-data-api-publishing' or type(self.scopes) is not frozenset:raise ValueError()
            allowed=({frozenset({YT_READ,YT_ANALYTICS}),frozenset({YT_READ,YT_ANALYTICS,YT_MONEY})} if self.purpose=='analytics' else {frozenset({UPLOAD,READ})} if self.purpose=='publishing' else set())
            if self.scopes not in allowed or not isinstance(self.client_id,str) or not re.fullmatch(r'[0-9]{1,30}-[A-Za-z0-9_-]{4,180}\.apps\.googleusercontent\.com',self.client_id):raise ValueError()
            if self.client_secret is not None and not opaque(self.client_secret,8,4096):raise ValueError()
            object.__setattr__(self,'target',parsed.model_copy(deep=True))
        except Exception:fail('GOOGLE_OAUTH_CLIENT_INVALID')
    def fingerprint(self):
        parsed=GoogleDesktopClient(self.target,self.purpose,self.client_id,self.scopes,self.client_secret)
        return checksum({'target':parsed.target.model_dump(mode='json'),'purpose':parsed.purpose,'client_id':parsed.client_id,'scopes':sorted(parsed.scopes),
            'client_secret_sha256':hashlib.sha256(parsed.client_secret.encode()).hexdigest() if parsed.client_secret is not None else None})

@dataclass(frozen=True)
class GoogleAuthorization:
    client:GoogleDesktopClient=field(repr=False)
    configuration_sha256:str
    redirect_uri:str
    created_at:datetime
    expires_at:datetime
    state:str=field(repr=False)
    verifier:str=field(repr=False)
    def check(self,now=None):
        if type(self.client) is not GoogleDesktopClient or self.client.fingerprint()!=self.configuration_sha256:fail('GOOGLE_OAUTH_CONFIGURATION_CHANGED')
        loopback(self.redirect_uri)
        if not opaque(self.state,43,128) or not isinstance(self.verifier,str) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',self.verifier):fail('GOOGLE_OAUTH_AUTHORIZATION_INVALID')
        if instant(self.expires_at)-instant(self.created_at)>timedelta(minutes=15) or self.expires_at<=self.created_at:fail('GOOGLE_OAUTH_AUTHORIZATION_INVALID')
        if not self.created_at<=instant(now)<self.expires_at:fail('GOOGLE_OAUTH_AUTHORIZATION_EXPIRED')
    def url(self,now=None):
        self.check(now);challenge=base64.urlsafe_b64encode(hashlib.sha256(self.verifier.encode('ascii')).digest()).decode().rstrip('=')
        return AUTHORIZATION_URL+'?'+urlencode({'client_id':self.client.client_id,'redirect_uri':self.redirect_uri,'response_type':'code','scope':' '.join(sorted(self.client.scopes)),
            'code_challenge':challenge,'code_challenge_method':'S256','state':self.state,'prompt':'consent'})

def authorization(client,redirect_uri,*,now=None,valid_for_seconds=600):
    if type(client) is not GoogleDesktopClient or type(valid_for_seconds) is not int or not 60<=valid_for_seconds<=900:fail('GOOGLE_OAUTH_AUTHORIZATION_INVALID')
    stamp=instant(now)
    return GoogleAuthorization(client,client.fingerprint(),loopback(redirect_uri),stamp,stamp+timedelta(seconds=valid_for_seconds),secrets.token_urlsafe(48),secrets.token_urlsafe(64))

@dataclass(frozen=True)
class GoogleTokenRequest:
    operation:str
    configuration_sha256:str
    issued_at:datetime
    body:bytes=field(repr=False)
    def __post_init__(self):
        if self.operation not in ('authorization_code','refresh_token') or not isinstance(self.configuration_sha256,str) or not re.fullmatch(r'[a-f0-9]{64}',self.configuration_sha256) or type(self.body) is not bytes or not 1<=len(self.body)<=16384:fail('GOOGLE_OAUTH_REQUEST_INVALID')
        instant(self.issued_at)
    def check(self,client):
        instant(self.issued_at)
        if type(client) is not GoogleDesktopClient or client.fingerprint()!=self.configuration_sha256:fail('GOOGLE_OAUTH_CONFIGURATION_CHANGED')
        try:value=pairs(self.body.decode('ascii'))
        except Exception:fail('GOOGLE_OAUTH_REQUEST_INVALID')
        fields={'client_id','grant_type',*({'code','code_verifier','redirect_uri'} if self.operation=='authorization_code' else {'refresh_token'})}
        if client.client_secret is not None:fields.add('client_secret')
        if set(value)!=fields or value['client_id']!=client.client_id or value['grant_type']!=self.operation or value.get('client_secret')!=client.client_secret:fail('GOOGLE_OAUTH_REQUEST_INVALID')
        if self.operation=='authorization_code':
            loopback(value['redirect_uri'])
            if not opaque(value['code'],1) or not re.fullmatch(r'[A-Za-z0-9._~-]{43,128}',value['code_verifier']):fail('GOOGLE_OAUTH_REQUEST_INVALID')
        elif not opaque(value['refresh_token']):fail('GOOGLE_OAUTH_REQUEST_INVALID')
        return value

def token_request(client,operation,stamp,**values):
    body={'client_id':client.client_id,'grant_type':operation,**values}
    if client.client_secret is not None:body['client_secret']=client.client_secret
    value=GoogleTokenRequest(operation,client.fingerprint(),instant(stamp),urlencode(body).encode('ascii'));value.check(client);return value

def exchange_request(flow,callback_query,*,now=None):
    if type(flow) is not GoogleAuthorization:fail('GOOGLE_OAUTH_AUTHORIZATION_INVALID')
    flow.check(now)
    if not isinstance(callback_query,str) or not callback_query.isascii() or len(callback_query)>8192 or any(ord(c)<32 for c in callback_query):fail('GOOGLE_OAUTH_CALLBACK_INVALID')
    value=pairs(callback_query)
    if set(value)-{'state','code','error','error_description','error_uri','scope','authuser','prompt','hd'} or not isinstance(value.get('state'),str) or not hmac.compare_digest(value['state'],flow.state):fail('GOOGLE_OAUTH_CALLBACK_STATE_INVALID')
    if ('code' in value)==('error' in value):fail('GOOGLE_OAUTH_CALLBACK_INVALID')
    if 'error' in value:fail('GOOGLE_OAUTH_CONSENT_DENIED',needs_reauthorization=True)
    if not opaque(value['code'],1):fail('GOOGLE_OAUTH_CALLBACK_INVALID')
    return token_request(flow.client,'authorization_code',instant(now),code=value['code'],code_verifier=flow.verifier,redirect_uri=flow.redirect_uri)

@dataclass(frozen=True)
class GoogleTokenResponse:
    status:int
    mock:bool
    body:bytes=field(repr=False)
    def __post_init__(self):
        if type(self.status) is not int or not 100<=self.status<=599 or type(self.mock) is not bool or type(self.body) is not bytes or len(self.body)>MAX_RESPONSE:fail('GOOGLE_OAUTH_RESPONSE_INVALID',uncertain=True)

@dataclass(frozen=True)
class GoogleOAuthGrant:
    target:PublishingTargetBinding
    purpose:str
    configuration_sha256:str
    scopes:frozenset[str]
    obtained_at:datetime
    expires_at:datetime
    refresh_expires_at:datetime|None
    mock:bool
    access_token:str=field(repr=False)
    refresh_token:str=field(repr=False)
    def check(self,client):
        if type(client) is not GoogleDesktopClient or client.fingerprint()!=self.configuration_sha256 or client.target!=self.target or client.purpose!=self.purpose or client.scopes!=self.scopes:fail('GOOGLE_OAUTH_GRANT_BINDING_CHANGED')
        if type(self.mock) is not bool or not opaque(self.access_token) or not opaque(self.refresh_token) or not instant(self.obtained_at)<instant(self.expires_at) or self.refresh_expires_at is not None and instant(self.refresh_expires_at)<=self.obtained_at:fail('GOOGLE_OAUTH_GRANT_INVALID')
    def public(self,client):
        self.check(client)
        return {'schema_version':'google-oauth-grant-proof-v1','target_binding_sha256':target_digest(self.target),'configuration_sha256':self.configuration_sha256,'purpose':self.purpose,
            'scopes':sorted(self.scopes),'obtained_at':self.obtained_at.isoformat(),'expires_at':self.expires_at.isoformat(),'refresh_expires_at':self.refresh_expires_at.isoformat() if self.refresh_expires_at is not None else None,
            'mock':self.mock,'token_returned':False,'account_verified':False,'publishing_enabled':False,'production_consent_renewed':False,'real_provider_tested':False}
    def credential(self,client,*,now=None):
        self.check(client)
        if self.expires_at<=instant(now)+timedelta(seconds=90):fail('GOOGLE_OAUTH_ACCESS_REFRESH_REQUIRED')
        kind=AnalyticsOAuthCredential if self.purpose=='analytics' else PublishingOAuthCredential
        return kind(self.target.model_copy(deep=True),self.expires_at,self.scopes,self.access_token)

def refresh_request(client,grant,*,now=None):
    if type(grant) is not GoogleOAuthGrant:fail('GOOGLE_OAUTH_GRANT_INVALID')
    grant.check(client);stamp=instant(now)
    if stamp<grant.obtained_at or grant.refresh_expires_at is not None and stamp>=grant.refresh_expires_at:fail('GOOGLE_OAUTH_REFRESH_EXPIRED',needs_reauthorization=True)
    return token_request(client,'refresh_token',stamp,refresh_token=grant.refresh_token)

def parse_tokens(client,request,response,*,now=None,previous=None):
    if type(request) is not GoogleTokenRequest or type(response) is not GoogleTokenResponse:fail('GOOGLE_OAUTH_RESPONSE_INVALID',uncertain=True)
    body=request.check(client);received=instant(now)
    if not request.issued_at<=received<request.issued_at+timedelta(minutes=15):fail('GOOGLE_OAUTH_OPERATION_EXPIRED',uncertain=True)
    if request.operation=='refresh_token':
        if type(previous) is not GoogleOAuthGrant:fail('GOOGLE_OAUTH_REFRESH_SOURCE_REQUIRED')
        previous.check(client)
        if body['refresh_token']!=previous.refresh_token or previous.mock is not response.mock or previous.refresh_expires_at is not None and received>=previous.refresh_expires_at:fail('GOOGLE_OAUTH_REFRESH_SOURCE_CHANGED',uncertain=True)
    elif previous is not None:fail('GOOGLE_OAUTH_REFRESH_SOURCE_INVALID')
    try:
        value=json.loads(response.body,object_pairs_hook=json_pairs,parse_constant=lambda _v:(_ for _ in ()).throw(ValueError()))
        if not isinstance(value,dict):raise ValueError()
    except Exception:fail('GOOGLE_OAUTH_RESPONSE_INVALID',uncertain=True)
    if response.status!=200:
        error=value.get('error')
        if response.status==400 and error=='invalid_grant':fail('GOOGLE_OAUTH_REAUTHORIZATION_REQUIRED',needs_reauthorization=True)
        if response.status in (400,401) and error in ('invalid_client','unauthorized_client'):fail('GOOGLE_OAUTH_CLIENT_REJECTED',needs_reauthorization=True)
        fail('GOOGLE_OAUTH_TOKEN_REQUEST_FAILED',uncertain=response.status>=500 or response.status==429)
    if 'error' in value:fail('GOOGLE_OAUTH_RESPONSE_INVALID',uncertain=True)
    try:
        scopes=value.get('scope');seconds=value.get('expires_in')
        if value.get('token_type')!='Bearer' or not isinstance(scopes,str) or len(scopes)>2048 or len(scopes.split(' '))!=len(set(scopes.split(' '))) or frozenset(scopes.split(' '))!=client.scopes or type(seconds) is not int or not 90<seconds<=86400 or not opaque(value.get('access_token')):raise ValueError()
        expiry=request.issued_at+timedelta(seconds=seconds)
        if expiry<=received+timedelta(seconds=90):raise ValueError()
        refresh=value.get('refresh_token',previous.refresh_token if previous is not None else None)
        if not opaque(refresh):raise ValueError()
        lifetime=value.get('refresh_token_expires_in')
        if 'refresh_token_expires_in' in value and (type(lifetime) is not int or not 0<lifetime<=315360000):raise ValueError()
        refresh_expiry=request.issued_at+timedelta(seconds=lifetime) if lifetime is not None else previous.refresh_expires_at if previous is not None else None
        if previous is not None and previous.refresh_expires_at is not None and refresh_expiry is not None:refresh_expiry=min(refresh_expiry,previous.refresh_expires_at)
        if refresh_expiry is not None and refresh_expiry<=received:raise ValueError()
        grant=GoogleOAuthGrant(client.target.model_copy(deep=True),client.purpose,client.fingerprint(),client.scopes,received,expiry,refresh_expiry,response.mock,value['access_token'],refresh)
        grant.check(client);return grant
    except Exception:fail('GOOGLE_OAUTH_TOKEN_FIELDS_INVALID',uncertain=True)

class GoogleOAuthTokenClient:
    """Only the fixed token endpoint; no redirects, proxy inheritance or retries."""
    def __init__(self,*,network_enabled=False,transport=None):
        if type(network_enabled) is not bool or transport is not None and type(transport) is not httpx.MockTransport:fail('GOOGLE_OAUTH_TRANSPORT_INVALID')
        self.network_enabled,self.transport=network_enabled,transport;self.frozen=(network_enabled,transport)
    @property
    def mock(self):return self.transport is not None
    def check(self):
        if type(self.network_enabled) is not bool or self.network_enabled is not self.frozen[0] or self.transport is not self.frozen[1]:fail('GOOGLE_OAUTH_TRANSPORT_CHANGED')
    async def send(self,client,request,*,now=None):
        self.check()
        if type(request) is not GoogleTokenRequest:fail('GOOGLE_OAUTH_REQUEST_INVALID')
        request.check(client)
        if not request.issued_at<=instant(now)<request.issued_at+timedelta(minutes=15):fail('GOOGLE_OAUTH_OPERATION_EXPIRED')
        if self.transport is None and not self.network_enabled:fail('GOOGLE_OAUTH_TOKEN_EXCHANGE_DISABLED')
        _install_privacy_filters();privacy=_sensitive.set(True);transport=self.transport;owned=transport is None;response=None;close_failed=False
        try:
            if owned:transport=httpx.AsyncHTTPTransport(verify=True,retries=0,trust_env=False,http2=False,limits=httpx.Limits(max_connections=1,max_keepalive_connections=0))
            outgoing=httpx.Request('POST',TOKEN_URL,headers={'Content-Type':'application/x-www-form-urlencoded','Accept':'application/json','Accept-Encoding':'identity'},content=request.body,
                extensions={'timeout':{'connect':5.0,'read':15.0,'write':15.0,'pool':5.0}})
            response=await transport.handle_async_request(outgoing)
            if 300<=response.status_code<400:fail('GOOGLE_OAUTH_REDIRECT_REJECTED',uncertain=True)
            if response.headers.get('content-encoding','identity').lower()!='identity':fail('GOOGLE_OAUTH_COMPRESSED_RESPONSE_REJECTED',uncertain=True)
            if response.headers.get('content-type','').split(';')[0].strip().lower()!='application/json' or 'dpop-nonce' in response.headers:fail('GOOGLE_OAUTH_RESPONSE_TYPE_UNSUPPORTED',uncertain=True)
            length=response.headers.get('content-length')
            if length is not None and (not re.fullmatch(r'[0-9]{1,10}',length) or int(length)>MAX_RESPONSE):fail('GOOGLE_OAUTH_RESPONSE_SIZE_LIMIT',uncertain=True)
            raw=bytearray()
            async for chunk in response.aiter_bytes():
                if len(raw)+len(chunk)>MAX_RESPONSE:fail('GOOGLE_OAUTH_RESPONSE_SIZE_LIMIT',uncertain=True)
                raw.extend(chunk)
            self.check();request.check(client)
            return GoogleTokenResponse(response.status_code,not owned,bytes(raw))
        except GoogleOAuthError:raise
        except Exception:fail('GOOGLE_OAUTH_NETWORK_OUTCOME_UNKNOWN',uncertain=True)
        finally:
            try:
                if response is not None:
                    try:await response.aclose()
                    except Exception:close_failed=True
                if owned and transport is not None:
                    try:await transport.aclose()
                    except Exception:close_failed=True
            finally:_sensitive.reset(privacy)
            if close_failed:fail('GOOGLE_OAUTH_TRANSPORT_CLOSE_FAILED',uncertain=True)
