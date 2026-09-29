from __future__ import annotations

import asyncio
import hashlib
import json
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app import provider_custody as custody


@pytest.fixture
def binding_data():
    evidence = tuple(
        {"kind": kind, "path": f"/sealed/{kind}.json", "manifest_sha256": character * 64}
        for kind, character in (
            ("logical_backup", "a"), ("physical_backup", "b"),
            ("off_host_backup", "c"), ("restore_test", "d"),
        )
    )
    return {
        "version": 1,
        "mode": "CUSTODY_ONLY",
        "authority_granted": False,
        "postgres_major": 16,
        "postgres_version": "16.15",
        "packages": (
            {"name": "postgresql-16", "version": "16.15-1.pgdg24.04+1", "repository_origin": "apt.postgresql.org/pub/repos/apt", "archive_sha256": "1" * 64},
            {"name": "postgresql-client-16", "version": "16.15-1.pgdg24.04+1", "repository_origin": "apt.postgresql.org/pub/repos/apt", "archive_sha256": "2" * 64},
        ),
        "system_identifier": "7000000000000000001",
        "database_name": custody.DATABASE_NAME,
        "database_oid": 16384,
        "schema_name": "public",
        "migration_head": custody.MIGRATION_HEAD,
        "socket_directory": custody.SOCKET_DIRECTORY,
        "port": custody.PORT,
        "data_root": custody.DATA_ROOT,
        "backup_root": custody.BACKUP_ROOT,
        "custody_tables": custody.CUSTODY_TABLES,
        "postgres_service_user": "postgres",
        "postgres_service_uid": 111,
        "postgres_service_gid": 112,
        "socket_group": "vf-custody-access",
        "socket_group_gid": 113,
        "socket_directory_mode": "2750",
        "socket_mode": "0770",
        "runtime_role": custody.RUNTIME_ROLE,
        "runtime_login": False,
        "qualification_role": custody.QUALIFICATION_ROLE,
        "qualification_access": "SELECT_ONLY",
        "evidence_references": evidence,
    }


def test_custody_binding_is_structurally_separate_from_authority(binding_data):
    binding = custody.CustodyBinding.model_validate(binding_data)
    assert binding.authority_granted is False
    assert binding.runtime_login is False
    for forbidden in ("operation_id", "operation_key", "o2_approval", "execution_window", "bundle_sha256", "provider_credential"):
        tampered = dict(binding_data, **{forbidden: "forbidden"})
        with pytest.raises(ValidationError):
            custody.CustodyBinding.model_validate(tampered)


@pytest.mark.parametrize(("field", "value"), [
    ("database_name", "vf_vf_v3_01_rc22_0d09fd22d9bc2936353f366b06bfefad"),
    ("postgres_major", 17), ("postgres_version", "16.14"),
    ("authority_granted", True), ("runtime_login", True),
    ("qualification_access", "DML"), ("migration_head", "0014"),
])
def test_wrong_custody_identity_fails_closed(binding_data, field, value):
    binding_data[field] = value
    with pytest.raises(ValidationError):
        custody.CustodyBinding.model_validate(binding_data)


def test_binding_hash_and_no_password(binding_data, tmp_path):
    path = tmp_path / "custody.json"
    raw = json.dumps(binding_data, sort_keys=True).encode()
    path.write_bytes(raw)
    binding = custody.load_custody_binding(path, hashlib.sha256(raw).hexdigest())
    url = custody.custody_url(binding)
    assert url.password is None
    assert url.username == custody.QUALIFICATION_ROLE
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_BINDING_HASH_MISMATCH"):
        custody.load_custody_binding(path, "0" * 64)
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_BINDING_NOT_CANONICAL"):
        custody.load_canonical_custody_binding(path, hashlib.sha256(raw).hexdigest())


def test_terminal_history_is_allowed_only_when_shared_custody_is_quiescent():
    control = [{"control_key": "global", "revision": 17}]
    assert custody._validate_quiescent_shared_custody(
        control,
        active_operations=0,
        reserved_vnd="0",
    ) == 0
    with pytest.raises(
        custody.CustodyBlocked,
        match="CUSTODY_ACTIVE_RESERVATION_STATE_INVALID",
    ):
        custody._validate_quiescent_shared_custody(
            control,
            active_operations=1,
            reserved_vnd="500",
        )
    with pytest.raises(
        custody.CustodyBlocked,
        match="CUSTODY_ACTIVE_RESERVATION_STATE_INVALID",
    ):
        custody._validate_quiescent_shared_custody(
            control,
            active_operations=0,
            reserved_vnd="1",
        )


