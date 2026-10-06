from __future__ import annotations

import re

from fastapi import APIRouter, Header, HTTPException, Request, status

from .auto_edit_models import (
    AutoEditAnalysisRead,
    AutoEditAnalysisRequest,
    TranscriptEditRequest,
    UploadCompleteRead,
    UploadCompleteRequest,
    UploadInitRequest,
    UploadRead,
)
from .auto_edit_providers import MediaProbeError, ProviderNotConfigured
from .auto_edit_service import AutoEditAnalysisService, UploadConflictError, UploadService, UploadSizeError
from .human_auth import authorize_project
from .transcript_editing import edit_transcript,TranscriptEditConflict
from .media_security import MediaScanUnavailable, MediaSecurityError, UnsafeMediaRejected
from .media_validation import MediaValidationError
from .highlight_drafts import (HighlightDraftRequest,HighlightDraftRead,HighlightDraftApply,
    HighlightDraftConflict,create_drafts,list_drafts,apply_draft)
from .timeline_models import TimelineRead
from .timeline_repository import TimelineConflictError
from .scene_intelligence import (SceneIntelligenceRequest,SceneIntelligenceRead,SceneIntelligenceConflict,
    create_assessment,list_assessments,get_assessment)


router = APIRouter(prefix="/api/v1")
_SHA256 = re.compile(r"^[a-f0-9]{64}$")


@router.get('/projects/{project_id}/scene-intelligence',response_model=list[SceneIntelligenceRead])
async def saved_scene_intelligence(project_id:str,request:Request):
    await authorize_project(request,project_id,'viewer')
    return await list_assessments(analysis_service_from(request).repository,project_id)


@router.get('/projects/{project_id}/scene-intelligence/{assessment_id}',response_model=SceneIntelligenceRead)
async def scene_intelligence_detail(project_id:str,assessment_id:str,request:Request):
    await authorize_project(request,project_id,'viewer')
    try:return await get_assessment(analysis_service_from(request).repository,project_id,assessment_id)
    except KeyError as exc:raise missing('Scene assessment') from exc


@router.post('/projects/{project_id}/scene-intelligence',response_model=SceneIntelligenceRead)
async def assess_scene_intelligence(project_id:str,payload:SceneIntelligenceRequest,request:Request):
    principal=await authorize_project(request,project_id,'editor')
    vision_service=getattr(request.app.state,'vision_analysis_service',None)
    try:return await create_assessment(analysis_service_from(request).repository,getattr(vision_service,'repository',None),
        project_id,payload,principal.subject)
    except KeyError as exc:raise missing('Source analysis/transcript/Vision') from exc
    except SceneIntelligenceConflict as exc:raise error(409,'SCENE_INTELLIGENCE_CONFLICT',str(exc)) from exc


@router.get('/projects/{project_id}/highlight-drafts',response_model=list[HighlightDraftRead])
async def saved_highlight_drafts(project_id:str,request:Request):
    await authorize_project(request,project_id,'viewer')
    return await list_drafts(analysis_service_from(request).repository,project_id)


@router.post('/projects/{project_id}/highlight-drafts',response_model=list[HighlightDraftRead])
async def generate_highlight_drafts(project_id:str,payload:HighlightDraftRequest,request:Request):
    principal=await authorize_project(request,project_id,'editor')
    try:return await create_drafts(analysis_service_from(request).repository,project_id,payload,principal.subject)
    except KeyError as exc:raise missing('Analysis/transcript/asset') from exc
    except (HighlightDraftConflict,ValueError) as exc:raise error(409,'HIGHLIGHT_DRAFT_CONFLICT',str(exc)) from exc


@router.post('/projects/{project_id}/highlight-drafts/{draft_id}/apply',response_model=TimelineRead)
async def apply_highlight_draft(project_id:str,draft_id:str,payload:HighlightDraftApply,request:Request):
    principal=await authorize_project(request,project_id,'editor')
    try:return await apply_draft(analysis_service_from(request).repository,project_id,draft_id,payload,principal.subject)
    except KeyError as exc:raise missing('Highlight draft') from exc
    except (HighlightDraftConflict,TimelineConflictError) as exc:raise error(409,'HIGHLIGHT_DRAFT_CONFLICT',str(exc)) from exc


@router.post('/projects/{project_id}/analyses/{analysis_id}/transcript',response_model=AutoEditAnalysisRead)
async def edit_analysis_transcript(project_id:str,analysis_id:str,payload:TranscriptEditRequest,request:Request):
    principal=await authorize_project(request,project_id,'editor')
    try:
        return await edit_transcript(analysis_service_from(request).repository,project_id,analysis_id,payload,principal.subject)
    except KeyError as exc:raise missing('Analysis') from exc
    except TranscriptEditConflict as exc:raise error(409,'TRANSCRIPT_EDIT_CONFLICT',str(exc)) from exc


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
    transcript_id: str | None = None,
) -> AutoEditAnalysisRead:
    service=analysis_service_from(request)
    result=await service.repository.get_analysis(analysis_id,transcript_id=transcript_id) if transcript_id is not None else await service.get(analysis_id)
    if result is None or result.project_id != project_id:
        raise missing("Analysis")
    return result
