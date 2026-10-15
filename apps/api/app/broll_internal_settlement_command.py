"""Append-only release of a known terminal internal-resolution intent.

This command never adopts output, changes a source or rewrites the original
job. An existing authenticated admission is the only original-authority proof.
"""
import copy
import hashlib
import json
import re
import uuid

from sqlalchemy import select

from .broll_internal_resolution_core import (
    InternalResolutionConflict, admission, begin, marked_admission, require, row_value, operation_key,
)
from .db import VideoProjectORM, utc_now
from .media_intelligence_db import MediaResolutionJobORM
from .media_intelligence_repository import _resolution_job_read
from .service_api_repository import ServiceOperationORM, digest

NAMESPACE = 'human:broll-internal-terminal-settlement.v1'
ACTION = 'broll.internal.terminal-settle.v1'
TERMINAL = {'failed', 'cancelled', 'succeeded'}
INTENT_FIELDS = {'schema_version', 'body', 'context', 'core_sha256',
    'principal_sha256', 'credential_sha256', 'receipt'}
AUTHORITY_FIELDS = {'token_id', 'subject', 'display_name', 'platform_role',
    'workspace_roles', 'expires_at', 'credential_sha256'}
MAX_INTENT_BYTES = 5 * 1024 * 1024
CODE = 'BROLL_INTERNAL_SETTLEMENT_INVALID'


def _hash(value):
    return isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value) is not None


def _guard(authority, guard):
    if not callable(guard) or guard() != authority:
        raise InternalResolutionConflict('BROLL_INTERNAL_SETTLEMENT_AUTHORITY_CHANGED', 403)


def _snapshot(row):
    return copy.deepcopy(row_value(row)) if row is not None else None


