from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.flow_b_acceptance import (
    FlowBAcceptanceBundle,
    FlowBAcceptancePolicy,
    evaluate_flow_b,
)


CAPABILITIES = ("research", "stock", "ai_image", "ai_video", "vision", "tts")


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _provider(capability: str, sequence: int) -> dict[str, object]:
    return {
        "capability": capability,
        "provider_key": f"fixture-{capability}",
        "model_or_workflow": f"deterministic-{capability}-v1",
        "fixture": True,
        "external_call": False,
        "paid": False,
        "real_provider_tested": False,
        "production_eligible": False,
        "request_sha256": _sha(f"request:{sequence}:{capability}"),
        "response_or_artifact_sha256": _sha(f"response:{sequence}:{capability}"),
        "charged_cost_vnd": 0,
        "currency": "VND",
        "secret_recorded": False,
    }


def _source(sequence: int, index: int) -> dict[str, object]:
    return {
        "source_id": f"SRC-{sequence}-{index}",
        "source_locator_sha256": _sha(f"locator:{sequence}:{index}"),
        "title": f"Nguồn kiểm thử {index}",
        "publisher": "NPD fixture publisher",
        "retrieved_at_utc": f"2026-08-28T0{sequence}:0{index}:00Z",
        "fixture": True,
        "real_source_tested": False,
        "response_sha256": _sha(f"source-response:{sequence}:{index}"),
        "secret_recorded": False,
    }


def _asset(
    sequence: int,
    kind: str,
    provider_key: str | None,
    shots: list[str],
    relevance: float | None,
) -> dict[str, object]:
    return {
        "asset_id": f"ASSET-{sequence}-{kind}",
        "kind": kind,
        "asset_sha256": _sha(f"asset:{sequence}:{kind}"),
        "provider_key": provider_key,
        "provider_receipt_sha256": _sha(f"receipt:{sequence}:{kind}"),
        "rights_record_id": f"RIGHTS-{sequence}-{kind}",
        "transformation_lineage_sha256": _sha(f"lineage:{sequence}:{kind}"),
        "used_in_shot_ids": shots,
        "visual_relevance_score": relevance,
        "decoded_or_verified": True,
        "fixture": True,
    }


