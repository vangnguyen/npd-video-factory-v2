"""One-shot AF_UNIX client/server for the host systemd credential resolver.

Only the root service opens the systemd credentials directory.  The executor
can request the single canonical alias only when every live execution binding
matches root-owned policy.  Secret bytes are returned in memory and are never
included in JSON, logs, evidence, argv, or environment variables.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import struct
from typing import Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .runtime_activation import (
    RuntimeActivationBinding,
    load_runtime_activation_binding,
)
from .provider_credentials import (
    provider_credential_binding,
    verify_provider_credential_binding,
)


CANONICAL_ALIAS = "secret://openai/codex-video"
SYSTEMD_CREDENTIAL_ID = "openai-codex-video"
CANONICAL_SOCKET = Path("/run/npd-video-factory/provider-secret-resolver.sock")
CANONICAL_POLICY = Path("/etc/npd-video-factory/provider-secret-resolver-policy.json")
MAX_REQUEST_BYTES = 4096
MAX_SECRET_BYTES = 8192


class ResolverBlocked(RuntimeError):
    """Fixed code-only failure safe for service and workflow output."""


class ResolverRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1, 2]
    provider_key: Literal["openai-transcription", "assemblyai-transcription"] = "openai-transcription"
    credential_alias: Literal[
        "secret://openai/codex-video",
        "secret://assemblyai/stt-video-factory-benchmark",
    ]
    operation_id: str = Field(min_length=1, max_length=200)
    authority_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_plane_promotion_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    o2_activation_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def provider_alias(self) -> "ResolverRequest":
        try:
            verify_provider_credential_binding(
                provider_key=self.provider_key,
                credential_alias=self.credential_alias,
            )
        except ValueError:
            raise ValueError("RESOLVER_REQUEST_PROVIDER_CREDENTIAL_MISMATCH") from None
        if self.provider_key == "assemblyai-transcription" and self.version != 2:
            raise ValueError("ASSEMBLYAI_RESOLVER_REQUEST_VERSION_INVALID")
        return self


class ResolverPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1, 2]
    mode: Literal["ONE_SHOT_PROVIDER_SECRET_RESOLUTION"]
    provider_key: Literal["openai-transcription", "assemblyai-transcription"] = "openai-transcription"
    credential_alias: Literal[
        "secret://openai/codex-video",
        "secret://assemblyai/stt-video-factory-benchmark",
    ]
    systemd_credential_id: Literal[
        "openai-codex-video",
        "assemblyai-stt-video-factory-benchmark",
    ]
    socket_path: Literal["/run/npd-video-factory/provider-secret-resolver.sock"]
    expected_peer_uid: int = Field(ge=1)
    expected_peer_gid: int = Field(ge=1)
    operation_id: str = Field(min_length=1, max_length=200)
    authority_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_plane_promotion_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    o2_activation_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    runtime_activation_binding: str = Field(pattern=r"^/.*")
    runtime_activation_binding_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    spent_marker_directory: str = Field(pattern=r"^/.*")
    valid_from_utc: datetime
    expires_at_utc: datetime
    max_resolutions: Literal[1]
    authority_granted: Literal[False]

    @model_validator(mode="after")
    def window(self) -> "ResolverPolicy":
        try:
            verify_provider_credential_binding(
                provider_key=self.provider_key,
                credential_alias=self.credential_alias,
                systemd_credential_id=self.systemd_credential_id,
            )
        except ValueError:
            raise ValueError("RESOLVER_PROVIDER_CREDENTIAL_BINDING_INVALID") from None
        if self.provider_key == "assemblyai-transcription" and self.version != 2:
            raise ValueError("ASSEMBLYAI_RESOLVER_POLICY_VERSION_INVALID")
        if self.valid_from_utc.tzinfo is None or self.expires_at_utc.tzinfo is None:
            raise ValueError("RESOLVER_TIMEZONE_REQUIRED")
        if self.valid_from_utc >= self.expires_at_utc:
            raise ValueError("RESOLVER_WINDOW_INVALID")
        return self


_REQUEST_FIELDS = (
    "provider_key",
    "credential_alias",
    "operation_id",
    "authority_receipt_sha256",
    "final_bundle_sha256",
    "execution_scope_sha256",
    "execution_plane_promotion_sha256",
    "o2_activation_receipt_sha256",
)


def _load_policy(path: Path = CANONICAL_POLICY) -> ResolverPolicy:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise ResolverBlocked("RESOLVER_POLICY_CUSTODY_INVALID")
        return ResolverPolicy.model_validate_json(path.read_bytes())
    except ResolverBlocked:
        raise
    except (OSError, ValueError, ValidationError):
        raise ResolverBlocked("RESOLVER_POLICY_INVALID") from None


def _verify_root_artifact(path: Path, code: str) -> None:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & 0o022
        ):
            raise ResolverBlocked(code)
    except ResolverBlocked:
        raise
    except OSError:
        raise ResolverBlocked(code) from None


def _peer_credentials(connection: socket.socket) -> tuple[int, int, int]:
    try:
        return struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    except (OSError, struct.error):
        raise ResolverBlocked("RESOLVER_PEER_CREDENTIALS_UNAVAILABLE") from None


def _read_request(connection: socket.socket) -> ResolverRequest:
    raw = bytearray()
    while len(raw) <= MAX_REQUEST_BYTES:
        chunk = connection.recv(min(1024, MAX_REQUEST_BYTES + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
        if raw.endswith(b"\n"):
            break
    if not raw.endswith(b"\n") or len(raw) > MAX_REQUEST_BYTES or b"\n" in raw[:-1]:
        raise ResolverBlocked("RESOLVER_REQUEST_MALFORMED")
    try:
        return ResolverRequest.model_validate_json(bytes(raw[:-1]))
    except (ValueError, ValidationError):
        raise ResolverBlocked("RESOLVER_REQUEST_MALFORMED") from None


def _validate_context(
    request: ResolverRequest,
    policy: ResolverPolicy,
    activation: RuntimeActivationBinding,
    *,
    now: datetime,
) -> None:
    if any(getattr(request, field) != getattr(policy, field) for field in _REQUEST_FIELDS):
        raise ResolverBlocked("RESOLVER_CONTEXT_MISMATCH")
    if any(getattr(request, field) != getattr(activation, field) for field in _REQUEST_FIELDS[2:]):
        raise ResolverBlocked("RESOLVER_ACTIVATION_MISMATCH")
    current = now.astimezone(timezone.utc)
    policy_start = policy.valid_from_utc.astimezone(timezone.utc)
    policy_end = policy.expires_at_utc.astimezone(timezone.utc)
    if (
        policy_start != activation.o2_valid_from_utc.astimezone(timezone.utc)
        or policy_end != activation.expires_at_utc.astimezone(timezone.utc)
        or not policy_start <= current < policy_end
    ):
        raise ResolverBlocked("RESOLVER_WINDOW_INACTIVE")


def _verify_spent_marker_root(marker_root: Path) -> None:
    try:
        root_info = marker_root.lstat()
        if (
            stat.S_ISLNK(root_info.st_mode)
            or not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_uid != 0
            or stat.S_IMODE(root_info.st_mode) & 0o077
        ):
            raise ResolverBlocked("RESOLVER_SPENT_MARKER_CUSTODY_INVALID")
    except ResolverBlocked:
        raise
    except OSError:
        raise ResolverBlocked("RESOLVER_SPENT_MARKER_CUSTODY_INVALID") from None


def _claim_once(policy: ResolverPolicy, request: ResolverRequest) -> Path:
    marker_root = Path(policy.spent_marker_directory)
    _verify_spent_marker_root(marker_root)
    context = request.model_dump_json().encode("utf-8")
    marker = marker_root / (hashlib.sha256(context).hexdigest() + ".spent")
    try:
        descriptor = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        os.write(descriptor, b"SPENT\n")
        os.fsync(descriptor)
        os.close(descriptor)
    except FileExistsError:
        raise ResolverBlocked("RESOLVER_ALREADY_USED") from None
    except OSError:
        raise ResolverBlocked("RESOLVER_SPENT_MARKER_FAILED") from None
    return marker


def serve_connection(
    connection: socket.socket,
    *,
    policy: ResolverPolicy,
    credential_loader: Callable[[], bytes],
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> str:
    """Serve one request.  Return only a fixed audit code, never secret data."""
    _, uid, gid = _peer_credentials(connection)
    if (uid, gid) != (policy.expected_peer_uid, policy.expected_peer_gid):
        raise ResolverBlocked("RESOLVER_PEER_REJECTED")
    request = _read_request(connection)
    activation_path = Path(policy.runtime_activation_binding)
    _verify_root_artifact(activation_path, "RESOLVER_ACTIVATION_CUSTODY_INVALID")
    activation = load_runtime_activation_binding(
        activation_path,
        policy.runtime_activation_binding_sha256,
    )
    _validate_context(request, policy, activation, now=now())
    _claim_once(policy, request)
    secret = credential_loader()
    if not isinstance(secret, bytes) or not 0 < len(secret) <= MAX_SECRET_BYTES or b"\x00" in secret:
        raise ResolverBlocked("RESOLVER_CREDENTIAL_INVALID")
    connection.sendall(struct.pack("!I", len(secret)) + secret)
    return "RESOLVER_HANDOFF_COMPLETE"


def _verify_socket(path: Path, expected_gid: int) -> None:
    if path != CANONICAL_SOCKET or not path.is_absolute() or path.is_symlink():
        raise ResolverBlocked("RESOLVER_SOCKET_PATH_INVALID")
    try:
        info = path.stat()
        parent = path.parent.stat()
    except OSError:
        raise ResolverBlocked("RESOLVER_UNAVAILABLE") from None
    if (
        not stat.S_ISSOCK(info.st_mode)
        or info.st_uid != 0
        or info.st_gid != expected_gid
        or stat.S_IMODE(info.st_mode) & 0o007
        or parent.st_uid != 0
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        raise ResolverBlocked("RESOLVER_SOCKET_CUSTODY_INVALID")


class SecretResolverClient:
    """Single-use client; successful handoff is exactly one credential read."""

    def __init__(self, policy: ResolverPolicy, request: ResolverRequest) -> None:
        self.policy = policy
        self.request = request
        self.reads: int | None = 0

    def resolve(self, alias: str) -> str:
        try:
            verify_provider_credential_binding(
                provider_key=self.request.provider_key,
                credential_alias=alias,
                systemd_credential_id=self.policy.systemd_credential_id,
            )
        except ValueError:
            raise ResolverBlocked("RESOLVER_ALIAS_OR_REENTRY_REJECTED") from None
        if alias != self.request.credential_alias or self.reads != 0:
            raise ResolverBlocked("RESOLVER_ALIAS_OR_REENTRY_REJECTED")
        _verify_socket(Path(self.policy.socket_path), self.policy.expected_peer_gid)
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(10)
            client.connect(self.policy.socket_path)
            _, server_uid, _ = _peer_credentials(client)
            if server_uid != 0:
                raise ResolverBlocked("RESOLVER_SERVER_PEER_REJECTED")
            raw = self.request.model_dump_json().encode("utf-8") + b"\n"
            if len(raw) > MAX_REQUEST_BYTES:
                raise ResolverBlocked("RESOLVER_REQUEST_MALFORMED")
            client.sendall(raw)
            # From this point a lost response cannot prove whether the root
            # service loaded the credential. Preserve UNKNOWN, never false 0.
            self.reads = None
            header = _recv_exact(client, 4)
            size = struct.unpack("!I", header)[0]
            if not 0 < size <= MAX_SECRET_BYTES:
                raise ResolverBlocked("RESOLVER_RESPONSE_INVALID")
            secret = _recv_exact(client, size)
        try:
            value = secret.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise ResolverBlocked("RESOLVER_RESPONSE_INVALID") from None
        if not value:
            raise ResolverBlocked("RESOLVER_RESPONSE_INVALID")
        self.reads = 1
        return value


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    value = bytearray()
    while len(value) < size:
        chunk = connection.recv(size - len(value))
        if not chunk:
            raise ResolverBlocked("RESOLVER_RESPONSE_TRUNCATED")
        value.extend(chunk)
    return bytes(value)


def systemd_credential_loader(policy: ResolverPolicy | None = None) -> bytes:
    directory = os.environ.get("CREDENTIALS_DIRECTORY")
    if not directory:
        raise ResolverBlocked("SYSTEMD_CREDENTIAL_DIRECTORY_MISSING")
    credential_id = (
        SYSTEMD_CREDENTIAL_ID
        if policy is None
        else provider_credential_binding(policy.provider_key).systemd_credential_id
    )
    path = Path(directory) / credential_id
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o077:
            raise ResolverBlocked("SYSTEMD_CREDENTIAL_CUSTODY_INVALID")
        return path.read_bytes()
    except ResolverBlocked:
        raise
    except OSError:
        raise ResolverBlocked("SYSTEMD_CREDENTIAL_UNAVAILABLE") from None


def service_main() -> int:
    """systemd socket-activation entrypoint; failures reveal only fixed codes."""
    try:
        policy = _load_policy()
        listen_pid = int(os.environ.get("LISTEN_PID", "0"))
        listen_fds = int(os.environ.get("LISTEN_FDS", "0"))
        if listen_pid != os.getpid() or listen_fds != 1:
            raise ResolverBlocked("RESOLVER_SOCKET_ACTIVATION_INVALID")
        listener = socket.socket(fileno=3)
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(5)
            serve_connection(
                connection,
                policy=policy,
                credential_loader=lambda: systemd_credential_loader(policy),
            )
        return 0
    except ResolverBlocked as exc:
        print(str(exc))
        return 2
    except Exception:
        print("RESOLVER_INTERNAL_FAILURE")
        return 2


if __name__ == "__main__":
    raise SystemExit(service_main())
