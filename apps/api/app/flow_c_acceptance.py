from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .models import StrictModel


AxisStatus = Literal["PASS", "FAIL", "BLOCKED", "NOT_TESTED"]
Verdict = Literal["PASS", "FAIL", "BLOCKED"]
ProviderCapability = Literal["trend", "analytics"]
Platform = Literal["youtube", "tiktok", "instagram_reels", "facebook"]
OwnerGate = Literal["G-01", "G-02", "G-03", "G-04", "G-05", "G-06", "G-11"]
MetricName = Literal[
    "views",
    "impressions",
    "reach",
    "watch_time",
    "average_view_duration",
    "completion_rate",
    "likes",
    "comments",
    "shares",
    "saves",
    "followers_gained",
    "clicks",
    "ctr",
    "revenue",
    "rpm",
    "observation_window_hours",
]


METRIC_NAMES: tuple[MetricName, ...] = (
    "views",
    "impressions",
    "reach",
    "watch_time",
    "average_view_duration",
    "completion_rate",
    "likes",
    "comments",
    "shares",
    "saves",
    "followers_gained",
    "clicks",
    "ctr",
    "revenue",
    "rpm",
    "observation_window_hours",
)


class FlowCAcceptancePolicy(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-06"] = "V3-01-06"
    consecutive_runs_required: Literal[2] = 2
    minimum_trend_sources: int = Field(default=3, ge=2)
    minimum_provenance_completeness: float = Field(default=1.0, ge=0, le=1)
    minimum_cluster_determinism: float = Field(default=1.0, ge=0, le=1)
    maximum_opportunity_score_delta: float = Field(default=0.000001, ge=0)
    minimum_analytics_snapshots: int = Field(default=2, ge=2)
    minimum_analytics_metric_completeness: float = Field(default=1.0, ge=0, le=1)
    minimum_learning_lineage_completeness: float = Field(default=1.0, ge=0, le=1)
    required_provider_capabilities: tuple[ProviderCapability, ...] = ("trend", "analytics")
    required_metrics: tuple[MetricName, ...] = METRIC_NAMES
    required_owner_gates: tuple[OwnerGate, ...] = (
        "G-01",
        "G-02",
        "G-03",
        "G-04",
        "G-05",
        "G-06",
        "G-11",
    )
    currency: Literal["VND"] = "VND"
    external_action_allowed_during_contract_test: Literal[False] = False
    real_publish_allowed_during_contract_test: Literal[False] = False


class FlowCProviderEvidence(StrictModel):
    capability: ProviderCapability
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    adapter_or_api_version: str = Field(min_length=1, max_length=240)
    fixture: bool
    external_call: bool
    paid: bool
    real_provider_tested: bool
    production_eligible: bool
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    charged_cost_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_provider_claim(self) -> "FlowCProviderEvidence":
        if self.fixture and self.real_provider_tested:
            raise ValueError("fixture provider cannot be promoted to real-provider evidence")
        if self.paid and not self.external_call:
            raise ValueError("paid provider evidence must be classified as external")
        return self


class FlowCTrendSourceEvidence(StrictModel):
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    source_locator_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=240)
    retrieved_at_utc: datetime
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    provenance_complete: bool
    fixture: bool
    external_call: bool
    real_source_tested: bool
    secret_recorded: Literal[False] = False

    @model_validator(mode="after")
    def validate_source_claim(self) -> "FlowCTrendSourceEvidence":
        if self.fixture and self.real_source_tested:
            raise ValueError("fixture trend source cannot be promoted to real-source evidence")
        if self.fixture and self.external_call:
            raise ValueError("fixture trend source cannot claim an external call")
        return self


class FlowCTrendSignalEvidence(StrictModel):
    signal_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    source_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    normalized_topic: str = Field(min_length=1, max_length=500)
    normalized_signal_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")


class FlowCTrendClusterEvidence(StrictModel):
    cluster_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    member_signal_ids: list[str] = Field(min_length=1, max_length=1000)
    cluster_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    recomputed_cluster_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_unique_members(self) -> "FlowCTrendClusterEvidence":
        if len(self.member_signal_ids) != len(set(self.member_signal_ids)):
            raise ValueError("trend cluster member signal IDs must be unique")
        return self