def _run(sequence: int) -> dict[str, object]:
    start_hour = 1 if sequence == 1 else 3
    shots = ["SHOT-01", "SHOT-02", "SHOT-03"]
    sources = [_source(sequence, index) for index in range(1, 4)]
    claims = [
        {
            "claim_id": f"CLAIM-{index}",
            "claim_sha256": _sha(f"claim:{sequence}:{index}"),
            "source_ids": [sources[index - 1]["source_id"]],
            "verification_status": "verified",
            "included_in_script": True,
        }
        for index in range(1, 4)
    ]
    return {
        "sequence": sequence,
        "run_id": f"flow-b-contract-{sequence}",
        "release_candidate_commit": "6" * 40,
        "started_at_utc": f"2026-08-28T{start_hour:02d}:00:00Z",
        "completed_at_utc": f"2026-08-28T{start_hour + 1:02d}:00:00Z",
        "business_brief_sha256": _sha("Vịnh Tiên owned brief"),
        "idea_id": "IDEA-VINH-TIEN-001",
        "research_sources": sources,
        "claim_map": claims,
        "script_claim_ids": [f"CLAIM-{index}" for index in range(1, 4)],
        "script_sha256": _sha(f"script:{sequence}"),
        "originality_similarity_scores": [0.12, 0.18, 0.24],
        "storyboard_shot_ids": shots,
        "media_plan_shot_ids": shots,
        "providers": [_provider(capability, sequence) for capability in CAPABILITIES],
        "assets": [
            _asset(sequence, "stock", "fixture-stock", ["SHOT-01"], 0.92),
            _asset(sequence, "ai_image", "fixture-ai_image", ["SHOT-02"], 0.90),
            _asset(sequence, "ai_video", "fixture-ai_video", ["SHOT-03"], 0.88),
            _asset(sequence, "music", None, [], None),
        ],
        "narration_expected_duration_seconds": 30,
        "narration_actual_duration_seconds": 30.9,
        "tts_audio_sha256": _sha(f"tts:{sequence}"),
        "subtitle_drift_seconds": [0.08, 0.12, 0.18, 0.20, 0.36],
        "integrated_loudness_lufs": -15.0,
        "true_peak_dbfs": -2.0,
        "clipping_sample_count": 0,
        "speech_music_ratio_db": 8.0,
        "ducking_applied": True,
        "timeline_sha256": _sha(f"timeline:{sequence}"),
        "approved_timeline_sha256": _sha(f"timeline:{sequence}"),
        "render_input_sha256": _sha(f"render-input:{sequence}"),
        "approved_render_input_sha256": _sha(f"render-input:{sequence}"),
        "preview_sha256": _sha(f"preview:{sequence}"),
        "final_video_sha256": _sha(f"final:{sequence}"),
        "render_width": 1080,
        "render_height": 1920,
        "render_duration_seconds": 30.9,
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
        "checkpoint": "V3-01-05",
        "release_candidate_commit": "6" * 40,
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


def _mark_real_provider(provider: dict[str, object]) -> None:
    provider.update(
        {
            "provider_key": f"self-hosted-{provider['capability']}",
            "model_or_workflow": f"locked-{provider['capability']}-workflow-v1",
            "fixture": False,
            "real_provider_tested": True,
            "production_eligible": True,
        }
    )


def _mark_real_run(run: dict[str, object]) -> None:
    provider_key_map: dict[str, str] = {}
    for provider in run["providers"]:  # type: ignore[index]
        old_key = str(provider["provider_key"])
        _mark_real_provider(provider)
        provider_key_map[old_key] = str(provider["provider_key"])
    for source in run["research_sources"]:  # type: ignore[index]
        source["fixture"] = False
        source["real_source_tested"] = True
    for asset in run["assets"]:  # type: ignore[index]
        if asset["provider_key"] in provider_key_map:
            asset["provider_key"] = provider_key_map[str(asset["provider_key"])]
        asset["fixture"] = False


def test_two_fixture_runs_pass_contract_but_remain_owner_gate_blocked() -> None:
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(_bundle()))
    assert evaluation.two_consecutive_runs is True
    assert evaluation.implemented.status == "PASS"
    assert evaluation.mock_tested.status == "PASS"
    assert evaluation.real_provider_tested.status == "BLOCKED"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.pending_owner_gates == ["G-01", "G-02", "G-03", "G-04", "G-11"]
    assert evaluation.verdict == "BLOCKED"
    assert evaluation.cost_total_vnd == 0


def test_fixture_provider_and_source_cannot_claim_real_evidence() -> None:
    provider_payload = _bundle()
    provider_payload["runs"][0]["providers"][0]["real_provider_tested"] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match="fixture evidence cannot be promoted"):
        FlowBAcceptanceBundle.model_validate(provider_payload)
    source_payload = _bundle()
    source_payload["runs"][0]["research_sources"][0]["real_source_tested"] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match="fixture source cannot be promoted"):
        FlowBAcceptanceBundle.model_validate(source_payload)


def test_two_runs_must_be_consecutive_on_the_same_locked_commit() -> None:
    payload = _bundle()
    payload["runs"][1]["release_candidate_commit"] = "7" * 40  # type: ignore[index]
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert evaluation.two_consecutive_runs is False
    assert evaluation.mock_tested.status == "FAIL"
    assert evaluation.verdict == "FAIL"


def test_research_claim_and_originality_metrics_are_measured() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["claim_map"][0]["source_ids"] = ["UNKNOWN-SOURCE"]
    run["claim_map"][1]["verification_status"] = "unsupported"
    run["originality_similarity_scores"] = [0.12, 0.41]
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    failures = set(evaluation.run_metrics[0].failures)
    assert failures >= {
        "CLAIM_SOURCE_COVERAGE_INCOMPLETE",
        "SCRIPT_FACTUAL_CONSISTENCY_INCOMPLETE",
        "ORIGINALITY_SIMILARITY_EXCEEDS_THRESHOLD",
    }


def test_storyboard_assets_rights_receipts_and_relevance_fail_closed() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["media_plan_shot_ids"] = ["SHOT-01", "SHOT-02"]
    run["assets"][2]["used_in_shot_ids"] = []
    run["assets"][0]["rights_record_id"] = None
    run["assets"][1]["provider_receipt_sha256"] = None
    run["assets"][2]["visual_relevance_score"] = 0.70
    run["assets"][0]["used_in_shot_ids"].append("SHOT-UNKNOWN")
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    failures = set(evaluation.run_metrics[0].failures)
    assert failures >= {
        "STORYBOARD_MEDIA_PLAN_COVERAGE_INCOMPLETE",
        "VISUAL_ASSET_SHOT_COVERAGE_INCOMPLETE",
        "ASSET_RIGHTS_PROVENANCE_INCOMPLETE",
        "ASSET_OR_PROVIDER_RECEIPT_INCOMPLETE",
        "VISUAL_RELEVANCE_BELOW_THRESHOLD",
        "ASSET_SHOT_REFERENCE_INVALID",
    }


