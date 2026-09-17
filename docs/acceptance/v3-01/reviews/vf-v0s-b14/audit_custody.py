"""Read-only RC-20 zero-call custody audit.

Run with the exact RC-20 checkout and the private, peer-auth PostgreSQL socket.
No operation identity, provider adapter, credential resolver or budget API is used.
"""

from __future__ import annotations

import argparse
import ast
import asyncio
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import asyncpg


RC_TAG = "vf-v3-01-rc20"
RC_COMMIT = "93b5441d44347c9c40b745bdfed0969880853f68"
TREE_SHA = "611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630"
LINEAGE = "al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624"
DATABASE = "vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d"
RC19_DATABASE = "vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed"
RC19_SYSTEM_ID = "7685665008963764889"
RC19_SOCKET = "/home/vang_nguyen/.local/share/npd-vf-rc19-ledger-d86a01b1a8c5/socket"
MIGRATION_HEAD = "0015_v3_01_dispatch"
BOOTSTRAP_PATH = "apps/api/app/provider_runtime_bootstrap.py"
RUNNER_PATH = "apps/api/app/provider_single_dispatch.py"
TABLES = (
    "provider_safety_operations",
    "provider_safety_attempts",
    "provider_safety_budget_days",
    "provider_safety_circuits",
    "provider_safety_budget_alerts",
    "provider_usage",
    "idempotency_keys",
    "cost_records",
)


