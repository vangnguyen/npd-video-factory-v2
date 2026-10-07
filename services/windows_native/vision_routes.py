import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .vision_models import NativeVisionRequest,NativeVisionAction
from .publication_routes import actor


def get(handler,path):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/vision(?:/(nvis_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if identity:
        if params:raise WorkflowError('NATIVE_VISION_PAGE_INVALID',400)
        return handler.server.vision.get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('NATIVE_VISION_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_VISION_PAGE_INVALID',400) from None
    return handler.server.vision.page(project,limit=limit,cursor=params.get('cursor',[None])[0])


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/vision(?:/(nvis_[a-f0-9]{32})/(process|cancel))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();service=handler.server.vision
    try:
        if action is None:
            value,replay=service.create(project,NativeVisionRequest.model_validate(body),actor=actor(handler));return {**value,'idempotent_replay':replay}
        payload=NativeVisionAction.model_validate(body)
        if action=='cancel':return service.cancel(project,identity,fingerprint=payload.expected_fingerprint,actor=actor(handler))
        service.process(project=project,identity=identity,fingerprint=payload.expected_fingerprint);return service.get(project,identity)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_VISION_FIELDS_INVALID',400) from None
