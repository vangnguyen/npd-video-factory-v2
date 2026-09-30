from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from app import runtime_role_failsafe as failsafe


NOW = datetime(2026, 9, 30, 13, 15, tzinfo=timezone.utc)


def marker_document(*, expires_at: datetime | None = None, **changes):
    value = {
        "version": 1,
        "runtime_activation_sha256": "a" * 64,
        "runtime_role": "vf_executor_runtime",
        "state": "LOGIN",
        "expires_at_utc": (expires_at or NOW + timedelta(minutes=15)).isoformat(),
    }
    value.update(changes)
    return value


def install_marker(tmp_path: Path, monkeypatch, *, raw: bytes | None = None, mode=0o640):
    parent = tmp_path / "run" / "npd-video-factory"
    parent.mkdir(parents=True)
    parent.chmod(0o755)
    marker = parent / "runtime-activation-active.json"
    marker.write_bytes(raw or (json.dumps(marker_document()).encode() + b"\n"))
    marker.chmod(mode)
    monkeypatch.setattr(failsafe, "ACTIVE_MARKER_PATH", marker)
    monkeypatch.setattr(failsafe, "ROOT_UID", os.getuid())
    return marker


def close_harness(monkeypatch, *, state="LOGIN", marker=None):
    closed = []
    monkeypatch.setattr(failsafe, "_require_postgres_identity", lambda: os.getgid())
    monkeypatch.setattr(failsafe, "_role_state", lambda: state)
    if isinstance(marker, Exception):
        monkeypatch.setattr(failsafe, "_read_active_marker", lambda _gid: (_ for _ in ()).throw(marker))
    elif marker is not None:
        monkeypatch.setattr(failsafe, "_read_active_marker", lambda _gid: marker)
    monkeypatch.setattr(failsafe, "_force_nologin", lambda: closed.append(True))
    return closed


def test_nologin_baseline_is_safe_and_does_not_touch_marker(monkeypatch):
    closed = close_harness(monkeypatch, state="NOLOGIN")
    monkeypatch.setattr(
        failsafe,
        "_read_active_marker",
        lambda _gid: (_ for _ in ()).throw(AssertionError("marker must not be read")),
    )
    assert failsafe.expire(NOW) == "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    assert closed == []


def test_login_with_valid_unexpired_marker_remains_active(monkeypatch):
    closed = close_harness(monkeypatch, marker=marker_document())
    assert failsafe.expire(NOW) == "RUNTIME_ROLE_ACTIVE_WITHIN_WINDOW"
    assert closed == []


@pytest.mark.parametrize(
    "marker",
    [
        marker_document(expires_at=NOW - timedelta(seconds=1)),
        marker_document(expires_at=datetime(2026, 9, 30, 14, 0)),
        failsafe.RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_UNAVAILABLE"),
        failsafe.RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_JSON_INVALID"),
        failsafe.RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_CUSTODY_INVALID"),
        failsafe.RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_SUBSTITUTED"),
        marker_document(runtime_role="unexpected"),
    ],
    ids=(
        "expired",
        "naive-expiry",
        "missing",
        "malformed",
        "permissions",
        "symlink",
        "wrong-role",
    ),
)
def test_unsafe_login_marker_states_force_nologin(monkeypatch, marker):
    if isinstance(marker, dict) and marker["runtime_role"] != "vf_executor_runtime":
        marker = failsafe.RuntimeMarkerInvalid("RUNTIME_ACTIVE_MARKER_BINDING_INVALID")
    closed = close_harness(monkeypatch, marker=marker)
    assert failsafe.expire(NOW) == "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    assert closed == [True]


def test_marker_custody_and_strict_schema(tmp_path, monkeypatch):
    marker = install_marker(tmp_path, monkeypatch)
    loaded = failsafe._read_active_marker(os.getgid())
    assert loaded == marker_document()
    assert marker.stat().st_mode & 0o777 == 0o640
    assert not marker.stat().st_mode & 0o020

    marker.write_text(json.dumps({**marker_document(), "unexpected": True}))
    marker.chmod(0o640)
    with pytest.raises(failsafe.RuntimeMarkerInvalid, match="SCHEMA_INVALID"):
        failsafe._read_active_marker(os.getgid())


def test_malformed_symlink_and_writable_markers_are_rejected(tmp_path, monkeypatch):
    marker = install_marker(tmp_path, monkeypatch, raw=b"not-json\n")
    with pytest.raises(failsafe.RuntimeMarkerInvalid, match="JSON_INVALID"):
        failsafe._read_active_marker(os.getgid())

    marker.unlink()
    target = marker.parent / "substitute.json"
    target.write_text(json.dumps(marker_document()))
    target.chmod(0o640)
    marker.symlink_to(target)
    with pytest.raises(failsafe.RuntimeMarkerInvalid, match="UNAVAILABLE"):
        failsafe._read_active_marker(os.getgid())

    marker.unlink()
    marker.write_text(json.dumps(marker_document()))
    marker.chmod(0o660)
    with pytest.raises(failsafe.RuntimeMarkerInvalid, match="CUSTODY_INVALID"):
        failsafe._read_active_marker(os.getgid())


def test_force_nologin_terminates_sessions_and_verifies(monkeypatch):
    calls = []

    def psql(statement):
        calls.append(statement)
        if statement == failsafe.ROLE_STATE_SQL:
            return "NOLOGIN"
        if statement == failsafe.COUNT_RUNTIME_SESSIONS_SQL:
            return "0"
        return ""

    monkeypatch.setattr(failsafe, "_psql", psql)
    failsafe._force_nologin()
    assert calls == [
        failsafe.FORCE_NOLOGIN_SQL,
        failsafe.TERMINATE_RUNTIME_SESSIONS_SQL,
        failsafe.ROLE_STATE_SQL,
        failsafe.COUNT_RUNTIME_SESSIONS_SQL,
    ]


def test_failsafe_has_only_fixed_local_postgres_controls():
    assert failsafe.POSTGRES_SOCKET_DIRECTORY == "/run/npd-video-factory/provider-custody/postgresql"
    assert failsafe.POSTGRES_PORT == 55432
    assert failsafe.POSTGRES_DATABASE == "postgres"
    assert failsafe.RUNTIME_ROLE == "vf_executor_runtime"
    assert failsafe.FORCE_NOLOGIN_SQL == "ALTER ROLE vf_executor_runtime NOLOGIN"
    assert "ALTER ROLE vf_executor_runtime LOGIN" not in failsafe._FIXED_SQL
    assert all("runuser" not in statement and "sudo" not in statement for statement in failsafe._FIXED_SQL)
    source = Path(failsafe.__file__).read_text(encoding="utf-8")
    assert "credstore.encrypted" not in source
    assert "credential.secret" not in source
    assert "provider_secret" not in source
    assert "execution-catalog" not in source
    assert "AF_INET" not in source and "127.0.0.1" not in source


def test_unknown_sql_is_rejected_before_process_launch(monkeypatch):
    monkeypatch.setattr(
        failsafe.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not launch")),
    )
    with pytest.raises(failsafe.RuntimeRoleFailsafeBlocked, match="SQL_NOT_ALLOWED"):
        failsafe._psql("SELECT current_user")
