from __future__ import annotations

import hashlib
import hmac
import json
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

from fastapi import HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator


HumanRole = Literal["viewer", "editor", "reviewer", "owner"]
ROLE_RANK: dict[HumanRole, int] = {
    "viewer": 10,
    "editor": 20,
    "reviewer": 30,
    "owner": 40,
}
_TOKEN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
_WORKSPACE_REF = re.compile(
    r"^(?:\*|wsp_[A-Za-z0-9_-]{4,64}|slug:[a-z0-9][a-z0-9-]{1,62})$"
)
_TOKEN_PREFIX = "vf1"


class HumanTokenRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    token_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$")
    token_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    subject: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@-]{2,159}$")
    display_name: str = Field(min_length=1, max_length=160)
    platform_role: HumanRole | None = None
    workspace_roles: dict[str, HumanRole] = Field(default_factory=dict)
    issued_at: datetime
    not_before: datetime | None = None
    expires_at: datetime
    enabled: bool = True

    @model_validator(mode="after")
    def validate_lifecycle(self) -> "HumanTokenRecord":
        issued_at = _as_utc(self.issued_at)
        not_before = _as_utc(self.not_before) if self.not_before else issued_at
        expires_at = _as_utc(self.expires_at)
        if not_before < issued_at:
            raise ValueError("not_before cannot precede issued_at")
        if expires_at <= not_before:
            raise ValueError("expires_at must be after not_before")
        if not self.platform_role and not self.workspace_roles:
            raise ValueError("a token must have a platform or workspace role")
        for workspace_ref in self.workspace_roles:
            if not _WORKSPACE_REF.fullmatch(workspace_ref):
                raise ValueError("workspace role keys must be *, wsp_* or slug:<workspace-slug>")
        return self


class HumanAuthRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1]
    tokens: dict[str, HumanTokenRecord] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_token_keys(self) -> "HumanAuthRegistry":
        for token_id, record in self.tokens.items():
            if token_id != record.token_id:
                raise ValueError("token registry key must match token_id")
        return self


@dataclass(frozen=True)
class HumanPrincipal:
    token_id: str
    subject: str
    display_name: str
    platform_role: HumanRole | None
    workspace_roles: Mapping[str, HumanRole]
    expires_at: datetime

    def role_for(self, workspace_id: str, workspace_slug: str | None = None) -> HumanRole | None:
        candidates: list[HumanRole] = []
        if self.platform_role:
            candidates.append(self.platform_role)
        for key in ("*", workspace_id, f"slug:{workspace_slug}" if workspace_slug else None):
            if key and key in self.workspace_roles:
                candidates.append(self.workspace_roles[key])
        return max(candidates, key=ROLE_RANK.__getitem__) if candidates else None

    def has_platform_role(self, required: HumanRole) -> bool:
        return bool(self.platform_role and ROLE_RANK[self.platform_role] >= ROLE_RANK[required])

    def has_any_role(self, required: HumanRole) -> bool:
        roles = list(self.workspace_roles.values())
        if self.platform_role:
            roles.append(self.platform_role)
        return any(ROLE_RANK[role] >= ROLE_RANK[required] for role in roles)


class HumanAuthVerifier:
    def __init__(self, registry: HumanAuthRegistry, *, max_token_ttl_seconds: int):
        self.registry = registry
        self.max_token_ttl_seconds = max_token_ttl_seconds
        for record in registry.tokens.values():
            ttl = (_as_utc(record.expires_at) - _as_utc(record.issued_at)).total_seconds()
            if ttl > max_token_ttl_seconds:
                raise ValueError("human auth token lifetime exceeds configured maximum")

    @classmethod
    def from_file(cls, path: Path, *, max_token_ttl_seconds: int) -> "HumanAuthVerifier":
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            registry = HumanAuthRegistry.model_validate(payload)
        except Exception as exc:
            raise ValueError("human auth registry is missing or invalid") from exc
        return cls(registry, max_token_ttl_seconds=max_token_ttl_seconds)

    def verify(self, authorization: str | None, *, now: datetime | None = None) -> HumanPrincipal:
        if not authorization or not authorization.startswith("Bearer "):
            raise InvalidHumanCredential
        token = authorization.removeprefix("Bearer ").strip()
        parts = token.split(".", 2)
        if len(parts) != 3 or parts[0] != _TOKEN_PREFIX or not _TOKEN_ID.fullmatch(parts[1]):
            raise InvalidHumanCredential
        if len(parts[2]) < 32 or len(token) > 512:
            raise InvalidHumanCredential
        record = self.registry.tokens.get(parts[1])
        supplied_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        expected_digest = record.token_sha256 if record else "0" * 64
        signature_valid = hmac.compare_digest(supplied_digest, expected_digest)
        if record is None or not signature_valid or not record.enabled:
            raise InvalidHumanCredential
        current = _as_utc(now or datetime.now(timezone.utc))
        not_before = _as_utc(record.not_before) if record.not_before else _as_utc(record.issued_at)
        if current < not_before or current >= _as_utc(record.expires_at):
            raise InvalidHumanCredential
        return HumanPrincipal(
            token_id=record.token_id,
            subject=record.subject,
            display_name=record.display_name,
            platform_role=record.platform_role,
            workspace_roles=dict(record.workspace_roles),
            expires_at=_as_utc(record.expires_at),
        )


class InvalidHumanCredential(Exception):
    pass


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


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
    if path.endswith("/publish"):
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
