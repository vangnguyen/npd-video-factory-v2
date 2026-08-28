from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.flow_c_acceptance import (
    METRIC_NAMES,
    FlowCAcceptanceBundle,
    FlowCAcceptancePolicy,
    evaluate_flow_c,
)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _provider(capability: str, sequence: int) -> dict[str, object]:
    return {
        "capability": capability,
        "provider_key": f"fixture-{capability}",
        "adapter_or_api_version": f"deterministic-{capability}-v1",
        "fixture": True,
        "external_call": False,
        "paid": False,
        "real_provider_tested": False,
        "production_eligible": False,
        "request_sha256": _sha(f"provider-request:{sequence}:{capability}"),
        "response_sha256": _sha(f"provider-response:{sequence}:{capability}"),
        "charged_cost_vnd": 0,
        "currency": "VND",
        "secret_recorded": False,
    }


def _source(sequence: int, index: int) -> dict[str, object]:
    return {
        "source_id": f"SRC-{sequence}-{index}",
        "provider_key": "fixture-trend",
        "source_locator_sha256": _sha(f"source-locator:{sequence}:{index}"),
        "title": f"Nguồn xu hướng fixture {index}",
        "publisher": "NPD deterministic fixture",
        "retrieved_at_utc": f"2026-08-28T0{sequence}:0{index}:00Z",
        "response_sha256": _sha(f"source-response:{sequence}:{index}"),
        "provenance_complete": True,
        "fixture": True,
        "external_call": False,
        "real_source_tested": False,
        "secret_recorded": False,
    }


def _points(sequence: int, snapshot: int) -> list[dict[str, object]]:
    values = {
        "views": 1000 + sequence * 100 + snapshot * 50,
        "impressions": 1500 + sequence * 100 + snapshot * 50,
        "reach": 900 + sequence * 100 + snapshot * 50,
        "watch_time": 28000 + sequence * 1000,
        "average_view_duration": 28,
        "completion_rate": 0.72,
        "likes": 120,
        "comments": 18,
        "shares": 35,
        "saves": 22,
        "followers_gained": 15,
        "clicks": 40,
        "ctr": 0.04,
        "revenue": None,
        "rpm": None,
        "observation_window_hours": snapshot * 12,
    }
    return [
        {
            "metric": metric,
            "value": values[metric],
            "unit": "VND" if metric in {"revenue", "rpm"} else "normalized",
            "supported": metric not in {"revenue", "rpm"},
        }
        for metric in METRIC_NAMES
    ]


def _snapshot(sequence: int, index: int, publication_id: str) -> dict[str, object]:
    hour = sequence * 2 + index
    return {
        "snapshot_id": f"SNAP-{sequence}-{index}",
        "publication_id": publication_id,
        "provider_key": "fixture-analytics",
        "collected_at_utc": f"2026-08-28T{hour:02d}:30:00Z",
        "source_kind": "fixture",
        "fixture": True,
        "external_call": False,
        "real_provider_tested": False,
        "request_sha256": _sha(f"analytics-request:{sequence}:{index}"),
        "response_sha256": _sha(f"analytics-response:{sequence}:{index}"),
        "points": _points(sequence, index),
    }


