"""Pre-wire operation/cost recording in existing tables; no network/provider activation."""
from dataclasses import dataclass
from decimal import Decimal
import hashlib
import re
import uuid

from sqlalchemy import select, update

from .db import CostRecordORM, JobORM, ProviderRegistryORM, ProviderUsageORM, VideoProjectORM, utc_now
from .publishing_db import PublicationEventORM, PublicationORM

OPERATIONS = frozenset({'account_lookup', 'initialize', 'chunk', 'reconcile', 'processing_status', 'thumbnail'})


class PublishingOperationError(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def amount(value):
    try:
        invalid = value is not None and (type(value) is not Decimal or not value.is_finite() or value < 0
            or value > Decimal('9999999999999999') or value.quantize(Decimal('0.0001')) != value)
    except Exception:
        invalid = True
    if invalid:
        raise PublishingOperationError('PUBLISH_COST_AMOUNT_INVALID')
    return value


@dataclass(frozen=True)
class OperationReservation:
    usage_id: str
    cost_id: str
    allowed: bool
    mock: bool


class PublishingOperationMeter:
    def __init__(self, session_factory, *, clock=utc_now):
        self.session_factory, self.clock = session_factory, clock

    async def admit(self, workspace, publication_id, operation, *, request_identity, estimated_cost=None,
                    max_ai_cost=None, job_id=None, mock=False):
        amount(estimated_cost); amount(max_ai_cost)
        if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(request_identity, str) or not re.fullmatch('[a-f0-9]{32}', request_identity) or type(mock) is not bool:
            raise PublishingOperationError('PUBLISH_COST_REQUEST_INVALID')
        operation_key = hashlib.sha256(f'{workspace}|{publication_id}|{operation}|{request_identity}'.encode()).hexdigest()
        async with self.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, publication_id)
                if parent is None or parent.workspace_id != workspace:
                    raise PublishingOperationError('PUBLISH_COST_SCOPE_NOT_FOUND')
                # Serialize competing publishing reservations on this project.
                # This does not claim coordination with other provider meters.
                locked = await session.execute(update(VideoProjectORM).where(VideoProjectORM.project_id == parent.project_id,
                    VideoProjectORM.workspace_id == workspace).values(updated_at=VideoProjectORM.updated_at))
                if locked.rowcount != 1:
                    raise PublishingOperationError('PUBLISH_COST_SCOPE_NOT_FOUND')
                if job_id is not None:
                    job = await session.get(JobORM, job_id)
                    if job is None or job.workspace_id != workspace or job.project_id != parent.project_id:
                        raise PublishingOperationError('PUBLISH_COST_JOB_SCOPE_INVALID')
                if await session.scalar(select(ProviderUsageORM).where(ProviderUsageORM.operation_key == operation_key)):
                    # A reserved request could already have crossed the wire.
                    # A cost-key replay is never permission to send it again.
                    raise PublishingOperationError('PUBLISH_OPERATION_ALREADY_RESERVED')
                provider = await session.scalar(select(ProviderRegistryORM).where(
                    ProviderRegistryORM.provider_key == parent.provider_key, ProviderRegistryORM.capability == 'publishing',
                    ProviderRegistryORM.workspace_id == workspace))
                if provider is None:
                    provider = await session.scalar(select(ProviderRegistryORM).where(
                        ProviderRegistryORM.provider_key == parent.provider_key, ProviderRegistryORM.capability == 'publishing',
                        ProviderRegistryORM.workspace_id.is_(None)))
                if provider is None:
                    raise PublishingOperationError('PUBLISH_COST_PROVIDER_NOT_REGISTERED')
                recorded = (await session.execute(select(CostRecordORM, ProviderUsageORM).join(
                    ProviderUsageORM, ProviderUsageORM.usage_id == CostRecordORM.provider_usage_id).where(
                    CostRecordORM.workspace_id == workspace, CostRecordORM.project_id == parent.project_id))).all()
                total, unknown = Decimal('0'), False
                for cost, usage in recorded:
                    if usage.status in ('not_sent', 'needs_approval'):
                        continue
                    observed = cost.actual_cost if cost.actual_cost is not None else cost.estimated_cost
                    if observed is None: unknown = True
                    else: total += observed
                blocked = max_ai_cost is not None and (unknown or estimated_cost is None or total + estimated_cost > max_ai_cost)
                now = self.clock(); usage_id = 'pus_' + uuid.uuid4().hex; cost_id = 'cost_' + uuid.uuid4().hex
                usage = ProviderUsageORM(usage_id=usage_id, operation_key=operation_key, workspace_id=workspace,
                    project_id=parent.project_id, job_id=job_id, provider_id=provider.provider_id, provider_key=parent.provider_key,
                    capability='publishing', model=None, operation='publishing.' + operation, units=Decimal('1'),
                    unit_name='request_intent', status='needs_approval' if blocked else 'dispatch_intent',
                    metadata_json={'publication_id': publication_id, 'operation': operation, 'mock': mock,
                        'provider_quota_units': None, 'external_request_confirmed': False}, created_at=now, completed_at=None)
                session.add(usage); await session.flush()
                cost = CostRecordORM(cost_id=cost_id, workspace_id=workspace, project_id=parent.project_id, job_id=job_id,
                    provider_usage_id=usage_id, estimated_cost=estimated_cost, actual_cost=None, currency='VND',
                    needs_approval=blocked, approved=False, provenance={'source': 'publishing-wire-admission', 'mock': mock,
                        'estimate_source': 'configured_estimate' if estimated_cost is not None else 'unknown'})
                session.add(cost)
                self.event(session, parent, 'publication.operation_reserved', {'usage_id': usage_id, 'cost_id': cost_id,
                    'operation': operation, 'needs_approval': blocked, 'mock': mock, 'external_action': False})
            # The operation and cost intent are durable before a caller receives admission.
            return OperationReservation(usage_id, cost_id, not blocked, mock)

    async def finish(self, workspace, publication_id, reservation, *, outcome):
        if not isinstance(reservation, OperationReservation) or outcome not in ('confirmed', 'outcome_unknown', 'not_sent'):
            raise PublishingOperationError('PUBLISH_OPERATION_OUTCOME_INVALID')
        async with self.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, publication_id)
                usage = await session.get(ProviderUsageORM, reservation.usage_id); cost = await session.get(CostRecordORM, reservation.cost_id)
                if (parent is None or parent.workspace_id != workspace or usage is None or cost is None
                    or usage.workspace_id != workspace or usage.project_id != parent.project_id
                    or usage.metadata_json.get('publication_id') != publication_id or cost.provider_usage_id != usage.usage_id
                    or cost.workspace_id != workspace or cost.project_id != parent.project_id
                    or reservation.mock != usage.metadata_json.get('mock')):
                    raise PublishingOperationError('PUBLISH_COST_SCOPE_NOT_FOUND')
                if usage.status == outcome:
                    return {'usage_id': usage.usage_id, 'status': outcome, 'actual_cost': cost.actual_cost}
                changed = await session.execute(update(ProviderUsageORM).where(ProviderUsageORM.usage_id == usage.usage_id,
                    ProviderUsageORM.status == 'dispatch_intent').values(status=outcome, completed_at=self.clock(),
                        metadata_json={**usage.metadata_json, 'request_outcome_recorded': True,
                            'external_request_confirmed': False if reservation.mock or outcome == 'not_sent' else True if outcome == 'confirmed' else None}))
                if changed.rowcount != 1:
                    raise PublishingOperationError('PUBLISH_OPERATION_OUTCOME_CONFLICT')
                self.event(session, parent, 'publication.operation_' + outcome, {'usage_id': usage.usage_id, 'cost_id': cost.cost_id,
                    'operation': usage.metadata_json['operation'], 'mock': reservation.mock,
                    'request_outcome_recorded': True, 'external_action': False if reservation.mock or outcome == 'not_sent' else None})
            return {'usage_id': reservation.usage_id, 'status': outcome, 'actual_cost': cost.actual_cost}

    def event(self, session, parent, event_type, payload):
        session.add(PublicationEventORM(event_id='pue_' + uuid.uuid4().hex, publication_id=parent.publication_id,
            project_id=parent.project_id, event_type=event_type, actor_ref='publishing-service',
            payload_json={**payload, 'secret_free': True}, created_at=self.clock()))
