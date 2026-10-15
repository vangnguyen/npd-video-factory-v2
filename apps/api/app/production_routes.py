from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from .human_auth import authorize_project
from .verified_artifact_delivery import (ArtifactDeliveryRejected, output_asset_read, deliver_verified_artifact,
    output_sql_snapshot, asset_output_identity)
from .production_db import ProductionRenderJobORM

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
    NarrationReflowRequest,
)
from .production_repository import ApprovalBoundaryError, ProductionConflictError
from .production_service import ProductionPackageService


router = APIRouter(prefix="/api/v1", tags=["audio-subtitle-render-qc"])


@router.get("/projects/{project_id}/subtitle-templates")
async def get_subtitle_templates(project_id: str, request: Request):
    from .human_auth import authorize_project
    from .subtitle_templates import template_catalog
    await authorize_project(request, project_id, "viewer")
    return template_catalog()


@router.post("/projects/{project_id}/narration-reflow")
async def reflow_narration(project_id: str, payload: NarrationReflowRequest, request: Request):
    from .human_auth import authorize_project
    principal = await authorize_project(request, project_id, "editor")
    try:
        return await service(request).reflow_narration(project_id, payload, actor_ref=principal.subject)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except ProductionConflictError as exc:
        raise conflict(exc) from exc
    except ProductionContractError as exc:
        raise invalid(exc) from exc


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
    from .human_auth import authorize_project
    principal = await authorize_project(request, project_id, "editor")
    payload = payload.model_copy(update={"actor_ref": principal.subject})
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
    principal = await authorize_project(request, project_id, 'editor')
    payload = payload.model_copy(update={'actor_ref': principal.subject})
    return await enqueue_final_render_command(project_id, payload, request)


async def enqueue_final_render_command(
    project_id: str,
    payload: FinalRenderCreateRequest,
    request: Request,
) -> RenderJobRead:
    """Canonical final command/error mapping for already admitted callers.

    The HTTP human handler and signed service facade each authorize their own
    principal and set actor_ref before calling. This helper grants no authority.
    """
    from .sql_variant_narration_activation import VariantNarrationQueueUnknownError
    try:
        return await service(request).enqueue_final(project_id, payload)
    except KeyError as exc:
        raise missing(str(exc.args[0])) from exc
    except VariantNarrationQueueUnknownError:
        raise HTTPException(503, detail={'code': 'SQL_VARIANT_NARRATION_QUEUE_OUTCOME_UNKNOWN'},
            headers={'Cache-Control': 'no-store'}) from None
    except ApprovalBoundaryError as exc:
        if str(exc) == 'SQL_VARIANT_NARRATION_NOT_CONFIGURED':
            raise HTTPException(503, detail={'code': str(exc)}, headers={'Cache-Control': 'no-store'}) from None
        raise conflict(exc) from exc
    except ProductionConflictError as exc:
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


@router.api_route("/projects/{project_id}/renders/{render_id}/content", methods=['GET','HEAD'], response_class=FileResponse)
async def render_content(project_id: str, render_id: str, request: Request) -> FileResponse:
    await authorize_project(request, project_id, 'viewer')
    render = await service(request).get_render(project_id, render_id)
    if render is None or render.output_asset_id is None:
        raise missing("render content")
    asset = await request.app.state.auto_edit_repository.get_asset(render.output_asset_id)
    if asset is None or asset.project_id != project_id or asset.workspace_id != render.workspace_id:
        raise missing("render asset")
    asset = asset.model_copy(deep=True)
    factory = request.app.state.auto_edit_repository.session_factory
    expected = await output_sql_snapshot(factory,ProductionRenderJobORM,ProductionRenderJobORM.render_id,render_id,
        project_id=project_id,workspace_id=render.workspace_id)
    if expected is None:
        raise missing('render asset')
    if expected['asset'] != asset_output_identity(asset):
        raise HTTPException(409,detail={'code':'ARTIFACT_OUTPUT_CHANGED'})
    async def current():
        latest = await output_sql_snapshot(factory,ProductionRenderJobORM,ProductionRenderJobORM.render_id,render_id,
            project_id=project_id,workspace_id=render.workspace_id)
        if latest != expected:
            raise ArtifactDeliveryRejected('ARTIFACT_OUTPUT_CHANGED')
    try:
        proof = output_asset_read(asset, workspace_id=render.workspace_id, project_id=project_id,
            storage=request.app.state.object_storage, kind='av-review' if render.render_kind=='review' else 'final-render')
        return await deliver_verified_artifact(proof=proof, storage=request.app.state.object_storage,
            staging_root=Path(request.app.state.production_render_download_root), basename='render.mp4',
            filename=asset.filename, media_type='video/mp4', current=current)
    except FileNotFoundError:
        raise missing('render object') from None
    except ArtifactDeliveryRejected as error:
        raise HTTPException(error.status, detail={'code':error.code}) from None


@router.api_route('/projects/{project_id}/renders/{render_id}/diagnostics/{name}',
    methods=['GET','HEAD'], response_class=FileResponse)
async def failed_render_diagnostic(project_id: str, render_id: str, name: str, request: Request) -> FileResponse:
    """Private rejected bytes; this route never becomes a playback/output URL."""
    await authorize_project(request, project_id, 'viewer')
    from .failed_render_evidence import ARTIFACTS, artifact_read
    if name not in ARTIFACTS:
        raise missing('render diagnostic')
    repository = service(request).repository
    recorded = await repository.failed_evidence_snapshot(project_id, render_id)
    if recorded is None:
        raise missing('render diagnostic')
    try:
        proof, filename, media_type = artifact_read(recorded['render'], recorded['ledger'], name)
        async def current():
            latest = await repository.failed_evidence_snapshot(project_id, render_id)
            if latest is None or latest['snapshot'] != recorded['snapshot']:
                raise ArtifactDeliveryRejected('FAILED_EVIDENCE_CHANGED')
            artifact_read(latest['render'], latest['ledger'], name)
        return await deliver_verified_artifact(proof=proof, storage=request.app.state.object_storage,
            staging_root=Path(request.app.state.production_render_download_root), basename='artifact.bin',
            filename='failed-qc-'+filename, media_type=media_type, current=current)
    except FileNotFoundError:
        raise missing('render diagnostic object') from None
    except ArtifactDeliveryRejected as error:
        raise HTTPException(error.status, detail={'code':error.code}) from None


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
