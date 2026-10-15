"""Owned internal job attempts; SQL is authoritative across Redis uncertainty."""
from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

from sqlalchemy import select

from .db import VideoProjectORM, utc_now
from .media_intelligence_db import MediaPlanItemORM, MediaResolutionJobORM, MediaAssetProvenanceORM
from .media_intelligence_repository import _resolution_job_read, _media_asset_read
from .service_api_repository import ServiceOperationORM, digest
from .frozen_storage_read import frozen_asset_read, asset_custody, MAX_SOURCE_BYTES
from .source_linked_edit_command import SourceLinkedConflict
from .broll_internal_resolution_core import (CLAIM_NAMESPACE, CLAIM_ACTION, MARKER,
    InternalResolutionConflict, begin, context, require, has_marker, marked_admission, admission)

QUEUE_KEY = 'npd:video-factory:v2:media-resolution:queued'
QUEUE_DEDUPE = "redis.call('LREM', KEYS[1], 0, ARGV[1]); return redis.call('RPUSH', KEYS[1], ARGV[1])"


def claim_id(job_id):
    return 'sop_' + digest({'namespace': CLAIM_NAMESPACE, 'job': job_id})[:32]


async def job_row(session, identifier, lock=False):
    query = select(MediaResolutionJobORM).where(MediaResolutionJobORM.resolution_job_id == identifier)
    job = await session.scalar((query.with_for_update() if lock else query).execution_options(populate_existing=True))
    if job is None:
        raise KeyError(identifier)
    return job


async def reviewed_project(session, identifier):
    # Classify without populating an ORM identity for an unmarked legacy job.
    # Its original later FOR UPDATE must still read fresh cancellation state.
    row = (await session.execute(select(MediaResolutionJobORM.project_id,
        MediaResolutionJobORM.provenance_json).where(
            MediaResolutionJobORM.resolution_job_id == identifier))).first()
    if row is None:
        raise KeyError(identifier)
    return row.project_id if isinstance(row.provenance_json, dict) and MARKER in row.provenance_json else None


async def own_claim(session, job, token=None, *, lock=True):
    row = await session.get(ServiceOperationORM, claim_id(job.resolution_job_id), with_for_update=lock)
    require(row is not None and row.service_id == CLAIM_NAMESPACE and row.action == CLAIM_ACTION
            and row.project_id == job.project_id and row.workspace_id == job.workspace_id
            and isinstance(row.response_json, dict) and row.response_sha256 == digest(row.response_json)
            and row.response_json.get('job_id') == job.resolution_job_id,
            'BROLL_INTERNAL_CLAIM_INVALID')
    _, saved = await marked_admission(session, job)
    require(row.actor_ref == 'worker:reviewed-internal-media'
            and row.key_sha256 == digest({'job_id': job.resolution_job_id})
            and row.request_sha256 == digest({'job_id': job.resolution_job_id,
                'request_sha256': saved['receipt']['request_sha256']})
            and row.response_json.get('operation_id') == saved['receipt']['operation_id']
            and set(row.response_json) == {'job_id', 'operation_id', 'token', 'materialization_started', 'byte_proof'}
            and isinstance(row.response_json.get('token'), str) and len(row.response_json['token']) == 32
            and type(row.response_json.get('materialization_started')) is bool,
            'BROLL_INTERNAL_CLAIM_INVALID')
    if token is not None:
        require(row.status == 'running' and row.response_json.get('token') == token,
                'BROLL_INTERNAL_CLAIM_LOST')
    return row


