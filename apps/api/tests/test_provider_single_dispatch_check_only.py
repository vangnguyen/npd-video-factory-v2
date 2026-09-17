"""No-secret, no-reservation qualification of the canonical single-dispatch runner."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.auto_edit_models import MediaMetadata
from app.provider_gate_loader import canonical_sha256
from app.provider_runtime_bootstrap import BootstrapBlocked
from app import provider_runtime_bootstrap, provider_single_dispatch as runner
from test_rc17_asr_w1_lineage_gate_bundle import _active_policy, _asr_context


REPO = Path(__file__).resolve().parents[3]


def _raw(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _virgin_custody():
    return {
        "result": "CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED",
        "operation_state": "VIRGIN_NOT_REGISTERED / NOT_CONSUMED",
        "control_present": True,
        "active_operations": 0,
        "exact_operation_attempts": 0,
        "reserved_vnd": "0",
        "counts": {"operations": 0, "attempts": 0, "budget_days": 0,
                   "circuits": 0, "budget_alerts": 0},
        "provider_request_receipt_mapping": "NO_OPERATION_OR_ATTEMPT_IN_THIS_BOUND_NAMESPACE",
        "active_reservation": "NONE_IN_THIS_BOUND_NAMESPACE",
        "ledger_bootstrap_write": {"ensure_state_invoked": False},
    }


@pytest.fixture
def qualified_inputs(tmp_path, monkeypatch):
    scope = _active_policy().execution_gate
    assert scope is not None
    policy = _active_policy().model_copy(update={"global_kill_switch_engaged": True})
    asset = tmp_path / "asset.wav"
    asset.write_bytes(b"synthetic audio fixture")
    transcript = tmp_path / "reference.txt"
    transcript.write_bytes(b"synthetic reference")
    rights = tmp_path / "rights.json"
    rights.write_bytes(_raw({"synthetic_rights": True}))
    operation = scope.allowed_operations[0]
    binding = SimpleNamespace(
        slot=1, rc_tag=scope.rc_tag, rc_commit=scope.rc_commit,
        governance_main_commit="b" * 40, executable_tree_sha256="c" * 64,
        acceptance_lineage_id=scope.acceptance_lineage_id,
        operation_key=operation.operation_key, database_name="vf_synthetic_ledger",
        system_identifier="123456", database_oid=100,
        authority_receipt_sha256="", bundle_sha256="d" * 64,
        execution_scope_sha256=scope.execution_scope_sha256,
        scope_sha256=canonical_sha256(scope),
        w1_profile_sha256=scope.asr_prompt_profile_sha256,
        prompt_sha256=scope.asr_prompt_profile.prompt_sha256,
        asset_sha256=_sha(asset.read_bytes()),
        reference_transcript_sha256=_sha(transcript.read_bytes()),
        rights_record_sha256=canonical_sha256({"synthetic_rights": True}),
    )
    manifest = {
        "operation_id": binding.operation_key,
        "ledger_operation_key": binding.operation_key,
        "ledger_identity": binding.database_name,
        "acceptance_lineage_id": binding.acceptance_lineage_id,
        "execution_scope_sha256": binding.execution_scope_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "w1_profile_sha256": binding.w1_profile_sha256,
        "slot": 1,
    }
    operation_manifest = tmp_path / "operation.json"
    operation_manifest.write_bytes(_raw(manifest))
    authority = {
        "decision": "APPROVED", "status": "GRANTED_NOT_CONSUMED",
        "main_provenance": "PASS", "rc_tag": binding.rc_tag,
        "rc_commit": binding.rc_commit,
        "governance_main_commit": binding.governance_main_commit,
        "executable_tree_sha256": binding.executable_tree_sha256,
        "dual_ci_provenance_sha256": "e" * 64,
        "executable_rc_ci_run_id": 101, "governance_main_ci_run_id": 102,
        "operation_key": binding.operation_key,
        "acceptance_lineage_id": binding.acceptance_lineage_id,
        "execution_scope_sha256": binding.execution_scope_sha256,
        "loaded_runtime_scope_sha256": binding.scope_sha256,
        "gate_bundle_sha256": binding.bundle_sha256,
        "operation_manifest_sha256": canonical_sha256(manifest),
        "asset_sha256": binding.asset_sha256,
        "reference_transcript_sha256": binding.reference_transcript_sha256,
        "rights_record_sha256": binding.rights_record_sha256,
        "asr_prompt_profile_sha256": binding.w1_profile_sha256,
        "prompt_sha256": binding.prompt_sha256,
        "provider_key": "openai-transcription", "model": "whisper-1",
        "capability": "asr", "language": "vi", "slot": 1,
        "operation_1_consumed": False, "operation_2_authorized": False,
        "budget_reserved_vnd": "0", "bundle_mounted": False,
        "dispatch_requires_separate_execution_task": True,
        "ledger": {"identity": binding.database_name,
                   "system_identifier": binding.system_identifier,
                   "database_oid": binding.database_oid},
        "approval_records": {
            gate: {"record_sha256": digest}
            for gate, digest in scope.approval_record_sha256.items()
        },
        "limits": {
            "per_operation_limit_vnd": str(scope.per_operation_limit_vnd),
            "acceptance_window_limit_vnd": str(scope.acceptance_window_limit_vnd),
            "max_attempts": 1, "max_concurrent_calls": 1,
            "automatic_retry": False, "model_fallback": False,
            "provider_http_timeout_seconds": scope.provider_http_timeout_seconds,
            "controller_hard_timeout_seconds": scope.controller_hard_timeout_seconds,
        },
        "valid_from_utc": scope.valid_from_utc.isoformat().replace("+00:00", "Z"),
        "expires_at_utc": scope.expires_at_utc.isoformat().replace("+00:00", "Z"),
        "asset_bytes": asset.stat().st_size,
        "asset_duration_seconds": 120.852,
    }
    authority_path = tmp_path / "authority.json"

    def save_authority():
        authority_path.write_bytes(_raw(authority))
        digest = _sha(authority_path.read_bytes())
        binding.authority_receipt_sha256 = digest
        return digest

    authority_sha = save_authority()
    provenance = tmp_path / "provenance.json"
    provenance.write_bytes(b"{}")
    paths = runner.SingleDispatchPaths(
        rc_source=REPO, binding=tmp_path / "binding.json",
        binding_sha256="f" * 64, bundle=tmp_path / "bundle.json",
        authority=authority_path, authority_sha256=authority_sha,
        provenance=provenance, provenance_sha256="e" * 64,
        operation_manifest=operation_manifest, asset=asset,
        reference_transcript=transcript, rights_record=rights,
        evidence_directory=tmp_path / "evidence",
    )
    monkeypatch.setattr(runner, "load_binding", lambda *_: binding)
    monkeypatch.setattr(provider_runtime_bootstrap, "verify_bound_source", lambda *_: None)

    def fake_git(_repo, *args):
        if args[:3] == ("ls-remote", "--heads", "origin"):
            return binding.governance_main_commit + " refs/heads/main"
        return "1" * 40

    monkeypatch.setattr(runner, "_git", fake_git)

    def fake_bundle(_path, **kw):
        if kw["expected_bundle_sha256"] != binding.bundle_sha256:
            raise ValueError("bundle mismatch")
        return scope

    monkeypatch.setattr(runner, "load_verified_provider_gate_bundle", fake_bundle)

    def fake_provenance(_raw_value, **kw):
        if (kw["expected_executable_rc_ci_run_id"], kw["expected_governance_main_ci_run_id"]) != (101, 102):
            raise ValueError("CI binding mismatch")
        return object()

    monkeypatch.setattr(runner, "validate_provider_acceptance_ci_provenance", fake_provenance)
    monkeypatch.setattr(runner, "provider_ci_provenance_sha256", lambda _: "e" * 64)
    monkeypatch.setattr(runner, "_wav_metadata", lambda _: MediaMetadata(
        media_kind="audio", detected_content_type="audio/wav", format_name="wav",
        duration_seconds=120.852, audio_channels=1, audio_sample_rate=16000,
    ))
    return SimpleNamespace(
        scope=scope, policy=policy, binding=binding, authority=authority,
        paths=paths, save_authority=save_authority,
        clock=lambda: scope.valid_from_utc - timedelta(minutes=1),
        active_clock=lambda: scope.valid_from_utc + timedelta(minutes=5),
    )


def test_pre_window_policy_validation_is_shared_without_dispatch():
    scope = _active_policy().execution_gate
    assert scope is not None
    policy = _active_policy().model_copy(update={"global_kill_switch_engaged": True})
    runner._verify_pre_dispatch_contract(
        scope=scope, policy=policy, context=_asr_context(1),
        now=scope.valid_from_utc - timedelta(minutes=1), require_active_window=False,
    )
    with pytest.raises(runner.SingleDispatchBlocked, match="BLOCKED_OUTSIDE_WINDOW"):
        runner._verify_pre_dispatch_contract(
            scope=scope, policy=policy, context=_asr_context(1),
            now=scope.valid_from_utc - timedelta(minutes=1), require_active_window=True,
        )


async def test_check_only_valid_and_never_enters_execution_path(qualified_inputs, monkeypatch):
    fixture = qualified_inputs
    # The static validator is real. A synthetic media hash makes the RC-17
    # rights preflight inapplicable here; that shared helper is tested above.
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    async def custody(*_args, **kwargs):
        assert kwargs == {"require_virgin_namespace": True}
        return _virgin_custody()
    monkeypatch.setattr(runner, "bootstrap_custody", custody)
    monkeypatch.setattr(runner, "create_async_engine", lambda *_a, **_k: pytest.fail("engine opened"))
    monkeypatch.setattr(runner, "OpenAITranscriptionProvider", lambda *_a, **_k: pytest.fail("adapter initialized"))
    monkeypatch.setattr(runner, "_run_protocol", lambda **_k: pytest.fail("dispatch protocol entered"))
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == "READY_FOR_EXECUTION_PREFLIGHT"
    assert result.ready_for_execution_preflight is True
    assert result.ready_for_provider_dispatch is False
    assert all((result.binding_valid, result.authority_valid, result.bundle_valid,
                result.ledger_valid, result.window_policy_valid, result.budget_policy_valid,
                result.kill_switch_valid, result.duplicate_check_valid,
                result.operation_unconsumed, result.provider_receipt_absent,
                result.reservation_absent))
    assert not result.credential_read_performed and not result.provider_call_performed
    assert result.evidence["reservation_invoked"] is False
    assert result.evidence["dispatch_marker_written"] is False
    assert result.evidence["bundle_mounted"] is False
    assert result.evidence_manifest_sha256 == _sha(runner._canonical_bytes(result.evidence))
    assert result.evidence["checked_bindings"]["executable_rc_ci_run_id"] == 101
    assert result.evidence["checked_bindings"]["governance_main_ci_run_id"] == 102


@pytest.mark.parametrize("failure,code", [
    ("authority", "AUTHORITY_DECISION_MISMATCH"),
    ("receipt", "AUTHORITY_BOOTSTRAP_HASH_MISMATCH"),
    ("ci", "DUAL_CI_PROVENANCE_INVALID"),
    ("bundle", "BUNDLE_VALIDATION_FAILED"),
    ("main", "GOVERNANCE_MAIN_DRIFT"),
    ("rc", "BOOTSTRAP_RC_TAG_MISMATCH"),
    ("budget", "AUTHORITY_BUDGET_MISMATCH"),
    ("manifest", "OPERATION_MANIFEST_BINDING_MISMATCH"),
])
async def test_binding_failure_blocks_both_check_only_and_real_before_secret(
    qualified_inputs, monkeypatch, failure, code,
):
    fixture = qualified_inputs
    if failure == "authority":
        fixture.authority["decision"] = "REJECTED"
    elif failure == "receipt":
        fixture.paths = replace(fixture.paths, authority_sha256="0" * 64)
    elif failure == "ci":
        fixture.authority["executable_rc_ci_run_id"] = 999
    elif failure == "bundle":
        monkeypatch.setattr(runner, "load_verified_provider_gate_bundle", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("mismatch")))
    elif failure == "main":
        monkeypatch.setattr(runner, "_git", lambda *_a: "0" * 40 + " refs/heads/main")
    elif failure == "rc":
        monkeypatch.setattr(provider_runtime_bootstrap, "verify_bound_source", lambda *_a: (_ for _ in ()).throw(BootstrapBlocked(code)))
    elif failure == "budget":
        fixture.authority["limits"]["per_operation_limit_vnd"] = "501"
    elif failure == "manifest":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["slot"] = 2
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    if failure in {"authority", "ci", "budget"}:
        fixture.paths = replace(fixture.paths, authority_sha256=fixture.save_authority())
    monkeypatch.setattr(runner, "bootstrap_custody", lambda *_a, **_k: pytest.fail("ledger reached"))
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.active_clock,
    )
    assert result.code == code
    assert not result.ready_for_execution_preflight
    assert not result.ready_for_provider_dispatch
    with pytest.raises((runner.SingleDispatchBlocked, BootstrapBlocked), match=code):
        await runner.run_single_dispatch(
            fixture.paths, runtime_policy=fixture.policy,
            credential_resolver=lambda _: pytest.fail("credential read"),
            clock=fixture.active_clock,
        )


@pytest.mark.parametrize("mutation", [
    "consumed", "provider_receipt", "reservation", "duplicate", "idempotency",
    "missing_count",
])
async def test_ledger_collision_fails_closed(qualified_inputs, monkeypatch, mutation):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    custody = _virgin_custody()
    if mutation == "consumed":
        custody["operation_state"] = "CONSUMED"
    elif mutation == "provider_receipt":
        custody["exact_operation_attempts"] = 1
    elif mutation == "reservation":
        custody["reserved_vnd"] = "500"
    elif mutation == "duplicate":
        custody["counts"]["operations"] = 1
    elif mutation == "idempotency":
        custody["counts"]["attempts"] = 1
    elif mutation == "missing_count":
        del custody["counts"]["attempts"]
    async def read_only(*_a, **_k):
        return custody
    monkeypatch.setattr(runner, "bootstrap_custody", read_only)
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == "CHECK_ONLY_LEDGER_NOT_VIRGIN"
    assert result.ready_for_execution_preflight is False
    assert result.ready_for_provider_dispatch is False


async def test_live_entrypoint_shares_virgin_custody_guard_before_credential(
    qualified_inputs, monkeypatch,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    custody = _virgin_custody()
    custody["counts"]["operations"] = 1
    async def read_only(*_a, **_k):
        return custody
    monkeypatch.setattr(runner, "bootstrap_custody", read_only)
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.active_clock,
    )
    assert result.code == "CHECK_ONLY_LEDGER_NOT_VIRGIN"
    with pytest.raises(runner.SingleDispatchBlocked, match="CHECK_ONLY_LEDGER_NOT_VIRGIN"):
        await runner.run_single_dispatch(
            fixture.paths, runtime_policy=fixture.policy,
            credential_resolver=lambda _: pytest.fail("credential read"),
            clock=fixture.active_clock,
        )


async def test_unexpected_error_is_typed_and_not_serialized(qualified_inputs, monkeypatch):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "load_binding", lambda *_: (_ for _ in ()).throw(RuntimeError("Bearer must-not-appear")))
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == "CHECK_ONLY_VALIDATION_FAILED"
    assert "must-not-appear" not in json.dumps(result.evidence)
    assert result.ready_for_provider_dispatch is False


@pytest.mark.parametrize("failure,code", [
    ("kill_switch", "RUNTIME_SAFETY_POLICY_NOT_AUTHORIZED"),
    ("expired", "WINDOW_EXPIRED"),
])
async def test_policy_failure_fails_closed(qualified_inputs, monkeypatch, failure, code):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "bootstrap_custody", lambda *_a, **_k: pytest.fail("ledger reached"))
    policy = fixture.policy
    clock = fixture.clock
    if failure == "kill_switch":
        policy = policy.model_copy(update={"global_kill_switch_engaged": False})
    else:
        clock = lambda: fixture.scope.expires_at_utc + timedelta(seconds=1)
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=policy, clock=clock,
    )
    assert result.code == code
    assert not result.ready_for_execution_preflight
