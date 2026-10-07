"""Read-only aggregation of frozen production features and compatible assessments."""
import hashlib
import uuid

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from .analytics_cohort import VERSION as WINNER_VERSION, bucket
from .analytics_db import AnalyticsMetricSnapshotORM, AnalyticsFeatureSnapshotORM, WinnerAssessmentORM
from .analytics_repository import _aware
from .db import utc_now
from .learning_db import ChannelLearningSnapshotORM
from .learning_models import LearningSnapshot, LearningObservation, aggregate, digest, snapshot_content
from .production_db import ProductionRenderJobORM
from .production_features import read as read_features
from .publishing_credentials import target_digest
from .publishing_db import PublicationORM
from .publishing_models import PublishingTargetBinding


class LearningError(ValueError):
    def __init__(self, code): self.code = code; super().__init__(code)


def read_snapshot(row):
    try:
        value = LearningSnapshot.model_validate(row.snapshot_json)
        if (digest(snapshot_content(value.model_dump(mode='json'))) != row.content_sha256
            or value.content_sha256 != row.content_sha256 or value.learning_snapshot_id != row.learning_snapshot_id
            or value.workspace_id != row.workspace_id or value.project_id != row.project_id
            or value.publication_id != row.publication_id or value.anchor_snapshot_id != row.anchor_snapshot_id
            or value.created_by != row.created_by or value.created_at != _aware(row.created_at)):
            raise ValueError()
        return value
    except (ValueError, TypeError): raise LearningError('LEARNING_SNAPSHOT_INVALID') from None


def target_of(publication):
    try: return target_digest(PublishingTargetBinding.model_validate((publication.provider_validation_json or {}).get('target_binding')))
    except ValueError: return None


def assessment_basis(assessment):
    return sorted([{'factor': item.get('factor'), 'weight': item.get('weight'), 'available': item.get('score') is not None}
        for item in (assessment.factors_json if assessment else [])], key=lambda item: str(item['factor']))


def frozen_observation(row, publication, feature, assessment, render):
    if (feature is None or assessment is None or render is None or assessment.algorithm_version != WINNER_VERSION
        or assessment.score is None or assessment.state == 'insufficient_data'
        or feature.project_id != row.project_id or feature.publication_id != row.publication_id
        or assessment.project_id != row.project_id or assessment.publication_id != row.publication_id
        or render.project_id != row.project_id or render.workspace_id != row.workspace_id
        or (feature.evidence_json or {}).get('project_metadata_source') != 'published_render_request_context'
        or feature.evidence_json.get('feature_context_sha256') != (render.manifest_json or {}).get('feature_context_sha256')
        or feature.evidence_json.get('timeline_version_id') != render.timeline_version_id): return None
    try: context = read_features(render.manifest_json or {}, workspace=row.workspace_id, project=row.project_id, timeline_version=render.timeline_version_id)
    except ValueError: return None
    if context is None or context.niche != feature.niche: return None
    factors = assessment.factors_json or []
    if not any(item.get('factor') in ('retention', 'completion') and item.get('score') is not None for item in factors): return None
    policies = {item.get('evidence', {}).get('policy_sha256') for item in factors}
    if len(policies) != 1 or not next(iter(policies)): return None
    remote = (publication.receipt_json or {}).get('remote_post_id')
    if not remote: return None
    try:
        return LearningObservation(snapshot_id=row.snapshot_id, publication_id=row.publication_id,
            assessment_id=assessment.assessment_id, render_id=render.render_id, timeline_version_id=render.timeline_version_id,
            feature_context_sha256=feature.evidence_json['feature_context_sha256'],
            remote_post_sha256=hashlib.sha256(remote.encode()).hexdigest(), collected_at=_aware(row.collected_at),
            score=float(assessment.score), winner_policy_sha256=next(iter(policies)), features={
                'trend_family': context.trend_cluster_id, 'hook': context.hook_type,
                'duration': bucket(float(feature.duration_seconds)) if feature.duration_seconds is not None else None,
                'visual_strategy': context.visual_strategy or feature.visual_strategy,
                'subtitle_style': feature.subtitle_template, 'voice_profile': feature.voice_profile,
                # Queue/receipt/collection time is not the actual publishing time.
                'publishing_window': None}, assessment_basis_sha256=digest(assessment_basis(assessment)))
    except (ValueError, TypeError): return None


