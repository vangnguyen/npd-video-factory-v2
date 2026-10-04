"""Offline same-path regression contracts. All HTTP responses below are synthetic."""
import importlib.util
import json
import os
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from app.codex_cloud_content_http import (
    CodexCloudContentHTTPClient, ContentAuthProbeApproval, ContentHTTPPathError, cloud_proxy_context,
)
from app.codex_cloud_content_secret import (
    CodexCloudContentSecretTransport, NETWORK_SECRET_VARIABLE, CONTENT_ALIAS, BACKEND_ID,
)
from app.mvp1_provider_admission import ProtectedResolverReference, digest
from app.storyboard_content_provider import ContentProviderProfile, ResponsesStoryboardContentProvider, ProviderEnablementError
from test_codex_cloud_content_secret import records, candidate, active_scope, ShapeForbidden

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("same_path_probe", ROOT / "scripts/content-cloud-auth-probe.py")
probe_script = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe_script)


def resolver_for(scope, raw_sha):
    return ProtectedResolverReference(scope,
        transport=CodexCloudContentSecretTransport(scope, raw_file_sha256=raw_sha), raw_file_sha256=raw_sha)


def approval_for(scope, raw_sha, **changes):
    instant = datetime.now(timezone.utc)
    data = dict(owner_decision_id="VF-MVP1-SYNTHETIC-AUTH-PROBE-TEST", approved_by="Owner (GitHub: vangnguyen)",
        auth_probe_authorized=True, source_head="a"*40, content_scope_sha256=digest(scope.model_dump(mode="json")),
        content_scope_raw_sha256=raw_sha, valid_from_utc=instant-timedelta(seconds=1), expires_at_utc=instant+timedelta(minutes=1))
    return ContentAuthProbeApproval.model_validate(data | changes)


@pytest.fixture
def binding(records, monkeypatch):
    _, manifest, scope, document = records
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, "synthetic-value-never-to-be-logged")
    return manifest, scope, document


async def test_auth_and_responses_share_constructor_backend_handoff_tls_and_proxy(binding, monkeypatch, capsys, caplog):
    manifest, disabled, document = binding
    raw_sha = manifest["admission_raw_file_sha256"]
    live = active_scope(disabled)  # Synthetic in-memory approval; no repository/real provider.
    configs, calls, handoffs = [], [], []
    original_handoff = CodexCloudContentSecretTransport._placeholder_handoff
    def handoff(self):
        handoffs.append((type(self).__name__, self.backend_id, self.logical_alias, self.network_secret_variable, self.https_host))
        return original_handoff(self)
    monkeypatch.setattr(CodexCloudContentSecretTransport, "_placeholder_handoff", handoff)
    class OfflineClient:
        def __init__(self, **config): configs.append(config)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def get(self, path, *, headers):
            assert path == "/v1/models/gpt-6-luna"
            assert headers == {"Authorization": "Bearer synthetic-value-never-to-be-logged"}
            calls.append("GET")
            return httpx.Response(200, json={"id": "gpt-6-luna"})
        async def post(self, path, *, headers, json):
            assert path == "/v1/responses"
            assert headers == {"Authorization": "Bearer synthetic-value-never-to-be-logged"}
            calls.append("POST")
            return httpx.Response(401)
    monkeypatch.setattr(httpx, "AsyncClient", OfflineClient)
    probe_resolver = resolver_for(disabled, raw_sha)
    response = await CodexCloudContentHTTPClient(probe_resolver, timeout_seconds=90).auth_probe(approval_for(disabled, raw_sha))
    assert response.status_code == 200
    provider = ResponsesStoryboardContentProvider(ContentProviderProfile.model_validate(live.profile), credential_resolver=resolver_for(live, raw_sha))
    with pytest.raises(ProviderEnablementError, match="PROVIDER_HTTP_401"):
        await provider._request(document, live.allowed_operations[0].asset_hash, provider._request_payload(document), candidate.context_for(live))
    assert calls == ["GET", "POST"]
    assert configs[0] == configs[1] == dict(base_url="https://api.openai.com", timeout=90, follow_redirects=False, trust_env=True, verify=True)
    assert len(handoffs) == 2 and handoffs[0] == handoffs[1] == (
        "CodexCloudContentSecretTransport", BACKEND_ID, CONTENT_ALIAS, NETWORK_SECRET_VARIABLE, "api.openai.com")
    captured = capsys.readouterr(); assert captured.out == captured.err == ""
    assert "synthetic-value-never-to-be-logged" not in caplog.text


