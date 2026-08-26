from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status

from .platform_models import (
    AssetRead,
    AssetRegister,
    CostRecordRead,
    JobEventRead,
    ProjectCostSummary,
    ProjectCreate,
    ProjectRead,
    ProjectVersionCreate,
    ProjectVersionRead,
    ProviderRead,
    WorkspaceCreate,
    WorkspaceRead,
)
from .repositories import PlatformRepository, PostgresJobStore


router = APIRouter(prefix="/api/v1")


def platform_from(request: Request) -> PlatformRepository:
    return request.app.state.platform_repository


def store_from(request: Request) -> PostgresJobStore:
    return request.app.state.job_store


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": f"{entity} not found."}},
    )


@router.post("/workspaces", response_model=WorkspaceRead, status_code=status.HTTP_201_CREATED)
async def create_workspace(payload: WorkspaceCreate, request: Request) -> WorkspaceRead:
    try:
        return await platform_from(request).create_workspace(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "CONFLICT", "message": str(exc)}}) from exc


@router.get("/workspaces", response_model=list[WorkspaceRead])
async def list_workspaces(request: Request) -> list[WorkspaceRead]:
    return await platform_from(request).list_workspaces()


@router.get("/workspaces/{workspace_id}", response_model=WorkspaceRead)
async def get_workspace(workspace_id: str, request: Request) -> WorkspaceRead:
    result = await platform_from(request).get_workspace(workspace_id)
    if result is None:
        raise missing("Workspace")
    return result


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(workspace_id: str, payload: ProjectCreate, request: Request) -> ProjectRead:
    try:
        return await platform_from(request).create_project(workspace_id, payload)
    except KeyError as exc:
        raise missing("Workspace") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "CONFLICT", "message": str(exc)}}) from exc


@router.get("/workspaces/{workspace_id}/projects", response_model=list[ProjectRead])
async def list_projects(workspace_id: str, request: Request) -> list[ProjectRead]:
    if await platform_from(request).get_workspace(workspace_id) is None:
        raise missing("Workspace")
    return await platform_from(request).list_projects(workspace_id)


@router.get("/projects/{project_id}", response_model=ProjectRead)
async def get_project(project_id: str, request: Request) -> ProjectRead:
    result = await platform_from(request).get_project(project_id)
    if result is None:
        raise missing("Project")
    return result


@router.post(
    "/projects/{project_id}/versions",
    response_model=ProjectVersionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_project_version(
    project_id: str,
    payload: ProjectVersionCreate,
    request: Request,
) -> ProjectVersionRead:
    try:
        return await platform_from(request).create_version(project_id, payload)
    except KeyError as exc:
        raise missing("Project") from exc


@router.get("/projects/{project_id}/versions", response_model=list[ProjectVersionRead])
async def list_project_versions(project_id: str, request: Request) -> list[ProjectVersionRead]:
    if await platform_from(request).get_project(project_id) is None:
        raise missing("Project")
    return await platform_from(request).list_versions(project_id)


@router.post(
    "/projects/{project_id}/assets/register",
    response_model=AssetRead,
    status_code=status.HTTP_201_CREATED,
)
async def register_asset(project_id: str, payload: AssetRegister, request: Request) -> AssetRead:
    try:
        return await platform_from(request).register_asset(project_id, payload)
    except KeyError as exc:
        raise missing("Project or version") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "CONFLICT", "message": str(exc)}}) from exc


@router.get("/projects/{project_id}/assets", response_model=list[AssetRead])
async def list_assets(project_id: str, request: Request) -> list[AssetRead]:
    if await platform_from(request).get_project(project_id) is None:
        raise missing("Project")
    return await platform_from(request).list_assets(project_id)


@router.get("/providers", response_model=list[ProviderRead])
async def list_providers(
    request: Request,
    capability: str | None = Query(default=None, max_length=120),
) -> list[ProviderRead]:
    return await platform_from(request).list_providers(capability=capability)


@router.get("/projects/{project_id}/costs", response_model=list[CostRecordRead])
async def list_project_costs(project_id: str, request: Request) -> list[CostRecordRead]:
    if await platform_from(request).get_project(project_id) is None:
        raise missing("Project")
    return await platform_from(request).list_cost_records(project_id)


@router.get("/projects/{project_id}/cost-summary", response_model=ProjectCostSummary)
async def get_project_cost_summary(project_id: str, request: Request) -> ProjectCostSummary:
    try:
        return await platform_from(request).project_cost_summary(project_id)
    except KeyError as exc:
        raise missing("Project") from exc


@router.get("/video-jobs/{job_id}/events", response_model=list[JobEventRead])
async def list_job_events(job_id: str, request: Request) -> list[JobEventRead]:
    if await store_from(request).get(job_id) is None:
        raise missing("Job")
    return await store_from(request).list_events(job_id)
