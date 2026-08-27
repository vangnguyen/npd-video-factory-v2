from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import StrictModel


AnalyticsPlatform = Literal["youtube", "tiktok", "instagram_reels", "facebook"]
AnalyticsProviderMode = Literal["fixture", "official"]
AnalyticsSyncTrigger = Literal["initial", "manual_refresh", "scheduled_refresh"]
AnalyticsSyncStatus = Literal[
    "scheduled",
    "queued",
    "running",
    "retry_scheduled",
    "succeeded",
    "not_configured",
    "failed",
    "cancelled",
]
WinnerState = Literal["winner_candidate", "normal", "underperforming", "insufficient_data"]
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


METRIC_NAMES: tuple[str, ...] = (
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


class AnalyticsSyncRequest(StrictModel):
    publication_id: str = Field(pattern=r"^pub_[A-Za-z0-9_-]{4,60}$")
    provider_mode: AnalyticsProviderMode = "fixture"
    trigger: AnalyticsSyncTrigger = "initial"
    fixture_profile: Literal[
        "winner_candidate", "normal", "underperforming", "insufficient_data", "rate_limited"
    ] = "winner_candidate"
    scheduled_for: datetime | None = None
    actor_ref: str = Field(default="studio-user", min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_schedule(self) -> "AnalyticsSyncRequest":
        if self.scheduled_for is not None and self.scheduled_for.tzinfo is None:
            raise ValueError("scheduled_for must include a timezone")
        if self.trigger == "scheduled_refresh" and self.scheduled_for is None:
            raise ValueError("scheduled_refresh requires scheduled_for")
        if self.provider_mode == "official" and self.fixture_profile != "winner_candidate":
            raise ValueError("fixture_profile applies only to the fixture provider")
        return self


class AnalyticsProviderStateRead(StrictModel):
    platform: AnalyticsPlatform
    provider_key: str
    mode: AnalyticsProviderMode
    adapter_state: Literal["mock", "not_configured", "contract_only", "ready"]
    credential_status: Literal["not_required", "not_configured", "configured"]
    supports_sync: bool
    supports_historical_snapshots: bool = True
    supports_rate_limit_backoff: bool = True
    external_calls_enabled: Literal[False] = False
    real_provider_tested: Literal[False] = False
    production_deployed: Literal[False] = False


class NormalizedMetrics(StrictModel):
    views: float | None = Field(default=None, ge=0)
    impressions: float | None = Field(default=None, ge=0)
    reach: float | None = Field(default=None, ge=0)
    watch_time: float | None = Field(default=None, ge=0, description="Seconds")
    average_view_duration: float | None = Field(default=None, ge=0, description="Seconds")
    completion_rate: float | None = Field(default=None, ge=0, le=1)
    likes: float | None = Field(default=None, ge=0)
    comments: float | None = Field(default=None, ge=0)
    shares: float | None = Field(default=None, ge=0)
    saves: float | None = Field(default=None, ge=0)
    followers_gained: float | None = Field(default=None, ge=0)
    clicks: float | None = Field(default=None, ge=0)
    ctr: float | None = Field(default=None, ge=0, le=1)
    revenue: float | None = Field(default=None, ge=0, description="VND")
    rpm: float | None = Field(default=None, ge=0, description="VND per 1,000 views")
    observation_window_hours: float | None = Field(default=None, ge=0)


class AnalyticsMetricPointRead(StrictModel):
    point_id: str
    metric: MetricName
    value: float | None
    unit: str
    supported: bool


class AnalyticsMetricSnapshotRead(StrictModel):
    snapshot_id: str
    sync_id: str
    workspace_id: str
    project_id: str
    publication_id: str
    platform: AnalyticsPlatform
    provider_key: str
    source: str
    source_kind: Literal["fixture", "official_api"]
    collected_at: datetime
    metrics: NormalizedMetrics
    points: list[AnalyticsMetricPointRead]
    mock: bool
    external_call: Literal[False] = False
    created_at: datetime


class VideoFeatureMetadata(StrictModel):
    feature_snapshot_id: str | None = None
    project_id: str
    publication_id: str
    trend_cluster_id: str | None = None
    idea_id: str | None = None
    hook_type: str | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    scene_count: int | None = Field(default=None, ge=0)
    subtitle_template: str | None = None
    voice_profile: str | None = None
    music_profile: str | None = None
    visual_strategy: str | None = None
    niche: str | None = None
    topic: str | None = None
    cta: str | None = None
    publishing_time: datetime | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    captured_at: datetime | None = None


class WinnerFactorRead(StrictModel):
    factor: Literal[
        "view_velocity",
        "retention",
        "completion",
        "engagement",
        "shares",
        "saves",
        "ctr",
        "follower_conversion",
        "revenue_efficiency",
        "production_cost_efficiency",
    ]
    score: float | None = Field(default=None, ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    evidence: dict[str, Any] = Field(default_factory=dict)


class WinnerAssessmentRead(StrictModel):
    assessment_id: str
    snapshot_id: str
    project_id: str
    publication_id: str
    state: WinnerState
    score: float | None = Field(default=None, ge=0, le=100)
    data_coverage: float = Field(ge=0, le=1)
    factors: list[WinnerFactorRead]
    evidence: list[str]
    recommendations: list[str]
    algorithm_version: str
    automatic_action: Literal[False] = False
    paid_media_mutation: Literal[False] = False
    content_deletion: Literal[False] = False
    created_at: datetime


class LearningInsightRead(StrictModel):
    insight_id: str
    project_id: str
    publication_id: str
    snapshot_id: str
    assessment_id: str
    trend_cluster_id: str | None
    idea_id: str | None
    insight_type: Literal[
        "trend_family",
        "hook",
        "duration",
        "visual_strategy",
        "subtitle_style",
        "voice_profile",
        "publishing_window",
        "data_collection",
    ]
    statement: str
    recommendation: str
    confidence: float = Field(ge=0, le=1)
    evidence_refs: list[str]
    applied: Literal[False] = False
    autonomous_execution: Literal[False] = False
    created_at: datetime


class AnalyticsSyncRead(StrictModel):
    sync_id: str
    workspace_id: str
    project_id: str
    publication_id: str
    platform: AnalyticsPlatform
    provider_key: str
    provider_mode: AnalyticsProviderMode
    trigger: AnalyticsSyncTrigger
    fixture_profile: str | None
    status: AnalyticsSyncStatus
    request_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    attempt_count: int = Field(ge=0)
    max_attempts: int = Field(ge=1)
    scheduled_for: datetime | None
    next_retry_at: datetime | None
    snapshot_id: str | None
    failure_code: str | None
    failure_reason: str | None
    mock: bool
    external_call: Literal[False] = False
    actor_ref: str
    created_at: datetime
    updated_at: datetime


class AnalyticsEventRead(StrictModel):
    event_id: str
    sync_id: str
    project_id: str
    event_type: str
    actor_ref: str
    payload: dict[str, Any]
    created_at: datetime


class AnalyticsReportRead(StrictModel):
    project_id: str
    status: Literal["not_started", "collecting", "ready", "not_configured", "failed"]
    latest_sync: AnalyticsSyncRead | None
    latest_snapshot: AnalyticsMetricSnapshotRead | None
    latest_assessment: WinnerAssessmentRead | None
    video_features: VideoFeatureMetadata | None
    learning_insights: list[LearningInsightRead]
    history_count: int = Field(ge=0)
    recommendation_only: Literal[True] = True
    external_execution_enabled: Literal[False] = False
