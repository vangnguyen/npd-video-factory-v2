"""Retain complete response/cost evidence before semantic or late configuration failure."""
import argparse, asyncio, json, re, sys, uuid
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api'))
import httpx
from services.windows_native.contracts import digest, file_sha, WorkflowError
from services.windows_native.store import Store
from services.windows_native.costs import CostLedger
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.vision_credentials import NativeVisionKeyVault
from services.windows_native.vision_registry import VisionProfile, NativeVisionFactory
from services.windows_native.media_frame_analysis import checked_path
from services.windows_native.backup import create_backup, restore_backup
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from scripts.north_star_vision_frame_bridge import config_for
from scripts.north_star_google_oauth_operations import journals
from app.openai_vision_provider import OpenAIVisionResponseError, VisionResponseObservation


def write(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    assert 'sk-explicit-synthetic-' not in raw and 'Bearer ' not in raw and 'data:image/' not in raw
    with path.open('x', encoding='utf-8', newline='\n') as h: h.write(raw)


def owned(path, kind, fresh=False):
    path = path.resolve()
    if path.parent != Path('C:/') or not re.fullmatch(r'vf-native-fixture-vision-response-' + kind + r'-[0-9]{2}', path.name) or fresh and path.exists():
        raise ValueError('Fresh owned Vision response fixture required')
    return path


def original(root, prior):
    config = config_for(root); store = Store(root); vision = NativeVision(store, config)
    projects = json.loads((prior / 'expected-projects.json').read_bytes()); bindings = json.loads((prior / 'input-bindings.json').read_bytes())
    for project, binding in zip(projects, bindings, strict=True):
        assert store.get(project['id']) == project
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='original-vision-response-input')
        assert NativeEvidenceFrameExtractor(root, config, project['id'], vision.sources(project, request)[0]).binding() == binding
    for row in json.loads((prior / 'expected-legacy-vision-history.json').read_bytes()):
        assert vision.get(row['project_id'], row['vision_id']) == row
    old = json.loads((prior / 'expected-journals.json').read_bytes()); current = journals(store)
    assert all(current[name][:len(rows)] == rows for name, rows in old.items())
    return config, store, vision, projects, bindings


def reopen(args):
    out = args.output.resolve(); root = owned(args.restore_root, 'restore')
    _, store, _, projects, _ = original(root, args.frame_input.resolve())
    expected = json.loads((out / 'expected-journals.json').read_bytes()); assert journals(store) == expected
    costs = CostLedger(store)
    for row in json.loads((out / 'response-observations.json').read_bytes()):
        observation = VisionResponseObservation.model_validate(row['observation'])
        with store.transaction() as con: saved = costs.record(con.execute('SELECT * FROM native_cost_operations WHERE id=?', (row['cost_operation_id'],)).fetchone())
        assert saved['status'] == 'response_received' and saved['receipt']['provider_response_sha256'] == observation.response_sha256
        assert saved['actual_cost'] is None and not saved['paid'] and not saved['external_call']
        assert not costs.pending(saved['id'])
    write(out / ('new-process-replay.json' if args.new_process else 'restored-in-process.json'), {
        'all_ten_journals_five_costs_complete_response_observations_original_projects_frames_and_histories_exact': True,
        'private_key_decrypt_provider_calls_or_late_authority_renewal': False, 'original_journal_rows_preserved': True,
        'observed_actual_paid_costs_known': False})


