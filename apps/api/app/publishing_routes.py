from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException, Request, Response, status

from .publishing_logic import PublishingContractError
from .human_auth import authorize_project, principal_from
from .publishing_dispatch import DispatchError
from .publishing_models import (
    PublicationCreateRequest,
    PublicationEventRead,
    PublicationRead,
    PublishApprovalRequest,
    PublishApprovalRevokeRequest,
    PublishScheduleRequest,
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


@router.get('/projects/{project_id}/publishing-profiles')
async def publishing_profiles(project_id: str, request: Request, response: Response):
    await authorize_project(request, project_id, 'viewer')
    response.headers['Cache-Control'] = 'no-store'
    return await service(request).profiles_for_project(project_id)


@router.get('/projects/{project_id}/publications/{publication_id}/publish-review')
async def publish_review(project_id: str, publication_id: str, request: Request, response: Response):
    await authorize_project(request, project_id, 'viewer')
    try:
        value = await service(request).publish_review(project_id, publication_id)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError) as exc:
        raise consent_error(exc) from None


def consent_error(exc):
    if isinstance(exc, KeyError):
        return error(404, 'PUBLICATION_NOT_FOUND', 'Publication was not found.')
    if isinstance(exc, DispatchError):
        code = exc.code
        status_code = 404 if code == 'PUBLISH_SCOPE_NOT_FOUND' else 403 if code == 'HUMAN_OWNER_PUBLISH_APPROVAL_REQUIRED' else 409
        return error(status_code, code, code)
    if isinstance(exc, PublishingPreconditionError):
        return error(409, exc.code, str(exc))
    return error(422, 'INVALID_PUBLISHING_REQUEST', str(exc))


@router.post('/projects/{project_id}/publications/{publication_id}/publish-approval')
async def approve_publish(project_id: str, publication_id: str, payload: PublishApprovalRequest, request: Request,
                          response: Response, idempotency_key: str = Header(alias='Idempotency-Key', min_length=16, max_length=200)):
    await authorize_project(request, project_id, 'owner')
    try:
        value = await service(request).approve_publish(project_id, publication_id, principal=principal_from(request),
            payload=payload, idempotency_key=idempotency_key)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError, PublishingContractError) as exc:
        raise consent_error(exc) from None


@router.post('/projects/{project_id}/publications/{publication_id}/publish-approval/revoke')
async def revoke_publish(project_id: str, publication_id: str, payload: PublishApprovalRevokeRequest, request: Request,
                         response: Response):
    await authorize_project(request, project_id, 'owner')
    try:
        value = await service(request).revoke_publish(project_id, publication_id, principal=principal_from(request),
            publish_approval_id=payload.publish_approval_id)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError) as exc:
        raise consent_error(exc) from None


@router.get('/projects/{project_id}/publications/{publication_id}/dispatch')
async def dispatch_status(project_id: str, publication_id: str, request: Request, response: Response):
    try:
        value = await service(request).dispatch_status(project_id, publication_id)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError) as exc:
        raise consent_error(exc) from None


@router.post('/projects/{project_id}/publications/{publication_id}/publishing-work')
async def schedule_publication(project_id: str, publication_id: str, payload: PublishScheduleRequest,
                               request: Request, response: Response):
    await authorize_project(request, project_id, 'owner')
    try:
        value = await service(request).schedule_publish(project_id, publication_id, principal=principal_from(request),
            publish_approval_id=payload.publish_approval_id)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError) as exc:
        raise consent_error(exc) from None


@router.get('/projects/{project_id}/publications/{publication_id}/publishing-work')
async def publication_work(project_id: str, publication_id: str, request: Request, response: Response):
    try:
        value = await service(request).publishing_work(project_id, publication_id)
        response.headers['Cache-Control'] = 'no-store'
        return value
    except (KeyError, DispatchError, PublishingPreconditionError) as exc:
        raise consent_error(exc) from None
