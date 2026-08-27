from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.db import Base, create_engine, create_session_factory
from app.human_auth import (
    HumanAuthRegistry,
    HumanAuthVerifier,
    HumanRateLimiter,
    InvalidHumanCredential,
    authorize_human_request,
    principal_from,
)
from app.main import app as production_app
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.platform_routes import router as platform_router
from app.repositories import PlatformRepository
from auth_test_support import MemoryRateStore


class MemoryJobStore:
    def __init__(self, records: dict[str, object]) -> None:
        self.records = records

    async def get(self, job_id: str) -> object | None:
        return self.records.get(job_id)


def token(token_id: str) -> str:
    return f"vf1.{token_id}.{secrets.token_urlsafe(36)}"


def record(
    raw_token: str,
    *,
    token_id: str,
    workspace_roles: dict[str, str] | None = None,
    platform_role: str | None = None,
    enabled: bool = True,
    issued_at: datetime | None = None,
    not_before: datetime | None = None,
    expires_at: datetime | None = None,
) -> dict[str, object]:
    issued = issued_at or datetime.now(timezone.utc) - timedelta(minutes=1)
    return {
        "token_id": token_id,
        "token_sha256": hashlib.sha256(raw_token.encode("utf-8")).hexdigest(),
        "subject": f"usr:{token_id}",
        "display_name": token_id.replace("-", " ").title(),
        "platform_role": platform_role,
        "workspace_roles": workspace_roles or {},
        "issued_at": issued.isoformat(),
        "not_before": (not_before or issued).isoformat(),
        "expires_at": (expires_at or issued + timedelta(hours=1)).isoformat(),
        "enabled": enabled,
    }


def registry(records: dict[str, dict[str, object]]) -> HumanAuthRegistry:
    return HumanAuthRegistry.model_validate({"version": 1, "tokens": records})


def configure_auth(
    app: FastAPI,
    *,
    platform: PlatformRepository,
    records: dict[str, dict[str, object]],
    rate_limit: int = 100,
    writes: bool = True,
) -> None:
    app.state.platform_repository = platform
    app.state.human_api_enabled = True
    app.state.human_write_enabled = writes
    app.state.human_auth_verifier = HumanAuthVerifier(
        registry(records), max_token_ttl_seconds=86_400
    )
    app.state.human_rate_limiter = HumanRateLimiter(
        MemoryRateStore(), requests_per_minute=rate_limit
    )


def auth_app() -> FastAPI:
    result = FastAPI()
    dependency = [Depends(authorize_human_request)]
    result.include_router(platform_router, dependencies=dependency)

    @result.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @result.get("/api/v1/auth/session", dependencies=dependency)
    async def session(request: Request) -> dict[str, object]:
        principal = principal_from(request)
        return {"subject": principal.subject, "workspace_roles": dict(principal.workspace_roles)}

    @result.post(
        "/api/v1/projects/{project_id}/approvals/{approval_id}/decision",
        dependencies=dependency,
    )
    async def decide(project_id: str, approval_id: str) -> dict[str, str]:
        return {"project_id": project_id, "approval_id": approval_id}

    @result.post("/api/v1/projects/{project_id}/publish", dependencies=dependency)
    async def publish(project_id: str) -> dict[str, str]:
        return {"project_id": project_id, "mode": "dry_run"}

    @result.get("/api/v1/video-jobs/{job_id}", dependencies=dependency)
    async def get_job(job_id: str) -> dict[str, str]:
        return {"job_id": job_id}

    @result.get(
        "/api/v1/video-jobs/{job_id}/artifacts/{artifact_name}",
        dependencies=dependency,
    )
    async def get_artifact(job_id: str, artifact_name: str) -> dict[str, str]:
        return {"job_id": job_id, "artifact_name": artifact_name}

    return result


def test_all_human_api_routes_are_protected_and_service_bridge_remains_separate() -> None:
    protected: list[str] = []
    bridge: list[str] = []
    for route in production_app.routes:
        included_router = getattr(route, "original_router", None)
        if included_router is not None:
            calls = {
                dependency.dependency
                for dependency in route.include_context.dependencies
            }
            paths = [candidate.path for candidate in included_router.routes]
        else:
            path = getattr(route, "path", "")
            if not path.startswith("/api/v1/"):
                continue
            calls = {dependency.call for dependency in route.dependant.dependencies}
            paths = [path]
        for path in paths:
            if path.startswith("/api/v1/bridge/"):
                bridge.append(path)
                assert authorize_human_request not in calls
            else:
                protected.append(path)
                assert authorize_human_request in calls, path
    assert protected and bridge