def _run(sequence: int) -> dict[str, object]:
    start_hour = 1 if sequence == 1 else 6
    publication_id = f"PUB-FLOW-C-{sequence}"
    cluster_sha = _sha(f"cluster:{sequence}:SIG-{sequence}-1:SIG-{sequence}-2:SIG-{sequence}-3")
    final_sha = _sha(f"final-video:{sequence}")
    snapshots = [_snapshot(sequence, 1, publication_id), _snapshot(sequence, 2, publication_id)]
    return {
        "sequence": sequence,
        "run_id": f"flow-c-contract-{sequence}",
        "release_candidate_commit": "8" * 40,
        "started_at_utc": f"2026-08-28T{start_hour:02d}:00:00Z",
        "completed_at_utc": f"2026-08-28T{start_hour + 4:02d}:00:00Z",
        "workspace_id": "WORKSPACE-NPD-001",
        "providers": [_provider("trend", sequence), _provider("analytics", sequence)],
        "trend_sources": [_source(sequence, index) for index in range(1, 4)],
        "trend_signals": [
            {
                "signal_id": f"SIG-{sequence}-{index}",
                "source_id": f"SRC-{sequence}-{index}",
                "normalized_topic": "Vịnh Tiên lifestyle",
                "normalized_signal_sha256": _sha(f"signal:{sequence}:{index}"),
            }
            for index in range(1, 4)
        ],
        "trend_clusters": [
            {
                "cluster_id": f"CLUSTER-{sequence}-01",
                "member_signal_ids": [f"SIG-{sequence}-{index}" for index in range(1, 4)],
                "cluster_sha256": cluster_sha,
                "recomputed_cluster_sha256": cluster_sha,
            }
        ],
        "opportunities": [
            {
                "opportunity_id": f"OPP-{sequence}-01",
                "cluster_id": f"CLUSTER-{sequence}-01",
                "score_input_sha256": _sha(f"score-input:{sequence}"),
                "opportunity_score": 82.5,
                "recomputed_opportunity_score": 82.5,
                "formula_version": "trend-opportunity-v1",
            }
        ],
        "selected_opportunity_id": f"OPP-{sequence}-01",
        "idea_id": f"IDEA-{sequence}-01",
        "idea_sha256": _sha(f"idea:{sequence}"),
        "idea_bound_cluster_sha256": cluster_sha,
        "project_id": f"PROJECT-{sequence}-01",
        "project_bound_idea_sha256": _sha(f"idea:{sequence}"),
        "publication": {
            "publication_id": publication_id,
            "project_id": f"PROJECT-{sequence}-01",
            "platform": "youtube",
            "final_video_sha256": final_sha,
            "approved_final_video_sha256": final_sha,
            "publication_bound_video_sha256": final_sha,
            "rights_record_ids": [f"RIGHTS-{sequence}-01"],
            "rights_gate_passed": True,
            "platform_validation_passed": True,
            "platform_validation_sha256": _sha(f"platform-validation:{sequence}"),
            "request_sha256": _sha(f"publication-request:{sequence}"),
            "idempotency_key_sha256": _sha(f"idempotency-key:{sequence}"),
            "duplicate_fingerprint_sha256": _sha(f"duplicate-fingerprint:{sequence}"),
            "replay_publication_id": publication_id,
            "idempotent_replay": True,
            "duplicate_post_created": False,
            "duplicate_prevention_passed": True,
            "status": "dry_run_succeeded",
            "fixture": True,
            "external_action": False,
            "real_publication_tested": False,
            "remote_post_id": None,
            "receipt_payload_sha256": _sha(f"publication-receipt:{sequence}"),
            "verified_receipt_payload_sha256": _sha(f"publication-receipt:{sequence}"),
            "receipt_valid": True,
            "production_path_tested": False,
        },
        "analytics_snapshots": snapshots,
        "winner_assessment": {
            "assessment_id": f"ASSESS-{sequence}-01",
            "snapshot_id": f"SNAP-{sequence}-2",
            "state": "winner_candidate",
            "score": 78.25,
            "recomputed_score": 78.25,
            "factors": [
                {
                    "factor": "retention",
                    "score": 80,
                    "weight": 0.5,
                    "evidence_refs": [f"SNAP-{sequence}-2:completion_rate"],
                },
                {
                    "factor": "engagement",
                    "score": 76.5,
                    "weight": 0.5,
                    "evidence_refs": [f"SNAP-{sequence}-2:shares"],
                },
            ],
            "evidence_refs": [f"SNAP-{sequence}-2", f"PUB-FLOW-C-{sequence}"],
            "algorithm_version": "winner-score-v1",
            "automatic_action": False,
            "paid_media_mutation": False,
        },
        "learning_insights": [
            {
                "insight_id": f"INSIGHT-{sequence}-01",
                "assessment_id": f"ASSESS-{sequence}-01",
                "snapshot_id": f"SNAP-{sequence}-2",
                "trend_cluster_id": f"CLUSTER-{sequence}-01",
                "idea_id": f"IDEA-{sequence}-01",
                "recommendation": "Ưu tiên kiểm thử lại hook, không tự động xuất bản.",
                "evidence_refs": [f"SNAP-{sequence}-2", f"CLUSTER-{sequence}-01"],
                "applied": False,
                "autonomous_execution": False,
            }
        ],
        "cost_ledger_total_vnd": 0,
        "currency": "VND",
        "restart_recovered": True,
        "human_review_passed": False,
        "human_review_final_sha256": None,
        "external_action_performed": False,
        "publish_performed": False,
    }


