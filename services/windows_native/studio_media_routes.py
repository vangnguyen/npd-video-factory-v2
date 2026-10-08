"""Scoped human storyboard planning; no provider jobs accepted through this DTO."""
import re
from .contracts import WorkflowError
from .studio_media_models import Create,Select,Revise,Apply


def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/media-plans',path)
    if not match:raise WorkflowError('STUDIO_MEDIA_PLAN_ROUTE_NOT_FOUND',404)
    if '?' in handler.path:raise WorkflowError('STUDIO_MEDIA_PLAN_PAGE_INVALID',400)
    return handler.server.media_planner.page(match[1])


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/media-plans(?:/(nmp_[a-f0-9]{32})/(select|revise|apply))?',path)
    if not match:raise WorkflowError('STUDIO_MEDIA_PLAN_ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();service=handler.server.media_planner
    try:payload=({'select':Select,'revise':Revise,'apply':Apply}.get(action,Create)).model_validate(body)
    except (ValueError,TypeError):raise WorkflowError('STUDIO_MEDIA_PLAN_FIELDS_INVALID',400) from None
    if identity is None:return service.create(project,payload)
    if action=='apply':return service.apply(project,identity,payload)
    return service.change(project,identity,payload)