@pytest.mark.asyncio
async def test_authentication_rbac_and_workspace_isolation(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'identity.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    platform = PlatformRepository(create_session_factory(engine))
    workspace_a = await platform.create_workspace(
        WorkspaceCreate(slug="workspace-a", name="Workspace A", owner_ref="owner-a")
    )
    workspace_b = await platform.create_workspace(
        WorkspaceCreate(slug="workspace-b", name="Workspace B", owner_ref="owner-b")
    )
    project_a = await platform.create_project(
        workspace_a.workspace_id, ProjectCreate(slug="project-a", name="Project A")
    )
    project_b = await platform.create_project(
        workspace_b.workspace_id, ProjectCreate(slug="project-b", name="Project B")
    )

    raw = {
        "viewer-a": token("viewer-a"),
        "editor-a": token("editor-a"),
        "reviewer-a": token("reviewer-a"),
        "owner": token("platform-owner"),
    }
    records = {
        "viewer-a": record(
            raw["viewer-a"], token_id="viewer-a", workspace_roles={workspace_a.workspace_id: "viewer"}
        ),
        "editor-a": record(
            raw["editor-a"], token_id="editor-a", workspace_roles={workspace_a.workspace_id: "editor"}
        ),
        "reviewer-a": record(
            raw["reviewer-a"], token_id="reviewer-a", workspace_roles={workspace_a.workspace_id: "reviewer"}
        ),
        "platform-owner": record(raw["owner"], token_id="platform-owner", platform_role="owner"),
    }
    app = auth_app()
    configure_auth(app, platform=platform, records=records)
    app.state.job_store = MemoryJobStore(
        {"vid_workspace_b": SimpleNamespace(workspace_id=workspace_b.workspace_id)}
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/healthz")).status_code == 200
        missing = await client.get("/api/v1/workspaces")
        assert missing.status_code == 401
        assert missing.headers["WWW-Authenticate"] == "Bearer"
        assert (await client.get(f"/api/v1/projects/{project_a.project_id}")).status_code == 401
        assert (await client.get("/api/v1/video-jobs/vid_workspace_b")).status_code == 401
        assert (
            await client.get("/api/v1/video-jobs/vid_workspace_b/artifacts/final.mp4")
        ).status_code == 401
        invalid = await client.get(
            "/api/v1/workspaces", headers={"Authorization": "Bearer vf1.viewer-a.changed-secret-value-that-is-long-enough"}
        )
        assert invalid.status_code == 401

        viewer_headers = {"Authorization": f"Bearer {raw['viewer-a']}"}
        visible = await client.get("/api/v1/workspaces", headers=viewer_headers)
        assert visible.status_code == 200
        assert [item["workspace_id"] for item in visible.json()] == [workspace_a.workspace_id]
        assert (await client.get(f"/api/v1/projects/{project_a.project_id}", headers=viewer_headers)).status_code == 200
        hidden = await client.get(f"/api/v1/projects/{project_b.project_id}", headers=viewer_headers)
        assert hidden.status_code == 404
        hidden_assets = await client.get(
            f"/api/v1/projects/{project_b.project_id}/assets", headers=viewer_headers
        )
        assert hidden_assets.status_code == 404
        assert (
            await client.get("/api/v1/video-jobs/vid_workspace_b", headers=viewer_headers)
        ).status_code == 404
        assert (
            await client.get(
                "/api/v1/video-jobs/vid_workspace_b/artifacts/final.mp4",
                headers=viewer_headers,
            )
        ).status_code == 404
        denied_write = await client.post(
            f"/api/v1/workspaces/{workspace_a.workspace_id}/projects",
            headers=viewer_headers,
            json={"slug": "viewer-write", "name": "Viewer write"},
        )
        assert denied_write.status_code == 403

        editor_headers = {"Authorization": f"Bearer {raw['editor-a']}"}
        allowed_write = await client.post(
            f"/api/v1/workspaces/{workspace_a.workspace_id}/projects",
            headers=editor_headers,
            json={"slug": "editor-write", "name": "Editor write"},
        )
        assert allowed_write.status_code == 201
        create_workspace = await client.post(
            "/api/v1/workspaces",
            headers=editor_headers,
            json={"slug": "forbidden-workspace", "name": "Forbidden", "owner_ref": "editor"},
        )
        assert create_workspace.status_code == 403
        editor_approval = await client.post(
            f"/api/v1/projects/{project_a.project_id}/approvals/apr_fixture/decision",
            headers=editor_headers,
        )
        assert editor_approval.status_code == 403

        reviewer_headers = {"Authorization": f"Bearer {raw['reviewer-a']}"}
        reviewer_approval = await client.post(
            f"/api/v1/projects/{project_a.project_id}/approvals/apr_fixture/decision",
            headers=reviewer_headers,
        )
        assert reviewer_approval.status_code == 200
        reviewer_publish = await client.post(
            f"/api/v1/projects/{project_a.project_id}/publish", headers=reviewer_headers
        )
        assert reviewer_publish.status_code == 403

        owner_headers = {"Authorization": f"Bearer {raw['owner']}"}
        assert (
            await client.post(f"/api/v1/projects/{project_b.project_id}/publish", headers=owner_headers)
        ).status_code == 200
        session = await client.get("/api/v1/auth/session", headers=owner_headers)
        assert session.status_code == 200 and session.json()["subject"] == "usr:platform-owner"
        assert "token" not in json.dumps(session.json()).lower()
    await engine.dispose()


def test_token_lifecycle_rotation_and_secret_safe_failure(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    active = token("active-key")
    revoked = token("revoked-key")
    expired = token("expired-key")
    verifier = HumanAuthVerifier(
        registry(
            {
                "active-key": record(active, token_id="active-key", platform_role="owner"),
                "revoked-key": record(
                    revoked, token_id="revoked-key", platform_role="owner", enabled=False
                ),
                "expired-key": record(
                    expired,
                    token_id="expired-key",
                    platform_role="owner",
                    issued_at=now - timedelta(hours=2),
                    expires_at=now - timedelta(hours=1),
                ),
            }
        ),
        max_token_ttl_seconds=86_400,
    )
    assert verifier.verify(f"Bearer {active}", now=now).subject == "usr:active-key"
    for value in (None, f"Bearer {active}x", f"Bearer {revoked}", f"Bearer {expired}"):
        with pytest.raises(InvalidHumanCredential):
            verifier.verify(value, now=now)

    with pytest.raises(ValueError, match="workspace role keys"):
        registry(
            {
                "invalid-ref": record(
                    token("invalid-ref"),
                    token_id="invalid-ref",
                    workspace_roles={"slug:INVALID": "owner"},
                )
            }
        )

    bad = tmp_path / "registry.json"
    bad.write_text('{"version":1,"tokens":{"leaked":"plaintext-secret"}}', encoding="utf-8")
    with pytest.raises(ValueError) as failure:
        HumanAuthVerifier.from_file(bad, max_token_ttl_seconds=86_400)
    assert "plaintext-secret" not in str(failure.value)


@pytest.mark.asyncio
async def test_rate_limit_and_emergency_write_switch(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'rate-limit.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    platform = PlatformRepository(create_session_factory(engine))
    workspace = await platform.create_workspace(
        WorkspaceCreate(slug="rate-limit", name="Rate limit", owner_ref="owner")
    )
    raw = token("rate-owner")
    records = {"rate-owner": record(raw, token_id="rate-owner", platform_role="owner")}
    app = auth_app()
    configure_auth(app, platform=platform, records=records, rate_limit=2)
    headers = {"Authorization": f"Bearer {raw}"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/v1/workspaces", headers=headers)).status_code == 200
        assert (
            await client.get(f"/api/v1/workspaces/{workspace.workspace_id}", headers=headers)
        ).status_code == 200
        limited = await client.get("/api/v1/workspaces", headers=headers)
        assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1

    configure_auth(app, platform=platform, records=records, writes=False)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        blocked = await client.post(
            f"/api/v1/workspaces/{workspace.workspace_id}/projects",
            headers=headers,
            json={"slug": "blocked-write", "name": "Blocked write"},
        )
        assert blocked.status_code == 503
        assert blocked.json()["detail"]["error"]["code"] == "HUMAN_WRITES_DISABLED"
    await engine.dispose()
