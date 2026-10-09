"""Signed scoped human thumbnail selection; no provider or publishing grant."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .render_thumbnails import Create,PATTERN
from .publication_routes import actor

BASE=r'/api/projects/([a-f0-9]{32})/render-thumbnails'

def get(handler,path):
    match=re.fullmatch(BASE+r'(?:/('+PATTERN+r'))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if identity:
        if params:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_PAGE_INVALID',400)
        return handler.server.render_thumbnails.get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_PAGE_INVALID',400)
    raw=params.get('limit',['25'])[0]
    if not re.fullmatch(r'[0-9]{1,3}',raw) or not 1<=int(raw)<=100:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_PAGE_INVALID',400)
    return handler.server.render_thumbnails.page(project,limit=int(raw),cursor=params.get('cursor',[None])[0])

def image(handler,path):
    match=re.fullmatch(BASE+r'/('+PATTERN+r')/image',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    if handler.path.partition('?')[2]:raise WorkflowError('NATIVE_RENDER_THUMBNAIL_PAGE_INVALID',400)
    pixels,selected=handler.server.render_thumbnails.image(*match.groups())
    handler.send_response(200);handler.common('image/png',len(pixels),{'X-VF-Thumbnail-Basis':'explicit_reviewed_render_frame',
        'X-VF-Thumbnail-SHA256':selected['frame']['sha256']});handler.end_headers();handler.wfile.write(pixels)

def post(handler,path,body):
    match=re.fullmatch(BASE,path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_RENDER_THUMBNAIL_FIELDS_INVALID',400) from None
    value,replay=handler.server.render_thumbnails.create(match.group(1),payload,actor=actor(handler))
    return {**value,'idempotent_replay':replay}
