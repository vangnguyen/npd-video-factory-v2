"""Read-only exact-scope ORM channel baselines using the shared pure policy."""
from types import SimpleNamespace
from sqlalchemy import func,select
from .analytics_db import AnalyticsFeatureSnapshotORM,AnalyticsMetricPointORM,AnalyticsMetricSnapshotORM,WinnerAssessmentORM
from .analytics_models import NormalizedMetrics
from .analytics_repository import _aware,_utc_input
from .production_db import ProductionRenderJobORM
from .production_features import read as read_render_features
from .publishing_credentials import target_digest
from .publishing_db import PublicationORM
from .publishing_models import PublishingTargetBinding
# Preserve existing public imports and persisted algorithm/policy versions.
from .analytics_channel_policy import (VERSION,WEIGHTS,WinnerChannelPolicy,rate,values,bucket,counter_growth,assess_channel)

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
