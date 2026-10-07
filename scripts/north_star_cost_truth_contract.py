"""Export actual isolated cost persistence with explicitly synthetic monetary inputs."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from app.analytics_logic import assess_winner
from app.analytics_models import NormalizedMetrics
from app.db import Base, create_engine, create_session_factory
from app.platform_models import ProjectCreate, WorkspaceCreate
from app.repositories import PlatformRepository


def write(path, value):
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


async def run(root):
    root.mkdir(parents=True, exist_ok=False)
    database = root / "cost-contract.sqlite3"
    url = f"sqlite+aiosqlite:///{database.as_posix()}"
    engine = create_engine(url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    platform = PlatformRepository(create_session_factory(engine))
    workspace = await platform.create_workspace(WorkspaceCreate(
        slug="cost-fixture", name="Explicit cost contract fixture", owner_ref="fixture-owner"))
    project = await platform.create_project(workspace.workspace_id,
        ProjectCreate(slug="partial-billing", name="Fixture costs; no real provider"))
    await platform.seed_providers([{
        "provider_key": "explicit-cost-fixture", "display_name": "Explicit synthetic cost inputs",
        "capability": "content", "adapter": "fixture", "routing_mode": "primary",
        "status": "healthy", "enabled": True, "supports_dry_run": True,
    }])
    usages = []
    for operation, estimate, actual in [
        ("zero", Decimal(0), Decimal(0)), ("estimated", Decimal(50), None),
        ("billed-fixture", None, Decimal(70)), ("unknown", None, None),
    ]:
        usage, _ = await platform.record_provider_operation(
            workspace_id=workspace.workspace_id, project_id=project.project_id, job_id=None,
            provider_key="explicit-cost-fixture", capability="content", operation=operation,
            model="no-provider-model", estimated_cost=estimate, actual_cost=actual,
            metadata={"fixture": True, "external_call": False, "real_billing_receipt": False})
        usages.append(usage.model_dump(mode="json"))
    summary = await platform.project_cost_summary(project.project_id)
    records = await platform.list_cost_records(project.project_id)
    assert summary.actual_cost_total is None and summary.estimated_cost_total is None
    assert summary.actual_cost == 70 and summary.estimated_cost == 50
    assert summary.unknown_actual_cost_operations == summary.unknown_estimated_cost_operations == 2
    await engine.dispose()
    engine = create_engine(url)
    restarted = PlatformRepository(create_session_factory(engine))
    assert await restarted.project_cost_summary(project.project_id) == summary
    _, replay = await restarted.record_provider_operation(
        workspace_id=workspace.workspace_id, project_id=project.project_id, job_id=None,
        provider_key="explicit-cost-fixture", capability="content", operation="estimated",
        estimated_cost=Decimal(999), actual_cost=Decimal(999))
    assert replay.actual_cost is None and replay.estimated_cost == 50
    assert await restarted.list_cost_records(project.project_id) == records
    await engine.dispose()
    assessment = assess_winner(NormalizedMetrics(revenue=1000, views=500, observation_window_hours=24),
        video_duration_seconds=None, production_cost_vnd=None)
    factor = next(item for item in assessment.factors if item.factor == "production_cost_efficiency")
    assert factor.score is None and factor.evidence["production_cost_vnd"] is None
    write(root / "cost-records.json", [item.model_dump(mode="json") for item in records])
    write(root / "cost-summary.json", summary.model_dump(mode="json"))
    write(root / "provider-usage.json", usages)
    write(root / "cost-assessment.json", factor.model_dump(mode="json"))
    receipt = {"schema": "north-star-cost-truth-contract-v1", "status": "PASS",
        "monetary_inputs": "explicit synthetic fixtures; not real billed spend",
        "records": len(records), "restart_exact": True, "idempotent_replay_exact": True,
        "unknown_actual_cost_preserved": True, "unknown_estimated_cost_preserved": True,
        "winner_cost_score_unavailable": True, "external_provider_calls": 0, "paid_operations": 0,
        "production_deployed": False, "totals_basis": summary.totals_basis,
        "database_sha256_after_close": hashlib.sha256(database.read_bytes()).hexdigest(),
        "exports_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in root.glob("*.json")}}
    write(root / "receipt.json", receipt)
    print(json.dumps({"status": "PASS", "output_root": str(root), "exports": 5, "records": len(records)}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(run(args.output_root.resolve()))
