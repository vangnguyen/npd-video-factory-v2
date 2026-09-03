#!/usr/bin/env python3
"""Validate the V3-01-18 OpenAI ASR matrix without credentials or network calls."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.openai_transcription_provider import (  # noqa: E402
    openai_asr_compatibility_matrix,
)


def report() -> dict[str, object]:
    rows = openai_asr_compatibility_matrix()
    candidates = tuple(row.model for row in rows)
    expected = ("whisper-1", "gpt-transcribe", "gpt-4o-transcribe")
    if candidates != expected:
        raise RuntimeError("ASR compatibility candidate set or order drifted")
    if any(row.selection_status != "PROPOSED_NOT_APPROVED" for row in rows):
        raise RuntimeError("V3-01-18 cannot approve or select an ASR model")
    if any(
        row.live_api_calls != 0 or row.credential_reads != 0 or row.spend_vnd != 0
        for row in rows
    ):
        raise RuntimeError("ASR compatibility evidence must remain zero-call")
    return {
        "schema_version": "v3-01-asr-compatibility.v1",
        "checkpoint": "V3-01-18",
        "status": "PASS",
        "evidence_kind": "OFFLINE_CONTRACT_MOCK_OFFICIAL_CAPABILITY",
        "model_selection": "PROPOSED_NOT_APPROVED",
        "candidates": [row.model_dump(mode="json") for row in rows],
        "runtime_authority": {
            "g01_asr": "NOT_APPROVED",
            "g02_asr": "NOT_APPROVED",
            "g03_asr": "NOT_APPROVED",
            "provider_calls": 0,
            "credential_reads": 0,
            "spend_vnd": 0,
            "deployments": 0,
            "publishes": 0,
        },
        "acceptance": {
            "implemented": "PASS",
            "mock_tested": "PASS",
            "real_provider_tested": "NOT_TESTED",
            "production_path_tested": "NOT_TESTED",
            "quality_accepted": "NOT_TESTED",
        },
        "production_verdict": "NO-GO",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    args = parser.parse_args()
    result = report()
    if args.verify is not None:
        recorded = json.loads(args.verify.read_text(encoding="utf-8"))
        if recorded != result:
            raise SystemExit("recorded ASR compatibility evidence does not match source")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
