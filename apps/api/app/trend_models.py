from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import Field, HttpUrl, model_validator

from .models import NicheName, StrictModel


TrendLifecycle = Literal[
    "discovered",
    "rising",
    "breakout",
    "mainstream",
    "saturated",
    "declining",
    "expired",
]
ProviderStatus = Literal["healthy", "degraded", "unavailable", "not_configured"]


class TrendSourceRead(StrictModel):
    source_id: str
    workspace_id: str | None
    provider_key: str
    display_name: str
    source_type: str
    status: ProviderStatus
    authorized_access: bool
    config_ref: str | None
    capabilities: dict[str, Any]
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrendCollectionRequest(StrictModel):
    provider_key: str = Field(default="fixture-trends", pattern=r"^[a-z0-9][a-z0-9-]{1,119}$")
    query: str | None = Field(default=None, max_length=240)
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")
    limit: int = Field(default=100, ge=1, le=500)


class ProviderTrendSignal(StrictModel):
    source: str = Field(min_length=1, max_length=80)
    source_reference: HttpUrl
    observed_at: datetime
    country: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    locale: str | None = Field(default=None, max_length=20)
    language: str | None = Field(default=None, max_length=12)
    keyword: str | None = Field(default=None, max_length=240)
    topic: str | None = Field(default=None, max_length=300)
    hashtags: list[str] = Field(default_factory=list, max_length=30)
    media_type: str | None = Field(default=None, max_length=80)
    format: str | None = Field(default=None, max_length=80)
    duration_seconds: float | None = Field(default=None, ge=0, le=86_400)
    views: int | None = Field(default=None, ge=0)
    likes: int | None = Field(default=None, ge=0)
    comments: int | None = Field(default=None, ge=0)
    shares: int | None = Field(default=None, ge=0)
    saves: int | None = Field(default=None, ge=0)
    engagement: float | None = Field(default=None, ge=0)
    creator_count: int | None = Field(default=None, ge=0)
    content_count: int | None = Field(default=None, ge=0)
    velocity: float | None = Field(default=None, ge=-100, le=100)
    acceleration: float | None = Field(default=None, ge=-100, le=100)
    evidence_summary: str = Field(min_length=1, max_length=1200)
    evidence_confidence: float = Field(default=0.8, ge=0, le=1)
    freshness: str = Field(default="current_snapshot", min_length=1, max_length=40)

    @model_validator(mode="after")
    def require_topic_or_keyword(self) -> "ProviderTrendSignal":
        if not self.topic and not self.keyword:
            raise ValueError("trend signal requires topic or keyword")
        self.hashtags = sorted({item.strip().casefold() for item in self.hashtags if item.strip()})
        return self


class TrendSnapshotRead(StrictModel):
    snapshot_id: str
    workspace_id: str
    source_id: str
    provider_key: str
    query: dict[str, Any]
    signal_count: int
    new_signal_count: int
    collected_at: datetime
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrendSignalRead(StrictModel):
    signal_id: str
    workspace_id: str
    snapshot_id: str
    source_id: str
    source: str
    source_reference: str
    observed_at: datetime
    country: str | None
    locale: str | None
    language: str | None
    keyword: str | None
    topic: str | None
    hashtags: list[str]
    media_type: str | None
    format: str | None
    duration_seconds: float | None
    views: int | None
    likes: int | None
    comments: int | None
    shares: int | None
    saves: int | None
    engagement: float | None
    creator_count: int | None
    content_count: int | None
    velocity: float | None
    acceleration: float | None
    raw_signal_hash: str
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class TrendEvidenceRead(StrictModel):
    evidence_id: str
    signal_id: str
    claim: str
    summary: str
    source_reference: str
    retrieved_at: datetime
    confidence: float
    freshness: str


class TrendCollectionResult(StrictModel):
    snapshot: TrendSnapshotRead
    signals: list[TrendSignalRead]
    evidence: list[TrendEvidenceRead]


