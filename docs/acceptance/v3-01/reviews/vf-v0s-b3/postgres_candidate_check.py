"""Explicit isolated candidate test; never a runtime/authority bootstrap command.

Uses only a supplied private peer socket. No env file/password/provider access.
Creates two new test databases from synthetic identities and preserves them.
Refuses an existing database; never drops/aliases the historical RC18 database.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import runpy
import subprocess
import sys
from pathlib import Path

import asyncpg
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app import provider_runtime_bootstrap as bootstrap
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key
from app.provider_safety_repository import ProviderSafetyRepository


async def check(repo: Path, socket: str, port: int, role: str, sequence: int) -> dict:
    fixture = runpy.run_path(str(repo / "apps/api/tests/test_provider_runtime_bootstrap.py"))
    data = fixture["binding_data"].__wrapped__()
    admin = await asyncpg.connect(host=socket, port=port, user=role, database="postgres")
    instance = str(await admin.fetchval("SELECT (pg_control_system()).system_identifier"))
    results = []
    writes = []
    try:
        for number in (19, 20):
            # Synthetic test identities, not new RCs/operation manifests/authorities.
            rc = "vf-v3-01-rc" + str(number)
            lineage = derive_acceptance_lineage_id(
                rc_tag=rc, rc_commit="b" * 40, provider_key="openai-transcription",
                model="whisper-1", capability="asr", sequence=sequence,
            )
            database = bootstrap.ledger_database_name(rc, lineage)
            exists = await admin.fetchval("SELECT oid FROM pg_database WHERE datname=$1", database)
            if exists:
                raise AssertionError("ISOLATED_TEST_DATABASE_ALREADY_EXISTS")
            # Identifier is restricted by canonical derivation/model, not free-form input.
            await admin.execute('CREATE DATABASE "' + database + '"')
            writes.append({"database": database, "kind": "ISOLATED_TEST_CATALOG_CREATE"})
            oid = int(await admin.fetchval("SELECT oid FROM pg_database WHERE datname=$1", database))
            data.update(
                rc_tag=rc, rc_commit="b" * 40, acceptance_lineage_id=lineage, sequence=sequence,
                operation_key=derive_rc_bound_operation_key(
                    rc_tag=rc, provider_key="openai-transcription", capability="asr",
                    slot=1, acceptance_lineage_id=lineage,
                ),
                system_identifier=instance, database_oid=oid, database_name=database,
                database_role=role, socket_directory=socket, port=port,
            )
            binding = bootstrap.BootstrapLedgerBinding(**data)
            bootstrap.verify_socket_custody(binding)
            url = bootstrap.ledger_url(binding)
            migration = (
                "from alembic.config import Config; from alembic import command; "
                "c=Config('alembic.ini'); "
                "c.set_main_option('sqlalchemy.url'," + repr(url.render_as_string().replace("%", "%%")) + "); "
                "command.upgrade(c,'head'); command.downgrade(c,'base'); command.upgrade(c,'head')"
            )
            result = subprocess.run(
                [sys.executable, "-B", "-c", migration], cwd=repo / "apps/api",
                capture_output=True, text=True, check=False,
            )
            if result.returncode:
                # The connection has no password; still never dump exception payloads.
                raise AssertionError("ISOLATED_MIGRATION_REPLAY_FAILED")
            writes.append({"database": database, "kind": "EXISTING_MIGRATION_REPLAY_AND_CONTROL_SEED"})
            engine = create_async_engine(url, echo=False)
            factory = async_sessionmaker(engine, expire_on_commit=False)
            try:
                first = await bootstrap.read_custody(factory, binding, require_virgin_namespace=True)
                await ProviderSafetyRepository(factory).ensure_state()
                second = await bootstrap.read_custody(factory, binding, require_virgin_namespace=True)
                assert first == second
                assert first["counts"] == dict(operations=0, attempts=0, budget_days=0, circuits=0, budget_alerts=0)
                assert first["control_rows"] == 1 and first["control_revision"] == 0
                denied = []
                for field, value in (
                    ("database_oid", oid + 1000), ("system_identifier", "1"),
                    ("database_role", "wrong_role"), ("schema_name", "wrong_schema"),
                ):
                    wrong = binding.model_copy(update={field: value})
                    try:
                        await bootstrap.read_custody(factory, wrong)
                    except bootstrap.BootstrapBlocked as exc:
                        assert str(exc) == "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:" + field
                        denied.append(field)
                    else:
                        raise AssertionError("WRONG_CUSTODY_WAS_ACCEPTED")
                if results:
                    try:
                        await bootstrap.read_custody(factory, previous_binding)
                    except bootstrap.BootstrapBlocked as exc:
                        assert str(exc) == "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:database_name"
                        denied.append("cross_rc_database")
                    else:
                        raise AssertionError("CROSS_RC_DATABASE_WAS_ACCEPTED")
                results.append({
                    "synthetic_test_rc_label": rc, "database": database,
                    "database_oid": oid, "system_identifier": instance,
                    "schema": "public", "postgres_major": 16,
                    "counts": first["counts"], "numeric_reserved_vnd": first["reserved_vnd"],
                    "control_rows": first["control_rows"], "control_revision": first["control_revision"],
                    "repeat_reads_identical": True, "negative_cases": denied,
                    "migration_replay": "0001..0014 upgrade/downgrade/base/upgrade PASS",
                    "ensure_state": "IDEMPOTENT_NO_ADDITIONAL_CONTROL_ROW",
                    "scope": "ISOLATED_SYNTHETIC_TEST_ONLY_NOT_A_FUTURE_RC_BINDING",
                })
                previous_binding = binding
            finally:
                await engine.dispose()
    finally:
        await admin.close()
    return {
        "result": "PASS", "tests": results, "test_bootstrap_ledger_writes": writes,
        "metadata_writes_only": True, "provider_calls": 0, "provider_credential_reads": 0,
        "live_reservations": 0, "production_business_writes": 0,
        "historical_rc18_database_accessed_or_mutated": False,
        "full_source_qualification": "NOT_CLAIMED_UNTAGGED_CANDIDATE",
        "final_execution_custody": "DEFERRED_UNTIL_NEW_RC_AND_FRESH_LINEAGE",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--test-sequence", type=int, required=True)
    parser.add_argument("--confirm-isolated-candidate-test", action="store_true", required=True)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(check(args.repo, args.socket, args.port, args.role, args.test_sequence)), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
