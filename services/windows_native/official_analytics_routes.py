"""Signed finite read intents/history; HTTP creation never calls the provider."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError,digest
from .official_analytics_models import Collect,Cancel
BASE=r'/api/projects/([a-f0-9]{32})/official-analytics'
IDENTITY=r'(noas_[a-f0-9]{32})'

def get(handler,path):
    service=handler.server.official_analytics;params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/official-analytics':
        if params:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400)
        return service.states()
    binding=re.fullmatch(BASE+r'/source/(nopu_[a-f0-9]{32})',path)
    if binding:
        if params:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400)
        service.check();project,publication_id=binding.groups();publication=service.publications.get(project,publication_id)
        if publication['status']!='completed' or publication['receipt'] is None:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_QUALIFIED_RECEIPT_REQUIRED')
        return {'schema_version':'native-official-analytics-publication-binding-v1','workspace_id':service.workspace,'project_id':project,
            'publication_id':publication_id,'publication_snapshot_sha256':publication['snapshot_sha256'],'receipt_sha256':digest(publication['receipt']),
            'target':publication['snapshot']['target'],'mock':publication['mock'],'remote_post_id':publication['receipt']['remote_post_id'],
            'receipt_qualified':True,'published':publication['published'],'publishing_enabled':False,'token_returned':False,'real_provider_tested':False}
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups()
    if identity:
        if params:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400)
        return service.get(project,identity)
    if set(params)-{'limit','cursor','publication'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_PAGE_INVALID',400) from None
    return service.page(project,limit=limit,cursor=params.get('cursor',[None])[0],publication=params.get('publication',[None])[0])

def post(handler,path,body):
    match=re.fullmatch(BASE+r'(?:/'+IDENTITY+r'/cancel)?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_CURRENT_OWNER_REQUIRED',403)
    project,identity=match.groups();service=handler.server.official_analytics;service.identity(session.principal)
    try:payload=(Cancel if identity else Collect).model_validate(body)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_OFFICIAL_ANALYTICS_FIELDS_INVALID',400) from None
    if identity:return service.cancel(project,identity,payload,principal=session.principal)
    value,replay=service.create(project,payload,principal=session.principal);handler.server.runner.wake.set()
    # Return the same qualified history shape for new and already completed keys.
    # This remains a local journal read; neither creation nor replay calls a provider.
    return {**service.get(project,value['sync_id']),'idempotent_replay':replay}
