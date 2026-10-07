import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .source_variants import Create,catalog
from .publication_routes import actor

def get(handler,path):
    if path=='/api/auto-edit/variant-profiles':return catalog()
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/variants',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if set(params)-{'limit','cursor'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('SOURCE_VARIANT_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('SOURCE_VARIANT_PAGE_INVALID',400) from None
    return handler.server.variants.page(match[1],limit=limit,cursor=params.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/variants',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('SOURCE_VARIANT_FIELDS_INVALID',400) from None
    value,replay=handler.server.variants.create(match[1],payload,actor=actor(handler));return {**value,'idempotent_replay':replay}
