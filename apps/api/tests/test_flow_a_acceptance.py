from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.flow_a_acceptance import (
    FlowAAcceptanceBundle,
    FlowAAcceptancePolicy,
    evaluate_flow_a,
)


def _provider(seed: str) -> dict[str, object]:
    return {
        "provider_key": f"fixture-{seed}",
        "model_or_workflow": f"deterministic-{seed}",
        "fixture": True,
        "external_call": False,
        "paid": False,
        "real_provider_tested": False,
        "production_eligible": False,
        "request_sha256": hashlib.sha256(f"request:{seed}".encode()).hexdigest(),
        "response_or_artifact_sha256": hashlib.sha256(f"response:{seed}".encode()).hexdigest(),
        "charged_cost_vnd": 0,
        "currency": "VND",
        "secret_recorded": False,
    }


def _run(sequence: int) -> dict[str, object]:
    first = "a" if sequence == 1 else "b"
    second = "c" if sequence == 1 else "d"
    start_hour = 1 if sequence == 1 else 3
    return {
        "sequence": sequence,
        "run_id": f"flow-a-contract-{sequence}",
        "release_candidate_commit": "4" * 40,
        "started_at_utc": f"2026-08-28T{start_hour:02d}:00:00Z",
        "completed_at_utc": f"2026-08-28T{start_hour + 1:02d}:00:00Z",
        "input_sha256": first * 64,
        "source_duration_seconds": 120,
        "source_width": 1920,
        "source_height": 1080,
        "source_has_audio": True,
        "source_language": "vi",
        "rights_record_id": f"RIGHTS-OWNED-{sequence:03d}",
        "input_owned_or_licensed": True,
        "asr": _provider("asr"),
        "vision": _provider("vision"),
        "tts": _provider("tts"),
        "reference_transcript": (
            "Dự án Vịnh Tiên có giá 100 triệu đồng và CTA đăng ký tư vấn hôm nay."
        ),
        "hypothesis_transcript": (
            "Dự án Vịnh Tiên có giá 100 triệu đồng và CTA đăng ký tư vấn hôm nay."
        ),
        "critical_terms": ["Vịnh Tiên", "100 triệu đồng", "đăng ký tư vấn"],
        "reference_scene_boundaries_seconds": [20, 50, 85],
        "predicted_scene_boundaries_seconds": [20.2, 49.9, 85.3],
        "reframe_safe_coverage": 0.98,
        "subtitle_drift_seconds": [0.08, 0.12, 0.18, 0.2, 0.32],
        "broll_asset_sha256": [second * 64],
        "broll_rights_record_ids": [f"RIGHTS-BROLL-{sequence:03d}"],
        "music_asset_sha256": "e" * 64,
        "music_rights_record_id": f"RIGHTS-MUSIC-{sequence:03d}",
        "timeline_sha256": "f" * 64,
        "approved_timeline_sha256": "f" * 64,
        "preview_sha256": "1" * 64,
        "final_video_sha256": "2" * 64,
        "full_decode_passed": True,
        "black_frame_qc_passed": True,
        "silence_qc_passed": True,
        "frozen_frame_qc_passed": True,
        "av_sync_qc_passed": True,
        "provider_receipts_valid": True,
        "restart_recovered": True,
        "production_path_tested": False,
        "human_review_passed": False,
        "human_review_final_sha256": None,
        "cost_ledger_total_vnd": 0,
        "currency": "VND",
        "external_action_performed": False,
        "publish_requested": False,
    }


def _bundle() -> dict[str, object]:
    return {
        "schema_version": 1,
        "checkpoint": "V3-01-04",
        "release_candidate_commit": "4" * 40,
        "environment": "LOCAL",
        "gates": {
            "g01_credentials": False,
            "g02_vnd_budget": False,
            "g03_rights_inputs": False,
            "g04_production_like_staging": False,
            "g11_human_quality": False,
            "approval_ids": [],
        },
        "safety": {
            "external_execution_enabled": False,
            "paid_execution_enabled": False,
            "global_kill_switch_engaged": True,
            "daily_budget_vnd": 0,
            "production_write_performed": False,
            "publish_performed": False,
        },
        "runs": [_run(1), _run(2)],
        "secret_recorded": False,
    }


def _real_provider(provider: dict[str, object]) -> None:
    provider.update(
        {
            "provider_key": "self-hosted-production-test",
            "model_or_workflow": "locked-production-workflow-v1",
            "fixture": False,
            "real_provider_tested": True,
            "production_eligible": True,
        }
    )


def test_two_mock_runs_pass_contract_but_remain_owner_gate_blocked() -> None:
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(_bundle()))
    assert evaluation.two_consecutive_runs is True
    assert evaluation.implemented.status == "PASS"
    assert evaluation.mock_tested.status == "PASS"
    assert evaluation.real_provider_tested.status == "BLOCKED"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.pending_owner_gates == ["G-01", "G-02", "G-03", "G-04", "G-11"]
    assert evaluation.verdict == "BLOCKED"
    assert evaluation.cost_total_vnd == 0


