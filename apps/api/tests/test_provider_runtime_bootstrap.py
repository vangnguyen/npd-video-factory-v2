from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

import app.provider_runtime_bootstrap as bootstrap
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key


@pytest.fixture
def binding_data():
    pins = json.loads(r'''{"main_sha":"4507fa593fd8cf5484eb1245f788e9ee54eede39","rc_tag":"vf-v3-01-rc18","rc_commit":"03e18c1f0c56fff8a13f167af74f34894c2db811","executable_tree_sha256":"ffddebe0b657f62360ca3930f1329c9e877024f373d22b9487fe30723e2deae5","operation_key":"v3-01-rc18-openai-transcription-asr-al-0001-0e0aa1417c53feb79da3656eaa0d228b059db841496243f533b48607312c8518-call-01","bundle_sha256":"bb0f588c1465386e2be4caadf578dc10bb23020061a01c82ff4beab8b6fc2743","authority_sha256":"9a2750d2f6f8db6e5a130726f56e216873c202b59e5408bcca42a4607c87e397","execution_scope_sha256":"64d69549493743774e035f04efb99d890f86799b79a9bbef06a7ee26c8b5cf77","final_scope_sha256":"bf23f78f972f319eba224b7ca4d988dfe5edf0f7bbaa1381cc80e916dfd814d5","profile_sha256":"9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1","prompt_sha256":"6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48","asset_sha256":"fce31015644960a5f69640d7f5b90a7da078887b15c9d17dc227530d26b875ef","reference_sha256":"585b460291f11f1eb54c2b9a728bca26953ccce98719859e16ab15c7af9ff36e","rights_sha256":"5fb56c9817595693abea89176362e0efebbcab54867788d427e9f4a76d0a8091"}''')
    lineage = derive_acceptance_lineage_id(
        rc_tag=pins["rc_tag"], rc_commit=pins["rc_commit"],
        provider_key="openai-transcription", model="whisper-1", capability="asr", sequence=1,
    )
    return {
        "version": 1, "mode": "ZERO_CALL_CUSTODY_ONLY",
        "environment": "v3_01_acceptance_runtime",
        "rc_tag": pins["rc_tag"], "rc_commit": pins["rc_commit"],
        "governance_main_commit": pins["main_sha"],
        "executable_tree_sha256": pins["executable_tree_sha256"],
        "acceptance_lineage_id": lineage, "sequence": 1,
        "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "slot": 1,
        "operation_key": pins["operation_key"],
        "authority_receipt_sha256": pins["authority_sha256"],
        "bundle_sha256": pins["bundle_sha256"],
        "execution_scope_sha256": pins["execution_scope_sha256"],
        "scope_sha256": pins["final_scope_sha256"],
        "w1_profile_sha256": pins["profile_sha256"], "prompt_sha256": pins["prompt_sha256"],
        "asset_sha256": pins["asset_sha256"],
        "reference_transcript_sha256": pins["reference_sha256"],
        "rights_record_sha256": pins["rights_sha256"],
        "system_identifier": "7000000000000000001", "database_oid": 16384,
        "database_name": bootstrap.ledger_database_name(pins["rc_tag"], lineage),
        "database_role": "vang_nguyen", "schema_name": "public", "postgres_major": 16,
        "socket_directory": "/nonexistent/private/socket", "port": 55438,
        "kill_switch_engaged": True, "external_execution_enabled": False,
        "paid_execution_enabled": False, "budget_reserved_vnd": "0",
    }


def test_exact_binding_and_no_plaintext_url(binding_data):
    binding = bootstrap.BootstrapLedgerBinding.model_validate(binding_data)
    url = bootstrap.ledger_url(binding)
    assert url.password is None
    assert url.username == "vang_nguyen"
    assert url.query["host"] == binding.socket_directory
    assert binding.operation_key.endswith("-call-01")
    assert len(binding.operation_key) < 200


