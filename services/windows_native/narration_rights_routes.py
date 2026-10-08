"""Existing Owner session/origin/CSRF/RBAC checks precede mutation bodies."""
import re
from .contracts import WorkflowError
from .publication_routes import actor
def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narration-rights',path)
    if not match or '?' in handler.path:raise WorkflowError('NATIVE_NARRATION_RIGHTS_ROUTE_NOT_FOUND',404)
    return handler.server.narration_rights.page(match[1])
def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narration-rights',path)
    if not match:raise WorkflowError('NATIVE_NARRATION_RIGHTS_ROUTE_NOT_FOUND',404)
    return handler.server.narration_rights.record(match[1],body,actor=actor(handler))
