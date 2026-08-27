from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI

from app.human_auth import HumanAuthRegistry, HumanAuthVerifier, HumanRateLimiter


TEST_HUMAN_TOKEN = f"vf1.test-owner.{secrets.token_urlsafe(36)}"
TEST_HUMAN_HEADERS = {"Authorization": f"Bearer {TEST_HUMAN_TOKEN}"}


class MemoryRateStore:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> bool:
        del key, seconds
        return True


def install_test_human_auth(
    app: FastAPI,
    *,
    platform_repository=None,
    platform_role: str | None = "owner",
    workspace_roles: dict[str, str] | None = None,
    requests_per_minute: int = 1_000,
) -> None:
    issued_at = datetime.now(timezone.utc)
    registry = HumanAuthRegistry.model_validate(
        {
            "version": 1,
            "tokens": {
                "test-owner": {
                    "token_id": "test-owner",
                    "token_sha256": hashlib.sha256(TEST_HUMAN_TOKEN.encode("utf-8")).hexdigest(),
                    "subject": "usr:test-owner",
                    "display_name": "Test Owner",
                    "platform_role": platform_role,
                    "workspace_roles": workspace_roles or {"*": "owner"},
                    "issued_at": issued_at.isoformat(),
                    "not_before": issued_at.isoformat(),
                    "expires_at": (issued_at + timedelta(hours=1)).isoformat(),
                    "enabled": True,
                }
            },
        }
    )
    app.state.human_api_enabled = True
    app.state.human_write_enabled = True
    app.state.human_auth_verifier = HumanAuthVerifier(registry, max_token_ttl_seconds=86_400)
    app.state.human_rate_limiter = HumanRateLimiter(
        MemoryRateStore(), requests_per_minute=requests_per_minute
    )
    if platform_repository is not None:
        app.state.platform_repository = platform_repository
