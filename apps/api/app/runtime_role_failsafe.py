"""PostgreSQL-user crash/expiry backstop for the executor runtime role.

This helper is intentionally separate from the root activation lifecycle.  It
can only observe the fixed runtime role and force it to NOLOGIN.  All database
coordinates, SQL statements, and the active-marker path are compile-time
constants; no provider, authority, bundle, catalog, or credential input is
accepted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import grp
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess


RUNTIME_ROLE = "vf_executor_runtime"
POSTGRES_USER = "postgres"
POSTGRES_GROUP = "postgres"
POSTGRES_SOCKET_DIRECTORY = "/run/npd-video-factory/provider-custody/postgresql"
POSTGRES_PORT = 55432
POSTGRES_DATABASE = "postgres"
PSQL = "/usr/lib/postgresql/16/bin/psql"
ACTIVE_MARKER_PATH = Path("/run/npd-video-factory/runtime-activation-active.json")
MAX_MARKER_BYTES = 4096
ROOT_UID = 0

ROLE_STATE_SQL = (
    "SELECT CASE WHEN rolcanlogin THEN 'LOGIN' ELSE 'NOLOGIN' END "
    "FROM pg_roles WHERE rolname='vf_executor_runtime'"
)
FORCE_NOLOGIN_SQL = "ALTER ROLE vf_executor_runtime NOLOGIN"
TERMINATE_RUNTIME_SESSIONS_SQL = (
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
    "WHERE usename='vf_executor_runtime' AND pid<>pg_backend_pid()"
)
COUNT_RUNTIME_SESSIONS_SQL = (
    "SELECT count(*) FROM pg_stat_activity WHERE usename='vf_executor_runtime'"
)
_FIXED_SQL = frozenset(
    {
        ROLE_STATE_SQL,
        FORCE_NOLOGIN_SQL,
        TERMINATE_RUNTIME_SESSIONS_SQL,
        COUNT_RUNTIME_SESSIONS_SQL,
    }
)
_MARKER_FIELDS = frozenset(
    {
        "version",
        "runtime_activation_sha256",
        "runtime_role",
        "state",
        "expires_at_utc",
    }
)


class RuntimeRoleFailsafeBlocked(RuntimeError):
    """Fixed code-only failure for the expiry backstop."""


class RuntimeMarkerInvalid(RuntimeError):
    """The active marker is absent or cannot authorize continued LOGIN."""


def _postgres_identity() -> tuple[int, int]:
    try:
        user = pwd.getpwnam(POSTGRES_USER)
        group = grp.getgrnam(POSTGRES_GROUP)
    except KeyError:
        raise RuntimeRoleFailsafeBlocked("POSTGRES_SERVICE_IDENTITY_MISSING") from None
    if user.pw_gid != group.gr_gid:
        raise RuntimeRoleFailsafeBlocked("POSTGRES_SERVICE_IDENTITY_MISMATCH")
    return user.pw_uid, group.gr_gid


def _require_postgres_identity() -> int:
    uid, gid = _postgres_identity()
    if os.geteuid() != uid or os.getegid() != gid:
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_POSTGRES_IDENTITY_REQUIRED")
    return gid


def _psql(statement: str) -> str:
    if statement not in _FIXED_SQL:
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_SQL_NOT_ALLOWED")
    result = subprocess.run(
        [
            PSQL,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            POSTGRES_SOCKET_DIRECTORY,
            "-p",
            str(POSTGRES_PORT),
            "-d",
            POSTGRES_DATABASE,
            "-Atqc",
            statement,
        ],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
        timeout=20,
        env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "PGAPPNAME": "npd-vf-runtime-role-failsafe"},
    )
    if result.returncode:
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_POSTGRES_COMMAND_FAILED")
    return result.stdout.strip()


def _role_state() -> str:
    state = _psql(ROLE_STATE_SQL)
    if state not in {"LOGIN", "NOLOGIN"}:
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_RUNTIME_ROLE_MISSING")
    return state


def _validate_marker_stat(info: os.stat_result, postgres_gid: int) -> None:
    mode = stat.S_IMODE(info.st_mode)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != ROOT_UID
        or info.st_gid != postgres_gid
        or mode & 0o7000
        or mode & 0o137
        or not mode & stat.S_IRGRP
    ):
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_CUSTODY_INVALID")


def _read_active_marker(postgres_gid: int) -> dict[str, object]:
    parent = ACTIVE_MARKER_PATH.parent
    try:
        parent_info = parent.lstat()
    except OSError:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_PARENT_INVALID") from None
    if (
        not stat.S_ISDIR(parent_info.st_mode)
        or stat.S_ISLNK(parent_info.st_mode)
        or parent_info.st_uid != ROOT_UID
        or stat.S_IMODE(parent_info.st_mode) & 0o022
    ):
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_PARENT_INVALID")

    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(ACTIVE_MARKER_PATH, flags)
    except OSError:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_UNAVAILABLE") from None
    try:
        before = ACTIVE_MARKER_PATH.lstat()
        opened = os.fstat(descriptor)
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_SUBSTITUTED")
        _validate_marker_stat(opened, postgres_gid)
        raw = os.read(descriptor, MAX_MARKER_BYTES + 1)
    except RuntimeMarkerInvalid:
        raise
    except OSError:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_UNAVAILABLE") from None
    finally:
        os.close(descriptor)
    if not raw or len(raw) > MAX_MARKER_BYTES:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_SIZE_INVALID")
    try:
        document = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_JSON_INVALID") from None
    if not isinstance(document, dict) or set(document) != _MARKER_FIELDS:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_SCHEMA_INVALID")
    if type(document["version"]) is not int or document["version"] != 1:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_SCHEMA_INVALID")
    if (
        not isinstance(document["runtime_activation_sha256"], str)
        or re.fullmatch(r"[a-f0-9]{64}", document["runtime_activation_sha256"]) is None
        or document["runtime_role"] != RUNTIME_ROLE
        or document["state"] != "LOGIN"
        or not isinstance(document["expires_at_utc"], str)
    ):
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_BINDING_INVALID")
    return document


def _marker_expiry(document: dict[str, object]) -> datetime:
    raw = str(document["expires_at_utc"])
    try:
        expiry = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_EXPIRY_INVALID") from None
    if expiry.tzinfo is None or expiry.utcoffset() is None:
        raise RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_EXPIRY_INVALID")
    return expiry.astimezone(timezone.utc)


def _force_nologin() -> None:
    _psql(FORCE_NOLOGIN_SQL)
    _psql(TERMINATE_RUNTIME_SESSIONS_SQL)
    if _role_state() != "NOLOGIN":
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_RUNTIME_ROLE_STILL_ACTIVE")
    if _psql(COUNT_RUNTIME_SESSIONS_SQL) != "0":
        raise RuntimeRoleFailsafeBlocked("FAILSAFE_RUNTIME_SESSIONS_REMAIN")


def expire(now: datetime) -> str:
    """Keep a valid in-window LOGIN state or force the fixed role closed."""
    postgres_gid = _require_postgres_identity()
    if _role_state() == "NOLOGIN":
        return "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    try:
        marker = _read_active_marker(postgres_gid)
        expiry = _marker_expiry(marker)
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeMarkerInvalid("FAILSAFE_CURRENT_TIME_INVALID")
        current = now.astimezone(timezone.utc)
        if current < expiry:
            return "RUNTIME_ROLE_ACTIVE_WITHIN_WINDOW"
    except RuntimeMarkerInvalid:
        pass
    _force_nologin()
    return "RUNTIME_ROLE_NOLOGIN_VERIFIED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("expire",))
    args = parser.parse_args()
    try:
        if args.action != "expire":  # pragma: no cover - argparse enforces this.
            raise RuntimeRoleFailsafeBlocked("FAILSAFE_ACTION_NOT_ALLOWED")
        result = expire(datetime.now(timezone.utc))
    except RuntimeRoleFailsafeBlocked as exc:
        print(str(exc))
        return 2
    except Exception:
        print("RUNTIME_ROLE_FAILSAFE_INTERNAL_FAILURE")
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
