#!/usr/bin/env python3
"""Deterministic public candidate generation/verification; never provider execution."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps/api"))
from app.codex_cloud_content_secret import (CodexCloudContentSecretTransport,
    compose_disabled_content_cloud_candidate, BACKEND_ID, CONTENT_ALIAS, NETWORK_SECRET_VARIABLE, HTTPS_HOST)
from app.content_models import ContentDocument
from app.mvp1_provider_admission import Mvp1AdmissionScope, canonical, digest
from app.provider_safety import ProviderCallContext, ProviderRightsEvidence, ProviderSafetyBlocked
from app.storyboard_content_provider import ContentProviderProfile, ResponsesStoryboardContentProvider

DIRECTORY = ROOT / "docs/acceptance/mvp1/content-live-01"
# Exact UTF-8 prompt, LF paragraph breaks, no BOM and no terminal newline.
PROMPT = """Viết một kịch bản video tiếng Việt dài khoảng 25–45 giây giới thiệu Vinhomes Green Paradise Cần Giờ cho khách hàng quan tâm bất động sản cao cấp.

Đây chỉ là bản nháp đề xuất để con người kiểm tra và phê duyệt.

Không được tự suy đoán hoặc bịa giá bán, chính sách bán hàng, tiến độ, ưu đãi, pháp lý, thông số quy hoạch hoặc tiện ích chưa có trong dữ liệu đầu vào.

Giữ nguyên chính xác tên “Vinhomes Green Paradise Cần Giờ”.

Tách rõ nội dung lời đọc và định hướng hình ảnh. Mọi thông tin cần nguồn xác minh phải được đưa vào facts_needing_source.

