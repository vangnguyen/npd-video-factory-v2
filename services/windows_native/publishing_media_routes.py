"""Signed media-disclosure requests/history/selection; public URLs never returned."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .contracts import WorkflowError
from .official_publication_models import Action
from .publishing_media_delivery import Create
from .meta_publishing import MediaBind,bind_media

BASE=r'/api/projects/([a-f0-9]{32})/official-publications/(nopu_[a-f0-9]{32})'
DELIVERY=r'(nmd_[a-f0-9]{32})'


def get(handler,path):
    journal=handler.server.official_publications;service=handler.server.publishing_media
    params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if path=='/api/connections/publishing-media':
        if params:raise WorkflowError('NATIVE_MEDIA_DELIVERY_PAGE_INVALID',400)
        if service is not None and service.factory is not None:return service.factory.public()
        return {'schema_version':'native-publishing-media-delivery-factory-v1','workspace_id':journal.workspace,'configuration_sha256':None,
            'status':'NOT_CONFIGURED','mock':False,'provider':'s3-publishing-media','credential_returned':False,'url_returned':False,
            'publishing_authority':False,'automatic_delivery':False,'real_provider_tested':False}
    match=re.fullmatch(BASE+r'/media-deliveries(?:/'+DELIVERY+r')?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,publication,identity=match.groups();journal.get(project,publication)
    if identity:
        if params:raise WorkflowError('NATIVE_MEDIA_DELIVERY_PAGE_INVALID',400)
        if service is None:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_FOUND',404)
        value=service.get(project,identity)
        if value['snapshot']['scope']['publication_id']!=publication:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_FOUND',404)
        return value
    if set(params)-{'limit','cursor'} or any(len(v)!=1 for v in params.values()):raise WorkflowError('NATIVE_MEDIA_DELIVERY_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_MEDIA_DELIVERY_PAGE_INVALID',400) from None
    cursor=params.get('cursor',[None])[0]
    if service is not None:return service.page(project,publication,limit=limit,cursor=cursor)
    if not 1<=limit<=100 or cursor is not None:raise WorkflowError('NATIVE_MEDIA_DELIVERY_PAGE_INVALID',400)
    return {'schema_version':'native-publishing-media-delivery-page-v1','workspace_id':journal.workspace,'project_id':project,'publication_id':publication,
        'items':[],'truncated':False,'next_cursor':None,'url_returned':False,'publishing_authority':False}


def post(handler,path,body):
    match=re.fullmatch(BASE+r'/(media-selection|media-deliveries(?:/'+DELIVERY+r'/(process|cancel))?)',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,publication,route,identity,action=match.groups();journal=handler.server.official_publications;service=handler.server.publishing_media
    session=getattr(handler,'auth_session',None)
    if session is None:raise WorkflowError('NATIVE_HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED',403)
    principal=session.principal;journal.identity(principal)
    try:payload=(MediaBind if route=='media-selection' else Action if identity else Create).model_validate(body)
    except (ValidationError,TypeError,ValueError):raise WorkflowError('NATIVE_MEDIA_DELIVERY_FIELDS_INVALID',400) from None
    journal.get(project,publication)
    if service is None:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_CONFIGURED')
    if route=='media-selection':
        value,replay=bind_media(journal,service,project,publication,payload,principal=principal)
        return {**value,'idempotent_replay':replay,'url_returned':False,'publishing_authority':False}
    if identity:
        value=service.get(project,identity)
        if value['snapshot']['scope']['publication_id']!=publication:raise WorkflowError('NATIVE_MEDIA_DELIVERY_NOT_FOUND',404)
        if value['snapshot_sha256']!=payload.expected_snapshot_sha256:raise WorkflowError('NATIVE_MEDIA_DELIVERY_SOURCE_CHANGED')
        return service.cancel(project,identity,principal=principal) if action=='cancel' else service.process(project,identity)
    if payload.publication_id!=publication:raise WorkflowError('NATIVE_MEDIA_DELIVERY_SOURCE_CHANGED')
    value,replay=service.create(project,payload,principal=principal);handler.server.runner.wake.set()
    return {**value,'idempotent_replay':replay}
