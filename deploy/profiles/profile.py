"""Render explicit isolated Compose JSON; never execute Docker or read secrets.

JSON is valid YAML. The official pinned Compose JSON Schema validates the
rendered model, while additional admission checks validate service relations.
Legacy Compose/deploy scripts are deliberately left available unchanged.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
from deploy.profiles.runtime import PROFILES, ProfileError, base_environment, identity

MINIO = 'ghcr.io/npd-ai/npd-minio@sha256:d37f79cb57ba531f92eeaf2a1a0e5f827dea982a429bb5a2903043c57ed04528'
REDIS_START = """set -eu; value=$$(cat /run/secrets/redis-password); case "$$value" in *[!A-Za-z0-9_-]*|'') exit 78;; esac; [ "$${#value}" -ge 32 ] && [ "$${#value}" -le 128 ]; umask 077; printf 'appendonly yes\nrequirepass %s\n' "$$value" > /tmp/vf-redis.conf; unset value; exec redis-server /tmp/vf-redis.conf"""


def health(command, *, interval='10s'):
    return {'test': command, 'interval': interval, 'timeout': '4s', 'retries': 12, 'start_period': '20s'}


def python_health(url):
    return health(['CMD', 'python', '-c', f"import urllib.request; urllib.request.urlopen('{url}',timeout=3)"])


def _render_profile(profile: str, instance: str, *, api_port: int, studio_port: int,
                    secrets_dir: Path | None = None, repo_root: Path = REPO) -> dict:
    name = identity(profile, instance)
    if any(type(port) is not int or not 1024 <= port <= 65535 for port in (api_port, studio_port)) or api_port == studio_port:
        raise ProfileError('PROFILE_PORTS_INVALID')
    production = profile.startswith('production-')
    if production and (not isinstance(secrets_dir, Path) or not secrets_dir.is_absolute()):
        raise ProfileError('PROFILE_SECRET_DIRECTORY_REQUIRED')
    if not repo_root.is_absolute():
        raise ProfileError('PROFILE_REPOSITORY_ABSOLUTE_REQUIRED')
    if production and Path(os.path.normpath(str(secrets_dir))).is_relative_to(Path(os.path.normpath(str(repo_root)))):
        raise ProfileError('PROFILE_SECRET_DIRECTORY_IN_SOURCE')
    source = lambda relative: str(repo_root / relative)
    common_build = {'context': str(repo_root), 'dockerfile': 'deploy/profiles/Dockerfile.python'}
    resources = {key: {} for key in ('postgres-data', 'redis-data', 'minio-data', 'runtime-data', 'backup-data')}
    services = {
        'postgres': {'image': 'postgres:16-alpine', 'restart': 'unless-stopped', 'networks': ['data'],
            'environment': {'POSTGRES_USER': 'video_factory', 'POSTGRES_DB': name.replace('-', '_')},
            'volumes': ['postgres-data:/var/lib/postgresql/data'],
            'healthcheck': health(['CMD', 'pg_isready', '-U', 'video_factory', '-d', name.replace('-', '_')])},
        'redis': {'image': 'redis:7-alpine', 'restart': 'unless-stopped', 'networks': ['data'],
            'volumes': ['redis-data:/data'], 'command': ['redis-server', '--appendonly', 'yes'],
            'healthcheck': health(['CMD', 'redis-cli', 'ping'])},
        'minio': {'image': MINIO, 'restart': 'unless-stopped', 'networks': ['data'],
            'command': ['server', '/data', '--console-address', ':9001'], 'volumes': ['minio-data:/data'],
            'healthcheck': health(['CMD-SHELL', 'curl -fsS http://localhost:9000/minio/health/live >/dev/null'])},
        'renderer': {'build': {'context': source('renderer')}, 'restart': 'unless-stopped',
            'init': True, 'networks': ['render'], 'environment': {'OPENAI_API_KEY': ''},
            'volumes': ['runtime-data:/workspace/storage'], 'shm_size': '2gb',
            'healthcheck': health(['CMD', 'node', '-e',
                "fetch('http://127.0.0.1:3001/healthz').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"])},
        'studio-web': {'build': {'context': source('apps/studio-web')}, 'restart': 'unless-stopped',
            'networks': ['front'], 'ports': [f'127.0.0.1:{studio_port}:8080'],
            'depends_on': {'api': {'condition': 'service_healthy'}},
            'healthcheck': health(['CMD-SHELL', 'wget -qO- http://127.0.0.1:8080/ >/dev/null'])}}
    secrets = {'human-auth': {'file': str(secrets_dir / 'human-auth.json') if production else source('deploy/testing/disabled-human-auth.json')},
               'agent-hub-disabled': {'file': source('deploy/testing/disabled-agent-hub.json')}}
    for role in ('api', 'worker', 'migrate', 'storage-init'):
        environment = base_environment(profile, instance, role)
        environment['PUBLIC_BASE_URL'] = f'http://127.0.0.1:{api_port}'
        command = {'api': ['uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'],
                   'worker': ['python', '-m', 'npd_worker.main'],
                   'migrate': ['alembic', '-c', '/workspace/apps/api/alembic.ini', 'upgrade', 'head'],
                   'storage-init': ['--init-storage']}[role]
        service = {'build': copy.deepcopy(common_build), 'environment': environment, 'command': command,
                   'restart': 'no' if role in {'migrate', 'storage-init'} else 'unless-stopped',
                   'init': True, 'networks': ['data'], 'security_opt': ['no-new-privileges:true'], 'cap_drop': ['ALL']}
        if role in {'api', 'worker'}:
            service['networks'] += ['render']
            service['volumes'] = ['runtime-data:/workspace/storage', 'backup-data:/workspace/backups']
            service['secrets'] = ['agent-hub-disabled'] + (['human-auth'] if role == 'api' else [])
            service['depends_on'] = {'migrate': {'condition': 'service_completed_successfully'},
                'storage-init': {'condition': 'service_completed_successfully'}, 'redis': {'condition': 'service_healthy'},
                'renderer': {'condition': 'service_healthy'}}
        else:
            service['depends_on'] = {('postgres' if role == 'migrate' else 'minio'): {'condition': 'service_healthy'}}
        if role == 'api':
            service['networks'] += ['front']
            service['ports'] = [f'127.0.0.1:{api_port}:8000']
            service['healthcheck'] = python_health('http://127.0.0.1:8000/readyz')
        services[role] = service
    if production:
        for key, filename in (('database-password', 'database-password'), ('redis-password', 'redis-password'),
                              ('object-access-key', 'object-access-key'), ('object-secret-key', 'object-secret-key')):
            secrets[key] = {'file': str(secrets_dir / filename)}
        services['postgres']['environment']['POSTGRES_PASSWORD_FILE'] = '/run/secrets/database-password'
        services['postgres']['secrets'] = ['database-password']
        services['redis']['secrets'] = ['redis-password']
        services['redis']['command'] = ['/bin/sh', '-ec', REDIS_START]
        services['redis']['healthcheck'] = health(['CMD-SHELL',
            'REDISCLI_AUTH=$$(cat /run/secrets/redis-password) redis-cli ping | grep -qx PONG'])
        services['minio']['environment'] = {'MINIO_ROOT_USER_FILE': '/run/secrets/object-access-key',
            'MINIO_ROOT_PASSWORD_FILE': '/run/secrets/object-secret-key'}
        services['minio']['secrets'] = ['object-access-key', 'object-secret-key']
        for role in ('api', 'worker', 'migrate', 'storage-init'):
            selected = ([] if role == 'storage-init' else ['database-password'])
            selected += ['redis-password'] if role in {'api', 'worker'} else []
            selected += ['object-access-key', 'object-secret-key'] if role != 'migrate' else []
            services[role]['secrets'] = services[role].get('secrets', []) + selected
    else:
        services['postgres']['environment']['POSTGRES_PASSWORD'] = 'development-only'
        services['minio']['environment'] = {'MINIO_ROOT_USER': 'video-factory-dev',
                                          'MINIO_ROOT_PASSWORD': 'video-factory-dev-only-change-me'}
    if profile == 'production-gpu':
        resources['comfyui-data'] = {}
        services['comfyui-bridge'] = {'build': {'context': source('services/comfyui-bridge')},
            'restart': 'unless-stopped', 'networks': ['render'],
            'environment': {'APP_ENV': 'production', 'COMFYUI_EXECUTION_ENABLED': 'false', 'COMFYUI_BACKEND': 'disabled',
                'COMFYUI_API_TOKEN': '', 'COMFYUI_BRIDGE_TOKEN': '',
                'COMFYUI_WORKFLOW_MANIFEST': '/workspace/workflows/comfyui/manifest.json',
                'COMFYUI_JOB_STORE_PATH': '/workspace/storage/comfyui/jobs.sqlite3',
                'COMFYUI_ARTIFACT_ROOT': '/workspace/storage/comfyui/artifacts'},
            'volumes': [f"{source('workflows/comfyui')}:/workspace/workflows/comfyui:ro", 'comfyui-data:/workspace/storage/comfyui'],
            'healthcheck': python_health('http://127.0.0.1:8011/healthz')}
    model = {'name': name, 'services': services, 'volumes': resources, 'secrets': secrets,
        'networks': {'front': {'driver': 'bridge'}, 'data': {'internal': True}, 'render': {'internal': True}},
        'x-video-factory': {'schema_version': 'isolated-deployment-profile.v1', 'profile': profile,
            'instance': instance, 'production_deployment_approval_required': production, 'docker_stack_acceptance': 'NOT_VERIFIED',
            'gpu_inference': 'NOT_CONFIGURED', 'worker_consumer_heartbeat': 'NOT_IMPLEMENTED',
            'backup_execution': 'NOT_VERIFIED', 'backup_volume': name + '_backup-data'}}
    return model


def build_profile(profile: str, instance: str, *, api_port: int, studio_port: int,
                  secrets_dir: Path | None = None, repo_root: Path = REPO) -> dict:
    model = _render_profile(profile, instance, api_port=api_port, studio_port=studio_port,
                            secrets_dir=secrets_dir, repo_root=repo_root)
    validate_profile(model, repo_root=repo_root)
    return model


def _approved_service_contract(model: dict, *, repo_root: Path) -> dict:
    """Only caller-selected identity, loopback ports and secret directory vary.

    A valid generic Compose document is insufficient authority to mount another
    product's data, change executable startup or grant additional secret access.
    Reconstruct the approved service contract without reading paths or secrets.
    """
    metadata = model['x-video-factory']
    ports = []
    for service, target in (('api', '8000'), ('studio-web', '8080')):
        mappings = model['services'][service].get('ports')
        if (not isinstance(mappings, list) or len(mappings) != 1
                or not isinstance(mappings[0], str)
                or not re.fullmatch(r'127\.0\.0\.1:[0-9]+:' + target, mappings[0])):
            raise ProfileError('PROFILE_HOST_EXPOSURE_INVALID')
        ports.append(int(mappings[0].split(':')[1]))
    secret_dir = None
    if metadata['profile'].startswith('production-'):
        secret = model.get('secrets', {}).get('human-auth')
        if not isinstance(secret, dict) or set(secret) != {'file'} or not isinstance(secret['file'], str):
            raise ProfileError('PROFILE_SECRET_CONTRACT_CHANGED')
        auth_file = Path(secret['file'])
        if not auth_file.is_absolute() or auth_file.name != 'human-auth.json':
            raise ProfileError('PROFILE_SECRET_CONTRACT_CHANGED')
        secret_dir = auth_file.parent
    return _render_profile(metadata['profile'], metadata['instance'],
                           api_port=ports[0], studio_port=ports[1],
                           secrets_dir=secret_dir, repo_root=repo_root)


def validate_profile(model: dict, *, repo_root: Path = REPO) -> None:
    import jsonschema
    if (not isinstance(model, dict)
            or not {'name', 'services', 'volumes', 'networks', 'secrets', 'x-video-factory'} <= set(model)
            or not isinstance(model['x-video-factory'], dict)):
        raise ProfileError('PROFILE_COMPOSE_SCHEMA_INVALID')
    root = Path(__file__).resolve().parent
    schema_bytes = (root / 'compose-spec.schema.json').read_bytes()
    provenance = json.loads((root / 'compose-spec.PROVENANCE.json').read_text())
    if hashlib.sha256(schema_bytes).hexdigest() != provenance['schema_sha256']:
        raise ProfileError('PROFILE_SCHEMA_CHANGED')
    schema = json.loads(schema_bytes)
    validator = jsonschema.validators.validator_for(schema)
    validator.check_schema(schema)
    try:
        validator(schema).validate(model)
    except jsonschema.ValidationError:
        raise ProfileError('PROFILE_COMPOSE_SCHEMA_INVALID') from None
    services = model['services']
    metadata = model.get('x-video-factory', {})
    expected_name = identity(metadata.get('profile'), metadata.get('instance'))
    if model['name'] != expected_name:
        raise ProfileError('PROFILE_RESOURCE_NAMESPACE_INVALID')
    roles = {'api', 'worker', 'migrate', 'storage-init'}
    expected_services = roles | {'postgres', 'redis', 'minio', 'renderer', 'studio-web'}
    if metadata['profile'] == 'production-gpu':
        expected_services.add('comfyui-bridge')
    if set(services) != expected_services:
        raise ProfileError('PROFILE_SERVICE_SET_INVALID')
    for role in roles:
        environment = services[role].get('environment')
        expected = base_environment(metadata['profile'], metadata['instance'], role)
        if (not isinstance(environment, dict)
                or any(environment.get(key) != value for key, value in expected.items())
                or set(environment) != set(expected) | {'PUBLIC_BASE_URL'}):
            raise ProfileError('PROFILE_ENVIRONMENT_CHANGED')
    if (set(model['networks']) != {'front', 'data', 'render'}
            or not all(isinstance(value, dict) for value in model['networks'].values())
            or model['networks']['data'].get('internal') is not True
            or model['networks']['render'].get('internal') is not True):
        raise ProfileError('PROFILE_PRIVATE_NETWORK_CHANGED')
    for value in model['volumes'].values():
        if value:
            raise ProfileError('PROFILE_VOLUME_NAMESPACE_INVALID')
    allowed_shell_dollars = {REDIS_START,
        'REDISCLI_AUTH=$$(cat /run/secrets/redis-password) redis-cli ping | grep -qx PONG'}
    def closed_interpolation(value):
        if isinstance(value, str) and '$' in value and value not in allowed_shell_dollars:
            raise ProfileError('PROFILE_INTERPOLATION_INVALID')
        if isinstance(value, dict):
            for key, nested in value.items():
                closed_interpolation(key)
                closed_interpolation(nested)
        if isinstance(value, list):
            for nested in value:
                closed_interpolation(nested)
    closed_interpolation(model)
    graph = {name: set(service.get('depends_on', {})) for name, service in services.items()}
    if any(not isinstance(service.get('depends_on', {}), dict) for service in services.values()):
        raise ProfileError('PROFILE_SERVICE_CONTRACT_CHANGED')
    if any(name != 'comfyui-bridge' and 'comfyui-bridge' in dependencies for name, dependencies in graph.items()):
        raise ProfileError('PROFILE_CPU_DEPENDS_ON_GPU')
    def visit(name, stack):
        if name in stack:
            raise ProfileError('PROFILE_DEPENDENCY_CYCLE')
        for target in graph[name]:
            if target not in services:
                raise ProfileError('PROFILE_DEPENDENCY_MISSING')
            condition = services[name]['depends_on'][target]['condition']
            if condition == 'service_healthy' and 'healthcheck' not in services[target]:
                raise ProfileError('PROFILE_HEALTH_CONDITION_MISSING')
            visit(target, stack | {name})
    for name in graph:
        visit(name, set())
    for name, service in services.items():
        if 'container_name' in service or 'env_file' in service or service.get('privileged') or service.get('network_mode'):
            raise ProfileError('PROFILE_ISOLATION_INVALID')
        if any(network not in model['networks'] for network in service['networks']):
            raise ProfileError('PROFILE_NETWORK_REFERENCE_INVALID')
        if any(not isinstance(secret, str) or secret not in model['secrets'] for secret in service.get('secrets', [])):
            raise ProfileError('PROFILE_SECRET_REFERENCE_INVALID')
        for port in service.get('ports', []):
            if name not in {'api', 'studio-web'} or not isinstance(port, str) or not re.fullmatch(r'127\.0\.0\.1:[0-9]+:[0-9]+', port):
                raise ProfileError('PROFILE_HOST_EXPOSURE_INVALID')
    if any(value.get('external') or value.get('name') for value in model['networks'].values()):
        raise ProfileError('PROFILE_NETWORK_NAMESPACE_INVALID')
    approved = _approved_service_contract(model, repo_root=repo_root)
    if model['secrets'] != approved['secrets']:
        raise ProfileError('PROFILE_SECRET_CONTRACT_CHANGED')
    if model['volumes'] != approved['volumes']:
        raise ProfileError('PROFILE_VOLUME_CONTRACT_CHANGED')
    if model['networks'] != approved['networks']:
        raise ProfileError('PROFILE_NETWORK_CONTRACT_CHANGED')
    for name, service in services.items():
        selected = approved['services'][name]
        if service.get('volumes') != selected.get('volumes'):
            raise ProfileError('PROFILE_SERVICE_MOUNTS_CHANGED')
        if service.get('networks') != selected.get('networks'):
            raise ProfileError('PROFILE_SERVICE_NETWORKS_CHANGED')
        if service.get('secrets') != selected.get('secrets'):
            raise ProfileError('PROFILE_SECRET_SCOPE_CHANGED')
        if service.get('build') != selected.get('build') or service.get('image') != selected.get('image'):
            raise ProfileError('PROFILE_BUILD_SOURCE_CHANGED')
        if 'entrypoint' in service or service.get('command') != selected.get('command'):
            raise ProfileError('PROFILE_BOOTSTRAP_CHANGED')
        if service.get('environment') != selected.get('environment'):
            raise ProfileError('PROFILE_ENVIRONMENT_CHANGED')
        if service != selected:
            raise ProfileError('PROFILE_SERVICE_CONTRACT_CHANGED')
    if model != approved:
        raise ProfileError('PROFILE_CONTRACT_CHANGED')


def configuration_command(model: dict, config_path: Path, empty_env_path: Path) -> list[str]:
    """Explicit project/context/files defeat ambient Compose/DOCKER_* selection.

