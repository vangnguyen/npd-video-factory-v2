"""Retained CPU frame input and structured mock contracts; no paid semantic call."""
import argparse, asyncio, base64, copy, hashlib, json, re, subprocess, sys, uuid
from dataclasses import asdict, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / 'apps/api'))
import httpx
from PIL import Image
from services.windows_native.contracts import digest, file_sha
from services.windows_native.pipeline import Config, Pipeline
from services.windows_native.store import Store
from services.windows_native.media import ingest_media
from services.windows_native.media_frame_analysis import view, checked_path
from services.windows_native.vision import NativeVision
from services.windows_native.vision_models import NativeVisionRequest
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.tests.test_vision_frame_bridge import response_payload
from services.windows_native.backup import create_backup, restore_backup, database_status
from app.openai_vision_provider import OpenAIVisionProvider
from scripts.north_star_google_oauth_operations import journals


def write(path, value):
    raw = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n'
    assert 'contract-key-not-real' not in raw and 'data:image/' not in raw and 'Bearer ' not in raw
    with path.open('x', encoding='utf-8', newline='\n') as handle:
        handle.write(raw)


def owned(path, kind, fresh=False):
    path = path.resolve()
    if path.parent != Path('C:/') or not re.fullmatch(r'vf-native-fixture-vision-frame-bridge-' + kind + r'-[0-9]{2}', path.name) or fresh and path.exists():
        raise ValueError('Fresh owned frame bridge root required')
    return path


def config_for(root):
    return Config(data_root=root, secret_file=root.parent / (root.name + '-absent-private') / 'absent-openai',
        assemblyai_secret_file=root.parent / (root.name + '-absent-private') / 'absent-asr')


def reopen(args):
    out = args.output.resolve(); root = owned(args.restore_root, 'restore')
    config = config_for(root); store = Store(root); vision = NativeVision(store, config)
    expected = json.loads((out / 'expected-projects.json').read_bytes())
    binding_exports = json.loads((out / 'input-bindings.json').read_bytes())
    contracts = json.loads((out / 'provider-contracts.json').read_bytes())
    for project, binding, result in zip(expected, binding_exports, contracts, strict=True):
        assert store.get(project['id']) == project
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[binding['source_observation_id']], request_key='retained-vision-input-recovery')
        source = vision.sources(project, request)[0]
        bridge = NativeEvidenceFrameExtractor(root, config, project['id'], source)
        assert bridge.binding() == binding
        extracted = asyncio.run(bridge.extract(checked_path(config, source['asset']), metadata=bridge.input_metadata(), scenes=[],
            asset_id=source['asset']['id'], sample_interval_seconds=1))
        assert [frame.sha256 for frame in extracted] == [frame['sha256'] for frame in binding['source_frame_evidence']]
        assert [(frame.timestamp_seconds, frame.evidence_frame_reference) for frame in extracted] == [(f['timestamp_seconds'], f['evidence_frame_reference']) for f in result['frames']]
    history = json.loads((out / 'expected-legacy-vision-history.json').read_bytes())
    for row in history:
        assert vision.get(row['project_id'], row['vision_id']) == row
    assert journals(store) == json.loads((out / 'expected-journals.json').read_bytes())
    assert database_status(store.db)['active_operations'] == 0
    write(out / ('new-process-replay.json' if args.new_process else 'restored-in-process.json'), {
        'two_projects_original_jobs_cpu_observations_png_payloads_metadata_bindings_mock_structured_refs_legacy_vision_history_all_journals_exact': True,
        'frame_input_extractions': 2, 'provider_calls': 0, 'paid_operations': 0,
        'decoded_pts_continuous_tracking_semantic_inference_or_runtime_enablement_claimed': False})


