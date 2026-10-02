"""Synthetic offline V2 contracts; never host or provider qualification evidence."""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path, PurePosixPath
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import executor_qualification as q, executor_promotion as promotion
from app import executor_execution as execution, executor_security as security
from app.provider_credentials import provider_credential_binding
from test_executor_plane import host, mock_probes
from test_executor_promotion import promotion_inputs
from test_executor_qualification_promotion import artifacts

PROVIDERS = ("openai-transcription", "assemblyai-transcription")


def backend(provider):
    credential = provider_credential_binding(provider)
    return {
        "version": 2, "task": q.QUALIFICATION_V2_TASK, "status": "PASS",
        "provider_key": provider, "credential_alias": credential.credential_alias,
        "systemd_version": "255 (255.4-1ubuntu8.17)",
        "host_key_present": True, "host_key_owner": "root:root",
        "host_key_mode": "0400", "host_key_regular_file": True,
        "host_key_symlink": False, "runner_host_key_read": False, "runner_host_key_write": False,
        "credential_mechanism": "LoadCredentialEncrypted",
        "systemd_credential_id": credential.systemd_credential_id,
        "encryption_key_type": "HOST", "synthetic_encrypt": "PASS", "name_binding": "PASS",
        "controlled_service_receive": "PASS", "access_isolation": "PASS", "cleanup": "PASS",
        "actual_provider_credential_decrypted": False, "provider_runtime_reads": 0, "provider_calls": 0,
        "encrypted_source_path": str(PurePosixPath("/etc/credstore.encrypted") / credential.systemd_credential_id),
        "encrypted_source_present": True, "encrypted_source_owner": "root:root",
        "encrypted_source_mode": "0400", "encrypted_source_regular_file": True,
        "encrypted_source_symlink": False, "encrypted_source_nonempty": True,
        "credstore_owner": "root:root", "credstore_mode": "0700",
        "runner_source_read": False, "runner_source_write": False, "runner_credstore_list": False,
    }


def binding(provider, receipt_hash):
    credential = provider_credential_binding(provider)
    return {
        "version": 2, "provider_key": provider, "credential_alias": credential.credential_alias,
        "capability_scope": ["asr"], "source_type": "SYSTEMD_ENCRYPTED_CREDENTIAL",
        "source_locator": str(PurePosixPath("/etc/credstore.encrypted") / credential.systemd_credential_id),
        "owner": "root", "expected_owner_uid": 0, "expected_owner_gid": 0, "expected_mode": "0400",
        "state": "BOUND_ENCRYPTED_SOURCE_PRESENT", "created_for": q.QUALIFICATION_V2_TASK,
        "authority_granted": False, "secret_source_present": True,
        "systemd_credential_id": credential.systemd_credential_id, "encryption_key_type": "HOST",
        "provider_runtime_reads": 0, "backend_qualification_receipt_sha256": receipt_hash,
    }


@pytest.fixture
def fixture_store(host, tmp_path, monkeypatch):
    """The only readable files are synthetic non-secret receipt and metadata."""
    receipt_path = tmp_path / "backend.json"
    binding_path = tmp_path / "binding.json"
    monkeypatch.setattr(q, "private_path", lambda *a, **k: None)
    monkeypatch.setattr(q, "SYSTEMD_BACKEND_RECEIPT", receipt_path)
    original_read = Path.read_bytes

    def guarded_read(path):
        if not path.is_relative_to(tmp_path):
            pytest.fail("credential or host-file read")
        return original_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    monkeypatch.setattr(q.socket, "create_connection", lambda *a, **k: pytest.fail("real network"))
    monkeypatch.setattr(q, "load_secret_binding", REAL_LOAD)
    monkeypatch.setattr(q, "secret_presence", REAL_PRESENCE)

    def install(provider="assemblyai-transcription", *, metadata_changes=None, backend_changes=None):
        receipt = backend(provider)
        receipt.update(backend_changes or {})
        raw = json.dumps(receipt, sort_keys=True).encode()
        receipt_path.write_bytes(raw)
        metadata = binding(provider, q.sha(raw))
        metadata.update(metadata_changes or {})
        binding_path.write_bytes(json.dumps(metadata, sort_keys=True).encode())
        return replace(host, secret_binding=str(binding_path)), metadata, receipt

    return install


