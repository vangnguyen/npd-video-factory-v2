"""Bounded fixture secrets and actual inert Settings in a child process."""
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import unquote, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from deploy.profiles.runtime import ProfileError, base_environment, prepare_environment, read_secret, initialize_storage


@pytest.fixture
def secrets(tmp_path):
    values = {'database-password': 'fixture-db@:/?#percent%value+safe-long', 'redis-password': 'r' * 64,
              'object-access-key': 'fixture-only-access', 'object-secret-key': 'fixture-only-object-secret-strong'}
    for name, value in values.items(): (tmp_path / name).write_text(value, encoding='utf-8')
    return tmp_path, values


def test_production_credentials_are_bounded_scoped_and_DSN_password_escaped(secrets):
    root, values = secrets
    hostile = {'PATH': os.environ.get('PATH', ''), 'OPENAI_API_KEY': 'UNUSED_AMBIENT_SECRET',
               'DATABASE_URL': 'foreign-host', 'PUBLISH_ENABLED': 'true', 'COMFYUI_EXECUTION_ENABLED': 'true'}
    original = dict(hostile)
    environment = prepare_environment('production-cpu', 'fixture01', 'api', secrets_root=root, ambient=hostile)
    parsed = urlparse(environment['DATABASE_URL'])
    assert parsed.hostname == 'postgres' and unquote(parsed.password) == values['database-password']
    assert 'fixture-db@:' not in environment['DATABASE_URL']
    assert environment['PUBLISH_ENABLED'] == environment['COMFYUI_EXECUTION_ENABLED'] == 'false'
    assert environment['OPENAI_API_KEY'] == '' and hostile == original
    # Least mounted scope: migrations need no Redis/object secret.
    environment = prepare_environment('production-cpu', 'fixture01', 'migrate', secrets_root=root, ambient={})
    assert 'REDIS_URL' not in environment and 'OBJECT_STORAGE_SECRET_KEY' not in environment


@pytest.mark.parametrize('failure', ['missing', 'oversize', 'newline', 'example', 'redis_injection', 'link'])
def test_secret_failure_is_closed_and_never_echoes_input(tmp_path, failure):
    target = tmp_path / 'redis-password'
    if failure == 'oversize': target.write_bytes(b'SECRET_PRIVATE_SENTINEL' * 100)
    if failure == 'newline': target.write_text('secret private\ninjected-configuration-secret')
    if failure == 'example': target.write_text('video-factory-dev-only-change-me')
    if failure == 'redis_injection': target.write_text('secret-with-redis;injection-and-private')
    if failure == 'link':
        original = tmp_path / 'original'; original.write_text('r' * 64)
        os.link(original, target)  # Real hard link; does not require Windows symlink privilege.
    with pytest.raises(ProfileError) as error: read_secret(tmp_path, 'redis-password', redis=True)
    assert 'SECRET_PRIVATE_SENTINEL' not in str(error.value) and 'private' not in str(error.value)


