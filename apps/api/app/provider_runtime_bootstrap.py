"""Zero-call custody phase for the existing durable provider-safety plane.

This module has no credential resolver, adapter, reservation or dispatch entrypoint.
It does not replace ProviderSafetyRepository/Controller or define a new gate schema.
The bound RC must contain this exact implementation before bootstrap can be valid.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import stat
import subprocess
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from .provider_ci_provenance import EXECUTABLE_TREE_PATHS, executable_tree_sha256
from .provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key
from .provider_safety_db import (
    ProviderSafetyAttemptORM,
    ProviderSafetyBudgetAlertORM,
    ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM,
    ProviderSafetyControlORM,
    ProviderSafetyOperationORM,
)
from .provider_safety_repository import ProviderSafetyRepository


MODULE_PATH = "apps/api/app/provider_runtime_bootstrap.py"


class BootstrapBlocked(ValueError):
    """Safe code-only failure; never serialize a connection URL or exception payload."""


def ledger_database_name(rc_tag: str, lineage_id: str) -> str:
    digest = hashlib.sha256((rc_tag + "\n" + lineage_id).encode("utf-8")).hexdigest()
    return "vf_" + rc_tag.replace("-", "_") + "_" + digest[:32]


class BootstrapLedgerBinding(BaseModel):
    """Non-secret endpoint/custody configuration, not execution authority."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1]
    mode: Literal["ZERO_CALL_CUSTODY_ONLY"]
    environment: Literal["v3_01_acceptance_runtime"]
    rc_tag: str = Field(pattern=r"^vf-v3-01-rc[1-9][0-9]*$")
    rc_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    governance_main_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    executable_tree_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    acceptance_lineage_id: str = Field(pattern=r"^al-[0-9]{4}-[a-f0-9]{64}$")
    sequence: int = Field(ge=1, le=9999)
    provider_key: Literal["openai-transcription"]
    model: Literal["whisper-1"]
    capability: Literal["asr"]
    language: Literal["vi"]
    slot: Literal[1, 2]
    operation_key: str = Field(min_length=1, max_length=200)
    authority_receipt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    bundle_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    execution_scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    scope_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    w1_profile_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    prompt_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reference_transcript_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_record_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    system_identifier: str = Field(pattern=r"^[0-9]+$")
    database_oid: int = Field(gt=0)
    database_name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    database_role: str = Field(pattern=r"^[a-z][a-z0-9_]{0,62}$")
    schema_name: Literal["public"]
    postgres_major: Literal[16]
    socket_directory: str = Field(min_length=1)
    port: int = Field(ge=1, le=65535)
    kill_switch_engaged: Literal[True]
    external_execution_enabled: Literal[False]
    paid_execution_enabled: Literal[False]
    budget_reserved_vnd: Literal["0"]

    @field_validator("version", "sequence", "slot", "database_oid", "postgres_major", "port", mode="before")
    @classmethod
    def json_integer_only(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("BOOTSTRAP_INTEGER_REQUIRED")
        return value

    @field_validator("kill_switch_engaged", "external_execution_enabled", "paid_execution_enabled", mode="before")
    @classmethod
    def json_boolean_only(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("BOOTSTRAP_BOOLEAN_REQUIRED")
        return value

    @model_validator(mode="after")
    def exact_identity(self) -> "BootstrapLedgerBinding":
        lineage = derive_acceptance_lineage_id(
            rc_tag=self.rc_tag, rc_commit=self.rc_commit,
            provider_key=self.provider_key, model=self.model,
            capability=self.capability, sequence=self.sequence,
        )
        operation = derive_rc_bound_operation_key(
            rc_tag=self.rc_tag, provider_key=self.provider_key,
            capability=self.capability, slot=self.slot,
            acceptance_lineage_id=lineage,
        )
        if self.acceptance_lineage_id != lineage or self.operation_key != operation:
            raise ValueError("BOOTSTRAP_OPERATION_IDENTITY_MISMATCH")
        if self.database_name != ledger_database_name(self.rc_tag, lineage):
            raise ValueError("BOOTSTRAP_DATABASE_NAMESPACE_MISMATCH")
        if not Path(self.socket_directory).is_absolute():
            raise ValueError("BOOTSTRAP_SOCKET_NOT_ABSOLUTE")
        return self


def load_binding(path: Path, expected_sha256: str) -> BootstrapLedgerBinding:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise BootstrapBlocked("BOOTSTRAP_BINDING_HASH_INVALID")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise BootstrapBlocked("BOOTSTRAP_BINDING_HASH_MISMATCH")
    try:
        return BootstrapLedgerBinding.model_validate(json.loads(raw))
    except (ValueError, ValidationError):
        raise BootstrapBlocked("BOOTSTRAP_BINDING_INVALID") from None


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


def verify_bound_source(repo: Path, binding: BootstrapLedgerBinding) -> None:
    if _git(repo, "rev-parse", "HEAD") != binding.rc_commit:
        raise BootstrapBlocked("BOOTSTRAP_SOURCE_COMMIT_MISMATCH")
    if _git(repo, "rev-parse", binding.rc_tag + "^{}") != binding.rc_commit:
        raise BootstrapBlocked("BOOTSTRAP_RC_TAG_MISMATCH")
    if _git(repo, "status", "--porcelain"):
        raise BootstrapBlocked("BOOTSTRAP_SOURCE_NOT_CLEAN")
    objects = {p: _git(repo, "rev-parse", binding.rc_commit + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    if executable_tree_sha256(objects) != binding.executable_tree_sha256:
        raise BootstrapBlocked("BOOTSTRAP_EXECUTABLE_TREE_MISMATCH")
    try:
        expected_blob = _git(repo, "rev-parse", binding.rc_commit + ":" + MODULE_PATH)
    except BootstrapBlocked:
        raise BootstrapBlocked("BOOTSTRAP_IMPLEMENTATION_NOT_IN_BOUND_RC") from None
    actual_blob = _git(repo, "hash-object", "--path", MODULE_PATH, str(Path(__file__).resolve()))
    if actual_blob != expected_blob:
        raise BootstrapBlocked("BOOTSTRAP_IMPLEMENTATION_BLOB_MISMATCH")
    if Path(__file__).resolve() != (repo / MODULE_PATH).resolve():
        raise BootstrapBlocked("BOOTSTRAP_IMPORT_SOURCE_MISMATCH")


def verify_socket_custody(binding: BootstrapLedgerBinding) -> None:
    directory = Path(binding.socket_directory)
    if directory.is_symlink() or not directory.is_dir():
        raise BootstrapBlocked("BOOTSTRAP_SOCKET_CUSTODY_INVALID")
    info = directory.stat()
    if not hasattr(os, "getuid") or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise BootstrapBlocked("BOOTSTRAP_SOCKET_OWNER_OR_PERMISSIONS_INVALID")


def ledger_url(binding: BootstrapLedgerBinding) -> URL:
    # Unix socket + peer role only: no password, env-file or fallback endpoint.
    return URL.create(
        "postgresql+asyncpg", username=binding.database_role, database=binding.database_name,
        query={"host": binding.socket_directory, "port": str(binding.port)},
    )


async def read_custody(
    session_factory: async_sessionmaker, binding: BootstrapLedgerBinding, *, require_virgin_namespace: bool = False,
) -> dict:
    """SELECT-only primitive. Full bootstrap additionally requires verify_bound_source."""
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        identity = (await session.execute(text(
            "SELECT current_database() AS database_name, current_user AS database_role, "
            "current_schema() AS schema_name, current_setting('server_version_num') AS version, "
            "(SELECT oid::int FROM pg_database WHERE datname=current_database()) AS database_oid, "
            "(pg_control_system()).system_identifier::text AS system_identifier"
        ))).mappings().one()
        for key in ("database_name", "database_role", "schema_name", "database_oid", "system_identifier"):
            if identity[key] != getattr(binding, key):
                raise BootstrapBlocked("BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:" + key)
        if int(identity["version"]) // 10000 != binding.postgres_major:
            raise BootstrapBlocked("BOOTSTRAP_POSTGRES_VERSION_MISMATCH")
        operation = await session.get(ProviderSafetyOperationORM, binding.operation_key)
        attempts = int(await session.scalar(select(func.count()).select_from(ProviderSafetyAttemptORM)
            .where(ProviderSafetyAttemptORM.operation_key == binding.operation_key)) or 0)
        control = await session.get(ProviderSafetyControlORM, ProviderSafetyRepository.CONTROL_KEY)
        control_rows = int(await session.scalar(select(func.count()).select_from(ProviderSafetyControlORM)) or 0)
        if control_rows > 1 or (control_rows == 1 and control is None):
            raise BootstrapBlocked("BOOTSTRAP_CONTROL_NAMESPACE_INVALID")
        counts = {}
        for label, orm in (
            ("operations", ProviderSafetyOperationORM), ("attempts", ProviderSafetyAttemptORM),
            ("budget_days", ProviderSafetyBudgetDayORM), ("circuits", ProviderSafetyCircuitORM),
            ("budget_alerts", ProviderSafetyBudgetAlertORM),
        ):
            counts[label] = int(await session.scalar(select(func.count()).select_from(orm)) or 0)
        foreign_operations = int(await session.scalar(select(func.count()).select_from(ProviderSafetyOperationORM)
            .where((ProviderSafetyOperationORM.acceptance_lineage_id != binding.acceptance_lineage_id)
                | ProviderSafetyOperationORM.acceptance_lineage_id.is_(None))) or 0)
        foreign_attempts = int(await session.scalar(select(func.count()).select_from(ProviderSafetyAttemptORM)
            .where((ProviderSafetyAttemptORM.acceptance_lineage_id != binding.acceptance_lineage_id)
                | ProviderSafetyAttemptORM.acceptance_lineage_id.is_(None))) or 0)
        active_operations = int(await session.scalar(select(func.count()).select_from(ProviderSafetyOperationORM)
            .where(ProviderSafetyOperationORM.status == "reserved")) or 0)
        reserved = str(await session.scalar(select(func.coalesce(func.sum(ProviderSafetyBudgetDayORM.reserved_vnd), 0))))
        if operation is not None or attempts:
            raise BootstrapBlocked("DUPLICATE_OPERATION_BLOCKED")
        if foreign_operations or foreign_attempts:
            raise BootstrapBlocked("BOOTSTRAP_CROSS_LINEAGE_STATE")
        if active_operations:
            raise BootstrapBlocked("BOOTSTRAP_ACTIVE_RESERVATION")
        try:
            numeric_reserved = Decimal(reserved)
        except InvalidOperation:
            raise BootstrapBlocked("BOOTSTRAP_RESERVED_AMOUNT_INVALID") from None
        if not numeric_reserved.is_finite() or numeric_reserved != 0:
            raise BootstrapBlocked("BOOTSTRAP_OUTSTANDING_RESERVATION")
        if require_virgin_namespace and any(counts.values()):
            raise BootstrapBlocked("BOOTSTRAP_NAMESPACE_NOT_VIRGIN")
        return {
            "identity": dict(identity), "counts": counts,
            "control_present": control is not None,
            "control_rows": control_rows,
            "control_revision": None if control is None else control.revision,
            "foreign_operations": foreign_operations, "foreign_attempts": foreign_attempts,
            "active_operations": active_operations,
            "operation_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
            "exact_operation_attempts": attempts, "reserved_vnd": reserved,
            "provider_request_receipt_mapping": "NO_OPERATION_OR_ATTEMPT_IN_THIS_BOUND_NAMESPACE",
            "active_reservation": "NONE_IN_THIS_BOUND_NAMESPACE",
            "bundle_mounted": False, "credential_reads": 0, "provider_calls": 0,
        }


async def bootstrap_custody(
    repo: Path, binding: BootstrapLedgerBinding, *, initialize_control: bool = False,
    require_virgin_namespace: bool = False,
) -> dict:
    # Source qualification occurs before any database access or metadata write.
    verify_bound_source(repo, binding)
    verify_socket_custody(binding)
    # An explicit empty database password prevents asyncpg from consulting
    # PGPASSWORD or a password file. This endpoint is private peer-auth only.
    engine = create_async_engine(
        ledger_url(binding), echo=False, pool_pre_ping=True,
        connect_args={"password": ""},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        before = await read_custody(factory, binding, require_virgin_namespace=require_virgin_namespace)
        wrote = 0
        if not before["control_present"]:
            if not initialize_control:
                raise BootstrapBlocked("BOOTSTRAP_CONTROL_NOT_INITIALIZED")
            if any(before["counts"].values()):
                raise BootstrapBlocked("BOOTSTRAP_ORPHAN_LEDGER_WITHOUT_CONTROL")
            # Existing canonical metadata registration only. No operation row or reservation.
            await ProviderSafetyRepository(factory).ensure_state()
            wrote = 1
        result = await read_custody(factory, binding, require_virgin_namespace=require_virgin_namespace)
        if not result["control_present"] or result["control_revision"] is None or result["control_revision"] < 0:
            raise BootstrapBlocked("BOOTSTRAP_CONTROL_STATE_INVALID")
        result.update({
            "result": "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED",
            "ledger_bootstrap_write": {"ensure_state_invoked": bool(wrote), "observed_control_presence_change": wrote, "operation_rows": 0, "reservation_vnd": "0"},
            "kill_switch": "ENGAGED", "external_execution": False, "paid_execution": False,
            "dispatch_entrypoint": None, "authority_created_or_changed": False,
        })
        return result
    finally:
        await engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Zero-call bootstrap/custody only; never dispatches")
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--expected-binding-sha256", required=True)
    parser.add_argument("--rc-source", type=Path, required=True)
    parser.add_argument("--initialize-control", action="store_true")
    parser.add_argument("--require-virgin-namespace", action="store_true")
    args = parser.parse_args()
    try:
        binding = load_binding(args.binding, args.expected_binding_sha256)
        result = asyncio.run(bootstrap_custody(
            args.rc_source, binding, initialize_control=args.initialize_control,
            require_virgin_namespace=args.require_virgin_namespace,
        ))
    except BootstrapBlocked as exc:
        print(json.dumps({"result": "BLOCKED", "code": str(exc), "provider_calls": 0, "credential_reads": 0}))
        return 2
    except Exception as exc:
        print(json.dumps({"result": "BLOCKED", "code": "BOOTSTRAP_FAILED", "exception_type": type(exc).__name__}))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
