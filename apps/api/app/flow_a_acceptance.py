from __future__ import annotations

import math
import re
import unicodedata
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel


AxisStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_TESTED"]
Verdict = Literal["PASS", "FAIL", "BLOCKED"]


class FlowAAcceptancePolicy(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-04"] = "V3-01-04"
    consecutive_runs_required: Literal[2] = 2
    minimum_source_duration_seconds: Literal[90] = 90
    minimum_source_width: Literal[1080] = 1080
    minimum_source_height: Literal[1080] = 1080
    maximum_asr_wer: Literal[0.15] = 0.15
    minimum_critical_term_accuracy: Literal[1.0] = 1.0
    scene_boundary_tolerance_seconds: Literal[0.5] = 0.5
    minimum_scene_boundary_f1: Literal[0.8] = 0.8
    minimum_reframe_safe_coverage: Literal[0.95] = 0.95
    maximum_subtitle_median_drift_seconds: Literal[0.2] = 0.2
    maximum_subtitle_p95_drift_seconds: Literal[0.5] = 0.5
    required_provider_capabilities: tuple[Literal["asr"], Literal["vision"], Literal["tts"]] = (
        "asr",
        "vision",
        "tts",
    )
    required_owner_gates: tuple[
        Literal["G-01"], Literal["G-02"], Literal["G-03"], Literal["G-04"], Literal["G-11"]
    ] = ("G-01", "G-02", "G-03", "G-04", "G-11")
    currency: Literal["VND"] = "VND"
    publish_allowed: Literal[False] = False
    external_action_allowed_during_contract_test: Literal[False] = False


class FlowAProviderEvidence(StrictModel):
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    model_or_workflow: str = Field(min_length=1, max_length=240)
    fixture: bool
    external_call: bool
    paid: bool
    real_provider_tested: bool
    production_eligible: bool
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_or_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    charged_cost_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_execution_claim(self) -> "FlowAProviderEvidence":
        if self.fixture and self.real_provider_tested:
            raise ValueError("fixture evidence cannot be promoted to real-provider evidence")
        if self.paid and not self.external_call:
            raise ValueError("paid provider evidence must be classified as external")
        return self


class FlowAGateSnapshot(StrictModel):
    g01_credentials: bool = False
    g02_vnd_budget: bool = False
    g03_rights_inputs: bool = False
    g04_production_like_staging: bool = False
    g11_human_quality: bool = False
    approval_ids: list[str] = Field(default_factory=list, max_length=20)


class FlowASafetySnapshot(StrictModel):
    external_execution_enabled: bool = False
    paid_execution_enabled: bool = False
    global_kill_switch_engaged: bool = True
    daily_budget_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    production_write_performed: Literal[False] = False
    publish_performed: Literal[False] = False


class FlowARunEvidence(StrictModel):
    sequence: int = Field(ge=1, le=2)
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    started_at_utc: datetime
    completed_at_utc: datetime
    input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_duration_seconds: float = Field(ge=90)
    source_width: int = Field(ge=1080)
    source_height: int = Field(ge=1080)
    source_has_audio: Literal[True] = True
    source_language: Literal["vi"] = "vi"
    rights_record_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$",
    )
    input_owned_or_licensed: bool
    asr: FlowAProviderEvidence
    vision: FlowAProviderEvidence
    tts: FlowAProviderEvidence
    reference_transcript: str = Field(min_length=1)
    hypothesis_transcript: str = Field(min_length=1)
    critical_terms: list[str] = Field(min_length=1, max_length=100)
    reference_scene_boundaries_seconds: list[float] = Field(min_length=1, max_length=1000)
    predicted_scene_boundaries_seconds: list[float] = Field(min_length=1, max_length=1000)
    reframe_safe_coverage: float = Field(ge=0, le=1)
    subtitle_drift_seconds: list[float] = Field(min_length=1, max_length=10000)
    broll_asset_sha256: list[str] = Field(min_length=1, max_length=100)
    broll_rights_record_ids: list[str] = Field(min_length=1, max_length=100)
    music_asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    music_rights_record_id: str = Field(
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$"
    )
    timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    full_decode_passed: bool
    black_frame_qc_passed: bool
    silence_qc_passed: bool
    frozen_frame_qc_passed: bool
    av_sync_qc_passed: bool
    provider_receipts_valid: bool
    restart_recovered: bool
    production_path_tested: bool
    human_review_passed: bool
    human_review_final_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    cost_ledger_total_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    external_action_performed: Literal[False] = False
    publish_requested: Literal[False] = False

    @model_validator(mode="after")
    def validate_run_contract(self) -> "FlowARunEvidence":
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("Flow A run completion must not precede its start")
        if self.input_owned_or_licensed and not self.rights_record_id:
            raise ValueError("owned or licensed Flow A input requires a rights record ID")
        if len(self.broll_asset_sha256) != len(self.broll_rights_record_ids):
            raise ValueError("each B-roll asset requires one rights record ID")
        for value in self.broll_asset_sha256:
            if re.fullmatch(r"[a-f0-9]{64}", value) is None:
                raise ValueError("B-roll asset hashes must be SHA-256 values")
        provider_cost = self.asr.charged_cost_vnd + self.vision.charged_cost_vnd + self.tts.charged_cost_vnd
        if self.cost_ledger_total_vnd < provider_cost:
            raise ValueError("run cost ledger cannot be lower than recorded provider charges")
        if self.human_review_passed and not self.human_review_final_sha256:
            raise ValueError("a passed human review must bind the final video hash")
        return self


