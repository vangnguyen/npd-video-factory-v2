"""Signed scoped review and one explicitly requested provider step; no auto-send."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_publication_models import Create,Approve,Action,Renew,Step
from .official_publication_worker import code

BASE=r'/api/projects/([a-f0-9]{32})/official-publications'
IDENTITY=r'(nopu_[a-f0-9]{32})'

def get(handler,path):
    service=handler.server.official_publications;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-publishing':
        if params:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PAGE_INVALID',400)
        return {**service.states(),'session_vault':handler.server.official_publish_vault.public()}
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r'(/state)?)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,state=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PAGE_INVALID',400)
        return service.state(project,identity) if state else service.get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r'/(approve|renew|revoke|cancel|step|poll))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();service=handler.server.official_publications
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED',403)
    principal=session.principal;service.identity(principal)
    try:payload={None:Create,'approve':Approve,'renew':Renew,'revoke':Action,'cancel':Action,'step':Step,'poll':Step}[action].model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_FIELDS_INVALID',400) from None
    if action is None:
        value,replay=service.create(project,payload,principal=principal)
        return {**value,'idempotent_replay':replay}
    if action=='approve':return service.approve(project,identity,payload,principal=principal)
    if action=='renew':
        renewal=service.renew(project,identity,payload,principal=principal)
        return {**service.get(project,identity),'renewal':renewal}
    if action=='cancel':return service.cancel(project,identity,payload,principal=principal)
    if action=='revoke':return service.revoke(project,identity,payload,principal=principal)
    value=service.get(project,identity)
    if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_BINDING_CHANGED')
    worker=handler.server.official_publish_worker
    try:
        if action=='step':return worker.step(project,identity,payload.expected_dispatch_version)
        return worker.poll_processing(project,identity,payload.expected_dispatch_version)
    except WorkflowError:raise
    except Exception as error:raise WorkflowError(code(error)) from None
