"""Signed Owner actions for bounded creator reads and unsent video choices."""
import asyncio,re
from urllib.parse import parse_qs
from pydantic import ValidationError
from app.publishing_wire import PublishingWireError
from .contracts import WorkflowError
from .tiktok_creators import NativeTikTokCreators,Check,Action,Draft

BASE=r'/api/projects/([a-f0-9]{32})/tiktok-creators'

def service(handler,*,required=True):
    value=getattr(handler.server,'tiktok_creators',None)
    if value is None:
        if required:raise WorkflowError('NATIVE_TIKTOK_CREATOR_NOT_CONFIGURED',503)
        return None
    if type(value) is not NativeTikTokCreators or value.store is not handler.server.store or value.workspace!=handler.server.publications.workspace_id:
        raise WorkflowError('NATIVE_TIKTOK_CREATOR_CONFIGURATION_CHANGED')
    value.check();return value

def get(handler,path):
    params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/tiktok-creators':
        if params:raise WorkflowError('NATIVE_TIKTOK_CREATOR_PAGE_INVALID',400)
        value=service(handler,required=False)
        return value.states() if value is not None else {'schema_version':'native-tiktok-creator-runtime-v1','workspace_id':handler.server.publications.workspace_id,
            'enabled':False,'default_enabled':False,'factories':[],'token_returned':False,'publishing_enabled':False,'publication_dispatch_supported':False,'automatic_retry':False,'real_provider_tested':False}
    match=re.fullmatch(BASE+r'/(checks|drafts)(?:/((?:ntcr_|ntpd_)[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,group,identity=match.groups();value=service(handler);kind='check' if group=='checks' else 'draft';prefix='ntcr_' if kind=='check' else 'ntpd_'
    if identity:
        if params or not identity.startswith(prefix):raise WorkflowError('NATIVE_TIKTOK_CREATOR_PAGE_INVALID',400)
        return value.get(project,identity) if kind=='check' else value.get_draft(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()) or not re.fullmatch('[0-9]{1,3}',params.get('limit',['25'])[0]):
        raise WorkflowError('NATIVE_TIKTOK_CREATOR_PAGE_INVALID',400)
    return value.page(project,kind=kind,limit=int(params.get('limit',['25'])[0]),cursor=params.get('cursor',[None])[0])

def owner(handler):
    value=service(handler);session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_TIKTOK_CURRENT_OWNER_REQUIRED',403)
    value.identity(session.principal);return session.principal

def post(handler,path,body,principal):
    match=re.fullmatch(BASE+r'/(checks|drafts)(?:/(ntcr_[a-f0-9]{32})/(fetch|cancel))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,group,identity,action=match.groups()
    if group=='drafts' and identity:raise WorkflowError('ROUTE_NOT_FOUND',404)
    value=service(handler);value.identity(principal)
    try:payload=(Action if action else Check if group=='checks' else Draft).model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_TIKTOK_CREATOR_FIELDS_INVALID',400) from None
    try:
        if action=='fetch':return asyncio.run(value.fetch(project,identity,principal=principal,expected_snapshot_sha256=payload.expected_snapshot_sha256))
        if action=='cancel':return value.cancel(project,identity,payload,principal=principal)
        result,replay=(value.create if group=='checks' else value.draft)(project,payload,principal=principal)
        return {**result,'idempotent_replay':replay}
    except PublishingWireError as error:raise WorkflowError(error.code,400) from None
