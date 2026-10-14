"""Owned read-only Studio video-word rehearsal over historical genuine ASR.

Only GET/HEAD over an independently pinned compact SQLite/Local clone is allowed.
No lifespan, DDL, worker, Redis, model, renderer, paid provider or publishing runs.
Server credentials stay in RAM and the generated no-store bootstrap only.
Shipped browser auth stores the synthetic expiring token in sessionStorage.
The public speech/synthetic card and prior word-CAS fixture are not Owner UAT.
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

ROOT = None  # Set only by the explicit frozen --source-root argument.
LOG = Path('C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007')
SEED_REPORT = LOG / 'word-independent-video-word-browser-seed-n1.json'
SEED_REPORT_SHA = '9c9b3b065942a8e07dd1dd47a85a44d585e7af6adc5e269fd1729163734b9105'
SEED = Path('C:/vfwui/t1-eu71ihc2')
ORIGINAL = Path('C:/vfns-video-real-asr-n1')
DATABASE_SHA = '34fde004df69d7c2eb065dfb313bcc90597a937e7e948a044da8ecfd1114acd9'
ORIGINAL_DATABASE_SHA = 'ef5ecfed1f7d6e7952c8a3f00a47c43b61e9d21175d1ec26dbf5ee05911cab3e'
OBJECT_KEY = ('workspaces/wsp_8582abb5b2004b69acc85bf4/projects/prj_7c9267f5bcf847a4ba7e0625/'
              'uploads/1a77addb76019e92c960f174/synthetic-card-public-fleurs-speech.mp4')
OBJECT_SHA = '1a77addb76019e92c960f17441d025927fa37994ed1a981e3ae512c3d2f39392'
OBJECT_SIZE = 411042
WORKSPACE_ID = 'wsp_8582abb5b2004b69acc85bf4'
PROJECT_ID = 'prj_7c9267f5bcf847a4ba7e0625'
ANALYSIS_ID = 'ana_8c53a48331594c6eb3fdab33'
SELECTED_TRANSCRIPT_ID = 'trn_626c74d3e8a943658851c0a9'
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_TREE_BYTES = 256 * 1024 * 1024

def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ordinary(path, *, directory=False):
    if not path.is_absolute():
        raise ValueError('VIDEO_WORD_BROWSER_ABSOLUTE_PATH_REQUIRED')
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('VIDEO_WORD_BROWSER_LINK_REJECTED')
    info = path.lstat()
    if directory:
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('VIDEO_WORD_BROWSER_DIRECTORY_REQUIRED')
    elif not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('VIDEO_WORD_BROWSER_SINGLE_LINK_FILE_REQUIRED')
    return path


def file_proof(path):
    ordinary(path)
    info = path.stat()
    if info.st_size > MAX_FILE_BYTES:
        raise ValueError('VIDEO_WORD_BROWSER_FILE_LIMIT')
    value = {'bytes': info.st_size, 'sha256': sha(path)}
    after = path.stat()
    if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (
            after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError('VIDEO_WORD_BROWSER_FILE_CHANGED')
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
                raise ValueError('VIDEO_WORD_BROWSER_TREE_LIMIT')
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
        raise ValueError('VIDEO_WORD_BROWSER_FROZEN_HEAD_REQUIRED')
    return {'head': expected, 'branch': call('branch', '--show-current')}


def source_proof():
    paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', 'apps/api/app',
                                    'apps/studio-web', 'packages/contracts'], text=True).splitlines()
    paths = [name for name in paths if '/tests/' not in name and name.endswith(('.py', '.js', '.mjs', '.html', '.css', '.json'))]
    paths.append('scripts/north_star_sql_narration_browser_host.py')
    return [{'path': name, **file_proof(ROOT / name)} for name in sorted(paths)]


def seed_proof():
    if file_proof(SEED_REPORT)['sha256'] != SEED_REPORT_SHA:
        raise ValueError('VIDEO_WORD_BROWSER_SEED_REPORT_CHANGED')
    report = json.loads(SEED_REPORT.read_bytes())
    expected = report['inspected_seeds']
    actual = []
    for root, database in ((ORIGINAL, ORIGINAL / 'evidence/cold-copy.sqlite'), (SEED, SEED / 'clone.sqlite')):
        if any(Path(str(database) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')):
            raise ValueError('VIDEO_WORD_BROWSER_SEED_NOT_QUIESCENT')
        db = file_proof(database)
        object_file = file_proof(root / 'objects' / OBJECT_KEY)
        pinned = next(value for value in expected if Path(value['database']['path']) == database)
        if (db != {key:pinned['database'][key] for key in ('bytes','sha256')}
            or object_file != {key:pinned['object'][key] for key in ('bytes','sha256')}
            or object_file != {'bytes':OBJECT_SIZE,'sha256':OBJECT_SHA}
            or db['sha256'] != (DATABASE_SHA if root == SEED else ORIGINAL_DATABASE_SHA)):
            raise ValueError('VIDEO_WORD_BROWSER_SEED_CHANGED')
        with sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
            connection.execute('PRAGMA query_only=ON')
            if connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or connection.execute('PRAGMA foreign_key_check').fetchall():
                raise ValueError('VIDEO_WORD_BROWSER_DATABASE_INVALID')
            row = connection.execute('SELECT workspace_id,project_id,asset_id,status,source_media_json,provenance_json FROM auto_edit_analyses WHERE analysis_id=?',(ANALYSIS_ID,)).fetchone()
            asset = connection.execute('SELECT workspace_id,project_id,object_key,size_bytes,checksum_sha256,content_type,asset_class,kind,provenance FROM assets WHERE asset_id=?',(row[2],)).fetchone() if row else None
            if not row or not asset or row[0:2] != (WORKSPACE_ID,PROJECT_ID) or row[3] != 'succeeded' or asset[:2] != row[:2] or asset[2:8] != (OBJECT_KEY,OBJECT_SIZE,OBJECT_SHA,'video/mp4','source','video'):
                raise ValueError('VIDEO_WORD_BROWSER_GRAPH_CHANGED')
            provenance = json.loads(asset[8])
            upload = connection.execute('SELECT workspace_id,project_id,asset_id,status,quarantine_state,trusted_at,scan_checksum_sha256,media_metadata_json FROM upload_sessions WHERE upload_id=?',(provenance.get('source_reference'),)).fetchone()
            if (provenance.get('source_type') != 'user_upload' or not upload or upload[:3] != (WORKSPACE_ID,PROJECT_ID,row[2])
                or upload[3] not in ('completed','completed_duplicate') or upload[4] != 'trusted' or not upload[5] or upload[6] != OBJECT_SHA
                or json.loads(upload[7]) != provenance.get('media_metadata') or json.loads(row[4]) != provenance.get('media_metadata')
                or json.loads(row[5]).get('source_asset_checksum') != OBJECT_SHA):
                raise ValueError('VIDEO_WORD_BROWSER_INTAKE_CHANGED')
            if root == SEED:
                timeline = connection.execute('SELECT current_version,current_version_id,source_analysis_id FROM timelines WHERE project_id=?',(PROJECT_ID,)).fetchone()
                selected = connection.execute('SELECT snapshot_json FROM timeline_versions WHERE timeline_version_id=?',(timeline[1],)).fetchone() if timeline else None
                if (not timeline or timeline[0] != 2 or timeline[2] != ANALYSIS_ID or not selected
                    or json.loads(selected[0]).get('metadata',{}).get('transcript_revision',{}).get('transcript_id') != SELECTED_TRANSCRIPT_ID):
                    raise ValueError('VIDEO_WORD_BROWSER_CANONICAL_CHANGED')
        actual.append({'root':str(root),'database':db,'source_object':object_file})
    return actual


def clone(seed_manifest, output):
    if (output.exists() or output.parent.resolve() != Path('C:/').resolve()
            or not re.fullmatch(r'vfns-sql-video-word-browser-[a-z0-9-]{2,32}', output.name)):
        raise ValueError('VIDEO_WORD_BROWSER_NEW_OWNED_ROOT_REQUIRED')
    ordinary(output.parent, directory=True)
    output.mkdir(exist_ok=False)
    for source, destination in ((SEED/'clone.sqlite', output/'readonly.db'),
                                (SEED/'objects'/OBJECT_KEY, output/'objects'/OBJECT_KEY)):
        ordinary(source)
        expected = file_proof(source)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with source.open('rb') as incoming, destination.open('xb') as target:
            copied = 0
            for block in iter(lambda: incoming.read(1024 * 1024), b''):
                copied += len(block)
                if copied > expected['bytes']:
                    raise ValueError('VIDEO_WORD_BROWSER_COPY_LIMIT')
                target.write(block)
        if file_proof(destination) != expected:
            raise ValueError('VIDEO_WORD_BROWSER_COPY_CHANGED')
    if seed_proof() != seed_manifest:
        raise ValueError('VIDEO_WORD_BROWSER_SEED_CHANGED_DURING_COPY')


def mounted_word_ui():
    html = ROOT / 'apps/studio-web/studio.html'
    studio = ROOT / 'apps/studio-web/studio.js'
    module = ROOT / 'apps/studio-web/video-transcript-word-review.mjs'
    return (module.is_file() and 'id="video-transcript-word-review"' in html.read_text(encoding='utf-8')
            and 'initializeVideoTranscriptWordReview' in studio.read_text(encoding='utf-8'))


def database_proof(path):
    proof = file_proof(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True) as connection:
        connection.execute('PRAGMA query_only = ON')
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
        counts = {}
        digest = hashlib.sha256()
        for table in tables:
            if not re.fullmatch('[A-Za-z0-9_]+', table):
                raise ValueError('VIDEO_WORD_BROWSER_SCHEMA_INVALID')
            rows = connection.execute('SELECT * FROM "' + table + '" ORDER BY rowid').fetchall()
            counts[table] = len(rows)
            digest.update(json.dumps([table, rows], sort_keys=True, separators=(',', ':'),
                                     default=lambda value: {'blob_sha256': hashlib.sha256(value).hexdigest()}).encode())
    if file_proof(path) != proof:
        raise ValueError('VIDEO_WORD_BROWSER_DATABASE_CHANGED')
    return {'file': proof, 'table_counts': counts, 'all_rows_sha256': digest.hexdigest()}


class DisabledQueue:
    def __init__(self):
        self.attempts = 0
    async def rpush(self, *args, **kwargs):
        self.attempts += 1
        raise RuntimeError('VIDEO_WORD_BROWSER_DISPATCH_DISABLED')


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
        audio_external_execution_enabled=False, vieneu_local_execution_enabled=False, sql_variant_narration_reuse_enabled=False,
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
    runtime = create_variant_narration_runtime(session_factory=factory, object_storage=storage, assets=auto, enabled=False)
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
    product.configure_sql_variant_api(app, session_factory=factory, object_storage=storage, uploaded_enabled=False, register_routes=False)
    now = datetime.now(timezone.utc)
    registry = HumanAuthRegistry.model_validate({'version':1, 'tokens':{'video-word-browser-fixture':{
        'token_id':'video-word-browser-fixture','token_sha256':hashlib.sha256(token.encode()).hexdigest(),
        'subject':'usr:video-word-browser-readonly-fixture','display_name':'Phiên kiểm thử chỉ đọc · không Owner UAT',
        'platform_role':None,'workspace_roles':{context['workspace_id']:'editor'},'issued_at':now.isoformat(),
        'not_before':now.isoformat(),'expires_at':(now+timedelta(hours=1)).isoformat(),'enabled':True}}})
    state.human_api_enabled, state.human_write_enabled = True, False
    state.human_auth_verifier = HumanAuthVerifier(registry, max_token_ttl_seconds=3600)
    state.human_rate_limiter = HumanRateLimiter(MemoryRateStore(), requests_per_minute=1000)
    requests = []

    @app.middleware('http')
    async def readonly_boundary(request, call_next):
        if request.method not in {'GET','HEAD'}:
            requests.append({'method':request.method,'path':request.url.path,'status':503,'blocked_before_body':True})
            return JSONResponse({'detail':{'code':'VIDEO_WORD_BROWSER_READ_ONLY','message':'Phiên rehearsal chỉ đọc; mọi mutation bị chặn.'}}, status_code=503)
        response = await call_next(request)
        requests.append({'method':request.method,'path':request.url.path,'status':response.status_code})
        return response

    html = (ROOT / 'apps/studio-web/studio.html').read_text(encoding='utf-8')
    entries = re.findall(r'<script type="module" src="(/studio\.js[^\"]*)"></script>', html)
    if len(entries) != 1:
        raise ValueError('VIDEO_WORD_BROWSER_STUDIO_ENTRY_CHANGED')
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

    app.mount('/', StaticFiles(directory=ROOT / 'apps/studio-web'), name='readonly-video-word-studio')
    return app, queue, requests


async def run(args):
    global ROOT
    ROOT = args.source_root
    ordinary(ROOT, directory=True)
    head = verify_head(args.expected_head)
    helper_before = file_proof(Path(__file__).absolute())
    source_before = await completed_io(source_proof)
    seed_before = await completed_io(seed_proof)
    context = {'workspace_id':WORKSPACE_ID,'project_id':PROJECT_ID,'analysis_id':ANALYSIS_ID,
               'selected_transcript_id':SELECTED_TRANSCRIPT_ID,'timeline_version':2}
    mounted = mounted_word_ui()
    if (verify_head(args.expected_head) != head or
            await completed_io(source_proof) != source_before or
            file_proof(Path(__file__).absolute()) != helper_before):
        raise ValueError('VIDEO_WORD_BROWSER_SOURCE_CHANGED_DURING_ADMISSION')
    if not args.serve:
        if await completed_io(seed_proof) != seed_before:
            raise ValueError('VIDEO_WORD_BROWSER_SEED_CHANGED_DURING_PREPARATION')
        write(args.prepare_output, {'schema_version':'sql-video-words-browser-prepare.v1','head':head,'source_root':str(ROOT),
            'source_files':source_before,'helper_source':helper_before,'seed_files':seed_before,'context':context,'word_ui_mounted':mounted,
            'host_started':False,'cloned':False,'model_calls':0,'DDL':0,'token_created':False,
            'fixture_scope':'Historical genuine ASR/public FLEURS speech + synthetic visual, prior automated word revision; no human listening or Owner acceptance.'})
        print(json.dumps({'status':'PREPARED_READ_ONLY_NO_HOST','word_ui_mounted':mounted,'output':str(args.prepare_output)}), flush=True)
        return
    if not mounted:
        raise ValueError('VIDEO_WORD_BROWSER_UI_NOT_MOUNTED')
    await completed_io(clone, seed_before, args.output_root)
    output = args.output_root
    before_db = await completed_io(database_proof, output / 'readonly.db')
    before_objects = await completed_io(tree_proof, output / 'objects')
    if (verify_head(args.expected_head) != head or
            await completed_io(source_proof) != source_before or
            file_proof(Path(__file__).absolute()) != helper_before):
        raise ValueError('VIDEO_WORD_BROWSER_SOURCE_CHANGED_BEFORE_CONFIGURATION')
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
    token = 'vf1.video-word-browser-fixture.' + secrets.token_urlsafe(36)
    app = queue = requests = server = server_task = listener = None
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex
    blocked_outbound = 0
    probes_validated = host_ready = rehearsal_completed = False
    try:
        app, queue, requests = await configure(factory, output, context, token)
        if (verify_head(args.expected_head) != head or
                await completed_io(source_proof) != source_before or
                file_proof(Path(__file__).absolute()) != helper_before):
            raise ValueError('VIDEO_WORD_BROWSER_SOURCE_CHANGED_BEFORE_LISTEN')
        listener = socket.socket()
        listener.bind(('127.0.0.1',0)); listener.listen(128)
        port = listener.getsockname()[1]
        url = 'http://127.0.0.1:' + str(port)
        def guarded_connect(actual_socket, address):
            nonlocal blocked_outbound
            if not isinstance(address, tuple) or address[:2] != ('127.0.0.1', port):
                blocked_outbound += 1
                raise RuntimeError('VIDEO_WORD_BROWSER_EXTERNAL_CONNECT_BLOCKED')
            return original_connect(actual_socket, address)
        def guarded_connect_ex(actual_socket, address):
            nonlocal blocked_outbound
            if not isinstance(address, tuple) or address[:2] != ('127.0.0.1', port):
                blocked_outbound += 1
                raise RuntimeError('VIDEO_WORD_BROWSER_EXTERNAL_CONNECT_BLOCKED')
            return original_connect_ex(actual_socket, address)
        socket.socket.connect, socket.socket.connect_ex = guarded_connect, guarded_connect_ex
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1',port=port,lifespan='off',access_log=False,
            log_level='warning',timeout_graceful_shutdown=5))
        server_task = asyncio.create_task(server.serve(sockets=[listener]))
        for _ in range(100):
            if server.started: break
            if server_task.done(): await server_task; raise ValueError('VIDEO_WORD_BROWSER_START_FAILED')
            await asyncio.sleep(.05)
        if not server.started: raise ValueError('VIDEO_WORD_BROWSER_START_TIMEOUT')
        prefix = '/api/v1/projects/' + context['project_id']
        analysis = prefix + '/analyses/' + context['analysis_id']
        paths = ['/', '/studio.js','/video-transcript-word-review.mjs','/auth.mjs','/api/v1/auth/session','/api/v1/capabilities',
                 '/api/v1/workspaces','/api/v1/workspaces/' + context['workspace_id'] + '/projects']
        paths += [prefix + suffix for suffix in ('','/assets','/analyses','/media-plans','/timeline','/timeline/versions',
            '/content-provider','/content-generation','/analysis-jobs','/audio-transcriptions','/vision-analyses',
            '/scene-intelligence','/highlight-drafts','/subtitle-templates','/publications','/analytics')]
        paths += [analysis, analysis + '/source']
        probes = []
        async with httpx.AsyncClient(base_url=url, timeout=30, trust_env=False, headers={'Authorization':'Bearer ' + token}) as client:
            for index, path in enumerate(paths):
                response = await client.get(path)
                record = {'path':path,'status':response.status_code,'bytes':len(response.content),'sha256':hashlib.sha256(response.content).hexdigest()}
                if path == analysis + '/source':
                    if (response.status_code != 200 or response.headers.get('content-type') != 'video/mp4'
                        or response.headers.get('cache-control') != 'no-store'
                        or response.headers.get('etag') != '"sha256-' + OBJECT_SHA + '"'
                        or response.headers.get('content-length') != str(OBJECT_SIZE)
                        or record['bytes'] != OBJECT_SIZE or record['sha256'] != OBJECT_SHA):
                        raise ValueError('VIDEO_WORD_BROWSER_SOURCE_GET_MISMATCH')
                    record['source_byte_proof'] = True  # No duplicate MP4 is archived.
                if response.headers.get('content-type','').startswith('application/json'):
                    name = 'get-' + str(index).zfill(2) + '.json'
                    write(output / name, response.json()); record['response_file'] = name
                probes.append(record)
            headers_only = await client.head(analysis + '/source')
            if (headers_only.status_code != 200 or headers_only.content != b'' or
                headers_only.headers.get('content-length') != str(OBJECT_SIZE) or
                headers_only.headers.get('etag') != '"sha256-' + OBJECT_SHA + '"'):
                raise ValueError('VIDEO_WORD_BROWSER_SOURCE_HEAD_MISMATCH')
            probes.append({'path':analysis+'/source','method':'HEAD','status':200,'body_bytes':0,'source_headers_verified':True})
            unauthenticated = await client.get(prefix + '/assets', headers={'Authorization':''})
            if unauthenticated.status_code != 401 or any(row['status'] != 200 for row in probes):
                write(output / 'failed-get-probes.json', probes)
                raise ValueError('VIDEO_WORD_BROWSER_ACTUAL_GET_PROBE_GAP')
        write(output / 'get-probes-before.json', probes)
        probes_validated = True
        if await completed_io(database_proof, output / 'readonly.db') != before_db:
            raise ValueError('VIDEO_WORD_BROWSER_GET_CHANGED_DATABASE')
        if queue.attempts or blocked_outbound:
            raise ValueError('VIDEO_WORD_BROWSER_READ_ATTEMPTED_DISPATCH')
        write(output / 'control.json', {'schema_version':'sql-video-words-browser-control.v1','url':url,'context':context,
            'source_root':str(ROOT),'source_head':head,'owned_pid':os.getpid(),'output_root':str(output),
            'finish_marker':str(output / 'finish.marker'),'ready':True,'auth_bootstrap':'Server RAM-only synthetic editor session; actual shipped auth/session',
            'server_token_or_registry_written':False,'browser_token_storage':'shipped auth sessionStorage (synthetic expiring token)',
            'token_body_archived':False,'all_HTTP_writes_disabled':True,'sqlite_immutable_readonly':True,'lifespan':False,'DDL':0,
            'model_calls':0,'provider_calls':0,'renderer_calls':0,'Redis':False,'Owner_UAT':False,'probes':len(probes)})
        print(json.dumps({'status':'OWNED_READ_ONLY_HOST_READY','url':url,'control':str(output / 'control.json')}), flush=True)
        host_ready = True
        deadline = time.monotonic() + args.max_seconds
        while time.monotonic() < deadline and not (output / 'finish.marker').exists() and not server_task.done():
            await asyncio.sleep(.25)
        rehearsal_completed = True
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
        result = {'schema_version':'sql-video-words-browser-result.v1','source_head_unchanged':verify_head(args.expected_head) == head,
            'source_files_unchanged':source_before == after_source,'source_before':source_before,'source_after':after_source,
            'helper_source_unchanged':file_proof(Path(__file__).absolute()) == helper_before,'helper_source':helper_before,
            'original_seed_unchanged':seed_before == after_seed,'seed_file_count':4,
            'cloned_database_unchanged':before_db == after_db,'database_before':before_db,'database_after':after_db,
            'cloned_object_files_unchanged':before_objects == after_objects,'cloned_objects_before':before_objects,
            'queue_dispatch_attempts':queue.attempts if queue is not None else None,'blocked_outbound_attempts':blocked_outbound,
            'HTTP_mutation_attempts':sum(row['method'] not in {'GET','HEAD'} for row in (requests or [])),
            'new_model_inferences':0,'provider_dispatches':0,'renderer_calls':0,'DDL':0,'main_lifespan':False,'Redis':False,
            'server_token_or_registry_written':False,'browser_token_storage':'shipped auth sessionStorage (synthetic expiring token)',
            'token_body_archived':False,'network_scope':'owned loopback HTTP only','Owner_UAT':False,
            'actual_GET_HEAD_probes_validated':probes_validated,'host_ready':host_ready,
            'rehearsal_completed':rehearsal_completed,'finish_marker_seen':(output/'finish.marker').is_file(),
            'fixture_scope':'Historical genuine ASR/public FLEURS speech + synthetic visual, automated word-CAS fixture; no new inference/human listening/Owner acceptance.'}
        passed = all(result[key] for key in ('source_head_unchanged','source_files_unchanged','helper_source_unchanged',
            'original_seed_unchanged','cloned_database_unchanged','cloned_object_files_unchanged'))
        passed = (passed and probes_validated and host_ready and rehearsal_completed and
                  queue is not None and queue.attempts == 0 and blocked_outbound == 0 and result['HTTP_mutation_attempts'] == 0)
        result['status'] = 'READ_ONLY_REHEARSAL_SOURCE_PRESERVED' if passed else 'READ_ONLY_SCOPE_NOT_SATISFIED'
        write(output / 'result.json', result)
        print(json.dumps({'status':'OWNED_READ_ONLY_HOST_FINISHED','result':str(output / 'result.json'),
                          'database_unchanged':result['cloned_database_unchanged'],'source_unchanged':result['source_files_unchanged']}), flush=True)


def parse():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--expected-head',required=True)
    parser.add_argument('--output-root',type=Path,required=True)
    parser.add_argument('--max-seconds',type=int,choices=range(60,3601),default=900)
    parser.add_argument('--serve',action='store_true')
    parser.add_argument('--prepare-output',type=Path)
    args = parser.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.expected_head): parser.error('exact commit SHA required')
    if not args.source_root.is_absolute() or not args.output_root.is_absolute(): parser.error('absolute source/new-owned-root required')
    if args.serve == (args.prepare_output is not None): parser.error('choose serve or prepare-output')
    return args

if __name__ == '__main__':
    asyncio.run(run(parse()))
