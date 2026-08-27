from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from .analytics_models import (
    AnalyticsEventRead,
    AnalyticsMetricSnapshotRead,
    AnalyticsProviderStateRead,
    AnalyticsReportRead,
    AnalyticsSyncRead,
    AnalyticsSyncRequest,
    LearningInsightRead,
    WinnerAssessmentRead,
)
from .analytics_repository import AnalyticsIdempotencyConflict
from .analytics_service import AnalyticsBoundaryError, AnalyticsService


router = APIRouter(prefix="/api/v1", tags=["analytics"])


def service(request: Request) -> AnalyticsService:
    return request.app.state.analytics_service


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message}},
    )


@router.post(
    "/projects/{project_id}/analytics/syncs",
    response_model=AnalyticsSyncRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_analytics_sync(
    project_id: str,
    payload: AnalyticsSyncRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> AnalyticsSyncRead:
    try:
        sync, replay = await service(request).create_sync(
            project_id=project_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        response.headers["X-Idempotent-Replay"] = "true" if replay else "false"
        return sync
    except KeyError as exc:
        raise error(404, "ANALYTICS_REFERENCE_NOT_FOUND", str(exc.args[0])) from exc
    except AnalyticsIdempotencyConflict as exc:
        raise error(409, "IDEMPOTENCY_KEY_CONFLICT", str(exc)) from exc
    except AnalyticsBoundaryError as exc:
        raise error(409, exc.code, str(exc)) from exc


@router.get("/projects/{project_id}/analytics", response_model=AnalyticsReportRead)
async def analytics_report(project_id: str, request: Request) -> AnalyticsReportRead:
    try:
        return await service(request).report(project_id)
    except KeyError as exc:
        raise error(404, "PROJECT_NOT_FOUND", str(exc.args[0])) from exc


@router.get("/projects/{project_id}/analytics/syncs", response_model=list[AnalyticsSyncRead])
async def list_analytics_syncs(project_id: str, request: Request) -> list[AnalyticsSyncRead]:
    return await service(request).list_syncs(project_id)


@router.get(
    "/projects/{project_id}/analytics/syncs/{sync_id}",
    response_model=AnalyticsSyncRead,
)
async def get_analytics_sync(project_id: str, sync_id: str, request: Request) -> AnalyticsSyncRead:
    result = await service(request).get_sync(project_id, sync_id)
    if result is None:
        raise error(404, "ANALYTICS_SYNC_NOT_FOUND", "Analytics sync was not found.")
    return result


@router.get(
    "/projects/{project_id}/analytics/snapshots",
    response_model=list[AnalyticsMetricSnapshotRead],
)
async def analytics_snapshots(
    project_id: str, request: Request
) -> list[AnalyticsMetricSnapshotRead]:
    try:
        return await service(request).snapshots(project_id)
    except KeyError as exc:
        raise error(404, "PROJECT_NOT_FOUND", str(exc.args[0])) from exc


@router.get(
    "/projects/{project_id}/analytics/assessments",
    response_model=list[WinnerAssessmentRead],
)
async def analytics_assessments(
    project_id: str, request: Request
) -> list[WinnerAssessmentRead]:
    try:
        return await service(request).assessments(project_id)
    except KeyError as exc:
        raise error(404, "PROJECT_NOT_FOUND", str(exc.args[0])) from exc


@router.get(
    "/projects/{project_id}/analytics/learning-insights",
    response_model=list[LearningInsightRead],
)
async def analytics_learning_insights(
    project_id: str, request: Request
) -> list[LearningInsightRead]:
    try:
        return await service(request).insights(project_id)
    except KeyError as exc:
        raise error(404, "PROJECT_NOT_FOUND", str(exc.args[0])) from exc


@router.get(
    "/projects/{project_id}/analytics/history",
    response_model=list[AnalyticsEventRead],
)
async def analytics_history(project_id: str, request: Request) -> list[AnalyticsEventRead]:
    try:
        return await service(request).events(project_id)
    except KeyError as exc:
        raise error(404, "PROJECT_NOT_FOUND", str(exc.args[0])) from exc


@router.get("/analytics-providers", response_model=list[AnalyticsProviderStateRead])
async def analytics_providers(request: Request) -> list[AnalyticsProviderStateRead]:
    return service(request).provider_states()