async def bound(session, job, saved, *, lock=False, materialized_asset=None, terminal=False):
    p, r = saved['private'], saved['receipt']
    value, item, assets = await context(session, job.project_id, job.media_plan_id,
        job.media_plan_item_id, p['authority'], lock=lock, original_item=p['item_input'])
    if terminal:
        require(job.status == 'succeeded' and item.status == 'resolved'
                and item.selected_media_asset_id == job.output_media_asset_id,
                'BROLL_INTERNAL_OUTPUT_SUPERSEDED')
    else:
        require(item.status == 'resolving'
                and item.selected_media_asset_id == p['item_input']['selected_media_asset_id']
                and item.needs_attention == p['item_input']['needs_attention'],
                'BROLL_INTERNAL_ITEM_CHANGED')
    require(value['context_sha256'] == r['context_sha256'], 'BROLL_INTERNAL_SOURCE_CHANGED')
    asset = assets[r['asset_id']]
    require(asset_custody(asset) == p['selected_asset_custody'], 'BROLL_INTERNAL_ASSET_CHANGED')
    if materialized_asset is not None:
        require(asset_custody(materialized_asset) == p['selected_asset_custody'],
                'BROLL_INTERNAL_MATERIALIZED_ASSET_CHANGED')
    return asset, item


def valid_evidence(e, asset):
    measured = asset.provenance['media_metadata']
    require(e.asset_id == asset.asset_id and e.project_id == asset.project_id and e.workspace_id == asset.workspace_id
            and e.provenance.get('asset_checksum_sha256') == asset.checksum_sha256
            and e.rights_status == str(asset.provenance.get('rights_status', 'unknown'))
            and e.license == str(asset.provenance.get('license', 'unknown'))
            and e.width == measured['width'] and e.height == measured['height']
            and (not asset.content_type.startswith('video/') or e.duration_seconds == measured['duration_seconds'])
            and (not e.publishing_allowed or e.rights_status in {'owned', 'licensed', 'verified'}
                and e.production_eligible and not asset.provenance.get('fixture')),
            'BROLL_INTERNAL_OUTPUT_PROVENANCE_CHANGED')


async def observation(service, session, op, saved):
    r = saved['receipt']
    job = await job_row(session, r['resolution_job_id'])
    linked, _ = await marked_admission(session, job)
    require(linked.operation_id == op.operation_id, 'BROLL_INTERNAL_OBSERVATION_MISMATCH')
    current, code, output = False, None, None
    if job.status in {'queued', 'running', 'succeeded'}:
        try:
            asset, _ = await bound(session, job, saved, terminal=job.status == 'succeeded')
            if job.status == 'succeeded':
                claim = await own_claim(session, job, lock=False)
                require(claim.status == 'succeeded', 'BROLL_INTERNAL_CLAIM_INVALID')
                e = await session.get(MediaAssetProvenanceORM, job.output_media_asset_id)
                require(e is not None, 'BROLL_INTERNAL_OUTPUT_MISSING')
                output = _media_asset_read(e)
                valid_evidence(output, asset)
            current = True
        except (InternalResolutionConflict, SourceLinkedConflict, ValueError, KeyError) as exc:
            current, output, code = False, None, getattr(exc, 'code', 'BROLL_INTERNAL_SOURCE_INVALID')
    require(job.status in {'queued', 'running', 'failed', 'cancelled', 'succeeded'},
            'BROLL_INTERNAL_JOB_STATE_INVALID')
    return {'schema_version': 'broll-internal-resolution-observation.v1',
        'receipt': r, 'job': _resolution_job_read(job).model_dump(mode='json'),
        'state': ('resolved' if current and job.status == 'succeeded' else
            'queued' if current and job.status == 'queued' else
            job.status if job.status in {'failed', 'cancelled'} else 'unknown'),
        'source_current': current, 'can_adopt': current and job.status == 'succeeded',
        'output': output.model_dump(mode='json') if output is not None else None,
        'error_code': code, 'needs_attention': not current or job.status in {'running', 'failed', 'cancelled'},
        'handoff': 'unverified' if job.status == 'queued' else 'not_queued',
        'provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}


async def reject_queued(service, identifier):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session, True)
            first = await job_row(session, identifier)
            await session.get(VideoProjectORM, first.project_id, with_for_update=True)
            job = await job_row(session, identifier, True)
            _, saved = await marked_admission(session, job)
            if job.status != 'queued':
                return
            item = await session.get(MediaPlanItemORM, job.media_plan_item_id, with_for_update=True)
            job.status, job.error_code = 'failed', 'BROLL_INTERNAL_SOURCE_CHANGED'
            job.failure_reason, job.updated_at = 'Reviewed inputs no longer match; no resolution performed.', utc_now()
            if item and item.status == 'resolving' and item.selected_media_asset_id == saved['private']['item_input']['selected_media_asset_id']:
                item.status, item.needs_attention, item.updated_at = 'failed', True, utc_now()


