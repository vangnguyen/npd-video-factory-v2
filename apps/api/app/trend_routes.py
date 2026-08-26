from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from .trend_models import (
    ContentQueueItemRead,
    ContentQueueRefreshRequest,
    IdeaCandidateRead,
    IdeaGenerateRequest,
    IdeaProjectRead,
    TrendClusterRead,
    TrendClusterRefreshRequest,
    TrendCollectionRequest,
    TrendCollectionResult,
    TrendSignalRead,
    TrendSourceRead,
)
from .trend_providers import TrendProviderNotConfigured
from .trend_service import TrendIntelligenceService


router = APIRouter(prefix="/api/v1", tags=["trend-intelligence"])


def service_from(request: Request) -> TrendIntelligenceService:
    return request.app.state.trend_intelligence_service


def api_error(code: str, message: str, http_status: int) -> HTTPException:
    return HTTPException(
        status_code=http_status,
        detail={"error": {"code": code, "message": message}},
    )


@router.get("/trend-sources", response_model=list[TrendSourceRead])
async def list_trend_sources(request: Request) -> list[TrendSourceRead]:
    return await service_from(request).list_sources()


@router.post(
    "/workspaces/{workspace_id}/trend-signals/collect",
    response_model=TrendCollectionResult,
    status_code=status.HTTP_201_CREATED,
)
async def collect_trend_signals(
    workspace_id: str,
    payload: TrendCollectionRequest,
    request: Request,
) -> TrendCollectionResult:
    try:
        return await service_from(request).collect(workspace_id, payload)
    except TrendProviderNotConfigured as exc:
        raise api_error("PROVIDER_NOT_CONFIGURED", "Trend provider is not configured.", 409) from exc
    except KeyError as exc:
        entity = "Trend provider" if exc.args and exc.args[0] == payload.provider_key else "Workspace"
        raise api_error("NOT_FOUND", f"{entity} not found.", 404) from exc


@router.get("/workspaces/{workspace_id}/trend-signals", response_model=list[TrendSignalRead])
async def list_trend_signals(
    workspace_id: str,
    request: Request,
    platform: str | None = Query(default=None, max_length=80),
    country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$"),
) -> list[TrendSignalRead]:
    try:
        items = await service_from(request).list_signals(workspace_id)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc
    if platform:
        items = [item for item in items if item.source == platform]
    if country:
        items = [item for item in items if item.country == country]
    return items


@router.post(
    "/workspaces/{workspace_id}/trend-clusters/refresh",
    response_model=list[TrendClusterRead],
)
async def refresh_trend_clusters(
    workspace_id: str,
    payload: TrendClusterRefreshRequest,
    request: Request,
) -> list[TrendClusterRead]:
    try:
        return await service_from(request).refresh_clusters(workspace_id, payload)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc


@router.get("/workspaces/{workspace_id}/trend-clusters", response_model=list[TrendClusterRead])
async def list_trend_clusters(
    workspace_id: str,
    request: Request,
    lifecycle: str | None = Query(default=None, max_length=40),
    platform: str | None = Query(default=None, max_length=80),
    minimum_score: float | None = Query(default=None, ge=0, le=100),
) -> list[TrendClusterRead]:
    try:
        items = await service_from(request).list_clusters(workspace_id)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc
    if lifecycle:
        items = [item for item in items if item.lifecycle == lifecycle]
    if platform:
        items = [item for item in items if platform in item.platforms]
    if minimum_score is not None:
        items = [item for item in items if item.score and item.score.total_score >= minimum_score]
    return items


@router.get("/trend-clusters/{cluster_id}", response_model=TrendClusterRead)
async def get_trend_cluster(cluster_id: str, request: Request) -> TrendClusterRead:
    item = await service_from(request).get_cluster(cluster_id)
    if item is None:
        raise api_error("NOT_FOUND", "Trend cluster not found.", 404)
    return item


@router.post("/trend-clusters/{cluster_id}/ideas/generate", response_model=list[IdeaCandidateRead])
async def generate_ideas(
    cluster_id: str,
    payload: IdeaGenerateRequest,
    request: Request,
) -> list[IdeaCandidateRead]:
    try:
        return await service_from(request).generate_ideas(cluster_id, payload)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Trend cluster not found.", 404) from exc


@router.get("/workspaces/{workspace_id}/ideas", response_model=list[IdeaCandidateRead])
async def list_ideas(
    workspace_id: str,
    request: Request,
    cluster_id: str | None = Query(default=None, max_length=64),
    channel: str | None = Query(default=None, max_length=80),
) -> list[IdeaCandidateRead]:
    try:
        items = await service_from(request).list_ideas(workspace_id)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc
    if cluster_id:
        items = [item for item in items if item.cluster_id == cluster_id]
    if channel:
        items = [item for item in items if item.channel == channel]
    return items


@router.post(
    "/workspaces/{workspace_id}/content-opportunities/refresh",
    response_model=list[ContentQueueItemRead],
)
async def refresh_content_opportunities(
    workspace_id: str,
    payload: ContentQueueRefreshRequest,
    request: Request,
) -> list[ContentQueueItemRead]:
    try:
        return await service_from(request).refresh_queue(workspace_id, payload)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc


@router.get(
    "/workspaces/{workspace_id}/content-opportunities",
    response_model=list[ContentQueueItemRead],
)
async def list_content_opportunities(
    workspace_id: str,
    request: Request,
) -> list[ContentQueueItemRead]:
    try:
        return await service_from(request).list_queue(workspace_id)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Workspace not found.", 404) from exc


@router.post(
    "/ideas/{idea_id}/projects",
    response_model=IdeaProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_from_idea(idea_id: str, request: Request) -> IdeaProjectRead:
    try:
        return await service_from(request).create_draft_project(idea_id)
    except KeyError as exc:
        raise api_error("NOT_FOUND", "Idea not found.", 404) from exc
