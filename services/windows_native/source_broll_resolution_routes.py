"""Scoped, explicit Source B-roll orchestration; no browser credentials."""
import re
from pydantic import ValidationError
from .contracts import WorkflowError
from .publication_routes import actor
from .source_broll_resolution_models import Create, Step, Apply

BASE = r'/api/projects/([a-f0-9]{32})/auto-edit/broll-resolutions'
IDENTITY = r'nbr_[a-f0-9]{32}'


def get(handler, path):
    if '?' in handler.path:
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_PAGE_INVALID', 400)
    match = re.fullmatch(BASE+r'(?:/('+IDENTITY+r'))?', path)
    if not match:
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_ROUTE_NOT_FOUND', 404)
    project, identity = match.groups()
    service = handler.server.source_broll_resolution
    return service.get(project, identity) if identity else service.page(project)


def post(handler, path, body):
    match = re.fullmatch(BASE+r'(?:/('+IDENTITY+r')/(step|apply))?', path)
    if not match:
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_ROUTE_NOT_FOUND', 404)
    project, identity, action = match.groups()
    service = handler.server.source_broll_resolution
    try:
        if identity is None:
            value, replay = service.create(project, Create.model_validate(body), actor=actor(handler))
        else:
            method, model = (service.step, Step) if action == 'step' else (service.apply, Apply)
            value, replay = method(project, identity, model.model_validate(body), actor=actor(handler))
        return {**value, 'idempotent_replay':replay}
    except ValidationError:
        raise WorkflowError('SOURCE_BROLL_RESOLUTION_FIELDS_INVALID', 400) from None