async def handoff(service, operation_id):
    # Only the explicit authorized admission POST calls this function.
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session)
            _, saved = await admission(session, operation_id)
            job = await job_row(session, saved['receipt']['resolution_job_id'])
            await marked_admission(session, job)
            if job.status != 'queued':
                return 'not_queued'
            try:
                await bound(session, job, saved)
            except (InternalResolutionConflict, SourceLinkedConflict, ValueError, KeyError):
                identifier = job.resolution_job_id
            else:
                identifier = None
    if identifier is not None:
        await reject_queued(service, identifier)
        return 'source_changed'
    evaluate = getattr(service.queue, 'eval', None)
    if not callable(evaluate):
        return 'handoff_pending'
    try:
        result = await evaluate(QUEUE_DEDUPE, 1, QUEUE_KEY, saved['receipt']['resolution_job_id'])
        return 'enqueued' if type(result) is int and result > 0 else 'handoff_pending'
    except Exception:
        # Lost acknowledgement and missing handoff are intentionally equivalent.
        return 'handoff_pending'


async def claim(service, identifier):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session, True)
            first = await job_row(session, identifier)
            await session.get(VideoProjectORM, first.project_id, with_for_update=True)
            job = await job_row(session, identifier, True)
            _, saved = await marked_admission(session, job)
            if job.status != 'queued':
                return None
            # No lease takeover: an existing attempt is never replayed.
            require(await session.get(ServiceOperationORM, claim_id(identifier)) is None,
                    'BROLL_INTERNAL_ATTEMPT_ALREADY_EXISTS')
            asset, _ = await bound(session, job, saved, lock=True)
            token, stamp = uuid.uuid4().hex, utc_now()
            value = {'job_id': identifier, 'operation_id': saved['receipt']['operation_id'],
                'token': token, 'materialization_started': False, 'byte_proof': None}
            session.add(ServiceOperationORM(operation_id=claim_id(identifier), workspace_id=job.workspace_id,
                service_id=CLAIM_NAMESPACE, action=CLAIM_ACTION, project_id=job.project_id,
                actor_ref='worker:reviewed-internal-media', key_sha256=digest({'job_id': identifier}),
                request_sha256=digest({'job_id': identifier, 'request_sha256': saved['receipt']['request_sha256']}),
                status='running', response_json=value, response_sha256=digest(value), created_at=stamp, updated_at=stamp))
            job.status, job.progress, job.updated_at = 'running', 5, stamp
            return token, asset


async def prove_bytes(service, identifier, token, asset):
    service.staging_root.mkdir(parents=True, exist_ok=True)
    # The existing bounded adapter verifies provider, key prefix, size and hash,
    # and drains cancelled I/O before this owned temporary directory is removed.
    with tempfile.TemporaryDirectory(prefix=identifier + '-review-', dir=service.staging_root) as directory:
        proof = frozen_asset_read(asset, workspace_id=asset.workspace_id, project_id=asset.project_id,
            storage=service.object_storage, maximum=MAX_SOURCE_BYTES)
        await proof.download(service.object_storage, Path(directory) / 'registered-asset.bin')
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session, True)
            job = await job_row(session, identifier)
            await session.get(VideoProjectORM, job.project_id, with_for_update=True)
            job = await job_row(session, identifier, True)
            _, saved = await marked_admission(session, job)
            await bound(session, job, saved, lock=True, materialized_asset=asset)
            row = await own_claim(session, job, token)
            row.response_json = {**row.response_json, 'byte_proof': asset_custody(asset)}
            row.response_sha256, row.updated_at = digest(row.response_json), utc_now()


