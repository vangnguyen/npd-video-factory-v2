from __future__ import annotations

import time
from typing import Protocol

from fastapi import HTTPException, Request, status

# Preserve existing public import names while sharing the provider-free verifier.
from .human_identity import (
    HumanAuthRegistry, HumanAuthVerifier, HumanPrincipal, HumanRole, HumanTokenRecord,
    InvalidHumanCredential, ROLE_RANK, _as_utc,
)


class RateLimitStore(Protocol):
    async def incr(self, key: str) -> int: ...

    async def expire(self, key: str, seconds: int) -> object: ...


class HumanRateLimiter:
    def __init__(self, store: RateLimitStore, *, requests_per_minute: int):
        self.store = store
        self.requests_per_minute = requests_per_minute

    async def check(self, token_id: str, *, now_seconds: float | None = None) -> None:
        now = now_seconds if now_seconds is not None else time.time()
        bucket = int(now // 60)
        key = f"npd:video-factory:v3:human-rate:{token_id}:{bucket}"
        count = int(await self.store.incr(key))
        if count == 1:
            await self.store.expire(key, 120)
        if count > self.requests_per_minute:
            retry_after = max(1, 60 - int(now % 60))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
                detail={"error": {"code": "RATE_LIMITED", "message": "Request rate limit exceeded."}},
            )


def _error(status_code: int, code: str, message: str, *, authenticate: bool = False) -> HTTPException:
    headers = {"WWW-Authenticate": "Bearer"} if authenticate else None
    return HTTPException(
        status_code=status_code,
        headers=headers,
        detail={"error": {"code": code, "message": message}},
    )


def principal_from(request: Request) -> HumanPrincipal:
    principal = getattr(request.state, "human_principal", None)
    if not isinstance(principal, HumanPrincipal):
        raise _error(503, "AUTH_UNAVAILABLE", "Human authentication is unavailable.")
    return principal


async def authenticate_human_request(request: Request) -> HumanPrincipal:
    if not getattr(request.app.state, "human_api_enabled", False):
        raise _error(503, "HUMAN_API_DISABLED", "Human API access is disabled by the emergency switch.")
    verifier = getattr(request.app.state, "human_auth_verifier", None)
    limiter = getattr(request.app.state, "human_rate_limiter", None)
    if not isinstance(verifier, HumanAuthVerifier) or not isinstance(limiter, HumanRateLimiter):
        raise _error(503, "AUTH_UNAVAILABLE", "Human authentication is unavailable.")
    try:
        principal = verifier.verify(request.headers.get("Authorization"))
    except InvalidHumanCredential as exc:
        raise _error(401, "AUTHENTICATION_REQUIRED", "A valid human session token is required.", authenticate=True) from exc
    try:
        await limiter.check(principal.token_id)
    except HTTPException:
        raise
    except Exception as exc:
        raise _error(503, "AUTH_UNAVAILABLE", "Human authentication is unavailable.") from exc
    request.state.human_principal = principal
    return principal


def required_role_for(request: Request) -> HumanRole:
    path = request.url.path
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return "viewer"
    if path == "/api/v1/workspaces" and request.method == "POST":
        return "owner"
    if "/approvals/" in path and path.endswith("/decision"):
        return "reviewer"
    if path.endswith(("/publish", "/publish-approval", "/publish-approval/revoke", "/publishing-work")):
        return "owner"
    return "editor"


async def authorize_human_request(request: Request) -> HumanPrincipal:
    principal = await authenticate_human_request(request)
    required = required_role_for(request)
    if request.method not in {"GET", "HEAD", "OPTIONS"} and not getattr(
        request.app.state, "human_write_enabled", False
    ):
        raise _error(503, "HUMAN_WRITES_DISABLED", "Human API writes are disabled by the emergency switch.")

    params = request.path_params
    workspace = None
    platform = getattr(request.app.state, "platform_repository", None)
    if "workspace_id" in params:
        workspace = await platform.get_workspace(params["workspace_id"]) if platform else None
    elif "project_id" in params:
        project = await platform.get_project(params["project_id"]) if platform else None
        workspace = await platform.get_workspace(project.workspace_id) if platform and project else None
    elif "job_id" in params:
        store = getattr(request.app.state, "job_store", None)
        job = await store.get(params["job_id"]) if store else None
        workspace = await platform.get_workspace(job.workspace_id) if platform and job and job.workspace_id else None
    elif "upload_id" in params:
        service = getattr(request.app.state, "upload_service", None)
        upload = await service.get(params["upload_id"]) if service else None
        workspace = await platform.get_workspace(upload.workspace_id) if platform and upload else None
    elif "cluster_id" in params:
        service = getattr(request.app.state, "trend_intelligence_service", None)
        cluster = await service.get_cluster(params["cluster_id"]) if service else None
        workspace = await platform.get_workspace(cluster.workspace_id) if platform and cluster else None
    elif "idea_id" in params:
        repository = getattr(request.app.state, "trend_repository", None)
        idea = await repository.get_idea(params["idea_id"]) if repository else None
        workspace = await platform.get_workspace(idea.workspace_id) if platform and idea else None

    has_scoped_identifier = any(
        key in params for key in ("workspace_id", "project_id", "job_id", "upload_id", "cluster_id", "idea_id")
    )
    if has_scoped_identifier and workspace is None:
        raise _error(404, "NOT_FOUND", "Resource not found.")
    if workspace is not None:
        role = principal.role_for(workspace.workspace_id, workspace.slug)
        if role is None:
            # Cross-workspace denials deliberately look identical to missing objects.
            raise _error(404, "NOT_FOUND", "Resource not found.")
        if ROLE_RANK[role] < ROLE_RANK[required]:
            raise _error(403, "FORBIDDEN", f"The {required} role is required.")
        return principal

    if request.url.path == "/api/v1/workspaces" and request.method == "POST":
        if not principal.has_platform_role("owner"):
            raise _error(403, "FORBIDDEN", "Platform owner role is required.")
    elif not principal.has_any_role(required):
        raise _error(403, "FORBIDDEN", f"The {required} role is required.")
    return principal


async def authorize_workspace(
    request: Request,
    workspace_id: str,
    required: HumanRole,
) -> HumanPrincipal:
    principal = principal_from(request)
    platform = getattr(request.app.state, "platform_repository", None)
    workspace = await platform.get_workspace(workspace_id) if platform else None
    if workspace is None:
        raise _error(404, "NOT_FOUND", "Resource not found.")
    role = principal.role_for(workspace.workspace_id, workspace.slug)
    if role is None:
        raise _error(404, "NOT_FOUND", "Resource not found.")
    if ROLE_RANK[role] < ROLE_RANK[required]:
        raise _error(403, "FORBIDDEN", f"The {required} role is required.")
    return principal


async def authorize_project(request: Request, project_id: str, required: HumanRole) -> HumanPrincipal:
    platform = getattr(request.app.state, "platform_repository", None)
    project = await platform.get_project(project_id) if platform else None
    if project is None:
        raise _error(404, "NOT_FOUND", "Resource not found.")
    return await authorize_workspace(request, project.workspace_id, required)