class FlowCOpportunityEvidence(StrictModel):
    opportunity_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    cluster_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    score_input_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    opportunity_score: float = Field(ge=0, le=100)
    recomputed_opportunity_score: float = Field(ge=0, le=100)
    formula_version: str = Field(min_length=1, max_length=120)


class FlowCMetricPointEvidence(StrictModel):
    metric: MetricName
    value: float | None = Field(default=None, ge=0)
    unit: str = Field(min_length=1, max_length=80)
    supported: bool

    @model_validator(mode="after")
    def validate_null_semantics(self) -> "FlowCMetricPointEvidence":
        if not self.supported and self.value is not None:
            raise ValueError("unsupported analytics metric must be represented as null")
        if self.metric in {"completion_rate", "ctr"} and self.value is not None and self.value > 1:
            raise ValueError("ratio analytics metric must be between zero and one")
        return self


class FlowCAnalyticsSnapshotEvidence(StrictModel):
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    publication_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    provider_key: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{1,119}$")
    collected_at_utc: datetime
    source_kind: Literal["fixture", "official_api"]
    fixture: bool
    external_call: bool
    real_provider_tested: bool
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    response_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    points: list[FlowCMetricPointEvidence] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def validate_snapshot_claim(self) -> "FlowCAnalyticsSnapshotEvidence":
        metrics = [point.metric for point in self.points]
        if len(metrics) != len(set(metrics)):
            raise ValueError("analytics snapshot metric names must be unique")
        if self.fixture and self.real_provider_tested:
            raise ValueError("fixture analytics snapshot cannot be promoted to real evidence")
        if self.fixture and (self.external_call or self.source_kind != "fixture"):
            raise ValueError("fixture analytics snapshot must remain local fixture evidence")
        if not self.fixture and self.source_kind == "fixture":
            raise ValueError("non-fixture analytics snapshot cannot use fixture source kind")
        return self


class FlowCPublicationEvidence(StrictModel):
    publication_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    platform: Platform
    final_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    approved_final_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    publication_bound_video_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_record_ids: list[str] = Field(min_length=1, max_length=1000)
    rights_gate_passed: bool
    platform_validation_passed: bool
    platform_validation_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    request_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    duplicate_fingerprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    replay_publication_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    idempotent_replay: bool
    duplicate_post_created: Literal[False] = False
    duplicate_prevention_passed: bool
    status: Literal["dry_run_succeeded", "published"]
    fixture: bool
    external_action: bool
    real_publication_tested: bool
    remote_post_id: str | None = Field(default=None, min_length=1, max_length=240)
    receipt_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    verified_receipt_payload_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    receipt_valid: bool
    production_path_tested: bool

    @model_validator(mode="after")
    def validate_publication_claim(self) -> "FlowCPublicationEvidence":
        if self.fixture and self.real_publication_tested:
            raise ValueError("fixture publication cannot be promoted to real publication evidence")
        if self.fixture and self.external_action:
            raise ValueError("fixture publication cannot claim an external action")
        if self.real_publication_tested:
            if not self.external_action or self.status != "published" or not self.remote_post_id:
                raise ValueError("real publication evidence requires a remote published receipt")
        elif self.remote_post_id is not None:
            raise ValueError("non-real publication evidence cannot record a remote post ID")
        return self


class FlowCWinnerFactorEvidence(StrictModel):
    factor: str = Field(min_length=1, max_length=120)
    score: float | None = Field(default=None, ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)


class FlowCWinnerAssessmentEvidence(StrictModel):
    assessment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    state: Literal["winner_candidate", "normal", "underperforming", "insufficient_data"]
    score: float | None = Field(default=None, ge=0, le=100)
    recomputed_score: float | None = Field(default=None, ge=0, le=100)
    factors: list[FlowCWinnerFactorEvidence] = Field(min_length=1, max_length=100)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    algorithm_version: str = Field(min_length=1, max_length=120)
    automatic_action: Literal[False] = False
    paid_media_mutation: Literal[False] = False


class FlowCLearningInsightEvidence(StrictModel):
    insight_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    assessment_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    snapshot_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    trend_cluster_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    idea_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    recommendation: str = Field(min_length=1, max_length=1000)
    evidence_refs: list[str] = Field(min_length=1, max_length=100)
    applied: Literal[False] = False
    autonomous_execution: Literal[False] = False


