"""Actual persistence of explicitly mock official processing/visibility observations."""
from datetime import datetime, timedelta, timezone
import json

import httpx
import pytest
from sqlalchemy import select

from app.publishing_db import PublicationORM, PublicationEventORM
from app.publishing_dispatch import DispatchError
from app.publishing_processing import PublishingProcessingJournal
from app.publishing_wire import OfficialResponse, PublishingWireError
from app.youtube_upload import VideoObservation, video_observation
from test_publishing_dispatch import fixture_stack, prepared
from test_publishing_worker import configured_worker

VID = 'AbcD_12-345'


def response(status):
    return OfficialResponse(200, {}, json.dumps({'items': [{'id': VID, 'status': status,
        'processingDetails': {'processingStatus': 'succeeded'}}]}).encode())


def test_selected_status_fields_preserve_unknown_visibility_and_validate_schedule():
    assert video_observation(response({}), VID) == VideoObservation('processed')
    instant = datetime(2026, 12, 1, tzinfo=timezone.utc)
    assert video_observation(response({'privacyStatus': 'private', 'publishAt': instant.isoformat()}), VID) == VideoObservation('processed', 'private', instant)
    for status in ({'privacyStatus': 'invented'}, {'publishAt': 'private-invalid'}, {'publishAt': '2026-12-01T00:00:00'}, {'publishAt': True}):
        with pytest.raises(PublishingWireError, match='PROVIDER_STATUS_INVALID'):
            video_observation(response(status), VID)


async def uploaded(fixture, *, metadata=None):
    grant, state = await prepared(fixture)
    journal = fixture['journal']; workspace, pub = fixture['workspace'], state['publication_id']
    init = await journal.intent(workspace, pub, state['version'], 'init')
    state = await journal.finish(init, session_ref='pss_' + 'a' * 32)
    chunk = await journal.intent(workspace, pub, state['version'], 'chunk', offset=0, length=state['total_bytes'])
    await journal.finish(chunk, acknowledged_bytes=state['total_bytes'], remote_post_id=VID)
    if metadata:
        async with journal.session_factory() as session:
            async with session.begin():
                parent = await session.get(PublicationORM, pub)
                parent.metadata_json = {**parent.metadata_json, **metadata}
    return PublishingProcessingJournal(journal.session_factory, clock=lambda: fixture['clock'][0]), grant


@pytest.mark.asyncio
@pytest.mark.parametrize('observation,status,failure', [
    (VideoObservation('processing'), 'publishing', None),
    (VideoObservation('unknown'), 'publishing', None),
    (VideoObservation('processed'), 'publishing', 'YOUTUBE_VISIBILITY_UNCONFIRMED_REVIEW_REQUIRED'),
    (VideoObservation('processed', 'public'), 'publishing', 'YOUTUBE_VISIBILITY_UNCONFIRMED_REVIEW_REQUIRED'),
    (VideoObservation('processed', 'private'), 'published', None),
    (VideoObservation('failed_requires_review'), 'failed', 'YOUTUBE_PROCESSING_FAILED_REVIEW_REQUIRED')])
async def test_processing_does_not_infer_publication_and_keeps_mock_receipts_explicit(fixture_stack, observation, status, failure):
    fixture = fixture_stack; journal, grant = await uploaded(fixture)
    await fixture['journal'].revoke(fixture['workspace'], grant['publish_approval_id'], principal=fixture['principals']['owner'])
    value = await journal.record(fixture['workspace'], fixture['publication'].publication_id, VID, observation, mock=True)
    assert value['status'] == status and value['failure_code'] == failure and value['published'] is False
    assert value['receipt'] is None if status != 'published' else value['receipt']['remote_url'] is None
    if status == 'published':
        receipt = value['receipt']; assert receipt['mock'] and not receipt['external_action']
        await fixture['stack'].engine.dispose()
        later = await journal.record(fixture['workspace'], fixture['publication'].publication_id, VID, VideoObservation('unknown'), mock=True)
        assert later['receipt'] == receipt
    async with journal.session_factory() as session:
        events = (await session.scalars(select(PublicationEventORM).where(
            PublicationEventORM.event_type == 'publication.processing_observed'))).all()
        assert events and all(event.payload_json['mock'] is True for event in events)


@pytest.mark.asyncio
async def test_schedule_needs_exact_observed_private_deadline_then_public_release(fixture_stack):
    fixture = fixture_stack; future = fixture['clock'][0] + timedelta(minutes=30)
    journal, _grant = await uploaded(fixture, metadata={'privacy': 'private', 'scheduled_at': future.isoformat()})
    workspace, pub = fixture['workspace'], fixture['publication'].publication_id
    value = await journal.record(workspace, pub, VID, VideoObservation('processed', 'private'), mock=True)
    assert value['status'] == 'publishing' and value['receipt'] is None and value['failure_code']
    value = await journal.record(workspace, pub, VID, VideoObservation('processed', 'private', future), mock=True)
    assert value['status'] == 'scheduled' and value['receipt'] is None
    fixture['clock'][0] = future + timedelta(seconds=1)
    value = await journal.record(workspace, pub, VID, VideoObservation('processed', 'private'), mock=True)
    assert value['status'] == 'scheduled' and value['failure_code'] and value['receipt'] is None
    value = await journal.record(workspace, pub, VID, VideoObservation('processed', 'public'), mock=True)
    assert value['status'] == 'published' and value['mock_publication_complete'] and not value['published']


@pytest.mark.asyncio
async def test_foreign_scope_wrong_remote_and_mock_mode_cannot_record_receipt(fixture_stack):
    fixture = fixture_stack; journal, _grant = await uploaded(fixture)
    for workspace, remote, mock in [('foreign', VID, True), (fixture['workspace'], 'ZbcD_12-345', True), (fixture['workspace'], VID, False)]:
        with pytest.raises(DispatchError, match='PROCESSING_SCOPE_OR_UPLOAD_INVALID'):
            await journal.record(workspace, fixture['publication'].publication_id, remote, VideoObservation('processed', 'private'), mock=mock)


@pytest.mark.asyncio
async def test_worker_polls_existing_upload_with_only_scoped_mock_gets(fixture_stack, tmp_path):
    fixture = fixture_stack; worker, _options, receiver, grant, _work, _policy = await configured_worker(fixture, tmp_path)
    workspace, pub = fixture['workspace'], fixture['publication'].publication_id
    for _ in range(4): await worker.step(workspace, pub)
    await worker.journal.revoke(workspace, grant['publish_approval_id'], principal=fixture['principals']['owner'])
    calls = []
    def handler(request):
        calls.append(request.method); assert request.method == 'GET'
        if request.url.path.endswith('/channels'): return httpx.Response(200, json={'items': [{'id': worker.credential_resolver(None).target.target_account_id}]})
        assert request.url.params['id'] == VID
        return httpx.Response(200, json={'items': [{'id': VID, 'status': {'privacyStatus': 'private'}, 'processingDetails': {'processingStatus': 'succeeded'}}]})
    worker.client.transport = httpx.MockTransport(handler)
    value = await worker.poll_processing(workspace, pub)
    assert calls == ['GET', 'GET'] and value['mock_publication_complete'] and value['published'] is False
    assert receiver.initializations == 1
