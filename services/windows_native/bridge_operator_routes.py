"""Human Native operator reads/selections; cannot configure keys or enable HTTP."""
import re
from urllib.parse import parse_qs
from .contracts import WorkflowError
from .publication_routes import actor


def get(handler,path):
    bridge=handler.server.bridge;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/bridge/state' and not params:return bridge.operator_state()
    if path=='/api/bridge/events':
        if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_BRIDGE_PAGE_INVALID',400)
        try:limit=int(params.get('limit',['25'])[0])
        except ValueError:raise WorkflowError('NATIVE_BRIDGE_PAGE_INVALID',400) from None
        return bridge.page(limit=limit,cursor=params.get('cursor',[None])[0])
    match=re.fullmatch(r'/api/bridge/events/(bevt_[a-f0-9]{48})/delivery',path)
    if match and not params:return bridge.audit(match[1])
    raise WorkflowError('NATIVE_BRIDGE_ROUTE_NOT_FOUND',404)


def post(handler,path,body):
    match=re.fullmatch(r'/api/bridge/events/(bevt_[a-f0-9]{48})/(enqueue|cancel)',path)
    if not match:raise WorkflowError('NATIVE_BRIDGE_ROUTE_NOT_FOUND',404)
    return handler.server.bridge.select_delivery(match[1],body,actor=actor(handler),action=match[2])
