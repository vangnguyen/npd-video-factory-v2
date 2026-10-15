"""Actor-scoped request settlement, with immutable preparation/late-result audit.

Recovery never authenticates an expired token, dispatches a provider, applies a
plan, deletes evidence, or refunds an operation. Existing operation tables only.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime

from sqlalchemy import select

from .broll_plan_review_command import BrollPlanConflict, _begin, _context, _public
from .db import VideoProjectORM, utc_now
from .service_api_repository import ServiceOperationORM, digest


SETTLEMENT_NAMESPACE = 'human:broll-request-settlement.v1'
SETTLEMENT_ACTION = 'broll.request.abandon.v1'
LATE_NAMESPACE = 'human:broll-request-late-result.v1'
PUBLIC_FIELDS = {'subject', 'display_name', 'platform_role', 'workspace_roles', 'expires_at', 'human_write_enabled'}


def private_identity(authority, authorization, writes):
    token = authorization.removeprefix('Bearer ').strip()
    return {'schema_version': 'broll-recovery-identity.v1', 'authority': authority,
        'credential_sha256': hashlib.sha256(token.encode()).hexdigest(),
        'public_session': {**{k: authority[k] for k in PUBLIC_FIELDS - {'human_write_enabled'}},
            'human_write_enabled': writes is True}}


def _fail(code='BROLL_RECOVERY_PROOF_INVALID', status=409):
    raise BrollPlanConflict(code, status)


def _hash(value):
    return isinstance(value, str) and len(value) == 64 and all(c in '0123456789abcdef' for c in value)


def _parse(raw):
    def constant(_):
        raise ValueError('nonfinite')
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    return json.loads(raw, parse_constant=constant, object_pairs_hook=unique)


def _intent(raw, expected):
    from .broll_plan_review_api import BrollPlanPrepare
    try:
        if not isinstance(raw, str) or len(raw.encode()) > 5 * 1024 * 1024:
            _fail()
        if hashlib.sha256(raw.encode()).hexdigest() != expected:
            _fail()
        value = _parse(raw)
        if set(value) != {'schema_version', 'body', 'context', 'boundary', 'session_sha256', 'credential_sha256'} \
                or value['schema_version'] != 'broll-plan-pending.v1':
            _fail()
        request = BrollPlanPrepare.model_validate(value['body']).model_dump(mode='json')
        if request != value['body'] or not _hash(value['session_sha256']) or not _hash(value['credential_sha256']):
            _fail()
        context = value['context']
        literal = context['context_json']
        public = {k: v for k, v in context.items() if k not in {'context_json', 'context_sha256'}}
        if not _hash(context.get('authority_sha256')) or not _hash(context.get('context_sha256')) \
                or not isinstance(literal, str) or len(literal) > 65536 or _parse(literal) != public \
                or hashlib.sha256(literal.encode()).hexdigest() != context['context_sha256'] \
                or request['context_sha256'] != context['context_sha256'] \
                or context['schema_version'] != 'broll-plan-review-context.v1':
            _fail()
        boundary = _parse(value['boundary'])
        if not isinstance(boundary, list) or len(boundary) != 7 or set(boundary[2]) != PUBLIC_FIELDS:
            _fail()
        principal = boundary[2]
        if digest(principal) != value['session_sha256'] or principal['human_write_enabled'] is not True \
                or boundary[0] != context['workspace_id'] or boundary[1] != context['project_id'] \
                or principal['subject'] != context['actor_ref'] or boundary[6] != request['learning_snapshot_id']:
            _fail()
        timeline = boundary[3]
        if timeline['timeline_id'] != context['timeline_id'] or timeline['current_version'] != context['timeline_version'] \
                or timeline['current_version_id'] != context['timeline_version_id']:
            _fail()
        return {**value, 'principal': principal, 'intent_sha256': expected}
    except BrollPlanConflict:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
        _fail()


def settlement_key(project, actor, authority_sha, request_key):
    # Context is evidence, not part of the key: changing a context must never
    # revive a sealed original authority/key pair.
    return digest({'project_id': project, 'actor_ref': actor,
        'original_authority_sha256': authority_sha, 'request_key': request_key})


async def find_settlement(session, project, actor, authority_sha, request_key):
    return await session.scalar(select(ServiceOperationORM).where(
        ServiceOperationORM.service_id == SETTLEMENT_NAMESPACE,
        ServiceOperationORM.project_id == project, ServiceOperationORM.actor_ref == actor,
        ServiceOperationORM.key_sha256 == settlement_key(project, actor, authority_sha, request_key)))


def _snapshot(row):
    if row is None:
        return None
    return {k: (getattr(row, k).isoformat() if isinstance(getattr(row, k), datetime) else getattr(row, k))
        for k in ['operation_id', 'workspace_id', 'service_id', 'action', 'project_id', 'actor_ref',
            'key_sha256', 'request_sha256', 'status', 'response_status', 'response_json', 'response_sha256',
            'created_at', 'updated_at']}


async def _original(session, project, actor, intent):
    from .broll_plan_review_command import NAMESPACE, ACTION
    context, body = intent['context'], intent['body']
    rows = (await session.scalars(select(ServiceOperationORM).where(
        ServiceOperationORM.service_id == NAMESPACE, ServiceOperationORM.action == ACTION,
        ServiceOperationORM.project_id == project, ServiceOperationORM.actor_ref == actor,
        ServiceOperationORM.response_json['receipt']['request_key'].as_string() == body['request_key'],
        ServiceOperationORM.response_json['receipt']['authority_sha256'].as_string() == context['authority_sha256']
    ).with_for_update())).all()
    if len(rows) > 1:
        _fail('BROLL_RECOVERY_AMBIGUOUS')
    row = rows[0] if rows else None
    if row:
        public = _public(row, replayed=True)
        r = public['receipt']
        if r['context_sha256'] != context['context_sha256'] or r['settings'] != body['settings'] \
                or r['learning_snapshot_id'] != body['learning_snapshot_id'] or r['source'] != context['source'] \
                or r['timeline_id'] != context['timeline_id'] or r['timeline_version'] != context['timeline_version'] \
                or r['timeline_version_id'] != context['timeline_version_id'] or row.workspace_id != context['workspace_id']:
            _fail()
    return row


def _verify_identity(authority, intent, registry, row=None, sealed=None):
    old = intent['principal']
    if any(authority[k] != old[k] for k in ['subject', 'display_name', 'platform_role', 'workspace_roles']):
        _fail('BROLL_RECOVERY_AUTHORITY_CHANGED', 403)
    binding = (row.response_json or {}).get('_recovery_identity') if row else None
    if binding is None and sealed:
        binding = sealed.response_json.get('_verified_identity')
    if binding:
        if binding.get('authority') is None:
            # Legacy metadata alone cannot prove sha('Bearer '+old_token).
            # Never trust a client-rehashed opaque authority or old N1 seal.
            _fail('BROLL_RECOVERY_IDENTITY_UNVERIFIABLE')
        if binding.get('schema_version') != 'broll-recovery-identity.v1' \
                or binding.get('public_session') != old or binding.get('credential_sha256') != intent['credential_sha256'] \
                or digest(binding['authority']) != intent['context']['authority_sha256']:
            _fail()
        return binding
    # Identification metadata only. The request already passed fresh normal
    # authentication; expiration/enabled state here never authenticates anyone.
    candidates = [record for record in registry.tokens.values()
        if record.token_sha256 == intent['credential_sha256']]
    if len(candidates) != 1:
        _fail('BROLL_RECOVERY_IDENTITY_UNVERIFIABLE')
    record = candidates[0]
    public = {'subject': record.subject, 'display_name': record.display_name,
        'platform_role': record.platform_role, 'workspace_roles': dict(record.workspace_roles),
        'expires_at': record.expires_at.isoformat(), 'human_write_enabled': True}
    if public != old or record.token_id != authority['token_id'] \
            or digest(authority) != intent['context']['authority_sha256']:
        _fail('BROLL_RECOVERY_IDENTITY_UNVERIFIABLE')
    # With no server witness, only the exact currently authenticated original
    # authority is provable. An absent request cannot renew credentials here.
    return {'schema_version': 'broll-recovery-identity.v1', 'authority': authority,
        'credential_sha256': intent['credential_sha256'], 'public_session': old}


async def _current(service, session, project, authority, intent):
    current = await _context(service, session, project, authority, lock=True)
    original = intent['context']
    omitted = {'context_json', 'context_sha256', 'authority_sha256', 'can_prepare'}
    if not current['can_prepare'] or {k: v for k, v in current.items() if k not in omitted} \
            != {k: v for k, v in original.items() if k not in omitted}:
        _fail('BROLL_RECOVERY_SOURCE_CHANGED')
    return current


def _sealed_public(row):
    value = row.response_json
    if row.service_id != SETTLEMENT_NAMESPACE or row.action != SETTLEMENT_ACTION or row.status != 'succeeded' \
            or not isinstance(value, dict) or row.response_sha256 != digest(value) \
            or value.get('settlement', {}).get('settlement_id') != row.operation_id \
            or value['settlement'].get('actor_ref') != row.actor_ref:
        _fail('BROLL_RECOVERY_SETTLEMENT_INVALID')
    return {k: v for k, v in value.items() if not k.startswith('_')}


async def _observe(service, session, project, authority, registry, payload, *, witness_scope=None):
    intent = _intent(payload.intent_json, payload.intent_sha256)
    if intent['context']['project_id'] != project or intent['context']['actor_ref'] != authority['subject']:
        _fail('BROLL_RECOVERY_SCOPE_CHANGED', 403)
    target = await session.get(VideoProjectORM, project, with_for_update=True)
    if target is None:
        raise KeyError(project)
    if target.workspace_id != intent['context']['workspace_id']:
        _fail('BROLL_RECOVERY_SCOPE_CHANGED', 403)
    original = await _original(session, project, authority['subject'], intent)
    sealed = await find_settlement(session, project, authority['subject'],
        intent['context']['authority_sha256'], intent['body']['request_key'])
    if witness_scope is None:
        identity = _verify_identity(authority, intent, registry, original, sealed)
        current = await _current(service, session, project, authority, intent)
    else:
        from .broll_witnessed_recovery_command import WitnessRecoveryScope
        if not isinstance(witness_scope, WitnessRecoveryScope):
            _fail()
        # Verification is inside the same project transaction/lock, after all
        # original-operation and settlement reads. No client trust flag exists.
        identity, current = await witness_scope.verify(service, session, project, authority, intent, original)
    if sealed:
        public = _sealed_public(sealed)
        if public['intent_sha256'] != intent['intent_sha256']:
            _fail('BROLL_RECOVERY_INTENT_CHANGED')
    observed = {'original': _snapshot(original), 'settlement': _snapshot(sealed),
        'current_context_sha256': current['context_sha256'], 'authority_sha256': digest(authority),
        'intent_sha256': intent['intent_sha256']}
    if witness_scope is not None:
        observed['authorization_witness_sha256'] = identity['authorization_witness']['witness_sha256']
    observation = digest(observed)
    public_original = _public(original, replayed=True) if original else None
    return intent, identity, original, sealed, current, observation, public_original


def _read(intent, current, observation, original, settlement=None):
    return {'schema_version': 'broll-request-recovery.v1', 'state': 'settled' if settlement else 'observed',
        'workspace_id': intent['context']['workspace_id'], 'project_id': intent['context']['project_id'],
        'actor_ref': intent['context']['actor_ref'], 'intent_sha256': intent['intent_sha256'],
        'original_request_key': intent['body']['request_key'],
        'original_authority_sha256': intent['context']['authority_sha256'],
        'original_context_sha256': intent['context']['context_sha256'],
        'current_authority_sha256': current['authority_sha256'], 'current_context_sha256': current['context_sha256'],
        'source': current['source'], 'observation_sha256': observation,
        'original_result': original, 'preserved_plan': original.get('plan') if original else None,
        'preserved_plan_is_original_snapshot': True,
        'absent_credential_renewal_supported': False,
        'requires_server_identity_or_current_original_authority': True,
        'settlement': settlement, 'provider_calls': 0, 'source_media_mutated': False,
        'publish_requested': False, 'owner_approval_inferred': False}


async def inspect_request(service, project, authority, registry, payload, *, witness_scope=None):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            intent, _, original, sealed, current, observation, public = await _observe(
                service, session, project, authority, registry, payload, witness_scope=witness_scope)
            return _read(intent, current, observation, public,
                _sealed_public(sealed)['settlement'] if sealed else None)


async def abandon_request(service, project, authority, registry, payload, *, witness_scope=None):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session, write=True)
            intent, identity, original, sealed, current, observation, public = await _observe(
                service, session, project, authority, registry, payload, witness_scope=witness_scope)
            if sealed:
                return {**_sealed_public(sealed), 'current_authority_sha256': current['authority_sha256'],
                    'current_context_sha256': current['context_sha256']}
            if payload.observation_sha256 != observation:
                _fail('BROLL_RECOVERY_STALE_CAS')
            now = utc_now();identifier = 'sop_' + uuid.uuid4().hex
            receipt = {'schema_version': 'broll-request-settlement.v1', 'settlement_id': identifier,
                'actor_ref': authority['subject'], 'settled_by_authority_sha256': digest(authority),
                'intent_sha256': intent['intent_sha256'], 'original_request_key': intent['body']['request_key'],
                'original_authority_sha256': intent['context']['authority_sha256'],
                'original_context_sha256': intent['context']['context_sha256'],
                'observed_original_sha256': digest(_snapshot(original)), 'abandoned': True,
                'original_operation_id': original.operation_id if original else None,
                'created_at': now.isoformat(), 'provider_calls': 0}
            result = _read(intent, current, observation, public, receipt)
            stored = {**result, '_original_snapshot': _snapshot(original), '_verified_identity': identity,
                '_original_intent': intent}
            session.add(ServiceOperationORM(operation_id=identifier, workspace_id=intent['context']['workspace_id'],
                service_id=SETTLEMENT_NAMESPACE, action=SETTLEMENT_ACTION, project_id=project, actor_ref=authority['subject'],
                key_sha256=settlement_key(project, authority['subject'], intent['context']['authority_sha256'], intent['body']['request_key']),
                request_sha256=digest({'intent_sha256': intent['intent_sha256'], 'observation_sha256': observation}),
                status='succeeded', response_status=200, response_json=stored, response_sha256=digest(stored),
                created_at=now, updated_at=now))
            return result


async def read_settlement(service, project, authority, registry, identifier):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session)
            row = await session.get(ServiceOperationORM, identifier)
            if row is None or row.project_id != project or row.actor_ref != authority['subject']:
                raise KeyError(identifier)
            public = _sealed_public(row)
            intent = row.response_json['_original_intent']
            _verify_identity(authority, intent, registry, sealed=row)
            current = await _current(service, session, project, authority, intent)
            return {**public, 'current_authority_sha256': current['authority_sha256'],
                'current_context_sha256': current['context_sha256']}


async def record_late_result(session, sealed, original, plan=None, error_code=None):
    key = digest({'settlement': sealed.operation_id, 'original': original.operation_id})
    old = await session.scalar(select(ServiceOperationORM).where(
        ServiceOperationORM.service_id == LATE_NAMESPACE, ServiceOperationORM.key_sha256 == key,
        ServiceOperationORM.workspace_id == sealed.workspace_id))
    value = {'schema_version': 'broll-late-result.v1', 'settlement_id': sealed.operation_id,
        'original_operation_id': original.operation_id, 'project_id': original.project_id,
        'actor_ref': original.actor_ref, 'plan': plan, 'read_only': True, 'error_code': error_code,
        'provider_calls': 0, 'source_media_mutated': False, 'publish_requested': False}
    if old:
        if old.response_json != value or old.response_sha256 != digest(value):
            _fail('BROLL_RECOVERY_LATE_RESULT_CHANGED')
        return
    now = utc_now()
    session.add(ServiceOperationORM(operation_id='sop_' + uuid.uuid4().hex, workspace_id=sealed.workspace_id,
        service_id=LATE_NAMESPACE, action='broll.request.late-result.v1', project_id=original.project_id,
        actor_ref=original.actor_ref, key_sha256=key, request_sha256=original.request_sha256,
        status='succeeded', response_status=200, response_json=value, response_sha256=digest(value),
        created_at=now, updated_at=now))


async def record_failed_after_settlement(service, project, authority, identifier, plan):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await _begin(session, write=True)
            await session.get(VideoProjectORM, project, with_for_update=True)
            original = await session.get(ServiceOperationORM, identifier, with_for_update=True)
            sealed = await find_settlement(session, project, authority['subject'], digest(authority),
                original.response_json['receipt']['request_key']) if original else None
            if sealed:
                await record_late_result(session, sealed, original,
                    plan.model_dump(mode='json') if hasattr(plan, 'model_dump') else None,
                    error_code='BROLL_PREPARATION_FAILED')
                return True
    return False


async def read_late_results(service, project, authority, registry, identifier):
    await read_settlement(service, project, authority, registry, identifier)
    async with service.repository.session_factory() as session:
        rows = (await session.scalars(select(ServiceOperationORM).where(
            ServiceOperationORM.service_id == LATE_NAMESPACE, ServiceOperationORM.project_id == project,
            ServiceOperationORM.actor_ref == authority['subject'],
            ServiceOperationORM.response_json['settlement_id'].as_string() == identifier))).all()
        for row in rows:
            if row.status != 'succeeded' or row.response_sha256 != digest(row.response_json):
                _fail('BROLL_RECOVERY_LATE_RESULT_INVALID')
        return [row.response_json for row in rows]
