"""Owner registry/session gate precedes rights body; scoped original read history."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .render_thumbnail_rights import Create

BASE=r'/api/projects/([a-f0-9]{32})/render-thumbnail-rights'

def owner(handler):
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_CURRENT_OWNER_REQUIRED',403)
    handler.server.render_thumbnail_rights.identity(session.principal)
    return session.principal

def get(handler,path):
    service=handler.server.render_thumbnail_rights;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/render-thumbnail-rights':
        if params:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_PAGE_INVALID',400)
        return service.states()
    match=re.fullmatch(BASE+r'(?:/(nrto_[a-f0-9]{32})|/input/(ast_rthumb_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,thumbnail=match.groups()
    if identity or thumbnail:
        if params:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_PAGE_INVALID',400)
        return service.get(project,identity) if identity else service.input(project,thumbnail)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_PAGE_INVALID',400)
    raw=params.get('limit',['25'])[0]
    if not re.fullmatch(r'[0-9]{1,3}',raw) or not 1<=int(raw)<=100:raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_PAGE_INVALID',400)
    return service.page(project,limit=int(raw),cursor=params.get('cursor',[None])[0])

def post(handler,path,body,principal):
    match=re.fullmatch(BASE,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_THUMBNAIL_RIGHTS_FIELDS_INVALID',400) from None
    value,replay=handler.server.render_thumbnail_rights.record(match.group(1),payload,principal=principal)
    return {**value,'idempotent_replay':replay}
