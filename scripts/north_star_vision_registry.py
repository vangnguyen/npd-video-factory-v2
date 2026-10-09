"""Synthetic protected Vision keys, retained actual PNGs and public-only recovery."""
import argparse, asyncio, base64, hashlib, json, re, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api'))
import httpx
from services.windows_native.contracts import file_sha
from services.windows_native.store import Store
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.vision_credentials import NativeVisionKeyVault, PrivateVisionKey
from services.windows_native.vision_registry import VisionProfile, NativeVisionFactory, load
from services.windows_native.media_frame_analysis import checked_path
from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from scripts.north_star_vision_frame_bridge import config_for
from scripts.north_star_google_oauth_operations import journals
from scripts.north_star_google_oauth_vault import acl

KEY = 'sk-explicit-synthetic-vision-registry-not-real'


def write(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    assert KEY not in raw and 'Bearer ' not in raw and 'data:image/' not in raw
    with path.open('x', encoding='utf-8', newline='\n') as handle: handle.write(raw)


def owned(path, kind, fresh=False):
    path = path.resolve()
    if path.parent != Path('C:/') or not re.fullmatch(r'vf-native-fixture-vision-registry-' + kind + r'-[0-9]{2}', path.name) or fresh and path.exists():
        raise ValueError('Fresh owned Vision registry fixture root required')
    return path


def exact(root, prior):
    config = config_for(root); store = Store(root); vision = NativeVision(store, config)
    projects = json.loads((prior / 'expected-projects.json').read_bytes()); bindings = json.loads((prior / 'input-bindings.json').read_bytes())
    for project, binding in zip(projects, bindings, strict=True):
        assert store.get(project['id']) == project
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='retained-vision-key-input')
        bridge = NativeEvidenceFrameExtractor(root, config, project['id'], vision.sources(project, request)[0])
        assert bridge.binding() == binding
    for row in json.loads((prior / 'expected-legacy-vision-history.json').read_bytes()):
        assert vision.get(row['project_id'], row['vision_id']) == row
    assert journals(store) == json.loads((prior / 'expected-journals.json').read_bytes())
    return config, store, vision, projects, bindings


def reopen(args):
    root = owned(args.restore_root, 'restore'); private = owned(args.private_root, 'secrets'); out = args.output.resolve(); prior = args.input.resolve()
    exact(root, prior)
    receipt_export = json.loads((root / 'vision-public-key-receipts.json').read_bytes())
    assert receipt_export == json.loads((out / 'public-key-receipts.json').read_bytes())
    registry = private / 'public-vision-registry.json'
    mounted = NativeVisionKeyVault(private, root, 'wsp_vision_rehearsal')
    absent = owned(Path('C:/vf-native-fixture-vision-registry-secrets-02'), 'secrets', True)
    unmounted = NativeVisionKeyVault(absent, root, 'wsp_vision_rehearsal')
    from unittest.mock import patch
    with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO RECOVERY OR STARTUP DECRYPT')):
        original = next(iter(load(registry, mounted).values())).public()
        missing = next(iter(load(registry, unmounted, operator_enabled=True).values())).public()
    assert original['credential_present'] and original['status'] == 'NOT_CONFIGURED'
    assert not missing['credential_present'] and missing['status'] == 'NOT_CONFIGURED' and not absent.exists()
    write(out / ('new-process-replay.json' if args.new_process else 'restored-in-process.json'), {
        'original_two_projects_nine_pngs_nine_journals_four_legacy_histories_exact': True,
        'public_receipts_restored_exact_private_cipher_not_in_public_backup': True,
        'mounted_but_operator_disabled_and_unmounted_enabled_discovery_inert_without_decrypt': True,
        'private_root_references': [r['reference'] for r in receipt_export], 'external_calls': 0,
        'paid_operations': 0, 'semantic_inference_performed': False, 'runtime_authority_granted': False})


