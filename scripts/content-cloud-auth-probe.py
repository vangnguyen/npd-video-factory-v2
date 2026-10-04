#!/usr/bin/env python3
"""Default offline diagnostics. GET-only execution requires a separate Owner approval file."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
import httpx
from app.codex_cloud_content_http import CodexCloudContentHTTPClient, ContentAuthProbeApproval, CLIENT_ID, cloud_proxy_context
from app.codex_cloud_content_secret import CodexCloudContentSecretTransport, NETWORK_SECRET_VARIABLE, uses_codex_cloud_content_proxy
from app.mvp1_provider_admission import Mvp1AdmissionScope, ProtectedResolverReference
from app.provider_safety import ProviderCallContext

PROBE_CLAIMS_ROOT = Path("/workspace/shared/npd-vf-content-auth-probes/consumed")


def pinned_file(path, pin):
    path = Path(path)
    if path.is_symlink() or not re.fullmatch(r"[a-f0-9]{64}", pin or ""):
        raise ValueError("PUBLIC_ARTIFACT_PIN_REQUIRED")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError("PUBLIC_ARTIFACT_PIN_MISMATCH")
    return raw


def resolver_from(scope, raw_sha):
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=raw_sha)
    return ProtectedResolverReference(scope, transport=backend, raw_file_sha256=raw_sha)


def diagnose(scope=None, raw_sha=None):
    result = {"status": "CONTENT_PROXY_PATH_OFFLINE_DIAGNOSTIC", "client_id": CLIENT_ID,
        "base_url": "https://api.openai.com", "trust_env": True, "follow_redirects": False,
        "custom_transport_supplied": False, **cloud_proxy_context(),
        "network_secret_present": bool(os.environ.get(NETWORK_SECRET_VARIABLE)),
        "auth_probe_call_count": 0, "provider_call_count": 0, "raw_credential_reads": 0,
        "budget_reservations": 0, "execution_authorized": False}
    if scope is None:
        return result
    resolver = resolver_from(scope, raw_sha)
    item = scope.allowed_operations[0]
    context = ProviderCallContext(operation_key=item.operation_key, workspace_id=scope.workspace_id,
        project_id=scope.project_id, job_id="job_content_offline_proxy_diagnostic", provider_key=scope.provider_key,
        model=scope.model, capability=scope.capability, operation=item.operation, external_call=True, paid=True,
        estimated_cost_vnd=scope.per_operation_limit_vnd, credential_alias=scope.credential_alias,
        asset_id=item.asset_id, asset_hash=item.asset_hash, input_media_kind="document",
        requested_language="vi", max_output_tokens=scope.max_output_tokens, rights_required=True)
    def forbidden(*args, **kwargs):
        raise AssertionError("DIAGNOSTIC_NETWORK_FORBIDDEN")
    with patch.object(httpx.AsyncClient, "request", forbidden), patch.object(httpx.Client, "request", forbidden), \
            patch.object(socket.socket, "connect", forbidden):
        client = CodexCloudContentHTTPClient(resolver, timeout_seconds=scope.profile["timeout_seconds"])
        result.update(uses_codex_cloud_content_proxy=uses_codex_cloud_content_proxy(resolver),
            backend_admitted=resolver.backend_admitted, resolver_type=type(resolver).__name__,
            resolver_transport_type=type(resolver.transport).__name__, backend_id=resolver.transport.backend_id,
            logical_alias=resolver.transport.logical_alias, environment_variable=resolver.transport.network_secret_variable,
            credential_host=resolver.transport.https_host,
            placeholder_identity_match=resolver.diagnose_placeholder_identity(context))
        del client
    return result


async def probe(scope, raw_sha, approval, *, output_dir):
    # No generation operation, reservation or scope activation is performed here.
    approval.validate_binding(scope, raw_sha)
    actual_head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if actual_head != approval.source_head or scope.execution_authorized:
        raise ValueError("AUTH_PROBE_HEAD_OR_DISABLED_SCOPE_MISMATCH")
    if not cloud_proxy_context()["API_OPENAI_COM_PROXY_ROUTE_ENABLED"]:
        raise ValueError("PLACEHOLDER_ESCAPED_PROXY_CONTEXT")
    resolver = resolver_from(scope, raw_sha)
    client = CodexCloudContentHTTPClient(resolver, timeout_seconds=scope.profile["timeout_seconds"])
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=False)  # A prior consumed attempt is never overwritten.
    PROBE_CLAIMS_ROOT.mkdir(parents=True, exist_ok=True)
    approval_identity = hashlib.sha256(json.dumps(approval.model_dump(mode="json"),
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()  # PUBLIC approval only.
    with (PROBE_CLAIMS_ROOT / (approval_identity+".json")).open("x", encoding="utf-8") as claim:
        json.dump({"owner_decision_id": approval.owner_decision_id, "automatic_retry": False}, claim)
    marker = output_dir / "AUTH_PROBE_CONSUMED.json"
    with marker.open("x", encoding="utf-8") as handle:
        json.dump({"owner_decision_id": approval.owner_decision_id, "max_attempts": 1,
            "automatic_retry": False, "source_head": actual_head}, handle, sort_keys=True)
    result = {"client_id": CLIENT_ID, "execution_authorized": False, "content_generation_call_count": 0,
        "raw_credential_reads": 0, "content_budget_reservations": 0, "auth_probe_call_count": 1}
    try:
        response = await client.auth_probe(approval)  # The only network-capable statement; explicit probe command only.
        result["http_status"] = response.status_code
        request_id = response.headers.get("x-request-id")
        if request_id and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", request_id):
            result["safe_request_id"] = request_id
        if response.status_code == 200:
            returned = response.json().get("id")
            result["status"] = "CONTENT_CREDENTIAL_AUTH_PROBE_PASS" if returned == "gpt-6-luna" else "CONTENT_CREDENTIAL_AUTH_PROBE_FAILED_MODEL"
            if returned == "gpt-6-luna":
                result["returned_model_id"] = returned
        elif response.status_code in {401, 403}:
            result["status"] = f"CONTENT_CREDENTIAL_AUTH_PROBE_FAILED_{response.status_code}"
        else:
            result["status"] = "CONTENT_CREDENTIAL_AUTH_PROBE_FAILED_HTTP"
    except Exception:
        result["status"] = "CONTENT_CREDENTIAL_AUTH_PROBE_TRANSPORT_UNCERTAIN"
    finally:
        resolver.transport = None
    (output_dir / "AUTH_PROBE_RESULT.json").write_text(json.dumps(result, sort_keys=True, indent=2)+"\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="diagnose", choices=["diagnose", "probe"])
    parser.add_argument("--scope", type=Path)
    parser.add_argument("--scope-sha256")
    parser.add_argument("--owner-approval", type=Path)
    parser.add_argument("--approval-sha256")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args(argv)
    if args.action == "probe" and not all((args.scope, args.scope_sha256, args.owner_approval, args.approval_sha256, args.output_dir)):
        print(json.dumps({"status": "CONTENT_AUTH_PROBE_DISABLED_OWNER_APPROVAL_REQUIRED", "auth_probe_call_count": 0}))
        return 2
    try:
        scope = Mvp1AdmissionScope.model_validate_json(pinned_file(args.scope, args.scope_sha256)) if args.scope else None
        if args.action == "diagnose":
            result = diagnose(scope, args.scope_sha256)
        else:
            approval = ContentAuthProbeApproval.model_validate_json(pinned_file(args.owner_approval, args.approval_sha256))
            result = asyncio.run(probe(scope, args.scope_sha256, approval, output_dir=args.output_dir))
    except Exception:
        print(json.dumps({"status": "CONTENT_PROXY_PATH_CONFIG_REJECTED", "auth_probe_call_count": 0}))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
