"""Root-only PostgreSQL LOGIN lifecycle for one RuntimeActivationBinding.

This command has no provider transport and no credential access.  Its target
database, role, socket, peer map, and artifact paths are compile-time fixed so
an untrusted job cannot redirect privileged PostgreSQL or filesystem actions.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess

from .runtime_activation import (
    CANONICAL_DATABASE,
    CANONICAL_PORT,
    CANONICAL_RUNTIME_ROLE,
    CANONICAL_SOCKET_DIRECTORY,
    RuntimeActivationBlocked,
    load_runtime_activation_binding,
)
from .provider_secret_resolver import CANONICAL_POLICY, ResolverPolicy


ACTIVATION_PATH = Path("/etc/npd-video-factory/runtime-activation.json")
ACTIVATION_HASH_PATH = Path("/etc/npd-video-factory/runtime-activation.sha256")
RESOLVER_POLICY_HASH_PATH = Path(
    "/etc/npd-video-factory/provider-secret-resolver-policy.sha256"
)
ACTIVE_STATE_PATH = Path("/run/npd-video-factory/runtime-activation-active.json")
PSQL = "/usr/lib/postgresql/16/bin/psql"
RUNUSER = "/usr/sbin/runuser"
SYSTEMCTL = "/usr/bin/systemctl"
HBA_PATH = Path("/etc/npd-video-factory/provider-custody/postgresql-16/pg_hba.conf")
IDENT_PATH = Path("/etc/npd-video-factory/provider-custody/postgresql-16/pg_ident.conf")
ROOT_UID = 0


class HostActivationBlocked(RuntimeError):
    """Fixed code-only host failure."""


def _root_file(path: Path, *, mode_mask: int = 0o022) -> bytes:
    try:
        info = path.lstat()
        if (
            stat.S_ISLNK(info.st_mode)
            or not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or stat.S_IMODE(info.st_mode) & mode_mask
        ):
            raise HostActivationBlocked("HOST_ACTIVATION_FILE_CUSTODY_INVALID")
        return path.read_bytes()
    except HostActivationBlocked:
        raise
    except OSError:
        raise HostActivationBlocked("HOST_ACTIVATION_FILE_UNAVAILABLE") from None


def _load_current():
    raw_hash = _root_file(ACTIVATION_HASH_PATH).decode("ascii", "strict").strip()
    if re.fullmatch(r"[a-f0-9]{64}", raw_hash) is None:
        raise HostActivationBlocked("RUNTIME_ACTIVATION_HASH_INVALID")
    if hashlib.sha256(_root_file(ACTIVATION_PATH)).hexdigest() != raw_hash:
        raise HostActivationBlocked("RUNTIME_ACTIVATION_HASH_MISMATCH")
    try:
        return load_runtime_activation_binding(ACTIVATION_PATH, raw_hash), raw_hash
    except RuntimeActivationBlocked as exc:
        raise HostActivationBlocked(str(exc)) from None


def _load_resolver_policy(binding, binding_hash: str) -> ResolverPolicy:
    raw = _root_file(CANONICAL_POLICY)
    expected = _root_file(RESOLVER_POLICY_HASH_PATH).decode("ascii", "strict").strip()
    if re.fullmatch(r"[a-f0-9]{64}", expected) is None or hashlib.sha256(raw).hexdigest() != expected:
        raise HostActivationBlocked("RESOLVER_POLICY_HASH_MISMATCH")
    try:
        policy = ResolverPolicy.model_validate_json(raw)
    except Exception:
        raise HostActivationBlocked("RESOLVER_POLICY_INVALID") from None
    exact = {
        "operation_id": binding.operation_id,
        "authority_receipt_sha256": binding.authority_receipt_sha256,
        "final_bundle_sha256": binding.final_bundle_sha256,
        "execution_scope_sha256": binding.execution_scope_sha256,
        "execution_plane_promotion_sha256": binding.execution_plane_promotion_sha256,
        "o2_activation_receipt_sha256": binding.o2_activation_receipt_sha256,
        "runtime_activation_binding": str(ACTIVATION_PATH),
        "runtime_activation_binding_sha256": binding_hash,
        "valid_from_utc": binding.o2_valid_from_utc,
        "expires_at_utc": binding.expires_at_utc,
    }
    if any(getattr(policy, field) != value for field, value in exact.items()):
        raise HostActivationBlocked("RESOLVER_POLICY_BINDING_MISMATCH")
    try:
        peer = pwd.getpwnam(binding.os_peer_user)
    except KeyError:
        raise HostActivationBlocked("RUNTIME_OS_PEER_IDENTITY_MISSING") from None
    if (policy.expected_peer_uid, policy.expected_peer_gid) != (peer.pw_uid, peer.pw_gid):
        raise HostActivationBlocked("RESOLVER_POLICY_PEER_IDENTITY_MISMATCH")
    return policy


def _psql(statement: str) -> str:
    result = subprocess.run(
        [
            RUNUSER, "-u", "postgres", "--", PSQL, "-X", "-v", "ON_ERROR_STOP=1",
            "-h", CANONICAL_SOCKET_DIRECTORY, "-p", str(CANONICAL_PORT),
            "-d", "postgres", "-Atqc", statement,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
        timeout=20,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    if result.returncode:
        raise HostActivationBlocked("RUNTIME_ROLE_POSTGRES_COMMAND_FAILED")
    return result.stdout.strip()


def _login_state() -> str:
    value = _psql(
        "SELECT CASE WHEN rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END "
        "FROM pg_roles WHERE rolname='vf_executor_runtime'"
    )
    if value not in {"LOGIN", "NOLOGIN"}:
        raise HostActivationBlocked("RUNTIME_ROLE_MISSING")
    return value


def _verify_peer_auth() -> None:
    hba = _root_file(HBA_PATH).decode("utf-8", "strict").splitlines()
    ident = _root_file(IDENT_PATH).decode("utf-8", "strict").splitlines()
    hba_line = (
        "local   vf_provider_custody_v3_01   vf_executor_runtime     "
        "peer map=vf_executor_runtime_map"
    )
    ident_line = "vf_executor_runtime_map vf-executor vf_executor_runtime"
    active_hba = [line.strip() for line in hba if line.strip() and not line.lstrip().startswith("#")]
    active_ident = [line.strip() for line in ident if line.strip() and not line.lstrip().startswith("#")]
    if (
        active_hba.count(hba_line) != 1
        or active_ident.count(ident_line) != 1
        or any(re.search(r"(?:^|\s)trust(?:\s|$)", line) for line in active_hba)
        or _psql("SHOW hba_file") != str(HBA_PATH)
        or _psql("SHOW ident_file") != str(IDENT_PATH)
        or _psql("SHOW listen_addresses") != ""
        or _psql("SHOW unix_socket_directories") != CANONICAL_SOCKET_DIRECTORY
        or _psql("SHOW port") != str(CANONICAL_PORT)
    ):
        raise HostActivationBlocked("RUNTIME_PEER_AUTH_CONFIGURATION_INVALID")


def _alter(login: bool) -> None:
    statement = "ALTER ROLE vf_executor_runtime " + ("LOGIN" if login else "NOLOGIN")
    if not login:
        # NOLOGIN stops new sessions; terminate any surviving executor session
        # so a crashed/hung child cannot retain DML access past cleanup/expiry.
        statement += (
            "; SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE usename='vf_executor_runtime' AND pid<>pg_backend_pid()"
        )
    _psql(statement)
    expected = "LOGIN" if login else "NOLOGIN"
    if _login_state() != expected:
        raise HostActivationBlocked("RUNTIME_ROLE_STATE_CHANGE_FAILED")


def _systemctl(action: str, unit: str) -> None:
    if action not in {"start", "stop"} or unit not in {
        "npd-vf-secret-resolver.socket", "npd-vf-secret-resolver.service",
    }:
        raise HostActivationBlocked("RUNTIME_SYSTEMD_ACTION_INVALID")
    result = subprocess.run(
        [SYSTEMCTL, action, unit],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
        timeout=20,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
    )
    if result.returncode:
        raise HostActivationBlocked("RUNTIME_RESOLVER_SOCKET_STATE_FAILED")


def _persist_active(binding_hash: str, expires_at: str) -> None:
    payload = json.dumps(
        {
            "version": 1,
            "runtime_activation_sha256": binding_hash,
            "runtime_role": CANONICAL_RUNTIME_ROLE,
            "state": "LOGIN",
            "expires_at_utc": expires_at,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode() + b"\n"
    try:
        parent = ACTIVE_STATE_PATH.parent.lstat()
        postgres_gid = grp.getgrnam("postgres").gr_gid
    except (KeyError, OSError):
        raise HostActivationBlocked("RUNTIME_ACTIVATION_MARKER_CUSTODY_INVALID") from None
    if (
        not stat.S_ISDIR(parent.st_mode)
        or stat.S_ISLNK(parent.st_mode)
        or parent.st_uid != ROOT_UID
        or stat.S_IMODE(parent.st_mode) & 0o022
    ):
        raise HostActivationBlocked("RUNTIME_ACTIVATION_MARKER_CUSTODY_INVALID")
    temporary = ACTIVE_STATE_PATH.with_name(
        f".{ACTIVE_STATE_PATH.name}.tmp.{os.getpid()}"
    )
    descriptor = os.open(
        temporary,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
        0o640,
    )
    try:
        try:
            os.fchown(descriptor, ROOT_UID, postgres_gid)
            os.fchmod(descriptor, 0o640)
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    try:
        os.replace(temporary, ACTIVE_STATE_PATH)
        directory = os.open(ACTIVE_STATE_PATH.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def activate(now: datetime) -> str:
    binding, binding_hash = _load_current()
    _load_resolver_policy(binding, binding_hash)
    _verify_peer_auth()
    current = now.astimezone(timezone.utc)
    if not (
        binding.o2_valid_from_utc.astimezone(timezone.utc)
        <= current
        < binding.expires_at_utc.astimezone(timezone.utc)
    ):
        raise HostActivationBlocked("RUNTIME_ACTIVATION_OUTSIDE_WINDOW")
    if _login_state() != "NOLOGIN":
        raise HostActivationBlocked("RUNTIME_ROLE_BASELINE_NOT_NOLOGIN")
    if os.path.lexists(ACTIVE_STATE_PATH):
        raise HostActivationBlocked("RUNTIME_ACTIVATION_STALE_STATE_PRESENT")
    _alter(True)
    try:
        _persist_active(binding_hash, binding.expires_at_utc.astimezone(timezone.utc).isoformat())
        _systemctl("start", "npd-vf-secret-resolver.socket")
    except Exception:
        _alter(False)
        ACTIVE_STATE_PATH.unlink(missing_ok=True)
        raise HostActivationBlocked("RUNTIME_ACTIVATION_STATE_SEAL_FAILED") from None
    return "RUNTIME_ROLE_ACTIVATED"


def deactivate() -> str:
    # Fail closed even if the activation artifact is corrupt or missing.
    socket_stopped = True
    for unit in ("npd-vf-secret-resolver.service", "npd-vf-secret-resolver.socket"):
        try:
            _systemctl("stop", unit)
        except HostActivationBlocked:
            socket_stopped = False
    _alter(False)
    try:
        ACTIVE_STATE_PATH.unlink(missing_ok=True)
    except OSError:
        raise HostActivationBlocked("RUNTIME_DEACTIVATION_STATE_CLEANUP_FAILED") from None
    if not socket_stopped:
        raise HostActivationBlocked("RUNTIME_RESOLVER_SOCKET_STATE_FAILED")
    return "RUNTIME_ROLE_NOLOGIN_VERIFIED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("activate", "deactivate", "verify-nologin"))
    args = parser.parse_args()
    if os.geteuid() != 0:
        print("HOST_ACTIVATION_ROOT_REQUIRED")
        return 2
    try:
        if args.action == "activate":
            code = activate(datetime.now(timezone.utc))
        elif args.action == "deactivate":
            code = deactivate()
        else:
            if _login_state() != "NOLOGIN":
                raise HostActivationBlocked("RUNTIME_ROLE_STILL_ACTIVE")
            code = "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    except HostActivationBlocked as exc:
        print(str(exc))
        return 2
    except Exception:
        print("HOST_ACTIVATION_INTERNAL_FAILURE")
        return 2
    print(code)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
