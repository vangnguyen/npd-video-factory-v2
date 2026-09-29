from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from app import provider_custody as custody
from app import provider_runtime_bootstrap as bootstrap
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key


@pytest.fixture
def operation_data():
    rc_tag = "vf-v3-01-rc23"
    rc_commit = "a" * 40
    lineage = derive_acceptance_lineage_id(
        rc_tag=rc_tag,
        rc_commit=rc_commit,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        sequence=1,
    )
    return {
        "version": 2,
        "mode": "OPERATION_EXECUTION",
        "environment": "v3_01_acceptance_runtime",
        "rc_tag": rc_tag,
        "rc_commit": rc_commit,
        "governance_main_commit": "b" * 40,
        "executable_tree_sha256": "1" * 64,
        "executor_executable_tree_sha256": "2" * 64,
        "execution_plane_promotion_sha256": "3" * 64,
        "acceptance_lineage_id": lineage,
        "sequence": 1,
        "provider_key": "openai-transcription",
        "model": "whisper-1",
        "capability": "asr",
        "language": "vi",
        "credential_alias": "secret://openai/codex-video",
        "slot": 1,
        "operation_key": derive_rc_bound_operation_key(
            rc_tag=rc_tag,
            provider_key="openai-transcription",
            capability="asr",
            slot=1,
            acceptance_lineage_id=lineage,
        ),
        "authority_receipt_sha256": "4" * 64,
        "bundle_sha256": "5" * 64,
        "prepared_scope_sha256": "6" * 64,
        "execution_scope_sha256": "7" * 64,
        "loaded_scope_sha256": "8" * 64,
        "w1_profile_sha256": "9" * 64,
        "prompt_sha256": "a" * 64,
        "asset_sha256": "b" * 64,
        "reference_transcript_sha256": "c" * 64,
        "rights_record_sha256": "d" * 64,
    }