def _socket_path(monkeypatch, directory_uid=111, directory_mode=0o2750, socket_uid=111, socket_mode=0o770):
    class FakePath:
        def __init__(self, value):
            self.value = str(value)

        def __truediv__(self, child):
            return FakePath(self.value + "/" + child)

        def stat(self):
            if ".s.PGSQL." in self.value:
                return SimpleNamespace(st_mode=stat.S_IFSOCK | socket_mode, st_uid=socket_uid, st_gid=113)
            return SimpleNamespace(st_mode=stat.S_IFDIR | directory_mode, st_uid=directory_uid, st_gid=113)

    monkeypatch.setattr(custody, "Path", FakePath)
    monkeypatch.setattr(custody, "_require_canonical_path", lambda path: None)


def _host_identities(
    monkeypatch, *, service_uid=111, service_gid=112, socket_group_gid=113,
):
    monkeypatch.setattr(
        custody,
        "pwd",
        SimpleNamespace(getpwnam=lambda _name: SimpleNamespace(
            pw_uid=service_uid,
            pw_gid=service_gid,
        )),
    )
    monkeypatch.setattr(
        custody,
        "grp",
        SimpleNamespace(getgrnam=lambda _name: SimpleNamespace(
            gr_gid=socket_group_gid,
        )),
    )


def test_dedicated_postgres_service_identity_is_accepted(binding_data, monkeypatch):
    _host_identities(monkeypatch)
    _socket_path(monkeypatch)
    custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_runner_owned_socket_is_rejected(binding_data, monkeypatch):
    _host_identities(monkeypatch)
    _socket_path(monkeypatch, directory_uid=999, socket_uid=999)
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_SOCKET_DIRECTORY_IDENTITY_INVALID"):
        custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_world_writable_socket_is_rejected(binding_data, monkeypatch):
    _host_identities(monkeypatch)
    _socket_path(monkeypatch, socket_mode=0o777)
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_SOCKET_IDENTITY_INVALID"):
        custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_symlink_or_path_substitution_is_rejected(binding_data, monkeypatch):
    _host_identities(monkeypatch)
    monkeypatch.setattr(custody, "_require_canonical_path", lambda path: (_ for _ in ()).throw(custody.CustodyBlocked("CUSTODY_SOCKET_PATH_SUBSTITUTION")))
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_SOCKET_PATH_SUBSTITUTION"):
        custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_real_symlink_path_substitution_is_rejected(tmp_path):
    target = tmp_path / "real-socket-directory"
    target.mkdir()
    link = tmp_path / "substituted-socket-directory"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(
        custody.CustodyBlocked,
        match="CUSTODY_SOCKET_PATH_SUBSTITUTION",
    ):
        custody._require_canonical_path(link)


@pytest.mark.parametrize(("service_uid", "service_gid"), [
    (999, 112),
    (111, 999),
])
def test_wrong_named_postgres_service_uid_or_gid_is_rejected(
    binding_data, monkeypatch, service_uid, service_gid,
):
    _host_identities(
        monkeypatch,
        service_uid=service_uid,
        service_gid=service_gid,
    )
    with pytest.raises(
        custody.CustodyBlocked,
        match="CUSTODY_POSTGRES_SERVICE_IDENTITY_INVALID",
    ):
        custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_wrong_named_socket_group_gid_is_rejected(binding_data, monkeypatch):
    _host_identities(monkeypatch, socket_group_gid=999)
    with pytest.raises(
        custody.CustodyBlocked,
        match="CUSTODY_SOCKET_GROUP_IDENTITY_INVALID",
    ):
        custody.verify_socket_custody(custody.CustodyBinding.model_validate(binding_data))


def test_wrong_postgres_instance_is_rejected(binding_data):
    binding = custody.CustodyBinding.model_validate(binding_data)
    identity = {
        "database_name": binding.database_name,
        "database_role": binding.qualification_role,
        "schema_name": binding.schema_name,
        "version_num": "160015",
        "version": "16.15",
        "database_oid": binding.database_oid,
        "system_identifier": "7000000000000000002",
    }
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: identity))
    session = SimpleNamespace(execute=AsyncMock(side_effect=[None, result]))

    class Context:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *args):
            return False

    session.begin = Context
    with pytest.raises(custody.CustodyBlocked, match="CUSTODY_POSTGRES_INSTANCE_MISMATCH"):
        asyncio.run(custody.read_custody(Context, binding))


def test_qualification_source_enforces_select_only_and_read_only():
    source = Path(custody.__file__).read_text(encoding="utf-8")
    assert "REPEATABLE READ, READ ONLY" in source
    assert '("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")' in source
    assert '"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False, "TRUNCATE": False' in source
    assert "CUSTODY_QUALIFICATION_WRITE_SUCCEEDED" in source