@pytest.mark.parametrize("field", [
    "rc_tag", "rc_commit", "acceptance_lineage_id", "operation_key",
    "system_identifier", "database_oid", "database_name", "environment",
    "authority_receipt_sha256", "kill_switch_engaged",
])
def test_missing_binding_fails_closed(binding_data, field):
    del binding_data[field]
    with pytest.raises(ValidationError):
        bootstrap.BootstrapLedgerBinding.model_validate(binding_data)


@pytest.mark.parametrize(("field", "value"), [
    ("sequence", True), ("version", True), ("slot", True), ("port", "55438"),
    ("database_oid", "16384"), ("postgres_major", "16"),
    ("kill_switch_engaged", 1), ("external_execution_enabled", 0),
    ("paid_execution_enabled", 0), ("kill_switch_engaged", False),
    ("external_execution_enabled", True), ("paid_execution_enabled", True),
    ("budget_reserved_vnd", "500"), ("database_name", "fixture"),
    ("environment", "test"), ("slot", 3), ("provider_key", "fixture"),
    ("model", "gpt-transcribe"), ("language", "en"),
    ("socket_directory", "relative/path"), ("connection_password", "not-a-secret"),
])
def test_wrong_types_extra_fields_and_execution_flags_fail_closed(binding_data, field, value):
    binding_data[field] = value
    with pytest.raises(ValidationError):
        bootstrap.BootstrapLedgerBinding.model_validate(binding_data)


@pytest.mark.parametrize("field", ["rc_commit", "acceptance_lineage_id", "operation_key", "sequence"])
def test_tampered_lineage_fails_closed(binding_data, field):
    binding_data[field] = 2 if field == "sequence" else "a" * (40 if field == "rc_commit" else 64)
    with pytest.raises(ValidationError):
        bootstrap.BootstrapLedgerBinding.model_validate(binding_data)


def test_rc17_namespace_and_operation_cannot_alias_rc18(binding_data):
    rc17_lineage = derive_acceptance_lineage_id(
        rc_tag="vf-v3-01-rc17", rc_commit="d08ffc005d7f3ad517d355977b0bc3cc8d686906",
        provider_key="openai-transcription", model="whisper-1", capability="asr", sequence=1,
    )
    rc17_op = derive_rc_bound_operation_key(
        rc_tag="vf-v3-01-rc17", provider_key="openai-transcription", capability="asr",
        slot=1, acceptance_lineage_id=rc17_lineage,
    )
    assert bootstrap.ledger_database_name("vf-v3-01-rc17", rc17_lineage) != binding_data["database_name"]
    binding_data["operation_key"] = rc17_op
    with pytest.raises(ValidationError):
        bootstrap.BootstrapLedgerBinding.model_validate(binding_data)


def test_binding_bytes_integrity_and_safe_invalid_record(tmp_path, binding_data):
    path = tmp_path / "binding.json"
    raw = json.dumps(binding_data, sort_keys=True).encode()
    path.write_bytes(raw)
    loaded = bootstrap.load_binding(path, hashlib.sha256(raw).hexdigest())
    assert loaded.rc_tag == "vf-v3-01-rc18"
    with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_BINDING_HASH_MISMATCH"):
        bootstrap.load_binding(path, "0" * 64)
    binding_data["unbound_extra"] = True
    raw = json.dumps(binding_data).encode()
    path.write_bytes(raw)
    with pytest.raises(bootstrap.BootstrapBlocked, match="^BOOTSTRAP_BINDING_INVALID$"):
        bootstrap.load_binding(path, hashlib.sha256(raw).hexdigest())


@pytest.mark.parametrize("failure", [
    "BOOTSTRAP_SOURCE_COMMIT_MISMATCH", "BOOTSTRAP_RC_TAG_MISMATCH",
    "BOOTSTRAP_SOURCE_NOT_CLEAN", "BOOTSTRAP_EXECUTABLE_TREE_MISMATCH",
    "BOOTSTRAP_IMPLEMENTATION_NOT_IN_BOUND_RC", "BOOTSTRAP_IMPLEMENTATION_BLOB_MISMATCH",
])
def test_source_qualification_precedes_any_database_access(monkeypatch, binding_data, failure):
    def deny(*args):
        raise bootstrap.BootstrapBlocked(failure)
    engine = AsyncMock()
    monkeypatch.setattr(bootstrap, "verify_bound_source", deny)
    monkeypatch.setattr(bootstrap, "create_async_engine", engine)
    with pytest.raises(bootstrap.BootstrapBlocked, match=failure):
        asyncio.run(bootstrap.bootstrap_custody(Path("."), bootstrap.BootstrapLedgerBinding(**binding_data), initialize_control=True))
    engine.assert_not_called()


