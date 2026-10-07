"""Bounded reversible planning estimates from explicit channel-history feedback."""
import math
from typing import Literal
from pydantic import Field
from .models import StrictModel

VERSION = 'personalized-opportunity-estimate-v1'


class ChannelRankingPolicy(StrictModel):
    schema_version: Literal['channel-ranking-policy-v1'] = 'channel-ranking-policy-v1'
    history_weight: float = Field(default=.25, ge=0, le=.5, strict=True, allow_inf_nan=False)
    maximum_adjustment_points: float = Field(default=15, ge=0, le=25, strict=True, allow_inf_nan=False)


def rank_estimate(base_score, cluster_id, feedback, policy=None):
    if type(base_score) not in (int, float) or not math.isfinite(base_score) or not 0 <= base_score <= 100:
        raise ValueError('PERSONALIZED_BASE_SCORE_INVALID')
    policy = policy or ChannelRankingPolicy()
    family = next((item for item in (feedback or {}).get('recommendations', []) if item.get('dimension') == 'trend_family'), None)
    group = next((item for item in (family or {}).get('groups', []) if item.get('value') == cluster_id), None)
    difference = None
    if group and group.get('state') != 'insufficient_data' and type(group.get('score_difference')) in (int, float):
        difference = group['score_difference']
        if not math.isfinite(difference) or not -100 <= difference <= 100: raise ValueError('PERSONALIZED_HISTORY_INVALID')
    adjustment = None if difference is None else max(-policy.maximum_adjustment_points,
        min(policy.maximum_adjustment_points, policy.history_weight * difference))
    return {'algorithm_version': VERSION, 'estimated': True, 'recommendation_only': True, 'autonomous_execution': False,
        'base_planning_score': round(base_score, 3), 'channel_score_difference': difference,
        'history_adjustment_points': round(adjustment, 3) if adjustment is not None else None,
        'personalized_planning_score': round(max(0, min(100, base_score + (adjustment or 0))), 3),
        'history_state': 'available_descriptive_association' if difference is not None else 'insufficient_data',
        'learning_snapshot_id': (feedback or {}).get('learning_snapshot_id'), 'learning_content_sha256': (feedback or {}).get('content_sha256'),
        'history_mock': (feedback or {}).get('scope', {}).get('mock'), 'ranking_policy': policy.model_dump(mode='json'),
        'sample_snapshot_ids': group['snapshot_ids'] if difference is not None else [],
        'control_snapshot_ids': group['control_snapshot_ids'] if difference is not None else [],
        'limitation': 'Planning estimate from a descriptive association; no observed or predicted future performance is asserted.'}


def request_payload(request, *, exclude=()):
    # Adding optional controls cannot invalidate historical cache keys when unused.
    omitted = set(exclude) | {name for name in ('learning_snapshot_id', 'learning_policy') if getattr(request, name, None) is None}
    return request.model_dump(mode='json', exclude=omitted)
