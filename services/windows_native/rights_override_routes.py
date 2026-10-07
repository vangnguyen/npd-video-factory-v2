"""Existing human Owner/session/origin/CSRF guard precedes mutation body parsing."""
import re
from .contracts import WorkflowError
from .publication_routes import actor


def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/rights-overrides',path)
    if not match or '?' in handler.path:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_ROUTE_NOT_FOUND',404)
    return handler.server.rights_overrides.page(match[1])


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/rights-overrides/([a-f0-9]{32}\.(jpg|png|mp4|wav))',path)
    if not match:raise WorkflowError('NATIVE_RIGHTS_OVERRIDE_ROUTE_NOT_FOUND',404)
    return handler.server.rights_overrides.record(match[1],match[2],body,actor=actor(handler))
