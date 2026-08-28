#!/usr/bin/env python3
"""Validate a secret-free V3-01-07 DR/observability evidence bundle."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

from app.dr_observability_acceptance import (  # noqa: E402
    DRObservabilityBundle,
    DRObservabilityPolicy,
    evaluate_dr_observability,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument(
        "--policy",
        type=Path,
        default=REPOSITORY_ROOT / "packages" / "contracts" / "dr-observability-acceptance.v1.json",
    )
    parser.add_argument("--expect-verdict", choices=("PASS", "FAIL", "BLOCKED"))
    arguments = parser.parse_args()
    policy = DRObservabilityPolicy.model_validate_json(arguments.policy.read_text(encoding="utf-8"))
    bundle = DRObservabilityBundle.model_validate_json(arguments.bundle.read_text(encoding="utf-8"))
    evaluation = evaluate_dr_observability(bundle, policy)
    print(json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if arguments.expect_verdict and evaluation.verdict != arguments.expect_verdict:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
