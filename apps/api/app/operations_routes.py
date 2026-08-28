from __future__ import annotations

from fastapi import APIRouter, Request

from .operations_observability import OperationsObservabilityService, OperationsSnapshot


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


@router.get("/snapshot", response_model=OperationsSnapshot)
async def operations_snapshot(request: Request) -> OperationsSnapshot:
    service: OperationsObservabilityService = request.app.state.operations_observability
    return await service.snapshot()
