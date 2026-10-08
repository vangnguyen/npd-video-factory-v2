"""Human-authenticated explicit narrated family creation; no provider dispatch."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .narrated_variants import catalog
from .narrated_variants_models import Create
from .publication_routes import actor

def get(handler,path):
    if path=='/api/narrated/variant-profiles':return catalog()
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narrated-variants',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    query=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if set(query)-{'limit','cursor'} or any(len(v)!=1 for v in query.values()):raise WorkflowError('NARRATED_VARIANT_PAGE_INVALID',400)
    try:limit=int(query.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NARRATED_VARIANT_PAGE_INVALID',400) from None
    return handler.server.narrated_variants.page(match[1],limit=limit,cursor=query.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/narrated-variants',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:payload=Create.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NARRATED_VARIANT_FIELDS_INVALID',400) from None
    value,replay=handler.server.narrated_variants.create(match[1],payload,actor=actor(handler))
    return {**value,'idempotent_replay':replay}
