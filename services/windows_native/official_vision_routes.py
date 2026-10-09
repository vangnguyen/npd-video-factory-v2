"""Signed scoped official Vision review; each operation requires current Owner."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_vision_models import Analyze,Action

BASE = r'/api/projects/([a-f0-9]{32})/official-vision'
IDENTITY = r'(nvoi_[a-f0-9]{32})'


def service(handler):
    value = handler.server.official_vision
    if value is None: raise WorkflowError('NATIVE_OFFICIAL_VISION_NOT_CONFIGURED',503)
    return value


def get(handler,path):
    params = parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path == '/api/connections/official-vision':
        if params: raise WorkflowError('NATIVE_OFFICIAL_VISION_PAGE_INVALID',400)
        if handler.server.official_vision is not None: return handler.server.official_vision.states()
        return {'schema_version':'native-official-vision-runtime-v1','workspace_id':handler.server.publications.workspace_id,
            'enabled':False,'profiles':[],'current_owner_required':True,'finite_consent_required':True,'rights_required':True,
            'automatic_dispatch':False,'automatic_retry':False,'publishing_enabled':False,'real_provider_tested':False,'owner_uat_accepted':False}
    match = re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match: raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity = match.groups()
    if identity:
        if params: raise WorkflowError('NATIVE_OFFICIAL_VISION_PAGE_INVALID',400)
        return service(handler).get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()): raise WorkflowError('NATIVE_OFFICIAL_VISION_PAGE_INVALID',400)
    raw = params.get('limit',['25'])[0]
    if not re.fullmatch(r'[0-9]{1,3}',raw) or not 1 <= int(raw) <= 100: raise WorkflowError('NATIVE_OFFICIAL_VISION_PAGE_INVALID',400)
    cursor = params.get('cursor',[None])[0]
    if handler.server.official_vision is None:
        handler.server.store.get(project)
        if cursor is not None: raise WorkflowError('NATIVE_OFFICIAL_VISION_CURSOR_INVALID',400)
        return {'schema_version':'native-official-vision-page-v1','workspace_id':handler.server.publications.workspace_id,
            'project_id':project,'items':[],'next_cursor':None,'limit':int(raw),'automatic_dispatch':False,'publishing_enabled':False,'owner_uat_accepted':False}
    return service(handler).page(project,limit=int(raw),cursor=cursor)


def post(handler,path,body):
    match = re.fullmatch(BASE+r'(?:/'+IDENTITY+r'/(process|cancel))?',path)
    if not match: raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,action = match.groups(); session = getattr(handler,'auth_session',None)
    if session is None: raise WorkflowError('NATIVE_OFFICIAL_VISION_CURRENT_OWNER_REQUIRED',403)
    operations = service(handler); operations.identity(session.principal)
    try: payload = (Action if action else Analyze).model_validate(body)
    except (ValidationError,TypeError): raise WorkflowError('NATIVE_OFFICIAL_VISION_FIELDS_INVALID',400) from None
    if action == 'cancel': return operations.cancel(project,identity,payload,principal=session.principal)
    if action == 'process': return operations.process(project,identity,payload)
    value,replay = operations.create(project,payload,principal=session.principal)
    return {**value,'idempotent_replay':replay}
