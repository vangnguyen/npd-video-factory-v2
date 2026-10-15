"""Fenced scheduling for frozen, unpaid stock searches on the canonical MediaPlan."""
import copy
import math
import re
import uuid
from sqlalchemy import select, update
from .db import utc_now
from .media_intelligence_db import MediaPlanORM, MediaPlanStockEventORM
from .stock_wire_quota import digest
from .stock_planner_models import StockPlanningRead, StockPlannerHistoryRead

KEY = 'stock_planner_execution'
LEASE_SECONDS = 300
MAX_FAILED_WIRE_CYCLES = 3
TERMINAL = {'succeeded', 'failed', 'cancelled'}


class StockPlannerConflict(ValueError):
    pass


def clock(stamp):
    if type(stamp) not in (float, int) or not math.isfinite(stamp) or stamp < 0:
        raise ValueError('STOCK_PLANNER_CLOCK_INVALID')
    return float(stamp)


def state(provenance):
    value = provenance.get(KEY)
    if value is None:
        return None
    if not isinstance(value, dict) or value.get('schema_version') != 'sql-stock-planner.v1' \
            or value.get('status') not in {'waiting', 'running', *TERMINAL} \
            or digest(value.get('binding')) != value.get('binding_sha256'):
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    binding = value['binding']
    if binding.get('schema_version') != 'sql-stock-planner-binding.v1' or binding.get('paid') is not False \
            or digest(binding.get('inputs')) != binding.get('inputs_sha256') \
            or binding.get('provider', {}).get('paid') is not False:
        raise ValueError('STOCK_PLANNER_BINDING_INVALID')
    inputs = binding['inputs']
    if binding.get('source_file_sha256') != inputs.get('source_asset', {}).get('checksum_sha256') \
            or binding.get('budget_sha256') != digest({'max_ai_cost_vnd': str(inputs.get('configuration', {}).get('max_ai_cost_vnd')), 'paid': False}):
        raise ValueError('STOCK_PLANNER_BINDING_INVALID')
    statuses = inputs.get('provider_status', {})
    availability = {'stock': statuses.get('stock', {}).get('status') == 'healthy',
        'image': statuses.get('image_generation', {}).get('status') == 'healthy',
        'video': statuses.get('video_generation', {}).get('status') == 'healthy'}
    if binding.get('availability') != availability:
        raise ValueError('STOCK_PLANNER_BINDING_INVALID')
    searches = binding.get('searches')
    if not isinstance(searches, list) or not searches or len(searches) > 1000:
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    identifiers = [request.get('scene_id') for request in searches if isinstance(request, dict)]
    if len(identifiers) != len(searches) or len(set(identifiers)) != len(identifiers):
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    for request in searches:
        if set(request) != {'scene_id', 'strategy', 'query', 'orientation', 'limit'} \
                or request['strategy'] not in {'stock_image', 'stock_video'} \
                or not isinstance(request['query'], str) or not 1 <= len(request['query']) <= 500 \
                or request['orientation'] not in {'portrait', 'landscape', 'square', 'any'} or request['limit'] != 3:
            raise ValueError('STOCK_PLANNER_STATE_INVALID')
    if not isinstance(value.get('results'), dict) or not isinstance(value.get('failed_wire_cycles'), dict):
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    for scene, result in value['results'].items():
        if scene not in identifiers or not isinstance(result, dict) or set(result) != {'candidates', 'sha256'} \
                or not isinstance(result['candidates'], list) or digest(result['candidates']) != result['sha256']:
            raise ValueError('STOCK_PLANNER_RESULT_INVALID')
    for scene, failures in value['failed_wire_cycles'].items():
        if scene not in identifiers or type(failures) is not int or not 0 <= failures <= MAX_FAILED_WIRE_CYCLES:
            raise ValueError('STOCK_PLANNER_STATE_INVALID')
    for field in ('next_at', 'lease_until'):
        if value.get(field) is not None:
            clock(value[field])
    if (value.get('claim_id') is None) != (value.get('lease_until') is None) \
            or value.get('claim_id') is not None and not re.fullmatch(r'[a-f0-9]{32}', value['claim_id']) \
            or type(value.get('provider_calls')) is not int or value['provider_calls'] < 0:
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    if 'review_required' in value and type(value['review_required']) is not bool:
        raise ValueError('STOCK_PLANNER_STATE_INVALID')
    return copy.deepcopy(value)


