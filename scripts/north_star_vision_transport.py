"""Reuse retained actual Native frames under hardened wire mocks; no new CPU job."""
import argparse, asyncio, base64, copy, hashlib, json, logging, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api'))
import httpx
from app.auto_edit_models import SceneRead
from app.openai_vision_provider import OpenAIVisionProvider
from app.publishing_wire import _sensitive
from services.windows_native.contracts import file_sha
from services.windows_native.store import Store
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.media_frame_analysis import checked_path
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from scripts.north_star_vision_frame_bridge import owned, config_for, write
from scripts.north_star_google_oauth_operations import journals


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--restore-root', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); prior = args.input.resolve(); out = args.output.resolve()
    if out.exists() or out == ROOT or ROOT in out.parents:
        raise ValueError('Fresh external transport evidence required')
    root = owned(args.restore_root, 'restore'); config = config_for(root); store = Store(root); vision = NativeVision(store, config)
    projects = json.loads((prior / 'expected-projects.json').read_bytes())
    bindings = json.loads((prior / 'input-bindings.json').read_bytes())
    histories = json.loads((prior / 'expected-legacy-vision-history.json').read_bytes())
    expected_journals = json.loads((prior / 'expected-journals.json').read_bytes())
    assert journals(store) == expected_journals
    original_files = {p.relative_to(root).as_posix(): file_sha(p) for p in root.rglob('*') if p.is_file()
        and p.suffix != '.sqlite3' and not p.name.endswith(('-wal', '-shm'))}
    calls = []; results = []; visible_logs = []
    logger = logging.getLogger('httpcore.connection'); previous_level = logger.level
    class Capture(logging.Handler):
        def emit(self, record): visible_logs.append(record.getMessage())
    capture = Capture(); logger.addHandler(capture); logger.setLevel(logging.DEBUG)
    try:
        # These fixed controls intentionally bracket the context-local wire filter.
        logger.debug('NORMAL BEFORE NATIVE VISION TRANSPORT REHEARSAL')
        for project, binding in zip(projects, bindings, strict=True):
            assert store.get(project['id']) == project
            request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='retained-hardened-vision-transport')
            source = vision.sources(project, request)[0]; bridge = NativeEvidenceFrameExtractor(root, config, project['id'], source)
            assert bridge.binding() == binding
            def handler(request):
                assert str(request.url) == 'https://api.openai.com/v1/responses' and request.method == 'POST'
                assert request.headers['Accept-Encoding'] == 'identity'
                body = json.loads(request.content); assert body['store'] is False
                images = [value for value in body['input'][0]['content'] if value['type'] == 'input_image']
                checksums = [hashlib.sha256(base64.b64decode(value['image_url'].split(',', 1)[1], validate=True)).hexdigest() for value in images]
                assert checksums == [frame['sha256'] for frame in binding['source_frame_evidence']]
                logger.debug('SYNTHETIC PRIVATE VISION WIRE BODY')
                calls.append({'transport': 'explicit_httpx_protocol_mock', 'frame_count': len(images), 'frame_sha256': checksums,
                    'fixed_official_origin': True, 'store_false': True, 'identity_encoding': True})
                return httpx.Response(200, json=response_payload(len(images)))
            provider = OpenAIVisionProvider(credential_alias='explicit-synthetic-native-vision', credential_resolver=lambda _: 'contract-key-not-real',
                frame_extractor=bridge, transport=httpx.MockTransport(handler), allow_zero_cost_contract_test=True)
            prediction = asyncio.run(provider.analyze(checked_path(config, source['asset']), metadata=bridge.input_metadata(),
                scenes=[SceneRead.model_validate(value) for value in source['scenes']], asset_id=source['asset']['id'],
                checksum_sha256=source['asset']['sha256'], sample_interval_seconds=1))
            assert _sensitive.get() is False and bridge.binding() == binding and store.get(project['id']) == project
            assert prediction.provenance['mock_tested'] is True and prediction.provenance['real_provider_tested'] is False
            assert [(frame.timestamp_seconds, frame.evidence_frame_reference) for frame in prediction.frames] == [(f['timestamp_seconds'], f['reference']) for f in binding['source_frame_evidence']]
            results.append({'project_id': project['id'], 'source_sha256': source['asset']['sha256'],
                'frame_count': len(prediction.frames), 'frame_references': [frame.evidence_frame_reference for frame in prediction.frames],
                'request_sha256': prediction.provenance['request_sha256'], 'response_sha256': prediction.provenance['response_sha256'],
                'mock_cost_receipt': prediction.provenance['cost_receipt'], 'observed_actual_paid_cost_vnd': None,
                'semantic_inference_performed': False, 'external_provider_calls': 0, 'paid_operations': 0})
        logger.debug('NORMAL AFTER NATIVE VISION TRANSPORT REHEARSAL')
    finally:
        logger.removeHandler(capture); logger.setLevel(previous_level)
    assert visible_logs == ['NORMAL BEFORE NATIVE VISION TRANSPORT REHEARSAL', 'NORMAL AFTER NATIVE VISION TRANSPORT REHEARSAL']
    assert [value['frame_count'] for value in calls] == [1, 8]
    for row in histories:
        assert vision.get(row['project_id'], row['vision_id']) == row
    assert journals(store) == expected_journals
    assert all(file_sha(root / name) == checksum for name, checksum in original_files.items())
    sources = ('apps/api/app/openai_vision_provider.py', 'apps/api/tests/test_vision_transport_safety.py', 'scripts/north_star_vision_transport.py')
    write(out, {'schema_version': 'native-vision-hardened-transport-rehearsal-v1', 'source_sha256': {name: file_sha(ROOT / name) for name in sources},
        'prior_evidence_sha256': file_sha(prior / 'evidence.json'), 'prior_backup_sha256': file_sha(prior / 'public-vision-frame-input.zip'),
        'projects': 2, 'reused_actual_png_samples': 9, 'new_cpu_jobs': 0, 'mock_structured_requests': 2,
        'mock_wire_summary': calls, 'mock_results': results, 'normal_controls_visible_private_wire_logs_suppressed_context_restored': True,
        'original_projects_nine_journals_four_legacy_histories_all_source_files_exact': True, 'original_source_files': original_files,
        'real_secret_reads': 0, 'external_provider_calls': 0, 'paid_operations': 0, 'real_publications': 0,
        'semantic_inference_performed': False, 'continuous_tracking_performed': False, 'decoded_pts_verified': False,
        'native_official_runtime_integrated': False, 'browser_owner_real_provider_acceptance': False})
    print(json.dumps({'status': 'PASS', 'reused_png_frames': 9, 'mock_requests': 2, 'new_cpu_jobs': 0, 'private_wire_logs_suppressed': True}))


if __name__ == '__main__': main()