This returns an argv plan only. Even Docker config/build/up is never invoked by
the renderer, validator or tests; owner approval is required for deployment.
"""
    admitted = copy.deepcopy(model)
    validate_profile(admitted)
    if not config_path.is_absolute() or not empty_env_path.is_absolute():
        raise ProfileError('PROFILE_EXECUTION_PATH_INVALID')
    # The argv must refer to the exact admitted JSON, not another Compose file.
    # This is a point-in-time check, not a lease or permission to run Docker.
    try:
        identity_before = (_execution_identity(config_path), _execution_identity(empty_env_path))
        content = _read_execution_file(config_path, maximum=1_000_000)
        empty = _read_execution_file(empty_env_path, maximum=0)
        if empty != b'' or json.loads(content) != admitted:
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
        # Verify the pair after both earlier I/O boundaries. A config change
        # during env-file reading must not produce an argv for foreign bytes.
        final_content = _read_execution_file(config_path, maximum=1_000_000)
        final_empty = _read_execution_file(empty_env_path, maximum=0)
        if final_content != content or final_empty != empty:
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
        if (_execution_identity(config_path), _execution_identity(empty_env_path)) != identity_before:
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    except ProfileError:
        raise
    except (OSError, ValueError):
        raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED') from None
    return ['docker', '--context', 'default', 'compose', '--project-name', admitted['name'],
            '--env-file', str(empty_env_path), '--file', str(config_path), 'config']


def _execution_identity(path: Path) -> tuple:
    """Closed final metadata fence, with no further byte-read boundary."""
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def _read_execution_file(path: Path, *, maximum: int) -> bytes:
    for component in (path, *path.parents):
        info = component.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size > maximum:
        raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as source:
        if signature(os.fstat(source.fileno())) != signature(info):
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
        content = source.read(maximum + 1)
        if len(content) > maximum or signature(os.fstat(source.fileno())) != signature(info):
            raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    after = path.lstat()
    if (stat.S_ISLNK(after.st_mode) or getattr(after, 'st_file_attributes', 0) & 0x400
            or signature(after) != signature(info)):
        raise ProfileError('PROFILE_EXECUTION_FILE_CHANGED')
    return content


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', choices=PROFILES, required=True)
    parser.add_argument('--instance', required=True)
    parser.add_argument('--api-port', type=int, required=True)
    parser.add_argument('--studio-port', type=int, required=True)
    parser.add_argument('--secrets-dir', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        model = build_profile(args.profile, args.instance, api_port=args.api_port, studio_port=args.studio_port,
                              secrets_dir=args.secrets_dir)
        # Exclusive creation: an accepted config is never replaced silently.
        with args.output.open('x', encoding='utf-8', newline='\n') as output:
            output.write(json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + '\n')
        empty_env = args.output.parent / 'empty-profile.env'
        if empty_env.exists():
            if empty_env.is_symlink() or empty_env.read_bytes() != b'':
                raise ProfileError('PROFILE_EMPTY_ENV_CHANGED')
        else:
            with empty_env.open('xb'):
                pass
        print(json.dumps({'status': 'CONFIGURATION_RENDERED', 'profile': args.profile, 'name': model['name'],
                          'compose_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
                          'docker_config_argv': configuration_command(model, args.output.absolute(), empty_env.absolute()),
                          'docker_executed': False, 'deployment_accepted': False}))
    except Exception as error:
        print(json.dumps({'status': 'NOT_CONFIGURED', 'code': str(error) if isinstance(error, ProfileError) else 'PROFILE_RENDER_FAILED'}), file=sys.stderr)
        raise SystemExit(78) from None


if __name__ == '__main__':
    main()
