from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status

from .vision_models import VisionAnalysisRead, VisionAnalysisRequest
from .vision_providers import VisionProviderNotConfigured
from .vision_service import VisionAnalysisService


router = APIRouter(prefix="/api/v1")


def service_from(request: Request) -> VisionAnalysisService:
    return request.app.state.vision_analysis_service


def missing(entity: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={"error": {"code": "NOT_FOUND", "message": f"{entity} not found."}},
    )


def error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message}})


@router.post(
    "/projects/{project_id}/analyses/{analysis_id}/vision",
    response_model=VisionAnalysisRead,
    status_code=status.HTTP_201_CREATED,
)
async def analyze_vision(
    project_id: str,
    analysis_id: str,
    payload: VisionAnalysisRequest,
    request: Request,
) -> VisionAnalysisRead:
    try:
        return await service_from(request).analyze(
            project_id=project_id,
            analysis_id=analysis_id,
            payload=payload,
        )
    except KeyError as exc:
        raise missing("Project, Auto Edit analysis or asset") from exc
    except VisionProviderNotConfigured as exc:
        raise error(503, "PROVIDER_NOT_CONFIGURED", str(exc)) from exc
    except ValueError as exc:
        raise error(422, "INVALID_VISION_REQUEST", str(exc)) from exc


@router.get(
    "/projects/{project_id}/vision-analyses",
    response_model=list[VisionAnalysisRead],
)
async def list_vision_analyses(project_id: str, request: Request) -> list[VisionAnalysisRead]:
    try:
        return await service_from(request).list(project_id)
    except KeyError as exc:
        raise missing("Project") from exc


@router.get(
    "/projects/{project_id}/vision-analyses/{vision_analysis_id}",
    response_model=VisionAnalysisRead,
)
async def get_vision_analysis(
    project_id: str,
    vision_analysis_id: str,
    request: Request,
) -> VisionAnalysisRead:
    result = await service_from(request).get(vision_analysis_id)
    if result is None or result.project_id != project_id:
        raise missing("Vision analysis")
    return result