@pytest.mark.parametrize("provider", PROVIDERS)
def test_v2_presence_exact_provider_without_secret_read(fixture_store, provider):
    bound, metadata, receipt = fixture_store(provider)
    result = q.secret_presence(bound)
    identity = provider_credential_binding(provider)
    assert result["result"] == "PASS_SECRET_SOURCE_PRESENT_NOT_RESOLVED"
    assert result["provider_key"] == provider
    assert result["credential_alias"] == identity.credential_alias
    assert result["systemd_credential_id"] == identity.systemd_credential_id
    assert result["PROVIDER_CREDENTIAL_READS"] == 0 and result["plaintext_read"] is False
    assert result["backend_qualification_receipt_sha256"] == metadata["backend_qualification_receipt_sha256"]
    assert set(metadata) == q.SECRET_BINDING_V2_FIELDS
    assert set(receipt) == q.SYSTEMD_BACKEND_RECEIPT_V2_FIELDS


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("field", ("credential_alias", "systemd_credential_id", "source_locator"))
def test_v2_cross_provider_substitution_rejected(fixture_store, provider, field):
    other = PROVIDERS[1] if provider == PROVIDERS[0] else PROVIDERS[0]
    wrong = binding(other, "0" * 64)[field]
    bound, _, _ = fixture_store(provider, metadata_changes={field: wrong})
    with pytest.raises(q.Blocked, match="SECRET_BINDING_(POLICY|BOUND_STATE)_INVALID"):
        q.secret_presence(bound)


@pytest.mark.parametrize("change", [
    {"provider_key": "caller-selected"}, {"provider_key": []}, {"capability_scope": ["tts"]},
    {"credential_alias": "secret://other/credential"}, {"systemd_credential_id": "arbitrary"},
    {"source_locator": "/tmp/arbitrary-credential"}, {"authority_granted": True},
    {"provider_runtime_reads": 1}, {"provider_runtime_reads": False},
    {"expected_owner_uid": True}, {"expected_owner_gid": 1}, {"expected_mode": "0644"},
    {"created_for": "VF-SECRET-01"}, {"version": 2.0}, {"version": 3},
    {"hostname": "unapproved.example"}, {"endpoint": "https://unapproved.example"},
    {"credential_path": "/tmp/arbitrary"}, {"provider": "openai"},
])
def test_v2_hostile_metadata_fail_closed(fixture_store, change):
    bound, _, _ = fixture_store(metadata_changes=change)
    with pytest.raises(q.Blocked):
        q.secret_presence(bound)


def test_v1_assemblyai_is_not_a_historical_openai_binding(fixture_store):
    bound, metadata, _ = fixture_store()
    payload = dict(metadata, version=1, provider="assemblyai")
    del payload["provider_key"]
    Path(bound.secret_binding).write_text(json.dumps(payload))
    with pytest.raises(q.Blocked, match="SECRET_BINDING_POLICY_INVALID"):
        q.secret_presence(bound)


@pytest.mark.parametrize("provider", PROVIDERS)
@pytest.mark.parametrize("field", ("provider_key", "credential_alias", "systemd_credential_id", "encrypted_source_path"))
def test_v2_backend_cross_provider_replay_rejected(fixture_store, provider, field):
    other = PROVIDERS[1] if provider == PROVIDERS[0] else PROVIDERS[0]
    bound, _, _ = fixture_store(provider, backend_changes={field: backend(other)[field]})
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_INVALID"):
        q.secret_presence(bound)


@pytest.mark.parametrize("change", [
    {"version": 1}, {"task": "VF-SECRET-01"}, {"actual_provider_credential_decrypted": True},
    {"provider_runtime_reads": 1}, {"provider_calls": 1}, {"provider_calls": False},
    {"runner_source_read": True}, {"runner_source_write": True}, {"runner_credstore_list": True},
    {"host_key_symlink": True}, {"encrypted_source_symlink": True},
    {"encrypted_source_mode": "0644"}, {"encrypted_source_owner": "vf-executor:vf-executor"},
    {"encrypted_source_nonempty": False}, {"synthetic_encrypt": "NOT_TESTED"},
    {"name_binding": "NOT_TESTED"}, {"controlled_service_receive": "NOT_TESTED"},
    {"access_isolation": "NOT_TESTED"}, {"cleanup": "NOT_TESTED"}, {"extra": "unbound"},
])
def test_v2_backend_hostile_fields_rejected(fixture_store, change):
    bound, _, _ = fixture_store(backend_changes=change)
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_INVALID"):
        q.secret_presence(bound)


def test_v2_backend_exact_hash_is_required(fixture_store):
    bound, _, _ = fixture_store(metadata_changes={"backend_qualification_receipt_sha256": "0" * 64})
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_HASH_MISMATCH"):
        q.secret_presence(bound)