def read(provenance):
    value = state(provenance)
    if value is None:
        return None
    return StockPlanningRead(status=value['status'], binding_sha256=value['binding_sha256'],
        next_at=value['next_at'], lease_until=value['lease_until'], completed_searches=len(value['results']),
        total_searches=len(value['binding']['searches']), failed_wire_cycles=value['failed_wire_cycles'],
        error_code=value['error_code'], retryable=value['status'] == 'waiting', provider_calls=value['provider_calls'])


def snapshot(row):
    value = state(row.provenance_json)
    return {'media_plan_id': row.media_plan_id, 'workspace_id': row.workspace_id,
        'project_id': row.project_id, 'project_version_id': row.project_version_id,
        'version': row.version, 'fingerprint': row.fingerprint, 'status': row.status,
        'configuration': row.configuration_json, 'provider_status': row.provider_status_json,
        'max_ai_cost_vnd': str(row.max_ai_cost_vnd), 'error_code': row.error_code,
        'stock_planning': value, 'paid_replay_authorized': False, 'publishing_authorized': False}


def transition(session, row, value, action, *, details=None, before=None):
    previous = snapshot(row) if before is None else before
    row.provenance_json = {**row.provenance_json, KEY: value}
    row.status = {'waiting': 'stock_waiting', 'running': 'stock_searching', 'succeeded': 'draft',
        'failed': 'failed', 'cancelled': 'cancelled'}[value['status']]
    row.error_code = value['error_code']
    row.version += 1
    row.updated_at = utc_now()
    evidence = {'schema_version': 'sql-stock-planner-event.v1', 'before': previous,
        'after': snapshot(row), 'details': details or {}, 'owner_approval_inferred': False}
    session.add(MediaPlanStockEventORM(event_id='spe_'+uuid.uuid4().hex, media_plan_id=row.media_plan_id,
        workspace_id=row.workspace_id, version=row.version, action=action,
        evidence_json=evidence, evidence_sha256=digest(evidence)))


async def locked(session, identity):
    result = await session.execute(update(MediaPlanORM).where(MediaPlanORM.media_plan_id == identity)
        .values(updated_at=MediaPlanORM.updated_at))
    if result.rowcount != 1:
        raise KeyError(identity)
    return await session.get(MediaPlanORM, identity, with_for_update=True, populate_existing=True)


def owned(value, claim_id, stamp=None):
    return value is not None and value['status'] == 'running' and value['claim_id'] == claim_id \
        and (stamp is None or value['lease_until'] > clock(stamp))


async def initialize(repository, identity, binding, stamp, *, require_review=False):
    stamp = clock(stamp)
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity)
        if state(row.provenance_json) is not None:
            return
        value = {'schema_version': 'sql-stock-planner.v1', 'binding': binding,
            'binding_sha256': digest(binding), 'status': 'waiting', 'next_at': stamp,
            'claim_id': None, 'lease_until': None, 'results': {}, 'failed_wire_cycles': {},
            'provider_calls': 0, 'error_code': None,
            **({'review_required': True} if require_review else {})}
        transition(session, row, value, 'scheduled', details={'wire_calls': 0})


async def claim(repository, identity, stamp, *, expected_version=None, binding_sha256=None, allow_claim=True):
    stamp = clock(stamp)
    reviewed = expected_version is not None or binding_sha256 is not None
    if reviewed and (type(expected_version) is not int or expected_version < 1
            or not isinstance(binding_sha256, str) or not re.fullmatch(r'[a-f0-9]{64}', binding_sha256)):
        raise ValueError('STOCK_PLANNER_REVIEW_INVALID')
    if type(allow_claim) is not bool:
        raise ValueError('STOCK_PLANNER_CLAIM_PERMISSION_INVALID')
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity)
        value = state(row.provenance_json)
        # A reviewed HTTP retry must fence the claim itself, not a prior read.
        # Workers can checkpoint/defer between that read and this transaction.
        if reviewed and (value is None or row.version != expected_version
                or value['binding_sha256'] != binding_sha256):
            raise StockPlannerConflict('STOCK_PLANNER_REVIEW_STALE')
        if value is not None and value.get('review_required') is True and not reviewed:
            return None
        if not allow_claim or value is None or value['status'] in TERMINAL or value['next_at'] is not None and value['next_at'] > stamp \
                or value['claim_id'] is not None and value['lease_until'] > stamp:
            return None
        expired = value['claim_id'] is not None
        claim_id = uuid.uuid4().hex
        value.update(status='running', claim_id=claim_id, lease_until=stamp+LEASE_SECONDS, next_at=None)
        if value.get('review_required') is True:
            value['review_required'] = False
        transition(session, row, value, 'claimed', details={'expired_read_lease': expired,
            'unknown_outcome': expired, 'paid_replay_authorized': False, 'wire_calls': 0})
        return claim_id