def test_actual_rc18_cannot_use_candidate_bootstrap(monkeypatch, binding_data):
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    def lookup(repo, *args):
        if args[:2] == ("rev-parse", "HEAD") or args[:2] == ("rev-parse", binding.rc_tag + "^{}"):
            return binding.rc_commit
        if args[:2] == ("status", "--porcelain"):
            return ""
        if args and args[0] == "rev-parse" and args[1].endswith(":" + bootstrap.MODULE_PATH):
            raise bootstrap.BootstrapBlocked("BOOTSTRAP_SOURCE_LOOKUP_FAILED")
        return "a" * 40
    monkeypatch.setattr(bootstrap, "_git", lookup)
    monkeypatch.setattr(bootstrap, "executable_tree_sha256", lambda objects: binding.executable_tree_sha256)
    with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_IMPLEMENTATION_NOT_IN_BOUND_RC"):
        bootstrap.verify_bound_source(Path("."), binding)


def test_socket_rejects_symlink_and_world_access(tmp_path, binding_data):
    socket = tmp_path / "socket"
    socket.mkdir()
    binding_data["socket_directory"] = str(socket)
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    # Runtime socket custody requires a real POSIX owner-only directory.
    monkey_os = hasattr(bootstrap.os, "getuid")
    if monkey_os:
        socket.chmod(0o755)
        with pytest.raises(bootstrap.BootstrapBlocked):
            bootstrap.verify_socket_custody(binding)


@pytest.mark.parametrize("initialized", [False, True])
def test_metadata_registration_only_calls_existing_ensure_state(monkeypatch, binding_data, initialized):
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    before = {"control_present": initialized, "control_revision": 0, "counts": {"operations": 0}}
    after = {"control_present": True, "control_revision": 0, "counts": {"operations": 0}}
    read = AsyncMock(side_effect=[before, after])
    ensure = AsyncMock()
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(bootstrap, "verify_bound_source", lambda *args: None)
    monkeypatch.setattr(bootstrap, "verify_socket_custody", lambda *args: None)
    monkeypatch.setattr(bootstrap, "create_async_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(bootstrap, "async_sessionmaker", lambda *args, **kwargs: object())
    monkeypatch.setattr(bootstrap, "read_custody", read)
    monkeypatch.setattr(bootstrap, "ProviderSafetyRepository", lambda *args: SimpleNamespace(ensure_state=ensure))
    result = asyncio.run(bootstrap.bootstrap_custody(Path("."), binding, initialize_control=True))
    assert ensure.await_count == (0 if initialized else 1)
    assert result["ledger_bootstrap_write"]["operation_rows"] == 0
    assert result["ledger_bootstrap_write"]["reservation_vnd"] == "0"
    assert result["kill_switch"] == "ENGAGED"
    assert result["dispatch_entrypoint"] is None
    assert result["result"] == "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"


def test_inspect_does_not_initialize_control_implicitly(monkeypatch, binding_data):
    engine = SimpleNamespace(dispose=AsyncMock())
    monkeypatch.setattr(bootstrap, "verify_bound_source", lambda *args: None)
    monkeypatch.setattr(bootstrap, "verify_socket_custody", lambda *args: None)
    monkeypatch.setattr(bootstrap, "create_async_engine", lambda *args, **kwargs: engine)
    monkeypatch.setattr(bootstrap, "async_sessionmaker", lambda *args, **kwargs: object())
    monkeypatch.setattr(bootstrap, "read_custody", AsyncMock(return_value={"control_present": False}))
    with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_CONTROL_NOT_INITIALIZED"):
        asyncio.run(bootstrap.bootstrap_custody(Path("."), bootstrap.BootstrapLedgerBinding(**binding_data)))


def ledger_factory(binding_data, *, identity_change=None, operation=None, exact_attempts=0,
                   control_rows=1, counts=(0, 0, 0, 0, 0), foreign=(0, 0), active=0, reserved="0"):
    identity = {key: binding_data[key] for key in (
        "database_name", "database_role", "schema_name", "database_oid", "system_identifier")}
    identity["version"] = "160015"
    identity.update(identity_change or {})
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(one=lambda: identity))
    session = SimpleNamespace(
        execute=AsyncMock(side_effect=[None, result]),
        get=AsyncMock(side_effect=[operation, SimpleNamespace(revision=0) if control_rows else None]),
        scalar=AsyncMock(side_effect=[exact_attempts, control_rows, *counts, *foreign, active, reserved]),
    )
    class Context:
        async def __aenter__(self):
            return session
        async def __aexit__(self, *args):
            return False
    session.begin = Context
    return Context, session


