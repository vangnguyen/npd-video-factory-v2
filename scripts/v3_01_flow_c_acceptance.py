#!/usr/bin/env python3
"""Validate a redacted V3-01-06 Flow C evidence bundle without external actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "apps" / "api"))

from app.flow_c_acceptance import (  # noqa: E402
    FlowCAcceptanceBundle,
    FlowCAcceptancePolicy,
    evaluate_flow_c,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path, help="Secret-free Flow C evidence bundle")
    parser.add_argument(
        "--policy",
        type=Path,
        default=REPOSITORY_ROOT / "packages" / "contracts" / "flow-c-acceptance.v1.json",
    )
    parser.add_argument("--expect-verdict", choices=("PASS", "FAIL", "BLOCKED"))
    arguments = parser.parse_args()

    policy = FlowCAcceptancePolicy.model_validate_json(arguments.policy.read_text(encoding="utf-8"))
    bundle = FlowCAcceptanceBundle.model_validate_json(arguments.bundle.read_text(encoding="utf-8"))
    evaluation = evaluate_flow_c(bundle, policy)
    print(json.dumps(evaluation.model_dump(mode="json"), ensure_ascii=False, indent=2))
    if arguments.expect_verdict and evaluation.verdict != arguments.expect_verdict:
        print(
            f"expected verdict {arguments.expect_verdict}, got {evaluation.verdict}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
