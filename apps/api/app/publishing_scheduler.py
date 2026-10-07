"""Durable bounded scheduling. No background startup or default provider activation."""
import asyncio
import inspect
from dataclasses import dataclass, field
from datetime import timedelta
import re
import uuid

from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError

from .publishing_db import PublicationDispatchORM, PublicationWorkORM
from .publishing_dispatch import DispatchError, PublishingDispatchJournal, utc
from .publishing_worker import YouTubePublishingWorker


def public_work(row):
    return {**{name: getattr(row, name) for name in ('work_id', 'publication_id', 'workspace_id',
        'project_id', 'binding_sha256', 'status', 'version', 'failures', 'run_count', 'failure_code')},
        'next_run_at': utc(row.next_run_at).isoformat()}


@dataclass(frozen=True)
class WorkLease:
    work_id: str
    workspace_id: str
    publication_id: str
    version: int
    owner: str = field(repr=False)

    def __post_init__(self):
        if (not isinstance(self.owner, str) or not re.fullmatch('[a-f0-9]{32}', self.owner)
            or type(self.version) is not int or self.version < 2):
            raise DispatchError('PUBLISH_WORK_LEASE_INVALID')


class PublishingWorkQueue:
    def __init__(self, journal, *, lease_seconds=600):
        if type(lease_seconds) is not int or not 480 <= lease_seconds <= 900:
            raise DispatchError('PUBLISH_WORK_LEASE_INVALID')
        if type(journal) is not PublishingDispatchJournal or journal.require_target_binding is not True:
            raise DispatchError('PUBLISH_WORK_CONFIGURATION_INVALID')
        self.journal, self.session_factory, self.clock = journal, journal.session_factory, journal.clock
        self.lease_seconds = lease_seconds

    async def enqueue(self, workspace, publication_id):
        try:
            async with self.session_factory() as session:
                async with session.begin():
                    parent = await self.journal.parent(session, workspace, publication_id)
                    dispatch = await session.get(PublicationDispatchORM, publication_id)
                    if dispatch is None or dispatch.workspace_id != workspace:
                        raise DispatchError('PUBLISH_WORK_DISPATCH_REQUIRED')
                    prior = await session.scalar(select(PublicationWorkORM).where(PublicationWorkORM.publication_id == publication_id))
                    if prior is not None:
                        if prior.binding_sha256 != dispatch.binding_sha256:
                            raise DispatchError('PUBLISH_WORK_BINDING_CONFLICT')
                        return public_work(prior)
                    await self.journal.valid_grant(session, parent, dispatch.publish_approval_id)
                    now = utc(self.clock())
                    row = PublicationWorkORM(work_id='pwj_' + uuid.uuid4().hex, publication_id=publication_id,
                        workspace_id=workspace, project_id=parent.project_id, binding_sha256=dispatch.binding_sha256,
                        status='queued', version=1, failures=0, run_count=0, next_run_at=now, created_at=now, updated_at=now)
                    session.add(row); await session.flush()
                    self.journal.event(session, parent, 'publication.work_queued', 'publishing-service',
                        {'work_id': row.work_id, 'external_action': False})
                return public_work(row)
        except IntegrityError:
            raise DispatchError('PUBLISH_WORK_CONCURRENT_ENQUEUE_RELOAD') from None

    async def get(self, workspace, work_id):
        async with self.session_factory() as session:
            row = await session.get(PublicationWorkORM, work_id)
            if row is None or row.workspace_id != workspace:
                raise DispatchError('PUBLISH_WORK_SCOPE_NOT_FOUND')
            return public_work(row)

    async def for_publication(self, workspace, publication_id):
        async with self.session_factory() as session:
            await self.journal.parent(session, workspace, publication_id)
            row = await session.scalar(select(PublicationWorkORM).where(
                PublicationWorkORM.workspace_id == workspace, PublicationWorkORM.publication_id == publication_id))
            return public_work(row) if row is not None else None

    async def due(self, workspace, *, limit=8):
        if type(limit) is not int or not 1 <= limit <= 32:
            raise DispatchError('PUBLISH_WORK_LIMIT_INVALID')
        now = utc(self.clock())
        async with self.session_factory() as session:
            rows = (await session.scalars(select(PublicationWorkORM).where(
                PublicationWorkORM.workspace_id == workspace, PublicationWorkORM.next_run_at <= now,
                or_(PublicationWorkORM.status.in_(['queued', 'waiting']),
                    (PublicationWorkORM.status == 'running') & (PublicationWorkORM.lease_until <= now)))
                .order_by(PublicationWorkORM.next_run_at, PublicationWorkORM.work_id).limit(limit))).all()
            return [public_work(row) for row in rows]

    async def claim(self, workspace, work_id, expected_version):
        if type(expected_version) is not int or expected_version < 1:
            raise DispatchError('PUBLISH_WORK_VERSION_INVALID')
        now = utc(self.clock()); owner = uuid.uuid4().hex
        async with self.session_factory() as session:
            async with session.begin():
                row = await session.get(PublicationWorkORM, work_id)
                if (row is None or row.workspace_id != workspace or row.version != expected_version
                    or utc(row.next_run_at) > now or row.status not in ('queued', 'waiting', 'running')
                    or (row.status == 'running' and (row.lease_until is None or utc(row.lease_until) > now))):
                    raise DispatchError('PUBLISH_WORK_NOT_DUE_OR_STALE')
                dispatch = await session.get(PublicationDispatchORM, row.publication_id)
                if dispatch is None or dispatch.binding_sha256 != row.binding_sha256 or dispatch.workspace_id != workspace:
                    raise DispatchError('PUBLISH_WORK_BINDING_CONFLICT')
                result = await session.execute(update(PublicationWorkORM).where(PublicationWorkORM.work_id == work_id,
                    PublicationWorkORM.workspace_id == workspace, PublicationWorkORM.version == expected_version).values(
                        status='running', version=expected_version + 1, run_count=row.run_count + 1,
                        lease_owner=owner, lease_until=now + timedelta(seconds=self.lease_seconds), updated_at=now))
                if result.rowcount != 1:
                    raise DispatchError('PUBLISH_WORK_NOT_DUE_OR_STALE')
            return WorkLease(work_id, workspace, row.publication_id, expected_version + 1, owner)

    async def owned(self, lease):
        if type(lease) is not WorkLease or not re.fullmatch('[a-f0-9]{32}', lease.owner):
            raise DispatchError('PUBLISH_WORK_LEASE_INVALID')
        async with self.session_factory() as session:
            row = await session.get(PublicationWorkORM, lease.work_id)
            if (row is None or row.workspace_id != lease.workspace_id or row.publication_id != lease.publication_id
                or row.version != lease.version or row.lease_owner != lease.owner or row.status != 'running'
                or row.lease_until is None or utc(row.lease_until) <= utc(self.clock())):
                raise DispatchError('PUBLISH_WORK_OWNERSHIP_LOST')
            return row.failures

    async def finish(self, lease, *, status, delay=0, failure_code=None, failed=False):
        if status not in ('waiting', 'review_required', 'completed') or type(delay) is not int or not 0 <= delay <= 3600 or type(failed) is not bool:
            raise DispatchError('PUBLISH_WORK_RESULT_INVALID')
        if failure_code is not None and (not isinstance(failure_code, str) or not re.fullmatch('[A-Z0-9_]{1,100}', failure_code)):
            raise DispatchError('PUBLISH_WORK_RESULT_INVALID')
        failures = await self.owned(lease); now = utc(self.clock())
        async with self.session_factory() as session:
            async with session.begin():
                result = await session.execute(update(PublicationWorkORM).where(PublicationWorkORM.work_id == lease.work_id,
                    PublicationWorkORM.workspace_id == lease.workspace_id, PublicationWorkORM.publication_id == lease.publication_id,
                    PublicationWorkORM.version == lease.version, PublicationWorkORM.lease_owner == lease.owner,
                    PublicationWorkORM.status == 'running', PublicationWorkORM.lease_until > now).values(
                        status=status, version=lease.version + 1, failures=failures + 1 if failed else 0,
                        next_run_at=now + timedelta(seconds=delay), lease_owner=None, lease_until=None,
                        failure_code=failure_code, updated_at=now))
                if result.rowcount != 1:
                    raise DispatchError('PUBLISH_WORK_OWNERSHIP_LOST')
                parent = await self.journal.parent(session, lease.workspace_id, lease.publication_id)
                self.journal.event(session, parent, 'publication.work_' + status, 'publishing-service',
                    {'work_id': lease.work_id, 'failure_code': failure_code, 'external_action': False})
            return await self.get(lease.workspace_id, lease.work_id)