def test_custody_reads_repeatable_read_without_writes(binding_data):
    factory, session = ledger_factory(binding_data)
    result = asyncio.run(bootstrap.read_custody(factory, bootstrap.BootstrapLedgerBinding(**binding_data), require_virgin_namespace=True))
    assert result["operation_state"] == "VIRGIN_NOT_REGISTERED / NOT_CONSUMED"
    assert result["counts"] == dict(operations=0, attempts=0, budget_days=0, circuits=0, budget_alerts=0)
    assert "REPEATABLE READ, READ ONLY" in str(session.execute.call_args_list[0].args[0])
    assert session.execute.await_count == 2
    assert not hasattr(session, "add") and not hasattr(session, "commit")


@pytest.mark.parametrize(("change", "code"), [
    ({"identity_change": {"database_name": "historical"}}, "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:database_name"),
    ({"identity_change": {"database_role": "wrong_owner"}}, "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:database_role"),
    ({"identity_change": {"schema_name": "fixture"}}, "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:schema_name"),
    ({"identity_change": {"database_oid": 9}}, "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:database_oid"),
    ({"identity_change": {"system_identifier": "7000000000000000002"}}, "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:system_identifier"),
    ({"identity_change": {"version": "150010"}}, "BOOTSTRAP_POSTGRES_VERSION_MISMATCH"),
    ({"operation": object()}, "DUPLICATE_OPERATION_BLOCKED"),
    ({"exact_attempts": 1}, "DUPLICATE_OPERATION_BLOCKED"),
    ({"control_rows": 2}, "BOOTSTRAP_CONTROL_NAMESPACE_INVALID"),
    ({"foreign": (1, 0)}, "BOOTSTRAP_CROSS_LINEAGE_STATE"),
    ({"foreign": (0, 1)}, "BOOTSTRAP_CROSS_LINEAGE_STATE"),
    ({"active": 1}, "BOOTSTRAP_ACTIVE_RESERVATION"),
    ({"reserved": "NaN"}, "BOOTSTRAP_OUTSTANDING_RESERVATION"),
    ({"reserved": "Infinity"}, "BOOTSTRAP_OUTSTANDING_RESERVATION"),
    ({"reserved": "-1"}, "BOOTSTRAP_OUTSTANDING_RESERVATION"),
    ({"reserved": "0.000001"}, "BOOTSTRAP_OUTSTANDING_RESERVATION"),
    ({"reserved": "not-numeric"}, "BOOTSTRAP_RESERVED_AMOUNT_INVALID"),
    ({"counts": (1, 0, 0, 0, 0)}, "BOOTSTRAP_NAMESPACE_NOT_VIRGIN"),
])
def test_actual_custody_identity_duplicate_and_reservation_fail_closed(binding_data, change, code):
    factory, _ = ledger_factory(binding_data, **change)
    with pytest.raises(bootstrap.BootstrapBlocked, match=code):
        asyncio.run(bootstrap.read_custody(factory, bootstrap.BootstrapLedgerBinding(**binding_data), require_virgin_namespace=True))


