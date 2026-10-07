"""Provider-free human identity contract shared by Video Factory runtimes."""
from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