def _bundle() -> dict[str, object]:
    return {
        "schema_version": 1,
        "checkpoint": "V3-01-06",
        "release_candidate_commit": "8" * 40,
        "environment": "LOCAL",
        "gates": {
            "g01_credentials": False,
            "g02_vnd_budget": False,
            "g03_rights_inputs": False,
            "g04_production_like_staging": False,
            "g05_exact_artifact_approval": False,
            "g06_live_publication": False,
            "g11_human_quality": False,
            "approval_ids": [],
        },
        "safety": {
            "external_execution_enabled": False,
            "paid_execution_enabled": False,
            "analytics_external_execution_enabled": False,
            "global_kill_switch_engaged": True,
            "daily_budget_vnd": 0,
            "production_write_performed": False,
            "publish_performed": False,
        },
        "runs": [_run(1), _run(2)],
        "secret_recorded": False,
    }


def _mark_real_provider_axis(payload: dict[str, object]) -> None:
    payload["gates"].update(  # type: ignore[union-attr]
        {"g01_credentials": True, "g02_vnd_budget": True, "g03_rights_inputs": True}
    )
    payload["safety"].update(  # type: ignore[union-attr]
        {
            "external_execution_enabled": True,
            "analytics_external_execution_enabled": True,
            "global_kill_switch_engaged": False,
        }
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        for provider in run["providers"]:
            provider.update(
                {
                    "provider_key": f"official-{provider['capability']}",
                    "fixture": False,
                    "external_call": True,
                    "real_provider_tested": True,
                    "production_eligible": True,
                }
            )
        for source in run["trend_sources"]:
            source.update(
                {
                    "provider_key": "official-trend",
                    "fixture": False,
                    "external_call": True,
                    "real_source_tested": True,
                }
            )
        for snapshot in run["analytics_snapshots"]:
            snapshot.update(
                {
                    "provider_key": "official-analytics",
                    "source_kind": "official_api",
                    "fixture": False,
                    "external_call": True,
                    "real_provider_tested": True,
                }
            )


def test_two_fixture_runs_pass_contract_but_all_owner_gates_remain_blocked() -> None:
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(_bundle()))
    assert evaluation.two_consecutive_runs is True
    assert evaluation.implemented.status == "PASS"
    assert evaluation.mock_tested.status == "PASS"
    assert evaluation.real_provider_tested.status == "BLOCKED"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.pending_owner_gates == [
        "G-01",
        "G-02",
        "G-03",
        "G-04",
        "G-05",
        "G-06",
        "G-11",
    ]
    assert evaluation.verdict == "BLOCKED"
    assert evaluation.cost_total_vnd == 0
    assert evaluation.external_actions_performed is False
    assert evaluation.publish_performed is False


