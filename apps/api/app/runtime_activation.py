"""Strict host activation binding for one governed provider operation.

The binding is deployment state.  It is deliberately separate from both the
immutable PostgreSQL custody receipt and Owner provider authority.  Loading it
never mutates PostgreSQL and never grants provider authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


CANONICAL_RUNTIME_ROLE = "vf_executor_runtime"
CANONICAL_OS_PEER_USER = "vf-executor"
CANONICAL_PEER_MAP = "vf_executor_runtime_map"
CANONICAL_DATABASE = "vf_provider_custody_v3_01"
CANONICAL_SOCKET_DIRECTORY = "/run/npd-video-factory/provider-custody/postgresql"
CANONICAL_PORT = 55432


class RuntimeActivationBlocked(RuntimeError):
    """Fixed code-only failure safe for wrapper output."""


class RuntimeActivationBinding(BaseModel):
    """Root-owned, time-bounded PostgreSQL runtime activation state."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1]
    mode: Literal["RUNTIME_ACTIVATION"]
    authority_granted: Literal[False]
    custody_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_role: Literal["vf_executor_runtime"]
    execution_plane_promotion_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    executor_executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    operation_id: str = Field(min_length=1, max_length=200)
    authority_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    o2_activation_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    o2_valid_from_utc: datetime
    o2_expires_at_utc: datetime
    activated_at_utc: datetime
    expires_at_utc: datetime
    expected_live_role_state: Literal["LOGIN"]
    expected_post_execution_state: Literal["NOLOGIN"]
    peer_map_name: Literal["vf_executor_runtime_map"]
    os_peer_user: Literal["vf-executor"]
    database_role: Literal["vf_executor_runtime"]
    database_name: Literal["vf_provider_custody_v3_01"]
    socket_directory: Literal[
        "/run/npd-video-factory/provider-custody/postgresql"
    ]
    port: Literal[55432]
    activation_receipt_version: int = Field(ge=1, le=1)

    @model_validator(mode="after")
    def exact_window(self) -> "RuntimeActivationBinding":
        times = (
            self.o2_valid_from_utc,
            self.o2_expires_at_utc,
            self.activated_at_utc,
            self.expires_at_utc,
        )
        if any(value.tzinfo is None for value in times):
            raise ValueError("RUNTIME_ACTIVATION_TIMEZONE_REQUIRED")
        values = tuple(value.astimezone(timezone.utc) for value in times)
        valid_from, o2_expires, activated, expires = values
        if not valid_from < o2_expires or expires != o2_expires:
            raise ValueError("RUNTIME_ACTIVATION_WINDOW_MISMATCH")
        if activated >= expires:
            raise ValueError("RUNTIME_ACTIVATION_EXPIRED_AT_CREATION")
        return self


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def load_runtime_activation_binding(
    path: Path,
    expected_sha256: str,
) -> RuntimeActivationBinding:
    if re.fullmatch(r"[a-f0-9]{64}", expected_sha256) is None:
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_HASH_INVALID")
    try:
        raw = path.read_bytes()
    except OSError:
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_UNAVAILABLE") from None
    if _sha256(raw) != expected_sha256:
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_HASH_MISMATCH")
    try:
        return RuntimeActivationBinding.model_validate_json(raw)
    except (ValueError, ValidationError):
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_INVALID") from None


def verify_runtime_activation(
    binding: RuntimeActivationBinding,
    *,
    now: datetime,
    custody_binding_sha256: str,
    execution_plane_promotion_sha256: str,
    source_commit: str,
    executor_executable_tree_sha256: str,
    operation_id: str,
    authority_receipt_sha256: str,
    final_bundle_sha256: str,
    execution_scope_sha256: str,
    require_active_window: bool = True,
) -> None:
    expected = {
        "custody_binding_sha256": custody_binding_sha256,
        "execution_plane_promotion_sha256": execution_plane_promotion_sha256,
        "source_commit": source_commit,
        "executor_executable_tree_sha256": executor_executable_tree_sha256,
        "operation_id": operation_id,
        "authority_receipt_sha256": authority_receipt_sha256,
        "final_bundle_sha256": final_bundle_sha256,
        "execution_scope_sha256": execution_scope_sha256,
    }
    if any(getattr(binding, name) != value for name, value in expected.items()):
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_BINDING_MISMATCH")
    current = now.astimezone(timezone.utc)
    valid_from = binding.o2_valid_from_utc.astimezone(timezone.utc)
    expires = binding.expires_at_utc.astimezone(timezone.utc)
    if require_active_window and not valid_from <= current < expires:
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_OUTSIDE_WINDOW")
    if not require_active_window and current >= expires:
        raise RuntimeActivationBlocked("RUNTIME_ACTIVATION_EXPIRED")
