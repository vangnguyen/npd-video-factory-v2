"""Bounded mounted-secret bootstrap. Never read a workstation .env file.

Only --init-storage makes an infrastructure request. --check is inert and never
imports API lifespan, workers, providers or models. Deployment remains owner-gated.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import quote

PROFILES = ('dev', 'ci', 'production-cpu', 'production-gpu')
ROLES = ('api', 'worker', 'migrate', 'storage-init')
SECRETS = {'database': 'database-password', 'redis': 'redis-password',
           'access': 'object-access-key', 'object': 'object-secret-key'}


class ProfileError(ValueError):
    """Finite diagnostic; input, credentials, DSNs and paths are never echoed."""


def identity(profile: str, instance: str) -> str:
    if profile not in PROFILES or not isinstance(instance, str) or not re.fullmatch(r'[a-z][a-z0-9-]{2,23}', instance):
        raise ProfileError('PROFILE_IDENTITY_INVALID')
    return f'vf-{instance}-{profile}'


def base_environment(profile: str, instance: str, role: str) -> dict[str, str]:
    name = identity(profile, instance)
    if role not in ROLES:
        raise ProfileError('PROFILE_ROLE_INVALID')
    production = profile.startswith('production-')
    result = {'VF_DEPLOYMENT_PROFILE': profile, 'VF_INSTANCE': instance, 'VF_RUNTIME_ROLE': role,
        'APP_ENV': 'production' if production else 'ci' if profile == 'ci' else 'development',
        'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUNBUFFERED': '1',
        'VF_DATABASE_NAME': name.replace('-', '_'), 'VF_DATABASE_USER': 'video_factory',
        'JOB_STORAGE_ROOT': '/workspace/storage/jobs', 'ASSET_STORAGE_ROOT': '/workspace/storage/assets',
        'CONTRACTS_ROOT': '/workspace/packages/contracts',
        'VIDEO_MANIFEST_SCHEMA_PATH': '/workspace/packages/contracts/video-manifest.schema.json',
        'RENDERER_URL': 'http://renderer:3001', 'RENDERER_TIMEOUT_SECONDS': '600',
        'OBJECT_STORAGE_PROVIDER': 's3', 'OBJECT_STORAGE_ENDPOINT_URL': 'http://minio:9000',
        'OBJECT_STORAGE_BUCKET': name, 'OBJECT_STORAGE_REGION': 'us-east-1',
        'OBJECT_STORAGE_AUTO_CREATE_BUCKET': 'false', 'OBJECT_STORAGE_LOCAL_ROOT': '/workspace/storage/object-store',
        'UPLOAD_STAGING_ROOT': '/workspace/storage/uploads', 'ANALYSIS_STAGING_ROOT': '/workspace/storage/analysis',
        'VISION_STAGING_ROOT': '/workspace/storage/vision', 'MEDIA_STAGING_ROOT': '/workspace/storage/media-resolution',
        'PREVIEW_STAGING_ROOT': '/workspace/storage/previews', 'PREVIEW_DOWNLOAD_ROOT': '/workspace/storage/preview-downloads',
        'PRODUCTION_RENDER_STAGING_ROOT': '/workspace/storage/production-renders',
        'PRODUCTION_RENDER_DOWNLOAD_ROOT': '/workspace/storage/production-downloads',
        'STOCK_CACHE_ROOT': '/workspace/storage/stock-cache', 'FFMPEG_PATH': 'ffmpeg', 'FFPROBE_PATH': 'ffprobe',
        'HUMAN_API_ENABLED': 'true', 'HUMAN_WRITE_ENABLED': 'false' if production else 'true',
        'HUMAN_AUTH_KEYS_FILE': '/run/secrets/human-auth', 'HUMAN_AUTH_MAX_TOKEN_TTL_SECONDS': '86400',
        'HUMAN_RATE_LIMIT_PER_MINUTE': '120', 'HUMAN_APPROVAL_REQUIRED': 'true',
        'AGENT_HUB_SERVICE_KEYS_FILE': '/run/secrets/agent-hub-disabled',
        'AGENT_HUB_WEBHOOK_SIGNING_KEYS_FILE': '/run/secrets/agent-hub-disabled',
        'AGENT_HUB_WEBHOOK_MODE': 'disabled', 'CONTENT_GENERATION_PROVIDER': 'contract',
        'AUTO_EDIT_SIGNAL_PROVIDER': 'ffmpeg' if production else 'fixture',
        'MEDIA_MALWARE_SCANNER_MODE': 'disabled' if production else 'fixture',
        'AUDIO_TTS_PROVIDER': 'contract' if production else 'espeak',
        'TTS_PROVIDER': 'contract' if production else 'espeak',
        'PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED': 'true', 'PROVIDER_BUDGET_CURRENCY': 'VND',
        'PROVIDER_PER_OPERATION_LIMIT_VND': '0', 'PROVIDER_DAILY_LIMIT_VND': '0',
        'PROVIDER_HTTP_TIMEOUT_SECONDS': '90', 'CONTROLLER_HARD_TIMEOUT_SECONDS': '120',
        'PROVIDER_OPERATION_LEASE_SECONDS': '900', 'PROVIDER_RETENTION_CLEANUP_ENABLED': 'false',
        'COMFYUI_BRIDGE_URL': 'http://comfyui-bridge:8011',
        'DEFAULT_WORKSPACE_SLUG': name, 'DEFAULT_WORKSPACE_NAME': name,
        'DEFAULT_WORKSPACE_OWNER_REF': 'deployment-profile-unaccepted'}
    for key in ('PUBLISH_ENABLED', 'PUBLISH_EXTERNAL_EXECUTION_ENABLED', 'PUBLISH_OWNER_GATE_ENABLED',
                'PROVIDER_EXTERNAL_EXECUTION_ENABLED', 'PROVIDER_PAID_EXECUTION_ENABLED',
                'PROVIDER_VERIFIED_GATE_BUNDLE_ENABLED', 'CONTENT_EXTERNAL_EXECUTION_ENABLED',
                'CONTENT_ADMISSION_ENABLED', 'TTS_ADMISSION_ENABLED', 'AUDIO_EXTERNAL_EXECUTION_ENABLED',
                'MEDIA_EXTERNAL_EXECUTION_ENABLED', 'MEDIA_PAID_EXECUTION_ENABLED', 'COMFYUI_EXECUTION_ENABLED',
                'ANALYTICS_EXTERNAL_EXECUTION_ENABLED', 'ANALYTICS_SCHEDULED_REFRESH_ENABLED',
                'AGENT_HUB_BRIDGE_ENABLED', 'AGENT_HUB_WEBHOOK_EXTERNAL_DELIVERY_ENABLED',
                'OPERATIONS_EXTERNAL_NOTIFICATIONS_ENABLED', 'LOCAL_ASR_ENABLED',
                'ASSEMBLYAI_ASR_LIVE_EXECUTION_ENABLED', 'VIENEU_LOCAL_EXECUTION_ENABLED',
                'AUTO_EDIT_DERIVED_TIMING_ENABLED', 'SQL_VARIANT_NARRATION_REUSE_ENABLED'):
        result[key] = 'false'
    for key in ('TREND_FIXTURE_ENABLED', 'AUTO_EDIT_FIXTURE_ENABLED', 'VISION_FIXTURE_ENABLED',
                'MEDIA_FIXTURE_ENABLED', 'ANALYTICS_FIXTURE_ENABLED'):
        result[key] = 'false' if production else 'true'
    for key in ('TRANSCRIPTION_PROVIDER', 'VISION_PROVIDER', 'STOCK_MEDIA_PROVIDER',
                'IMAGE_GENERATION_PROVIDER', 'VIDEO_GENERATION_PROVIDER'):
        result[key] = 'contract' if production else 'fixture'
    for key in ('OPENAI_API_KEY', 'PEXELS_API_KEY', 'PIXABAY_API_KEY', 'ASSEMBLYAI_API_KEY',
                'COMFYUI_API_TOKEN', 'COMFYUI_BRIDGE_TOKEN'):
        result[key] = ''
    return result


def read_secret(root: Path, name: str, *, minimum=16, redis=False) -> str:
    if name not in SECRETS.values() or not root.is_absolute():
        raise ProfileError('PROFILE_SECRET_REFERENCE_INVALID')
    path = root / name
    try:
        for parent in (path, *path.parents):
            info = parent.lstat()
            if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
                raise ProfileError('PROFILE_SECRET_LINK_REJECTED')
        info = path.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or not 0 < info.st_size <= 1024:
            raise ProfileError('PROFILE_SECRET_LIMIT')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
        with os.fdopen(descriptor, 'rb') as source:
            opened = os.fstat(source.fileno())
            signature = lambda item: (item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns)
            if signature(opened) != signature(info):
                raise ProfileError('PROFILE_SECRET_CHANGED')
            value = source.read(1025).decode('utf-8').rstrip('\r\n')
            final = os.fstat(source.fileno())
            if signature(final) != signature(opened):
                raise ProfileError('PROFILE_SECRET_CHANGED')
        if not minimum <= len(value) <= 256 or any(ord(c) < 33 or ord(c) == 127 for c in value):
            raise ProfileError('PROFILE_SECRET_INVALID')
        if value in {'development-only', 'video-factory-dev-only-change-me', 'minioadmin'}:
            raise ProfileError('PROFILE_EXAMPLE_SECRET_REJECTED')
        if redis and not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', value):
            raise ProfileError('PROFILE_REDIS_SECRET_INVALID')
        after = path.lstat()
        if stat.S_ISLNK(after.st_mode) or getattr(after, 'st_file_attributes', 0) & 0x400:
            raise ProfileError('PROFILE_SECRET_LINK_REJECTED')
        if (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns):
            raise ProfileError('PROFILE_SECRET_CHANGED')
        return value
    except ProfileError:
        raise
    except (OSError, UnicodeError):
        raise ProfileError('PROFILE_SECRET_UNAVAILABLE') from None


def prepare_environment(profile: str, instance: str, role: str, *, secrets_root=Path('/run/secrets'), ambient=None) -> dict[str, str]:
    # The only inherited keys support executable/DLL lookup, never application
    # enablement or credentials. This function does not mutate its caller's env.
    ambient = os.environ if ambient is None else ambient
    result = {key: ambient[key] for key in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP', 'LANG') if key in ambient}
    result.update(base_environment(profile, instance, role))
    production = profile.startswith('production-')
    if role in {'api', 'worker', 'migrate'}:
        password = read_secret(secrets_root, SECRETS['database']) if production else 'development-only'
        result['DATABASE_URL'] = f"postgresql+asyncpg://video_factory:{quote(password, safe='')}@postgres:5432/{result['VF_DATABASE_NAME']}"
    if role in {'api', 'worker'}:
        password = read_secret(secrets_root, SECRETS['redis'], redis=True) if production else None
        result['REDIS_URL'] = f'redis://:{password}@redis:6379/0' if password else 'redis://redis:6379/0'
    if role in {'api', 'worker', 'storage-init'}:
        result['OBJECT_STORAGE_ACCESS_KEY'] = read_secret(secrets_root, SECRETS['access'], minimum=3) if production else 'video-factory-dev'
        result['OBJECT_STORAGE_SECRET_KEY'] = read_secret(secrets_root, SECRETS['object']) if production else 'video-factory-dev-only-change-me'
    return result


def check(environment: dict[str, str], role: str) -> dict:
    if role in {'api', 'worker'}:
        # Validate actual settings without loading the API lifespan or a worker.
        from app.config import Settings
        settings = Settings(_env_file=None, **{key.lower(): value for key, value in environment.items()})
        if settings.publish_enabled or settings.provider_external_execution_enabled or settings.provider_paid_execution_enabled:
            raise ProfileError('PROFILE_EXECUTION_GATE_CHANGED')
    return {'schema_version': 'deployment-runtime-check.v1', 'status': 'CONFIGURATION_VALID',
            'role': role, 'profile': environment['VF_DEPLOYMENT_PROFILE'], 'connections_performed': 0,
            'provider_calls': 0, 'deployment_accepted': False, 'secret_values_returned': False}


def initialize_storage(environment):
    # Explicit one-shot service within the generated private stack; never run by
    # compiler/check/tests. A production deployment requires separate approval.
    if (environment.get('OBJECT_STORAGE_ENDPOINT_URL') != 'http://minio:9000'
            or environment.get('OBJECT_STORAGE_BUCKET') != identity(environment.get('VF_DEPLOYMENT_PROFILE'), environment.get('VF_INSTANCE'))):
        raise ProfileError('PROFILE_STORAGE_SCOPE_CHANGED')
    import boto3
    from botocore.config import Config
    from botocore.exceptions import ClientError
    client = boto3.client('s3', endpoint_url=environment['OBJECT_STORAGE_ENDPOINT_URL'],
        aws_access_key_id=environment['OBJECT_STORAGE_ACCESS_KEY'], aws_secret_access_key=environment['OBJECT_STORAGE_SECRET_KEY'],
        region_name='us-east-1', config=Config(connect_timeout=3, read_timeout=10, proxies={}, retries={'total_max_attempts': 3},
                                             s3={'addressing_style': 'path'}))
    bucket = environment['OBJECT_STORAGE_BUCKET']
    try:
        client.head_bucket(Bucket=bucket)
    except ClientError as error:
        if error.response.get('Error', {}).get('Code') not in {'404', 'NoSuchBucket', 'NotFound'}:
            raise ProfileError('PROFILE_STORAGE_INIT_FAILED') from None
        client.create_bucket(Bucket=bucket)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--init-storage', action='store_true')
    parser.add_argument('--secrets-root', type=Path, default=Path('/run/secrets'))
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    try:
        profile, instance, role = (os.environ.get(key, '') for key in ('VF_DEPLOYMENT_PROFILE', 'VF_INSTANCE', 'VF_RUNTIME_ROLE'))
        environment = prepare_environment(profile, instance, role, secrets_root=args.secrets_root)
        # SDK initialization as well as executed application processes receive
        # only this profile's allowlist, never ambient proxy/AWS/provider flags.
        os.environ.clear()
        os.environ.update(environment)
        if args.check:
            print(json.dumps(check(environment, role)))
        elif args.init_storage and role == 'storage-init':
            initialize_storage(environment)
        elif args.command and role in {'api', 'worker', 'migrate'}:
            command = args.command[1:] if args.command[0] == '--' else args.command
            os.execvpe(command[0], command, environment)
        else:
            raise ProfileError('PROFILE_COMMAND_REQUIRED')
    except Exception as error:
        print(json.dumps({'status': 'NOT_READY', 'code': str(error) if isinstance(error, ProfileError) else 'PROFILE_RUNTIME_INVALID'}), file=sys.stderr)
        raise SystemExit(78) from None


if __name__ == '__main__':
    main()