@pytest.mark.parametrize('profile,role', [('dev', 'api'), ('ci', 'worker'), ('production-cpu', 'api'), ('production-gpu', 'worker')])
def test_actual_inert_settings_startup_has_no_connections_or_ambient_enablement(tmp_path, secrets, profile, role):
    root, values = secrets
    environment = dict(os.environ)
    environment.update(VF_DEPLOYMENT_PROFILE=profile, VF_INSTANCE='inert02', VF_RUNTIME_ROLE=role,
                       OPENAI_API_KEY='UNUSED_AMBIENT_SECRET', PUBLISH_ENABLED='true',
                       OBJECT_STORAGE_ENDPOINT_URL='https://unowned-storage.example', HUMAN_WRITE_ENABLED='true',
                       PYTHONPATH=str(ROOT / 'apps/api'))
    wrapper = """
import runpy,socket,sys
def denied(*args,**kwargs):raise AssertionError('INERT_STARTUP_CONNECTION_FORBIDDEN')
socket.create_connection=denied
socket.socket.connect=denied
script=sys.argv.pop(1)
runpy.run_path(script,run_name='__main__')
"""
    completed = subprocess.run([sys.executable, '-c', wrapper, str(ROOT / 'deploy/profiles/runtime.py'),
                                '--check', '--secrets-root', str(root)],
                               env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report['status'] == 'CONFIGURATION_VALID' and report['connections_performed'] == 0
    assert not report['deployment_accepted'] and report['provider_calls'] == 0
    assert all(value not in completed.stdout + completed.stderr for value in values.values())
    assert 'UNUSED_AMBIENT_SECRET' not in completed.stdout + completed.stderr
    assert environment['PUBLISH_ENABLED'] == 'true'  # Parent was not modified.


def test_cli_missing_production_secret_returns_only_bounded_code(tmp_path):
    environment = dict(os.environ, VF_DEPLOYMENT_PROFILE='production-cpu', VF_INSTANCE='missing01', VF_RUNTIME_ROLE='api')
    completed = subprocess.run([sys.executable, str(ROOT / 'deploy/profiles/runtime.py'), '--check', '--secrets-root', str(tmp_path)],
                               env=environment, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 78 and completed.stdout == ''
    assert json.loads(completed.stderr) == {'status': 'NOT_READY', 'code': 'PROFILE_SECRET_UNAVAILABLE'}
    assert str(tmp_path) not in completed.stderr


@pytest.mark.parametrize('state', ['exists', 'missing', 'denied'])
def test_storage_initialization_is_idempotent_scoped_and_never_creates_after_denial(monkeypatch, state):
    from botocore.exceptions import ClientError
    calls = []
    class FixtureClient:
        def head_bucket(self, **values):
            calls.append(('head', values))
            if state != 'exists':
                raise ClientError({'Error': {'Code': '404' if state == 'missing' else 'AccessDenied'}}, 'HeadBucket')
        def create_bucket(self, **values): calls.append(('create', values))
    def fixture_factory(service, **values):
        assert service == 's3' and values['endpoint_url'] == 'http://minio:9000'
        assert values['config'].proxies == {}
        return FixtureClient()
    monkeypatch.setattr('boto3.client', fixture_factory)
    environment = base_environment('production-cpu', 'isolated01', 'storage-init')
    environment.update(OBJECT_STORAGE_ACCESS_KEY='explicit-fixture-access', OBJECT_STORAGE_SECRET_KEY='explicit-fixture-secret')
    if state == 'denied':
        with pytest.raises(ProfileError, match='PROFILE_STORAGE_INIT_FAILED'): initialize_storage(environment)
    else:
        initialize_storage(environment)
    expected = [('head', {'Bucket': 'vf-isolated01-production-cpu'})]
    if state == 'missing': expected.append(('create', {'Bucket': 'vf-isolated01-production-cpu'}))
    assert calls == expected  # SDK fixture only; no real MinIO/network acceptance.


def test_actual_init_cli_scrubs_proxy_AWS_and_credentials_before_fixture_SDK(secrets, tmp_path):
    root, values = secrets
    environment = dict(os.environ, VF_DEPLOYMENT_PROFILE='production-cpu', VF_INSTANCE='init01', VF_RUNTIME_ROLE='storage-init',
        HTTP_PROXY='http://UNOWNED_PROXY_SENTINEL', HTTPS_PROXY='http://UNOWNED_PROXY_SENTINEL',
        AWS_PROFILE='UNUSED_HOST_PROFILE', AWS_ACCESS_KEY_ID='UNUSED_HOST_SECRET', AWS_ENDPOINT_URL='https://unowned.example')
    wrapper = """
import os,runpy,socket,sys,boto3
def denied(*args,**kwargs):raise AssertionError('REAL_NETWORK_FORBIDDEN')
socket.create_connection=denied
socket.socket.connect=denied
class FixtureClient:
    def head_bucket(self,**values):assert values=={'Bucket':'vf-init01-production-cpu'}
def client(service,**values):
    assert service=='s3' and values['endpoint_url']=='http://minio:9000'
    assert values['config'].proxies=={}
    assert all(key not in os.environ for key in ('HTTP_PROXY','HTTPS_PROXY','AWS_PROFILE','AWS_ACCESS_KEY_ID','AWS_ENDPOINT_URL'))
    return FixtureClient()
boto3.client=client
script=sys.argv.pop(1)
runpy.run_path(script,run_name='__main__')
print('INERT_SDK_FIXTURE_PASS')
"""
    completed = subprocess.run([sys.executable, '-c', wrapper, str(ROOT / 'deploy/profiles/runtime.py'), '--init-storage',
                                '--secrets-root', str(root)], env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == 'INERT_SDK_FIXTURE_PASS' and completed.stderr == ''
    assert all(value not in completed.stdout + completed.stderr for value in values.values())
