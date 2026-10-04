"""Portable, credential-free dev accounting bundle. Never reconstruct provider rows."""
from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, inspect, select

from .db import Base, create_engine, create_session_factory
from .provider_budget_epoch import (
    BudgetEpochArtifact, ProviderBudgetEpochRepository, SCHEMA_ID, public_bytes, sha256,
)

LEDGER = "DEV_LEDGER.sqlite3"


def public_evidence(raw):
    data = json.loads(raw)
    def check(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key.lower() in {"authorization", "password", "api_key", "secret_value", "placeholder"}:
                    raise ValueError("NON_PUBLIC_EVIDENCE_REJECTED")
                check(child)
        elif isinstance(value, list):
            for child in value: check(child)
        elif isinstance(value, str):
            if re.search(r"sk-[A-Za-z0-9_-]{20,}|Bearer\s+\S+|BEGIN .*PRIVATE KEY", value):
                raise ValueError("NON_PUBLIC_EVIDENCE_REJECTED")
    check(data)
    return data


def ledger_tables():
    return sorted((t for t in Base.metadata.tables.values()
        if t.name.startswith("provider_safety_")), key=lambda t: t.name)


async def verify_bundle(bundle: Path, *, operation_key: str, now: datetime,
                        expected_epoch_sha256: str | None = None):
    bundle = Path(bundle).resolve()
    index = json.loads((bundle / "CHECKSUMS.json").read_bytes())
    if index["schema_identity"] != SCHEMA_ID:
        raise ValueError("EPOCH_BUNDLE_SCHEMA_MISMATCH")
    for name, digest in index["file_hashes"].items():
        path = bundle / name
        if (Path(name).is_absolute() or ".." in Path(name).parts or path.is_symlink()
                or not path.resolve().is_relative_to(bundle)):
            raise ValueError("EPOCH_BUNDLE_PATH_REJECTED")
        if sha256(path.read_bytes()) != digest:
            raise ValueError("EPOCH_BUNDLE_CHECKSUM_MISMATCH")
    artifact = BudgetEpochArtifact.model_validate_json((bundle / "BUDGET_EPOCH.json").read_bytes())
    if (bundle / "BUDGET_EPOCH.json").read_bytes() != artifact.artifact_bytes:
        raise ValueError("EPOCH_ARTIFACT_BYTES_MISMATCH")
    if expected_epoch_sha256 and artifact.artifact_sha256 != expected_epoch_sha256:
        raise ValueError("EPOCH_OWNER_PIN_MISMATCH")
    if (bundle / "BUDGET_EPOCH.sha256").read_text() != artifact.artifact_sha256 + "  BUDGET_EPOCH.json\n":
        raise ValueError("EPOCH_ARTIFACT_CHECKSUM_MISMATCH")
    manifest = json.loads((bundle / "EVIDENCE_MANIFEST.json").read_bytes())
    if {x["artifact_id"]: x["sha256"] for x in manifest["artifacts"]} != artifact.evidence_hashes:
        raise ValueError("EPOCH_EVIDENCE_MANIFEST_MISMATCH")
    for entry in manifest["artifacts"]:
        expected = "evidence/" + entry["artifact_id"] + ".json"
        if entry["bundle_path"] != expected or index["file_hashes"].get(expected) != entry["sha256"]:
            raise ValueError("EPOCH_EVIDENCE_COPY_MISMATCH")
        public_evidence((bundle / expected).read_bytes())
    required = {"BUDGET_EPOCH.json", "BUDGET_EPOCH.sha256", "EVIDENCE_MANIFEST.json", LEDGER, "README.txt"}
    if not required.issubset(index["file_hashes"]):
        raise ValueError("EPOCH_BUNDLE_INCOMPLETE")
    # SQLite read-only URI: verification cannot create a missing ledger or change balances.
    engine = create_engine(f"sqlite+aiosqlite:///file:{(bundle / LEDGER).as_posix()}?mode=ro&uri=true")
    try:
        async with engine.connect() as conn:
            def check_schema(sync):
                schema = inspect(sync)
                names = set(schema.get_table_names())
                expected_names = {t.name for t in ledger_tables()}
                if names != expected_names:
                    raise ValueError("EPOCH_LEDGER_SCHEMA_MISMATCH")
                for table in ledger_tables():
                    if {c["name"] for c in schema.get_columns(table.name)} != {c.name for c in table.columns}:
                        raise ValueError("EPOCH_LEDGER_SCHEMA_MISMATCH")
            await conn.run_sync(check_schema)
        factory = create_session_factory(engine)
        proof = await ProviderBudgetEpochRepository(factory).budget_precheck(
            epoch_id=artifact.epoch_id, operation_key=operation_key,
            reservation_vnd=artifact.per_operation_limit_vnd, now=now)
        if proof["epoch_artifact_sha256"] != artifact.artifact_sha256:
            raise ValueError("EPOCH_DATABASE_PROVENANCE_PIN_MISMATCH")
        async with factory() as session:
            proof["row_counts"] = {t.name: int(await session.scalar(select(func.count()).select_from(t)) or 0)
                for t in ledger_tables()}
        proof.update(epoch_artifact_sha256=artifact.artifact_sha256,
            dev_ledger_sha256=index["file_hashes"][LEDGER], schema_identity=SCHEMA_ID)
    finally:
        await engine.dispose()
    if sha256((bundle / LEDGER).read_bytes()) != index["file_hashes"][LEDGER]:
        raise ValueError("EPOCH_LEDGER_CHANGED_DURING_READ_ONLY_PRECHECK")
    return proof


async def create_bundle(bundle: Path, *, artifact: BudgetEpochArtifact,
                        evidence_sources: dict[str, Path], operation_key: str):
    artifact = BudgetEpochArtifact.model_validate(artifact.model_dump())
    if set(evidence_sources) != set(artifact.evidence_hashes):
        raise ValueError("EPOCH_EVIDENCE_SET_MISMATCH")
    sources = {}
    for key, path in evidence_sources.items():
        path = Path(path)
        if path.is_symlink(): raise ValueError("EPOCH_EVIDENCE_PATH_REJECTED")
        raw = path.read_bytes()
        public_evidence(raw)
        if sha256(raw) != artifact.evidence_hashes[key]:
            raise ValueError("EPOCH_SOURCE_EVIDENCE_CHECKSUM_MISMATCH")
        sources[key] = (path.resolve(), raw)
    bundle = Path(bundle)
    bundle.mkdir(parents=True, exist_ok=False)  # Never overwrite a previous accounting epoch.
    (bundle / "evidence").mkdir()
    manifest = {"schema": "owner-accounting-epoch-evidence-v1",
        "historical_execution_artifact": artifact.historical_execution_artifact,
        "continuity_basis": artifact.owner_decision_id, "artifacts": []}
    for key, (source, raw) in sorted(sources.items()):
        name = "evidence/" + key + ".json"
        (bundle / name).write_bytes(raw)
        manifest["artifacts"].append({"artifact_id": key, "source_path": str(source),
            "bundle_path": name, "sha256": sha256(raw)})
    (bundle / "BUDGET_EPOCH.json").write_bytes(artifact.artifact_bytes)
    (bundle / "BUDGET_EPOCH.sha256").write_text(artifact.artifact_sha256 + "  BUDGET_EPOCH.json\n")
    (bundle / "EVIDENCE_MANIFEST.json").write_bytes(public_bytes(manifest))
    (bundle / "README.txt").write_text(
        "Owner accounting continuity epoch; this is not recovery of the historical ledger.\n"
        "The opening committed balance is OWNER_CARRY_FORWARD_CONSERVATIVE_CHARGE, not OpenAI billed spend.\n"
        "DEV_LEDGER.sqlite3 is the authoritative portable DEV provider-safety state. Preserve the complete file.\n"
        "Never recreate an already-used epoch from its opening JSON or delete operation/attempt rows.\n"
        "verify performs only read-only budget arithmetic; it never reserves or dispatches.\n"
        "After any future Owner-authorized execution, preserve a full SQLite backup and refresh its checksum.\n"
        "The opening epoch and evidence copies are immutable. Future ledger changes require new checkpoint evidence.\n"
        "No execution or production authority is granted by this bundle.\n", encoding="utf-8")
    engine = create_engine(f"sqlite+aiosqlite:///{(bundle / LEDGER).as_posix()}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(lambda sync: Base.metadata.create_all(sync, tables=ledger_tables()))
        repository = ProviderBudgetEpochRepository(create_session_factory(engine))
        await repository.initialize_epoch(artifact)
    finally:
        await engine.dispose()
    files = {p.relative_to(bundle).as_posix(): sha256(p.read_bytes())
        for p in bundle.rglob("*") if p.is_file()}
    (bundle / "CHECKSUMS.json").write_bytes(public_bytes({"schema_identity": SCHEMA_ID, "file_hashes": files}))
    return await verify_bundle(bundle, operation_key=operation_key, now=artifact.created_at_utc,
        expected_epoch_sha256=artifact.artifact_sha256)
