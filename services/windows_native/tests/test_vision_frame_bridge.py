"""Real Native PNG pixels and explicit structured HTTP mocks; no paid inference."""
import asyncio, base64, copy, hashlib, json, os, subprocess, sys, unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
import httpx

from services.windows_native.tests import test_vision as fixture
from services.windows_native.contracts import WorkflowError, digest
from services.windows_native.media_frame_analysis import frame_path, view
from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor
from services.windows_native.media import ingest_media
from services.windows_native.pipeline import Pipeline
from services.windows_native.vision_models import NativeVisionRequest
from app.auto_edit_models import MediaMetadata
from app.openai_vision_provider import OpenAIVisionProvider


def response_payload(count):
    frames = []
    for index in range(count):
        frames.append({'frame_index': index, 'caption': '[EXPLICIT HTTP MOCK] Minh họa AI educational short.',
            'scene_description': '[EXPLICIT HTTP MOCK] Generic educational frame, no real semantic inference.',
            'semantic_label': 'explicit_ai_education_mock', 'environment': 'explicit_mock', 'action': 'explicit_mock',
            'objects': [], 'ocr': [], 'primary_subject_box': None, 'saliency_box': None, 'headroom_ratio': .1,
            'visual_balance_score': .5, 'safe_crop': False, 'quality_score': .5, 'black_frame': False,
            'blur_score': .2, 'overexposed': False, 'underexposed': False, 'low_resolution': False,
            'watermark_or_logo_detected': False, 'frozen_or_duplicate': False,
            'quality_issues': ['explicit_mock_not_inferred'], 'confidence': .5})
    return {'id': 'resp_native_explicit_mock', 'status': 'completed', 'model': 'gpt-5-mini',
        'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps({'frames': frames}, ensure_ascii=False)}]}],
        'usage': {'input_tokens': 120, 'input_tokens_details': {'cached_tokens': 20}, 'output_tokens': 80}}


