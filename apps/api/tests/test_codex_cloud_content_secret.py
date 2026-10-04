"""Offline Cloud placeholder and disabled candidate contracts. No provider calls."""
import hashlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest
from pydantic import ValidationError

from app.codex_cloud_content_secret import (BACKEND_ID, CONTENT_ALIAS, NETWORK_SECRET_VARIABLE,
    CodexCloudContentSecretTransport, compose_disabled_content_cloud_candidate, uses_codex_cloud_content_proxy)
from app.mvp1_provider_admission import Mvp1AdmissionScope, ProtectedResolverReference, canonical
from app.storyboard_content_provider import ProviderEnablementError
from app.config import Settings
from app.mvp1_provider_admission import create_mvp1_lane_bindings

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("content_cloud_candidate", ROOT / "scripts/materialize-content-cloud-candidate.py")
candidate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(candidate)


@pytest.fixture
def records():
    return candidate.build_records("a" * 40)


def active_scope(scope):
    raw = scope.model_dump(mode="json")
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    start = max(start, now - timedelta(seconds=1))
    end = min(now + timedelta(minutes=1), now.replace(hour=23, minute=59, second=59, microsecond=999999))
    raw.update(execution_authorized=True, valid_from_utc=start, expires_at_utc=end, budget_day_utc=now.date())
    return Mvp1AdmissionScope.model_validate(raw)


def reference_metadata(scope, raw_sha):
    item = scope.allowed_operations[0]
    return dict(schema="mvp1-protected-resolver-reference-v1", provider_key=scope.provider_key,
        credential_alias=scope.credential_alias, scope_sha256=candidate.digest(scope.model_dump(mode="json")),
        scope_raw_file_sha256=raw_sha, operation_key=item.operation_key, workspace_id=scope.workspace_id,
        project_id=scope.project_id, job_id="job_synthetic_cloud", input_sha256=item.asset_hash,
        profile_sha256=scope.profile_sha256, max_resolutions=1)


def test_fixed_mapping_and_default_composition_is_uninstalled(records, monkeypatch):
    _, manifest, scope, _ = records
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, "opaque-synthetic-placeholder")
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"])
    read = backend.readiness()
    assert read["backend_id"] == BACKEND_ID == "codex-cloud-network-secret-content-v1"
    assert read["logical_alias"] == CONTENT_ALIAS
    assert read["network_secret_variable"] == "NPD_VF_CONTENT_API_KEY"
    assert read["https_host"] == "api.openai.com"
    assert read["credential_delivery"] == "PLACEHOLDER_AVAILABLE"
    provider = compose_disabled_content_cloud_candidate(scope,
        raw_file_sha256=manifest["admission_raw_file_sha256"], repository=None)
    assert provider.credential_resolver.backend_admitted
    assert uses_codex_cloud_content_proxy(provider.credential_resolver)
    assert provider.readiness() == "AUTHORITY_REQUIRED"
    for lane in ("content_generation", "tts"):
        assert create_mvp1_lane_bindings(Settings(_env_file=None), capability=lane, repository=None)["credential_resolver"] is None


@pytest.mark.parametrize("value", [None, ""])
def test_missing_placeholder_fails_closed_no_fallback(records, monkeypatch, value):
    _, manifest, scope, _ = records
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-fallback-must-not-be-used")
    monkeypatch.setenv("ARBITRARY_CONTENT_KEY", "synthetic-other-must-not-be-used")
    if value is None:
        monkeypatch.delenv(NETWORK_SECRET_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(NETWORK_SECRET_VARIABLE, value)
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"])
    assert backend.readiness()["credential_delivery"] == "PLACEHOLDER_UNAVAILABLE"
    with pytest.raises(RuntimeError, match="PLACEHOLDER_UNAVAILABLE"):
        backend(reference_metadata(scope, manifest["admission_raw_file_sha256"]))


@pytest.mark.parametrize("parameter", ["alias", "environment_variable", "host", "endpoint", "capability"])
def test_mapping_cannot_be_selected(records, parameter):
    _, manifest, scope, _ = records
    with pytest.raises(TypeError):
        CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"], **{parameter:"arbitrary"})


@pytest.mark.parametrize("field,value", [("credential_alias", "secret://openai/arbitrary"),
    ("environment_variable", "ARBITRARY_CONTENT_KEY"), ("host", "example.com"),
    ("endpoint", "https://api.openai.com/other"), ("provider_key", "openai-tts"),
    ("provider_key", "assemblyai-transcription"), ("input_sha256", "b"*64), ("max_resolutions", 2)])
def test_reference_cannot_change_mapping_or_scope(records, monkeypatch, field, value):
    _, manifest, scope, _ = records
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, "synthetic-placeholder")
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"])
    reference = reference_metadata(scope, manifest["admission_raw_file_sha256"])
    reference[field] = value
    with pytest.raises(RuntimeError, match="REFERENCE_REJECTED"):
        backend(reference)