@pytest.mark.parametrize(
    ("path", "message"),
    [
        (("runs", 0, "providers", 0, "real_provider_tested"), "fixture provider"),
        (("runs", 0, "trend_sources", 0, "real_source_tested"), "fixture trend source"),
        (("runs", 0, "analytics_snapshots", 0, "real_provider_tested"), "fixture analytics"),
        (("runs", 0, "publication", "real_publication_tested"), "fixture publication"),
    ],
)
def test_fixture_evidence_cannot_claim_real_status(path: tuple[object, ...], message: str) -> None:
    payload = _bundle()
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = True  # type: ignore[index]
    with pytest.raises(ValidationError, match=message):
        FlowCAcceptanceBundle.model_validate(payload)


def test_two_runs_must_be_consecutive_on_the_same_locked_commit() -> None:
    payload = _bundle()
    payload["runs"][1]["release_candidate_commit"] = "9" * 40  # type: ignore[index]
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert evaluation.two_consecutive_runs is False
    assert evaluation.mock_tested.status == "FAIL"
    assert evaluation.verdict == "FAIL"


def test_trend_provenance_cluster_and_score_reproducibility_are_measured() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["trend_sources"][0]["provenance_complete"] = False
    run["trend_signals"][0]["source_id"] = "SRC-UNKNOWN"
    run["trend_clusters"][0]["recomputed_cluster_sha256"] = _sha("wrong-cluster")
    run["opportunities"][0]["recomputed_opportunity_score"] = 80
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "TREND_SOURCE_PROVENANCE_INCOMPLETE",
        "TREND_SIGNAL_SOURCE_REFERENCE_INVALID",
        "TREND_CLUSTER_NOT_DETERMINISTIC",
        "OPPORTUNITY_SCORE_NOT_REPRODUCIBLE",
    }


def test_idea_project_and_video_hash_bindings_fail_closed() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["selected_opportunity_id"] = "OPP-UNKNOWN"
    run["project_bound_idea_sha256"] = _sha("wrong-idea")
    run["publication"]["approved_final_video_sha256"] = _sha("wrong-video")
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "SELECTED_OPPORTUNITY_REFERENCE_INVALID",
        "IDEA_TREND_BINDING_INVALID",
        "PROJECT_IDEA_BINDING_INVALID",
        "VIDEO_PROJECT_OR_APPROVAL_HASH_BINDING_INVALID",
    }


def test_publish_rights_platform_idempotency_duplicate_and_receipt_gates_fail_closed() -> None:
    payload = _bundle()
    publication = payload["runs"][0]["publication"]  # type: ignore[index]
    publication["rights_gate_passed"] = False
    publication["platform_validation_passed"] = False
    publication["idempotent_replay"] = False
    publication["duplicate_prevention_passed"] = False
    publication["verified_receipt_payload_sha256"] = _sha("wrong-receipt")
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "RIGHTS_GATE_NOT_PROVEN",
        "PLATFORM_VALIDATION_NOT_PROVEN",
        "PUBLISH_IDEMPOTENCY_REPLAY_FAILED",
        "DUPLICATE_POST_PREVENTION_FAILED",
        "PUBLICATION_RECEIPT_INTEGRITY_FAILED",
    }


def test_analytics_normalization_null_semantics_and_ordering_are_enforced() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["analytics_snapshots"][0]["points"].pop()
    run["analytics_snapshots"][1]["collected_at_utc"] = "2026-08-28T01:00:00Z"
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "ANALYTICS_NORMALIZATION_INCOMPLETE",
        "ANALYTICS_SNAPSHOT_ORDERING_INVALID",
        "WINNER_SCORE_NOT_REPRODUCIBLE_OR_EXPLAINABLE",
        "LEARNING_FEEDBACK_LINEAGE_INCOMPLETE",
    }

    fabricated = _bundle()
    point = fabricated["runs"][0]["analytics_snapshots"][0]["points"][13]  # type: ignore[index]
    point["value"] = 1
    with pytest.raises(ValidationError, match="unsupported analytics metric"):
        FlowCAcceptanceBundle.model_validate(fabricated)


