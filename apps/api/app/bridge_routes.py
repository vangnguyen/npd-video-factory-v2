from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from .bridge_auth import CONTRACT_VERSION_HEADER, ServiceAuthError, VerifiedService
from .bridge_models import (
    BRIDGE_CONTRACT_VERSION,
    BridgeContractRead,
    BridgeEventRead,
    BridgeProjectCreatedResponse,
    BridgeProjectRequestCreate,
    BridgeProjectRequestRead,
    BridgeProjectSummary,
    WebhookDeliveryRead,
)
from .bridge_repository import BridgeIdempotencyConflict
from .bridge_service import AgentHubBridgeService, BridgeBoundaryError


router = APIRouter(prefix="/api/v1/bridge", tags=["Agent Hub bridge"])


def bridge_from(request: Request) -> AgentHubBridgeService:
    service = getattr(request.app.state, "agent_hub_bridge_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "BRIDGE_DISABLED", "message": "Agent Hub bridge is disabled."}},
        )
    return service


async def require_service(request: Request) -> VerifiedService:
    verifier = getattr(request.app.state, "bridge_auth_verifier", None)
    if verifier is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": {"code": "BRIDGE_DISABLED", "message": "Agent Hub bridge is disabled."}},
        )
    if request.headers.get(CONTRACT_VERSION_HEADER) != BRIDGE_CONTRACT_VERSION:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": {"code": "CONTRACT_VERSION_REQUIRED", "message": "agent-hub-bridge.v1 is required."}},
        )
    try:
        identity = await verifier.verify(
            method=request.method,
            path=request.url.path,
            query=request.url.query,
            body=await request.body(),
            headers=request.headers,
        )
    except ServiceAuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": {"code": exc.code, "message": str(exc)}},
        ) from exc
    if "service" not in identity.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error": {"code": "SERVICE_ROLE_REQUIRED", "message": "The service role is required."}},
        )
    return identity


@router.get("/contract", response_model=BridgeContractRead)
async def get_contract(request: Request, _identity: VerifiedService = Depends(require_service)) -> BridgeContractRead:
    return bridge_from(request).contract()


@router.post("/project-requests", response_model=BridgeProjectCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_project_request(
    payload: BridgeProjectRequestCreate,
    request: Request,
    response: Response,
    identity: VerifiedService = Depends(require_service),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> BridgeProjectCreatedResponse:
    try:
        result = await bridge_from(request).create_draft_project(
            service_id=identity.service_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": {"code": "WORKSPACE_NOT_FOUND", "message": "Workspace not found."}}) from exc
    except BridgeIdempotencyConflict as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "IDEMPOTENCY_CONFLICT", "message": str(exc)}}) from exc
    except BridgeBoundaryError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": exc.code, "message": str(exc)}}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"error": {"code": "PROJECT_CONFLICT", "message": str(exc)}}) from exc
    response.headers["X-Idempotent-Replay"] = str(result.idempotent_replay).lower()
    return result


@router.get("/project-requests/{request_id}", response_model=BridgeProjectRequestRead)
async def get_project_request(
    request_id: str,
    request: Request,
    _identity: VerifiedService = Depends(require_service),
) -> BridgeProjectRequestRead:
    result = await bridge_from(request).repository.get_request(request_id)
    if result is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Bridge request not found."}})
    return result


@router.get("/projects/{project_id}/summary", response_model=BridgeProjectSummary)
async def get_project_summary(
    project_id: str,
    request: Request,
    _identity: VerifiedService = Depends(require_service),
) -> BridgeProjectSummary:
    try:
        return await bridge_from(request).project_summary(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Project not found."}}) from exc


@router.get("/events", response_model=list[BridgeEventRead])
async def list_events(
    request: Request,
    project_id: str | None = None,
    _identity: VerifiedService = Depends(require_service),
) -> list[BridgeEventRead]:
    return await bridge_from(request).repository.list_events(project_id=project_id)


@router.get("/webhook-deliveries", response_model=list[WebhookDeliveryRead])
async def list_deliveries(
    request: Request,
    project_id: str | None = None,
    _identity: VerifiedService = Depends(require_service),
) -> list[WebhookDeliveryRead]:
    return await bridge_from(request).repository.list_deliveries(project_id=project_id)