async def process(service, identifier):
    try:
        owned = await claim(service, identifier)
    except (InternalResolutionConflict, SourceLinkedConflict, ValueError, KeyError):
        await reject_queued(service, identifier)
        return await service.repository.get_resolution_job(identifier)
    if owned is None:
        return await service.repository.get_resolution_job(identifier)
    token, asset = owned
    try:
        await prove_bytes(service, identifier, token, asset)
        return await service._process_once(identifier, reviewed_internal_claim_id=token)
    except Exception:
        await service.repository.mark_resolution_failed(identifier,
            error_code='BROLL_INTERNAL_SOURCE_OR_BYTES_CHANGED', reason='Reviewed internal source could not be verified.',
            expected_reviewed_internal_claim_id=token)
        return await service.repository.get_resolution_job(identifier)


async def start_owned(session, identifier, token):
    project_id = await reviewed_project(session, identifier)
    if project_id is None:
        return False, None
    require(token is not None, 'BROLL_INTERNAL_PRIVATE_CLAIM_REQUIRED')
    await begin(session, True)
    await session.get(VideoProjectORM, project_id, with_for_update=True)
    job = await job_row(session, identifier, True)
    _, saved = await marked_admission(session, job)
    row = await own_claim(session, job, token)
    if job.status != 'running' or row.response_json['materialization_started']:
        return True, False
    asset, _ = await bound(session, job, saved, lock=True)
    require(row.response_json['byte_proof'] == asset_custody(asset), 'BROLL_INTERNAL_BYTE_PROOF_REQUIRED')
    row.response_json = {**row.response_json, 'materialization_started': True}
    row.response_sha256, row.updated_at = digest(row.response_json), utc_now()
    job.progress, job.updated_at = 10, utc_now()
    return True, True


async def guard_completion(session, identifier, token, asset):
    project_id = await reviewed_project(session, identifier)
    if project_id is None:
        return
    require(token is not None, 'BROLL_INTERNAL_PRIVATE_CLAIM_REQUIRED')
    await begin(session, True)
    await session.get(VideoProjectORM, project_id, with_for_update=True)
    job = await job_row(session, identifier, True)
    _, saved = await marked_admission(session, job)
    require(job.status == 'running', 'BROLL_INTERNAL_CLAIM_LOST')
    row = await own_claim(session, job, token)
    current_asset, _ = await bound(session, job, saved, lock=True, materialized_asset=asset)
    require(row.response_json['materialization_started'] is True
            and row.response_json['byte_proof'] == asset_custody(current_asset), 'BROLL_INTERNAL_BYTE_PROOF_REQUIRED')
    existing = await session.scalar(select(MediaAssetProvenanceORM).where(
        MediaAssetProvenanceORM.asset_id == asset.asset_id).with_for_update())
    if existing is not None:
        valid_evidence(_media_asset_read(existing), current_asset)
    # The normal completion writes follow within this same transaction. If they
    # fail, this private terminal claim is rolled back with the job/item writes.
    row.status, row.updated_at = 'succeeded', utc_now()


async def fail_owned(session, identifier, token, error_code):
    try:
        project_id = await reviewed_project(session, identifier)
    except KeyError:
        return False
    if project_id is None:
        return False
    if token is None:
        return True  # A legacy/unowned caller cannot mutate this job.
    await begin(session, True)
    await session.get(VideoProjectORM, project_id, with_for_update=True)
    job = await job_row(session, identifier, True)
    _, saved = await marked_admission(session, job)
    if job.status != 'running':
        return True
    row = await own_claim(session, job, token)
    item = await session.get(MediaPlanItemORM, job.media_plan_item_id, with_for_update=True)
    job.status, job.error_code = 'failed', error_code[:80]
    job.failure_reason, job.updated_at = 'Reviewed internal operation failed; no source or timeline mutation.', utc_now()
    if item and item.status == 'resolving' and item.selected_media_asset_id == saved['private']['item_input']['selected_media_asset_id']:
        item.status, item.needs_attention, item.updated_at = 'failed', True, utc_now()
    row.status, row.updated_at = 'rejected', utc_now()
    return True