@pytest.mark.parametrize(
    ("field", "value", "failure"),
    [
        ("narration_actual_duration_seconds", 33.0, "TTS_DURATION_ALIGNMENT_EXCEEDS_THRESHOLD"),
        ("subtitle_drift_seconds", [0.1, 0.2, 0.6], "SUBTITLE_P95_DRIFT_EXCEEDS_500MS"),
        ("integrated_loudness_lufs", -22.0, "INTEGRATED_LOUDNESS_OUTSIDE_RANGE"),
        ("true_peak_dbfs", -0.5, "AUDIO_PEAK_OR_CLIPPING_QC_FAILED"),
        ("speech_music_ratio_db", 4.0, "MUSIC_DUCKING_OR_SPEECH_RATIO_FAILED"),
        ("render_width", 720, "RENDER_RESOLUTION_BELOW_MINIMUM"),
    ],
)
def test_tts_subtitle_audio_and_render_thresholds_fail_closed(
    field: str,
    value: object,
    failure: str,
) -> None:
    payload = _bundle()
    payload["runs"][0][field] = value  # type: ignore[index]
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert failure in evaluation.run_metrics[0].failures


def test_approval_hash_restart_and_render_qc_are_enforced() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["approved_timeline_sha256"] = _sha("wrong-timeline")
    run["approved_render_input_sha256"] = _sha("wrong-render-input")
    run["restart_recovered"] = False
    run["full_decode_passed"] = False
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "APPROVAL_NOT_BOUND_TO_TIMELINE",
        "APPROVAL_NOT_BOUND_TO_RENDER_INPUT",
        "RESTART_RECOVERY_NOT_PROVEN",
        "RENDER_TECHNICAL_QC_FAILED",
    }


def test_real_axis_can_pass_while_production_and_quality_gates_remain_blocked() -> None:
    payload = _bundle()
    payload["gates"].update(  # type: ignore[union-attr]
        {"g01_credentials": True, "g02_vnd_budget": True, "g03_rights_inputs": True}
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        _mark_real_run(run)
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert evaluation.real_provider_tested.status == "PASS"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.verdict == "BLOCKED"


def test_real_axis_rejects_fixture_assets_even_after_provider_gates_open() -> None:
    payload = _bundle()
    payload["gates"].update(  # type: ignore[union-attr]
        {"g01_credentials": True, "g02_vnd_budget": True, "g03_rights_inputs": True}
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        _mark_real_run(run)
    payload["runs"][0]["assets"][0]["fixture"] = True  # type: ignore[index]
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert evaluation.real_provider_tested.status == "FAIL"
    assert "REAL_ASSET_EVIDENCE_INCOMPLETE" in evaluation.real_provider_tested.reasons


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
        _mark_real_run(run)
        run["production_path_tested"] = True
        run["human_review_passed"] = True
        run["human_review_final_sha256"] = run["final_video_sha256"]
    evaluation = evaluate_flow_b(FlowBAcceptanceBundle.model_validate(payload))
    assert evaluation.verdict == "PASS"
    assert evaluation.pending_owner_gates == []


def test_vnd_is_the_only_accepted_currency() -> None:
    payload = deepcopy(_bundle())
    payload["runs"][0]["currency"] = "USD"  # type: ignore[index]
    with pytest.raises(ValidationError):
        FlowBAcceptanceBundle.model_validate(payload)


def test_checked_in_flow_b_policy_matches_runtime_contract() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (repository_root / "packages" / "contracts" / "flow-b-acceptance.v1.json").read_text(
            encoding="utf-8"
        )
    )
    policy = FlowBAcceptancePolicy.model_validate(payload)
    assert policy.currency == "VND"
    assert policy.required_owner_gates == ("G-01", "G-02", "G-03", "G-04", "G-11")
    assert policy.required_provider_capabilities == CAPABILITIES
    assert policy.external_action_allowed_during_contract_test is False
