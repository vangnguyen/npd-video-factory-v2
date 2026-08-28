from __future__ import annotations

import math
from datetime import datetime
from decimal import Decimal
from statistics import median
from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel


AxisStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_TESTED"]
Verdict = Literal["PASS", "FAIL", "BLOCKED"]
ProviderCapability = Literal[
    "research",
    "stock",
    "ai_image",
    "ai_video",
    "vision",
    "tts",
]


class FlowBAcceptancePolicy(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-05"] = "V3-01-05"
    consecutive_runs_required: Literal[2] = 2
    minimum_research_sources: int = Field(default=3, ge=2)
    minimum_claim_source_coverage: float = Field(default=1.0, ge=0, le=1)
    minimum_verified_claim_coverage: float = Field(default=1.0, ge=0, le=1)
    maximum_originality_similarity: float = Field(default=0.30, ge=0, le=1)
    minimum_storyboard_plan_coverage: float = Field(default=1.0, ge=0, le=1)
    minimum_asset_shot_coverage: float = Field(default=1.0, ge=0, le=1)
    minimum_visual_relevance: float = Field(default=0.80, ge=0, le=1)
    maximum_tts_duration_deviation_ratio: float = Field(default=0.05, ge=0, le=1)
    maximum_subtitle_median_drift_seconds: float = Field(default=0.20, ge=0)
    maximum_subtitle_p95_drift_seconds: float = Field(default=0.50, ge=0)
    minimum_integrated_loudness_lufs: float = -18.0
    maximum_integrated_loudness_lufs: float = -12.0
    maximum_true_peak_dbfs: float = -1.0
    minimum_speech_music_ratio_db: float = 6.0
    minimum_render_width: int = Field(default=1080, ge=1)
    minimum_render_height: int = Field(default=1920, ge=1)
    required_provider_capabilities: tuple[ProviderCapability, ...] = (
        "research",
        "stock",
        "ai_image",
        "ai_video",
        "vision",
        "tts",
    )
    required_asset_kinds: tuple[Literal["stock", "ai_image", "ai_video", "music"], ...] = (
        "stock",
        "ai_image",
        "ai_video",
        "music",
    )
    required_owner_gates: tuple[
        Literal["G-01"], Literal["G-02"], Literal["G-03"], Literal["G-04"], Literal["G-11"]
    ] = ("G-01", "G-02", "G-03", "G-04", "G-11")
    currency: Literal["VND"] = "VND"
    publish_allowed: Literal[False] = False
    external_action_allowed_during_contract_test: Literal[False] = False

    @model_validator(mode="after")
    def validate_audio_range(self) -> "FlowBAcceptancePolicy":
        if self.minimum_integrated_loudness_lufs > self.maximum_integrated_loudness_lufs:
            raise ValueError("minimum loudness cannot exceed maximum loudness")
        return self


class FlowBProviderEvidence(StrictModel):
    capability: ProviderCapability
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
    def validate_execution_claim(self) -> "FlowBProviderEvidence":
        if self.fixture and self.real_provider_tested:
            raise ValueError("fixture evidence cannot be promoted to real-provider evidence")
        if self.paid and not self.external_call:
            raise ValueError("paid provider evidence must be classified as external")
        return self


class FlowBSourceEvidence(StrictModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    source_locator_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=240)
    retrieved_at_utc: datetime
    fixture: bool
    real_source_tested: bool
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_source_claim(self) -> "FlowBSourceEvidence":
        if self.fixture and self.real_source_tested:
            raise ValueError("fixture source cannot be promoted to real-source evidence")
        return self


class FlowBClaimEvidence(StrictModel):
    claim_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    claim_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_ids: list[str] = Field(default_factory=list, max_length=50)
    verification_status: Literal["verified", "rejected", "unsupported"]
    included_in_script: bool


class FlowBAssetEvidence(StrictModel):
    asset_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    kind: Literal["stock", "ai_image", "ai_video", "owned_visual", "music"]
    asset_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provider_key: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    provider_receipt_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    rights_record_id: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$",
    )
    transformation_lineage_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    used_in_shot_ids: list[str] = Field(default_factory=list, max_length=500)
    visual_relevance_score: float | None = Field(default=None, ge=0, le=1)
    decoded_or_verified: bool
    fixture: bool


