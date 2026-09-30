"""Zero-call operation/custody preflight for the durable provider-safety plane.

Operation identity and infrastructure custody are deliberately separate trust
domains. An :class:`OperationBinding` identifies one future call; a separately
hashed :class:`app.provider_custody.CustodyBinding` identifies PostgreSQL. This
module never resolves credentials, reserves budget, or dispatches a provider.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, or_, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256
from .provider_custody import (
    CUSTODY_TABLES,
    CustodyBinding,
    CustodyBlocked,
    load_canonical_custody_binding,
    verify_socket_custody,
)
from .provider_safety import (
    derive_acceptance_lineage_id,
    derive_provider_attempt_usage_id,
    derive_rc_bound_operation_key,
)
from .provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetAlertORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM,
    ProviderSafetyControlORM,
    ProviderSafetyOperationORM,
)


MODULE_PATH = "apps/api/app/provider_runtime_bootstrap.py"

RUNTIME_TABLE_PRIVILEGES = {
    "provider_safety_control": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "provider_safety_budget_days": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "provider_safety_circuits": frozenset({"SELECT", "INSERT", "UPDATE"}),
    "provider_safety_operations": frozenset({"SELECT", "INSERT", "UPDATE", "DELETE"}),
    "provider_safety_attempts": frozenset({"SELECT", "INSERT", "DELETE"}),
    "provider_safety_budget_alerts": frozenset({"SELECT", "INSERT"}),
}


class BootstrapBlocked(ValueError):
    """Safe code-only failure; never serialize connection or exception data."""


class OperationBinding(BaseModel):
    """Immutable operation identity; never PostgreSQL custody or authority."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[2]
    mode: Literal["OPERATION_EXECUTION"]
    environment: Literal["v3_01_acceptance_runtime"]
    rc_tag: str = Field(pattern=r"^vf-v3-01-rc[1-9][0-9]*$")
    rc_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    governance_main_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    executor_executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_plane_promotion_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_lineage_id: str = Field(pattern=r"^al-[0-9]{4}-[a-f0-9]{64}$")
    sequence: int = Field(ge=1, le=9999)
    provider_key: Literal["openai-transcription"]
    model: Literal["whisper-1"]
    capability: Literal["asr"]
    language: Literal["vi"]
    credential_alias: Literal["secret://openai/codex-video"]
    slot: Literal[1, 2]
    operation_key: str = Field(min_length=1, max_length=200)
    authority_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prepared_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    loaded_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    w1_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_transcript_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("version", "sequence", "slot", mode="before")
    @classmethod
    def json_integer_only(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("OPERATION_BINDING_INTEGER_REQUIRED")
        return value

    @model_validator(mode="after")
    def exact_identity(self) -> "OperationBinding":
        lineage = derive_acceptance_lineage_id(
            rc_tag=self.rc_tag,
            rc_commit=self.rc_commit,
            provider_key=self.provider_key,
            model=self.model,
            capability=self.capability,
            sequence=self.sequence,
        )
        operation = derive_rc_bound_operation_key(
            rc_tag=self.rc_tag,
            provider_key=self.provider_key,
            capability=self.capability,
            slot=self.slot,
            acceptance_lineage_id=lineage,
        )
        if self.acceptance_lineage_id != lineage or self.operation_key != operation:
            raise ValueError("OPERATION_BINDING_IDENTITY_MISMATCH")
        return self


def load_operation_binding(path: Path, expected_sha256: str) -> OperationBinding:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise BootstrapBlocked("OPERATION_BINDING_HASH_INVALID")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise BootstrapBlocked("OPERATION_BINDING_HASH_MISMATCH")
    try:
        return OperationBinding.model_validate_json(raw)
    except (ValueError, ValidationError):
        raise BootstrapBlocked("OPERATION_BINDING_INVALID") from None


def _git_argv(repo: Path, *args: str) -> list[str]:
    # Windows-created worktrees contain a Windows-absolute .git pointer.
    # Under WSL use its translated Git metadata directory, not another checkout.
    marker = repo / ".git"
    if os.name == "posix" and marker.is_file():
        pointer = marker.read_text(encoding="utf-8").strip()
        match = re.fullmatch(r"gitdir: ([A-Za-z]):[/\\](.+)", pointer)
        if match:
            metadata = Path("/mnt") / match[1].lower() / match[2].replace("\\", "/")
            if not metadata.is_dir():
                raise BootstrapBlocked("BOOTSTRAP_GIT_METADATA_UNREACHABLE")
            return ["git", "--git-dir=" + str(metadata), "--work-tree=" + str(repo), *args]
    return ["git", "-C", str(repo), *args]


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        _git_argv(repo, *args), capture_output=True, text=True, check=False,
    )
    if result.returncode:
        raise BootstrapBlocked("BOOTSTRAP_SOURCE_LOOKUP_FAILED")
    return result.stdout.strip()


