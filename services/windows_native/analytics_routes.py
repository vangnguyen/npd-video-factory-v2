"""Native analytics reads and explicit Owner fixture requests; no browser provider access."""
import re
from urllib.parse import parse_qs
from pydantic import ValidationError
from .analytics_models import NativeAnalyticsRequest,NativeAnalyticsAction
from .analytics_refresh_models import NativeAnalyticsRefreshCreate,NativeAnalyticsRefreshState,NativeAnalyticsRefreshTick
from .contracts import WorkflowError
from .publication_routes import actor


def get(handler,path):
    if '/analytics-refresh' in path:
        match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/analytics-refresh(?:/(narp_[a-f0-9]{32}))?',path)
        if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
        project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
        if identity:
            if params:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_PAGE_INVALID',400)
            return handler.server.analytics_refresh.get(project,identity)
        if set(params)-{'limit','cursor'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('NATIVE_ANALYTICS_REFRESH_PAGE_INVALID',400)
        try:limit=int(params.get('limit',['25'])[0])
        except ValueError:raise WorkflowError('NATIVE_ANALYTICS_REFRESH_PAGE_INVALID',400) from None
        return handler.server.analytics_refresh.page(project,limit=limit,cursor=params.get('cursor',[None])[0])
    if path=='/api/analytics/providers':return handler.server.analytics.states()
    if path=='/api/analytics/overview':
        params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
        if set(params)-{'limit','cursor'} or any(len(values)!=1 for values in params.values()):raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
        try:limit=int(params.get('limit',['25'])[0])
        except ValueError:raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400) from None
        return handler.server.analytics.overview(limit=limit,cursor=params.get('cursor',[None])[0])
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/analytics(?:/(nasy_[a-f0-9]{32}))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity=match.groups();params=parse_qs(handler.path.partition('?')[2],keep_blank_values=True)
    if identity:
        if params:raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
        return handler.server.analytics.get(project,identity)
    if set(params)-{'limit','cursor','publication_id'} or any(len(values)!=1 for values in params.values()):
        raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
    try:limit=int(params.get('limit',['25'])[0])
    except ValueError:raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400) from None
    publication=params.get('publication_id',[None])[0]
    if publication is not None and not re.fullmatch(r'npub_[a-f0-9]{32}',publication):raise WorkflowError('NATIVE_ANALYTICS_PAGE_INVALID',400)
    return handler.server.analytics.page(project,limit=limit,cursor=params.get('cursor',[None])[0],publication=publication)


def post(handler,path,body):
    if '/analytics-refresh' in path:
        match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/analytics-refresh(?:/(tick)|/(narp_[a-f0-9]{32})/state)?',path)
        if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
        project,tick,identity=match.groups();service=handler.server.analytics_refresh
        try:
            if tick:
                NativeAnalyticsRefreshTick.model_validate(body)
                return service.tick(project=project,actor=actor(handler))
            if identity:return service.state(project,identity,NativeAnalyticsRefreshState.model_validate(body),actor=actor(handler))
            value,replay=service.create(project,NativeAnalyticsRefreshCreate.model_validate(body),actor=actor(handler))
            return {**value,'idempotent_replay':replay}
        except (ValidationError,TypeError):raise WorkflowError('NATIVE_ANALYTICS_REFRESH_FIELDS_INVALID',400) from None
    match=re.fullmatch(r'/api/projects/([a-f0-9]{32})/analytics(?:/(nasy_[a-f0-9]{32})/(process|cancel))?',path)
    if not match:raise WorkflowError('ROUTE_NOT_FOUND',404)
    project,identity,action=match.groups();service=handler.server.analytics
    try:
        if action is None:
            value,replay=service.create(project,NativeAnalyticsRequest.model_validate(body),actor=actor(handler))
            return {**value,'idempotent_replay':replay}
        payload=NativeAnalyticsAction.model_validate(body)
        if action=='cancel':return service.cancel(project,identity,fingerprint=payload.expected_fingerprint,actor=actor(handler))
        service.process(project=project,identity=identity,fingerprint=payload.expected_fingerprint)
        return service.get(project,identity)
    except (ValidationError,TypeError):raise WorkflowError('NATIVE_ANALYTICS_FIELDS_INVALID',400) from None
