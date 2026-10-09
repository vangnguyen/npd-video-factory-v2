"""Signed scoped rendered-QC reads and explicit current Owner operations."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError,digest
from .render_vision_models import RenderAnalyze,RenderAction
from .render_vision_frame_bridge import NativeRenderEvidenceFrameExtractor
from .render_frame_qc import checked
import hashlib

BASE=r'/api/projects/([a-f0-9]{32})/render-vision'
IDENTITY=r'(nrvi_[a-f0-9]{32})'


def service(handler):
    value=handler.server.render_vision
    if value is None:raise WorkflowError('NATIVE_RENDER_VISION_NOT_CONFIGURED',503)
    return value


def input_view(handler,project,job):
    server=handler.server;workspace=server.publications.workspace_id
    bridge=NativeRenderEvidenceFrameExtractor(server.store,server.config,project,job,workspace_id=workspace)
    binding=bridge.binding()
    return {'schema_version':'native-render-vision-input-view-v1','workspace_id':workspace,'project_id':project,'render_job_id':job,
        'revision':binding['current_project_revision'],'input_sha256':digest(binding),'binding':binding,
        'provider_authorized':False,'source_asset_consent_reused':False,'automatic_dispatch':False,'publishing_enabled':False,'owner_uat_accepted':False}


def frame(handler,path):
    match=re.fullmatch(BASE+r'/input/([a-f0-9]{32})/frame/([0-7])',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    if handler.path.partition('?')[2]:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
    project,job,index=match.groups();server=handler.server
    bridge=NativeRenderEvidenceFrameExtractor(server.store,server.config,project,job,workspace_id=server.publications.workspace_id)
    binding=bridge.binding();frames=binding['record']['observation']['frames']
    if int(index)>=len(frames):raise WorkflowError('NATIVE_RENDER_VISION_FRAME_NOT_FOUND',404)
    original=frames[int(index)];payload=checked(server.store.root/'jobs'/job,original['evidence_frame_reference']).read_bytes()
    if hashlib.sha256(payload).hexdigest()!=original['sha256'] or digest(bridge.binding())!=digest(binding):
        raise WorkflowError('NATIVE_RENDER_VISION_INPUT_CHANGED')
    handler.send_response(200);handler.common('image/png',len(payload))
    handler.end_headers();handler.wfile.write(payload)


def get(handler,path):
    params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True);server=handler.server
    if path=='/api/connections/render-vision':
        if params:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
        if server.render_vision is not None:return server.render_vision.states()
        return {'schema_version':'native-render-vision-runtime-v1','workspace_id':server.publications.workspace_id,'enabled':False,'profiles':[],
            'purpose':'rendered_video_quality_review','current_owner_required':True,'finite_consent_required':True,'original_request_response_cost_journal':True,
            'source_asset_consent_reused':False,'automatic_dispatch':False,'automatic_retry':False,'publishing_enabled':False,
            'hard_qc_replaced':False,'owner_uat_accepted':False,'real_provider_tested':False}
    match=re.fullmatch(BASE+r'/input/([a-f0-9]{32})',path)
    if match:
        if params:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
        return input_view(handler,*match.groups())
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
        return service(handler).get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
    raw=params.get('limit',['25'])[0]
    if not re.fullmatch(r'[0-9]{1,3}',raw) or not 1<=int(raw)<=100:raise WorkflowError('NATIVE_RENDER_VISION_PAGE_INVALID',400)
    cursor=params.get('cursor',[None])[0]
    if server.render_vision is None:
        server.store.get(project)
        if cursor is not None:raise WorkflowError('NATIVE_RENDER_VISION_CURSOR_INVALID',400)
        return {'schema_version':'native-render-vision-page-v1','workspace_id':server.publications.workspace_id,'project_id':project,
            'items':[],'next_cursor':None,'limit':int(raw),'automatic_dispatch':False,'publishing_enabled':False,'owner_uat_accepted':False}
    return service(handler).page(project,limit=int(raw),cursor=cursor)


def post(handler,path,body):
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r'/(process|cancel))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_RENDER_VISION_CURRENT_OWNER_REQUIRED',403)
    operations=service(handler);operations.identity(session.principal)
    try:payload=(RenderAction if action else RenderAnalyze).model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_RENDER_VISION_FIELDS_INVALID',400) from None
    if action=='cancel':return operations.cancel(project,identity,payload,principal=session.principal)
    if action=='process':return operations.process(project,identity,payload)
    value,replay=operations.create(project,payload,principal=session.principal)
    return {**value,'idempotent_replay':replay}
