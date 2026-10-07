"""Bounded local readiness and allowlisted, content-free operational telemetry."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import math
from pathlib import Path
import re
import sqlite3
import stat
import time


LOGGER = logging.getLogger('video_factory.native')
EVENTS = {'http_request', 'worker_step', 'worker_failed', 'intelligence_completed', 'intelligence_failed'}
STAGES = {'http', 'starting', 'content', 'transcription', 'media_analysis', 'tts', 'render', 'worker', 'research', 'ideas'}
PROVIDERS = {'assemblyai', 'openai', 'local_vieneu', 'ffmpeg', 'local_io'}


def configure_logging():
    # Do not enable SDK/HTTP library logs: upload URLs may contain credentials.
    if not LOGGER.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter('%(message)s'))
        LOGGER.addHandler(handler)
    LOGGER.propagate = False
    LOGGER.setLevel(logging.INFO)


def identifier(value):
    return value if isinstance(value, str) and re.fullmatch('[a-f0-9]{32}', value) else None


def route_context(path):
    # Never retain URL, query, filename, token, arbitrary slug or user input.
    path = path.split('?', 1)[0]
    project = re.match(r'^/api/projects/([a-f0-9]{32})(?:/|$)', path)
    job = re.match(r'^/api/jobs/([a-f0-9]{32})(?:/|$)', path)
    if project:
        return 'project', project[1], None
    if job:
        return 'job', None, job[1]
    fixed = {'/healthz': 'health', '/readyz': 'readiness', '/api/health': 'health',
        '/api/session': 'session', '/api/runtime-status': 'runtime', '/api/projects': 'projects',
        '/api/connections/assemblyai': 'connection', '/': 'studio'}
    if path in fixed:
        return fixed[path], None, None
    for prefix, route in (('/api/intelligence/', 'intelligence'), ('/api/production/', 'production'),
                          ('/api/assets', 'assets'), ('/api/auto-edit/', 'auto_edit'),('/v1/','bridge')):
        if path.startswith(prefix):
            return route, None, None
    return 'other', None, None


def step_context(step):
    # Only fixed categories leave the process; original arbitrary step strings do not.
    if not isinstance(step, str):
        return 'worker', None
    if step in {'asr_upload', 'asr_create_transcript', 'asr_observe_known_transcript'}:
        return 'transcription', 'assemblyai'
    if step in {'asr_local_media_analysis', 'asr_extract_audio'}:
        return 'media_analysis', 'ffmpeg'
    if step.startswith('content'):
        return 'content', 'openai'
    if step.startswith('tts'):
        return 'tts', 'local_vieneu'
    if step.startswith('render'):
        return 'render', 'ffmpeg'
    return ('starting', 'local_io') if step == 'starting' else ('worker', None)


class Observer:
    def __init__(self, sink=None):
        self.sink = sink or LOGGER.info

    def emit(self, event, *, request_id=None, project_id=None, job_id=None, run_id=None, stage='http',
             provider=None, duration=None, status=None, method=None, route=None):
        if event not in EVENTS:
            return
        record = {'schema': 'vf-native-operation-v1', 'event': event,
            'timestamp': datetime.now(timezone.utc).isoformat(), 'request_id': identifier(request_id),
            'project_id': identifier(project_id), 'job_id': identifier(job_id), 'run_id': identifier(run_id),
            'stage': stage if stage in STAGES else 'worker',
            'provider': provider if provider in PROVIDERS else None,
            'duration': round(duration, 6) if type(duration) in (int, float) and math.isfinite(duration) and 0 <= duration < 86400 else None}
        if event == 'http_request':
            record.update(status=status if type(status) is int and 100 <= status <= 599 else None,
                method=method if method in {'GET', 'POST'} else None,
                route=route if route in {'project', 'job', 'health', 'readiness', 'session', 'runtime',
                    'projects', 'connection', 'studio', 'intelligence', 'production', 'assets', 'auto_edit', 'bridge','other'} else 'other')
        try:
            self.sink(json.dumps(record, ensure_ascii=True, separators=(',', ':')))
        except Exception:
            # Telemetry failure cannot change job outcomes or HTTP responses.
            pass


def unlinked(path):
    try:
        for part in (path, *path.parents):
            info = part.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                return False
        return True
    except OSError:
        return False


def database_ready(path, required):
    if not unlinked(path) or not path.is_file():
        return False
    con = None
    try:
        deadline = time.monotonic() + .5
        con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=.2)
        con.execute('PRAGMA trusted_schema=OFF')
        con.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if not required <= tables:
            return False
        # Read availability/schema, not an integrity or full recovery certification.
        con.execute('SELECT 1 FROM sqlite_master LIMIT 1').fetchone()
        return True
    except (OSError, sqlite3.Error):
        return False
    finally:
        if con is not None:
            con.close()


def readiness(server):
    root = Path(server.config.data_root).absolute()
    checks = {'state_root': unlinked(root) and root.is_dir(),
        'auth_configuration': server.access is None or server.access.ready(),
        'workflow_database': database_ready(root / 'workflow.sqlite3', {'projects', 'jobs', 'events', 'project_versions'}),
        'intelligence_database': database_ready(root / 'intelligence.sqlite3', {'records', 'versions', 'operations', 'decisions'}),
        'production_worker': server.workers_enabled and server.runner.thread.is_alive() and not server.runner.stop.is_set(),
        'intelligence_worker': server.workers_enabled and server.intelligence.thread.is_alive() and not server.intelligence.stop.is_set(),
        'ffmpeg_tools_present': all((server.config.ffmpeg_bin / filename).is_file() for filename in ('ffmpeg.exe', 'ffprobe.exe'))}
    ready = all(checks.values())
    return {'schema': 'vf-native-readiness-v1', 'status': 'ready' if ready else 'not_ready',
        'checks': checks, 'scope': 'local_core_queue_and_media_tool_presence',
        'optional_providers_checked': False, 'provider_calls': 0,
        'runtime_integrity_acceptance_checked': False}, 200 if ready else 503
