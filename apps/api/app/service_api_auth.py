"""Exact signed service requests with explicit workspace capabilities.

Human principals remain human. Sensitive approval/publication routes verify both
the service signature and a real existing human verifier/role.
"""
import json,re
from dataclasses import dataclass
from fastapi import HTTPException,Request
from fastapi.routing import APIRoute
from .bridge_auth import ServiceAuthError,ServiceAuthVerifier,CONTRACT_VERSION_HEADER
from .service_api_contract import grants

def error(status,code):return HTTPException(status,headers={'Cache-Control':'no-store'},detail={'error':{'code':code,'message':code}})

@dataclass(frozen=True)
class ServiceActor:
    service_id:str
    workspace_grants:object
    @property
    def subject(self):return 'svc:'+self.service_id

async def verify(request:Request):
    if isinstance(getattr(request.state,'service_actor',None),ServiceActor):return request.state.service_actor
    verifier=getattr(request.app.state,'bridge_auth_verifier',None)
    if not getattr(request.app.state,'service_api_enabled',False) or not isinstance(verifier,ServiceAuthVerifier):
        raise error(503,'SERVICE_API_DISABLED')
    sensitive={'x-npd-service-id','x-npd-key-id','x-npd-timestamp','x-npd-nonce','x-npd-content-sha256',
        'x-npd-signature','x-npd-contract-version','content-length','content-type','idempotency-key','authorization'}
    names=[k.decode().lower() for k,v in request.scope['headers']]
    if any(names.count(k)>1 for k in sensitive):raise error(400,'SERVICE_DUPLICATE_HEADERS')
    if request.headers.get(CONTRACT_VERSION_HEADER)!='agent-hub-bridge.v1':raise error(400,'SERVICE_CONTRACT_REQUIRED')
    required=('X-NPD-Service-Id','X-NPD-Key-Id','X-NPD-Timestamp','X-NPD-Nonce','X-NPD-Content-SHA256','X-NPD-Signature')
    if not all(request.headers.get(k) for k in required) or request.headers.get('X-NPD-Service-Id') not in verifier.identities:
        raise error(401,'SERVICE_AUTH_REQUIRED')
    limit=32*1024*1024 if re.fullmatch(r'/v1/uploads/[^/]+/parts/\d+',request.url.path) else 8*1024*1024
    try:size=int(request.headers.get('Content-Length','0'))
    except ValueError:raise error(400,'SERVICE_BODY_INVALID') from None
    if not 0<=size<=limit:raise error(413,'SERVICE_BODY_TOO_LARGE')
    chunks=[];total=0
    async for chunk in request.stream():
        total+=len(chunk)
        if total>limit:raise error(413,'SERVICE_BODY_TOO_LARGE')
        chunks.append(chunk)
    raw=b''.join(chunks);request._body=raw
    if total!=size:raise error(400,'SERVICE_BODY_INVALID')
    try:principal=await verifier.verify(method=request.method,path=request.url.path,query=request.url.query,body=raw,headers=request.headers)
    except ServiceAuthError as exc:raise error(401,exc.code) from None
    identity=verifier.identities[principal.service_id]
    if identity.roles!=('service',):raise error(403,'SERVICE_ROLE_ONLY_REQUIRED')
    try:bound=grants(dict(identity.workspace_grants))
    except ValueError:raise error(503,'SERVICE_API_GRANTS_INVALID') from None
    if request.method in ('POST','PUT') and '/parts/' not in request.url.path:
        if request.headers.get('Content-Type','').split(';')[0]!='application/json':raise error(415,'SERVICE_JSON_REQUIRED')
        def pairs(items):
            result={}
            for key,value in items:
                if key in result:raise ValueError()
                result[key]=value
            return result
        def invalid(_):raise ValueError()
        try:json.loads(raw,object_pairs_hook=pairs,parse_constant=invalid)
        except (ValueError,UnicodeError):raise error(400,'SERVICE_BODY_INVALID') from None
    request.state.service_actor=ServiceActor(principal.service_id,bound)
    return request.state.service_actor

class ServiceRoute(APIRoute):
    def get_route_handler(self):
        original=super().get_route_handler()
        async def signed(request):
            try:
                await verify(request);response=await original(request)
            except HTTPException as exc:
                exc.headers={**(exc.headers or {}),'Cache-Control':'no-store'};raise
            response.headers['Cache-Control']='no-store'
            response.headers['X-NPD-Service-API-Version']='video-factory-service.v1';return response
        return signed

async def workspace(request,identity,action):
    actor=await verify(request)
    if identity not in actor.workspace_grants:raise error(404,'NOT_FOUND')
    if action not in actor.workspace_grants[identity]:raise error(403,'SERVICE_CAPABILITY_REQUIRED')
    if await request.app.state.platform_repository.get_workspace(identity) is None:raise error(404,'NOT_FOUND')
    return actor

async def project(request,identity,action):
    value=await request.app.state.platform_repository.get_project(identity)
    if value is None:raise error(404,'NOT_FOUND')
    actor=await workspace(request,value.workspace_id,action);return actor,value

async def human(request,project_id,role):
    from .human_auth import authenticate_human_request,authorize_project
    if not getattr(request.app.state,'human_write_enabled',False):raise error(503,'HUMAN_WRITES_DISABLED')
    await authenticate_human_request(request)
    return await authorize_project(request,project_id,role)
