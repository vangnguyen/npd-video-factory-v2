"""Versioned, evidence-bound channel recommendations; no execution commands."""
import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal

from pydantic import Field, StrictInt, model_validator

from .models import StrictModel

DIMENSIONS = ('trend_family', 'hook', 'duration', 'visual_strategy', 'subtitle_style', 'voice_profile', 'publishing_window')


class LearningPolicy(StrictModel):
    schema_version: Literal['channel-learning-policy-v1'] = 'channel-learning-policy-v1'
    minimum_group_posts: StrictInt = Field(default=3, ge=3, le=50)
    minimum_control_posts: StrictInt = Field(default=3, ge=3, le=50)
    maximum_posts: StrictInt = Field(default=100, ge=6, le=100)
    minimum_score_difference: float = Field(default=10, ge=0, le=100, strict=True, allow_inf_nan=False)

    @model_validator(mode='after')
    def bounded_samples(self):
        if self.minimum_group_posts + self.minimum_control_posts > self.maximum_posts:
            raise ValueError('LEARNING_POLICY_INVALID')
        return self


class LearningCreate(StrictModel):
    publication_id: str = Field(pattern=r'^pub_[A-Za-z0-9_-]{4,60}$')
    provider_mode: Literal['official', 'fixture'] = 'official'
    policy: LearningPolicy = Field(default_factory=LearningPolicy)


class LearningObservation(StrictModel):
    snapshot_id: str
    publication_id: str
    assessment_id: str
    render_id: str
    timeline_version_id: str
    feature_context_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    remote_post_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    collected_at: datetime
    score: float = Field(ge=0, le=100, allow_inf_nan=False)
    features: dict[str, Annotated[str | None, Field(max_length=1000)]]
    winner_policy_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    assessment_basis_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')

    @model_validator(mode='after')
    def scope(self):
        if set(self.features) != set(DIMENSIONS) or self.collected_at.tzinfo is None:
            raise ValueError('LEARNING_OBSERVATION_INVALID')
        return self


class LearningGroup(StrictModel):
    value: str = Field(min_length=1, max_length=1000)
    state: Literal['recommendation_candidate', 'no_positive_association', 'insufficient_data']
    sample_count: int
    control_count: int
    median_assessment_score: float | None
    control_median_score: float | None
    score_difference: float | None
    snapshot_ids: list[str]
    control_snapshot_ids: list[str]
    recommendation: str


class LearningDimension(StrictModel):
    dimension: str
    state: Literal['recommendations_available', 'insufficient_data', 'no_positive_association']
    missing_feature_posts: int
    groups: list[LearningGroup]
    groups_truncated: bool = False


class LearningSnapshot(StrictModel):
    learning_snapshot_id: str
    schema_version: Literal['channel-learning-snapshot-v1'] = 'channel-learning-snapshot-v1'
    workspace_id: str
    project_id: str
    publication_id: str
    anchor_snapshot_id: str
    scope: dict
    policy: LearningPolicy
    observations: list[LearningObservation]
    dimensions: list[LearningDimension]
    candidate_rows_truncated: bool
    selected_posts_truncated: bool
    excluded_rows: dict[str, int]
    content_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')
    created_at: datetime
    created_by: str
    recommendation_only: Literal[True] = True
    autonomous_execution: Literal[False] = False
    production_deployed: Literal[False] = False
    limitations: list[str]


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def snapshot_content(value):
    return {key: child for key, child in value.items() if key not in ('learning_snapshot_id', 'content_sha256', 'created_at', 'created_by')}


def aggregate(observations, policy):
    """Descriptive median association, with independent distinct-post controls."""
    from statistics import median
    if len(observations) > policy.maximum_posts or len({row.remote_post_sha256 for row in observations}) != len(observations):
        raise ValueError('LEARNING_DISTINCT_POST_BOUNDARY_INVALID')
    if len({row.winner_policy_sha256 for row in observations}) > 1 or len({row.assessment_basis_sha256 for row in observations}) > 1:
        raise ValueError('LEARNING_ASSESSMENT_BASIS_MISMATCH')
    results = []
    for dimension in DIMENSIONS:
        values = sorted({row.features[dimension] for row in observations if row.features[dimension] is not None})
        groups = []
        for value in values[:20]:
            sample = [row for row in observations if row.features[dimension] == value]
            # Unknown feature values cannot be treated as a competing strategy.
            control = [row for row in observations if row.features[dimension] not in (None, value)]
            enough = len(sample) >= policy.minimum_group_posts and len(control) >= policy.minimum_control_posts
            a = median(row.score for row in sample) if enough else None
            b = median(row.score for row in control) if enough else None
            difference = round(a - b, 3) if enough else None
            state = 'insufficient_data' if not enough else 'recommendation_candidate' if difference > 0 and difference >= policy.minimum_score_difference else 'no_positive_association'
            groups.append(LearningGroup(value=value, state=state, sample_count=len(sample), control_count=len(control),
                median_assessment_score=a, control_median_score=b, score_difference=difference,
                snapshot_ids=[row.snapshot_id for row in sample], control_snapshot_ids=[row.snapshot_id for row in control],
                recommendation='Consider a reviewed experiment with this feature; association does not establish a causal improvement.'
                    if state == 'recommendation_candidate' else 'Collect more compatible posts.' if not enough
                    else 'No positive association meets the configured threshold.'))
        groups.sort(key=lambda row: (-(row.score_difference if row.score_difference is not None else -101), row.value))
        state = 'recommendations_available' if any(row.state == 'recommendation_candidate' for row in groups) else 'no_positive_association' if any(row.state != 'insufficient_data' for row in groups) else 'insufficient_data'
        results.append(LearningDimension(dimension=dimension, state=state, missing_feature_posts=sum(row.features[dimension] is None for row in observations), groups=groups, groups_truncated=len(values) > 20))
    return results