class ChannelLearningService:
    def __init__(self, factory): self.factory = factory

    async def get(self, workspace, identity):
        async with self.factory() as session:
            row = await session.get(ChannelLearningSnapshotORM, identity)
            return read_snapshot(row) if row and row.workspace_id == workspace else None

    async def list(self, project, *, limit=50):
        async with self.factory() as session:
            rows = (await session.scalars(select(ChannelLearningSnapshotORM).where(ChannelLearningSnapshotORM.project_id == project)
                .order_by(ChannelLearningSnapshotORM.created_at.desc(), ChannelLearningSnapshotORM.learning_snapshot_id.desc()).limit(limit))).all()
            return [read_snapshot(row) for row in rows]

    async def feedback(self, workspace, identity, *, niche=None):
        value = await self.get(workspace, identity)
        if value is None: raise LearningError('LEARNING_SNAPSHOT_NOT_FOUND')
        if niche is not None and value.scope.get('niche') != niche: raise LearningError('LEARNING_NICHE_MISMATCH')
        return {'learning_snapshot_id': value.learning_snapshot_id, 'content_sha256': value.content_sha256,
            'scope': value.scope, 'recommendation_only': True, 'autonomous_execution': False,
            'recommendations': [item.model_dump(mode='json') for item in value.dimensions],
            'limitations': value.limitations}

    async def create(self, project, payload, *, actor, key):
        request_hash = digest(payload.model_dump(mode='json')); key_hash = hashlib.sha256(key.encode()).hexdigest()
        async with self.factory() as session:
            prior = await session.scalar(select(ChannelLearningSnapshotORM).where(ChannelLearningSnapshotORM.project_id == project,
                ChannelLearningSnapshotORM.idempotency_key_hash == key_hash))
            if prior:
                if prior.request_fingerprint != request_hash: raise LearningError('LEARNING_IDEMPOTENCY_CONFLICT')
                return read_snapshot(prior), True
            publication = await session.get(PublicationORM, payload.publication_id)
            if publication is None or publication.project_id != project: raise LearningError('LEARNING_PUBLICATION_NOT_FOUND')
            if payload.provider_mode != 'official': raise LearningError('LEARNING_OFFICIAL_CHANNEL_SCOPE_REQUIRED')
            anchor = await session.scalar(select(AnalyticsMetricSnapshotORM).where(
                AnalyticsMetricSnapshotORM.publication_id == payload.publication_id,
                AnalyticsMetricSnapshotORM.source_kind == 'official_api').order_by(
                    AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(), AnalyticsMetricSnapshotORM.snapshot_id.desc()).limit(1))
            target = target_of(publication)
            evidence = (anchor.evidence_json or {}) if anchor else {}
            if (anchor is None or anchor.project_id != project or anchor.workspace_id != publication.workspace_id
                or anchor.platform != publication.platform or not target or evidence.get('account_match') is not True
                or evidence.get('target_binding_sha256') != target or publication.status != 'published'
                or publication.mode != 'live' or publication.dry_run): raise LearningError('LEARNING_CHANNEL_SCOPE_UNVERIFIED')
            anchor_feature = await session.scalar(select(AnalyticsFeatureSnapshotORM).where(AnalyticsFeatureSnapshotORM.snapshot_id == anchor.snapshot_id))
            anchor_render = await session.get(ProductionRenderJobORM, publication.final_render_id)
            if anchor_feature is None or anchor_render is None: raise LearningError('LEARNING_FROZEN_FEATURES_REQUIRED')
            # The anchor can be insufficient; it still defines exact transport/report/account scope.
            try: anchor_context = read_features(anchor_render.manifest_json or {}, workspace=publication.workspace_id, project=project, timeline_version=anchor_render.timeline_version_id)
            except ValueError: raise LearningError('LEARNING_FROZEN_FEATURES_REQUIRED') from None
            if (anchor_context is None or not anchor_context.niche or anchor_feature.niche != anchor_context.niche
                or anchor_feature.project_id != project or anchor_feature.publication_id != publication.publication_id
                or (anchor_feature.evidence_json or {}).get('project_metadata_source') != 'published_render_request_context'
                or (anchor_feature.evidence_json or {}).get('timeline_version_id') != anchor_render.timeline_version_id
                or (anchor_feature.evidence_json or {}).get('feature_context_sha256') != anchor_render.manifest_json.get('feature_context_sha256')):
                raise LearningError('LEARNING_FROZEN_FEATURES_REQUIRED')
            scope = {'workspace_id': publication.workspace_id, 'platform': anchor.platform, 'provider_key': anchor.provider_key,
                'source_kind': anchor.source_kind, 'mock': anchor.mock, 'external_call': anchor.external_call,
                'target_binding_sha256': target, 'query': evidence.get('query'),
                'niche': anchor_context.niche, 'render_profile': anchor_render.profile,
                'actual_publishing_time_available': False, 'winner_algorithm_version': WINNER_VERSION}
            rank = select(AnalyticsMetricSnapshotORM.snapshot_id, func.row_number().over(
                partition_by=AnalyticsMetricSnapshotORM.publication_id,
                order_by=(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.created_at.desc(), AnalyticsMetricSnapshotORM.snapshot_id.desc())).label('position')).where(
                    AnalyticsMetricSnapshotORM.workspace_id == publication.workspace_id,
                    AnalyticsMetricSnapshotORM.platform == anchor.platform,
                    AnalyticsMetricSnapshotORM.provider_key == anchor.provider_key,
                    AnalyticsMetricSnapshotORM.source_kind == anchor.source_kind,
                    AnalyticsMetricSnapshotORM.mock == anchor.mock,
                    AnalyticsMetricSnapshotORM.external_call == anchor.external_call,
                    AnalyticsMetricSnapshotORM.collected_at <= anchor.collected_at).subquery()
            rows = (await session.execute(select(AnalyticsMetricSnapshotORM, PublicationORM, AnalyticsFeatureSnapshotORM, WinnerAssessmentORM, ProductionRenderJobORM)
                .join(rank, rank.c.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
                .join(PublicationORM, PublicationORM.publication_id == AnalyticsMetricSnapshotORM.publication_id)
                .outerjoin(AnalyticsFeatureSnapshotORM, AnalyticsFeatureSnapshotORM.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
                .outerjoin(WinnerAssessmentORM, WinnerAssessmentORM.snapshot_id == AnalyticsMetricSnapshotORM.snapshot_id)
                .outerjoin(ProductionRenderJobORM, ProductionRenderJobORM.render_id == PublicationORM.final_render_id)
                .where(rank.c.position == 1).order_by(AnalyticsMetricSnapshotORM.collected_at.desc(), AnalyticsMetricSnapshotORM.snapshot_id.desc()).limit(501))).all()
            anchor_assessment = await session.scalar(select(WinnerAssessmentORM).where(WinnerAssessmentORM.snapshot_id == anchor.snapshot_id))
            anchor_policies = {item.get('evidence', {}).get('policy_sha256') for item in (anchor_assessment.factors_json if anchor_assessment else [])}
            winner_policy = next(iter(anchor_policies)) if len(anchor_policies) == 1 and next(iter(anchor_policies)) else None
            basis = assessment_basis(anchor_assessment)
            scope['winner_factor_basis'] = basis
            basis_sha256 = digest(basis)
            observations = []; selected = set(); excluded = {}; posts_truncated = False
            for row, parent, feature, assessment, render in rows[:500]:
                reason = None; evidence = row.evidence_json or {}
                if (parent.workspace_id != publication.workspace_id or parent.project_id != row.project_id
                    or parent.platform != anchor.platform or parent.status != 'published' or parent.mode != 'live' or parent.dry_run
                    or target_of(parent) != target or evidence.get('target_binding_sha256') != target
                    or evidence.get('account_match') is not True or evidence.get('query') != scope['query']): reason = 'incompatible_scope'
                item = None if reason else frozen_observation(row, parent, feature, assessment, render)
                if not reason and item is None: reason = 'missing_or_invalid_frozen_assessment'
                if item and (feature.niche != scope['niche'] or render.profile != scope['render_profile']): reason = 'incompatible_creative_scope'
                if item and not reason and winner_policy and item.winner_policy_sha256 != winner_policy: reason = 'incompatible_winner_policy'
                if item and not reason and item.assessment_basis_sha256 != basis_sha256: reason = 'incompatible_assessment_basis'
                if item and not reason and item.remote_post_sha256 in selected: reason = 'duplicate_remote_post'
                if reason:
                    excluded[reason] = excluded.get(reason, 0) + 1
                    continue
                if len(observations) >= payload.policy.maximum_posts:
                    posts_truncated = True; continue
                winner_policy = item.winner_policy_sha256
                selected.add(item.remote_post_sha256); observations.append(item)
            scope['winner_policy_sha256'] = winner_policy
            value = LearningSnapshot(learning_snapshot_id='lsn_' + uuid.uuid4().hex[:24], workspace_id=publication.workspace_id,
                project_id=project, publication_id=publication.publication_id, anchor_snapshot_id=anchor.snapshot_id,
                scope=scope, policy=payload.policy, observations=observations, dimensions=aggregate(observations, payload.policy),
                candidate_rows_truncated=len(rows) > 500, selected_posts_truncated=posts_truncated, excluded_rows=excluded,
                content_sha256='0' * 64, created_at=utc_now(), created_by=actor, limitations=[
                    'Descriptive association of relative winner assessment scores; no causal effect or future performance guarantee.',
                    'Latest compatible observations from a bounded scan are not an exhaustive channel history or account totals.',
                    'Requested report intervals do not certify complete provider coverage or equal publication age.',
                    'Publishing windows stay unavailable until authoritative actual publication timestamps are supported.',
                    'Mock transport observations are synthetic evidence and are never combined with real provider observations.',
                    'Feature labels are frozen project annotations or edit facts, not independently verified semantic classifications.'])
            value.content_sha256 = digest(snapshot_content(value.model_dump(mode='json')))
            session.add(ChannelLearningSnapshotORM(learning_snapshot_id=value.learning_snapshot_id, workspace_id=value.workspace_id,
                project_id=project, publication_id=value.publication_id, anchor_snapshot_id=value.anchor_snapshot_id,
                idempotency_key_hash=key_hash, request_fingerprint=request_hash, content_sha256=value.content_sha256,
                snapshot_json=value.model_dump(mode='json'), created_at=value.created_at, created_by=actor))
            try: await session.commit()
            except IntegrityError:
                await session.rollback()
                row = await session.scalar(select(ChannelLearningSnapshotORM).where(ChannelLearningSnapshotORM.project_id == project,
                    ChannelLearningSnapshotORM.idempotency_key_hash == key_hash))
                if row is None: raise
                if row.request_fingerprint != request_hash: raise LearningError('LEARNING_IDEMPOTENCY_CONFLICT') from None
                return read_snapshot(row), True
            return value, False
