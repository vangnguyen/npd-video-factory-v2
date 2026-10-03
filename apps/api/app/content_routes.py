from fastapi import APIRouter, HTTPException, Request
from .content_models import ContentSaveRequest
from .content_service import ContentConflictError
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
        return await request.app.state.content_service.save(project_id, payload)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "NOT_FOUND"}) from exc
    except ContentConflictError as exc:
        raise HTTPException(409, detail={"code": "CONTENT_VERSION_CONFLICT", "message": str(exc)}) from exc
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "CONTENT_INVALID", "message": str(exc)}) from exc