Không tự phê duyệt nội dung và không tự xuất bản."""
ASSET_ID = "pver_content_live_01_prompt"
WORKSPACE = "workspace_mvp1_content_dev_acceptance"
PROJECT = "project_mvp1_content_live_01"
PURPOSE = "bounded content generation proposal only"
WINDOW_START = "2027-01-15T08:00:00Z"
WINDOW_END = "2027-01-15T09:00:00Z"


def public_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode("utf-8") + b"\n"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()  # PUBLIC artifacts only; no credential argument.


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def build_records(source_commit):
    if len(source_commit) != 40 or any(c not in "0123456789abcdef" for c in source_commit):
        raise ValueError("exact source commit required")
    prompt_bytes = PROMPT.encode("utf-8")
    prompt_sha = sha(prompt_bytes)
    document = ContentDocument(input_kind="prompt", original_text=PROMPT,
        protected_terms=["Vinhomes Green Paradise Cần Giờ"])
    selected = ContentProviderProfile(version=2, model="gpt-6-luna", reasoning_effort="none",
        max_output_tokens=2048, timeout_seconds=90,
        input_vnd_per_million_tokens=3000, output_vnd_per_million_tokens=15000, estimated_cost_vnd=5000)
    rights = ProviderRightsEvidence(rights_record_id="mvp1-content-live-01-internal-prompt",
        asset_id=ASSET_ID, asset_hash=prompt_sha, source_type="internal",
        provider=selected.provider_key, provider_asset_or_job_id=ASSET_ID,
        source_url_or_reference="owner-controlled:CONTENT_PROMPT.txt", acquired_at_utc="2026-10-04T00:00:00Z",
        license_name=PURPOSE, license_version_or_terms_date="Owner task VF-MVP1-CONTENT-CLOUD-BACKEND-MATERIALIZE-07",
        commercial_use=True, derivative_use=True, social_platform_use=[], territory=[], expiry=None,
        attribution_required=False, attribution_text="",
        model_or_voice_rights="Internal proposal generation only; no voice or media assets included.",
        person_likeness_consent="No person likeness input included.",
        trademark_review="Preserve supplied project name; factual/trademark/publication review remains human responsibility.",
        evidence_reference="Owner-controlled prompt supplied in task VF-MVP1-CONTENT-CLOUD-BACKEND-MATERIALIZE-07",
        reviewer="Owner (GitHub: vangnguyen)", decision="APPROVED", secret_recorded=False)
    rights_raw = rights.model_dump(mode="json")
    identity = dict(source_commit=source_commit, profile_sha256=selected.sha256,
        workspace_id=WORKSPACE, project_id=PROJECT, asset_id=ASSET_ID, asset_hash=prompt_sha)
    operation_key = "mvp1-content_generation-" + digest(identity)
    scope = Mvp1AdmissionScope(capability="content_generation", provider_key=selected.provider_key,
        credential_alias=CONTENT_ALIAS, source_commit=source_commit, workspace_id=WORKSPACE,
        project_id=PROJECT, model=selected.model, profile=selected.model_dump(mode="json"),
        profile_sha256=selected.sha256,
        # Schema-required candidate identifier, NOT an allocated execution approval.
        owner_approval_id="V3-01-APP-999907", decision="APPROVED", approved_by="Owner (GitHub: vangnguyen)",
        purpose=PURPOSE, execution_authorized=False, valid_from_utc=WINDOW_START,
        expires_at_utc=WINDOW_END, budget_day_utc="2027-01-15",
        per_operation_limit_vnd=5000, acceptance_window_limit_vnd=20000,
        allowed_operations=[dict(operation_key=operation_key, operation="storyboard-proposal",
            asset_id=ASSET_ID, asset_hash=prompt_sha, rights_record=rights_raw,
            rights_record_sha256=digest(rights_raw), prompt_document_sha256=digest(document.model_dump(mode="json")))])
    scope_raw = scope.model_dump(mode="json")
    files = {"CONTENT_PROMPT.txt": prompt_bytes,
        "CONTENT_PROFILE.json": public_json(selected.model_dump(mode="json")),
        "CONTENT_RIGHTS.json": public_json(rights_raw), "CONTENT_SCOPE_DISABLED.json": public_json(scope_raw)}
    payload = ResponsesStoryboardContentProvider(selected)._request_payload(document)
    candidate = {"schema": "mvp1-content-cloud-disabled-candidate-v1",
        "status": "CONTENT_CLOUD_BACKEND_SOURCE_READY / OWNER_CANDIDATE_APPROVAL_REQUIRED",
        "owner_execution_approval": "PENDING", "execution_authorized": False,
        "source_commit": source_commit, "backend_id": BACKEND_ID,
        "logical_alias": CONTENT_ALIAS, "network_secret_variable": NETWORK_SECRET_VARIABLE,
        "credential_destination": HTTPS_HOST,
        "prompt_encoding": "UTF-8; LF paragraph breaks; no BOM; no terminal newline",
        "prompt_sha256": prompt_sha, "input_sha256": prompt_sha,
        "input_document": document.model_dump(mode="json"),
        "input_document_sha256": digest(document.model_dump(mode="json")),
        "profile_sha256": selected.sha256, "rights_sha256": digest(rights_raw),
        "admission_raw_file_sha256": sha(files["CONTENT_SCOPE_DISABLED.json"]),
        "canonical_scope_sha256": digest(scope_raw), "request_sha256": sha(canonical(payload)),
        "operation_key": operation_key,
        "planning_prices": {"input_usd_per_million_tokens": "0.10", "output_usd_per_million_tokens": "0.50",
            "fx_vnd_per_usd": 30000, "pricing_tier": "Standard short-context", "source": "Owner task pricing inputs"},
        "operation_ceiling_vnd": 5000, "day_ceiling_vnd": 20000,
        "window_status": "FUTURE_METADATA_ONLY_NOT_EXECUTION_AUTHORITY",
        "scope_approval_fields": "Schema-required candidate markers; Owner execution approval PENDING; not allocated authority",
        "provider_calls": 0, "raw_credential_reads": 0, "spend_vnd": 0, "production_writes": 0}
    files["CONTENT_CANDIDATE.json"] = public_json(candidate)
    return files, candidate, scope, document


def verify_files(directory=DIRECTORY):
    candidate = json.loads((directory / "CONTENT_CANDIDATE.json").read_bytes())
    files, expected, scope, document = build_records(candidate["source_commit"])
    for name, raw in files.items():
        if (directory / name).read_bytes() != raw:
            raise ValueError("public candidate bytes differ: " + name)
    return expected, scope, document


def verify_source(source_commit):
    # The candidate pins its Content request-defining implementation, not
    # unrelated accounting additions. Original public candidate bytes remain
    # immutable, and ancestry plus every request-defining source is still checked.
    git("merge-base", "--is-ancestor", source_commit, "HEAD")
    sources = ["apps/api/app/codex_cloud_content_secret.py", "apps/api/app/content_models.py",
        "apps/api/app/content_service.py", "apps/api/app/models.py",
        "apps/api/app/mvp1_provider_admission.py", "apps/api/app/storyboard_content_provider.py",
        "apps/api/app/provider_safety.py", "apps/api/app/provider_safety_durable.py"]
    if git("diff", "--name-only", source_commit, "--", *sources):
        raise ValueError("implementation differs from pinned source commit")


def context_for(scope):
    item = scope.allowed_operations[0]
    return ProviderCallContext(operation_key=item.operation_key, workspace_id=scope.workspace_id,
        project_id=scope.project_id, job_id="job_content_cloud_disabled_01", provider_key=scope.provider_key,
        model=scope.model, capability=scope.capability, operation=item.operation, external_call=True, paid=True,
        estimated_cost_vnd=scope.per_operation_limit_vnd, credential_alias=scope.credential_alias,
        asset_id=item.asset_id, asset_hash=item.asset_hash, input_media_kind="document",
        requested_language="vi", max_output_tokens=2048, rights_required=True)


async def qualify(scope, document, raw_file_sha256):
    # Any accidental network, credential handoff or ledger access is a failure.
    repository = Mock(spec=[], name="forbidden-production-repository")
    provider = compose_disabled_content_cloud_candidate(scope, raw_file_sha256=raw_file_sha256,
        repository=repository)
    context = context_for(scope)
    forbidden = Mock(side_effect=AssertionError("disabled candidate boundary reached"))
    with patch("httpx.AsyncClient.request", forbidden), patch("httpx.Client.request", forbidden), \
            patch("socket.socket.connect", forbidden):
        result = provider.prepare_zero_call(document, check_time=scope.valid_from_utc,
            workspace_id=scope.workspace_id, project_id=scope.project_id, job_id=context.job_id,
            source_version_id=context.asset_id, input_sha256=context.asset_hash, operation_key=context.operation_key)
        assert scope.denial_for(context, scope.valid_from_utc) == "MVP1_EXECUTION_AUTHORITY_REQUIRED"
        try:
            await provider.controller.execute(context, forbidden)
        except ProviderSafetyBlocked:
            pass
        else:
            raise AssertionError("disabled execute was not rejected")
        try:
            provider.credential_resolver.resolve_for_context(context)
        except RuntimeError:
            pass
        else:
            raise AssertionError("disabled resolver was not rejected")
    forbidden.assert_not_called()
    assert repository.mock_calls == []
    readiness = provider.credential_resolver.transport.readiness()
    return {**readiness, "backend_admitted": provider.credential_resolver.backend_admitted,
        "request_sha256": result["request_sha256"], "disabled_execute": "REJECTED",
        "network_policy": "NETWORK_POLICY_PLATFORM_MANAGED",
        "provider_calls": 0, "placeholder_handoffs": 0, "raw_credential_reads": 0,
        "budget_reservations": 0, "spend_vnd": 0, "production_writes": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["materialize", "verify", "qualify"])
    parser.add_argument("--source-commit", help="exact committed implementation; materialize only")
    args = parser.parse_args()
    if args.action == "materialize":
        source = args.source_commit or git("rev-parse", "HEAD")
        files, candidate, _, _ = build_records(source)
        DIRECTORY.mkdir(parents=True, exist_ok=True)
        prompt_path = DIRECTORY / "CONTENT_PROMPT.txt"
        if prompt_path.exists() and prompt_path.read_bytes() != files["CONTENT_PROMPT.txt"]:
            raise ValueError("refusing to rewrite materialized prompt")
        for name, raw in files.items():
            (DIRECTORY / name).write_bytes(raw)
    else:
        if args.source_commit:
            parser.error("--source-commit applies only to materialize")
        candidate, scope, document = verify_files()
        verify_source(scope.source_commit)
        if args.action == "qualify":
            result = asyncio.run(qualify(scope, document, candidate["admission_raw_file_sha256"]))
            if result["credential_delivery"] != "PLACEHOLDER_AVAILABLE":
                print(json.dumps(result, sort_keys=True))
                return 2
            print(json.dumps(result, sort_keys=True))
    print(json.dumps({k:v for k,v in candidate.items() if k.endswith("sha256") or k in {
        "source_commit", "operation_key", "status", "owner_execution_approval", "execution_authorized"}}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
