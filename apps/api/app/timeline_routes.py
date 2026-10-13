from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from .verified_artifact_delivery import (ArtifactDeliveryRejected, output_asset_read, deliver_verified_artifact,
    output_sql_snapshot, asset_output_identity)
from .timeline_db import PreviewJobORM

from .timeline_logic import TimelineEditError
from .timeline_models import (
    PreviewCreateRequest,
    PreviewRead,
    TimelineCreateRequest,
    TimelineMutationRequest,
    TimelineRead,
    TimelineRestoreRequest,
    TimelineVersionRead,
)
from .timeline_repository import TimelineConflictError
from .timeline_service import PreviewService, TimelineService
from .human_auth import principal_from,authorize_project
from .timeline_reframe import ReframeApplyRequest,apply_reframe


router = APIRouter(prefix="/api/v1", tags=["auto-edit-studio"])


def timeline_service(request: Request) -> TimelineService:
    return request.app.state.timeline_service


def preview_service(request: Request) -> PreviewService:
    return request.app.state.preview_service


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": f"{entity} was not found"},
    )


def invalid(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "TIMELINE_INVALID", "message": message},
    )


@router.post('/projects/{project_id}/timeline/reframe',response_model=TimelineRead)
async def reframe_timeline(project_id:str,payload:ReframeApplyRequest,request:Request):
    principal=await authorize_project(request,project_id,'editor')
    vision_service=getattr(request.app.state,'vision_analysis_service',None)
    try:
        return await apply_reframe(timeline_service(request),getattr(vision_service,'repository',None),
                                   project_id,payload,principal.subject)
    except KeyError as exc:raise missing('Source timeline or Vision analysis') from exc
    except TimelineConflictError as exc:
        raise HTTPException(409,detail={'code':'TIMELINE_VERSION_CONFLICT','message':str(exc)}) from exc
    except TimelineEditError as exc:raise invalid(str(exc)) from exc


@router.post(
    "/projects/{project_id}/timeline",
    response_model=TimelineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_timeline(
    project_id: str,
    payload: TimelineCreateRequest,
    request: Request,
) -> TimelineRead:
    try:
        payload = payload.model_copy(update={"actor_ref": principal_from(request).subject})
        return await timeline_service(request).create(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except TimelineConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
            detail={"code": "TIMELINE_VERSION_CONFLICT", "message": str(exc),
                    "expected_version": exc.expected, "current_version": exc.actual}) from exc
    except TimelineEditError as exc:
        raise invalid(str(exc)) from exc


@router.get("/projects/{project_id}/timeline", response_model=TimelineRead)
async def get_timeline(project_id: str, request: Request) -> TimelineRead:
    timeline = await timeline_service(request).get(project_id)
    if timeline is None:
        raise missing("timeline")
    return timeline


@router.put("/projects/{project_id}/timeline", response_model=TimelineRead)
async def update_timeline(
    project_id: str,
    payload: TimelineMutationRequest,
    request: Request,
) -> TimelineRead:
    try:
        payload = payload.model_copy(update={"actor_ref": principal_from(request).subject})
        return await timeline_service(request).mutate(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except TimelineConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TIMELINE_VERSION_CONFLICT",
                "message": str(exc),
                "expected_version": exc.expected,
                "current_version": exc.actual,
            },
        ) from exc
    except TimelineEditError as exc:
        raise invalid(str(exc)) from exc


@router.post("/projects/{project_id}/timeline/restore", response_model=TimelineRead)
async def restore_timeline(
    project_id: str,
    payload: TimelineRestoreRequest,
    request: Request,
) -> TimelineRead:
    try:
        payload = payload.model_copy(update={"actor_ref": principal_from(request).subject})
        return await timeline_service(request).restore(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except TimelineConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "TIMELINE_VERSION_CONFLICT",
                "message": str(exc),
                "expected_version": exc.expected,
                "current_version": exc.actual,
            },
        ) from exc


@router.get(
    "/projects/{project_id}/timeline/versions",
    response_model=list[TimelineVersionRead],
)
async def list_timeline_versions(project_id: str, request: Request) -> list[TimelineVersionRead]:
    return await timeline_service(request).list_versions(project_id)


@router.post(
    "/projects/{project_id}/preview",
    response_model=PreviewRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_preview(
    project_id: str,
    payload: PreviewCreateRequest,
    request: Request,
) -> PreviewRead:
    try:
        payload = payload.model_copy(update={"actor_ref": principal_from(request).subject})
        return await preview_service(request).enqueue(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc


@router.get("/projects/{project_id}/previews/{preview_id}", response_model=PreviewRead)
async def get_preview(project_id: str, preview_id: str, request: Request) -> PreviewRead:
    preview = await preview_service(request).get(project_id, preview_id)
    if preview is None:
        raise missing("preview")
    return preview


@router.post("/projects/{project_id}/previews/{preview_id}/cancel", response_model=PreviewRead)
async def cancel_preview(project_id: str, preview_id: str, request: Request) -> PreviewRead:
    preview = await preview_service(request).cancel(project_id, preview_id)
    if preview is None:
        raise missing("preview")
    return preview


@router.api_route("/projects/{project_id}/previews/{preview_id}/content", methods=['GET','HEAD'], response_class=FileResponse)
async def preview_content(project_id: str, preview_id: str, request: Request) -> FileResponse:
    await authorize_project(request, project_id, 'viewer')
    preview = await preview_service(request).get(project_id, preview_id)
    if preview is None or preview.output_asset_id is None:
        raise missing("preview content")
    asset = await request.app.state.auto_edit_repository.get_asset(preview.output_asset_id)
    if asset is None or asset.project_id != project_id or asset.workspace_id != preview.workspace_id:
        raise missing("preview asset")
    asset = asset.model_copy(deep=True)
    factory = request.app.state.auto_edit_repository.session_factory
    expected = await output_sql_snapshot(factory,PreviewJobORM,PreviewJobORM.preview_id,preview_id,
        project_id=project_id,workspace_id=preview.workspace_id)
    if expected is None:
        raise missing('preview asset')
    if expected['asset'] != asset_output_identity(asset):
        raise HTTPException(409,detail={'code':'ARTIFACT_OUTPUT_CHANGED'})
    async def current():
        latest = await output_sql_snapshot(factory,PreviewJobORM,PreviewJobORM.preview_id,preview_id,
            project_id=project_id,workspace_id=preview.workspace_id)
        if latest != expected:
            raise ArtifactDeliveryRejected('ARTIFACT_OUTPUT_CHANGED')
    try:
        proof = output_asset_read(asset, workspace_id=preview.workspace_id, project_id=project_id,
            storage=request.app.state.object_storage, kind='proxy-preview')
        return await deliver_verified_artifact(proof=proof, storage=request.app.state.object_storage,
            staging_root=Path(request.app.state.preview_download_root), basename='preview.mp4',
            filename='preview.mp4', media_type='video/mp4', current=current)
    except FileNotFoundError:
        raise missing('preview object') from None
    except ArtifactDeliveryRejected as error:
        raise HTTPException(error.status, detail={'code':error.code}) from None