def verify_bound_source(repo: Path, binding: OperationBinding) -> None:
    if _git(repo, "rev-parse", "HEAD") != binding.rc_commit:
        raise BootstrapBlocked("BOOTSTRAP_SOURCE_COMMIT_MISMATCH")
    if _git(repo, "rev-parse", binding.rc_tag + "^{}") != binding.rc_commit:
        raise BootstrapBlocked("BOOTSTRAP_RC_TAG_MISMATCH")
    if _git(repo, "status", "--porcelain"):
        raise BootstrapBlocked("BOOTSTRAP_SOURCE_NOT_CLEAN")
    objects = {
        path: _git(repo, "rev-parse", binding.rc_commit + ":" + path)
        for path in EXECUTABLE_TREE_PATHS
    }
    if executable_tree_sha256(objects) != binding.executable_tree_sha256:
        raise BootstrapBlocked("BOOTSTRAP_EXECUTABLE_TREE_MISMATCH")
    try:
        expected_blob = _git(repo, "rev-parse", binding.rc_commit + ":" + MODULE_PATH)
    except BootstrapBlocked:
        raise BootstrapBlocked("BOOTSTRAP_IMPLEMENTATION_NOT_IN_BOUND_RC") from None
    actual_blob = _git(
        repo,
        "hash-object",
        "--path",
        MODULE_PATH,
        str(Path(__file__).resolve()),
    )
    if actual_blob != expected_blob:
        raise BootstrapBlocked("BOOTSTRAP_IMPLEMENTATION_BLOB_MISMATCH")
    if Path(__file__).resolve() != (repo / MODULE_PATH).resolve():
        raise BootstrapBlocked("BOOTSTRAP_IMPORT_SOURCE_MISMATCH")


def qualification_ledger_url(binding: CustodyBinding) -> URL:
    """SELECT-only peer-auth endpoint used by check-only validation."""
    return URL.create(
        "postgresql+asyncpg",
        username=binding.qualification_role,
        database=binding.database_name,
        query={"host": binding.socket_directory, "port": str(binding.port)},
    )


def runtime_ledger_url(binding: CustodyBinding) -> URL:
    """Future DML endpoint; the role remains NOLOGIN until separate activation."""
    return URL.create(
        "postgresql+asyncpg",
        username=binding.runtime_role,
        database=binding.database_name,
        query={"host": binding.socket_directory, "port": str(binding.port)},
    )


