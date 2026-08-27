from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

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
        return await timeline_service(request).create(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
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


@router.get("/projects/{project_id}/previews/{preview_id}/content", response_class=FileResponse)
async def preview_content(project_id: str, preview_id: str, request: Request) -> FileResponse:
    preview = await preview_service(request).get(project_id, preview_id)
    if preview is None or preview.output_asset_id is None:
        raise missing("preview content")
    asset = await request.app.state.auto_edit_repository.get_asset(preview.output_asset_id)
    if asset is None or asset.project_id != project_id:
        raise missing("preview asset")
    download_root = Path(request.app.state.preview_download_root).resolve()
    target_dir = (download_root / uuid.uuid4().hex).resolve()
    if download_root not in target_dir.parents:
        raise HTTPException(status_code=500, detail={"code": "INVALID_PREVIEW_PATH"})
    target = target_dir / "preview.mp4"
    try:
        await request.app.state.object_storage.download_file(
            object_key=asset.object_key,
            destination=target,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise missing("preview object") from exc
    return FileResponse(
        target,
        media_type="video/mp4",
        filename="preview.mp4",
        background=BackgroundTask(shutil.rmtree, target_dir, ignore_errors=True),
    )
