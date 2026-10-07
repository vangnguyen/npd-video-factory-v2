from fastapi import APIRouter, Depends, Header, Request, Response

from .analytics_refresh_models import AnalyticsRefreshCreate, AnalyticsRefreshRead, AnalyticsRefreshStateChange
from .analytics_refresh_service import AnalyticsRefreshService
from .analytics_refresh_repository import AnalyticsRefreshError
from .analytics_routes import private_analytics_response, error
from .human_auth import authorize_project

router = APIRouter(prefix='/api/v1/projects/{project_id}/analytics/refresh-plans', tags=['analytics refresh'],
    dependencies=[Depends(private_analytics_response)])


def service(request): return AnalyticsRefreshService(request.app.state.analytics_service)


def failure(exc):
    return error(404 if exc.code in ('ANALYTICS_REFRESH_PUBLICATION_NOT_FOUND', 'ANALYTICS_REFRESH_NOT_FOUND') else 409,
        exc.code, exc.code)


@router.post('', response_model=AnalyticsRefreshRead, status_code=201)
async def create_plan(project_id: str, payload: AnalyticsRefreshCreate, request: Request, response: Response,
        idempotency_key: str = Header(alias='Idempotency-Key', min_length=16, max_length=200)):
    principal = await authorize_project(request, project_id, 'owner')
    try:
        plan, replay = await service(request).create(project_id, payload, actor=principal.subject, key=idempotency_key)
        response.headers['X-Idempotent-Replay'] = 'true' if replay else 'false'
        return plan
    except AnalyticsRefreshError as exc: raise failure(exc) from None


@router.get('', response_model=list[AnalyticsRefreshRead])
async def plans(project_id: str, request: Request):
    return await service(request).repository.list(project_id)


@router.get('/{plan_id}', response_model=AnalyticsRefreshRead)
async def read_plan(project_id: str, plan_id: str, request: Request):
    result = await service(request).repository.get(project_id, plan_id)
    if result is None: raise error(404, 'ANALYTICS_REFRESH_NOT_FOUND', 'Refresh plan was not found.')
    return result


@router.post('/{plan_id}/state', response_model=AnalyticsRefreshRead)
async def state(project_id: str, plan_id: str, payload: AnalyticsRefreshStateChange, request: Request):
    principal = await authorize_project(request, project_id, 'owner')
    try: return await service(request).change_state(project_id, plan_id, payload, actor=principal.subject)
    except AnalyticsRefreshError as exc: raise failure(exc) from None


@router.get('/{plan_id}/history')
async def history(project_id: str, plan_id: str, request: Request):
    try: return await service(request).repository.history(project_id, plan_id)
    except AnalyticsRefreshError as exc: raise failure(exc) from None