def private_directory(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_dir():
        raise AssertionError("CUSTODY_DIRECTORY_INVALID")
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid != os.getuid() or mode & 0o077:
        raise AssertionError("CUSTODY_OWNER_OR_MODE_INVALID")
    return {"path": str(path), "uid": info.st_uid, "mode": oct(mode)}


async def inspect(args: argparse.Namespace) -> dict[str, object]:
    source = args.rc_source.resolve()
    sys.path.insert(0, str(source / "apps/api"))
    from app import provider_runtime_bootstrap as bootstrap  # noqa: PLC0415
    from app.provider_ci_provenance import (  # noqa: PLC0415
        EXECUTABLE_TREE_PATHS,
        executable_tree_sha256,
    )
    from app.provider_safety import derive_acceptance_lineage_id  # noqa: PLC0415

    def rc_git(*arguments: str) -> str:
        proc = subprocess.run(
            bootstrap._git_argv(source, *arguments),
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode:
            raise AssertionError("RC_SOURCE_GIT_LOOKUP_FAILED")
        return proc.stdout.strip()

    if Path(bootstrap.__file__).resolve() != (source / BOOTSTRAP_PATH).resolve():
        raise AssertionError("BOOTSTRAP_IMPORT_SOURCE_MISMATCH")
    bootstrap.verify_bound_source(source, SimpleNamespace(
        rc_tag=RC_TAG, rc_commit=RC_COMMIT, executable_tree_sha256=TREE_SHA,
    ))
    if rc_git("rev-parse", "HEAD") != RC_COMMIT or rc_git("rev-parse", RC_TAG + "^{}") != RC_COMMIT:
        raise AssertionError("RC_TAG_COMMIT_MISMATCH")
    if rc_git("status", "--porcelain"):
        raise AssertionError("RC_SOURCE_NOT_CLEAN")
    objects = {p: rc_git("rev-parse", RC_COMMIT + ":" + p) for p in EXECUTABLE_TREE_PATHS}
    if executable_tree_sha256(objects) != TREE_SHA:
        raise AssertionError("RC_EXECUTABLE_TREE_MISMATCH")
    blobs = {}
    for path in (BOOTSTRAP_PATH, RUNNER_PATH):
        expected = rc_git("rev-parse", RC_COMMIT + ":" + path)
        actual = rc_git("hash-object", "--path", path, str((source / path).resolve()))
        if expected != actual:
            raise AssertionError("RC_SOURCE_BLOB_MISMATCH")
        blobs[path] = expected
    runner = ast.parse((source / RUNNER_PATH).read_text(encoding="utf-8"))
    if not any(isinstance(node, ast.AsyncFunctionDef) and node.name == "run_single_dispatch" for node in runner.body):
        raise AssertionError("SINGLE_DISPATCH_ENTRYPOINT_ABSENT")

    lineage = derive_acceptance_lineage_id(
        rc_tag=RC_TAG, rc_commit=RC_COMMIT, provider_key="openai-transcription",
        model="whisper-1", capability="asr", sequence=1,
    )
    database = bootstrap.ledger_database_name(RC_TAG, lineage)
    if lineage != LINEAGE or database != DATABASE or database == RC19_DATABASE:
        raise AssertionError("LEDGER_LINEAGE_IDENTITY_MISMATCH")

    socket = Path(args.socket)
    root = socket.parent
    custody = {
        "root": private_directory(root),
        "socket": private_directory(socket),
        "postgres": private_directory(root / "postgres"),
    }
    bootstrap.verify_socket_custody(SimpleNamespace(socket_directory=str(socket)))
    required_operation_fields = (
        "operation_key", "authority_receipt_sha256", "bundle_sha256",
        "execution_scope_sha256", "scope_sha256",
    )
    if not all(bootstrap.BootstrapLedgerBinding.model_fields[name].is_required()
               for name in required_operation_fields):
        raise AssertionError("BOOTSTRAP_REQUIRED_FIELD_CONTRACT_CHANGED")
    connection = await asyncpg.connect(
        host=str(socket), port=args.port, user=args.role, database=DATABASE, password="",
    )
    try:
        async with connection.transaction(isolation="repeatable_read", readonly=True):
            identity = await connection.fetchrow(
                "SELECT current_database() AS database_name, current_user AS database_role, "
                "current_schema() AS schema_name, current_setting('server_version') AS server_version, "
                "current_setting('server_version_num') AS server_version_num, "
                "current_setting('listen_addresses') AS listen_addresses, "
                "current_setting('port') AS port, "
                "(SELECT oid::int FROM pg_database WHERE datname=current_database()) AS database_oid, "
                "(pg_control_system()).system_identifier::text AS system_identifier"
            )
            if identity is None:
                raise AssertionError("POSTGRES_IDENTITY_ABSENT")
            if (
                identity["database_name"] != DATABASE
                or identity["database_role"] != args.role
                or identity["schema_name"] != "public"
                or int(identity["server_version_num"]) // 10000 != 16
                or identity["listen_addresses"] != ""
                or int(identity["port"]) != args.port
                or identity["system_identifier"] == RC19_SYSTEM_ID
            ):
                raise AssertionError("POSTGRES_CUSTODY_IDENTITY_MISMATCH")
            migrations = sorted(
                row["version_num"] for row in await connection.fetch("SELECT version_num FROM alembic_version")
            )
            if migrations != [MIGRATION_HEAD]:
                raise AssertionError("MIGRATION_HEAD_MISMATCH")
            controls = await connection.fetch(
                "SELECT control_key, revision FROM provider_safety_control ORDER BY control_key"
            )
            control_state = [(row["control_key"], row["revision"]) for row in controls]
            if control_state not in ([], [("global", 0)]):
                raise AssertionError("CONTROL_SEED_INVALID")
            counts = {
                table: int(await connection.fetchval(f'SELECT count(*) FROM "{table}"'))
                for table in TABLES
            }
            if any(counts.values()):
                raise AssertionError("RC20_LEDGER_NOT_VIRGIN")
            reserved = str(await connection.fetchval(
                "SELECT coalesce(sum(reserved_vnd), 0) FROM provider_safety_budget_days"
            ))
            if reserved not in {"0", "0.0000"}:
                raise AssertionError("RC20_ACTIVE_RESERVATION")
            rc_databases = [row["datname"] for row in await connection.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'vf_vf_v3_01_rc%' ORDER BY datname"
            )]
            if rc_databases != [DATABASE]:
                raise AssertionError("RC19_RC20_DATABASE_ISOLATION_FAILED")
            hba = await connection.fetch(
                "SELECT type, auth_method, error FROM pg_hba_file_rules WHERE type IN ('local', 'host')"
            )
            if any(row["error"] for row in hba):
                raise AssertionError("POSTGRES_HBA_PARSE_ERROR")
            if not any(row["type"] == "local" and row["auth_method"] == "peer" for row in hba):
                raise AssertionError("POSTGRES_PEER_AUTH_ABSENT")
            if any(row["type"] == "host" and row["auth_method"] != "reject" for row in hba):
                raise AssertionError("POSTGRES_HOST_AUTH_NOT_REJECTED")
    finally:
        await connection.close()

    historical = await asyncpg.connect(
        host=RC19_SOCKET, port=55439, user=args.role, database=RC19_DATABASE, password="",
    )
    try:
        async with historical.transaction(isolation="repeatable_read", readonly=True):
            rc19_identity = await historical.fetchrow(
                "SELECT current_database() AS database_name, "
                "(pg_control_system()).system_identifier::text AS system_identifier"
            )
            if (
                rc19_identity is None
                or rc19_identity["database_name"] != RC19_DATABASE
                or rc19_identity["system_identifier"] != RC19_SYSTEM_ID
                or rc19_identity["system_identifier"] == identity["system_identifier"]
            ):
                raise AssertionError("RC19_RC20_SYSTEM_ISOLATION_FAILED")
    finally:
        await historical.close()

    defaults = {}
    for line in rc_git("show", RC_COMMIT + ":.env.example").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            defaults[key] = value
    if (
        defaults.get("PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED") != "true"
        or defaults.get("PROVIDER_EXTERNAL_EXECUTION_ENABLED") != "false"
        or defaults.get("PROVIDER_PAID_EXECUTION_ENABLED") != "false"
    ):
        raise AssertionError("CHECKED_IN_SAFETY_DEFAULTS_DRIFT")

    return {
        "result": "RC20_CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED",
        "rc": {"tag": RC_TAG, "commit": RC_COMMIT, "executable_tree_sha256": TREE_SHA},
        "lineage": {"id": lineage, "database": database, "identity_match": True},
        "source_blobs": blobs,
        "bootstrap_source_guard": "PASS",
        "bootstrap_socket_guard": "PASS",
        "required_operation_bound_fields": required_operation_fields,
        "postgres": {**dict(identity), "custody": custody, "transport": "PRIVATE_UNIX_SOCKET_PEER"},
        "migration_head": migrations[0],
        "control_seed": control_state,
        "virgin_state": {"classification": "VIRGIN_READY_FOR_OPERATION_REBIND", "counts": counts, "reserved_vnd": reserved},
        "isolation": {
            "rc19_database": RC19_DATABASE,
            "rc19_system_identifier": rc19_identity["system_identifier"],
            "rc20_system_identifier": identity["system_identifier"],
            "distinct_clusters": True,
            "rc19_database_absent_from_rc20_cluster": True,
        },
        "safety": {
            "kill_switch_checked_in_default": "ENGAGED", "bundle_mounted": False,
            "credential_reads": 0, "budget_reserved_vnd": "0",
            "provider_calls": 0, "production_business_writes": 0, "actual_cost_vnd": "0",
        },
        "bootstrap_operation_bound_invocation": "DEFERRED_REQUIRES_OPERATION_AND_AUTHORITY_FIELDS",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rc-source", type=Path, required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(inspect(args)), sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