def test_diagnostic_equality_no_encoding_logging_network_or_execution(binding, monkeypatch, capsys, caplog):
    manifest, scope, _ = binding
    opaque = ShapeForbidden("synthetic opaque diagnostic value")
    environment = dict(os.environ)
    environment[NETWORK_SECRET_VARIABLE] = opaque
    monkeypatch.setattr(os, "environ", environment)
    forbidden = Mock(side_effect=AssertionError("network forbidden"))
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    result = probe_script.diagnose(scope, manifest["admission_raw_file_sha256"])
    assert result["placeholder_identity_match"] is True
    assert result["uses_codex_cloud_content_proxy"] is True and result["backend_admitted"] is True
    assert result["resolver_transport_type"] == "CodexCloudContentSecretTransport"
    assert result["execution_authorized"] is False
    assert result["auth_probe_call_count"] == result["provider_call_count"] == result["budget_reservations"] == 0
    assert opaque not in json.dumps(result) and opaque not in caplog.text
    captured = capsys.readouterr(); assert captured.out == captured.err == ""
    forbidden.assert_not_called()
    assert not scope.execution_authorized


@pytest.mark.parametrize("custom", [Mock(), httpx.MockTransport(lambda request: httpx.Response(200))])
async def test_custom_transport_fails_before_handoff_and_constructor(binding, monkeypatch, custom):
    manifest, scope, document = binding
    scope = active_scope(scope)
    resolver = resolver_for(scope, manifest["admission_raw_file_sha256"])
    constructor = Mock(side_effect=AssertionError("client must not be constructed"))
    monkeypatch.setattr(httpx, "AsyncClient", constructor)
    provider = ResponsesStoryboardContentProvider(ContentProviderProfile.model_validate(scope.profile), credential_resolver=resolver, transport=custom)
    with pytest.raises(ProviderEnablementError, match="CUSTOM_TRANSPORT_PROXY_BYPASS_RISK"):
        await provider._request(document, scope.allowed_operations[0].asset_hash, provider._request_payload(document), candidate.context_for(scope))
    assert resolver._claimed == set()
    constructor.assert_not_called()


@pytest.mark.parametrize("parameter", ["host", "base_url", "credential_alias", "network_secret_variable", "proxy", "trust_env", "verify", "headers"])
def test_factory_has_no_arbitrary_host_secret_or_proxy_options(binding, parameter):
    manifest, scope, _ = binding
    with pytest.raises(TypeError):
        CodexCloudContentHTTPClient(resolver_for(scope, manifest["admission_raw_file_sha256"]), timeout_seconds=90, **{parameter: "arbitrary"})


@pytest.mark.parametrize("field,value", [("https_host", "example.com"), ("network_secret_variable", "ARBITRARY_KEY"),
    ("logical_alias", "secret://arbitrary"), ("backend_id", "arbitrary-backend")])
def test_backend_metadata_tampering_is_rejected(binding, field, value):
    manifest, scope, _ = binding
    resolver = resolver_for(scope, manifest["admission_raw_file_sha256"])
    setattr(resolver.transport, field, value)
    with pytest.raises(ContentHTTPPathError, match="FIXED_BINDING_REQUIRED"):
        CodexCloudContentHTTPClient(resolver, timeout_seconds=90)


@pytest.mark.parametrize("no_proxy", ["api.openai.com", ".openai.com", "*", "https://api.openai.com"])
async def test_no_proxy_route_bypass_is_blocked(binding, monkeypatch, no_proxy):
    manifest, scope, _ = binding
    monkeypatch.setenv("NO_PROXY", no_proxy); monkeypatch.setenv("no_proxy", no_proxy)
    assert cloud_proxy_context()["NO_PROXY_EXCLUDES_API_OPENAI_COM"] is True
    resolver = resolver_for(scope, manifest["admission_raw_file_sha256"])
    with pytest.raises(ContentHTTPPathError, match="PLACEHOLDER_ESCAPED_PROXY_CONTEXT"):
        await CodexCloudContentHTTPClient(resolver, timeout_seconds=90).auth_probe(approval_for(scope, manifest["admission_raw_file_sha256"]))
    assert resolver._claimed == set()


