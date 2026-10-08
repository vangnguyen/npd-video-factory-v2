"""Signed scoped queue approval/history/cancel; creation never dispatches."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_publication_queue import QueueCreate,QueueCancel
BASE=r'/api/projects/([a-f0-9]{32})/official-publications/(nopu_[a-f0-9]{32})/queue'
PLAN=r'(nopq_[a-f0-9]{32})'

def get(handler,path):
    queue=handler.server.official_publish_queue;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-publish-queue':
        if params:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_PAGE_INVALID',400)
        return queue.states()
    match=re.fullmatch(BASE+r'(?:/'+PLAN+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,publication,plan=match.groups()
    if plan:
        if params:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_PAGE_INVALID',400)
        value=queue.get(project,plan)
        if value['publication_id']!=publication:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_FOUND',404)
        return value
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_PAGE_INVALID',400) from None
    return queue.page(project,publication,limit=limit,cursor=params.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE+r'(?:/'+PLAN+r'/cancel)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,publication,plan=match.groups();queue=handler.server.official_publish_queue;session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED',403)
    principal=session.principal;queue.journal.identity(principal)
    try:payload=(QueueCancel if plan else QueueCreate).model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_FIELDS_INVALID',400) from None
    if plan:
        value=queue.get(project,plan)
        if value['publication_id']!=publication:raise WorkflowError('NATIVE_OFFICIAL_PUBLISH_QUEUE_NOT_FOUND',404)
        return queue.cancel(project,plan,payload,principal=principal)
    value=queue.create(project,publication,payload,principal=principal);handler.server.runner.wake.set();return value