def test_v2_cannot_reuse_full_v1_openai_backend_receipt(fixture_store, monkeypatch):
    bound, _, receipt = fixture_store()
    receipt.update(version=1, task="VF-SECRET-01")
    del receipt["provider_key"], receipt["credential_alias"]
    raw = json.dumps(receipt).encode()
    q.SYSTEMD_BACKEND_RECEIPT.write_bytes(raw)
    metadata = binding("assemblyai-transcription", q.sha(raw))
    Path(bound.secret_binding).write_text(json.dumps(metadata))
    with pytest.raises(q.Blocked, match="SYSTEMD_BACKEND_RECEIPT_INVALID"):
        q.secret_presence(bound)


@pytest.mark.parametrize("provider,hostname", [
    ("openai-transcription", "api.openai.com"),
    ("assemblyai-transcription", "api.assemblyai.com"),
])
def test_tls_probe_static_target_no_http_or_secret(monkeypatch, provider, hostname):
    connection, context = MagicMock(), MagicMock()
    tls = context.wrap_socket.return_value.__enter__.return_value
    tls.getpeercert.return_value = {"synthetic_certificate": True}
    create = MagicMock(return_value=connection)
    monkeypatch.setattr(q.socket, "create_connection", create)
    monkeypatch.setattr(q.ssl, "create_default_context", lambda: context)
    result = q.provider_network(provider)
    create.assert_called_once_with((hostname, 443), timeout=10)
    context.wrap_socket.assert_called_once_with(connection.__enter__.return_value, server_hostname=hostname)
    assert result["hostname"] == hostname and result["provider_key"] == provider
    assert result["http_requests"] == result["credential_reads"] == 0
    assert result["probe"] == "TLS_HANDSHAKE_ONLY"
    tls.send.assert_not_called()
    tls.sendall.assert_not_called()


@pytest.mark.parametrize("provider", ["unknown", "https://arbitrary", "api.assemblyai.com", [], None])
def test_unknown_network_provider_rejected_before_connect(monkeypatch, provider):
    monkeypatch.setattr(q.socket, "create_connection", lambda *a, **k: pytest.fail("network"))
    with pytest.raises(q.Blocked, match="PROVIDER_NETWORK_NOT_ALLOWLISTED"):
        q.provider_network(provider)


def test_missing_tls_certificate_blocks(monkeypatch):
    connection, context = MagicMock(), MagicMock()
    context.wrap_socket.return_value.__enter__.return_value.getpeercert.return_value = {}
    monkeypatch.setattr(q.socket, "create_connection", lambda *a, **k: connection)
    monkeypatch.setattr(q.ssl, "create_default_context", lambda: context)
    with pytest.raises(q.Blocked, match="PROVIDER_TLS_UNVERIFIED"):
        q.provider_network("assemblyai-transcription")


@pytest.mark.parametrize("payload", [
    b'ASSEMBLYAI_API_KEY=synthetic-only', b'ASSEMBLYAI_API_KEY: synthetic-only',
    b'{"ASSEMBLYAI_API_KEY":"synthetic-only"}', b'{"Authorization":"synthetic-only"}',
    b'Authorization: synthetic-only', b'Bearer synthetic-only', b'OPENAI_API_KEY=synthetic-only',
])
def test_secret_evidence_patterns_rejected(payload):
    with pytest.raises(q.Blocked, match="SECRET_SCAN_FAILED"):
        q.secret_scan(payload)


def test_hashes_and_public_aliases_are_not_secrets():
    q.secret_scan(json.dumps({"sha256": "a" * 64,
                              "credential_alias": provider_credential_binding(PROVIDERS[1]).credential_alias}).encode())


async def test_v2_qualification_binds_same_network_and_presence(host, tmp_path, mock_probes, fixture_store, monkeypatch):
    # Restore real metadata validators over only the synthetic files.
    # mock_probes installed mocks; use the saved module functions below.
    monkeypatch.setattr(q, "load_secret_binding", REAL_LOAD)
    monkeypatch.setattr(q, "secret_presence", REAL_PRESENCE)
    bound, _, _ = fixture_store()
    monkeypatch.setattr(q, "provider_network", lambda key: {
        "PROVIDER_NETWORK": "VERIFIED", "provider_key": key, "hostname": "api.assemblyai.com", "port": 443,
        "probe": "TLS_HANDSHAKE_ONLY", "tls_certificate_present": True, "http_requests": 0, "credential_reads": 0,
    })
    report = await q.qualify(bound, tmp_path)
    assert report["verdict"] == "CAPABILITY_PROBES_PASS"
    assert report["version"] == 2 and report["task"] == q.QUALIFICATION_V2_TASK
    assert report["provider_identity"]["provider_key"] == "assemblyai-transcription"
    assert report["execution_plane_qualified"] is False
    assert report["credential_reads"] == report["provider_calls"] == 0
    q.verify_qualification_provider_identity(report, q.secret_presence(bound), probes=True)