class NativeVisionFrameBridgeTests(unittest.TestCase):
    setUp = fixture.NativeVisionTests.setUp
    tearDown = fixture.NativeVisionTests.tearDown
    payload = fixture.NativeVisionTests.payload

    def source(self):
        return self.service.sources(self.project, self.payload())[0]

    def bridge(self, source=None):
        return NativeEvidenceFrameExtractor(self.root, self.config, self.project['id'], self.source() if source is None else source)

    def extract(self, bridge, **changes):
        from services.windows_native.media_frame_analysis import checked_path
        arguments = {'metadata': bridge.input_metadata(), 'scenes': [], 'asset_id': bridge.source['asset']['id'], 'sample_interval_seconds': 1}
        arguments.update(changes)
        return asyncio.run(bridge.extract(checked_path(self.config, bridge.source['asset']), **arguments))

    def test_real_mounted_png_original_and_input_metadata_binding_no_mutation_or_inference(self):
        original = self.store.get(self.project['id']); source = self.source(); bridge = self.bridge(source)
        source['asset']['title'] = 'caller mutation cannot change the frozen snapshot'
        frames = self.extract(bridge); binding = bridge.binding()
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].payload, frame_path(self.root, self.frames['observations'][0]['frames'][0]).read_bytes())
        self.assertEqual(hashlib.sha256(frames[0].payload).hexdigest(), frames[0].sha256)
        self.assertEqual(binding['source_sha256'], bridge.source['asset']['sha256'])
        self.assertEqual(binding['original_source_metadata'], bridge.source['source_media'])
        self.assertEqual(binding['vision_input_metadata']['detected_content_type'], 'image/png')
        self.assertEqual(binding['vision_input_metadata']['width'], binding['source_frame_evidence'][0]['width'])
        self.assertIsNone(binding['decoded_pts_seconds'])
        self.assertFalse(binding['semantic_inference_performed']); self.assertFalse(binding['continuous_tracking_performed'])
        self.assertFalse(binding['frozen_video_detection_performed']); self.assertEqual(binding['external_provider_calls'], 0)
        self.assertEqual(self.store.get(self.project['id']), original); self.assertEqual(view(self.store, self.project['id']), self.frames)

    def test_request_source_metadata_asset_scenes_and_nonfinite_interval_refuse(self):
        bridge = self.bridge()
        wrong = bridge.input_metadata().model_copy(update={'width': 999})
        for change in ({'metadata': wrong}, {'asset_id': 'foreign'}, {'sample_interval_seconds': 0},
            {'sample_interval_seconds': True}, {'sample_interval_seconds': float('inf')}, {'sample_interval_seconds': float('nan')}):
            with self.subTest(change=list(change)), self.assertRaisesRegex(WorkflowError, 'INPUT_REQUEST_INVALID'):
                self.extract(bridge, **change)
        self.assertEqual(len(self.extract(bridge, metadata=MediaMetadata.model_validate(bridge.source['source_media']))), 1)
        with self.assertRaisesRegex(WorkflowError, 'INPUT_REQUEST_INVALID'):
            asyncio.run(bridge.extract(Path('C:/unmounted-native-frame-source'), metadata=bridge.input_metadata(), scenes=[],
                asset_id=bridge.source['asset']['id'], sample_interval_seconds=1))

    def test_physical_source_or_frame_corruption_rejects_before_any_payload(self):
        bridge = self.bridge(); frame = self.frames['observations'][0]['frames'][0]
        frame_path(self.root, frame).write_bytes(b'EXPLICIT CORRUPTED PUBLIC PNG')
        with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): self.extract(bridge)

    def test_original_source_corruption_or_root_mutation_rejects(self):
        bridge = self.bridge()
        from services.windows_native.media_frame_analysis import checked_path
        path = checked_path(self.config, bridge.source['asset']); path.write_bytes(b'EXPLICIT CORRUPTED OWNED SOURCE')
        with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): bridge.binding()

    def test_rehashed_observation_cannot_fake_decoded_pixels_or_png_dimensions(self):
        for field, value in [('decoded_pixels_sha256', 'f' * 64), ('width', 479)]:
            source = self.source(); source['source_observation']['observation']['frames'][0][field] = value
            source['source_observation']['sha256'] = digest(source['source_observation']['observation'])
            bridge = self.bridge(source)
            with self.subTest(field=field), self.assertRaisesRegex(WorkflowError, 'FRAME_INPUT_INVALID'): self.extract(bridge)

    def test_frozen_source_project_root_bound_and_input_limits_cannot_drift(self):
        for change in (lambda b: setattr(b, 'root', self.root / 'other'), lambda b: setattr(b, 'project_id', 'f' * 32),
            lambda b: setattr(b, 'max_frames', 2), lambda b: setattr(b, 'max_image_bytes', 100000000),
            lambda b: b.source['source_observation']['observation']['frames'][0].update(timestamp_seconds=1)):
            bridge = self.bridge(); change(bridge)
            with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): bridge.binding()

    def test_source_snapshot_schema_magic_dimensions_and_transcript_reference_refuse(self):
        for change in (lambda s: s.update(extra=True), lambda s: s['source_media'].update(width=321),
            lambda s: s['source_media'].update(detected_content_type='image/png' if s['source_media']['detected_content_type']=='image/jpeg' else 'image/jpeg'),
            lambda s: s.update(transcript_ref={'transcript_id': 'explicit', 'version': True, 'sha256': 'a' * 64})):
            source = self.source(); change(source)
            with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): self.bridge(source)

    def test_valid_transcript_version_is_bound_without_claiming_current_live_authority(self):
        source = self.source(); source['transcript_ref'] = {'transcript_id': 'explicit-transcript-version', 'version': 2, 'sha256': 'a' * 64}
        bridge = self.bridge(source); self.assertEqual(bridge.binding()['transcript_ref'], source['transcript_ref'])
        bridge.source['transcript_ref']['version'] = 3
        with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): bridge.binding()

    def test_hard_linked_source_or_frame_refuses(self):
        bridge = self.bridge(); frame = self.frames['observations'][0]['frames'][0]
        os.link(frame_path(self.root, frame), Path(self.temp.name) / 'owned-link-to-frame.png')
        with self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): self.extract(bridge)

    def test_late_original_source_drift_rechecks_after_decoding(self):
        bridge = self.bridge()
        from services.windows_native.media_frame_analysis import checked_path
        path = checked_path(self.config, bridge.source['asset']); original = Image.Image.load; changed = False
        def load(image, *args, **kwargs):
            nonlocal changed
            value = original(image, *args, **kwargs)
            if not changed:
                changed = True; path.write_bytes(b'EXPLICIT LATE OWNED SOURCE DRIFT')
            return value
        with patch.object(Image.Image, 'load', load), self.assertRaisesRegex(WorkflowError, 'INPUT_BINDING_INVALID'): self.extract(bridge)

    def test_existing_api_adapter_receives_exact_native_png_and_preserves_structured_references(self):
        bridge = self.bridge(); calls = []; before = self.store.get(self.project['id'])
        def handler(request):
            body = json.loads(request.content); calls.append(body)
            self.assertFalse(body['store'])
            inputs = body['input'][0]['content']; images = [v for v in inputs if v['type'] == 'input_image']
            payload = base64.b64decode(images[0]['image_url'].split(',', 1)[1], validate=True)
            self.assertEqual(hashlib.sha256(payload).hexdigest(), bridge.binding()['source_frame_evidence'][0]['sha256'])
            self.assertNotIn('real-estate', inputs[0]['text'])
            return httpx.Response(200, json=response_payload(bridge.max_frames))
        provider = OpenAIVisionProvider(credential_alias='explicit-synthetic-native-vision', credential_resolver=lambda _: 'contract-key-not-real',
            frame_extractor=bridge, transport=httpx.MockTransport(handler), allow_zero_cost_contract_test=True)
        from services.windows_native.media_frame_analysis import checked_path
        result = asyncio.run(provider.analyze(checked_path(self.config, bridge.source['asset']), metadata=bridge.input_metadata(), scenes=[],
            asset_id=bridge.source['asset']['id'], checksum_sha256=bridge.source['asset']['sha256'], sample_interval_seconds=1))
        self.assertEqual(len(calls), 1); self.assertTrue(result.provenance['mock_tested']); self.assertFalse(result.provenance['real_provider_tested'])
        self.assertEqual(result.frames[0].evidence_frame_reference, bridge.binding()['source_frame_evidence'][0]['reference'])
        self.assertEqual(result.provenance['source_checksum'], bridge.source['asset']['sha256'])
        self.assertEqual(result.frames[0].semantic_label, 'explicit_ai_education_mock')
        self.assertEqual(self.store.get(self.project['id']), before)
        pending, _ = self.service.create(self.project['id'], self.payload(provider_mode='official', fixture_acknowledged=False), actor='fixture-owner')
        self.assertEqual(pending['status'], 'not_configured'); self.assertIsNone(pending['result'])

    def test_4k_original_dimensions_remain_honest_while_actual_provider_input_is_bounded(self):
        source = Path(self.temp.name) / 'explicit-owned-large-image.png'; Image.new('RGB', (3840, 2160), (42, 137, 242)).save(source)
        asset = ingest_media(self.config, source, 'image/png', 'Explicit technology educational test', rights_confirmed=True, illustration=True)
        project = self.store.create('Technology profile large owned frame', '', 'media')
        project = self.store.append_media(project['id'], project['revision'], asset)
        job = self.store.enqueue(project['id'], project['revision'], 'media_frames', 'native-owned-large-frame-evidence'); job = self.store.claim()
        result = Pipeline(self.config).run(job, lambda _: None); self.store.finish(job, result=result); project = self.store.get(project['id'])
        frames = view(self.store, project['id']); request = NativeVisionRequest(revision=project['revision'], observation_ids=[frames['observations'][0]['observation_id']], request_key='large-native-frame-source-binding')
        bridge = NativeEvidenceFrameExtractor(self.root, self.config, project['id'], self.service.sources(project, request)[0])
        binding = bridge.binding(); self.assertEqual(binding['original_source_metadata']['width'], 3840)
        self.assertEqual(binding['original_source_metadata']['height'], 2160); self.assertEqual(binding['vision_input_metadata']['width'], 480)
        self.assertEqual(binding['vision_input_metadata']['height'], 270)
        from services.windows_native.media_frame_analysis import checked_path
        payload = asyncio.run(bridge.extract(checked_path(self.config, asset), metadata=bridge.input_metadata(), scenes=[], asset_id=asset['id'], sample_interval_seconds=1))
        self.assertEqual(len(payload), 1); self.assertEqual(bridge.binding(), binding)

    def test_bridge_imports_without_api_framework_database_or_gpu(self):
        source = "from services.windows_native.vision_frame_bridge import NativeEvidenceFrameExtractor; import sys; assert not any(n.startswith(('sqlalchemy','fastapi','torch','vieneu')) for n in sys.modules)"
        subprocess.run([sys.executable, '-c', source], check=True, capture_output=True, timeout=30)

    def test_actual_video_eight_seek_samples_use_same_adapter_without_new_decode_or_timeline_change(self):
        source = Path(self.temp.name) / 'explicit-owned-two-second-video.mp4'
        subprocess.run([str(self.config.ffmpeg_bin / 'ffmpeg.exe'), '-v', 'error', '-nostdin', '-n', '-f', 'lavfi',
            '-i', 'testsrc2=size=640x360:rate=24:duration=2', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(source)],
            check=True, capture_output=True, timeout=30)
        asset = ingest_media(self.config, source, 'video/mp4', 'Explicit technology owned video fixture', rights_confirmed=True, illustration=False)
        project = self.store.create('Technology same engine eight-frame video', '', 'media')
        project = self.store.append_media(project['id'], project['revision'], asset)
        job = self.store.enqueue(project['id'], project['revision'], 'media_frames', 'native-owned-eight-frame-evidence'); job = self.store.claim()
        output = Pipeline(self.config).run(job, lambda _: None); self.store.finish(job, result=output); project = self.store.get(project['id'])
        frames = view(self.store, project['id']); request = NativeVisionRequest(revision=project['revision'], observation_ids=[frames['observations'][0]['observation_id']], request_key='eight-native-frame-source-binding')
        bridge = NativeEvidenceFrameExtractor(self.root, self.config, project['id'], self.service.sources(project, request)[0])
        calls = []
        def handler(request):
            body = json.loads(request.content); calls.append(body)
            images = [item for item in body['input'][0]['content'] if item['type'] == 'input_image']
            self.assertEqual(len(images), 8)
            self.assertEqual([hashlib.sha256(base64.b64decode(item['image_url'].split(',', 1)[1], validate=True)).hexdigest() for item in images],
                [item['sha256'] for item in bridge.binding()['source_frame_evidence']])
            return httpx.Response(200, json=response_payload(8))
        provider = OpenAIVisionProvider(credential_alias='explicit-synthetic-native-vision', credential_resolver=lambda _: 'contract-key-not-real',
            frame_extractor=bridge, transport=httpx.MockTransport(handler), allow_zero_cost_contract_test=True)
        from services.windows_native.media_frame_analysis import checked_path
        with patch('services.windows_native.source_render.command_run', side_effect=AssertionError('No second media decode')):
            result = asyncio.run(provider.analyze(checked_path(self.config, asset), metadata=bridge.input_metadata(), scenes=[],
                asset_id=asset['id'], checksum_sha256=asset['sha256'], sample_interval_seconds=1))
        self.assertEqual(len(calls), 1); self.assertEqual(len(result.frames), 8)
        self.assertEqual([(item.timestamp_seconds, item.evidence_frame_reference) for item in result.frames],
            [(item['timestamp_seconds'], item['reference']) for item in bridge.binding()['source_frame_evidence']])
        self.assertEqual(bridge.binding()['original_source_metadata']['media_kind'], 'video')
        self.assertEqual(bridge.binding()['vision_input_metadata']['media_kind'], 'image')
        self.assertEqual(self.store.get(project['id']), project)