def test_asr_and_tts_cannot_install_content_backend(records):
    from test_mvp1_provider_admission import synthetic_scope
    tts, _, _ = synthetic_scope("tts")
    with pytest.raises(ValueError, match="MAPPING_REJECTED"):
        CodexCloudContentSecretTransport(tts, raw_file_sha256="b"*64)
    _, _, scope, _ = records
    with pytest.raises(ValidationError):
        Mvp1AdmissionScope.model_validate(scope.model_dump() | {"capability":"asr"})


class ShapeForbidden(str):
    def strip(self, *args): raise AssertionError("placeholder shape inspected")
    def startswith(self, *args): raise AssertionError("placeholder shape inspected")
    def encode(self, *args): raise AssertionError("placeholder encoded/hashed")
    def __hash__(self): raise AssertionError("placeholder hashed")


def test_unchanged_opaque_handoff_without_shape_hash_or_logging(records, monkeypatch, capsys, caplog):
    _, manifest, scope, _ = records
    scope = active_scope(scope)  # SYNTHETIC execution scope; no provider transport.
    placeholder = ShapeForbidden("opaque value without any API-key shape")
    monkeypatch.setattr("app.codex_cloud_content_secret.os.environ", {NETWORK_SECRET_VARIABLE:placeholder})
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"])
    assert backend.readiness()["credential_delivery"] == "PLACEHOLDER_AVAILABLE"
    resolver = ProtectedResolverReference(scope, transport=backend, raw_file_sha256=manifest["admission_raw_file_sha256"])
    assert resolver.resolve_for_context(candidate.context_for(scope)) is placeholder
    with pytest.raises(RuntimeError, match="ALREADY_CLAIMED"):
        resolver.resolve_for_context(candidate.context_for(scope))
    assert placeholder not in repr(backend)
    captured = capsys.readouterr()
    assert captured.out == captured.err == caplog.text == ""


@pytest.mark.parametrize("placeholder", ["opaque-synthetic-placeholder", " "])
async def test_mock_header_unchanged_and_proxy_required(records, monkeypatch, placeholder):
    _, manifest, scope, document = records
    scope = active_scope(scope)
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, placeholder)
    backend = CodexCloudContentSecretTransport(scope, raw_file_sha256=manifest["admission_raw_file_sha256"])
    resolver = ProtectedResolverReference(scope, transport=backend, raw_file_sha256=manifest["admission_raw_file_sha256"])
    from app.storyboard_content_provider import ResponsesStoryboardContentProvider, ContentProviderProfile
    provider = ResponsesStoryboardContentProvider(ContentProviderProfile.model_validate(scope.profile), credential_resolver=resolver)
    captured = {}
    class OfflineClient:
        def __init__(self, **kwargs): captured.update(kwargs)
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, path, *, headers, json):
            assert path == "/v1/responses"  # In-memory fake ONLY.
            assert headers == {"Authorization":"Bearer " + placeholder}
            return httpx.Response(401)
    monkeypatch.setattr("app.storyboard_content_provider.httpx.AsyncClient", OfflineClient)
    with pytest.raises(ProviderEnablementError, match="PROVIDER_HTTP_401"):
        await provider._request(document, scope.allowed_operations[0].asset_hash,
            provider._request_payload(document), candidate.context_for(scope))
    assert captured["trust_env"] is True
    assert captured["follow_redirects"] is False
    assert captured["base_url"] == "https://api.openai.com"