@pytest.fixture
def custody_data():
    evidence = tuple(
        {
            "kind": kind,
            "path": f"/sealed/{kind}.json",
            "manifest_sha256": character * 64,
        }
        for kind, character in (
            ("logical_backup", "a"),
            ("physical_backup", "b"),
            ("off_host_backup", "c"),
            ("restore_test", "d"),
        )
    )
    return {
        "version": 1,
        "mode": "CUSTODY_ONLY",
        "authority_granted": False,
        "postgres_major": 16,
        "postgres_version": "16.15",
        "packages": (
            {
                "name": "postgresql-16",
                "version": "16.15-1.pgdg24.04+1",
                "repository_origin": "apt.postgresql.org/pub/repos/apt",
                "archive_sha256": "1" * 64,
            },
            {
                "name": "postgresql-client-16",
                "version": "16.15-1.pgdg24.04+1",
                "repository_origin": "apt.postgresql.org/pub/repos/apt",
                "archive_sha256": "2" * 64,
            },
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


def _operation(operation_data):
    return bootstrap.OperationBinding.model_validate(operation_data)


def _custody(custody_data):
    return custody.CustodyBinding.model_validate(custody_data)


def _snapshot(operation, custody_binding):
    return {
        "identity": {
            "database_name": custody_binding.database_name,
            "database_role": custody_binding.qualification_role,
            "schema_name": custody_binding.schema_name,
            "version_num": "160015",
            "version": "16.15",
            "database_oid": custody_binding.database_oid,
            "system_identifier": custody_binding.system_identifier,
        },
        "expected_role": custody_binding.qualification_role,
        "migration_head": custody_binding.migration_head,
        "control_rows": [{"control_key": "global", "revision": 7}],
        "exact_operation": None,
        "exact_attempts": [],
        "exact_usage_attempt": None,
        "attempt_lineage_pairs": [{
            "attempt_lineage_id": "al-0001-" + "e" * 64,
            "operation_lineage_id": "al-0001-" + "e" * 64,
        }],
        "active_operations": [],
        "receipt_rows": [{
            "dispatch_request_sha256": "e" * 64,
            "dispatch_client_request_id": "historical-client-id",
        }],
        "budget_rows": [{
            "currency": "VND",
            "daily_limit_vnd": "1000",
            "committed_vnd": "300",
            "reserved_vnd": "0",
        }],
        "circuit_rows": [{
            "provider_key": operation.provider_key,
            "capability": operation.capability,
            "state": "closed",
            "consecutive_failures": 0,
            "opened_at": None,
            "half_open_operation_key": None,
        }],
        "counts": {
            "operations": 1,
            "attempts": 1,
            "budget_days": 1,
            "circuits": 1,
            "budget_alerts": 0,
        },
    }


def test_operation_and_custody_bindings_are_separate(operation_data, custody_data):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    assert custody_binding.database_name == "vf_provider_custody_v3_01"
    assert not {
        "database_name", "database_oid", "system_identifier", "socket_directory",
        "database_role", "postgres_major",
    }.intersection(operation.model_fields_set)
    with pytest.raises(ValidationError):
        bootstrap.OperationBinding.model_validate({
            **operation_data,
            "database_name": "vf_vf_v3_01_rc23_forbidden",
        })
    with pytest.raises(ValidationError):
        custody.CustodyBinding.model_validate({
            **custody_data,
            "rc_tag": operation.rc_tag,
        })


def test_same_canonical_custody_supports_sequential_rc_lineages(operation_data, custody_data):
    canonical = _custody(custody_data)
    for rc_tag, commit, sequence in (
        ("vf-v3-01-rc23", "a" * 40, 1),
        ("vf-v3-01-rc24", "f" * 40, 2),
    ):
        lineage = derive_acceptance_lineage_id(
            rc_tag=rc_tag,
            rc_commit=commit,
            provider_key="openai-transcription",
            model="whisper-1",
            capability="asr",
            sequence=sequence,
        )
        data = {
            **operation_data,
            "rc_tag": rc_tag,
            "rc_commit": commit,
            "sequence": sequence,
            "acceptance_lineage_id": lineage,
            "operation_key": derive_rc_bound_operation_key(
                rc_tag=rc_tag,
                provider_key="openai-transcription",
                capability="asr",
                slot=1,
                acceptance_lineage_id=lineage,
            ),
        }
        assert _operation(data).operation_key.startswith("v3-01-")
        assert canonical.database_name == custody.DATABASE_NAME


@pytest.mark.parametrize("field", [
    "rc_tag", "rc_commit", "governance_main_commit", "acceptance_lineage_id",
    "operation_key", "authority_receipt_sha256", "executor_executable_tree_sha256",
    "execution_plane_promotion_sha256", "prepared_scope_sha256",
])
def test_missing_operation_identity_fails_closed(operation_data, field):
    del operation_data[field]
    with pytest.raises(ValidationError):
        _operation(operation_data)


@pytest.mark.parametrize(("field", "value"), [
    ("version", 1),
    ("version", True),
    ("slot", 3),
    ("sequence", True),
    ("provider_key", "other"),
    ("model", "other"),
    ("credential_alias", "secret://other"),
    ("database_name", custody.DATABASE_NAME),
])
def test_wrong_types_values_and_custody_fields_fail_closed(operation_data, field, value):
    operation_data[field] = value
    with pytest.raises(ValidationError):
        _operation(operation_data)


def test_operation_binding_hash_is_exact(tmp_path, operation_data):
    path = tmp_path / "operation.json"
    raw = json.dumps(operation_data, sort_keys=True).encode()
    path.write_bytes(raw)
    assert bootstrap.load_operation_binding(path, hashlib.sha256(raw).hexdigest()).slot == 1
    with pytest.raises(bootstrap.BootstrapBlocked, match="OPERATION_BINDING_HASH_MISMATCH"):
        bootstrap.load_operation_binding(path, "0" * 64)


def test_completed_unrelated_lineage_is_allowed(operation_data, custody_data):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    result = bootstrap._validate_operation_snapshot(
        _snapshot(operation, custody_binding),
        operation,
        custody_binding,
    )
    assert result["operation_state"] == "FRESH_OPERATION_NOT_REGISTERED / NOT_CONSUMED"
    assert result["counts"]["operations"] == 1
    assert result["counts"]["attempts"] == 1
    assert result["reserved_vnd"] == "0"


def test_same_request_content_hash_across_completed_lineages_is_allowed(
    operation_data, custody_data,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["receipt_rows"].append({
        "dispatch_request_sha256": snapshot["receipt_rows"][0]["dispatch_request_sha256"],
        "dispatch_client_request_id": "different-historical-client-id",
    })
    result = bootstrap._validate_operation_snapshot(
        snapshot,
        operation,
        custody_binding,
    )
    assert result["operation_state"] == "FRESH_OPERATION_NOT_REGISTERED / NOT_CONSUMED"


@pytest.mark.parametrize("request_sha256", [
    None,
    "",
    "e" * 63,
    "E" * 64,
    "g" * 64,
    7,
])
def test_malformed_historical_provider_receipt_hash_fails_closed(
    operation_data, custody_data, request_sha256,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["receipt_rows"][0]["dispatch_request_sha256"] = request_sha256

    with pytest.raises(
        bootstrap.BootstrapBlocked,
        match="CUSTODY_PROVIDER_RECEIPT_STATE_INVALID",
    ):
        bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)


@pytest.mark.parametrize("client_request_id", [
    None,
    "",
    "contains whitespace",
    "contains/slash",
    "x" * 201,
    7,
])
def test_malformed_historical_client_request_id_fails_closed(
    operation_data, custody_data, client_request_id,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["receipt_rows"][0]["dispatch_client_request_id"] = client_request_id

    with pytest.raises(
        bootstrap.BootstrapBlocked,
        match="CUSTODY_IDEMPOTENCY_STATE_INVALID",
    ):
        bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)


def test_historical_receipt_row_shape_is_exact_and_valid_boundary_is_allowed(
    operation_data, custody_data,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["receipt_rows"][0] = {
        "dispatch_request_sha256": "f" * 64,
        "dispatch_client_request_id": "A0._:-" + "x" * 194,
    }
    result = bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)
    assert result["provider_calls"] == 0
    assert result["credential_reads"] == 0

    snapshot["receipt_rows"][0]["unexpected"] = "not-canonical"
    with pytest.raises(
        bootstrap.BootstrapBlocked,
        match="CUSTODY_RECEIPT_STATE_INVALID",
    ):
        bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)


def test_available_half_open_probe_state_is_allowed(
    operation_data, custody_data,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["circuit_rows"][0].update(
        state="half_open",
        consecutive_failures=1,
        opened_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
        half_open_operation_key=None,
    )
    result = bootstrap._validate_operation_snapshot(
        snapshot,
        operation,
        custody_binding,
    )
    assert result["operation_state"] == "FRESH_OPERATION_NOT_REGISTERED / NOT_CONSUMED"


def test_structurally_valid_open_circuit_is_reported_for_policy_evaluation(
    operation_data, custody_data,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    snapshot["circuit_rows"][0].update(
        state="open",
        consecutive_failures=1,
        opened_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
    )
    result = bootstrap._validate_operation_snapshot(
        snapshot,
        operation,
        custody_binding,
    )
    assert result["target_circuit"]["state"] == "open"


@pytest.mark.parametrize(("mutation", "code"), [
    ("duplicate", "DUPLICATE_OPERATION_BLOCKED"),
    ("attempt", "CUSTODY_EXACT_ATTEMPT_COLLISION"),
    ("usage_id", "CUSTODY_EXACT_ATTEMPT_USAGE_ID_COLLISION"),
    ("receipt", "CUSTODY_PROVIDER_RECEIPT_COLLISION"),
    ("idempotency", "CUSTODY_IDEMPOTENCY_COLLISION"),
    ("complete_marker", "CUSTODY_IDEMPOTENCY_COLLISION"),
    ("operation_lineage", "CUSTODY_EXACT_OPERATION_LINEAGE_MISMATCH"),
    ("attempt_lineage", "CUSTODY_EXACT_ATTEMPT_LINEAGE_MISMATCH"),
    ("active", "CUSTODY_ACTIVE_RESERVATION_CONFLICT"),
    ("reserved", "CUSTODY_OUTSTANDING_RESERVATION"),
    ("joined_lineage", "CUSTODY_ATTEMPT_LINEAGE_INTEGRITY_INVALID"),
    ("duplicate_client", "CUSTODY_IDEMPOTENCY_COLLISION"),
    ("circuit", "CUSTODY_CIRCUIT_STATE_INVALID"),
    ("stale_half_open", "CUSTODY_CIRCUIT_STATE_INVALID"),
])
def test_precise_collision_and_integrity_failures(
    operation_data, custody_data, mutation, code,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    exact = {
        "operation_key": operation.operation_key,
        "acceptance_lineage_id": operation.acceptance_lineage_id,
        "status": "succeeded",
        "dispatch_started_at": None,
        "dispatch_request_sha256": None,
        "dispatch_client_request_id": None,
    }
    if mutation == "duplicate":
        snapshot["exact_operation"] = exact
    elif mutation == "attempt":
        snapshot["exact_attempts"] = [{
            "operation_key": operation.operation_key,
            "acceptance_lineage_id": operation.acceptance_lineage_id,
            "attempt": 1,
        }]
    elif mutation == "usage_id":
        snapshot["exact_usage_attempt"] = {
            "usage_id": "pus_collision",
            "operation_key": "unrelated-operation",
            "acceptance_lineage_id": "al-0001-" + "e" * 64,
            "attempt": 1,
        }
    elif mutation == "receipt":
        snapshot["exact_operation"] = {**exact, "dispatch_request_sha256": "1" * 64}
    elif mutation == "idempotency":
        snapshot["exact_operation"] = {**exact, "dispatch_client_request_id": "client"}
    elif mutation == "complete_marker":
        snapshot["exact_operation"] = {
            **exact,
            "dispatch_started_at": datetime(2026, 9, 28, tzinfo=timezone.utc),
            "dispatch_request_sha256": "1" * 64,
            "dispatch_client_request_id": "schema-valid-complete-marker",
        }
    elif mutation == "operation_lineage":
        snapshot["exact_operation"] = {**exact, "acceptance_lineage_id": "al-0001-" + "0" * 64}
    elif mutation == "attempt_lineage":
        snapshot["exact_attempts"] = [{
            "operation_key": operation.operation_key,
            "acceptance_lineage_id": "al-0001-" + "0" * 64,
            "attempt": 1,
        }]
    elif mutation == "active":
        snapshot["active_operations"] = [{
            "operation_key": "unrelated-active",
            "acceptance_lineage_id": "al-0001-" + "e" * 64,
            "reserved_vnd": "500",
        }]
    elif mutation == "reserved":
        snapshot["budget_rows"][0]["reserved_vnd"] = "1"
    elif mutation == "joined_lineage":
        snapshot["attempt_lineage_pairs"][0]["attempt_lineage_id"] = "al-0001-" + "0" * 64
    elif mutation == "duplicate_client":
        snapshot["receipt_rows"].append({
            "dispatch_request_sha256": "f" * 64,
            "dispatch_client_request_id": snapshot["receipt_rows"][0]["dispatch_client_request_id"],
        })
    elif mutation == "circuit":
        snapshot["circuit_rows"][0]["half_open_operation_key"] = "stale"
    elif mutation == "stale_half_open":
        snapshot["circuit_rows"][0].update(
            state="half_open",
            consecutive_failures=1,
            opened_at=datetime(2026, 9, 28, tzinfo=timezone.utc),
            half_open_operation_key="missing-active-operation",
        )
    with pytest.raises(bootstrap.BootstrapBlocked, match=code):
        bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)


@pytest.mark.parametrize(("mutation", "code"), [
    ("database", "CUSTODY_POSTGRES_IDENTITY_MISMATCH"),
    ("oid", "CUSTODY_POSTGRES_IDENTITY_MISMATCH"),
    ("system", "CUSTODY_POSTGRES_IDENTITY_MISMATCH"),
    ("role", "CUSTODY_POSTGRES_IDENTITY_MISMATCH"),
    ("version", "CUSTODY_POSTGRES_VERSION_MISMATCH"),
    ("migration", "CUSTODY_MIGRATION_HEAD_MISMATCH"),
    ("control", "CUSTODY_CONTROL_STATE_INVALID"),
])
def test_postgres_identity_and_control_fail_closed(
    operation_data, custody_data, mutation, code,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    snapshot = _snapshot(operation, custody_binding)
    if mutation == "database":
        snapshot["identity"]["database_name"] = "wrong"
    elif mutation == "oid":
        snapshot["identity"]["database_oid"] = 9
    elif mutation == "system":
        snapshot["identity"]["system_identifier"] = "9"
    elif mutation == "role":
        snapshot["identity"]["database_role"] = custody.RUNTIME_ROLE
    elif mutation == "version":
        snapshot["identity"]["version_num"] = "150015"
    elif mutation == "migration":
        snapshot["migration_head"] = "0014"
    elif mutation == "control":
        snapshot["control_rows"] = []
    with pytest.raises(bootstrap.BootstrapBlocked, match=code):
        bootstrap._validate_operation_snapshot(snapshot, operation, custody_binding)


def test_source_qualification_precedes_database_access(
    operation_data, custody_data, monkeypatch,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    engine = AsyncMock()
    monkeypatch.setattr(
        bootstrap,
        "verify_bound_source",
        lambda *_: (_ for _ in ()).throw(
            bootstrap.BootstrapBlocked("BOOTSTRAP_SOURCE_COMMIT_MISMATCH")
        ),
    )
    monkeypatch.setattr(bootstrap, "create_async_engine", engine)
    with pytest.raises(bootstrap.BootstrapBlocked, match="BOOTSTRAP_SOURCE_COMMIT_MISMATCH"):
        asyncio.run(bootstrap.inspect_operation_custody(Path("."), operation, custody_binding))
    engine.assert_not_called()


def test_bound_source_success_checks_exact_tree_implementation_and_import(
    operation_data, monkeypatch,
):
    operation = _operation(operation_data)
    source = Path(bootstrap.__file__).resolve().parents[3]
    calls = []

    def lookup(_repo, *args):
        calls.append(args)
        if args == ("status", "--porcelain"):
            return ""
        if args in {
            ("rev-parse", "HEAD"),
            ("rev-parse", operation.rc_tag + "^{}"),
        }:
            return operation.rc_commit
        return "a" * 40

    monkeypatch.setattr(bootstrap, "_git", lookup)
    monkeypatch.setattr(
        bootstrap,
        "executable_tree_sha256",
        lambda _objects: operation.executable_tree_sha256,
    )
    bootstrap.verify_bound_source(source, operation)
    assert any(args[0] == "hash-object" for args in calls)
    for path in bootstrap.EXECUTABLE_TREE_PATHS:
        assert ("rev-parse", operation.rc_commit + ":" + path) in calls


@pytest.mark.parametrize(("failure", "code"), [
    ("head", "BOOTSTRAP_SOURCE_COMMIT_MISMATCH"),
    ("tag", "BOOTSTRAP_RC_TAG_MISMATCH"),
    ("dirty", "BOOTSTRAP_SOURCE_NOT_CLEAN"),
    ("tree", "BOOTSTRAP_EXECUTABLE_TREE_MISMATCH"),
    ("implementation_missing", "BOOTSTRAP_IMPLEMENTATION_NOT_IN_BOUND_RC"),
    ("implementation_blob", "BOOTSTRAP_IMPLEMENTATION_BLOB_MISMATCH"),
    ("import", "BOOTSTRAP_IMPORT_SOURCE_MISMATCH"),
])
def test_each_operation_source_guard_fails_closed(
    operation_data, monkeypatch, failure, code,
):
    operation = _operation(operation_data)
    source = Path(bootstrap.__file__).resolve().parents[3]
    if failure == "import":
        source = source / "different-checkout"

    def lookup(_repo, *args):
        if args == ("status", "--porcelain"):
            return " M arbitrary.py" if failure == "dirty" else ""
        if args == ("rev-parse", "HEAD"):
            return "b" * 40 if failure == "head" else operation.rc_commit
        if args == ("rev-parse", operation.rc_tag + "^{}"):
            return "b" * 40 if failure == "tag" else operation.rc_commit
        if args == (
            "rev-parse",
            operation.rc_commit + ":" + bootstrap.MODULE_PATH,
        ) and failure == "implementation_missing":
            raise bootstrap.BootstrapBlocked("BOOTSTRAP_SOURCE_LOOKUP_FAILED")
        if args and args[0] == "hash-object" and failure == "implementation_blob":
            return "b" * 40
        return "a" * 40

    monkeypatch.setattr(bootstrap, "_git", lookup)
    monkeypatch.setattr(
        bootstrap,
        "executable_tree_sha256",
        lambda _objects: (
            "0" * 64 if failure == "tree" else operation.executable_tree_sha256
        ),
    )
    with pytest.raises(bootstrap.BootstrapBlocked, match=code):
        bootstrap.verify_bound_source(source, operation)


@pytest.mark.parametrize(("role", "expected_user"), [
    ("qualification", custody.QUALIFICATION_ROLE),
    ("runtime", custody.RUNTIME_ROLE),
])
def test_role_specific_connection_uses_only_custody_binding(
    operation_data, custody_data, monkeypatch, role, expected_user,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    engine = SimpleNamespace(dispose=AsyncMock())
    observed = {}
    monkeypatch.setattr(bootstrap, "verify_bound_source", lambda *_: None)
    monkeypatch.setattr(bootstrap, "verify_socket_custody", lambda *_: None)

    def create(url, **kwargs):
        observed["url"] = url
        observed["kwargs"] = kwargs
        return engine

    monkeypatch.setattr(bootstrap, "create_async_engine", create)
    monkeypatch.setattr(bootstrap, "async_sessionmaker", lambda *_a, **_k: object())
    monkeypatch.setattr(
        bootstrap,
        "read_operation_custody",
        AsyncMock(return_value={"result": "safe"}),
    )
    asyncio.run(
        bootstrap.inspect_operation_custody(
            Path("."), operation, custody_binding, role=role,
        )
    )
    assert observed["url"].username == expected_user
    assert observed["url"].database == custody.DATABASE_NAME
    assert observed["url"].password is None
    assert observed["kwargs"]["connect_args"] == {"password": ""}


def test_check_only_implementation_has_no_write_or_provider_boundary():
    source = Path(bootstrap.__file__).read_text(encoding="utf-8")
    assert "REPEATABLE READ, READ ONLY" in source
    for forbidden in (
        ".add(", ".commit(", "ensure_state(", "reserve_operation(",
        "record_attempt(", "finish_operation(", "credential_resolver",
    ):
        assert forbidden not in source


def test_operation_custody_snapshot_executes_only_read_statements_and_preserves_state(
    operation_data, custody_data,
):
    operation = _operation(operation_data)
    custody_binding = _custody(custody_data)
    expected = _snapshot(operation, custody_binding)
    database_state = {
        "control_revision": 7,
        "operations": 1,
        "attempts": 1,
        "reserved_vnd": "0",
    }
    state_before = dict(database_state)
    statements = []
    get_calls = []

    class Result:
        def __init__(self, *, one=None, all_rows=()):
            self._one = one
            self._all = list(all_rows)

        def mappings(self):
            return self

        def scalars(self):
            return self

        def one(self):
            return self._one

        def all(self):
            return list(self._all)

    results = iter((
        Result(),
        Result(one=expected["identity"]),
        Result(all_rows=[expected["migration_head"]]),
        Result(all_rows=expected["control_rows"]),
        Result(all_rows=expected["exact_attempts"]),
        Result(all_rows=expected["attempt_lineage_pairs"]),
        Result(all_rows=expected["active_operations"]),
        Result(all_rows=expected["receipt_rows"]),
        Result(all_rows=expected["budget_rows"]),
        Result(all_rows=expected["circuit_rows"]),
    ))
    scalar_counts = iter(expected["counts"].values())

    class Transaction:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    class ReadOnlySession:
        def __init__(self, state):
            self.state = state

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

        def begin(self):
            return Transaction()

        async def execute(self, statement):
            statements.append(statement)
            return next(results)

        async def get(self, model, key):
            get_calls.append((model, key))
            return None

        async def scalar(self, statement):
            statements.append(statement)
            return next(scalar_counts)

    session = ReadOnlySession(database_state)
    result = asyncio.run(bootstrap.read_operation_custody(
        lambda: session,
        operation,
        custody_binding,
        expected_role=custody_binding.qualification_role,
    ))

    assert result["result"] == "OPERATION_CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED"
    assert session.state == state_before
    assert len(statements) == 15
    assert len(get_calls) == 2
    for statement in statements:
        sql = str(statement).strip().upper()
        assert sql.startswith(("SELECT", "SET TRANSACTION")), sql
        assert not sql.startswith(("INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "TRUNCATE"))


def test_windows_worktree_pointer_is_translated_not_replaced(tmp_path, monkeypatch):
    (tmp_path / ".git").write_text(
        "gitdir: C:/verified/repository/.git/worktrees/rc23\n",
        encoding="utf-8",
    )
    real_is_dir = Path.is_dir
    monkeypatch.setattr(
        Path,
        "is_dir",
        lambda path: True
        if str(path) == "/mnt/c/verified/repository/.git/worktrees/rc23"
        else real_is_dir(path),
    )
    args = bootstrap._git_argv(tmp_path, "rev-parse", "HEAD")
    if os.name == "posix":
        assert args == [
            "git",
            "--git-dir=/mnt/c/verified/repository/.git/worktrees/rc23",
            "--work-tree=" + str(tmp_path),
            "rev-parse",
            "HEAD",
        ]


def test_cli_has_no_execution_switch(monkeypatch):
    monkeypatch.setattr("sys.argv", ["bootstrap", "--dispatch"])
    with pytest.raises(SystemExit):
        bootstrap.main()