def test_fixture_cannot_be_promoted_to_real_provider_evidence() -> None:
    payload = _bundle()
    payload["runs"][0]["asr"]["real_provider_tested"] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match="fixture evidence cannot be promoted"):
        FlowAAcceptanceBundle.model_validate(payload)


def test_two_runs_must_use_same_locked_commit_and_distinct_inputs() -> None:
    payload = _bundle()
    payload["runs"][1]["release_candidate_commit"] = "5" * 40  # type: ignore[index]
    payload["runs"][1]["input_sha256"] = "a" * 64  # type: ignore[index]
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    assert evaluation.two_consecutive_runs is False
    assert evaluation.mock_tested.status == "FAIL"
    assert evaluation.verdict == "FAIL"


def test_asr_wer_and_critical_terms_are_measured_not_declared() -> None:
    payload = _bundle()
    payload["runs"][0]["hypothesis_transcript"] = "Dự án khác không có số tiền."  # type: ignore[index]
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    failures = evaluation.run_metrics[0].failures
    assert "ASR_WER_EXCEEDS_15_PERCENT" in failures
    assert "CRITICAL_TERM_ACCURACY_BELOW_100_PERCENT" in failures
    assert evaluation.mock_tested.status == "FAIL"


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("predicted_scene_boundaries_seconds", [5, 10, 15], "SCENE_BOUNDARY_F1_BELOW_0_80"),
        ("reframe_safe_coverage", 0.94, "REFRAME_SAFE_COVERAGE_BELOW_95_PERCENT"),
        ("subtitle_drift_seconds", [0.1, 0.2, 0.6], "SUBTITLE_P95_DRIFT_EXCEEDS_500MS"),
    ],
)
def test_measured_media_quality_thresholds_fail_closed(
    field: str,
    value: object,
    failure: str,
) -> None:
    payload = _bundle()
    payload["runs"][0][field] = value  # type: ignore[index]
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    assert failure in evaluation.run_metrics[0].failures
    assert evaluation.verdict == "FAIL"


def test_approval_restart_and_qc_evidence_are_hash_bound() -> None:
    payload = _bundle()
    payload["runs"][0]["approved_timeline_sha256"] = "3" * 64  # type: ignore[index]
    payload["runs"][0]["restart_recovered"] = False  # type: ignore[index]
    payload["runs"][0]["full_decode_passed"] = False  # type: ignore[index]
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "APPROVAL_NOT_BOUND_TO_TIMELINE",
        "RESTART_RECOVERY_NOT_PROVEN",
        "TECHNICAL_QC_FAILED",
    }


def test_real_axis_can_pass_while_g04_and_g11_remain_blocked() -> None:
    payload = _bundle()
    payload["gates"].update(  # type: ignore[union-attr]
        {"g01_credentials": True, "g02_vnd_budget": True, "g03_rights_inputs": True}
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        _real_provider(run["asr"])
        _real_provider(run["vision"])
        _real_provider(run["tts"])
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    assert evaluation.real_provider_tested.status == "PASS"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.verdict == "BLOCKED"


def test_all_axes_require_production_path_and_hash_bound_human_review() -> None:
    payload = _bundle()
    payload["environment"] = "STAGING_PRODUCTION_LIKE"
    payload["gates"].update(  # type: ignore[union-attr]
        {
            "g01_credentials": True,
            "g02_vnd_budget": True,
            "g03_rights_inputs": True,
            "g04_production_like_staging": True,
            "g11_human_quality": True,
        }
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        _real_provider(run["asr"])
        _real_provider(run["vision"])
        _real_provider(run["tts"])
        run["production_path_tested"] = True
        run["human_review_passed"] = True
        run["human_review_final_sha256"] = run["final_video_sha256"]
    evaluation = evaluate_flow_a(FlowAAcceptanceBundle.model_validate(payload))
    assert evaluation.verdict == "PASS"
    assert evaluation.pending_owner_gates == []


def test_currency_is_vnd_only() -> None:
    payload = deepcopy(_bundle())
    payload["runs"][0]["currency"] = "USD"  # type: ignore[index]
    with pytest.raises(ValidationError):
        FlowAAcceptanceBundle.model_validate(payload)


def test_checked_in_flow_a_policy_matches_strict_runtime_contract() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (repository_root / "packages" / "contracts" / "flow-a-acceptance.v1.json").read_text(
            encoding="utf-8"
        )
    )
    policy = FlowAAcceptancePolicy.model_validate(payload)
    assert policy.currency == "VND"
    assert policy.required_owner_gates == ("G-01", "G-02", "G-03", "G-04", "G-11")
    assert policy.external_action_allowed_during_contract_test is False
