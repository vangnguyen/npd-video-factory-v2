#!/usr/bin/env python3
"""Offline by default. One fixed POST requires a separate, pinned Owner canary approval."""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import re
import sys
import time
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.codex_cloud_content_http import (
    CANARY_REQUEST_SHA256, CLIENT_ID, CodexCloudContentHTTPClient,
    ContentResponsesCanaryApproval, canary_request_payload, cloud_proxy_context,
)
from app.mvp1_provider_admission import Mvp1AdmissionScope, digest

# Reuse the established public-artifact loader, fixed resolver and offline
# diagnostic; its auth network command is never invoked here.
_spec = importlib.util.spec_from_file_location("content_canary_offline_helpers", ROOT / "scripts/content-cloud-auth-probe.py")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
CANARY_CLAIMS_ROOT = Path("/workspace/shared/npd-vf-content-responses-canary/consumed")


def diagnose(scope=None, raw_sha=None):
    result = _helpers.diagnose(scope, raw_sha)
    result.update(status="CONTENT_RESPONSES_CANARY_OFFLINE_DIAGNOSTIC",
        canary_request_sha256=CANARY_REQUEST_SHA256, responses_canary_call_count=0,
        content_generation_call_count=0, content_operations=0, new_conservative_charges=0,
        production_writes=0, content_budget_authorized=False)
    return result


def observed_usage(body, scope):
    usage = body.get("usage")
    if not isinstance(usage, dict):
        return None
    incoming, outgoing = usage.get("input_tokens"), usage.get("output_tokens")
    if any(type(value) is not int or value < 0 for value in (incoming, outgoing)):
        return None
    cost = (Decimal(incoming)*Decimal(str(scope.profile["input_vnd_per_million_tokens"]))
        + Decimal(outgoing)*Decimal(str(scope.profile["output_vnd_per_million_tokens"]))) / Decimal(1_000_000)
    return {"input_tokens": incoming, "output_tokens": outgoing,
        "modeled_cost_vnd": str(cost.quantize(Decimal("0.000001"), rounding=ROUND_CEILING)),
        "provider_billing_observed": False}  # Token usage is not an invoice.


def safe_identity(value):
    pattern = r"(?:req_[A-Za-z0-9_.-]{1,160}|[a-fA-F0-9]{8}(?:-[a-fA-F0-9]{4}){3}-[a-fA-F0-9]{12})"
    return value if isinstance(value, str) and re.fullmatch(pattern, value) else None


def classify(response, scope):
    result = {"http_status": response.status_code}
    request_id = safe_identity(response.headers.get("x-request-id"))
    if request_id:
        result["safe_request_id"] = request_id
    try:
        body = response.json()
    except Exception:
        body = None
    malformed = not isinstance(body, dict)
    if malformed:
        body = {}
    response_id = body.get("id")
    if isinstance(response_id, str) and re.fullmatch(r"resp_[A-Za-z0-9_-]{1,160}", response_id):
        result["response_id"] = response_id
    if body.get("model") == "gpt-6-luna":
        result["returned_model"] = "gpt-6-luna"
    if body.get("status") in ("completed", "incomplete", "failed", "queued", "in_progress", "cancelled"):
        result["response_status"] = body["status"]
    # Never retain raw output/error bodies; they can echo request/credential data.
    error = body.get("error")
    if isinstance(error, dict):
        # An allowlist prevents a provider error field from becoming a disclosure channel.
        known_types = {"invalid_request_error", "authentication_error", "permission_error", "rate_limit_error", "server_error"}
        known_codes = {"invalid_api_key", "insufficient_quota", "rate_limit_exceeded", "model_not_found",
            "permission_denied", "invalid_parameter", "unsupported_parameter", "invalid_value", "access_denied"}
        if isinstance(error.get("type"), str) and error["type"] in known_types:
            result["safe_error_type"] = error["type"]
        if isinstance(error.get("code"), str) and error["code"] in known_codes:
            result["safe_error_code"] = error["code"]
    status = response.status_code
    if status == 200 and body.get("status") == "completed" and body.get("model") == "gpt-6-luna":
        outputs = body.get("output", [])
        valid = (isinstance(outputs, list) and len(outputs) == 1 and isinstance(outputs[0], dict)
            and outputs[0].get("type") == "message" and isinstance(outputs[0].get("content"), list)
            and len(outputs[0]["content"]) == 1 and isinstance(outputs[0]["content"][0], dict)
            and outputs[0]["content"][0].get("type") == "output_text"
            and isinstance(outputs[0]["content"][0].get("text"), str)
            and outputs[0]["content"][0]["text"].strip() == "OK")
        usage = observed_usage(body, scope)
        if valid and usage is not None and usage["output_tokens"] <= 16:
            result.update(status="CONTENT_RESPONSES_CANARY_PASS", classification="POST_INFERENCE_COMPATIBLE",
                acknowledgement="OK", CANARY_OBSERVED_USAGE=usage)
        else:
            result.update(status="CONTENT_RESPONSES_CANARY_FAILED_RESPONSE", classification="INVALID_CANARY_ACKNOWLEDGEMENT_OR_USAGE")
    elif status in {401, 403, 400, 429}:
        codes = {401:"POST_AUTH_OR_KEY_PERMISSION_BLOCKER", 403:"KEY_ENDPOINT_PERMISSION_OR_PROJECT_ACCESS_BLOCKER",
            400:"PAYLOAD_COMPATIBILITY_BLOCKER", 429:"RATE_OR_QUOTA_BLOCKER"}
        result.update(status=f"CONTENT_RESPONSES_CANARY_FAILED_{status}", classification=codes[status])
    elif status >= 500:
        result.update(status="CONTENT_RESPONSES_CANARY_FAILED_5XX", classification="PROVIDER_SERVER_FAILURE")
    elif malformed:
        result.update(status="CONTENT_RESPONSES_CANARY_FAILED_RESPONSE", classification="MALFORMED_PROVIDER_RESPONSE")
    else:
        result.update(status="CONTENT_RESPONSES_CANARY_FAILED_RESPONSE", classification="UNEXPECTED_HTTP_OR_RESPONSE_STATUS")
    usage = observed_usage(body, scope)
    if usage is not None:
        result["CANARY_OBSERVED_USAGE"] = usage
    return result


