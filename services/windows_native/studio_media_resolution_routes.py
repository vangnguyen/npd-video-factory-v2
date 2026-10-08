"""Human-scoped storyboard resolution; existing provider roles remain unchanged."""
import re
from .contracts import WorkflowError
from .publication_routes import actor
from .studio_media_resolution import Generate,Search,Download,Import


def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/media-resolutions(?:/(nmr_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_ROUTE_NOT_FOUND',404)
    if '?' in handler.path:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_PAGE_INVALID',400)
    project,identity=match.groups();service=handler.server.media_resolution
    return service.get(project,identity) if identity else service.page(project)


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/(?:media-plans/(nmp_[a-f0-9]{32})/resolve/(generate|search|download)|media-resolutions/(nmr_[a-f0-9]{32})/import)',path)
    if not match:raise WorkflowError('STUDIO_MEDIA_RESOLUTION_ROUTE_NOT_FOUND',404)
    project,plan,action,identity=match.groups();service=handler.server.media_resolution
    try:payload=({'generate':Generate,'search':Search,'download':Download}.get(action,Import)).model_validate(body)
    except (ValueError,TypeError):raise WorkflowError('STUDIO_MEDIA_RESOLUTION_FIELDS_INVALID',400) from None
    if identity:return service.attach(project,identity,payload,actor=actor(handler))
    value,replay=service.create(project,plan,payload,actor=actor(handler))
    return {**value,'idempotent_replay':replay}
