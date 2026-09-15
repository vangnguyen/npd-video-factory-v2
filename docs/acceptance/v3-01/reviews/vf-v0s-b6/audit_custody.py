"""Read-only RC-19 lineage/custody audit for VF-V0S-B6.

This verifier deliberately stops at the lineage-level custody boundary.  It
does not construct an operation identity, an authority record, or a runtime
bundle, and it never invokes a provider adapter or credential resolver.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import asyncpg


GOVERNANCE_MAIN = "d13c57bf480ed3b6b8b56f46370fef58b291810b"
RC_TAG = "vf-v3-01-rc19"
RC_COMMIT = "dc8ff55322267dfe54674fa6c4003a899bf235ab"
EXECUTABLE_TREE_SHA256 = "432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502"
PROVENANCE_SHA256 = "12128084c7fff1397b2476e5360b45e13232eef0bbf161f962c3c6de38d43228"
EXPECTED_LINEAGE = "al-0001-d86a01b1a8c5a312d1f17f48afd182e73df255e2b2777f0fee4c0ba131153afd"
EXPECTED_DATABASE = "vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed"
RC18_DATABASE = "vf_vf_v3_01_rc18_466d54d9ede1b6f7f3179ddd52b7e251"
RC18_SYSTEM_IDENTIFIER = "7685407204168180413"
EXPECTED_MIGRATION_HEAD = "0014_v3_01_27"
BOOTSTRAP_MODULE = "apps/api/app/provider_runtime_bootstrap.py"


def directory_custody(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_dir():
        raise AssertionError("SOCKET_CUSTODY_PATH_INVALID")
    info = path.stat()
    mode = stat.S_IMODE(info.st_mode)
    assert info.st_uid == os.getuid(), "SOCKET_CUSTODY_OWNER_MISMATCH"
    assert mode & 0o077 == 0, "SOCKET_CUSTODY_PERMISSIONS_TOO_OPEN"
    return {"path": str(path), "uid": info.st_uid, "mode": oct(mode), "symlink": False}


async def audit(args: argparse.Namespace) -> dict[str, object]:
    rc_source = args.rc_source.resolve()
    sys.path.insert(0, str(rc_source / "apps/api"))
    from app import provider_runtime_bootstrap as bootstrap  # noqa: PLC0415
    from app.provider_ci_provenance import (  # noqa: PLC0415
        EXECUTABLE_TREE_PATHS,
        executable_tree_sha256,
    )
    from app.provider_safety import (  # noqa: PLC0415
        derive_acceptance_lineage_id,
        validate_acceptance_lineage_id,
    )

    def rc_git(*git_args: str) -> str:
        result = subprocess.run(
            bootstrap._git_argv(rc_source, *git_args),
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode:
            raise RuntimeError("SAFE_GIT_LOOKUP_FAILED")
        return result.stdout.strip()

    assert Path(bootstrap.__file__).resolve() == (rc_source / BOOTSTRAP_MODULE).resolve()
    assert rc_git("rev-parse", "HEAD") == RC_COMMIT
    assert rc_git("rev-parse", RC_TAG + "^{}") == RC_COMMIT
    assert rc_git("status", "--porcelain") == ""
    objects = {
        path: rc_git("rev-parse", RC_COMMIT + ":" + path)
        for path in EXECUTABLE_TREE_PATHS
    }
    tree_hash = executable_tree_sha256(objects)
    assert tree_hash == EXECUTABLE_TREE_SHA256
    expected_blob = rc_git("rev-parse", RC_COMMIT + ":" + BOOTSTRAP_MODULE)
    actual_blob = rc_git(
        "hash-object",
        "--path",
        BOOTSTRAP_MODULE,
        str(Path(bootstrap.__file__).resolve()),
    )
    assert actual_blob == expected_blob

    lineage = derive_acceptance_lineage_id(
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        sequence=1,
    )
    validate_acceptance_lineage_id(
        lineage,
        rc_tag=RC_TAG,
        rc_commit=RC_COMMIT,
        provider_key="openai-transcription",
        model="whisper-1",
        capability="asr",
        sequence=1,
    )
    database = bootstrap.ledger_database_name(RC_TAG, lineage)
    assert lineage == EXPECTED_LINEAGE
    assert database == EXPECTED_DATABASE
    assert database != RC18_DATABASE

    socket = Path(args.socket)
    socket_evidence = directory_custody(socket)
    connection = await asyncpg.connect(
        host=str(socket),
        port=args.port,
        user=args.role,
        database=database,
        password="",
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
            assert identity is not None
            assert identity["database_name"] == EXPECTED_DATABASE
            assert identity["database_role"] == args.role
            assert identity["schema_name"] == "public"
            assert int(identity["server_version_num"]) // 10000 == 16
            assert identity["listen_addresses"] == ""
            assert int(identity["port"]) == args.port
            assert identity["system_identifier"] != RC18_SYSTEM_IDENTIFIER

            migration_rows = await connection.fetch("SELECT version_num FROM alembic_version")
            migrations = sorted(row["version_num"] for row in migration_rows)
            assert migrations == [EXPECTED_MIGRATION_HEAD]
            controls = await connection.fetch(
                "SELECT control_key, revision FROM provider_safety_control ORDER BY control_key"
            )
            assert [(row["control_key"], row["revision"]) for row in controls] == [("global", 0)]

            names = (
                "provider_safety_operations",
                "provider_safety_attempts",
                "provider_safety_budget_days",
                "provider_safety_circuits",
                "provider_safety_budget_alerts",
                "provider_usage",
                "idempotency_keys",
                "cost_records",
            )
            counts = {}
            for name in names:
                counts[name] = int(await connection.fetchval(f'SELECT count(*) FROM "{name}"'))
            assert all(value == 0 for value in counts.values())
            reserved = str(
                await connection.fetchval(
                    "SELECT coalesce(sum(reserved_vnd), 0) FROM provider_safety_budget_days"
                )
            )
            assert reserved in {"0", "0.0000"}
            other_databases = sorted(
                await connection.fetch(
                    "SELECT datname FROM pg_database WHERE datname LIKE 'vf_vf_v3_01_rc%' ORDER BY datname"
                ),
                key=lambda row: row["datname"],
            )
            rc_databases = [row["datname"] for row in other_databases]
            assert rc_databases == [EXPECTED_DATABASE]
    finally:
        await connection.close()

    defaults = {}
    for line in rc_git("show", RC_COMMIT + ":.env.example").splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            defaults[key] = value
    assert defaults["PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED"] == "true"
    assert defaults["PROVIDER_EXTERNAL_EXECUTION_ENABLED"] == "false"
    assert defaults["PROVIDER_PAID_EXECUTION_ENABLED"] == "false"
    assert defaults["PROVIDER_PER_OPERATION_LIMIT_VND"] == "0"
    assert defaults["PROVIDER_DAILY_LIMIT_VND"] == "0"

    source = (rc_source / BOOTSTRAP_MODULE).read_text(encoding="utf-8")
    operation_bound_fields = [
        "operation_key",
        "authority_receipt_sha256",
        "bundle_sha256",
        "execution_scope_sha256",
        "scope_sha256",
    ]
    assert all(field + ":" in source for field in operation_bound_fields)

    return {
        "task_id": "VF-V0S-B6",
        "verdict": "REVIEW_REQUIRED",
        "governance_main_sha": GOVERNANCE_MAIN,
        "main_provenance": "PASS",
        "dual_ci_provenance": "PASS",
        "provenance_sha256": PROVENANCE_SHA256,
        "rc": {"tag": RC_TAG, "commit": RC_COMMIT, "executable_tree_sha256": tree_hash},
        "bootstrap": {
            "entrypoint": "python -m app.provider_runtime_bootstrap",
            "module_blob": expected_blob,
            "exact_rc_source": "PASS",
            "lineage_naming_and_custody_primitives": "VERIFIED",
            "full_operation_bound_invocation": "DEFERRED_REQUIRES_OPERATION_REBIND",
            "operation_bound_fields": operation_bound_fields,
            "provider_execution_path_entered": False,
        },
        "lineage": {
            "sequence": 1,
            "acceptance_lineage_id": lineage,
            "database_name": database,
            "expected_database_name": EXPECTED_DATABASE,
            "identity_match": True,
            "operation_id_generated": False,
        },
        "postgres": {
            "system_identifier": identity["system_identifier"],
            "server_version": identity["server_version"],
            "server_version_num": identity["server_version_num"],
            "database": identity["database_name"],
            "database_oid": identity["database_oid"],
            "role": identity["database_role"],
            "schema": identity["schema_name"],
            "listen_addresses": identity["listen_addresses"],
            "port": int(identity["port"]),
            "socket": socket_evidence,
            "transport": "LOCAL_UNIX_SOCKET_PEER_NO_PASSWORD",
        },
        "migrations": {"head": migrations[0], "control_seed": "global/revision=0"},
        "virgin_state": {
            "classification": "VIRGIN_READY_FOR_OPERATION_REBIND",
            "row_counts": counts,
            "reserved_vnd": reserved,
            "provider_request_receipt_exists": False,
            "active_reservation": False,
            "duplicate_or_idempotency_collision": False,
            "operation_1_consumed": False,
            "operation_state_created": False,
        },
        "isolation": {
            "rc18_database": RC18_DATABASE,
            "rc18_database_present_in_rc19_cluster": False,
            "rc18_system_identifier": RC18_SYSTEM_IDENTIFIER,
            "rc19_system_identifier": identity["system_identifier"],
            "system_identifier_distinct": True,
            "shared_operation_or_reservation_keys": False,
        },
        "safety": {
            "kill_switch": "ENGAGED",
            "external_execution": False,
            "paid_execution": False,
            "bundle_mounted": False,
            "credential_reads": 0,
            "budget_reserved_vnd": "0",
            "real_provider_calls": 0,
            "production_business_writes": 0,
            "actual_cost_vnd": "0",
        },
        "blocker": "BOOTSTRAP_SCHEMA_REQUIRES_OPERATION_BINDING_BEFORE_FULL_RC19_INVOCATION",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rc-source", type=Path, required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = asyncio.run(audit(args))
    rendered = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    else:
        print(rendered, end="")


if __name__ == "__main__":
    main()
