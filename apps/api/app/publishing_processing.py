"""Append observed processing/visibility; retain immutable publication receipts."""
import uuid

from sqlalchemy import update

from .publishing_db import PublicationDispatchORM, PublicationORM, PublicationEventORM
from .publishing_dispatch import DispatchError, utc
from .publishing_models import PublicationMetadata, PublicationReceipt
from .youtube_upload import VideoObservation, video_id


class PublishingProcessingJournal:
    def __init__(self, session_factory, *, clock):
        self.session_factory, self.clock = session_factory, clock

    async def record(self, workspace, publication_id, remote_id, observation, *, mock):
        remote_id = video_id(remote_id)
        if type(observation) is not VideoObservation or type(mock) is not bool:
            raise DispatchError('PUBLISH_PROCESSING_OBSERVATION_INVALID')
        observation = VideoObservation(observation.processing, observation.privacy, observation.scheduled_at)
        now = utc(self.clock())
        async with self.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, publication_id, with_for_update=True)
                dispatch = await session.get(PublicationDispatchORM, publication_id)
                if (parent is None or dispatch is None or parent.workspace_id != workspace
                    or dispatch.workspace_id != workspace or dispatch.project_id != parent.project_id
                    or parent.platform != 'youtube' or parent.mode != 'live' or parent.mock != mock
                    or dispatch.phase != 'uploaded' or dispatch.remote_post_id != remote_id
                    or dispatch.acknowledged_bytes != dispatch.total_bytes):
                    raise DispatchError('PUBLISH_PROCESSING_SCOPE_OR_UPLOAD_INVALID')
                metadata = PublicationMetadata.model_validate(parent.metadata_json)
                status, failure = parent.status, parent.failure_code
                if parent.receipt_json is None and parent.status in ('publishing', 'scheduled'):
                    failure = None
                    if observation.processing == 'failed_requires_review':
                        status, failure = 'failed', 'YOUTUBE_PROCESSING_FAILED_REVIEW_REQUIRED'
                    elif observation.processing == 'processed':
                        expected_schedule = metadata.scheduled_at
                        if expected_schedule is None:
                            if observation.privacy == metadata.privacy:
                                status = 'published'
                            else:
                                failure = 'YOUTUBE_VISIBILITY_UNCONFIRMED_REVIEW_REQUIRED'
                        elif utc(expected_schedule) > now:
                            if observation.privacy == 'private' and observation.scheduled_at == utc(expected_schedule):
                                status = 'scheduled'
                            else:
                                failure = 'YOUTUBE_SCHEDULE_UNCONFIRMED_REVIEW_REQUIRED'
                        elif observation.privacy == 'public':
                            status = 'published'
                        else:
                            failure = 'YOUTUBE_SCHEDULE_RELEASE_UNCONFIRMED_REVIEW_REQUIRED'
                receipt = parent.receipt_json
                if status == 'published' and receipt is None:
                    receipt = PublicationReceipt(receipt_id='rcpt_' + uuid.uuid4().hex,
                        provider_key=parent.provider_key, platform='youtube', mode='live',
                        request_fingerprint=parent.request_fingerprint, remote_post_id=remote_id,
                        remote_url=None, mock=mock, external_action=not mock, created_at=now).model_dump(mode='json')
                changed = await session.execute(update(PublicationORM).where(
                    PublicationORM.publication_id == publication_id, PublicationORM.workspace_id == workspace,
                    PublicationORM.status == parent.status, PublicationORM.updated_at == parent.updated_at).values(
                        status=status, receipt_json=receipt, failure_code=failure,
                        failure_reason=None, external_action=not mock, updated_at=now))
                if changed.rowcount != 1:
                    raise DispatchError('PUBLISH_PROCESSING_STALE_RELOAD')
                evidence = {'processing': observation.processing, 'privacy': observation.privacy,
                    'scheduled_at': observation.scheduled_at.isoformat() if observation.scheduled_at else None,
                    'remote_post_id': remote_id, 'status': status, 'failure_code': failure,
                    'mock': mock, 'external_action': not mock, 'secret_free': True}
                session.add(PublicationEventORM(event_id='pue_' + uuid.uuid4().hex, publication_id=publication_id,
                    project_id=parent.project_id, event_type='publication.processing_observed',
                    actor_ref='publishing-service', payload_json=evidence, created_at=now))
            return {**evidence, 'observed_at': now.isoformat(), 'receipt': receipt,
                'published': status == 'published' and not mock, 'mock_publication_complete': status == 'published' and mock}
