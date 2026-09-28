"""Infrastructure-only PostgreSQL custody qualification.

This module deliberately has no operation, authority, credential, reservation,
or provider-dispatch model.  A custody receipt proves only the identity and
read-only inspectability of the durable ProviderSafetyRepository database.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from sqlalchemy import text
from sqlalchemy.engine import URL
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import async_sessionmaker

DATABASE_NAME = "vf_provider_custody_v3_01"
MIGRATION_HEAD = "0015_v3_01_dispatch"
SOCKET_DIRECTORY = "/run/npd-video-factory/provider-custody/postgresql"
DATA_ROOT = "/var/lib/npd-video-factory/provider-custody/postgresql/16/data"
BACKUP_ROOT = "/var/backups/npd-video-factory/provider-custody/postgresql-16"
PORT = 55432
RUNTIME_ROLE = "vf_executor_runtime"
QUALIFICATION_ROLE = "vf_custody_qualifier"
CUSTODY_TABLES = (
    "provider_safety_control",
    "provider_safety_budget_days",
    "provider_safety_circuits",
    "provider_safety_operations",
    "provider_safety_attempts",
    "provider_safety_budget_alerts",
)


class CustodyBlocked(ValueError):
    """Code-only custody failure with no operation/authority dependency."""


class PackageIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9+.-]+$")
    version: str = Field(min_length=1, max_length=160)
    repository_origin: Literal["apt.postgresql.org/pub/repos/apt"]
    archive_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    kind: Literal["logical_backup", "physical_backup", "off_host_backup", "restore_test"]
    path: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def path_is_absolute(self) -> "EvidenceReference":
        if not self.path.startswith("/"):
            raise ValueError("CUSTODY_EVIDENCE_PATH_NOT_ABSOLUTE")
        return self


class CustodyBinding(BaseModel):
    """Immutable infrastructure identity; never provider-call authority."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    version: Literal[1]
    mode: Literal["CUSTODY_ONLY"]
    authority_granted: Literal[False]
    postgres_major: Literal[16]
    postgres_version: Literal["16.15"]
    packages: tuple[PackageIdentity, ...] = Field(min_length=2)
    system_identifier: str = Field(pattern=r"^[0-9]+$")
    database_name: Literal[DATABASE_NAME]
    database_oid: int = Field(gt=0)
    schema_name: Literal["public"]
    migration_head: Literal[MIGRATION_HEAD]
    socket_directory: Literal[SOCKET_DIRECTORY]
    port: Literal[PORT]
    data_root: Literal[DATA_ROOT]
    backup_root: Literal[BACKUP_ROOT]
    custody_tables: tuple[str, ...]
    postgres_service_user: str = Field(pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    postgres_service_uid: int = Field(ge=1)
    postgres_service_gid: int = Field(ge=1)
    socket_group: str = Field(pattern=r"^[a-z_][a-z0-9_-]{0,31}$")
    socket_group_gid: int = Field(ge=1)
    socket_directory_mode: Literal["2750"]
    socket_mode: Literal["0770"]
    runtime_role: Literal[RUNTIME_ROLE]
    runtime_login: Literal[False]
    qualification_role: Literal[QUALIFICATION_ROLE]
    qualification_access: Literal["SELECT_ONLY"]
    evidence_references: tuple[EvidenceReference, ...] = Field(min_length=4, max_length=4)

    @field_validator(
        "version", "postgres_major", "database_oid", "port", "postgres_service_uid",
        "postgres_service_gid", "socket_group_gid", mode="before",
    )
    @classmethod
    def integers_are_json_integers(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("CUSTODY_INTEGER_REQUIRED")
        return value

    @field_validator("authority_granted", "runtime_login", mode="before")
    @classmethod
    def booleans_are_json_booleans(cls, value: object) -> object:
        if type(value) is not bool:
            raise ValueError("CUSTODY_BOOLEAN_REQUIRED")
        return value

    @model_validator(mode="after")
    def exact_contract(self) -> "CustodyBinding":
        if self.custody_tables != CUSTODY_TABLES:
            raise ValueError("CUSTODY_TABLE_SET_MISMATCH")
        package_names = tuple(package.name for package in self.packages)
        if package_names != tuple(sorted(set(package_names))):
            raise ValueError("CUSTODY_PACKAGE_SET_NOT_CANONICAL")
        if not {"postgresql-16", "postgresql-client-16"} <= set(package_names):
            raise ValueError("CUSTODY_REQUIRED_PACKAGES_MISSING")
        evidence_kinds = tuple(reference.kind for reference in self.evidence_references)
        if set(evidence_kinds) != {"logical_backup", "physical_backup", "off_host_backup", "restore_test"}:
            raise ValueError("CUSTODY_EVIDENCE_SET_MISMATCH")
        return self


def load_custody_binding(path: Path, expected_sha256: str) -> CustodyBinding:
    if not re.fullmatch(r"[a-f0-9]{64}", expected_sha256):
        raise CustodyBlocked("CUSTODY_BINDING_HASH_INVALID")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise CustodyBlocked("CUSTODY_BINDING_HASH_MISMATCH")
    try:
        return CustodyBinding.model_validate_json(raw)
    except (ValueError, ValidationError):
        raise CustodyBlocked("CUSTODY_BINDING_INVALID") from None


def custody_url(binding: CustodyBinding) -> URL:
    return URL.create(
        "postgresql+asyncpg",
        username=binding.qualification_role,
        database=binding.database_name,
        query={"host": binding.socket_directory, "port": str(binding.port)},
    )


def _require_canonical_path(path: Path) -> None:
    if not path.is_absolute():
        raise CustodyBlocked("CUSTODY_SOCKET_PATH_NOT_ABSOLUTE")
    try:
        if path.resolve(strict=True) != path:
            raise CustodyBlocked("CUSTODY_SOCKET_PATH_SUBSTITUTION")
        current = path
        while True:
            if stat.S_ISLNK(current.lstat().st_mode):
                raise CustodyBlocked("CUSTODY_SOCKET_PATH_SUBSTITUTION")
            if current.parent == current:
                break
            current = current.parent
    except CustodyBlocked:
        raise
    except OSError:
        raise CustodyBlocked("CUSTODY_SOCKET_PATH_INVALID") from None


def verify_socket_custody(binding: CustodyBinding) -> None:
    """Bind the endpoint to the dedicated PostgreSQL service and socket group."""
    directory = Path(binding.socket_directory)
    _require_canonical_path(directory)
    directory_info = directory.stat()
    if not stat.S_ISDIR(directory_info.st_mode):
        raise CustodyBlocked("CUSTODY_SOCKET_DIRECTORY_INVALID")
    if (
        directory_info.st_uid != binding.postgres_service_uid
        or directory_info.st_gid != binding.socket_group_gid
        or stat.S_IMODE(directory_info.st_mode) != int(binding.socket_directory_mode, 8)
    ):
        raise CustodyBlocked("CUSTODY_SOCKET_DIRECTORY_IDENTITY_INVALID")
    socket_path = directory / f".s.PGSQL.{binding.port}"
    _require_canonical_path(socket_path)
    socket_info = socket_path.stat()
    if not stat.S_ISSOCK(socket_info.st_mode):
        raise CustodyBlocked("CUSTODY_SOCKET_TYPE_INVALID")
    if (
        socket_info.st_uid != binding.postgres_service_uid
        or socket_info.st_gid != binding.socket_group_gid
        or stat.S_IMODE(socket_info.st_mode) != int(binding.socket_mode, 8)
    ):
        raise CustodyBlocked("CUSTODY_SOCKET_IDENTITY_INVALID")
    if hasattr(os, "getuid") and binding.postgres_service_uid == os.getuid():
        raise CustodyBlocked("CUSTODY_POSTGRES_SERVICE_NOT_DEDICATED")


async def _negative_write_probe(session, statement: str) -> None:
    await session.execute(text("SAVEPOINT custody_negative_probe"))
    try:
        await session.execute(text(statement))
    except DBAPIError:
        await session.execute(text("ROLLBACK TO SAVEPOINT custody_negative_probe"))
        await session.execute(text("RELEASE SAVEPOINT custody_negative_probe"))
    else:
        await session.execute(text("ROLLBACK TO SAVEPOINT custody_negative_probe"))
        await session.execute(text("RELEASE SAVEPOINT custody_negative_probe"))
        raise CustodyBlocked("CUSTODY_QUALIFICATION_WRITE_SUCCEEDED")
    if str(await session.scalar(text("SHOW transaction_read_only"))).lower() != "on":
        raise CustodyBlocked("CUSTODY_TRANSACTION_NOT_READ_ONLY")
    await session.scalar(text("SELECT count(*) FROM provider_safety_control"))


async def read_custody(session_factory: async_sessionmaker, binding: CustodyBinding) -> dict:
    """Qualify identity, baseline, and strict SELECT-only access without writes."""
    async with session_factory() as session, session.begin():
        await session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
        identity = (await session.execute(text(
            "SELECT current_database() AS database_name, current_user AS database_role, "
            "current_schema() AS schema_name, current_setting('server_version_num') AS version_num, "
            "current_setting('server_version') AS version, "
            "(SELECT oid::int FROM pg_database WHERE datname=current_database()) AS database_oid, "
            "(pg_control_system()).system_identifier::text AS system_identifier"
        ))).mappings().one()
        expected = {
            "database_name": binding.database_name,
            "database_role": binding.qualification_role,
            "schema_name": binding.schema_name,
            "database_oid": binding.database_oid,
            "system_identifier": binding.system_identifier,
        }
        if any(identity[key] != value for key, value in expected.items()):
            raise CustodyBlocked("CUSTODY_POSTGRES_INSTANCE_MISMATCH")
        if int(identity["version_num"]) // 10000 != binding.postgres_major or not str(identity["version"]).startswith(binding.postgres_version):
            raise CustodyBlocked("CUSTODY_POSTGRES_VERSION_MISMATCH")
        isolation = str(await session.scalar(text("SHOW transaction_isolation"))).lower()
        read_only = str(await session.scalar(text("SHOW transaction_read_only"))).lower()
        if isolation != "repeatable read" or read_only != "on":
            raise CustodyBlocked("CUSTODY_TRANSACTION_MODE_INVALID")
        migration = (await session.execute(text("SELECT version_num FROM alembic_version"))).scalars().all()
        if migration != [binding.migration_head]:
            raise CustodyBlocked("CUSTODY_MIGRATION_HEAD_MISMATCH")
        migration_privileges = {
            privilege: bool(await session.scalar(
                text("SELECT has_table_privilege(current_user, 'public.alembic_version', :privilege)"),
                {"privilege": privilege},
            ))
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE")
        }
        if migration_privileges != {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False, "TRUNCATE": False}:
            raise CustodyBlocked("CUSTODY_MIGRATION_TABLE_PRIVILEGE_MISMATCH")
        counts: dict[str, int] = {}
        privileges: dict[str, dict[str, bool]] = {}
        for table in binding.custody_tables:
            counts[table] = int(await session.scalar(text(f'SELECT count(*) FROM "{table}"')) or 0)
            table_privileges = {}
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                table_privileges[privilege] = bool(await session.scalar(
                    text("SELECT has_table_privilege(current_user, :table, :privilege)"),
                    {"table": binding.schema_name + "." + table, "privilege": privilege},
                ))
            if table_privileges != {"SELECT": True, "INSERT": False, "UPDATE": False, "DELETE": False, "TRUNCATE": False}:
                raise CustodyBlocked("CUSTODY_QUALIFICATION_PRIVILEGE_MISMATCH")
            privileges[table] = table_privileges
        if bool(await session.scalar(text("SELECT has_schema_privilege(current_user, :schema, 'USAGE')"), {"schema": binding.schema_name})) is not True:
            raise CustodyBlocked("CUSTODY_SCHEMA_USAGE_MISSING")
        if bool(await session.scalar(text("SELECT has_schema_privilege(current_user, :schema, 'CREATE')"), {"schema": binding.schema_name})):
            raise CustodyBlocked("CUSTODY_SCHEMA_CREATE_PRESENT")
        database_privileges = {
            privilege: bool(await session.scalar(
                text("SELECT has_database_privilege(current_user, :database, :privilege)"),
                {"database": binding.database_name, "privilege": privilege},
            ))
            for privilege in ("CONNECT", "CREATE", "TEMP")
        }
        if database_privileges != {"CONNECT": True, "CREATE": False, "TEMP": False}:
            raise CustodyBlocked("CUSTODY_DATABASE_PRIVILEGE_MISMATCH")
        control = (await session.execute(text("SELECT control_key, revision FROM provider_safety_control"))).mappings().all()
        if len(control) != 1 or control[0]["control_key"] != "global" or control[0]["revision"] != 0:
            raise CustodyBlocked("CUSTODY_BASELINE_CONTROL_INVALID")
        if any(counts[table] for table in binding.custody_tables if table != "provider_safety_control"):
            raise CustodyBlocked("CUSTODY_BASELINE_NOT_EMPTY")
        for statement in (
            "INSERT INTO provider_safety_control (control_key, revision, updated_at) VALUES ('qualification-probe', 0, now())",
            "UPDATE provider_safety_control SET revision = revision WHERE control_key = 'global'",
            "DELETE FROM provider_safety_control WHERE control_key = 'global'",
            "CREATE TEMP TABLE custody_qualification_probe(value integer)",
        ):
            await _negative_write_probe(session, statement)
        return {
            "identity": dict(identity),
            "migration_head": migration[0],
            "counts": counts,
            "qualification_access": "SELECT_ONLY",
            "qualification_privileges": privileges,
            "qualification_migration_privileges": migration_privileges,
            "qualification_database_privileges": database_privileges,
            "transaction_isolation": isolation,
            "transaction_read_only": read_only,
            "negative_write_tests": {"INSERT": "REJECTED", "UPDATE": "REJECTED", "DELETE": "REJECTED", "DDL": "REJECTED"},
            "authority_granted": False,
            "provider_calls": 0,
            "credential_reads": 0,
            "budget_reserved_vnd": "0",
            "operation_consumption": 0,
            "actual_cost_vnd": "0",
        }
