from fastapi import APIRouter, HTTPException, Request
from .content_models import ContentSaveRequest, ContentGenerateRequest, ContentApplyRequest
from .content_service import ContentConflictError
from .content_generation import ContentProviderUnavailable
from .human_auth import principal_from
from .platform_models import ProjectVersionRead

router = APIRouter(prefix="/api/v1", tags=["multi-input-content"])

@router.get("/projects/{project_id}/storyboard-media-plan")
async def storyboard_media_plan(project_id: str, request: Request):
    from .media_intelligence_logic import plan_storyboard_media
    version = await request.app.state.content_service.latest(project_id)
    if version is None:
        raise HTTPException(404, detail={"code": "CONTENT_NOT_FOUND"})
    return {"content_version_id": version.project_version_id,
            "items": plan_storyboard_media(version.snapshot["content"]), "external_call": False}

@router.get("/projects/{project_id}/content", response_model=ProjectVersionRead | None)
async def latest_content(project_id: str, request: Request):
    return await request.app.state.content_service.latest(project_id)

@router.put("/projects/{project_id}/content", response_model=ProjectVersionRead)
async def save_content(project_id: str, payload: ContentSaveRequest, request: Request):
    try:
        return await request.app.state.content_service.save(project_id, payload, actor_ref=principal_from(request).subject)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except ContentConflictError as exc:
        raise HTTPException(409, detail={"code": "CONTENT_VERSION_CONFLICT", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "CONTENT_INVALID", "message": str(exc)}) from exc


def generation_from(request):
    return request.app.state.content_generation_service


@router.get("/projects/{project_id}/content-provider")
async def content_provider(project_id: str, request: Request):
    return await generation_from(request).availability()


@router.get("/projects/{project_id}/content-generation")
async def latest_generation(project_id: str, request: Request):
    return await generation_from(request).latest(project_id)


@router.post("/projects/{project_id}/content-generation", status_code=202)
async def generate_content(project_id: str, payload: ContentGenerateRequest, request: Request):
    try:
        return await generation_from(request).create(project_id, payload, actor_ref=principal_from(request).subject)
    except ContentProviderUnavailable as exc:
        raise HTTPException(503, detail={"code": "CONTENT_PROVIDER_NOT_CONFIGURED", "message": str(exc)}) from exc
    except ContentConflictError as exc:
        raise HTTPException(409, detail={"code": "CONTENT_VERSION_CONFLICT", "message": str(exc)}) from exc


@router.get("/projects/{project_id}/content-generation/{generation_id}")
async def get_generation(project_id: str, generation_id: str, request: Request):
    try:
        return await generation_from(request).get(project_id, generation_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc


@router.post("/projects/{project_id}/content-generation/{generation_id}/cancel")
async def cancel_generation(project_id: str, generation_id: str, request: Request):
    try:
        return await generation_from(request).cancel(project_id, generation_id, actor_ref=principal_from(request).subject)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc


@router.post("/projects/{project_id}/content-generation/{generation_id}/apply", response_model=ProjectVersionRead)
async def apply_generation(project_id: str, generation_id: str, payload: ContentApplyRequest, request: Request):
    try:
        return await generation_from(request).apply(project_id, generation_id,
            expected_version=payload.expected_content_version_id, actor_ref=principal_from(request).subject)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except ContentConflictError as exc:
        raise HTTPException(409, detail={"code": "CONTENT_VERSION_CONFLICT", "message": str(exc)}) from exc
