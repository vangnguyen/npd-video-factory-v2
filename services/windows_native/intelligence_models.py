"""Business-neutral, versioned Content Intelligence contracts."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def stamp():
    return datetime.now(timezone.utc)


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    id: str = Field(default_factory=lambda: uuid4().hex, pattern=r"^[0-9a-f]{32}$")
    created_at: datetime = Field(default_factory=stamp)
    updated_at: datetime = Field(default_factory=stamp)
    version: int = Field(default=1, ge=1, strict=True)
    provenance: dict = Field(min_length=1)

    @field_validator("created_at", "updated_at")
    @classmethod
    def aware(cls, value):
        if value.tzinfo is None:
            raise ValueError("Timezone required")
        return value.astimezone(timezone.utc)


class ResearchSource(Record):
    source_type: Literal["web", "provided_document", "test_fixture"]
    reference: str = Field(min_length=1, max_length=2000)
    title: str = Field(min_length=1, max_length=500)
    timestamp: datetime | None = None
    retrieved_at: datetime
    raw_provenance: dict = Field(min_length=1)
    text: str = Field(min_length=1, max_length=100000)
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    publication_date_known: bool = False

    @field_validator("timestamp", "retrieved_at")
    @classmethod
    def dates(cls, value):
        return Record.aware(value) if value is not None else value


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    quote: str = Field(min_length=1, max_length=3000)


class ResearchFinding(Record):
    run_id: str
    kind: Literal["SOURCED_FACT", "MODEL_INFERENCE", "UNCERTAIN"]
    claim: str = Field(min_length=1, max_length=3000)
    source_references: list[Citation] = Field(max_length=10)
    relevance: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    timestamp_relevance: str = Field(min_length=1, max_length=500)
    grounding: Literal["SOURCE_REPORTED", "INFERENCE", "UNRESOLVED"]

    @model_validator(mode="after")
    def grounded(self):
        expected = {"SOURCED_FACT": "SOURCE_REPORTED", "MODEL_INFERENCE": "INFERENCE", "UNCERTAIN": "UNRESOLVED"}
        if self.grounding != expected[self.kind]:
            raise ValueError("Grounding must match finding type")
        if self.kind == "SOURCED_FACT" and (not self.source_references or self.claim not in [c.quote for c in self.source_references]):
            raise ValueError("Sourced claims must be an exact attributed quotation; never model-verified truth")
        return self


class TrendSignal(Record):
    run_id: str
    topic: str = Field(min_length=1, max_length=300)
    related_project: str | None = None
    entity: str | None = None
    signal_type: Literal["source_update", "research_request"]
    source_id: str
    finding_ids: list[str]
    observed_at: datetime
    strength: float = Field(ge=0, le=1)
    freshness: str

    @field_validator("observed_at")
    @classmethod
    def date(cls, value):
        return Record.aware(value)


QueueStatus = Literal["NEW", "REVIEWING", "APPROVED", "REJECTED", "IN_PRODUCTION", "PRODUCED"]


class Opportunity(Record):
    run_id: str
    topic: str = Field(min_length=1, max_length=300)
    related_project: str | None = None
    target_audience: str
    reason_now: str
    supporting_signals: list[str]
    proposed_angle: str
    research_freshness: str
    opportunity_score: float = Field(default=0, ge=0, le=100)
    suggested_hook: str = ""
    candidate_format: str = ""
    status: QueueStatus = "NEW"
    selected_idea_id: str | None = None
    brief_id: str | None = None
    production_project_id: str | None = None


class ContentIdea(Record):
    run_id: str
    opportunity_id: str
    generation: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    hook: str = Field(min_length=1, max_length=500)
    angle: str = Field(min_length=1, max_length=1000)
    target_audience: str = Field(min_length=1, max_length=500)
    format: str = Field(min_length=1, max_length=150)
    estimated_duration: int = Field(ge=15, le=180)
    cta: str = Field(min_length=1, max_length=500)
    related_project: str | None
    supporting_research: list[str] = Field(min_length=1, max_length=30)
    evidence_references: list[str] = Field(min_length=1, max_length=30)
    key_points: list[str] = Field(min_length=1, max_length=8)
    rationale: str = Field(min_length=1, max_length=1500)
    status: Literal["CANDIDATE", "SELECTED", "REJECTED", "SUPERSEDED"] = "CANDIDATE"


class ContentBrief(Record):
    run_id: str
    idea_id: str
    idea_version: int
    objective: str = Field(min_length=1, max_length=1000)
    audience: str = Field(min_length=1, max_length=500)
    key_facts: list[str] = Field(max_length=30)
    angle: str = Field(min_length=1, max_length=1000)
    hook: str = Field(min_length=1, max_length=500)
    talking_points: list[str] = Field(min_length=1, max_length=10)
    cta: str = Field(min_length=1, max_length=500)
    source_references: list[str] = Field(min_length=1, max_length=30)
    constraints: list[str] = Field(min_length=1, max_length=20)
    status: Literal["DRAFT", "APPROVED", "SUPERSEDED"] = "DRAFT"
    approval: dict | None = None


DIMENSIONS = ("relevance", "freshness", "audience_fit", "product_fit", "hook_strength", "evidence_strength",
              "production_feasibility", "lead_potential", "novelty", "risk")


class IdeaScore(Record):
    idea_id: str
    idea_version: int
    scoring_type: Literal["HEURISTIC_SCORING"] = "HEURISTIC_SCORING"
    components: dict[str, float]
    weights: dict[str, float]
    final_score: float = Field(ge=0, le=100)
    rationale: dict[str, str]
    config_sha256: str
    as_of: datetime

    @model_validator(mode="after")
    def dimensions(self):
        if any(set(v) != set(DIMENSIONS) for v in (self.components, self.weights, self.rationale)):
            raise ValueError("All ten scoring dimensions required")
        if any(not 0 <= v <= 100 for v in self.components.values()) or any(not 0 <= v <= 10 for v in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError("Invalid score or weights")
        return self

    @field_validator("as_of")
    @classmethod
    def date(cls, value):
        return Record.aware(value)


class ResearchRun(Record):
    query: str = Field(min_length=1, max_length=1000)
    context: dict
    provider: str
    model: str | None = None
    status: Literal["NEW", "RESEARCHING", "FINDINGS", "IDEAS", "FAILED"] = "NEW"
    source_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    signal_ids: list[str] = Field(default_factory=list)
    opportunity_id: str | None = None
    idea_ids: list[str] = Field(default_factory=list)
    generation: int = 0
    error: dict | None = None
    provider_metadata: dict = Field(default_factory=dict)


MODELS = {c.__name__: c for c in (ResearchSource, ResearchFinding, TrendSignal, Opportunity, ContentIdea, ContentBrief, IdeaScore, ResearchRun)}
