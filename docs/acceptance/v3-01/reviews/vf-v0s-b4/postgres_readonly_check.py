"""VF-V0S-B4 SELECT-only regression on the two pre-existing B3 synthetic test DBs.
No catalog/schema/control/operation/budget writes. This is not future RC custody.
"""
from __future__ import annotations
import argparse, asyncio, json, runpy
from pathlib import Path
import asyncpg
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from app import provider_runtime_bootstrap as bootstrap
from app.provider_safety import derive_acceptance_lineage_id, derive_rc_bound_operation_key

EXPECTED = {
  19: ("vf_vf_v3_01_rc19_c6da26ba2a8795793f7d36051a816b7d", 17842),
  20: ("vf_vf_v3_01_rc20_20b9045ce79c76077018d74956d89b9a", 20739),
}
async def check(repo):
    socket = "/home/vang_nguyen/.local/share/npd-vf-rc18-ledger-0e0aa1417c53/socket"
    role, port, instance, sequence = "vang_nguyen", 55438, "7685407204168180413", 9997
    data = runpy.run_path(str(repo / "apps/api/tests/test_provider_runtime_bootstrap.py"))["binding_data"].__wrapped__()
    password_file_reads = []
    import asyncpg.connect_utils as connect_utils
    def deny_password_file(*args, **kwargs):
        password_file_reads.append(1)
        raise AssertionError("PASSWORD_FILE_LOOKUP_NOT_ALLOWED")
    connect_utils._read_passwordfile = deny_password_file
    admin = await asyncpg.connect(host=socket, port=port, user=role, database="postgres", password="")
    results, previous_binding = [], None
    try:
        async with admin.transaction(readonly=True, isolation="repeatable_read"):
            assert str(await admin.fetchval("SELECT (pg_control_system()).system_identifier")) == instance
            for number, (expected_database, expected_oid) in EXPECTED.items():
                rc = "vf-v3-01-rc" + str(number)
                lineage = derive_acceptance_lineage_id(rc_tag=rc, rc_commit="b"*40,
                    provider_key="openai-transcription", model="whisper-1", capability="asr", sequence=sequence)
                database = bootstrap.ledger_database_name(rc, lineage)
                assert database == expected_database
                assert await admin.fetchval("SELECT oid::int FROM pg_database WHERE datname=$1", database) == expected_oid
                data.update(rc_tag=rc, rc_commit="b"*40, acceptance_lineage_id=lineage, sequence=sequence,
                    operation_key=derive_rc_bound_operation_key(rc_tag=rc, provider_key="openai-transcription",
                        capability="asr", slot=1, acceptance_lineage_id=lineage),
                    database_name=database, database_oid=expected_oid, system_identifier=instance,
                    database_role=role, socket_directory=socket, port=port)
                binding = bootstrap.BootstrapLedgerBinding(**data)
                bootstrap.verify_socket_custody(binding)
                engine = create_async_engine(bootstrap.ledger_url(binding), echo=False, connect_args={"password": ""})
                factory = async_sessionmaker(engine, expire_on_commit=False)
                try:
                    first = await bootstrap.read_custody(factory, binding, require_virgin_namespace=True)
                    second = await bootstrap.read_custody(factory, binding, require_virgin_namespace=True)
                    assert first == second
                    assert first["counts"] == dict(operations=0, attempts=0, budget_days=0, circuits=0, budget_alerts=0)
                    assert first["control_rows"] == 1 and first["control_revision"] == 0
                    async with factory() as session, session.begin():
                        await session.execute(text("SET TRANSACTION READ ONLY"))
                        migration = await session.scalar(text("SELECT version_num FROM alembic_version"))
                    assert migration == "0014_v3_01_27", migration
                    denied = []
                    for field, value in (("database_oid", 1), ("system_identifier", "1"),
                                          ("database_role", "wrong_role"), ("schema_name", "wrong_schema")):
                        try:
                            await bootstrap.read_custody(factory, binding.model_copy(update={field: value}))
                        except bootstrap.BootstrapBlocked as exc:
                            assert str(exc) == "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:" + field
                            denied.append(field)
                        else:
                            raise AssertionError("WRONG_CUSTODY_ACCEPTED")
                    if previous_binding is not None:
                        try:
                            await bootstrap.read_custody(factory, previous_binding)
                        except bootstrap.BootstrapBlocked as exc:
                            assert str(exc) == "BOOTSTRAP_POSTGRES_IDENTITY_MISMATCH:database_name"
                            denied.append("cross_rc_database")
                        else:
                            raise AssertionError("CROSS_RC_CUSTODY_ACCEPTED")
                    results.append({"database": database, "database_oid": expected_oid,
                        "scope": "EXISTING_B3_SYNTHETIC_TEST_DATABASE_ONLY_NOT_FUTURE_EXECUTION_LINEAGE",
                        "migration_head": migration, "repeat_reads_identical": True,
                        "counts": first["counts"], "control_rows": first["control_rows"],
                        "control_revision": first["control_revision"], "reserved_vnd": first["reserved_vnd"],
                        "negative_identity_cases": denied})
                    previous_binding = binding
                finally:
                    await engine.dispose()
    finally:
        await admin.close()
    assert password_file_reads == []
    return {"task":"VF-V0S-B4", "result":"PASS", "tests": results,
        "password_file_reads":0, "postgres_writes":0, "new_database_or_namespace_created":False,
        "historical_rc18_execution_database_accessed":False,
        "future_execution_custody":"NOT_CREATED_REQUIRES_FRESH_RC_AND_LINEAGE",
        "provider_calls":0,"provider_credential_reads":0,"live_budget_reserved_vnd":"0",
        "production_business_writes":0}
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,required=True)
    print(json.dumps(asyncio.run(check(parser.parse_args().repo)),sort_keys=True,indent=2))
