"""Scoped human requests; credentials/configuration never enter the browser."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .publication_routes import actor
from .stock_models import StockSearch,StockDownload,StockAction,StockImport


def get(handler,path):
    service=handler.server.stock
    if path=='/api/stock/providers':
        if '?' in handler.path:raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400)
        return service.providers()
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/stock(?:/(nstk_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('NATIVE_STOCK_ROUTE_NOT_FOUND',404)
    project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if identity:
        if params:raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_STOCK_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0])


def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/stock/(search|download|nstk_[a-f0-9]{32}/(?:cancel|import))',path)
    if not match:raise WorkflowError('NATIVE_STOCK_ROUTE_NOT_FOUND',404)
    project,action=match.groups();service=handler.server.stock
    try:
        if action in ('search','download'):
            value,replay=service.create(project,({'search':StockSearch,'download':StockDownload}[action]).model_validate(body),actor=actor(handler))
            return {**value,'idempotent_replay':replay}
        identity,action=action.split('/')
        if action=='import':return service.attach(project,identity,StockImport.model_validate(body),actor=actor(handler))
        return service.cancel(project,identity,fingerprint=StockAction.model_validate(body).expected_fingerprint,actor=actor(handler))
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_STOCK_FIELDS_INVALID',400) from None