@pytest.mark.parametrize("reserved", ["0", "0.0000", "0E-6", "-0.0000"])
def test_numeric_zero_in_custody_does_not_compare_raw_strings(binding_data, reserved):
    factory, _ = ledger_factory(binding_data, reserved=reserved)
    assert asyncio.run(bootstrap.read_custody(factory, bootstrap.BootstrapLedgerBinding(**binding_data)))["reserved_vnd"] == reserved


def test_other_completed_slot_same_lineage_does_not_alias_current_operation(binding_data):
    factory, _ = ledger_factory(binding_data, counts=(1, 1, 1, 1, 0))
    result = asyncio.run(bootstrap.read_custody(factory, bootstrap.BootstrapLedgerBinding(**binding_data)))
    assert result["operation_state"] == "VIRGIN_NOT_REGISTERED / NOT_CONSUMED"
    assert result["counts"]["operations"] == 1


def test_socket_symlink_rejected(tmp_path, binding_data):
    original = tmp_path / "original"
    original.mkdir(mode=0o700)
    alias = tmp_path / "alias"
    alias.symlink_to(original, target_is_directory=True)
    binding_data["socket_directory"] = str(alias)
    with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_SOCKET_CUSTODY_INVALID"):
        bootstrap.verify_socket_custody(bootstrap.BootstrapLedgerBinding(**binding_data))


