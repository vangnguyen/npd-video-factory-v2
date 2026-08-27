from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from .production_logic import ProductionContractError
from .production_models import (
    ApprovalDecisionRequest,
    ApprovalRead,
    ApprovalRequest,
    AudioMixReplaceRequest,
    FinalRenderCreateRequest,
    ProductionEventRead,
    ProductionPackageCreateRequest,
    ProductionPackageRead,
    RenderCreateRequest,
    RenderJobRead,
    SubtitleReplaceRequest,
)
from .production_repository import ApprovalBoundaryError, ProductionConflictError
from .production_service import ProductionPackageService


router = APIRouter(prefix="/api/v1", tags=["audio-subtitle-render-qc"])


def service(request: Request) -> ProductionPackageService:
    return request.app.state.production_package_service


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"code": "NOT_FOUND", "message": f"{entity} was not found"},
    )


def invalid(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail={"code": "PRODUCTION_PACKAGE_INVALID", "message": str(exc)},
    )


def conflict(exc: Exception) -> HTTPException:
    detail: dict[str, object] = {"code": "PRODUCTION_PACKAGE_CONFLICT", "message": str(exc)}
    if isinstance(exc, ProductionConflictError):
        detail.update(
            {
                "entity": exc.entity,
                "expected_version": exc.expected,
                "current_version": exc.actual,
            }
        )
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.post(
    "/projects/{project_id}/production-package",
    response_model=ProductionPackageRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_or_refresh_package(
    project_id: str,
    payload: ProductionPackageCreateRequest,
    request: Request,
) -> ProductionPackageRead:
    try:
        return await service(request).create_or_refresh(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ProductionConflictError as exc:
        raise conflict(exc) from exc
    except ProductionContractError as exc:
        raise invalid(exc) from exc


@router.get("/projects/{project_id}/production-package", response_model=ProductionPackageRead)
async def get_package(project_id: str, request: Request) -> ProductionPackageRead:
    package = await service(request).get(project_id)
    if package is None:
        raise missing("production-package")
    return package


@router.put("/projects/{project_id}/subtitles", response_model=ProductionPackageRead)
async def replace_subtitles(
    project_id: str,
    payload: SubtitleReplaceRequest,
    request: Request,
) -> ProductionPackageRead:
    try:
        return await service(request).replace_subtitles(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ProductionConflictError as exc:
        raise conflict(exc) from exc
    except ProductionContractError as exc:
        raise invalid(exc) from exc


@router.put("/projects/{project_id}/audio-mix", response_model=ProductionPackageRead)
async def replace_audio_mix(
    project_id: str,
    payload: AudioMixReplaceRequest,
    request: Request,
) -> ProductionPackageRead:
    try:
        return await service(request).replace_audio_mix(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ProductionConflictError as exc:
        raise conflict(exc) from exc
    except ProductionContractError as exc:
        raise invalid(exc) from exc


@router.post(
    "/projects/{project_id}/review-render",
    response_model=RenderJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_review_render(
    project_id: str,
    payload: RenderCreateRequest,
    request: Request,
) -> RenderJobRead:
    try:
        return await service(request).enqueue_review(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ProductionConflictError as exc:
        raise conflict(exc) from exc
    except (ApprovalBoundaryError, ProductionContractError) as exc:
        raise invalid(exc) from exc


@router.post(
    "/projects/{project_id}/final-render",
    response_model=RenderJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_final_render(
    project_id: str,
    payload: FinalRenderCreateRequest,
    request: Request,
) -> RenderJobRead:
    try:
        return await service(request).enqueue_final(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except (ProductionConflictError, ApprovalBoundaryError) as exc:
        raise conflict(exc) from exc
    except ProductionContractError as exc:
        raise invalid(exc) from exc


@router.get("/projects/{project_id}/renders/{render_id}", response_model=RenderJobRead)
async def get_render(project_id: str, render_id: str, request: Request) -> RenderJobRead:
    render = await service(request).get_render(project_id, render_id)
    if render is None:
        raise missing("render")
    return render


@router.post("/projects/{project_id}/renders/{render_id}/cancel", response_model=RenderJobRead)
async def cancel_render(
    project_id: str,
    render_id: str,
    request: Request,
    actor_ref: str = Query(default="studio-user", min_length=1, max_length=160),
) -> RenderJobRead:
    render = await service(request).cancel_render(project_id, render_id, actor_ref)
    if render is None:
        raise missing("render")
    return render


@router.get("/projects/{project_id}/renders/{render_id}/content", response_class=FileResponse)
async def render_content(project_id: str, render_id: str, request: Request) -> FileResponse:
    render = await service(request).get_render(project_id, render_id)
    if render is None or render.output_asset_id is None:
        raise missing("render content")
    asset = await request.app.state.auto_edit_repository.get_asset(render.output_asset_id)
    if asset is None or asset.project_id != project_id:
        raise missing("render asset")
    download_root = Path(request.app.state.production_render_download_root).resolve()
    target_dir = (download_root / uuid.uuid4().hex).resolve()
    if download_root not in target_dir.parents:
        raise HTTPException(status_code=500, detail={"code": "INVALID_RENDER_PATH"})
    target = target_dir / asset.filename
    try:
        await request.app.state.object_storage.download_file(
            object_key=asset.object_key,
            destination=target,
        )
    except FileNotFoundError as exc:
        shutil.rmtree(target_dir, ignore_errors=True)
        raise missing("render object") from exc
    return FileResponse(
        target,
        media_type="video/mp4",
        filename=asset.filename,
        background=BackgroundTask(shutil.rmtree, target_dir, ignore_errors=True),
    )


@router.post(
    "/projects/{project_id}/approvals",
    response_model=ApprovalRead,
    status_code=status.HTTP_201_CREATED,
)
async def request_approval(
    project_id: str,
    payload: ApprovalRequest,
    request: Request,
) -> ApprovalRead:
    try:
        return await service(request).request_approval(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ApprovalBoundaryError as exc:
        raise conflict(exc) from exc


@router.post("/projects/{project_id}/approvals/{approval_id}/decision", response_model=ApprovalRead)
async def decide_approval(
    project_id: str,
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
) -> ApprovalRead:
    try:
        return await service(request).decide_approval(project_id, approval_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ApprovalBoundaryError as exc:
        raise conflict(exc) from exc


@router.get("/projects/{project_id}/production-history", response_model=list[ProductionEventRead])
async def production_history(project_id: str, request: Request) -> list[ProductionEventRead]:
    return await service(request).history(project_id)