def test_deterministic_public_bytes_and_independent_hashes(records):
    files, manifest, scope, document = records
    assert files == candidate.build_records("a"*40)[0]
    assert files["CONTENT_PROMPT.txt"] == candidate.PROMPT.encode("utf-8")
    assert not files["CONTENT_PROMPT.txt"].endswith(b"\n")
    assert manifest["prompt_sha256"] == "385c14fab304cbe5629e3746c063a313f13e5dfb0b282410259676f438ca326f"
    public_digest = lambda value: hashlib.sha256(json.dumps(value, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    assert manifest["prompt_sha256"] == hashlib.sha256(files["CONTENT_PROMPT.txt"]).hexdigest()
    assert manifest["profile_sha256"] == public_digest(json.loads(files["CONTENT_PROFILE.json"]))
    assert manifest["rights_sha256"] == public_digest(json.loads(files["CONTENT_RIGHTS.json"]))
    assert manifest["canonical_scope_sha256"] == public_digest(json.loads(files["CONTENT_SCOPE_DISABLED.json"]))
    assert manifest["admission_raw_file_sha256"] == hashlib.sha256(files["CONTENT_SCOPE_DISABLED.json"]).hexdigest()
    assert scope.allowed_operations[0].asset_hash == manifest["prompt_sha256"]
    assert scope.allowed_operations[0].rights_record["asset_hash"] == manifest["prompt_sha256"]
    assert not scope.execution_authorized and len(scope.allowed_operations) == 1
    assert scope.profile["input_vnd_per_million_tokens"] == "3000"
    assert scope.profile["output_vnd_per_million_tokens"] == "15000"
    assert scope.per_operation_limit_vnd == 5000 and scope.acceptance_window_limit_vnd == 20000
    changed = candidate.build_records("b"*40)[1]
    assert changed["operation_key"] != manifest["operation_key"]
    assert changed["canonical_scope_sha256"] != manifest["canonical_scope_sha256"]
    assert changed["request_sha256"] == manifest["request_sha256"]


@pytest.mark.parametrize("name", ["CONTENT_PROMPT.txt", "CONTENT_PROFILE.json", "CONTENT_RIGHTS.json",
    "CONTENT_SCOPE_DISABLED.json", "CONTENT_CANDIDATE.json"])
def test_verifier_rejects_any_artifact_drift(records, tmp_path, name):
    files, _, _, _ = records
    for key, raw in files.items(): (tmp_path/key).write_bytes(raw)
    candidate.verify_files(tmp_path)
    (tmp_path/name).write_bytes(files[name] + b"\n")
    with pytest.raises(ValueError): candidate.verify_files(tmp_path)


async def test_disabled_execute_and_qualification_never_touch_network_or_ledger(records, monkeypatch):
    _, manifest, scope, document = records
    monkeypatch.setenv(NETWORK_SECRET_VARIABLE, "synthetic-placeholder")
    result = await candidate.qualify(scope, document, manifest["admission_raw_file_sha256"])
    assert result["backend_admitted"] and result["disabled_execute"] == "REJECTED"
    assert result["request_sha256"] == manifest["request_sha256"]
    assert result["provider_calls"] == result["raw_credential_reads"] == result["budget_reservations"] == 0
    # Even enabling policy switches cannot turn the disabled scope into authority.
    provider = compose_disabled_content_cloud_candidate(scope,
        raw_file_sha256=manifest["admission_raw_file_sha256"], repository=Mock(spec=[]))
    provider.controller.policy.global_kill_switch_engaged = False
    provider.controller.policy.external_execution_enabled = True
    provider.controller.policy.paid_execution_enabled = True
    from app.provider_safety import ProviderSafetyBlocked
    callback = Mock(side_effect=AssertionError("disabled scope must deny"))
    with pytest.raises(ProviderSafetyBlocked) as blocked:
        await provider.controller.execute(candidate.context_for(scope), callback)
    assert blocked.value.code == "MVP1_EXECUTION_AUTHORITY_REQUIRED"
    callback.assert_not_called()
    with pytest.raises(ValueError, match="DISABLED_CANDIDATE_REQUIRED"):
        compose_disabled_content_cloud_candidate(active_scope(scope), raw_file_sha256="b"*64, repository=None)


@pytest.mark.parametrize("field,value", [("original_text", "changed prompt"),
    ("creative_instructions", "changed instructions"), ("supplied_facts", ["unapproved claim"]),
    ("protected_terms", [])])
def test_raw_prompt_hash_also_pins_entire_document(records, field, value):
    _, manifest, scope, document = records
    provider = compose_disabled_content_cloud_candidate(scope,
        raw_file_sha256=manifest["admission_raw_file_sha256"], repository=None)
    altered = document.model_copy(update={field:value})
    with pytest.raises(ProviderEnablementError, match="PROMPT_DOCUMENT_MISMATCH"):
        provider.input_sha256(altered, scope.allowed_operations[0].asset_id)


def test_legacy_document_input_hash_remains_unchanged():
    from test_mvp1_provider_admission import synthetic_scope
    scope, profile, document = synthetic_scope()
    assert "prompt_document_sha256" not in scope.model_dump(mode="json")["allowed_operations"][0]
    from app.storyboard_content_provider import ResponsesStoryboardContentProvider
    from types import SimpleNamespace
    provider = ResponsesStoryboardContentProvider(profile, controller=SimpleNamespace(policy=SimpleNamespace(execution_gate=scope)))
    assert provider.input_sha256(document, scope.allowed_operations[0].asset_id) == hashlib.sha256(canonical(document.model_dump(mode="json"))).hexdigest()
