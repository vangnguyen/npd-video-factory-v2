#!/usr/bin/env python3
"""Secret-safe evidence utilities for the V3-01 production acceptance audit.

The utility is deliberately unable to call providers, deploy, publish, or read a
runtime .env file.  It validates the checked-in acceptance register, validates
small redacted evidence records, and creates deterministic SHA-256 manifests.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError


ALLOWED_MATRIX_STATUSES = {"PASS", "FAIL", "BLOCKED", "NOT_TESTED", "N/A"}
EXPECTED_MATRIX_IDS = (
    "FND-01", "FND-02", "FND-03", "FND-04", "FND-05", "FND-06", "FND-07", "FND-08", "FND-09", "FND-10",
    "TRD-01", "TRD-02", "TRD-03", "TRD-04", "IDE-01", "IDE-02", "RES-01", "SCR-01", "SCR-02",
    "UPL-01", "ASR-01", "EDT-01", "EDT-02", "EDT-03", "VIS-01", "REF-01", "BRL-01", "STK-01",
    "CFY-01", "IMG-01", "VID-01", "TTS-01", "SUB-01", "MUS-01", "SFX-01", "TML-01", "PRV-01",
    "APR-01", "RND-01", "QC-01", "QC-02", "PUB-01", "PUB-02", "PUB-03", "PUB-04", "ANA-01",
    "ANA-02", "ANA-03", "WIN-01", "LRN-01", "OPS-01", "OPS-02", "OPS-03", "OPS-04", "OPS-05",
    "OPS-06", "OPS-07", "OPS-08", "OPS-09", "OPS-10",
)
EXPECTED_GATES = tuple(f"G-{index:02d}" for index in range(13))
REQUIRED_DOCS = (
    "00_BASELINE.md", "01_IMPLEMENTATION_INVENTORY.md", "02_ACCEPTANCE_MATRIX.md",
    "02_ACCEPTANCE_MATRIX.csv", "03_PROVIDER_AUDIT.md", "04_FLOW_A_UPLOAD_AUTO_EDIT.md",
    "05_FLOW_B_IDEA_AI_VIDEO.md", "06_FLOW_C_TREND_PUBLISH_ANALYTICS.md",
    "07_QUALITY_ACCEPTANCE.md", "08_SECURITY_AUDIT.md", "09_COST_AUDIT.md",
    "10_RIGHTS_PROVENANCE_AUDIT.md", "11_BACKUP_RESTORE_ROLLBACK.md",
    "12_OBSERVABILITY_SOAK.md", "13_GAP_REGISTER.md", "13_GAP_REGISTER.csv",
    "14_REMEDIATION_PR_PLAN.md", "15_OWNER_GATES.md", "16_FINAL_VERDICT.md",
    "17_V3_01_01_IDENTITY_INGRESS_SAFETY.md",
    "18_V3_01_02_PROVIDER_SAFETY_PLANE.md",
    "19_V3_01_03_INGRESS_MEDIA_DURABLE_SAFETY.md",
    "20_V3_01_04_FLOW_A_CLOSURE.md",
    "21_V3_01_05_FLOW_B_CLOSURE.md",
    "22_V3_01_06_FLOW_C_CLOSURE.md",
    "23_V3_01_07_DR_OBSERVABILITY.md",
    "24_V3_01_08_CONSOLIDATION_RC_GATE.md",
    "25_V3_01_09_OPENAI_VISION_ADAPTER.md",
    "26_V3_01_10_VERIFIED_ACCEPTANCE_GATE_LOADER.md",
)
SENSITIVE_KEY = re.compile(
    r"(^|_)(authorization|cookie|password|passwd|secret|token|api_key|private_key|client_secret)($|_)",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    re.compile(r"(?i)(?:password|passwd|client_secret|api_key|access_token)\s*[:=]\s*['\"]?(?!<|\$\{|TBD|REDACTED|NOT_RECORDED)[^\s,'\"]{8,}"),
)


class ValidationFailure(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def redact_payload(value: Any, *, key: str = "") -> Any:
    """Return a JSON-compatible copy with sensitive values removed."""

    if key and SENSITIVE_KEY.search(key) and key.lower() not in {
        "key_id", "object_key", "idempotency_key_hash", "secret_recorded"
    }:
        return "<REDACTED>"
    if isinstance(value, dict):
        return {str(item_key): redact_payload(item_value, key=str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_payload(item) for item in value]
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub("<REDACTED>", redacted)
        return redacted
    return value


def _load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def validate_matrix(path: Path) -> int:
    rows = _load_csv(path)
    required = {"id", "module", "implemented", "mock_tested", "real_provider_tested", "production_path_tested", "quality_accepted", "critical", "evidence_ids", "gap_ids", "notes"}
    if not rows:
        raise ValidationFailure("acceptance matrix is empty")
    missing_headers = required - set(rows[0])
    if missing_headers:
        raise ValidationFailure(f"matrix missing headers: {sorted(missing_headers)}")
    ids = tuple(row["id"].strip() for row in rows)
    if ids != EXPECTED_MATRIX_IDS:
        raise ValidationFailure("matrix IDs do not exactly match the V3-01 master catalog")
    for row in rows:
        for axis in ("implemented", "mock_tested", "real_provider_tested", "production_path_tested", "quality_accepted"):
            status = row[axis].strip()
            if status not in ALLOWED_MATRIX_STATUSES:
                raise ValidationFailure(f"{row['id']} has invalid {axis}: {status!r}")
        if not row["module"].strip() or not row["critical"].strip() or not row["notes"].strip():
            raise ValidationFailure(f"{row['id']} has a blank required descriptive field")
        if "PASS" in {row[axis].strip() for axis in ("implemented", "mock_tested", "real_provider_tested", "production_path_tested", "quality_accepted")} and not row["evidence_ids"].strip():
            raise ValidationFailure(f"{row['id']} contains PASS without evidence IDs")
    return len(rows)


def validate_gap_register(path: Path) -> int:
    rows = _load_csv(path)
    required = {"gap_id", "title", "severity", "status", "matrix_rows", "impact", "containment", "remediation", "owner", "pr_ids"}
    if not rows:
        raise ValidationFailure("gap register is empty")
    missing_headers = required - set(rows[0])
    if missing_headers:
        raise ValidationFailure(f"gap register missing headers: {sorted(missing_headers)}")
    seen: set[str] = set()
    for row in rows:
        gap_id = row["gap_id"].strip()
        if not re.fullmatch(r"V3-01-GAP-\d{3}", gap_id) or gap_id in seen:
            raise ValidationFailure(f"invalid or duplicate gap ID: {gap_id!r}")
        seen.add(gap_id)
        if row["severity"].strip() not in {"P0", "P1", "P2"}:
            raise ValidationFailure(f"{gap_id} has invalid severity")
        if row["status"].strip() not in {"OPEN", "IN_PROGRESS", "REMEDIATED", "VERIFIED", "ACCEPTED_EXCEPTION"}:
            raise ValidationFailure(f"{gap_id} has invalid status")
        for field in ("title", "matrix_rows", "impact", "containment", "remediation", "owner"):
            if not row[field].strip():
                raise ValidationFailure(f"{gap_id} has blank {field}")
    return len(rows)


def scan_for_secrets(paths: Iterable[Path]) -> None:
    findings: list[str] = []
    for root in paths:
        candidates = [root] if root.is_file() else [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            if any(part in {"private", "raw", ".git", "node_modules"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for pattern in SECRET_PATTERNS:
                if pattern.search(text):
                    findings.append(str(path))
                    break
    if findings:
        raise ValidationFailure(f"potential secret material detected in: {sorted(set(findings))}")


def validate_schema_file(path: Path) -> None:
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)


def validate_approval_records(docs: Path) -> int:
    schema_path = docs / "schemas" / "approval-record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    approval_dir = docs / "approvals"
    approval_files = sorted(approval_dir.glob("V3-01-APP-*.json")) if approval_dir.exists() else []
    seen: set[str] = set()
    for approval_file in approval_files:
        record = json.loads(approval_file.read_text(encoding="utf-8"))
        try:
            validator.validate(record)
        except ValidationError as exc:
            raise ValidationFailure(f"invalid approval record {approval_file.name}: {exc.message}") from exc
        approval_id = record["approval_id"]
        if approval_file.stem != approval_id:
            raise ValidationFailure(f"approval filename does not match approval_id: {approval_file.name}")
        if approval_id in seen:
            raise ValidationFailure(f"duplicate approval ID: {approval_id}")
        seen.add(approval_id)
    return len(approval_files)


def validate_rights_records(docs: Path) -> int:
    schema_path = docs / "schemas" / "rights-record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    rights_dir = docs / "rights"
    rights_files = sorted(rights_dir.glob("*.json")) if rights_dir.exists() else []
    seen: set[str] = set()
    for rights_file in rights_files:
        record = json.loads(rights_file.read_text(encoding="utf-8"))
        try:
            validator.validate(record)
        except ValidationError as exc:
            raise ValidationFailure(
                f"invalid RightsRecord {rights_file.name}: {exc.message}"
            ) from exc
        rights_record_id = record["rights_record_id"]
        if rights_file.stem != rights_record_id:
            raise ValidationFailure(
                f"rights filename does not match rights_record_id: {rights_file.name}"
            )
        if rights_record_id in seen:
            raise ValidationFailure(f"duplicate RightsRecord ID: {rights_record_id}")
        seen.add(rights_record_id)
    return len(rights_files)


def validate_repo(repo: Path) -> None:
    docs = repo / "docs" / "acceptance" / "v3-01"
    missing = [name for name in REQUIRED_DOCS if not (docs / name).is_file()]
    if missing:
        raise ValidationFailure(f"missing required acceptance documents: {missing}")
    matrix_count = validate_matrix(docs / "02_ACCEPTANCE_MATRIX.csv")
    gap_count = validate_gap_register(docs / "13_GAP_REGISTER.csv")
    gates = (docs / "15_OWNER_GATES.md").read_text(encoding="utf-8")
    missing_gates = [gate for gate in EXPECTED_GATES if gate not in gates]
    if missing_gates:
        raise ValidationFailure(f"owner gate register missing: {missing_gates}")
    schema_dir = docs / "schemas"
    schema_files = sorted(schema_dir.glob("*.schema.json"))
    if not schema_files:
        raise ValidationFailure("no V3-01 evidence schemas found")
    for schema_file in schema_files:
        validate_schema_file(schema_file)
    approval_count = validate_approval_records(docs)
    rights_count = validate_rights_records(docs)
    scan_targets = [docs]
    evidence_root = repo / "evidence" / "v3-01"
    if evidence_root.exists():
        scan_targets.append(evidence_root)
    scan_for_secrets(scan_targets)
    run_dirs = sorted(path.parent for path in evidence_root.glob("*/run-manifest.json")) if evidence_root.exists() else []
    for run_dir in run_dirs:
        validate_run(repo, run_dir)
    evidence_ids = {
        json.loads(path.read_text(encoding="utf-8")).get("evidence_id")
        for path in evidence_root.glob("*/**/evidence-*.json")
    } if evidence_root.exists() else set()
    referenced_ids = {
        evidence_id.strip()
        for row in _load_csv(docs / "02_ACCEPTANCE_MATRIX.csv")
        for evidence_id in row["evidence_ids"].split(";")
        if evidence_id.strip()
    }
    missing_evidence = sorted(referenced_ids - evidence_ids)
    if missing_evidence:
        raise ValidationFailure(f"matrix references missing evidence records: {missing_evidence}")
    print(
        f"v3-01 validation=PASS matrix_rows={matrix_count} gaps={gap_count} "
        f"schemas={len(schema_files)} approvals={approval_count} rights={rights_count} "
        f"evidence_runs={len(run_dirs)}"
    )


def validate_hashes(run_dir: Path) -> int:
    manifest_path = run_dir / "SHA256SUMS.txt"
    if not manifest_path.is_file():
        raise ValidationFailure("run is missing SHA256SUMS.txt")
    recorded: dict[str, str] = {}
    for line_number, line in enumerate(manifest_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line:
            continue
        try:
            digest, relative_name = line.split("  ", 1)
        except ValueError as exc:
            raise ValidationFailure(f"invalid SHA256SUMS line {line_number}") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or relative_name in recorded:
            raise ValidationFailure(f"invalid or duplicate SHA256SUMS entry: {relative_name!r}")
        relative = Path(relative_name)
        target = (run_dir / relative).resolve()
        if relative.is_absolute() or run_dir.resolve() not in target.parents:
            raise ValidationFailure(f"hash entry escapes run directory: {relative_name!r}")
        recorded[relative.as_posix()] = digest
    expected_files = [
        path for path in run_dir.rglob("*")
        if path.is_file()
        and path != manifest_path
        and not any(part in {"private", "raw"} for part in path.parts)
    ]
    expected_names = {path.relative_to(run_dir).as_posix() for path in expected_files}
    if set(recorded) != expected_names:
        missing = sorted(expected_names - set(recorded))
        extra = sorted(set(recorded) - expected_names)
        raise ValidationFailure(f"SHA256SUMS coverage mismatch missing={missing} extra={extra}")
    for path in expected_files:
        name = path.relative_to(run_dir).as_posix()
        if sha256_file(path) != recorded[name]:
            raise ValidationFailure(f"SHA256 mismatch: {name}")
    return len(expected_files)


def validate_run(repo: Path, run_dir: Path) -> None:
    root = (repo / "evidence" / "v3-01").resolve()
    resolved = run_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValidationFailure("run directory must be inside evidence/v3-01")
    schemas = repo / "docs" / "acceptance" / "v3-01" / "schemas"
    manifest_schema = json.loads((schemas / "run-manifest.schema.json").read_text(encoding="utf-8"))
    evidence_schema = json.loads((schemas / "evidence-record.schema.json").read_text(encoding="utf-8"))
    manifest = json.loads((resolved / "run-manifest.json").read_text(encoding="utf-8"))
    Draft202012Validator(manifest_schema).validate(manifest)
    evidence_files = sorted(resolved.rglob("evidence-*.json"))
    for evidence_file in evidence_files:
        evidence = json.loads(evidence_file.read_text(encoding="utf-8"))
        Draft202012Validator(evidence_schema).validate(evidence)
        if evidence["commit_sha"] != manifest["commit_sha"]:
            raise ValidationFailure(f"evidence commit does not match run manifest: {evidence_file.name}")
    artifact_paths = {
        path.relative_to(resolved).as_posix()
        for path in resolved.rglob("*")
        if path.is_file()
        and path.name not in {"run-manifest.json", "SHA256SUMS.txt"}
        and not any(part in {"private", "raw"} for part in path.parts)
    }
    if set(manifest["artifact_manifest"]) != artifact_paths:
        missing = sorted(artifact_paths - set(manifest["artifact_manifest"]))
        extra = sorted(set(manifest["artifact_manifest"]) - artifact_paths)
        raise ValidationFailure(f"artifact manifest coverage mismatch missing={missing} extra={extra}")
    hash_count = validate_hashes(resolved)
    scan_for_secrets([resolved])
    print(
        f"v3-01 run validation=PASS run={resolved.name} "
        f"evidence_records={len(evidence_files)} hashed_files={hash_count}"
    )


def write_hashes(repo: Path, run_dir: Path) -> None:
    root = (repo / "evidence" / "v3-01").resolve()
    resolved = run_dir.resolve()
    if resolved != root and root not in resolved.parents:
        raise ValidationFailure("run directory must be inside evidence/v3-01")
    output = resolved / "SHA256SUMS.txt"
    rows: list[str] = []
    for path in sorted(item for item in resolved.rglob("*") if item.is_file() and item != output):
        if any(part in {"private", "raw"} for part in path.parts):
            continue
        rows.append(f"{sha256_file(path)}  {path.relative_to(resolved).as_posix()}")
    output.write_text("\n".join(rows) + "\n", encoding="utf-8", newline="\n")
    print(f"v3-01 hashes=written files={len(rows)} path={output}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-repo")
    validate = subparsers.add_parser("validate-run")
    validate.add_argument("run_dir", type=Path)
    hashes = subparsers.add_parser("write-hashes")
    hashes.add_argument("run_dir", type=Path)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    repo = args.repo.resolve()
    try:
        if args.command == "validate-repo":
            validate_repo(repo)
        elif args.command == "validate-run":
            validate_run(repo, args.run_dir)
        elif args.command == "write-hashes":
            write_hashes(repo, args.run_dir)
        else:
            raise ValidationFailure(f"unsupported command: {args.command}")
    except (OSError, ValueError, json.JSONDecodeError, SchemaError, ValidationError, ValidationFailure) as exc:
        print(f"v3-01 validation=FAIL reason={exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