def run(args):
    state = owned(args.state_root, 'state', True); restored = owned(args.restore_root, 'restore', True)
    private = owned(args.private_root, 'secrets', True); out = args.output.resolve(); prior = args.input.resolve()
    if out.exists() or out == ROOT or ROOT in out.parents: raise ValueError('Fresh external Vision registry evidence required')
    out.mkdir(parents=True); original_backup = prior / 'public-vision-frame-input.zip'
    write(out / 'prior-to-owned-state-restore.json', restore_backup(original_backup, state, expected_sha256=file_sha(original_backup)))
    config, store, vision, projects, bindings = exact(state, prior)
    originals = {p.relative_to(state).as_posix(): file_sha(p) for p in state.rglob('*') if p.is_file()
        and p.suffix != '.sqlite3' and not p.name.endswith(('-wal', '-shm'))}
    vault = NativeVisionKeyVault(private, state, 'wsp_vision_rehearsal')
    value = PrivateVisionKey(workspace_id=vault.workspace, credential_alias='explicit-vision-rehearsal', api_key=KEY)
    receipts = [vault.save(value), vault.save(value)]
    assert receipts[0]['reference'] != receipts[1]['reference']
    assert receipts[0]['key_binding_sha256'] == receipts[1]['key_binding_sha256']
    for r in receipts:
        assert acl(vault.path(r['reference'])) and vault.key(r) == KEY
        assert KEY.encode() not in vault.path(r['reference']).read_bytes()
    private_hashes = {r['reference']: file_sha(vault.path(r['reference'])) for r in receipts}
    p = VisionProfile(profile_id='nvip_' + 'a' * 32, enabled=True, key_receipt=receipts[1],
        estimated_cost_vnd='200', input_vnd_per_million_tokens='10000', cached_input_vnd_per_million_tokens='1000', output_vnd_per_million_tokens='20000')
    public_registry = private / 'public-vision-registry.json'
    write(public_registry, {'version': 1, 'workspace_id': vault.workspace, 'profiles': [p.model_dump(mode='json')]})
    from unittest.mock import patch
    with patch('services.windows_native.assemblyai_connection._dpapi', side_effect=AssertionError('NO REGISTRY DISCOVERY DECRYPT')):
        default = next(iter(load(public_registry, vault).values())).public()
    assert default['status'] == 'NOT_CONFIGURED' and default['credential_present'] and not default['provider_authorized']
    calls = []; results = []
    for project, binding in zip(projects, bindings, strict=True):
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='protected-key-structured-mock')
        source = vision.sources(project, request)[0]; bridge = NativeEvidenceFrameExtractor(state, config, project['id'], source)
        def handler(request):
            assert request.headers['Authorization'] == 'Bearer ' + KEY
            assert str(request.url) == 'https://api.openai.com/v1/responses' and request.method == 'POST'
            body = json.loads(request.content); assert body['store'] is False
            images = [v for v in body['input'][0]['content'] if v['type'] == 'input_image']
            checksums = [hashlib.sha256(base64.b64decode(v['image_url'].split(',', 1)[1], validate=True)).hexdigest() for v in images]
            assert checksums == [v['sha256'] for v in binding['source_frame_evidence']]
            calls.append({'frame_count': len(images), 'frame_sha256': checksums, 'fixed_endpoint': True, 'synthetic_key_matches': True})
            return httpx.Response(200, json=response_payload(len(images)))
        factory = NativeVisionFactory(p, vault, operator_enabled=True, transport=httpx.MockTransport(handler))
        provider = factory.provider(bridge)
        prediction = asyncio.run(provider.analyze(checked_path(config, source['asset']), metadata=bridge.input_metadata(), scenes=[],
            asset_id=source['asset']['id'], checksum_sha256=source['asset']['sha256'], sample_interval_seconds=1))
        assert prediction.provenance['mock_tested'] and not prediction.provenance['real_provider_tested']
        assert [(f.timestamp_seconds, f.evidence_frame_reference) for f in prediction.frames] == [(f['timestamp_seconds'], f['reference']) for f in binding['source_frame_evidence']]
        results.append({'project_id': project['id'], 'frame_count': len(prediction.frames), 'configuration_sha256': factory.sha256,
            'request_sha256': prediction.provenance['request_sha256'], 'response_sha256': prediction.provenance['response_sha256'],
            'computed_mock_usage_cost_vnd': str(prediction.actual_cost_vnd), 'observed_actual_paid_cost_vnd': None,
            'semantic_inference_performed': False, 'runtime_authority_granted': False})
    assert [v['frame_count'] for v in calls] == [1, 8]
    exact(state, prior)
    assert all(file_sha(state / name) == checksum for name, checksum in originals.items())
    assert all(file_sha(vault.path(ref)) == checksum for ref, checksum in private_hashes.items())
    write(state / 'vision-public-key-receipts.json', receipts); write(out / 'public-key-receipts.json', receipts)
    write(out / 'default-public-discovery.json', default); write(out / 'mock-wire-summary.json', calls); write(out / 'mock-results.json', results)
    backup = create_backup(config, out / 'public-vision-registry.zip'); write(out / 'backup.json', backup)
    import zipfile
    with zipfile.ZipFile(out / 'public-vision-registry.zip') as z:
        assert not any(name.endswith('.dpapi') for name in z.namelist())
        assert all(KEY.encode() not in z.read(name) for name in z.namelist())
    write(out / 'restore.json', restore_backup(out / 'public-vision-registry.zip', restored, expected_sha256=backup['sha256']))
    reopen(args)
    sources = ('services/windows_native/vision_credentials.py', 'services/windows_native/vision_registry.py',
        'services/windows_native/tests/test_vision_registry.py', 'scripts/north_star_vision_registry.py')
    write(out / 'evidence.json', {'schema_version': 'native-vision-registry-rehearsal-v1', 'source_sha256': {n: file_sha(ROOT / n) for n in sources},
        'prior_backup_sha256': file_sha(original_backup), 'current_backup_sha256': backup['sha256'],
        'projects': 2, 'actual_png_samples': 9, 'new_cpu_jobs': 0, 'mock_structured_requests': 2,
        'actual_synthetic_dpapi_immutable_keys': 2, 'actual_protected_dacl_verified': 2,
        'original_projects_nine_journals_four_legacy_histories_all_files_exact': True,
        'startup_discovery_and_recovery_no_decrypt_or_automatic_authority': True,
        'real_secret_reads': 0, 'external_provider_calls': 0, 'paid_operations': 0, 'real_publications': 0,
        'semantic_inference_performed': False, 'native_official_runtime_integrated': False,
        'decoded_pts_verified': False, 'continuous_tracking_performed': False, 'browser_owner_acceptance': False,
        'exports': {f.name: {'sha256': file_sha(f), 'bytes': f.stat().st_size} for f in out.iterdir() if f.is_file()}})
    print(json.dumps({'status': 'PASS', 'protected_synthetic_keys': 2, 'actual_dacl_checks': 2, 'mock_requests': 2, 'reused_pngs': 9, 'external_calls': 0}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--input', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    p.add_argument('--state-root', type=Path); p.add_argument('--restore-root', type=Path, required=True); p.add_argument('--private-root', type=Path, required=True)
    p.add_argument('--new-process', action='store_true'); args = p.parse_args()
    if args.new_process: reopen(args)
    else: run(args)
