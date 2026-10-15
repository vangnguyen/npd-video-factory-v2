"""One SQL admission receipt/job; handoff is an explicit POST-only operation."""
from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select

from .db import VideoProjectORM, utc_now
from .media_intelligence_db import MediaResolutionJobORM
from .service_api_repository import ServiceOperationORM, digest
from .broll_internal_resolution_core import (NAMESPACE, ACTION, MARKER, ACTIVE,
    InternalResolutionConflict, begin, context, require, operation_key, admission)


async def find(session, project_id, authority, key):
    return await session.scalar(select(ServiceOperationORM).where(
        ServiceOperationORM.service_id == NAMESPACE, ServiceOperationORM.project_id == project_id,
        ServiceOperationORM.actor_ref == authority['subject'],
        ServiceOperationORM.key_sha256 == operation_key(authority, project_id, key)))


async def inspect_context(service, project_id, plan_id, item_id, authority):
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session)
            value, _, _ = await context(session, project_id, plan_id, item_id, authority)
            return value


async def inspect_job(service, project_id, plan_id, item_id, authority, key, job_id):
    from .broll_internal_resolution_worker import observation
    async with service.repository.session_factory() as session:
        async with session.begin():
            await begin(session)
            op = await find(session, project_id, authority, key)
            if op is None:
                raise KeyError(key)
            op, saved = await admission(session, op.operation_id)
            r = saved['receipt']
            require(r['media_plan_id'] == plan_id and r['media_plan_item_id'] == item_id
                    and r['resolution_job_id'] == job_id, 'BROLL_INTERNAL_OBSERVATION_MISMATCH')
            return await observation(service, session, op, saved)


async def admit(service, project_id, plan_id, item_id, authority, payload):
    from .broll_internal_resolution_worker import handoff, observation
    request = payload.model_dump(mode='json')
    request_sha = digest({'project_id': project_id, 'plan_id': plan_id, 'item_id': item_id,
        'authority': authority, 'request': request})
    factory = service.repository.session_factory
    async with factory() as session:
        async with session.begin():
            await begin(session, True)
            project = await session.get(VideoProjectORM, project_id, with_for_update=True)
            if project is None:
                raise KeyError(project_id)
            prior = await find(session, project_id, authority, payload.request_key)
            if prior is not None:
                require(prior.request_sha256 == request_sha, 'BROLL_INTERNAL_IDEMPOTENCY_CONFLICT')
                op, saved = await admission(session, prior.operation_id)
                require(saved['receipt']['media_plan_id'] == plan_id
                        and saved['receipt']['media_plan_item_id'] == item_id, 'BROLL_INTERNAL_IDEMPOTENCY_CONFLICT')
                from .broll_internal_settlement_command import require_unsettled
                await require_unsettled(session, op, saved)
                operation_id = op.operation_id
            else:
                value, item, assets = await context(session, project_id, plan_id, item_id, authority, lock=True)
                require(value['context_sha256'] == payload.context_sha256, 'BROLL_INTERNAL_CONTEXT_CHANGED')
                chosen = next((v for v in value['candidates'] if v['asset_id'] == payload.asset_id), None)
                require(chosen is not None and chosen['available'], 'BROLL_INTERNAL_SAVED_SELECTION_REQUIRED')
                active = await session.scalar(select(MediaResolutionJobORM.resolution_job_id).where(
                    MediaResolutionJobORM.media_plan_item_id == item_id,
                    MediaResolutionJobORM.status.in_(ACTIVE)))
                require(active is None and item.status != 'resolving', 'BROLL_INTERNAL_ITEM_BUSY')
                operation_id, job_id = 'sop_' + uuid.uuid4().hex, 'mrj_' + uuid.uuid4().hex[:24]
                stamp = utc_now()
                fingerprint = digest({'namespace': NAMESPACE, 'operation_id': operation_id, 'request_sha256': request_sha})
                internal_request = {'source_asset_id': payload.asset_id,
                    'checksum_sha256': assets[payload.asset_id].checksum_sha256}
                static = {'resolution_job_id': job_id, 'fingerprint': fingerprint,
                    'workspace_id': project.workspace_id, 'project_id': project_id,
                    'project_version_id': project.current_version_id,
                    'media_plan_id': plan_id, 'media_plan_item_id': item_id,
                    'provider_key': 'internal-media', 'capability': 'internal_media',
                    'operation': 'reuse-user-asset', 'selected_candidate_id': None,
                    'request_json': internal_request, 'external_call': False, 'paid': False,
                    'real_provider_tested': False}
                marker = {'operation_id': operation_id, 'binding_sha256': value['context_sha256']}
                job = MediaResolutionJobORM(**static, status='queued', progress=0,
                    estimated_cost_vnd=Decimal('0'), provenance_json={MARKER: marker,
                        'request': internal_request, 'source_media_mutated': False, 'publish_requested': False},
                    created_at=stamp, updated_at=stamp)
                receipt = {'schema_version': 'broll-internal-resolution-receipt.v1',
                    'operation_id': operation_id, 'workspace_id': project.workspace_id,
                    'project_id': project_id, 'actor_ref': authority['subject'],
                    'authority_sha256': digest(authority), 'request_key': payload.request_key,
                    'request_sha256': request_sha, 'context_sha256': value['context_sha256'],
                    'media_plan_id': plan_id, 'media_plan_item_id': item_id,
                    'resolution_job_id': job_id, 'asset_id': payload.asset_id,
                    'asset_custody_sha256': digest(chosen['asset_custody']),
                    'timeline_id': value['timeline_id'], 'timeline_version_id': value['timeline_version_id'],
                    'timeline_version': value['timeline_version'], 'source': value['source'],
                    'provider_calls': 0, 'publishing_enabled': False, 'owner_approval_inferred': False}
                saved = {'receipt': receipt, 'private': {'authority': authority,
                    'context': value, 'job': static, 'item_input': value['item'],
                    'selected_asset_custody': chosen['asset_custody']}}
                op = ServiceOperationORM(operation_id=operation_id, workspace_id=project.workspace_id,
                    service_id=NAMESPACE, action=ACTION, project_id=project_id, actor_ref=authority['subject'],
                    key_sha256=operation_key(authority, project_id, payload.request_key), request_sha256=request_sha,
                    status='succeeded', response_status=202, response_json=saved,
                    response_sha256=digest(saved), created_at=stamp, updated_at=stamp)
                session.add_all([op, job])
                item.status, item.updated_at = 'resolving', stamp
    # No queue handoff occurs before the atomic receipt/job transaction commits.
    # Uncertain queue acknowledgement never creates a second logical job.
    queue_state = await handoff(service, operation_id)
    async with factory() as session:
        async with session.begin():
            await begin(session)
            op, saved = await admission(session, operation_id)
            result = await observation(service, session, op, saved)
            result['handoff'] = queue_state
            return result