def _decimal(value: object, code: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise BootstrapBlocked(code) from None
    if not result.is_finite():
        raise BootstrapBlocked(code)
    return result


def _validate_operation_snapshot(
    snapshot: dict[str, object],
    operation: OperationBinding,
    custody: CustodyBinding,
) -> dict[str, object]:
    """Validate one fresh operation without requiring an otherwise virgin DB."""
    identity = snapshot.get("identity")
    if not isinstance(identity, dict):
        raise BootstrapBlocked("CUSTODY_POSTGRES_IDENTITY_INVALID")
    expected_identity = {
        "database_name": custody.database_name,
        "database_role": snapshot.get("expected_role"),
        "schema_name": custody.schema_name,
        "database_oid": custody.database_oid,
        "system_identifier": custody.system_identifier,
    }
    if any(identity.get(key) != value for key, value in expected_identity.items()):
        raise BootstrapBlocked("CUSTODY_POSTGRES_IDENTITY_MISMATCH")
    version_num = identity.get("version_num")
    if not isinstance(version_num, str) or not version_num.isdigit() or int(version_num) // 10000 != custody.postgres_major:
        raise BootstrapBlocked("CUSTODY_POSTGRES_VERSION_MISMATCH")
    version = identity.get("version")
    if not isinstance(version, str) or not version.startswith(custody.postgres_version):
        raise BootstrapBlocked("CUSTODY_POSTGRES_VERSION_MISMATCH")
    if snapshot.get("migration_head") != custody.migration_head:
        raise BootstrapBlocked("CUSTODY_MIGRATION_HEAD_MISMATCH")

    control = snapshot.get("control_rows")
    if (
        not isinstance(control, list)
        or len(control) != 1
        or control[0].get("control_key") != "global"
        or type(control[0].get("revision")) is not int
        or control[0]["revision"] < 0
    ):
        raise BootstrapBlocked("CUSTODY_CONTROL_STATE_INVALID")

    exact = snapshot.get("exact_operation")
    attempts = snapshot.get("exact_attempts")
    if not isinstance(attempts, list):
        raise BootstrapBlocked("CUSTODY_ATTEMPT_STATE_INVALID")
    for attempt in attempts:
        if attempt.get("acceptance_lineage_id") != operation.acceptance_lineage_id:
            raise BootstrapBlocked("CUSTODY_EXACT_ATTEMPT_LINEAGE_MISMATCH")
    if attempts:
        raise BootstrapBlocked("CUSTODY_EXACT_ATTEMPT_COLLISION")
    exact_usage_attempt = snapshot.get("exact_usage_attempt")
    if exact_usage_attempt is not None:
        if not isinstance(exact_usage_attempt, dict):
            raise BootstrapBlocked("CUSTODY_ATTEMPT_STATE_INVALID")
        raise BootstrapBlocked("CUSTODY_EXACT_ATTEMPT_USAGE_ID_COLLISION")
    if exact is not None:
        if not isinstance(exact, dict):
            raise BootstrapBlocked("CUSTODY_OPERATION_STATE_INVALID")
        if exact.get("acceptance_lineage_id") != operation.acceptance_lineage_id:
            raise BootstrapBlocked("CUSTODY_EXACT_OPERATION_LINEAGE_MISMATCH")
        if exact.get("dispatch_client_request_id") is not None:
            raise BootstrapBlocked("CUSTODY_IDEMPOTENCY_COLLISION")
        if exact.get("dispatch_request_sha256") is not None or exact.get("dispatch_started_at") is not None:
            raise BootstrapBlocked("CUSTODY_PROVIDER_RECEIPT_COLLISION")
        raise BootstrapBlocked("DUPLICATE_OPERATION_BLOCKED")

    lineage_pairs = snapshot.get("attempt_lineage_pairs")
    if not isinstance(lineage_pairs, list) or any(
        pair.get("attempt_lineage_id") != pair.get("operation_lineage_id")
        for pair in lineage_pairs
    ):
        raise BootstrapBlocked("CUSTODY_ATTEMPT_LINEAGE_INTEGRITY_INVALID")

    receipt_rows = snapshot.get("receipt_rows")
    if not isinstance(receipt_rows, list):
        raise BootstrapBlocked("CUSTODY_RECEIPT_STATE_INVALID")
    client_ids: list[str] = []
    receipt_fields = {"dispatch_request_sha256", "dispatch_client_request_id"}
    for row in receipt_rows:
        if not isinstance(row, dict) or set(row) != receipt_fields:
            raise BootstrapBlocked("CUSTODY_RECEIPT_STATE_INVALID")
        request_sha256 = row.get("dispatch_request_sha256")
        if not isinstance(request_sha256, str) or re.fullmatch(r"[a-f0-9]{64}", request_sha256) is None:
            raise BootstrapBlocked("CUSTODY_PROVIDER_RECEIPT_STATE_INVALID")
        client_request_id = row.get("dispatch_client_request_id")
        if (
            not isinstance(client_request_id, str)
            or re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", client_request_id) is None
        ):
            raise BootstrapBlocked("CUSTODY_IDEMPOTENCY_STATE_INVALID")
        client_ids.append(client_request_id)
    if len(client_ids) != len(set(client_ids)):
        raise BootstrapBlocked("CUSTODY_IDEMPOTENCY_COLLISION")

    active = snapshot.get("active_operations")
    if not isinstance(active, list):
        raise BootstrapBlocked("CUSTODY_ACTIVE_OPERATION_STATE_INVALID")
    if active:
        raise BootstrapBlocked("CUSTODY_ACTIVE_RESERVATION_CONFLICT")

    budget_rows = snapshot.get("budget_rows")
    if not isinstance(budget_rows, list):
        raise BootstrapBlocked("CUSTODY_BUDGET_STATE_INVALID")
    reserved_total = Decimal("0")
    for row in budget_rows:
        if row.get("currency") != "VND":
            raise BootstrapBlocked("CUSTODY_BUDGET_STATE_INVALID")
        limit = _decimal(row.get("daily_limit_vnd"), "CUSTODY_BUDGET_STATE_INVALID")
        committed = _decimal(row.get("committed_vnd"), "CUSTODY_BUDGET_STATE_INVALID")
        reserved = _decimal(row.get("reserved_vnd"), "CUSTODY_BUDGET_STATE_INVALID")
        if min(limit, committed, reserved) < 0 or committed + reserved > limit:
            raise BootstrapBlocked("CUSTODY_BUDGET_STATE_INVALID")
        reserved_total += reserved
    if reserved_total != 0:
        raise BootstrapBlocked("CUSTODY_OUTSTANDING_RESERVATION")

    circuits = snapshot.get("circuit_rows")
    if not isinstance(circuits, list):
        raise BootstrapBlocked("CUSTODY_CIRCUIT_STATE_INVALID")
    active_operation_keys = {row.get("operation_key") for row in active}
    circuit_keys: set[tuple[object, object]] = set()
    target_circuit: dict[str, object] | None = None
    for row in circuits:
        circuit_key = (row.get("provider_key"), row.get("capability"))
        if (
            not all(isinstance(value, str) and value for value in circuit_key)
            or circuit_key in circuit_keys
            or row.get("state") not in {"closed", "open", "half_open"}
            or type(row.get("consecutive_failures")) is not int
            or row["consecutive_failures"] < 0
            or (
                row.get("state") in {"open", "half_open"}
                and row["consecutive_failures"] < 1
            )
            or (row.get("state") == "closed" and row.get("opened_at") is not None)
            or (
                row.get("state") in {"open", "half_open"}
                and (
                    not isinstance(row.get("opened_at"), datetime)
                    or row["opened_at"].tzinfo is None
                )
            )
            or (row.get("state") != "half_open" and row.get("half_open_operation_key") is not None)
            or (
                row.get("half_open_operation_key") is not None
                and row.get("half_open_operation_key") not in active_operation_keys
            )
        ):
            raise BootstrapBlocked("CUSTODY_CIRCUIT_STATE_INVALID")
        circuit_keys |= {circuit_key}
        if circuit_key == (operation.provider_key, operation.capability):
            target_circuit = dict(row)

    counts = snapshot.get("counts")
    expected_count_keys = {"operations", "attempts", "budget_days", "circuits", "budget_alerts"}
    if (
        not isinstance(counts, dict)
        or set(counts) != expected_count_keys
        or any(type(value) is not int or value < 0 for value in counts.values())
    ):
        raise BootstrapBlocked("CUSTODY_COUNT_STATE_INVALID")

    return {
        **snapshot,
        "result": "OPERATION_CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED",
        "operation_state": "FRESH_OPERATION_NOT_REGISTERED / NOT_CONSUMED",
        "exact_operation_attempts": 0,
        "provider_request_receipt": "ABSENT_FOR_EXACT_OPERATION",
        "idempotency_collision": False,
        "active_reservation": "NONE",
        "reserved_vnd": str(reserved_total),
        "target_circuit": target_circuit or {
            "provider_key": operation.provider_key,
            "capability": operation.capability,
            "state": "closed",
            "consecutive_failures": 0,
            "opened_at": None,
            "half_open_operation_key": None,
        },
        "bundle_mounted": False,
        "credential_reads": 0,
        "provider_calls": 0,
        "authority_granted": False,
    }


async def read_operation_custody(
    session_factory: async_sessionmaker,
    operation: OperationBinding,
    custody: CustodyBinding,
    *,
    expected_role: str,
) -> dict[str, object]:
    """Read exact-operation and global safety state in one read-only snapshot."""
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        identity = (await session.execute(text(
            "SELECT current_database() AS database_name, current_user AS database_role, "
            "current_schema() AS schema_name, current_setting('server_version_num') AS version_num, "
            "current_setting('server_version') AS version, "
            "(SELECT oid::int FROM pg_database WHERE datname=current_database()) AS database_oid, "
            "(pg_control_system()).system_identifier::text AS system_identifier"
        ))).mappings().one()
        # The runtime role is intentionally confined to the six custody
        # tables.  Migration-table inspection belongs to the SELECT-only
        # qualification role and the independently sealed CustodyBinding.
        migration = (
            [custody.migration_head]
            if expected_role == custody.runtime_role
            else (await session.execute(text(
                "SELECT version_num FROM alembic_version"
            ))).scalars().all()
        )
        runtime_security = None
        if expected_role == custody.runtime_role:
            role = (await session.execute(text(
                "SELECT rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                "rolreplication, rolbypassrls FROM pg_roles WHERE rolname=current_user"
            ))).mappings().one()
            memberships = (await session.execute(text(
                "SELECT parent.rolname FROM pg_auth_members m "
                "JOIN pg_roles parent ON parent.oid=m.roleid "
                "JOIN pg_roles member ON member.oid=m.member "
                "WHERE member.rolname=current_user ORDER BY parent.rolname"
            ))).scalars().all()
            table_rows = (await session.execute(text(
                "SELECT c.relname AS table_name, "
                "has_table_privilege(current_user,c.oid,'SELECT') AS can_select, "
                "has_table_privilege(current_user,c.oid,'INSERT') AS can_insert, "
                "has_table_privilege(current_user,c.oid,'UPDATE') AS can_update, "
                "has_table_privilege(current_user,c.oid,'DELETE') AS can_delete, "
                "has_table_privilege(current_user,c.oid,'TRUNCATE') AS can_truncate, "
                "has_table_privilege(current_user,c.oid,'REFERENCES') AS can_references, "
                "has_table_privilege(current_user,c.oid,'TRIGGER') AS can_trigger "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='r' ORDER BY c.relname"
            ))).mappings().all()
            sequences = (await session.execute(text(
                "SELECT c.relname AS sequence_name, "
                "has_sequence_privilege(current_user,c.oid,'USAGE') AS can_usage, "
                "has_sequence_privilege(current_user,c.oid,'SELECT') AS can_select, "
                "has_sequence_privilege(current_user,c.oid,'UPDATE') AS can_update "
                "FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace "
                "WHERE n.nspname='public' AND c.relkind='S' ORDER BY c.relname"
            ))).mappings().all()
            runtime_security = {
                "role": dict(role),
                "memberships": list(memberships),
                "database_connect": bool(await session.scalar(text(
                    "SELECT has_database_privilege(current_user,current_database(),'CONNECT')"
                ))),
                "database_create": bool(await session.scalar(text(
                    "SELECT has_database_privilege(current_user,current_database(),'CREATE')"
                ))),
                "database_temporary": bool(await session.scalar(text(
                    "SELECT has_database_privilege(current_user,current_database(),'TEMP')"
                ))),
                "schema_usage": bool(await session.scalar(text(
                    "SELECT has_schema_privilege(current_user,current_schema(),'USAGE')"
                ))),
                "schema_create": bool(await session.scalar(text(
                    "SELECT has_schema_privilege(current_user,current_schema(),'CREATE')"
                ))),
                "tables": [dict(row) for row in table_rows],
                "sequences": [dict(row) for row in sequences],
            }
        control_rows = (await session.execute(
            select(ProviderSafetyControlORM.control_key, ProviderSafetyControlORM.revision)
        )).mappings().all()
        exact_model = await session.get(ProviderSafetyOperationORM, operation.operation_key)
        exact_operation = None if exact_model is None else {
            "operation_key": exact_model.operation_key,
            "acceptance_lineage_id": exact_model.acceptance_lineage_id,
            "status": exact_model.status,
            "dispatch_started_at": exact_model.dispatch_started_at,
            "dispatch_request_sha256": exact_model.dispatch_request_sha256,
            "dispatch_client_request_id": exact_model.dispatch_client_request_id,
        }
        exact_attempts = list((await session.execute(
            select(
                ProviderSafetyAttemptORM.operation_key,
                ProviderSafetyAttemptORM.acceptance_lineage_id,
                ProviderSafetyAttemptORM.attempt,
            ).where(ProviderSafetyAttemptORM.operation_key == operation.operation_key)
        )).mappings().all())
        exact_usage_model = await session.get(
            ProviderSafetyAttemptORM,
            derive_provider_attempt_usage_id(operation.operation_key, 1),
        )
        exact_usage_attempt = None if exact_usage_model is None else {
            "usage_id": exact_usage_model.usage_id,
            "operation_key": exact_usage_model.operation_key,
            "acceptance_lineage_id": exact_usage_model.acceptance_lineage_id,
            "attempt": exact_usage_model.attempt,
        }
        attempt_lineage_pairs = list((await session.execute(
            select(
                ProviderSafetyAttemptORM.acceptance_lineage_id.label("attempt_lineage_id"),
                ProviderSafetyOperationORM.acceptance_lineage_id.label("operation_lineage_id"),
            ).join(
                ProviderSafetyOperationORM,
                ProviderSafetyOperationORM.operation_key == ProviderSafetyAttemptORM.operation_key,
            )
        )).mappings().all())
        active_operations = list((await session.execute(
            select(
                ProviderSafetyOperationORM.operation_key,
                ProviderSafetyOperationORM.acceptance_lineage_id,
                ProviderSafetyOperationORM.reserved_vnd,
            ).where(ProviderSafetyOperationORM.status == "reserved")
        )).mappings().all())
        receipt_rows = list((await session.execute(
            select(
                ProviderSafetyOperationORM.dispatch_request_sha256,
                ProviderSafetyOperationORM.dispatch_client_request_id,
            ).where(or_(
                ProviderSafetyOperationORM.dispatch_request_sha256.is_not(None),
                ProviderSafetyOperationORM.dispatch_client_request_id.is_not(None),
            ))
        )).mappings().all())
        budget_rows = list((await session.execute(select(
            ProviderSafetyBudgetDayORM.currency,
            ProviderSafetyBudgetDayORM.daily_limit_vnd,
            ProviderSafetyBudgetDayORM.committed_vnd,
            ProviderSafetyBudgetDayORM.reserved_vnd,
        ))).mappings().all())
        circuit_rows = list((await session.execute(select(
            ProviderSafetyCircuitORM.provider_key,
            ProviderSafetyCircuitORM.capability,
            ProviderSafetyCircuitORM.state,
            ProviderSafetyCircuitORM.consecutive_failures,
            ProviderSafetyCircuitORM.opened_at,
            ProviderSafetyCircuitORM.half_open_operation_key,
        ))).mappings().all())
        counts: dict[str, int] = {}
        for label, orm in (
            ("operations", ProviderSafetyOperationORM),
            ("attempts", ProviderSafetyAttemptORM),
            ("budget_days", ProviderSafetyBudgetDayORM),
            ("circuits", ProviderSafetyCircuitORM),
            ("budget_alerts", ProviderSafetyBudgetAlertORM),
        ):
            counts[label] = int(await session.scalar(select(func.count()).select_from(orm)) or 0)
        snapshot: dict[str, object] = {
            "identity": dict(identity),
            "expected_role": expected_role,
            "migration_head": migration[0] if len(migration) == 1 else None,
            "control_rows": [dict(row) for row in control_rows],
            "exact_operation": exact_operation,
            "exact_attempts": [dict(row) for row in exact_attempts],
            "exact_usage_attempt": exact_usage_attempt,
            "attempt_lineage_pairs": [dict(row) for row in attempt_lineage_pairs],
            "active_operations": [dict(row) for row in active_operations],
            "receipt_rows": [dict(row) for row in receipt_rows],
            "budget_rows": [dict(row) for row in budget_rows],
            "circuit_rows": [dict(row) for row in circuit_rows],
            "counts": counts,
            "runtime_security": runtime_security,
        }
        return _validate_operation_snapshot(snapshot, operation, custody)


def verify_runtime_role_security(snapshot: dict[str, object]) -> None:
    """Reject inherited, excessive, or incomplete live runtime privileges."""
    security = snapshot.get("runtime_security")
    if not isinstance(security, dict):
        raise BootstrapBlocked("RUNTIME_ROLE_SECURITY_MISSING")
    role = security.get("role")
    if not isinstance(role, dict) or role != {
        "rolcanlogin": True,
        "rolsuper": False,
        "rolcreatedb": False,
        "rolcreaterole": False,
        "rolreplication": False,
        "rolbypassrls": False,
    }:
        raise BootstrapBlocked("RUNTIME_ROLE_ATTRIBUTES_INVALID")
    if security.get("memberships") != []:
        raise BootstrapBlocked("RUNTIME_ROLE_MEMBERSHIP_FORBIDDEN")
    if (
        security.get("database_connect") is not True
        or security.get("database_create") is not False
        or security.get("database_temporary") is not False
        or security.get("schema_usage") is not True
        or security.get("schema_create") is not False
    ):
        raise BootstrapBlocked("RUNTIME_ROLE_DATABASE_PRIVILEGES_INVALID")
    tables = security.get("tables")
    if not isinstance(tables, list):
        raise BootstrapBlocked("RUNTIME_ROLE_TABLE_PRIVILEGES_INVALID")
    seen: set[str] = set()
    columns = {
        "SELECT": "can_select", "INSERT": "can_insert", "UPDATE": "can_update",
        "DELETE": "can_delete", "TRUNCATE": "can_truncate",
        "REFERENCES": "can_references", "TRIGGER": "can_trigger",
    }
    for row in tables:
        if not isinstance(row, dict) or not isinstance(row.get("table_name"), str):
            raise BootstrapBlocked("RUNTIME_ROLE_TABLE_PRIVILEGES_INVALID")
        name = row["table_name"]
        allowed = RUNTIME_TABLE_PRIVILEGES.get(name, frozenset())
        actual = frozenset(privilege for privilege, key in columns.items() if row.get(key) is True)
        if actual != allowed:
            raise BootstrapBlocked("RUNTIME_ROLE_TABLE_PRIVILEGES_INVALID")
        seen |= {name}
    if not set(CUSTODY_TABLES) <= seen:
        raise BootstrapBlocked("RUNTIME_ROLE_TABLE_PRIVILEGES_INVALID")
    sequences = security.get("sequences")
    if not isinstance(sequences, list) or any(
        not isinstance(row, dict)
        or any(row.get(key) is not False for key in ("can_usage", "can_select", "can_update"))
        for row in sequences
    ):
        raise BootstrapBlocked("RUNTIME_ROLE_SEQUENCE_PRIVILEGES_INVALID")


async def inspect_operation_custody(
    repo: Path,
    operation: OperationBinding,
    custody: CustodyBinding,
    *,
    role: Literal["qualification", "runtime"] = "qualification",
) -> dict[str, object]:
    """Verify source, dedicated socket identity and one zero-write snapshot."""
    verify_bound_source(repo, operation)
    try:
        verify_socket_custody(custody)
    except CustodyBlocked as exc:
        raise BootstrapBlocked(str(exc)) from None
    expected_role = custody.qualification_role if role == "qualification" else custody.runtime_role
    url = qualification_ledger_url(custody) if role == "qualification" else runtime_ledger_url(custody)
    engine = create_async_engine(
        url,
        echo=False,
        pool_pre_ping=True,
        connect_args={"password": ""},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        return await read_operation_custody(
            factory,
            operation,
            custody,
            expected_role=expected_role,
        )
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-call operation/custody inspection only")
    parser.add_argument("--operation-binding", type=Path, required=True)
    parser.add_argument("--operation-binding-sha256", required=True)
    parser.add_argument("--custody-binding", type=Path, required=True)
    parser.add_argument("--custody-binding-sha256", required=True)
    parser.add_argument("--rc-source", type=Path, required=True)
    args = parser.parse_args()
    try:
        operation = load_operation_binding(args.operation_binding, args.operation_binding_sha256)
        custody = load_canonical_custody_binding(
            args.custody_binding,
            args.custody_binding_sha256,
        )
        result = asyncio.run(inspect_operation_custody(args.rc_source, operation, custody))
    except (BootstrapBlocked, CustodyBlocked) as exc:
        print(json.dumps({
            "result": "BLOCKED",
            "code": str(exc),
            "provider_calls": 0,
            "credential_reads": 0,
            "budget_reserved_vnd": "0",
        }))
        return 2
    except Exception as exc:
        print(json.dumps({
            "result": "BLOCKED",
            "code": "BOOTSTRAP_FAILED",
            "exception_type": type(exc).__name__,
        }))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
