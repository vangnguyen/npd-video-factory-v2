"""Real rendered Compose schema/relations, no Docker or infrastructure calls."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from deploy.profiles.profile import build_profile, validate_profile, configuration_command
from deploy.profiles.runtime import ProfileError
from deploy.profiles import profile as compiler


@pytest.mark.parametrize('profile', ['dev', 'ci', 'production-cpu', 'production-gpu'])
def test_rendered_model_has_closed_startup_graph_and_scoped_data_plane(tmp_path, profile, monkeypatch):
    # Vendor schema validation is offline; a resolver cannot fetch another schema.
    def denied(*args, **kwargs): raise AssertionError('Schema validation must be offline')
    monkeypatch.setattr('urllib.request.urlopen', denied)
    model = build_profile(profile, 'acceptance01', api_port=41000, studio_port=41001,
                          secrets_dir=tmp_path / 'unprovisioned')
    validate_profile(json.loads(json.dumps(model)))
    services = model['services']
    assert 'env_file' not in json.dumps(model) and 'container_name' not in json.dumps(model)
    assert not set(services['studio-web']['networks']) & set(services['postgres']['networks'])
    assert not set(services['renderer']['networks']) & set(services['redis']['networks'])
    assert 'ports' not in services['postgres'] and 'ports' not in services['redis'] and 'ports' not in services['minio']
    for consumer in ('api', 'worker'):
        assert services[consumer]['depends_on']['migrate']['condition'] == 'service_completed_successfully'
        assert services[consumer]['depends_on']['storage-init']['condition'] == 'service_completed_successfully'
        assert services[consumer]['depends_on']['renderer']['condition'] == 'service_healthy'
    for consumer in services:
        assert 'comfyui-bridge' not in services[consumer].get('depends_on', {})
    assert ('comfyui-bridge' in services) == (profile == 'production-gpu')
    assert model['x-video-factory']['gpu_inference'] == 'NOT_CONFIGURED'


def test_all_profiles_and_instances_have_independent_persistent_resource_names(tmp_path):
    names = set()
    for instance in ('workspace01', 'workspace02'):
        for profile in ('dev', 'ci', 'production-cpu', 'production-gpu'):
            model = build_profile(profile, instance, api_port=42000, studio_port=42001, secrets_dir=tmp_path / instance)
            resources = {model['name'] + '_' + key for key in (*model['volumes'], *model['networks'])}
            assert not resources & names
            names |= resources
            assert model['services']['api']['environment']['OBJECT_STORAGE_BUCKET'] == model['name']
            assert model['services']['postgres']['environment']['POSTGRES_DB'] == model['name'].replace('-', '_')


@pytest.mark.parametrize('tamper,code', [
    ('paid', 'PROFILE_ENVIRONMENT_CHANGED'), ('env_file', 'PROFILE_ISOLATION_INVALID'),
    ('network', 'PROFILE_NETWORK_NAMESPACE_INVALID'), ('volume', 'PROFILE_VOLUME_NAMESPACE_INVALID'),
    ('gpu_dependency', 'PROFILE_CPU_DEPENDS_ON_GPU'), ('cycle', 'PROFILE_DEPENDENCY_CYCLE'),
    ('missing', 'PROFILE_DEPENDENCY_MISSING'), ('health', 'PROFILE_HEALTH_CONDITION_MISSING'),
    ('host_database', 'PROFILE_HOST_EXPOSURE_INVALID'), ('namespace', 'PROFILE_RESOURCE_NAMESPACE_INVALID'),
    ('host_bind', 'PROFILE_VOLUME_NAMESPACE_INVALID'), ('interpolation', 'PROFILE_INTERPOLATION_INVALID')])
def test_mutated_rendered_models_fail_before_a_launch_plan(tmp_path, tamper, code):
    model = build_profile('production-cpu', 'guard01', api_port=43000, studio_port=43001, secrets_dir=tmp_path)
    if tamper == 'paid': model['services']['worker']['environment']['PUBLISH_ENABLED'] = 'true'
    if tamper == 'env_file': model['services']['api']['env_file'] = '.env'
    if tamper == 'network': model['networks']['front']['name'] = 'agent-hub-shared'
    if tamper == 'volume': model['volumes']['runtime-data']['external'] = True
    if tamper == 'gpu_dependency': model['services']['worker']['depends_on']['comfyui-bridge'] = {'condition': 'service_started'}
    if tamper == 'cycle': model['services']['renderer']['depends_on'] = {'worker': {'condition': 'service_started'}}
    if tamper == 'missing': model['services']['api']['depends_on']['missing-service'] = {'condition': 'service_started'}
    if tamper == 'health': del model['services']['renderer']['healthcheck']
    if tamper == 'host_database': model['services']['postgres']['ports'] = ['127.0.0.1:43002:5432']
    if tamper == 'namespace': model['name'] = 'existing-npd-production'
    if tamper == 'host_bind': model['volumes']['runtime-data']['driver_opts'] = {'type': 'none', 'o': 'bind', 'device': '/srv/agent-hub'}
    if tamper == 'interpolation': model['secrets']['database-password']['file'] = '/external/${AMBIENT_SECRET}/database-password'
    with pytest.raises(ProfileError, match=code): validate_profile(model)


def test_actual_cli_render_ignores_ambient_credentials_and_never_overwrites(tmp_path):
    output = tmp_path / 'ci.json'
    environment = dict(os.environ, OPENAI_API_KEY='UNUSED_HOST_SECRET_SENTINEL',
                       PUBLISH_ENABLED='true', COMPOSE_PROJECT_NAME='agent-hub-production',
                       DOCKER_HOST='tcp://unowned.example:2375', COMPOSE_FILE='foreign.yml')
    before = dict(environment)
    args = [sys.executable, str(ROOT / 'deploy/profiles/profile.py'), '--profile', 'ci', '--instance', 'inert01',
            '--api-port', '44000', '--studio-port', '44001', '--output', str(output)]
    completed = subprocess.run(args, env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    model = json.loads(output.read_text())
    report = json.loads(completed.stdout)
    assert 'UNUSED_HOST_SECRET_SENTINEL' not in output.read_text() + completed.stdout + completed.stderr
    assert model['services']['api']['environment']['PUBLISH_ENABLED'] == 'false'
    plan = report['docker_config_argv']
    assert plan[:4] == ['docker', '--context', 'default', 'compose']
    assert plan[4:6] == ['--project-name', model['name']] and '--env-file' in plan
    assert (tmp_path / 'empty-profile.env').read_bytes() == b'' and environment == before
    original = output.read_bytes()
    again = subprocess.run(args, env=environment, cwd=tmp_path, capture_output=True, text=True, timeout=30)
    assert again.returncode == 78 and output.read_bytes() == original
    assert 'SECRET_SENTINEL' not in again.stderr


def test_production_secret_reference_cannot_point_into_source_checkout(tmp_path):
    with pytest.raises(ProfileError, match='PROFILE_SECRET_DIRECTORY_IN_SOURCE'):
        build_profile('production-cpu', 'separate01', api_port=45000, studio_port=45001,
                      secrets_dir=ROOT / 'secret-placeholder', repo_root=ROOT)


@pytest.mark.parametrize('tamper,code', [
    ('foreign_host_bind', 'PROFILE_SERVICE_MOUNTS_CHANGED'),
    ('long_bind', 'PROFILE_SERVICE_MOUNTS_CHANGED'),
    ('cross_data_volume', 'PROFILE_SERVICE_MOUNTS_CHANGED'),
    ('volume_from', 'PROFILE_SERVICE_CONTRACT_CHANGED'),
    ('studio_data_network', 'PROFILE_SERVICE_NETWORKS_CHANGED'),
    ('renderer_data_network', 'PROFILE_SERVICE_NETWORKS_CHANGED'),
    ('host_alias', 'PROFILE_SERVICE_CONTRACT_CHANGED'),
    ('storage_database_secret', 'PROFILE_SECRET_SCOPE_CHANGED'),
    ('worker_auth_secret', 'PROFILE_SECRET_SCOPE_CHANGED'),
    ('bootstrap_entrypoint', 'PROFILE_BOOTSTRAP_CHANGED'),
    ('worker_command', 'PROFILE_BOOTSTRAP_CHANGED'),
    ('foreign_build_context', 'PROFILE_BUILD_SOURCE_CHANGED'),
    ('foreign_dockerfile', 'PROFILE_BUILD_SOURCE_CHANGED'),
    ('image_override', 'PROFILE_BUILD_SOURCE_CHANGED'),
    ('gpu_enabled_remote', 'PROFILE_ENVIRONMENT_CHANGED'),
    ('gpu_paid_token', 'PROFILE_ENVIRONMENT_CHANGED'),
    ('foreign_workflow_bind', 'PROFILE_SERVICE_MOUNTS_CHANGED'),
    ('health_secret_output', 'PROFILE_SERVICE_CONTRACT_CHANGED'),
    ('public_url_foreign', 'PROFILE_ENVIRONMENT_CHANGED'),
    ('missing_volume_definition', 'PROFILE_VOLUME_CONTRACT_CHANGED'),
    ('build_ssh', 'PROFILE_BUILD_SOURCE_CHANGED'),
    ('docker_socket', 'PROFILE_SERVICE_MOUNTS_CHANGED'),
])
def test_edited_json_service_authority_is_rejected_before_config_argv(tmp_path, tamper, code, monkeypatch):
    """Reviewer admissions and adjacent schema-valid Compose authority edits."""
    def denied(*args, **kwargs):
        raise AssertionError('No Docker, process or network is permitted')
    monkeypatch.setattr(subprocess, 'run', denied)
    monkeypatch.setattr(subprocess, 'Popen', denied)
    monkeypatch.setattr('socket.socket.connect', denied)
    model = build_profile('production-gpu', 'closed01', api_port=47000, studio_port=47001,
                          secrets_dir=tmp_path / 'unprovisioned')
    services = model['services']
    if tamper == 'foreign_host_bind': services['worker']['volumes'] = ['/srv/foreign-agent-hub:/workspace/storage']
    if tamper == 'long_bind': services['worker']['volumes'] = [{'type':'bind','source':'/srv/foreign-agent-hub','target':'/workspace/storage'}]
    if tamper == 'cross_data_volume': services['worker']['volumes'] = ['postgres-data:/workspace/storage']
    if tamper == 'volume_from': services['worker']['volumes_from'] = ['container:foreign-agent-hub']
    if tamper == 'studio_data_network': services['studio-web']['networks'].append('data')
    if tamper == 'renderer_data_network': services['renderer']['networks'].append('data')
    if tamper == 'host_alias': services['worker']['extra_hosts'] = ['agent-hub:host-gateway']
    if tamper == 'storage_database_secret': services['storage-init']['secrets'].append('database-password')
    if tamper == 'worker_auth_secret': services['worker']['secrets'].append('human-auth')
    if tamper == 'bootstrap_entrypoint': services['api']['entrypoint'] = ['/bin/sh','-ec','cat /run/secrets/database-password']
    if tamper == 'worker_command': services['worker']['command'] = ['/bin/sh','-ec','cat /run/secrets/object-secret-key']
    if tamper == 'foreign_build_context': services['api']['build']['context'] = '/srv/foreign-agent-hub'
    if tamper == 'foreign_dockerfile': services['worker']['build']['dockerfile'] = 'foreign-secret-reader.Dockerfile'
    if tamper == 'image_override': services['postgres']['image'] = 'foreign/database:latest'
    if tamper == 'gpu_enabled_remote': services['comfyui-bridge']['environment'].update(COMFYUI_EXECUTION_ENABLED='true', COMFYUI_BACKEND='remote')
    if tamper == 'gpu_paid_token': services['comfyui-bridge']['environment']['COMFYUI_API_TOKEN'] = 'SYNTHETIC_UNUSED_SENTINEL'
    if tamper == 'foreign_workflow_bind': services['comfyui-bridge']['volumes'][0] = '/srv/foreign-agent-hub:/workspace/workflows/comfyui:ro'
    if tamper == 'health_secret_output': services['api']['healthcheck']['test'] = ['CMD-SHELL','cat /run/secrets/database-password']
    if tamper == 'public_url_foreign': services['api']['environment']['PUBLIC_BASE_URL'] = 'http://foreign-agent-hub:8000'
    if tamper == 'missing_volume_definition': del model['volumes']['runtime-data']
    if tamper == 'build_ssh': services['api']['build']['ssh'] = ['default']
    if tamper == 'docker_socket': services['worker']['volumes'].append('/var/run/docker.sock:/var/run/docker.sock')
    # Exercise the serialized boundary, independently of mutable builder objects.
    path = tmp_path / 'edited.json'
    path.write_text(json.dumps(model), encoding='utf-8')
    empty = tmp_path / 'empty-profile.env'
    empty.write_bytes(b'')
    edited = json.loads(path.read_bytes())
    with pytest.raises(ProfileError, match=code):
        validate_profile(edited)
    with pytest.raises(ProfileError, match=code):
        configuration_command(edited, path, empty)


@pytest.mark.parametrize('tamper', ['foreign_json', 'nonempty_env', 'hardlink', 'oversize', 'missing'])
def test_argv_checks_actual_files_instead_of_a_separate_valid_model(tmp_path, tamper):
    model = build_profile('production-cpu', 'fileguard01', api_port=48000, studio_port=48001,
                          secrets_dir=tmp_path / 'unprovisioned')
    config = tmp_path / 'profile.json'
    config.write_text(json.dumps(model), encoding='utf-8')
    empty = tmp_path / 'empty-profile.env'
    empty.write_bytes(b'')
    admitted = configuration_command(model, config, empty)
    assert admitted[-1] == 'config' and str(config) in admitted
    if tamper == 'foreign_json':
        foreign = copy.deepcopy(model)
        foreign['services']['api']['entrypoint'] = ['cat', '/run/secrets/database-password']
        config.write_text(json.dumps(foreign), encoding='utf-8')
    if tamper == 'nonempty_env': empty.write_text('COMPOSE_PROJECT_NAME=foreign-agent-hub', encoding='utf-8')
    if tamper == 'hardlink': os.link(config, tmp_path / 'second-reference.json')
    if tamper == 'oversize': config.write_bytes(b' ' * 1_000_001)
    if tamper == 'missing': config = tmp_path / 'not-created.json'
    with pytest.raises(ProfileError, match='PROFILE_EXECUTION_FILE_CHANGED'):
        configuration_command(model, config, empty)


@pytest.mark.parametrize('boundary', ['first_env', 'last_env', 'second_config_env',
                                     'config_same_bytes_replaced', 'env_same_bytes_replaced',
                                     'caller_model_mutated'])
def test_actual_two_file_read_boundaries_have_a_final_pair_fence(tmp_path, monkeypatch, boundary):
    """Actual owned file edits across the admitted config/env tuple reads.

    first_env reproduces independent DP03. last_env changes the already reread
    config during the final env read; same-byte replacement checks identity,
    while caller_model_mutated checks that the validated DTO stays immutable.
    """
    model = build_profile('production-cpu', 'pairguard01', api_port=49000, studio_port=49001,
                          secrets_dir=tmp_path / 'unprovisioned')
    config, empty = tmp_path / 'approved.json', tmp_path / 'empty-profile.env'
    config.write_text(json.dumps(model), encoding='utf-8')
    empty.write_bytes(b'')
    original_content = config.read_bytes()
    foreign = copy.deepcopy(model)
    foreign['services']['worker']['command'] = ['cat', '/run/secrets/database-password']
    real_read = compiler._read_execution_file
    calls = {config: 0, empty: 0}
    changed = []
    def mutate_at_read(path, *, maximum):
        calls[path] += 1
        if path == empty and calls[path] == (2 if boundary == 'last_env' else 1):
            if boundary in {'first_env', 'last_env'}:
                config.write_text(json.dumps(foreign), encoding='utf-8')
                changed.append('config')
            if boundary == 'config_same_bytes_replaced':
                replacement = tmp_path / 'new-config.json'
                replacement.write_bytes(original_content)
                os.replace(replacement, config)
                changed.append('config_identity')
            if boundary == 'env_same_bytes_replaced':
                replacement = tmp_path / 'new-env.env'
                replacement.write_bytes(b'')
                os.replace(replacement, empty)
                changed.append('env_identity')
        if path == config and calls[path] == 2 and boundary == 'second_config_env':
            empty.write_text('COMPOSE_PROJECT_NAME=foreign-agent-hub', encoding='utf-8')
            changed.append('env')
        if path == config and calls[path] == 1 and boundary == 'caller_model_mutated':
            model['services']['worker']['command'] = foreign['services']['worker']['command']
            config.write_text(json.dumps(foreign), encoding='utf-8')
            changed.append('model_and_config')
        return real_read(path, maximum=maximum)
    monkeypatch.setattr(compiler, '_read_execution_file', mutate_at_read)
    with pytest.raises(ProfileError, match='PROFILE_EXECUTION_FILE_CHANGED'):
        configuration_command(model, config, empty)
    assert changed, 'The actual I/O-boundary edit must occur before refusal'
    if boundary.startswith('config_same'):
        assert config.read_bytes() == original_content
    if boundary.startswith('env_same'):
        assert empty.read_bytes() == b''
