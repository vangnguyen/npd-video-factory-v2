"""Native Owner declaration boundary; no provider verification or rights override."""
import re
from .contracts import WorkflowError
from .publication_routes import actor


def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/rights',path)
    if not match or '?' in handler.path:raise WorkflowError('NATIVE_RIGHTS_ROUTE_NOT_FOUND',404)
    return handler.server.rights.page(match[1])


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/rights/([a-f0-9]{32}\.(?:jpg|png|mp4|wav))',path)
    if not match:raise WorkflowError('NATIVE_RIGHTS_ROUTE_NOT_FOUND',404)
    return handler.server.rights.declare(match[1],match[2],body,actor=actor(handler))
