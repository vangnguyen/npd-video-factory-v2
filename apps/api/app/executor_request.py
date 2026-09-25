"""Strict structured requests; authority and dispatch stay host controlled."""
from __future__ import annotations
import json
import os
import re
import asyncio
from .executor_qualification import ZERO, Blocked, require

FIELDS = {
    "operation_id": r"[A-Za-z0-9][A-Za-z0-9._:-]{0,199}",
    "bundle_id": r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}",
    "bundle_sha256": r"[a-f0-9]{64}",
    "loaded_scope_sha256": r"[a-f0-9]{64}",
    "authority_receipt_sha256": r"[a-f0-9]{64}",
    "rc_tag": r"vf-v3-01-rc[1-9][0-9]*",
    "rc_commit": r"[a-f0-9]{40}",
    "governance_main_sha": r"[a-f0-9]{40}",
    "provider_capability": r"asr",
}

def validate_request(value: object) -> dict[str, str]:
    require(isinstance(value, dict) and set(value) == set(FIELDS), "INPUT_FIELDS_INVALID")
    for name, pattern in FIELDS.items():
        require(isinstance(value[name], str) and re.fullmatch(pattern, value[name]) is not None,
                "INPUT_VALUE_INVALID")
    require(value["rc_tag"] != "vf-v3-01-rc22", "RC22_EXECUTION_CLOSED")
    return value

def main() -> int:
    try:
        value = validate_request(json.loads(os.environ.get("VF_REQUEST_JSON", "null")))
        from .executor_execution import execute
        result = asyncio.run(execute(value))
        print(json.dumps(result))
        return 0 if result["state"] == "QUALITY_REVIEW_REQUIRED" else 2
    except Blocked as exc:
        code = str(exc)
    except Exception:
        code = "INPUT_FIELDS_INVALID"
    print(json.dumps({"state": "BLOCKED_PRE_CALL", "code": code, **ZERO,
                      "bundle_mounted": False, "authority_inferred": False}))
    return 2

if __name__ == "__main__":
    raise SystemExit(main())