async def canary(scope, raw_sha, approval, *, output_dir):
    approval.validate_binding(scope, raw_sha)  # HEAD, window and disabled binding; before credential.
    safe = diagnose(scope, raw_sha)  # In-memory equality only, guarded against networking.
    required = {"uses_codex_cloud_content_proxy": True, "backend_admitted": True,
        "placeholder_identity_match": True, "HTTPS_PROXY_AVAILABLE": True,
        "NO_PROXY_EXCLUDES_API_OPENAI_COM": False, "CA_CONFIGURATION_AVAILABLE": True, "trust_env": True}
    if any(safe.get(key) != value for key, value in required.items()):
        raise ValueError("CONTENT_CANARY_SAFE_PATH_REQUIRED")
    if not cloud_proxy_context()["API_OPENAI_COM_PROXY_ROUTE_ENABLED"]:
        raise ValueError("PLACEHOLDER_ESCAPED_PROXY_CONTEXT")
    resolver = _helpers.resolver_from(scope, raw_sha)
    client = CodexCloudContentHTTPClient(resolver, timeout_seconds=scope.profile["timeout_seconds"])
    payload = canary_request_payload()
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)
    CANARY_CLAIMS_ROOT.mkdir(parents=True, exist_ok=True)
    # Public decision identity, independent of window/pins/output directory.
    claim_id = digest({"kind": "responses-canary", "owner_decision_id": approval.owner_decision_id})
    claim_data = {"owner_decision_id": approval.owner_decision_id, "automatic_retry": False,
        "approval_sha256": digest(approval.model_dump(mode="json")), "source_head": approval.source_head,
        "canary_request_sha256": CANARY_REQUEST_SHA256}
    with (CANARY_CLAIMS_ROOT / (claim_id+".json")).open("x", encoding="utf-8") as handle:
        json.dump(claim_data, handle, sort_keys=True)
    with (output_dir / "CANARY_CONSUMED.json").open("x", encoding="utf-8") as handle:
        json.dump(claim_data, handle, sort_keys=True)
    result = {"source_head": approval.source_head, "client_identity": CLIENT_ID,
        "backend_identity": approval.backend_id, "canary_request_sha256": CANARY_REQUEST_SHA256,
        "safe_proxy_tls_checks": {key:safe[key] for key in required}, "responses_canary_call_count":1,
        "provider_call_count":1, "auth_probe_call_count":0, "content_generation_call_count":0,
        "content_operations":0, "raw_credential_reads":0, "budget_reservations":0,
        "new_conservative_charges":0, "production_writes":0, "execution_authorized":False,
        "content_budget_authorized":False}
    started = time.monotonic()
    try:
        response = await client.responses_canary(payload, approval)  # The only network-capable statement.
        result.update(classify(response, scope))
    except Exception:
        result.update(status="CONTENT_RESPONSES_CANARY_TRANSPORT_UNCERTAIN", classification="TRANSPORT_UNCERTAIN")
    finally:
        result["latency_ms"] = round((time.monotonic()-started)*1000, 3)
        resolver.transport = None
        result["canary_resolver_detached"] = True
    with (output_dir / "CANARY_RESULT.json").open("x", encoding="utf-8") as handle:
        json.dump(result, handle, sort_keys=True, indent=2)
        handle.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="diagnose", choices=["diagnose", "canary"])
    parser.add_argument("--owner-approval", type=Path)
    parser.add_argument("--approval-sha256")
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--scope-sha256")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.action == "canary" and not all((args.owner_approval, args.approval_sha256, args.scope, args.scope_sha256, args.output_dir)):
        print(json.dumps({"status":"CONTENT_RESPONSES_CANARY_DISABLED_OWNER_APPROVAL_REQUIRED", "provider_call_count":0}))
        return 2
    try:
        scope = Mvp1AdmissionScope.model_validate_json(_helpers.pinned_file(args.scope, args.scope_sha256)) if args.scope else None
        if args.action == "diagnose":
            result = diagnose(scope, args.scope_sha256)
        else:
            approval = ContentResponsesCanaryApproval.model_validate_json(_helpers.pinned_file(args.owner_approval, args.approval_sha256))
            result = asyncio.run(canary(scope, args.scope_sha256, approval, output_dir=args.output_dir))
    except Exception:
        print(json.dumps({"status":"CONTENT_RESPONSES_CANARY_CONFIG_REJECTED", "provider_call_count":0}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
