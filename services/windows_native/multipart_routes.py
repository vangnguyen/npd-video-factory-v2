"""Signed existing Native edit/read boundaries; chunk bodies are bounded bytes."""
import re,socket
from pydantic import ValidationError
from .contracts import WorkflowError
from .multipart_ingestion import CHUNK_BYTES

PATTERN=r'/api/projects/([a-f0-9]{32})/uploads(?:/(nup_[a-f0-9]{32})(?:/(chunks|complete|cancel))?)?'
def handles(path):return re.fullmatch(PATTERN,path) is not None
def dispatch(handler,*,write):
    if '?' in handler.path:raise WorkflowError('UPLOAD_QUERY_INVALID',400)
    match=re.fullmatch(PATTERN,handler.path);project,identity,action=match.groups();service=handler.server.multipart_uploads
    try:
        if not write:
            if action:raise WorkflowError('UPLOAD_ROUTE_NOT_FOUND',404)
            result=service.get(project,identity) if identity else service.page(project)
        elif action=='chunks':
            headers=handler.headers;length=headers.get('Content-Length','');offset=headers.get('X-VF-Offset','');sha=headers.get('X-VF-SHA256','')
            if headers.get('Transfer-Encoding') or headers.get('Content-Type')!='application/octet-stream' or not re.fullmatch(r'[0-9]{1,7}',length) or not 0<int(length)<=CHUNK_BYTES or not re.fullmatch(r'[0-9]{1,10}',offset) or not re.fullmatch(r'[a-f0-9]{64}',sha):
                raise WorkflowError('UPLOAD_CHUNK_HEADERS_INVALID',400)
            previous_timeout=handler.connection.gettimeout();handler.connection.settimeout(15)
            try:raw=handler.rfile.read(int(length))
            except (socket.timeout,TimeoutError):raise WorkflowError('UPLOAD_CHUNK_READ_TIMEOUT',408) from None
            finally:handler.connection.settimeout(previous_timeout)
            if len(raw)!=int(length):raise WorkflowError('UPLOAD_CHUNK_INCOMPLETE',400)
            result,replay=service.chunk(project,identity,int(offset),sha,raw);result={**result,'idempotent_replay':replay}
        else:
            body=handler.read_body(max_bytes=4096)
            if identity is None:
                actor=handler.auth_session.principal.token_id if handler.server.access is not None else 'legacy-local-editor'
                result,replay=service.create(project,body,actor=actor);result={**result,'idempotent_replay':replay}
            elif action=='complete':result,replay=service.complete(project,identity,body);result={**result,'idempotent_replay':replay}
            elif action=='cancel':
                if body:raise WorkflowError('UPLOAD_CANCEL_FIELDS_INVALID',400)
                result=service.cancel(project,identity)
            else:raise WorkflowError('UPLOAD_ROUTE_NOT_FOUND',404)
    except (ValidationError,ValueError,TypeError):raise WorkflowError('UPLOAD_FIELDS_INVALID',400) from None
    return handler.reply(result,headers={'Cache-Control':'no-store'})
