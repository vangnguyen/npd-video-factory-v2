"""Signed finite refresh routes; no provider request from HTTP creation."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_analytics_refresh import RefreshCreate,RefreshCancel,parse_refresh
BASE=r'/api/projects/([a-f0-9]{32})/official-analytics-refresh'
IDENTITY=r'(noap_[a-f0-9]{32})'
def get(handler,path):
    service=handler.server.official_analytics_refresh;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-analytics-refresh':
        if params:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400)
        return service.states()
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'publication','limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_REFRESH_PAGE_INVALID',400) from None
    return service.page(project,publication=params.get('publication',[None])[0],limit=limit,cursor=params.get('cursor',[None])[0])
def post(handler,path,body):
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r'/cancel)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CURRENT_OWNER_REQUIRED',403)
    service=handler.server.official_analytics_refresh;service.analytics.identity(session.principal);project,identity=match.groups()
    try:payload=RefreshCancel.model_validate(body) if identity else parse_refresh(body)
    except (ValidationError,TypeError,ValueError):raise WorkflowError('NATIVE_OFFICIAL_REFRESH_FIELDS_INVALID',400) from None
    if identity:return service.cancel(project,identity,payload,principal=session.principal)
    value,replay=service.create(project,payload,principal=session.principal);handler.server.runner.wake.set()
    return {**value,'idempotent_replay':replay}
