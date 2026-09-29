"""No-secret, zero-write qualification of the canonical single-dispatch path."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import provider_single_dispatch as runner
from app.auto_edit_models import MediaMetadata
from app.provider_custody import CANONICAL_CUSTODY_BINDING_SHA256
from app.provider_gate_loader import canonical_sha256
from app.provider_runtime_bootstrap import BootstrapBlocked
from test_rc17_asr_w1_lineage_gate_bundle import _active_policy, _asr_context


REPO = Path(__file__).resolve().parents[3]


def _raw(payload):
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()


def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _fresh_operation_custody():
    """A fresh operation in valid custody that already has terminal history."""
    return {
        "result": "OPERATION_CUSTODY_VERIFIED_NOT_EXECUTION_AUTHORIZED",
        "operation_state": "FRESH_OPERATION_NOT_REGISTERED / NOT_CONSUMED",
        "active_operations": [],
        "exact_operation_attempts": 0,
        "reserved_vnd": "0",
        "counts": {
            "operations": 4,
            "attempts": 4,
            "budget_days": 2,
            "circuits": 1,
            "budget_alerts": 1,
        },
        "provider_request_receipt": "ABSENT_FOR_EXACT_OPERATION",
        "idempotency_collision": False,
        "active_reservation": "NONE",
        "target_circuit": {
            "provider_key": "openai-transcription",
            "capability": "asr",
            "state": "closed",
            "consecutive_failures": 0,
            "opened_at": None,
            "half_open_operation_key": None,
        },
        "bundle_mounted": False,
        "credential_reads": 0,
        "provider_calls": 0,
        "authority_granted": False,
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
    allowed_operation = scope.allowed_operations[0]
    operation = SimpleNamespace(
        slot=1,
        sequence=17,
        rc_tag=scope.rc_tag,
        rc_commit=scope.rc_commit,
        governance_main_commit="b" * 40,
        executable_tree_sha256="c" * 64,
        executor_executable_tree_sha256="1" * 64,
        execution_plane_promotion_sha256="2" * 64,
        acceptance_lineage_id=scope.acceptance_lineage_id,
        operation_key=allowed_operation.operation_key,
        authority_receipt_sha256="",
        bundle_sha256="d" * 64,
        prepared_scope_sha256="3" * 64,
        execution_scope_sha256=scope.execution_scope_sha256,
        loaded_scope_sha256=canonical_sha256(scope),
        w1_profile_sha256=scope.asr_prompt_profile_sha256,
        prompt_sha256=scope.asr_prompt_profile.prompt_sha256,
        asset_sha256=_sha(asset.read_bytes()),
        reference_transcript_sha256=_sha(transcript.read_bytes()),
        rights_record_sha256=canonical_sha256({"synthetic_rights": True}),
        credential_alias=scope.credential_alias,
    )
    custody = SimpleNamespace(
        database_name="vf_provider_custody_v3_01",
        system_identifier="123456",
        database_oid=100,
        socket_directory="/run/npd-video-factory/provider-custody/postgresql",
        port=55432,
        qualification_role="vf_custody_qualifier",
        runtime_role="vf_executor_runtime",
    )
    manifest = {
        "operation_id": operation.operation_key,
        "ledger_operation_key": operation.operation_key,
        "custody_binding_sha256": CANONICAL_CUSTODY_BINDING_SHA256,
        "acceptance_lineage_id": operation.acceptance_lineage_id,
        "prepared_scope_sha256": operation.prepared_scope_sha256,
        "execution_scope_sha256": operation.execution_scope_sha256,
        "prompt_sha256": operation.prompt_sha256,
        "w1_profile_sha256": operation.w1_profile_sha256,
        "slot": 1,
    }
    operation_manifest = tmp_path / "operation.json"
    operation_manifest.write_bytes(_raw(manifest))
    authority = {
        "decision": "APPROVED",
        "status": "GRANTED_NOT_CONSUMED",
        "main_provenance": "PASS",
        "rc_tag": operation.rc_tag,
        "rc_commit": operation.rc_commit,
        "governance_main_commit": operation.governance_main_commit,
        "executable_tree_sha256": operation.executable_tree_sha256,
        "executor_executable_tree_sha256": operation.executor_executable_tree_sha256,
        "execution_plane_promotion_sha256": operation.execution_plane_promotion_sha256,
        "dual_ci_provenance_sha256": "e" * 64,
        "executable_rc_ci_run_id": 101,
        "governance_main_ci_run_id": 102,
        "operation_key": operation.operation_key,
        "acceptance_lineage_id": operation.acceptance_lineage_id,
        "prepared_scope_sha256": operation.prepared_scope_sha256,
        "execution_scope_sha256": operation.execution_scope_sha256,
        "loaded_runtime_scope_sha256": operation.loaded_scope_sha256,
        "gate_bundle_sha256": operation.bundle_sha256,
        "operation_manifest_sha256": canonical_sha256(manifest),
        "custody_binding_sha256": CANONICAL_CUSTODY_BINDING_SHA256,
        "asset_sha256": operation.asset_sha256,
        "reference_transcript_sha256": operation.reference_transcript_sha256,
        "rights_record_sha256": operation.rights_record_sha256,
        "asr_prompt_profile_sha256": operation.w1_profile_sha256,
        "prompt_sha256": operation.prompt_sha256,
        "provider_key": "openai-transcription",
        "model": "whisper-1",
        "capability": "asr",
        "language": "vi",
        "slot": 1,
        "operation_1_consumed": False,
        "operation_2_authorized": False,
        "budget_reserved_vnd": "0",
        "bundle_mounted": False,
        "dispatch_requires_separate_execution_task": True,
        "approval_records": {
            gate: {"record_sha256": digest}
            for gate, digest in scope.approval_record_sha256.items()
        },
        "limits": {
            "per_operation_limit_vnd": str(scope.per_operation_limit_vnd),
            "acceptance_window_limit_vnd": str(scope.acceptance_window_limit_vnd),
            "max_attempts": 1,
            "max_concurrent_calls": 1,
            "automatic_retry": False,
            "model_fallback": False,
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
        operation.authority_receipt_sha256 = digest
        return digest

    authority_sha = save_authority()
    provenance = tmp_path / "provenance.json"
    provenance.write_bytes(b"{}")
    paths = runner.SingleDispatchPaths(
        rc_source=REPO,
        operation_binding=tmp_path / "operation-binding.json",
        operation_binding_sha256="f" * 64,
        custody_binding=tmp_path / "custody-binding.json",
        custody_binding_sha256=CANONICAL_CUSTODY_BINDING_SHA256,
        bundle=tmp_path / "bundle.json",
        authority=authority_path,
        authority_sha256=authority_sha,
        provenance=provenance,
        provenance_sha256="e" * 64,
        operation_manifest=operation_manifest,
        asset=asset,
        reference_transcript=transcript,
        rights_record=rights,
        evidence_directory=tmp_path / "evidence",
    )
    monkeypatch.setattr(runner, "load_operation_binding", lambda *_: operation)
    monkeypatch.setattr(runner, "load_custody_binding", lambda *_: custody)
    monkeypatch.setattr(runner, "verify_bound_source", lambda *_: None)

    def fake_git(_repo, *args):
        if args[:3] == ("ls-remote", "--heads", "origin"):
            return operation.governance_main_commit + " refs/heads/main"
        return "1" * 40

    monkeypatch.setattr(runner, "_git", fake_git)

    def fake_bundle(_path, **kwargs):
        if kwargs["expected_bundle_sha256"] != operation.bundle_sha256:
            raise ValueError("bundle mismatch")
        return scope

    monkeypatch.setattr(runner, "load_verified_provider_gate_bundle", fake_bundle)

    def fake_provenance(_raw_value, **kwargs):
        if (
            kwargs["expected_executable_rc_ci_run_id"],
            kwargs["expected_governance_main_ci_run_id"],
        ) != (101, 102):
            raise ValueError("CI binding mismatch")
        return object()

    monkeypatch.setattr(runner, "validate_provider_acceptance_ci_provenance", fake_provenance)
    monkeypatch.setattr(runner, "provider_ci_provenance_sha256", lambda _: "e" * 64)
    monkeypatch.setattr(
        runner,
        "_wav_metadata",
        lambda _: MediaMetadata(
            media_kind="audio",
            detected_content_type="audio/wav",
            format_name="wav",
            duration_seconds=120.852,
            audio_channels=1,
            audio_sample_rate=16000,
        ),
    )
    return SimpleNamespace(
        scope=scope,
        policy=policy,
        operation=operation,
        custody=custody,
        authority=authority,
        paths=paths,
        save_authority=save_authority,
        clock=lambda: scope.valid_from_utc - timedelta(minutes=1),
        active_clock=lambda: scope.valid_from_utc + timedelta(minutes=5),
    )


def test_pre_window_policy_validation_is_shared_without_dispatch():
    scope = _active_policy().execution_gate
    assert scope is not None
    policy = _active_policy().model_copy(update={"global_kill_switch_engaged": True})
    runner._verify_pre_dispatch_contract(
        scope=scope,
        policy=policy,
        context=_asr_context(1),
        now=scope.valid_from_utc - timedelta(minutes=1),
        require_active_window=False,
    )
    with pytest.raises(runner.SingleDispatchBlocked, match="BLOCKED_OUTSIDE_WINDOW"):
        runner._verify_pre_dispatch_contract(
            scope=scope,
            policy=policy,
            context=_asr_context(1),
            now=scope.valid_from_utc - timedelta(minutes=1),
            require_active_window=True,
        )


async def test_check_only_accepts_completed_unrelated_history_without_side_effects(
    qualified_inputs, monkeypatch,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)

    async def custody(*_args, **kwargs):
        assert kwargs == {"role": "qualification"}
        return _fresh_operation_custody()

    monkeypatch.setattr(runner, "inspect_operation_custody", custody)
    monkeypatch.setattr(
        runner, "create_async_engine", lambda *_a, **_k: pytest.fail("engine opened"),
    )
    monkeypatch.setattr(
        runner,
        "OpenAITranscriptionProvider",
        lambda *_a, **_k: pytest.fail("adapter initialized"),
    )
    monkeypatch.setattr(
        runner, "_run_protocol", lambda **_k: pytest.fail("dispatch protocol entered"),
    )
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == "READY_FOR_EXECUTION_PREFLIGHT"
    assert result.ready_for_execution_preflight is True
    assert result.ready_for_provider_dispatch is False
    assert all(
        (
            result.binding_valid,
            result.authority_valid,
            result.bundle_valid,
            result.ledger_valid,
            result.window_policy_valid,
            result.budget_policy_valid,
            result.kill_switch_valid,
            result.duplicate_check_valid,
            result.operation_unconsumed,
            result.provider_receipt_absent,
            result.reservation_absent,
        )
    )
    assert not result.credential_read_performed and not result.provider_call_performed
    assert result.evidence["reservation_invoked"] is False
    assert result.evidence["dispatch_marker_written"] is False
    assert result.evidence["bundle_mounted"] is False
    assert result.evidence["ledger_readback"]["counts"]["operations"] == 4
    assert result.evidence_manifest_sha256 == _sha(runner._canonical_bytes(result.evidence))
    checked = result.evidence["checked_bindings"]
    assert checked["executable_rc_ci_run_id"] == 101
    assert checked["governance_main_ci_run_id"] == 102
    assert checked["custody_binding_sha256"] == CANONICAL_CUSTODY_BINDING_SHA256
    assert checked["ledger_identity"] == "vf_provider_custody_v3_01"


@pytest.mark.parametrize("state,cooldown_elapsed,expected", [
    ("open", False, "CIRCUIT_OPEN"),
    ("open", True, "READY_FOR_EXECUTION_PREFLIGHT"),
    ("half_open", False, "CIRCUIT_HALF_OPEN_NOT_READY"),
    ("half_open", True, "READY_FOR_EXECUTION_PREFLIGHT"),
])
async def test_target_circuit_cooldown_is_checked_before_secret_boundary(
    qualified_inputs, monkeypatch, state, cooldown_elapsed, expected,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    custody = _fresh_operation_custody()
    evaluation_time = fixture.scope.valid_from_utc
    age = fixture.policy.circuit.cooldown_seconds + 1 if cooldown_elapsed else 1
    custody["target_circuit"].update(
        state=state,
        consecutive_failures=1,
        opened_at=evaluation_time - timedelta(seconds=age),
    )

    async def read_only(*_args, **kwargs):
        assert kwargs == {"role": "qualification"}
        return custody

    monkeypatch.setattr(runner, "inspect_operation_custody", read_only)
    result = await runner.validate_single_dispatch(
        fixture.paths,
        runtime_policy=fixture.policy,
        clock=fixture.clock,
    )
    assert result.code == expected
    assert result.credential_read_performed is False
    assert result.provider_call_performed is False


@pytest.mark.parametrize(
    "failure,code",
    [
        ("authority", "AUTHORITY_DECISION_MISMATCH"),
        ("receipt", "AUTHORITY_BOOTSTRAP_HASH_MISMATCH"),
        ("ci", "DUAL_CI_PROVENANCE_INVALID"),
        ("bundle", "BUNDLE_VALIDATION_FAILED"),
        ("main", "GOVERNANCE_MAIN_DRIFT"),
        ("rc", "BOOTSTRAP_RC_TAG_MISMATCH"),
        ("budget", "AUTHORITY_BUDGET_MISMATCH"),
        ("manifest", "OPERATION_MANIFEST_BINDING_MISMATCH"),
        ("custody_hash", "CUSTODY_BINDING_NOT_CANONICAL"),
        ("authority_custody", "AUTHORITY_CUSTODY_IDENTITY_FORBIDDEN"),
        ("manifest_custody", "OPERATION_MANIFEST_CUSTODY_IDENTITY_FORBIDDEN"),
        ("authority_custody_alias", "AUTHORITY_RECEIPT_FIELDS_INVALID"),
        ("authority_custody_wrapper", "AUTHORITY_RECEIPT_FIELDS_INVALID"),
        ("manifest_custody_alias", "OPERATION_MANIFEST_FIELDS_INVALID"),
        ("manifest_custody_wrapper", "OPERATION_MANIFEST_FIELDS_INVALID"),
        ("authority_boolean_integer", "AUTHORITY_LIMITS_MISMATCH"),
        ("manifest_boolean_integer", "OPERATION_MANIFEST_BINDING_MISMATCH"),
    ],
)
async def test_binding_failure_blocks_check_only_and_live_before_secret(
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
        monkeypatch.setattr(
            runner,
            "load_verified_provider_gate_bundle",
            lambda *_a, **_k: (_ for _ in ()).throw(ValueError("mismatch")),
        )
    elif failure == "main":
        monkeypatch.setattr(
            runner, "_git", lambda *_a: "0" * 40 + " refs/heads/main",
        )
    elif failure == "rc":
        monkeypatch.setattr(
            runner,
            "verify_bound_source",
            lambda *_a: (_ for _ in ()).throw(BootstrapBlocked(code)),
        )
    elif failure == "budget":
        fixture.authority["limits"]["per_operation_limit_vnd"] = "501"
    elif failure == "manifest":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["slot"] = 2
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    elif failure == "custody_hash":
        fixture.paths = replace(fixture.paths, custody_binding_sha256="0" * 64)
    elif failure == "authority_custody":
        fixture.authority["ledger"] = {
            "identity": "vf_provider_custody_v3_01",
            "system_identifier": "123456",
            "database_oid": 100,
        }
    elif failure == "manifest_custody":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["ledger_identity"] = "vf_provider_custody_v3_01"
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    elif failure == "authority_custody_alias":
        fixture.authority["ledger_socket"] = "/run/forbidden-alias"
    elif failure == "authority_custody_wrapper":
        fixture.authority["custody_identity"] = {
            "name": "vf_provider_custody_v3_01",
        }
    elif failure == "manifest_custody_alias":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["ledger_system_identifier"] = "7000000000000000001"
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    elif failure == "manifest_custody_wrapper":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["custody_identity"] = {
            "name": "vf_provider_custody_v3_01",
        }
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    elif failure == "authority_boolean_integer":
        fixture.authority["limits"]["max_attempts"] = True
    elif failure == "manifest_boolean_integer":
        manifest = json.loads(fixture.paths.operation_manifest.read_bytes())
        manifest["slot"] = True
        fixture.paths.operation_manifest.write_bytes(_raw(manifest))
    if failure in {
        "authority", "ci", "budget", "authority_custody",
        "authority_custody_alias", "authority_custody_wrapper",
        "authority_boolean_integer",
    }:
        fixture.paths = replace(
            fixture.paths, authority_sha256=fixture.save_authority(),
        )
    monkeypatch.setattr(
        runner,
        "inspect_operation_custody",
        lambda *_a, **_k: pytest.fail("custody reached"),
    )
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.active_clock,
    )
    assert result.code == code
    assert not result.ready_for_execution_preflight
    assert not result.ready_for_provider_dispatch
    with pytest.raises((runner.SingleDispatchBlocked, BootstrapBlocked), match=code):
        await runner.run_single_dispatch(
            fixture.paths,
            runtime_policy=fixture.policy,
            credential_resolver=lambda _: pytest.fail("credential read"),
            clock=fixture.active_clock,
        )


@pytest.mark.parametrize(
    "code",
    [
        "DUPLICATE_OPERATION_BLOCKED",
        "CUSTODY_EXACT_ATTEMPT_COLLISION",
        "CUSTODY_EXACT_ATTEMPT_USAGE_ID_COLLISION",
        "CUSTODY_PROVIDER_RECEIPT_COLLISION",
        "CUSTODY_IDEMPOTENCY_COLLISION",
        "CUSTODY_ACTIVE_RESERVATION_CONFLICT",
        "CUSTODY_EXACT_OPERATION_LINEAGE_MISMATCH",
        "CUSTODY_EXACT_ATTEMPT_LINEAGE_MISMATCH",
    ],
)
async def test_precise_custody_collision_code_is_preserved_without_secret_read(
    qualified_inputs, monkeypatch, code,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)

    async def blocked(*_args, **_kwargs):
        raise BootstrapBlocked(code)

    monkeypatch.setattr(runner, "inspect_operation_custody", blocked)
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == code
    assert result.ready_for_execution_preflight is False
    assert result.ready_for_provider_dispatch is False
    assert result.credential_read_performed is False
    assert result.provider_call_performed is False


async def test_live_entrypoint_uses_runtime_custody_guard_before_credential(
    qualified_inputs, monkeypatch,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    custody = _fresh_operation_custody()
    custody["active_operations"] = [
        {"operation_key": "unrelated-active-operation", "reserved_vnd": "500"},
    ]

    async def read_only(*_args, **kwargs):
        assert kwargs == {"role": "runtime"}
        return custody

    monkeypatch.setattr(runner, "inspect_operation_custody", read_only)
    with pytest.raises(
        runner.SingleDispatchBlocked, match="CHECK_ONLY_OPERATION_CUSTODY_INVALID",
    ):
        await runner.run_single_dispatch(
            fixture.paths,
            runtime_policy=fixture.policy,
            credential_resolver=lambda _: pytest.fail("credential read"),
            clock=fixture.active_clock,
        )


async def test_live_open_circuit_blocks_before_credential_read(
    qualified_inputs, monkeypatch,
):
    fixture = qualified_inputs
    monkeypatch.setattr(runner, "_verify_pre_dispatch_contract", lambda **_: None)
    now = fixture.active_clock()
    custody = _fresh_operation_custody()
    custody["target_circuit"].update(
        state="open",
        consecutive_failures=1,
        opened_at=now - timedelta(seconds=1),
    )

    async def read_only(*_args, **kwargs):
        assert kwargs == {"role": "runtime"}
        return custody

    monkeypatch.setattr(runner, "inspect_operation_custody", read_only)
    with pytest.raises(runner.SingleDispatchBlocked, match="CIRCUIT_OPEN"):
        await runner.run_single_dispatch(
            fixture.paths,
            runtime_policy=fixture.policy,
            credential_resolver=lambda _: pytest.fail("credential read"),
            clock=fixture.active_clock,
        )


async def test_unexpected_error_is_typed_and_not_serialized(
    qualified_inputs, monkeypatch,
):
    fixture = qualified_inputs
    monkeypatch.setattr(
        runner,
        "load_operation_binding",
        lambda *_: (_ for _ in ()).throw(RuntimeError("Bearer must-not-appear")),
    )
    result = await runner.validate_single_dispatch(
        fixture.paths, runtime_policy=fixture.policy, clock=fixture.clock,
    )
    assert result.code == "CHECK_ONLY_VALIDATION_FAILED"
    assert "must-not-appear" not in json.dumps(result.evidence)
    assert result.ready_for_provider_dispatch is False


@pytest.mark.parametrize(
    "failure,code",
    [
        ("kill_switch", "RUNTIME_SAFETY_POLICY_NOT_AUTHORIZED"),
        ("expired", "WINDOW_EXPIRED"),
    ],
)
async def test_policy_failure_fails_closed(
    qualified_inputs, monkeypatch, failure, code,
):
    fixture = qualified_inputs
    monkeypatch.setattr(
        runner,
        "inspect_operation_custody",
        lambda *_a, **_k: pytest.fail("custody reached"),
    )
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
