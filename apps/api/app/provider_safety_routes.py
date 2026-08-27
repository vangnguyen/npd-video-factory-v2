from __future__ import annotations

from fastapi import APIRouter, Request

from .provider_safety import ProviderSafetyController, ProviderSafetySnapshot


router = APIRouter(prefix="/api/v1")


@router.get("/provider-safety", response_model=ProviderSafetySnapshot)
async def provider_safety_snapshot(request: Request) -> ProviderSafetySnapshot:
    controller = getattr(request.app.state, "provider_safety_controller", None)
    if not isinstance(controller, ProviderSafetyController):
        controller = ProviderSafetyController.fail_closed()
    return await controller.snapshot()