def run(args):
    out = args.output.resolve(); state = owned(args.state_root, 'state', True); restored = owned(args.restore_root, 'restore', True)
    prior = args.frame_input.resolve(); registry_input = args.registry_input.resolve()
    if out.exists() or out == ROOT or ROOT in out.parents: raise ValueError('Fresh external response evidence required')
    out.mkdir(parents=True); archive = registry_input / 'public-vision-registry.zip'
    write(out / 'prior-restore.json', restore_backup(archive, state, expected_sha256=file_sha(archive)))
    config, store, vision, projects, bindings = original(state, prior)
    costs = CostLedger(store)
    private = Path('C:/vf-native-fixture-vision-registry-secrets-01'); vault = NativeVisionKeyVault(private, state, 'wsp_vision_rehearsal')
    public = json.loads((private / 'public-vision-registry.json').read_bytes()); profile = VisionProfile.model_validate(public['profiles'][0])
    receipt_export = json.loads((registry_input / 'public-key-receipts.json').read_bytes())
    private_hashes = {r['reference']: file_sha(vault.path(r['reference'])) for r in receipt_export}
    original_files = {p.relative_to(state).as_posix(): file_sha(p) for p in state.rglob('*') if p.is_file()
        and p.suffix != '.sqlite3' and not p.name.endswith(('-wal', '-shm'))}
    wire = []; observations = []; results = []
    for number, kind in enumerate(('success', 'invalid-structured', 'wrong-model', 'missing-usage', 'late-config')):
        project = projects[number % 2]; binding = bindings[number % 2]
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='response-observer-retained-'+kind)
        source = vision.sources(project, request)[0]; bridge = NativeEvidenceFrameExtractor(state, config, project['id'], source)
        def handler(request):
            wire.append({'kind': kind, 'fixed_endpoint': str(request.url) == 'https://api.openai.com/v1/responses', 'method': request.method})
            payload = response_payload(bridge.max_frames)
            if kind == 'invalid-structured': payload['output'][0]['content'][0]['text'] = 'INVALID EXPLICIT MOCK SEMANTICS'
            if kind == 'wrong-model': payload['model'] = 'unapproved-model'
            if kind == 'missing-usage': payload.pop('usage')
            if kind == 'late-config': factory.operator_enabled = False
            return httpx.Response(200, json=payload)
        factory = NativeVisionFactory(profile, vault, operator_enabled=True, transport=httpx.MockTransport(handler))
        operation = costs.begin(project_id=project['id'], provider='openai-vision', model='gpt-5-mini',
            operation='vision_response.'+uuid.uuid4().hex, request_sha256=digest({'input': binding, 'configuration': factory.sha256, 'kind': kind}),
            estimated_cost='200', external_call=False, paid=False)
        def retain(observation):
            parsed = VisionResponseObservation.model_validate(observation.model_dump(mode='json'))
            usage = None if parsed.input_tokens is None else {'input_tokens': parsed.input_tokens,
                'output_tokens': parsed.output_tokens, 'total_tokens': parsed.input_tokens + parsed.output_tokens}
            # Known response evidence is settled before any late Owner/config/source fence.
            costs.settle(operation, status='response_received', response_sha256=parsed.response_sha256, usage=usage)
            observations.append({'kind': kind, 'cost_operation_id': operation, 'observation': parsed.model_dump(mode='json'),
                'actual_billed_cost_vnd': None, 'provider_body_or_captions_persisted': False})
        adapter = factory.provider(bridge, response_observer=retain); failure = None
        try:
            result = asyncio.run(adapter.analyze(checked_path(config, source['asset']), metadata=bridge.input_metadata(), scenes=[],
                asset_id=source['asset']['id'], checksum_sha256=source['asset']['sha256'], sample_interval_seconds=1))
            assert kind in ('success', 'late-config') and result.provenance['response_sha256'] == observations[-1]['observation']['response_sha256']
        except OpenAIVisionResponseError as error:
            assert kind in ('invalid-structured', 'wrong-model', 'missing-usage'); failure = error.code
        assert not costs.pending(operation)
        if kind == 'late-config':
            try: factory.check()
            except WorkflowError: failure = 'NATIVE_VISION_FACTORY_CONFIGURATION_CHANGED'
            else: raise AssertionError('Late configuration must not grant runtime success')
        results.append({'kind': kind, 'complete_response_retained': True, 'failure_code': failure,
            'mock_adapter_semantic_success': kind == 'success', 'native_runtime_authority_or_success_claimed': False})
        original(state, prior)
    assert len(wire) == len(observations) == 5
    assert all(v['observation']['calculated_usage_cost_vnd'] is None if v['kind'] == 'missing-usage'
        else v['observation']['calculated_usage_cost_vnd'] is not None for v in observations)
    assert all(file_sha(state / name) == checksum for name, checksum in original_files.items())
    assert all(file_sha(vault.path(ref)) == checksum for ref, checksum in private_hashes.items())
    write(out / 'response-observations.json', observations); write(out / 'mock-wire-summary.json', wire); write(out / 'mock-outcomes.json', results)
    write(out / 'cost-summary.json', [costs.summary(p['id']) for p in projects]); write(out / 'expected-journals.json', journals(store))
    backup = create_backup(config, out / 'public-vision-response.zip'); write(out / 'backup.json', backup)
    write(out / 'restore.json', restore_backup(out / 'public-vision-response.zip', restored, expected_sha256=backup['sha256']))
    reopen(args)
    sources = ('apps/api/app/openai_vision_provider.py', 'apps/api/tests/test_vision_response_observer.py',
        'services/windows_native/vision_registry.py', 'services/windows_native/tests/test_vision_registry.py', 'scripts/north_star_vision_response.py')
    write(out / 'evidence.json', {'schema_version': 'native-vision-complete-response-rehearsal-v1',
        'source_sha256': {n: file_sha(ROOT / n) for n in sources}, 'public_backup_sha256': backup['sha256'],
        'two_projects_original_nine_journal_rows_frames_all_files_four_legacy_histories_preserved': True,
        'journal_count': len(journals(store)), 'mock_requests': 5, 'complete_observations': 5, 'cost_operations': 5,
        'known_usage_observations': 4, 'unknown_usage_observations': 1, 'reused_unique_pngs': 9, 'new_cpu_jobs': 0,
        'known_evidence_settled_before_semantic_or_late_configuration_failure': True,
        'original_private_cipher_generations_exact': True, 'provider_bodies_or_captions_in_observations': False,
        'real_secret_reads': 0, 'external_provider_calls': 0, 'paid_operations': 0, 'real_publications': 0,
        'semantic_inference_performed': False, 'native_official_runtime_integrated': False,
        'browser_owner_acceptance': False, 'billing_invoice_verified': False,
        'exports': {p.name: {'sha256': file_sha(p), 'bytes': p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status': 'PASS', 'mock_requests': 5, 'retained_complete_responses': 5, 'known_usage': 4, 'unknown_usage': 1, 'actual_paid_costs': None}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--frame-input', type=Path, required=True); p.add_argument('--registry-input', type=Path)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--state-root', type=Path); p.add_argument('--restore-root', type=Path, required=True)
    p.add_argument('--new-process', action='store_true'); args = p.parse_args()
    if args.new_process: reopen(args)
    else: run(args)