def run(args):
    out = args.output.resolve(); state = owned(args.state_root, 'state', True); restored = owned(args.restore_root, 'restore', True)
    if out.exists() or out == ROOT or ROOT in out.parents:
        raise ValueError('Fresh external frame bridge evidence required')
    out.mkdir(parents=True); state.mkdir(); config = config_for(state); store = Store(state); vision = NativeVision(store, config)
    supplied = out / 'explicit-owned-image-source.png'
    Image.new('RGB', (3840, 2160), (42, 137, 242)).save(supplied)
    video = out / 'explicit-owned-video-source.mp4'
    subprocess.run([str(config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n', '-f', 'lavfi',
        '-i', 'testsrc2=size=640x360:rate=24:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(video)],
        check=True, capture_output=True, timeout=30)
    original_projects = []; bindings = []; contracts = []; wire = []; histories = []; frame_jobs = []
    for number, (source_file, kind, content_type) in enumerate(((supplied, 'image', 'image/png'), (video, 'video', 'video/mp4')), 1):
        asset = ingest_media(config, source_file, content_type, 'Explicit technology input rehearsal', rights_confirmed=True, illustration=kind == 'image')
        project = store.create('Technology educational frame input ' + str(number), '', 'media')
        project = store.append_media(project['id'], project['revision'], asset)
        job = store.enqueue(project['id'], project['revision'], 'media_frames', 'retained-frame-input-cpu-' + str(number)); job = store.claim()
        produced = Pipeline(config).run(job, lambda _: None); store.finish(job, result=produced); project = store.get(project['id'])
        frame_jobs.append(store.get_job(job['id']))
        observation = view(store, project['id'])['observations'][0]
        request = NativeVisionRequest(revision=project['revision'], observation_ids=[observation['observation_id']], request_key='retained-frame-input-binding-' + str(number))
        source = vision.sources(project, request)[0]; bridge = NativeEvidenceFrameExtractor(state, config, project['id'], source)
        binding = bridge.binding(); before = copy.deepcopy(project)
        def handler(request):
            assert str(request.url) == 'https://api.openai.com/v1/responses' and request.method == 'POST'
            body = json.loads(request.content); assert body['store'] is False
            prompt = body['input'][0]['content'][0]['text']; assert 'any content niche' in prompt and 'real-estate media' not in prompt
            images = [value for value in body['input'][0]['content'] if value['type'] == 'input_image']
            checksums = [hashlib.sha256(base64.b64decode(value['image_url'].split(',', 1)[1], validate=True)).hexdigest() for value in images]
            assert checksums == [frame['sha256'] for frame in binding['source_frame_evidence']]
            wire.append({'transport': 'explicit_httpx_protocol_mock', 'method': 'POST', 'fixed_official_endpoint': True,
                'frame_count': len(images), 'frame_sha256': checksums, 'store_false': True, 'niche_generic_sample_limit_prompt': True})
            return httpx.Response(200, json=response_payload(len(images)))
        provider = OpenAIVisionProvider(credential_alias='explicit-synthetic-native-vision', credential_resolver=lambda _: 'contract-key-not-real',
            frame_extractor=bridge, transport=httpx.MockTransport(handler), allow_zero_cost_contract_test=True)
        prediction = asyncio.run(provider.analyze(checked_path(config, asset), metadata=bridge.input_metadata(), scenes=[],
            asset_id=asset['id'], checksum_sha256=asset['sha256'], sample_interval_seconds=1))
        assert store.get(project['id']) == before and bridge.binding() == binding
        assert prediction.provenance['mock_tested'] is True and prediction.provenance['real_provider_tested'] is False
        assert [(frame.timestamp_seconds, frame.evidence_frame_reference) for frame in prediction.frames] == [(f['timestamp_seconds'], f['reference']) for f in binding['source_frame_evidence']]
        contracts.append({'fixture_kind': 'explicit_structured_http_mock_not_semantic_or_paid_provider_acceptance',
            'project_id': project['id'], 'asset_id': asset['id'], 'frames': [asdict(frame) for frame in prediction.frames],
            'adapter_provenance': prediction.provenance, 'adapter_declares_paid_external_capability': True,
            'mock_cost_receipt_vnd': str(prediction.actual_cost_vnd), 'observed_actual_paid_cost_vnd': None,
            'semantic_inference_performed': False, 'actual_external_provider_calls': 0, 'actual_paid_operations': 0})
        bindings.append(binding); original_projects.append(project)
        # Preserve the exact existing fixture and NOT_CONFIGURED histories alongside the new input primitive.
        fixture_request = request.model_copy(update={'provider_mode': 'fixture', 'fixture_acknowledged': True, 'request_key': 'retained-legacy-vision-fixture-' + str(number)})
        row, _ = vision.create(project['id'], fixture_request, actor='explicit-rehearsal-owner'); done = vision.process(project=project['id'], identity=row['vision_id'], fingerprint=row['request_fingerprint'])
        assert done['status'] == 'succeeded'; histories.append(vision.get(project['id'], row['vision_id']))
        official_request = request.model_copy(update={'request_key': 'retained-legacy-vision-official-' + str(number)})
        row, _ = vision.create(project['id'], official_request, actor='explicit-rehearsal-owner')
        assert row['status'] == 'not_configured' and row['result'] is None; histories.append(vision.get(project['id'], row['vision_id']))
        assert store.get(project['id']) == before
    assert len(wire) == 2 and [v['frame_count'] for v in wire] == [1, 8]
    write(out / 'input-bindings.json', bindings); write(out / 'provider-contracts.json', contracts); write(out / 'mock-wire-summary.json', wire)
    write(out / 'expected-projects.json', original_projects); write(out / 'frame-jobs.json', frame_jobs)
    write(out / 'expected-legacy-vision-history.json', histories); write(out / 'expected-journals.json', journals(store))
    backup = create_backup(config, out / 'public-vision-frame-input.zip'); write(out / 'backup.json', backup)
    write(out / 'restore.json', restore_backup(out / 'public-vision-frame-input.zip', restored, expected_sha256=backup['sha256']))
    reopen(args)
    sources = ('services/windows_native/vision_frame_bridge.py', 'services/windows_native/tests/test_vision_frame_bridge.py',
        'apps/api/app/openai_vision_provider.py', 'apps/api/tests/test_vision_multi_niche.py', 'scripts/north_star_vision_frame_bridge.py')
    write(out / 'evidence.json', {'schema_version': 'native-vision-frame-input-rehearsal-v1', 'source_sha256': {name: file_sha(ROOT / name) for name in sources},
        'projects': 2, 'cpu_media_frame_jobs': 2, 'actual_sampled_png_frames': 9, 'mock_structured_requests': 2,
        'original_image_dimensions': [3840, 2160], 'original_video_dimensions': [640, 360],
        'actual_input_frame_dimensions': [[b['vision_input_metadata']['width'], b['vision_input_metadata']['height']] for b in bindings],
        'legacy_vision_histories': 4, 'journal_count': len(journals(store)), 'source_project_and_timeline_exact': True,
        'real_secret_reads': 0, 'external_provider_calls': 0, 'paid_operations': 0, 'real_publications': 0,
        'semantic_inference_performed': False, 'continuous_tracking_performed': False, 'decoded_pts_verified': False,
        'native_official_runtime_integrated': False, 'browser_owner_real_provider_acceptance': False,
        'exports': {p.name: {'sha256': file_sha(p), 'bytes': p.stat().st_size} for p in out.iterdir() if p.is_file()}})
    print(json.dumps({'status': 'PASS', 'projects': 2, 'actual_png_frames': 9, 'mock_requests': 2, 'legacy_histories': 4, 'external_calls': 0}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--state-root', type=Path); parser.add_argument('--restore-root', type=Path, required=True)
    parser.add_argument('--new-process', action='store_true'); args = parser.parse_args()
    if args.new_process: reopen(args)
    else: run(args)