class OpportunityWeights(StrictModel):
    velocity: float = Field(default=1.3, ge=0, le=10)
    acceleration: float = Field(default=1.2, ge=0, le=10)
    cross_platform_spread: float = Field(default=1.2, ge=0, le=10)
    engagement_quality: float = Field(default=1.0, ge=0, le=10)
    novelty: float = Field(default=1.0, ge=0, le=10)
    channel_fit: float = Field(default=1.0, ge=0, le=10)
    format_fit: float = Field(default=0.9, ge=0, le=10)
    monetization_fit: float = Field(default=0.8, ge=0, le=10)
    saturation: float = Field(default=1.1, ge=0, le=10)
    competition: float = Field(default=0.9, ge=0, le=10)
    rights_risk: float = Field(default=1.3, ge=0, le=10)
    policy_risk: float = Field(default=1.2, ge=0, le=10)


class TrendContext(StrictModel):
    channel: str = Field(default="short-video", min_length=1, max_length=80)
    niche: NicheName = NicheName.CUSTOM
    business_objective: str = Field(default="awareness", min_length=1, max_length=80)
    weights: OpportunityWeights = Field(default_factory=OpportunityWeights)


class TrendClusterRefreshRequest(TrendContext):
    as_of: datetime | None = None
    similarity_threshold: float = Field(default=0.34, ge=0.1, le=1)


class TrendScoreRead(StrictModel):
    trend_score_id: str
    cluster_id: str
    channel: str
    niche: str
    business_objective: str
    total_score: float
    components: dict[str, float]
    weights: dict[str, float]
    estimated: Literal[True] = True
    version: int
    created_at: datetime
    updated_at: datetime


class TrendClusterRead(StrictModel):
    cluster_id: str
    workspace_id: str
    canonical_key: str
    topic: str
    summary: str
    lifecycle: TrendLifecycle
    first_observed_at: datetime
    last_observed_at: datetime
    signal_count: int
    platforms: list[str]
    countries: list[str]
    languages: list[str]
    formats: list[str]
    keywords: list[str]
    hashtags: list[str]
    score: TrendScoreRead | None
    source_references: list[str]
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class IdeaGenerateRequest(TrendContext):
    audience: str = Field(default="general audience", min_length=1, max_length=500)
    cta: str = Field(default="Learn more", min_length=1, max_length=500)
    budget_vnd: int | None = Field(default=None, ge=0)
    count: int = Field(default=3, ge=1, le=6)


class IdeaScoreRead(StrictModel):
    idea_score_id: str
    idea_id: str
    total_score: float
    components: dict[str, float]
    estimated: Literal[True] = True
    rationale: list[str]
    version: int
    created_at: datetime
    updated_at: datetime


class IdeaCandidateRead(StrictModel):
    idea_id: str
    workspace_id: str
    cluster_id: str
    project_id: str | None
    variant_key: str
    channel: str
    niche: str
    business_objective: str
    title: str
    angle: str
    hook_concept: str
    format: str
    recommended_duration_seconds: int
    visual_concept: str
    audience: str
    cta_concept: str
    trend_references: list[str]
    originality_notes: str
    brief: dict[str, Any]
    status: Literal["draft", "selected"]
    score: IdeaScoreRead
    version: int
    provenance: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class ContentQueueRefreshRequest(IdeaGenerateRequest):
    top_n: int = Field(default=10, ge=1, le=50)
    ideas_per_cluster: int = Field(default=3, ge=1, le=6)


class ContentQueueItemRead(StrictModel):
    queue_item_id: str
    queue_run_id: str
    workspace_id: str
    opportunity_id: str
    cluster_id: str
    idea_id: str
    channel: str
    rank: int
    score: float
    state: Literal["proposed"]
    evidence_summary: list[str]
    generated_at: datetime
    idea: IdeaCandidateRead
    version: int
    provenance: dict[str, Any]


class IdeaProjectRead(StrictModel):
    idea_id: str
    project_id: str
    project_version_id: str
    status: Literal["selected"]
