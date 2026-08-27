from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from .media_intelligence_models import (
    MediaAssetProvenanceRead,
    MediaPlanRead,
    MediaPlanRequest,
    MediaResolutionJobRead,
    MediaResolutionRequest,
)
from .media_intelligence_providers import MediaProviderNotConfigured
from .media_intelligence_service import MediaPlanningService, MediaResolutionService


router = APIRouter(prefix="/api/v1")


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
) -> MediaPlanRead:
    try:
        return await planning_service(request).create(project_id=project_id, payload=payload)
    except KeyError as exc:
        raise missing("Project, Auto Edit analysis, Vision analysis or source asset") from exc
    except MediaProviderNotConfigured as exc:
        raise error(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_MEDIA_PLAN", str(exc)) from exc


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