class PublishingScheduler:
    def __init__(self, queue, worker_factory, *, max_failures=5):
        if type(queue) is not PublishingWorkQueue or not callable(worker_factory) or type(max_failures) is not int or not 1 <= max_failures <= 10:
            raise DispatchError('PUBLISH_SCHEDULER_CONFIGURATION_INVALID')
        self.queue, self.worker_factory, self.max_failures = queue, worker_factory, max_failures

    async def run_one(self, workspace, work_id, expected_version):
        lease = await self.queue.claim(workspace, work_id, expected_version)
        async def guard(): await self.queue.owned(lease)
        try:
            async with asyncio.timeout(360):
                worker = self.worker_factory(guard)
                if inspect.isawaitable(worker): worker = await worker
                if type(worker) is not YouTubePublishingWorker or worker.journal is not self.queue.journal or worker.admission_guard is not guard:
                    raise DispatchError('PUBLISH_SCHEDULER_CONFIGURATION_INVALID')
                state = await self.queue.journal.get(workspace, lease.publication_id)
                result = await (worker.poll_processing(workspace, lease.publication_id) if state['phase'] == 'uploaded'
                    else worker.step(workspace, lease.publication_id))
            complete = result.get('status') == 'published'
            review = result.get('status') == 'failed' or result.get('failure_code') is not None
            delay = 120 if state['phase'] == 'uploaded' else 2
            retry_after = result.get('retry_after')
            if type(retry_after) is int and 1 <= retry_after <= 3600: delay = max(delay, retry_after)
            return await self.queue.finish(lease, status='completed' if complete else 'review_required' if review else 'waiting',
                delay=0 if complete or review else delay,
                failure_code=result.get('failure_code'))
        except asyncio.CancelledError:
            # Leave the durable lease/intent. Restart reclaims only after expiry.
            raise
        except Exception as error:
            failures = await self.queue.owned(lease)
            state = await self.queue.journal.get(workspace, lease.publication_id)
            code = getattr(error, 'code', 'PUBLISH_WORK_STEP_FAILED')
            if not isinstance(code, str) or not re.fullmatch('[A-Z0-9_]{1,100}', code): code = 'PUBLISH_WORK_STEP_FAILED'
            retry = (state['phase'] in ('init_ready', 'upload_ready', 'chunk_uncertain', 'chunk_intent', 'reconcile_intent', 'uploaded')
                and code in ('PUBLISHING_NETWORK_OUTCOME_UNKNOWN', 'YOUTUBE_STATUS_UNAVAILABLE', 'PUBLISH_WORK_STEP_FAILED',
                    'PUBLISHING_READ_RETRY_REQUIRED', 'PUBLISHING_RECONCILIATION_REQUIRED', 'PUBLISHING_TRANSPORT_FAILED',
                    'PUBLISHING_RECONCILIATION_LEASE_ACTIVE'))
            retry = retry and failures + 1 < self.max_failures
            retry_after = getattr(error, 'retry_after', None)
            delay = min(3600, 30 * 2 ** failures)
            if type(retry_after) is int and 1 <= retry_after <= 3600: delay = max(delay, retry_after)
            return await self.queue.finish(lease, status='waiting' if retry else 'review_required',
                delay=delay if retry else 0, failure_code=code, failed=True)
