"""Read review/configuration creates no consent, dispatch or provider action."""
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import AssetORM
from app.publishing_db import PublishApprovalORM, PublicationDispatchORM
from app.publishing_models import PublishApprovalRequest
from app.publishing_profiles import PublishingProfile, PublishingProfileCatalog, PublishingProfileRegistry
from test_publishing_dispatch import fixture_stack
from test_publishing_queue import configured_service, consent_payload, headers, http_app, queued


@pytest.mark.asyncio
async def test_review_is_scoped_read_only_no_store_and_separate_from_consent(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    path = f'/api/v1/projects/{row.project_id}/publications/{row.publication_id}/publish-review'
    async with AsyncClient(transport=ASGITransport(app=http_app(fixture, configured)), base_url='http://fixture') as client:
        for role in ('viewer', 'reviewer', 'editor', 'owner'):
            result = await client.get(path, headers=headers(role))
            assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
            value = result.json()
            assert value['artifact_sha256'] == fixture['source_sha'] and value['request_fingerprint'] == row.request_fingerprint
            assert value['metadata'] == row.metadata.model_dump(mode='json')
            assert value['active_publish_approval'] is None and value['external_action'] is False
            assert value['owner_gates_enabled'] is True
            assert not any(secret in result.text for secret in ('lease_owner', 'owner_token_id', 'session_ref', 'upload_token'))
        foreign = await client.get(path.replace(row.project_id, 'prj_foreign_fixture'), headers=headers('owner'))
        assert foreign.status_code == 404
        missing = await client.get(path.replace(row.publication_id, 'pub_missing_fixture'), headers=headers('owner'))
        assert missing.status_code == 404
        denied = await client.get(path)
        assert denied.status_code == 401
    async with fixture['stack'].repository.session_factory() as session:
        assert not (await session.scalars(select(PublishApprovalORM))).all()
        assert not (await session.scalars(select(PublicationDispatchORM))).all()
    assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
async def test_review_displays_only_current_unrevoked_consent_and_disabled_flags(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    grant = await configured.service.approve_publish(row.project_id, row.publication_id,
        principal=fixture['principals']['owner'], payload=PublishApprovalRequest.model_validate(consent_payload(fixture, row, configured)),
        idempotency_key='explicit-review-consent-fixture')
    review = await configured.service.publish_review(row.project_id, row.publication_id)
    assert review['active_publish_approval'] == grant
    configured.service.settings.publish_enabled = False
    review = await configured.service.publish_review(row.project_id, row.publication_id)
    assert review['owner_gates_enabled'] is False  # Read is not enablement.
    await configured.service.revoke_publish(row.project_id, row.publication_id, principal=fixture['principals']['owner'],
        publish_approval_id=grant['publish_approval_id'])
    assert (await configured.service.publish_review(row.project_id, row.publication_id))['active_publish_approval'] is None
    assert configured.provider.publish_calls == 0


@pytest.mark.asyncio
async def test_changed_artifact_invalidates_consent_in_review_without_rebinding_it(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    grant = await configured.service.approve_publish(row.project_id, row.publication_id,
        principal=fixture['principals']['owner'], payload=PublishApprovalRequest.model_validate(consent_payload(fixture, row, configured)),
        idempotency_key='explicit-stale-review-fixture')
    async with fixture['stack'].repository.session_factory() as session:
        asset = await session.get(AssetORM, row.output_asset_id); asset.checksum_sha256 = 'b' * 64; await session.commit()
    review = await configured.service.publish_review(row.project_id, row.publication_id)
    assert review['artifact_sha256'] == 'b' * 64 and review['active_publish_approval'] is None
    async with fixture['stack'].repository.session_factory() as session:
        old = await session.get(PublishApprovalORM, grant['publish_approval_id'])
        assert old.binding_json['artifact_sha256'] == fixture['source_sha']  # Never rewrite consent history.


@pytest.mark.asyncio
async def test_profile_list_is_project_scoped_latest_and_default_empty(fixture_stack):
    fixture = fixture_stack; configured = configured_service(fixture); row, _ = await queued(fixture, configured)
    assert await configured.service.profiles_for_project(row.project_id) == []
    source = configured.target[0].model_dump()
    def profile(**overrides):
        return PublishingProfile(target={**source, 'provider_key': 'youtube-data-api-publishing', **overrides},
            category_id='27', made_for_kids=False, contains_synthetic_media=False)
    old = profile(); latest = profile(profile_version=2, target_account_id='NEW_FIXTURE_ACCOUNT')
    foreign = profile(workspace_id='wsp_foreign_fixture')
    configured.service.profile_registry = PublishingProfileRegistry(PublishingProfileCatalog(profiles=[old, latest, foreign]))
    path = f'/api/v1/projects/{row.project_id}/publishing-profiles'
    async with AsyncClient(transport=ASGITransport(app=http_app(fixture, configured)), base_url='http://fixture') as client:
        result = await client.get(path, headers=headers('viewer'))
        assert result.status_code == 200 and result.headers['cache-control'] == 'no-store'
        assert len(result.json()) == 1 and result.json()[0]['target']['profile_version'] == 2
        assert result.json()[0]['target']['workspace_id'] == row.workspace_id
        assert 'wsp_foreign_fixture' not in result.text
    assert configured.provider.publish_calls == 0
