"""Authenticated Native account metadata/read intents; client supplies no secrets."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .publication_routes import actor
from .official_accounts import Verify

def get(handler,path):
    service=handler.server.official_accounts;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-accounts':
        if params:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400)
        return service.states()
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/account-checks(?:/(nack_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/official-accounts/(npac_[a-f0-9]{32})/verify',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    try:payload=Verify.model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_ACCOUNT_FIELDS_INVALID',400) from None
    value,replay=handler.server.official_accounts.create(*match.groups(),payload,actor=actor(handler))
    handler.server.runner.wake.set()
    return {**value,'idempotent_replay':replay}