def _parse(raw, expected):
    def unique(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError()
            result[key] = value
        return result
    def invalid(_value):
        raise ValueError()
    try:
        require(isinstance(raw, str) and 0 < len(raw.encode()) <= MAX_INTENT_BYTES
            and _hash(expected) and hashlib.sha256(raw.encode()).hexdigest() == expected, CODE)
        value = json.loads(raw, object_pairs_hook=unique, parse_constant=invalid)
        require(isinstance(value, dict) and set(value) == INTENT_FIELDS
            and value['schema_version'] == 'sql-broll-internal-pending.v1'
            and all(_hash(value[k]) for k in ('core_sha256', 'principal_sha256', 'credential_sha256'))
            and isinstance(value['receipt'], dict), 'BROLL_INTERNAL_KNOWN_RECEIPT_REQUIRED')
        from .broll_internal_resolution_api import InternalResolutionRequest
        require(InternalResolutionRequest.model_validate(value['body']).model_dump(mode='json') == value['body'], CODE)
        require(re.fullmatch(r'sop_[a-f0-9]{32}', value['receipt'].get('operation_id', '')) is not None, CODE)
        return value
    except (InternalResolutionConflict,):
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise InternalResolutionConflict(CODE) from None


def _proof(op, saved, intent):
    try:
        p, receipt = saved['private'], saved['receipt']
        authority, context, body = p['authority'], p['context'], intent['body']
        require(isinstance(authority, dict) and set(authority) == AUTHORITY_FIELDS
            and authority['subject'] == op.actor_ref and _hash(authority['credential_sha256'])
            and op.response_status == 202 and op.key_sha256 == operation_key(authority, op.project_id, body['request_key'])
            and digest(authority) == receipt['authority_sha256']
            and receipt['schema_version'] == 'broll-internal-resolution-receipt.v1'
            and type(receipt['provider_calls']) is int and receipt['provider_calls'] == 0
            and receipt['publishing_enabled'] is False and receipt['owner_approval_inferred'] is False
            and intent['receipt'] == receipt and intent['context'] == context
            and body['request_key'] == receipt['request_key'] and body['asset_id'] == receipt['asset_id']
            and body['context_sha256'] == receipt['context_sha256'] == context['context_sha256']
            and digest({'project_id': op.project_id, 'plan_id': receipt['media_plan_id'],
                'item_id': receipt['media_plan_item_id'], 'authority': authority, 'request': body}) == op.request_sha256,
            CODE)
        literal = context['context_json']
        require(isinstance(literal, str) and hashlib.sha256(literal.encode()).hexdigest() == context['context_sha256']
            and json.loads(literal) == {k:v for k,v in context.items() if k not in {'context_json', 'context_sha256'}}
            and context['workspace_id'] == op.workspace_id and context['project_id'] == op.project_id
            and context['actor_ref'] == op.actor_ref and context['authority_sha256'] == receipt['authority_sha256']
            and type(context['provider_calls']) is int and context['provider_calls'] == 0
            and context['publishing_enabled'] is False and context['owner_approval_inferred'] is False
            and context['source'] == receipt['source'] and context['timeline_id'] == receipt['timeline_id']
            and context['timeline_version'] == receipt['timeline_version']
            and context['timeline_version_id'] == receipt['timeline_version_id']
            and digest(p['selected_asset_custody']) == receipt['asset_custody_sha256']
            and p['selected_asset_custody']['asset_id'] == receipt['asset_id'], CODE)
        public = {k:v for k,v in authority.items() if k not in {'token_id', 'credential_sha256'}}
        public['human_write_enabled'] = True
        require(digest(public) == intent['principal_sha256'], CODE)
        # Client raw-token/core hashes are opaque local binding metadata. They
        # do not prove authentication and are never converted to Bearer hashes.
        return authority
    except InternalResolutionConflict:
        raise
    except (ValueError, TypeError, KeyError, RecursionError):
        raise InternalResolutionConflict(CODE) from None


def _same_actor(current, original):
    if not all(current[k] == original[k] for k in ('subject', 'display_name', 'platform_role', 'workspace_roles')):
        raise InternalResolutionConflict('BROLL_INTERNAL_SETTLEMENT_AUTHORITY_CHANGED', 403)


def _key(op, saved):
    r = saved['receipt']
    return digest({'namespace': NAMESPACE, 'workspace_id': op.workspace_id,
        'project_id': op.project_id, 'actor_ref': op.actor_ref, 'original_operation_id': op.operation_id,
        'original_authority_sha256': r['authority_sha256'], 'original_request_key': r['request_key']})


def _public(row, op, saved):
    try:
        value = row.response_json
        require(row.service_id == NAMESPACE and row.action == ACTION and row.status == 'succeeded'
            and row.response_status == 200 and row.workspace_id == op.workspace_id and row.project_id == op.project_id
            and row.actor_ref == op.actor_ref and row.key_sha256 == _key(op, saved)
            and isinstance(value, dict) and set(value) == {'public', 'private'}
            and row.response_sha256 == digest(value), CODE)
        result, p = value['public'], value['private']
        intent = _parse(p['intent_json'], result['intent_sha256'])
        _proof(op, saved, intent)
        observed = p['observation']
        require(result['schema_version'] == 'broll-internal-terminal-settlement.v1'
            and result['state'] == 'settled' and result['settlement']['settlement_id'] == row.operation_id
            and result['settlement']['decision'] == 'release_held_intent'
            and result['settlement']['current_output_adopted'] is False and result['settlement']['provider_calls'] == 0
            and result['settlement']['original_operation_id'] == op.operation_id
            and result['settlement']['resolution_job_id'] == result['job']['resolution_job_id']
            and result['settlement']['terminal_status'] == result['job']['status']
            and result['admission_receipt'] == saved['receipt']
            and result['workspace_id'] == op.workspace_id and result['project_id'] == op.project_id
            and result['actor_ref'] == op.actor_ref and result['original_operation_id'] == op.operation_id
            and result['job']['resolution_job_id'] == saved['receipt']['resolution_job_id']
            and result['job']['status'] in TERMINAL and result['output'] is None and result['can_adopt'] is False
            and result['provider_calls'] == 0 and result['publishing_enabled'] is False
            and result['owner_approval_inferred'] is False and result['original_job_preserved'] is True
            and observed['original_operation_sha256'] == digest(_snapshot(op))
            and observed['intent_sha256'] == result['intent_sha256'] and observed['settlement'] is None
            and observed['current_authority_sha256'] == result['settlement']['settled_by_authority_sha256']
            and observed['job']['resolution_job_id'] == result['job']['resolution_job_id']
            and observed['job']['status'] == result['job']['status']
            and observed['job_public_sha256'] == digest(result['job'])
            and observed['worker_claim_status'] == result['worker_claim_status']
            and observed['worker_claim_present'] is result['worker_claim_present']
            and digest(observed) == result['observation_sha256']
            and row.request_sha256 == digest({'intent_sha256': result['intent_sha256'],
                'observation_sha256': result['observation_sha256'], 'decision': 'release_held_intent'}), CODE)
        return copy.deepcopy(result)
    except InternalResolutionConflict:
        raise
    except (KeyError, TypeError, ValueError, RecursionError):
        raise InternalResolutionConflict(CODE) from None


async def settlement_for(session, op, saved):
    """Verified namespace only. No current-source requirement or SQL mutation."""
    row = await session.scalar(select(ServiceOperationORM).where(
        ServiceOperationORM.service_id == NAMESPACE, ServiceOperationORM.workspace_id == op.workspace_id,
        ServiceOperationORM.key_sha256 == _key(op, saved)).execution_options(populate_existing=True))
    if row is not None:
        _public(row, op, saved)
    return row


async def require_unsettled(session, op, saved):
    require(await settlement_for(session, op, saved) is None, 'BROLL_INTERNAL_REQUEST_SETTLED')


async def _observe(service, session, project_id, plan_id, item_id, authority, payload, guard):
    from .broll_internal_resolution_worker import job_row, own_claim, claim_id
    intent = _parse(payload.intent_json, payload.intent_sha256)
    target = await session.scalar(select(VideoProjectORM).where(VideoProjectORM.project_id == project_id)
        .with_for_update().execution_options(populate_existing=True))
    _guard(authority, guard)
    if target is None:
        raise KeyError(project_id)
    operation_id = intent['receipt']['operation_id']
    op, saved = await admission(session, operation_id)
    _guard(authority, guard)
    original = _proof(op, saved, intent)
    _same_actor(authority, original)
    receipt = saved['receipt']
    require(op.project_id == project_id and op.workspace_id == target.workspace_id
        and receipt['media_plan_id'] == plan_id and receipt['media_plan_item_id'] == item_id,
        'BROLL_INTERNAL_SETTLEMENT_SCOPE_CHANGED')
    job = await job_row(session, receipt['resolution_job_id'], True)
    _guard(authority, guard)
    linked, linked_saved = await marked_admission(session, job)
    _guard(authority, guard)
    require(linked.operation_id == op.operation_id and linked_saved == saved, CODE)
    require(job.status in TERMINAL, 'BROLL_INTERNAL_TERMINAL_JOB_REQUIRED')
    claim = await session.get(ServiceOperationORM, claim_id(job.resolution_job_id), with_for_update=True,
        populate_existing=True)
    _guard(authority, guard)
    if claim is not None:
        claim = await own_claim(session, job)
        _guard(authority, guard)
        proof = claim.response_json
        expected = saved['private']['selected_asset_custody']
        require(claim.status in {'running', 'succeeded', 'rejected'}
            and re.fullmatch('[a-f0-9]{32}', proof['token']) is not None
            and (proof['byte_proof'] is None or proof['byte_proof'] == expected)
            and (proof['materialization_started'] is False or proof['byte_proof'] == expected), CODE)
    if job.status == 'succeeded':
        require(claim is not None and claim.status == 'succeeded' and isinstance(job.output_media_asset_id, str)
            and job.output_media_asset_id and claim.response_json['materialization_started'] is True
            and claim.response_json['byte_proof'] == saved['private']['selected_asset_custody'],
            'BROLL_INTERNAL_TERMINAL_PROOF_REQUIRED')
    sealed = await settlement_for(session, op, saved)
    _guard(authority, guard)
    if sealed is not None:
        result = _public(sealed, op, saved)
        require(result['intent_sha256'] == payload.intent_sha256, 'BROLL_INTERNAL_SETTLEMENT_INTENT_CHANGED')
        return intent, op, saved, job, sealed, result, None
    job_public = _resolution_job_read(job).model_dump(mode='json')
    observed = {'original_operation_sha256': digest(_snapshot(op)), 'job': _snapshot(job), 'job_public_sha256': digest(job_public),
        'worker_claim_sha256': digest(_snapshot(claim)), 'intent_sha256': payload.intent_sha256,
        'worker_claim_status': claim.status if claim else None, 'worker_claim_present': claim is not None,
        'current_authority_sha256': digest(authority), 'settlement': None}
    result = {'schema_version': 'broll-internal-terminal-settlement.v1', 'state': 'observed',
        'workspace_id': target.workspace_id, 'project_id': project_id, 'actor_ref': authority['subject'],
        'original_operation_id': op.operation_id, 'intent_sha256': payload.intent_sha256,
        'admission_receipt': copy.deepcopy(receipt), 'job': job_public,
        'worker_claim_present': claim is not None, 'worker_claim_status': claim.status if claim else None,
        'observation_sha256': digest(observed), 'settlement': None,
        'can_adopt': False, 'output': None, 'original_job_preserved': True,
        'provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}
    return intent, op, saved, job, None, result, observed


async def inspect(service, project_id, plan_id, item_id, authority, payload, authority_guard):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session)
            _guard(authority, authority_guard)
            *_, result, _observed = await _observe(service, session, project_id, plan_id, item_id,
                authority, payload, authority_guard)
            _guard(authority, authority_guard)
            return result


async def settle(service, project_id, plan_id, item_id, authority, payload, authority_guard):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session, True)
            _guard(authority, authority_guard)
            _, op, saved, _, sealed, result, observed = await _observe(service, session,
                project_id, plan_id, item_id, authority, payload, authority_guard)
            _guard(authority, authority_guard)
            if sealed is not None:
                return result
            require(payload.observation_sha256 == result['observation_sha256'], 'BROLL_INTERNAL_SETTLEMENT_STALE_CAS')
            stamp, identifier = utc_now(), 'sop_' + uuid.uuid4().hex
            result = {**result, 'state': 'settled', 'settlement': {
                'settlement_id': identifier, 'decision': 'release_held_intent',
                'settled_by_authority_sha256': digest(authority), 'created_at': stamp.isoformat(),
                'original_operation_id': op.operation_id, 'resolution_job_id': result['job']['resolution_job_id'],
                'terminal_status': result['job']['status'], 'current_output_adopted': False,
                'provider_calls': 0}}
            value = {'public': result, 'private': {'intent_json': payload.intent_json, 'observation': observed}}
            _guard(authority, authority_guard)  # No await between final authority and first insert.
            session.add(ServiceOperationORM(operation_id=identifier, workspace_id=op.workspace_id,
                service_id=NAMESPACE, action=ACTION, project_id=op.project_id, actor_ref=op.actor_ref,
                key_sha256=_key(op, saved), request_sha256=digest({'intent_sha256': payload.intent_sha256,
                    'observation_sha256': result['observation_sha256'], 'decision': 'release_held_intent'}),
                status='succeeded', response_status=200, response_json=value, response_sha256=digest(value),
                created_at=stamp, updated_at=stamp))
            await session.flush()
            _guard(authority, authority_guard)
            return copy.deepcopy(result)


async def read(service, project_id, plan_id, item_id, authority, identifier, authority_guard):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session)
            _guard(authority, authority_guard)
            row = await session.get(ServiceOperationORM, identifier, populate_existing=True)
            _guard(authority, authority_guard)
            if row is None or row.service_id != NAMESPACE or row.project_id != project_id or row.actor_ref != authority['subject']:
                raise KeyError(identifier)
            try:
                operation_id = row.response_json['public']['original_operation_id']
                op, saved = await admission(session, operation_id)
                _guard(authority, authority_guard)
                target = await session.get(VideoProjectORM, project_id, populate_existing=True)
                _guard(authority, authority_guard)
                require(target is not None and target.workspace_id == op.workspace_id
                    and saved['receipt']['media_plan_id'] == plan_id and saved['receipt']['media_plan_item_id'] == item_id,
                    'BROLL_INTERNAL_SETTLEMENT_SCOPE_CHANGED')
                _same_actor(authority, saved['private']['authority'])
                result = _public(row, op, saved)
                _guard(authority, authority_guard)
                return result
            except InternalResolutionConflict:
                raise
            except (KeyError, TypeError, ValueError):
                raise InternalResolutionConflict(CODE) from None
