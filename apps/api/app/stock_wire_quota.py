"""Durable SQL stock scheduling at the wire boundary, separate from paid gates.

An admission is a fenced read-only lease. It never authorizes payment, rights,
publishing, or replay of an unknown paid outcome. Cache hits make no admission.
"""
from contextlib import asynccontextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import time
import uuid
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .db import utc_now
from .stock_retry_policy import MAX_COOLDOWN_SECONDS, StockWireBackoff, wire_backoff
from .stock_wire_context import CURRENT_OPERATION
from .stock_wire_quota_db import StockWireControlORM, StockWireEventORM, StockWireScopeORM

WIRE_LEASE_SECONDS = 180


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class StockWireDeferred(Exception):
    def __init__(self, code, next_at):
        self.code, self.next_at = code, next_at
        super().__init__(code)


@dataclass(frozen=True)
class StockWirePermit:
    scope: dict
    lease_id: str
    lease_until: float
    operation: dict


def validate_scope(scope):
    if not isinstance(scope, dict) or set(scope) != {'schema_version', 'workspace_id', 'root_sha256',
            'provider', 'mode', 'configuration_sha256', 'request_class'}:
        raise ValueError('STOCK_WIRE_SCOPE_INVALID')
    if scope['schema_version'] != 'sql-stock-wire-scope.v1' or scope['provider'] not in {'pexels', 'pixabay'} \
            or scope['mode'] not in {'fixture', 'official'} or scope['request_class'] not in {'api', 'cdn'}:
        raise ValueError('STOCK_WIRE_SCOPE_INVALID')
    if not isinstance(scope['workspace_id'], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', scope['workspace_id']):
        raise ValueError('STOCK_WIRE_SCOPE_INVALID')
    for field in ('root_sha256', 'configuration_sha256'):
        if not isinstance(scope[field], str) or not re.fullmatch(r'[a-f0-9]{64}', scope[field]):
            raise ValueError('STOCK_WIRE_SCOPE_INVALID')


def validate_operation(operation, scope):
    if not isinstance(operation, dict) or set(operation) != {'workspace_id', 'project_id', 'source_ref', 'budget_sha256'} \
            or operation['workspace_id'] != scope['workspace_id']:
        raise ValueError('STOCK_WIRE_OPERATION_INVALID')
    for key in ('workspace_id', 'project_id', 'source_ref'):
        if not isinstance(operation[key], str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,200}', operation[key]):
            raise ValueError('STOCK_WIRE_OPERATION_INVALID')
    if not isinstance(operation['budget_sha256'], str) or not re.fullmatch(r'[a-f0-9]{64}', operation['budget_sha256']):
        raise ValueError('STOCK_WIRE_OPERATION_INVALID')


class StockWireQuotaRepository:
    def __init__(self, session_factory):
        self.session_factory = session_factory

    async def ensure_state(self):
        async with self.session_factory() as session:
            if await session.get(StockWireControlORM, 'global') is not None:
                return
            session.add(StockWireControlORM(control_key='global', revision=0))
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()

    async def lock(self, session):
        # First write serializes PostgreSQL processes; SQLite also serializes
        # writers. The row is initialized before request admission.
        result = await session.execute(update(StockWireControlORM).where(
            StockWireControlORM.control_key == 'global').values(revision=StockWireControlORM.revision + 1))
        if result.rowcount != 1:
            raise ValueError('STOCK_WIRE_CONTROL_NOT_INITIALIZED')

    def checked(self, row, scope):
        validate_scope(scope)
        if row is None:
            return None
        if row.scope_json != scope or row.scope_sha256 != digest(scope) \
                or digest(row.evidence_json) != row.evidence_sha256:
            raise ValueError('STOCK_WIRE_STATE_INVALID')
        if type(row.cooldown_until) not in (int, float) or not math.isfinite(row.cooldown_until) or row.cooldown_until < 0:
            raise ValueError('STOCK_WIRE_STATE_INVALID')
        if (row.lease_id is None) != (row.lease_until is None) or row.lease_id is not None and (
                not re.fullmatch(r'[a-f0-9]{32}', row.lease_id) or not math.isfinite(row.lease_until) or row.lease_until <= 0):
            raise ValueError('STOCK_WIRE_STATE_INVALID')
        if row.cooldown_until:
            evidence = row.evidence_json
            if evidence.get('scope') != scope or evidence.get('wire_observed') is not True \
                    or evidence.get('semantic_health_assessment') is not False:
                raise ValueError('STOCK_WIRE_STATE_INVALID')
            try:
                observation = StockWireBackoff(**evidence['backoff'])
            except (TypeError, KeyError):
                raise ValueError('STOCK_WIRE_STATE_INVALID') from None
            validate_operation(evidence.get('operation'), scope)
            if type(observation.status_code) is not int or type(observation.observed_at) not in (int, float) \
                    or type(observation.delay_seconds) not in (int, float) or type(observation.blocked_until) not in (int, float) \
                    or observation.observed_at < 0 or observation.blocked_until != row.cooldown_until or not math.isfinite(observation.observed_at) \
                    or not 0 <= observation.delay_seconds <= MAX_COOLDOWN_SECONDS \
                    or abs(observation.observed_at + observation.delay_seconds - observation.blocked_until) > 1e-6:
                raise ValueError('STOCK_WIRE_STATE_INVALID')
            if observation.basis == 'successful_api_quota_exhaustion':
                if scope['request_class'] != 'api' or not 200 <= observation.status_code < 300 \
                        or type(observation.remaining) is not int or observation.remaining != 0 or observation.reset_epoch != observation.blocked_until \
                        or observation.blocked_until <= observation.observed_at:
                    raise ValueError('STOCK_WIRE_STATE_INVALID')
            elif observation.basis != 'retryable_wire_response' or observation.status_code not in {429, 500, 502, 503, 504}:
                raise ValueError('STOCK_WIRE_STATE_INVALID')
        return row

    def event(self, session, scope, action, evidence):
        session.add(StockWireEventORM(event_id='swq_'+uuid.uuid4().hex, scope_sha256=digest(scope),
            action=action, evidence_json=evidence, evidence_sha256=digest(evidence)))

    async def admit(self, scope, operation, stamp, *, lease_seconds=WIRE_LEASE_SECONDS):
        validate_scope(scope)
        validate_operation(operation, scope)
        if type(stamp) not in (int, float) or not math.isfinite(stamp) or stamp < 0 \
                or type(lease_seconds) is not int or not 30 <= lease_seconds <= 600:
            raise ValueError('STOCK_WIRE_CLOCK_INVALID')
        blocked = None
        async with self.session_factory() as session:
            async with session.begin():
                await self.lock(session)
                row = self.checked(await session.get(StockWireScopeORM, digest(scope), with_for_update=True), scope)
                if row is None:
                    row = StockWireScopeORM(scope_sha256=digest(scope), scope_json=scope, cooldown_until=0,
                        evidence_json={}, evidence_sha256=digest({}))
                    session.add(row)
                    await session.flush()
                if row.cooldown_until > stamp:
                    blocked = StockWireDeferred('STOCK_PROVIDER_COOLDOWN', row.cooldown_until)
                elif row.lease_id is not None and row.lease_until > stamp:
                    blocked = StockWireDeferred('STOCK_PROVIDER_WIRE_BUSY', row.lease_until)
                else:
                    if row.lease_id is not None:
                        self.event(session, scope, 'expired_lease_recovered', {'scope':scope,
                            'lease_id':row.lease_id, 'outcome_unknown':True, 'paid_replay_authorized':False})
                    lease = uuid.uuid4().hex
                    row.lease_id, row.lease_until, row.updated_at = lease, stamp + lease_seconds, utc_now()
                    self.event(session, scope, 'lease_admitted', {'scope':scope, 'operation':operation,
                        'lease_id':lease, 'lease_until':row.lease_until, 'wire_observed':False})
                    permit = StockWirePermit(scope, lease, row.lease_until, operation)
                if blocked is not None:
                    self.event(session, scope, 'deferred_before_wire', {'scope':scope, 'operation':operation,
                        'next_at':blocked.next_at, 'code':blocked.code, 'wire_attempts':0})
        if blocked is not None:
            raise blocked
        return permit

    async def check_permit(self, permit, stamp):
        async with self.session_factory() as session:
            row = self.checked(await session.get(StockWireScopeORM, digest(permit.scope)), permit.scope)
            if row is None or row.lease_id != permit.lease_id or row.lease_until <= stamp:
                raise StockWireDeferred('STOCK_PROVIDER_LEASE_LOST', max(stamp + 5, row.lease_until or 0) if row else stamp + 5)

    async def release(self, permit, *, stamp, status=None, headers=None, wire_attempted=False):
        async with self.session_factory() as session:
            async with session.begin():
                await self.lock(session)
                row = self.checked(await session.get(StockWireScopeORM, digest(permit.scope), with_for_update=True), permit.scope)
                if row is None or row.lease_id != permit.lease_id:
                    return False
                observation = wire_backoff(status, headers, stamp, permit.scope['request_class']) if status is not None else None
                if observation is not None and observation.blocked_until >= row.cooldown_until:
                    evidence = {'schema_version':'sql-stock-wire-cooldown.v1','scope':permit.scope,
                        'operation':permit.operation,'backoff':asdict(observation),'wire_observed':True,
                        'semantic_health_assessment':False,'owner_uat_accepted':False,'publishing_authorized':False}
                    row.cooldown_until, row.evidence_json, row.evidence_sha256 = observation.blocked_until, evidence, digest(evidence)
                    self.event(session, permit.scope, 'cooldown_observed', evidence)
                self.event(session, permit.scope, 'lease_released', {'scope':permit.scope,
                    'operation':permit.operation,'lease_id':permit.lease_id,'status_code':status,
                    'wire_attempted':wire_attempted,'outcome_unknown':wire_attempted and status is None})
                row.lease_id, row.lease_until, row.updated_at = None, None, utc_now()
        return True

    async def history(self, scope):
        validate_scope(scope)
        async with self.session_factory() as session:
            self.checked(await session.get(StockWireScopeORM, digest(scope)), scope)
            rows = (await session.scalars(select(StockWireEventORM).where(
                StockWireEventORM.scope_sha256 == digest(scope)).order_by(StockWireEventORM.created_at, StockWireEventORM.event_id))).all()
            if any(digest(row.evidence_json) != row.evidence_sha256 for row in rows):
                raise ValueError('STOCK_WIRE_EVENT_INVALID')
            return [{'action':row.action, 'evidence':row.evidence_json,'sha256':row.evidence_sha256} for row in rows]


class StockWireQuotaGuard:
    def __init__(self, repository, *, clock=time.time):
        self.repository, self.clock = repository, clock

    def scope(self, adapter, workspace, request_class):
        operation = CURRENT_OPERATION.get()
        if operation is None or operation.workspace_id != workspace:
            raise ValueError('STOCK_WIRE_OPERATION_SCOPE_REQUIRED')
        return {'schema_version':'sql-stock-wire-scope.v1','workspace_id':workspace,
            'root_sha256':digest(str(adapter.cache_root.resolve())),'provider':adapter.key,
            'mode':adapter.cache_mode,'configuration_sha256':adapter.cache_binding_sha256,'request_class':request_class}

    def operation(self):
        value = CURRENT_OPERATION.get()
        if value is None:
            raise ValueError('STOCK_WIRE_OPERATION_SCOPE_REQUIRED')
        return {'workspace_id':value.workspace_id, 'project_id':value.project_id,
            'source_ref':value.source_ref,'budget_sha256':value.budget_sha256}

    async def admit(self, adapter, workspace, request_class):
        scope = self.scope(adapter, workspace, request_class)
        operation = CURRENT_OPERATION.get()
        permit = operation.permits.pop(digest(scope), None)
        if permit is not None:
            await self.repository.check_permit(permit, float(self.clock()))
        else:
            permit = await self.repository.admit(scope, self.operation(), float(self.clock()))
        operation.wire_attempts += 1
        return permit

    async def release(self, permit, *, status=None, headers=None, wire_attempted=True):
        return await self.repository.release(permit, stamp=float(self.clock()), status=status,
            headers=headers, wire_attempted=wire_attempted)

    @asynccontextmanager
    async def prepare_download(self, adapter, workspace, metadata):
        operation = CURRENT_OPERATION.get()
        if operation is None:
            raise ValueError('STOCK_WIRE_OPERATION_SCOPE_REQUIRED')
        required = ['cdn']
        if metadata is not None:
            key, body = metadata
            operation.cached_inputs[key] = body
        else:
            required.insert(0, 'api')
        permits = []
        try:
            for request_class in required:
                scope = self.scope(adapter, workspace, request_class)
                permit = await self.repository.admit(scope, self.operation(), float(self.clock()))
                permits.append(permit)
                operation.permits[digest(scope)] = permit
            yield
        finally:
            for permit in permits:
                operation.permits.pop(digest(permit.scope), None)
                await self.release(permit, wire_attempted=False)
            operation.cached_inputs.clear()
