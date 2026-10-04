#!/usr/bin/env python3
"""Initialize or verify an Owner accounting epoch; no provider IO or credential handling."""
import argparse
import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.provider_budget_epoch import BudgetEpochArtifact
from app.provider_budget_epoch_bundle import create_bundle, verify_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["initialize", "verify"])
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--operation-key", required=True)
    parser.add_argument("--epoch-source", type=Path)
    parser.add_argument("--evidence-sources", type=Path)
    parser.add_argument("--expected-epoch-sha256")
    args = parser.parse_args()
    if args.command == "initialize":
        if not args.epoch_source or not args.evidence_sources:
            parser.error("initialize requires --epoch-source and --evidence-sources")
        artifact = BudgetEpochArtifact.model_validate_json(args.epoch_source.read_bytes())
        head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        if artifact.source_head != head:
            raise ValueError("EPOCH_SOURCE_HEAD_MISMATCH")
        sources = {key: Path(value) for key, value in json.loads(args.evidence_sources.read_bytes()).items()}
        result = asyncio.run(create_bundle(args.bundle, artifact=artifact,
            evidence_sources=sources, operation_key=args.operation_key))
    else:
        if not args.expected_epoch_sha256:
            parser.error("verify requires the Owner-reviewed --expected-epoch-sha256")
        result = asyncio.run(verify_bundle(args.bundle, operation_key=args.operation_key,
            now=datetime.now(timezone.utc), expected_epoch_sha256=args.expected_epoch_sha256))
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