def test_winner_score_and_learning_lineage_must_be_reproducible() -> None:
    payload = _bundle()
    run = payload["runs"][0]  # type: ignore[index]
    run["winner_assessment"]["recomputed_score"] = 60
    run["learning_insights"][0]["assessment_id"] = "ASSESS-UNKNOWN"
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert set(evaluation.run_metrics[0].failures) >= {
        "WINNER_SCORE_NOT_REPRODUCIBLE_OR_EXPLAINABLE",
        "LEARNING_FEEDBACK_LINEAGE_INCOMPLETE",
    }


def test_restart_recovery_and_offline_external_boundary_are_enforced() -> None:
    payload = _bundle()
    payload["runs"][0]["restart_recovered"] = False  # type: ignore[index]
    payload["safety"]["external_execution_enabled"] = True  # type: ignore[index]
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert "RESTART_RECOVERY_NOT_PROVEN" in evaluation.run_metrics[0].failures
    assert "OFFLINE_CONTRACT_TEST_EXTERNAL_ACTION_BOUNDARY_VIOLATED" in evaluation.mock_tested.reasons
    assert evaluation.verdict == "FAIL"


def test_real_provider_axis_can_pass_while_production_and_quality_remain_blocked() -> None:
    payload = _bundle()
    payload["environment"] = "STAGING_PRODUCTION_LIKE"
    _mark_real_provider_axis(payload)
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert evaluation.real_provider_tested.status == "PASS"
    assert evaluation.production_path_tested.status == "BLOCKED"
    assert evaluation.quality_accepted.status == "BLOCKED"
    assert evaluation.verdict == "BLOCKED"


def test_all_axes_require_real_publish_receipt_and_hash_bound_human_review() -> None:
    payload = _bundle()
    payload["environment"] = "STAGING_PRODUCTION_LIKE"
    _mark_real_provider_axis(payload)
    payload["gates"].update(  # type: ignore[union-attr]
        {
            "g04_production_like_staging": True,
            "g05_exact_artifact_approval": True,
            "g06_live_publication": True,
            "g11_human_quality": True,
        }
    )
    payload["safety"].update(  # type: ignore[union-attr]
        {"production_write_performed": True, "publish_performed": True}
    )
    for run in payload["runs"]:  # type: ignore[union-attr]
        publication = run["publication"]
        publication.update(
            {
                "fixture": False,
                "external_action": True,
                "real_publication_tested": True,
                "status": "published",
                "remote_post_id": f"remote-{run['sequence']}",
                "production_path_tested": True,
            }
        )
        run["external_action_performed"] = True
        run["publish_performed"] = True
        run["human_review_passed"] = True
        run["human_review_final_sha256"] = publication["final_video_sha256"]
    evaluation = evaluate_flow_c(FlowCAcceptanceBundle.model_validate(payload))
    assert evaluation.verdict == "PASS"
    assert evaluation.pending_owner_gates == []


def test_vnd_is_the_only_accepted_currency() -> None:
    payload = deepcopy(_bundle())
    payload["runs"][0]["currency"] = "USD"  # type: ignore[index]
    with pytest.raises(ValidationError):
        FlowCAcceptanceBundle.model_validate(payload)


def test_checked_in_flow_c_policy_matches_runtime_contract() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    payload = json.loads(
        (repository_root / "packages" / "contracts" / "flow-c-acceptance.v1.json").read_text(
            encoding="utf-8"
        )
    )
    policy = FlowCAcceptancePolicy.model_validate(payload)
    assert policy.currency == "VND"
    assert policy.required_provider_capabilities == ("trend", "analytics")
    assert policy.required_metrics == METRIC_NAMES
    assert policy.required_owner_gates == (
        "G-01",
        "G-02",
        "G-03",
        "G-04",
        "G-05",
        "G-06",
        "G-11",
    )
    assert policy.external_action_allowed_during_contract_test is False
    assert policy.real_publish_allowed_during_contract_test is False
