"""Pure channel-relative winner policy; no database, transport or worker imports."""
import hashlib,json,math
from datetime import datetime,timezone
from statistics import median
from typing import Annotated,Literal
from pydantic import Field,StrictInt,model_validator
from .analytics_logic import AssessmentDraft
from .analytics_models import WinnerFactorRead
from .models import StrictModel

def _utc_input(value):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError('ANALYTICS_TIMESTAMP_TIMEZONE_REQUIRED')
    return value.astimezone(timezone.utc)

VERSION = 'winner-channel-assessment-v1'
WEIGHTS = dict(view_velocity=.18, retention=.16, completion=.16, engagement=.13, shares=.08,
    saves=.07, ctr=.08, follower_conversion=.06, revenue_efficiency=.05, production_cost_efficiency=.03)


class WinnerChannelPolicy(StrictModel):
    schema_version: Literal['winner-channel-policy-v1'] = 'winner-channel-policy-v1'
    minimum_peer_posts: StrictInt = Field(default=5, ge=3, le=100)
    maximum_peer_posts: StrictInt = Field(default=100, ge=3, le=100)
    minimum_views: StrictInt = Field(default=500, ge=1)
    minimum_counter_interval_hours: float = Field(default=6, ge=1, le=720, allow_inf_nan=False, strict=True)
    minimum_weight_coverage: float = Field(default=.4, ge=.1, le=1, allow_inf_nan=False, strict=True)
    winner_threshold: float = Field(default=72, ge=0, le=100, allow_inf_nan=False, strict=True)
    underperforming_threshold: float = Field(default=38, ge=0, le=100, allow_inf_nan=False, strict=True)
    weights: dict[str, Annotated[float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)]] = Field(default_factory=lambda: dict(WEIGHTS))

    @model_validator(mode='after')
    def policy(self):
        if self.minimum_peer_posts > self.maximum_peer_posts or self.underperforming_threshold >= self.winner_threshold:
            raise ValueError('WINNER_CHANNEL_POLICY_INVALID')
        if set(self.weights) != set(WEIGHTS) or any(not math.isfinite(v) or not 0 <= v <= 1 for v in self.weights.values()) or sum(self.weights.values()) <= 0:
            raise ValueError('WINNER_CHANNEL_WEIGHTS_INVALID')
        return self

    def digest(self):
        return hashlib.sha256(json.dumps(self.model_dump(mode='json'), sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def rate(value, views): return value / views if value is not None and views is not None and views > 0 else None


def values(metrics, duration, cost=None, velocity=None):
    if type(cost) not in (int, float) or not math.isfinite(cost) or cost <= 0: cost = None
    counters = ('likes', 'comments', 'shares', 'saves')
    signature = [name for name in counters if getattr(metrics, name) is not None]
    interactions = sum(getattr(metrics, name) for name in signature) if signature else None
    return {
        'view_velocity': velocity,
        'retention': metrics.average_view_duration / duration if metrics.average_view_duration is not None and duration and duration > 0 else None,
        'completion': metrics.completion_rate, 'engagement': rate(interactions, metrics.views),
        'shares': rate(metrics.shares, metrics.views), 'saves': rate(metrics.saves, metrics.views), 'ctr': metrics.ctr,
        'follower_conversion': rate(metrics.followers_gained, metrics.views),
        'revenue_efficiency': metrics.rpm if metrics.rpm is not None else rate(metrics.revenue, metrics.views) * 1000 if rate(metrics.revenue, metrics.views) is not None else None,
        'production_cost_efficiency': metrics.revenue / cost if metrics.revenue is not None and cost and cost > 0 else None,
        'engagement_components': signature,
    }


def bucket(duration):
    if duration is None or duration <= 0: return None
    return next((label for maximum, label in ((30, '0-30'), (60, '30-60'), (180, '60-180')) if duration <= maximum), '180+')


def counter_growth(current, previous, policy):
    if previous is None: return None
    if (current.evidence.get('metric_scope') != 'cumulative_video_counters'
        or previous['evidence'].get('metric_scope') != 'cumulative_video_counters'
        or current.metrics.views is None or previous['metrics'].views is None): return None
    elapsed = (_utc_input(current.collected_at) - previous['collected_at']).total_seconds() / 3600
    delta = current.metrics.views - previous['metrics'].views
    if elapsed < policy.minimum_counter_interval_hours or delta < 0: return None
    return {'reported_counter_growth_per_hour': delta / elapsed, 'delta_views': delta, 'elapsed_collection_hours': elapsed,
        'previous_snapshot_id': previous['snapshot_id'], 'current_collected_at': _utc_input(current.collected_at).isoformat(),
        'previous_collected_at': previous['collected_at'].isoformat(), 'provider_update_lag_unknown': True,
        'actual_publishing_age_hours': None}


def assess_channel(metrics, *, duration, production_cost, context, policy):
    growth = context['counter_growth']
    raw = values(metrics, duration, production_cost, growth['reported_counter_growth_per_hour'] if growth else None)
    factors = []
    total_weight = sum(policy.weights.values())
    for name, weight in policy.weights.items():
        observations = [(peer['snapshot_id'], peer['values'].get(name)) for peer in context['peers']
            if name != 'engagement' or peer['values']['engagement_components'] == raw['engagement_components']]
        observations = [(ref, value) for ref, value in observations if value is not None]
        baseline = median(value for _, value in observations) if len(observations) >= policy.minimum_peer_posts else None
        value = raw[name]
        score = None
        if value is not None and baseline is not None:
            score = 50 if value == baseline == 0 else 100 if baseline == 0 else min(100, max(0, value / baseline * 50))
        factors.append(WinnerFactorRead(factor=name, score=round(score, 3) if score is not None else None,
            weight=weight / total_weight, evidence={'raw_value': value, 'peer_median': baseline,
                'peer_snapshot_ids': [ref for ref, _ in observations], 'peer_count': len(observations),
                'comparison': 'matching_channel_report_scope', 'policy_sha256': policy.digest(),
                'engagement_components': raw['engagement_components'] if name == 'engagement' else None,
                'counter_growth': growth if name == 'view_velocity' else None,
                'peer_counter_growth': {peer['snapshot_id']: peer['counter_growth'] for peer in context['peers']
                    if peer.get('counter_growth')} if name == 'view_velocity' else None,
                'production_cost_vnd': production_cost if name == 'production_cost_efficiency' else None} ))
    available = sum(f.weight for f in factors if f.score is not None)
    sufficient = (context['scope_verified'] and len(context['peers']) >= policy.minimum_peer_posts
        and metrics.views is not None and metrics.views >= policy.minimum_views
        and available >= policy.minimum_weight_coverage
        and any(f.score is not None and f.factor in ('retention', 'completion') for f in factors))
    score = round(sum(f.score * f.weight for f in factors if f.score is not None) / available, 3) if sufficient and available else None
    state = 'insufficient_data' if score is None else 'winner_candidate' if score >= policy.winner_threshold else 'underperforming' if score <= policy.underperforming_threshold else 'normal'
    evidence = [f'Channel policy SHA256: {policy.digest()}; matched distinct peer posts: {len(context["peers"])}.',
        'Peers share workspace, exact account/profile binding, platform, provider, transport, requested report interval, render format, duration bucket and frozen niche.',
        f'Available configured weight: {available:.6f}; minimum {policy.minimum_weight_coverage:.6f}. Median peer value scores 50; twice median scores 100.',
        'Requested report dates do not certify complete provider coverage or equal publication age. Counter growth measures reported count changes between collections; provider update lag is unknown.',
        f'Candidate scan truncated: {context["candidate_rows_truncated"]}; at most 500 rows and {policy.maximum_peer_posts} distinct peers.']
    return AssessmentDraft(state=state, score=score, data_coverage=round(available, 6), factors=factors, evidence=evidence,
        recommendations=['Review this relative assessment with its missing metrics and peer evidence.',
            'Collect compatible observations before changing creative strategy; do not delete posts or change media budgets automatically.'], algorithm_version=VERSION)
