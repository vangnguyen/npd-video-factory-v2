"""Owned loopback rehearsal of the complete Studio shell against actual SQL APIs.

Clones a quiescent, first-party fixture database/object tree. No captured HTTP DTO
is replayed. The normal main lifespan, workers, Redis, provider dispatch, renderer
and publishing remain disabled. Only explicit child transcript-word CAS is allowed.
The fixture's saved speech/scene evidence is synthetic, not real ASR or Owner UAT.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import secrets
import socket
import sqlite3
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'apps/api'))

import httpx
import uvicorn
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import Settings
from app.db import Base, ProviderUsageORM
from app.human_auth import HumanAuthVerifier, HumanRateLimiter
from app.object_storage import LocalObjectStorageProvider
from app.sql_variant_repository import canonical, record_value
from app.uploaded_audio_db import UploadedAudioORM


def file_proof(path):
    size, digest = 0, hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            size += len(block)
            digest.update(block)
    return {'bytes': size, 'sha256': digest.hexdigest()}


def ordinary(path, *, directory=False):
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError('FIXTURE_PATH_NOT_CANONICAL')
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise ValueError('FIXTURE_REPARSE_REFUSED')
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('FIXTURE_DIRECTORY_REQUIRED')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('FIXTURE_PLAIN_SINGLE_LINK_REQUIRED')
    return path


def tree_proof(root):
    ordinary(root, directory=True)
    rows = []
    for path in sorted(root.rglob('*')):
        ordinary(path, directory=path.is_dir())
        if path.is_file():
            rows.append({'path': path.relative_to(root).as_posix(), **file_proof(path)})
    return rows


def write_json(path, value):
    # New evidence only. Never overwrite prior runs.
    with path.open('x', encoding='utf-8', newline='\n') as target:
        json.dump(value, target, ensure_ascii=False, indent=2)
        target.write('\n')


def backup(source, target, *, readonly=False):
    uri = f'file:{source.as_posix()}?mode=ro' if readonly else str(source)
    with sqlite3.connect(uri, uri=readonly) as incoming, sqlite3.connect(target) as outgoing:
        incoming.backup(outgoing)


def clone_seed(seed, target):
    before = tree_proof(seed)
    db = ordinary(seed / 'dev.db')
    if any((seed / ('dev.db' + suffix)).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('FIXTURE_SEED_NOT_QUIESCENT')
    target.mkdir(exist_ok=False)
    objects = target / 'objects'
    objects.mkdir()
    backup(db, target / 'dev.db', readonly=True)
    for row in before:
        if not row['path'].startswith('objects/'):
            continue
        source, destination = seed / row['path'], target / row['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                outgoing.write(block)
        if file_proof(destination) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
            raise ValueError('FIXTURE_COPY_CHECKSUM_MISMATCH')
    if tree_proof(seed) != before:
        raise ValueError('FIXTURE_SEED_CHANGED_DURING_CLONE')
    return before


class FixtureSettings(Settings):
    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                   dotenv_settings, file_secret_settings):
        # Explicit fixture arguments and model defaults only. No real env/.env/secrets.
        return (init_settings,)


class DisabledQueue:
    def __init__(self):
        self.attempts = []

    async def rpush(self, key, *values):
        self.attempts.append({'key': key, 'count': len(values)})
        raise RuntimeError('FIXTURE_WORKER_DISPATCH_DISABLED')


class FixtureRateStore:
    def __init__(self):
        self.counts = {}

    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key, seconds):
        return True


async def master_rows(factory, project):
    async with factory() as session:
        rows = {}
        for mapper in sorted(Base.registry.mappers, key=lambda m: m.class_.__tablename__):
            model = mapper.class_
            if not hasattr(model, 'project_id'):
                continue
            values = (await session.scalars(select(model).where(model.project_id == project)
                       .order_by(*model.__table__.primary_key.columns))).all()
            rows[model.__tablename__] = [record_value(value) for value in values]
        return rows


async def configure(factory, output, context):
    # Main registers the real routers and ORM models. Its normal lifespan is not run.
    import app.main as product
    from app.content_generation import ContentGenerationService
    from app.media_intelligence_service import MediaProviderBundle
    from app.media_intelligence_providers import (ContractOnlyStockMediaProvider,
        ContractOnlyImageGenerationProvider, ContractOnlyVideoGenerationProvider)
    from app.auto_edit_providers import ContractOnlyTranscriptionProvider

    settings = FixtureSettings(human_api_enabled=True, human_write_enabled=True,
        database_url='sqlite+aiosqlite:///' + (output / 'dev.db').as_posix(),
        contracts_root=ROOT / 'packages/contracts', object_storage_local_root=output / 'objects',
        human_auth_keys_file=output / '.private/human-auth-registry.json',
        auto_edit_fixture_enabled=False, transcription_provider='contract',
        auto_edit_signal_provider='ffmpeg', vision_fixture_enabled=False, vision_provider='contract',
        trend_fixture_enabled=False, analytics_fixture_enabled=False,
        provider_global_kill_switch_engaged=True, provider_external_execution_enabled=False,
        provider_paid_execution_enabled=False, local_asr_enabled=False,
        asr_external_execution_enabled=False, asr_paid_execution_enabled=False,
        content_generation_provider='contract', content_external_execution_enabled=False,
        media_provider_mode='contract', media_external_execution_enabled=False,
        media_paid_execution_enabled=False, publish_enabled=False,
        publish_external_execution_enabled=False, publish_owner_gate_enabled=False,
        agent_hub_bridge_enabled=False, agent_hub_webhook_external_delivery_enabled=False,
        youtube_analytics_credential_ref='', tiktok_analytics_credential_ref='',
        instagram_analytics_credential_ref='', facebook_analytics_credential_ref='',
        youtube_publishing_credential_ref='', tiktok_publishing_credential_ref='',
        instagram_publishing_credential_ref='', facebook_publishing_credential_ref='')
    product.settings = settings
    app, state = product.app, product.app.state
    storage = LocalObjectStorageProvider(output / 'objects')
    queue = DisabledQueue()
    platform = product.PlatformRepository(factory)
    auto = product.AutoEditRepository(factory)
    timeline = product.TimelineRepository(factory)
    media = product.MediaIntelligenceRepository(factory)
    vision = product.VisionRepository(factory)
    production = product.ProductionRepository(factory)
    publishing = product.PublishingRepository(factory)
    analytics = product.AnalyticsRepository(factory)
    state.database_session_factory = factory
    state.platform_repository, state.object_storage = platform, storage
    state.auto_edit_repository, state.timeline_repository = auto, timeline
    state.media_intelligence_repository, state.vision_repository = media, vision
    state.production_repository = production
    state.default_workspace_id = context['workspace_id']
    state.job_store = product.PostgresJobStore(factory, queue, platform=platform, object_storage=storage)
    state.channel_learning_service = product.ChannelLearningService(factory)
    state.content_service = product.ContentService(platform)
    state.content_generation_service = ContentGenerationService(platform=platform, store=state.job_store,
        queue=queue, mode='contract')
    state.timeline_service = product.TimelineService(repository=timeline, platform=platform,
        auto_edit_repository=auto, media_repository=media, object_storage=storage,
        validator=product.TimelineContractValidator(settings.contracts_root / 'timeline.schema.json'))
    state.auto_edit_analysis_service = product.AutoEditAnalysisService(repository=auto, platform=platform,
        object_storage=storage, transcription_provider=ContractOnlyTranscriptionProvider(),
        signal_provider=product.FFmpegMediaSignalProvider(), staging_root=output / 'analysis-stage')
    state.auto_edit_job_service = product.AutoEditJobService(analysis_service=state.auto_edit_analysis_service, queue=queue)
    state.uploaded_audio_service = product.UploadedAudioService(session_factory=factory, platform=platform,
        object_storage=storage, queue=queue, provider=ContractOnlyTranscriptionProvider(), staging_root=output / 'audio-stage')
    state.vision_analysis_service = product.VisionAnalysisService(repository=vision, auto_edit_repository=auto,
        platform=platform, object_storage=storage, provider=product.ContractOnlyVisionProvider(),
        staging_root=output / 'vision-stage')
    state.media_provider_bundle = MediaProviderBundle(stock=ContractOnlyStockMediaProvider(),
        image=ContractOnlyImageGenerationProvider(), video=ContractOnlyVideoGenerationProvider())
    state.media_planning_service = product.MediaPlanningService(repository=media, auto_edit_repository=auto,
        vision_repository=vision, platform=platform, providers=state.media_provider_bundle,
        allow_external_execution=False, allow_paid_execution=False, object_storage=storage,
        learning=state.channel_learning_service)
    state.media_resolution_service = product.MediaResolutionService(repository=media, platform=platform,
        auto_edit_repository=auto, object_storage=storage, providers=state.media_provider_bundle,
        queue=queue, staging_root=output / 'media-stage', allow_external_execution=False, allow_paid_execution=False)
    state.production_package_service = product.ProductionPackageService(repository=production,
        timeline_repository=timeline, asset_repository=auto, queue=queue, settings=settings)
    state.publishing_service = product.PublishingService(repository=publishing, production_repository=production,
        asset_repository=auto, capabilities=product.PublishingCapabilityRegistry(settings.contracts_root / 'publishing-capabilities.json'),
        providers=product.PublishingProviderRegistry(settings), settings=settings)
    state.analytics_provider_registry = product.AnalyticsProviderRegistry(settings)
    state.analytics_service = product.AnalyticsService(repository=analytics, publishing_repository=publishing,
        platform_repository=platform, providers=state.analytics_provider_registry, queue=queue, settings=settings)
    product.configure_sql_variant_api(app, session_factory=factory, object_storage=storage,
        uploaded_enabled=True, register_routes=False)
    state.human_api_enabled = state.human_write_enabled = True
    state.human_auth_verifier = HumanAuthVerifier.from_file(settings.human_auth_keys_file, max_token_ttl_seconds=3600)
    state.human_rate_limiter = HumanRateLimiter(FixtureRateStore(), requests_per_minute=1000)
    requests = []
    allowed_write = f"/api/v1/projects/{context['project_id']}/audio-transcriptions/{context['audio_id']}/transcript-words"

    @app.middleware('http')
    async def fixture_boundary(request, call_next):
        if request.method not in {'GET', 'HEAD', 'OPTIONS'} and not (request.method == 'POST' and request.url.path == allowed_write):
            requests.append({'method': request.method, 'path': request.url.path, 'status': 503, 'fixture_denied_dispatch': True})
            return JSONResponse({'detail': {'code': 'FIXTURE_DISPATCH_DISABLED',
                'message': 'Owned rehearsal: only explicit child transcript-word review is enabled.'}}, status_code=503)
        response = await call_next(request)
        requests.append({'method': request.method, 'path': request.url.path, 'status': response.status_code})
        return response

    @app.get('/', include_in_schema=False)
    async def studio():
        return FileResponse(ROOT / 'apps/studio-web/studio.html')

    app.mount('/', StaticFiles(directory=ROOT / 'apps/studio-web'), name='fixture-studio-assets')
    return app, queue, requests


async def run(args):
    seed, output = args.seed_root.absolute(), args.output_root.absolute()
    ordinary(output.parent, directory=True)
    if output.exists() or output == seed or seed in output.parents or output in seed.parents:
        raise ValueError('FIXTURE_OUTPUT_MUST_BE_NEW_SEPARATE_ROOT')
    before = await asyncio.to_thread(clone_seed, seed, output)
    private = output / '.private'
    private.mkdir()
    token = 'vf1.variant-browser.' + secrets.token_urlsafe(36)
    now = datetime.now(timezone.utc)
    context = dict(workspace_id=args.workspace_id, master_project_id=args.master_project_id,
                   project_id=args.project_id, audio_id=args.audio_id, family_id=args.family_id, receipt_id=args.receipt_id)
    registry = {'version': 1, 'tokens': {'variant-browser': {'token_id': 'variant-browser',
        'token_sha256': hashlib.sha256(token.encode()).hexdigest(), 'subject': 'usr:variant-browser-fixture',
        'display_name': 'Kiểm thử riêng · media tổng hợp, không ASR thật', 'platform_role': None,
        'workspace_roles': {args.workspace_id: 'editor'}, 'issued_at': now.isoformat(),
        'not_before': now.isoformat(), 'expires_at': (now + timedelta(seconds=3600)).isoformat(), 'enabled': True}}}
    write_json(private / 'human-auth-registry.json', registry)
    with (private / 'fixture-token.txt').open('x', encoding='utf-8') as target:
        target.write(token)
    write_json(output / 'seed-manifest-before.json', {'root': str(seed), 'files': before})
    engine = create_async_engine('sqlite+aiosqlite:///' + (output / 'dev.db').as_posix())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    server_task = server = None
    source_before = None
    app = queue = requests = None
    try:
        app, queue, requests = await configure(factory, output, context)
        # Additive DDL only in the new clone; never mutate seed/live schema.
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        source_before = await master_rows(factory, args.master_project_id)
        write_json(output / 'master-before.json', source_before)
        async with factory() as session:
            parent = await session.scalar(select(UploadedAudioORM).where(UploadedAudioORM.project_id == args.project_id,
                UploadedAudioORM.audio_id == args.audio_id))
            if parent is None:
                raise ValueError('FIXTURE_IMPORTED_AUDIO_NOT_FOUND')
        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        listener.listen(128)
        port = listener.getsockname()[1]
        url = f'http://127.0.0.1:{port}'
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
            lifespan='off', access_log=False, log_level='warning'))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        for _ in range(100):
            if server.started:
                break
            if server_task.done():
                await server_task
                raise ValueError('FIXTURE_HOST_START_FAILED')
            await asyncio.sleep(.05)
        probes = []
        paths = ['/', '/studio.js', '/verified-variant-source.mjs', '/api/v1/auth/session', '/api/v1/capabilities',
            '/api/v1/workspaces', f'/api/v1/workspaces/{args.workspace_id}/projects']
        prefix = f'/api/v1/projects/{args.project_id}'
        paths += [prefix + suffix for suffix in ('/assets', '/analyses', '/media-plans', '/timeline', '/timeline/versions',
            '/publications', '/analytics', '/vision-analyses', '/subtitle-templates', '/scene-intelligence', '/highlight-drafts',
            '/content', '/content-provider', '/content-generation', '/analysis-jobs', '/production-package', '/audio-transcriptions')]
        paths += ['/api/v1/publishing-platforms', '/api/v1/analytics-providers',
            f'/api/v1/projects/{args.master_project_id}/variant-families/{args.family_id}/receipts/{args.receipt_id}',
            prefix + f'/audio-transcriptions/{args.audio_id}', prefix + f'/audio-transcriptions/{args.audio_id}/source']
        async with httpx.AsyncClient(base_url=url, timeout=30, headers={'Authorization': 'Bearer ' + token}) as client:
            for index, path in enumerate(paths):
                response = await client.get(path)
                entry = {'method': 'GET', 'path': path, 'status': response.status_code,
                    'bytes': len(response.content), 'sha256': hashlib.sha256(response.content).hexdigest()}
                if response.headers.get('content-type', '').startswith('application/json'):
                    name = f'probe-{index:02d}.json'
                    write_json(output / name, response.json())
                    entry['response_file'] = name
                probes.append(entry)
            response = await client.get(prefix + f'/audio-transcriptions/{args.audio_id}/source', headers={'Range': 'bytes=0-31'})
            probes.append({'method': 'GET', 'path': prefix + f'/audio-transcriptions/{args.audio_id}/source',
                           'range': 'bytes=0-31', 'status': response.status_code, 'bytes': len(response.content)})
            unauth = await client.get(prefix + '/assets', headers={'Authorization': ''})
            probes.append({'method': 'GET', 'path': prefix + '/assets', 'unauthenticated': True, 'status': unauth.status_code})
        write_json(output / 'probes-before.json', probes)
        failures = [p for p in probes if p['status'] not in (200, 206) and not (p['unauthenticated'] if 'unauthenticated' in p else False)]
        expected_missing = [p for p in failures if p['path'].endswith('/production-package') and p['status'] == 404]
        unexpected = [p for p in failures if p not in expected_missing]
        if unexpected or unauth.status_code != 401 or response.status_code != 206:
            write_json(output / 'probe-failures.json', unexpected)
            raise ValueError('FIXTURE_ACTUAL_API_PROBE_GAP')
        control = {'schema_version': 'owned-sql-variant-browser-host.v1', 'url': url, 'context': context,
            'token_file': str(private / 'fixture-token.txt'), 'registry_sha256': file_proof(private / 'human-auth-registry.json')['sha256'],
            'finish_marker': str(output / 'finish.marker'), 'output_root': str(output), 'source_root': str(ROOT),
            'fixture_semantics': 'Saved synthetic speech/scene evidence; actual SQL/HTTP/read/playback/word CAS, no inference or Owner acceptance.',
            'main_lifespan': False, 'worker_started': False, 'external_provider_calls': 0,
            'renderer_calls': 0, 'paid_operations': 0, 'captured_dto_replay': False,
            'only_allowed_write': 'POST ' + allowed_path(context), 'probe_count': len(probes),
            'expected_missing_package': expected_missing, 'ready': True}
        write_json(output / 'control.json', control)
        print(json.dumps({'ready': True, 'url': url, 'control_path': str(output / 'control.json'),
                          'output_root': str(output), 'probe_count': len(probes)}, indent=2), flush=True)
        deadline = time.monotonic() + args.max_seconds
        while time.monotonic() < deadline and not (output / 'finish.marker').exists() and not server_task.done():
            await asyncio.sleep(.25)
    finally:
        if server is not None:
            server.should_exit = True
        if server_task is not None:
            await server_task
        try:
            current_master = await master_rows(factory, args.master_project_id)
            write_json(output / 'master-after.json', current_master)
            current_audio = current_timeline = None
            if app is not None:
                current_audio = await app.state.uploaded_audio_service.repository.get(args.project_id, args.audio_id)
                current_timeline = await app.state.timeline_repository.get_timeline(args.project_id)
                write_json(output / 'child-audio-after.json', current_audio.model_dump(mode='json'))
                write_json(output / 'child-timeline-after.json', current_timeline.model_dump(mode='json'))
            async with factory() as session:
                usage = await session.scalar(select(func.count()).select_from(ProviderUsageORM))
            write_json(output / 'http-requests.json', requests or [])
            await engine.dispose()
            await asyncio.to_thread(backup, output / 'dev.db', output / 'after-backup.sqlite')
            write_json(output / 'result.json', {'master_unchanged': source_before is not None and canonical(current_master) == canonical(source_before),
                'seed_unchanged': await asyncio.to_thread(tree_proof, seed) == before, 'provider_usage_count': usage,
                'queue_dispatch_attempts': queue.attempts if queue is not None else [],
                'child_transcript_version': current_audio.current.version if current_audio else None,
                'child_timeline_version': current_timeline.current_version if current_timeline else None, 'new_model_inferences': 0,
                'provider_calls': 0, 'renderer_calls': 0, 'network_scope': 'owned loopback HTTP only',
                'paid_operations': 0, 'owner_uat_accepted': False, 'database_backup': file_proof(output / 'after-backup.sqlite')})
        finally:
            await engine.dispose()
        print(json.dumps({'finished': True, 'output_root': str(output), 'result_path': str(output / 'result.json')}, indent=2), flush=True)


def allowed_path(context):
    return f"/api/v1/projects/{context['project_id']}/audio-transcriptions/{context['audio_id']}/transcript-words"


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed-root', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    for name in ('workspace-id', 'master-project-id', 'project-id', 'audio-id', 'family-id', 'receipt-id'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--max-seconds', type=int, default=900, choices=range(60, 3601))
    return parser.parse_args()


if __name__ == '__main__':
    asyncio.run(run(parse()))
