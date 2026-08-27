from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from .analytics_models import (
    AnalyticsSyncRequest,
    METRIC_NAMES,
    NormalizedMetrics,
    VideoFeatureMetadata,
    WinnerAssessmentRead,
    WinnerFactorRead,
)


ANALYTICS_ALGORITHM_VERSION = "winner-assessment-v2-10.1"
METRIC_UNITS: dict[str, str] = {
    "views": "count",
    "impressions": "count",
    "reach": "count",
    "watch_time": "seconds",
    "average_view_duration": "seconds",
    "completion_rate": "ratio",
    "likes": "count",
    "comments": "count",
    "shares": "count",
    "saves": "count",
    "followers_gained": "count",
    "clicks": "count",
    "ctr": "ratio",
    "revenue": "VND",
    "rpm": "VND_per_1000_views",
    "observation_window_hours": "hours",
}


@dataclass(frozen=True)
class AssessmentDraft:
    state: str
    score: float | None
    data_coverage: float
    factors: list[WinnerFactorRead]
    evidence: list[str]
    recommendations: list[str]


@dataclass(frozen=True)
class InsightDraft:
    insight_type: str
    statement: str
    recommendation: str
    confidence: float
    evidence_refs: list[str]


def hash_idempotency_key(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def analytics_request_fingerprint(payload: AnalyticsSyncRequest) -> str:
    encoded = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def metric_points(metrics: NormalizedMetrics) -> list[dict[str, Any]]:
    values = metrics.model_dump()
    return [
        {
            "metric": name,
            "value": values[name],
            "unit": METRIC_UNITS[name],
            "supported": values[name] is not None,
        }
        for name in METRIC_NAMES
    ]


def assess_winner(
    metrics: NormalizedMetrics,
    *,
    video_duration_seconds: float | None,
    production_cost_vnd: float | None,
) -> AssessmentDraft:
    values = metrics.model_dump()
    views = _number(values.get("views"))
    hours = _number(values.get("observation_window_hours"))
    average_duration = _number(values.get("average_view_duration"))
    completion_rate = _number(values.get("completion_rate"))
    ctr = _number(values.get("ctr"))
    revenue = _number(values.get("revenue"))
    rpm = _number(values.get("rpm"))

    interactions = _sum_if_any(
        values.get("likes"), values.get("comments"), values.get("shares"), values.get("saves")
    )
    factors = [
        _factor(
            "view_velocity",
            _ratio_score((views / hours) if views is not None and hours and hours > 0 else None, 1_000),
            0.18,
            views=views,
            observation_window_hours=hours,
            views_per_hour=round(views / hours, 3) if views is not None and hours and hours > 0 else None,
        ),
        _factor(
            "retention",
            _ratio_score(
                (average_duration / video_duration_seconds)
                if average_duration is not None and video_duration_seconds and video_duration_seconds > 0
                else None,
                0.72,
            ),
            0.16,
            average_view_duration=average_duration,
            duration_seconds=video_duration_seconds,
        ),
        _factor(
            "completion",
            _ratio_score(completion_rate, 0.75),
            0.16,
            completion_rate=completion_rate,
        ),
        _factor(
            "engagement",
            _ratio_score(
                interactions / views if interactions is not None and views and views > 0 else None,
                0.08,
            ),
            0.13,
            interactions=interactions,
            views=views,
        ),
        _factor(
            "shares",
            _ratio_score(_safe_rate(values.get("shares"), views), 0.02),
            0.08,
            shares=_number(values.get("shares")),
            views=views,
        ),
        _factor(
            "saves",
            _ratio_score(_safe_rate(values.get("saves"), views), 0.015),
            0.07,
            saves=_number(values.get("saves")),
            views=views,
        ),
        _factor("ctr", _ratio_score(ctr, 0.05), 0.08, ctr=ctr),
        _factor(
            "follower_conversion",
            _ratio_score(_safe_rate(values.get("followers_gained"), views), 0.02),
            0.06,
            followers_gained=_number(values.get("followers_gained")),
            views=views,
        ),
        _factor(
            "revenue_efficiency",
            _ratio_score(
                rpm if rpm is not None else (revenue / views * 1_000 if revenue is not None and views else None),
                100_000,
            ),
            0.05,
            revenue_vnd=revenue,
            rpm_vnd=rpm,
        ),
        _factor(
            "production_cost_efficiency",
            _ratio_score(
                revenue / production_cost_vnd
                if revenue is not None and production_cost_vnd and production_cost_vnd > 0
                else None,
                3,
            ),
            0.03,
            revenue_vnd=revenue,
            production_cost_vnd=production_cost_vnd,
        ),
    ]
    available_weight = sum(item.weight for item in factors if item.score is not None)
    total_weight = sum(item.weight for item in factors)
    coverage = round(available_weight / total_weight, 6) if total_weight else 0
    sufficient = bool(
        views is not None
        and views >= 500
        and hours is not None
        and hours >= 6
        and coverage >= 0.55
        and (average_duration is not None or completion_rate is not None)
    )
    evidence = [
        f"Metric coverage is {coverage * 100:.1f}% of the explainable score weight.",
        (
            f"Observation covers {hours:.1f} hours and {views:.0f} views."
            if hours is not None and views is not None
            else "Observation window or view volume is unavailable."
        ),
        "Every available factor is normalized against a versioned V2-10 reference threshold.",
    ]
    if not sufficient:
        return AssessmentDraft(
            state="insufficient_data",
            score=None,
            data_coverage=coverage,
            factors=factors,
            evidence=[*evidence, "At least 6 hours, 500 views and retention/completion evidence are required."],
            recommendations=[
                "Collect another historical snapshot before classifying performance.",
                "Do not delete content or change paid-media budget from incomplete evidence.",
            ],
        )
    score = round(
        sum((item.score or 0) * item.weight for item in factors if item.score is not None)
        / available_weight,
        3,
    )
    if score >= 72:
        state = "winner_candidate"
        recommendations = [
            "Owner should review this video as a candidate for a controlled creative follow-up.",
            "Reuse the strongest hook and format only as a new test; do not auto-scale paid media.",
        ]
    elif score <= 38:
        state = "underperforming"
        recommendations = [
            "Test a clearer first-two-second hook and a shorter edit in a new version.",
            "Keep the existing post; no automatic deletion or budget mutation is allowed.",
        ]
    else:
        state = "normal"
        recommendations = [
            "Continue collecting snapshots and test one controlled creative variable at a time.",
            "Treat the score as decision support, not an execution command.",
        ]
    return AssessmentDraft(
        state=state,
        score=score,
        data_coverage=coverage,
        factors=factors,
        evidence=evidence,
        recommendations=recommendations,
    )


def learning_insights(
    *,
    assessment: AssessmentDraft,
    features: VideoFeatureMetadata,
    snapshot_ref: str,
) -> list[InsightDraft]:
    base_confidence = min(0.95, max(0.2, assessment.data_coverage))
    evidence = [snapshot_ref, ANALYTICS_ALGORITHM_VERSION]
    if assessment.state == "insufficient_data":
        return [
            InsightDraft(
                insight_type="data_collection",
                statement="Current evidence is not sufficient to infer a reusable content pattern.",
                recommendation="Wait for a later historical snapshot and compare the same post over time.",
                confidence=base_confidence,
                evidence_refs=evidence,
            )
        ]

    direction = "positive" if assessment.state == "winner_candidate" else "weak" if assessment.state == "underperforming" else "neutral"
    drafts: list[InsightDraft] = []
    if features.trend_cluster_id:
        drafts.append(
            InsightDraft(
                insight_type="trend_family",
                statement=f"The linked trend family has {direction} observed performance evidence.",
                recommendation="Use this evidence in the next human-reviewed Trend Radar comparison.",
                confidence=base_confidence,
                evidence_refs=[*evidence, features.trend_cluster_id],
            )
        )
    if features.hook_type:
        drafts.append(
            InsightDraft(
                insight_type="hook",
                statement=f"Hook pattern '{features.hook_type}' has {direction} observed performance evidence.",
                recommendation="Draft one controlled hook variant and compare it without auto-publishing.",
                confidence=base_confidence,
                evidence_refs=[*evidence, features.idea_id or "no-linked-idea"],
            )
        )
    if features.duration_seconds is not None:
        drafts.append(
            InsightDraft(
                insight_type="duration",
                statement=f"A {features.duration_seconds:.1f}-second edit has {direction} observed performance evidence.",
                recommendation="Keep duration as a measurable variable in the next owner-reviewed test.",
                confidence=base_confidence,
                evidence_refs=evidence,
            )
        )
    if features.visual_strategy:
        drafts.append(
            InsightDraft(
                insight_type="visual_strategy",
                statement=f"Visual strategy '{features.visual_strategy}' has {direction} observed performance evidence.",
                recommendation="Return this evidence to Media Planner as a recommendation only.",
                confidence=base_confidence,
                evidence_refs=evidence,
            )
        )
    if features.subtitle_template:
        drafts.append(
            InsightDraft(
                insight_type="subtitle_style",
                statement=f"Subtitle style '{features.subtitle_template}' is linked to this performance observation.",
                recommendation="Compare the same style against one controlled alternative before standardizing it.",
                confidence=base_confidence * 0.9,
                evidence_refs=evidence,
            )
        )
    if features.voice_profile:
        drafts.append(
            InsightDraft(
                insight_type="voice_profile",
                statement=f"Voice profile '{features.voice_profile}' is linked to this performance observation.",
                recommendation="Require human Vietnamese voice acceptance before treating this as a reusable voice pattern.",
                confidence=base_confidence * 0.8,
                evidence_refs=evidence,
            )
        )
    if features.publishing_time:
        drafts.append(
            InsightDraft(
                insight_type="publishing_window",
                statement=f"Publishing hour {features.publishing_time.hour:02d}:00 is linked to this observation.",
                recommendation="Compare at least three posts before recommending a channel publishing window.",
                confidence=min(base_confidence, 0.55),
                evidence_refs=evidence,
            )
        )
    return drafts or [
        InsightDraft(
            insight_type="data_collection",
            statement="Performance is classified, but reusable video features are incomplete.",
            recommendation="Capture trend, idea, timeline and production metadata before the next sync.",
            confidence=base_confidence,
            evidence_refs=evidence,
        )
    ]


def assessment_model(
    *,
    assessment_id: str,
    snapshot_id: str,
    project_id: str,
    publication_id: str,
    draft: AssessmentDraft,
    created_at,
) -> WinnerAssessmentRead:
    return WinnerAssessmentRead(
        assessment_id=assessment_id,
        snapshot_id=snapshot_id,
        project_id=project_id,
        publication_id=publication_id,
        state=draft.state,  # type: ignore[arg-type]
        score=draft.score,
        data_coverage=draft.data_coverage,
        factors=draft.factors,
        evidence=draft.evidence,
        recommendations=draft.recommendations,
        algorithm_version=ANALYTICS_ALGORITHM_VERSION,
        automatic_action=False,
        paid_media_mutation=False,
        content_deletion=False,
        created_at=created_at,
    )


def _factor(factor: str, score: float | None, weight: float, **evidence: Any) -> WinnerFactorRead:
    return WinnerFactorRead(
        factor=factor,  # type: ignore[arg-type]
        score=round(score, 3) if score is not None else None,
        weight=weight,
        evidence=evidence,
    )


def _number(value: Any) -> float | None:
    return float(value) if value is not None else None


def _safe_rate(numerator: Any, denominator: float | None) -> float | None:
    value = _number(numerator)
    if value is None or denominator is None or denominator <= 0:
        return None
    return value / denominator


def _sum_if_any(*values: Any) -> float | None:
    numbers = [_number(value) for value in values]
    present = [value for value in numbers if value is not None]
    return sum(present) if present else None


def _ratio_score(value: float | None, reference: float) -> float | None:
    if value is None:
        return None
    return max(0, min(100, value / reference * 100))
