"""Separate service HMAC boundary; human session cookies grant no /v1 access."""
import json
import re
from urllib.parse import parse_qs
from .bridge import HEADERS,VERSION
from .contracts import WorkflowError


def dispatch(handler):
    handler.boundary(session=False)
    path,_,query=handler.path.partition('?')
    headers={key:handler.headers.get(key,'') for key in HEADERS}
    if any(len(handler.headers.get_all(key,[]))>1 for key in (*HEADERS,'Content-Length','Content-Type','Idempotency-Key')):
        raise WorkflowError('NATIVE_BRIDGE_DUPLICATE_HEADERS',400)
    # Reject unauthenticated requests before reading their body. The full MAC
    # then verifies the exact bounded bytes before JSON is parsed.
    if handler.server.bridge.verifier is None:raise WorkflowError('NATIVE_BRIDGE_SERVICE_AUTH_NOT_CONFIGURED',503)
    if not all(headers.values()):raise WorkflowError('SERVICE_AUTH_REQUIRED',401)
    if headers.get(HEADERS[0]) not in handler.server.bridge.identities:raise WorkflowError('SERVICE_AUTH_INVALID',401)
    body=b''
    if handler.command=='POST':
        try:length=int(handler.headers.get('Content-Length','0'))
        except ValueError:raise WorkflowError('NATIVE_BRIDGE_BODY_INVALID',400) from None
        if (not 1<=length<=65536 or handler.headers.get('Transfer-Encoding')
            or handler.headers.get('Content-Type','').split(';')[0]!='application/json'):
            raise WorkflowError('NATIVE_BRIDGE_BODY_INVALID',400)
        body=handler.rfile.read(length)
        if len(body)!=length:raise WorkflowError('NATIVE_BRIDGE_BODY_INVALID',400)
    elif handler.headers.get('Transfer-Encoding') or handler.headers.get('Content-Length','0')!='0':
        raise WorkflowError('NATIVE_BRIDGE_BODY_INVALID',400)
    service=handler.server.bridge.authenticate(handler.command,path,query,body,headers)
    bridge=handler.server.bridge
    if handler.command=='GET':
        if path=='/v1/contract' and not query:return handler.reply(bridge.contract(),headers={'Cache-Control':'no-store'})
        if path=='/v1/events':
            values=parse_qs(query,keep_blank_values=True)
            if set(values)-{'limit','cursor'} or any(len(v)!=1 for v in values.values()):raise WorkflowError('NATIVE_BRIDGE_PAGE_INVALID',400)
            try:limit=int(values.get('limit',['25'])[0])
            except ValueError:raise WorkflowError('NATIVE_BRIDGE_PAGE_INVALID',400) from None
            return handler.reply(bridge.page(limit=limit,cursor=values.get('cursor',[None])[0]),headers={'Cache-Control':'no-store'})
        match=re.fullmatch(r'/v1/events/(bevt_[a-f0-9]{48})/delivery',path)
        if match and not query:return handler.reply(bridge.audit(match[1]),headers={'Cache-Control':'no-store'})
        match=re.fullmatch(r'/v1/projects/([a-f0-9]{32})',path)
        if match and not query:return handler.reply(bridge.project_summary(match[1]),headers={'Cache-Control':'no-store'})
    elif path=='/v1/projects' and not query:
        try:
            def pairs(items):
                result={}
                for key,value in items:
                    if key in result:raise ValueError()
                    result[key]=value
                return result
            payload=json.loads(body,object_pairs_hook=pairs)
            if not isinstance(payload,dict):raise ValueError()
        except ValueError:raise WorkflowError('NATIVE_BRIDGE_BODY_INVALID',400) from None
        value=bridge.draft(service,payload,handler.headers.get('Idempotency-Key'))
        return handler.reply(value,200 if value['idempotent_replay'] else 201,headers={'Cache-Control':'no-store'})
    raise WorkflowError('NATIVE_BRIDGE_ROUTE_NOT_FOUND',404)
