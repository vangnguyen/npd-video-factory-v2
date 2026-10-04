"""Synthetic accounting tests only. No provider transport or historical execution rows."""
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text

from app.db import Base, create_engine, create_session_factory
from app.provider_budget_epoch import BudgetEpochArtifact, ProviderBudgetEpochRepository
from app.provider_budget_epoch_bundle import create_bundle, ledger_tables, verify_bundle
from app.provider_safety import ProviderCallContext
from app.provider_safety_db import (
    ProviderSafetyAccountingEpochORM, ProviderSafetyAttemptORM, ProviderSafetyBudgetDayORM,
    ProviderSafetyCircuitORM, ProviderSafetyOperationORM,
)

NOW = datetime(2026, 10, 4, 7, 45, tzinfo=timezone.utc)


def artifact(**updates):
    data = dict(epoch_id="mvp1-content-budget-epoch-2026-10-04-02", created_at_utc=NOW,
        budget_day=NOW.date(), source_head="a" * 40,
        owner_decision_id="VF-MVP1-CONTENT-BUDGET-CARRY-FORWARD-14",
        daily_limit_vnd=20000, opening_committed_vnd=5000, available_vnd=15000,
        per_operation_limit_vnd=5000, evidence_hashes={"owner-decision": "b" * 64})
    data.update(updates)
    return BudgetEpochArtifact(**data)


@pytest.fixture
async def ledger(tmp_path):
    pg = os.getenv("MVP1_TEST_PG_URL")
    control = None
    schema = None
    if pg:
        from urllib.parse import urlparse
        parsed = urlparse(pg.replace("postgresql+asyncpg", "postgresql"))
        assert parsed.hostname == "127.0.0.1" and parsed.username == "mvp1_dev"
        assert parsed.path == "/mvp1_devtests" and parsed.password in {None, "synthetic_fixture_only"}
        from sqlalchemy.ext.asyncio import create_async_engine
        schema = "epoch_" + uuid.uuid4().hex
        control = create_engine(pg)
        async with control.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_async_engine(pg, connect_args={"server_settings": {"search_path": schema}})
    else:
        engine = create_engine(f"sqlite+aiosqlite:///{tmp_path}/ledger.db")
    async with engine.begin() as conn:
        await conn.run_sync(lambda sync: Base.metadata.create_all(sync, tables=ledger_tables()))
    factory = create_session_factory(engine)
    yield engine, factory, ProviderBudgetEpochRepository(factory)
    await engine.dispose()
    if control:
        async with control.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        await control.dispose()


async def precheck(repo, **updates):
    args = dict(epoch_id=artifact().epoch_id, operation_key="synthetic-new-operation",
        reservation_vnd=Decimal(5000), now=NOW)
    args.update(updates)
    return await repo.budget_precheck(**args)


async def test_opening_balance_has_provenance_and_precheck_never_reserves(ledger):
    _, factory, repo = ledger
    await repo.initialize_epoch(artifact())
    proof = await precheck(repo)
    assert Decimal(proof["committed_vnd"]) == 5000
    assert Decimal(proof["available_vnd"]) == 15000
    assert Decimal(proof["post_reservation_maximum_vnd"]) == 10000
    assert Decimal(proof["remaining_headroom_after_reservation_vnd"]) == 10000
    assert proof["reservation_performed"] is False
    async with factory() as session:
        for table in [ProviderSafetyOperationORM, ProviderSafetyAttemptORM, ProviderSafetyCircuitORM]:
            assert await session.scalar(select(func.count()).select_from(table)) == 0
        row = await session.get(ProviderSafetyAccountingEpochORM, artifact().epoch_id)
        assert row.classification == "OWNER_CARRY_FORWARD_CONSERVATIVE_CHARGE"
        assert row.artifact_json["execution_authorized"] is False
        assert row.artifact_sha256 == artifact().artifact_sha256


async def test_reinitialization_preserves_subsequent_balances_and_rejects_changed_provenance(ledger):
    _, factory, repo = ledger
    item = artifact()
    await repo.initialize_epoch(item)
    async with factory() as session:
        budget = await session.get(ProviderSafetyBudgetDayORM, NOW.date())
        budget.committed_vnd = Decimal(7000)
        budget.reserved_vnd = Decimal(1000)
        await session.commit()
    await repo.initialize_epoch(item)
    async with factory() as session:
        budget = await session.get(ProviderSafetyBudgetDayORM, NOW.date())
        assert budget.committed_vnd == 7000 and budget.reserved_vnd == 1000
    with pytest.raises(ValueError, match="DIFFERENT_PROVENANCE"):
        await repo.initialize_epoch(artifact(source_head="c" * 40))
    with pytest.raises(ValueError, match="OUTSTANDING_RESERVATION"):
        await precheck(repo)


async def test_new_epoch_refuses_nonempty_target_without_overwriting(ledger):
    _, factory, repo = ledger
    async with factory() as session:
        session.add(ProviderSafetyBudgetDayORM(budget_day=NOW.date(), currency="VND",
            daily_limit_vnd=20000, committed_vnd=Decimal(1234), reserved_vnd=Decimal(0)))
        await session.commit()
    with pytest.raises(ValueError, match="FRESH_EMPTY"):
        await repo.initialize_epoch(artifact())
    async with factory() as session:
        assert (await session.get(ProviderSafetyBudgetDayORM, NOW.date())).committed_vnd == 1234
        assert await session.scalar(select(func.count()).select_from(ProviderSafetyAccountingEpochORM)) == 0


