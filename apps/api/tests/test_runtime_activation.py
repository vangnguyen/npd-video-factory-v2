from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest
from pydantic import ValidationError

from app import runtime_activation as activation
from app import runtime_activation_host as host


NOW = datetime(2026, 9, 30, 13, 15, tzinfo=timezone.utc)


def binding_data(**changes):
    value = {
        "version": 1,
        "mode": "RUNTIME_ACTIVATION",
        "authority_granted": False,
        "custody_binding_sha256": "c" * 64,
        "runtime_role": "vf_executor_runtime",
        "execution_plane_promotion_sha256": "d" * 64,
        "source_commit": "a" * 40,
        "executor_executable_tree_sha256": "e" * 64,
        "operation_id": "op-01",
        "authority_receipt_sha256": "a" * 64,
        "final_bundle_sha256": "b" * 64,
        "execution_scope_sha256": "e" * 64,
        "o2_activation_receipt_sha256": "f" * 64,
        "o2_valid_from_utc": datetime(2026, 9, 30, 13, 0, tzinfo=timezone.utc),
        "o2_expires_at_utc": datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc),
        "activated_at_utc": datetime(2026, 9, 30, 13, 1, tzinfo=timezone.utc),
        "expires_at_utc": datetime(2026, 9, 30, 14, 0, tzinfo=timezone.utc),
        "expected_live_role_state": "LOGIN",
        "expected_post_execution_state": "NOLOGIN",
        "peer_map_name": "vf_executor_runtime_map",
        "os_peer_user": "vf-executor",
        "database_role": "vf_executor_runtime",
        "database_name": "vf_provider_custody_v3_01",
        "socket_directory": "/run/npd-video-factory/provider-custody/postgresql",
        "port": 55432,
        "activation_receipt_version": 1,
    }
    value.update(changes)
    return value


def binding(**changes):
    return activation.RuntimeActivationBinding.model_validate(binding_data(**changes))


def verify(value, **changes):
    arguments = {
        "now": NOW,
        "custody_binding_sha256": "c" * 64,
        "execution_plane_promotion_sha256": "d" * 64,
        "source_commit": "a" * 40,
        "executor_executable_tree_sha256": "e" * 64,
        "operation_id": "op-01",
        "authority_receipt_sha256": "a" * 64,
        "final_bundle_sha256": "b" * 64,
        "execution_scope_sha256": "e" * 64,
    }
    arguments.update(changes)
    activation.verify_runtime_activation(value, **arguments)


def test_binding_is_strict_and_separate_from_authority():
    verify(binding())
    with pytest.raises(ValidationError):
        activation.RuntimeActivationBinding.model_validate({**binding_data(), "credential": "forbidden"})
    assert binding().authority_granted is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("operation_id", "wrong"),
        ("authority_receipt_sha256", "f" * 64),
        ("final_bundle_sha256", "f" * 64),
        ("execution_scope_sha256", "f" * 64),
        ("execution_plane_promotion_sha256", "f" * 64),
    ],
)
def test_binding_context_mismatch_fails_closed(field, value):
    with pytest.raises(activation.RuntimeActivationBlocked, match="RUNTIME_ACTIVATION_BINDING_MISMATCH"):
        verify(binding(), **{field: value})


def test_missing_hash_and_expired_activation_fail_closed(tmp_path):
    raw = binding().model_dump_json().encode()
    path = tmp_path / "activation.json"
    path.write_bytes(raw)
    loaded = activation.load_runtime_activation_binding(path, hashlib.sha256(raw).hexdigest())
    assert loaded == binding()
    with pytest.raises(activation.RuntimeActivationBlocked, match="RUNTIME_ACTIVATION_HASH_MISMATCH"):
        activation.load_runtime_activation_binding(path, "f" * 64)
    with pytest.raises(activation.RuntimeActivationBlocked, match="RUNTIME_ACTIVATION_OUTSIDE_WINDOW"):
        verify(binding(), now=NOW + timedelta(hours=2))


def test_host_activation_and_all_cleanup_paths_restore_nologin(tmp_path, monkeypatch):
    value = binding()
    state = {"login": False}
    monkeypatch.setattr(host, "_load_current", lambda: (value, "h" * 64))
    monkeypatch.setattr(host, "_load_resolver_policy", lambda *args: object())
    monkeypatch.setattr(host, "_verify_peer_auth", lambda: None)
    monkeypatch.setattr(host, "ACTIVE_STATE_PATH", tmp_path / "active.json")
    monkeypatch.setattr(host, "_login_state", lambda: "LOGIN" if state["login"] else "NOLOGIN")
    monkeypatch.setattr(host, "_alter", lambda login: state.update(login=login))
    systemd = []
    monkeypatch.setattr(host, "_systemctl", lambda action, unit: systemd.append((action, unit)))
    assert host.activate(NOW) == "RUNTIME_ROLE_ACTIVATED"
    assert state["login"] is True
    assert systemd[-1] == ("start", "npd-vf-secret-resolver.socket")
    assert host.deactivate() == "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    assert state["login"] is False
    assert ("stop", "npd-vf-secret-resolver.socket") in systemd
    # Crash/expiry path is independent of the executor's Python finally.
    state["login"] = True
    host._persist_active("h" * 64, value.expires_at_utc.isoformat())
    assert host.expire(NOW + timedelta(hours=2)) == "RUNTIME_ROLE_NOLOGIN_VERIFIED"
    assert state["login"] is False


def test_unauthorized_activation_requires_sealed_binding(monkeypatch):
    monkeypatch.setattr(host, "_load_current", lambda: (_ for _ in ()).throw(
        host.HostActivationBlocked("RUNTIME_ACTIVATION_HASH_MISMATCH")
    ))
    with pytest.raises(host.HostActivationBlocked, match="RUNTIME_ACTIVATION_HASH_MISMATCH"):
        host.activate(NOW)


def test_peer_auth_is_exact_and_rejects_trust(monkeypatch):
    hba = (
        "local   vf_provider_custody_v3_01   vf_executor_runtime     "
        "peer map=vf_executor_runtime_map\n"
        "local all all reject\n"
    ).encode()
    ident = b"vf_executor_runtime_map vf-executor vf_executor_runtime\n"
    monkeypatch.setattr(
        host, "_root_file",
        lambda path, **kwargs: hba if path == host.HBA_PATH else ident,
    )
    settings = {
        "SHOW hba_file": str(host.HBA_PATH),
        "SHOW ident_file": str(host.IDENT_PATH),
        "SHOW listen_addresses": "",
        "SHOW unix_socket_directories": activation.CANONICAL_SOCKET_DIRECTORY,
        "SHOW port": str(activation.CANONICAL_PORT),
    }
    monkeypatch.setattr(host, "_psql", settings.__getitem__)
    host._verify_peer_auth()
    hba = hba.replace(b"peer map=vf_executor_runtime_map", b"trust")
    with pytest.raises(host.HostActivationBlocked, match="RUNTIME_PEER_AUTH_CONFIGURATION_INVALID"):
        host._verify_peer_auth()