def test_windows_worktree_pointer_is_translated_not_replaced(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text("gitdir: C:/verified/repository/.git/worktrees/rc18\n", encoding="utf-8")
    real_is_dir = Path.is_dir
    monkeypatch.setattr(Path, "is_dir", lambda p: True if str(p) == "/mnt/c/verified/repository/.git/worktrees/rc18" else real_is_dir(p))
    args = bootstrap._git_argv(tmp_path, "rev-parse", "HEAD")
    if bootstrap.os.name == "posix":
        assert args == ["git", "--git-dir=/mnt/c/verified/repository/.git/worktrees/rc18", "--work-tree=" + str(tmp_path), "rev-parse", "HEAD"]


def test_windows_worktree_pointer_unreachable_fails_closed(tmp_path):
    (tmp_path / ".git").write_text("gitdir: Z:/nonexistent/repository/.git/worktrees/rc18\n", encoding="utf-8")
    if bootstrap.os.name == "posix":
        with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_GIT_METADATA_UNREACHABLE"):
            bootstrap._git_argv(tmp_path, "rev-parse", "HEAD")


def test_cli_has_no_execution_switch(monkeypatch):
    monkeypatch.setattr("sys.argv", ["bootstrap", "--dispatch"])
    with pytest.raises(SystemExit):
        bootstrap.main()


@pytest.mark.parametrize(("rc_tag", "sequence"), [
    ("vf-v3-01-rc17", 1), ("vf-v3-01-rc18", 2),
    ("vf-v3-01-rc19", 1), ("vf-v3-01-rc120", 9999),
])
def test_generic_rc_and_lineage_namespaces_are_not_historical_rc18(binding_data, rc_tag, sequence):
    # Synthetic contract identities only; no tag, operation registration or authority is created.
    lineage = derive_acceptance_lineage_id(
        rc_tag=rc_tag, rc_commit="b" * 40, provider_key="openai-transcription",
        model="whisper-1", capability="asr", sequence=sequence,
    )
    historical_database = binding_data["database_name"]
    binding_data.update(
        rc_tag=rc_tag, rc_commit="b" * 40, sequence=sequence,
        acceptance_lineage_id=lineage,
        operation_key=derive_rc_bound_operation_key(
            rc_tag=rc_tag, provider_key="openai-transcription", capability="asr",
            slot=1, acceptance_lineage_id=lineage,
        ),
        database_name=bootstrap.ledger_database_name(rc_tag, lineage),
    )
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    assert binding.database_name != historical_database
    assert len(binding.database_name) <= 63
    assert binding.database_name == bootstrap.ledger_database_name(rc_tag, lineage)
    binding_data["database_name"] = historical_database
    with pytest.raises(ValidationError, match="BOOTSTRAP_DATABASE_NAMESPACE_MISMATCH"):
        bootstrap.BootstrapLedgerBinding(**binding_data)


def test_source_qualification_success_checks_exact_import_and_blob(monkeypatch, binding_data):
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    source = Path(bootstrap.__file__).resolve().parents[3]
    calls = []
    def lookup(repo, *args):
        calls.append(args)
        if args[0] == "status":
            return ""
        if args[:2] in (("rev-parse", "HEAD"), ("rev-parse", binding.rc_tag + "^{}")):
            return binding.rc_commit
        return "a" * 40
    monkeypatch.setattr(bootstrap, "_git", lookup)
    monkeypatch.setattr(bootstrap, "executable_tree_sha256", lambda objects: binding.executable_tree_sha256)
    bootstrap.verify_bound_source(source, binding)
    assert any(args[0] == "hash-object" for args in calls)
    assert len([args for args in calls if args[0] == "rev-parse"]) == 15


@pytest.mark.parametrize(("lookup_failure", "code"), [
    ("head", "BOOTSTRAP_SOURCE_COMMIT_MISMATCH"),
    ("tag", "BOOTSTRAP_RC_TAG_MISMATCH"),
    ("dirty", "BOOTSTRAP_SOURCE_NOT_CLEAN"),
    ("tree", "BOOTSTRAP_EXECUTABLE_TREE_MISMATCH"),
    ("blob", "BOOTSTRAP_IMPLEMENTATION_BLOB_MISMATCH"),
    ("import", "BOOTSTRAP_IMPORT_SOURCE_MISMATCH"),
])
def test_each_exact_source_guard_fails_closed(monkeypatch, binding_data, lookup_failure, code):
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    source = Path(bootstrap.__file__).resolve().parents[3]
    if lookup_failure == "import":
        source = source / "different-checkout"
    def lookup(repo, *args):
        if args[0] == "status":
            return " M arbitrary.py" if lookup_failure == "dirty" else ""
        if args[:2] == ("rev-parse", "HEAD"):
            return "b" * 40 if lookup_failure == "head" else binding.rc_commit
        if args[:2] == ("rev-parse", binding.rc_tag + "^{}"):
            return "b" * 40 if lookup_failure == "tag" else binding.rc_commit
        if args[0] == "hash-object" and lookup_failure == "blob":
            return "b" * 40
        return "a" * 40
    monkeypatch.setattr(bootstrap, "_git", lookup)
    monkeypatch.setattr(bootstrap, "executable_tree_sha256", lambda objects: "0" * 64 if lookup_failure == "tree" else binding.executable_tree_sha256)
    with pytest.raises(bootstrap.BootstrapBlocked, match=code):
        bootstrap.verify_bound_source(source, binding)


def test_bootstrap_does_not_import_credential_settings_or_dispatch_code():
    import ast
    tree = ast.parse(Path(bootstrap.__file__).read_text(encoding="utf-8"))
    imports = [node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any("settings" in name or "credentials" in name or "transcription_providers" in name for name in imports)
    calls = [node.func.attr for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)]
    assert "reserve_operation" not in calls and "execute" in calls
    assert "ensure_state" in calls


def test_peer_engine_explicitly_disables_password_env_and_file_fallback(monkeypatch, binding_data):
    binding = bootstrap.BootstrapLedgerBinding(**binding_data)
    observed = {}
    engine = SimpleNamespace(dispose=AsyncMock())
    def create(url, **kwargs):
        observed.update(kwargs)
        assert url.password is None
        return engine
    monkeypatch.setattr(bootstrap, "verify_bound_source", lambda *args: None)
    monkeypatch.setattr(bootstrap, "verify_socket_custody", lambda *args: None)
    monkeypatch.setattr(bootstrap, "create_async_engine", create)
    monkeypatch.setattr(bootstrap, "async_sessionmaker", lambda *args, **kwargs: object())
    read = {"control_present": True, "control_revision": 0, "counts": {"operations": 0}}
    monkeypatch.setattr(bootstrap, "read_custody", AsyncMock(side_effect=[read, read]))
    asyncio.run(bootstrap.bootstrap_custody(Path("."), binding))
    assert observed["connect_args"] == {"password": ""}
