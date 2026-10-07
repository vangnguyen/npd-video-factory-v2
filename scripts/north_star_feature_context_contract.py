"""Owned SQLite/render/analytics restart proof; media and provider outputs are fixtures."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import httpx
from sqlalchemy import select
from app.main import app
from app.db import AssetORM, VideoProjectORM, create_engine, create_session_factory
from app.analytics_repository import AnalyticsRepository
from app.analytics_providers import AnalyticsProviderRegistry
from app.analytics_service import AnalyticsService, AnalyticsSyncProcessor
from app.platform_models import ProjectVersionCreate
from app.production_models import (
    ApprovalDecisionRequest, ApprovalRequest, FinalRenderCreateRequest,
    ProductionPackageCreateRequest, RenderCreateRequest,
)
from app.production_repository import ProductionRepository
from app.publishing_repository import PublishingRepository
from app.trend_repository import TrendRepository
from auth_test_support import TEST_HUMAN_HEADERS
from test_analytics_learning import FakeQueue, analytics_settings
from test_analytics_publication_api import application
from test_audio_subtitle_render_qc import setup_stack
from test_publishing import request_for, publishing_settings, PublishingService, PublishingCapabilityRegistry, PublishingProviderRegistry, CAPABILITIES


def write(root, name, value):
    with (root / name).open('x', encoding='utf-8') as file: json.dump(value, file, ensure_ascii=False, indent=2, default=str)


async def restored(database, project, render_id):
    engine = create_engine('sqlite+aiosqlite:///' + Path(database).as_posix())
    factory = create_session_factory(engine)
    repository = AnalyticsRepository(factory)
    result = {'report': (await repository.report(project)).model_dump(mode='json'),
        'snapshots': [row.model_dump(mode='json') for row in await repository.list_snapshots(project)],
        'render': (await ProductionRepository(factory).get_render(render_id)).model_dump(mode='json')}
    await engine.dispose()
    return result


async def run(args):
    root = Path(args.output); root.mkdir(parents=True, exist_ok=False)
    owned = root / 'owned-fixture'; owned.mkdir()
    stack = await setup_stack(owned)
    try:
        async with stack.repository.session_factory() as session:
            project = await session.get(VideoProjectORM, stack.project.project_id); project.niche = 'technology'
            asset = await session.get(AssetORM, stack.asset.asset_id)
            asset.provenance = {'source_type': 'user_upload', 'rights_status': 'owned', 'license': 'EXPLICIT TEST FIXTURE',
                'production_eligible': True, 'fixture_only': True}
            await session.commit()
        version = await stack.platform.create_version(stack.project.project_id, ProjectVersionCreate(
            snapshot={'topic': 'AI educational fixture', 'source_idea': {'hook_concept': 'Explain a misconception',
                'cta_concept': 'Compare tools', 'visual_concept': 'Demonstration'}}))
        package = await stack.service.create_or_refresh(stack.project.project_id,
            ProductionPackageCreateRequest(expected_timeline_version=1, actor_ref='EXPLICIT FIXTURE; NOT OWNER UAT'))
        review = await stack.service.enqueue_review(stack.project.project_id, RenderCreateRequest(expected_timeline_version=1,
            expected_subtitle_version=package.subtitle.version, expected_audio_version=package.audio_mix.version))
        review = await stack.processor.process(review.render_id)
        approval = await stack.service.request_approval(stack.project.project_id,
            ApprovalRequest(review_render_id=review.render_id, requester_ref='EXPLICIT FIXTURE'))
        await stack.service.decide_approval(stack.project.project_id, approval.approval_id,
            ApprovalDecisionRequest(decision='approved', reviewer_ref='EXPLICIT FIXTURE; NOT OWNER UAT'))
        final = await stack.service.enqueue_final(stack.project.project_id, FinalRenderCreateRequest(expected_timeline_version=1,
            expected_subtitle_version=package.subtitle.version, expected_audio_version=package.audio_mix.version,
            approval_id=approval.approval_id, profile='vertical-1080x1920'))
        frozen = final.manifest['feature_context']
        later = await stack.platform.create_version(stack.project.project_id, ProjectVersionCreate(snapshot={'topic': 'Unrelated later topic'}))
        async with stack.repository.session_factory() as session:
            project = await session.get(VideoProjectORM, stack.project.project_id); project.niche = 'unrelated-later-niche'
            await session.commit()
        final = await stack.processor.process(final.render_id)
        assert final.status == 'ready' and final.manifest['feature_context'] == frozen
        final_asset = await stack.asset_repository.get_asset(final.output_asset_id)
        assert final_asset.project_version_id == version.project_version_id != later.project_version_id
        exported_asset = await stack.asset_repository.get_asset(final.manifest['supporting_asset_ids']['render-evidence'])
        evidence_file = root / 'persisted-render-evidence.json'
        await stack.storage.download_file(object_key=exported_asset.object_key, destination=evidence_file)
        assert json.loads(evidence_file.read_text(encoding='utf-8'))['feature_context'] == frozen
        publishing = PublishingService(repository=PublishingRepository(stack.repository.session_factory),
            production_repository=stack.repository, asset_repository=stack.asset_repository,
            capabilities=PublishingCapabilityRegistry(CAPABILITIES), providers=PublishingProviderRegistry(publishing_settings()),
            settings=publishing_settings())
        publication, _ = await publishing.create(project_id=stack.project.project_id, payload=request_for(final.render_id),
            idempotency_key='feature-context-dry-run-publication')
        assert publication.mock and not publication.external_action
        repository = AnalyticsRepository(stack.repository.session_factory)
        settings = analytics_settings(); providers = AnalyticsProviderRegistry(settings)
        service = AnalyticsService(repository=repository, publishing_repository=publishing.repository,
            platform_repository=stack.platform, providers=providers, queue=FakeQueue(), settings=settings)
        processor = AnalyticsSyncProcessor(repository=repository, publishing_repository=publishing.repository,
            platform_repository=stack.platform, trend_repository=TrendRepository(stack.repository.session_factory),
            timeline_repository=stack.timeline_repository, production_repository=stack.repository, providers=providers, settings=settings)
        data = SimpleNamespace(production=stack, publication=publication, service=service)
        calls = []; first = None
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=application(data)), base_url='http://fixture', headers=TEST_HUMAN_HEADERS) as client:
            base = f'/api/v1/projects/{stack.project.project_id}/analytics'
            for index, profile in enumerate(('normal', 'underperforming')):
                response = await client.post(base + '/syncs', json={'publication_id': publication.publication_id,
                    'provider_mode': 'fixture', 'fixture_profile': profile}, headers={'Idempotency-Key': 'frozen-feature-mock-sync-' + str(index)})
                assert response.status_code == 202
                result = await processor.process(response.json()['sync_id']); assert result.status == 'succeeded' and result.mock and not result.external_call
                calls.append({'method': 'POST', 'status': 202, 'source': 'fixture'})
                if first is None: first = (await repository.list_snapshots(stack.project.project_id))[0].model_dump(mode='json')
            for suffix in ('', '/snapshots'):
                response = await client.get(base + suffix); assert response.status_code == 200
                calls.append({'method': 'GET', 'status': 200, 'source': 'fixture'})
        features = (await repository.report(stack.project.project_id)).video_features
        assert features.niche == 'technology' and features.topic == 'AI educational fixture'
        assert features.hook_type == 'Explain a misconception' and features.cta == 'Compare tools'
        assert features.evidence['project_version_id'] == version.project_version_id
        assert any(row.model_dump(mode='json') == first for row in await repository.list_snapshots(stack.project.project_id))
        await stack.engine.dispose()
        expected = await restored(owned / 'production.db', stack.project.project_id, final.render_id)
        fresh = json.loads(subprocess.check_output([sys.executable, str(Path(__file__).resolve()), '--read-db', str(owned / 'production.db'),
            '--project', stack.project.project_id, '--render', final.render_id], timeout=45))
        assert fresh == expected
        write(root, 'restored-state.json', fresh); write(root, 'frozen-context.json', frozen); write(root, 'api-requests.json', calls)
        write(root, 'lineage.json', {'original_version_id': version.project_version_id, 'later_version_id': later.project_version_id,
            'output_asset_version_id': final_asset.project_version_id, 'evidence_asset_version_id': exported_asset.project_version_id,
            'feature_context_sha256': final.manifest['feature_context_sha256'],
            'evidence_file_sha256': hashlib.sha256(evidence_file.read_bytes()).hexdigest()})
        write(root, 'contract.json', {'status': 'PASS', 'fresh_process_restore': True, 'authenticated_api_requests': len(calls),
            'immutable_mock_snapshots': 2, 'frozen_labels_survive_edits': True, 'render_and_asset_lineage_match': True,
            'media_is_nonplayable_fixture_bytes': True, 'full_media_qc_tested': False, 'real_provider_tested': False,
            'external_calls': 0, 'real_credentials_read': 0, 'paid_calls': 0, 'owner_uat_accepted': False,
            'accepted_media_replaced': False, 'production_deployed': False, 'learning_loop_ready': False})
        print(json.dumps({'status': 'PASS', 'output': str(root), 'snapshots': 2, 'api_requests': len(calls)}))
    finally: await stack.engine.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output'); parser.add_argument('--read-db')
    parser.add_argument('--project'); parser.add_argument('--render'); args = parser.parse_args()
    if args.read_db: print(json.dumps(asyncio.run(restored(args.read_db, args.project, args.render))))
    else:
        assert args.output
        asyncio.run(run(args))