REAL_LOAD, REAL_PRESENCE = q.load_secret_binding, q.secret_presence


async def test_bad_metadata_prevents_tls_and_presence(host, tmp_path, mock_probes, monkeypatch):
    monkeypatch.setattr(q, "load_secret_binding", lambda *a: (_ for _ in ()).throw(q.Blocked("SECRET_BINDING_POLICY_INVALID")))
    monkeypatch.setattr(q, "provider_network", lambda *a: pytest.fail("TLS before metadata validation"))
    monkeypatch.setattr(q, "secret_presence", lambda *a: pytest.fail("presence before metadata validation"))
    result = await q.qualify(host, tmp_path)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["E6"]["status"] == result["gates"]["E7"]["status"] == "BLOCKED"


def versioned_evidence(secret):
    return {"version": 2, "task": q.QUALIFICATION_V2_TASK,
            "provider_identity": q.qualification_provider_identity(secret)}


@pytest.fixture
def current_v2_secret(fixture_store):
    bound, _, _ = fixture_store()
    return q.secret_presence(bound)


def test_v2_promotion_retains_identity_and_is_not_authority(promotion_inputs, current_v2_secret, monkeypatch):
    host, config, files = promotion_inputs
    secret = current_v2_secret
    identity = versioned_evidence(secret)
    files["/probe"].update(identity)
    files["/security"].update(identity)
    files["/probe"]["gates"]["E7"] = {"status": "PASS", **secret}
    files["/probe"]["gates"]["E6"] = {
        "status": "PASS", "provider_key": secret["provider_key"], "hostname": "api.assemblyai.com",
        "port": 443, "probe": "TLS_HANDSHAKE_ONLY", "tls_certificate_present": True,
        "http_requests": 0, "credential_reads": 0,
    }
    monkeypatch.setattr(q, "secret_presence", lambda *a: secret)
    sealed = {}
    monkeypatch.setattr(q, "persist", lambda root, name, data: sealed.setdefault(name, deepcopy(data)) and "a" * 64)
    result = promotion.promote(host, config)
    assert result["receipt"]["provider_identity"] == identity["provider_identity"]
    assert result["receipt"]["version"] == 2
    assert result["receipt"]["authority_granted"] is False and result["receipt"]["o2"] == "NO"
    assert sealed["evidence-manifest.json"]["provider_identity"] == identity["provider_identity"]


@pytest.mark.parametrize("field,value", [
    ("provider_key", "openai-transcription"), ("credential_alias", "secret://openai/codex-video"),
    ("systemd_credential_id", "openai-codex-video"), ("hostname", "api.openai.com"),
    ("port", 444), ("port", "443"), ("secret_binding_sha256", "0" * 64),
    ("backend_qualification_receipt_sha256", "0" * 64), ("endpoint", "unapproved"),
])
def test_v2_identity_relabeling_rejected(current_v2_secret, field, value):
    document = versioned_evidence(current_v2_secret)
    document["provider_identity"][field] = value
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        q.verify_qualification_provider_identity(document, current_v2_secret)


@pytest.mark.parametrize("changes", [{"version": 1}, {"task": "VF-SECRET-01"}, {"version": 2.0}])
def test_v2_identity_cannot_be_downgraded(current_v2_secret, changes):
    document = {**versioned_evidence(current_v2_secret), **changes}
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        q.verify_qualification_provider_identity(document, current_v2_secret)


def test_v2_evidence_not_accepted_against_v1_openai_presence(current_v2_secret):
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        q.verify_qualification_provider_identity(versioned_evidence(current_v2_secret), {"binding_sha256": "a" * 64})


