"""Current Owner/CSRF OAuth actions; private callbacks only in bounded POST bodies."""
import asyncio,re
from urllib.parse import parse_qs
from pydantic import Field,ValidationError
from .contracts import WorkflowError
from .google_oauth_operations import Start,Refresh,Cancel
from app.google_oauth_protocol import GoogleOAuthError

BASE=r'/api/projects/([a-f0-9]{32})/google-oauth'
AUTH=r'(ngoa_[a-f0-9]{32})'
OP=r'(ngop_[a-f0-9]{32})'

class Exchange(Cancel):
    callback_query:str=Field(min_length=1,max_length=8192,repr=False)

def service(handler):
    value=handler.server.google_oauth
    if value is None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_NOT_CONFIGURED',503)
    return value

def get(handler,path):
    params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/google-oauth':
        if params:raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400)
        if handler.server.google_oauth is not None:return handler.server.google_oauth.states()
        return {'schema_version':'native-google-oauth-runtime-v1','workspace_id':handler.server.publications.workspace_id,'enabled':False,'default_enabled':False,'slots':[],
            'automatic_refresh':False,'startup_decryption':False,'account_verified':False,'token_returned':False,'publishing_enabled':False,'production_consent_renewed':False,'real_provider_tested':False}
    match=re.fullmatch(BASE+r'/(authorizations|operations)(?:/(ngoa_[a-f0-9]{32}|ngop_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,group,identity=match.groups();kind='authorization' if group=='authorizations' else 'operation'
    if identity:
        if params or not identity.startswith('ngoa_' if kind=='authorization' else 'ngop_'):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400)
        return service(handler).get(project,identity,kind=kind)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400)
    raw=params.get('limit',['25'])[0]
    if not re.fullmatch(r'[0-9]{1,3}',raw):raise WorkflowError('NATIVE_GOOGLE_OAUTH_PAGE_INVALID',400)
    return service(handler).page(project,kind=kind,limit=int(raw),cursor=params.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE+r'/(authorizations|refresh)(?:/'+AUTH+r'/(authorization-url|exchange|cancel))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,group,identity,action=match.groups()
    if group=='refresh' and identity:raise WorkflowError('ROUTE_NOT_FOUND',404)
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_GOOGLE_OAUTH_CURRENT_OWNER_REQUIRED',403)
    operations=service(handler);operations.identity(session.principal)
    try:payload=(Exchange if action=='exchange' else Cancel if action else Refresh if group=='refresh' else Start).model_validate(body)
    except (ValidationError,TypeError,GoogleOAuthError):raise WorkflowError('NATIVE_GOOGLE_OAUTH_FIELDS_INVALID',400) from None
    if action=='authorization-url':
        return {'schema_version':'native-google-oauth-authorization-url-v1','authorization_id':identity,'authorization_url':operations.authorization_url(project,identity,principal=session.principal,expected_snapshot_sha256=payload.expected_snapshot_sha256),
            'external_human_browser_required':True,'token_returned':False,'publishing_enabled':False}
    if action=='exchange':return asyncio.run(operations.exchange(project,identity,payload.callback_query,principal=session.principal,expected_snapshot_sha256=payload.expected_snapshot_sha256))
    if action=='cancel':return operations.cancel(project,identity,payload,principal=session.principal)
    if group=='refresh':return asyncio.run(operations.refresh(project,payload,principal=session.principal))
    if payload.redirect_uri!=f'http://127.0.0.1:{handler.server.server_port}/oauth/google/callback':raise WorkflowError('NATIVE_GOOGLE_OAUTH_SERVER_REDIRECT_REQUIRED',400)
    value,replay=operations.start(project,payload,principal=session.principal);return {**value,'idempotent_replay':replay}
