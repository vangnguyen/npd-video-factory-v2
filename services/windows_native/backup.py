"""Offline Native snapshots and checksum-anchored restore into a fresh directory."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile

from .contracts import WorkflowError, canonical, digest, file_sha
from .pipeline import Config, REPO
from .store import now

MAX_FILES = 50000
MAX_TOTAL = 10 * 1024**3
MAX_FILE = 2 * 1024**3
MAX_MANIFEST = 8 * 1024**2
DATABASES = ('workflow.sqlite3', 'intelligence.sqlite3')
EXCLUDED = {'.server.lock', 'workflow.sqlite3-wal', 'workflow.sqlite3-shm',
            'intelligence.sqlite3-wal', 'intelligence.sqlite3-shm'}


def io_path(path):
    """Use Windows extended syntax only for IO after ordinary containment checks."""
    path=Path(path).absolute();value=str(path)
    if os.name=='nt' and len(value)>=240 and not value.startswith('\\\\?\\'):
        return Path('\\\\?\\UNC\\'+value[2:] if value.startswith('\\\\') else '\\\\?\\'+value)
    return path


def guard(path, *, exists=False):
    path = Path(path).absolute()
    if '..' in path.parts:
        raise WorkflowError('BACKUP_PATH_INVALID', 400)
    for item in reversed((path, *path.parents)):
        try:
            info = io_path(item).lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise WorkflowError('BACKUP_LINKED_PATH_REJECTED', 400)
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            raise WorkflowError('BACKUP_LINKED_PATH_REJECTED', 400)
    if exists and not io_path(path).exists():
        raise WorkflowError('BACKUP_PATH_NOT_FOUND', 404)
    return path


def relative_name(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 1024 or '\\' in value or ':' in value or '\x00' in value:
        raise WorkflowError('BACKUP_ENTRY_PATH_INVALID', 400)
    parts = value.split('/')
    if any(part in ('', '.', '..') or part.rstrip(' .') != part
           or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part, re.I) for part in parts):
        raise WorkflowError('BACKUP_ENTRY_PATH_INVALID', 400)
    if PurePosixPath(value).is_absolute():
        raise WorkflowError('BACKUP_ENTRY_PATH_INVALID', 400)
    return value


@contextmanager
def offline_lease(root):
    guard(root / '.server.lock')
    if os.name == 'nt':
        from .windows_job import lock_data_root
        handle = lock_data_root(root)
    else:
        import fcntl
        handle = (root / '.server.lock').open('a+b')
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            handle.close()
            raise WorkflowError('DATA_ROOT_ALREADY_IN_USE') from None
    try:
        yield
    finally:
        handle.close()


def read_database(path):
    con = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=5)
    con.execute('PRAGMA trusted_schema=OFF')
    return con


def database_status(path):
    con = read_database(path)
    try:
        if con.execute('PRAGMA quick_check').fetchall() != [('ok',)]:
            raise WorkflowError('BACKUP_DATABASE_INTEGRITY_FAILED')
        tables = {row[0] for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        expected = {'projects', 'jobs', 'project_versions', 'events'} if path.name == 'workflow.sqlite3' else {'records', 'versions', 'operations', 'decisions'}
        if not expected <= tables:
            raise WorkflowError('BACKUP_DATABASE_SCHEMA_UNSUPPORTED')
        counts = {table: con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0] for table in sorted(expected)}
        if path.name == 'workflow.sqlite3':
            busy = con.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','running','retrying')").fetchone()[0]
            if 'native_cost_operations' in tables:
                counts['native_cost_operations'] = con.execute('SELECT count(*) FROM native_cost_operations').fetchone()[0]
            if 'native_rights_requests' in tables:counts['native_rights_requests']=con.execute('SELECT count(*) FROM native_rights_requests').fetchone()[0]
            if 'native_rights_override_requests' in tables:counts['native_rights_override_requests']=con.execute('SELECT count(*) FROM native_rights_override_requests').fetchone()[0]
            for name in ('native_stock_bindings','native_stock_jobs','native_stock_imports','native_stock_events'):
                if name in tables:counts[name]=con.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0]
            if 'native_stock_jobs' in tables:busy+=con.execute("SELECT count(*) FROM native_stock_jobs WHERE status IN ('queued','running','retry_scheduled')").fetchone()[0]
            for name in ('native_publications','native_publication_events','native_analytics_syncs','native_analytics_snapshots','native_analytics_events','native_vision_intents','native_vision_events','native_source_variant_batches','native_bridge_bindings','native_bridge_events','native_bridge_requests','native_bridge_deliveries','native_bridge_attempts','native_bridge_cursors','native_bridge_selections'):
                if name in tables:counts[name]=con.execute('SELECT count(*) FROM "'+name+'"').fetchone()[0]
            if 'native_publications' in tables:
                busy+=con.execute("SELECT count(*) FROM native_publications WHERE status IN ('queued','scheduled')").fetchone()[0]
            if 'native_analytics_syncs' in tables:
                busy+=con.execute("SELECT count(*) FROM native_analytics_syncs WHERE status IN ('queued','scheduled','retry_scheduled')").fetchone()[0]
            if 'native_vision_intents' in tables:
                busy+=con.execute("SELECT count(*) FROM native_vision_intents WHERE status='queued'").fetchone()[0]
            if 'native_bridge_deliveries' in tables:
                busy+=con.execute("SELECT count(*) FROM native_bridge_deliveries WHERE status IN ('queued','running','retry_scheduled')").fetchone()[0]
            for identifier, revision, document in con.execute('SELECT id,revision,document FROM projects'):
                history = con.execute('SELECT document FROM project_versions WHERE project_id=? AND revision=?', (identifier, revision)).fetchone()
                if history is None or digest(json.loads(document)) != digest(json.loads(history[0])):
                    raise WorkflowError('BACKUP_PROJECT_HISTORY_INTEGRITY_FAILED')
        else:
            if 'native_bridge_source_events' in tables:counts['native_bridge_source_events']=con.execute('SELECT count(*) FROM native_bridge_source_events').fetchone()[0]
            busy = con.execute("SELECT count(*) FROM operations WHERE status IN ('QUEUED','RUNNING')").fetchone()[0]
            for identifier, version, document in con.execute('SELECT id,version,document FROM records'):
                history = con.execute('SELECT document,sha256 FROM versions WHERE id=? AND version=?', (identifier, version)).fetchone()
                if history is None or digest(json.loads(document)) != history[1] or digest(json.loads(history[0])) != history[1]:
                    raise WorkflowError('BACKUP_INTELLIGENCE_HISTORY_INTEGRITY_FAILED')
        logical = hashlib.sha256()
        for line in con.iterdump():
            logical.update(line.encode('utf-8')); logical.update(b'\n')
        return {'quick_check': 'ok', 'counts': counts, 'active_operations': busy,
                'user_version': con.execute('PRAGMA user_version').fetchone()[0],
                'logical_sha256': logical.hexdigest()}
    finally:
        con.close()


def snapshot_database(source, target):
    started = time.monotonic()
    def progress(*_args):
        if time.monotonic() - started > 180:
            raise WorkflowError('BACKUP_DATABASE_TIMEOUT')
    original = read_database(source)
    target_con = sqlite3.connect(target)
    try:
        original.backup(target_con, pages=128, progress=progress, sleep=.05)
    finally:
        target_con.close()
        original.close()


def entries(root):
    result = []
    def walk(folder):
        with os.scandir(folder) as scanned:
            items = sorted(scanned, key=lambda item: item.name)
        for item in items:
            path = guard(Path(item.path), exists=True)
            if item.is_dir(follow_symlinks=False):
                walk(path)
            elif item.is_file(follow_symlinks=False):
                name = path.relative_to(root).as_posix()
                if name in EXCLUDED or name in DATABASES:
                    continue
                relative_name(name)
                if path.name.lower() == '.env' or path.suffix.lower() in {'.pem', '.key', '.pfx', '.dpapi'}:
                    raise WorkflowError('BACKUP_SECRET_FILE_IN_DATA_ROOT_REJECTED', 400)
                if path.suffix.lower() in {'.sqlite3', '.db'}:
                    raise WorkflowError('BACKUP_UNKNOWN_DATABASE_REJECTED', 400)
                if path.stat().st_size > MAX_FILE:
                    raise WorkflowError('BACKUP_FILE_SIZE_LIMIT', 400)
                result.append(('state/' + name, path))
                if len(result) > MAX_FILES:
                    raise WorkflowError('BACKUP_ENTRY_LIMIT', 400)
            else:
                raise WorkflowError('BACKUP_SPECIAL_FILE_REJECTED', 400)
    walk(root)
    return result


def add_file(archive, name, path):
    before = (path.stat().st_size, path.stat().st_mtime_ns)
    checksum = hashlib.sha256()
    size = 0
    with path.open('rb') as source, archive.open(name, 'w', force_zip64=True) as target:
        while chunk := source.read(1024**2):
            size += len(chunk)
            if size > MAX_FILE:
                raise WorkflowError('BACKUP_FILE_SIZE_LIMIT', 400)
            checksum.update(chunk)
            target.write(chunk)
    if before != (path.stat().st_size, path.stat().st_mtime_ns) or size != before[0] or file_sha(path) != checksum.hexdigest():
        raise WorkflowError('BACKUP_SOURCE_CHANGED_DURING_COPY')
    return {'path': name, 'bytes': size, 'sha256': checksum.hexdigest()}


def create_backup(config, output):
    config.validate_data_root()
    root = guard(config.data_root, exists=True)
    output = guard(output)
    guard(output.parent, exists=True)
    if output.exists() or root == output or root in output.parents:
        raise WorkflowError('BACKUP_OUTPUT_MUST_BE_NEW_AND_OUTSIDE_SOURCE', 400)
    if not (root / 'workflow.sqlite3').is_file():
        raise WorkflowError('BACKUP_WORKFLOW_DATABASE_REQUIRED', 400)
    partial = output.with_name('.' + output.name + '.partial-' + uuid.uuid4().hex)
    with offline_lease(root), tempfile.TemporaryDirectory(prefix='vf-native-db-snapshot-') as temporary:
        databases = {}
        source_files = entries(root)
        for name in DATABASES:
            source = root / name
            if source.is_file():
                facts = database_status(source)
                if facts['active_operations']:
                    raise WorkflowError('BACKUP_SOURCE_HAS_ACTIVE_OPERATIONS')
                target = Path(temporary) / name
                snapshot_database(source, target)
                if database_status(target) != facts:
                    raise WorkflowError('BACKUP_DATABASE_SNAPSHOT_MISMATCH')
                databases[name] = facts
                source_files.append(('state/' + name, target))
        # Snapshot source configuration as evidence; restore never overwrites the checkout.
        config_dir = REPO / 'services/windows_native'
        for folder in ('profiles', 'locks'):
            for path in sorted((config_dir / folder).glob('*.json')):
                guard(path, exists=True)
                source_files.append(('configuration/source-config/' + path.relative_to(config_dir).as_posix(), path))
        total = sum(path.stat().st_size for _, path in source_files)
        if total > MAX_TOTAL or len(source_files) > MAX_FILES:
            raise WorkflowError('BACKUP_TOTAL_SIZE_OR_ENTRY_LIMIT', 400)
        manifest = {'schema': 'native-offline-backup-v1', 'created_at': now(), 'source_root': str(root),
            'runtime_paths': config.dump(), 'databases': databases, 'offline_required': True,
            'configured_secret_file_contents_included': False, 'services_started': False,
            'entries': []}
        with zipfile.ZipFile(partial, mode='x', compression=zipfile.ZIP_STORED) as archive:
            if os.name != 'nt':
                partial.chmod(0o600)
            for name, path in sorted(source_files):
                manifest['entries'].append(add_file(archive, relative_name(name), path))
            encoded = canonical(manifest)
            if len(encoded) > MAX_MANIFEST:
                raise WorkflowError('BACKUP_MANIFEST_SIZE_LIMIT')
            archive.writestr('manifest.json', encoded)
        # Source membership and database activity are checked again before committing the package.
        if [(name, str(path)) for name, path in entries(root)] != [(name, str(path)) for name, path in source_files if name.startswith('state/') and path.parent != Path(temporary)]:
            raise WorkflowError('BACKUP_SOURCE_CHANGED_DURING_COPY')
        for row, (_, path) in zip(manifest['entries'], sorted(source_files)):
            if file_sha(path) != row['sha256']:
                raise WorkflowError('BACKUP_SOURCE_CHANGED_DURING_COPY')
        for name, facts in databases.items():
            if database_status(root / name) != facts:
                raise WorkflowError('BACKUP_SOURCE_CHANGED_DURING_COPY')
        with partial.open('r+b') as handle:
            os.fsync(handle.fileno())
        if output.exists():
            raise WorkflowError('BACKUP_OUTPUT_ALREADY_EXISTS')
        partial.rename(output)
    return {'schema': 'native-backup-receipt-v1', 'backup_path': str(output), 'sha256': file_sha(output),
            'bytes': output.stat().st_size, 'manifest_sha256': hashlib.sha256(canonical(manifest)).hexdigest(),
            'entries': len(manifest['entries']), 'database_status': databases,
            'production_deployed': False, 'services_started': False}


def validate_archive(archive):
    infos = archive.infolist()
    if len(infos) > MAX_FILES + 1 or len({info.filename.casefold() for info in infos}) != len(infos):
        raise WorkflowError('BACKUP_ARCHIVE_ENTRY_LIMIT_OR_DUPLICATE', 400)
    by_name = {}
    for info in infos:
        relative_name(info.filename)
        mode = (info.external_attr >> 16) & 0xffff
        if info.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG) or info.compress_type != zipfile.ZIP_STORED or info.flag_bits & 1:
            raise WorkflowError('BACKUP_ARCHIVE_ENTRY_TYPE_REJECTED', 400)
        if info.file_size < 0 or info.file_size > MAX_FILE or info.compress_size != info.file_size:
            raise WorkflowError('BACKUP_ARCHIVE_SIZE_LIMIT', 400)
        by_name[info.filename] = info
    info = by_name.get('manifest.json')
    if info is None or info.file_size > MAX_MANIFEST:
        raise WorkflowError('BACKUP_MANIFEST_INVALID', 400)
    try:
        manifest = json.loads(archive.read(info))
        if manifest['schema'] != 'native-offline-backup-v1' or not isinstance(manifest['entries'], list):
            raise ValueError()
        if set(manifest['runtime_paths']) != set(Config.__dataclass_fields__):
            raise ValueError()
        if any(not isinstance(value, str) or not 1 <= len(value) <= 2048 or '\x00' in value for value in manifest['runtime_paths'].values()):
            raise ValueError()
        expected = {'manifest.json'}
        total = 0
        for row in manifest['entries']:
            name = relative_name(row['path'])
            if not name.startswith(('state/', 'configuration/source-config/')) or name in expected:
                raise ValueError()
            if type(row['bytes']) is not int or not 0 <= row['bytes'] <= MAX_FILE or not re.fullmatch('[a-f0-9]{64}', row['sha256']):
                raise ValueError()
            if name not in by_name or by_name[name].file_size != row['bytes']:
                raise ValueError()
            total += row['bytes']
            expected.add(name)
        if total > MAX_TOTAL or expected != set(by_name) or 'state/workflow.sqlite3' not in expected:
            raise ValueError()
        if set(manifest['databases']) - set(DATABASES) or 'workflow.sqlite3' not in manifest['databases']:
            raise ValueError()
        if manifest['offline_required'] is not True or manifest['services_started'] is not False:
            raise ValueError()
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        raise WorkflowError('BACKUP_MANIFEST_INVALID', 400) from None
    return manifest


def restore_backup(backup, destination, *, expected_sha256):
    backup = guard(backup, exists=True)
    destination = guard(destination)
    guard(destination.parent, exists=True)
    if destination.exists() or backup == destination or backup in destination.parents:
        raise WorkflowError('RESTORE_REQUIRES_NEW_DESTINATION', 400)
    if backup.stat().st_size > MAX_TOTAL + 256 * 1024**2:
        raise WorkflowError('BACKUP_TOTAL_SIZE_OR_ENTRY_LIMIT', 400)
    if not isinstance(expected_sha256, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected_sha256) or file_sha(backup) != expected_sha256.lower():
        raise WorkflowError('BACKUP_TRUSTED_CHECKSUM_MISMATCH', 400)
    expected_sha256 = expected_sha256.lower()
    staging = destination.with_name('.' + destination.name + '.restore-' + uuid.uuid4().hex)
    with zipfile.ZipFile(backup, 'r') as archive:
        manifest = validate_archive(archive)
        original_root = Path(manifest['source_root']).absolute()
        if destination == original_root or original_root in destination.parents:
            raise WorkflowError('RESTORE_REQUIRES_DIFFERENT_SOURCE_ROOT', 400)
        config = Config(**{key: Path(value) for key, value in manifest['runtime_paths'].items()})
        config = replace(config, data_root=destination)
        config.validate_data_root()
        manifest_sha = hashlib.sha256(canonical(manifest)).hexdigest()
        staging.mkdir(mode=0o700, exist_ok=False)
        for row in manifest['entries']:
            name = row['path']
            relative = name[len('state/'):] if name.startswith('state/') else '_recovery/' + manifest_sha + '/' + name
            target = guard(staging / relative)
            if staging not in target.parents:
                raise WorkflowError('BACKUP_ENTRY_PATH_INVALID', 400)
            io_path(target.parent).mkdir(parents=True, exist_ok=True)
            checksum, size = hashlib.sha256(), 0
            with archive.open(name) as source, io_path(target).open('xb') as output:
                while chunk := source.read(1024**2):
                    size += len(chunk)
                    if size > row['bytes']:
                        raise WorkflowError('BACKUP_ENTRY_HASH_MISMATCH')
                    checksum.update(chunk); output.write(chunk)
                output.flush(); os.fsync(output.fileno())
            if size != row['bytes'] or checksum.hexdigest() != row['sha256']:
                raise WorkflowError('BACKUP_ENTRY_HASH_MISMATCH')
        for name, facts in manifest['databases'].items():
            if database_status(staging / name) != facts or facts['active_operations']:
                raise WorkflowError('RESTORE_DATABASE_STATUS_MISMATCH')
        receipt = {'schema': 'native-restore-receipt-v1', 'backup_sha256': expected_sha256,
            'manifest_sha256': manifest_sha, 'original_source_root': str(original_root),
            'destination': str(destination), 'verified_entries': len(manifest['entries']),
            'database_status': manifest['databases'], 'services_started': False, 'provider_calls': 0,
            'publishing_enabled': False, 'owner_uat_accepted': False, 'production_deployed': False,
            'receipt_path': str(destination / ('.vf-restore-' + manifest_sha + '.json')),
            'runtime_config_path': str(destination / ('.vf-runtime-' + manifest_sha + '.json'))}
        with (staging / ('.vf-restore-' + manifest_sha + '.json')).open('xb') as handle:
            handle.write(canonical(receipt)); handle.flush(); os.fsync(handle.fileno())
        with (staging / ('.vf-runtime-' + manifest_sha + '.json')).open('xb') as handle:
            handle.write(canonical(config.dump())); handle.flush(); os.fsync(handle.fileno())
        if destination.exists():
            raise WorkflowError('RESTORE_REQUIRES_NEW_DESTINATION', 400)
        staging.rename(destination)
    return receipt
