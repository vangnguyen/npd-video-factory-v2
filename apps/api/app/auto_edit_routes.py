from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException, Request, status

from .auto_edit_models import (
    AutoEditAnalysisRead,
    AutoEditAnalysisRequest,
    UploadCompleteRead,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadRead,
)
from .auto_edit_providers import MediaProbeError, ProviderNotConfigured
from .auto_edit_service import AutoEditAnalysisService, UploadConflictError, UploadService, UploadSizeError
from .human_auth import authorize_project
from .media_security import MediaScanUnavailable, MediaSecurityError, UnsafeMediaRejected
from .media_validation import MediaValidationError


router = APIRouter(prefix="/api/v1")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


def upload_service_from(request: Request) -> UploadService:
    return request.app.state.upload_service


def analysis_service_from(request: Request) -> AutoEditAnalysisService:
    return request.app.state.auto_edit_analysis_service


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": f"{entity} not found."}},
    )


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


@router.post("/uploads/init", response_model=UploadRead, status_code=status.HTTP_201_CREATED)
async def initialize_upload(payload: UploadInitRequest, request: Request) -> UploadRead:
    try:
        await authorize_project(request, payload.project_id, "editor")
        return await upload_service_from(request).initialize(payload)
    except KeyError as exc:
        raise missing("Project or version") from exc
    except UploadSizeError as exc:
        raise error(413, "UPLOAD_TOO_LARGE", str(exc)) from exc


@router.get("/uploads/{upload_id}", response_model=UploadRead)
async def get_upload(upload_id: str, request: Request) -> UploadRead:
    result = await upload_service_from(request).get(upload_id)
    if result is None:
        raise missing("Upload")
    return result


@router.put("/uploads/{upload_id}/parts/{part_number}", response_model=UploadRead)
async def upload_part(
    upload_id: str,
    part_number: int,
    request: Request,
    x_part_sha256: str | None = Header(default=None),
) -> UploadRead:
    if x_part_sha256 and not _SHA256.fullmatch(x_part_sha256):
        raise error(422, "INVALID_PART_CHECKSUM", "X-Part-SHA256 must be lowercase SHA-256.")
    try:
        return await upload_service_from(request).store_part(
            upload_id,
            part_number,
            request.stream(),
            expected_part_sha256=x_part_sha256,
        )
    except KeyError as exc:
        raise missing("Upload") from exc
    except UploadSizeError as exc:
        raise error(413, "INVALID_PART_SIZE", str(exc)) from exc
    except UploadConflictError as exc:
        raise error(409, "UPLOAD_CONFLICT", str(exc)) from exc


@router.post("/uploads/{upload_id}/complete", response_model=UploadCompleteRead)
async def complete_upload(
    upload_id: str,
    payload: UploadCompleteRequest,
    request: Request,
) -> UploadCompleteRead:
    try:
        return await upload_service_from(request).complete(upload_id, payload)
    except KeyError as exc:
        raise missing("Upload") from exc
    except UploadConflictError as exc:
        raise error(409, "UPLOAD_CONFLICT", str(exc)) from exc
    except (MediaValidationError, MediaProbeError) as exc:
        raise error(422, "MEDIA_VALIDATION_FAILED", str(exc)) from exc
    except UnsafeMediaRejected as exc:
        raise error(422, "UNSAFE_MEDIA_REJECTED", str(exc)) from exc
    except MediaScanUnavailable as exc:
        raise error(503, "MEDIA_SCAN_UNAVAILABLE", str(exc)) from exc
    except MediaSecurityError as exc:
        raise error(409, "MEDIA_SECURITY_CHECK_FAILED", str(exc)) from exc


@router.post(
    "/projects/{project_id}/analyze",
    response_model=AutoEditAnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_project(
    project_id: str,
    payload: AutoEditAnalysisRequest,
    request: Request,
) -> AutoEditAnalysisRead:
    try:
        return await analysis_service_from(request).analyze(project_id, payload)
    except KeyError as exc:
        raise missing("Project or asset") from exc
    except ProviderNotConfigured as exc:
        raise error(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_ANALYSIS_REQUEST", str(exc)) from exc


@router.get("/projects/{project_id}/analyses", response_model=list[AutoEditAnalysisRead])
async def list_project_analyses(project_id: str, request: Request) -> list[AutoEditAnalysisRead]:
    try:
        return await analysis_service_from(request).list(project_id)
    except KeyError as exc:
        raise missing("Project") from exc


@router.get(
    "/projects/{project_id}/analyses/{analysis_id}",
    response_model=AutoEditAnalysisRead,
)
async def get_project_analysis(
    project_id: str,
    analysis_id: str,
    request: Request,
) -> AutoEditAnalysisRead:
    result = await analysis_service_from(request).get(analysis_id)
    if result is None or result.project_id != project_id:
        raise missing("Analysis")
    return result
