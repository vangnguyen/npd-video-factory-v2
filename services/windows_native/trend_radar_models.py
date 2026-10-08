"""Native Trend Radar contracts; optional evidence never becomes a measured metric."""
from datetime import datetime
import math
from typing import Literal
from pydantic import Field, model_validator
from app.models import StrictModel
from app.trend_models import ProviderTrendSignal, OpportunityWeights
from app.personalized_opportunities import ChannelRankingPolicy
from app.learning_models import LearningPolicy
from .intelligence_models import Record

ID = r'^[a-f0-9]{32}$'
SHA = r'^[a-f0-9]{64}$'

class RadarRecord(Record):
    schema_version: Literal['native-trend-radar-record-v1'] = 'native-trend-radar-record-v1'
    workspace_id: str = Field(pattern=r'^wsp_[A-Za-z0-9_-]{4,64}$')
    record_type: Literal['collection','signal','cluster','assessment','handoff','learning']
    payload: dict

class SignalEvidence(ProviderTrendSignal):
    entities: list[str] = Field(default_factory=list, max_length=30)
    embedding: list[float] | None = Field(default=None, min_length=2, max_length=2048)
    embedding_model: str | None = Field(default=None, max_length=120)
    published_at: datetime | None = None

    @model_validator(mode='after')
    def evidence(self):
        if any(type(v) in (float,int) and not math.isfinite(v) for v in self.model_dump().values()):raise ValueError('Finite metrics required')
        if any(getattr(self,k) is not None and getattr(self,k)>10**18 for k in ('views','likes','comments','shares','saves','creator_count','content_count')):raise ValueError('Bounded provider counters required')
        if self.embedding is not None and any(not math.isfinite(v) or abs(v)>1000000 for v in self.embedding):raise ValueError('Finite bounded embedding required')
        if (self.embedding is None) != (self.embedding_model is None): raise ValueError('Embedding model required')
        if self.embedding is not None and not any(self.embedding): raise ValueError('Zero embedding')
        if any(not isinstance(v,str) or not 1 <= len(v.strip()) <= 120 for v in self.entities): raise ValueError('Invalid entity')
        if self.observed_at.tzinfo is None or (self.published_at and self.published_at.tzinfo is None): raise ValueError('Timezone required')
        self.entities = sorted(set(v.strip() for v in self.entities))
        return self

class CollectRequest(StrictModel):
    provider_key: str = Field(pattern=r'^[a-z0-9][a-z0-9-]{1,119}$')
    query: str | None = Field(default=None, max_length=240)
    country: str | None = Field(default=None, pattern=r'^[A-Z]{2}$')
    locale: str | None = Field(default=None, pattern=r'^[a-z]{2}(?:-[A-Z]{2})?$')
    language: str | None = Field(default=None, pattern=r'^[a-z]{2,3}$')
    limit: int = Field(default=100, ge=1, le=200, strict=True)
    fixture_acknowledged: bool = Field(default=False, strict=True)
    refresh: bool = Field(default=False, strict=True)
    request_key: str = Field(min_length=16, max_length=100)

class ClusterPolicy(StrictModel):
    schema_version: Literal['native-trend-clustering-v2'] = 'native-trend-clustering-v2'
    similarity_threshold: float = Field(default=.34, ge=.1, le=1, allow_inf_nan=False)
    maximum_gap_days: float = Field(default=7, ge=.01, le=30, allow_inf_nan=False)
    keyword_weight: float = Field(default=.4, ge=0, le=1)
    hashtag_weight: float = Field(default=.15, ge=0, le=1)
    entity_weight: float = Field(default=.2, ge=0, le=1)
    semantic_weight: float = Field(default=.25, ge=0, le=1)
    temporal_bonus: float = Field(default=.05, ge=0, le=.1)
    cross_platform_bonus: float = Field(default=.05, ge=0, le=.1)
    @model_validator(mode='after')
    def weights(self):
        if any(type(v) in (int,float) and not math.isfinite(v) for v in self.model_dump().values()):raise ValueError('Finite clustering weights required')
        if self.keyword_weight+self.hashtag_weight+self.entity_weight+self.semantic_weight <= 0: raise ValueError('Positive similarity weight required')
        return self

class RefreshRequest(StrictModel):
    channel_profile_ref: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    business_objective: str = Field(default='awareness', min_length=1, max_length=80)
    platform: Literal['youtube','tiktok','instagram_reels','facebook'] = 'youtube'
    weights: OpportunityWeights = Field(default_factory=OpportunityWeights)
    clustering: ClusterPolicy = Field(default_factory=ClusterPolicy)
    lookback_days: int = Field(default=30, ge=1, le=365, strict=True)
    learning_snapshot_id: str | None = Field(default=None, pattern=ID)
    ranking_policy: ChannelRankingPolicy = Field(default_factory=ChannelRankingPolicy)
    request_key: str = Field(min_length=16, max_length=100)

class HandoffRequest(StrictModel):
    assessment_id: str = Field(pattern=ID)
    expected_sha256: str = Field(pattern=SHA)
    acknowledged: bool = Field(strict=True)
    request_key: str = Field(min_length=16, max_length=100)
    @model_validator(mode='after')
    def approved(self):
        if self.acknowledged is not True:raise ValueError('Explicit acknowledgment required')
        return self

class LearningRequest(StrictModel):
    channel_profile_ref: str = Field(pattern=r'^[a-z][a-z0-9-]{2,60}@[1-9][0-9]*$')
    platform: Literal['youtube','tiktok','instagram_reels','facebook'] = 'youtube'
    provider_mode: Literal['fixture','official'] = 'official'
    fixture_acknowledged: bool = Field(default=False, strict=True)
    policy: LearningPolicy = Field(default_factory=LearningPolicy)
    request_key: str = Field(min_length=16, max_length=100)
