from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from .publishing_logic import PublishingContractError
from .publishing_models import (
    PublicationCreateRequest,
    PublicationEventRead,
    PublicationRead,
    PublishingPlatformStateRead,
)
from .publishing_repository import PublicationIdempotencyConflict
from .publishing_service import PublishingBoundaryError, PublishingPreconditionError, PublishingService


router = APIRouter(prefix="/api/v1", tags=["publishing"])


def service(request: Request) -> PublishingService:
    return request.app.state.publishing_service


def error(status_code: int, code: str, message: str, **context: object) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error": {"code": code, "message": message, **context}},
    )


@router.post(
    "/projects/{project_id}/publish",
    response_model=PublicationRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_publication(
    project_id: str,
    payload: PublicationCreateRequest,
    request: Request,
    response: Response,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=200),
) -> PublicationRead:
    try:
        publication, replay = await service(request).create(
            project_id=project_id,
            payload=payload,
            idempotency_key=idempotency_key,
        )
        response.headers["X-Idempotent-Replay"] = "true" if replay else "false"
        return publication
    except KeyError as exc:
        raise error(404, "PUBLISHING_REFERENCE_NOT_FOUND", str(exc.args[0])) from exc
    except PublicationIdempotencyConflict as exc:
        raise error(409, "IDEMPOTENCY_KEY_CONFLICT", str(exc)) from exc
    except PublishingPreconditionError as exc:
        raise error(409, exc.code, str(exc)) from exc
    except PublishingBoundaryError as exc:
        publication = exc.publication
        raise error(
            409,
            publication.failure_code or "PUBLISHING_BLOCKED",
            publication.failure_reason or "Publication validation failed.",
            publication_id=publication.publication_id,
            status=publication.status,
            external_action=publication.external_action,
        ) from exc
    except PublishingContractError as exc:
        raise error(422, "INVALID_PUBLISHING_REQUEST", str(exc)) from exc


@router.get("/projects/{project_id}/publications", response_model=list[PublicationRead])
async def list_publications(project_id: str, request: Request) -> list[PublicationRead]:
    return await service(request).list(project_id)


@router.get("/projects/{project_id}/publications/{publication_id}", response_model=PublicationRead)
async def get_publication(project_id: str, publication_id: str, request: Request) -> PublicationRead:
    publication = await service(request).get(project_id, publication_id)
    if publication is None:
        raise error(404, "PUBLICATION_NOT_FOUND", "Publication was not found.")
    return publication


@router.get(
    "/projects/{project_id}/publication-history",
    response_model=list[PublicationEventRead],
)
async def publication_history(project_id: str, request: Request) -> list[PublicationEventRead]:
    return await service(request).history(project_id)


@router.get("/publishing-platforms", response_model=list[PublishingPlatformStateRead])
async def publishing_platforms(request: Request) -> list[PublishingPlatformStateRead]:
    return service(request).platform_states()