async def test_missing_proxy_blocks_child_context_without_exposing_proxy_credentials(binding, monkeypatch):
    manifest, scope, _ = binding
    for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
        monkeypatch.delenv(key, raising=False)
    safe = cloud_proxy_context()
    assert safe["HTTPS_PROXY_AVAILABLE"] is False and safe["API_OPENAI_COM_PROXY_ROUTE_ENABLED"] is False
    with pytest.raises(ContentHTTPPathError, match="PLACEHOLDER_ESCAPED_PROXY_CONTEXT"):
        await CodexCloudContentHTTPClient(resolver_for(scope, manifest["admission_raw_file_sha256"]), timeout_seconds=90).auth_probe(approval_for(scope, manifest["admission_raw_file_sha256"]))
    monkeypatch.setenv("https_proxy", "http://synthetic-user:synthetic-password@proxy.invalid:8080")
    assert "synthetic" not in repr(cloud_proxy_context())


async def test_no_ambient_key_fallback_or_logging(binding, monkeypatch, capsys, caplog):
    manifest, scope, _ = binding
    monkeypatch.delenv(NETWORK_SECRET_VARIABLE)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-ambient-must-not-be-used")
    resolver = resolver_for(scope, manifest["admission_raw_file_sha256"])
    with pytest.raises(ContentHTTPPathError, match="CONTENT_CREDENTIAL_UNAVAILABLE"):
        await CodexCloudContentHTTPClient(resolver, timeout_seconds=90).auth_probe(approval_for(scope, manifest["admission_raw_file_sha256"]))
    assert "synthetic-ambient" not in caplog.text
    captured = capsys.readouterr(); assert captured.out == captured.err == ""


@pytest.mark.parametrize("change", ["disabled", "expired", "raw_sha", "canonical_sha"])
async def test_probe_owner_authority_required_before_credential(binding, change):
    manifest, scope, _ = binding
    changes = {"disabled": {"auth_probe_authorized": False}, "expired": {
        "valid_from_utc": datetime.now(timezone.utc)-timedelta(minutes=2),
        "expires_at_utc": datetime.now(timezone.utc)-timedelta(minutes=1)},
        "raw_sha": {"content_scope_raw_sha256": "b"*64}, "canonical_sha": {"content_scope_sha256": "b"*64}}[change]
    resolver = resolver_for(scope, manifest["admission_raw_file_sha256"])
    with pytest.raises(ContentHTTPPathError, match="OWNER_AUTHORITY_REQUIRED"):
        await CodexCloudContentHTTPClient(resolver, timeout_seconds=90).auth_probe(approval_for(scope, manifest["admission_raw_file_sha256"], **changes))
    assert resolver._claimed == set()


def test_probe_cli_disabled_without_separate_approval(monkeypatch, capsys):
    forbidden = Mock(side_effect=AssertionError("no network or subprocess"))
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(probe_script.subprocess, "check_output", forbidden)
    assert probe_script.main(["probe"]) == 2
    assert json.loads(capsys.readouterr().out)["auth_probe_call_count"] == 0
    assert probe_script.main([]) == 0
    assert json.loads(capsys.readouterr().out)["provider_call_count"] == 0
    forbidden.assert_not_called()


async def test_probe_durable_claim_cannot_be_bypassed_with_new_output_directory(binding, monkeypatch, tmp_path):
    manifest, scope, _ = binding
    approval = approval_for(scope, manifest["admission_raw_file_sha256"])
    monkeypatch.setattr(probe_script, "PROBE_CLAIMS_ROOT", tmp_path/"claims")
    monkeypatch.setattr(probe_script.subprocess, "check_output", lambda *a, **kw: "a"*40+"\n")
    calls = []
    async def offline_probe(self, approved):
        calls.append(approved.owner_decision_id)
        return httpx.Response(200, json={"id": "gpt-6-luna"})
    monkeypatch.setattr(CodexCloudContentHTTPClient, "auth_probe", offline_probe)
    first = await probe_script.probe(scope, manifest["admission_raw_file_sha256"], approval, output_dir=tmp_path/"first")
    assert first["status"] == "CONTENT_CREDENTIAL_AUTH_PROBE_PASS"
    with pytest.raises(FileExistsError):
        await probe_script.probe(scope, manifest["admission_raw_file_sha256"], approval, output_dir=tmp_path/"second")
    assert len(calls) == 1
    assert not scope.execution_authorized


def test_candidate_pin_still_detects_request_implementation_changes():
    original = "class Example:\n    def _request_payload(self):\n        return {'model': 'approved'}\n"
    changed = original.replace("approved", "different")
    assert candidate.request_nodes(original, ["Example._request_payload"]) != candidate.request_nodes(changed, ["Example._request_payload"])