async def checkpoint(repository, identity, claim_id, scene_id, candidates, calls, *, stamp=None):
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity);value = state(row.provenance_json)
        if not owned(value, claim_id, stamp):
            return False
        if scene_id in value['results']:
            return value['results'][scene_id]['candidates'] == candidates
        value['results'][scene_id] = {'candidates': candidates, 'sha256': digest(candidates)}
        value['provider_calls'] += calls
        if stamp is not None:
            value['lease_until'] = clock(stamp)+LEASE_SECONDS
        transition(session, row, value, 'search_checkpointed', details={'scene_id': scene_id, 'wire_calls': calls})
        return True


async def wait(repository, identity, claim_id, *, scene_id, code, next_at, calls, stamp):
    stamp = clock(stamp);next_at = clock(next_at)
    if next_at < stamp or type(calls) is not int or calls < 0:
        raise ValueError('STOCK_PLANNER_WAIT_INVALID')
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity);value = state(row.provenance_json)
        if not owned(value, claim_id, stamp):
            return False
        value['provider_calls'] += calls
        if calls:
            value['failed_wire_cycles'][scene_id] = value['failed_wire_cycles'].get(scene_id, 0)+1
        exhausted = value['failed_wire_cycles'].get(scene_id, 0) >= MAX_FAILED_WIRE_CYCLES
        value.update(status='failed' if exhausted else 'waiting', claim_id=None, lease_until=None,
            next_at=None if exhausted else next_at, error_code='STOCK_PLANNER_RETRY_EXHAUSTED' if exhausted else code)
        transition(session, row, value, 'retry_exhausted' if exhausted else 'deferred',
            details={'scene_id': scene_id, 'wire_calls': calls, 'retry_cycle_consumed': bool(calls),
                'paid_operations': 0, 'observed_at': stamp})
        return True


async def fail(repository, identity, claim_id, code, *, calls=0, stamp=None):
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity);value = state(row.provenance_json)
        if not owned(value, claim_id, stamp):
            return False
        value['provider_calls'] += calls
        value.update(status='failed', claim_id=None, lease_until=None, next_at=None, error_code=code)
        transition(session, row, value, 'failed', details={'code': code})
        return True


async def cancel(repository, identity, expected_version, binding_sha256):
    async with repository.session_factory() as session, session.begin():
        row = await locked(session, identity);value = state(row.provenance_json)
        if value is None:
            raise StockPlannerConflict('STOCK_PLANNER_NOT_MANAGED')
        if row.version != expected_version or value['binding_sha256'] != binding_sha256:
            raise StockPlannerConflict('STOCK_PLANNER_REVIEW_STALE')
        if value['status'] in TERMINAL:
            return
        value.update(status='cancelled', claim_id=None, lease_until=None, next_at=None, error_code=None)
        transition(session, row, value, 'cancelled', details={'wire_calls': 0})


async def due(repository, stamp, limit=25):
    stamp = clock(stamp)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('STOCK_PLANNER_RECOVERY_LIMIT_INVALID')
    async with repository.session_factory() as session:
        rows = (await session.scalars(select(MediaPlanORM).where(MediaPlanORM.status.in_(
            ['stock_waiting', 'stock_searching'])).order_by(MediaPlanORM.created_at))).all()
        result = []
        for row in rows:
            value = state(row.provenance_json)
            if value is not None and value.get('review_required') is not True and value['binding'].get('paid') is False and (
                value['claim_id'] is not None and value['lease_until'] <= stamp
                or value['claim_id'] is None and value['next_at'] is not None and value['next_at'] <= stamp):
                result.append(row.media_plan_id)
            if len(result) == limit:
                break
        return result


async def history(repository, identity):
    async with repository.session_factory() as session:
        rows = (await session.scalars(select(MediaPlanStockEventORM).where(
            MediaPlanStockEventORM.media_plan_id == identity).order_by(MediaPlanStockEventORM.version))).all()
        if any(digest(row.evidence_json) != row.evidence_sha256 for row in rows):
            raise ValueError('STOCK_PLANNER_HISTORY_INVALID')
        return [StockPlannerHistoryRead(event_id=row.event_id, media_plan_id=identity, version=row.version,
            action=row.action, evidence=row.evidence_json, sha256=row.evidence_sha256) for row in rows]