@pytest.fixture
def v2_artifacts(artifacts, current_v2_secret, monkeypatch):
    host, files, catalog = artifacts
    secret = current_v2_secret
    for path in ("/promotion", "/probe", "/security", "/evidence"):
        files[path].update(deepcopy(versioned_evidence(secret)))
    for path in ("/promotion", "/evidence"):
        files[path]["secret_binding_sha256"] = secret["binding_sha256"]
    files["/probe"]["gates"]["E7"] = {"status": "PASS", **secret}
    files["/probe"]["gates"]["E6"] = {
        "status": "PASS", "provider_key": secret["provider_key"], "hostname": "api.assemblyai.com",
        "port": 443, "probe": "TLS_HANDSHAKE_ONLY", "tls_certificate_present": True,
        "http_requests": 0, "credential_reads": 0,
    }
    monkeypatch.setattr(q, "secret_presence", lambda *a: secret)
    return host, files, catalog


def test_v2_promotion_consumer_accepts_bound_provider(v2_artifacts):
    host, _, catalog = v2_artifacts
    execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("path", ("/promotion", "/probe", "/security", "/evidence"))
@pytest.mark.parametrize("field,value", [
    ("provider_key", "openai-transcription"), ("hostname", "api.openai.com"),
    ("credential_alias", "secret://openai/codex-video"), ("backend_qualification_receipt_sha256", "0" * 64),
])
def test_v2_promotion_consumer_rejects_cross_provider_evidence(v2_artifacts, path, field, value):
    host, files, catalog = v2_artifacts
    files[path]["provider_identity"][field] = value
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("path", ("/promotion", "/probe", "/security", "/evidence"))
def test_v2_consumer_rejects_v1_downgrade(v2_artifacts, path):
    host, files, catalog = v2_artifacts
    files[path].pop("provider_identity")
    files[path]["version"] = 1
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


@pytest.mark.parametrize("field,value", [
    ("provider_key", "openai-transcription"), ("hostname", "api.openai.com"),
    ("http_requests", 1), ("credential_reads", 1), ("tls_certificate_present", False),
])
def test_e6_cannot_differ_from_e7(v2_artifacts, field, value):
    host, files, catalog = v2_artifacts
    files["/probe"]["gates"]["E6"][field] = value
    with pytest.raises(q.Blocked, match="QUALIFICATION_PROVIDER_IDENTITY_MISMATCH"):
        execution.verify_qualification(catalog, host)


async def test_metadata_drift_blocks_v2_qualification(host, tmp_path, mock_probes, fixture_store, monkeypatch):
    bound, _, _ = fixture_store()
    real = q.secret_presence

    def changed(h):
        result = real(h)
        result["binding_sha256"] = "0" * 64
        return result

    monkeypatch.setattr(q, "secret_presence", changed)
    result = await q.qualify(bound, tmp_path)
    assert result["verdict"] == "BLOCKED"
    assert result["gates"]["E7"]["code"] == "SECRET_BINDING_CHANGED_DURING_QUALIFICATION"


def test_v2_security_review_retains_identity_and_isolation(host, tmp_path, fixture_store, monkeypatch):
    bound, _, _ = fixture_store()
    manifest = {"version": 1, "mode": "ZERO_CALL_QUALIFICATION",
                "approved_qualification_workflows": [], "approved_execution_workflows": []}
    monkeypatch.setattr(q, "admission_manifest", lambda *a: manifest)
    expected = {"GITHUB_REPOSITORY": host.execution_repository, "GITHUB_EVENT_NAME": "workflow_dispatch",
                "GITHUB_REF": "refs/heads/main", "GITHUB_WORKFLOW_SHA": host.execution_workflow_commit,
                "GITHUB_WORKFLOW_REF": q.QUALIFICATION_WORKFLOW_REF}
    locked = False

    @contextmanager
    def synthetic_lock(*args):
        nonlocal locked
        if locked:
            raise q.Blocked("CONCURRENT_EXECUTION_BLOCKED")
        locked = True
        try:
            yield
        finally:
            locked = False

    monkeypatch.setattr(q, "plane_lock", synthetic_lock)
    monkeypatch.setattr(q, "persist", lambda *a: "a" * 64)
    Path(bound.kill_switch).write_bytes(b"ENGAGED\n")
    result = security.review(bound, tmp_path, hook=SimpleNamespace(allowed=lambda env, policy: env == expected))
    report = result["report"]
    assert report["version"] == 2 and report["task"] == q.QUALIFICATION_V2_TASK
    assert report["provider_identity"]["provider_key"] == "assemblyai-transcription"
    assert report["hostile_job_tests"] == {name: "PASS" for name in security.HOSTILE_JOB_TESTS}
    assert report["kill_switch"] == "ENGAGED" and report["provider_execution_allowlist"] == "EMPTY"
    assert report["credential_reads"] == report["provider_calls"] == 0