class FlowBGateSnapshot(StrictModel):
    g01_credentials: bool = False
    g02_vnd_budget: bool = False
    g03_rights_inputs: bool = False
    g04_production_like_staging: bool = False
    g11_human_quality: bool = False
    approval_ids: list[str] = Field(default_factory=list, max_length=20)


class FlowBSafetySnapshot(StrictModel):
    external_execution_enabled: bool = False
    paid_execution_enabled: bool = False
    global_kill_switch_engaged: bool = True
    daily_budget_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    production_write_performed: Literal[False] = False
    publish_performed: Literal[False] = False


class FlowBRunEvidence(StrictModel):
    sequence: int = Field(ge=1, le=2)
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    started_at_utc: datetime
    completed_at_utc: datetime
    business_brief_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    idea_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    research_sources: list[FlowBSourceEvidence] = Field(min_length=1, max_length=100)
    claim_map: list[FlowBClaimEvidence] = Field(min_length=1, max_length=500)
    script_claim_ids: list[str] = Field(min_length=1, max_length=500)
    script_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    originality_similarity_scores: list[float] = Field(min_length=1, max_length=1000)
    storyboard_shot_ids: list[str] = Field(min_length=1, max_length=500)
    media_plan_shot_ids: list[str] = Field(min_length=1, max_length=500)
    providers: list[FlowBProviderEvidence] = Field(min_length=1, max_length=50)
    assets: list[FlowBAssetEvidence] = Field(min_length=1, max_length=1000)
    narration_expected_duration_seconds: float = Field(gt=0)
    narration_actual_duration_seconds: float = Field(gt=0)
    tts_audio_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    subtitle_drift_seconds: list[float] = Field(min_length=1, max_length=10000)
    integrated_loudness_lufs: float
    true_peak_dbfs: float
    clipping_sample_count: int = Field(ge=0)
    speech_music_ratio_db: float
    ducking_applied: bool
    timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_timeline_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    render_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_render_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    preview_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    final_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    render_width: int = Field(gt=0)
    render_height: int = Field(gt=0)
    render_duration_seconds: float = Field(gt=0)
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
    def validate_run_contract(self) -> "FlowBRunEvidence":
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("Flow B run completion must not precede its start")
        provider_keys = [provider.provider_key for provider in self.providers]
        if len(provider_keys) != len(set(provider_keys)):
            raise ValueError("Flow B provider keys must be unique within a run")
        source_ids = [source.source_id for source in self.research_sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("Flow B source IDs must be unique within a run")
        claim_ids = [claim.claim_id for claim in self.claim_map]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("Flow B claim IDs must be unique within a run")
        if len(self.script_claim_ids) != len(set(self.script_claim_ids)):
            raise ValueError("Flow B script claim IDs must be unique")
        if any(score < 0 or score > 1 for score in self.originality_similarity_scores):
            raise ValueError("Flow B originality similarity scores must be between zero and one")
        shot_ids = self.storyboard_shot_ids
        if len(shot_ids) != len(set(shot_ids)):
            raise ValueError("Flow B storyboard shot IDs must be unique")
        asset_ids = [asset.asset_id for asset in self.assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("Flow B asset IDs must be unique within a run")
        provider_cost = sum(
            (provider.charged_cost_vnd for provider in self.providers),
            Decimal("0"),
        )
        if self.cost_ledger_total_vnd < provider_cost:
            raise ValueError("run cost ledger cannot be lower than provider charges")
        if self.human_review_passed and not self.human_review_final_sha256:
            raise ValueError("a passed human review must bind the final video hash")
        return self


class FlowBAcceptanceBundle(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-05"] = "V3-01-05"
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: Literal["LOCAL", "CI", "STAGING_PRODUCTION_LIKE", "PRODUCTION"]
    gates: FlowBGateSnapshot
    safety: FlowBSafetySnapshot
    runs: list[FlowBRunEvidence] = Field(min_length=2, max_length=2)
    secret_recorded: Literal[False] = False


class FlowBRunMetrics(StrictModel):
    run_id: str
    research_source_count: int = Field(ge=0)
    claim_source_coverage: float = Field(ge=0, le=1)
    verified_claim_coverage: float = Field(ge=0, le=1)
    maximum_originality_similarity: float = Field(ge=0, le=1)
    storyboard_plan_coverage: float = Field(ge=0, le=1)
    asset_shot_coverage: float = Field(ge=0, le=1)
    rights_completeness: float = Field(ge=0, le=1)
    receipt_completeness: float = Field(ge=0, le=1)
    minimum_visual_relevance: float = Field(ge=0, le=1)
    tts_duration_deviation_ratio: float = Field(ge=0)
    subtitle_median_drift_seconds: float = Field(ge=0)
    subtitle_p95_drift_seconds: float = Field(ge=0)
    cost_total_vnd: Decimal = Field(ge=0)
    technical_passed: bool
    failures: list[str]


class FlowBAxisResult(StrictModel):
    status: AxisStatus
    reasons: list[str] = Field(default_factory=list)


class FlowBAcceptanceEvaluation(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-05"] = "V3-01-05"
    verdict: Verdict
    two_consecutive_runs: bool
    run_metrics: list[FlowBRunMetrics]
    implemented: FlowBAxisResult
    mock_tested: FlowBAxisResult
    real_provider_tested: FlowBAxisResult
    production_path_tested: FlowBAxisResult
    quality_accepted: FlowBAxisResult
    pending_owner_gates: list[Literal["G-01", "G-02", "G-03", "G-04", "G-11"]]
    cost_total_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    external_actions_performed: Literal[False] = False
    publish_performed: Literal[False] = False


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _p95(values: list[float]) -> float:
    ordered = sorted(abs(value) for value in values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _evaluate_run(run: FlowBRunEvidence, policy: FlowBAcceptancePolicy) -> FlowBRunMetrics:
    failures: list[str] = []
    source_ids = {source.source_id for source in run.research_sources}
    claims = {claim.claim_id: claim for claim in run.claim_map}
    script_claims = [claims.get(claim_id) for claim_id in run.script_claim_ids]
    sourced = sum(
        claim is not None
        and bool(claim.source_ids)
        and set(claim.source_ids).issubset(source_ids)
        for claim in script_claims
    )
    verified = sum(
        claim is not None
        and claim.included_in_script
        and claim.verification_status == "verified"
        for claim in script_claims
    )
    claim_source_coverage = _ratio(sourced, len(run.script_claim_ids))
    verified_claim_coverage = _ratio(verified, len(run.script_claim_ids))
    maximum_similarity = max(run.originality_similarity_scores)

    storyboard_shots = set(run.storyboard_shot_ids)
    planned_shots = set(run.media_plan_shot_ids)
    storyboard_plan_coverage = _ratio(len(storyboard_shots & planned_shots), len(storyboard_shots))
    visual_assets = [asset for asset in run.assets if asset.kind != "music"]
    covered_shots = {
        shot_id
        for asset in visual_assets
        for shot_id in asset.used_in_shot_ids
        if shot_id in storyboard_shots
    }
    asset_shot_coverage = _ratio(len(covered_shots), len(storyboard_shots))
    rights_completeness = _ratio(
        sum(bool(asset.rights_record_id) for asset in run.assets),
        len(run.assets),
    )
    receipt_completeness = _ratio(
        sum(
            bool(asset.provider_receipt_sha256 and asset.transformation_lineage_sha256)
            for asset in run.assets
        ),
        len(run.assets),
    )
    relevance_values = [
        asset.visual_relevance_score
        for asset in visual_assets
        if asset.visual_relevance_score is not None
    ]
    minimum_relevance = min(relevance_values) if relevance_values else 0.0
    duration_deviation = abs(
        run.narration_actual_duration_seconds - run.narration_expected_duration_seconds
    ) / run.narration_expected_duration_seconds
    drift_values = [abs(value) for value in run.subtitle_drift_seconds]
    drift_median = float(median(drift_values))
    drift_p95 = _p95(drift_values)

    if len(run.research_sources) < policy.minimum_research_sources:
        failures.append("RESEARCH_SOURCE_COUNT_BELOW_MINIMUM")
    if claim_source_coverage < policy.minimum_claim_source_coverage:
        failures.append("CLAIM_SOURCE_COVERAGE_INCOMPLETE")
    if verified_claim_coverage < policy.minimum_verified_claim_coverage:
        failures.append("SCRIPT_FACTUAL_CONSISTENCY_INCOMPLETE")
    if maximum_similarity > policy.maximum_originality_similarity:
        failures.append("ORIGINALITY_SIMILARITY_EXCEEDS_THRESHOLD")
    if storyboard_plan_coverage < policy.minimum_storyboard_plan_coverage:
        failures.append("STORYBOARD_MEDIA_PLAN_COVERAGE_INCOMPLETE")
    if asset_shot_coverage < policy.minimum_asset_shot_coverage:
        failures.append("VISUAL_ASSET_SHOT_COVERAGE_INCOMPLETE")
    required_kinds = set(policy.required_asset_kinds)
    if not required_kinds.issubset({asset.kind for asset in run.assets}):
        failures.append("REQUIRED_MEDIA_KIND_MISSING")
    if rights_completeness < 1:
        failures.append("ASSET_RIGHTS_PROVENANCE_INCOMPLETE")
    if receipt_completeness < 1 or not run.provider_receipts_valid:
        failures.append("ASSET_OR_PROVIDER_RECEIPT_INCOMPLETE")
    provider_keys = {provider.provider_key for provider in run.providers}
    if any(asset.provider_key and asset.provider_key not in provider_keys for asset in run.assets):
        failures.append("ASSET_PROVIDER_REFERENCE_INVALID")
    if any(
        shot_id not in storyboard_shots
        for asset in visual_assets
        for shot_id in asset.used_in_shot_ids
    ):
        failures.append("ASSET_SHOT_REFERENCE_INVALID")
    if any(not asset.decoded_or_verified for asset in run.assets):
        failures.append("ASSET_DECODE_OR_VERIFICATION_FAILED")
    if minimum_relevance < policy.minimum_visual_relevance:
        failures.append("VISUAL_RELEVANCE_BELOW_THRESHOLD")
    if set(policy.required_provider_capabilities) - {provider.capability for provider in run.providers}:
        failures.append("REQUIRED_PROVIDER_CAPABILITY_MISSING")
    if duration_deviation > policy.maximum_tts_duration_deviation_ratio:
        failures.append("TTS_DURATION_ALIGNMENT_EXCEEDS_THRESHOLD")
    if drift_median > policy.maximum_subtitle_median_drift_seconds:
        failures.append("SUBTITLE_MEDIAN_DRIFT_EXCEEDS_200MS")
    if drift_p95 > policy.maximum_subtitle_p95_drift_seconds:
        failures.append("SUBTITLE_P95_DRIFT_EXCEEDS_500MS")
    if not (
        policy.minimum_integrated_loudness_lufs
        <= run.integrated_loudness_lufs
        <= policy.maximum_integrated_loudness_lufs
    ):
        failures.append("INTEGRATED_LOUDNESS_OUTSIDE_RANGE")
    if run.true_peak_dbfs > policy.maximum_true_peak_dbfs or run.clipping_sample_count:
        failures.append("AUDIO_PEAK_OR_CLIPPING_QC_FAILED")
    if run.speech_music_ratio_db < policy.minimum_speech_music_ratio_db or not run.ducking_applied:
        failures.append("MUSIC_DUCKING_OR_SPEECH_RATIO_FAILED")
    if run.timeline_sha256 != run.approved_timeline_sha256:
        failures.append("APPROVAL_NOT_BOUND_TO_TIMELINE")
    if run.render_input_sha256 != run.approved_render_input_sha256:
        failures.append("APPROVAL_NOT_BOUND_TO_RENDER_INPUT")
    if run.render_width < policy.minimum_render_width or run.render_height < policy.minimum_render_height:
        failures.append("RENDER_RESOLUTION_BELOW_MINIMUM")
    if not all(
        (
            run.full_decode_passed,
            run.black_frame_qc_passed,
            run.silence_qc_passed,
            run.frozen_frame_qc_passed,
            run.av_sync_qc_passed,
        )
    ):
        failures.append("RENDER_TECHNICAL_QC_FAILED")
    if not run.restart_recovered:
        failures.append("RESTART_RECOVERY_NOT_PROVEN")

    return FlowBRunMetrics(
        run_id=run.run_id,
        research_source_count=len(run.research_sources),
        claim_source_coverage=round(claim_source_coverage, 6),
        verified_claim_coverage=round(verified_claim_coverage, 6),
        maximum_originality_similarity=round(maximum_similarity, 6),
        storyboard_plan_coverage=round(storyboard_plan_coverage, 6),
        asset_shot_coverage=round(asset_shot_coverage, 6),
        rights_completeness=round(rights_completeness, 6),
        receipt_completeness=round(receipt_completeness, 6),
        minimum_visual_relevance=round(minimum_relevance, 6),
        tts_duration_deviation_ratio=round(duration_deviation, 6),
        subtitle_median_drift_seconds=round(drift_median, 6),
        subtitle_p95_drift_seconds=round(drift_p95, 6),
        cost_total_vnd=run.cost_ledger_total_vnd,
        technical_passed=not failures,
        failures=failures,
    )


def evaluate_flow_b(
    bundle: FlowBAcceptanceBundle,
    policy: FlowBAcceptancePolicy | None = None,
) -> FlowBAcceptanceEvaluation:
    policy = policy or FlowBAcceptancePolicy()
    ordered = sorted(bundle.runs, key=lambda run: run.sequence)
    sequence_ok = [run.sequence for run in ordered] == [1, 2]
    distinct_runs = len({run.run_id for run in ordered}) == 2
    locked_commit = all(
        run.release_candidate_commit == bundle.release_candidate_commit for run in ordered
    )
    chronological = ordered[0].completed_at_utc <= ordered[1].started_at_utc
    two_consecutive_runs = all((sequence_ok, distinct_runs, locked_commit, chronological))
    metrics = [_evaluate_run(run, policy) for run in ordered]

    mock_reasons: list[str] = []
    if not two_consecutive_runs:
        mock_reasons.append("TWO_CONSECUTIVE_LOCKED_RC_RUNS_NOT_PROVEN")
    mock_reasons.extend(
        f"{metric.run_id}:{failure}" for metric in metrics for failure in metric.failures
    )
    mock_axis = FlowBAxisResult(status="PASS" if not mock_reasons else "FAIL", reasons=mock_reasons)

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
    if not real_gate_pending:
        providers = [provider for run in ordered for provider in run.providers]
        sources = [source for run in ordered for source in run.research_sources]
        if not all(
            provider.real_provider_tested and not provider.fixture and provider.production_eligible
            for provider in providers
        ):
            real_reasons.append("REAL_PRODUCTION_ELIGIBLE_PROVIDER_EVIDENCE_INCOMPLETE")
        if not all(source.real_source_tested and not source.fixture for source in sources):
            real_reasons.append("REAL_RESEARCH_SOURCE_EVIDENCE_INCOMPLETE")
        if not all(asset.rights_record_id for run in ordered for asset in run.assets):
            real_reasons.append("REAL_ASSET_RIGHTS_EVIDENCE_INCOMPLETE")
        if not all(not asset.fixture for run in ordered for asset in run.assets):
            real_reasons.append("REAL_ASSET_EVIDENCE_INCOMPLETE")
        external_real = any(provider.external_call for provider in providers)
        paid_real = any(provider.paid for provider in providers)
        if external_real and (
            not bundle.safety.external_execution_enabled
            or bundle.safety.global_kill_switch_engaged
        ):
            real_reasons.append("EXTERNAL_PROVIDER_SAFETY_STATE_NOT_AUTHORIZED")
        if paid_real and (
            not bundle.safety.paid_execution_enabled or bundle.safety.daily_budget_vnd <= 0
        ):
            real_reasons.append("PAID_PROVIDER_VND_BUDGET_NOT_ACTIVE")
    real_axis = FlowBAxisResult(
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
    production_axis = FlowBAxisResult(status=production_status, reasons=production_reasons)

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
    quality_axis = FlowBAxisResult(status=quality_status, reasons=quality_reasons)

    axes = [mock_axis, real_axis, production_axis, quality_axis]
    if any(axis.status == "FAIL" for axis in axes):
        verdict: Verdict = "FAIL"
    elif all(axis.status == "PASS" for axis in axes):
        verdict = "PASS"
    else:
        verdict = "BLOCKED"
    return FlowBAcceptanceEvaluation(
        verdict=verdict,
        two_consecutive_runs=two_consecutive_runs,
        run_metrics=metrics,
        implemented=FlowBAxisResult(
            status="PASS",
            reasons=["FLOW_B_ACCEPTANCE_CONTRACT_AND_DETERMINISTIC_EVALUATOR_PRESENT"],
        ),
        mock_tested=mock_axis,
        real_provider_tested=real_axis,
        production_path_tested=production_axis,
        quality_accepted=quality_axis,
        pending_owner_gates=pending,
        cost_total_vnd=sum((run.cost_ledger_total_vnd for run in ordered), Decimal("0")),
    )
