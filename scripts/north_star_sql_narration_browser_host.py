"""Owned read-only Studio narration rehearsal over completed SQL speech artifacts.

The normal main routers and current Studio modules are used. This helper never
runs main lifespan, migrations, workers, Redis, a model, TTS, renderer, publishing
or an HTTP mutation. Editor authentication is a RAM-only synthetic session. It
does not constitute Owner UAT, listening acceptance or new provider evidence.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
LOG = Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007')
HANDOFF = LOG / 'sql-spoken-six-local-real-handoff-n1.json'
HANDOFF_SHA = 'dfe3d5e80747b19ca9322ffe4e821754efd1f9858a566f0de8eec6d1940bc7e9'
SEED = Path('C:/vfns-sql-spoken-six-n4')
DATABASE_SHA = 'cf4addc57dad95227d40c28dbc157593b8517398a2237083cbe9df5cb6bb6838'
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TREE_BYTES = 256 * 1024 * 1024


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ordinary(path, *, directory=False):
    if not path.is_absolute():
        raise ValueError('NARRATION_BROWSER_ABSOLUTE_PATH_REQUIRED')
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('NARRATION_BROWSER_LINK_REJECTED')
    info = path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('NARRATION_BROWSER_DIRECTORY_REQUIRED')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('NARRATION_BROWSER_SINGLE_LINK_FILE_REQUIRED')
    return path


def file_proof(path):
    ordinary(path)
    info = path.stat()
    if info.st_size > MAX_FILE_BYTES:
        raise ValueError('NARRATION_BROWSER_FILE_LIMIT')
    value = {'bytes': info.st_size, 'sha256': sha(path)}
    after = path.stat()
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('NARRATION_BROWSER_FILE_CHANGED')
    return value


def tree_proof(root):
    ordinary(root, directory=True)
    rows = []
    total = 0
    for path in sorted(root.rglob('*')):
        ordinary(path, directory=path.is_dir())
        if path.is_file():
            value = file_proof(path)
            total += value['bytes']
            if len(rows) >= 1024 or total > MAX_TREE_BYTES:
                raise ValueError('NARRATION_BROWSER_TREE_LIMIT')
            rows.append({'path': path.relative_to(root).as_posix(), **value})
    return rows


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
        stream.write('\n')


async def completed_io(function, *arguments):
    task = asyncio.create_task(asyncio.to_thread(function, *arguments))
    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            cancelled = True
    result = task.result()
    if cancelled:
        raise asyncio.CancelledError
    return result


def verify_head(expected):
    call = lambda *args: subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()
    if call('rev-parse', 'HEAD') != expected or call('diff', '--name-only') or call('diff', '--cached', '--name-only'):
        raise ValueError('NARRATION_BROWSER_FROZEN_HEAD_REQUIRED')
    return {'head': expected, 'branch': call('branch', '--show-current')}


def source_proof():
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', 'apps/api/app',
                                    'apps/studio-web', 'packages/contracts'], text=True).splitlines()
    paths = [name for name in paths if '/tests/' not in name and name.endswith(('.py', '.js', '.mjs', '.html', '.css', '.json'))]
    paths.append('scripts/north_star_sql_narration_browser_host.py')
    return [{'path': name, **file_proof(ROOT / name)} for name in sorted(paths)]


def seed_proof():
    if sha(HANDOFF) != HANDOFF_SHA:
        raise ValueError('NARRATION_BROWSER_HANDOFF_CHANGED')
    handoff = json.loads(HANDOFF.read_bytes())
    expected = [{'path': row['relative_path'].replace('\\', '/'), 'bytes': row['bytes'],
                 'sha256': row['sha256']} for row in handoff['all_required_files']]
    current = tree_proof(SEED)
    actual = {row['path']: row for row in current}
    if any(actual.get(row['path']) != row for row in expected) or sha(SEED / 'cold.db') != DATABASE_SHA:
        raise ValueError('NARRATION_BROWSER_COMPLETED_SEED_CHANGED')
    if any((SEED / ('cold.db' + suffix)).exists() for suffix in ('-wal', '-shm', '-journal')):
        raise ValueError('NARRATION_BROWSER_SEED_NOT_QUIESCENT')
    return current


def clone(seed_manifest, output):
    if (output.exists() or output.parent.resolve() != Path('C:/').resolve()
            or not re.fullmatch(r'vfns-sql-narration-browser-[a-z0-9-]{2,32}', output.name)):
        raise ValueError('NARRATION_BROWSER_NEW_OWNED_ROOT_REQUIRED')
    ordinary(output.parent, directory=True)
    output.mkdir(exist_ok=False)
    for row in seed_manifest:
        if row['path'] != 'cold.db' and not row['path'].startswith('objects/'):
            continue
        source = SEED / row['path']
        destination = output / ('readonly.db' if row['path'] == 'cold.db' else row['path'])
        destination.parent.mkdir(parents=True, exist_ok=True)
        ordinary(source)
        with source.open('rb') as incoming, destination.open('xb') as target:
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                target.write(block)
        if file_proof(destination) != {'bytes': row['bytes'], 'sha256': row['sha256']}:
            raise ValueError('NARRATION_BROWSER_COPY_CHANGED')
    if tree_proof(SEED) != seed_manifest:
        raise ValueError('NARRATION_BROWSER_SEED_CHANGED_DURING_COPY')


def database_proof(path):
    proof = file_proof(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        connection.execute('PRAGMA query_only = ON')
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {}
        digest = hashlib.sha256()
        for table in tables:
            if not re.fullmatch('[A-Za-z0-9_]+', table):
                raise ValueError('NARRATION_BROWSER_SCHEMA_INVALID')
            rows = connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
            counts[table] = len(rows)
            digest.update(json.dumps([table, rows], sort_keys=True, separators=(',', ':'),
                                     default=lambda value: {'blob_sha256': hashlib.sha256(value).hexdigest()}).encode())
    if file_proof(path) != proof:
        raise ValueError('NARRATION_BROWSER_DATABASE_CHANGED')
    return {'file': proof, 'table_counts': counts, 'all_rows_sha256': digest.hexdigest()}


class DisabledQueue:
    def __init__(self):
        self.attempts = 0
    async def rpush(self, *args, **kwargs):
        self.attempts += 1
        raise RuntimeError('NARRATION_BROWSER_DISPATCH_DISABLED')


class MemoryRateStore:
    def __init__(self):
        self.counts = {}
    async def incr(self, key):
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]
    async def expire(self, *args):
        return True


async def configure(factory, output, context, token):
    # Discard process ambient configuration before the first app.config import;
    # the cloned root has no .env. The invoking parent environment is untouched.
    inherited = {key: os.environ[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG') if key in os.environ}
    os.environ.clear()
    os.environ.update(inherited, PYTHONDONTWRITEBYTECODE='1')
    os.chdir(output)
    sys.path.insert(0, str(ROOT / 'apps/api'))
    from app.config import Settings
    import app.main as product
    from app.human_auth import HumanAuthRegistry, HumanAuthVerifier, HumanRateLimiter
    from app.content_generation import ContentGenerationService
    from app.media_intelligence_service import MediaProviderBundle
    from app.media_intelligence_providers import ContractOnlyStockMediaProvider, ContractOnlyImageGenerationProvider, ContractOnlyVideoGenerationProvider
    from app.auto_edit_providers import ContractOnlyTranscriptionProvider
    from app.object_storage import LocalObjectStorageProvider
    from app.sql_variant_narration_runtime import create_variant_narration_runtime
    from fastapi.responses import HTMLResponse, Response, JSONResponse
    from fastapi.staticfiles import StaticFiles
    from starlette.requests import Request
    # FastAPI resolves postponed annotations using module globals, not this
    # configuration function's locals. No application imports occur at startup
    # of --prepare; this name is installed only for explicit host configuration.
    globals()['BrowserRequest'] = Request

    class FixtureSettings(Settings):
        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
            return (init_settings,)

    settings = FixtureSettings(human_api_enabled=True, human_write_enabled=False,
        database_url='sqlite+aiosqlite:///file:' + (output / 'readonly.db').as_posix() + '?mode=ro&immutable=1&uri=true',
        contracts_root=ROOT / 'packages/contracts', object_storage_provider='local', object_storage_local_root=output / 'objects',
        auto_edit_fixture_enabled=False, transcription_provider='contract', auto_edit_signal_provider='ffmpeg',
        vision_fixture_enabled=False, vision_provider='contract', trend_fixture_enabled=False, analytics_fixture_enabled=False,
        provider_global_kill_switch_engaged=True, provider_external_execution_enabled=False, provider_paid_execution_enabled=False,
        local_asr_enabled=False, asr_external_execution_enabled=False, asr_paid_execution_enabled=False,
        content_generation_provider='contract', content_external_execution_enabled=False, media_provider_mode='contract',
        media_external_execution_enabled=False, media_paid_execution_enabled=False, audio_tts_provider='contract',
        audio_external_execution_enabled=False, vieneu_local_execution_enabled=False, sql_variant_narration_reuse_enabled=True,
        publish_enabled=False, publish_external_execution_enabled=False, publish_owner_gate_enabled=False,
        agent_hub_bridge_enabled=False, agent_hub_webhook_external_delivery_enabled=False,
        youtube_analytics_credential_ref='', tiktok_analytics_credential_ref='', instagram_analytics_credential_ref='',
        facebook_analytics_credential_ref='', youtube_publishing_credential_ref='', tiktok_publishing_credential_ref='',
        instagram_publishing_credential_ref='', facebook_publishing_credential_ref='')
    product.settings = settings
    app, state = product.app, product.app.state
    storage = LocalObjectStorageProvider(output / 'objects')
    queue = DisabledQueue()
    platform, auto = product.PlatformRepository(factory), product.AutoEditRepository(factory)
    timeline, media, vision = product.TimelineRepository(factory), product.MediaIntelligenceRepository(factory), product.VisionRepository(factory)
    runtime = create_variant_narration_runtime(session_factory=factory, object_storage=storage, assets=auto, enabled=True)
    production = product.ProductionRepository(factory, variant_narration_admission=runtime.admission, variant_narration_fence=runtime.fence)
    publishing, analytics = product.PublishingRepository(factory), product.AnalyticsRepository(factory)
    state.database_session_factory = factory
    state.platform_repository, state.object_storage = platform, storage
    state.auto_edit_repository, state.timeline_repository = auto, timeline
    state.media_intelligence_repository, state.vision_repository = media, vision
    state.production_repository, state.sql_variant_narration_runtime = production, runtime
    state.default_workspace_id = context['workspace_id']
    state.job_store = product.PostgresJobStore(factory, queue, platform=platform, object_storage=storage)
    state.channel_learning_service = product.ChannelLearningService(factory)
    state.content_service = product.ContentService(platform)
    state.content_generation_service = ContentGenerationService(platform=platform, store=state.job_store, queue=queue, mode='contract')
    state.timeline_service = product.TimelineService(repository=timeline, platform=platform,
        auto_edit_repository=auto, media_repository=media, object_storage=storage,
        validator=product.TimelineContractValidator(settings.contracts_root / 'timeline.schema.json'))
    state.auto_edit_analysis_service = product.AutoEditAnalysisService(repository=auto, platform=platform, object_storage=storage,
        transcription_provider=ContractOnlyTranscriptionProvider(), signal_provider=product.FFmpegMediaSignalProvider(), staging_root=output / 'unused-analysis')
    state.auto_edit_job_service = product.AutoEditJobService(analysis_service=state.auto_edit_analysis_service, queue=queue)
    state.uploaded_audio_service = product.UploadedAudioService(session_factory=factory, platform=platform, object_storage=storage,
        queue=queue, provider=ContractOnlyTranscriptionProvider(), staging_root=output / 'unused-audio')
    state.vision_analysis_service = product.VisionAnalysisService(repository=vision, auto_edit_repository=auto,
        platform=platform, object_storage=storage, provider=product.ContractOnlyVisionProvider(), staging_root=output / 'unused-vision')
    bundle = MediaProviderBundle(stock=ContractOnlyStockMediaProvider(), image=ContractOnlyImageGenerationProvider(), video=ContractOnlyVideoGenerationProvider())
    state.media_provider_bundle = bundle
    state.media_planning_service = product.MediaPlanningService(repository=media, auto_edit_repository=auto,
        vision_repository=vision, platform=platform, providers=bundle, allow_external_execution=False, allow_paid_execution=False,
        object_storage=storage, learning=state.channel_learning_service)
    state.media_resolution_service = product.MediaResolutionService(repository=media, platform=platform,
        auto_edit_repository=auto, object_storage=storage, providers=bundle, queue=queue, staging_root=output / 'unused-media',
        allow_external_execution=False, allow_paid_execution=False)
    state.production_package_service = product.ProductionPackageService(repository=production,
        timeline_repository=timeline, asset_repository=auto, queue=queue, settings=settings)
    state.production_render_download_root = output / 'read-downloads'
    state.publishing_service = product.PublishingService(repository=publishing, production_repository=production,
        asset_repository=auto, capabilities=product.PublishingCapabilityRegistry(settings.contracts_root / 'publishing-capabilities.json'),
        providers=product.PublishingProviderRegistry(settings), settings=settings)
    state.analytics_provider_registry = product.AnalyticsProviderRegistry(settings)
    state.analytics_service = product.AnalyticsService(repository=analytics, publishing_repository=publishing,
        platform_repository=platform, providers=state.analytics_provider_registry, queue=queue, settings=settings)
    product.configure_sql_variant_api(app, session_factory=factory, object_storage=storage, uploaded_enabled=True, register_routes=False)
    now = datetime.now(timezone.utc)
    registry = HumanAuthRegistry.model_validate({'version':1, 'tokens':{'narration-browser-fixture':{
        'token_id':'narration-browser-fixture','token_sha256':hashlib.sha256(token.encode()).hexdigest(),
        'subject':'usr:narration-browser-readonly-fixture','display_name':'Phiên kiểm thử chỉ đọc · không Owner UAT',
        'platform_role':None,'workspace_roles':{context['workspace_id']:'editor'},'issued_at':now.isoformat(),
        'not_before':now.isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat(),'enabled':True}}})
    state.human_api_enabled, state.human_write_enabled = True, False
    state.human_auth_verifier = HumanAuthVerifier(registry, max_token_ttl_seconds=3600)
    state.human_rate_limiter = HumanRateLimiter(MemoryRateStore(), requests_per_minute=1000)
    requests = []

    @app.middleware('http')
    async def readonly_boundary(request, call_next):
        if request.method not in {'GET','HEAD','OPTIONS'}:
            requests.append({'method':request.method,'path':request.url.path,'status':503,'blocked_before_body':True})
            return JSONResponse({'detail':{'code':'NARRATION_BROWSER_READ_ONLY','message':'Phiên rehearsal chỉ đọc; mọi mutation bị chặn.'}}, status_code=503)
        response = await call_next(request)
        requests.append({'method':request.method,'path':request.url.path,'status':response.status_code})
        return response

    html = (ROOT / 'apps/studio-web/studio.html').read_text(encoding='utf-8')
    entries = re.findall(r'<script type="module" src="(/studio\.js[^\"]*)"></script>', html)
    if len(entries) != 1:
        raise ValueError('NARRATION_BROWSER_STUDIO_ENTRY_CHANGED')
    entry = entries[0]
    html = html.replace('<script type="module" src="' + entry + '"></script>',
                        '<script type="module" src="/__fixture_session.mjs"></script>')
    session_module = ('import {setSessionToken} from "/auth.mjs";\nsetSessionToken(' + json.dumps(token) + ');\n'
        + 'localStorage.setItem("npd-studio-project",' + json.dumps(context['project_id']) + ');\n'
        + 'document.title="[Chỉ đọc fixture] "+document.title;\nawait import(' + json.dumps(entry) + ');\n')

    @app.get('/', include_in_schema=False)
    async def studio():
        return HTMLResponse(html, headers={'Cache-Control':'no-store'})

    @app.get('/__fixture_session.mjs', include_in_schema=False)
    async def session_bootstrap(request: BrowserRequest):
        # Generated only in RAM. Never persist or include its body in evidence.
        if request.client.host != '127.0.0.1' or request.query_params or request.headers.get('sec-fetch-site') != 'same-origin':
            return Response(status_code=403)
        return Response(session_module, media_type='application/javascript', headers={'Cache-Control':'no-store'})

    app.mount('/', StaticFiles(directory=ROOT / 'apps/studio-web'), name='readonly-narration-studio')
    return app, queue, requests


async def run(args):
    head = verify_head(args.expected_head)
    source_before = await completed_io(source_proof)
    seed_before = await completed_io(seed_proof)
    outcome = json.loads((SEED / 'outcome.json').read_bytes())
    child = next((row for row in outcome['children'] if row['profile']['target'] == args.target), None)
    if child is None:
        raise ValueError('NARRATION_BROWSER_TARGET_NOT_FOUND')
    receipt = json.loads((SEED / 'children' / args.target / 'narration-receipt.json').read_bytes())
    context = {'workspace_id':receipt['workspace_id'], 'master_project_id':outcome['master_project_id'],
        'project_id':child['project_id'],'family_id':outcome['family_id'],'receipt_id':receipt['receipt_id'],
        'target':args.target, 'all_children':outcome['children']}
    if not args.serve:
        write(args.prepare_output, {'schema_version':'sql-narration-browser-word-prepare.v1','head':head,'source_files':source_before,
            'seed_files':seed_before,'context':context,'host_started':False,'model_calls':0,'DDL':0,'token_created':False})
        print(json.dumps({'status':'PREPARED_READ_ONLY_NO_HOST','output':str(args.prepare_output)}), flush=True)
        return
    await completed_io(clone, seed_before, args.output_root)
    output = args.output_root
    before_db = await completed_io(database_proof, output / 'readonly.db')
    before_objects = await completed_io(tree_proof, output / 'objects')
    import httpx
    import uvicorn
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlalchemy import event
    engine = create_async_engine('sqlite+aiosqlite:///file:' + (output / 'readonly.db').as_posix() + '?mode=ro&immutable=1&uri=true')
    @event.listens_for(engine.sync_engine, 'connect')
    def connection_read_only(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA query_only=ON')
        cursor.close()
    factory = async_sessionmaker(engine, expire_on_commit=False)
    token = 'vf1.narration-browser-fixture.' + secrets.token_urlsafe(36)
    app = queue = requests = server = server_task = listener = None
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    blocked_outbound = 0
    try:
        app, queue, requests = await configure(factory, output, context, token)
        listener = socket.socket()
        listener.bind(('127.0.0.1',0)); listener.listen(128)
        port = listener.getsockname()[1]
        url = 'http://127.0.0.1:' + str(port)
        def guarded_connect(actual_socket, address):
            nonlocal blocked_outbound
            if not isinstance(address, tuple) or address[:2] != ('127.0.0.1', port):
                blocked_outbound += 1
                raise RuntimeError('NARRATION_BROWSER_EXTERNAL_CONNECT_BLOCKED')
            return original_connect(actual_socket, address)
        def guarded_connect_ex(actual_socket, address):
            nonlocal blocked_outbound
            if not isinstance(address, tuple) or address[:2] != ('127.0.0.1', port):
                blocked_outbound += 1
                raise RuntimeError('NARRATION_BROWSER_EXTERNAL_CONNECT_BLOCKED')
            return original_connect_ex(actual_socket, address)
        socket.socket.connect, socket.socket.connect_ex = guarded_connect, guarded_connect_ex
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',port=port,lifespan='off',access_log=False,
            log_level='warning',timeout_graceful_shutdown=5))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        for _ in range(100):
            if server.started: break
            if server_task.done(): await server_task; raise ValueError('NARRATION_BROWSER_START_FAILED')
            await asyncio.sleep(.05)
        if not server.started: raise ValueError('NARRATION_BROWSER_START_TIMEOUT')
        prefix = '/api/v1/projects/' + context['project_id']
        narration = '/api/v1/projects/' + context['master_project_id'] + '/variant-families/' + context['family_id'] + '/children/' + context['project_id']
        paths = ['/', '/studio.js','/sql-variant-narration.mjs','/api/v1/auth/session','/api/v1/capabilities',
                 '/api/v1/workspaces','/api/v1/workspaces/' + context['workspace_id'] + '/projects']
        paths += [prefix + suffix for suffix in ('','/assets','/analyses','/media-plans','/timeline','/timeline/versions',
            '/production-package','/production-history','/content','/content-provider','/content-generation','/analysis-jobs',
            '/audio-transcriptions','/vision-analyses','/scene-intelligence','/highlight-drafts','/subtitle-templates','/publications','/analytics')]
        paths += ['/api/v1/publishing-platforms','/api/v1/analytics-providers',
                  narration + '/narration-reuse-availability', narration + '/narration-reuse-proposal',
                  narration + '/narration-receipts/' + context['receipt_id']]
        probes = []
        async with httpx.AsyncClient(base_url=url, timeout=30, trust_env=False, headers={'Authorization':'Bearer ' + token}) as client:
            for index, path in enumerate(paths):
                response = await client.get(path)
                record = {'path':path,'status':response.status_code,'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest()}
                if response.headers.get('content-type','').startswith('application/json'):
                    name = 'get-' + str(index).zfill(2) + '.json'
                    write(output / name, response.json()); record['response_file'] = name
                probes.append(record)
            unauthenticated = await client.get(prefix + '/assets', headers={'Authorization':''})
            if unauthenticated.status_code != 401 or any(row['status'] != 200 for row in probes):
                write(output / 'failed-get-probes.json', probes)
                raise ValueError('NARRATION_BROWSER_ACTUAL_GET_PROBE_GAP')
        write(output / 'get-probes-before.json', probes)
        if await completed_io(database_proof, output / 'readonly.db') != before_db:
            raise ValueError('NARRATION_BROWSER_GET_CHANGED_DATABASE')
        if queue.attempts or blocked_outbound:
            raise ValueError('NARRATION_BROWSER_READ_ATTEMPTED_DISPATCH')
        write(output / 'control.json', {'schema_version':'sql-narration-browser-word-control.v1','url':url,'context':context,
            'source_root':str(ROOT),'source_head':head,'owned_pid':os.getpid(),'output_root':str(output),
            'finish_marker':str(output / 'finish.marker'),'ready':True,'auth_bootstrap':'RAM-only synthetic editor session; actual auth/session',
            'token_persisted':False,'all_HTTP_writes_disabled':True,'sqlite_immutable_readonly':True,'lifespan':False,'DDL':0,
            'model_calls':0,'provider_calls':0,'renderer_calls':0,'Redis':False,'Owner_UAT':False,'probes':len(probes)})
        print(json.dumps({'status':'OWNED_READ_ONLY_HOST_READY','url':url,'control':str(output / 'control.json')}), flush=True)
        deadline = time.monotonic() + args.max_seconds
        while time.monotonic() < deadline and not (output / 'finish.marker').exists() and not server_task.done():
            await asyncio.sleep(.25)
    finally:
        if server is not None: server.should_exit = True
        if server_task is not None:
            while not server_task.done():
                try: await asyncio.shield(server_task)
                except asyncio.CancelledError: pass
            server_task.result()
        socket.socket.connect, socket.socket.connect_ex = original_connect, original_connect_ex
        if listener is not None: listener.close()
        await engine.dispose()
        after_db = await completed_io(database_proof, output / 'readonly.db')
        after_objects = await completed_io(tree_proof, output / 'objects')
        after_seed = await completed_io(seed_proof)
        after_source = await completed_io(source_proof)
        write(output / 'http-request-statuses.json', requests or [])
        result = {'schema_version':'sql-narration-browser-word-result.v1','source_head_unchanged':verify_head(args.expected_head) == head,
            'source_files_unchanged':source_before == after_source,'source_before':source_before,'source_after':after_source,
            'original_seed_unchanged':seed_before == after_seed,'seed_file_count':len(seed_before),
            'cloned_database_unchanged':before_db == after_db,'database_before':before_db,'database_after':after_db,
            'cloned_object_files_unchanged':before_objects == after_objects,'cloned_objects_before':before_objects,
            'queue_dispatch_attempts':queue.attempts if queue is not None else None,'blocked_outbound_attempts':blocked_outbound,
            'HTTP_mutation_attempts':sum(row['method'] not in {'GET','HEAD','OPTIONS'} for row in (requests or [])),
            'new_model_inferences':0,'provider_dispatches':0,'renderer_calls':0,'DDL':0,'main_lifespan':False,'Redis':False,
            'token_body_or_registry_archived':False,'network_scope':'owned loopback HTTP only','Owner_UAT':False,
            'fixture_scope':'Existing genuine master speech reused by child receipts; manual source/clock/editor/reviewer fixture, no new inference or listening acceptance.'}
        passed = all(result[key] for key in ('source_head_unchanged','source_files_unchanged',
            'original_seed_unchanged','cloned_database_unchanged','cloned_object_files_unchanged'))
        passed = passed and queue is not None and queue.attempts == 0 and blocked_outbound == 0 and result['HTTP_mutation_attempts'] == 0
        result['status'] = 'READ_ONLY_REHEARSAL_SOURCE_PRESERVED' if passed else 'READ_ONLY_SCOPE_NOT_SATISFIED'
        write(output / 'result.json', result)
        print(json.dumps({'status':'OWNED_READ_ONLY_HOST_FINISHED','result':str(output / 'result.json'),
                          'database_unchanged':result['cloned_database_unchanged'],'source_unchanged':result['source_files_unchanged']}), flush=True)


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--target',choices=['youtube_landscape','youtube_shorts','tiktok','instagram_reels','social_square','social_feed'],default='youtube_shorts')
    parser.add_argument('--max-seconds',type=int,choices=range(60,3601),default=900)
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--prepare-output',type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.expected_head): parser.error('exact commit SHA required')
    if not args.output_root.is_absolute(): parser.error('absolute new owned output root required')
    if args.serve == (args.prepare_output is not None): parser.error('choose serve or prepare-output')
    return args


if __name__ == '__main__':
    asyncio.run(run(parse()))