class FlowAAcceptanceBundle(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-04"] = "V3-01-04"
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: Literal["LOCAL", "CI", "STAGING_PRODUCTION_LIKE", "PRODUCTION"]
    gates: FlowAGateSnapshot
    safety: FlowASafetySnapshot
    runs: list[FlowARunEvidence] = Field(min_length=2, max_length=2)
    secret_recorded: Literal[False] = False


class FlowARunMetrics(StrictModel):
    run_id: str
    wer: float = Field(ge=0)
    critical_term_accuracy: float = Field(ge=0, le=1)
    scene_boundary_f1: float = Field(ge=0, le=1)
    subtitle_median_drift_seconds: float = Field(ge=0)
    subtitle_p95_drift_seconds: float = Field(ge=0)
    reframe_safe_coverage: float = Field(ge=0, le=1)
    technical_passed: bool
    failures: list[str]


class FlowAAxisResult(StrictModel):
    status: AxisStatus
    reasons: list[str] = Field(default_factory=list)


class FlowAAcceptanceEvaluation(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-04"] = "V3-01-04"
    verdict: Verdict
    two_consecutive_runs: bool
    run_metrics: list[FlowARunMetrics]
    implemented: FlowAAxisResult
    mock_tested: FlowAAxisResult
    real_provider_tested: FlowAAxisResult
    production_path_tested: FlowAAxisResult
    quality_accepted: FlowAAxisResult
    pending_owner_gates: list[Literal["G-01", "G-02", "G-03", "G-04", "G-11"]]
    cost_total_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    external_actions_performed: Literal[False] = False
    publish_performed: Literal[False] = False


def _tokens(value: str) -> list[str]:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.findall(r"\w+", normalized, flags=re.UNICODE)


def _word_error_rate(reference: str, hypothesis: str) -> float:
    expected = _tokens(reference)
    actual = _tokens(hypothesis)
    if not expected:
        return 0.0 if not actual else 1.0
    previous = list(range(len(actual) + 1))
    for row, expected_token in enumerate(expected, start=1):
        current = [row]
        for column, actual_token in enumerate(actual, start=1):
            current.append(
                min(
                    current[column - 1] + 1,
                    previous[column] + 1,
                    previous[column - 1] + (expected_token != actual_token),
                )
            )
        previous = current
    return previous[-1] / len(expected)


def _critical_term_accuracy(reference: str, hypothesis: str, terms: list[str]) -> float:
    expected = " ".join(_tokens(reference))
    actual = " ".join(_tokens(hypothesis))
    required = [" ".join(_tokens(term)) for term in terms]
    if not required or any(not term or term not in expected for term in required):
        return 0.0
    return sum(term in actual for term in required) / len(required)


def _scene_boundary_f1(reference: list[float], predicted: list[float], tolerance: float = 0.5) -> float:
    unmatched = set(range(len(predicted)))
    matches = 0
    for target in reference:
        candidates = [index for index in unmatched if abs(predicted[index] - target) <= tolerance]
        if not candidates:
            continue
        best = min(candidates, key=lambda index: abs(predicted[index] - target))
        unmatched.remove(best)
        matches += 1
    precision = matches / len(predicted) if predicted else 0.0
    recall = matches / len(reference) if reference else 0.0
    return 0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)


def _p95(values: list[float]) -> float:
    ordered = sorted(abs(value) for value in values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _evaluate_run(run: FlowARunEvidence, policy: FlowAAcceptancePolicy) -> FlowARunMetrics:
    wer = _word_error_rate(run.reference_transcript, run.hypothesis_transcript)
    critical_accuracy = _critical_term_accuracy(
        run.reference_transcript,
        run.hypothesis_transcript,
        run.critical_terms,
    )
    scene_f1 = _scene_boundary_f1(
        run.reference_scene_boundaries_seconds,
        run.predicted_scene_boundaries_seconds,
        policy.scene_boundary_tolerance_seconds,
    )
    drift_values = [abs(value) for value in run.subtitle_drift_seconds]
    drift_median = float(median(drift_values))
    drift_p95 = _p95(drift_values)
    failures: list[str] = []
    if wer > policy.maximum_asr_wer:
        failures.append("ASR_WER_EXCEEDS_15_PERCENT")
    if critical_accuracy < policy.minimum_critical_term_accuracy:
        failures.append("CRITICAL_TERM_ACCURACY_BELOW_100_PERCENT")
    if scene_f1 < policy.minimum_scene_boundary_f1:
        failures.append("SCENE_BOUNDARY_F1_BELOW_0_80")
    if run.reframe_safe_coverage < policy.minimum_reframe_safe_coverage:
        failures.append("REFRAME_SAFE_COVERAGE_BELOW_95_PERCENT")
    if drift_median > policy.maximum_subtitle_median_drift_seconds:
        failures.append("SUBTITLE_MEDIAN_DRIFT_EXCEEDS_200MS")
    if drift_p95 > policy.maximum_subtitle_p95_drift_seconds:
        failures.append("SUBTITLE_P95_DRIFT_EXCEEDS_500MS")
    if run.timeline_sha256 != run.approved_timeline_sha256:
        failures.append("APPROVAL_NOT_BOUND_TO_TIMELINE")
    if not all(
        (
            run.full_decode_passed,
            run.black_frame_qc_passed,
            run.silence_qc_passed,
            run.frozen_frame_qc_passed,
            run.av_sync_qc_passed,
        )
    ):
        failures.append("TECHNICAL_QC_FAILED")
    if not run.provider_receipts_valid:
        failures.append("PROVIDER_RECEIPT_INVALID")
    if not run.restart_recovered:
        failures.append("RESTART_RECOVERY_NOT_PROVEN")
    return FlowARunMetrics(
        run_id=run.run_id,
        wer=round(wer, 6),
        critical_term_accuracy=round(critical_accuracy, 6),
        scene_boundary_f1=round(scene_f1, 6),
        subtitle_median_drift_seconds=round(drift_median, 6),
        subtitle_p95_drift_seconds=round(drift_p95, 6),
        reframe_safe_coverage=run.reframe_safe_coverage,
        technical_passed=not failures,
        failures=failures,
    )


def evaluate_flow_a(
    bundle: FlowAAcceptanceBundle,
    policy: FlowAAcceptancePolicy | None = None,
) -> FlowAAcceptanceEvaluation:
    policy = policy or FlowAAcceptancePolicy()
    ordered = sorted(bundle.runs, key=lambda run: run.sequence)
    sequence_ok = [run.sequence for run in ordered] == [1, 2]
    distinct_runs = len({run.run_id for run in ordered}) == 2
    distinct_inputs = len({run.input_sha256 for run in ordered}) == 2
    locked_commit = all(
        run.release_candidate_commit == bundle.release_candidate_commit for run in ordered
    )
    chronological = ordered[0].completed_at_utc <= ordered[1].started_at_utc
    two_consecutive_runs = all(
        (sequence_ok, distinct_runs, distinct_inputs, locked_commit, chronological)
    )
    metrics = [_evaluate_run(run, policy) for run in ordered]
    mock_reasons: list[str] = []
    if not two_consecutive_runs:
        mock_reasons.append("TWO_CONSECUTIVE_LOCKED_RC_RUNS_NOT_PROVEN")
    mock_reasons.extend(
        f"{metric.run_id}:{failure}" for metric in metrics for failure in metric.failures
    )
    mock_axis = FlowAAxisResult(status="PASS" if not mock_reasons else "FAIL", reasons=mock_reasons)

    pending: list[Literal["G-01", "G-02", "G-03", "G-04", "G-11"]] = []
    if not bundle.gates.g01_credentials:
        pending.append("G-01")
    if not bundle.gates.g02_vnd_budget:
        pending.append("G-02")
    if not bundle.gates.g03_rights_inputs:
        pending.append("G-03")
    if not bundle.gates.g04_production_like_staging:
        pending.append("G-04")
    if not bundle.gates.g11_human_quality:
        pending.append("G-11")

    real_gate_pending = [gate for gate in pending if gate in {"G-01", "G-02", "G-03"}]
    real_reasons = [f"OWNER_GATE_PENDING:{gate}" for gate in real_gate_pending]
    provider_evidence = [provider for run in ordered for provider in (run.asr, run.vision, run.tts)]
    if not real_gate_pending:
        if not all(
            provider.real_provider_tested and not provider.fixture and provider.production_eligible
            for provider in provider_evidence
        ):
            real_reasons.append("REAL_PRODUCTION_ELIGIBLE_PROVIDER_EVIDENCE_INCOMPLETE")
        if not all(run.input_owned_or_licensed and run.rights_record_id for run in ordered):
            real_reasons.append("OWNED_INPUT_RIGHTS_EVIDENCE_INCOMPLETE")
        if not all(run.music_rights_record_id and run.broll_rights_record_ids for run in ordered):
            real_reasons.append("MUSIC_OR_BROLL_RIGHTS_EVIDENCE_INCOMPLETE")
        external_real = any(provider.external_call for provider in provider_evidence)
        paid_real = any(provider.paid for provider in provider_evidence)
        if external_real and (
            not bundle.safety.external_execution_enabled
            or bundle.safety.global_kill_switch_engaged
        ):
            real_reasons.append("EXTERNAL_PROVIDER_SAFETY_STATE_NOT_AUTHORIZED")
        if paid_real and (
            not bundle.safety.paid_execution_enabled or bundle.safety.daily_budget_vnd <= 0
        ):
            real_reasons.append("PAID_PROVIDER_VND_BUDGET_NOT_ACTIVE")
    real_axis = FlowAAxisResult(
        status="BLOCKED" if real_gate_pending else ("PASS" if not real_reasons else "FAIL"),
        reasons=real_reasons,
    )

    production_reasons: list[str] = []
    if "G-04" in pending:
        production_reasons.append("OWNER_GATE_PENDING:G-04")
        production_status: AxisStatus = "BLOCKED"
    else:
        if real_axis.status != "PASS":
            production_reasons.append("REAL_PROVIDER_AXIS_NOT_PASS")
        if not all(run.production_path_tested for run in ordered):
            production_reasons.append("PRODUCTION_PATH_EVIDENCE_INCOMPLETE")
        production_status = "PASS" if not production_reasons else "FAIL"
    production_axis = FlowAAxisResult(status=production_status, reasons=production_reasons)

    quality_reasons: list[str] = []
    if "G-11" in pending:
        quality_reasons.append("OWNER_GATE_PENDING:G-11")
        quality_status: AxisStatus = "BLOCKED"
    else:
        if production_axis.status != "PASS":
            quality_reasons.append("PRODUCTION_PATH_AXIS_NOT_PASS")
        for run in ordered:
            if not run.human_review_passed:
                quality_reasons.append(f"{run.run_id}:HUMAN_FULL_WATCH_NOT_ACCEPTED")
            elif run.human_review_final_sha256 != run.final_video_sha256:
                quality_reasons.append(f"{run.run_id}:HUMAN_REVIEW_NOT_BOUND_TO_FINAL_HASH")
        quality_status = "PASS" if not quality_reasons else "FAIL"
    quality_axis = FlowAAxisResult(status=quality_status, reasons=quality_reasons)

    axes = [mock_axis, real_axis, production_axis, quality_axis]
    if any(axis.status == "FAIL" for axis in axes):
        verdict: Verdict = "FAIL"
    elif all(axis.status == "PASS" for axis in axes):
        verdict = "PASS"
    else:
        verdict = "BLOCKED"
    return FlowAAcceptanceEvaluation(
        verdict=verdict,
        two_consecutive_runs=two_consecutive_runs,
        run_metrics=metrics,
        implemented=FlowAAxisResult(
            status="PASS",
            reasons=["FLOW_A_ACCEPTANCE_CONTRACT_AND_DETERMINISTIC_EVALUATOR_PRESENT"],
        ),
        mock_tested=mock_axis,
        real_provider_tested=real_axis,
        production_path_tested=production_axis,
        quality_accepted=quality_axis,
        pending_owner_gates=pending,
        cost_total_vnd=sum((run.cost_ledger_total_vnd for run in ordered), Decimal("0")),
    )