class FlowCGateSnapshot(StrictModel):
    g01_credentials: bool = False
    g02_vnd_budget: bool = False
    g03_rights_inputs: bool = False
    g04_production_like_staging: bool = False
    g05_exact_artifact_approval: bool = False
    g06_live_publication: bool = False
    g11_human_quality: bool = False
    approval_ids: list[str] = Field(default_factory=list, max_length=20)


class FlowCSafetySnapshot(StrictModel):
    external_execution_enabled: bool = False
    paid_execution_enabled: bool = False
    analytics_external_execution_enabled: bool = False
    global_kill_switch_engaged: bool = True
    daily_budget_vnd: Decimal = Field(default=Decimal("0"), ge=0)
    production_write_performed: bool = False
    publish_performed: bool = False


class FlowCRunEvidence(StrictModel):
    sequence: int = Field(ge=1, le=2)
    run_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    started_at_utc: datetime
    completed_at_utc: datetime
    workspace_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    providers: list[FlowCProviderEvidence] = Field(min_length=2, max_length=20)
    trend_sources: list[FlowCTrendSourceEvidence] = Field(min_length=1, max_length=100)
    trend_signals: list[FlowCTrendSignalEvidence] = Field(min_length=1, max_length=1000)
    trend_clusters: list[FlowCTrendClusterEvidence] = Field(min_length=1, max_length=1000)
    opportunities: list[FlowCOpportunityEvidence] = Field(min_length=1, max_length=1000)
    selected_opportunity_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    idea_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    idea_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    idea_bound_cluster_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    project_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,159}$")
    project_bound_idea_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    publication: FlowCPublicationEvidence
    analytics_snapshots: list[FlowCAnalyticsSnapshotEvidence] = Field(min_length=2, max_length=100)
    winner_assessment: FlowCWinnerAssessmentEvidence
    learning_insights: list[FlowCLearningInsightEvidence] = Field(min_length=1, max_length=100)
    cost_ledger_total_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    restart_recovered: bool
    human_review_passed: bool
    human_review_final_sha256: str | None = Field(
        default=None,
        pattern=r"^[a-f0-9]{64}$",
    )
    external_action_performed: bool
    publish_performed: bool

    @model_validator(mode="after")
    def validate_run_contract(self) -> "FlowCRunEvidence":
        if self.completed_at_utc < self.started_at_utc:
            raise ValueError("Flow C run completion must not precede its start")
        for label, values in (
            ("provider keys", [item.provider_key for item in self.providers]),
            ("source IDs", [item.source_id for item in self.trend_sources]),
            ("signal IDs", [item.signal_id for item in self.trend_signals]),
            ("cluster IDs", [item.cluster_id for item in self.trend_clusters]),
            ("opportunity IDs", [item.opportunity_id for item in self.opportunities]),
            ("snapshot IDs", [item.snapshot_id for item in self.analytics_snapshots]),
            ("insight IDs", [item.insight_id for item in self.learning_insights]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"Flow C {label} must be unique within a run")
        provider_cost = sum(
            (provider.charged_cost_vnd for provider in self.providers),
            Decimal("0"),
        )
        if self.cost_ledger_total_vnd < provider_cost:
            raise ValueError("run cost ledger cannot be lower than provider charges")
        if self.human_review_passed and not self.human_review_final_sha256:
            raise ValueError("a passed human review must bind the final video hash")
        return self


class FlowCAcceptanceBundle(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-06"] = "V3-01-06"
    release_candidate_commit: str = Field(pattern=r"^[a-f0-9]{40}$")
    environment: Literal["LOCAL", "CI", "STAGING_PRODUCTION_LIKE", "PRODUCTION"]
    gates: FlowCGateSnapshot
    safety: FlowCSafetySnapshot
    runs: list[FlowCRunEvidence] = Field(min_length=2, max_length=2)
    secret_recorded: Literal[False] = False


class FlowCRunMetrics(StrictModel):
    run_id: str
    trend_source_count: int = Field(ge=0)
    provenance_completeness: float = Field(ge=0, le=1)
    cluster_determinism: float = Field(ge=0, le=1)
    maximum_opportunity_score_delta: float = Field(ge=0)
    idea_trend_binding: bool
    project_idea_binding: bool
    video_hash_binding: bool
    rights_gate_passed: bool
    platform_validation_passed: bool
    idempotency_replay_passed: bool
    duplicate_prevention_passed: bool
    receipt_integrity_passed: bool
    analytics_metric_completeness: float = Field(ge=0, le=1)
    missing_metric_null_semantics_passed: bool
    snapshot_ordering_passed: bool
    winner_explainability_passed: bool
    learning_lineage_completeness: float = Field(ge=0, le=1)
    cost_total_vnd: Decimal = Field(ge=0)
    restart_recovered: bool
    technical_passed: bool
    failures: list[str]


class FlowCAxisResult(StrictModel):
    status: AxisStatus
    reasons: list[str] = Field(default_factory=list)


class FlowCAcceptanceEvaluation(StrictModel):
    schema_version: Literal[1] = 1
    checkpoint: Literal["V3-01-06"] = "V3-01-06"
    verdict: Verdict
    two_consecutive_runs: bool
    run_metrics: list[FlowCRunMetrics]
    implemented: FlowCAxisResult
    mock_tested: FlowCAxisResult
    real_provider_tested: FlowCAxisResult
    production_path_tested: FlowCAxisResult
    quality_accepted: FlowCAxisResult
    pending_owner_gates: list[OwnerGate]
    cost_total_vnd: Decimal = Field(ge=0)
    currency: Literal["VND"] = "VND"
    external_actions_performed: bool
    publish_performed: bool


def _ratio(numerator: int, denominator: int) -> float:
    return 0.0 if denominator == 0 else numerator / denominator


def _evaluate_run(run: FlowCRunEvidence, policy: FlowCAcceptancePolicy) -> FlowCRunMetrics:
    failures: list[str] = []
    providers = {provider.provider_key: provider for provider in run.providers}
    sources = {source.source_id: source for source in run.trend_sources}
    signals = {signal.signal_id: signal for signal in run.trend_signals}
    clusters = {cluster.cluster_id: cluster for cluster in run.trend_clusters}
    opportunities = {item.opportunity_id: item for item in run.opportunities}

    provenance_completeness = _ratio(
        sum(source.provenance_complete for source in run.trend_sources),
        len(run.trend_sources),
    )
    cluster_determinism = _ratio(
        sum(cluster.cluster_sha256 == cluster.recomputed_cluster_sha256 for cluster in run.trend_clusters),
        len(run.trend_clusters),
    )
    score_delta = max(
        abs(item.opportunity_score - item.recomputed_opportunity_score)
        for item in run.opportunities
    )

    selected_opportunity = opportunities.get(run.selected_opportunity_id)
    selected_cluster = (
        clusters.get(selected_opportunity.cluster_id) if selected_opportunity is not None else None
    )
    idea_binding = bool(
        selected_cluster
        and run.idea_bound_cluster_sha256 == selected_cluster.cluster_sha256
    )
    project_binding = run.project_bound_idea_sha256 == run.idea_sha256
    publication = run.publication
    video_binding = (
        publication.project_id == run.project_id
        and publication.final_video_sha256 == publication.approved_final_video_sha256
        and publication.final_video_sha256 == publication.publication_bound_video_sha256
    )
    idempotency = (
        publication.idempotent_replay
        and publication.replay_publication_id == publication.publication_id
    )
    duplicate_prevention = (
        publication.duplicate_prevention_passed and not publication.duplicate_post_created
    )
    receipt_integrity = (
        publication.receipt_valid
        and publication.receipt_payload_sha256 == publication.verified_receipt_payload_sha256
    )

    required_metrics = set(policy.required_metrics)
    present_points = sum(
        len(required_metrics & {point.metric for point in snapshot.points})
        for snapshot in run.analytics_snapshots
    )
    metric_completeness = _ratio(
        present_points,
        len(required_metrics) * len(run.analytics_snapshots),
    )
    null_semantics = all(
        point.supported or point.value is None
        for snapshot in run.analytics_snapshots
        for point in snapshot.points
    )
    snapshot_ordering = all(
        earlier.collected_at_utc < later.collected_at_utc
        for earlier, later in zip(run.analytics_snapshots, run.analytics_snapshots[1:])
    )
    latest_snapshot = max(run.analytics_snapshots, key=lambda item: item.collected_at_utc)
    assessment = run.winner_assessment
    score_reproducible = (
        assessment.score is None
        and assessment.recomputed_score is None
        or assessment.score is not None
        and assessment.recomputed_score is not None
        and abs(assessment.score - assessment.recomputed_score) <= policy.maximum_opportunity_score_delta
    )
    winner_explainable = bool(
        assessment.snapshot_id == latest_snapshot.snapshot_id
        and score_reproducible
        and assessment.factors
        and assessment.evidence_refs
        and all(factor.evidence_refs for factor in assessment.factors)
    )
    valid_insights = sum(
        insight.assessment_id == assessment.assessment_id
        and insight.snapshot_id == latest_snapshot.snapshot_id
        and selected_cluster is not None
        and insight.trend_cluster_id == selected_cluster.cluster_id
        and insight.idea_id == run.idea_id
        and bool(insight.evidence_refs)
        and not insight.applied
        and not insight.autonomous_execution
        for insight in run.learning_insights
    )
    learning_lineage = _ratio(valid_insights, len(run.learning_insights))

    if len(run.trend_sources) < policy.minimum_trend_sources:
        failures.append("TREND_SOURCE_COUNT_BELOW_MINIMUM")
    if provenance_completeness < policy.minimum_provenance_completeness:
        failures.append("TREND_SOURCE_PROVENANCE_INCOMPLETE")
    if set(policy.required_provider_capabilities) - {provider.capability for provider in run.providers}:
        failures.append("REQUIRED_PROVIDER_CAPABILITY_MISSING")
    if any(source.provider_key not in providers for source in run.trend_sources):
        failures.append("TREND_SOURCE_PROVIDER_REFERENCE_INVALID")
    if any(signal.source_id not in sources for signal in run.trend_signals):
        failures.append("TREND_SIGNAL_SOURCE_REFERENCE_INVALID")
    if any(
        signal_id not in signals
        for cluster in run.trend_clusters
        for signal_id in cluster.member_signal_ids
    ):
        failures.append("TREND_CLUSTER_SIGNAL_REFERENCE_INVALID")
    if cluster_determinism < policy.minimum_cluster_determinism:
        failures.append("TREND_CLUSTER_NOT_DETERMINISTIC")
    if any(item.cluster_id not in clusters for item in run.opportunities):
        failures.append("OPPORTUNITY_CLUSTER_REFERENCE_INVALID")
    if score_delta > policy.maximum_opportunity_score_delta:
        failures.append("OPPORTUNITY_SCORE_NOT_REPRODUCIBLE")
    if selected_opportunity is None:
        failures.append("SELECTED_OPPORTUNITY_REFERENCE_INVALID")
    if not idea_binding:
        failures.append("IDEA_TREND_BINDING_INVALID")
    if not project_binding:
        failures.append("PROJECT_IDEA_BINDING_INVALID")
    if not video_binding:
        failures.append("VIDEO_PROJECT_OR_APPROVAL_HASH_BINDING_INVALID")
    if not publication.rights_gate_passed or not publication.rights_record_ids:
        failures.append("RIGHTS_GATE_NOT_PROVEN")
    if not publication.platform_validation_passed:
        failures.append("PLATFORM_VALIDATION_NOT_PROVEN")
    if not idempotency:
        failures.append("PUBLISH_IDEMPOTENCY_REPLAY_FAILED")
    if not duplicate_prevention:
        failures.append("DUPLICATE_POST_PREVENTION_FAILED")
    if not receipt_integrity:
        failures.append("PUBLICATION_RECEIPT_INTEGRITY_FAILED")
    if len(run.analytics_snapshots) < policy.minimum_analytics_snapshots:
        failures.append("ANALYTICS_SNAPSHOT_COUNT_BELOW_MINIMUM")
    if any(snapshot.publication_id != publication.publication_id for snapshot in run.analytics_snapshots):
        failures.append("ANALYTICS_PUBLICATION_REFERENCE_INVALID")
    if any(
        snapshot.provider_key not in providers
        or providers[snapshot.provider_key].capability != "analytics"
        for snapshot in run.analytics_snapshots
    ):
        failures.append("ANALYTICS_PROVIDER_REFERENCE_INVALID")
    if metric_completeness < policy.minimum_analytics_metric_completeness:
        failures.append("ANALYTICS_NORMALIZATION_INCOMPLETE")
    if not null_semantics:
        failures.append("MISSING_ANALYTICS_METRIC_NOT_NULL")
    if not snapshot_ordering:
        failures.append("ANALYTICS_SNAPSHOT_ORDERING_INVALID")
    if not winner_explainable:
        failures.append("WINNER_SCORE_NOT_REPRODUCIBLE_OR_EXPLAINABLE")
    if learning_lineage < policy.minimum_learning_lineage_completeness:
        failures.append("LEARNING_FEEDBACK_LINEAGE_INCOMPLETE")
    if not run.restart_recovered:
        failures.append("RESTART_RECOVERY_NOT_PROVEN")
    if publication.fixture and (
        publication.external_action or publication.status != "dry_run_succeeded"
    ):
        failures.append("FIXTURE_PUBLICATION_BOUNDARY_VIOLATED")

    return FlowCRunMetrics(
        run_id=run.run_id,
        trend_source_count=len(run.trend_sources),
        provenance_completeness=round(provenance_completeness, 6),
        cluster_determinism=round(cluster_determinism, 6),
        maximum_opportunity_score_delta=round(score_delta, 9),
        idea_trend_binding=idea_binding,
        project_idea_binding=project_binding,
        video_hash_binding=video_binding,
        rights_gate_passed=publication.rights_gate_passed,
        platform_validation_passed=publication.platform_validation_passed,
        idempotency_replay_passed=idempotency,
        duplicate_prevention_passed=duplicate_prevention,
        receipt_integrity_passed=receipt_integrity,
        analytics_metric_completeness=round(metric_completeness, 6),
        missing_metric_null_semantics_passed=null_semantics,
        snapshot_ordering_passed=snapshot_ordering,
        winner_explainability_passed=winner_explainable,
        learning_lineage_completeness=round(learning_lineage, 6),
        cost_total_vnd=run.cost_ledger_total_vnd,
        restart_recovered=run.restart_recovered,
        technical_passed=not failures,
        failures=failures,
    )


def evaluate_flow_c(
    bundle: FlowCAcceptanceBundle,
    policy: FlowCAcceptancePolicy | None = None,
) -> FlowCAcceptanceEvaluation:
    policy = policy or FlowCAcceptancePolicy()
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
    if bundle.environment in {"LOCAL", "CI"} and (
        bundle.safety.external_execution_enabled
        or bundle.safety.analytics_external_execution_enabled
        or bundle.safety.production_write_performed
        or bundle.safety.publish_performed
        or any(run.external_action_performed or run.publish_performed for run in ordered)
    ):
        mock_reasons.append("OFFLINE_CONTRACT_TEST_EXTERNAL_ACTION_BOUNDARY_VIOLATED")
    mock_axis = FlowCAxisResult(status="PASS" if not mock_reasons else "FAIL", reasons=mock_reasons)

    gate_values: list[tuple[OwnerGate, bool]] = [
        ("G-01", bundle.gates.g01_credentials),
        ("G-02", bundle.gates.g02_vnd_budget),
        ("G-03", bundle.gates.g03_rights_inputs),
        ("G-04", bundle.gates.g04_production_like_staging),
        ("G-05", bundle.gates.g05_exact_artifact_approval),
        ("G-06", bundle.gates.g06_live_publication),
        ("G-11", bundle.gates.g11_human_quality),
    ]
    pending = [gate for gate, granted in gate_values if not granted]

    real_gate_pending = [gate for gate in pending if gate in {"G-01", "G-02", "G-03"}]
    real_reasons = [f"OWNER_GATE_PENDING:{gate}" for gate in real_gate_pending]
    if not real_gate_pending:
        providers = [provider for run in ordered for provider in run.providers]
        sources = [source for run in ordered for source in run.trend_sources]
        snapshots = [snapshot for run in ordered for snapshot in run.analytics_snapshots]
        if not all(
            provider.real_provider_tested and not provider.fixture and provider.production_eligible
            for provider in providers
        ):
            real_reasons.append("REAL_PRODUCTION_ELIGIBLE_PROVIDER_EVIDENCE_INCOMPLETE")
        if not all(source.real_source_tested and not source.fixture for source in sources):
            real_reasons.append("REAL_TREND_SOURCE_EVIDENCE_INCOMPLETE")
        if not all(
            snapshot.real_provider_tested
            and not snapshot.fixture
            and snapshot.source_kind == "official_api"
            for snapshot in snapshots
        ):
            real_reasons.append("REAL_ANALYTICS_PROVIDER_EVIDENCE_INCOMPLETE")
        external_real = any(provider.external_call for provider in providers) or any(
            source.external_call for source in sources
        ) or any(snapshot.external_call for snapshot in snapshots)
        paid_real = any(provider.paid for provider in providers)
        if external_real and (
            not bundle.safety.external_execution_enabled
            or not bundle.safety.analytics_external_execution_enabled
            or bundle.safety.global_kill_switch_engaged
        ):
            real_reasons.append("EXTERNAL_PROVIDER_SAFETY_STATE_NOT_AUTHORIZED")
        if paid_real and (
            not bundle.safety.paid_execution_enabled or bundle.safety.daily_budget_vnd <= 0
        ):
            real_reasons.append("PAID_PROVIDER_VND_BUDGET_NOT_ACTIVE")
    real_axis = FlowCAxisResult(
        status="BLOCKED" if real_gate_pending else ("PASS" if not real_reasons else "FAIL"),
        reasons=real_reasons,
    )

    production_gate_pending = [gate for gate in pending if gate in {"G-04", "G-05", "G-06"}]
    production_reasons = [f"OWNER_GATE_PENDING:{gate}" for gate in production_gate_pending]
    if production_gate_pending:
        production_status: AxisStatus = "BLOCKED"
    else:
        if real_axis.status != "PASS":
            production_reasons.append("REAL_PROVIDER_AXIS_NOT_PASS")
        if bundle.environment not in {"STAGING_PRODUCTION_LIKE", "PRODUCTION"}:
            production_reasons.append("PRODUCTION_LIKE_ENVIRONMENT_NOT_PROVEN")
        if not all(
            run.publication.production_path_tested
            and run.publication.real_publication_tested
            and run.publication.external_action
            and run.publication.status == "published"
            and run.publication.receipt_valid
            for run in ordered
        ):
            production_reasons.append("REAL_PUBLICATION_PATH_EVIDENCE_INCOMPLETE")
        if (
            not bundle.safety.external_execution_enabled
            or bundle.safety.global_kill_switch_engaged
            or not bundle.safety.production_write_performed
            or not bundle.safety.publish_performed
        ):
            production_reasons.append("PRODUCTION_PUBLICATION_SAFETY_STATE_NOT_AUTHORIZED")
        production_status = "PASS" if not production_reasons else "FAIL"
    production_axis = FlowCAxisResult(status=production_status, reasons=production_reasons)

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
            elif run.human_review_final_sha256 != run.publication.final_video_sha256:
                quality_reasons.append(f"{run.run_id}:HUMAN_REVIEW_NOT_BOUND_TO_FINAL_HASH")
        quality_status = "PASS" if not quality_reasons else "FAIL"
    quality_axis = FlowCAxisResult(status=quality_status, reasons=quality_reasons)

    axes = [mock_axis, real_axis, production_axis, quality_axis]
    if any(axis.status == "FAIL" for axis in axes):
        verdict: Verdict = "FAIL"
    elif all(axis.status == "PASS" for axis in axes):
        verdict = "PASS"
    else:
        verdict = "BLOCKED"
    return FlowCAcceptanceEvaluation(
        verdict=verdict,
        two_consecutive_runs=two_consecutive_runs,
        run_metrics=metrics,
        implemented=FlowCAxisResult(
            status="PASS",
            reasons=["FLOW_C_ACCEPTANCE_CONTRACT_AND_DETERMINISTIC_EVALUATOR_PRESENT"],
        ),
        mock_tested=mock_axis,
        real_provider_tested=real_axis,
        production_path_tested=production_axis,
        quality_accepted=quality_axis,
        pending_owner_gates=pending,
        cost_total_vnd=sum((run.cost_ledger_total_vnd for run in ordered), Decimal("0")),
        external_actions_performed=any(run.external_action_performed for run in ordered),
        publish_performed=any(run.publish_performed for run in ordered),
    )
