from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from .media_intelligence_models import (
    MediaAssetProvenanceRead,
    MediaPlanRead,
    MediaPlanRequest,
    MediaResolutionJobRead,
    MediaResolutionRequest,
)
from .media_intelligence_providers import MediaProviderNotConfigured
from .media_intelligence_service import MediaPlanningService, MediaResolutionService
from .human_auth import authorize_project
from .broll_planner import BrollApplyRequest, apply_broll
from .timeline_models import TimelineRead
from .timeline_logic import TimelineEditError
from .timeline_repository import TimelineConflictError
from .learning_service import LearningError
from .stock_planner_models import StockPlannerAction, StockPlanningRead, StockPlannerHistoryRead
from .stock_planner_retry import StockPlannerConflict


router = APIRouter(prefix="/api/v1")


@router.post('/projects/{project_id}/media-plans/{media_plan_id}/apply-broll',response_model=TimelineRead)
async def apply_supporting_broll(project_id: str,media_plan_id: str,payload: BrollApplyRequest,request: Request):
    principal=await authorize_project(request,project_id,'editor')
    try:
        return await apply_broll(request.app.state.timeline_service,project_id,media_plan_id,payload,principal.subject)
    except KeyError as exc:raise missing('Supporting media plan, timeline or selected asset') from exc
    except (TimelineEditError,TimelineConflictError) as exc:raise error(409,'BROLL_TIMELINE_CONFLICT',str(exc)) from exc


def planning_service(request: Request) -> MediaPlanningService:
    return request.app.state.media_planning_service


def resolution_service(request: Request) -> MediaResolutionService:
    return request.app.state.media_resolution_service


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": f"{entity} not found."}},
    )


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


@router.post(
    "/projects/{project_id}/media-plans",
    response_model=MediaPlanRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_media_plan(
    project_id: str,
    payload: MediaPlanRequest,
    request: Request,
    response: Response,
) -> MediaPlanRead:
    try:
        result = await planning_service(request).create(project_id=project_id, payload=payload)
        if result.stock_planning and result.stock_planning.status in {'waiting', 'running'}:
            response.status_code = status.HTTP_202_ACCEPTED
        return result
    except LearningError as exc:
        raise error(404 if exc.code.endswith('_NOT_FOUND') else 409, exc.code, exc.code) from None
    except KeyError as exc:
        raise missing("Project, Auto Edit analysis, Vision analysis or source asset") from exc
    except MediaProviderNotConfigured as exc:
        raise error(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_MEDIA_PLAN", str(exc)) from exc


async def managed_plan(project_id, media_plan_id, request, role):
    await authorize_project(request, project_id, role)
    plan = await planning_service(request).get(media_plan_id)
    if plan is None or plan.project_id != project_id:
        raise missing('Media plan')
    if plan.stock_planning is None:
        raise error(503, 'STOCK_PLANNER_NOT_CONFIGURED', 'Scheduled read-only stock search is not configured for this plan.')
    return plan


@router.get('/projects/{project_id}/media-plans/{media_plan_id}/stock-search', response_model=StockPlanningRead)
async def read_stock_search(project_id: str, media_plan_id: str, request: Request):
    return (await managed_plan(project_id, media_plan_id, request, 'viewer')).stock_planning


@router.get('/projects/{project_id}/media-plans/{media_plan_id}/stock-search/history', response_model=list[StockPlannerHistoryRead])
async def read_stock_search_history(project_id: str, media_plan_id: str, request: Request):
    await managed_plan(project_id, media_plan_id, request, 'viewer')
    return await planning_service(request).stock_search_history(media_plan_id)


@router.post('/projects/{project_id}/media-plans/{media_plan_id}/stock-search/retry', response_model=MediaPlanRead)
async def retry_stock_search(project_id: str, media_plan_id: str, payload: StockPlannerAction,
    request: Request, response: Response):
    await managed_plan(project_id, media_plan_id, request, 'editor')
    try:
        result = await planning_service(request).retry_stock_search(media_plan_id, payload)
        if result.stock_planning.status in {'waiting', 'running'}:
            response.status_code = 202
        return result
    except StockPlannerConflict as exc:
        raise error(409, str(exc), 'The reviewed plan version or stock binding changed.') from None


@router.post('/projects/{project_id}/media-plans/{media_plan_id}/stock-search/cancel', response_model=MediaPlanRead)
async def cancel_stock_search(project_id: str, media_plan_id: str, payload: StockPlannerAction, request: Request):
    await managed_plan(project_id, media_plan_id, request, 'editor')
    try:
        return await planning_service(request).cancel_stock_search(media_plan_id, payload)
    except StockPlannerConflict as exc:
        raise error(409, str(exc), 'The reviewed plan version or stock binding changed.') from None


@router.get("/projects/{project_id}/media-plans", response_model=list[MediaPlanRead])
async def list_media_plans(project_id: str, request: Request) -> list[MediaPlanRead]:
    try:
        return await planning_service(request).list(project_id)
    except KeyError as exc:
        raise missing("Project") from exc


@router.get(
    "/projects/{project_id}/media-plans/{media_plan_id}",
    response_model=MediaPlanRead,
)
async def get_media_plan(
    project_id: str,
    media_plan_id: str,
    request: Request,
) -> MediaPlanRead:
    result = await planning_service(request).get(media_plan_id)
    if result is None or result.project_id != project_id:
        raise missing("Media plan")
    return result


@router.post(
    "/projects/{project_id}/media-plans/{media_plan_id}/items/{media_plan_item_id}/resolve",
    response_model=MediaResolutionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resolve_media_plan_item(
    project_id: str,
    media_plan_id: str,
    media_plan_item_id: str,
    payload: MediaResolutionRequest,
    request: Request,
) -> MediaResolutionJobRead:
    try:
        return await resolution_service(request).enqueue(
            project_id=project_id,
            media_plan_id=media_plan_id,
            media_plan_item_id=media_plan_item_id,
            payload=payload,
        )
    except KeyError as exc:
        raise missing("Project, media plan or media plan item") from exc
    except MediaProviderNotConfigured as exc:
        raise error(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_MEDIA_RESOLUTION", str(exc)) from exc


@router.get(
    "/projects/{project_id}/media-resolution-jobs/{resolution_job_id}",
    response_model=MediaResolutionJobRead,
)
async def get_media_resolution_job(
    project_id: str,
    resolution_job_id: str,
    request: Request,
) -> MediaResolutionJobRead:
    result = await resolution_service(request).get(resolution_job_id)
    if result is None or result.project_id != project_id:
        raise missing("Media resolution job")
    return result


@router.get(
    "/projects/{project_id}/media-assets",
    response_model=list[MediaAssetProvenanceRead],
)
async def list_media_assets(
    project_id: str,
    request: Request,
) -> list[MediaAssetProvenanceRead]:
    try:
        return await planning_service(request).list_media_assets(project_id)
    except KeyError as exc:
        raise missing("Project") from exc