async def test_existing_atomic_reservation_consumes_opening_balance(ledger):
    _, _, repo = ledger
    await repo.initialize_epoch(artifact(opening_committed_vnd=17000, available_vnd=3000))
    context = ProviderCallContext(operation_key="synthetic-budget-check", workspace_id="workspace-test",
        project_id="project-test", job_id="job-test", provider_key="openai-storyboard-content",
        model="gpt-6-luna", capability="content_generation", operation="storyboard-proposal",
        external_call=True, paid=True, estimated_cost_vnd=Decimal(5000), rights_required=False)
    result = await repo.reserve_operation(context, now=NOW, max_attempts=1, max_concurrent_calls=1,
        per_operation_limit_vnd=Decimal(5000), daily_limit_vnd=Decimal(20000),
        circuit_failure_threshold=3, circuit_cooldown_seconds=30, retention_days=400)
    assert not result.allowed and result.code == "DAILY_BUDGET_EXCEEDED"
    with pytest.raises(ValueError, match="DAILY_CAPACITY"):
        await precheck(repo)


async def test_used_operation_is_rejected_by_read_only_precheck(ledger):
    _, _, repo = ledger
    await repo.initialize_epoch(artifact())
    context = ProviderCallContext(operation_key="synthetic-new-operation", workspace_id="workspace-test",
        project_id="project-test", job_id="job-test", provider_key="openai-storyboard-content",
        model="gpt-6-luna", capability="content_generation", operation="storyboard-proposal",
        external_call=True, paid=True, estimated_cost_vnd=Decimal(5000), rights_required=False)
    result = await repo.reserve_operation(context, now=NOW, max_attempts=1, max_concurrent_calls=1,
        per_operation_limit_vnd=Decimal(5000), daily_limit_vnd=Decimal(20000),
        circuit_failure_threshold=3, circuit_cooldown_seconds=30, retention_days=400)
    assert result.allowed
    with pytest.raises(ValueError, match="OPERATION_ALREADY_USED"):
        await precheck(repo)


async def test_corrupt_or_wrong_day_budget_does_not_pass(ledger):
    _, factory, repo = ledger
    await repo.initialize_epoch(artifact())
    with pytest.raises(ValueError, match="DAY_MISMATCH"):
        await precheck(repo, now=NOW + timedelta(days=1))
    with pytest.raises(ValueError, match="OPERATION_CEILING"):
        await precheck(repo, reservation_vnd=Decimal(5001))
    async with factory() as session:
        budget = await session.get(ProviderSafetyBudgetDayORM, NOW.date())
        budget.committed_vnd = Decimal(0)
        await session.commit()
    with pytest.raises(ValueError, match="BUDGET_CORRUPT"):
        await precheck(repo)


@pytest.mark.parametrize("updates", [
    {"execution_authorized": True}, {"production_authority": True},
    {"created_at_utc": NOW.replace(tzinfo=None)}, {"available_vnd": 20000},
    {"opening_reserved_vnd": 5000}, {"classification": "ACTUAL_OPENAI_SPEND"},
])
def test_artifact_rejects_authority_or_invalid_accounting(updates):
    with pytest.raises(ValidationError): artifact(**updates)


async def test_portable_bundle_verifies_offline_and_rejects_tamper_and_overwrite(tmp_path):
    evidence = tmp_path / "decision.json"
    evidence.write_text(json.dumps({"decision_id": "synthetic-owner-accounting", "provider_calls": 0}))
    from app.provider_budget_epoch import sha256
    item = artifact(evidence_hashes={"owner-decision": sha256(evidence.read_bytes())})
    bundle = tmp_path / "bundle"
    proof = await create_bundle(bundle, artifact=item, evidence_sources={"owner-decision": evidence},
        operation_key="synthetic-unused-operation")
    assert proof["row_counts"]["provider_safety_operations"] == 0
    assert proof["row_counts"]["provider_safety_attempts"] == 0
    assert proof["row_counts"]["provider_safety_circuits"] == 0
    result = await verify_bundle(bundle, operation_key="synthetic-unused-operation", now=NOW,
        expected_epoch_sha256=item.artifact_sha256)
    assert result == proof
    with pytest.raises(FileExistsError):
        await create_bundle(bundle, artifact=item, evidence_sources={"owner-decision": evidence},
            operation_key="synthetic-unused-operation")
    with pytest.raises(ValueError, match="OWNER_PIN"):
        await verify_bundle(bundle, operation_key="synthetic-unused-operation", now=NOW,
            expected_epoch_sha256="f" * 64)
    (bundle / "BUDGET_EPOCH.json").write_bytes(item.artifact_bytes + b" ")
    with pytest.raises(ValueError, match="CHECKSUM_MISMATCH"):
        await verify_bundle(bundle, operation_key="synthetic-unused-operation", now=NOW)


async def test_bundle_rejects_secret_evidence_before_writing(tmp_path):
    from app.provider_budget_epoch import sha256
    evidence = tmp_path / "unsafe.json"
    evidence.write_text(json.dumps({"Authorization": "synthetic-forbidden-value"}))
    item = artifact(evidence_hashes={"owner-decision": sha256(evidence.read_bytes())})
    with pytest.raises(ValueError, match="NON_PUBLIC_EVIDENCE"):
        await create_bundle(tmp_path / "bundle", artifact=item,
            evidence_sources={"owner-decision": evidence}, operation_key="synthetic-unused")
    assert not (tmp_path / "bundle").exists()
