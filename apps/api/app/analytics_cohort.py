"""Read-only exact-scope channel baselines; unsupported observations stay null."""
import hashlib
import json
import math
from statistics import median
from typing import Annotated, Literal
from types import SimpleNamespace

from pydantic import Field, StrictInt, model_validator
from sqlalchemy import func, select

from .analytics_db import AnalyticsFeatureSnapshotORM, AnalyticsMetricPointORM, AnalyticsMetricSnapshotORM, WinnerAssessmentORM
from .analytics_logic import AssessmentDraft
from .analytics_models import NormalizedMetrics, WinnerFactorRead
from .analytics_repository import _aware, _utc_input
from .models import StrictModel
from .production_db import ProductionRenderJobORM
from .production_features import read as read_render_features
from .publishing_credentials import target_digest
from .publishing_db import PublicationORM
from .publishing_models import PublishingTargetBinding

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


async def channel_context(factory, *, sync, publication, collection, features, policy):
    """Bound candidate rows, preserve transport/date/account scope, dedupe remote posts."""
    context = {'peers': [], 'candidate_rows_truncated': False, 'counter_growth': None,
        'policy_sha256': policy.digest(), 'scope_verified': False}
    target = publication.provider_validation.target_binding if publication.provider_validation else None
    if not target or collection.source_kind != 'official_api' or collection.evidence.get('account_match') is not True:
        return context
    scope = target_digest(target)
    if collection.evidence.get('target_binding_sha256') != scope: return context
    context['scope_verified'] = True
    context['target_binding_sha256'] = scope
    at = _utc_input(collection.collected_at); query = collection.evidence.get('query')
    async with factory() as session:
        current_render = await session.get(ProductionRenderJobORM, publication.final_render_id)
        rank = select(AnalyticsMetricSnapshotORM.snapshot_id, func.row_number().over(
            partition_by=AnalyticsMetricSnapshotORM.publication_id,
            order_by=(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(),
                AnalyticsMetricSnapshotORM.snapshot_id.desc())).label('position')).where(
            AnalyticsMetricSnapshotORM.workspace_id == sync.workspace_id,
            AnalyticsMetricSnapshotORM.platform == sync.platform,
            AnalyticsMetricSnapshotORM.provider_key == collection.provider_key,
            AnalyticsMetricSnapshotORM.source_kind == collection.source_kind,
            AnalyticsMetricSnapshotORM.mock == collection.mock,
            AnalyticsMetricSnapshotORM.external_call == collection.external_call,
            AnalyticsMetricSnapshotORM.collected_at <= at).subquery()
        rows = (await session.execute(select(AnalyticsMetricSnapshotORM, PublicationORM, AnalyticsFeatureSnapshotORM,
            WinnerAssessmentORM, ProductionRenderJobORM)
            .join(rank, rank.c.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
            .join(PublicationORM, PublicationORM.publication_id == AnalyticsMetricSnapshotORM.publication_id)
            .outerjoin(AnalyticsFeatureSnapshotORM, AnalyticsFeatureSnapshotORM.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
            .outerjoin(WinnerAssessmentORM, WinnerAssessmentORM.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
            .join(ProductionRenderJobORM, ProductionRenderJobORM.render_id == PublicationORM.final_render_id)
            .where(rank.c.position <= 2)
            .order_by(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(),
                AnalyticsMetricSnapshotORM.snapshot_id.desc()).limit(501))).all()
        context['candidate_rows_truncated'] = len(rows) > 500
        ids = [row[0].snapshot_id for row in rows[:500]]
        points = (await session.scalars(select(AnalyticsMetricPointORM).where(AnalyticsMetricPointORM.snapshot_id.in_(ids)))).all()
        metrics = {}
        for point in points: metrics.setdefault(point.snapshot_id, {})[point.metric_name] = float(point.value) if point.value is not None else None
        selected = {}; current_post = publication.receipt.remote_post_id if publication.receipt else None
        for row, parent, feature, assessment, peer_render in rows[:500]:
            evidence = row.evidence_json or {}
            if (parent.workspace_id != sync.workspace_id or parent.project_id != row.project_id or parent.platform != sync.platform
                or parent.status != 'published' or parent.mode != 'live' or parent.dry_run
                or evidence.get('account_match') is not True or evidence.get('target_binding_sha256') != scope
                or evidence.get('query') != query): continue
            try: peer_target = PublishingTargetBinding.model_validate((parent.provider_validation_json or {}).get('target_binding'))
            except ValueError: continue
            if target_digest(peer_target) != scope: continue
            receipt = parent.receipt_json or {}; remote = receipt.get('remote_post_id')
            if not remote: continue
            parsed = NormalizedMetrics.model_validate(metrics.get(row.snapshot_id, {}))
            item = {'snapshot_id': row.snapshot_id, 'publication_id': row.publication_id, 'metrics': parsed,
                'evidence': evidence, 'collected_at': _aware(row.collected_at)}
            if row.publication_id == sync.publication_id and remote == current_post:
                if context['counter_growth'] is None: context['counter_growth'] = counter_growth(collection, item, policy)
                continue
            if remote == current_post: continue
            if remote in selected:
                saved = selected[remote]
                if saved['publication_id'] == row.publication_id and saved.get('counter_growth') is None:
                    growth = counter_growth(SimpleNamespace(metrics=saved['metrics'], evidence=saved['evidence'],
                        collected_at=saved['collected_at']), item, policy)
                    if growth:
                        saved['counter_growth'] = growth
                        saved['values']['view_velocity'] = growth['reported_counter_growth_per_hour']
                continue
            if len(selected) >= policy.maximum_peer_posts: continue
            if (current_render is None or peer_render.profile != current_render.profile or feature is None
                or peer_render.project_id != parent.project_id or peer_render.workspace_id != sync.workspace_id
                or feature.project_id != row.project_id or feature.publication_id != row.publication_id
                or (feature.evidence_json or {}).get('project_metadata_source') != 'published_render_request_context'
                or feature.niche != features.niche or bucket(float(feature.duration_seconds) if feature.duration_seconds is not None else None) != bucket(features.duration_seconds)):
                continue
            try:
                frozen = read_render_features(peer_render.manifest_json or {}, workspace=sync.workspace_id,
                    project=parent.project_id, timeline_version=peer_render.timeline_version_id)
            except ValueError: continue
            if (frozen is None or frozen.niche != feature.niche
                or feature.evidence_json.get('feature_context_sha256') != (peer_render.manifest_json or {}).get('feature_context_sha256')
                or feature.evidence_json.get('timeline_version_id') != peer_render.timeline_version_id): continue
            cost = None
            if assessment:
                cost = next((factor.get('evidence', {}).get('production_cost_vnd') for factor in assessment.factors_json
                    if factor.get('factor') == 'production_cost_efficiency'), None)
            item['values'] = values(parsed, float(feature.duration_seconds) if feature.duration_seconds is not None else None, cost)
            selected[remote] = item
        context['peers'] = list(selected.values())
    return context


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
